# Affluense-lite: money event -> ranked list of people an RM should call

Give it a real Indian money event (IPO sale, buyback, acquisition) as a few public links.
It returns people who got paid, a rupee RANGE with working, timing, confidence, evidence links,
and a short RM brief.

## Run it (about 5 minutes)

```bash
pip install -r requirements.txt
python -m pytest -q                     # offline tests with a fake model, no key needed

# put your key in a .env file (it's in .gitignore, never committed)
copy .env.example .env                  # then paste your key into .env
# .env.example is set up for Google Gemini (free tier works). For Anthropic, see the
# commented lines in it. Values already set in your shell override .env.

# a saved event
python run.py events/sedemac_ipo.json

# a brand-new event, live (this is what you do on the call)
python run.py --name "Some Co buyback" --url https://link1 --url https://link2

# also hunt for earlier deals of the top sellers (Anthropic key only, costs more)
python run.py events/sedemac_ipo.json --follow-web
```
Output goes to `outputs/<event>/report.md` + `report.json`.
Costs: `outputs/cost_log.csv` (one row per model call, with person) and `outputs/runs.csv`
(one row per run: total $, wall time, $ per person).
Run the same command twice: the 2nd run is $0 and under a second (everything is cached).

**What the real runs cost** (model `gemini-3.5-flash-lite`, paid-tier prices; see `outputs/runs.csv`):
SEDEMAC IPO $0.021 (582-page prospectus, 18 people, 4 model calls, 20 s) · RBA acquisition
$0.0014 · Astrotalk buyback $0.0013 · Jio IPO $0.0041 · every second run $0.00.
The brief's cap is $2 per event.

**Free-tier limit:** Gemini's free tier allows about 20 requests per model per day. One event
uses 1-4, because call notes are written 10 people per request. If the quota runs out, the run
stops calling the model, uses template notes, and says so in the run notes.

**If a site blocks the download** (NSE/BSE often do), open it in a browser, save the PDF, and
point the event at the file while still citing the public link:
```json
{"name": "X Ltd IPO", "sources": [{"url": "https://public/link/rhp.pdf", "file": "C:/saved/rhp.pdf"}]}
```
The RBA and Astrotalk events work this way; their saved copies are in `events/saved/`
(included in the submission zip, kept out of Git).
Behind a company proxy? `truststore` (in requirements) makes Python use the Windows
certificate store, so HTTPS works without turning off verification.

## The agents (what each gets, returns, runs on)

```
 event links
     │
     v
 [1 FETCH]        engine/steps/fetcher.py                                   CODE
     │            gets: URL or saved file    returns: text with [[page N]] markers
     │            opens SEBI filing pages to their PDFs, blocks LinkedIn etc, obeys robots.txt,
     │            caches every download
     v
 [2 EXTRACT]      engine/steps/extractor.py  (+ verify.py)                  LLM + CODE
     │            code picks the relevant pages (~10k tokens) -> LLM returns JSON -> code checks it
     │            returns: people, role, the exact WORDS for shares/amount ("Rs 120 crore"),
     │            each with a word-for-word quote. Anything not found in the source is dropped.
     v
 [3 MATCH NAMES]  engine/steps/resolver.py                                  CODE
     │            "Mr. Rajesh Sharma" = "Rajesh Sharma" -> merge
     │            "R K Sharma" vs "Rajesh Kumar Sharma" -> NOT merged, both flagged, confidence down
     v
 [4 ESTIMATE]     engine/steps/estimator.py                                 CODE
     │            shares x price band = ₹ range, or stated amount ± 10% if rounded; working shown
     │            no number in source -> "not estimable" (never a guess)
     v
 [5 FOLLOW-ON]    engine/steps/followon.py                                  CODE (+ optional LLM)
     │            ledger of past runs: free, every person
     │            --follow-web: LLM web search returns URLs ONLY -> back through steps 1-2
     │            stops at: depth 1, top 3 people, 2 URLs each, cached, inside the $2 cap
     v
 [6 RANK]         engine/steps/ranker.py                                    CODE
     │            score = 50% amount + 30% confidence + 20% timing; companies go to a separate list
     v
 [7 BRIEF]        engine/steps/briefer.py                                   LLM + CODE
     │            ONE call writes notes for up to 10 people; each person's facts only.
     │            code checks each note: a new number, or a missing/cut-off note -> template
     v
 outputs/<event>/report.md + report.json, outputs/cost_log.csv, outputs/runs.csv
```
Only steps 2 and 7 use an LLM (plus the optional web search in 5). Everything else is
plain code because it has to be exact, free and repeatable.

What decides what runs next: the comment at the top of `engine/pipeline.py`.

## Why no LangGraph/CrewAI
The flow is a straight line with a few `if`s. A framework would add a learning curve without
adding anything here. It would start to earn its place if we needed retries with state,
human-in-the-loop pauses, or parallel branches per person.

## Folder structure
```
run.py               start here: the command line
engine/
  pipeline.py        calls the steps in order, decides what to skip
  steps/             one file per step (see diagram above)
  shared/            config.py (settings), llm.py (AI calls + cache), costlog.py, report.py
events/              one JSON per event; saved/ holds pages you saved by hand (not committed)
tests/               offline tests with a fake AI
docs/                Part A, Part C, decision log, what's broken
cache/  outputs/     created on first run
```

## Data rules followed
Public sources only. No LinkedIn. No phone/email/address collected. Delete `cache/` and
`outputs/` when the hiring process ends.
