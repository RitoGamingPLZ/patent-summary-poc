# backend/app/schemas.py
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from datetime import date
import uuid

class Claim(BaseModel):
    num: str
    text: str

    class Config:
        orm_mode = True

class PatentBase(BaseModel):
    publication_number: str
    title: str
    abstract: Optional[str] = None
    claims: Optional[List[Claim]] = None
    assignee: Optional[str] = None

class PatentCreate(PatentBase):
    pass

class Patent(PatentBase):
    id: str

    class Config:
        orm_mode = True

class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None

class ProductCreate(ProductBase):
    company_id: str

class Product(ProductBase):
    id: str

    class Config:
        orm_mode = True

# Company schemas
class CompanyBase(BaseModel):
    name: str

class CompanyCreate(CompanyBase):
    pass

class Company(CompanyBase):
    id: str
    products: Optional[List[Product]] = []  # List of products related to the company

    class Config:
        orm_mode = True

class InfringingProductSchema(BaseModel):
    product_name: str
    infringement_likelihood: str
    relevant_claims: List[Any]
    explanation: str
    specific_features: List[str]

class InfringementAnalysisSchema(BaseModel):
    id: str
    patent_id: str
    company_name: str
    analysis_date: str  # Use `str` to format the date as an ISO string in responses
    overall_risk_assessment: str
    top_infringing_products: List[InfringingProductSchema]

class InfringementResponse(BaseModel):
    infringement_analysis: InfringementAnalysisSchema

class SavedReport(BaseModel):
    id: str
    analysis_id: str
    report_date: date