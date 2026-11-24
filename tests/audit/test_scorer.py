from datetime import date
from decimal import Decimal as D

from audit.schema import Invoice, LineItem
from audit.scorer import HEADER_FIELDS, FieldResult, aggregate, score_invoice


def make_truth(**over):
    kw = dict(
        vendor_name="Acme Corporation",
        invoice_id="INV-1001",
        invoice_date=date(2026, 4, 3),
        due_date=date(2026, 5, 3),
        currency="USD",
        subtotal=D("1000.00"),
        tax_total=D("250.00"),
        total=D("1250.00"),
        line_items=[LineItem("Software License", D("1"), D("1000.00"), D("1000.00"))],
    )
    kw.update(over)
    return Invoice(**kw)


T = make_truth()

T2 = make_truth(
    subtotal=D("1500.00"),
    tax_total=D("0.00"),
    total=D("1500.00"),
    line_items=[
        LineItem("Software License", D("1"), D("1000.00"), D("1000.00")),
        LineItem("Onsite Training Day", D("2"), D("250.00"), D("500.00")),
    ],
)


def stringify(inv: Invoice) -> dict:
    """Truth -> prediction dict with string values, as a runner would emit."""
    d = {}
    for f in HEADER_FIELDS:
        v = getattr(inv, f)
        d[f] = None if v is None else (v.isoformat() if isinstance(v, date) else str(v))
    d["line_items"] = [
        {k: (None if getattr(li, k) is None else str(getattr(li, k)))
         for k in ("description", "quantity", "unit_price", "amount")}
        for li in inv.line_items
    ]
    return d


def by_field(results):
    return {r.field: r for r in results}


P = stringify(T)
P_wrong_total = {**P, "total": "999.00"}


def test_exact_prediction_all_correct():
    for mode in ("strict", "lenient"):
        res = score_invoice(T, P, mode, set(), False)
        r = by_field(res)
        assert set(r) == set(HEADER_FIELDS) | {
            "line[0].description", "line[0].quantity", "line[0].unit_price", "line[0].amount"}
        assert all(x.status == "correct" for x in res), res
        assert not any(x.flagged for x in res)


def test_wrong_unflagged_total_is_silent():
    res = score_invoice(T, P_wrong_total, "lenient", set(), False)
    r = by_field(res)
    assert r["total"].status == "wrong" and not r["total"].flagged
    agg = aggregate({"d1": res})
    assert agg["silent_errors"]["count"] == 1
    assert agg["silent_errors"]["rate"] == 1 / len(res)


def test_low_confidence_flag_makes_error_not_silent():
    res = score_invoice(T, P_wrong_total, "lenient", {"total"}, False)
    r = by_field(res)
    assert r["total"].status == "wrong" and r["total"].flagged
    assert not r["subtotal"].flagged
    assert aggregate({"d1": res})["silent_errors"]["count"] == 0


def test_invoice_flag_covers_all_fields():
    res = score_invoice(T, P_wrong_total, "lenient", set(), True)
    assert res and all(x.flagged for x in res)
    assert aggregate({"d1": res})["silent_errors"]["count"] == 0


def test_missing_is_not_silent():
    pred = {k: v for k, v in P.items() if k != "due_date"}
    res = score_invoice(T, pred, "lenient", set(), False)
    r = by_field(res)
    assert r["due_date"].status == "missing"
    agg = aggregate({"d1": res})
    assert agg["silent_errors"]["count"] == 0
    assert agg["missing"]["count"] == 1


def test_null_and_blank_prediction_is_missing():
    res = by_field(score_invoice(T, {**P, "due_date": None, "total": "  "}, "strict", set(), False))
    assert res["due_date"].status == "missing"
    assert res["total"].status == "missing"


def test_unparseable_prediction_is_wrong():
    res = by_field(score_invoice(T, {**P, "total": "n/a"}, "lenient", set(), False))
    assert res["total"].status == "wrong"


def test_empty_prediction_all_missing():
    for pred in ({}, None):
        res = score_invoice(T2, pred, "lenient", set(), False)
        assert len(res) == len(HEADER_FIELDS) + 8
        assert all(x.status == "missing" for x in res)
        assert aggregate({"d1": res})["silent_errors"]["count"] == 0


def test_truth_none_field_excluded():
    t = make_truth(due_date=None)
    res = score_invoice(t, {**P, "due_date": "2026-05-03"}, "strict", set(), False)
    assert "due_date" not in by_field(res)
    res = score_invoice(t, {k: v for k, v in P.items() if k != "due_date"}, "strict", set(), False)
    assert "due_date" not in by_field(res)
    agg = aggregate({"d1": res})
    assert agg["missing"]["count"] == 0
    assert agg["invoice_fully_correct_pct"] == 100.0


def test_strict_rejects_formatted_amount_lenient_accepts():
    pred = {**P, "total": "$1,250.00"}
    assert by_field(score_invoice(T, pred, "strict", set(), False))["total"].status == "wrong"
    assert by_field(score_invoice(T, pred, "lenient", set(), False))["total"].status == "correct"


def test_amounts_equal_to_the_cent():
    assert by_field(score_invoice(T, {**P, "total": "1250"}, "strict", set(), False))["total"].status == "correct"
    assert by_field(score_invoice(T, {**P, "total": "1250.01"}, "lenient", set(), False))["total"].status == "wrong"


def test_dates_strict_iso_lenient_text():
    pred = {**P, "invoice_date": "April 3, 2026"}
    assert by_field(score_invoice(T, pred, "strict", set(), False))["invoice_date"].status == "wrong"
    assert by_field(score_invoice(T, pred, "lenient", set(), False))["invoice_date"].status == "correct"


