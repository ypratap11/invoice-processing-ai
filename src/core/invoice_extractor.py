"""Invoice fields from a Document AI Invoice Parser response.

The Invoice Parser returns its results as entities, not tables: header fields
are top-level entities (``supplier_name``, ``total_amount`` ...) and each line
item is a ``line_item`` entity whose ``properties`` are ``line_item/*``
children. ``extract_invoice`` reads both, using each entity's
``normalized_value`` when it carries a typed value (money, number, date) and
the raw ``mention_text`` otherwise.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from google.cloud import documentai

# schema field -> Invoice Parser entity type
HEADER_ENTITIES = {
    "vendor_name": "supplier_name",
    "invoice_id": "invoice_id",
    "invoice_date": "invoice_date",
    "due_date": "due_date",
    "currency": "currency",
    "subtotal": "net_amount",
    "tax_total": "total_tax_amount",
    "total": "total_amount",
}
HEADER_FIELDS = tuple(HEADER_ENTITIES)
LINE_ENTITY = "line_item"
LINE_CHILDREN = {
    "line_item/description": "description",
    "line_item/quantity": "quantity",
    "line_item/unit_price": "unit_price",
    "line_item/amount": "amount",
}
LINE_FIELDS = tuple(LINE_CHILDREN.values())

_MONEY = {"subtotal", "tax_total", "total", "unit_price", "amount"}
_DATES = {"invoice_date", "due_date"}


def _which(nv) -> str | None:
    return type(nv).pb(nv).WhichOneof("structured_value")


def _dec_str(d: Decimal, money: bool) -> str:
    if money and d.as_tuple().exponent > -2:
        d = d.quantize(Decimal("0.01"))
    elif not money:
        d = d.normalize()
    return format(d, "f")


def _number(nv) -> Decimal | None:
    kind = _which(nv)
    if kind == "money_value":
        m = nv.money_value
        return Decimal(m.units) + Decimal(m.nanos) / Decimal(10 ** 9)
    if kind == "float_value":
        # float_value is a 32-bit float (383.8 -> 383.79998779296875); the
        # normalized text carries the exact decimal, so prefer it.
        try:
            return Decimal(nv.text.strip())
        except InvalidOperation:
            return Decimal(f"{nv.float_value:.7g}")
    if kind == "integer_value":
        return Decimal(nv.integer_value)
    return None


def _value(entity, field: str) -> str | None:
    """Normalized value as a plain string when present, else the mention text."""
    if "normalized_value" in entity:
        nv = entity.normalized_value
        if field in _DATES and _which(nv) == "date_value":
            dv = nv.date_value
            try:
                return date(dv.year, dv.month, dv.day).isoformat()
            except ValueError:
                pass
        elif field in _MONEY or field == "quantity":
            n = _number(nv)
            if n is not None:
                return _dec_str(n, money=field in _MONEY)
        elif field == "currency" and nv.text.strip():
            return nv.text.strip()
    text = (entity.mention_text or "").strip()
    return text or None


def _best(entities, field: str):
    """Highest-confidence entity with a value (first one wins a tie)."""
    best, best_val = None, None
    for e in entities:
        v = _value(e, field)
        if v is not None and (best is None or e.confidence > best.confidence):
            best, best_val = e, v
    return best, best_val


def _line(entity) -> tuple[dict, float]:
    by_field: dict[str, list] = {}
    for prop in entity.properties:
        fld = LINE_CHILDREN.get(prop.type_)
        if fld:
            by_field.setdefault(fld, []).append(prop)
    line = dict.fromkeys(LINE_FIELDS)
    for fld, props in by_field.items():
        _, v = _best(props, fld)
        line[fld] = v
    if not by_field and (entity.mention_text or "").strip():
        line["description"] = entity.mention_text.strip()
    # child fields inherit their line's flag: the line's confidence is the
    # line_item entity's own, not its children's
    return line, entity.confidence


def extract_invoice(doc: documentai.Document) -> tuple[dict, dict[str, float]]:
    """Return ``(invoice, confidence)``.

    ``invoice`` has every schema header field (None when not found) and
    ``line_items``: one dict per ``line_item`` entity on any page, in document
    order, with description/quantity/unit_price/amount. ``confidence`` has the
    chosen entity's confidence per found header field and, if there are lines,
    ``line_items`` = the lowest ``line_item`` entity confidence (child fields
    inherit their line's flag; child confidences are not used)."""
    by_type: dict[str, list] = {}
    for e in doc.entities:
        by_type.setdefault(e.type_, []).append(e)

    inv: dict = {}
    conf: dict[str, float] = {}
    for fld, etype in HEADER_ENTITIES.items():
        e, v = _best(by_type.get(etype, []), fld)
        inv[fld] = v
        if e is not None:
            conf[fld] = e.confidence

    if inv["currency"] is None:
        total, _ = _best(by_type.get("total_amount", []), "total")
        if total is not None and _which(total.normalized_value) == "money_value":
            code = total.normalized_value.money_value.currency_code
            if code:
                inv["currency"] = code
                conf["currency"] = total.confidence

    lines, line_confs = [], []
    for e in by_type.get(LINE_ENTITY, []):
        line, c = _line(e)
        lines.append(line)
        line_confs.append(c)
    inv["line_items"] = lines
    if line_confs:
        conf["line_items"] = min(line_confs)
    return inv, conf


def entity_text(doc: documentai.Document, entity_type: str) -> str | None:
    """Mention text of the highest-confidence entity of a type (for display-only
    fields outside the schema, e.g. addresses)."""
    _, v = _best([e for e in doc.entities if e.type_ == entity_type], "")
    return v
