import { FormEvent, ReactNode, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "./api";

export function Logo() {
  return (
    <span className="brand-mark" aria-hidden>
      <svg width="13" height="13" viewBox="0 0 14 14"><path d="M1 13V1h12v3.4H4.6v2h6v3.3h-6V13z" fill="#fff" /></svg>
    </span>
  );
}

export function Arrow() {
  return <svg className="arrow" width="10" height="10" viewBox="0 0 10 10" aria-hidden><path d="M2 1l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

export function SearchBox({ initial = "", autoFocus = false, placeholder = "Search a ticker, e.g. AAPL or RELIANCE", button = true, className = "hero-search" }:
  { initial?: string; autoFocus?: boolean; placeholder?: string; button?: boolean; className?: string }) {
  const [v, setV] = useState(initial);
  const nav = useNavigate();
  const go = (e: FormEvent) => {
    e.preventDefault();
    const id = v.trim();
    if (id) nav(`/company/${encodeURIComponent(id)}`);
  };
  return (
    <form onSubmit={go} role="search" className={className}>
      <input className="input" value={v} onChange={(e) => setV(e.target.value)} placeholder={placeholder}
        aria-label="Company ticker or name" autoFocus={autoFocus} autoCapitalize="characters" spellCheck={false} />
      {button && <button className="btn lg" type="submit">Search <Arrow /></button>}
    </form>
  );
}

export function Notice({ kind, children }: { kind: "err" | "warn" | "info"; children: ReactNode }) {
  return <div className={`notice ${kind}`} role={kind === "err" ? "alert" : "status"}>{children}</div>;
}

export function ErrorNotice({ error }: { error: ApiError }) {
  const unsupported = error.status === 501;
  return (
    <Notice kind={unsupported ? "info" : "err"}>
      <div><strong>{unsupported ? "Not available for this company" : "Something went wrong"}</strong>{error.message}</div>
    </Notice>
  );
}

export function Skeleton({ h = 20, w = "100%" }: { h?: number; w?: number | string }) {
  return <div className="skeleton" style={{ height: h, width: w }} />;
}

export function Spinner({ dark }: { dark?: boolean }) {
  return <span className={`spinner${dark ? " dark" : ""}`} aria-hidden />;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="empty"><h3>{title}</h3><div>{children}</div></div>;
}

export function Star({ on, toggle, label }: { on: boolean; toggle: () => void; label: string }) {
  return (
    <button className="star" aria-pressed={on} aria-label={on ? `Remove ${label} from watchlist` : `Add ${label} to watchlist`} title={on ? "On your watchlist" : "Add to watchlist"} onClick={toggle}>
      <svg width="20" height="20" viewBox="0 0 24 24" fill={on ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"><path d="M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1 5.9L12 16.9 6.8 19.7l1-5.9L3.5 9.7l5.9-.8z" /></svg>
    </button>
  );
}
