import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from engine.steps import estimator, ranker, resolver, verify


def test_name_matching():
    assert resolver.compare("Rajesh Kumar Sharma", "Sharma Rajesh Kumar") == "same"
    assert resolver.compare("Mr. Rajesh Sharma", "Rajesh Sharma") == "same"
    assert resolver.compare("R K Sharma", "Rajesh Kumar Sharma") == "maybe"   # not sure -> don't merge
    assert resolver.compare("Rajesh Sharma", "Suresh Gupta") == "different"
    assert resolver.compare("Tiger Global Five Holdings", "Rajesh Sharma") == "different"


def test_real_name_traps_from_runs():
    # SEDEMAC RHP: brothers on separate rows, same father's name in the middle
    assert resolver.compare("Atul Hiralal Shah", "Bakul Hiralal Shah") == "different"
    # RBA filing: same man written two ways -> unsure; father vs son -> different
    assert resolver.compare("Aayush Madhusudan Agrawal", "Aayush Agrawal") == "maybe"
    assert resolver.compare("Madhusudan Agrawal", "Aayush Madhusudan Agrawal") == "different"
    # Indian legal forms that are not people
    assert resolver.is_org("Society for Innovation and Entrepreneurship")
    assert resolver.is_org("Himanshu Kantilal Sanghavi HUF")


def test_number_split_by_pdf_is_rejoined():
    # real SEDEMAC page 111: "30, 000 Equity Shares ... allotted to Arvind Munde" was read as 30
    assert verify.parse_quantity("30, 000 Equity Shares") == 30000
    assert verify.number_in_text(30000, "and 30, 000 Equity Shares were allotted")


def test_date_range_uses_last_day():
    when, how = estimator._read_date("4 to 6 Mar, 2026")
    assert str(when) == "2026-03-06" and "last day" in how


def test_batched_brief_with_invented_number_falls_back(monkeypatch):
    import json
    from engine.shared import llm
    from engine.steps import briefer
    people = [{"name": n, "role": None, "link": "sold_in_offer", "confidence": 0.5,
               "confidence_why": ["x"], "timing": {"text": "now"},
               "amount": {"low": 1e7, "high": 2e7, "working": "100 shares x 10"}} for n in ("A B", "C D")]
    reply = {"briefs": [{"id": 1, "brief": "A B sold 100 shares."},
                        {"id": 2, "brief": "C D made 999 crore."}]}          # 999 is invented
    calls = []
    monkeypatch.setattr(llm, "ask", lambda *a, **k: calls.append(1) or json.dumps(reply))
    out, notes = briefer.write_briefs(people, "Test event")
    assert len(calls) == 1                                    # one call for the whole batch
    assert out[0][1] == "llm" and out[1][1] == "template (model added a number)"


def test_merge_keeps_unsure_apart():
    a = {"name": "R K Sharma", "evidence": [{"url": "u1"}], "shares": None}
    b = {"name": "Rajesh Kumar Sharma", "evidence": [{"url": "u2"}], "shares": 100}
    out = resolver.merge([a, b])
    assert len(out) == 2
    assert out[0]["possible_matches"] == ["Rajesh Kumar Sharma"]


def test_merge_joins_sure_matches():
    a = {"name": "Rajesh Sharma", "evidence": [{"url": "u1"}], "shares": None}
    b = {"name": "Mr. Rajesh Sharma", "evidence": [{"url": "u2"}], "shares": 100}
    out = resolver.merge([a, b])
    assert len(out) == 1 and out[0]["shares"] == 100 and len(out[0]["evidence"]) == 2


def test_invented_number_is_dropped():
    src = "Rajesh Sharma is offering up to 1,59,69,410 equity shares in the offer."
    p = {"name": "Rajesh Sharma", "quote": "Rajesh Sharma is offering up to 1,59,69,410 equity shares",
         "shares": 15969410, "amount_inr": 900000000}       # amount is NOT in the quote
    clean, problems = verify.check_person(p, src)
    assert clean["shares"] == 15969410
    assert clean["amount_inr"] is None


def test_fake_quote_rejected():
    clean, _ = verify.check_person({"name": "X Y", "quote": "this sentence is not in the source at all"},
                                   "completely different text")
    assert clean is None


def test_estimate_has_working_and_up_to_factor():
    p = {"shares": 1000000, "quote": "offering up to 1,000,000 shares"}
    ev = {"price_low": 100, "price_high": 120}
    a = estimator.estimate_amount(p, ev)
    assert a["low"] == 1000000 * 100 * 0.5 and a["high"] == 120000000
    assert "assumption" in a["working"]


def test_no_shares_no_number():
    a = estimator.estimate_amount({"shares": None}, {"price_low": 1, "price_high": 2})
    assert a["low"] is None


def test_org_confidence_capped():
    c, _ = ranker.confidence({"role": "x", "is_org": True}, 3)
    assert c <= 0.4


