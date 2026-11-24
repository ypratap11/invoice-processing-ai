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


# A currency marker before or after the number: a symbol, "Rs"/"Rs." (any
# case) or an upper-case ISO 4217 code ("INR", "USD"), glued or spaced.
_CURRENCY = r"(?:[$€£¥₹]|(?i:rs)\.?|[A-Z]{3})"
_AMOUNT_RE = re.compile(
    rf"^{_CURRENCY}?\s*(?P<num>-?\s*(?:\d{{1,3}}(?:,\d{{2,3}})+|\d+)(?:\.\d+)?|-?\.\d+)\s*{_CURRENCY}?$"
)


class UnparseableAmount(ValueError):
    """An amount is present but is not a number with an optional currency marker."""


def _amount(v) -> Decimal | None:
    """Plain or display amount ("1250.00", "$1,250.00", "Rs.27,376.93", "(5.00)")
    -> Decimal; None if absent. Raises ``UnparseableAmount`` if present but not
    a number, so the caller can flag it instead of skipping the check."""
    if _blank(v):
        return None
    s = str(v).strip()
    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = s[1:-1].strip()
    if s.startswith("-") and not s[1:2].isdigit():  # "-$5.00", "-Rs.5"
        negative, s = True, s[1:].strip()
    m = _AMOUNT_RE.match(s)
    if m is None:
        raise UnparseableAmount(str(v))
    try:
        d = Decimal(re.sub(r"[\s,]", "", m.group("num")))
    except InvalidOperation as e:  # pragma: no cover - the regex admits only numbers
        raise UnparseableAmount(str(v)) from e
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

    unparseable: list[str] = []

    def amount(value, name):
        try:
            return _amount(value)
        except UnparseableAmount:
            unparseable.append(f"unparseable_amount:{name}")
            return None

    raw_lines = inv.get("line_items") or []
    lines = [(i, li) for i, li in enumerate(raw_lines) if isinstance(li, dict)]
    parsed = [(i, tuple(amount(li.get(k), f"line[{i}].{k}") for k in ("quantity", "unit_price", "amount")))
              for i, li in lines]
    for _, (q, p, a) in parsed:
        if None not in (q, p, a) and abs(q * p - a) > TOLERANCE:
            reasons.append("line_math")
            break

    subtotal, tax, total = (amount(inv.get(k), k) for k in ("subtotal", "tax_total", "total"))
    # a sum is only meaningful when every term in it was read; an unreadable
    # term is reported as unparseable_amount instead
    lines_readable = not any(r.startswith("unparseable_amount:line[") and r.endswith(".amount")
                             for r in unparseable)
    if lines and subtotal is not None and lines_readable:
        # a discount is a line with a negative amount, so a plain sum is right
        line_sum = sum((a or Decimal(0) for _, (_, _, a) in parsed), Decimal(0))
        if abs(line_sum - subtotal) > TOLERANCE:
            reasons.append("lines_sum_mismatch")
    tax_readable = "unparseable_amount:tax_total" not in unparseable
    if subtotal is not None and total is not None and tax_readable:
        if abs(subtotal + (tax or Decimal(0)) - total) > TOLERANCE:
            reasons.append("total_mismatch")
    return reasons + unparseable
