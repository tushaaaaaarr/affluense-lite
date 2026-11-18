"""Scores a run against hand-checked answer keys in backend/benchmarks/.

An answer key lists every seller a filing names, with offered shares, checked by hand against
the filing itself. A run is scored only when it read that filing, so the numbers are like for like.
"""
import json
import re

from engine.shared import config
from engine.steps import resolver

KEYS_DIR = config.ROOT / "benchmarks"


def _norm(name):
    name = re.sub(r"\(.*?\)", " ", name or "")          # drops "(represented by ...)"
    return re.sub(r"[^a-z0-9]", "", name.lower())       # PDF text often splits words: "Him anshu"


def load_keys():
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(KEYS_DIR.glob("*.json"))]


def key_for(result):
    urls = {e.get("url", "").lower()
            for p in (result.get("people") or []) + (result.get("institutions") or [])
            for e in p.get("evidence") or []}
    return next((k for k in load_keys() if k["source_url"].lower() in urls), None)


def _find(name, candidates):
    want = _norm(name)
    for p in candidates:
        got = _norm(p["name"])
        if got == want or (min(len(got), len(want)) > 10 and (got.startswith(want) or want.startswith(got))):
            return p
    return next((p for p in candidates if resolver.compare(name, p["name"]) == "same"), None)


def _rate(n, d):
    return round(n / d, 3) if d else None


def score(result, key):
    people = result.get("people") or []
    orgs = result.get("institutions") or []
    org_ids = {id(p) for p in orgs}
    used = {}                                             # id(predicted) -> answer-key name
    groups, misrouted, share_rows = {}, [], []

    for group, expect_org in (("individuals", False), ("institutions", True)):
        found, missed = [], []
        for entry in key[group]:
            hit = _find(entry["name"], [p for p in people + orgs if id(p) not in used])
            if hit is None:
                missed.append(entry["name"])
                continue
            used[id(hit)] = entry["name"]
            found.append(entry["name"])
            if (id(hit) in org_ids) != expect_org:
                misrouted.append(entry["name"])
            if entry.get("shares") is not None:
                share_rows.append({"name": entry["name"], "expected": entry["shares"], "got": hit.get("shares")})
        groups[group] = {"found": len(found), "expected": len(key[group]), "missed": missed}

    claimed = [p for p in people + orgs if p.get("link") == key["link"]]
    false_positives = [p["name"] for p in claimed if id(p) not in used]
    exact = [r for r in share_rows if r["got"] == r["expected"]]
    found_total = sum(g["found"] for g in groups.values())
    expected_total = sum(g["expected"] for g in groups.values())
    return {
        "name": key["name"],
        "source_url": key["source_url"],
        "checked_against": key["checked_against"],
        "recall": {"found": found_total, "expected": expected_total, "rate": _rate(found_total, expected_total)},
        "precision": {"correct": len(claimed) - len(false_positives), "claimed": len(claimed),
                      "rate": _rate(len(claimed) - len(false_positives), len(claimed)),
                      "false_positives": false_positives},
        "individuals": groups["individuals"],
        "institutions": groups["institutions"],
        "routing": {"correct": found_total - len(misrouted), "checked": found_total, "misrouted": misrouted},
        "shares": {"exact": len(exact), "checked": len(share_rows),
                   "mismatches": [r for r in share_rows if r["got"] != r["expected"]]},
        "other_leads": [p["name"] for p in people + orgs if id(p) not in used and p.get("link") != key["link"]],
    }


def for_result(result):
    key = key_for(result)
    return score(result, key) if key else None
