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


def test_rupee_amounts_parse_and_line_math_still_runs():
    # quantity misread as 5050 (truth 50) on an invoice whose money fields are all "Rs."
    inv = {
        "vendor_name": "Example Couriers",
        "invoice_id": "CN-1",
        "invoice_date": "2026-01-04",
        "subtotal": "Rs.24,461.23",
        "tax_total": "Rs.0.00",
        "total": "Rs.24,461.23",
        "line_items": [
            {"description": "Return", "quantity": "1", "unit_price": "Rs.23.23", "amount": "Rs.23.23"},
            {"description": "Express", "quantity": "5050", "unit_price": "Rs.488.76",
             "amount": "Rs.24,438.00"},
        ],
    }
    assert check(inv) == ["line_math"]
    inv["line_items"][1]["quantity"] = "50"
    assert check(inv) == []


def test_currency_codes_and_symbols_are_stripped():
    from decimal import Decimal
    from src.core.invoice_checks import _amount

    assert _amount("Rs.27,376.93") == Decimal("27376.93")
    assert _amount("Rs 27,376.93") == Decimal("27376.93")
    assert _amount("₹27,376.93") == Decimal("27376.93")
    assert _amount("INR 1,000.50") == Decimal("1000.50")
    assert _amount("USD1,000.50") == Decimal("1000.50")
    assert _amount("€ 12.00") == Decimal("12.00")
    assert _amount("$1,250.00") == Decimal("1250.00")
    assert _amount("(5.00)") == Decimal("-5.00")
    assert _amount("27,376.93 Rs.") == Decimal("27376.93")
    assert _amount("-$5.00") == Decimal("-5.00")
    assert _amount("-5.00") == Decimal("-5.00")


def test_unparseable_amount_is_flagged_not_skipped():
    inv = _with(total="12.34.56")
    assert "unparseable_amount:total" in check(inv)
    inv = copy.deepcopy(CLEAN)
    inv["line_items"][2]["amount"] = "five dollars"
    assert "unparseable_amount:line[2].amount" in check(inv)
