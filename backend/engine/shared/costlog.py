"""Tiny cost + timing logger.
  outputs/cost_log.csv  one row per LLM call (stage, person, tokens, $, seconds, cached?)
  outputs/runs.csv      one row per run (event total $, wall time, people, $ per person)
"""
import csv
import uuid
from datetime import datetime

from engine.shared import config

CSV_PATH = config.OUT_DIR / "cost_log.csv"
RUNS_PATH = config.OUT_DIR / "runs.csv"
FIELDS = ["run_id", "time", "event", "stage", "person", "model", "in_tokens", "out_tokens",
          "cost_usd", "seconds", "cached"]
RUN_FIELDS = ["run_id", "time", "event", "model", "llm_calls", "cached_calls", "cost_usd",
              "wall_seconds", "people", "cost_per_person_usd"]

run_id = uuid.uuid4().hex[:8]
rows = []          # kept in memory too, so we can print a summary


class BudgetError(Exception):
    pass


def new_run():
    global run_id, rows
    run_id = uuid.uuid4().hex[:8]
    rows = []


def _append(path, fields, row):
    new_file = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new_file:
            w.writeheader()
        w.writerow(row)


def log(event, stage, model, in_tok, out_tok, cost, seconds, cached, person=""):
    row = dict(run_id=run_id, time=datetime.now().isoformat(timespec="seconds"), event=event,
               stage=stage, person=person, model=model, in_tokens=in_tok, out_tokens=out_tok,
               cost_usd=round(cost, 6), seconds=round(seconds, 2), cached=cached)
    rows.append(row)
    _append(CSV_PATH, FIELDS, row)


def log_run(event, wall_seconds, n_people):
    s = summary(event)
    _append(RUNS_PATH, RUN_FIELDS, dict(
        run_id=run_id, time=datetime.now().isoformat(timespec="seconds"), event=event,
        model=config.MODEL, llm_calls=s["calls"], cached_calls=s["cached_calls"],
        cost_usd=s["cost_usd"], wall_seconds=wall_seconds, people=n_people,
        cost_per_person_usd=round(s["cost_usd"] / n_people, 4) if n_people else ""))


def spent(event=None):
    return sum(r["cost_usd"] for r in rows if event is None or r["event"] == event)


def check_budget(event):
    if spent(event) >= config.MAX_COST_PER_EVENT:
        raise BudgetError(f"hit the ${config.MAX_COST_PER_EVENT} cap for {event}")


def summary(event):
    mine = [r for r in rows if r["event"] == event]
    return {
        "calls": len(mine),
        "cached_calls": sum(1 for r in mine if r["cached"]),
        "cost_usd": round(sum(r["cost_usd"] for r in mine), 4),
        "seconds": round(sum(r["seconds"] for r in mine), 1),
    }


def per_person(event):
    """Cost per person = their own calls (brief) + an equal share of event-level calls."""
    mine = [r for r in rows if r["event"] == event]
    shared = sum(r["cost_usd"] for r in mine if not r["person"])
    own = {}
    for r in mine:
        if r["person"]:
            own[r["person"]] = own.get(r["person"], 0) + r["cost_usd"]
    return shared, own
