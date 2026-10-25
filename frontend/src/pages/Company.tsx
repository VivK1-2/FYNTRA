import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api, ApiError, Fact, Filing, Financials, IngestStatus, Market, Trend } from "../api";
import { GroupedBars, Legend, PriceChart } from "../charts";
import { Empty, ErrorNotice, Notice, SearchBox, Skeleton, Spinner, Star } from "../components";
import { csvDownload, date, money, pct, price } from "../format";
import { useAsync } from "../hooks";
import { useRecents, useWatchlist } from "../storage";
import Ask from "./Ask";
import Search from "./SearchTab";
import Xbrl from "./Xbrl";

type Tab = "overview" | "financials" | "filings" | "xbrl" | "search" | "ask";
const YEARS = [2025, 2024, 2023, 2022, 2021, 2020, 2019];
const RANGES = ["1mo", "3mo", "6mo", "1y", "5y"] as const;
const RANGE_LABEL: Record<string, string> = { "1mo": "1M", "3mo": "3M", "6mo": "6M", "1y": "1Y", "5y": "5Y" };

export default function CompanyPage() {
  const { id = "" } = useParams();
  const [tab, setTab] = useState<Tab>("overview");
  const [fy, setFy] = useState(2024);
  const [range, setRange] = useState<(typeof RANGES)[number]>("1y");
  const company = useAsync(() => api.company(id), [id]);
  const c = company.data;
  const india = c?.country === "India";
  const fin = useAsync(() => (c && !india ? api.financials(id, fy) : Promise.resolve(null)), [id, fy, c?.id, india]);
  const mkt = useAsync(() => (c ? api.market(id, range) : Promise.resolve(null)), [id, range, c?.id]);
  const watch = useWatchlist();
  const recents = useRecents();
  useEffect(() => setTab("overview"), [id]);
  useEffect(() => { if (c?.ticker) recents.add(c.ticker); /* eslint-disable-next-line */ }, [c?.ticker]);

  const tabs: [Tab, string][] = [
    ["overview", "Overview"],
    ...(india ? [] : [["financials", "Financials"] as [Tab, string]]),
    ["filings", "Annual reports"],
    ["xbrl", "XBRL facts"],
    ["search", "Search reports"],
    ["ask", "Ask"],
  ];
  const q = mkt.data?.quote;
  const up = (q?.change ?? 0) >= 0;

  return (
    <>
      <section className="page-head">
        <div className="wrap">
          <div className="head-row">
            <div>
              {company.loading && <Skeleton h={38} w={280} />}
              {c && (
                <>
                  <h1>{c.name} {c.ticker && <Star on={watch.has(c.ticker)} toggle={() => watch.toggle(c.ticker!)} label={c.ticker} />}</h1>
                  <div className="meta">
                    {[c.ticker, c.exchange, c.country, c.currency, c.sec_cik ? `CIK ${c.sec_cik}` : null].filter(Boolean).map((m, i, a) => (
                      <span key={String(m)} style={{ display: "contents" }}><span>{m}</span>{i < a.length - 1 && <span className="sep" />}</span>
                    ))}
                  </div>
                </>
              )}
              {company.error && <h1>{id}</h1>}
            </div>
            {q && (
              <div className="price">
                <div className="big num">{price(q.price, q.currency ?? "USD")}</div>
                {q.change !== null && q.change !== undefined && (
                  <div className={`chg num ${up ? "up" : "down"}`}>{up ? "▲" : "▼"} {Math.abs(q.change).toFixed(2)} ({Math.abs(q.change_pct ?? 0).toFixed(2)}%) today</div>
                )}
              </div>
            )}
          </div>
          <div className="tabs" role="tablist">
            {tabs.map(([k, label]) => (
              <button key={k} role="tab" aria-selected={tab === k} className="tab" onClick={() => setTab(k)}>{label}</button>
            ))}
          </div>
        </div>
      </section>

      <div className="wrap body">
        {company.error && (
          <div style={{ display: "grid", gap: 16 }}>
            <ErrorNotice error={company.error} />
            <div style={{ maxWidth: 420 }}><SearchBox initial={id} className="hero-search" button={false} /></div>
          </div>
        )}
        {c && tab === "overview" && <Overview id={id} fy={fy} setFy={setFy} fin={fin} mkt={mkt} range={range} setRange={setRange} india={india} currency={c.currency ?? "USD"} />}
        {c && tab === "financials" && <Statements fin={fin} fy={fy} setFy={setFy} ticker={c.ticker ?? id} />}
        {c && tab === "filings" && <Filings id={id} />}
        {c && tab === "xbrl" && <Xbrl id={id} india={india} />}
        {c && tab === "search" && <Search id={id} />}
        {c && tab === "ask" && <Ask id={id} />}
      </div>
    </>
  );
}

