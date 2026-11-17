"""Step 7: writes the 3-4 line RM brief for each person.

One model call writes the notes for a whole batch of people (up to BRIEF_BATCH). One call per
person blew through the Gemini free tier's 20 requests/day on a single IPO.
The model only sees the verified facts and is told not to add any. Then plain code checks each
note against THAT person's facts only: any number not in them, or a missing/cut-off note, and we
use a boring template instead.
"""
from engine.shared import config, costlog, llm
from engine.steps import verify
from engine.steps.estimator import crore
from engine.steps.extractor import parse_json

SYSTEM = """You write short call-prep notes for a wealth relationship manager, one per person.
Use ONLY the facts given for that person. Do not add numbers, names, or claims not in their facts.
3-4 short lines each. Say how sure we are. No contact details. No flattery.
Return JSON only: {"briefs": [{"id": 1, "brief": "..."}]}"""


def template_brief(p, event_name):
    amt = p["amount"]
    if amt["low"] is None:
        amount_txt = "Amount not known from public sources"
    elif amt["low"] == amt["high"]:
        amount_txt = f"Source states {crore(amt['high'])}"
    else:
        amount_txt = f"Estimated {crore(amt['low'])} to {crore(amt['high'])}"
    return (f"{p['name']} ({p.get('role') or 'role not stated'}) is linked to {event_name}: "
            f"{p.get('link', 'other')}.\n{amount_txt}.\nTiming: {p['timing']['text']}.\n"
            f"Confidence {p['confidence']:.2f}.")


def _facts(p, event_name):
    return (f"Event: {event_name}\nName: {p['name']}\nRole: {p.get('role')}\n"
            f"Link to event: {p.get('link')}\nAmount: {p['amount']['working']}\n"
            f"Timing: {p['timing']['text']}\nConfidence: {p['confidence']} "
            f"({'; '.join(p['confidence_why'])})")


def _check(text, facts, p, event_name):
    if not text:
        return template_brief(p, event_name), "template (model reply missing or cut off)"
    allowed = verify.numbers_in(facts)
    if any(n not in allowed for n in verify.numbers_in(text)):
        return template_brief(p, event_name), "template (model added a number)"
    return text, "llm"


def write_briefs(persons, event_name):
    """Returns ([(brief, how_made), ...] in the same order as persons, [problem notes])."""
    results, notes = [], []
    for start in range(0, len(persons), config.BRIEF_BATCH):
        batch = persons[start:start + config.BRIEF_BATCH]
        facts = {i: _facts(p, event_name) for i, p in enumerate(batch, 1)}
        prompt = "\n\n".join(f"### id {i}\n{f}" for i, f in facts.items())
        try:
            raw = llm.ask(SYSTEM, prompt, stage="brief", event=event_name, max_tokens=6000)
            got = {int(b["id"]): (b.get("brief") or "").strip() for b in parse_json(raw)["briefs"]}
        except costlog.BudgetError as e:          # $ cap or daily quota: no more model calls
            notes.append(str(e))
            results += [(template_brief(p, event_name), "template (budget or quota hit)") for p in persons[start:]]
            break
        except Exception as e:                    # bad JSON or API hiccup: this batch gets templates
            notes.append(f"briefs for {len(batch)} people failed: {e}")
            got = {}
        results += [_check(got.get(i, ""), facts[i], p, event_name) for i, p in enumerate(batch, 1)]
    return results, notes
