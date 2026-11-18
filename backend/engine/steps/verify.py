"""The anti-hallucination part. Plain code, no LLM.

The model has to give us a word-for-word quote with every fact. We check:
  1. the quote really exists in the source text
  2. the person's name is inside the quote
  3. every number we keep is inside the quote. Better still, the model copies the words
     ("up to 2.5 lakh shares", "Rs 120 crore") and CODE turns them into a number, so the
     model never does arithmetic like crore -> rupees.
If a check fails we throw the fact away. A missing number is fine; an invented one is not.
"""
import re

from engine.shared import config

UNITS = {"crore": 1e7, "crores": 1e7, "cr": 1e7, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5,
         "lacs": 1e5, "million": 1e6, "mn": 1e6, "billion": 1e9, "bn": 1e9, "thousand": 1e3}


def _join_split_numbers(s):
    """PDF text can break '30,000' into '30, 000' (a real SEDEMAC row read as 30 shares)."""
    return re.sub(r"(\d),\s+(\d{3})(?!\d)", r"\1,\2", s)


def norm(s):
    s = (s or "").lower()
    s = s.replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    return _join_split_numbers(re.sub(r"\s+", " ", s).strip())


def quote_in_source(quote, source_text):
    q = norm(quote)
    return len(q) >= 15 and q in norm(source_text)


def _canon(num_str):
    """'1,59,69,410' -> '15969410', '512.' -> '512', '420.50' -> '420.5'."""
    s = num_str.replace(",", "").rstrip(".")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def to_number(v):
    """Model output can be 15969410, 15969410.0 or '1,59,69,410'. Returns float or None."""
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def numbers_in(text):
    """All numbers in text in canonical form."""
    return {_canon(n) for n in re.findall(r"\d[\d,]*\.?\d*", _join_split_numbers(text or ""))}


def number_in_text(value, text):
    x = to_number(value)
    if x is None:
        return False
    return _canon(str(int(x)) if x.is_integer() else str(x)) in numbers_in(text)


def parse_quantity(text):
    """'1,59,69,410 equity shares' -> 15969410; '2.5 lakh shares' -> 250000. None if no number.
    For a range like 'Rs 100-120 crore' this returns the LOW end (100 crore)."""
    t = norm(text)
    m = re.search(r"\d[\d,]*\.?\d*", t)
    if not m:
        return None
    value = float(_canon(m.group(0)))
    # only the first word after the number counts, so "... shares aggregating Rs 50 crore"
    # can't turn a share count into crores
    words = re.findall(r"[a-z]+", t[m.end():])
    if words and words[0] in UNITS:
        return value * UNITS[words[0]]
    return value


def parse_money(text):
    """'Rs 120 crore' -> (1.2e9, ''); '$5 million' -> (5e6*USD_INR, 'converted at ...').
    Returns (rupees, note) or (None, reason)."""
    t = norm(text)
    value = parse_quantity(t)
    if value is None:
        return None, "no number in amount text"
    if "$" in t or "usd" in t or "dollar" in t:
        return value * config.USD_INR, f"converted from USD at ₹{config.USD_INR:g}/$ (my assumption)"
    return value, ""


def name_in_quote(name, quote):
    # compare on the longest word of the name so "Mr. R K Sharma" still matches
    words = [w for w in re.findall(r"[a-z]+", norm(name)) if len(w) > 2]
    if not words:
        return False
    return max(words, key=len) in norm(quote)


def check_person(p, source_text):
    """Returns (cleaned_person_or_None, list_of_problems)."""
    problems = []
    quote = p.get("quote") or ""
    if not quote_in_source(quote, source_text):
        return None, ["quote not found in source"]
    if not name_in_quote(p.get("name", ""), quote):
        return None, ["name not inside quote"]
    if p.get("link") == "tendered_in_buyback":
        normalized_quote = norm(quote)
        mentions_buyback = any(term in normalized_quote for term in ("buyback", "buy-back", "tender offer"))
        states_participation = re.search(
            r"\b(tender(?:ed|ing)?|sold|selling|sell|participat(?:e|ed|ing)|eligible|receiv(?:e|ed|ing)|benefit(?:ed|ing))\b",
            normalized_quote,
        )
        if not (mentions_buyback and states_participation):
            return None, ["quote does not explicitly connect person to buyback participation"]

    # preferred path: model copied the words, code reads the number
    for text_field, num_field in (("shares_text", "shares"), ("amount_text", "amount_inr")):
        words = p.get(text_field)
        if not words:
            continue
        if norm(words) not in norm(quote):
            problems.append(f"{text_field}='{words}' not in quote, dropped")
            p[num_field] = None
            continue
        if num_field == "shares":
            p["shares"] = parse_quantity(words)
        else:
            p["amount_inr"], p["amount_note"] = parse_money(words)

    # fallback path: model gave a bare number, it must appear literally in the quote
    for field in ("shares", "amount_inr"):
        v = p.get(field)
        if v is None or p.get(field.replace("_inr", "") + "_text"):
            continue
        if not number_in_text(v, quote):
            problems.append(f"{field}={v} not in quote, dropped")
            p[field] = None
        else:
            p[field] = to_number(v)

    if p.get("shares") is not None:
        p["shares"] = int(p["shares"])

    # a role is a fact too: keep it only if the quote says it
    role = p.get("role")
    if role and norm(role) not in norm(quote):
        problems.append(f"role '{role}' not in quote, dropped")
        p["role"] = None
    return p, problems


def check_event_price(ev, source_text):
    """Price band numbers must be inside their quote; the date must be inside its quote."""
    quote = ev.get("price_quote") or ""
    ok = quote_in_source(quote, source_text)
    for f in ("price_low", "price_high"):
        v = ev.get(f)
        if v is None:
            continue
        ev[f] = to_number(v) if ok and number_in_text(v, quote) else None
    if ev.get("price_low") is None or ev.get("price_high") is None:
        ev["price_low"] = ev["price_high"] = None          # half a band is not a band
        ev["price_quote"] = None

    dq = ev.get("date_quote") or ""
    if not (quote_in_source(dq, source_text) and norm(ev.get("date")) in norm(dq)):
        ev["date"] = ev["date_quote"] = None
    return ev