type Async<T> = { data?: T | null; error?: ApiError; loading: boolean };

function YearPicker({ fy, setFy }: { fy: number; setFy: (n: number) => void }) {
  return (
    <label style={{ display: "inline-flex", gap: 8, alignItems: "center", fontSize: 14 }}>
      Fiscal year
      <select className="select" value={fy} onChange={(e) => setFy(+e.target.value)}>
        {YEARS.map((y) => <option key={y} value={y}>FY{y}</option>)}
      </select>
    </label>
  );
}

/* ---------------- overview ---------------- */
function Overview({ id, fy, setFy, fin, mkt, range, setRange, india, currency }: {
  id: string; fy: number; setFy: (n: number) => void; fin: Async<Financials>; mkt: Async<Market>;
  range: string; setRange: (r: (typeof RANGES)[number]) => void; india: boolean; currency: string;
}) {
  const f = fin.data;
  const cur = f?.income_statement.revenue?.currency ?? "USD";
  const m = mkt.data;
  return (
    <>
      <div className="panel" style={{ marginTop: 0 }}>
        <header>
          <h3>Share price</h3>
          <div className="pills" role="group" aria-label="Time range">
            {RANGES.map((r) => <button key={r} aria-pressed={range === r} onClick={() => setRange(r)}>{RANGE_LABEL[r]}</button>)}
          </div>
        </header>
        <div className="chart-box">
          {mkt.loading && <Skeleton h={260} />}
          {mkt.error && <ErrorNotice error={mkt.error} />}
          {m && <PriceChart points={m.points} fmt={(n) => price(n, m.quote.currency ?? currency)} />}
        </div>
        {m && (
          <div className="stats" style={{ margin: 0, borderBottom: 0 }}>
            <Mini k="Day range" v={m.quote.day_low != null && m.quote.day_high != null ? `${price(m.quote.day_low, currency)} – ${price(m.quote.day_high, currency)}` : "—"} />
            <Mini k="52-week range" v={m.quote.year_low != null && m.quote.year_high != null ? `${price(m.quote.year_low, currency)} – ${price(m.quote.year_high, currency)}` : "—"} />
            <Mini k="Volume" v={m.quote.volume != null ? Math.round(m.quote.volume).toLocaleString("en-US") : "—"} />
            <Mini k="Source" v={m.source === "yahoo" ? "Yahoo Finance" : "Stooq"} />
          </div>
        )}
      </div>

      {india && (
        <div style={{ marginTop: 28 }}>
          <Notice kind="info">
            <div><strong>Financial statements aren't available for Indian companies yet</strong>
              You can still read their annual reports: open <em>Annual reports</em>, make a report searchable, then search it or ask questions.</div>
          </Notice>
        </div>
      )}

      {!india && (
        <>
          <div className="sec-head" style={{ marginTop: 40 }}>
            <h2>Key figures</h2><YearPicker fy={fy} setFy={setFy} />
          </div>
          {fin.error && <ErrorNotice error={fin.error} />}
          {fin.loading && <Skeleton h={90} />}
          {f && (
            <>
              <div className="stats">
                <Stat k="Revenue" v={money(f.income_statement.revenue?.value, cur)} n={f.period} />
                <Stat k="Net income" v={money(f.income_statement.net_income?.value, cur)} n={f.period} />
                <Stat k="Total assets" v={money(f.balance_sheet.total_assets?.value, cur)} n="Year end" />
                <Stat k="Net margin" v={pct(f.ratios?.net_margin?.value)} n="Net income ÷ revenue" />
              </div>
              <Trends id={id} fy={fy} />
              <Ratios f={f} />
            </>
          )}
        </>
      )}
    </>
  );
}

