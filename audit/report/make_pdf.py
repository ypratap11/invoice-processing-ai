"""Build the two-page audit summary PDF (audit/REPORT.pdf) with reportlab.

    python -m audit.report.make_pdf

Page 1: claim vs measured, headline chart, top findings. Page 2: method, review-rate
views, model comparison, limits. Numbers are read from audit/results/*.json; the
narrative mirrors audit/REPORT.md. Fails if the result is not exactly 2 pages.
"""
from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

REPO = Path(__file__).resolve().parents[2]
RESULTS = REPO / "audit" / "results"
CHARTS = REPO / "audit" / "report"
OUT = REPO / "audit" / "REPORT.pdf"

INK, INK2, RULE, BLUE = colors.HexColor("#0b0b0b"), colors.HexColor("#52514e"), \
    colors.HexColor("#d6d5cf"), colors.HexColor("#2a78d6")

H1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=INK, spaceAfter=2)
SUB = ParagraphStyle("sub", fontName="Helvetica", fontSize=8, leading=10, textColor=INK2, spaceAfter=6)
H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=INK,
                    spaceBefore=6, spaceAfter=3)
BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=8.2, leading=10.4, textColor=INK,
                      alignment=TA_LEFT, spaceAfter=3)
BUL = ParagraphStyle("bul", parent=BODY, leftIndent=9, bulletIndent=0, spaceAfter=2)
CELL = ParagraphStyle("cell", fontName="Helvetica", fontSize=7.6, leading=9.2, textColor=INK)
CELLB = ParagraphStyle("cellb", parent=CELL, fontName="Helvetica-Bold")


def load(run):
    return json.loads((RESULTS / f"{run}.json").read_text(encoding="utf-8"))


def stats(r, mode="lenient"):
    docs = r["per_doc"]
    fields = [f for d in docs for f in d[mode]["fields"]]
    agg = r[f"aggregate_{mode}"]
    full = sum(1 for d in docs if d[mode]["extra_lines"] == 0
               and all(f["status"] == "correct" for f in d[mode]["fields"]))
    return {"n": len(docs), "full": full, "fields": len(fields),
            "correct": sum(f["status"] == "correct" for f in fields),
            "hdr_ok": sum(f["status"] == "correct" for f in fields if not f["field"].startswith("line")),
            "hdr_n": sum(1 for f in fields if not f["field"].startswith("line")),
            "line_ok": sum(f["status"] == "correct" for f in fields if f["field"].startswith("line")),
            "line_n": sum(1 for f in fields if f["field"].startswith("line")),
            "silent": agg["silent_errors"]["count"], "missing": agg["missing"]["count"],
            "review": round(agg["review_rate"] * len(docs)),
            "cost": r["summary"]["api_cost_usd"], "lat": r["summary"]["median_latency_s"],
            "lines": sum(d["pred_lines"] for d in docs), "truth_lines": sum(d["truth_lines"] for d in docs)}


def checks_only(r, mode):
    """Re-score with confidence flags removed (checks only), frozen scorer, no API calls."""
    from audit.generate.testset import load_testset
    from audit.scorer import aggregate, score_invoice
    truth = {d[0]: d[2] for d in load_testset()}
    agg = aggregate({d["doc_id"]: score_invoice(truth[d["doc_id"]], d["pred"], mode, set(), d["invoice_flagged"])
                     for d in r["per_doc"]})
    return round(agg["review_rate"] * agg["n_docs"]), agg["silent_errors"]["count"]


def table(rows, widths, header=True):
    data = [[Paragraph(str(c), CELLB if (header and i == 0) or j == 0 else CELL) for j, c in enumerate(row)]
            for i, row in enumerate(rows)]
    t = Table(data, colWidths=widths, hAlign="LEFT")
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
             ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
             ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
    if header:
        style.append(("LINEBELOW", (0, 0), (-1, 0), 0.9, INK))
    t.setStyle(TableStyle(style))
    return t


def p(text, style=BODY):
    return Paragraph(text, style)


def bullets(items):
    return [Paragraph(t, BUL, bulletText="•") for t in items]


