# FYNTRA Backend

**FYNTRA = Financial Year Narratives, Tables, Ratios & Answers**

**The Filing-to-Insight Engine for Smarter Investing.**
A read-only research API that finds official annual reports for public companies, extracts and indexes their text with page references, computes financial metrics in code, and lets a language model explain the evidence with citations that are verified in code.

> **Design principle:** sources provide facts, Python computes metrics, retrieval selects evidence, the AI explains that evidence, and the interface shows where every answer came from. An AI model is never the source of a number.

FYNTRA is a research and educational tool. It does not trade, connect to brokers, predict prices or give investment advice.

---

## Contents
1. [Project status](#project-status)
2. [Architecture](#architecture)
3. [Quick start (local)](#quick-start-local)
4. [Configuration](#configuration)
5. [API reference](#api-reference)
6. [LLM gateway](#llm-gateway)
7. [Document pipeline](#document-pipeline)
8. [Testing and evaluation](#testing)
9. [Deployment (VPS)](#deployment-vps)
10. [Security notes](#security-notes)
11. [Known limitations](#known-limitations)
12. [Project layout](#project-layout)

---

## Project status

| Area | Status | Notes |
|---|---|---|
| Company resolver (US via SEC, India via NSE) | Working | NSE access uses a cookie session with a Yahoo `.NS` fallback; it is not an official API |
| SEC 10-K discovery and NSE annual-report discovery | Working | Official archive URLs |
| SEC XBRL financials and ratios | Working | Correct fiscal year and period length; each ratio records its formula |
| Document pipeline (download, extract, chunk, index, search) | Working | PostgreSQL full-text search; text PDFs and HTML |
| Cited question answering (`/ask`, `/compare/ask`) | Working | Three checks in code: quote, sentence, number |
| XBRL fact explorer (SEC inline XBRL and NSE XBRL) | Working | CSV export |
| Market data (Yahoo, Stooq fallback) | Working | 90 s cache |
| LLM gateway | Working | One model plus an optional fallback, set only in `.env` |
| Rate limits, admin endpoints, question log | Working | In-memory limits, single process |
| Evaluation kit (31 questions) | Working | `scripts/eval_qa.py` |
| VPS deployment files | Provided | Not validated on a live server |
| Statements and ratios for Indian companies | Not built | XBRL facts are available |
| OCR for scanned reports, job queue, usage budgets | Not built | Scanned PDFs are flagged `needs_ocr` |

## Architecture

A modular monolith: one codebase, clear layers, deployable on a single VPS.

```
Frontend (server side, holds the API key)
        |
        v
Caddy (HTTPS)  ->  FastAPI API  ->  PostgreSQL (data + full-text search)
                      |   \
                      |    +-> LLM gateway -> model provider(s)
                      v
              Filing providers  ->  SEC EDGAR (US)
                                    NSE / BSE / company IR (India, planned)
                      |
                      v
        Document pipeline (download -> extract -> chunk -> index)
                      |
                      v
              Local volume (original filings)
```

Layers, from the outside in:

1. **API** (`app/api`): validation, authentication, response shaping. No business logic.
2. **Services** (`app/services`): use cases such as company resolution, document ingestion and ratio calculation.
3. **Providers** (`app/providers`): one adapter per data source behind a common interface, so a source can be replaced or disabled without touching the rest.
4. **LLM gateway** (`app/llm`): the only code that talks to model providers.
5. **Data** (`app/models`, `app/db`, `alembic`): SQLAlchemy models and migrations.

## Quick start (local)

Requirements: Python 3.12, Docker (for PostgreSQL).

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` (the example is already set up for local development): paste your `LLM_API_KEY`, choose `LLM_MODEL`, and put your real email in `SEC_USER_AGENT`. Keep `API_KEY` equal to `FYNTRA_API_KEY` in the frontend `.env`.

Check the model settings before starting the server: `python scripts/check_llm.py`.

Then start the database, apply migrations and run the server:

```bash
docker compose up -d db
alembic upgrade head
uvicorn app.main:app --reload
```

Interactive API docs: <http://127.0.0.1:8000/docs>

Try it:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/v1/company/AAPL
curl http://127.0.0.1:8000/api/v1/company/AAPL/filings
curl "http://127.0.0.1:8000/api/v1/company/AAPL/financials/complete?fy=2023"
```

## Configuration

All settings come from environment variables or the `.env` file. Never commit `.env`.

| Variable | Default | Purpose |
|---|---|---|
| `ENVIRONMENT` | `development` | `production` enables startup safety checks and hides `/docs` |
| `DATABASE_URL` | local PostgreSQL | `postgresql+asyncpg://user:pass@host:5432/dbname` |
| `API_KEY` | insecure default | Sent by clients in the `X-API-Key` header. Use `disabled` only for local development |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed frontend origins. No `*` in production |
| `SEC_USER_AGENT` | placeholder | Must include a real contact email; the SEC blocks anonymous clients |
| `ADMIN_KEY` | empty (admin off) | Key typed into the Admin page (`X-Admin-Key` header). Generate with `openssl rand -hex 24`. Wrong guesses are throttled |
| `LLM_BASE_URL` | `https://api.scalemax.pro/token/v1` | OpenAI-compatible endpoint (`/chat/completions` is added automatically) |
| `LLM_API_KEY` | none | Your model provider key |
| `LLM_MODEL` | `gpt-6-luna` | The model used for answers. Set only here, in the backend |
| `LLM_FALLBACK_MODEL` | empty | Optional second model on the same endpoint, tried only if the first fails |
| `LLM_TIMEOUT_SECONDS` | `60` | Per-request model timeout |
| `STORAGE_DIR` | `/data/filings` | Where original filings are saved. Use a writable path locally |

Production-only variables used by `docker-compose.prod.yml`: `API_DOMAIN`, `POSTGRES_PASSWORD`.

In production the app refuses to start if `API_KEY` is weak or disabled, CORS contains `*`, or the SEC contact email is still a placeholder.

## API reference

**New migration:** run `alembic upgrade head` after updating (adds the `ask_logs` table).

### Admin and XBRL endpoints
- `GET /api/v1/company/{id}/filings/status`: status of every downloaded filing in one call.
- `GET /api/v1/company/{id}/filings/{accession}/xbrl?q=&dimensional=&limit=&offset=`: every tagged figure in a downloaded SEC filing (inline XBRL), with period, unit and breakdowns. Needs the filing to be made searchable first.
- `/api/v1/admin/*` (needs `X-Admin-Key`): `overview`, `filings`, `filings/{id}/reingest`, `DELETE filings/{id}`, `asks`, `cache/clear`.

- `GET /api/v1/company/{id}/xbrl-filings` and `GET .../xbrl-facts?url=`: NSE results filings with XBRL for Indian companies (the file is downloaded from NSE hosts only).

- `POST /api/v1/compare/ask`: the same question put to 2-3 companies; each answer is verified and cited separately (`accessions` can pin a report per ticker).

### Accuracy evaluation
`eval/questions.json` holds 31 questions (figure lookups, narrative questions, questions the reports cannot answer, and cross-company comparisons) with expected answers. With the backend running:

    python scripts/eval_qa.py --prepare     # first time: downloads and indexes the three reports
    python scripts/eval_qa.py               # later runs

It prints PASS/FAIL per question and writes `eval/results/<time>.md` with answer accuracy, correct "not found" rate, citation and page-number rates and average time. The expected figures were prepared from public filings; confirm a figure against the filing before treating a FAIL as a wrong answer. See [`docs/EVALUATION.md`](../docs/EVALUATION.md) for the method.

Base path: `/api/v1`. Every endpoint except `GET /health` requires the `X-API-Key` header unless `API_KEY=disabled`. Errors use one shape: `{"success": false, "error": {"code": "...", "message": "..."}}`.

| Method and path | Description |
|---|---|
| `GET /health` | Liveness and database check (no key needed) |
| `GET /company/{identifier}` | Resolve a ticker or CIK to a company; saved for reuse |
| `GET /company/{identifier}/filings?limit=5` | Latest 10-K filings with official SEC links |
| `GET /company/{identifier}/financials/complete?fy=2023` | Income statement, balance sheet, cash flow and ratios, each value with its source tag |
| `POST /company/{identifier}/filings/{accession}/ingest` | Start downloading, parsing and indexing a filing (returns `202`; reuses an already processed filing) |
| `GET /company/{identifier}/filings/{accession}/status` | Ingestion status, page count, chunk count and errors |
| `GET /company/{identifier}/search?q=...&accession=...&limit=8` | Matching passages with page, section and source link |

Ingestion status values: `pending`, `processing`, `processed`, `failed`, `needs_ocr`.

Error codes you may see: `COMPANY_NOT_FOUND` (404), `FILING_NOT_FOUND` (404), `FINANCIAL_DATA_UNAVAILABLE` (404), `NOT_SUPPORTED` (501, for features not built yet such as Indian filings).

## LLM gateway

`app/llm/gateway.py` is the single place that calls the language model. The model name, endpoint and key live only in the backend `.env` (`LLM_MODEL`, `LLM_BASE_URL`, `LLM_API_KEY`); the web app never sees or sets them.

- Calls the OpenAI-style `/chat/completions` endpoint.
- Retries with backoff on rate limits, server errors and timeouts. A bad key, unknown model or spend limit is not retried; the optional `LLM_FALLBACK_MODEL` is tried next.
- JSON mode validates the reply and asks the model once to correct invalid JSON.
- The model that answered is stored with each question in `ask_logs` (database only) for audit.
- Real provider errors are written to the backend log and shown by `python scripts/check_llm.py`; users only see a short, generic message.

To change the model, edit `LLM_MODEL` in `.env` and restart the backend.

## Document pipeline

Flow for one filing: **download, extract, chunk, index, search.**

- **Download** (`downloader.py`): HTTPS only, hosts limited to sec.gov, nseindia.com and bseindia.com, redirects re-checked, 120 MB cap, content must really be a PDF or HTML page, atomic save with a SHA-256 hash.
- **Extract** (`extractor.py`): PDFs use PyMuPDF with real page numbers. HTML (SEC filings) is split on explicit page breaks; without them the filing is marked as having no page numbers so citations refer to sections instead of invented pages. PDFs with almost no text are flagged `needs_ocr`.
- **Chunk** (`chunker.py`): about 3,200 characters per chunk with a small overlap. Headings such as "Item 1A. Risk Factors" start a new chunk, and each chunk keeps its page range and section.
- **Index and search** (`search.py`): PostgreSQL full-text search (GIN index) matches any meaningful word and ranks passages with more matches higher. SQLite (used in tests) falls back to simple scoring.
- **Orchestration** (`ingest.py`): runs as a background task, is idempotent, skips filings already processed, retries filings stuck for more than 15 minutes, and records failures instead of crashing.

## Testing

```bash
pytest
```

Tests run offline (94 tests, one needs PostgreSQL): external services are mocked, the database is in-memory SQLite, and PDFs and HTML pages are generated on the fly. They cover SEC fact selection, filing discovery, authentication, the LLM gateway (fallback, retries, JSON repair, both formats), download safety, extraction, chunking and an end-to-end ingest and search.

One test uses a real PostgreSQL database and is skipped unless you provide one that has had migrations applied:

```bash
TEST_PG_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/fyntra pytest tests/test_documents.py
```

## Deployment (VPS)

The production stack is in `docker-compose.prod.yml`: Caddy (automatic HTTPS), the API and PostgreSQL. Only ports 80 and 443 are public. Database migrations run automatically when the API container starts.

```bash
cp deploy/.env.production.example .env && chmod 600 .env    # then fill in real values
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

Full step-by-step instructions (server hardening, Docker, DNS, verification, backups, troubleshooting) are in [`deploy/VPS_SETUP.md`](deploy/VPS_SETUP.md).

## Security notes

- Keep every secret in `.env` or a secret manager. Never put keys in frontend code, screenshots, chat or Git.
- The frontend should call this API from its **server side** and hold the API key there. A key placed in browser code is public.
- Filing text is untrusted input. The model treats it only as evidence, and only quoted, verified sentences ever reach the user.
- Downloads are restricted to allowlisted hosts and validated before saving.
- Rate limits are in memory per client IP. Put the API behind the provided Caddy proxy before exposing it.

## Known limitations

- Retrieval is keyword-based; a question using none of the report's words can miss the right passage.
- Scanned PDFs cannot be read until OCR is added. Tables inside PDFs are not extracted.
- Statements and ratios come from SEC XBRL data, so they cover US companies. XBRL tags differ between companies, so some values can be missing.
- The NSE interface is not an official API and may change or block server IPs; the Yahoo and Stooq feeds are unofficial.
- Background jobs run inside the API process; a restart interrupts them (stale jobs are retried automatically).
- The 31-question evaluation set is small and is a check of behaviour, not a statistical benchmark.

## Project layout

```
app/
  api/v1/            routers and endpoints (company, financials, documents, ask, xbrl, market, compare, admin, health)
  core/              settings, errors, HTTP client, storage helper
  db/                database session and base model
  llm/               LLM gateway
  models/            SQLAlchemy models (companies, filings, document chunks)
  providers/         data sources (sec/, india/nse/) behind a common interface
  schemas/           Pydantic response models
  services/          company service, ratio calculator, document pipeline
alembic/             database migrations
deploy/              Caddyfile and VPS setup guide
tests/               offline test suite (94 tests)
eval/                31-question evaluation set
scripts/             check_llm.py (model check) and eval_qa.py (accuracy run)
docker-compose.yml        local PostgreSQL
docker-compose.prod.yml   production stack for a VPS
```

## Cited Q&A: `POST /api/v1/company/{id}/ask`

Body: `{"question": "...", "accession": "optional filing"}`.
Retrieves the best passages from ingested reports, asks the model for a JSON answer with `[n]` citations, then
verifies in code: each citation's quote must appear verbatim in its passage, each sentence needs a verified
citation, and every number must appear in the cited passage. Failing sentences are dropped; if none survive the
response is `status: "insufficient_evidence"`. With no matching passages the model is not called at all.

## More endpoints

| Endpoint | What it does |
|---|---|
| `GET /api/v1/company/{id}/market?range=1mo\|3mo\|6mo\|1y\|5y` | Quote + price history. Yahoo first; Stooq fallback for US tickers. Indian tickers use the NSE listing (`SYMBOL.NS`). |
| `GET /api/v1/company/{id}/financials/trend?from_fy=2020&to_fy=2024` | Key numbers per fiscal year (years without data are skipped). |
| `GET /api/v1/compare?tickers=AAPL,MSFT&fy=2024` | 2-4 US companies side by side; one failing company does not fail the rest. |
| `GET /api/v1/company/{id}/filings` | 10-K (US) or NSE annual reports (India). Indian reports ingest and search like SEC filings. |

Rate limiting: `RATE_LIMIT_PER_MINUTE` and the stricter `RATE_LIMIT_LLM_PER_MINUTE` (for `/ask` and `/ingest`)
return HTTP 429 with a `Retry-After` header. In-memory, per client IP, single process.

Not verified live: the Yahoo/Stooq responses and the NSE annual-reports response were built from the providers'
documented/known formats and tested with mocks. Check them first on your machine.