function Mini({ k, v }: { k: string; v: string }) {
  return <div className="stat"><div className="k">{k}</div><div className="num" style={{ color: "var(--ink)", fontWeight: 600, fontSize: 16, marginTop: 2 }}>{v}</div></div>;
}
function Stat({ k, v, n }: { k: string; v: string; n: string }) {
  return <div className="stat"><div className="k">{k}</div><div className="v num">{v}</div><div className="n">{n}</div></div>;
}

function Trends({ id, fy }: { id: string; fy: number }) {
  const t = useAsync<Trend>(() => api.trend(id, fy - 4, fy), [id, fy]);
  const d = t.data;
  const labels = d?.years.map((y) => `FY${y.fy}`) ?? [];
  const col = (k: "revenue" | "net_income" | "gross_margin" | "operating_margin" | "net_margin") => d?.years.map((y) => y[k]) ?? [];
  const cur = d?.currency ?? "USD";
  const exportCsv = () => d && csvDownload(`${d.ticker}-trend.csv`, [
    ["Fiscal year", "Revenue", "Gross profit", "Operating income", "Net income", "Net margin", "Total assets", "Operating cash flow", "Free cash flow"],
    ...d.years.map((y) => [`FY${y.fy}`, y.revenue, y.gross_profit, y.operating_income, y.net_income, y.net_margin, y.total_assets, y.operating_cash_flow, y.free_cash_flow]),
  ]);
  return (
    <>
      <div className="panel">
        <header>
          <h3>Revenue and net income, five years</h3>
          <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
            {d && <Legend items={[{ label: "Revenue", color: "var(--s1)" }, { label: "Net income", color: "var(--s2)" }]} />}
            <button className="btn ghost sm" onClick={exportCsv} disabled={!d}>Download CSV</button>
          </div>
        </header>
        <div className="chart-box">
          {t.loading && <Skeleton h={250} />}
          {t.error && <ErrorNotice error={t.error} />}
          {d && d.years.length > 0 && <GroupedBars groups={labels} fmt={(n) => money(n, cur)}
            series={[{ key: "rev", label: "Revenue", color: "var(--s1)", values: col("revenue") }, { key: "ni", label: "Net income", color: "var(--s2)", values: col("net_income") }]} />}
          {d && d.years.length === 0 && <Empty title="No yearly data found" />}
        </div>
      </div>
      {d && d.years.length > 0 && (
        <div className="panel">
          <header>
            <h3>Margins</h3>
            <Legend items={[{ label: "Gross", color: "var(--s1)" }, { label: "Operating", color: "var(--s2)" }, { label: "Net", color: "var(--s3)" }]} />
          </header>
          <div className="chart-box">
            <GroupedBars groups={labels} fmt={(n) => pct(n)} axis={(n) => `${Math.round(n * 100)}%`}
              series={[{ key: "g", label: "Gross margin", color: "var(--s1)", values: col("gross_margin") }, { key: "o", label: "Operating margin", color: "var(--s2)", values: col("operating_margin") }, { key: "n", label: "Net margin", color: "var(--s3)", values: col("net_margin") }]} />
          </div>
        </div>
      )}
    </>
  );
}

