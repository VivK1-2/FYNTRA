import re

import httpx
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from app.models.company import Company
from app.providers.base import CompanyProvider
from app.providers.india.nse.client import NSEClient
from app.services.documents.downloader import DownloadError, validate_url

_URL_KEYS = ("fileName", "filename", "fileUrl", "file_url", "url", "attachment", "link")
_YEAR = re.compile(r"(?<!\d)(20\d{2})(?!\d)")


def _row_url(row: Dict[str, Any]) -> Optional[str]:
    for k in _URL_KEYS:
        v = row.get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v
    return None


def _row_years(row: Dict[str, Any], url: str) -> Optional[int]:
    """Fiscal year END (e.g. 2024 for FY 2023-24)."""
    to = str(row.get("toYr") or row.get("to_year") or "")
    if to.isdigit():
        return int(to)
    found = [int(y) for y in _YEAR.findall(url)]
    return max(found) if found else None


class NSEProvider(CompanyProvider):
    """
    Company resolution + annual report discovery from NSE. Not verified against the live NSE API yet.
    Retrieval order per the blueprint: NSE -> BSE -> company IR page.
    """

    def __init__(self):
        self.client = NSEClient()

    async def resolve_company(self, identifier: str) -> Optional[Company]:
        identifier = identifier.upper().strip()
        data = await self.client.search_company(identifier)
        rows = data.get("symbols", []) if isinstance(data, dict) else []
        for result in rows:
            if str(result.get("symbol", "")).upper() == identifier:
                name = result.get("companyName") or result.get("symbol_info") or result.get("name") or identifier
                return Company(name=name, ticker=identifier, exchange="NSE", country="India", currency="INR")
        return await self._resolve_via_yahoo(identifier)

    async def _resolve_via_yahoo(self, symbol: str) -> Optional[Company]:
        """If NSE's own search is unreachable, an NSE listing still shows up on Yahoo as SYMBOL.NS."""
        if not re.fullmatch(r"[A-Z0-9&-]{1,20}", symbol):
            return None
        from app.providers.market import yahoo

        try:
            async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
                m = await yahoo.fetch(client, f"{symbol}.NS", "1mo")
        except yahoo.MarketUnavailable:
            return None
        q = m["quote"]
        if q.get("currency") != "INR":
            return None
        return Company(name=q.get("name") or symbol, ticker=symbol, exchange="NSE", country="India", currency="INR")

    async def find_filings(self, company: Company, form: str = "10-K", limit: int = 5) -> List[Dict[str, Any]]:
        """Annual reports listed on NSE, newest first. Only https links on official hosts are returned."""
        symbol = (company.ticker or "").upper()
        payload = await self.client.get_annual_reports(symbol)
        rows = payload.get("data") if isinstance(payload, dict) else payload
        out: List[Dict[str, Any]] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            url = _row_url(row)
            if not url:
                continue
            try:
                validate_url(url)
            except DownloadError:
                continue
            end = _row_years(row, url)
            label = f"FY {end - 1}-{str(end)[2:]}" if end else "Annual report"
            out.append(
                {
                    "provider": "nse",
                    "form": "Annual report",
                    "filing_date": None,
                    "report_date": None,
                    "fiscal_year": end,
                    "fiscal_label": label,
                    "accession_number": f"NSE-{symbol}-{end or len(out)}",
                    "primary_document": urlparse(url).path.rsplit("/", 1)[-1],
                    "document_url": url,
                    "index_url": f"https://www.nseindia.com/companies-listing/corporate-filings-annual-reports?symbol={symbol}",
                }
            )
        out.sort(key=lambda f: f["fiscal_year"] or 0, reverse=True)
        return out[:limit]

    async def find_xbrl_filings(self, company: Company, limit: int = 12) -> List[Dict[str, Any]]:
        """Results filings that carry an XBRL file. Row field names are matched loosely (not verified live)."""
        symbol = (company.ticker or "").upper()
        out: List[Dict[str, Any]] = []
        seen = set()
        for period in ("Annual", "Quarterly"):
            payload = await self.client.get_financial_results(symbol, period)
            rows = payload.get("data") if isinstance(payload, dict) else payload
            for row in rows or []:
                if not isinstance(row, dict):
                    continue
                url = next((v for v in row.values() if isinstance(v, str) and v.startswith("http") and v.lower().endswith(".xml")), None)
                if not url or url in seen:
                    continue
                try:
                    validate_url(url)
                except DownloadError:
                    continue
                seen.add(url)
                to = str(row.get("toDate") or row.get("to_date") or row.get("qe_Date") or "")
                out.append({
                    "period": period,
                    "period_end": to or None,
                    "audited": str(row.get("audited") or row.get("auditedUnAudited") or "") or None,
                    "consolidated": str(row.get("consolidated") or row.get("consolidatedNonConsolidated") or "") or None,
                    "filing_date": str(row.get("broadcastDate") or row.get("filingDate") or "") or None,
                    "url": url,
                })
        return out[:limit]

    async def get_structured_data(self, company: Company, fy: int = 2023) -> Dict[str, Any]:
        return {}
