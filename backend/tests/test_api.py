from fastapi.testclient import TestClient
import base64

from backend import app as api
from engine.shared import costlog, llm


client = TestClient(api.app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_analyze_rejects_local_source():
    response = client.post("/api/events/analyze", json={
        "name": "Example IPO",
        "urls": ["http://127.0.0.1/private"],
    })
    assert response.status_code == 422


def test_analyze_returns_pipeline_result(monkeypatch):
    expected = {"event": "Example IPO", "people": [], "institutions": [], "cost": {"cost_usd": 0}}
    monkeypatch.setattr(api.pipeline, "run_event", lambda spec, follow_web=False: expected)
    response = client.post("/api/events/analyze", json={
        "name": "Example IPO",
        "urls": ["https://example.com/filing.pdf"],
    })
    assert response.status_code == 200
    assert response.json() == expected


def test_analyze_can_access_followon_database_from_worker_thread(monkeypatch):
    expected = {"event": "Example IPO", "people": [], "institutions": [], "cost": {"cost_usd": 0}}

    def run_event(spec, follow_web=False):
        api.pipeline.followon.remember(spec["name"], [])
        return expected

    monkeypatch.setattr(api.pipeline, "run_event", run_event)
    response = client.post("/api/events/analyze", json={
        "name": "Example IPO",
        "urls": ["https://example.com/filing.pdf"],
    })

    assert response.status_code == 200
    assert response.json() == expected


def test_analyze_can_access_llm_cache_from_worker_thread(monkeypatch):
    expected = {"event": "Example IPO", "people": [], "institutions": [], "cost": {"cost_usd": 0}}
    monkeypatch.setattr(llm, "_call", lambda model, system, prompt, max_tokens: ("cached response", 1, 1))
    prompt = f"api-cache-worker-thread-regression-{id(monkeypatch)}"

    def run_event(spec, follow_web=False):
        costlog.new_run()
        assert llm.ask("system", prompt, "extract", spec["name"]) == "cached response"
        return expected

    monkeypatch.setattr(api.pipeline, "run_event", run_event)
    response = client.post("/api/events/analyze", json={
        "name": "Example IPO",
        "urls": ["https://example.com/filing.pdf"],
    })

    assert response.status_code == 200
    assert response.json() == expected


def test_log_routes_require_username_and_password(monkeypatch):
    monkeypatch.setattr(api, "LOGS_USERNAME", "logs-user")
    monkeypatch.setattr(api, "LOGS_PASSWORD", "secret-pass")

    response = client.get("/api/logs/runs")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Basic"

    wrong_credentials = base64.b64encode(b"logs-user:wrong-pass").decode("ascii")
    wrong_response = client.get(
        "/api/logs/runs",
        headers={"Authorization": f"Basic {wrong_credentials}"},
    )
    assert wrong_response.status_code == 401


def test_log_routes_show_rows_and_download_csv(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "LOGS_USERNAME", "logs-user")
    monkeypatch.setattr(api, "LOGS_PASSWORD", "secret-pass")
    monkeypatch.setattr(costlog, "RUNS_PATH", tmp_path / "runs.csv")
    costlog.RUNS_PATH.write_text(
        "run_id,time,event,model,llm_calls,cached_calls,cost_usd,wall_seconds,people,cost_per_person_usd\n"
        "run-1,2026-11-18,Example IPO,gemini,1,0,0.01,2.0,1,0.01\n",
        encoding="utf-8",
    )

    encoded_credentials = base64.b64encode(b"logs-user:secret-pass").decode("ascii")
    headers = {"Authorization": f"Basic {encoded_credentials}"}
    response = client.get("/api/logs/runs", headers=headers)
    download = client.get("/api/logs/csv/runs", headers=headers)

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["rows"][0]["event"] == "Example IPO"
    assert download.status_code == 200
    assert "text/csv" in download.headers["content-type"]
    assert "run-1" in download.text


def test_upload_pdf_for_blocked_source(monkeypatch, tmp_path):
    expected = {"event": "Example IPO", "people": [], "institutions": [], "cost": {"cost_usd": 0}}
    captured = {}

    async def fake_analyze(spec, follow_web):
        captured.update(spec)
        return expected

    monkeypatch.setattr(api, "_analyze", fake_analyze)
    response = client.post(
        "/api/events/analyze-upload",
        data={
            "name": "Example IPO",
            "urls": "https://nsearchives.nseindia.com/corporate/example.pdf",
            "source_file_url": "https://nsearchives.nseindia.com/corporate/example.pdf",
            "follow_web": "false",
        },
        files={"source_file": ("example.pdf", b"%PDF-1.7 fake-pdf-content", "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json() == expected
    assert captured["sources"][0]["url"].startswith("https://nsearchives.nseindia.com/")
    assert captured["sources"][0]["file"].endswith(".pdf")
    assert not __import__("pathlib").Path(captured["sources"][0]["file"]).exists()


def test_upload_saved_html_for_blocked_source(monkeypatch):
    expected = {"event": "Astrotalk ESOP buyback", "people": [], "institutions": [], "cost": {"cost_usd": 0}}
    captured = {}

    async def fake_analyze(spec, follow_web):
        captured.update(spec)
        return expected

    monkeypatch.setattr(api, "_analyze", fake_analyze)
    public_url = "https://www.moneycontrol.com/news/business/astrotalk-esop-buyback.html"
    response = client.post(
        "/api/events/analyze-upload",
        data={
            "name": "Astrotalk ESOP buyback",
            "urls": f"{public_url}\nhttps://www.dealstreetasia.com/stories/astrology-astrotalk-esop-491981",
            "source_file_url": public_url,
            "follow_web": "false",
        },
        files={"source_file": ("astrotalk_moneycontrol.html", b"<!doctype html><html><body>Astrotalk buyback</body></html>", "text/html")},
    )

    assert response.status_code == 200
    assert response.json() == expected
    assert captured["sources"][0]["url"] == public_url
    assert captured["sources"][0]["file"].endswith(".html")
    assert not __import__("pathlib").Path(captured["sources"][0]["file"]).exists()