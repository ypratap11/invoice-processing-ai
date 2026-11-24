"""Invoice/LineItem schema and JSON load/save."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path


@dataclass
class LineItem:
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None


@dataclass
class Invoice:
    vendor_name: str | None = None
    invoice_id: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    currency: str | None = None
    subtotal: Decimal | None = None
    tax_total: Decimal | None = None
    total: Decimal | None = None
    line_items: list[LineItem] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


_DEC_LINE = ("quantity", "unit_price", "amount")
_DEC_INV = ("subtotal", "tax_total", "total")
_DATES = ("invoice_date", "due_date")


def _dec(v):
    return None if v is None else Decimal(v)


def _date(v):
    return None if v is None else date.fromisoformat(v)


def _to_jsonable(inv: Invoice) -> dict:
    d = {
        "vendor_name": inv.vendor_name,
        "invoice_id": inv.invoice_id,
        "currency": inv.currency,
        "tags": list(inv.tags),
    }
    for k in _DATES:
        v = getattr(inv, k)
        d[k] = None if v is None else v.isoformat()
    for k in _DEC_INV:
        v = getattr(inv, k)
        d[k] = None if v is None else str(v)
    d["line_items"] = [
        {
            "description": li.description,
            **{k: (None if getattr(li, k) is None else str(getattr(li, k))) for k in _DEC_LINE},
        }
        for li in inv.line_items
    ]
    return d


def save_invoice(inv: Invoice, path) -> None:
    Path(path).write_text(json.dumps(_to_jsonable(inv), indent=2), encoding="utf-8")


def load_invoice(path) -> Invoice:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    items = [
        LineItem(description=li.get("description"), **{k: _dec(li.get(k)) for k in _DEC_LINE})
        for li in d.get("line_items", [])
    ]
    return Invoice(
        vendor_name=d.get("vendor_name"),
        invoice_id=d.get("invoice_id"),
        currency=d.get("currency"),
        line_items=items,
        tags=list(d.get("tags", [])),
        **{k: _date(d.get(k)) for k in _DATES},
        **{k: _dec(d.get(k)) for k in _DEC_INV},
    )
