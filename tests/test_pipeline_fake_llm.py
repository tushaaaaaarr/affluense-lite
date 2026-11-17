"""End-to-end with a FAKE model and a made-up company ('Examplo Ltd'). This only tests wiring;
real-data runs are in outputs/."""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from engine import pipeline
from engine.shared import config, llm
from engine.steps import fetcher

DOC = ("Examplo Limited IPO. Price band Rs 100 to Rs 120 per equity share. "
       "Rajesh Sharma, Promoter, is offering up to 1,000,000 equity shares in the offer for sale. "
       "Tiger Example Holdings Limited is offering up to 5,000,000 equity shares in the offer for sale. "
       "The issue opens on 01 January 2026.")


def fake_ask(system, prompt, stage, event, person="", max_tokens=0, model=None):
    if stage == "extract":
        return json.dumps({
            "event": {"company": "Examplo", "kind": "ipo", "price_low": 100, "price_high": 120,
                      "price_quote": "Price band Rs 100 to Rs 120 per equity share",
                      "date": "01 January 2026", "date_quote": "The issue opens on 01 January 2026"},
            "people": [
                {"name": "Rajesh Sharma", "role": "Promoter", "link": "sold_in_offer",
                 "shares_text": "up to 1,000,000 equity shares", "amount_text": None,
                 "quote": "Rajesh Sharma, Promoter, is offering up to 1,000,000 equity shares in the offer for sale"},
                {"name": "Tiger Example Holdings Limited", "role": None, "link": "sold_in_offer", "shares": 5000000,
                 "amount_inr": None, "quote": "Tiger Example Holdings Limited is offering up to 5,000,000 equity shares in the offer for sale"},
                {"name": "Ghost Person", "role": None, "link": "other", "shares": 5, "amount_inr": 5,
                 "quote": "Ghost Person made this quote up and it is not in the document"},
            ]})
    if stage == "brief":
        return json.dumps({"briefs": [{"id": 1, "brief": "Rajesh Sharma sold via the offer. Confidence moderate."}]})
    return ""


def test_pipeline(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "ask", fake_ask)
    monkeypatch.setattr(fetcher, "get_text", lambda s: DOC)
    from engine.steps import briefer, extractor
    extractor.llm.ask = fake_ask
    briefer.llm.ask = fake_ask
    res = pipeline.run_event({"name": "Examplo test IPO", "sources": ["fake://doc"]})
    names = [p["name"] for p in res["people"]]
    assert names == ["Rajesh Sharma"]                       # org separated out
    assert [o["name"] for o in res["institutions"]] == ["Tiger Example Holdings Limited"]
    assert "Ghost Person" not in names                      # fabricated quote rejected
    p = res["people"][0]
    assert p["amount"]["high"] == 1000000 * 120
    assert p["evidence"][0]["quote"]
    assert p["brief_by"] == "llm" and "Rajesh Sharma sold" in p["brief"]
    assert res["event_info"]["price_url"] == "fake://doc"           # every figure has a link
    assert "fake://doc" in p["amount"]["working"]

    from engine.shared import report
    monkeypatch.setattr(config, "OUT_DIR", tmp_path)
    md = report.write(res).read_text(encoding="utf-8")              # ₹ must not crash on Windows
    assert "Rajesh Sharma" in md and "₹" in md


def test_todo_sources_are_skipped(monkeypatch):
    monkeypatch.setattr(fetcher, "get_text", lambda s: (_ for _ in ()).throw(AssertionError("fetched")))
    res = pipeline.run_event({"name": "Empty", "sources": ["TODO: add link"]})
    assert res["people"] == [] and "placeholder" in res["notes"][0]
