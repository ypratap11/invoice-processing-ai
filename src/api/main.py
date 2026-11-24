"""
FastAPI Backend for Invoice Processing AI
Complete production-ready API with Google Document AI integration
Using existing Google Cloud configuration
"""

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import os
import io
import json
from pathlib import Path
import uvicorn
from datetime import datetime
import logging
import sys
from pathlib import Path

# Load environment variables from .env file FIRST
from dotenv import load_dotenv

load_dotenv()

# Google Cloud imports
from google.cloud import documentai

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add the project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Initialize FastAPI app
app = FastAPI(
    title="Invoice Processing AI",
    description="Advanced invoice processing using Google Document AI with LangChain Agent",
    version="2.0.0"  # Updated version for MVP
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models for request/response
class ProcessingResult(BaseModel):
    success: bool
    message: str
    extracted_data: Optional[Dict[str, Any]] = None
    confidence_scores: Optional[Dict[str, float]] = None
    processing_time: Optional[float] = None
    review_required: bool = False
    review_reasons: List[str] = []


class HealthCheck(BaseModel):
    status: str
    timestamp: str
    version: str


# Configuration using environment variables
from src.core.docai_client import credentials_available, settings as _settings

_docai_settings = _settings()


class Config:
    # Google Cloud Document AI settings from environment (see src/core/docai_client.py)
    PROJECT_ID = _docai_settings.project_id
    LOCATION = _docai_settings.location
    PROCESSOR_ID = _docai_settings.processor_id

    # File upload settings
    MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", 10 * 1024 * 1024))  # 10MB
    ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".gif"}

    @classmethod
    def verify_credentials(cls):
        """Verify Google Cloud credentials are properly set"""
        if credentials_available():
            logger.info("Google Cloud credentials found")
            return True
        logger.error("Google Cloud credentials are not configured")
        return False


config = Config()


# Document AI processing (single path shared by the API and the agent tool)
from src.core import docai_client
from src.core.invoice_checks import check as check_invoice
from src.core.invoice_extractor import HEADER_FIELDS, entity_text, extract_invoice

LOW_CONFIDENCE = 0.7

MIME_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tiff": "image/tiff",
    ".gif": "image/gif",
}

RECENT_PROCESSING_PATH = project_root / "recent_processing.json"

# The only directory the agent's process_invoice tool may read files from
# (env UPLOAD_DIR, default "uploads"; a relative value is under the project root).
UPLOAD_DIR = project_root / os.getenv("UPLOAD_DIR", "uploads")


def get_document_ai_client():
    """Document AI client, or None if it cannot be created (startup check only)."""
    try:
        return docai_client.get_client()
    except Exception as e:
        logger.error(f"Failed to initialize Document AI client: {e}")
        return None


def extract_invoice_data(document: documentai.Document):
    """Response shape the Streamlit frontend renders, filled from ``extract_invoice``.

    Returns ``(extracted_data, confidence_scores)``; line items are schema
    dicts (description, quantity, unit_price, amount)."""
    inv, confidence = extract_invoice(document)
    vendor_info = {"name": inv["vendor_name"]}
    bill_to = entity_text(document, "receiver_name")
    if bill_to:
        vendor_info["bill_to"] = bill_to
    addresses = {}
    for key, etype in (("vendor_address", "supplier_address"),
                       ("billing_address", "receiver_address")):
        text = entity_text(document, etype)
        if text:
            addresses[key] = text
    extracted_data = {
        "vendor_info": vendor_info,
        "invoice_details": {"invoice_number": inv["invoice_id"]},
        "line_items": inv["line_items"],
        "totals": {"total_amount": inv["total"], "net_amount": inv["subtotal"],
                   "tax_amount": inv["tax_total"], "currency": inv["currency"]},
        "dates": {"invoice_date": inv["invoice_date"], "due_date": inv["due_date"]},
        "addresses": addresses,
    }
    return extracted_data, confidence


def review_reasons(inv: dict, confidence: Dict[str, float]) -> List[str]:
    """Deterministic check failures plus fields extracted with low confidence."""
    reasons = check_invoice(inv)
    reasons += [f"low_confidence:{f}" for f in (*HEADER_FIELDS, "line_items")
                if confidence.get(f, 1.0) < LOW_CONFIDENCE]
    return reasons


