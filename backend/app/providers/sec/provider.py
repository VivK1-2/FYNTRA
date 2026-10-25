from datetime import date
from typing import Any, Dict, List, Optional

from app.models.company import Company
from app.providers.base import CompanyProvider
from app.providers.sec.client import SECClient

ANNUAL_FORMS = ("10-K", "10-K/A", "10-KT")

# Tags tried in order of preference (companies use different us-gaap tags for the same concept).
TAGS = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss"],
    "total_assets": ["Assets"],
    "total_liabilities": ["Liabilities"],
    "total_equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "cash_and_equivalents": ["CashAndCashEquivalentsAtCarryingValue", "Cash"],
    "total_debt": ["DebtAndCapitalLeaseObligations", "LongTermDebtAndCapitalLeaseObligations", "LongTermDebt"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "capital_expenditure": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
}


def archive_url(cik: str, accession: str, document: str) -> str:
    """Official SEC archive URL: /Archives/edgar/data/{cik}/{accession without dashes}/{document}."""
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{document}"


def _days(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


class SECProvider(CompanyProvider):
    def __init__(self):
        self.client = SECClient()

    async def resolve_company(self, identifier: str) -> Optional[Company]:
        identifier = identifier.upper().strip()
        tickers_data = await self.client.get_company_tickers()

        target_cik = None
        for data in tickers_data.values():
            if data.get("ticker") == identifier:
                target_cik = str(data.get("cik_str"))
                break
        if not target_cik and identifier.isdigit():
            target_cik = identifier
        if not target_cik:
            return None

        try:
            submissions = await self.client.get_company_submissions(target_cik)
        except Exception:  # noqa: BLE001
            return None

        tickers_list = submissions.get("tickers", [])
        exchanges = submissions.get("exchanges") or [None]
        return Company(
            name=submissions.get("name"),
            ticker=tickers_list[0] if tickers_list else identifier,
            exchange=exchanges[0],
            country="USA",
            currency="USD",
            sec_cik=target_cik,
        )

    async def find_filings(self, company: Company, form: str = "10-K", limit: int = 5) -> List[Dict[str, Any]]:
        """Annual-report discovery from the SEC submissions feed (newest first)."""
        if not company.sec_cik:
            return []
        sub = await self.client.get_company_submissions(company.sec_cik)
        recent = (sub.get("filings") or {}).get("recent") or {}
        forms = recent.get("form", [])
        wanted = ANNUAL_FORMS if form == "10-K" else (form,)
        out: List[Dict[str, Any]] = []
        for i, f in enumerate(forms):
            if f not in wanted:
                continue
            accession = recent["accessionNumber"][i]
            doc = recent["primaryDocument"][i]
            out.append(
                {
                    "provider": "sec",
                    "form": f,
                    "filing_date": recent["filingDate"][i],
                    "report_date": recent["reportDate"][i] or None,  # fiscal period end
                    "accession_number": accession,
                    "primary_document": doc,
                    "document_url": archive_url(company.sec_cik, accession, doc),
                    "index_url": f"https://www.sec.gov/Archives/edgar/data/{int(company.sec_cik)}/"
                    f"{accession.replace('-', '')}/",
                }
            )
            if len(out) >= limit:
                break
        return out

    def _extract_fact(
        self, facts: Dict[str, Any], tags: List[str], fy: int, flow: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Pick the value for fiscal year `fy` from XBRL company facts.

        A 10-K also carries prior-year comparatives tagged with the same `fy`, so we select the
        entry with the LATEST period end, and for income/cash-flow items require a ~12 month duration.
        """
        us_gaap = facts.get("us-gaap", {})
        for tag in tags:
            usd = (us_gaap.get(tag, {}).get("units", {}) or {}).get("USD", [])
            candidates = []
            for f in usd:
                if f.get("fy") != fy or f.get("fp") != "FY" or f.get("form") not in ANNUAL_FORMS:
                    continue
                if flow:
                    if not f.get("start") or not f.get("end"):
                        continue
                    if not 350 <= _days(f["start"], f["end"]) <= 380:
                        continue
                candidates.append(f)
            if not candidates:
                continue
            best = max(candidates, key=lambda f: (f["end"], f.get("filed", "")))
            return {
                "metric": tag,
                "value": best.get("val"),
                "currency": "USD",
                "unit": "USD",
                "period": f"FY{fy}",
                "statement_type": "consolidated",
                "value_type": "reported",
                "source": {
                    "provider": "SEC",
                    "document_id": best.get("accn"),
                    "xbrl_tag": f"us-gaap:{tag}",
                },
            }
        return None

    async def get_structured_data(self, company: Company, fy: int = 2023) -> Dict[str, Any]:
        if not company.sec_cik:
            return {}
        facts = (await self.client.get_company_facts(company.sec_cik)).get("facts", {})

        def flow(key: str):
            return self._extract_fact(facts, TAGS[key], fy, flow=True)

        def instant(key: str):
            return self._extract_fact(facts, TAGS[key], fy, flow=False)

        return {
            "income_statement": {
                "revenue": flow("revenue"),
                "cost_of_revenue": flow("cost_of_revenue"),
                "gross_profit": flow("gross_profit"),
                "operating_income": flow("operating_income"),
                "net_income": flow("net_income"),
            },
            "balance_sheet": {
                "total_assets": instant("total_assets"),
                "total_liabilities": instant("total_liabilities"),
                "total_equity": instant("total_equity"),
                "cash_and_equivalents": instant("cash_and_equivalents"),
                "total_debt": instant("total_debt"),
            },
            "cash_flow": {
                "operating_cash_flow": flow("operating_cash_flow"),
                "capital_expenditure": flow("capital_expenditure"),
            },
        }
