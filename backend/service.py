# backend/app/service.py

import json
import uuid
from typing import List, Dict, Any, Tuple
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from fuzzywuzzy import fuzz
import re
import schemas
from models import Company, InfringingProduct, Patent, Product, InfringementAnalysis, Claim, SavedReport
from openai import OpenAI
import os

api_key = os.getenv("OPENAI_API_KEY")

client = OpenAI(
    # defaults to os.environ.get("OPENAI_API_KEY")
    api_key=api_key,
)

def extract_key_phrases(claims: List[str]) -> List[str]:
    key_phrases = []
    for claim in claims:
        # Basic word tokenization using regex
        words = re.findall(r"\b\w+\b", claim)  # Matches words only
        
        # Basic noun-like detection (e.g., capitalize first letter or all caps for entities)
        phrases = [word for word in words if word.istitle() or word.isupper()]
        key_phrases.extend(phrases)
    return key_phrases

# Use ChatGPT API for summarizing text
def summarize_text(text: str, max_length: int = 2048) -> str:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Summarize the following text."},
            {"role": "user", "content": text}
        ],
        max_tokens=max_length // 4  # Roughly control the summary length
    )
    return response.choices[0].message.content.strip()

# Use ChatGPT API to generate an overall risk assessment
def generate_overall_risk_assessment(top_products: List[Tuple[str, str]]) -> str:
    product_1, likelihood_1 = top_products[0]
    product_2, likelihood_2 = top_products[1]
    prompt = (
        f"Product 1 Explanation:\n{product_1}\nLikelihood: {likelihood_1}\n\n"
        f"Product 2 Explanation:\n{product_2}\nLikelihood: {likelihood_2}\n\n"
    )
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Provide an overall risk assessment for the likelihood of infringement."},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content.strip()

def get_detailed_infringement_analysis(patent_summary, claims, product_description):
    # Format claims into a readable format for the prompt
    claims_text = "\n".join(f"Claim {claim['num']}: {claim['text']}" for claim in claims)
    
    # ChatGPT prompt to request all needed details in JSON format
    prompt = (
        "Given the following product description and patent claims, identify the claims that are relevant "
        "to the product description and provide a JSON response in the specified format. The response should include:\n"
        "- `relevant_claims`: a list of relevant claims with each item containing `num` and `text`.\n"
        "- `likelihood`: a single string indicating the overall likelihood of infringement, which can be 'High', 'Moderate', or 'Low'.\n"
        "- `specific_features`: a list of specific features from the product description that overlap with the patent claims.\n"
        "- `explanation`: a concise explanation describing why these claims and features suggest potential infringement.\n\n"
        f"Product Description:\n{product_description}\n\n"
        f"Patent Summary:\n{patent_summary}\n\n"
        f"Patent Claims:\n{claims_text}\n\n"
        "Please respond in the following JSON format:\n"
        "{\n"
        "  \"relevant_claims\": [<claim_number>],\n"
        "  \"likelihood\": \"<High/Moderate/Low>\",\n"
        "  \"specific_features\": [\"<feature_1>\", \"<feature_2>\", ...],\n"
        "  \"explanation\": \"<Brief explanation of potential infringement>\"\n"
        "}"
    )
    
    # Requesting ChatGPT to generate the output
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "You are an AI assistant helping with patent analysis."},
            {"role": "user", "content": prompt}
        ]
    )
    
    # Extracting the JSON response from ChatGPT
    response_json = response.choices[0].message.content.strip()
    
    # Attempt to parse the response as JSON
    try:
        parsed_response = json.loads(response_json)
    except json.JSONDecodeError:
        # Fallback structure in case of JSON parsing error
        parsed_response = {
            "relevant_claims": [],
            "likelihood": "Unknown",
            "specific_features": [],
            "explanation": "No explanation provided."
        }
    
    return parsed_response

