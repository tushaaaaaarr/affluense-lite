import { useState } from "react";
import * as XLSX from "xlsx";
import { ArrowDownRight, ArrowUpRight, Check, CircleAlert, ClipboardCheck, Download, ExternalLink, FileSpreadsheet, FileText, FileUp, Flag, KeyRound, LoaderCircle, Search, ShieldCheck, Sparkles, ThumbsDown, X } from "lucide-react";

const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

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

  async function analyze(event) {
    event.preventDefault();
    setError("");
    setResult(null);
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
        response = await fetch(`${API_URL}/api/events/analyze-upload`, { method: "POST", body: formData });
      } else {
        response = await fetch(`${API_URL}/api/events/analyze`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: name.trim(), urls, follow_web: followWeb }),
        });
      }
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "The analysis could not be completed.");
      setResult(body);
    } catch (reason) {
      setError(reason.message === "Failed to fetch"
        ? "Can't reach the analysis API. Check its URL and that the backend is awake."
        : reason.message);
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
  const topAmount = people[0]?.amount;
  const analysisStatus = result?.analysis_status || "complete";
  const statusLabels = {
    complete: "VERIFIED",
    partial: "PARTIAL",
    no_leads: "NO LEADS",
    failed: "NEEDS ATTENTION",
  };
  const logLabels = logKind === "costs"
    ? { run_id: "Run ID", time: "Time", event: "Event", stage: "Stage", person: "Person", model: "Model", in_tokens: "Input tokens", out_tokens: "Output tokens", cost_usd: "Cost (USD)", seconds: "Seconds", cached: "Cached" }
    : logKind === "reviews"
      ? { run_id: "Run ID", event: "Event", person: "Person", decision: "Decision", note: "Note", updated_at: "Reviewed at" }
      : { run_id: "Run ID", time: "Time", event: "Event", model: "Model", llm_calls: "Calls", cached_calls: "Cached", cost_usd: "Cost (USD)", wall_seconds: "Wall seconds", people: "People", cost_per_person_usd: "Cost / person" };

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="wordmark" href="#top" aria-label="Affluense home">
          <span className="mark"><span /></span>
          <span>affluense<span className="wordmark-lite"> / lite</span></span>
        </a>
        <div className="topbar-status"><span className="status-dot" /> PRIVATE BETA <span className="topbar-divider" /> INDIA</div>
        <div className="topbar-actions"><button className="logs-open-button" type="button" onClick={() => setLogsOpen(true)} aria-expanded={logsOpen}><ClipboardCheck size={14} /> Review & logs</button><a className="docs-link" href="https://github.com/tushaaaaaarr/affluense-lite" target="_blank" rel="noreferrer">Project <ExternalLink size={14} /></a></div>
      </header>

      <section className="intro" id="top">
        <div>
          <div className="eyebrow"><span className="eyebrow-line" /> EVENT INTELLIGENCE <span className="eyebrow-index">01 / 03</span></div>
          <h1>Find the people<br /><em>behind the event.</em></h1>
          <p className="intro-copy">Turn public filings and news into a verified, prioritized call list for your next conversation.</p>
        </div>
        <div className="intro-stamp" aria-hidden="true"><span>PUBLIC</span><strong>↗</strong><span>RECORDS</span></div>
      </section>

      <div className="workspace">
        <section className="input-panel" aria-labelledby="form-heading">
          <div className="panel-heading">
            <div className="panel-kicker">01 <span> / </span> NEW ANALYSIS</div>
            <h2 id="form-heading">Set the event</h2>
          </div>
          <form onSubmit={analyze}>
            <label htmlFor="event-name">Event name</label>
            <input id="event-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Acme Ltd IPO" maxLength={160} />

            <label htmlFor="source-links">Source links <span className="label-note">UP TO 8</span></label>
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
              {!loading && <ArrowUpRight size={17} className="button-arrow" />}
            </button>
            <p className="cost-note"><Sparkles size={13} /> Model usage capped at $2 per event</p>
          </form>
        </section>

        <section className="results-panel" aria-live="polite" aria-busy={loading}>
          {loading ? (
            <div className="empty-state loading-state"><div className="loader-orbit"><span /><span /><span /></div><p>Reading public sources</p><small>Verifying names, amounts, and evidence quotes</small></div>
          ) : result ? (
            <>
              <div className="results-heading">
                <div><div className="panel-kicker">02 <span> / </span> ANALYSIS COMPLETE</div><h2>{result.event}</h2></div>
                <div className="results-actions">
                  <button className="export-button" type="button" onClick={() => downloadWorkbook(result)}>
                    <FileSpreadsheet size={16} /><span>Export Excel</span><Download size={14} />
                  </button>
                  <span className={`complete-tag complete-${analysisStatus}`}><span className="status-dot" /> {statusLabels[analysisStatus] || "REVIEW"}</span>
                </div>
              </div>
              {analysisStatus === "failed" && <div className="analysis-warning" role="alert"><CircleAlert size={16} /><span>No source could be analyzed. Check the source links and model API configuration, then review the run notes.</span></div>}
              {analysisStatus === "partial" && <div className="analysis-warning" role="status"><CircleAlert size={16} /><span>Some sources failed. This list may be incomplete; review the run notes before using it.</span></div>}
              {analysisStatus === "no_leads" && <div className="analysis-notice"><ShieldCheck size={16} /><span>Sources were analyzed, but no leads passed the evidence checks.</span></div>}
              <div className="metric-strip">
                <div><span>PEOPLE TO CALL</span><strong>{people.length.toString().padStart(2, "0")}</strong></div>
                <div><span>TOP ESTIMATE</span><strong className="metric-amount">{amountLabel(topAmount)}</strong></div>
                <div><span>MODEL COST</span><strong>${result.cost?.cost_usd?.toFixed(4) ?? "0.0000"}</strong></div>
              </div>
              <div className="table-caption"><strong>{people.length} ranked {people.length === 1 ? "lead" : "leads"}</strong><span>{people.length > 0 ? "Scroll inside the table to browse the full list" : "No individual leads passed verification"}</span></div>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>RANK / PERSON</th><th>WHY THEY GOT MONEY</th><th>EST. PROCEEDS</th><th>TIMING</th><th>CONFIDENCE SIGNALS</th><th>EVIDENCE</th><th>RM REVIEW</th></tr></thead>
                  <tbody>
                    {people.map((person, index) => (
                      <tr key={`${person.name}-${index}`}>
                        <td><div className="person-cell"><span className="rank-number">{String(index + 1).padStart(2, "0")}</span><div><strong>{person.name}</strong><small>{person.role || "Role not stated in quote"}</small><details className="row-detail"><summary>RM brief</summary><p>{person.brief || "No brief available."}</p></details></div></div></td>
                        <td><strong className="reason-value">{reasonLabel(person.link)}</strong>{person.earlier_events?.length > 0 && <small className="cell-subtext">Earlier deal match available</small>}</td>
                        <td><strong className="amount-value">{amountLabel(person.amount)}</strong><small className="cell-subtext">{person.amount?.kind === "none" ? "Source has no number" : "Gross estimate, before tax / fees"}</small>{person.amount?.working && <details className="row-detail"><summary>Estimate working</summary><p>{person.amount.working}</p></details>}</td>
                        <td><span className={`timing-pill timing-${person.timing?.status || "unknown"}`}>{person.timing?.status === "now" ? <ArrowDownRight size={13} /> : <ArrowUpRight size={13} />}{person.timing?.status || "unknown"}</span><small className="cell-subtext timing-text">{person.timing?.text}</small></td>
                        <td><div className="confidence"><span>{Math.round((person.confidence || 0) * 100)}%</span><i><b style={{ width: `${Math.round((person.confidence || 0) * 100)}%` }} /></i></div><small className="cell-subtext">Identity match</small><details className="row-detail"><summary>Confidence breakdown</summary><div className="signal-list"><span>Identity <b>{Math.round((person.confidence_dimensions?.identity?.score ?? person.confidence ?? 0) * 100)}%</b></span><span>Transaction <b>{Math.round((person.confidence_dimensions?.transaction?.score ?? 0) * 100)}%</b></span><span>Amount <b>{person.confidence_dimensions?.amount?.score == null ? "Not estimable" : `${Math.round(person.confidence_dimensions.amount.score * 100)}%`}</b></span><span>Sources <b>{person.confidence_dimensions?.corroboration?.source_count ?? person.evidence?.length ?? 0}</b></span></div><small className="signal-note">Heuristic indicators, not calibrated probabilities.</small></details></td>
                        <td>{person.evidence?.length ? <details className="evidence-details"><summary>{person.evidence.length} source{person.evidence.length === 1 ? "" : "s"}</summary>{person.evidence.map((item, evidenceIndex) => <div className="evidence-item" key={`${item.url}-${evidenceIndex}`}><a className="evidence-link" href={item.url} target="_blank" rel="noreferrer">Open source{item.page ? ` · p. ${item.page}` : ""}<ExternalLink size={12} /></a><blockquote>{item.quote}</blockquote></div>)}</details> : <span className="cell-subtext">Not available</span>}</td>
                        <td><div className="review-controls"><select aria-label={`Review decision for ${person.name}`} value={reviewDecisions[reviewKey(person)] || ""} onChange={(event) => setReviewDecisions((current) => ({ ...current, [reviewKey(person)]: event.target.value }))}><option value="">Choose decision</option><option value="accepted">Accept lead</option><option value="rejected">Reject lead</option><option value="needs_review">Flag for review</option></select><input aria-label={`Review note for ${person.name}`} value={reviewNotes[reviewKey(person)] || ""} onChange={(event) => setReviewNotes((current) => ({ ...current, [reviewKey(person)]: event.target.value }))} placeholder="Optional note" maxLength={1000} /><button className="review-save-button" type="button" onClick={() => saveReview(person)} disabled={reviewStatuses[reviewKey(person)] === "Saving…"}>{reviewStatuses[reviewKey(person)] === "Saving…" ? "Saving…" : "Save review"}</button>{reviewStatuses[reviewKey(person)] && <small className="review-status">{reviewStatuses[reviewKey(person)]}</small>}</div></td>
                      </tr>
                    ))}
                    {people.length === 0 && <tr><td className="no-people" colSpan="7">{analysisStatus === "failed" ? "No sources were successfully analyzed. See the run notes." : "Sources were analyzed; no individuals passed the evidence checks."}</td></tr>}
                  </tbody>
                </table>
              </div>
              {result.institutions?.length > 0 && <p className="institution-note">{result.institutions.length} institutional seller{result.institutions.length === 1 ? "" : "s"} listed separately.</p>}
              {result.notes?.length > 0 && <details className="run-notes"><summary>Run notes ({result.notes.length})</summary><ul>{result.notes.map((note, index) => <li key={index}>{note}</li>)}</ul></details>}
            </>
          ) : (
            <div className="empty-state">
              <div className="empty-glyph"><span /><span /><span /></div>
              <div className="panel-kicker">02 <span> / </span> YOUR RESULTS</div>
              <h2>The next useful<br />conversation starts here.</h2>
              <p>Submit an event and its public sources. Ranked people, proceeds estimates, and evidence will appear in this workspace.</p>
              <div className="empty-foot"><span>01 — VERIFIED QUOTES</span><span>02 — RANKED LEADS</span><span>03 — CALL NOTES</span></div>
            </div>
          )}
        </section>
      </div>
      {logsOpen && <div className="logs-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setLogsOpen(false); }}><section className="logs-section logs-modal" role="dialog" aria-modal="true" aria-labelledby="logs-heading">
        <div className="logs-modal-bar"><span>OPERATIONS & REVIEW</span><button className="logs-close-button" type="button" aria-label="Close review and logs" onClick={() => setLogsOpen(false)}><X size={17} /></button></div>
        <div className="logs-heading"><div><div className="panel-kicker">03 <span> / </span> OPERATIONS</div><h2 id="logs-heading">Run and cost logs</h2></div><p>Review model calls, cached runs, token counts, and per-person cost records.</p></div>
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
      <footer className="page-footer"><span>© AFFLUENSE LITE</span><span>ESTIMATES ARE EVIDENCE-BASED, NOT FINANCIAL ADVICE</span><span>BUILT FOR BETTER CALLS <ArrowUpRight size={13} /></span></footer>
    </main>
  );
}

export default App;