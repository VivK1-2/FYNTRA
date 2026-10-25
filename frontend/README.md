# FYNTRA frontend

React + Vite + TypeScript, styled after Stripe's design language. Runs locally and talks to the FYNTRA backend.

## Run it (the backend (see ../backend) must already be running on port 8000)

    cd frontend
    npm install
    cp .env.example .env      # set FYNTRA_API_KEY to the SAME value as API_KEY in the backend .env
    npm run dev               # open http://127.0.0.1:5173

Production-style local run: `npm run build && npm run preview`.
Stop with Ctrl+C. Restart after editing `.env`. Needs Node 18+.

## How the API key stays safe
The browser only calls `/api/...` on its own origin. The Vite server (vite.config.ts) forwards those requests to the
backend and adds the `X-API-Key` header from `.env`. The key is never in the JS bundle. `.env` is git-ignored.
Everything binds to 127.0.0.1, so only your computer can reach it.

## Pages
- Home: ticker search, how answers are built, feature overview
- Company: Overview (price chart, key figures, 5-year trends, margins), Financials (CSV export), Annual reports
  (make searchable), Search reports, Ask (cited answers, optional report picker, and "Compare with other companies" to put one question to 2-3 companies). Indian companies show price + annual reports.
- Markets: your watchlist (star any company) with 1-month sparklines, plus recently viewed
- Compare: up to four US companies on one fiscal year, shareable via the URL
- XBRL facts (company tab): every figure tagged in a US 10-K, or in the XBRL file an Indian company filed with NSE with its results; filterable, CSV export
- Admin (`/admin`): sign in with the backend `ADMIN_KEY`; system status, reports (re-read, delete), question log

Watchlist, recent searches and the light/dark theme are stored in this browser only.