def test_copied_words_become_numbers_in_code():
    src = "Co-founder Puneet Gupta sold shares worth Rs 120 crore in the secondary round."
    p = {"name": "Puneet Gupta", "role": "Co-founder", "amount_text": "Rs 120 crore",
         "quote": "Co-founder Puneet Gupta sold shares worth Rs 120 crore in the secondary round"}
    clean, problems = verify.check_person(p, src)
    assert clean["amount_inr"] == 120 * 1e7 and not problems


def test_copied_words_must_be_in_quote():
    src = "Puneet Gupta sold some of his shares in the secondary round."
    p = {"name": "Puneet Gupta", "amount_text": "Rs 120 crore",
         "quote": "Puneet Gupta sold some of his shares in the secondary round"}
    clean, _ = verify.check_person(p, src)
    assert clean["amount_inr"] is None


def test_share_words_and_units():
    assert verify.parse_quantity("up to 12,50,000 Equity Shares") == 1250000
    assert verify.parse_quantity("2.5 lakh shares") == 250000
    # a crore later in the text must not turn a share count into crores
    assert verify.parse_quantity("1,000 equity shares aggregating Rs 5 crore") == 1000


def test_usd_amount_is_an_estimate_with_working():
    rupees, note = verify.parse_money("$5 million")
    assert rupees > 0 and "assumption" in note
    a = estimator.estimate_amount({"amount_inr": rupees, "amount_note": note}, {})
    assert a["kind"] == "estimate" and a["low"] < a["high"] and "USD" in a["working"]


def test_number_at_end_of_sentence_and_string_numbers():
    assert verify.number_in_text(512, "The buyback price is Rs 512.")
    assert verify.number_in_text("1,59,69,410", "offering 1,59,69,410 shares")
    assert verify.number_in_text(420.5, "at Rs 420.50 per share")


def test_role_not_in_quote_is_dropped():
    src = "Rajesh Sharma is offering up to 100 equity shares."
    p = {"name": "Rajesh Sharma", "role": "Managing Director",
         "quote": "Rajesh Sharma is offering up to 100 equity shares"}
    clean, problems = verify.check_person(p, src)
    assert clean["role"] is None and problems


def test_buyback_spokesperson_quote_is_not_seller_evidence():
    source = (
        "The $125 million buyback will benefit employees and early investors. "
        "\"The people who joined us early on are the reason we are here today,\" "
        "said Ritesh Arora, Co-founder and CEO of BrowserStack."
    )
    person = {
        "name": "Ritesh Arora",
        "role": "Co-founder",
        "link": "tendered_in_buyback",
        "quote": "\"The people who joined us early on are the reason we are here today,\" "
        "said Ritesh Arora, Co-founder and CEO of BrowserStack.",
    }

    clean, problems = verify.check_person(person, source)

    assert clean is None
    assert "buyback participation" in problems[0]


def test_unverified_date_is_dropped():
    ev = verify.check_event_price({"date": "05 March 2026", "date_quote": "opens on 4 March 2026"},
                                  "The issue opens on 4 March 2026.")
    assert ev["date"] is None


def test_seller_table_page_beats_boilerplate():
    from engine.steps import extractor
    boiler = "The Selling Shareholders accept responsibility for the offer for sale. " * 60
    table = "1. Manish Sharma Up to 45,000 Equity Shares of face value of ₹10 each\n" * 20
    text = "".join(f"[[page {i}]]\n{boiler}\n" for i in range(1, 30)) + f"[[page 30]]\n{table}"
    picked = [p for p, _ in extractor.pick_chunks(text, limit=len(table) + len(boiler) + 10)]
    assert 30 in picked


def test_rounded_stated_amount_becomes_a_range():
    a = estimator.estimate_amount({"amount_inr": 120 * 1e7, "amount_text": "Rs 120 crore"}, {})
    assert a["low"] < 120 * 1e7 < a["high"] and "rounded" in a["working"]


def test_exact_stated_amount_stays_exact():
    a = estimator.estimate_amount({"amount_inr": 123456789, "amount_text": "Rs 12,34,56,789"}, {})
    assert a["low"] == a["high"] == 123456789 and "exact" in a["working"]


def test_sebi_wrapper_page_points_to_pdf():
    from engine.steps import fetcher
    url = "https://www.sebi.gov.in/filings/public-issues/feb-2026/x-rhp_100355.html"
    ipo = ("<html><body><iframe src='../../../web/?file=https://www.sebi.gov.in/sebi_data/"
           "attachdocs/mar-2026/1773656117962.PDF' title='RHP'></iframe></body></html>")
    assert fetcher.linked_pdfs(ipo, url) == \
        ["https://www.sebi.gov.in/sebi_data/attachdocs/mar-2026/1773656117962.PDF"]
    buyback = ("<a href='https://www.sebi.gov.in/sebi_data/commondocs/nov-2026/X%20AP_p.pdf'>Addendum</a>"
               "<a href='https://www.sebi.gov.in/sebi_data/commondocs/nov-2026/X%20PA_p.pdf'>PA</a>")
    assert len(fetcher.linked_pdfs(buyback, url)) == 2
    assert fetcher.linked_pdfs("<html><p>news</p></html>", url) == []
