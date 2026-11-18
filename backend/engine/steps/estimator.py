"""Turns verified facts into a rupee RANGE + timing. Plain arithmetic, no LLM.

Rules:
- If the source states the amount -> a range around it: rounded news figures ("Rs 120 crore")
  and USD conversions get +/-ROUNDED_BAND; an exact filing figure stays exact.
- Else if we have shares AND a price (both verified) -> shares x price band.
- Else -> no number at all. We say "not estimable" instead of guessing.
Every number comes with a 'working' string so an RM (or I) can check it.
"""
import re
from datetime import date

from dateutil import parser as dateparser

from engine.shared import config


def crore(x):
    return f"₹{x / 1e7:,.1f} cr"


def is_rounded(person):
    """'120 crore' has 2 significant digits -> rounded. '12,34,56,789' has 9 -> exact."""
    words = person.get("amount_text") or str(int(person["amount_inr"]))
    m = re.search(r"\d[\d,]*\.?\d*", words)
    digits = re.sub(r"\D", "", m.group(0)).strip("0") if m else ""
    return len(digits) <= 3


def estimate_amount(person, event):
    if person.get("amount_inr"):
        a = person["amount_inr"]
        why = []
        if is_rounded(person):
            why.append("the source gives a rounded figure")
        if person.get("amount_note"):
            why.append(person["amount_note"])
        if not why:
            return {"low": a, "high": a, "kind": "stated",
                    "working": f"source states the exact figure {crore(a)} (see evidence quote), "
                               f"so no range is needed"}
        band = config.ROUNDED_BAND
        return {"low": a * (1 - band), "high": a * (1 + band), "kind": "estimate",
                "working": f"source states {crore(a)}; {'; '.join(why)}, so shown "
                           f"+/-{band:.0%} = {crore(a * (1 - band))} to {crore(a * (1 + band))} "
                           f"(the +/-{band:.0%} is my assumption)"}

    shares = person.get("shares")
    lo_p, hi_p = event.get("price_low"), event.get("price_high")
    if shares and lo_p and hi_p:
        low, high = shares * lo_p, shares * hi_p
        if person.get("link") == "esop":
            note = "value of ESOP shares held, at the offer price; not cash unless they sell"
        else:
            note = "gross proceeds, before tax and fees"
        if "up to" in (person.get("quote") or "").lower():
            low = low * config.UP_TO_FACTOR
            note += (f"; source says 'up to', so low end uses {int(config.UP_TO_FACTOR*100)}% "
                     f"of shares (my assumption)")
        price_src = f" [price from {event['price_url']}]" if event.get("price_url") else ""
        return {"low": low, "high": high, "kind": "estimate",
                "working": f"{shares:,} shares x ₹{lo_p:,.0f}-₹{hi_p:,.0f} = "
                           f"{crore(low)} to {crore(high)} ({note}){price_src}"}

    return {"low": None, "high": None, "kind": "none",
            "working": "source gives no share count or amount; not estimated"}


def _read_date(d):
    """'20 January 2026' -> date. A range like '4 to 6 Mar, 2026' -> its LAST day, because
    sale proceeds can't arrive before the offer closes."""
    try:
        return dateparser.parse(d, dayfirst=True).date(), ""
    except Exception:
        pass
    last = re.split(r"\s+to\s+|\s*[–-]\s*", d)[-1]
    try:
        return dateparser.parse(last, dayfirst=True).date(), f" (last day of '{d}')"
    except Exception:
        return None, ""


def estimate_timing(person, event):
    d = event.get("date")
    if not d or not event.get("date_quote"):
        return {"status": "unknown", "text": "No dated source; check settlement date"}
    when, how = _read_date(d)
    if when is None:
        return {"status": "unknown", "text": f"Could not read date '{d}'"}
    if person.get("link") == "esop":
        return {"status": "unknown", "text": "ESOP payouts follow their own vesting/exercise rules"}
    src = f" [date from {event['date_url']}]" if event.get("date_url") else ""
    if when <= date.today():
        return {"status": "now", "text": f"Event dated {when:%d %b %Y}{how}; cash likely already received{src}"}
    return {"status": "later", "text": f"Event dated {when:%d %b %Y}{how}; cash expected after this{src}"}
