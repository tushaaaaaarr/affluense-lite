import { Fragment, useEffect, useRef, useState } from "react";
import * as XLSX from "xlsx";
import { ArrowDownRight, ArrowLeft, ArrowUpRight, Check, ChevronDown, ChevronRight, CircleAlert, ClipboardCheck, Download, ExternalLink, FileText, FileUp, History, KeyRound, ListOrdered, LoaderCircle, MessageSquareText, Moon, Quote, Search, ShieldCheck, Sparkles, Sun, Target, Users, X } from "lucide-react";

const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

const STAGES = [
  { id: "fetch", label: "Read sources" },
  { id: "extract", label: "Extract and verify quotes" },
  { id: "match", label: "Match names" },
  { id: "estimate", label: "Estimate proceeds and timing" },
  { id: "follow", label: "Check earlier deals" },
  { id: "rank", label: "Rank leads" },
  { id: "brief", label: "Write call notes" },
];

const SCORE_PARTS = [["amount", "Proceeds size"], ["confidence", "Identity confidence"], ["timing", "Timing"]];

function percent(rate) {
  return rate == null ? "n/a" : `${Math.round(rate * 100)}%`;
}

function errorDetail(body, fallback) {
  if (typeof body?.detail === "string") return body.detail;
  if (Array.isArray(body?.detail) && body.detail[0]?.msg) return body.detail[0].msg.replace(/^Value error, /, "");
  return fallback;
}

function apiError(reason) {
  return reason.message === "Failed to fetch"
    ? "Can't reach the analysis API. Check its URL and that the backend is awake."
    : reason.message;
}

function evidenceHref(item) {
  if (!/^https?:\/\//i.test(item.url || "")) return undefined;
  const base = item.url.split("#")[0];
  return item.page && /\.pdf($|\?)/i.test(base) ? `${base}#page=${item.page}` : item.url;
}

async function readAnalysisStream(response, onProgress) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop();
    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line);
      if (event.type === "progress") onProgress(event);
      else if (event.type === "result") return event.result;
      else if (event.type === "error") throw new Error(event.detail);
    }
    if (done) throw new Error("The analysis stopped before it finished. Try again.");
  }
}

function amountLabel(amount) {
  if (amount?.high == null) return "Not estimable";
  const crore = (amount.high / 10_000_000).toLocaleString("en-IN", { maximumFractionDigits: 1 });
  if (amount.low === amount.high) return `₹${crore} cr`;
  const low = (amount.low / 10_000_000).toLocaleString("en-IN", { maximumFractionDigits: 1 });
  return `₹${low}–${crore} cr`;
}

function safeSpreadsheetText(value) {
  const text = value == null ? "" : String(value);
  return /^[\s]*[=+\-@]/.test(text) ? `'${text}` : text;
}

function reasonLabel(link) {
  const labels = {
    sold_in_offer: "Sold shares in offer",
    tendered_in_buyback: "Tendered shares in buyback",
    sold_to_acquirer: "Sold shares to acquirer",
    esop: "ESOP shares held or paid out",
    early_investor: "Early investor exit",
    other: "Other transaction",
  };
  return labels[link] || "Transaction not classified";
}

function csvCell(value) {
  const raw = value == null ? "" : String(value);
  const safe = /^[\s]*[=+\-@]/.test(raw) ? `'${raw}` : raw;
  return `"${safe.replaceAll('"', '""')}"`;
}

function basicAuthHeader(username, password) {
  const bytes = new TextEncoder().encode(`${username}:${password}`);
  const binary = Array.from(bytes, (byte) => String.fromCharCode(byte)).join("");
  return `Basic ${btoa(binary)}`;
}

