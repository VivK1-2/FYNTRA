import { ReactNode, useEffect, useRef, useState } from "react";
import { axisMoney, shortDate } from "./format";

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [w, setW] = useState(640);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setW(Math.max(260, el.clientWidth)));
    ro.observe(el);
    setW(Math.max(260, el.clientWidth));
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

function niceTicks(min: number, max: number, count = 4, cover = false): number[] {
  if (max === min) return [min];
  const step0 = (max - min) / count;
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) ?? step0;
  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; out.length < 12; v += step) {
    out.push(+v.toFixed(10));
    if (v >= max - 1e-9) break;
  }
  if (!cover && out.length > 1 && out[out.length - 1] > max + 1e-9) out.pop();
  return out;
}

/* ---------- price line with area + crosshair ---------- */
export function PriceChart({ points, fmt }: { points: { t: string; c: number }[]; fmt: (n: number) => string }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const h = 260, R = 12, T = 12, B = 26;
  if (points.length < 2) return <div ref={ref} />;
  const vals = points.map((p) => p.c);
  const lo = Math.min(...vals), hi = Math.max(...vals), pad = (hi - lo) * 0.08 || 1;
  const y0 = lo - pad, y1 = hi + pad;
  const ticks = niceTicks(y0, y1, 4);
  const L = Math.max(56, Math.max(...ticks.map((t) => fmt(t).length)) * 7.4 + 14);
  const x = (i: number) => L + (i / (points.length - 1)) * (w - L - R);
  const y = (v: number) => T + (1 - (v - y0) / (y1 - y0)) * (h - T - B);
  const line = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.c).toFixed(1)}`).join("");
  const area = `${line}L${x(points.length - 1)},${h - B}L${x(0)},${h - B}Z`;
  const long = new Date(points[points.length - 1].t).getTime() - new Date(points[0].t).getTime() > 200 * 864e5;
  const xt = (w < 460 ? [0, 0.5, 1] : [0, 0.25, 0.5, 0.75, 1]).map((f) => Math.round(f * (points.length - 1)));
  const hp = hover !== null ? points[hover] : null;

  const move = (e: React.PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const f = (e.clientX - r.left - L) / (w - L - R);
    setHover(Math.min(points.length - 1, Math.max(0, Math.round(f * (points.length - 1)))));
  };

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <svg width={w} height={h} onPointerMove={move} onPointerLeave={() => setHover(null)} role="img"
        aria-label={`Price from ${points[0].t} to ${points[points.length - 1].t}`}>
        <defs>
          <linearGradient id="pc-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="var(--s1)" stopOpacity="0.2" /><stop offset="1" stopColor="var(--s1)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <g className="axis">
          {ticks.map((t) => (
            <g key={t}><line className="gridline" x1={L} x2={w - R} y1={y(t)} y2={y(t)} /><text x={L - 8} y={y(t) + 4} textAnchor="end">{fmt(t)}</text></g>
          ))}
          {xt.map((i, k) => (
            <text key={k} x={x(i)} y={h - 6} textAnchor={k === 0 ? "start" : k === xt.length - 1 ? "end" : "middle"}>{shortDate(points[i].t, long)}</text>
          ))}
        </g>
        <path d={area} fill="url(#pc-fill)" />
        <path d={line} fill="none" stroke="var(--s1)" strokeWidth="2" strokeLinejoin="round" />
        {hp && (
          <g>
            <line x1={x(hover!)} x2={x(hover!)} y1={T} y2={h - B} stroke="var(--muted)" strokeDasharray="3 3" />
            <circle cx={x(hover!)} cy={y(hp.c)} r="5" fill="var(--s1)" stroke="var(--bg)" strokeWidth="2" />
          </g>
        )}
      </svg>
      {hp && (
        <div className="tip" style={{ left: Math.min(w - 130, Math.max(L, x(hover!) - 50)), top: 0 }}>
          <b>{fmt(hp.c)}</b><br />{shortDate(hp.t, false)} {new Date(hp.t).getFullYear()}
        </div>
      )}
    </div>
  );
}

/* ---------- tiny trend line for lists ---------- */
export function Sparkline({ values, up }: { values: number[]; up?: boolean }) {
  if (values.length < 2) return null;
  const w = 96, h = 28, lo = Math.min(...values), hi = Math.max(...values);
  const d = values.map((v, i) => `${i ? "L" : "M"}${((i / (values.length - 1)) * (w - 2) + 1).toFixed(1)},${(h - 3 - ((v - lo) / (hi - lo || 1)) * (h - 6)).toFixed(1)}`).join("");
  return <svg width={w} height={h} aria-hidden><path d={d} fill="none" stroke={up ? "var(--good)" : "var(--bad)"} strokeWidth="1.6" strokeLinejoin="round" /></svg>;
}

/* ---------- grouped columns (one group per year) ---------- */
export interface Series { key: string; label: string; color: string; values: (number | null)[] }

export function GroupedBars({ groups, series, fmt, axis = axisMoney }: { groups: string[]; series: Series[]; fmt: (n: number) => string; axis?: (n: number) => string }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const h = 250, L = 52, R = 8, T = 10, B = 26;
  const all = series.flatMap((s) => s.values.filter((v): v is number => v !== null));
  const hi = Math.max(0, ...all), lo = Math.min(0, ...all);
  const ticks = niceTicks(lo, hi * 1.05 || 1, 4, true);
  const top = Math.max(...ticks), bot = Math.min(...ticks, lo);
  const y = (v: number) => T + (1 - (v - bot) / (top - bot || 1)) * (h - T - B);
  const gw = (w - L - R) / Math.max(1, groups.length);
  const bw = Math.min(34, (gw * 0.72) / series.length);
  const gap = 2;

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <svg width={w} height={h} role="img" aria-label="Values by fiscal year" onPointerLeave={() => setHover(null)}>
        <g className="axis">
          {ticks.map((t) => (<g key={t}><line className="gridline" x1={L} x2={w - R} y1={y(t)} y2={y(t)} /><text x={L - 8} y={y(t) + 4} textAnchor="end">{axis(t)}</text></g>))}
          {groups.map((g, i) => <text key={g} x={L + gw * i + gw / 2} y={h - 7} textAnchor="middle">{g}</text>)}
        </g>
        {groups.map((g, i) => {
          const cx = L + gw * i + gw / 2;
          const start = cx - (series.length * bw + (series.length - 1) * gap) / 2;
          return (
            <g key={g} onPointerMove={() => setHover(i)}>
              <rect x={L + gw * i} y={T} width={gw} height={h - T - B} fill="transparent" />
              {series.map((s, k) => {
                const v = s.values[i];
                if (v === null) return null;
                const y1 = y(Math.max(v, 0)), y2 = y(Math.min(v, 0));
                return <rect key={s.key} x={start + k * (bw + gap)} y={y1} width={bw} height={Math.max(1, y2 - y1)} rx="3" fill={s.color} opacity={hover === null || hover === i ? 1 : 0.45} />;
              })}
            </g>
          );
        })}
      </svg>
      {hover !== null && (
        <div className="tip" style={{ left: Math.min(w - 190, Math.max(L, L + gw * hover + gw / 2 - 80)), top: 0 }}>
          <b>{groups[hover]}</b>
          {series.map((s) => <div key={s.key}><span style={{ color: s.color }}>■</span> {s.label}: {s.values[hover] === null ? "n/a" : fmt(s.values[hover] as number)}</div>)}
        </div>
      )}
    </div>
  );
}

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return <div className="legend">{items.map((i) => <span key={i.label}><i style={{ background: i.color }} />{i.label}</span>)}</div>;
}

/* ---------- one metric across companies (direct labels, entity colours) ---------- */
export function HBars({ rows, fmt }: { rows: { label: string; color: string; value: number | null }[]; fmt: (n: number) => string }): ReactNode {
  const max = Math.max(...rows.map((r) => Math.abs(r.value ?? 0)), 1e-9);
  return (
    <div style={{ padding: "8px 0 14px" }}>
      {rows.map((r) => (
        <div className="hbar" key={r.label}>
          <strong style={{ color: "var(--ink)" }}>{r.label}</strong>
          <div className="hbar-track">{r.value !== null && <div className="hbar-fill" style={{ width: `${(Math.max(r.value, 0) / max) * 100}%`, background: r.color }} />}</div>
          <span className="num" style={{ textAlign: "right", color: "var(--ink)", fontWeight: 600 }}>{r.value === null ? "—" : fmt(r.value)}</span>
        </div>
      ))}
    </div>
  );
}
