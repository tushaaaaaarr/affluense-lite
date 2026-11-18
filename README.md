# Affluense-lite: money event -> ranked list of people an RM should call

Give it a real Indian money event (IPO sale, buyback, acquisition) as a few public links.
It returns people who got paid, a rupee RANGE with working, timing, confidence, evidence links,
and a short RM brief.

## Run it (about 5 minutes)

```bash
pip install -r backend/requirements.txt
python -m pytest -q                     # offline tests with a fake model, no key needed

# put your key and private log sign-in credentials in backend/.env (never commit it)
copy backend/.env.example backend/.env  # then paste your key into backend/.env
# backend/.env.example is set up for Google Gemini (free tier works). For Anthropic, see the
# commented lines in it. Replace LOGS_USERNAME and LOGS_PASSWORD with private values too.
# Values already set in your shell override .env.

# a saved event
python backend/run.py backend/events/sedemac_ipo.json
python backend/run.py backend/events/fdc_buyback.json
python backend/run.py backend/events/coding_ninjas_acquisition.json

# a brand-new event, live (this is what you do on the call)
python backend/run.py --name "Some Co buyback" --url https://link1 --url https://link2

# also hunt for earlier deals of the top sellers (Anthropic key only, costs more)
python backend/run.py backend/events/sedemac_ipo.json --follow-web
```
Output goes to `backend/outputs/<event>/report.md` + `report.json`.
Costs: `backend/outputs/cost_log.csv` (one row per model call, with person) and `backend/outputs/runs.csv`
(one row per run: total $, wall time, $ per person).
Run the same command twice: the 2nd run is $0 and under a second (everything is cached).

## Web app (Vercel + Render)

The React frontend is in `frontend/`; the FastAPI service, CLI, tests, and `engine/` are all in
`backend/`. Render's free web service can sleep when idle, so the first
request may take a little while to wake up. Its filesystem is temporary: cached downloads and
CSV logs can be cleared when the service restarts or redeploys.

1. Deploy this repository to Render using the blueprint in `backend/render.yaml` (or create a
    Python web service with build command `pip install -r backend/requirements.txt` and start command
    `uvicorn app:app --app-dir backend --host 0.0.0.0 --port $PORT`).
2. In Render, set the model environment variables from `backend/.env.example`, plus
    `FRONTEND_ORIGINS=https://<your-vercel-domain>`.
3. Import the repository in Vercel with `frontend` as the root directory. Set
    `VITE_API_URL=https://<your-render-service>.onrender.com`, then deploy.
4. For local development, install `backend/requirements.txt`, run
    `uvicorn app:app --app-dir backend --reload` from the repository root, and run `npm install` then
    `npm run dev` from `frontend/`. Copy `frontend/.env.example` to `frontend/.env` if needed.
    Set private `LOGS_USERNAME` and `LOGS_PASSWORD` values in Render's environment and local
    `backend/.env`. The UI uses HTTP Basic sign-in for logs; keep these values out of the frontend
    environment and never commit them.

The API accepts public HTTP(S) source links and optional uploaded PDF copies for blocked sources.
It exposes `/api/health`, `POST /api/events/analyze`, and `POST /api/events/analyze-upload`.

### Example UI inputs

Open the frontend and paste the event name into **Event name** and the URLs into **Source links**,
one URL per line. Use public pages or PDFs. For blocked pages, attach a saved PDF or HTML copy with
its public citation URL.

**SEDEMAC IPO**
```text
Event name: SEDEMAC Mechatronics IPO (Mar 2026)
Source links:
https://www.tradejini.com/blogs/sedemac-mechatronics-ipo-mainboard-mechatronics-ipo-in-mobility-and-industrial-markets
https://www.sebi.gov.in/sebi_data/attachdocs/mar-2026/1773656117962.PDF
```

**Jio Platforms IPO** (fresh issue; a successful run may correctly return no individual sellers)
```text
Event name: Jio Platforms IPO (Oct 2026)
Source links:
https://www.sebi.gov.in/sebi_data/attachdocs/oct-2026/1792045029108.pdf
```

