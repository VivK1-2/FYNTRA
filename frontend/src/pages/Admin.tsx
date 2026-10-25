import { FormEvent, useCallback, useEffect, useState } from "react";
import { adminKey, AdminAsk, AdminFiling, AdminOverview, api, ApiError } from "../api";
import { ErrorNotice, Notice, Skeleton, Spinner } from "../components";
import { date } from "../format";

type Tab = "overview" | "filings" | "questions";
const TABS: [Tab, string][] = [["overview", "Overview"], ["filings", "Reports"], ["questions", "Questions"]];

const bytes = (n?: number | null) => (n == null ? "—" : n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(0)} KB` : `${(n / 1048576).toFixed(1)} MB`);
const uptime = (s: number) => (s < 90 ? `${s}s` : s < 5400 ? `${Math.round(s / 60)} min` : s < 172800 ? `${(s / 3600).toFixed(1)} h` : `${Math.round(s / 86400)} days`);
const when = (s?: string | null) => (s ? new Date(s).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—");

function Login({ onDone }: { onDone: () => void }) {
  const [key, setKey] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    adminKey.set(key.trim());
    setBusy(true); setErr(null);
    try { await api.admin.overview(); onDone(); }
    catch (x) {
      adminKey.clear();
      const a = x as ApiError;
      setErr(a.status === 401 ? "That key is not correct." : a.message);
    }
    setBusy(false);
  };
  return (
    <div className="wrap body" style={{ maxWidth: 460 }}>
      <h1 style={{ fontSize: 34, letterSpacing: "-0.035em" }}>Admin</h1>
      <p style={{ margin: "10px 0 22px" }}>Enter the admin key from the backend <span className="mono">.env</span> (ADMIN_KEY). It is kept only for this browser tab.</p>
      <form onSubmit={submit} className="panel" style={{ padding: 20, marginTop: 0 }}>
        <label htmlFor="ak" style={{ fontWeight: 600, fontSize: 14 }}>Admin key</label>
        <input id="ak" type="password" className="input" style={{ margin: "8px 0 14px" }} value={key} onChange={(e) => setKey(e.target.value)} autoComplete="off" autoFocus />
        {err && <div style={{ marginBottom: 14 }}><Notice kind="err"><div>{err}</div></Notice></div>}
        <button className="btn" disabled={!key.trim() || busy}>{busy ? <><Spinner /> Checking</> : "Sign in"}</button>
      </form>
    </div>
  );
}

function Stat({ k, v, n }: { k: string; v: string | number; n?: string }) {
  return <div className="stat"><div className="k">{k}</div><div className="v">{v}</div>{n && <div className="n">{n}</div>}</div>;
}

function Overview() {
  const [o, setO] = useState<AdminOverview | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const load = useCallback(() => api.admin.overview().then(setO, setErr), []);
  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, [load]);
  if (err) return <ErrorNotice error={err} />;
  if (!o) return <Skeleton h={260} />;
  const ok = o.status === "healthy";
  const clear = async () => { const r = await api.admin.clearCache(); setMsg(`Cleared ${r.market + r.sec_facts + r.xbrl_documents} cached items.`); load(); };
  const f = o.counts.filings_by_status;
  return (
    <>
      <div className="panel" style={{ marginTop: 0 }}>
        <header><h3>System</h3><span className={`badge ${ok ? "good" : "bad"}`}>{ok ? "Backend healthy" : "Backend degraded"}</span></header>
        <div className="stats" style={{ margin: 0, border: 0 }}>
          <Stat k="Database" v={o.database_ok ? "Connected" : "Down"} />
          <Stat k="Uptime" v={uptime(o.uptime_seconds)} n={`Version ${o.version}`} />
          <Stat k="Environment" v={o.environment} />
          <Stat k="Stored files" v={bytes(o.storage_bytes)} />
        </div>
      </div>
      <div className="panel">
        <header><h3>Content</h3></header>
        <div className="stats" style={{ margin: 0, border: 0 }}>
          <Stat k="Companies" v={o.counts.companies} />
          <Stat k="Reports" v={o.counts.filings} n={`${f.processed ?? 0} searchable, ${f.failed ?? 0} failed`} />
          <Stat k="Searchable passages" v={o.counts.passages.toLocaleString()} />
          <Stat k="Questions asked" v={o.counts.questions} n={`${o.counts.questions_24h} in the last 24 h`} />
        </div>
      </div>
      <div className="panel">
        <header><h3>Configuration</h3></header>
        <div className="table-wrap"><table className="table"><tbody>
          <tr><td className="k">Rate limit</td><td>{o.limits.per_minute} requests per minute per client, {o.limits.llm_per_minute} for AI calls</td></tr>
          <tr><td className="k">Caches</td><td>{o.caches.market} prices, {o.caches.sec_facts} SEC filings data, {o.caches.xbrl_documents} XBRL documents <button className="btn ghost sm" style={{ marginLeft: 10 }} onClick={clear}>Clear</button></td></tr>
        </tbody></table></div>
      </div>
      {msg && <p className="muted" style={{ marginTop: 12, fontSize: 14 }}>{msg}</p>}
    </>
  );
}

function statusBadge(s: string, err?: string | null) {
  if (s === "processed") return <span className="badge good">Searchable</span>;
  if (s === "failed") return <span className="badge bad" title={err ?? ""}>Failed</span>;
  if (s === "needs_ocr") return <span className="badge warn">Scanned</span>;
  return <span className="badge brand">{s === "pending" ? "Queued" : "Reading"}</span>;
}

function Filings() {
  const [rows, setRows] = useState<AdminFiling[] | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const load = useCallback(() => api.admin.filings().then(setRows, setErr), []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!rows?.some((r) => r.status === "pending" || r.status === "processing")) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [rows, load]);
  const act = async (id: number, fn: () => Promise<unknown>) => {
    setBusy(id);
    try { await fn(); await load(); } catch (e) { setErr(e as ApiError); }
    setBusy(null);
  };
  if (err) return <ErrorNotice error={err} />;
  if (!rows) return <Skeleton h={220} />;
  if (!rows.length) return <p className="muted">No reports have been downloaded yet.</p>;
  return (
    <div className="panel" style={{ marginTop: 0 }}><div className="table-wrap"><table className="table">
      <thead><tr><th>Company</th><th>Report</th><th>Status</th><th className="r">Passages</th><th className="r">File</th><th className="r">Actions</th></tr></thead>
      <tbody>{rows.map((r) => (
        <tr key={r.id}>
          <td className="k">{r.ticker ?? "—"}<div style={{ color: "var(--muted)", fontWeight: 400 }}>{r.company}</div></td>
          <td>{r.form}<div className="mono" style={{ color: "var(--muted)" }}>{date(r.filing_date)}</div></td>
          <td>{statusBadge(r.status, r.error)}{r.error && <div style={{ color: "var(--bad)", fontSize: 12.5, maxWidth: 240 }}>{r.error.slice(0, 80)}</div>}</td>
          <td className="r num">{r.passages.toLocaleString()}</td>
          <td className="r num">{bytes(r.file_bytes)}</td>
          <td className="r" style={{ whiteSpace: "nowrap" }}>
            <button className="btn ghost sm" disabled={busy === r.id} onClick={() => act(r.id, () => api.admin.reingest(r.id, false))}>Re-read</button>{" "}
            <button className="btn ghost sm" disabled={busy === r.id} onClick={() => act(r.id, () => api.admin.reingest(r.id, true))}>Re-download</button>{" "}
            <button className="btn ghost sm danger" disabled={busy === r.id} onClick={() => { if (window.confirm(`Delete this ${r.form} for ${r.ticker}? The downloaded file and its searchable text will be removed.`)) act(r.id, () => api.admin.remove(r.id)); }}>Delete</button>
          </td>
        </tr>
      ))}</tbody>
    </table></div></div>
  );
}

function Questions() {
  const [rows, setRows] = useState<AdminAsk[] | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  useEffect(() => { api.admin.asks().then(setRows, setErr); }, []);
  if (err) return <ErrorNotice error={err} />;
  if (!rows) return <Skeleton h={220} />;
  if (!rows.length) return <p className="muted">Nobody has asked a question yet.</p>;
  const badge = (s: string) => s === "answered" ? <span className="badge good">Answered</span> : s === "error" ? <span className="badge bad">Error</span> : <span className="badge warn">Not enough evidence</span>;
  return (
    <div className="panel" style={{ marginTop: 0 }}><div className="table-wrap"><table className="table">
      <thead><tr><th>When</th><th>Company</th><th>Question</th><th>Result</th><th className="r">Sources</th><th className="r">Time</th></tr></thead>
      <tbody>{rows.map((r) => (
        <tr key={r.id}>
          <td className="num" style={{ whiteSpace: "nowrap" }}>{when(r.created_at)}</td>
          <td className="k">{r.ticker ?? "—"}</td>
          <td style={{ maxWidth: 380 }}>{r.question}</td>
          <td>{badge(r.status)}{r.dropped_sentences > 0 && <div style={{ color: "var(--muted)", fontSize: 12.5 }}>{r.dropped_sentences} unsupported removed</div>}</td>
          <td className="r num">{r.citations}</td>
          <td className="r num">{r.latency_ms != null ? `${(r.latency_ms / 1000).toFixed(1)} s` : "—"}</td>
        </tr>
      ))}</tbody>
    </table></div></div>
  );
}

export default function Admin() {
  const [authed, setAuthed] = useState(!!adminKey.get());
  const [tab, setTab] = useState<Tab>("overview");
  if (!authed) return <Login onDone={() => setAuthed(true)} />;
  return (
    <div className="wrap body">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 34, letterSpacing: "-0.035em" }}>Admin</h1>
        <button className="btn ghost sm" onClick={() => { adminKey.clear(); setAuthed(false); }}>Sign out</button>
      </div>
      <div className="tabs" role="tablist" style={{ marginBottom: 22 }}>
        {TABS.map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} className="tab" onClick={() => setTab(k)}>{l}</button>)}
      </div>
      <AuthGuard onLost={() => setAuthed(false)}>
        {tab === "overview" && <Overview />}
        {tab === "filings" && <Filings />}
        {tab === "questions" && <Questions />}
      </AuthGuard>
    </div>
  );
}

// If the key stops working (backend restarted with a new ADMIN_KEY), return to the sign-in screen.
function AuthGuard({ children, onLost }: { children: React.ReactNode; onLost: () => void }) {
  useEffect(() => {
    const t = setInterval(() => { api.admin.overview().catch((e: ApiError) => { if (e.status === 401) { adminKey.clear(); onLost(); } }); }, 60000);
    return () => clearInterval(t);
  }, [onLost]);
  return <>{children}</>;
}
