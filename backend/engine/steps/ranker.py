"""Confidence + ranking. Plain code. The formula is on purpose simple so I can explain it.

Confidence = "are we sure this is the right person and the right link to the event?"
It is NOT about the amount. Amount uncertainty is already shown by the range width.
"""
import math

TIMING_SCORE = {"now": 1.0, "later": 0.6, "unknown": 0.3}


def confidence(person, n_sources):
    score, why = 0.5, ["named with a verified quote in a source"]
    if n_sources >= 2:
        score += 0.2
        why.append(f"{n_sources} separate sources")
    if person.get("role"):
        score += 0.1
        why.append("role stated")
    if person.get("aliases"):
        score -= 0.05
        why.append("name matched across spellings")
    if person.get("possible_matches"):
        score -= 0.2
        why.append("could be confused with: " + ", ".join(person["possible_matches"]))
    if person.get("is_org"):
        score = min(score, 0.4)
        why.append("this is an organisation, not a person; need the human behind it")
    return round(max(0.05, min(score, 0.95)), 2), why


def rank_score(person):
    amt = person["amount"]["high"] or 0
    # log scale so a 500 cr seller doesn't totally drown a 5 cr seller
    amount_part = min(math.log10(amt / 1e6 + 1) / 4, 1.0) if amt else 0.0
    timing_part = TIMING_SCORE[person["timing"]["status"]]
    return round(0.5 * amount_part + 0.3 * person["confidence"] + 0.2 * timing_part, 4)
