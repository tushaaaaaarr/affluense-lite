from fastapi.testclient import TestClient

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


def test_log_routes_require_access_token(monkeypatch):
    monkeypatch.setattr(api, "LOGS_ACCESS_TOKEN", "test-token")

    response = client.get("/api/logs/runs")

    assert response.status_code == 401


def test_log_routes_show_rows_and_download_csv(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "LOGS_ACCESS_TOKEN", "test-token")
    monkeypatch.setattr(costlog, "RUNS_PATH", tmp_path / "runs.csv")
    costlog.RUNS_PATH.write_text(
        "run_id,time,event,model,llm_calls,cached_calls,cost_usd,wall_seconds,people,cost_per_person_usd\n"
        "run-1,2026-11-18,Example IPO,gemini,1,0,0.01,2.0,1,0.01\n",
        encoding="utf-8",
    )

    headers = {"X-Logs-Token": "test-token"}
    response = client.get("/api/logs/runs", headers=headers)
    download = client.get("/api/logs/csv/runs", headers=headers)

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["rows"][0]["event"] == "Example IPO"
    assert download.status_code == 200
    assert "text/csv" in download.headers["content-type"]
    assert "run-1" in download.text