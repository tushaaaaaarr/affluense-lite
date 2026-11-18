import asyncio
import csv
import hmac
import io
import ipaddress
import logging
import os
import socket
from pathlib import Path
from uuid import uuid4
from typing import Literal
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from engine import pipeline
from engine.shared import config, costlog

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
LOGS_USERNAME = os.getenv("LOGS_USERNAME", "")
LOGS_PASSWORD = os.getenv("LOGS_PASSWORD", "")
_basic_auth = HTTPBasic(auto_error=False)
MAX_SOURCE_FILE_BYTES = 25 * 1024 * 1024
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

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, urls):
        return [_validate_public_url(url) for url in urls]


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


async def _analyze(spec, follow_web):
    async with _analysis_lock:
        try:
            return await run_in_threadpool(pipeline.run_event, spec, follow_web=follow_web)
        except Exception as exc:
            logger.exception("Event analysis failed for %s", spec["name"])
            raise HTTPException(
                status_code=502,
                detail="Analysis failed. Check the source links and model API configuration, then try again.",
            ) from exc


@app.post("/api/events/analyze")
async def analyze_event(request: AnalyzeRequest):
    spec = {"name": request.name.strip(), "sources": request.urls}
    return await _analyze(spec, request.follow_web)


@app.post("/api/events/analyze-upload")
async def analyze_event_with_pdf(
    name: str = Form(...),
    urls: str = Form(...),
    source_file_url: str = Form(...),
    source_file: UploadFile = File(...),
    follow_web: bool = Form(False),
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
    sources = [
        {"url": url, "file": str(file_path)} if url == source_file_url else url
        for url in source_urls
    ]
    try:
        return await _analyze({"name": name, "sources": sources}, follow_web)
    finally:
        file_path.unlink(missing_ok=True)
        await source_file.close()