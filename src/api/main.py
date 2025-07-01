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
from google.api_core.client_options import ClientOptions

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


class HealthCheck(BaseModel):
    status: str
    timestamp: str
    version: str


# Configuration using environment variables
class Config:
    # Google Cloud Document AI settings from environment
    PROJECT_ID = os.getenv("GCP_PROJECT_ID", "invoiceprocessingai2498")
    LOCATION = os.getenv("GCP_LOCATION", "us")
    PROCESSOR_ID = os.getenv("GCP_PROCESSOR_ID", "cca0593594bfdba1")

    # File upload settings
    MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", 10 * 1024 * 1024))  # 10MB
    ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".gif"}

    @classmethod
    def verify_credentials(cls):
        """Verify Google Cloud credentials are properly set"""
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if creds_path and os.path.exists(creds_path):
            logger.info(f"Google Cloud credentials found: {creds_path}")
            return True
        else:
            logger.error(f"Google Cloud credentials not found. Path: {creds_path}")
            return False


config = Config()


# Initialize Document AI client
def get_document_ai_client():
    """Initialize and return Document AI client"""
    try:
        # Verify credentials first
        if not Config.verify_credentials():
            logger.error("Google Cloud credentials verification failed")
            return None

        # Set up client options for the specified location
        opts = ClientOptions(api_endpoint=f"{config.LOCATION}-documentai.googleapis.com")
        client = documentai.DocumentProcessorServiceClient(client_options=opts)
        logger.info(f"Document AI client initialized for location: {config.LOCATION}")
        logger.info(f"Using project: {config.PROJECT_ID}, processor: {config.PROCESSOR_ID}")
        return client
    except Exception as e:
        logger.error(f"Failed to initialize Document AI client: {e}")
        logger.error(f"Credentials path: {os.getenv('GOOGLE_APPLICATION_CREDENTIALS')}")
        return None


# Invoice processing functions
def extract_invoice_data(document: documentai.Document) -> Dict[str, Any]:
    """Extract structured data from processed invoice document"""

    extracted_data = {
        "vendor_info": {},
        "invoice_details": {},
        "line_items": [],
        "totals": {},
        "dates": {},
        "addresses": {}
    }

    confidence_scores = {}

    # Process entities
    for entity in document.entities:
        entity_type = entity.type_
        entity_value = entity.mention_text if entity.mention_text else ""
        confidence = entity.confidence

        # Store confidence scores
        confidence_scores[entity_type] = confidence

        # Categorize entities based on common invoice fields
        if entity_type in ["supplier_name", "vendor_name", "remit_to_name"]:
            extracted_data["vendor_info"]["name"] = entity_value
        elif entity_type in ["supplier_address", "vendor_address", "remit_to_address"]:
            extracted_data["addresses"]["vendor_address"] = entity_value
        elif entity_type in ["invoice_id", "invoice_number"]:
            extracted_data["invoice_details"]["invoice_number"] = entity_value
        elif entity_type in ["invoice_date", "invoice_issue_date"]:
            extracted_data["dates"]["invoice_date"] = entity_value
        elif entity_type in ["due_date", "payment_due_date"]:
            extracted_data["dates"]["due_date"] = entity_value
        elif entity_type in ["total_amount", "invoice_total_amount"]:
            extracted_data["totals"]["total_amount"] = entity_value
        elif entity_type in ["net_amount", "subtotal_amount"]:
            extracted_data["totals"]["net_amount"] = entity_value
        elif entity_type in ["total_tax_amount", "tax_amount"]:
            extracted_data["totals"]["tax_amount"] = entity_value
        elif entity_type in ["currency"]:
            extracted_data["totals"]["currency"] = entity_value
        elif entity_type in ["receiver_name", "bill_to_name"]:
            extracted_data["vendor_info"]["bill_to"] = entity_value
        elif entity_type in ["receiver_address", "bill_to_address"]:
            extracted_data["addresses"]["billing_address"] = entity_value

    # Process tables (line items)
    for page in document.pages:
        for table in page.tables:
            headers = []
            rows = []

            # Extract headers from header rows
            if table.header_rows:
                for header_row in table.header_rows:
                    header_cells = []
                    for cell in header_row.cells:
                        cell_text = ""
                        if cell.layout.text_anchor:
                            # Extract text from text segments
                            for segment in cell.layout.text_anchor.text_segments:
                                start_index = segment.start_index
                                end_index = segment.end_index
                                cell_text += document.text[start_index:end_index]
                        header_cells.append(cell_text.strip())
                    headers = header_cells
                    break  # Use first header row

            # Extract data rows
            for row in table.body_rows:
                row_data = {}
                for i, cell in enumerate(row.cells):
                    cell_text = ""
                    if cell.layout.text_anchor:
                        # Extract text from text segments
                        for segment in cell.layout.text_anchor.text_segments:
                            start_index = segment.start_index
                            end_index = segment.end_index
                            cell_text += document.text[start_index:end_index]

                    # Map to header or use column index
                    if i < len(headers) and headers[i]:
                        row_data[headers[i]] = cell_text.strip()
                    else:
                        row_data[f"column_{i}"] = cell_text.strip()

                # Only add non-empty rows
                if any(value.strip() for value in row_data.values() if value):
                    rows.append(row_data)

            # Add line items if we found any
            if rows:
                extracted_data["line_items"] = rows
                break  # Use first table with data

    return extracted_data, confidence_scores


