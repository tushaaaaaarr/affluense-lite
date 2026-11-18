import asyncio
import csv
import io
import ipaddress
import logging
import os
import secrets
import socket
from typing import Literal
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from engine import pipeline
from engine.shared import costlog

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
LOGS_ACCESS_TOKEN = os.getenv("LOGS_ACCESS_TOKEN", "")
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
    allow_headers=["Content-Type", "X-Logs-Token"],
)

_analysis_lock = asyncio.Lock()


@app.get("/api/health")
async def health():
    return {"status": "ok"}


def _require_logs_access(x_logs_token: str | None = Header(default=None)):
    if not LOGS_ACCESS_TOKEN or not x_logs_token or not secrets.compare_digest(
        x_logs_token, LOGS_ACCESS_TOKEN
    ):
        raise HTTPException(status_code=401, detail="A valid log access token is required.")


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


@app.post("/api/events/analyze")
async def analyze_event(request: AnalyzeRequest):
    spec = {"name": request.name.strip(), "sources": request.urls}
    async with _analysis_lock:
        try:
            return await run_in_threadpool(pipeline.run_event, spec, follow_web=request.follow_web)
        except Exception as exc:
            logger.exception("Event analysis failed for %s", request.name)
            raise HTTPException(
                status_code=502,
                detail="Analysis failed. Check the source links and model API configuration, then try again.",
            ) from exc