# Main function for patent infringement check logic
def patent_infringement_check_logic(publication_number: str, company_name: str, db: Session) -> Dict[str, Any]:
    patent = db.query(Patent).filter(Patent.publication_number == publication_number).first()
    company = search_company_by_name(company_name, db)
    if not patent:
        raise ValueError("Patent not found")
    if not company:
        raise ValueError("Company not found")

    patent_summary = summarize_text(patent.abstract + " " + patent.description)
    claims_text = [claim.text for claim in patent.claims]
    key_phrases = extract_key_phrases(claims_text)
    products = db.query(Product).filter(Product.company_id == company.id).all()

    relevance_scores = []
    for product in products:
        description = product.description or ""
        # Calculate the fuzzy match scores for each key phrase
        scores = [fuzz.partial_ratio(phrase, description) for phrase in key_phrases]
        
        # Calculate the average score
        avg_score = sum(scores) / len(scores) if scores else 0  # Handle empty scores gracefully
        relevance_scores.append((product, avg_score))

    top_products = sorted(relevance_scores, key=lambda x: x[1], reverse=True)[:2]
    analysis = InfringementAnalysis(
        id=str(uuid.uuid4()),
        patent_id=patent.publication_number,
        company_id=company.id,
        analysis_date=func.current_date(),
        overall_risk_assessment=""
    )
    db.add(analysis)
    db.commit()

    top_product_explanations = []
    for product, score in top_products:
        response = get_detailed_infringement_analysis(
            patent_summary,
            [{"num": claim.num, "text": claim.text} for claim in patent.claims],
            product.description
        )
        relevant_claims = response.get("relevant_claims", [])
        likelihood = response.get("likelihood", "Unknown")
        specific_features = response.get("specific_features", [])
        explanation = response.get("explanation", "No explanation provided.")
        top_product_explanations.append((explanation, likelihood))

        infringing_product = InfringingProduct(
            analysis_id=analysis.id,
            product_id=product.id,
            product_name=product.name,
            infringement_likelihood=likelihood,
            relevant_claims=relevant_claims,
            explanation=explanation,
            specific_features=specific_features
        )
        db.add(infringing_product)

    analysis.overall_risk_assessment = generate_overall_risk_assessment(top_product_explanations)
    db.commit()

    return {
        "infringement_analysis": {
            'id': analysis.id,
            "patent_id": patent.id,
            "company_name": company.name,
            "analysis_date": analysis.analysis_date.isoformat(),
            "overall_risk_assessment": analysis.overall_risk_assessment,
            "top_infringing_products": [
                {
                    "product_name": product.product_name,
                    "infringement_likelihood": product.infringement_likelihood,
                    "relevant_claims": [claim["num"] for claim in product.relevant_claims],
                    "explanation": product.explanation,
                    "specific_features": product.specific_features
                }
                for product in analysis.top_infringing_products
            ]
        }
    }

def get_infringement_report(analysis_id: str, db: Session) -> schemas.InfringementResponse:
    # Fetch the infringement analysis by ID
    analysis = db.query(InfringementAnalysis).filter(InfringementAnalysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Infringement analysis not found")
        
    # Fetch the related company and patent
    company = db.query(Company).filter(Company.id == analysis.company_id).first()
    patent = db.query(Patent).filter(Patent.publication_number == analysis.patent_id).first()
    if not company or not patent:
        raise HTTPException(status_code=404, detail="Related company or patent not found")

    # Fetch associated infringing products
    infringing_products = db.query(InfringingProduct).filter(InfringingProduct.analysis_id == analysis_id).all()

    # Prepare the top infringing products in the required format
    top_infringing_products = [
        {
            "product_name": product.product_name,
            "infringement_likelihood": product.infringement_likelihood,
            "relevant_claims": [claim["num"] for claim in product.relevant_claims],
            "explanation": product.explanation,
            "specific_features": product.specific_features
        }
        for product in infringing_products
    ]
    # Structure the response
    response = {
        "infringement_analysis": {
            "id": analysis.id,
            "patent_id": patent.publication_number,
            "company_name": company.name,
            "analysis_date": analysis.analysis_date.isoformat(),  # Ensure ISO date format
            "overall_risk_assessment": analysis.overall_risk_assessment,
            "top_infringing_products": top_infringing_products
        }
    }

    return response

def save_infringement_report(analysis_id: str, db: Session) -> schemas.SavedReport:
    # Check if the report already exists
    if db.query(SavedReport).filter(SavedReport.analysis_id == analysis_id).first():
        raise HTTPException(status_code=400, detail="Report with this analysis_id already saved.")
    
    # Fetch associated analysis, company, and patent to confirm validity
    analysis = db.query(InfringementAnalysis).filter(InfringementAnalysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Infringement analysis not found.")
    
    # Create and save the new report
    saved_report = SavedReport(
        id=str(uuid.uuid4()),
        analysis_id=analysis_id,
        report_date=func.current_date(),
    )
    db.add(saved_report)
    db.commit()
    db.refresh(saved_report)

    return saved_report

def list_saved_reports(db: Session):
    # Query all saved reports, ordered by date descending
    saved_reports = db.query(SavedReport).order_by(SavedReport.report_date.desc()).all()
    return saved_reports

# Retrieve a single company by name (fuzzy match)
def search_company_by_name(company_name: str, db: Session, threshold: int = 60) -> Company:
    companies = db.query(Company).all()
    matches = [
        (company, fuzz.ratio(company.name, company_name)) for company in companies
        if fuzz.ratio(company.name, company_name) >= threshold
    ]
    
    if not matches:
        raise ValueError("No matching companies found")
    
    best_match = max(matches, key=lambda x: x[1])[0]  # Get the company with the highest score
    return best_match