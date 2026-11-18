import { useState } from "react";
import * as XLSX from "xlsx";
import { ArrowDownRight, ArrowUpRight, CircleAlert, Download, ExternalLink, FileSpreadsheet, FileText, KeyRound, LoaderCircle, Search, ShieldCheck, Sparkles } from "lucide-react";

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
  appendSheet("Leads", leads, [8, 14, 30, 30, 24, 20, 20, 24, 72, 15, 72, 16, 16, 72, 48]);
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
  const [logsToken, setLogsToken] = useState("");
  const [logKind, setLogKind] = useState("runs");
  const [logData, setLogData] = useState(null);
  const [logsError, setLogsError] = useState("");
  const [logsLoading, setLogsLoading] = useState(false);
  const [downloadLoading, setDownloadLoading] = useState(false);

  async function analyze(event) {
    event.preventDefault();
    setError("");
    setResult(null);
    const urls = sourceText.split(/\r?\n/).map((url) => url.trim()).filter(Boolean);
    if (!name.trim() || urls.length === 0) {
      setError("Add an event name and at least one source link.");
      return;
    }
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/events/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), urls, follow_web: followWeb }),
      });
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
    setLogKind(kind);
    setLogsError("");
    setLogsLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/logs/${kind}`, {
        headers: { "X-Logs-Token": logsToken },
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "Could not load the log.");
      setLogData(body);
    } catch (reason) {
      setLogData(null);
      setLogsError(reason.message === "Failed to fetch"
        ? "Can't reach the analysis API. Check its URL and that the backend is awake."
        : reason.message);
    } finally {
      setLogsLoading(false);
    }
  }

  async function downloadLogCsv() {
    setLogsError("");
    setDownloadLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/logs/csv/${logKind}`, {
        headers: { "X-Logs-Token": logsToken },
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
    : { run_id: "Run ID", time: "Time", event: "Event", model: "Model", llm_calls: "Calls", cached_calls: "Cached", cost_usd: "Cost (USD)", wall_seconds: "Wall seconds", people: "People", cost_per_person_usd: "Cost / person" };

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="wordmark" href="#top" aria-label="Affluense home">
          <span className="mark"><span /></span>
          <span>affluense<span className="wordmark-lite"> / lite</span></span>
        </a>
        <div className="topbar-status"><span className="status-dot" /> PRIVATE BETA <span className="topbar-divider" /> INDIA</div>
        <a className="docs-link" href="https://github.com" target="_blank" rel="noreferrer">Project <ExternalLink size={14} /></a>
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
              <div className="table-wrap">
                <table>
                  <thead><tr><th>RANK / PERSON</th><th>WHY THEY GOT MONEY</th><th>EST. PROCEEDS</th><th>TIMING</th><th>CONFIDENCE</th><th>EVIDENCE</th></tr></thead>
                  <tbody>
                    {people.map((person, index) => (
                      <tr key={`${person.name}-${index}`}>
                        <td><div className="person-cell"><span className="rank-number">{String(index + 1).padStart(2, "0")}</span><div><strong>{person.name}</strong><small>{person.role || "Role not stated in quote"}</small><details className="row-detail"><summary>RM brief</summary><p>{person.brief || "No brief available."}</p></details></div></div></td>
                        <td><strong className="reason-value">{reasonLabel(person.link)}</strong>{person.earlier_events?.length > 0 && <small className="cell-subtext">Earlier deal match available</small>}</td>
                        <td><strong className="amount-value">{amountLabel(person.amount)}</strong><small className="cell-subtext">{person.amount?.kind === "none" ? "Source has no number" : "Gross estimate, before tax / fees"}</small>{person.amount?.working && <details className="row-detail"><summary>Estimate working</summary><p>{person.amount.working}</p></details>}</td>
                        <td><span className={`timing-pill timing-${person.timing?.status || "unknown"}`}>{person.timing?.status === "now" ? <ArrowDownRight size={13} /> : <ArrowUpRight size={13} />}{person.timing?.status || "unknown"}</span><small className="cell-subtext timing-text">{person.timing?.text}</small></td>
                        <td><div className="confidence"><span>{Math.round((person.confidence || 0) * 100)}%</span><i><b style={{ width: `${Math.round((person.confidence || 0) * 100)}%` }} /></i></div><small className="cell-subtext">Person match</small></td>
                        <td>{person.evidence?.length ? <details className="evidence-details"><summary>{person.evidence.length} source{person.evidence.length === 1 ? "" : "s"}</summary>{person.evidence.map((item, evidenceIndex) => <div className="evidence-item" key={`${item.url}-${evidenceIndex}`}><a className="evidence-link" href={item.url} target="_blank" rel="noreferrer">Open source{item.page ? ` · p. ${item.page}` : ""}<ExternalLink size={12} /></a><blockquote>{item.quote}</blockquote></div>)}</details> : <span className="cell-subtext">Not available</span>}</td>
                      </tr>
                    ))}
                    {people.length === 0 && <tr><td className="no-people" colSpan="6">{analysisStatus === "failed" ? "No sources were successfully analyzed. See the run notes." : "Sources were analyzed; no individuals passed the evidence checks."}</td></tr>}
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
      <section className="logs-section" aria-labelledby="logs-heading">
        <div className="logs-heading"><div><div className="panel-kicker">03 <span> / </span> OPERATIONS</div><h2 id="logs-heading">Run and cost logs</h2></div><p>Review model calls, cached runs, token counts, and per-person cost records.</p></div>
        <div className="logs-access">
          <label htmlFor="logs-token"><KeyRound size={14} /> Log access token</label>
          <div className="logs-token-row"><input id="logs-token" type="password" autoComplete="off" value={logsToken} onChange={(event) => setLogsToken(event.target.value)} placeholder="Enter LOGS_ACCESS_TOKEN" /><button type="button" className="secondary-button" onClick={() => loadLogs()} disabled={logsLoading}>{logsLoading ? "Loading…" : "Load logs"}</button></div>
          <small>Set LOGS_ACCESS_TOKEN in the backend environment. The token stays in this browser session only.</small>
        </div>
        <div className="logs-toolbar">
          <div className="log-tabs" role="tablist" aria-label="Log type">
            <button type="button" role="tab" aria-selected={logKind === "runs"} className={logKind === "runs" ? "active" : ""} onClick={() => loadLogs("runs")}>Run history</button>
            <button type="button" role="tab" aria-selected={logKind === "costs"} className={logKind === "costs" ? "active" : ""} onClick={() => loadLogs("costs")}>Model calls</button>
          </div>
          <button type="button" className="secondary-button" onClick={downloadLogCsv} disabled={downloadLoading || !logData?.total}>{downloadLoading ? "Preparing…" : <><FileText size={14} /> Download {logKind === "costs" ? "cost_log.csv" : "runs.csv"}</>}</button>
        </div>
        {logsError && <div className="error-message logs-error" role="alert"><CircleAlert size={16} /> {logsError}</div>}
        {logData && <><p className="logs-count">Showing {logData.rows.length} of {logData.total} {logKind === "costs" ? "model calls" : "runs"}. Download CSV for the complete file.</p><div className="table-wrap logs-table-wrap"><table className="logs-table"><thead><tr>{logData.columns.map((column) => <th key={column}>{logLabels[column] || column}</th>)}</tr></thead><tbody>{logData.rows.map((row, rowIndex) => <tr key={`${row.run_id}-${row.time}-${rowIndex}`}>{logData.columns.map((column) => <td key={column}>{row[column] || "—"}</td>)}</tr>)}{logData.rows.length === 0 && <tr><td className="no-people" colSpan={logData.columns.length}>No log entries yet.</td></tr>}</tbody></table></div></>}
      </section>
      <footer className="page-footer"><span>© AFFLUENSE LITE</span><span>ESTIMATES ARE EVIDENCE-BASED, NOT FINANCIAL ADVICE</span><span>BUILT FOR BETTER CALLS <ArrowUpRight size={13} /></span></footer>
    </main>
  );
}

export default App;