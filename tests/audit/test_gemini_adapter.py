"""Gemini runner: response parsing, malformed JSON, cost from usage (offline)."""
import json

import pytest

from audit.runners import gemini


def _resp(payload, **usage):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return {"text": text, "usage": {"prompt_tokens": 1000, "output_tokens": 200,
                                    "thoughts_tokens": 0, **usage}}


def test_adapt_parses_schema_json():
    payload = {"vendor_name": "Acme", "invoice_id": "INV-1", "invoice_date": "2024-01-31",
               "due_date": None, "currency": "USD", "subtotal": "90.00", "tax_total": "10.00",
               "total": "100.00",
               "line_items": [{"description": "Widget", "quantity": "2", "unit_price": "45.00",
                               "amount": "90.00"}]}
    p = gemini.adapt(_resp(payload))
    assert p.error is None and p.flags == set()
    assert p.fields["vendor_name"] == "Acme" and p.fields["total"] == "100.00"
    assert p.fields["due_date"] is None
    assert p.line_items == [{"description": "Widget", "quantity": "2", "unit_price": "45.00",
                             "amount": "90.00"}]


def test_adapt_before_after_are_same():
    assert gemini.adapt_before is gemini.adapt and gemini.adapt_after is gemini.adapt


def test_adapt_malformed_json_is_error():
    p = gemini.adapt(_resp("{not json"))
    assert p.error and p.fields == {} and p.line_items == []


def test_adapt_non_object_is_error():
    assert gemini.adapt(_resp("[1,2]")).error


def test_cost_from_usage():
    # thoughts are billed as output
    c = gemini.cost_from_usage({"prompt_tokens": 1_000_000, "output_tokens": 100_000,
                                "thoughts_tokens": 100_000})
    assert c == pytest.approx(gemini.PRICE_IN + 2 * 0.1 * gemini.PRICE_OUT)


def test_estimate_is_upper_bound(tmp_path):
    p = tmp_path / "a.png"
    p.write_bytes(b"x")
    assert gemini.estimate_cost(p) >= gemini.cost_from_usage(
        {"prompt_tokens": 2000, "output_tokens": 2000, "thoughts_tokens": 0})
