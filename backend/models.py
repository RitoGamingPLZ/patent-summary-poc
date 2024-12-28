# backend/app/models.py
from sqlalchemy import Column, String, Text, ForeignKey, Date, JSON, create_engine
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
import uuid
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get DATABASE_URL from .env or use default
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./patent_data.db")
# Define the SQLite engine and Base class
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Model Definitions
class Patent(Base):
    __tablename__ = "patents"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    publication_number = Column(String(255), unique=True, nullable=False)
    title = Column(Text, nullable=False)
    abstract = Column(Text)
    description = Column(Text)
    claims = relationship("Claim", back_populates="patent", cascade="all, delete-orphan")
    assignee = Column(String(255))

class Claim(Base):
    __tablename__ = "claims"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    patent_id = Column(String, ForeignKey("patents.id", ondelete="CASCADE"), nullable=False)
    num = Column(String, nullable=False)  # Store claim number
    text = Column(Text, nullable=False)   # Store claim text

    # Relationship to Patent
    patent = relationship("Patent", back_populates="claims")

class Company(Base):
    __tablename__ = "companies"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), unique=True, nullable=False)

class Product(Base):
    __tablename__ = "products"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String, ForeignKey("companies.id", ondelete="CASCADE"))
    name = Column(String(255), nullable=False)
    description = Column(Text)
    company = relationship("Company", back_populates="products")

class InfringementAnalysis(Base):
    __tablename__ = "infringement_analyses"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    patent_id = Column(String, ForeignKey("patents.id", ondelete="CASCADE"))
    company_id = Column(String, ForeignKey("companies.id", ondelete="CASCADE"))
    analysis_date = Column(Date, nullable=False)
    overall_risk_assessment = Column(String(50))

    # Define relationship to InfringingProduct
    top_infringing_products = relationship("InfringingProduct", back_populates="analysis", cascade="all, delete-orphan")


class InfringingProduct(Base):
    __tablename__ = "infringing_products"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    analysis_id = Column(String, ForeignKey("infringement_analyses.id", ondelete="CASCADE"))
    product_id = Column(String, ForeignKey("products.id", ondelete="CASCADE"))
    product_name = Column(String(255))
    infringement_likelihood = Column(String(50))
    relevant_claims = Column(JSON)
    explanation = Column(Text)
    specific_features = Column(JSON)

    # Define relationship back to InfringementAnalysis
    analysis = relationship("InfringementAnalysis", back_populates="top_infringing_products")

class SavedReport(Base):
    __tablename__ = "saved_reports"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    analysis_id = Column(String, ForeignKey("infringement_analyses.id", ondelete="CASCADE"), unique=True)
    report_date = Column(Date, default="CURRENT_DATE")

# Relationships
Company.products = relationship("Product", order_by=Product.id, back_populates="company")

# Create all tables
Base.metadata.create_all(bind=engine)
