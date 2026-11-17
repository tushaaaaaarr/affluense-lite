"""Keep test runs out of the real cost log and the real follow-on ledger."""
import sqlite3
import sys
import pathlib

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from engine.shared import config, costlog
from engine.steps import followon


@pytest.fixture(autouse=True)
def isolated_logs(monkeypatch, tmp_path):
    # tests use their own fake clients, whatever provider .env picks for real runs
    monkeypatch.setattr(config, "PROVIDER", "anthropic")
    monkeypatch.setattr(config, "MODEL", "claude-haiku-5-5")
    monkeypatch.setattr(costlog, "CSV_PATH", tmp_path / "cost_log.csv")
    monkeypatch.setattr(costlog, "RUNS_PATH", tmp_path / "runs.csv")
    db = sqlite3.connect(":memory:")
    db.execute("create table ledger (name text, event text, link text, amount_high real)")
    db.execute("create table web_cache (key text primary key, urls text)")
    monkeypatch.setattr(followon, "_db", db)