**FDC Limited buyback** (tender offer; the Letter of Offer names the promoters who intend to tender)
```text
Event name: FDC Limited buyback (Nov 2026)
Source links:
https://www.sebi.gov.in/filings/buybacks/oct-2026/fdc-limited_105562.html
```
The SEBI filing page is expanded to its Letter of Offer and Public Announcement. Each promoter's range
runs from their guaranteed entitlement (the filing's general-category ratio x shares offered x ₹500)
up to everything accepted, capped at the ₹120 crore buyback size.

**BrowserStack ESOP buyback** (official company announcement; recipients are not individually named)
```text
Event name: BrowserStack ESOP and share buyback (Jan 2026)
Source links:
https://www.browserstack.com/press/browserstack-announces-125-million-esop-and-share-buyback-program-creating-wealth-for-over-500-employees
```

**Info Edge / Coding Ninjas acquisition** (founder-held stake purchase)
```text
Event name: Info Edge acquisition of Coding Ninjas founder stake (Jul 2026)
Source links:
https://www.infoedge.in/announcements/SEIntimationCodingNinjaandB88726.pdf
https://entrackr.com/news/info-edge-takes-full-control-of-coding-ninjas-after-acquiring-remaining-45-stake-for-rs-399-cr-12140095
```
The official filing states that 45.36% was acquired from Coding Ninjas' founders for about ₹39.91 crore; it does not name the individual sellers, so the system should not invent a person-level split.

### View and download cost logs

Open **Run and cost logs**, sign in with the `LOGS_USERNAME` and `LOGS_PASSWORD` configured for the
backend, and load either **Run history** (`runs.csv`) or **Model calls** (`cost_log.csv`). The UI
shows the latest 100 rows and downloads the complete CSV. Access is password-protected because call
logs may contain names. A fresh deployment shows empty logs until it has processed an event.

### Evidence review and evaluation

Each lead separates identity-match, transaction-evidence, and amount-method indicators. The source
count and URLs show whether evidence is corroborated across independent links. These are transparent
rule-based heuristics, not calibrated probabilities; the amount range and its working remain separate.
Use the per-row **RM review** control to accept, reject, or flag a lead and optionally record a note.
Decisions are upserted by run and person in `backend/cache/reviews.sqlite`; **Review and logs → RM
reviews** shows recent decisions and can export them as CSV. Review endpoints use the same Basic
sign-in as cost logs. The database is local/ephemeral on a free Render instance.

Run `python -m pytest -q` for the offline evaluation set. It includes source-quote verification,
buyback spokesperson rejection, ambiguous-name handling, corroboration signals, and valid no-lead
outcomes. Live event outputs are also retained in `backend/outputs/<event>/report.json` for manual
spot checks.

**What the real runs cost** (model `gemini-3.5-flash-lite`, paid-tier prices; see `backend/outputs/runs.csv`):
SEDEMAC IPO $0.021 (582-page prospectus, 18 people, 4 model calls, 20 s) · Jio IPO $0.0041.
BrowserStack first run $0.0013 (2 calls; cached rerun $0) · Info Edge/Coding Ninjas $0.0027 (2 calls).
Older Astrotalk and RBA cost rows remain in the CSV history; their report files are no longer in the active outputs.
The brief's cap is $2 per event.

**Free-tier limit:** Gemini's free tier allows about 20 requests per model per day. One event
uses 1-4, because call notes are written 10 people per request. If the quota runs out, the run
stops calling the model, uses template notes, and says so in the run notes.

**If a site blocks the download** (NSE/BSE often do), add the public link to **Source links**, expand
**Source blocked? Attach a saved copy**, repeat that same public URL as the citation URL, and choose
the PDF or HTML page saved from your browser. Uploads are limited to 25 MB and are deleted after
analysis. The old RBA and Astrotalk saved source copies remain in `backend/events/saved/` if you need to rerun those legacy inputs.
The CLI also accepts this source format:
```json
{"name": "X Ltd IPO", "sources": [{"url": "https://public/link/rhp.pdf", "file": "C:/saved/rhp.pdf"}]}
```
Behind a company proxy? `truststore` (in requirements) makes Python use the Windows
certificate store, so HTTPS works without turning off verification.

## The agents (what each gets, returns, runs on)

```
 event links
     │
     v
 [1 FETCH]        backend/engine/steps/fetcher.py                            CODE
     │            gets: URL or saved file    returns: text with [[page N]] markers
     │            opens SEBI filing pages to their PDFs, blocks LinkedIn etc, obeys robots.txt,
     │            caches every download
     v
 [2 EXTRACT]      backend/engine/steps/extractor.py  (+ verify.py)           LLM + CODE
     │            code picks the relevant pages (~10k tokens) -> LLM returns JSON -> code checks it
     │            returns: people, role, the exact WORDS for shares/amount ("Rs 120 crore"),
     │            each with a word-for-word quote. Anything not found in the source is dropped.
     v
 [3 MATCH NAMES]  backend/engine/steps/resolver.py                           CODE
     │            "Mr. Rajesh Sharma" = "Rajesh Sharma" -> merge
     │            "R K Sharma" vs "Rajesh Kumar Sharma" -> NOT merged, both flagged, confidence down
     v
 [4 ESTIMATE]     backend/engine/steps/estimator.py                          CODE
     │            shares x price band = ₹ range, or stated amount ± 10% if rounded; working shown
     │            no number in source -> "not estimable" (never a guess)
     v
 [5 FOLLOW-ON]    backend/engine/steps/followon.py                           CODE (+ optional LLM)
     │            ledger of past runs: free, every person
     │            --follow-web: LLM web search returns URLs ONLY -> back through steps 1-2
     │            stops at: depth 1, top 3 people, 2 URLs each, cached, inside the $2 cap
     v
 [6 RANK]         backend/engine/steps/ranker.py                             CODE
     │            score = 50% amount + 30% confidence + 20% timing; separate identity/transaction/amount signals
     │            and source corroboration are reported as heuristics, not probabilities
     v
 [7 BRIEF]        backend/engine/steps/briefer.py                            LLM + CODE
     │            ONE call writes notes for up to 10 people; each person's facts only.
     │            code checks each note: a new number, or a missing/cut-off note -> template
     v
 backend/outputs/<event>/report.md + report.json, cost_log.csv, runs.csv
```
Only steps 2 and 7 use an LLM (plus the optional web search in 5). Everything else is
plain code because it has to be exact, free and repeatable.

What decides what runs next: the comment at the top of `backend/engine/pipeline.py`.

## Why no LangGraph/CrewAI
The flow is a straight line with a few `if`s. A framework would add a learning curve without
adding anything here. It would start to earn its place if we needed retries with state,
human-in-the-loop pauses, or parallel branches per person.

## Folder structure
```
backend/
    app.py             FastAPI service
    run.py             command-line entry point
    engine/
        pipeline.py      calls the steps in order, decides what to skip
        steps/           one file per step (see diagram above)
        shared/          config.py (settings), llm.py (AI calls + cache), costlog.py, report.py
    events/            one JSON per event; saved/ holds pages you saved by hand (not committed)
    tests/             offline tests with a fake AI
    cache/ outputs/    created on first run
frontend/             Vite React application
docs/                 Part A, Part C, decision log, what's broken
```
