"""Strict and lenient parsers for amounts and dates, plus text normalisation."""
from __future__ import annotations

import re
from datetime import date, datetime
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
    # strip currency symbols/codes (letters and non-numeric symbols) first
    core = re.sub(r"[^\d.,\-()]", "", s)
    negative = False
    m = re.fullmatch(r"\(([^()]*)\)", core)
    if m:
        negative, core = True, m.group(1)
    if core.startswith("-"):
        negative, core = True, core[1:]
    elif core.endswith("-"):
        negative, core = True, core[:-1]
    t = core
    if "-" in t or "(" in t or ")" in t:
        return None
    if re.search(r"[A-Za-z]-", s) or re.search(r"\d[A-Za-z]", s):
        return None  # identifiers like INV-1234, not amounts
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
        a = _dateparser.parse(s, dayfirst=False, default=datetime(2001, 1, 1)).date()
        b = _dateparser.parse(s, dayfirst=False, default=datetime(2002, 2, 2)).date()
    except (ValueError, OverflowError):
        return None
    return a if a == b else None


def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", s.casefold()).strip()
