from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

class CompanyBase(BaseModel):
    name: str
    ticker: Optional[str] = None
    exchange: Optional[str] = None
    country: Optional[str] = None
    currency: Optional[str] = None
    isin: Optional[str] = None
    sec_cik: Optional[str] = None

class CompanyCreate(CompanyBase):
    pass

class CompanyResponse(CompanyBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
