"""Field-level scoring of a raw prediction against a truth Invoice.

The rules in this module decide every published accuracy number. They are
frozen by the git tag ``audit-scoring-frozen``; changing them after the tag
invalidates comparisons with earlier results.

Statuses:
  correct  - prediction parses and matches truth under the mode's rule
  wrong    - prediction is present (non-blank) but unparseable or not equal
  missing  - prediction absent, None, or blank, or a truth line item that no
             predicted line was aligned to
Silent error = status ``wrong`` and not flagged. ``missing`` is never silent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

import numpy as np
from rapidfuzz import fuzz
from scipy.optimize import linear_sum_assignment

from audit.normalize import norm_text, parse_amount, parse_date
from audit.schema import Invoice

HEADER_FIELDS = ["vendor_name", "invoice_id", "invoice_date", "due_date",
                 "currency", "subtotal", "tax_total", "total"]
LINE_FIELDS = ["description", "quantity", "unit_price", "amount"]

_AMOUNT_FIELDS = {"subtotal", "tax_total", "total", "quantity", "unit_price", "amount"}
_DATE_FIELDS = {"invoice_date", "due_date"}

VENDOR_LENIENT_MIN = 90       # token_set_ratio for lenient vendor match
LINE_MATCH_MIN = 60           # below this an aligned pair is treated as unmatched
DESCRIPTION_MATCH_MIN = 85    # token_set_ratio for a correct line description

Status = Literal["correct", "wrong", "missing"]
Mode = Literal["strict", "lenient"]


@dataclass
class FieldResult:
    field: str
    status: Status
    flagged: bool


class ScoreResult(list):
    """list[FieldResult] that also carries ``extra_lines`` (predicted line
    items not aligned to any truth line)."""

    extra_lines: int = 0


def _sim(a, b) -> float:
    if a is None or b is None:
        return 0.0
    return fuzz.token_set_ratio(norm_text(str(a)), norm_text(str(b)))


def _blank(v) -> bool:
    return v is None or str(v).strip() == ""


def _compare(field: str, truth, pred, mode: Mode) -> Status:
    if _blank(pred):
        return "missing"
    strict = mode == "strict"
    p = str(pred)
    if field in _AMOUNT_FIELDS:
        v = parse_amount(p, strict=strict)
        # Decimal equality: "1250" == "1250.00"; 1250.001 != 1250.00 (to the cent and exact)
        ok = v is not None and v == truth
    elif field in _DATE_FIELDS:
        v = parse_date(p, strict=strict)
        ok = v is not None and v == truth
    elif field == "invoice_id":
        if strict:
            ok = p.strip() == str(truth).strip()
        else:
            ok = norm_text(p).replace(" ", "") == norm_text(str(truth)).replace(" ", "")
    elif field == "vendor_name":
        if strict:
            ok = norm_text(p) == norm_text(str(truth))
        else:
            ok = _sim(p, truth) >= VENDOR_LENIENT_MIN
    elif field == "currency":
        c = p.strip().upper()
        ok = re.fullmatch(r"[A-Z]{3}", c) is not None and c == str(truth).strip().upper()
    elif field == "description":
        # one rule for both modes (brief specifies only the fuzzy threshold)
        ok = _sim(p, truth) >= DESCRIPTION_MATCH_MIN
    else:  # pragma: no cover - unknown field is a programming error
        raise ValueError(f"no scoring rule for field {field!r}")
    return "correct" if ok else "wrong"


def score_invoice(truth: Invoice, pred: dict | None, mode: Mode,
                  flags: set[str], invoice_flagged: bool) -> ScoreResult:
    """Score one document. ``pred`` holds string values as the runner produced
    them; an empty/None ``pred`` (runner failure) yields ``missing`` for every
    truth field. Truth fields that are None (e.g. an invoice with no due date)
    are excluded from scoring entirely: they count as neither correct nor
    missing, whatever the prediction says."""
    if mode not in ("strict", "lenient"):
        raise ValueError(f"mode must be 'strict' or 'lenient', got {mode!r}")
    pred = pred or {}
    flags = set(flags or ())
    out = ScoreResult()

    for f in HEADER_FIELDS:
        t = getattr(truth, f)
        if t is None:
            continue  # truth absent: excluded from scoring
        out.append(FieldResult(f, _compare(f, t, pred.get(f), mode),
                               invoice_flagged or f in flags))

    truth_lines = truth.line_items or []
    pred_lines = [p for p in (pred.get("line_items") or []) if isinstance(p, dict)]
    match: dict[int, int] = {}
    if truth_lines and pred_lines:
        sim = np.array([[_sim(tl.description, pl.get("description")) for pl in pred_lines]
                        for tl in truth_lines], dtype=float)
        rows, cols = linear_sum_assignment(100.0 - sim)
        match = {int(r): int(c) for r, c in zip(rows, cols) if sim[r, c] >= LINE_MATCH_MIN}
    out.extra_lines = len(pred_lines) - len(match)

    line_flag = invoice_flagged or "line_items" in flags
    for i, tl in enumerate(truth_lines):
        pl = pred_lines[match[i]] if i in match else None
        for k in LINE_FIELDS:
            t = getattr(tl, k)
            if t is None:
                continue  # truth absent: excluded from scoring
            name = f"line[{i}].{k}"
            status = "missing" if pl is None else _compare(k, t, pl.get(k), mode)
            out.append(FieldResult(name, status, line_flag or name in flags))
    return out


def _generic(field: str) -> str:
    m = re.fullmatch(r"line\[\d+\]\.(\w+)", field)
    return f"line.{m.group(1)}" if m else field


def aggregate(results: dict) -> dict:
    """Aggregate per-document results.

    - field_accuracy: correct / scored per field; line-item fields are pooled
      across lines as ``line.description`` etc. Missing counts as not correct.
    - invoice_fully_correct_pct: percent (0-100) of docs where every scored
      field is correct and no extra predicted lines exist.
    - silent_errors / missing: {"count", "rate"}, rate over all scored fields.
    - review_rate: fraction (0-1) of docs with any flagged field.
    - extra_lines: total predicted line items not aligned to a truth line.
    """
    n_docs = len(results)
    per_field: dict[str, list[int]] = {}
    total_fields = silent = missing = fully = reviewed = extra = 0
    for res in results.values():
        doc_extra = getattr(res, "extra_lines", 0)
        extra += doc_extra
        if any(r.flagged for r in res):
            reviewed += 1
        if doc_extra == 0 and all(r.status == "correct" for r in res):
            fully += 1
        for r in res:
            total_fields += 1
            c = per_field.setdefault(_generic(r.field), [0, 0])
            c[1] += 1
            if r.status == "correct":
                c[0] += 1
            elif r.status == "missing":
                missing += 1
            elif r.status == "wrong" and not r.flagged:
                silent += 1
    rate = (lambda x: x / total_fields) if total_fields else (lambda x: 0.0)
    return {
        "field_accuracy": {f: ok / n for f, (ok, n) in per_field.items()},
        "invoice_fully_correct_pct": 100.0 * fully / n_docs if n_docs else 0.0,
        "silent_errors": {"count": silent, "rate": rate(silent)},
        "missing": {"count": missing, "rate": rate(missing)},
        "review_rate": reviewed / n_docs if n_docs else 0.0,
        "extra_lines": extra,
        "n_docs": n_docs,
    }