def process_invoice_bytes(file_content: bytes, mime_type: str) -> Dict[str, Any]:
    """Process one file with Document AI (one call) and extract + check it.

    Returns ``invoice`` (schema keys), ``extracted_data`` (frontend shape),
    ``confidence_scores``, ``review_required`` and ``review_reasons``."""
    document = docai_client.process_bytes(file_content, mime_type)
    inv, _ = extract_invoice(document)
    extracted_data, confidence = extract_invoice_data(document)
    reasons = review_reasons(inv, confidence)
    return {"invoice": inv, "extracted_data": extracted_data,
            "confidence_scores": confidence,
            "review_required": bool(reasons), "review_reasons": reasons}


async def process_document_with_ai(file_content: bytes, mime_type: str) -> ProcessingResult:
    """Process document using Google Document AI"""

    start_time = datetime.now()

    try:
        out = process_invoice_bytes(file_content, mime_type)
        processing_time = (datetime.now() - start_time).total_seconds()
        return ProcessingResult(
            success=True,
            message="Document processed successfully with Google Document AI",
            extracted_data=out["extracted_data"],
            confidence_scores=out["confidence_scores"],
            processing_time=processing_time,
            review_required=out["review_required"],
            review_reasons=out["review_reasons"],
        )

    except Exception:
        # details stay in the server log; clients get a generic message
        logger.exception("Document processing failed")
        processing_time = (datetime.now() - start_time).total_seconds()

        return ProcessingResult(
            success=False,
            message="Processing failed (see server log)",
            extracted_data=None,
            confidence_scores=None,
            processing_time=processing_time
        )


# Import agent components AFTER all dependencies are loaded
try:
    from src.api.agent_endpoints import agent_router
    from src.database import create_tables

    # Add agent router
    app.include_router(agent_router)
    logger.info("✅ LangChain Agent endpoints loaded successfully")

except ImportError as e:
    logger.warning(f"⚠️ Agent components not available: {e}")
    logger.warning("Running in legacy mode without AI agent features")


# Initialize database tables on startup
@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    logger.info("🚀 Starting Invoice Processing AI...")

    # Initialize database if agent components are available
    try:
        create_tables()
        logger.info("✅ Database tables initialized")
    except NameError:
        logger.info("📊 Running without database (legacy mode)")

    # Verify Document AI setup
    client = get_document_ai_client()
    if client:
        logger.info("✅ Document AI client ready")
    else:
        logger.warning("⚠️ Document AI client not available")

    logger.info("🎉 Application startup complete!")


# API Routes
@app.get("/", response_model=HealthCheck)
async def health_check():
    """Health check endpoint"""
    return HealthCheck(
        status="healthy",
        timestamp=datetime.now().isoformat(),
        version="2.0.0"
    )


