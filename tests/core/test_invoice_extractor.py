"""Entity-based invoice extraction from a Document AI Invoice Parser response (offline)."""
import json
from pathlib import Path

import pytest
from google.cloud import documentai

from src.core.invoice_extractor import extract_invoice

FIXTURE = Path(__file__).parent / "fixtures" / "docai_multipage.json"
REPO = Path(__file__).resolve().parents[2]


def _doc(mutate=None) -> documentai.Document:
    d = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if mutate:
        mutate(d)
    return documentai.Document.from_json(json.dumps(d), ignore_unknown_fields=True)


def test_line_items_across_pages():
    inv, conf = extract_invoice(_doc())
    assert inv["line_items"] == [
        {"description": "A4 paper ream", "quantity": "10", "unit_price": "4.50", "amount": "45.00"},
        {"description": "Staples box", "quantity": "2", "unit_price": "3.25", "amount": "6.50"},
        {"description": "Toner cartridge", "quantity": "1", "unit_price": "1198.50",
         "amount": "1198.50"},
    ]
    # children inherit their line's flag: confidence is the line entity's own
    assert conf["line_items"] == pytest.approx(1.0)


def test_line_items_confidence_is_min_of_line_entities_not_children():
    def f(d):
        lines = [e for e in d["entities"] if e["type"] == "line_item"]
        lines[0]["properties"][1]["confidence"] = 0.05  # a child: ignored
        lines[2]["confidence"] = 0.62                    # a line entity: counts
    _, conf = extract_invoice(_doc(f))
    assert conf["line_items"] == pytest.approx(0.62)


def test_uses_normalized_values():
    inv, _ = extract_invoice(_doc())
    assert inv["total"] == "1250.00"          # mention "$1,250.00", moneyValue 1250
    assert inv["subtotal"] == "1250.00"
    assert inv["tax_total"] == "0.00"
    assert inv["invoice_date"] == "2026-04-03"  # mention "03/04/2026"
    assert inv["due_date"] == "2026-05-04"
    assert inv["currency"] == "USD"            # mention "$", normalized "USD"
    assert inv["invoice_id"] == "INV-7731"


def test_falls_back_to_mention_text_without_normalized_value():
    def strip(d):
        for e in d["entities"]:
            if e["type"] == "total_amount":
                e.pop("normalizedValue")
    inv, _ = extract_invoice(_doc(strip))
    assert inv["total"] == "$1,250.00"


def test_currency_from_total_money_when_no_currency_entity():
    def drop(d):
        d["entities"] = [e for e in d["entities"] if e["type"] != "currency"]
        for e in d["entities"]:
            if e["type"] == "total_amount":
                e["normalizedValue"]["moneyValue"]["currencyCode"] = "EUR"
    inv, _ = extract_invoice(_doc(drop))
    assert inv["currency"] == "EUR"


def test_repeated_entity_does_not_overwrite_header():
    inv, conf = extract_invoice(_doc())
    # two supplier_name entities (0.41 first, 0.88 later): the higher-confidence one wins
    assert inv["vendor_name"] == "Northwind Paper Co."
    assert conf["vendor_name"] == pytest.approx(0.88)


def test_absent_fields_are_none():
    def drop(d):
        d["entities"] = [e for e in d["entities"] if e["type"] != "due_date"]
    inv, conf = extract_invoice(_doc(drop))
    assert inv["due_date"] is None and "due_date" not in conf


def test_float_money_is_padded_to_cents():
    # real responses carry money as floatValue (e.g. 383.8 for "383.80")
    def f(d):
        for e in d["entities"]:
            if e["type"] == "total_amount":
                e["normalizedValue"] = {"text": "383.8", "floatValue": 383.8}
    inv, _ = extract_invoice(_doc(f))
    assert inv["total"] == "383.80"


def test_agent_tool_has_no_sample_data():
    assert "Acme Corporation" not in (REPO / "src" / "agents" / "tools.py").read_text(encoding="utf-8")


def test_old_document_processor_removed():
    assert not (REPO / "src" / "core" / "document_processor.py").exists()
