"""Follow-on leads: "this seller probably sold in an earlier deal too".

Two sources, both with hard stops:
 1. LEDGER (free): every person from every past run is saved in a small sqlite file.
    If today's person matches someone from an earlier event we say so. No network, no tokens.
 2. WEB (optional, costs money): ask the model's web-search tool for *URLs only* about a person.
    The model never gives us facts here. The URLs go through the same fetch -> extract -> verify
    pipeline, so a made-up claim can't sneak in.

When do we stop?  depth <= FOLLOW_MAX_DEPTH, only the top FOLLOW_MAX_PEOPLE people,
at most FOLLOW_MAX_URLS_EACH urls per person, and the per-event dollar cap.
Follow-on results never trigger further follow-ons (that's the depth limit).
"""
import json
import sqlite3
import threading
import time

from engine.shared import config, costlog
from engine.steps import resolver

_db = sqlite3.connect(config.CACHE_DIR / "ledger.sqlite", check_same_thread=False)
_db_lock = threading.RLock()
_db.execute("create table if not exists ledger (name text, event text, link text, amount_high real)")
_db.execute("create table if not exists web_cache (key text primary key, urls text)")


def remember(event_name, people):
    with _db_lock:
        _db.execute("delete from ledger where event=?", (event_name,))      # re-runs shouldn't duplicate
        for p in people:
            _db.execute("insert into ledger values (?,?,?,?)",
                        (p["name"], event_name, p.get("link"), p["amount"]["high"]))
        _db.commit()


def ledger_hits(person, current_event):
    hits = []
    with _db_lock:
        rows = _db.execute("select name, event, link, amount_high from ledger").fetchall()
    for name, event, link, amt in rows:
        if event == current_event:
            continue
        verdict = resolver.compare(person["name"], name)
        if verdict in ("same", "maybe"):
            hits.append({"name_there": name, "event": event, "link": link,
                         "match": verdict})
    return hits


def web_leads(person, event_name, depth):
    """Returns a list of URLs. Anthropic only (uses their web search tool).
    Not used unless --follow-web is passed. Results are cached, so a repeat run is free."""
    if depth >= config.FOLLOW_MAX_DEPTH:
        return []
    key = f"{person['name']}|{event_name}"
    with _db_lock:
        row = _db.execute("select urls from web_cache where key=?", (key,)).fetchone()
    if row:
        costlog.log(event_name, "followon_search", config.MODEL, 0, 0, 0.0, 0.0, True, person["name"])
        return json.loads(row[0])

    if config.PROVIDER != "anthropic":
        raise RuntimeError("web follow-on needs the Anthropic web search tool; ledger still works")
    costlog.check_budget(event_name)
    import anthropic
    client = anthropic.Anthropic()
    t0 = time.time()
    resp = client.messages.create(
        model=config.MODEL, max_tokens=300,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}],
        messages=[{"role": "user", "content":
                   f"Find news or Indian exchange filings about '{person['name']}' selling shares, "
                   f"tendering in a buyback, or getting an ESOP payout in the last 2 years. "
                   f"Ignore anything about: {event_name}. Search only, no summary needed."}],
    )
    urls = []
    for block in resp.content:
        if getattr(block, "type", "") == "web_search_tool_result":
            for item in (block.content or []):
                u = getattr(item, "url", None)
                if u and u not in urls:
                    urls.append(u)
    urls = urls[:config.FOLLOW_MAX_URLS_EACH]

    n_searches = getattr(getattr(resp.usage, "server_tool_use", None), "web_search_requests", 0) or 0
    cost = (resp.usage.input_tokens / 1e6 * config.PRICES.get(config.MODEL, (0, 0))[0]
            + resp.usage.output_tokens / 1e6 * config.PRICES.get(config.MODEL, (0, 0))[1]
            + n_searches * config.WEB_SEARCH_COST_USD)
    costlog.log(event_name, "followon_search", config.MODEL, resp.usage.input_tokens,
                resp.usage.output_tokens, cost, time.time() - t0, False, person["name"])
    with _db_lock:
        _db.execute("insert or replace into web_cache values (?,?)", (key, json.dumps(urls)))
        _db.commit()
    return urls