@app.post("/process-invoice", response_model=ProcessingResult)
async def process_invoice(file: UploadFile = File(...)):
    """
    Process an invoice file and extract structured data

    Supports: PDF, PNG, JPG, JPEG, TIFF, GIF
    Max file size: 10MB
    """

    # Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # Check file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(config.ALLOWED_EXTENSIONS)}"
        )

    # Read file content
    try:
        file_content = await file.read()
    except Exception:
        logger.exception("Failed to read uploaded file")
        raise HTTPException(status_code=400, detail="Failed to read file")

    # Check file size
    if len(file_content) > config.MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size: {config.MAX_FILE_SIZE / (1024 * 1024):.1f}MB"
        )

    mime_type = MIME_TYPES.get(file_ext, "application/octet-stream")

    # Process the document (one Document AI call per upload)
    result = await process_document_with_ai(file_content, mime_type)

    # Store recent processing data for AI agent access
    if result.success and result.extracted_data:
        try:
            # Calculate average confidence
            avg_confidence = 0
            if result.confidence_scores:
                avg_confidence = sum(result.confidence_scores.values()) / len(result.confidence_scores)

            # Extract key information
            vendor_name = "Unknown Vendor"
            total_amount = "0.00"

            if result.extracted_data.get("vendor_info", {}).get("name"):
                vendor_name = result.extracted_data["vendor_info"]["name"]

            if result.extracted_data.get("totals", {}).get("total_amount"):
                total_amount = result.extracted_data["totals"]["total_amount"]

            # Prepare data for agent
            recent_data = {
                "timestamp": datetime.now().isoformat(),
                "filename": file.filename,
                "vendor": vendor_name,
                "amount": total_amount,
                "confidence": f"{avg_confidence:.1%}" if avg_confidence else "Unknown",
                "processing_time": f"{result.processing_time:.2f}s" if result.processing_time else "Unknown",
                "invoice_number": result.extracted_data.get("invoice_details", {}).get("invoice_number", "N/A"),
                "invoice_date": result.extracted_data.get("dates", {}).get("invoice_date", "N/A"),
                "line_items_count": len(result.extracted_data.get("line_items", [])),
                "extraction_success": True,
                "review_required": result.review_required,
                "review_reasons": result.review_reasons,
            }

            # Save to file that agent can read
            with open(RECENT_PROCESSING_PATH, "w") as f:
                json.dump(recent_data, f, indent=2)

            logger.info(f"✅ Saved recent processing data for agent: {vendor_name} - ${total_amount}")

        except Exception as e:
            logger.warning(f"⚠️ Failed to save recent processing data: {e}")

    return result


@app.get("/config")
async def get_config():
    """Get current configuration (non-sensitive data only)"""
    return {
        "max_file_size_mb": config.MAX_FILE_SIZE / (1024 * 1024),
        "allowed_extensions": list(config.ALLOWED_EXTENSIONS),
        "processor_location": config.LOCATION,
        "project_id": config.PROJECT_ID,
        "processor_id": config.PROCESSOR_ID[:8] + "...",  # Partial ID for security
        "api_version": "2.0.0",
        "features": {
            "document_ai": True,
            "langchain_agent": "agent_router" in locals(),
            "database": "create_tables" in locals()
        }
    }


@app.post("/batch-process")
async def batch_process_invoices(files: List[UploadFile] = File(...)):
    """
    Process multiple invoice files in batch
    """

    if len(files) > 10:  # Limit batch size
        raise HTTPException(status_code=400, detail="Too many files. Maximum 10 files per batch.")

    results = []

    for i, file in enumerate(files):
        try:
            # Validate file
            if not file.filename:
                results.append({
                    "file_index": i,
                    "filename": "unknown",
                    "success": False,
                    "message": "No filename provided"
                })
                continue

            # Check file extension
            file_ext = Path(file.filename).suffix.lower()
            if file_ext not in config.ALLOWED_EXTENSIONS:
                results.append({
                    "file_index": i,
                    "filename": file.filename,
                    "success": False,
                    "message": f"Unsupported file type: {file_ext}"
                })
                continue

            # Read and process file
            file_content = await file.read()

            if len(file_content) > config.MAX_FILE_SIZE:
                results.append({
                    "file_index": i,
                    "filename": file.filename,
                    "success": False,
                    "message": "File too large"
                })
                continue

            # Determine MIME type and process
            mime_type = MIME_TYPES.get(file_ext, "application/octet-stream")

            # Process document
            result = await process_document_with_ai(file_content, mime_type)

            results.append({
                "file_index": i,
                "filename": file.filename,
                "success": result.success,
                "message": result.message,
                "extracted_data": result.extracted_data,
                "confidence_scores": result.confidence_scores,
                "processing_time": result.processing_time,
                "review_required": result.review_required,
                "review_reasons": result.review_reasons,
            })

        except Exception:
            logger.exception("Batch processing failed for file %d", i)
            results.append({
                "file_index": i,
                "filename": file.filename if file.filename else "unknown",
                "success": False,
                "message": "Processing error (see server log)"
            })

    return {
        "batch_results": results,
        "total_files": len(files),
        "successful_files": sum(1 for r in results if r["success"]),
        "failed_files": sum(1 for r in results if not r["success"])
    }


# Run the application
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )