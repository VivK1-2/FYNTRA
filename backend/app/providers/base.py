from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.models.company import Company


class CompanyProvider(ABC):
    """
    Base interface that all filing providers (SEC, NSE, BSE, company IR) implement.
    Keep providers dumb: they discover and fetch. Parsing, analytics and AI live elsewhere.
    """

    @abstractmethod
    async def resolve_company(self, identifier: str) -> Optional[Company]:
        ...

    @abstractmethod
    async def find_filings(self, company: Company, form: str = "10-K", limit: int = 5) -> List[Dict[str, Any]]:
        """Return filing metadata dicts (form, filing_date, period, urls), newest first."""

    @abstractmethod
    async def get_structured_data(self, company: Company, fy: int) -> Dict[str, Any]:
        """Structured financial values for a fiscal year, each with provenance."""
