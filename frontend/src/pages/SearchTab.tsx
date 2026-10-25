import { FormEvent, useState } from "react";
import { api, ApiError, SearchHit } from "../api";
import { Empty, ErrorNotice, Spinner } from "../components";
import { date } from "../format";

function highlight(text: string, q: string) {
  const terms = q.toLowerCase().match(/[a-z0-9]{3,}/g) ?? [];
  if (!terms.length) return text;
  const re = new RegExp(`(${terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
  return text.split(re).map((part, i) => (i % 2 ? <mark key={i}>{part}</mark> : part));
}

export default function Search({ id }: { id: string }) {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [asked, setAsked] = useState("");
  const [error, setError] = useState<ApiError | null>(null);

  const run = async (e: FormEvent) => {
    e.preventDefault();
    if (q.trim().length < 2) return;
    setBusy(true); setError(null);
    try { setHits(await api.search(id, q.trim())); setAsked(q.trim()); }
    catch (err) { setError(err as ApiError); setHits(null); }
    finally { setBusy(false); }
  };

  return (
    <>
      <div className="sec-head"><div><h2>Search the reports</h2><p style={{ marginTop: 4 }}>Finds passages in reports you've made searchable. Try “supply chain risks” or “share repurchases”.</p></div></div>
      <form onSubmit={run} style={{ display: "flex", gap: 10, maxWidth: 620 }}>
        <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="What do you want to find?" aria-label="Search query" />
        <button className="btn" type="submit" disabled={busy}>{busy ? <Spinner /> : "Search"}</button>
      </form>
      <div style={{ marginTop: 24 }}>
        {error && <ErrorNotice error={error} />}
        {hits && hits.length === 0 && (
          <Empty title="No matching passages">Nothing matched “{asked}”. If you haven't yet, make a report searchable on the Annual reports tab.</Empty>
        )}
        {hits && hits.length > 0 && (
          <div className="panel" style={{ marginTop: 0 }}>
            {hits.map((h) => (
              <div className="hit" key={h.chunk_id}>
                <div className="where">
                  <strong style={{ color: "var(--ink)" }}>{h.form}{h.filing_date ? ` · ${date(h.filing_date)}` : ""}</strong>
                  {h.section && <span>{h.section.length > 60 ? h.section.slice(0, 60) + "…" : h.section}</span>}
                  {h.page_start != null && <span>Page {h.page_start}{h.page_end && h.page_end !== h.page_start ? `–${h.page_end}` : ""}</span>}
                  {h.document_url && <a href={h.document_url} target="_blank" rel="noreferrer noopener">Source</a>}
                </div>
                <p>{highlight(h.text.length > 900 ? h.text.slice(0, 900) + "…" : h.text, asked)}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
