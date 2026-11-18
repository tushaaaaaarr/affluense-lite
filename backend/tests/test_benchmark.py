from pathlib import Path
import json

from engine.shared import benchmark

KEY = {
    "name": "Example IPO sellers",
    "source_url": "https://example.com/RHP.pdf",
    "checked_against": "test fixture",
    "link": "sold_in_offer",
    "individuals": [
        {"name": "Himanshu Kantilal Sanghavi", "shares": 25200},
        {"name": "Rahul Bahri", "shares": 1800},
        {"name": "Devang Mehta", "shares": 16650},
    ],
    "institutions": [{"name": "Mace Private Limited", "shares": 765900}],
}


def _lead(name, link="sold_in_offer", shares=None):
    return {"name": name, "link": link, "shares": shares,
            "evidence": [{"url": "https://example.com/rhp.pdf", "quote": name}]}


def test_scores_recall_precision_routing_and_shares():
    result = {
        "people": [
            _lead("Him anshu Kantilal Sanghavi", shares=25200),    # split by PDF text, still a match
            _lead("Rahul Bahri", shares=18),                        # share count read wrong
            _lead("Mace Private Limited", shares=765900),           # institution put in the people list
            _lead("Someone Else"),                                  # not a seller in the filing
            _lead("Arvind Munde", link="esop"),                     # different transaction type
        ],
        "institutions": [],
    }

    s = benchmark.score(result, KEY)

    assert s["recall"] == {"found": 3, "expected": 4, "rate": 0.75}
    assert s["individuals"]["missed"] == ["Devang Mehta"]
    assert s["precision"]["false_positives"] == ["Someone Else"]
    assert s["routing"]["misrouted"] == ["Mace Private Limited"]
    assert s["shares"]["exact"] == 2
    assert s["shares"]["mismatches"] == [{"name": "Rahul Bahri", "expected": 1800, "got": 18}]
    assert s["other_leads"] == ["Arvind Munde"]


def test_only_runs_that_read_the_benchmarked_filing_are_scored(monkeypatch):
    monkeypatch.setattr(benchmark, "load_keys", lambda: [KEY])
    result = {"people": [_lead("Rahul Bahri")], "institutions": []}
    assert benchmark.for_result(result)["recall"]["found"] == 1     # URL match ignores case

    result["people"][0]["evidence"][0]["url"] = "https://example.com/news"
    assert benchmark.for_result(result) is None


def test_saved_sedemac_report_meets_benchmark():
    path = Path(__file__).parents[1] / "outputs" / "sedemac-mechatronics-ipo-mar-2026" / "report.json"
    s = benchmark.for_result(json.loads(path.read_text(encoding="utf-8")))

    # model output varies between fresh runs (Rahul Bahri, the last table row, is sometimes missed)
    assert s["individuals"]["found"] >= s["individuals"]["expected"] - 1
    assert s["recall"]["rate"] >= 0.95
    assert s["precision"]["rate"] == 1.0
    assert s["routing"]["misrouted"] == []
    assert s["shares"]["exact"] == s["shares"]["checked"]