function Ratios({ f }: { f: Financials }) {
  const rows: [string, Fact | null | undefined][] = f.ratios ? [
    ["Gross margin", f.ratios.gross_margin], ["Operating margin", f.ratios.operating_margin], ["Net margin", f.ratios.net_margin],
    ["Return on assets", f.ratios.roa], ["Return on equity", f.ratios.roe],
  ] : [];
  const max = Math.max(0.01, ...rows.map(([, r]) => Math.abs(r?.value ?? 0)));
  return (
    <div className="panel">
      <header><h3>Profitability and returns · {f.period}</h3><span className="badge brand">Calculated in code</span></header>
      {rows.length === 0 ? <Empty title="No ratios for this year" /> : rows.map(([label, r]) => (
        <div className="ratio-row" key={label} title={r?.source.xbrl_tag ?? ""}>
          <span>{label}</span>
          <div className="ratio-track"><div className="ratio-fill" style={{ width: `${(Math.abs(r?.value ?? 0) / max) * 100}%` }} /></div>
          <span className="ratio-val num">{pct(r?.value)}</span>
        </div>
      ))}
    </div>
  );
}

/* ---------------- financial statements ---------------- */
function Statements({ fin, fy, setFy, ticker }: { fin: Async<Financials>; fy: number; setFy: (n: number) => void; ticker: string }) {
  const f = fin.data;
  const sections: [string, [string, Fact | null | undefined][]][] = f ? [
    ["Income statement", [
      ["Revenue", f.income_statement.revenue], ["Cost of revenue", f.income_statement.cost_of_revenue],
      ["Gross profit", f.income_statement.gross_profit], ["Operating expenses", f.income_statement.operating_expenses],
      ["Operating income", f.income_statement.operating_income], ["Net income", f.income_statement.net_income],
      ["Earnings per share (basic)", f.income_statement.basic_eps]]],
    ["Balance sheet", [
      ["Cash and equivalents", f.balance_sheet.cash_and_equivalents], ["Total assets", f.balance_sheet.total_assets],
      ["Total liabilities", f.balance_sheet.total_liabilities], ["Total equity", f.balance_sheet.total_equity],
      ["Total debt", f.balance_sheet.total_debt]]],
    ["Cash flow", [
      ["Operating cash flow", f.cash_flow.operating_cash_flow], ["Capital expenditure", f.cash_flow.capital_expenditure],
      ["Free cash flow", f.cash_flow.free_cash_flow]]],
  ] : [];
  const exportCsv = () => f && csvDownload(`${ticker}-${f.period}.csv`, [
    ["Statement", "Item", "Value", "Currency", "Period", "Type", "Source tag"],
    ...sections.flatMap(([s, rows]) => rows.map(([label, x]) => [s, label, x?.value ?? "", x?.currency ?? "", x?.period ?? f.period, x?.value_type ?? "", x?.source.xbrl_tag ?? ""])),
  ]);
  return (
    <>
      <div className="sec-head">
        <h2>Financial statements</h2>
        <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
          <YearPicker fy={fy} setFy={setFy} />
          <button className="btn ghost sm" onClick={exportCsv} disabled={!f}>Download CSV</button>
        </div>
      </div>
      {fin.error && <ErrorNotice error={fin.error} />}
      {fin.loading && <Skeleton h={260} />}
      {sections.map(([title, rows]) => (
        <div className="panel" key={title}>
          <header><h3>{title}</h3></header>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Item</th><th className="r">Value</th><th>Period</th><th>Source</th></tr></thead>
              <tbody>
                {rows.map(([label, x]) => (
                  <tr key={label}>
                    <td className="k">{label}</td>
                    <td className="r num">{x ? (label.startsWith("Earnings") ? `$${x.value?.toFixed(2) ?? "—"}` : money(x.value, x.currency ?? "USD")) : "—"}</td>
                    <td>{x?.period ?? "—"}</td>
                    <td>{x ? <span className="code" title={x.source.provider}>{x.value_type === "calculated" ? "Calculated · " : ""}{x.source.xbrl_tag ?? x.source.provider}</span> : <span className="muted">Not reported</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </>
  );
}

/* ---------------- filings + ingest ---------------- */
function statusBadge(s?: IngestStatus) {
  if (!s) return <span className="badge">Not downloaded</span>;
  switch (s.status) {
    case "processed": return <span className="badge good">Searchable · {s.page_count ?? "?"} pages</span>;
    case "processing": case "pending": return <span className="badge brand">Reading…</span>;
    case "needs_ocr": return <span className="badge warn">Scanned, can't read yet</span>;
    default: return <span className="badge bad" title={s.error ?? ""}>Failed{s.error ? `: ${s.error.slice(0, 50)}` : ""}</span>;
  }
}

function Filings({ id }: { id: string }) {
  const list = useAsync(() => api.filings(id, 8), [id]);
  const [status, setStatus] = useState<Record<string, IngestStatus>>({});
  const [err, setErr] = useState<string | null>(null);
  const timers = useRef<Record<string, number>>({});
  useEffect(() => () => Object.values(timers.current).forEach(clearInterval), []);

  useEffect(() => {
    if (list.data && list.data.length) api.ingestStatuses(id).then(setStatus, () => {});
  }, [list.data, id]);

  const poll = (acc: string) => {
    clearInterval(timers.current[acc]);
    timers.current[acc] = window.setInterval(async () => {
      try {
        const s = await api.ingestStatus(id, acc);
        setStatus((p) => ({ ...p, [acc]: s }));
        if (!["pending", "processing"].includes(s.status)) clearInterval(timers.current[acc]);
      } catch { clearInterval(timers.current[acc]); }
    }, 2000);
  };

  const ingest = async (f: Filing) => {
    setErr(null);
    try {
      const s = await api.ingest(id, f.accession_number);
      setStatus((p) => ({ ...p, [f.accession_number]: s }));
      if (["pending", "processing"].includes(s.status)) poll(f.accession_number);
    } catch (e) { setErr((e as Error).message); }
  };

  const isNse = list.data?.[0]?.provider === "nse";
  return (
    <>
      <div className="sec-head"><h2>{isNse ? "Annual reports" : "Annual reports (10-K)"}</h2></div>
      {list.error && <ErrorNotice error={list.error} />}
      {err && <Notice kind="err"><div>{err}</div></Notice>}
      {list.loading && <Skeleton h={200} />}
      {list.data && list.data.length === 0 && <Empty title="No annual reports found">The source returned no reports for this company.</Empty>}
      {list.data && list.data.length > 0 && (
        <div className="panel" style={{ marginTop: 0 }}>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>{isNse ? "Fiscal year" : "Filed"}</th><th>{isNse ? "Source" : "Period end"}</th><th>Search status</th><th className="r">Actions</th></tr></thead>
              <tbody>
                {list.data.map((f) => {
                  const s = status[f.accession_number];
                  const busy = !!s && ["pending", "processing"].includes(s.status);
                  const done = s?.status === "processed";
                  return (
                    <tr key={f.accession_number}>
                      <td className="k">{f.fiscal_label ?? date(f.filing_date)}</td>
                      <td>{isNse ? "NSE" : date(f.report_date)}</td>
                      <td>{statusBadge(s)}</td>
                      <td className="r" style={{ whiteSpace: "nowrap" }}>
                        <a className="btn ghost sm" href={f.document_url} target="_blank" rel="noreferrer noopener">Open original</a>{" "}
                        {!done && <button className="btn sm" disabled={busy} onClick={() => ingest(f)}>{busy ? <><Spinner /> Reading</> : s?.status === "failed" ? "Try again" : "Make searchable"}</button>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
      <p className="muted" style={{ fontSize: 14, marginTop: 14 }}>
        Making a report searchable downloads it once from the official source, reads the text with page numbers and stores it on this computer.
      </p>
    </>
  );
}
