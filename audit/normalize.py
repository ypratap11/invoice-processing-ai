"""Strict and lenient parsers for amounts and dates, plus text normalisation."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from dateutil import parser as _dateparser

_STRICT_AMOUNT = re.compile(r"-?\d+(\.\d+)?")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse_amount(s: str | None, strict: bool) -> Decimal | None:
    if s is None:
        return None
    s = str(s).strip()
    if strict:
        return Decimal(s) if _STRICT_AMOUNT.fullmatch(s) else None
    negative = s.startswith("(") and s.endswith(")")
    t = re.sub(r"[^\d.,\-]", "", s)
    if t.startswith("-"):
        negative = True
    t = t.replace("-", "")
    if not re.search(r"\d", t):
        return None
    if "." in t and "," in t:
        dec = "." if t.rfind(".") > t.rfind(",") else ","
        thou = "," if dec == "." else "."
        t = t.replace(thou, "").replace(dec, ".")
    elif "," in t:
        head, _, tail = t.rpartition(",")
        if t.count(",") == 1 and len(tail) == 2:
            t = head + "." + tail
        else:
            t = t.replace(",", "")
    try:
        v = Decimal(t)
    except InvalidOperation:
        return None
    return -v if negative else v


def parse_date(s: str | None, strict: bool) -> date | None:
    if s is None:
        return None
    s = str(s).strip()
    if _ISO_DATE.fullmatch(s):
        try:
            return date.fromisoformat(s)
        except ValueError:
            return None
    if strict:
        return None
    try:
        return _dateparser.parse(s, dayfirst=False).date()
    except (ValueError, OverflowError):
        return None


def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", s.casefold()).strip()
