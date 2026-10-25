import { FormEvent, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, Compare as CompareResult, Metrics } from "../api";
import { HBars } from "../charts";
import { Empty, ErrorNotice, Notice, Skeleton } from "../components";
import { csvDownload, money, pct } from "../format";
import { useAsync } from "../hooks";

const COLORS = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)"];
const YEARS = [2025, 2024, 2023, 2022, 2021, 2020, 2019];

const CHARTS: [keyof Metrics, string, "money" | "pct"][] = [
  ["revenue", "Revenue", "money"], ["net_income", "Net income", "money"],
  ["net_margin", "Net margin", "pct"], ["operating_margin", "Operating margin", "pct"], ["roe", "Return on equity", "pct"], ["roa", "Return on assets", "pct"],
];
const TABLE: [keyof Metrics, string, "money" | "pct"][] = [
  ...CHARTS, ["gross_margin", "Gross margin", "pct"], ["total_assets", "Total assets", "money"],
  ["operating_cash_flow", "Operating cash flow", "money"], ["free_cash_flow", "Free cash flow", "money"],
];

export default function Compare() {
  const [params, setParams] = useSearchParams();
  const tickers = (params.get("t") ?? "AAPL,MSFT").split(",").map((t) => t.trim().toUpperCase()).filter(Boolean).slice(0, 4);
  const fy = +(params.get("fy") ?? 2024) || 2024;
  const [add, setAdd] = useState("");
  const set = (t: string[], y = fy) => setParams({ t: t.join(","), fy: String(y) }, { replace: true });
  const res = useAsync<CompareResult>(() => (tickers.length >= 2 ? api.compare(tickers, fy) : Promise.reject(null)), [tickers.join(","), fy]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const t = add.trim().toUpperCase();
    if (t && !tickers.includes(t) && tickers.length < 4) set([...tickers, t]);
    setAdd("");
  };
  const fmt = (kind: "money" | "pct", v: number | null, cur = "USD") => (kind === "pct" ? pct(v) : money(v, cur));
  const d = res.data;
  const colorOf = (t: string) => COLORS[tickers.indexOf(t)] ?? COLORS[0];

  const exportCsv = () => d && csvDownload(`compare-FY${d.fy}.csv`, [
    ["Metric", ...d.companies.map((c) => c.ticker)],
    ...TABLE.map(([k, label]) => [label, ...d.companies.map((c) => c.metrics?.[k] ?? "")]),
  ]);

  return (
    <div className="wrap body">
      <div className="sec-head">
        <div><h1 style={{ fontSize: 34, letterSpacing: "-0.035em" }}>Compare</h1><p style={{ marginTop: 6 }}>Up to four US companies on the same fiscal year.</p></div>
        <label style={{ display: "inline-flex", gap: 8, alignItems: "center", fontSize: 14 }}>
          Fiscal year
          <select className="select" value={fy} onChange={(e) => set(tickers, +e.target.value)}>{YEARS.map((y) => <option key={y} value={y}>FY{y}</option>)}</select>
        </label>
      </div>

      <div className="chips">
        {tickers.map((t, i) => (
          <span className="tkr" key={t}><i style={{ background: COLORS[i] }} />{t}<button aria-label={`Remove ${t}`} onClick={() => set(tickers.filter((x) => x !== t))}>×</button></span>
        ))}
        {tickers.length < 4 && (
          <form onSubmit={submit} style={{ display: "flex", gap: 8 }}>
            <input className="input" style={{ width: 150, padding: "7px 12px" }} value={add} onChange={(e) => setAdd(e.target.value)} placeholder="Add a ticker" aria-label="Add a ticker to compare" autoCapitalize="characters" spellCheck={false} />
            <button className="btn ghost sm" type="submit">Add</button>
          </form>
        )}
      </div>

      <div style={{ marginTop: 24 }}>
        {tickers.length < 2 && <div className="panel"><Empty title="Add at least two companies">Fiscal years differ between companies, so FY2024 means each company's own fiscal year.</Empty></div>}
        {tickers.length >= 2 && res.loading && <Skeleton h={300} />}
        {tickers.length >= 2 && res.error && res.error.message && <ErrorNotice error={res.error} />}
        {d && (
          <>
            {d.companies.filter((c) => c.error).map((c) => <div key={c.ticker} style={{ marginBottom: 10 }}><Notice kind="warn"><div><strong>{c.ticker}</strong>{c.error}</div></Notice></div>)}
            <div className="cmp-grid">
              {CHARTS.map(([k, label, kind]) => (
                <div className="panel" style={{ marginTop: 0 }} key={k}>
                  <header><h3>{label}</h3></header>
                  <HBars rows={d.companies.map((c) => ({ label: c.ticker, color: colorOf(c.ticker), value: c.metrics?.[k] ?? null }))} fmt={(n) => fmt(kind, n)} />
                </div>
              ))}
            </div>
            <div className="panel" style={{ marginTop: 20 }}>
              <header><h3>All figures · FY{d.fy}</h3><button className="btn ghost sm" onClick={exportCsv}>Download CSV</button></header>
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th>Metric</th>{d.companies.map((c) => <th className="r" key={c.ticker}>{c.ticker}</th>)}</tr></thead>
                  <tbody>
                    {TABLE.map(([k, label, kind]) => (
                      <tr key={k}><td className="k">{label}</td>{d.companies.map((c) => <td className="r num" key={c.ticker}>{fmt(kind, c.metrics?.[k] ?? null, c.currency)}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
