// All calls go to same-origin /api/*; the dev/preview server adds the X-API-Key header.

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

const ADMIN_KEY = "fyntra.admin";
export const adminKey = {
  get: () => { try { return sessionStorage.getItem(ADMIN_KEY) ?? ""; } catch { return ""; } },
  set: (v: string) => { try { sessionStorage.setItem(ADMIN_KEY, v); } catch { /* ignore */ } },
  clear: () => { try { sessionStorage.removeItem(ADMIN_KEY); } catch { /* ignore */ } },
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError(0, "NETWORK", "Can't reach the backend. Check that it is running on port 8000.");
  }
  if (!res.ok) {
    let code = "ERROR";
    let message = `Request failed (${res.status}).`;
    try {
      const body = await res.json();
      if (body?.error) {
        code = body.error.code ?? code;
        message = body.error.message ?? message;
      } else if (typeof body?.detail === "string") {
        message = body.detail;
      } else if (Array.isArray(body?.detail)) {
        message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
      }
    } catch {
      /* non-JSON error body */
    }
    if (res.status === 429) message = message || "Too many requests. Wait a moment and try again.";
    if (res.status === 403) message = "The backend rejected the API key. Make sure FYNTRA_API_KEY in the frontend .env matches the backend's API_KEY, then restart the frontend.";
    throw new ApiError(res.status, code, message);
  }
  return res.json() as Promise<T>;
}

const enc = encodeURIComponent;

export interface Company {
  id: number; name: string; ticker?: string | null; exchange?: string | null;
  country?: string | null; currency?: string | null; isin?: string | null; sec_cik?: string | null;
}
export interface Filing {
  provider: string; form: string; filing_date?: string | null; report_date?: string | null;
  accession_number: string; primary_document: string; document_url: string; index_url: string;
  fiscal_label?: string | null;
}
export interface Fact {
  metric: string; value: number | null; currency: string | null; unit: string | null; period: string;
  value_type: string;
  source: { provider: string; document_url?: string | null; page?: number | null; xbrl_tag?: string | null };
}
type Section<K extends string> = Partial<Record<K, Fact | null>>;
export interface Financials {
  ticker: string; period: string; filing_type: string; validation_status: string;
  income_statement: Section<"revenue" | "cost_of_revenue" | "gross_profit" | "operating_expenses" | "operating_income" | "net_income" | "basic_eps">;
  balance_sheet: Section<"cash_and_equivalents" | "total_assets" | "total_liabilities" | "total_equity" | "total_debt">;
  cash_flow: Section<"operating_cash_flow" | "capital_expenditure" | "free_cash_flow">;
  ratios: Section<"gross_margin" | "operating_margin" | "net_margin" | "roa" | "roe"> | null;
}
export interface IngestStatus {
  accession_number: string; status: string; page_count?: number | null; chunk_count: number;
  has_page_numbers: boolean; needs_ocr: boolean; error?: string | null; document_url?: string | null;
}
export interface SearchHit {
  chunk_id: number; accession_number?: string | null; form: string; filing_date?: string | null;
  document_url?: string | null; page_start?: number | null; page_end?: number | null;
  section?: string | null; text: string; score: number;
}
export interface Citation {
  n: number; quote: string; accession_number?: string | null; form: string; filing_date?: string | null;
  page_start?: number | null; page_end?: number | null; section?: string | null; document_url?: string | null; passage: string;
}
export interface AskResult {
  question: string; status: "answered" | "insufficient_evidence"; answer?: string | null; reason?: string | null;
  citations: Citation[]; dropped_sentences: number; passages_considered: number; latency_ms?: number | null;
}
export interface CompareAskResult { question: string; companies: { ticker: string; name?: string | null; result?: AskResult | null; error?: string | null }[] }
export interface Quote {
  symbol: string; name?: string | null; currency?: string | null; exchange?: string | null; price: number;
  previous_close?: number | null; change?: number | null; change_pct?: number | null; day_high?: number | null;
  day_low?: number | null; year_high?: number | null; year_low?: number | null; volume?: number | null; as_of?: string | null;
}
export interface Market { source: string; range: string; quote: Quote; points: { t: string; c: number }[] }
export type Metrics = Record<"revenue" | "gross_profit" | "operating_income" | "net_income" | "eps" | "total_assets" | "total_equity" | "cash" | "operating_cash_flow" | "free_cash_flow" | "gross_margin" | "operating_margin" | "net_margin" | "roa" | "roe", number | null>;
export interface Trend { ticker: string; currency: string; years: ({ fy: number } & Metrics)[] }
export interface Compare { fy: number; companies: { ticker: string; name: string | null; currency: string; metrics: Metrics | null; error: string | null }[] }
export interface XbrlFact {
  concept: string; label: string; value: number; unit: string; decimals?: string | null;
  period_type: string; start?: string | null; end?: string | null; dimensions: string[];
}
export interface XbrlResult {
  accession_number: string; has_xbrl: boolean; document: Record<string, string>;
  total_facts: number; matched: number; offset: number; facts: XbrlFact[];
}
export interface IndiaXbrlFiling { period: string; period_end?: string | null; audited?: string | null; consolidated?: string | null; filing_date?: string | null; url: string }
export interface AdminOverview {
  status: string; database_ok: boolean; version: string; environment: string; uptime_seconds: number;
  counts: { companies: number; filings: number; filings_by_status: Record<string, number>; passages: number; questions: number; questions_24h: number; questions_by_status: Record<string, number> };
  storage_bytes: number; limits: { per_minute: number; llm_per_minute: number };
  caches: { market: number; sec_facts: number; xbrl_documents: number };
}
export interface AdminFiling {
  id: number; ticker?: string | null; company?: string | null; provider: string; form: string; accession_number?: string | null;
  fiscal_year?: number | null; filing_date?: string | null; status: string; error?: string | null; pages?: number | null;
  passages: number; file_bytes?: number | null; updated_at?: string | null;
}
export interface AdminAsk {
  id: number; ticker?: string | null; question: string; status: string; reason?: string | null;
  latency_ms?: number | null; citations: number; dropped_sentences: number; created_at?: string | null;
}
export interface Health { status: string; [k: string]: unknown }