function downloadWorkbook(result) {
  const people = result.people || [];
  const institutions = result.institutions || [];
  const allLeads = [
    ...people.map((person, index) => ({ person, rank: index + 1, category: "Individual" })),
    ...institutions.map((institution, index) => ({ person: institution, rank: index + 1, category: "Institution" })),
  ];
  const workbook = XLSX.utils.book_new();
  const summaryRows = [
    { Field: "Event", Value: safeSpreadsheetText(result.event) },
    { Field: "Analysis status", Value: safeSpreadsheetText(result.analysis_status || "complete") },
    { Field: "Sources analyzed", Value: `${result.source_counts?.succeeded ?? "?"} / ${result.source_counts?.attempted ?? "?"}` },
    { Field: "Company", Value: safeSpreadsheetText(result.event_info?.company) },
    { Field: "Event type", Value: safeSpreadsheetText(result.event_info?.kind) },
    { Field: "Event date", Value: safeSpreadsheetText(result.event_info?.date) },
    { Field: "People", Value: people.length },
    { Field: "Institutional sellers", Value: institutions.length },
    { Field: "Model cost (USD)", Value: result.cost?.cost_usd ?? 0 },
  ];
  const leads = allLeads.map(({ person, rank, category }) => ({
    Rank: rank,
    Category: category,
    Name: safeSpreadsheetText(person.name),
    Role: safeSpreadsheetText(person.role),
    "Sale type": safeSpreadsheetText(person.link?.replaceAll("_", " ")),
    "Estimated low (INR)": person.amount?.low ?? "",
    "Estimated high (INR)": person.amount?.high ?? "",
    Estimate: safeSpreadsheetText(amountLabel(person.amount)),
    "Estimate working": safeSpreadsheetText(person.amount?.working),
    Timing: safeSpreadsheetText(person.timing?.status),
    "Timing details": safeSpreadsheetText(person.timing?.text),
    "Confidence (%)": Math.round((person.confidence || 0) * 100),
    "Identity confidence (%)": Math.round((person.confidence_dimensions?.identity?.score ?? person.confidence ?? 0) * 100),
    "Transaction confidence (%)": Math.round((person.confidence_dimensions?.transaction?.score ?? 0) * 100),
    "Amount confidence": person.confidence_dimensions?.amount?.status || "not available",
    "Source corroboration": person.confidence_dimensions?.corroboration?.source_count ?? person.evidence?.length ?? 0,
    "Priority score": person.score ?? "",
    "Call note": safeSpreadsheetText(person.brief),
    "Earlier events": safeSpreadsheetText((person.earlier_events || []).map((item) => item.event || item.name || "").filter(Boolean).join("; ")),
  }));
  const evidence = allLeads.flatMap(({ person, category }) => (person.evidence || []).map((item) => ({
    Category: category,
    Name: safeSpreadsheetText(person.name),
    Source: safeSpreadsheetText(item.url),
    Page: item.page ?? "",
    Quote: safeSpreadsheetText(item.quote),
  })));
  const appendSheet = (name, rows, widths) => {
    const sheet = XLSX.utils.json_to_sheet(rows);
    sheet["!cols"] = widths.map((wch) => ({ wch }));
    XLSX.utils.book_append_sheet(workbook, sheet, name);
  };

  appendSheet("Summary", summaryRows, [24, 72]);
  appendSheet("Leads", leads, [8, 14, 30, 30, 24, 20, 20, 24, 72, 15, 72, 16, 18, 19, 24, 20, 16, 72, 48]);
  appendSheet("Evidence", evidence, [14, 30, 72, 10, 100]);
  if (institutions.length) {
    appendSheet("Institutions", leads.filter((lead) => lead.Category === "Institution"), [8, 14, 36, 34, 24, 20, 20, 24, 72, 15, 72, 16, 16, 72, 48]);
  }

  const filename = (result.event || "affluense-analysis")
    .replace(/[<>:"/\\|?*]+/g, "-").trim().slice(0, 70) || "affluense-analysis";
  XLSX.writeFile(workbook, `${filename}.xlsx`);
}

function App() {
  const [name, setName] = useState("");
  const [sourceText, setSourceText] = useState("");
  const [followWeb, setFollowWeb] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [logsOpen, setLogsOpen] = useState(false);
  const [logsUsername, setLogsUsername] = useState("");
  const [logsPassword, setLogsPassword] = useState("");
  const [logsAuthenticated, setLogsAuthenticated] = useState(false);
  const [logKind, setLogKind] = useState("runs");
  const [logData, setLogData] = useState(null);
  const [logsError, setLogsError] = useState("");
  const [logsLoading, setLogsLoading] = useState(false);
  const [downloadLoading, setDownloadLoading] = useState(false);
  const [reviewDecisions, setReviewDecisions] = useState({});
  const [reviewNotes, setReviewNotes] = useState({});
  const [reviewStatuses, setReviewStatuses] = useState({});
  const [sourceFile, setSourceFile] = useState(null);
  const [sourceFileUrl, setSourceFileUrl] = useState("");
  const [leadView, setLeadView] = useState("people");
  const [expandedRows, setExpandedRows] = useState({});
  const [progress, setProgress] = useState([]);
  const [runs, setRuns] = useState([]);
  const [openingRun, setOpeningRun] = useState("");
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme === "dark" ? "dark" : "light");

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("theme", theme);
    } catch {
      // storage can be blocked; the theme still applies for this visit
    }
  }, [theme]);
  // results shown per browser-history entry, so Back/Forward can restore them
  const shownResults = useRef(new Map());

  useEffect(() => {
    loadRuns();
    const linkedRun = window.location.hash.match(/^#run=(.+)$/)?.[1];
    if (linkedRun) openRun(decodeURIComponent(linkedRun), { replace: true });
    function onPopState(event) {
      setExpandedRows({});
      setLeadView("people");
      setResult(shownResults.current.get(event.state?.resultKey) || null);
    }
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  function showResult(body, runId, { replace = false } = {}) {
    const resultKey = runId ? `run:${runId}` : `analysis:${Date.now()}`;
    shownResults.current.set(resultKey, body);
    setLeadView("people");
    setExpandedRows({});
    setResult(body);
    const url = runId ? `#run=${encodeURIComponent(runId)}` : "#result";
    window.history[replace ? "replaceState" : "pushState"]({ resultKey }, "", url);
  }

  function closeResult() {
    if (window.history.state?.resultKey) {
      window.history.back();
      return;
    }
    setResult(null);
    setExpandedRows({});
  }

  async function loadRuns() {
    try {
      const response = await fetch(`${API_URL}/api/runs`);
      if (response.ok) setRuns((await response.json()).runs || []);
    } catch {
      // history is optional; the form works without it
    }
  }

  async function openRun(id, options) {
    setError("");
    setOpeningRun(id);
    try {
      const response = await fetch(`${API_URL}/api/runs/${encodeURIComponent(id)}`);
      const body = await response.json();
      if (!response.ok) throw new Error(errorDetail(body, "Could not open this analysis."));
      showResult(body, id, options);
    } catch (reason) {
      setError(apiError(reason));
    } finally {
      setOpeningRun("");
    }
  }

  async function analyze(event) {
    event.preventDefault();
    setError("");
    setResult(null);
    setProgress([]);
    setLeadView("people");
    setExpandedRows({});
    const urls = sourceText.split(/\r?\n/).map((url) => url.trim()).filter(Boolean);
    if (!name.trim() || urls.length === 0) {
      setError("Add an event name and at least one source link.");
      return;
    }
    if (sourceFile && (!sourceFileUrl.trim() || !urls.includes(sourceFileUrl.trim()))) {
      setError("Add the uploaded source's public URL to Source links and enter the same URL below the upload field.");
      return;
    }
    if (sourceFile && (sourceFile.size > 25 * 1024 * 1024 || !/\.(pdf|html?)$/i.test(sourceFile.name))) {
      setError("Upload a PDF or HTML page smaller than 25 MB.");
      return;
    }
    setLoading(true);
    try {
      let response;
      if (sourceFile) {
        const formData = new FormData();
        formData.append("name", name.trim());
        formData.append("urls", urls.join("\n"));
        formData.append("source_file_url", sourceFileUrl.trim());
        formData.append("source_file", sourceFile);
        formData.append("follow_web", String(followWeb));
        formData.append("stream", "true");
        response = await fetch(`${API_URL}/api/events/analyze-upload`, { method: "POST", body: formData });
      } else {
        response = await fetch(`${API_URL}/api/events/analyze`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: name.trim(), urls, follow_web: followWeb, stream: true }),
        });
      }
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(errorDetail(body, "The analysis could not be completed."));
      }
      const finished = await readAnalysisStream(response, (update) => setProgress((current) => [...current, update]));
      showResult(finished);
      loadRuns();
    } catch (reason) {
      setError(apiError(reason));
    } finally {
      setLoading(false);
    }
  }

  async function loadLogs(kind = logKind) {
    if (!logsUsername || !logsPassword) {
      setLogsError("Enter the log username and password configured on the backend.");
      return;
    }
    setLogKind(kind);
    setLogsError("");
    setLogsLoading(true);
    try {
      const endpoint = kind === "reviews" ? "/api/reviews" : `/api/logs/${kind}`;
      const response = await fetch(`${API_URL}${endpoint}`, {
        headers: { Authorization: basicAuthHeader(logsUsername, logsPassword) },
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "Could not load the log.");
      setLogData(body);
      setLogsAuthenticated(true);
    } catch (reason) {
      setLogData(null);
      setLogsAuthenticated(false);
      setLogsError(reason.message === "Failed to fetch"
        ? "Can't reach the analysis API. Check its URL and that the backend is awake."
        : reason.message);
    } finally {
      setLogsLoading(false);
    }
  }

  async function downloadLogCsv() {
    if (!logsUsername || !logsPassword) {
      setLogsError("Enter the log username and password configured on the backend.");
      return;
    }
    setLogsError("");
    setDownloadLoading(true);
    try {
      if (logKind === "reviews") {
        const rows = logData?.rows || [];
        const columns = logData?.columns || [];
        const content = [columns.map(csvCell).join(","), ...rows.map((row) => columns.map((column) => csvCell(row[column])).join(","))].join("\r\n");
        const blobUrl = URL.createObjectURL(new Blob([content], { type: "text/csv;charset=utf-8" }));
        const link = document.createElement("a");
        link.href = blobUrl;
        link.download = "rm_reviews.csv";
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
        return;
      }
      const response = await fetch(`${API_URL}/api/logs/csv/${logKind}`, {
        headers: { Authorization: basicAuthHeader(logsUsername, logsPassword) },
      });
      if (!response.ok) {
        const body = await response.json();
        throw new Error(body.detail || "Could not download the log.");
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = logKind === "costs" ? "cost_log.csv" : "runs.csv";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (reason) {
      setLogsError(reason.message === "Failed to fetch"
        ? "Can't reach the analysis API. Check its URL and that the backend is awake."
        : reason.message);
    } finally {
      setDownloadLoading(false);
    }
  }

  function reviewKey(person) {
    return `${result?.run_id || result?.event || "run"}:${person.name}`;
  }

  async function saveReview(person) {
    const key = reviewKey(person);
    const decision = reviewDecisions[key];
    if (!decision) {
      setReviewStatuses((current) => ({ ...current, [key]: "Choose a review decision first." }));
      return;
    }
    if (!logsUsername || !logsPassword) {
      setReviewStatuses((current) => ({ ...current, [key]: "Sign in under Logs to save reviews." }));
      setLogsOpen(true);
      return;
    }
    setReviewStatuses((current) => ({ ...current, [key]: "Saving…" }));
    try {
      const response = await fetch(`${API_URL}/api/reviews`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: basicAuthHeader(logsUsername, logsPassword),
        },
        body: JSON.stringify({
          run_id: result.run_id || result.event,
          event: result.event,
          person: person.name,
          decision,
          note: reviewNotes[key] || "",
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "Could not save this review.");
      setReviewStatuses((current) => ({ ...current, [key]: "Saved to review history." }));
    } catch (reason) {
      setReviewStatuses((current) => ({ ...current, [key]: reason.message }));
    }
  }

  const people = result?.people || [];
  const institutions = result?.institutions || [];
  const leads = leadView === "institutions" ? institutions : people;
  const decisionLabels = { accepted: "Accepted", rejected: "Rejected", needs_review: "Flagged" };
  const toggleRow = (key) => setExpandedRows((current) => ({ ...current, [key]: !current[key] }));
  const topAmount = people[0]?.amount;
  const analysisStatus = result?.analysis_status || "complete";
  const funnel = result?.funnel;
  const bench = result?.benchmark;
  const benchIssues = bench ? [
    ...[...bench.individuals.missed, ...bench.institutions.missed].map((who) => `Missed: ${who}`),
    ...bench.precision.false_positives.map((who) => `Not a seller in the filing: ${who}`),
    ...bench.routing.misrouted.map((who) => `Put in the wrong list: ${who}`),
    ...bench.shares.mismatches.map((row) => `Share count for ${row.name}: expected ${row.expected.toLocaleString("en-IN")}, read ${row.got == null ? "nothing" : row.got.toLocaleString("en-IN")}`),
  ] : [];
  const stageMessages = Object.fromEntries(progress.map((update) => [update.stage, update.message]));
  const lastStage = progress.at(-1)?.stage;
  const currentStage = lastStage === "done" ? STAGES.length : Math.max(0, STAGES.findIndex((stage) => stage.id === lastStage));
  const statusLabels = {
    complete: "Verified",
    partial: "Partial",
    no_leads: "No leads",
    failed: "Needs attention",
  };
  const logLabels = logKind === "costs"
    ? { run_id: "Run ID", time: "Time", event: "Event", stage: "Stage", person: "Person", model: "Model", in_tokens: "Input tokens", out_tokens: "Output tokens", cost_usd: "Cost (USD)", seconds: "Seconds", cached: "Cached" }
    : logKind === "reviews"
      ? { run_id: "Run ID", event: "Event", person: "Person", decision: "Decision", note: "Note", updated_at: "Reviewed at" }
      : { run_id: "Run ID", time: "Time", event: "Event", model: "Model", llm_calls: "Calls", cached_calls: "Cached", cost_usd: "Cost (USD)", wall_seconds: "Wall seconds", people: "People", cost_per_person_usd: "Cost / person" };

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="topbar-brand">
          <a className="wordmark" href="#top" aria-label="Affluense home">
            <span className="mark"><span /></span>
            <span>affluense<span className="wordmark-lite">lite</span></span>
          </a>
          <span className="beta-badge"><span className="status-dot" /> Private beta · India</span>
        </div>
        <div className="topbar-actions">
          <button className="theme-toggle" type="button" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`} title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}>{theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}</button>
          <button className="logs-open-button" type="button" onClick={() => setLogsOpen(true)} aria-expanded={logsOpen}><ClipboardCheck size={15} /> Review & logs</button>
          <a className="docs-link" href="https://github.com/tushaaaaaarr/affluense-lite" target="_blank" rel="noreferrer">Project <ExternalLink size={14} /></a>
        </div>
      </header>

      <section className="intro" id="top">
        <h1>Find the people behind the event</h1>
        <p className="intro-copy">Turn public filings and news into a verified, prioritized call list for your next conversation.</p>
      </section>

      <div className="workspace">
        <section className="input-panel" aria-labelledby="form-heading">
          <div className="panel-heading">
            <h2 id="form-heading">New analysis</h2>
            <p className="panel-subtitle">Describe the event and add its public sources.</p>
          </div>
          <form onSubmit={analyze}>
            <label htmlFor="event-name">Event name</label>
            <input id="event-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Acme Ltd IPO" maxLength={160} />

            <label htmlFor="source-links">Source links <span className="label-note">Up to 8</span></label>
            <textarea id="source-links" value={sourceText} onChange={(event) => setSourceText(event.target.value)} placeholder={"Paste public links, one per line\nhttps://..."} rows={5} />
            <div className="field-hint"><ShieldCheck size={14} /> Evidence is checked against the source text.</div>
            <details className="upload-details">
              <summary><FileUp size={14} /> Source blocked? Attach a saved copy</summary>
              <label htmlFor="source-file-url">Public citation URL</label>
              <input id="source-file-url" type="url" value={sourceFileUrl} onChange={(event) => setSourceFileUrl(event.target.value)} placeholder="Use the same URL listed above" />
              <label htmlFor="source-file">Saved PDF or HTML copy</label>
              <input id="source-file" type="file" accept="application/pdf,.pdf,text/html,.html,.htm" onChange={(event) => setSourceFile(event.target.files?.[0] || null)} />
              <small>{sourceFile ? `${sourceFile.name} selected` : "PDF or HTML, up to 25 MB. Its public URL must also be listed above."}</small>
            </details>

            <label className="toggle-row" htmlFor="follow-web">
              <span className="toggle-copy"><strong>Search earlier deals</strong><small>Optional web search; may use more model calls.</small></span>
              <span className="switch"><input id="follow-web" type="checkbox" checked={followWeb} onChange={(event) => setFollowWeb(event.target.checked)} /><span /></span>
            </label>

            {error && <div className="error-message" role="alert"><CircleAlert size={16} /> {error}</div>}
            <button className="analyze-button" type="submit" disabled={loading}>
              {loading ? <LoaderCircle className="spin" size={17} /> : <Search size={17} />}
              {loading ? "Reading sources…" : "Analyze event"}
            </button>
            <p className="cost-note"><Sparkles size={13} /> Model usage capped at $2 per event</p>
          </form>
          {runs.length > 0 && (
            <div className="history">
              <div className="history-head"><History size={14} /> Saved analyses</div>
              <ul>
                {runs.map((run) => (
                  <li key={run.id}>
                    <button type="button" className={`history-item${result?.event === run.event ? " active" : ""}`} onClick={() => openRun(run.id)} disabled={loading || Boolean(openingRun)}>
                      <span className="history-title">{run.event}</span>
                      <span className="history-meta">
                        {openingRun === run.id ? "Opening…" : `${run.people} people · ${run.institutions} institutions`}
                        {run.benchmarked && <span className="history-badge"><Target size={11} /> Benchmarked</span>}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        <section className="results-panel" aria-live="polite" aria-busy={loading}>
          {loading ? (
            <div className="progress-panel">
              <div className="progress-head">
                <LoaderCircle className="spin" size={22} />
                <div><strong>Analyzing {name.trim()}</strong><small>{progress.at(-1)?.message || "Starting the pipeline…"}</small></div>
              </div>
              <ol className="stage-list">
                {STAGES.map((stage, index) => {
                  const state = index < currentStage ? "done" : index === currentStage ? "active" : "pending";
                  return (
                    <li key={stage.id} className={`stage stage-${state}`}>
                      <span className="stage-icon">{state === "done" ? <Check size={13} /> : state === "active" ? <LoaderCircle className="spin" size={13} /> : index + 1}</span>
                      <div><strong>{stage.label}</strong>{stageMessages[stage.id] && <small>{stageMessages[stage.id]}</small>}</div>
                    </li>
                  );
                })}
              </ol>
              <p className="progress-note"><ShieldCheck size={14} /> Every name, number, and date must match a word-for-word quote from the source, or it is dropped.</p>
            </div>
          ) : result ? (
            <>
              <div className="results-heading">
                <div>
                  <button type="button" className="back-button" onClick={closeResult}><ArrowLeft size={15} /> Back</button>
                  <div className="panel-kicker">Analysis results</div><h2>{result.event}</h2>
                </div>
                <div className="results-actions">
                  <button className="export-button" type="button" onClick={() => downloadWorkbook(result)}>
                    <Download size={15} /> Export to Excel
                  </button>
                  <span className={`complete-tag complete-${analysisStatus}`}><span className="status-dot" /> {statusLabels[analysisStatus] || "REVIEW"}</span>
                </div>
              </div>
              {analysisStatus === "failed" && <div className="analysis-warning" role="alert"><CircleAlert size={16} /><span>No source could be analyzed. Check the source links and model API configuration, then review the run notes.</span></div>}
              {analysisStatus === "partial" && <div className="analysis-warning" role="status"><CircleAlert size={16} /><span>Some sources failed. This list may be incomplete; review the run notes before using it.</span></div>}
              {analysisStatus === "no_leads" && <div className="analysis-notice"><ShieldCheck size={16} /><span>Sources were analyzed, but no leads passed the evidence checks.</span></div>}
              <div className="metric-strip">
                <div><span>People to call</span><strong>{people.length}</strong></div>
                <div><span>Top estimate</span><strong className="metric-amount">{amountLabel(topAmount)}</strong></div>
                <div><span>Model cost</span><strong>${result.cost?.cost_usd?.toFixed(4) ?? "0.0000"}</strong></div>
              </div>
              {funnel && (
                <div className="funnel" aria-label="Verification funnel">
                  <div><strong>{funnel.mentions_verified + funnel.mentions_rejected}</strong><span>Mentions extracted</span></div>
                  <ChevronRight size={16} aria-hidden="true" />
                  <div className="funnel-pass"><strong>{funnel.mentions_verified}</strong><span>Passed quote check</span></div>
                  <ChevronRight size={16} aria-hidden="true" />
                  <div><strong>{funnel.entities}</strong><span>Unique names</span></div>
                  <ChevronRight size={16} aria-hidden="true" />
                  <div><strong>{funnel.people}</strong><span>People · {funnel.institutions} institutions</span></div>
                  <p className="funnel-note">{funnel.mentions_rejected} mention{funnel.mentions_rejected === 1 ? "" : "s"} rejected for lacking a word-for-word source quote{funnel.fields_removed ? `; ${funnel.fields_removed} unsupported field${funnel.fields_removed === 1 ? "" : "s"} removed from kept names` : ""}.</p>
                </div>
              )}
              {bench && (
                <section className="benchmark-card" aria-labelledby="benchmark-heading">
                  <div className="benchmark-head">
                    <h3 id="benchmark-heading"><Target size={16} /> Accuracy check</h3>
                    <p>Scored against a hand-checked answer key: {bench.checked_against}</p>
                  </div>
                  <div className="benchmark-stats">
                    <div><span>Sellers found</span><strong>{bench.recall.found}/{bench.recall.expected}</strong><small>{percent(bench.recall.rate)} recall</small></div>
                    <div><span>Claimed sellers correct</span><strong>{bench.precision.correct}/{bench.precision.claimed}</strong><small>{percent(bench.precision.rate)} precision</small></div>
                    <div><span>Put in the right list</span><strong>{bench.routing.correct}/{bench.routing.checked}</strong><small>Person vs institution</small></div>
                    <div><span>Share counts exact</span><strong>{bench.shares.exact}/{bench.shares.checked}</strong><small>Against the filing table</small></div>
                  </div>
                  {benchIssues.length > 0 && <ul className="benchmark-issues">{benchIssues.map((issue) => <li key={issue}><CircleAlert size={13} /> {issue}</li>)}</ul>}
                  {bench.other_leads.length > 0 && <p className="benchmark-note">{bench.other_leads.length} other lead{bench.other_leads.length === 1 ? "" : "s"} (such as ESOP holders) are a different transaction type and are not scored by this key.</p>}
                </section>
              )}
              <div className="table-toolbar">
                <div className="seg-tabs" role="tablist" aria-label="Lead type">
                  <button type="button" role="tab" aria-selected={leadView === "people"} className={leadView === "people" ? "active" : ""} onClick={() => setLeadView("people")}>People <span className="tab-count">{people.length}</span></button>
                  {institutions.length > 0 && <button type="button" role="tab" aria-selected={leadView === "institutions"} className={leadView === "institutions" ? "active" : ""} onClick={() => setLeadView("institutions")}>Institutions <span className="tab-count">{institutions.length}</span></button>}
                </div>
                {leads.length > 0 && <span className="table-hint">Select a row to see the brief, evidence, and review options.</span>}
              </div>
              <div className="table-wrap">
                <table className="leads-table">
                  <colgroup><col className="col-rank" /><col className="col-person" /><col className="col-reason" /><col className="col-amount" /><col className="col-timing" /><col className="col-confidence" /><col className="col-sources" /><col className="col-toggle" /></colgroup>
                  <thead><tr><th>#</th><th>Name</th><th>Transaction</th><th>Est. proceeds</th><th>Timing</th><th>Confidence</th><th>Sources</th><th><span className="sr-only">Details</span></th></tr></thead>
                  <tbody>
                    {leads.map((person, index) => {
                      const key = reviewKey(person);
                      const expanded = Boolean(expandedRows[key]);
                      const confidence = Math.round((person.confidence || 0) * 100);
                      const dims = person.confidence_dimensions || {};
                      const status = reviewStatuses[key];
                      const savedDecision = status === "Saved to review history." ? reviewDecisions[key] : null;
                      return (
                        <Fragment key={`${person.name}-${index}`}>
                          <tr className={`lead-row${expanded ? " is-expanded" : ""}`} onClick={() => toggleRow(key)}>
                            <td><span className="rank-number">{index + 1}</span></td>
                            <td><div className="person-cell"><strong>{person.name}</strong><small>{person.role || "Role not stated in quote"}</small>{savedDecision && <span className={`decision-badge decision-${savedDecision}`}>{decisionLabels[savedDecision]}</span>}</div></td>
                            <td><span className="reason-value">{reasonLabel(person.link)}</span>{person.earlier_events?.length > 0 && <small className="cell-subtext">Earlier deal match</small>}</td>
                            <td><strong className="amount-value">{amountLabel(person.amount)}</strong><small className="cell-subtext">{person.amount?.kind === "none" ? "Source has no number" : "Gross, before tax / fees"}</small></td>
                            <td><span className={`timing-pill timing-${person.timing?.status || "unknown"}`} title={person.timing?.text || undefined}>{person.timing?.status === "now" ? <ArrowDownRight size={13} /> : <ArrowUpRight size={13} />}{person.timing?.status || "unknown"}</span></td>
                            <td><div className="confidence"><span>{confidence}%</span><i><b style={{ width: `${confidence}%` }} /></i></div></td>
                            <td><span className="source-count">{person.evidence?.length || 0}</span></td>
                            <td><button type="button" className="row-toggle" aria-expanded={expanded} aria-label={`${expanded ? "Hide" : "Show"} details for ${person.name}`}><ChevronDown size={16} /></button></td>
                          </tr>
                          {expanded && (
                            <tr className="detail-row">
                              <td colSpan="8">
                                <div className="detail-grid">
                                  <section>
                                    <h4>RM brief</h4>
                                    <p>{person.brief || "No brief available."}</p>
                                    {person.amount?.working && <><h4>Estimate working</h4><p>{person.amount.working}</p></>}
                                    {person.timing?.text && <><h4>Timing</h4><p>{person.timing.text}</p></>}
                                  </section>
                                  <section>
                                    <h4>Confidence breakdown</h4>
                                    <div className="signal-list">
                                      <span>Identity <b>{Math.round((dims.identity?.score ?? person.confidence ?? 0) * 100)}%</b></span>
                                      <span>Transaction <b>{Math.round((dims.transaction?.score ?? 0) * 100)}%</b></span>
                                      <span>Amount <b>{dims.amount?.score == null ? "Not estimable" : `${Math.round(dims.amount.score * 100)}%`}</b></span>
                                      <span>Sources <b>{dims.corroboration?.source_count ?? person.evidence?.length ?? 0}</b></span>
                                    </div>
                                    <small className="signal-note">Heuristic indicators, not calibrated probabilities.</small>
                                    {person.confidence_why?.length > 0 && <ul className="reason-list">{person.confidence_why.map((reason) => <li key={reason}>{reason}</li>)}</ul>}
                                  </section>
                                  {person.score_parts && (
                                    <section>
                                      <h4>Why this rank</h4>
                                      <div className="score-parts">
                                        {SCORE_PARTS.map(([part, label]) => {
                                          const { points, max } = person.score_parts[part];
                                          return <div key={part}><span>{label}</span><i><b style={{ width: `${max ? Math.round((points / max) * 100) : 0}%` }} /></i><em>{points.toFixed(2)} / {max}</em></div>;
                                        })}
                                      </div>
                                      <small className="signal-note">Score {person.score?.toFixed(2)}: 50% proceeds (log scale), 30% identity confidence, 20% timing.</small>
                                    </section>
                                  )}
                                  <section>
                                    <h4>Evidence</h4>
                                    {person.evidence?.length ? person.evidence.map((item, evidenceIndex) => <div className="evidence-item" key={`${item.url}-${evidenceIndex}`}><blockquote>{item.quote}</blockquote><a className="evidence-link" href={evidenceHref(item)} target="_blank" rel="noreferrer">{item.page ? `Open page ${item.page}` : "Open source"}<ExternalLink size={12} /></a></div>) : <p>Not available.</p>}
                                  </section>
                                  <section>
                                    <h4>RM review</h4>
                                    <div className="review-controls">
                                      <select aria-label={`Review decision for ${person.name}`} value={reviewDecisions[key] || ""} onChange={(event) => setReviewDecisions((current) => ({ ...current, [key]: event.target.value }))}><option value="">Choose decision</option><option value="accepted">Accept lead</option><option value="rejected">Reject lead</option><option value="needs_review">Flag for review</option></select>
                                      <input aria-label={`Review note for ${person.name}`} value={reviewNotes[key] || ""} onChange={(event) => setReviewNotes((current) => ({ ...current, [key]: event.target.value }))} placeholder="Optional note" maxLength={1000} />
                                      <button className="review-save-button" type="button" onClick={() => saveReview(person)} disabled={status === "Saving…"}>{status === "Saving…" ? "Saving…" : "Save review"}</button>
                                      {status && <small className="review-status">{status}</small>}
                                    </div>
                                  </section>
                                </div>
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })}
                    {leads.length === 0 && <tr><td className="no-people" colSpan="8">{analysisStatus === "failed" ? "No sources were successfully analyzed. See the run notes." : "Sources were analyzed; no individuals passed the evidence checks."}</td></tr>}
                  </tbody>
                </table>
              </div>
              {result.notes?.length > 0 && <details className="run-notes"><summary>Run notes ({result.notes.length})</summary><ul>{result.notes.map((note, index) => <li key={index}>{note}</li>)}</ul></details>}
            </>
          ) : (
            <div className="empty-state">
              <div className="empty-icon"><Users size={22} /></div>
              <h2>No analysis yet</h2>
              <p>Submit an event and its public sources. Ranked people, proceeds estimates, and evidence will appear here.</p>
              <div className="empty-features">
                <div><Quote size={16} /><strong>Verified quotes</strong><span>Every lead is backed by source text.</span></div>
                <div><ListOrdered size={16} /><strong>Ranked leads</strong><span>Prioritized by proceeds, timing, and confidence.</span></div>
                <div><MessageSquareText size={16} /><strong>Call notes</strong><span>A short brief for each conversation.</span></div>
              </div>
              {runs.length > 0 && (
                <div className="saved-shortcuts">
                  <span>Or open a saved analysis</span>
                  <div>{runs.slice(0, 4).map((run) => <button key={run.id} type="button" onClick={() => openRun(run.id)} disabled={Boolean(openingRun)}>{run.benchmarked && <Target size={12} />}{run.event}</button>)}</div>
                </div>
              )}
            </div>
          )}
        </section>
      </div>
      {logsOpen && <div className="logs-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setLogsOpen(false); }}><section className="logs-modal" role="dialog" aria-modal="true" aria-labelledby="logs-heading">
        <div className="logs-heading"><div><h2 id="logs-heading">Review & logs</h2><p>Review model calls, cached runs, token counts, and per-person cost records.</p></div><button className="logs-close-button" type="button" aria-label="Close review and logs" onClick={() => setLogsOpen(false)}><X size={18} /></button></div>
        <div className="logs-access">
          <label htmlFor="logs-username"><KeyRound size={14} /> Log sign-in</label>
          <div className="logs-token-row"><input id="logs-username" autoComplete="username" value={logsUsername} onChange={(event) => { setLogsUsername(event.target.value); setLogsAuthenticated(false); setLogData(null); }} placeholder="Username" /><input id="logs-password" type="password" autoComplete="current-password" value={logsPassword} onChange={(event) => { setLogsPassword(event.target.value); setLogsAuthenticated(false); setLogData(null); }} placeholder="Password" /><button type="button" className="secondary-button" onClick={() => loadLogs()} disabled={logsLoading}>{logsLoading ? "Signing in…" : logsAuthenticated ? "Refresh logs" : "Sign in"}</button></div>
          <small>Use LOGS_USERNAME and LOGS_PASSWORD configured on the backend. Credentials stay in this browser session only.</small>
        </div>
        <div className="logs-toolbar">
          <div className="log-tabs" role="tablist" aria-label="Log type">
            <button type="button" role="tab" aria-selected={logKind === "runs"} className={logKind === "runs" ? "active" : ""} onClick={() => loadLogs("runs")}>Run history</button>
            <button type="button" role="tab" aria-selected={logKind === "costs"} className={logKind === "costs" ? "active" : ""} onClick={() => loadLogs("costs")}>Model calls</button>
            <button type="button" role="tab" aria-selected={logKind === "reviews"} className={logKind === "reviews" ? "active" : ""} onClick={() => loadLogs("reviews")}>RM reviews</button>
          </div>
          <button type="button" className="secondary-button" onClick={downloadLogCsv} disabled={downloadLoading || !logData?.total}>{downloadLoading ? "Preparing…" : <><FileText size={14} /> Download {logKind === "reviews" ? "rm_reviews.csv" : logKind === "costs" ? "cost_log.csv" : "runs.csv"}</>}</button>
        </div>
        {logsError && <div className="error-message logs-error" role="alert"><CircleAlert size={16} /> {logsError}</div>}
        {logData && <><p className="logs-count">Showing {logData.rows.length} of {logData.total} {logKind === "costs" ? "model calls" : "runs"}. Download CSV for the complete file.</p><div className="table-wrap logs-table-wrap"><table className="logs-table"><thead><tr>{logData.columns.map((column) => <th key={column}>{logLabels[column] || column}</th>)}</tr></thead><tbody>{logData.rows.map((row, rowIndex) => <tr key={`${row.run_id}-${row.time}-${rowIndex}`}>{logData.columns.map((column) => <td key={column}>{row[column] || "—"}</td>)}</tr>)}{logData.rows.length === 0 && <tr><td className="no-people" colSpan={logData.columns.length}>No log entries yet.</td></tr>}</tbody></table></div></>}
      </section></div>}
      <footer className="page-footer"><span>© Affluense Lite</span><span>Estimates are evidence-based and not financial advice.</span></footer>
    </main>
  );
}

export default App;