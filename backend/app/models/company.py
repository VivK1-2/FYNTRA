from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.db.base_class import Base

class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    ticker = Column(String, index=True, nullable=True)
    exchange = Column(String, nullable=True)
    country = Column(String, nullable=True)
    currency = Column(String, nullable=True)
    isin = Column(String, index=True, nullable=True)
    sec_cik = Column(String, index=True, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
