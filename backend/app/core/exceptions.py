from fastapi import Request, status
from fastapi.responses import JSONResponse

class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        self.code = code
        self.message = message
        self.status_code = status_code

class CompanyNotFoundError(AppError):
    def __init__(self, identifier: str):
        super().__init__(
            code="COMPANY_NOT_FOUND",
            message=f"Company '{identifier}' could not be resolved.",
            status_code=status.HTTP_404_NOT_FOUND
        )

class FinancialDataUnavailableError(AppError):
    def __init__(self, detail: str = "Financial data unavailable"):
        super().__init__(
            code="FINANCIAL_DATA_UNAVAILABLE",
            message=detail,
            status_code=status.HTTP_404_NOT_FOUND
        )

class FilingNotFoundError(AppError):
    def __init__(self, accession: str):
        super().__init__(
            code="FILING_NOT_FOUND",
            message=f"Filing '{accession}' was not found for this company.",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class NotSupportedError(AppError):
    def __init__(self, detail: str = "Not supported yet"):
        super().__init__(code="NOT_SUPPORTED", message=detail, status_code=status.HTTP_501_NOT_IMPLEMENTED)


class MarketDataUnavailableError(AppError):
    def __init__(self, detail: str = "Market data is unavailable right now."):
        super().__init__(code="MARKET_DATA_UNAVAILABLE", message=detail, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)


async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.code,
                "message": exc.message
            },
            "meta": {}
        }
    )
