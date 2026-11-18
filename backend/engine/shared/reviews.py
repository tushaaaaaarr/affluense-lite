"""Persist human review decisions for leads from analysis runs."""
import sqlite3
import threading
from datetime import datetime

from engine.shared import config

DB_PATH = config.CACHE_DIR / "reviews.sqlite"
_db = sqlite3.connect(DB_PATH, check_same_thread=False)
_db_lock = threading.RLock()
_db.execute(
    """create table if not exists reviews (
        run_id text not null,
        event text not null,
        person text not null,
        decision text not null,
        note text not null,
        updated_at text not null,
        primary key (run_id, person)
    )"""
)
_db.commit()


def save(run_id, event, person, decision, note=""):
    updated_at = datetime.now().isoformat(timespec="seconds")
    with _db_lock:
        _db.execute(
            """insert into reviews values (?, ?, ?, ?, ?, ?)
            on conflict(run_id, person) do update set
                event=excluded.event,
                decision=excluded.decision,
                note=excluded.note,
                updated_at=excluded.updated_at""",
            (run_id, event, person, decision, note, updated_at),
        )
        _db.commit()
    return {
        "run_id": run_id,
        "event": event,
        "person": person,
        "decision": decision,
        "note": note,
        "updated_at": updated_at,
    }


def list_recent(limit=100):
    with _db_lock:
        rows = _db.execute(
            "select run_id, event, person, decision, note, updated_at "
            "from reviews order by updated_at desc limit ?",
            (limit,),
        ).fetchall()
    fields = ("run_id", "event", "person", "decision", "note", "updated_at")
    return [dict(zip(fields, row)) for row in rows]
