"""Writes the markdown + json report for one event."""
import json
import re

from engine.shared import config


def crore(x):
    return f"₹{x / 1e7:,.1f} cr"


def _range(a):
    if a["low"] is None:
        return "not estimable"
    if a["low"] == a["high"]:
        return f"{crore(a['high'])} (exact figure stated in source)"
    return f"{crore(a['low'])} to {crore(a['high'])} (estimate)"


def write(result):
    slug = re.sub(r"[^a-z0-9]+", "-", result["event"].lower()).strip("-")
    folder = config.OUT_DIR / slug
    folder.mkdir(exist_ok=True)
    c = result["cost"]
    shared, own = result["per_person"]
    n = len(result["people"]) + len(result["institutions"])
    ev = result["event_info"]
    lines = [f"# {result['event']}", "",
             f"Run cost: ${c['cost_usd']} | LLM calls: {c['calls']} ({c['cached_calls']} cached) | "
             f"time: {result['wall_seconds']}s | model: {config.MODEL}", ""]

    if ev.get("price_low") is not None:
        lines.append(f"- **Price:** ₹{ev['price_low']:,g} to ₹{ev['price_high']:,g} - "
                     f"{ev['price_url']}: \"{ev['price_quote']}\"")
    if ev.get("date"):
        lines.append(f"- **Date:** {ev['date']} - {ev['date_url']}: \"{ev['date_quote']}\"")
    lines.append("")

    # the short list the Head of RMs asked for, details below
    if result["people"]:
        lines += ["| # | Name | Why they got money | Rough amount | Timing | Confidence |",
                  "|---|---|---|---|---|---|"]
        for i, p in enumerate(result["people"], 1):
            lines.append(f"| {i} | {p['name']} | {p.get('link')} | {_range(p['amount'])} | "
                         f"{p['timing']['status']} | {p['confidence']} |")
        lines.append("")
    else:
        lines += ["**No individuals found with verified evidence.** See run notes below.", ""]

    for i, p in enumerate(result["people"], 1):
        lines += [f"## {i}. {p['name']} - {p.get('role') or 'role not stated in quote'}",
                  f"- **Why they got money:** {p.get('link')}",
                  f"- **Rough amount:** {_range(p['amount'])}",
                  f"  - working: {p['amount']['working']}",
                  f"- **Timing:** {p['timing']['text']}",
                  f"- **Confidence (right person):** {p['confidence']} - {'; '.join(p['confidence_why'])}",
                  f"- **Score:** {p['score']}"]
        if p.get("aliases"):
            lines.append(f"- **Also written as:** {', '.join(p['aliases'])}")
        if p.get("earlier_events"):
            lines.append("- **Also seen in earlier runs:** " +
                         ", ".join(f"{h['event']} ({h['match']} match: {h['name_there']})"
                                   for h in p["earlier_events"]))
        lines.append("- **Evidence:**")
        for e in p["evidence"]:
            pg = f" (page {e['page']})" if e.get("page") else ""
            lines.append(f"  - {e['url']}{pg}: \"{e['quote']}\"")
        if p.get("follow_on"):
            lines.append("- **Earlier deals found on the web (verified quotes, different event):**")
            for e in p["follow_on"]:
                lines.append(f"  - {e['url']}: \"{e['quote']}\"")
        elif p.get("lead_urls") is not None:
            lines.append("- **Web follow-on:** searched, nothing verified")
        lines.append(f"- **Cost for this person:** ${own.get(p['name'], 0) + (shared / n if n else 0):.4f}")
        lines += ["- **RM brief** (" + p["brief_by"] + "):", "", "  > " + p["brief"].replace("\n", "\n  > "), ""]

    if result["institutions"]:
        lines += ["## Institutional sellers (organisations, not people to call directly)", ""]
        for o in result["institutions"]:
            lines.append(f"- {o['name']}: {o.get('link')}, {_range(o['amount'])} - "
                         f"{o['evidence'][0]['url']}")
        lines.append("")

    if result["notes"]:
        lines += ["## Run notes (things that went wrong or were dropped)", ""]
        lines += [f"- {n}" for n in result["notes"]]

    (folder / "report.md").write_text("\n".join(lines), encoding="utf-8")
    (folder / "report.json").write_text(json.dumps(result, indent=2, default=str, ensure_ascii=False),
                                        encoding="utf-8")
    return folder / "report.md"
