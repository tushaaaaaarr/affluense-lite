"""Score saved reports against the hand-checked answer keys in benchmarks/.

Usage:
  python evaluate.py                          every saved report that read a benchmarked filing
  python evaluate.py outputs/<event>/report.json
"""
import json
import sys
from pathlib import Path

from engine.shared import benchmark, config


def _pct(rate):
    return "n/a" if rate is None else f"{rate:.0%}"


def show(path, s):
    print(f"\n{s['name']}\n  report:  {path}\n  checked: {s['checked_against']}")
    print(f"  recall     {s['recall']['found']}/{s['recall']['expected']} sellers ({_pct(s['recall']['rate'])})")
    for group in ("individuals", "institutions"):
        g = s[group]
        missed = f"  missed: {', '.join(g['missed'])}" if g["missed"] else ""
        print(f"    {group:<13}{g['found']}/{g['expected']}{missed}")
    p = s["precision"]
    print(f"  precision  {p['correct']}/{p['claimed']} claimed sellers are real ({_pct(p['rate'])})"
          + (f"  false: {', '.join(p['false_positives'])}" if p["false_positives"] else ""))
    r = s["routing"]
    print(f"  routing    {r['correct']}/{r['checked']} put in the right list (person vs institution)"
          + (f"  wrong: {', '.join(r['misrouted'])}" if r["misrouted"] else ""))
    sh = s["shares"]
    print(f"  shares     {sh['exact']}/{sh['checked']} offered-share counts exact")
    for m in sh["mismatches"]:
        print(f"    {m['name']}: expected {m['expected']:,}, got {m['got']}")
    if s["other_leads"]:
        print(f"  outside the answer key (other transaction types): {len(s['other_leads'])}")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    paths = [Path(a) for a in sys.argv[1:]] or sorted(config.OUT_DIR.glob("*/report.json"))
    scored = 0
    for path in paths:
        s = benchmark.for_result(json.loads(path.read_text(encoding="utf-8")))
        if s:
            show(path, s)
            scored += 1
    if not scored:
        print("No saved report read a benchmarked filing. Try: python run.py events/sedemac_ipo.json")


if __name__ == "__main__":
    main()
