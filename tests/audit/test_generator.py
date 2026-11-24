import csv
import json
import re
from collections import Counter
from pathlib import Path

import pytest

from audit.generate.generator import (
    LAYOUTS,
    _VENDORS,
    doc_id_for,
    generate_invoices,
    layout_for,
)
from audit.generate.render import render_pdf, render_scanned
from audit.generate.testset import load_testset
from audit.schema import _to_jsonable, load_invoice, save_invoice

REPO = Path(__file__).resolve().parents[2]
TESTSET = REPO / "audit" / "testset"

MINIMUMS = {"multipage": 5, "discount": 5, "multi_tax": 5, "non_usd": 5,
            "dmy_date": 5, "bad_total": 3, "scanned": 8}


def to_json(invs):
    return json.dumps([_to_jsonable(i) for i in invs], sort_keys=True)


def test_generator_is_deterministic():
    assert to_json(generate_invoices()) == to_json(generate_invoices())


def test_different_seed_differs():
    assert to_json(generate_invoices(seed=1)) != to_json(generate_invoices())


def test_hard_case_minimums():
    invs = generate_invoices()
    assert len(invs) == 40
    counts = Counter(t for inv in invs for t in inv.tags)
    for tag, n in MINIMUMS.items():
        assert counts[tag] >= n, (tag, counts[tag])
    for inv in invs:
        if "multipage" in inv.tags:
            assert len(inv.line_items) >= 25
        if "discount" in inv.tags:
            assert any(li.amount < 0 for li in inv.line_items)
        if "non_usd" in inv.tags:
            assert inv.currency in {"EUR", "GBP", "INR"}
        else:
            assert inv.currency == "USD"
        if "scanned" in inv.tags:
            assert "multipage" not in inv.tags
    assert counts["decimal_comma"] >= 1
    assert counts["non_usd"] - counts["decimal_comma"] >= 1
    assert sum(1 for inv in invs if inv.due_date is None) >= 3


def test_layouts_each_used_at_least_six_times():
    c = Counter(layout_for(i) for i in range(40))
    assert set(c) == set(LAYOUTS)
    assert len(LAYOUTS) == 5
    assert min(c.values()) >= 6


def test_truth_arithmetic_holds_except_bad_total():
    for inv in generate_invoices():
        assert sum(li.amount for li in inv.line_items) == inv.subtotal
        if "bad_total" in inv.tags:
            assert inv.subtotal + inv.tax_total != inv.total
        else:
            assert inv.subtotal + inv.tax_total == inv.total


def test_values_are_cent_quantized_and_ids_unique():
    invs = generate_invoices()
    assert len({i.invoice_id for i in invs}) == 40
    assert len({i.vendor_name for i in invs}) == 40
    for inv in invs:
        for v in (inv.subtotal, inv.tax_total, inv.total,
                  *(li.amount for li in inv.line_items)):
            assert v == v.quantize(v.__class__("0.01"))
        if inv.due_date is not None:
            assert inv.due_date > inv.invoice_date


def test_vendor_names_come_only_from_recorded_lists():
    """Allowlist: every generated vendor is one of the generator's invented
    names, and every public vendor is the one recorded in SOURCES.md."""
    invented = {name for name, _ in _VENDORS}
    assert {inv.vendor_name for inv in generate_invoices()} <= invented
    recorded = dict(re.findall(r"^\| (pub-\d{3}) \| ([^|]+?) \|$",
                               (TESTSET / "SOURCES.md").read_text(encoding="utf-8"), re.M))
    for doc_id, _, truth in load_testset():
        if doc_id.startswith("gen-"):
            assert truth.vendor_name in invented, doc_id
        else:
            assert recorded.get(doc_id) == truth.vendor_name, doc_id


def test_doc_ids():
    assert doc_id_for(0) == "gen-001"
    assert doc_id_for(39) == "gen-040"


def test_render_multipage_pdf(tmp_path):
    inv = next(i for i in generate_invoices() if "multipage" in i.tags)
    for layout in LAYOUTS:
        pages = render_pdf(inv, layout, tmp_path / f"m{layout}.pdf")
        assert 2 <= pages <= 3
        assert (tmp_path / f"m{layout}.pdf").stat().st_size > 1000


