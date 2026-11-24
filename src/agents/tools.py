from langchain.tools import BaseTool
from typing import Optional, Type
from pydantic import BaseModel, Field
import json
import time
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session
from src.database import (
    get_db, save_invoice_to_db, search_invoices_by_vendor,
    get_recent_invoices, get_invoices_by_amount_range, SessionLocal
)


class InvoiceProcessingInput(BaseModel):
    file_path: str = Field(description="Path to the invoice file to process")


class InvoiceProcessingTool(BaseTool):
    name = "process_invoice"
    description = "Process uploaded invoice files using Google Document AI. Returns extracted vendor info, amounts, dates, and line items with confidence scores."
    args_schema: Type[BaseModel] = InvoiceProcessingInput

    def _run(self, file_path: str) -> str:
        try:
            # Same path as the /process-invoice endpoint: one Document AI call,
            # entity-based extraction, deterministic checks.
            from src.api.main import MIME_TYPES, process_invoice_bytes

            path = Path(file_path)
            mime_type = MIME_TYPES.get(path.suffix.lower())
            if mime_type is None:
                return f"❌ Unsupported file type: {path.suffix or '(none)'}"
            start = time.perf_counter()
            out = process_invoice_bytes(path.read_bytes(), mime_type)
            processing_time = round(time.perf_counter() - start, 3)
            inv = out["invoice"]
            result = {
                "filename": path.name,
                "invoice": inv,
                "confidence_scores": out["confidence_scores"],
                "review_required": out["review_required"],
                "review_reasons": out["review_reasons"],
                "processing_time": processing_time,
            }

            # Save to database (columns: total_amount Float, invoice_date DateTime)
            db = SessionLocal()
            try:
                saved = save_invoice_to_db({
                    "filename": path.name,
                    "vendor_name": inv["vendor_name"],
                    "total_amount": _as_float(inv["total"]),
                    "invoice_date": _as_datetime(inv["invoice_date"]),
                    "invoice_number": inv["invoice_id"],
                    "line_items": inv["line_items"],
                    "confidence_scores": out["confidence_scores"],
                    "raw_extraction": out["extracted_data"],
                    "processing_time": processing_time,
                }, db)
                result["database_id"] = saved.id
            except Exception as e:
                result["database_error"] = str(e)
            finally:
                db.close()

            return json.dumps(result, indent=2, ensure_ascii=False)

        except Exception as e:
            return f"❌ Error processing invoice: {str(e)}"


def _as_float(value):
    """Plain decimal string from the extractor -> float; None if absent/not numeric."""
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _as_datetime(value):
    """ISO date from the extractor -> datetime; None if absent/not ISO."""
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


class InvoiceSearchInput(BaseModel):
    query: str = Field(description="Search query for invoices (vendor name, amount range, etc.)")


class InvoiceSearchTool(BaseTool):
    name = "search_invoices"
    description = "Search processed invoices by vendor name, amount range, or other criteria. Use natural language queries like 'invoices from Acme' or 'invoices over 1000 dollars'."
    args_schema: Type[BaseModel] = InvoiceSearchInput

    def _run(self, query: str) -> str:
        try:
            db = SessionLocal()
            results = []

            # Simple query parsing
            query_lower = query.lower()

            if "over" in query_lower or "above" in query_lower:
                # Extract amount for range search
                import re
                amount_match = re.search(r'(\d+(?:\.\d{2})?)', query)
                if amount_match:
                    min_amount = float(amount_match.group(1))
                    results = get_invoices_by_amount_range(min_amount, 999999, db)

            elif "from" in query_lower:
                # Extract vendor name
                vendor_part = query_lower.split("from")[-1].strip()
                vendor_name = vendor_part.split()[0] if vendor_part.split() else ""
                results = search_invoices_by_vendor(vendor_name, db)

            else:
                # Default to recent invoices
                results = get_recent_invoices(10, db)

            db.close()

            if not results:
                return "❌ No invoices found matching your criteria."

            # Format results
            response = f"📋 Found {len(results)} invoice(s):\n\n"
            total_value = 0

            for inv in results[:5]:  # Limit to 5 for readability
                response += f"• **{inv.vendor_name}** - ${inv.total_amount:,.2f} ({inv.invoice_date.strftime('%Y-%m-%d')})\n"
                total_value += inv.total_amount or 0

            if len(results) > 5:
                response += f"... and {len(results) - 5} more\n"

            response += f"\n💰 **Total Value:** ${total_value:,.2f}"

            return response

        except Exception as e:
            return f"❌ Error searching invoices: {str(e)}"


class InvoiceAnalyticsInput(BaseModel):
    period: str = Field(description="Time period for analytics (this month, this quarter, etc.)")


class InvoiceAnalyticsTool(BaseTool):
    name = "analyze_invoices"
    description = "Analyze invoice data and provide insights like spending trends, top vendors, average amounts, etc."
    args_schema: Type[BaseModel] = InvoiceAnalyticsInput

    def _run(self, period: str = "this month") -> str:
        try:
            db = SessionLocal()

            # Get all invoices for analysis
            all_invoices = get_recent_invoices(100, db)
            db.close()

            if not all_invoices:
                return "❌ No invoice data available for analysis."

            # Basic analytics
            total_amount = sum(inv.total_amount or 0 for inv in all_invoices)
            avg_amount = total_amount / len(all_invoices) if all_invoices else 0

            # Top vendors
            vendor_totals = {}
            for inv in all_invoices:
                vendor = inv.vendor_name or "Unknown"
                vendor_totals[vendor] = vendor_totals.get(vendor, 0) + (inv.total_amount or 0)

            top_vendors = sorted(vendor_totals.items(), key=lambda x: x[1], reverse=True)[:3]

            response = f"""📊 **Invoice Analytics** ({period})

**Summary:**
• Total Invoices: {len(all_invoices)}
• Total Amount: ${total_amount:,.2f}
• Average Amount: ${avg_amount:,.2f}

**Top Vendors:**"""

            for i, (vendor, amount) in enumerate(top_vendors, 1):
                response += f"\n{i}. {vendor}: ${amount:,.2f}"

            # Simple insights
            if avg_amount > 1000:
                response += "\n\n💡 **Insight:** High average invoice value - consider bulk purchase negotiations"

            if len(set(inv.vendor_name for inv in all_invoices)) < len(all_invoices) * 0.5:
                response += "\n💡 **Insight:** Vendor consolidation opportunity detected"

            return response

        except Exception as e:
            return f"❌ Error analyzing invoices: {str(e)}"


# Tool registry for easy access
AVAILABLE_TOOLS = [
    InvoiceProcessingTool(),
    InvoiceSearchTool(),
    InvoiceAnalyticsTool()
]