from typing import Dict, Any, Optional
from app.schemas.financials import IncomeStatement, BalanceSheet, FinancialFact, SourceProvenance

class RatioCalculator:
    
    @staticmethod
    def _create_calculated_fact(metric_name: str, value: float, period: str, formula: str) -> FinancialFact:
        return FinancialFact(
            metric=metric_name,
            value=value,
            currency="%", # Often ratios are percentages or multipliers
            unit="ratio",
            period=period,
            statement_type="consolidated",
            value_type="calculated",
            source=SourceProvenance(
                provider="EQBackendAPI_Internal",
                xbrl_tag=f"Formula: {formula}"
            )
        )

    @staticmethod
    def _get_val(fact: Optional[FinancialFact]) -> Optional[float]:
        if fact and fact.value is not None:
            return fact.value
        return None

    def calculate(self, period: str, inc: IncomeStatement, bal: BalanceSheet) -> Dict[str, Any]:
        ratios = {}
        
        rev = self._get_val(inc.revenue)
        gp = self._get_val(inc.gross_profit)
        op_inc = self._get_val(inc.operating_income)
        net_inc = self._get_val(inc.net_income)
        
        assets = self._get_val(bal.total_assets)
        equity = self._get_val(bal.total_equity)

        # Profitability Ratios
        if gp is not None and rev:
            ratios["gross_margin"] = self._create_calculated_fact(
                "Gross Margin", gp / rev, period, "Gross Profit / Revenue"
            )
            
        if op_inc is not None and rev:
            ratios["operating_margin"] = self._create_calculated_fact(
                "Operating Margin", op_inc / rev, period, "Operating Income / Revenue"
            )
            
        if net_inc is not None and rev:
            ratios["net_margin"] = self._create_calculated_fact(
                "Net Margin", net_inc / rev, period, "Net Income / Revenue"
            )
            
        # Return Ratios
        if net_inc is not None and assets:
            ratios["roa"] = self._create_calculated_fact(
                "ROA", net_inc / assets, period, "Net Income / Total Assets"
            )
            
        if net_inc is not None and equity:
            ratios["roe"] = self._create_calculated_fact(
                "ROE", net_inc / equity, period, "Net Income / Total Equity"
            )

        return ratios
