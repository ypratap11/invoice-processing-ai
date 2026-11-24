from decimal import Decimal as D
from datetime import date
from audit.normalize import parse_amount, parse_date, norm_text

def test_amount_strict_accepts_plain_decimal():
    assert parse_amount("1250.00", strict=True) == D("1250.00")
def test_amount_strict_rejects_formatted():
    assert parse_amount("$1,250.00", strict=True) is None
def test_amount_lenient_us_and_symbols():
    assert parse_amount("$1,250.00", strict=False) == D("1250.00")
    assert parse_amount("USD 1,250", strict=False) == D("1250")
def test_amount_lenient_european():
    assert parse_amount("1.234,56", strict=False) == D("1234.56")
    assert parse_amount("EUR 1.234,56", strict=False) == D("1234.56")
def test_amount_lenient_parentheses_negative():
    assert parse_amount("(12.00)", strict=False) == D("-12.00")
def test_amount_garbage_is_none():
    assert parse_amount("n/a", strict=False) is None and parse_amount(None, strict=False) is None
def test_date_strict_iso_only():
    assert parse_date("2026-04-03", strict=True) == date(2026, 4, 3)
    assert parse_date("April 3, 2026", strict=True) is None
def test_date_lenient_parses_text():
    assert parse_date("April 3, 2026", strict=False) == date(2026, 4, 3)
def test_date_lenient_ambiguous_is_month_first():
    assert parse_date("03/04/2026", strict=False) == date(2026, 3, 4)
def test_norm_text():
    assert norm_text("  ACME   Corp\n") == "acme corp"
