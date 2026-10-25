"""Shared financial-statement building used by the single-year, trend and compare endpoints."""
from typing import Any, Dict, Optional

from app.core.exceptions import FinancialDataUnavailableError, NotSupportedError
from app.models.company import Company
from app.providers.sec.provider import SECProvider
from app.schemas.financials import (
    BalanceSheet, CashFlow, CompleteFinancialResponse, FinancialFact, FinancialRatios, IncomeStatement,
    SourceProvenance,
)
from app.services.ratios import RatioCalculator


async def build_financials(company: Company, fy: int) -> CompleteFinancialResponse:
    if company.country != "USA":
        raise NotSupportedError("Structured financials for Indian companies are not implemented yet.")
    data = await SECProvider().get_structured_data(company, fy=fy)
    if not data or not any(v for section in data.values() for v in section.values()):
        raise FinancialDataUnavailableError(detail=f"No financial data found for FY{fy}.")
    inc = IncomeStatement(**data.get("income_statement", {}))
    bal = BalanceSheet(**data.get("balance_sheet", {}))
    ratios = RatioCalculator().calculate(f"FY{fy}", inc, bal)
    cf = CashFlow(**data.get("cash_flow", {}))
    ocf, capex = cf.operating_cash_flow, cf.capital_expenditure
    if cf.free_cash_flow is None and ocf and ocf.value is not None and capex and capex.value is not None:
        cf.free_cash_flow = FinancialFact(
            metric="Free cash flow", value=ocf.value - abs(capex.value), currency=ocf.currency, unit=ocf.unit,
            period=ocf.period, value_type="calculated",
            source=SourceProvenance(provider="FYNTRA", xbrl_tag="Formula: operating cash flow - capital expenditure"),
        )
    return CompleteFinancialResponse(
        company_id=company.id, ticker=company.ticker, filing_type="10-K", period=f"FY{fy}",
        income_statement=inc, balance_sheet=bal, cash_flow=cf,
        ratios=FinancialRatios(**ratios), validation_status="success",
    )


def _v(fact: Any) -> Optional[float]:
    return fact.value if fact is not None else None


def flatten(r: CompleteFinancialResponse) -> Dict[str, Optional[float]]:
    """Plain numbers for charts and comparison tables (ratios are fractions, e.g. 0.24 = 24%)."""
    rat = r.ratios
    return {
        "revenue": _v(r.income_statement.revenue),
        "gross_profit": _v(r.income_statement.gross_profit),
        "operating_income": _v(r.income_statement.operating_income),
        "net_income": _v(r.income_statement.net_income),
        "eps": _v(r.income_statement.basic_eps),
        "total_assets": _v(r.balance_sheet.total_assets),
        "total_equity": _v(r.balance_sheet.total_equity),
        "cash": _v(r.balance_sheet.cash_and_equivalents),
        "operating_cash_flow": _v(r.cash_flow.operating_cash_flow),
        "free_cash_flow": _v(r.cash_flow.free_cash_flow),
        "gross_margin": _v(rat.gross_margin) if rat else None,
        "operating_margin": _v(rat.operating_margin) if rat else None,
        "net_margin": _v(rat.net_margin) if rat else None,
        "roa": _v(rat.roa) if rat else None,
        "roe": _v(rat.roe) if rat else None,
    }
