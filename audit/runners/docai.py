"""Document AI runner: the app's own call path, plus adapters to schema keys.

``fetch`` sends the file exactly as the app does (``get_document_ai_client()``,
``config`` processor, ``RawDocument`` + ``ProcessRequest`` on the regional
endpoint) and returns the Document as ``documentai.Document.to_json`` dict.

``adapt_before`` runs the app's ``extract_invoice_data`` unchanged and only
renames keys. Task 5 adds ``adapt_after`` (same ``doc_json -> Prediction``
signature); ``run_audit`` looks adapters up by name, so it is a drop-in.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

from audit.runners.base import Prediction

USD_PER_10_PAGES = 0.10
LOW_CONFIDENCE = 0.7

_MIME = {".pdf": "application/pdf", ".png": "image/png",
         ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}

# Schema field -> the Document AI entity types the app reads into it
# (mirrors the if/elif chain in src/api/main.py::extract_invoice_data).
ENTITY_TYPES = {
    "vendor_name": ("supplier_name", "vendor_name", "remit_to_name"),
    "invoice_id": ("invoice_id", "invoice_number"),
    "invoice_date": ("invoice_date", "invoice_issue_date"),
    "due_date": ("due_date", "payment_due_date"),
    "currency": ("currency",),
    "subtotal": ("net_amount", "subtotal_amount"),
    "tax_total": ("total_tax_amount", "tax_amount"),
    "total": ("total_amount", "invoice_total_amount"),
}

# Fixed table-header keyword map, checked in this order; a header takes the
# first rule with a keyword that is a substring of it (case-insensitive), and
# the first (left-most) column mapped to a field wins.
HEADER_RULES = [
    ("description", ("desc", "item", "product", "service")),
    ("quantity", ("qty", "quantity")),
    ("unit_price", ("unit price", "rate", "price")),
    ("amount", ("amount", "total", "line total")),
]
LINE_FIELDS = ("description", "quantity", "unit_price", "amount")


def mime_type(path: Path) -> str:
    try:
        return _MIME[Path(path).suffix.lower()]
    except KeyError:
        raise ValueError(f"unsupported file type: {path}") from None


def page_count(path: Path) -> int:
    path = Path(path)
    if mime_type(path) == "application/pdf":
        import pypdfium2
        pdf = pypdfium2.PdfDocument(str(path))
        try:
            return len(pdf)
        finally:
            pdf.close()
    return 1


def cost_for_pages(pages: int) -> float:
    """$0.10 per started block of 10 pages."""
    return round(USD_PER_10_PAGES * math.ceil(max(pages, 1) / 10), 2)


def estimate_cost(path: Path) -> float:
    return cost_for_pages(page_count(path))


def _app():
    from src.api import main  # loads .env and the app's config on first import
    return main


@lru_cache(maxsize=1)
def _client():
    client = _app().get_document_ai_client()
    if client is None:
        raise RuntimeError("Document AI client not available (see app log: credentials)")
    return client


def processor_name() -> str:
    cfg = _app().config
    return _client().processor_path(cfg.PROJECT_ID, cfg.LOCATION, cfg.PROCESSOR_ID)


def model_info() -> dict:
    """Processor resource name, its default version and that version's display name."""
    name = processor_name()
    info = {"processor": name, "processor_version": None, "processor_version_display_name": None}
    try:
        proc = _client().get_processor(name=name)
        info["processor_type"] = proc.type_
        info["processor_version"] = proc.default_processor_version
        ver = _client().get_processor_version(name=proc.default_processor_version)
        info["processor_version_display_name"] = ver.display_name
    except Exception as e:  # informational only; never block a run on it
        info["processor_version_error"] = f"{type(e).__name__}: {e}"
    return info


def fetch(path: Path) -> dict:
    """Process one file with the app's processor; return the Document as JSON dict.

    Page images (``pages[].image``) are dropped from the returned dict to keep
    the cache small; no adapter reads them. Charging is done by the run loop
    via ``fetch.cost`` before this is called."""
    from google.cloud import documentai

    path = Path(path)
    raw = documentai.RawDocument(content=path.read_bytes(), mime_type=mime_type(path))
    request = documentai.ProcessRequest(name=processor_name(), raw_document=raw)
    result = _client().process_document(request=request)
    doc = json.loads(documentai.Document.to_json(result.document))
    for page in doc.get("pages", []):
        page.pop("image", None)
    return doc


fetch.cost = estimate_cost


def _document(doc_json: dict):
    from google.cloud import documentai
    return documentai.Document.from_json(json.dumps(doc_json), ignore_unknown_fields=True)


def map_line(row: dict) -> dict:
    out = dict.fromkeys(LINE_FIELDS)
    taken: set[str] = set()
    for header, value in row.items():
        h = str(header).lower()
        for fld, keywords in HEADER_RULES:
            if any(k in h for k in keywords):
                if fld not in taken:
                    out[fld] = value
                    taken.add(fld)
                break  # a header maps to its first matching rule only
    return out


def _low_confidence_flags(document, confidence_scores: dict) -> set[str]:
    """Fields whose source entity (the last entity of a read type, as the app
    overwrites earlier ones) has confidence < LOW_CONFIDENCE."""
    source: dict[str, str] = {}
    for ent in document.entities:
        for fld, types in ENTITY_TYPES.items():
            if ent.type_ in types:
                source[fld] = ent.type_
    return {fld for fld, t in source.items() if confidence_scores.get(t, 1.0) < LOW_CONFIDENCE}


def adapt_before(doc_json: dict) -> Prediction:
    document = _document(doc_json)
    data, conf = _app().extract_invoice_data(document)
    vendor, details = data.get("vendor_info", {}), data.get("invoice_details", {})
    dates, totals = data.get("dates", {}), data.get("totals", {})
    fields = {
        "vendor_name": vendor.get("name"),
        "invoice_id": details.get("invoice_number"),
        "invoice_date": dates.get("invoice_date"),
        "due_date": dates.get("due_date"),
        "currency": totals.get("currency"),
        "subtotal": totals.get("net_amount"),
        "tax_total": totals.get("tax_amount"),
        "total": totals.get("total_amount"),
    }
    return Prediction(doc_id="", fields=fields,
                      line_items=[map_line(r) for r in data.get("line_items", [])],
                      flags=_low_confidence_flags(document, conf))
