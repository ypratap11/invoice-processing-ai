"""Deterministic consistency checks on an extracted invoice.

``check(inv)`` takes an invoice dict in schema keys (string values, as
``invoice_extractor.extract_invoice`` returns) and lists the reasons it needs
human review; an empty list means every check passed. The checks use only
arithmetic and the invoice's own numbers, so a failure is a fact about the
extraction (or the document), not a model's opinion.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

TOLERANCE = Decimal("0.01")
REQUIRED = ("vendor_name", "invoice_id", "invoice_date", "total")


def _blank(v) -> bool:
    return v is None or str(v).strip() == ""


def _amount(v) -> Decimal | None:
    """Plain or display amount ("1250.00", "$1,250.00", "(5.00)") -> Decimal; None if absent/unparseable."""
    if _blank(v):
        return None
    s = str(v).strip()
    negative = s.startswith("(") and s.endswith(")")
    s = re.sub(r"[^\d.\-]", "", s)
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return -abs(d) if negative else d


def _date(v) -> date | None:
    return date.fromisoformat(str(v).strip())


def check(inv: dict) -> list[str]:
    reasons = [f"missing_required:{f}" for f in REQUIRED if _blank(inv.get(f))]

    dates = {}
    bad = False
    for f in ("invoice_date", "due_date"):
        if _blank(inv.get(f)):
            continue
        try:
            dates[f] = _date(inv[f])
        except ValueError:
            bad = True
    if bad:
        reasons.append("bad_date")
    if len(dates) == 2 and dates["due_date"] < dates["invoice_date"]:
        reasons.append("due_before_invoice")

    lines = [li for li in (inv.get("line_items") or []) if isinstance(li, dict)]
    for li in lines:
        q, p, a = (_amount(li.get(k)) for k in ("quantity", "unit_price", "amount"))
        if None not in (q, p, a) and abs(q * p - a) > TOLERANCE:
            reasons.append("line_math")
            break

    subtotal, tax, total = (_amount(inv.get(k)) for k in ("subtotal", "tax_total", "total"))
    if lines and subtotal is not None:
        # a discount is a line with a negative amount, so a plain sum is right
        line_sum = sum((_amount(li.get("amount")) or Decimal(0) for li in lines), Decimal(0))
        if abs(line_sum - subtotal) > TOLERANCE:
            reasons.append("lines_sum_mismatch")
    if subtotal is not None and total is not None:
        if abs(subtotal + (tax or Decimal(0)) - total) > TOLERANCE:
            reasons.append("total_mismatch")
    return reasons