def test_invoice_id_rules():
    pred = {**P, "invoice_id": "  INV-1001 "}
    assert by_field(score_invoice(T, pred, "strict", set(), False))["invoice_id"].status == "correct"
    pred = {**P, "invoice_id": "inv - 1001"}
    assert by_field(score_invoice(T, pred, "strict", set(), False))["invoice_id"].status == "wrong"
    assert by_field(score_invoice(T, pred, "lenient", set(), False))["invoice_id"].status == "correct"


def test_vendor_fuzzy_lenient_only():
    pred = {**P, "vendor_name": "ACME Corporation Inc."}
    assert by_field(score_invoice(T, pred, "strict", set(), False))["vendor_name"].status == "wrong"
    assert by_field(score_invoice(T, pred, "lenient", set(), False))["vendor_name"].status == "correct"
    pred = {**P, "vendor_name": "  ACME   corporation "}
    assert by_field(score_invoice(T, pred, "strict", set(), False))["vendor_name"].status == "correct"
    pred = {**P, "vendor_name": "Globex Industries"}
    assert by_field(score_invoice(T, pred, "lenient", set(), False))["vendor_name"].status == "wrong"


def test_currency_upper_three_letter():
    assert by_field(score_invoice(T, {**P, "currency": " usd "}, "strict", set(), False))["currency"].status == "correct"
    assert by_field(score_invoice(T, {**P, "currency": "$"}, "lenient", set(), False))["currency"].status == "wrong"
    assert by_field(score_invoice(T, {**P, "currency": "EUR"}, "lenient", set(), False))["currency"].status == "wrong"


def test_line_items_aligned_out_of_order():
    pred = stringify(T2)
    pred["line_items"] = list(reversed(pred["line_items"]))
    res = score_invoice(T2, pred, "strict", set(), False)
    assert all(x.status == "correct" for x in res), res
    assert res.extra_lines == 0


def test_unmatched_truth_line_all_missing():
    pred = stringify(T2)
    pred["line_items"] = pred["line_items"][:1]
    r = by_field(score_invoice(T2, pred, "lenient", set(), False))
    for k in ("description", "quantity", "unit_price", "amount"):
        assert r[f"line[0].{k}"].status == "correct"
        assert r[f"line[1].{k}"].status == "missing"


def test_low_similarity_pair_is_unmatched_and_extra_counted():
    pred = stringify(T)
    pred["line_items"] = [
        pred["line_items"][0],
        {"description": "Freight charges", "quantity": "1", "unit_price": "5", "amount": "5"},
    ]
    res = score_invoice(T, pred, "lenient", set(), False)
    assert res.extra_lines == 1
    t = make_truth(line_items=[LineItem("Software License", D("1"), D("1000.00"), D("1000.00"))])
    pred = stringify(t)
    pred["line_items"][0]["description"] = "Freight charges"
    res = score_invoice(t, pred, "lenient", set(), False)
    r = by_field(res)
    assert all(r[f"line[0].{k}"].status == "missing" for k in ("description", "quantity", "unit_price", "amount"))
    assert res.extra_lines == 1
    assert aggregate({"d1": res})["extra_lines"] == 1


def test_matched_line_wrong_amount_and_description_threshold():
    pred = stringify(T)
    # similarity >= 60 so matched, but < 85 so description wrong
    pred["line_items"][0] = {"description": "Software Licence Renewal", "quantity": "1",
                             "unit_price": "1000.00", "amount": "900.00"}
    r = by_field(score_invoice(T, pred, "lenient", set(), False))
    assert r["line[0].description"].status == "wrong"
    assert r["line[0].amount"].status == "wrong"
    assert r["line[0].unit_price"].status == "correct"


def test_line_items_flag_inherited():
    pred = stringify(T)
    pred["line_items"][0]["amount"] = "1.00"
    res = score_invoice(T, pred, "lenient", {"line_items"}, False)
    r = by_field(res)
    assert all(r[f"line[0].{k}"].flagged for k in ("description", "quantity", "unit_price", "amount"))
    assert not r["total"].flagged
    assert aggregate({"d1": res})["silent_errors"]["count"] == 0


def test_aggregate_fully_correct_and_review_rate():
    good = score_invoice(T, P, "lenient", set(), False)
    flagged = score_invoice(T, P_wrong_total, "lenient", set(), True)
    agg = aggregate({"d1": good, "d2": flagged})
    assert agg["n_docs"] == 2
    assert agg["invoice_fully_correct_pct"] == 50.0
    assert agg["review_rate"] == 0.5
    assert agg["field_accuracy"]["total"] == 0.5
    assert agg["field_accuracy"]["subtotal"] == 1.0
    assert agg["field_accuracy"]["line.amount"] == 1.0
    assert agg["silent_errors"]["count"] == 0


def test_extra_line_prevents_fully_correct():
    pred = stringify(T)
    pred["line_items"].append({"description": "Freight charges", "quantity": "1",
                               "unit_price": "5", "amount": "5"})
    res = score_invoice(T, pred, "lenient", set(), False)
    assert all(x.status == "correct" for x in res)
    assert aggregate({"d1": res})["invoice_fully_correct_pct"] == 0.0


def test_amounts_quantized_to_cent_half_up():
    def st(v, mode="strict"):
        return by_field(score_invoice(T, {**P, "total": v}, mode, set(), False))["total"].status
    assert st("1250.004") == "correct"
    assert st("1249.995") == "correct"   # half-up rounds to 1250.00
    assert st("1250.006") == "wrong"
    assert st("1250.005") == "wrong"     # half-up rounds to 1250.01
    assert st("$1,250.004", "lenient") == "correct"
