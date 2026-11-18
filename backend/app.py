import asyncio
import csv
import hmac
import io
import ipaddress
import json
import logging
import os
import re
import socket
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from typing import Literal
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from engine import pipeline
from engine.shared import benchmark, config, costlog, report, reviews
from engine.steps import ranker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
LOGS_USERNAME = os.getenv("LOGS_USERNAME", "")
LOGS_PASSWORD = os.getenv("LOGS_PASSWORD", "")
_basic_auth = HTTPBasic(auto_error=False)
MAX_SOURCE_FILE_BYTES = 25 * 1024 * 1024
ANALYSIS_FAILED = "Analysis failed. Check the source links and model API configuration, then try again."
RUN_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,119}")
LOG_SPECS = {
    "costs": ("CSV_PATH", costlog.FIELDS, "cost_log.csv"),
    "runs": ("RUNS_PATH", costlog.RUN_FIELDS, "runs.csv"),
}


def _validate_public_url(value):
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
        raise ValueError("Use a public http:// or https:// link")
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local")):
        raise ValueError("Local network links are not allowed")
    try:
        addresses = {item[4][0].split("%")[0] for item in socket.getaddrinfo(host, parsed.port or 443)}
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise ValueError("Links must resolve to a public address")
    except (socket.gaierror, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("Links must"):
            raise
        raise ValueError("The link host could not be resolved") from exc
    return value.strip()


class AnalyzeRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    urls: list[str] = Field(min_length=1, max_length=8)
    follow_web: bool = False
    stream: bool = False

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, urls):
        return [_validate_public_url(url) for url in urls]


class ReviewRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=64)
    event: str = Field(min_length=1, max_length=160)
    person: str = Field(min_length=1, max_length=200)
    decision: Literal["accepted", "rejected", "needs_review"]
    note: str = Field(default="", max_length=1000)


