"""The app's original extraction, frozen for the audit's "before" adapter.

``extract_invoice_data`` below is a verbatim copy of
``src/api/main.py::extract_invoice_data`` at commit 1df4af9 (the code the
"before" run measured). The app now uses ``src.core.invoice_extractor``;
this copy keeps ``adapt_before`` reproducible. Do not edit.
"""
from typing import Any, Dict

from google.cloud import documentai


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
