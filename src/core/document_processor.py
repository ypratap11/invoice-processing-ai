"""
Google Document AI integration for OCR and document processing
"""
from google.cloud import documentai
from typing import Dict, List, Optional
import logging
import sys
import os

# Add src to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from utils.config import get_settings
except ImportError:
    # Alternative import for different execution contexts
    import sys

    sys.path.append('src')
    from utils.config import get_settings

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Handles document processing using Google Document AI"""

    def __init__(self):
        """Initialize Document AI client"""
        try:
            self.client = documentai.DocumentProcessorServiceClient()
            settings = get_settings()
            self.processor_path = self.client.processor_path(
                settings.GCP_PROJECT_ID,
                settings.GCP_LOCATION,
                settings.GCP_PROCESSOR_ID
            )
            logger.info("Document AI client initialized successfully")
            print(f"✅ Document AI initialized for processor: {settings.GCP_PROCESSOR_ID}")
        except Exception as e:
            logger.error(f"Failed to initialize Document AI client: {str(e)}")
            print(f"❌ Failed to initialize Document AI: {str(e)}")
            raise

    def process_document(self, file_content: bytes, mime_type: str) -> Dict:
        """
        Process a document using Google Document AI

        Args:
            file_content: Raw document bytes
            mime_type: MIME type of the document (application/pdf, image/jpeg, etc.)

        Returns:
            Dictionary containing extracted data and metadata
        """
        try:
            print(f"🔍 Processing document with Document AI...")

            # Create request
            request = documentai.ProcessRequest(
                name=self.processor_path,
                raw_document=documentai.RawDocument(
                    content=file_content,
                    mime_type=mime_type
                )
            )

            # Process document
            result = self.client.process_document(request=request)
            document = result.document

            print(f"📄 Document processed successfully!")
            print(f"   - Pages: {len(document.pages)}")
            print(f"   - Text length: {len(document.text)} characters")
            print(f"   - Entities found: {len(document.entities)}")

            # Extract structured data
            extracted_data = self._extract_structured_data(document)
            confidence_scores = self._calculate_confidence_scores(document)

            return {
                "success": True,
                "extracted_data": extracted_data,
                "full_text": document.text,
                "confidence_scores": confidence_scores,
                "processing_metadata": {
                    "page_count": len(document.pages),
                    "processor_version": self.processor_path,
                    "entities_count": len(document.entities)
                }
            }

        except Exception as e:
            error_msg = f"Document processing failed: {str(e)}"
            logger.error(error_msg)
            print(f"❌ {error_msg}")
            return {
                "success": False,
                "error": str(e),
                "extracted_data": {},
                "full_text": "",
                "confidence_scores": {}
            }

    def _extract_structured_data(self, document) -> Dict:
        """Extract key-value pairs from document entities"""
        extracted = {}

        print(f"🔧 Extracting structured data...")

        for entity in document.entities:
            key = entity.type_.replace("_", " ").title()
            value = entity.mention_text.strip()
            confidence = entity.confidence

            extracted[key] = {
                "value": value,
                "confidence": confidence,
                "normalized_value": self._normalize_value(entity.type_, value)
            }

            print(f"   - {key}: {value} (confidence: {confidence:.2f})")

        return extracted

    def _normalize_value(self, entity_type: str, value: str) -> str:
        """Normalize extracted values based on entity type"""
        if entity_type in ["total_amount", "subtotal_amount", "net_amount"]:
            # Remove currency symbols and normalize
            import re
            normalized = re.sub(r'[^\d.,]', '', value)
            return normalized
        elif entity_type in ["invoice_date", "due_date", "receipt_date"]:
            # Normalize date format
            return self._normalize_date(value)

        return value

    def _normalize_date(self, date_str: str) -> str:
        """Normalize date to YYYY-MM-DD format"""
        try:
            from dateutil.parser import parse
            parsed_date = parse(date_str)
            return parsed_date.strftime("%Y-%m-%d")
        except:
            return date_str

    def _calculate_confidence_scores(self, document) -> Dict:
        """Calculate overall confidence metrics"""
        if not document.entities:
            return {"overall": 0.0, "count": 0}

        confidences = [entity.confidence for entity in document.entities]
        return {
            "overall": sum(confidences) / len(confidences),
            "min": min(confidences),
            "max": max(confidences),
            "count": len(confidences)
        }


# Test function
def test_processor():
    """Test the document processor with initialization"""
    try:
        print("🧪 Testing Document Processor...")
        processor = DocumentProcessor()
        print("✅ Document processor test successful!")
        print("🎉 Ready to process documents!")
        return True
    except Exception as e:
        print(f"❌ Document processor test failed: {str(e)}")
        print("💡 Make sure your .env file has correct GCP credentials")
        return False


if __name__ == "__main__":
    test_processor()