app = FastAPI(title="Affluense-lite API", version="1.0.0")
origins = [origin.strip() for origin in __import__("os").getenv(
    "FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

_analysis_lock = asyncio.Lock()
_background_tasks = set()


@app.get("/api/health")
async def health():
    return {"status": "ok"}


def _require_logs_access(credentials: HTTPBasicCredentials | None = Depends(_basic_auth)):
    if not LOGS_USERNAME or not LOGS_PASSWORD:
        raise HTTPException(status_code=503, detail="Log sign-in is not configured on the backend.")
    if credentials is None or not (
        hmac.compare_digest(credentials.username, LOGS_USERNAME)
        and hmac.compare_digest(credentials.password, LOGS_PASSWORD)
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect log username or password.",
            headers={"WWW-Authenticate": "Basic"},
        )


@app.get("/api/logs/csv/{kind}", dependencies=[Depends(_require_logs_access)])
async def download_log_csv(kind: Literal["costs", "runs"]):
    path_name, fields, filename = LOG_SPECS[kind]
    path = getattr(costlog, path_name)
    if path.exists():
        return FileResponse(path, media_type="text/csv", filename=filename)
    buffer = io.StringIO(newline="")
    csv.writer(buffer).writerow(fields)
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/logs/{kind}", dependencies=[Depends(_require_logs_access)])
async def read_log(kind: Literal["costs", "runs"]):
    path_name, fields, _ = LOG_SPECS[kind]
    path = getattr(costlog, path_name)
    rows = []
    if path.exists():
        with path.open(newline="", encoding="utf-8") as file:
            rows = list(csv.DictReader(file))
    return {"columns": fields, "rows": list(reversed(rows[-100:])), "total": len(rows)}


@app.post("/api/reviews", dependencies=[Depends(_require_logs_access)])
async def save_review(request: ReviewRequest):
    return reviews.save(
        request.run_id,
        request.event.strip(),
        request.person.strip(),
        request.decision,
        request.note.strip(),
    )


@app.get("/api/reviews", dependencies=[Depends(_require_logs_access)])
async def read_reviews(limit: int = Query(default=100, ge=1, le=500)):
    rows = reviews.list_recent(limit)
    return {
        "columns": ["run_id", "event", "person", "decision", "note", "updated_at"],
        "rows": rows,
        "total": len(rows),
    }


def _finish(result):
    """Score against an answer key when one exists, and save the run so it shows in history."""
    scored = benchmark.for_result(result)
    if scored:
        result["benchmark"] = scored
    if result.get("people") or result.get("institutions"):
        try:
            report.write(result)
        except Exception:
            logger.exception("Could not save the report for %s", result.get("event"))
    return result


async def _analyze(spec, follow_web):
    async with _analysis_lock:
        try:
            result = await run_in_threadpool(pipeline.run_event, spec, follow_web=follow_web)
            return await run_in_threadpool(_finish, result)
        except Exception as exc:
            logger.exception("Event analysis failed for %s", spec["name"])
            raise HTTPException(status_code=502, detail=ANALYSIS_FAILED) from exc


def _stream_analysis(spec, follow_web, cleanup=None):
    """Runs the pipeline and streams newline-delimited JSON: progress events, then the result."""
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()

    def on_progress(stage, message, data):
        loop.call_soon_threadsafe(queue.put_nowait,
                                  {"type": "progress", "stage": stage, "message": message, "data": data})

    async def worker():
        try:
            if _analysis_lock.locked():
                await queue.put({"type": "progress", "stage": "queue",
                                 "message": "Waiting for another analysis to finish", "data": {}})
            async with _analysis_lock:
                result = await run_in_threadpool(pipeline.run_event, spec, follow_web=follow_web,
                                                 on_progress=on_progress)
                await run_in_threadpool(_finish, result)
            await queue.put({"type": "result", "result": result})
        except Exception:
            logger.exception("Event analysis failed for %s", spec["name"])
            await queue.put({"type": "error", "detail": ANALYSIS_FAILED})
        finally:
            if cleanup:
                cleanup()
            await queue.put(None)

    task = asyncio.create_task(worker())
    _background_tasks.add(task)                 # keeps the run alive if the browser disconnects
    task.add_done_callback(_background_tasks.discard)

    async def lines():
        while (item := await queue.get()) is not None:
            yield json.dumps(item, default=str, ensure_ascii=False) + "\n"

    return StreamingResponse(lines(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/events/analyze")
async def analyze_event(request: AnalyzeRequest):
    spec = {"name": request.name.strip(), "sources": request.urls}
    if request.stream:
        return _stream_analysis(spec, request.follow_web)
    return await _analyze(spec, request.follow_web)


@app.post("/api/events/analyze-upload")
async def analyze_event_with_pdf(
    name: str = Form(...),
    urls: str = Form(...),
    source_file_url: str = Form(...),
    source_file: UploadFile = File(...),
    follow_web: bool = Form(False),
    stream: bool = Form(False),
):
    name = name.strip()
    source_urls = [_validate_public_url(url) for url in urls.splitlines() if url.strip()]
    source_file_url = _validate_public_url(source_file_url)
    if not 2 <= len(name) <= 160:
        raise HTTPException(status_code=422, detail="Event name must be between 2 and 160 characters.")
    if not 1 <= len(source_urls) <= 8:
        raise HTTPException(status_code=422, detail="Provide between 1 and 8 public source links.")
    if source_file_url not in source_urls:
        raise HTTPException(status_code=422, detail="The uploaded file's public URL must be in Source links.")

    file_bytes = await source_file.read(MAX_SOURCE_FILE_BYTES + 1)
    if len(file_bytes) > MAX_SOURCE_FILE_BYTES:
        raise HTTPException(status_code=413, detail="Source file uploads are limited to 25 MB.")
    suffix = Path(source_file.filename or "").suffix.lower()
    if suffix == ".pdf" and file_bytes.startswith(b"%PDF-"):
        pass
    elif suffix in {".html", ".htm"}:
        html_start = file_bytes[:4096].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
        if not any(marker in html_start for marker in (b"<html", b"<!doctype html", b"<head", b"<body")):
            raise HTTPException(status_code=422, detail="Upload a valid HTML page or PDF file.")
    else:
        raise HTTPException(status_code=422, detail="Upload a valid HTML page or PDF file.")

    upload_dir = config.CACHE_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / f"{uuid4().hex}{suffix}"
    file_path.write_bytes(file_bytes)
    await source_file.close()
    sources = [
        {"url": url, "file": str(file_path)} if url == source_file_url else url
        for url in source_urls
    ]
    spec = {"name": name, "sources": sources}
    if stream:
        return _stream_analysis(spec, follow_web, cleanup=lambda: file_path.unlink(missing_ok=True))
    try:
        return await _analyze(spec, follow_web)
    finally:
        file_path.unlink(missing_ok=True)


def _saved_report(run_id):
    path = config.OUT_DIR / run_id / "report.json"
    if not RUN_ID_PATTERN.fullmatch(run_id) or not path.is_file():
        raise HTTPException(status_code=404, detail="Saved analysis not found.")
    return json.loads(path.read_text(encoding="utf-8")), path


@app.get("/api/runs")
def list_runs():
    runs = []
    for path in config.OUT_DIR.glob("*/report.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        runs.append({
            "id": path.parent.name,
            "event": data.get("event") or path.parent.name,
            "status": data.get("analysis_status", "complete"),
            "people": len(data.get("people") or []),
            "institutions": len(data.get("institutions") or []),
            "cost_usd": (data.get("cost") or {}).get("cost_usd"),
            "saved_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds"),
            "benchmarked": benchmark.key_for(data) is not None,
        })
    runs.sort(key=lambda run: run["saved_at"], reverse=True)
    return {"runs": runs}


@app.get("/api/runs/{run_id}")
def read_run(run_id: str):
    data, _ = _saved_report(run_id)
    for lead in (data.get("people") or []) + (data.get("institutions") or []):
        # reports saved before score_parts existed still get the rank explanation
        if "score_parts" not in lead and lead.get("amount") and lead.get("timing") and lead.get("confidence") is not None:
            lead["score_parts"] = ranker.rank_parts(lead)
    data.pop("benchmark", None)
    scored = benchmark.for_result(data)
    if scored:
        data["benchmark"] = scored
    return data