def build(out: Path = OUT) -> Path:
    b, a, g = stats(load("docai-before")), stats(load("docai-after")), stats(load("gemini-after"))
    as_, gs = stats(load("docai-after"), "strict"), stats(load("gemini-after"), "strict")
    co_review, co_len = checks_only(load("docai-after"), "lenient")
    _, co_str = checks_only(load("docai-after"), "strict")
    pct = lambda x, n: f"{100 * x / n:.0f}%"
    story = [
        p("Invoice accuracy audit", H1),
        p("Subject: this repository's invoice extraction app (FastAPI + Google Document AI Invoice Parser). "
          "Runs 2026-11-23 on 53 labeled invoices. Scoring rules frozen before the first measured run "
          "(git tag audit-scoring-frozen). Full report, data and method: audit/REPORT.md. "
          "Pratap Yeragudipati, Augaster.", SUB),
        p("What was claimed, and what was measured", H2),
        table([
            ["", "App as built", "App after fixes", "Gemini 3.8 Flash + same checks"],
            ["Old README: \"95%+ accuracy\". Invoices fully correct", f"<b>{b['full']} of {b['n']}</b>",
             f"<b>{a['full']} of {a['n']}</b>", f"<b>{g['full']} of {g['n']}</b>"],
            ["Line items returned", f"<b>{b['lines']} of {b['truth_lines']}</b>",
             f"{a['lines']} for {a['truth_lines']} printed", f"{g['lines']} of {g['truth_lines']}"],
            ["Values correct (all fields)", f"{b['correct']:,} of {b['fields']:,} ({pct(b['correct'], b['fields'])})",
             f"{a['correct']:,} of {a['fields']:,} ({pct(a['correct'], a['fields'])})",
             f"{g['correct']:,} of {g['fields']:,} ({100 * g['correct'] / g['fields']:.1f}%)"],
            ["Values missing", f"{b['missing']:,}", f"{a['missing']:,}", f"{g['missing']:,}"],
            ["Old README: \"Zero data entry errors\". Wrong values passed on silently",
             f"{b['silent']}", f"{a['silent']}", f"{g['silent']}"],
            ["Invoices sent to human review", f"{b['review']} of {b['n']}", f"{a['review']} of {a['n']}",
             f"{g['review']} of {g['n']}"],
            ["Cost per invoice", "$0.20 (called twice per upload)", f"${a['cost'] / a['n']:.2f}",
             f"about ${g['cost'] / g['n']:.3f}"],
        ], [2.35 * inch, 1.45 * inch, 1.45 * inch, 1.85 * inch]),
        Spacer(1, 2),
        p("Lenient scoring (formatting cleaned up the same way for every system). Before the fixes the "
          "silent-error count is low only because most values were not returned at all; a blank is visible, "
          "so it is not counted as silent. The old claims of 100% success rate, 90% time saving and 99.9% "
          "uptime had no measurement behind them and were removed; this audit tests accuracy only.", SUB),
        Image(str(CHARTS / "before_after.png"), width=7.1 * inch, height=7.1 * inch * 672 / 1600),
        p("Top findings", H2),
        *bullets([
            "<b>Line items were never extracted, on 53 of 53 invoices.</b> The app read line items only from "
            "detected tables. Document AI returned 0 tables but 472 line_item entities, which the app ignored. "
            "0 of 471 printed lines reached the user, with no error and no flag.",
            "<b>The chat agent's invoice tool returned made-up data.</b> It answered every request with a "
            "hard-coded sample invoice ($1,250, \"Acme Corporation\") and saved it to the database as if processed.",
            "<b>Two extractors, one dead; and every upload paid Document AI twice</b> ($0.20 per invoice for one "
            "result). Two security issues were found and fixed during the audit: the agent tool could be steered "
            "into reading files outside the upload folder, and error messages revealed the credentials file path.",
            f"<b>After the fixes:</b> header values are right {a['hdr_ok']} of {a['hdr_n']} times "
            f"({pct(a['hdr_ok'], a['hdr_n'])}) and line values {a['line_ok']:,} of {a['line_n']:,} "
            f"({pct(a['line_ok'], a['line_n'])}), but only {a['full']} of {a['n']} invoices are fully right. "
            f"New arithmetic checks stop most wrong values from passing silently, by sending {a['review']} of "
            f"{a['n']} invoices to a person. That is a safety net, not automation.",
        ]),
        PageBreak(),
        p("How it was measured", H2),
        *bullets([
            "<b>Test set:</b> 40 generated invoices (5 layouts; hard cases: 17 day-first dates, 11 non-USD, "
            "10 discounts, 10 scanned-look images, 7 several-tax, 6 two-page, 4 decimal-comma, 4 with a wrong "
            "printed total) plus 13 public invoices from katanaml-org/invoices-donut-data-v1 (MIT; images from "
            "Kozlowski &amp; Weichbroth 2021, Mendeley Data, doi:10.17632/tnj49gpmtz.2, CC BY 4.0), every label "
            "checked by eye.",
            "<b>System under test:</b> the app's own API path and original extraction code, on Invoice Parser "
            "pretrained-invoice-v2.0-2023-12-06. Each invoice was sent to Document AI once; before and after "
            "re-use the same cached responses, so the difference is the app's code alone.",
            "<b>Scoring:</b> 2,283 values (407 header, 1,876 line-item over 471 lines). Amounts and quantities "
            "equal to the cent; dates equal as dates; vendor and line description by fuzzy match "
            "(token_set_ratio 90 and 85); lines paired by best description match. <i>Strict</i> = the value as the "
            "app returns it; <i>lenient</i> = after one shared clean-up (separators, symbols, unambiguous date formats).",
            "<b>Silent error</b> = a wrong value that is not flagged for review. Missing values are never silent. "
            "Flags: before, Document AI confidence below 0.7; after, any failed check sends the whole invoice to "
            "review. Checks: qty x price = amount, lines add to subtotal, subtotal + tax = total, valid dates "
            "with due date not before invoice date, required fields present.",
            "<b>Gemini:</b> gemini-3.8-flash on Vertex AI (global endpoint), temperature 0, JSON schema output; the "
            "prompt asks for ISO dates and plain numbers and is quoted in full in REPORT.md.",
        ]),
        p("The review rate, read honestly", H2),
        table([
            ["App after fixes: what can flag an invoice", "Sent to review", "Silent errors, lenient",
             "Silent errors, strict"],
            ["(a) Checks only", f"{co_review} of 53 ({pct(co_review, 53)})", f"{co_len}", f"{co_str}"],
            ["(b) Checks + Document AI confidence &lt; 0.7", f"{a['review']} of 53 ({pct(a['review'], 53)})", f"{a['silent']}",
             f"{as_['silent']}"],
        ], [2.9 * inch, 1.3 * inch, 1.45 * inch, 1.45 * inch]),
        Spacer(1, 3),
        p("<b>A 92% review rate is not a usable operating point:</b> if 49 of 53 invoices go to a person, the "
          "app is mostly a pre-filled form. The checks do catch all 4 invoices whose own printed total is wrong. "
          "31 of the 32 remaining lenient silent errors sit on 4 scanned invoices where Document AI splits each "
          "printed row into fragments; values shift between rows but still add up, so no check fires. The 32nd "
          "is one misread quantity (\"5050\" for 50) on a digital PDF. Better line extraction, not looser "
          "checks, is the way to a lower review rate."),
        p("Model comparison (lenient first: Gemini was told to output clean formats, the app was not)", H2),
        table([
            ["", "App after fixes (Document AI)", "Gemini 3.8 Flash + same checks"],
            ["Invoices fully correct", f"{a['full']} of 53 (strict {as_['full']})", f"{g['full']} of 53 (strict {gs['full']})"],
            ["Silent errors", f"{a['silent']} (strict {as_['silent']})", f"{g['silent']} (strict {gs['silent']})"],
            ["Sent to review", f"{a['review']} of 53", f"{g['review']} of 53 (4 wrong-total invoices, 3 blank tax totals)"],
            ["Cost, 53 invoices / per invoice", f"${a['cost']:.2f} / $0.10", f"${g['cost']:.3f} / about $0.006"],
            ["Median time per invoice", f"{a['lat']:.1f} s", f"{g['lat']:.1f} s"],
        ], [2.1 * inch, 2.2 * inch, 2.8 * inch]),
        Spacer(1, 3),
        p("Prices: Document AI $0.10 per document (Google pricing page, checked 2026-11-23). Gemini: actual tokens "
          "at $0.75 / $3.75 per million input / output, the Vertex AI global-endpoint introductory price (checked "
          "2026-11-24), rising to $1.50 / $7.50 on 2027-01-01 (about $0.012 per invoice). The global endpoint does "
          "not pin where data is processed (us-central1 returned not-found for Gemini in this project). All spend "
          "($7.09 on the ledger, a conservative pre-charge) came from free-trial credit. A local-model comparison "
          "is deferred."),
        p("Limits", H2),
        *bullets([
            "<b>Mostly synthetic.</b> 40 of 53 invoices are generated by the author; the 13 public ones come from a "
            "single synthetic template. No real supplier invoices, handwriting or phone photos. Public truth uses "
            "net line amounts although the lines also print gross; one layout prints US-order dates on a "
            "European-looking page; 3 day-first invoices print the month as a word.",
            "<b>Small and single-shot.</b> 53 invoices, one processor version, one Gemini prompt and one run, all "
            "on 2026-11-23. One or two invoices of difference is noise; 0 vs 6 vs 48 is not.",
            "<b>Scoring generosity.</b> token_set_ratio treats a subset of words as a full match, which flatters "
            "lenient vendor and description scores. Quantities are compared to the cent.",
            "<b>Open items:</b> the several-tax-lines case is caught by checks, not fixed; a failed extraction "
            "reports review_required = false; a few agent endpoints still echo raw errors.",
            "<b>Changes after the scoring freeze: none</b> (no diff to audit/scorer.py or audit/normalize.py "
            "since tag audit-scoring-frozen).",
        ]),
    ]
    doc = SimpleDocTemplate(str(out), pagesize=letter, leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                            topMargin=0.5 * inch, bottomMargin=0.5 * inch,
                            title="Invoice accuracy audit", author="Pratap Yeragudipati, Augaster")
    doc.build(story)
    import pypdfium2
    pdf = pypdfium2.PdfDocument(str(out))
    n = len(pdf)
    pdf.close()
    if n != 2:
        raise SystemExit(f"{out.name} has {n} pages, expected 2")
    return out


if __name__ == "__main__":
    print(build().relative_to(REPO).as_posix())
