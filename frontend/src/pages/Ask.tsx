import { FormEvent, ReactNode, useState } from "react";
import { api, ApiError, AskResult, CompareAskResult, Citation } from "../api";
import { ErrorNotice, Notice, Spinner } from "../components";
import { date } from "../format";
import { useAsync } from "../hooks";

const SUGGESTIONS = [
  "What are the main supply chain risks?",
  "How does the company describe competition?",
  "What does management say about share repurchases?",
  "What legal proceedings are disclosed?",
];

interface Turn { q: string; result?: AskResult; compare?: CompareAskResult; error?: ApiError; pending: boolean }

export default function Ask({ id }: { id: string }) {
  const [q, setQ] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const busy = turns.some((t) => t.pending);
  const [acc, setAcc] = useState("");
  const [cmp, setCmp] = useState(false);
  const [others, setOthers] = useState("");
  const reports = useAsync(async () => {
    const [list, status] = await Promise.all([api.filings(id, 8), api.ingestStatuses(id)]);
    return list.filter((f) => status[f.accession_number]?.status === "processed");
  }, [id]);
  const peers = others.split(/[\s,]+/).map((t) => t.trim().toUpperCase()).filter(Boolean).slice(0, 2);

  const submit = async (question: string) => {
    const text = question.trim();
    if (text.length < 3 || busy) return;
    setQ("");
    setTurns((p) => [{ q: text, pending: true }, ...p]);
    try {
      if (cmp) {
        const compare = await api.askCompare([id.toUpperCase(), ...peers], text);
        setTurns((p) => p.map((t, i) => (i === 0 ? { ...t, compare, pending: false } : t)));
      } else {
        const result = await api.ask(id, text, acc);
        setTurns((p) => p.map((t, i) => (i === 0 ? { ...t, result, pending: false } : t)));
      }
    } catch (e) {
      setTurns((p) => p.map((t, i) => (i === 0 ? { ...t, error: e as ApiError, pending: false } : t)));
    }
  };
  const onSubmit = (e: FormEvent) => { e.preventDefault(); submit(q); };

  return (
    <>
      <div className="sec-head"><h2>Ask a question</h2></div>
      <p style={{ margin: "0 0 16px", maxWidth: "42em" }}>
        Answers come only from the reports you've made searchable. Each sentence links to the passage it relies on, and
        any sentence that can't be backed by a passage is removed.
      </p>
      <div className="toolbar" style={{ marginBottom: 12 }}>
        {!cmp && reports.data && reports.data.length > 0 && (
          <select className="input sm" value={acc} onChange={(e) => setAcc(e.target.value)} aria-label="Report to ask about">
            <option value="">All searchable reports</option>
            {reports.data.map((f) => <option key={f.accession_number} value={f.accession_number}>{f.fiscal_label ?? `${f.form} filed ${date(f.filing_date)}`}</option>)}
          </select>
        )}
        <label className="check"><input type="checkbox" checked={cmp} onChange={(e) => setCmp(e.target.checked)} /> Compare with other companies</label>
        {cmp && <input className="input sm" value={others} onChange={(e) => setOthers(e.target.value)} placeholder="e.g. MSFT, TSLA" aria-label="Other tickers" style={{ width: 160 }} />}
      </div>
      {cmp && <p className="muted" style={{ fontSize: 14, margin: "0 0 12px" }}>The same question is answered separately from each company's own reports. Each company needs a searchable report.</p>}
      <form onSubmit={onSubmit} style={{ display: "flex", gap: 10, maxWidth: 720 }}>
        <input className="input" value={q} onChange={(e) => setQ(e.target.value)} maxLength={500}
          placeholder="Ask about this company's annual report" aria-label="Your question" />
        <button className="btn" type="submit" disabled={busy || q.trim().length < 3 || (cmp && peers.length < 1)}>{busy ? <Spinner /> : "Ask"}</button>
      </form>
      {turns.length === 0 && (
        <div className="hero-links" style={{ marginTop: 14, maxWidth: 720 }}>
          <span>Try</span>
          {SUGGESTIONS.map((s) => <button key={s} onClick={() => submit(s)}>{s}</button>)}
        </div>
      )}
      <div style={{ marginTop: 28, display: "grid", gap: 24 }}>
        {turns.map((t, i) => <TurnView key={turns.length - i} turn={t} />)}
      </div>
    </>
  );
}

function TurnView({ turn }: { turn: Turn }) {
  return (
    <section aria-live="polite">
      <div style={{ color: "var(--navy)", fontWeight: 600, fontSize: 17, marginBottom: 10 }}>{turn.q}</div>
      {turn.pending && <div className="panel" style={{ marginTop: 0, padding: 22, display: "flex", gap: 12, alignItems: "center" }}><Spinner dark /> Reading the reports…</div>}
      {turn.error && <ErrorNotice error={turn.error} />}
      {turn.result && <ResultView r={turn.result} />}
      {turn.compare && (
        <div className="cmp-grid">
          {turn.compare.companies.map((c) => (
            <div key={c.ticker}>
              <h3 style={{ fontSize: 15, margin: "0 0 8px", letterSpacing: "-0.01em" }}>{c.ticker}{c.name ? <span style={{ color: "var(--muted)", fontWeight: 400 }}> · {c.name}</span> : null}</h3>
              {c.error && <Notice kind="err"><div>{c.error}</div></Notice>}
              {c.result && <ResultView r={c.result} />}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function ResultView({ r }: { r: AskResult }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <>
      {r.status === "insufficient_evidence" && <Refusal result={r} />}
      {r.status === "answered" && (
        <div className="panel" style={{ marginTop: 0 }}>
          <div style={{ padding: "20px 22px", fontSize: 16.5, lineHeight: 1.65, color: "var(--navy)", maxWidth: "46em" }}>
            {renderAnswer(r.answer ?? "", r.citations, (n) => setOpen(open === n ? null : n))}
          </div>
          <div style={{ borderTop: "1px solid var(--line)", background: "var(--wash)", padding: "14px 22px", display: "grid", gap: 10 }}>
            <div style={{ fontSize: 14, color: "var(--muted)" }}>
              {r.citations.length} {r.citations.length === 1 ? "source" : "sources"}
              {r.dropped_sentences > 0 && <> · {r.dropped_sentences} unsupported {r.dropped_sentences === 1 ? "sentence" : "sentences"} removed</>}
            </div>
            {r.citations.map((c) => <Source key={c.n} c={c} open={open === c.n} toggle={() => setOpen(open === c.n ? null : c.n)} />)}
          </div>
          {r.latency_ms ? <div style={{ padding: "10px 22px", fontSize: 13, color: "var(--muted)" }}>Answered in {(r.latency_ms / 1000).toFixed(1)} s</div> : null}
        </div>
      )}
    </>
  );
}

function renderAnswer(text: string, cites: Citation[], pick: (n: number) => void): ReactNode[] {
  const valid = new Set(cites.map((c) => c.n));
  return text.split(/(\[\d+\])/g).map((part, i) => {
    const m = part.match(/^\[(\d+)\]$/);
    if (!m) return part;
    const n = +m[1];
    return valid.has(n)
      ? <button key={i} className="cite" onClick={() => pick(n)} aria-label={`Show source ${n}`}>{n}</button>
      : null;
  });
}

function Source({ c, open, toggle }: { c: Citation; open: boolean; toggle: () => void }) {
  const pages = c.page_start != null ? `Page ${c.page_start}${c.page_end && c.page_end !== c.page_start ? `–${c.page_end}` : ""}` : null;
  return (
    <div className={`source${open ? " open" : ""}`}>
      <button className="source-head" onClick={toggle} aria-expanded={open}>
        <span className="cite static">{c.n}</span>
        <span style={{ flex: 1, textAlign: "left" }}>
          <strong style={{ color: "var(--navy)" }}>{c.form} · {date(c.filing_date)}</strong>
          <span style={{ color: "var(--muted)" }}>{c.section ? ` · ${c.section.length > 50 ? c.section.slice(0, 50) + "…" : c.section}` : ""}{pages ? ` · ${pages}` : ""}</span>
        </span>
        <span aria-hidden style={{ color: "var(--muted)" }}>{open ? "Hide" : "Show"}</span>
      </button>
      {open && (
        <div className="source-body">
          <p>{markQuote(c.passage, c.quote)}</p>
          {c.document_url && <a href={c.document_url} target="_blank" rel="noreferrer noopener">Open the full report on SEC</a>}
        </div>
      )}
    </div>
  );
}

function markQuote(passage: string, quote: string): ReactNode {
  // match ignoring whitespace differences so the highlighted quote lines up with the passage
  const esc = quote.trim().replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s+");
  const m = new RegExp(esc, "i").exec(passage);
  if (!m) return passage;
  return <>{passage.slice(0, m.index)}<mark>{m[0]}</mark>{passage.slice(m.index + m[0].length)}</>;
}

function Refusal({ result }: { result: AskResult }) {
  const msg =
    result.reason === "no_matching_passages"
      ? "No passages matched this question. Make sure a report is searchable on the Annual reports tab, or try different words."
      : result.reason === "unverified"
      ? "The model's answer couldn't be backed by the report text, so it was withheld. Try rephrasing the question."
      : "The report passages found don't contain an answer to this question.";
  return <Notice kind="info"><div><strong>No answer from the reports</strong><div>{msg}</div></div></Notice>;
}
