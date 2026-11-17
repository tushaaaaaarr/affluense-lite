"""All the knobs in one place so I don't hunt through files later."""
import os
from pathlib import Path

try:                    # use the OS certificate store (needed behind corporate HTTPS proxies)
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parents[2]      # project folder (this file is engine/shared/)
CACHE_DIR = ROOT / "cache"
OUT_DIR = ROOT / "outputs"
CACHE_DIR.mkdir(exist_ok=True)
OUT_DIR.mkdir(exist_ok=True)


def _load_env_file(path):
    """KEY=value lines from .env (kept out of git). Variables already set in the shell win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_env_file(ROOT / ".env")

# Which API the key is for: "anthropic" (default) or "openai" (any OpenAI-compatible endpoint,
# set OPENAI_BASE_URL if it isn't api.openai.com). I don't know yet which key Klypup will send.
PROVIDER = os.getenv("AFF_PROVIDER", "anthropic").lower()

# cheap model for reading filings + writing briefs. Change with AFF_MODEL env var.
MODEL = os.getenv("AFF_MODEL", "claude-haiku-5-5" if PROVIDER == "anthropic" else "gpt-4o-mini")

# Gemini "thinks" before answering and bills it as output. "low" keeps that small; empty = model default.
# ("none" timed out on gemini-3.5-flash when I tested it.)
REASONING_EFFORT = os.getenv("AFF_REASONING_EFFORT", "")

# USD per 1M tokens (input, output). Output price includes thinking tokens.
# Gemini: from cloud.google.com/vertex-ai/generative-ai/pricing, read 15 Nov 2026 (global endpoint).
# Claude/OpenAI rows are placeholders I could not check. On the Gemini free tier the real bill is $0;
# the log still shows what the run would cost on the paid tier, which is the honest number to compare.
# A model missing from this dict is logged at $0, so the run prints a warning (see llm.py).
PRICES = {
    "gemini-3.5-flash": (1.50, 9.00),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.6-flash": (0.75, 3.75),       # intro price until 31 Dec 2026
    "gemini-3.8-flash": (0.75, 3.75),       # intro price until 31 Dec 2026
    "claude-haiku-5-5": (1.0, 5.0),
    "claude-sonnet-5-5": (3.0, 15.0),
    "gpt-4o-mini": (0.15, 0.60),
}
WEB_SEARCH_COST_USD = 0.01     # per search, charged on top of tokens (placeholder, check it)

MAX_COST_PER_EVENT = 2.00      # the brief says aim for under $2
MAX_CHARS_TO_LLM = 40000       # how much filing text we send for extraction (~10k tokens)
MAX_LINKED_DOCS = 4            # a SEBI filing page can link several PDFs; read at most this many
EXTRACT_MAX_OUT_TOKENS = 8000  # an RHP can list 20+ sellers; a cut-off JSON is useless
BRIEF_BATCH = 10               # people per call-note request (free Gemini tier: 20 requests/day)

# Some news gives amounts in dollars. This rate is MY assumption and is printed in the working.
USD_INR = 88.0

# A stated but rounded figure ("Rs 120 crore") or a USD conversion is shown as +/- this much.
# Also my assumption, printed in the working.
ROUNDED_BAND = 0.10

# sites we never fetch (terms forbid scraping)
BLOCKED_DOMAINS = ["linkedin.com", "facebook.com", "instagram.com", "x.com", "twitter.com"]

# follow-on lead limits
FOLLOW_MAX_DEPTH = 1           # only look one hop away from the original event
FOLLOW_MAX_PEOPLE = 3          # only chase the top 3 people
FOLLOW_MAX_URLS_EACH = 2

# "up to N shares" in an offer means the real number sold can be lower.
# This is MY assumption (an estimate), shown in the working of every amount that uses it.
UP_TO_FACTOR = 0.5
