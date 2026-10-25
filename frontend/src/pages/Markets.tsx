import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, Market } from "../api";
import { Sparkline } from "../charts";
import { Empty, Skeleton, Star } from "../components";
import { price } from "../format";
import { useRecents, useWatchlist } from "../storage";

type Row = { loading: boolean; data?: Market; error?: string };

export default function Markets() {
  const watch = useWatchlist();
  const recents = useRecents().list;
  const nav = useNavigate();
  const [rows, setRows] = useState<Record<string, Row>>({});
  const [add, setAdd] = useState("");

  useEffect(() => {
    watch.list.filter((t) => !rows[t]).forEach((t) => {
      setRows((p) => ({ ...p, [t]: { loading: true } }));
      api.market(t, "1mo").then(
        (data) => setRows((p) => ({ ...p, [t]: { loading: false, data } })),
        (e: Error) => setRows((p) => ({ ...p, [t]: { loading: false, error: e.message } })),
      );
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [watch.list.join(",")]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const t = add.trim().toUpperCase();
    if (t && !watch.has(t)) watch.toggle(t);
    setAdd("");
  };

  return (
    <div className="wrap body">
      <div className="sec-head">
        <div><h1 style={{ fontSize: 34, letterSpacing: "-0.035em" }}>Markets</h1><p style={{ marginTop: 6 }}>Your watchlist with the last month of prices. It's saved in this browser.</p></div>
        <form onSubmit={submit} style={{ display: "flex", gap: 8 }}>
          <input className="input" style={{ width: 190 }} value={add} onChange={(e) => setAdd(e.target.value)} placeholder="Add a ticker" aria-label="Add a ticker to the watchlist" autoCapitalize="characters" spellCheck={false} />
          <button className="btn ghost" type="submit">Add</button>
        </form>
      </div>

      {watch.list.length === 0 ? (
        <div className="panel"><Empty title="Your watchlist is empty">
          Add a ticker above, or start with one of these.
          <div className="hero-links" style={{ justifyContent: "center", marginTop: 14 }}>
            {["AAPL", "MSFT", "NVDA", "RELIANCE"].map((t) => <button key={t} onClick={() => watch.toggle(t)}>{t}</button>)}
          </div>
        </Empty></div>
      ) : (
        <div className="panel" style={{ marginTop: 20 }}>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Company</th><th className="r">Price</th><th className="r">Change today</th><th>1 month</th><th className="r"></th></tr></thead>
              <tbody>
                {watch.list.map((t) => {
                  const r = rows[t];
                  const q = r?.data?.quote;
                  const up = (q?.change ?? 0) >= 0;
                  return (
                    <tr key={t}>
                      <td><Link className="rowlink" to={`/company/${t}`}>{t}</Link>{q?.name && <div className="muted" style={{ fontSize: 13.5 }}>{q.name}</div>}</td>
                      {r?.loading || !r ? <td colSpan={3}><Skeleton h={18} w={220} /></td>
                        : r.error ? <td colSpan={3} className="muted">Unavailable: {r.error}</td>
                        : <>
                          <td className="r num">{price(q!.price, q!.currency ?? "USD")}</td>
                          <td className={`r num chg ${up ? "up" : "down"}`}>{q!.change_pct == null ? "—" : `${up ? "▲" : "▼"} ${Math.abs(q!.change_pct).toFixed(2)}%`}</td>
                          <td><Sparkline values={r.data!.points.map((p) => p.c)} up={r.data!.points[r.data!.points.length - 1].c >= r.data!.points[0].c} /></td>
                        </>}
                      <td className="r"><Star on label={t} toggle={() => watch.toggle(t)} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {recents.length > 0 && (
        <>
          <div className="sec-head" style={{ marginTop: 40 }}><h2>Recently viewed</h2></div>
          <div className="hero-links" style={{ marginTop: 0 }}>
            {recents.map((t) => <button key={t} onClick={() => nav(`/company/${t}`)}>{t}</button>)}
          </div>
        </>
      )}
    </div>
  );
}
