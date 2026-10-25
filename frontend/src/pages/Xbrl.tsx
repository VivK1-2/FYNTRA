import { useEffect, useState } from "react";
import { api, ApiError, XbrlFact, XbrlResult } from "../api";
import { Empty, ErrorNotice, Skeleton, Spinner } from "../components";
import { csvDownload, date } from "../format";
import { useAsync } from "../hooks";

const PAGE = 200;

function fmtValue(f: XbrlFact): string {
  const v = f.value;
  if (f.unit === "INR") {
    return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", notation: Math.abs(v) >= 1e5 ? "compact" : "standard", maximumFractionDigits: 2 }).format(v);
  }
  const usd = f.unit.startsWith("USD") && !f.unit.includes("/");
  if (usd && Math.abs(v) >= 1e6) {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 2 }).format(v);
  }
  if (usd) return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(v);
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 }).format(v);
}

const period = (f: XbrlFact) =>
  f.period_type === "instant" ? `As of ${date(f.end)}` : f.start && f.end ? `${date(f.start)} to ${date(f.end)}` : date(f.end);

export default function Xbrl({ id, india = false }: { id: string; india?: boolean }) {
  // One list shape for both markets: key is what the API needs to find the file, label is what the person sees.
  const filings = useAsync(async (): Promise<{ key: string; label: string }[]> => {
    if (india) {
      const r = await api.indiaXbrlFilings(id);
      return r.filings.map((f) => ({
        key: f.url,
        label: [f.period, f.period_end && `ended ${f.period_end}`, f.consolidated, f.audited].filter(Boolean).join(" · "),
      }));
    }
    const [list, status] = await Promise.all([api.filings(id, 8), api.ingestStatuses(id)]);
    return list.filter((f) => status[f.accession_number]).map((f) => ({ key: f.accession_number, label: `${f.form} · filed ${date(f.filing_date)}` }));
  }, [id, india]);
  const [acc, setAcc] = useState("");
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [dim, setDim] = useState(false);
  const [res, setRes] = useState<XbrlResult | null>(null);
  const [facts, setFacts] = useState<XbrlFact[]>([]);
  const [err, setErr] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (!acc && filings.data?.length) setAcc(filings.data[0].key); }, [filings.data, acc]);
  useEffect(() => { const t = setTimeout(() => setTerm(q.trim()), 300); return () => clearTimeout(t); }, [q]);

  useEffect(() => {
    if (!acc) return;
    let live = true;
    setBusy(true); setErr(null);
    (india ? api.indiaXbrl : api.xbrl)(id, acc, term, dim, 0, PAGE).then(
      (r) => { if (live) { setRes(r); setFacts(r.facts); setBusy(false); } },
      (e) => { if (live) { setErr(e as ApiError); setRes(null); setFacts([]); setBusy(false); } },
    );
    return () => { live = false; };
  }, [id, acc, term, dim, india]);

  const more = async () => {
    setBusy(true);
    try {
      const r = await (india ? api.indiaXbrl : api.xbrl)(id, acc, term, dim, facts.length, PAGE);
      setFacts((p) => [...p, ...r.facts]);
    } catch (e) { setErr(e as ApiError); }
    setBusy(false);
  };

  const exportCsv = async () => {
    if (!res) return;
    const all = await (india ? api.indiaXbrl : api.xbrl)(id, acc, term, dim, 0, 5000);
    csvDownload(`xbrl-${id}-${acc}.csv`, [
      ["Concept", "Label", "Value", "Unit", "Period start", "Period end", "Dimensions"],
      ...all.facts.map((f) => [f.concept, f.label, f.value, f.unit, f.start, f.end, f.dimensions.join(" | ")]),
    ]);
  };

  return (
    <>
      <div className="sec-head"><h2>XBRL facts</h2></div>
      <p className="muted" style={{ fontSize: 14.5, maxWidth: "46em", margin: "-4px 0 16px" }}>
        {india ? "Figures from the XBRL file the company filed with NSE with its financial results, with the period each was reported for. Amounts are in rupees." : "Every number the company tagged in its filing, with the period and unit it was reported for. Read directly from the downloaded report."}
      </p>
      {filings.error && <ErrorNotice error={filings.error} />}
      {filings.loading && <Skeleton h={200} />}
      {filings.data && filings.data.length === 0 && (
        india
          ? <Empty title="No XBRL filings found">NSE did not list any results filings with XBRL for this company.</Empty>
          : <Empty title="No downloaded reports yet">Open the Annual reports tab and choose “Make searchable” on a filing. Its tagged figures will appear here.</Empty>
      )}
      {filings.data && filings.data.length > 0 && (
        <div className="panel" style={{ marginTop: 0 }}>
          <header>
            <div className="toolbar">
              <select className="input sm" value={acc} onChange={(e) => setAcc(e.target.value)} aria-label="Filing">
                {filings.data.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
              </select>
              <input className="input sm" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter, e.g. revenue or debt" aria-label="Filter by concept" />
              <label className="check"><input type="checkbox" checked={dim} onChange={(e) => setDim(e.target.checked)} /> Include breakdowns (segments, products)</label>
            </div>
            <button className="btn ghost sm" disabled={!res || !res.matched} onClick={exportCsv}>Export CSV</button>
          </header>
          {err && <div style={{ padding: 20 }}><ErrorNotice error={err} /></div>}
          {res && !res.has_xbrl && <div style={{ padding: 20 }}><Empty title="No XBRL tags in this file">{india ? "The file had no numeric facts." : "Only filings from about 2019 onward carry inline XBRL."}</Empty></div>}
          {res && res.has_xbrl && (
            <>
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th>Item</th><th className="r">Value</th><th>Period</th><th>Breakdown</th></tr></thead>
                  <tbody>
                    {facts.map((f, i) => (
                      <tr key={i}>
                        <td className="k">{f.label}<div className="mono" style={{ color: "var(--muted)", fontWeight: 400 }}>{f.concept}</div></td>
                        <td className="r num" title={`${f.value} ${f.unit}`}>{fmtValue(f)}</td>
                        <td>{period(f)}</td>
                        <td style={{ maxWidth: 260, color: "var(--muted)" }}>{f.dimensions.map((d) => d.split(":").pop()).join(", ") || "Total"}</td>
                      </tr>
                    ))}
                    {facts.length === 0 && <tr><td colSpan={4} style={{ padding: 24, textAlign: "center", color: "var(--muted)" }}>Nothing matches “{term}”.</td></tr>}
                  </tbody>
                </table>
              </div>
              <div className="panel-foot">
                <span>Showing {facts.length.toLocaleString()} of {res.matched.toLocaleString()}{!dim && res.total_facts > res.matched && !term ? ` (${(res.total_facts - res.matched).toLocaleString()} breakdown values hidden)` : ""}</span>
                {facts.length < res.matched && <button className="btn ghost sm" disabled={busy} onClick={more}>{busy ? <Spinner dark /> : "Load more"}</button>}
              </div>
            </>
          )}
          {busy && !res && !err && <div style={{ padding: 20 }}><Skeleton h={160} /></div>}
        </div>
      )}
    </>
  );
}
