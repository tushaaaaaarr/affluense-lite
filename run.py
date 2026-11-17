"""Usage:
  python run.py events/my_event.json
  python run.py --name "Some Co IPO" --url https://... --url https://...   (new event, live)
  add --follow-web to also look for earlier deals of the top sellers (costs more)
"""
import argparse
import json
import os
import sys

from engine import pipeline
from engine.shared import config, report


def main():
    # names from PDFs can contain odd characters; never crash on printing them
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", nargs="?", help="path to event json")
    ap.add_argument("--name")
    ap.add_argument("--url", action="append", default=[])
    ap.add_argument("--follow-web", action="store_true")
    args = ap.parse_args()

    if args.spec:
        with open(args.spec, encoding="utf-8") as f:
            spec = json.load(f)
    elif args.name and args.url:
        spec = {"name": args.name, "sources": args.url}
    else:
        ap.error("give an event json OR --name and at least one --url")

    key_var = "OPENAI_API_KEY" if config.PROVIDER == "openai" else "ANTHROPIC_API_KEY"
    if not os.getenv(key_var):
        print(f"No {key_var} set. Cached answers still work, but new model calls will fail.")

    result = pipeline.run_event(spec, follow_web=args.follow_web)
    path = report.write(result)
    print()
    for i, p in enumerate(result["people"][:10], 1):
        print(f"  {i}. {p['name']}  ({p.get('link')}, confidence {p['confidence']})")
    print(f"\nwrote {path}")
    print("cost:", result["cost"], f"wall time: {result['wall_seconds']}s")


if __name__ == "__main__":
    main()
