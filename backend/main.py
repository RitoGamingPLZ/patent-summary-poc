# backend/main.py
from typing import List
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from os import path
from fuzzywuzzy import fuzz
import json
import uuid

import schemas
from database import get_db
from models import Claim, Patent, Product, Company, SavedReport
from service import get_infringement_report, list_saved_reports, patent_infringement_check_logic, save_infringement_report, search_company_by_name
import os
from starlette.middleware.cors import CORSMiddleware

app = FastAPI()

origins = [
    "http://localhost:3000",  # React/Vue frontend running on port 3000
    "http://localhost:8000",  # Other localhost URL or frontend
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)
DATABASE_PATH = os.getenv("DATABASE_PATH", "./patent_data.db")



# Import data from JSON files into the database
@app.on_event("startup")
def load_data():
    db = next(get_db())

    # Check if the database file already exists
    if path.exists(DATABASE_PATH) and db.query(Patent).first() is not None:
        print("Database file exists. Skipping data load.")
        return  # Exit the function if the database file exists
    
    print("Database file not found or empty. Loading initial data...")

    # Get the directory of the current file (main.py) and locate JSON files
    base_dir = path.dirname(path.abspath(__file__))
    patents_path = path.join(base_dir, 'json', 'patents.json')
    products_path = path.join(base_dir, 'json', 'company_products.json')
    with open(patents_path, encoding="utf-8") as f:
        patents_data = json.load(f)
        for patent in patents_data:
            db_patent = Patent(
                id=str(uuid.uuid4()),
                publication_number=patent['publication_number'],
                title=patent['title'],
                description=patent['description'],
                abstract=patent['abstract'],
                assignee=patent['assignee']
            )
            db.add(db_patent)
            db.commit()
            claims = json.loads(patent['claims'])
            for claim in claims:
                db_claim = Claim(
                    id=str(uuid.uuid4()),
                    patent_id=db_patent.id,
                    text=claim['text'],
                    num=claim['num']  
                )
                db.add(db_claim)
            db.commit()

    with open(products_path, encoding="utf-8") as f:
        products_data = json.load(f)
        for company in products_data['companies']:
            db_company = Company(id=str(uuid.uuid4()), name=company['name'])
            db.add(db_company)
            db.commit()

            for product in company['products']:
                db_product = Product(
                    id=str(uuid.uuid4()),
                    company_id=db_company.id,
                    name=product['name'],
                    description=product['description']
                )
                db.add(db_product)
            db.commit()

@app.get("/patents/", response_model=List[schemas.Patent])
def get_patents(db: Session = Depends(get_db)):
    return db.query(Patent).all()

@app.get("/companies/", response_model=List[schemas.Company])
def get_companies(db: Session = Depends(get_db)):
    companies = db.query(Company).options(joinedload(Company.products)).all()
    return companies

@app.get("/patents/search", response_model=schemas.Patent)
def search_patent(publication_number: str, db: Session = Depends(get_db), threshold: int = 60):
    patents = db.query(Patent).all()
    
    # Use rapidfuzz to find matches with a similarity above the threshold
    matches = [
        (patent, fuzz.ratio(patent.publication_number, publication_number)) for patent in patents 
        if fuzz.ratio(patent.publication_number, publication_number) >= threshold
    ]
    
    if not matches:
        raise HTTPException(status_code=404, detail="No matching patents found")
    
    best_match = max(matches, key=lambda x: x[1])[0]  # Get the patent with the highest score
    return best_match

# Endpoint to get a company by fuzzy matching on name
@app.get("/companies/search", response_model=schemas.Company)
def search_company(name: str, db: Session = Depends(get_db), threshold: int = 60):
    try:
        # Call the service function to search for the company by name
        best_match = search_company_by_name(name, db, threshold)
        
        if best_match:
            return best_match
        
        raise HTTPException(status_code=404, detail="No matching companies found")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.post("/patent-infringement", response_model=schemas.InfringementResponse)
def patent_infringement_check(patent_id: str, company_name: str, db: Session = Depends(get_db)):
    try:
        response = patent_infringement_check_logic(patent_id, company_name, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return response

@app.get("/infringement-report/{analysis_id}", response_model=schemas.InfringementResponse)
def get_infringement_report_api(analysis_id: str, db: Session = Depends(get_db)):
    return get_infringement_report(analysis_id, db)


@app.post("/save-report", response_model=schemas.SavedReport)
def save_infringement_report_api(analysis_id: str, db: Session = Depends(get_db)):
    return save_infringement_report(analysis_id, db)

@app.get("/saved-reports", response_model=List[schemas.SavedReport])
def get_saved_reports_api(db: Session = Depends(get_db)):
    return list_saved_reports(db)

@app.get("/saved-reports/{report_id}", response_model=schemas.SavedReport)
def get_saved_report_by_id_api(report_id: str, db: Session = Depends(get_db)):
    saved_report = db.query(SavedReport).filter(SavedReport.id == report_id).first()
    if not saved_report:
        raise HTTPException(status_code=404, detail="Report not found")
    return saved_report