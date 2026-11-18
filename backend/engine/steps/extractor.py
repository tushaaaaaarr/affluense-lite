"""Agent 2: reads the filing/article and pulls out who got money.

Step 1 (plain code): pick the few chunks of the document that look relevant, so we don't
         pay the model to read 400 pages of risk factors.
Step 2 (LLM):       turn those chunks into JSON.
Step 3 (plain code): verify.py throws away anything that isn't backed by a real quote.
"""
import json
import re

from engine.shared import config, llm
from engine.steps import verify

KEYWORDS = {
    "offer for sale": 3, "selling shareholder": 4, "promoter selling": 4, "equity shares": 1,
    "tendered": 3, "buyback": 3, "buy-back": 3, "open offer": 3, "acquirer": 2, "esop": 2,
    "employee stock": 2, "price band": 3, "per equity share": 2, "sold": 1, "consideration": 2,
    "early investor": 2, "secondary": 2, "exit": 1, "stake": 1, "crore": 1,
    "intention of the promoter": 8, "intended to tender": 6, "proposed to be tendered": 6,
    "intend to tender": 4, "ratio of buyback": 6, "schedule of activities": 4, "closing date": 2,
}
# Seller tables are rows of "Up to 2,410,650 Equity Shares". Keywords alone missed them on a real
# RHP (picked the cover page and boilerplate instead), so a page full of share counts wins.
PATTERNS = [(re.compile(r"up to [\d,]+ equity shares"), 10), (re.compile(r"\d[\d,]{4,} equity shares"), 3),
            (re.compile(r"equity shares for every [\d,]+ equity shares"), 8)]

SYSTEM = """You extract facts about who RECEIVED money in an Indian corporate event
(sold shares in an IPO offer for sale, tendered in a buyback, sold to an acquirer, got an ESOP
payout, early investor exiting). Do NOT list people or firms who paid money (acquirers, new
investors, anchor investors), or advisers, bankers, auditors, lawyers.
Rules:
- Use ONLY the text given. Never use outside knowledge.
- Every person MUST have a "quote": an exact copy (max 300 chars) of the sentence/table row
  from the text that mentions them. Copy it character for character.
- "role": copy the role words exactly as written in the quote (e.g. "Promoter Selling
  Shareholder", "co-founder"), or null.
- "shares_text" / "amount_text": COPY the words from the quote that give the number of shares
  or the money they got (e.g. "up to 12,50,000 Equity Shares", "Rs 120 crore", "$5 million").
  Do not convert or calculate. null if the quote does not say it.
- Price: for a band copy both ends; for a single buyback/offer price use it for both.
  "date" must be copied exactly from "date_quote". Prefer the date money is paid or the
  offer/buyback closes (closing or settlement date), not a record date or filing date.
- "size_text": COPY the words giving the total size of the offer/buyback in money
  (e.g. "up to ₹ 250 crore"), with "size_quote" the sentence it is in. null if not given.
- Buybacks: promoters listed in a table of shareholders intending to tender ARE people who get
  money (link "tendered_in_buyback"). Quote their table row and copy the number of shares
  intended to tender as "shares_text". "ratio_text": COPY the entitlement ratio for the
  general category (e.g. "2 Equity Shares for every 75 Equity Shares"), with "ratio_quote".
- Shares held "in the capacity as Trustee of" a trust belong to the trust: name the trust
  (e.g. "ABC Family Trust"), not the trustee.
- If you are unsure about a field, use null.
- Output JSON only, no commentary.

Schema:
{"event": {"company": str|null, "kind": str|null,
           "price_low": number|null, "price_high": number|null, "price_quote": str|null,
           "date": str|null, "date_quote": str|null,
           "size_text": str|null, "size_quote": str|null,
           "ratio_text": str|null, "ratio_quote": str|null},
 "people": [{"name": str, "role": str|null,
             "link": "sold_in_offer|tendered_in_buyback|sold_to_acquirer|esop|early_investor|other",
             "shares_text": str|null, "amount_text": str|null, "quote": str}]}"""


def split_chunks(text, size=3000):
    """PDF text has [[page N]] markers -> one chunk per page. Otherwise cut every ~3000 chars."""
    if "[[page " in text:
        parts = re.split(r"\[\[page (\d+)\]\]", text)
        return [(int(parts[i]), parts[i + 1]) for i in range(1, len(parts) - 1, 2)]
    return [(None, text[i:i + size]) for i in range(0, len(text), size)]


def pick_chunks(text, limit=config.MAX_CHARS_TO_LLM):
    chunks = split_chunks(text)
    if len(text) <= limit:              # a news article: just send all of it
        return chunks
    scored = []
    for idx, (page, body) in enumerate(chunks):
        low = body.lower()
        # cap each keyword: in a buyback letter every page says "buyback" a dozen times
        score = sum(w * min(low.count(k), 3) for k, w in KEYWORDS.items())
        score += sum(w * len(rx.findall(low)) for rx, w in PATTERNS)
        if score > 0:
            scored.append((score, idx))
    scored.sort(reverse=True)

    chosen, used = [], 0
    for score, idx in scored:
        size = len(chunks[idx][1])
        if used + size > limit:
            continue
        chosen.append(idx)
        used += size
    chosen.sort()                       # back to document order
    return [chunks[i] for i in chosen]


def parse_json(raw):
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    start, end = raw.find("{"), raw.rfind("}")
    return json.loads(raw[start:end + 1])


def page_of(quote, chunks):
    """Which page did the quote come from? (so the evidence link can say 'page 123')"""
    q = verify.norm(quote)
    for page, body in chunks:
        if q in verify.norm(body):
            return page
    return None


def extract(source_url, text, event_name, cost_event=None, stage="extract"):
    """cost_event: which event the tokens are charged to (follow-ons charge the parent event)."""
    chunks = pick_chunks(text)
    if not chunks:
        return {"event": {}, "people": [], "dropped": [{"why": "no relevant text found"}]}

    # label each chunk so the model can't confuse them
    body = "\n\n".join(f"--- page {p} ---\n{t}" if p else f"--- excerpt ---\n{t}" for p, t in chunks)
    raw = llm.ask(SYSTEM, f"Event: {event_name}\n\nTEXT:\n{body}", stage=stage,
                  event=cost_event or event_name, max_tokens=config.EXTRACT_MAX_OUT_TOKENS)

    try:
        data = parse_json(raw)
    except Exception:
        return {"event": {}, "people": [], "dropped": [{"why": "model gave bad JSON"}]}

    # verify against the chunks we actually sent (not the whole doc)
    sent_text = "\n".join(t for _, t in chunks)
    event = verify.check_event_price(data.get("event") or {}, sent_text)

    people, dropped = [], []
    for p in data.get("people") or []:
        clean, problems = verify.check_person(p, sent_text)
        if clean is None:
            dropped.append({"name": p.get("name"), "why": problems})
            continue
        if problems:
            dropped.append({"name": p.get("name"), "why": problems, "kept_person": True})
        clean["evidence"] = [{"url": source_url, "page": page_of(clean["quote"], chunks),
                              "quote": clean["quote"]}]
        people.append(clean)
    return {"event": event, "people": people, "dropped": dropped}