const adminInit = (init: RequestInit = {}): RequestInit => ({ ...init, headers: { ...(init.headers as Record<string, string>), "X-Admin-Key": adminKey.get() } });

export const api = {
  health: () => request<Health>("/health"),
  company: (id: string) => request<Company>(`/api/v1/company/${enc(id)}`),
  filings: (id: string, limit = 8) => request<Filing[]>(`/api/v1/company/${enc(id)}/filings?limit=${limit}`),
  financials: (id: string, fy: number) => request<Financials>(`/api/v1/company/${enc(id)}/financials/complete?fy=${fy}`),
  ingest: (id: string, acc: string) =>
    request<IngestStatus>(`/api/v1/company/${enc(id)}/filings/${enc(acc)}/ingest`, { method: "POST" }),
  ingestStatuses: (id: string) => request<Record<string, IngestStatus>>(`/api/v1/company/${enc(id)}/filings/status`),
  xbrl: (id: string, acc: string, q: string, dimensional: boolean, offset = 0, limit = 200) =>
    request<XbrlResult>(`/api/v1/company/${enc(id)}/filings/${enc(acc)}/xbrl?q=${enc(q)}&dimensional=${dimensional}&offset=${offset}&limit=${limit}`),
  indiaXbrlFilings: (id: string) => request<{ ticker: string; filings: IndiaXbrlFiling[] }>(`/api/v1/company/${enc(id)}/xbrl-filings`),
  indiaXbrl: (id: string, url: string, q: string, dimensional: boolean, offset = 0, limit = 200) =>
    request<XbrlResult>(`/api/v1/company/${enc(id)}/xbrl-facts?url=${enc(url)}&q=${enc(q)}&dimensional=${dimensional}&offset=${offset}&limit=${limit}`),
  admin: {
    overview: () => request<AdminOverview>("/api/v1/admin/overview", adminInit()),
    filings: () => request<AdminFiling[]>("/api/v1/admin/filings", adminInit()),
    reingest: (id: number, redownload: boolean) => request<{ id: number }>(`/api/v1/admin/filings/${id}/reingest?redownload=${redownload}`, adminInit({ method: "POST" })),
    remove: (id: number) => request<{ deleted: number }>(`/api/v1/admin/filings/${id}`, adminInit({ method: "DELETE" })),
    asks: () => request<AdminAsk[]>("/api/v1/admin/asks", adminInit()),
    clearCache: () => request<Record<string, number>>("/api/v1/admin/cache/clear", adminInit({ method: "POST" })),
  },
  ingestStatus: (id: string, acc: string) =>
    request<IngestStatus>(`/api/v1/company/${enc(id)}/filings/${enc(acc)}/status`),
  search: (id: string, q: string, accession?: string) =>
    request<SearchHit[]>(
      `/api/v1/company/${enc(id)}/search?q=${enc(q)}&limit=8${accession ? `&accession=${enc(accession)}` : ""}`,
    ),
  ask: (id: string, question: string, accession?: string) =>
    request<AskResult>(`/api/v1/company/${enc(id)}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, accession: accession || undefined }),
    }),
  askCompare: (tickers: string[], question: string) =>
    request<CompareAskResult>("/api/v1/compare/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tickers, question }),
    }),
  market: (id: string, range: string) => request<Market>(`/api/v1/company/${enc(id)}/market?range=${range}`),
  trend: (id: string, from: number, to: number) =>
    request<Trend>(`/api/v1/company/${enc(id)}/financials/trend?from_fy=${from}&to_fy=${to}`),
  compare: (tickers: string[], fy: number) =>
    request<Compare>(`/api/v1/compare?tickers=${tickers.map(enc).join(",")}&fy=${fy}`),
};