async def process_document_with_ai(file_content: bytes, mime_type: str) -> ProcessingResult:
    """Process document using Google Document AI"""

    start_time = datetime.now()

    try:
        # Initialize client
        client = get_document_ai_client()
        if not client:
            raise HTTPException(status_code=500, detail="Document AI client not available")

        # Create the full resource name
        name = client.processor_path(config.PROJECT_ID, config.LOCATION, config.PROCESSOR_ID)
        logger.info(f"Using processor: {name}")

        # Create document object
        raw_document = documentai.RawDocument(content=file_content, mime_type=mime_type)

        # Create process request
        request = documentai.ProcessRequest(name=name, raw_document=raw_document)

        # Process the document
        logger.info("Sending document to Document AI...")
        result = client.process_document(request=request)
        document = result.document

        logger.info(f"Document processed. Found {len(document.entities)} entities")

        # Extract structured data
        extracted_data, confidence_scores = extract_invoice_data(document)

        # Calculate processing time
        processing_time = (datetime.now() - start_time).total_seconds()

        return ProcessingResult(
            success=True,
            message="Document processed successfully with Google Document AI",
            extracted_data=extracted_data,
            confidence_scores=confidence_scores,
            processing_time=processing_time
        )

    except Exception as e:
        logger.error(f"Document processing failed: {e}")
        processing_time = (datetime.now() - start_time).total_seconds()

        return ProcessingResult(
            success=False,
            message=f"Processing failed: {str(e)}",
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
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")

    # Check file size
    if len(file_content) > config.MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size: {config.MAX_FILE_SIZE / (1024 * 1024):.1f}MB"
        )

    # Determine MIME type
    mime_type_map = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".tiff": "image/tiff",
        ".gif": "image/gif"
    }
    mime_type = mime_type_map.get(file_ext, "application/octet-stream")

    # Process the document
    result = await process_document_with_ai(file_content, mime_type)

    # Process the document
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
                "extraction_success": True
            }

            # Save to file that agent can read
            recent_file_path = Path(__file__).parent.parent.parent / "recent_processing.json"
            with open(recent_file_path, "w") as f:
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
            mime_type_map = {
                ".pdf": "application/pdf",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".tiff": "image/tiff",
                ".gif": "image/gif"
            }
            mime_type = mime_type_map.get(file_ext, "application/octet-stream")

            # Process document
            result = await process_document_with_ai(file_content, mime_type)

            results.append({
                "file_index": i,
                "filename": file.filename,
                "success": result.success,
                "message": result.message,
                "extracted_data": result.extracted_data,
                "confidence_scores": result.confidence_scores,
                "processing_time": result.processing_time
            })

        except Exception as e:
            results.append({
                "file_index": i,
                "filename": file.filename if file.filename else "unknown",
                "success": False,
                "message": f"Processing error: {str(e)}"
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