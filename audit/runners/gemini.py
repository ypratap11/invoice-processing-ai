"""Gemini runner: a frontier-model comparison against the Document AI path.

``fetch`` sends the document as inline bytes to Gemini on Vertex AI with a JSON
response schema matching the truth schema (all values strings) and returns the
raw JSON text plus usage metadata. Gemini gives no calibrated confidence, so
predictions carry no flags. ``before`` and ``after`` use the same adapter; the
``after`` run differs only by ``invoice_checks`` applied in run_audit.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from audit.runners.base import Prediction
from audit.runners.docai import mime_type, page_count

PROJECT = "augaster-invoice-audit"
# Newest GA Flash model reachable by this project. The regional endpoint
# us-central1 returns 404 for every Gemini model here, so the "global"
# endpoint is used (verified by test calls 2026-11-23).
MODEL = "gemini-3.8-flash"
LOCATION = "global"

# USD per 1M tokens, standard tier, valid through 2026-12-31 (rises to 1.50 / 7.50
# on 2027-01-01). Source: https://aistudio.google.com/docs/pricing (Gemini Developer
# API page, "Gemini 3.8 Flash"), read 2026-11-23; the Vertex AI pricing page did
# not render its tables to the fetcher. Output price includes thinking tokens.
PRICE_IN = 0.75
PRICE_OUT = 3.75

MAX_OUTPUT_TOKENS = 8192
# Conservative upper bounds used to price a call before it is made.
EST_TOKENS_PER_PAGE = 2000
EST_PROMPT_TOKENS = 800

PROMPT = """You are extracting data from an invoice document. Return one JSON object matching the response schema.

Rules:
- Dates: ISO format YYYY-MM-DD.
- Numbers (subtotal, tax_total, total, quantity, unit_price, amount): plain decimal numbers as strings, no currency symbols, no thousands separators, '.' as the decimal mark (e.g. "1234.50").
- currency: the ISO 4217 code (e.g. "USD", "EUR", "GBP").
- Discounts and credits: output them as separate line items with a negative amount.
- vendor_name, invoice_id and line item descriptions: copy exactly as printed.
- tax_total is the total tax amount; total is the final amount due/payable.
- Use null for any value that is not present on the document. Do not guess or compute missing values.
- List every line item in document order."""

_STR = {"type": "STRING", "nullable": True}
RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        **{k: _STR for k in ("vendor_name", "invoice_id", "invoice_date", "due_date",
                             "currency", "subtotal", "tax_total", "total")},
        "line_items": {
            "type": "ARRAY",
            "items": {"type": "OBJECT",
                      "properties": {k: _STR for k in
                                     ("description", "quantity", "unit_price", "amount")}},
        },
    },
}
HEADER_FIELDS = ("vendor_name", "invoice_id", "invoice_date", "due_date",
                 "currency", "subtotal", "tax_total", "total")
LINE_FIELDS = ("description", "quantity", "unit_price", "amount")


def cost_from_usage(usage: dict) -> float:
    out = (usage.get("output_tokens") or 0) + (usage.get("thoughts_tokens") or 0)
    return ((usage.get("prompt_tokens") or 0) * PRICE_IN + out * PRICE_OUT) / 1e6


def estimate_cost(path: Path) -> float:
    """Upper bound: generous input tokens per page plus the full output cap."""
    pages = page_count(path)
    tin = EST_PROMPT_TOKENS + EST_TOKENS_PER_PAGE * pages
    return math.ceil(cost_from_usage({"prompt_tokens": tin, "output_tokens": MAX_OUTPUT_TOKENS})
                     * 1e4) / 1e4


_CLIENT = None


def _client():
    """One shared client, kept referenced (a temporary client is closed on GC)."""
    global _CLIENT
    if _CLIENT is None:
        from google import genai
        _CLIENT = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
    return _CLIENT


def model_info() -> dict:
    return {"model": MODEL, "location": LOCATION, "project": PROJECT,
            "price_in_per_1m": PRICE_IN, "price_out_per_1m": PRICE_OUT}


def fetch(path: Path) -> dict:
    from google.genai import types

    path = Path(path)
    resp = _client().models.generate_content(
        model=MODEL,
        contents=[types.Part.from_bytes(data=path.read_bytes(), mime_type=mime_type(path)),
                  PROMPT],
        config=types.GenerateContentConfig(
            temperature=0, max_output_tokens=MAX_OUTPUT_TOKENS,
            response_mime_type="application/json", response_schema=RESPONSE_SCHEMA))
    u = resp.usage_metadata
    usage = {"prompt_tokens": u.prompt_token_count or 0,
             "output_tokens": u.candidates_token_count or 0,
             "thoughts_tokens": getattr(u, "thoughts_token_count", 0) or 0}
    return {"text": resp.text, "usage": usage, "cost_usd": cost_from_usage(usage),
            "model": MODEL}


def priced_cost(path: Path) -> float:
    """Pre-call price; builds the client first so missing credentials raise
    before the ledger is charged."""
    _client()
    return estimate_cost(path)


fetch.cost = priced_cost


def adapt(resp: dict) -> Prediction:
    try:
        data = json.loads(resp["text"])
    except (TypeError, ValueError, KeyError) as e:
        return Prediction(doc_id="", error=f"malformed JSON from Gemini: {e}")
    if not isinstance(data, dict):
        return Prediction(doc_id="", error="malformed JSON from Gemini: not an object")
    lines = data.get("line_items") or []
    return Prediction(
        doc_id="",
        fields={f: data.get(f) for f in HEADER_FIELDS},
        line_items=[{f: li.get(f) for f in LINE_FIELDS} for li in lines if isinstance(li, dict)])


adapt_before = adapt_after = adapt
