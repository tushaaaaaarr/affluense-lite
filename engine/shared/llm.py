"""One place where we talk to the model. It does 3 things:
1. cache (same prompt -> no new call, no cost)  <- this is how repeat runs get cheap
2. cost + time logging
3. stop if the event budget is used up
"""
import hashlib
import sqlite3
import time

from engine.shared import config, costlog

_db = sqlite3.connect(config.CACHE_DIR / "llm_cache.sqlite")
_db.execute("create table if not exists calls (key text primary key, text text, in_tok int, out_tok int)")
_client = None
_warned = set()


def _cost(model, in_tok, out_tok):
    if model not in config.PRICES and model not in _warned:
        _warned.add(model)
        print(f"WARNING: no price for '{model}' in config.PRICES, cost log will show $0")
    price_in, price_out = config.PRICES.get(model, (0, 0))
    return in_tok / 1e6 * price_in + out_tok / 1e6 * price_out


def _call(model, system, prompt, max_tokens):
    """Returns (text, input_tokens, output_tokens). The only provider-specific code.
    A reply cut off at max_tokens comes back as "" so callers treat it as no answer."""
    global _client
    if config.PROVIDER == "openai":
        import openai
        if _client is None:
            # Gemini often answers 503 "high demand"; the SDK retries those with backoff
            _client = openai.OpenAI(max_retries=5, timeout=180)
        extra = {"reasoning_effort": config.REASONING_EFFORT} if config.REASONING_EFFORT else {}
        try:
            resp = _client.chat.completions.create(
                model=model, max_tokens=max_tokens,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                **extra,
            )
        except openai.RateLimitError as e:
            if "PerDay" in str(e) or "per day" in str(e):
                # retrying can't help until tomorrow, so stop like the $ cap does
                raise costlog.BudgetError(f"daily request quota for {model} is used up "
                                          f"(free tier). Cached steps still work.") from e
            raise
        u = resp.usage
        # Gemini leaves hidden "thinking" tokens out of completion_tokens but bills them as output
        out_tok = max(u.completion_tokens or 0, (u.total_tokens or 0) - (u.prompt_tokens or 0))
        cut = resp.choices[0].finish_reason == "length"
        return ("" if cut else resp.choices[0].message.content or ""), u.prompt_tokens, out_tok

    if _client is None:
        import anthropic          # imported late so tests work without the package/key
        _client = anthropic.Anthropic()
    resp = _client.messages.create(
        model=model, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    if getattr(resp, "stop_reason", "") == "max_tokens":
        text = ""
    return text, resp.usage.input_tokens, resp.usage.output_tokens


def ask(system, prompt, stage, event, person="", max_tokens=2500, model=None):
    model = model or config.MODEL
    key = hashlib.sha256(f"{model}|{system}|{prompt}".encode()).hexdigest()

    row = _db.execute("select text, in_tok, out_tok from calls where key=?", (key,)).fetchone()
    if row:
        costlog.log(event, stage, model, row[1], row[2], 0.0, 0.0, True, person)
        return row[0]

    costlog.check_budget(event)

    t0 = time.time()
    text, in_tok, out_tok = _call(model, system, prompt, max_tokens)
    secs = time.time() - t0

    if text.strip():                 # never cache an empty or cut-off answer
        _db.execute("insert or replace into calls values (?,?,?,?)", (key, text, in_tok, out_tok))
        _db.commit()
    costlog.log(event, stage, model, in_tok, out_tok, _cost(model, in_tok, out_tok), secs, False, person)
    return text
