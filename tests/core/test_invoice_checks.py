"""Deterministic invoice consistency checks."""
import copy

from src.core.invoice_checks import check

CLEAN = {
    "vendor_name": "Northwind Paper Co.",
    "invoice_id": "INV-7731",
    "invoice_date": "2026-04-03",
    "due_date": "2026-05-03",
    "currency": "USD",
    "subtotal": "100.00",
    "tax_total": "8.00",
    "total": "108.00",
    "line_items": [
        {"description": "Paper", "quantity": "10", "unit_price": "4.50", "amount": "45.00"},
        {"description": "Toner", "quantity": "1", "unit_price": "60.00", "amount": "60.00"},
        {"description": "Discount", "quantity": None, "unit_price": None, "amount": "-5.00"},
    ],
}


def _with(**kw):
    inv = copy.deepcopy(CLEAN)
    inv.update(kw)
    return inv


def test_checks_clean_invoice_passes():
    assert check(CLEAN) == []


def test_checks_total_mismatch():
    bad_total = _with(total="118.00")
    assert "total_mismatch" in check(bad_total)


def test_checks_total_within_a_cent_passes():
    assert "total_mismatch" not in check(_with(total="108.01"))


def test_checks_lines_sum_mismatch():
    inv = copy.deepcopy(CLEAN)
    inv["line_items"] = inv["line_items"][:2]  # discount line lost: 105 != 100
    assert "lines_sum_mismatch" in check(inv)


def test_lines_sum_skipped_without_lines_or_subtotal():
    assert "lines_sum_mismatch" not in check(_with(line_items=[]))
    assert "lines_sum_mismatch" not in check(_with(subtotal=None, total="8.00"))


def test_checks_line_math():
    inv = copy.deepcopy(CLEAN)
    inv["line_items"][0]["amount"] = "54.00"
    inv["subtotal"], inv["total"] = "109.00", "117.00"
    assert check(inv) == ["line_math"]


def test_checks_missing_required():
    no_id = _with(invoice_id=None)
    assert "missing_required:invoice_id" in check(no_id)
    reasons = check(_with(vendor_name="  ", total=None, invoice_date=None))
    assert {"missing_required:vendor_name", "missing_required:total",
            "missing_required:invoice_date"} <= set(reasons)


def test_checks_due_before_invoice():
    assert "due_before_invoice" in check(_with(due_date="2026-04-02"))
    assert "due_before_invoice" not in check(_with(due_date="2026-04-03"))


def test_checks_bad_date():
    assert "bad_date" in check(_with(invoice_date="03/04/2026"))
    assert "bad_date" in check(_with(due_date="2026-02-30"))


def test_amounts_with_symbols_and_commas_are_parsed():
    inv = _with(subtotal="$1,000.00", tax_total="0", total="1,000.00",
                line_items=[{"description": "x", "quantity": "1", "unit_price": "1000",
                             "amount": "$1,000.00"}])
    assert check(inv) == []
