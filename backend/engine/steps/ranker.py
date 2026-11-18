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


def confidence_dimensions(person, n_sources):
    identity_score, identity_why = confidence(person, n_sources)
    known_links = {
        "sold_in_offer", "tendered_in_buyback", "sold_to_acquirer", "esop",
        "early_investor", "other",
    }
    transaction_score = 0.62 if person.get("link") in known_links else 0.35
    transaction_why = ["transaction quote passed source verification"]
    if person.get("role"):
        transaction_score += 0.05
        transaction_why.append("role is stated in the evidence quote")
    if n_sources >= 2:
        transaction_score += 0.15
        transaction_why.append(f"transaction corroborated by {n_sources} source URLs")

    amount = person.get("amount") or {}
    amount_kind = amount.get("kind")
    if amount_kind == "stated":
        amount_score, amount_status = 0.95, "source-stated"
    elif amount_kind == "estimate":
        working = (amount.get("working") or "").lower()
        if "assumption" in working or "up to" in working or "rounded" in working:
            amount_score, amount_status = 0.55, "estimated-with-assumption"
        else:
            amount_score, amount_status = 0.75, "calculated-from-source"
    else:
        amount_score, amount_status = None, "not-estimable"

    source_urls = sorted({item["url"] for item in person.get("evidence", []) if item.get("url")})
    return {
        "identity": {"score": identity_score, "reasons": identity_why},
        "transaction": {
            "score": round(min(transaction_score, 0.95), 2),
            "reasons": transaction_why,
        },
        "amount": {"score": amount_score, "status": amount_status},
        "corroboration": {
            "source_count": len(source_urls),
            "independent_sources": len(source_urls) >= 2,
            "source_urls": source_urls,
        },
        "method": "Heuristic indicators; not calibrated probabilities.",
    }


WEIGHTS = {"amount": 0.5, "confidence": 0.3, "timing": 0.2}


def _parts(person):
    amt = person["amount"]["high"] or 0
    # log scale so a 500 cr seller doesn't totally drown a 5 cr seller
    amount_part = min(math.log10(amt / 1e6 + 1) / 4, 1.0) if amt else 0.0
    timing_part = TIMING_SCORE[person["timing"]["status"]]
    return {"amount": WEIGHTS["amount"] * amount_part,
            "confidence": WEIGHTS["confidence"] * person["confidence"],
            "timing": WEIGHTS["timing"] * timing_part}


def rank_score(person):
    return round(sum(_parts(person).values()), 4)


def rank_parts(person):
    """The score split into its three weighted parts, so the UI can explain a rank."""
    return {k: {"points": round(v, 4), "max": WEIGHTS[k]} for k, v in _parts(person).items()}
