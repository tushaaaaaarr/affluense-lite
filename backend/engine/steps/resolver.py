"""Same person, different spellings. Plain code first, and we are careful about merging.

Rule of thumb: wrongly merging two people is WORSE than leaving a duplicate, because an RM
would call the wrong person with the wrong story. So when unsure we do NOT merge; we mark
the two as "possible match" and lower the confidence.
"""
import re
from difflib import SequenceMatcher

TITLES = {"mr", "mrs", "ms", "dr", "shri", "smt", "sh", "prof", "late"}
# includes Indian legal forms seen in real filings: HUF (Hindu Undivided Family), Society, Trust
ORG_WORDS = {"limited", "ltd", "llp", "llc", "fund", "funds", "holdings", "trust", "capital",
             "partners", "pte", "inc", "corporation", "corp", "bank", "insurance", "investments",
             "ventures", "mauritius", "fii", "fdi", "company", "private", "pvt", "board",
             "authority", "group", "services", "management", "equity", "huf", "society",
             "foundation", "association", "institute", "university", "enterprises", "industries"}


def tokens(name):
    words = re.findall(r"[a-z]+", (name or "").lower())
    return [w for w in words if w not in TITLES]


def is_org(name):
    return any(w in ORG_WORDS for w in tokens(name))


def _initials_ok(a, b):
    """'R K Sharma' vs 'Rajesh Kumar Sharma': last names equal and every initial lines up."""
    if not a or not b or a[-1] != b[-1]:
        return False
    # the 'short' one is the one with fewer letters overall (initials), not fewer words
    short, long_ = (a, b) if len(''.join(a)) <= len(''.join(b)) else (b, a)
    rest_long = long_[:-1]
    for i, w in enumerate(short[:-1]):
        if i >= len(rest_long):
            return False
        if not (rest_long[i] == w or (len(w) == 1 and rest_long[i].startswith(w))):
            return False
    return True


def compare(name_a, name_b):
    """Returns 'same', 'maybe' or 'different'."""
    a, b = tokens(name_a), tokens(name_b)
    if not a or not b:
        return "different"
    if sorted(a) == sorted(b):
        return "same"                                   # same words, maybe reordered
    ratio = SequenceMatcher(None, " ".join(a), " ".join(b)).ratio()
    if is_org(name_a) != is_org(name_b):
        return "different"
    # Two full first names that clearly differ are two people, even with the same middle and last
    # name: "Atul Hiralal Shah" vs "Bakul Hiralal Shah" are brothers (Hiralal = father's name).
    if (not is_org(name_a) and len(a[0]) > 1 and len(b[0]) > 1
            and SequenceMatcher(None, a[0], b[0]).ratio() < 0.8):
        return "different"
    if ratio >= 0.93 and a[-1] == b[-1]:
        return "same"                                   # one-letter typo
    if _initials_ok(a, b):
        return "maybe"                                  # could be the same, could be a cousin
    if ratio >= 0.80:
        return "maybe"
    return "different"


def merge(people):
    """people: list of dicts with name/evidence. Returns merged list."""
    merged = []
    for p in people:
        p.setdefault("aliases", [])
        p.setdefault("possible_matches", [])
        home = None
        for m in merged:
            verdict = compare(p["name"], m["name"])
            if verdict == "same":
                home = m
                break
            if verdict == "maybe":
                m["possible_matches"].append(p["name"])
                p["possible_matches"].append(m["name"])
        if home is None:
            merged.append(p)
            continue
        # fold p into home
        if p["name"] != home["name"]:
            home["aliases"].append(p["name"])
        home["evidence"].extend(p["evidence"])
        for f in ("shares", "amount_inr", "role"):
            if home.get(f) is None and p.get(f) is not None:
                home[f] = p[f]
    return merged
