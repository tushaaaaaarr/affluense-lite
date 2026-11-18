"""Small offline quality set for source grounding, role attribution, and abstention."""
from engine.steps import ranker, resolver, verify


EVIDENCE_CASES = [
    {
        "case": "buyback spokesperson is not a participant",
        "source": (
            "The $125 million buyback will benefit employees and early investors. "
            "The people who joined us early on are the reason we are here today, "
            "said Ritesh Arora, Co-founder and CEO of BrowserStack."
        ),
        "person": {
            "name": "Ritesh Arora",
            "role": "Co-founder",
            "link": "tendered_in_buyback",
            "quote": "The people who joined us early on are the reason we are here today, "
            "said Ritesh Arora, Co-founder and CEO of BrowserStack.",
        },
        "keep": False,
    },
    {
        "case": "named tendering employee is supported",
        "source": "Kannu Mittal tendered 20,000 vested shares in the company buyback.",
        "person": {
            "name": "Kannu Mittal",
            "role": "employee",
            "link": "tendered_in_buyback",
            "shares_text": "20,000 vested shares",
            "quote": "Kannu Mittal tendered 20,000 vested shares in the company buyback.",
        },
        "keep": True,
    },
    {
        "case": "buyback table row under an intention-to-tender heading is supported",
        "source": (
            "The Promoters have expressed their intention to participate in the Buyback. The details of "
            "the Promoters intending to participate in the Buyback, along with the maximum number of "
            "Equity Shares proposed to be tendered by each of them, are set out below: "
            "1. Mr. Ameya Ashok Chandavarkar 99,23,930 99,23,930"
        ),
        "person": {
            "name": "Ameya Ashok Chandavarkar",
            "link": "tendered_in_buyback",
            "shares_text": "99,23,930",
            "quote": "1. Mr. Ameya Ashok Chandavarkar 99,23,930 99,23,930",
        },
        "keep": True,
    },
    {
        "case": "promoter named near a buyback but holding no shares is not a lead",
        "source": (
            "The Board noted the intention of Promoters for their participation in the Buyback. "
            "Mr. Mohan A Chandavarkar, Chairman & Managing Director, is authorised to give effect to it."
        ),
        "person": {
            "name": "Mohan A Chandavarkar",
            "role": "Chairman & Managing Director",
            "link": "tendered_in_buyback",
            "quote": "The Board noted the intention of Promoters for their participation in the Buyback. "
            "Mr. Mohan A Chandavarkar, Chairman & Managing Director, is authorised to give effect to it.",
        },
        "keep": False,
    },
]


def test_source_grounding_evaluation_cases():
    for case in EVIDENCE_CASES:
        cleaned, _ = verify.check_person(dict(case["person"]), case["source"])
        assert (cleaned is not None) is case["keep"], case["case"]


def test_cross_source_evidence_is_reported_as_corroboration():
    mentions = [
        {"name": "Rajesh Sharma", "role": "Promoter", "link": "sold_in_offer",
         "evidence": [{"url": "https://example.com/filing.pdf", "quote": "Rajesh Sharma sold shares."}]},
        {"name": "Rajesh Sharma", "role": "Promoter", "link": "sold_in_offer",
         "evidence": [{"url": "https://example.com/announcement", "quote": "Rajesh Sharma sold shares."}]},
    ]
    merged = resolver.merge(mentions)[0]
    merged["amount"] = {"kind": "stated", "working": "source states exact amount"}

    dimensions = ranker.confidence_dimensions(merged, n_sources=2)

    assert dimensions["corroboration"]["source_count"] == 2
    assert dimensions["corroboration"]["independent_sources"] is True
    assert dimensions["transaction"]["score"] > 0.62


def test_ambiguous_names_stay_separate_in_evaluation_set():
    left = {"name": "R K Sharma", "evidence": []}
    right = {"name": "Rajesh Kumar Sharma", "evidence": []}

    assert resolver.compare(left["name"], right["name"]) == "maybe"
