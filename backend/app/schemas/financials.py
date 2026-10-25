from pydantic import BaseModel
from typing import Optional

class SourceProvenance(BaseModel):
    provider: str
    document_id: Optional[str] = None
    document_url: Optional[str] = None
    page: Optional[int] = None
    xbrl_tag: Optional[str] = None

class FinancialFact(BaseModel):
    metric: str
    value: Optional[float]
    currency: Optional[str]
    unit: Optional[str]
    period: str
    statement_type: str = "consolidated"
    value_type: str = "reported" # reported, calculated, ai_extracted
    source: SourceProvenance

class IncomeStatement(BaseModel):
    revenue: Optional[FinancialFact] = None
    cost_of_revenue: Optional[FinancialFact] = None
    gross_profit: Optional[FinancialFact] = None
    operating_expenses: Optional[FinancialFact] = None
    operating_income: Optional[FinancialFact] = None
    net_income: Optional[FinancialFact] = None
    basic_eps: Optional[FinancialFact] = None

class BalanceSheet(BaseModel):
    cash_and_equivalents: Optional[FinancialFact] = None
    total_assets: Optional[FinancialFact] = None
    total_liabilities: Optional[FinancialFact] = None
    total_equity: Optional[FinancialFact] = None
    total_debt: Optional[FinancialFact] = None

class CashFlow(BaseModel):
    operating_cash_flow: Optional[FinancialFact] = None
    capital_expenditure: Optional[FinancialFact] = None
    free_cash_flow: Optional[FinancialFact] = None

class FinancialRatios(BaseModel):
    gross_margin: Optional[FinancialFact] = None
    operating_margin: Optional[FinancialFact] = None
    net_margin: Optional[FinancialFact] = None
    roa: Optional[FinancialFact] = None
    roe: Optional[FinancialFact] = None

class CompleteFinancialResponse(BaseModel):
    company_id: int
    ticker: str
    filing_type: str
    period: str
    income_statement: IncomeStatement
    balance_sheet: BalanceSheet
    cash_flow: CashFlow
    ratios: Optional[FinancialRatios] = None
    validation_status: str = "success"