def test_render_single_page_and_scanned(tmp_path):
    from PIL import Image
    inv = next(i for i in generate_invoices() if "scanned" in i.tags)
    pdf = tmp_path / "s.pdf"
    assert render_pdf(inv, 1, pdf) == 1
    png = tmp_path / "s.png"
    render_scanned(pdf, png, seed=7)
    im = Image.open(png)
    assert im.width > 1000 and im.height > 1400  # ~150 dpi letter
    png2 = tmp_path / "s2.png"
    render_scanned(pdf, png2, seed=7)
    assert png.read_bytes() == png2.read_bytes()


def test_rendered_text_contains_truth_values(tmp_path):
    """The printed document must carry the truth values (as text)."""
    import pypdfium2 as pdfium
    for inv in generate_invoices()[:10]:
        pdf = tmp_path / "t.pdf"
        render_pdf(inv, 1, pdf)
        doc = pdfium.PdfDocument(str(pdf))
        text = "".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
        doc.close()
        assert inv.vendor_name in text
        assert inv.invoice_id in text


def test_manifest_matches_files():
    rows = list(csv.DictReader((TESTSET / "manifest.csv").open(encoding="utf-8")))
    assert rows, "manifest is empty"
    assert set(rows[0]) == {"doc_id", "source", "file", "license", "tags"}
    assert len({r["doc_id"] for r in rows}) == len(rows)
    gen = [r for r in rows if r["source"] == "generated"]
    assert len(gen) == 40
    for r in rows:
        f = TESTSET / r["file"]
        assert f.exists(), f
        truth = f.parent / f"{r['doc_id']}.json"
        inv = load_invoice(truth)
        assert inv.total is not None
        assert sorted(t for t in r["tags"].split(";") if t) == sorted(inv.tags)
        if "scanned" in inv.tags:
            assert f.suffix == ".png"


def test_load_testset():
    items = load_testset()
    assert len(items) >= 40
    doc_id, path, inv = items[0]
    assert doc_id == "gen-001" and path.exists() and inv.vendor_name


def test_generated_truth_matches_generator():
    """Committed truth JSON is exactly what the generator produces."""
    for i, inv in enumerate(generate_invoices()):
        p = TESTSET / "generated" / f"{doc_id_for(i)}.json"
        assert json.loads(p.read_text(encoding="utf-8")) == _to_jsonable(inv)


def test_descriptions_have_no_scientific_notation():
    for inv in generate_invoices():
        for li in inv.line_items:
            assert "E+" not in li.description and "E-" not in li.description, li.description


def test_every_document_prints_its_truth_totals(tmp_path):
    """Render each invoice with its assigned layout; the extracted PDF text must
    contain the invoice id, vendor, and the subtotal/tax lines/total as printed."""
    import pypdfium2 as pdfium
    from audit.generate.render import fmt_num
    for i, inv in enumerate(generate_invoices()):
        pdf = tmp_path / f"{i}.pdf"
        render_pdf(inv, layout_for(i), pdf)
        doc = pdfium.PdfDocument(str(pdf))
        text = "".join(doc[k].get_textpage().get_text_range() for k in range(len(doc)))
        doc.close()
        for sym in ("$", "€", "£", "Rs."):  # layout 4 glues symbols on
            text = text.replace(sym, "")
        comma = "decimal_comma" in inv.tags
        neg = layout_for(i) == 4
        for v in [inv.subtotal, inv.total] + [t for _, t in inv.tax_lines]:
            assert fmt_num(v, comma, neg) in text, (i, v)
        assert sum(t for _, t in inv.tax_lines) == inv.tax_total
        for li in inv.line_items:
            assert fmt_num(li.amount, comma, neg) in text, (i, li)


def test_every_testset_truth_is_consistent():
    """Committed truth (generated + public): arithmetic holds unless bad_total;
    the public subset is 10-20 docs with ids pub-NNN."""
    items = load_testset()
    pub = [d for d, _, _ in items if d.startswith("pub-")]
    assert len(pub) == 0 or 10 <= len(pub) <= 20
    for doc_id, path, inv in items:
        assert sum(li.amount for li in inv.line_items) == inv.subtotal, doc_id
        if "bad_total" not in inv.tags:
            assert inv.subtotal + inv.tax_total == inv.total, doc_id
