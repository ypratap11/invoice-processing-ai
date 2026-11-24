"""Render truth invoices to PDF in five layouts, plus a scanned PNG variant.

The printed values are exactly the truth values (see generator.py): the
renderer never computes a total of its own, so a ``bad_total`` invoice prints
its (wrong) truth total. PDFs are written with ``invariant=1`` so re-rendering
yields byte-identical files.
"""
from __future__ import annotations

import io
import random
from datetime import date
from decimal import Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from audit.schema import Invoice

W, H = letter
SYMBOL = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "Rs."}
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


# --- formatting --------------------------------------------------------------
def fmt_num(v: Decimal, comma: bool, paren_neg: bool = False) -> str:
    s = f"{abs(v):,.2f}"
    if comma:
        s = s.replace(",", "_").replace(".", ",").replace("_", ".")
    if v < 0:
        return f"({s})" if paren_neg else f"-{s}"
    return s


def fmt_qty(q: Decimal | None, comma: bool) -> str:
    if q is None:
        return ""
    s = str(q.normalize()) if q != q.to_integral() else str(int(q))
    return s.replace(".", ",") if comma else s


def fmt_date(d: date, style: str, layout: int) -> str:
    mon, mon3 = MONTHS[d.month - 1], MONTHS[d.month - 1][:3]
    if style == "dmy":
        return {1: f"{d.day:02d}/{d.month:02d}/{d.year}",
                2: f"{d.day} {mon} {d.year}",
                3: f"{d.day:02d}-{d.month:02d}-{d.year}",
                4: f"{d.day:02d}/{d.month:02d}/{d.year}",
                5: f"{d.day:02d}.{d.month:02d}.{d.year}"}[layout]
    return {1: f"{d.month:02d}/{d.day:02d}/{d.year}",
            2: f"{mon} {d.day}, {d.year}",
            3: d.isoformat(),
            4: f"{mon3} {d.day}, {d.year}",
            5: f"{d.month:02d}/{d.day:02d}/{d.year}"}[layout]


def _extras(inv: Invoice) -> dict:
    """Print-only details; defaults let a plain Invoice render too."""
    g = lambda k, d: getattr(inv, k, d)  # noqa: E731
    tax_lines = g("tax_lines", None) or [("Tax", inv.tax_total or Decimal("0.00"))]
    return dict(
        customer=g("customer", ()) or ("Customer",),
        vaddr=g("vendor_address", ()) or (),
        tax_lines=tax_lines,
        po=g("po_number", None),
        terms=g("terms", "") or ("Due on receipt" if inv.due_date is None else ""),
        comma=g("decimal_comma", "decimal_comma" in inv.tags),
        style=g("date_style", "dmy" if "dmy_date" in inv.tags else "mdy"),
    )


# --- layout base -------------------------------------------------------------
class Layout:
    font, bold = "Helvetica", "Helvetica-Bold"
    size = 9
    row_h = 18
    first_top = 540     # y of the table header on page 1
    cont_top = 700      # y of the table header on continuation pages
    bottom = 72
    totals_h = 130
    paren_neg = False
    # (key, title, x, align) ; align "l" uses x as left edge, "r" as right edge
    columns: list[tuple[str, str, float, str]] = []

    def __init__(self, inv: Invoice, layout: int):
        self.inv, self.n = inv, layout
        self.x = _extras(inv)
        self.sym = SYMBOL.get(inv.currency or "", "")

    # helpers
    def num(self, v):
        return fmt_num(v, self.x["comma"], self.paren_neg)

    def date(self, d):
        return fmt_date(d, self.x["style"], self.n)

    def text(self, c, x, y, s, font=None, size=None, align="l", color=colors.black):
        c.setFillColor(color)
        c.setFont(font or self.font, size or self.size)
        if align == "r":
            c.drawRightString(x, y, s)
        elif align == "c":
            c.drawCentredString(x, y, s)
        else:
            c.drawString(x, y, s)

    def cell(self, key, li, idx) -> str:
        if key == "no":
            return str(idx + 1)
        if key == "desc":
            return li.description or ""
        if key == "qty":
            return fmt_qty(li.quantity, self.x["comma"])
        if key == "unit":
            return "" if li.unit_price is None else self.money_cell(li.unit_price)
        if key == "amount":
            return self.money_cell(li.amount)
        raise KeyError(key)

    def money_cell(self, v):
        return self.num(v)

    # page parts (override)
    def first_header(self, c):
        raise NotImplementedError

    def cont_header(self, c, page, pages):
        self.text(c, 50, H - 50, self.inv.vendor_name, self.bold, 12)
        self.text(c, W - 50, H - 50, f"Invoice {self.inv.invoice_id} (continued)",
                  align="r")

    def table_header(self, c, y):
        for key, title, x, al in self.columns:
            self.text(c, x, y, title, self.bold, align=al)
        c.setLineWidth(0.6)
        c.line(48, y - 5, W - 48, y - 5)

    def row(self, c, y, li, idx):
        for key, _t, x, al in self.columns:
            s = self.cell(key, li, idx)
            size = self.size
            if key == "desc":
                while stringWidth(s, self.font, size) > self.desc_width and size > 6:
                    size -= 0.5
            self.text(c, x, y, s, size=size, align=al)

    desc_width = 230

    def totals(self, c, y):
        raise NotImplementedError

    def carry(self, c, y):
        self.text(c, W - 50, y - 6, "Continued on next page", "Helvetica-Oblique", 8,
                  align="r")

    def footer(self, c, page, pages):
        self.text(c, W / 2, 36, f"Page {page} of {pages}", size=8, align="c",
                  color=colors.grey)

    # shared totals block: label right-aligned at lx, value right-aligned at vx
    def totals_lines(self):
        inv = self.inv
        out = [("Subtotal", self.num(inv.subtotal))]
        out += [(name, self.num(v)) for name, v in self.x["tax_lines"]]
        return out


def _bill_to(lay: Layout, c, x, y, title="Bill To"):
    lay.text(c, x, y, title, lay.bold, 9)
    for k, line in enumerate(lay.x["customer"]):
        lay.text(c, x, y - 13 * (k + 1), line, lay.bold if k == 0 else lay.font, 9)


# --- layout 1: classic -------------------------------------------------------
class Classic(Layout):
    columns = [("desc", "Description", 56, "l"), ("qty", "Qty", 360, "r"),
               ("unit", "Unit Price", 460, "r"), ("amount", "Amount", W - 56, "r")]

    def first_header(self, c):
        inv, x = self.inv, self.x
        self.text(c, 50, H - 70, inv.vendor_name, self.bold, 18)
        for k, line in enumerate(x["vaddr"]):
            self.text(c, 50, H - 88 - 12 * k, line, size=9, color=colors.darkgrey)
        self.text(c, W - 50, H - 70, "INVOICE", self.bold, 26, align="r",
                  color=colors.HexColor("#33415c"))
        meta = [("Invoice No:", inv.invoice_id),
                ("Invoice Date:", self.date(inv.invoice_date))]
        if inv.due_date:
            meta.append(("Due Date:", self.date(inv.due_date)))
        meta.append(("Terms:", x["terms"]))
        if x["po"]:
            meta.append(("PO Number:", x["po"]))
        for k, (a, b) in enumerate(meta):
            self.text(c, W - 160, H - 100 - 14 * k, a, self.bold, align="r")
            self.text(c, W - 50, H - 100 - 14 * k, b, align="r")
        _bill_to(self, c, 50, H - 190)

    def table_header(self, c, y):
        c.setFillColor(colors.HexColor("#e6e9ef"))
        c.rect(48, y - 6, W - 96, 18, stroke=0, fill=1)
        super().table_header(c, y)

    def row(self, c, y, li, idx):
        super().row(c, y, li, idx)
        c.setStrokeColor(colors.HexColor("#d0d4dc"))
        c.setLineWidth(0.4)
        c.line(48, y - 6, W - 48, y - 6)
        c.setStrokeColor(colors.black)

    def totals(self, c, y):
        rows = self.totals_lines() + [("Total", f"{self.sym}{self.num(self.inv.total)}")]
        for k, (a, b) in enumerate(rows):
            last = k == len(rows) - 1
            yy = y - 16 * k - (6 if last else 0)
            if last:
                c.line(380, yy + 13, W - 48, yy + 13)
            self.text(c, 460, yy, a, self.bold if last else self.font, 11 if last else 9,
                      align="r")
            self.text(c, W - 56, yy, b, self.bold if last else self.font,
                      11 if last else 9, align="r")
        self.text(c, 50, 60, "Thank you for your business.", "Helvetica-Oblique", 9)


# --- layout 2: colour band ---------------------------------------------------
class Band(Layout):
    teal = colors.HexColor("#0f5257")
    columns = [("no", "#", 56, "l"), ("desc", "Item", 76, "l"), ("qty", "Qty", 370, "r"),
               ("unit", "Rate", 460, "r"), ("amount", "Total", W - 56, "r")]
    desc_width = 270

    def first_header(self, c):
        inv, x = self.inv, self.x
        c.setFillColor(self.teal)
        c.rect(0, H - 100, W, 100, stroke=0, fill=1)
        self.text(c, 50, H - 55, inv.vendor_name, self.bold, 20, color=colors.white)
        self.text(c, 50, H - 75, "  |  ".join(x["vaddr"]), size=8, color=colors.white)
        self.text(c, W - 50, H - 55, "INVOICE", self.bold, 16, align="r",
                  color=colors.white)
        top = H - 135
        _bill_to(self, c, 50, top, "Billed to")
        self.text(c, 250, top, "Invoice details", self.bold)
        det = [("Number", inv.invoice_id), ("Issued", self.date(inv.invoice_date)),
               ("Due", self.date(inv.due_date) if inv.due_date else "Upon receipt")]
        if x["po"]:
            det.append(("Your ref", x["po"]))
        for k, (a, b) in enumerate(det):
            self.text(c, 250, top - 14 * (k + 1), a, color=colors.grey)
            self.text(c, 305, top - 14 * (k + 1), b)
        self.text(c, W - 50, top, f"Amount due ({inv.currency})", self.bold, align="r")
        self.text(c, W - 50, top - 26, f"{inv.currency} {self.num(inv.total)}", self.bold,
                  18, align="r", color=self.teal)

    def cont_header(self, c, page, pages):
        c.setFillColor(self.teal)
        c.rect(0, H - 60, W, 60, stroke=0, fill=1)
        self.text(c, 50, H - 38, self.inv.vendor_name, self.bold, 14, color=colors.white)
        self.text(c, W - 50, H - 38, f"Invoice {self.inv.invoice_id}", align="r",
                  color=colors.white)

    def row(self, c, y, li, idx):
        if idx % 2 == 0:
            c.setFillColor(colors.HexColor("#eef5f5"))
            c.rect(48, y - 6, W - 96, self.row_h, stroke=0, fill=1)
        super().row(c, y, li, idx)

    def totals(self, c, y):
        rows = [("Sub-total", self.num(self.inv.subtotal))] + self.totals_lines()[1:]
        for k, (a, b) in enumerate(rows):
            self.text(c, 470, y - 16 * k, a, align="r")
            self.text(c, W - 56, y - 16 * k, b, align="r")
        yy = y - 16 * len(rows) - 10
        c.setFillColor(self.teal)
        c.rect(330, yy - 7, W - 378, 22, stroke=0, fill=1)
        self.text(c, 470, yy, f"Amount due ({self.inv.currency})", self.bold, 10,
                  align="r", color=colors.white)
        self.text(c, W - 56, yy, self.num(self.inv.total), self.bold, 10, align="r",
                  color=colors.white)


# --- layout 3: monospace statement -------------------------------------------
class Mono(Layout):
    font, bold = "Courier", "Courier-Bold"
    size = 9
    row_h = 15
    first_top = 520
    columns = [("no", "LN", 50, "l"), ("desc", "DESCRIPTION", 74, "l"),
               ("qty", "QTY", 380, "r"), ("unit", "PRICE", 470, "r"),
               ("amount", "EXTENDED", W - 50, "r")]
    desc_width = 270

    def dashes(self, c, y):
        self.text(c, 50, y, "-" * 92, size=9)

    def first_header(self, c):
        inv, x = self.inv, self.x
        self.text(c, W / 2, H - 60, inv.vendor_name.upper(), self.bold, 14, align="c")
        self.text(c, W / 2, H - 76, " * ".join(x["vaddr"]), size=8, align="c")
        self.dashes(c, H - 92)
        self.text(c, 50, H - 110, "I N V O I C E", self.bold, 12)
        meta = [("Inv No.", inv.invoice_id), ("Dated", self.date(inv.invoice_date)),
                ("Payable by", self.date(inv.due_date) if inv.due_date else x["terms"]),
                ("Currency", inv.currency)]
        if x["po"]:
            meta.append(("Cust PO", x["po"]))
        for k, (a, b) in enumerate(meta):
            self.text(c, 330, H - 110 - 13 * k, f"{a:<11}: {b}")
        _bill_to(self, c, 50, H - 140, "SOLD TO:")
        self.dashes(c, H - 230)

    def table_header(self, c, y):
        for key, title, x, al in self.columns:
            self.text(c, x, y, title, self.bold, align=al)
        self.dashes(c, y - 10)

    def carry(self, c, y):
        self.text(c, W - 50, y - 4, "*** CONTINUED ***", align="r")

    def totals(self, c, y):
        self.dashes(c, y + 6)
        rows = [("NET", self.num(self.inv.subtotal))]
        rows += [(n.upper(), self.num(v)) for n, v in self.x["tax_lines"]]
        rows += [(f"TOTAL {self.inv.currency}", self.num(self.inv.total))]
        for k, (a, b) in enumerate(rows):
            last = k == len(rows) - 1
            self.text(c, 440, y - 8 - 14 * k, a, self.bold if last else self.font,
                      align="r")
            self.text(c, W - 50, y - 8 - 14 * k, b, self.bold if last else self.font,
                      align="r")
        self.text(c, 50, 60, "TERMS: " + (self.x["terms"] or "AS AGREED"), size=8)

    def footer(self, c, page, pages):
        self.text(c, W - 50, 36, f"PAGE {page}/{pages}", size=8, align="r")


# --- layout 4: boxed meta, qty first, parenthesised negatives ------------------
class Boxed(Layout):
    paren_neg = True
    first_top = 520
    columns = [("qty", "Qty", 80, "r"), ("desc", "Description", 100, "l"),
               ("unit", "Unit cost", 460, "r"), ("amount", "Line total", W - 56, "r")]
    desc_width = 260

    def money_cell(self, v):
        s = self.num(v)
        return f"({self.sym}{s[1:]}" if s.startswith("(") else f"{self.sym}{s}"

    def first_header(self, c):
        inv, x = self.inv, self.x
        initials = "".join(w[0] for w in inv.vendor_name.split() if w[0].isalpha())[:2]
        c.setFillColor(colors.HexColor("#7a3e2b"))
        c.rect(50, H - 110, 56, 56, stroke=0, fill=1)
        self.text(c, 78, H - 90, initials, self.bold, 22, align="c", color=colors.white)
        self.text(c, W - 50, H - 66, inv.vendor_name, self.bold, 15, align="r")
        for k, line in enumerate(x["vaddr"]):
            self.text(c, W - 50, H - 82 - 12 * k, line, size=8, align="r")
        self.text(c, 50, H - 150, "Invoice", self.bold, 22,
                  color=colors.HexColor("#7a3e2b"))
        heads = ["Invoice #", "Date", "Due"] + (["P.O."] if x["po"] else [])
        vals = [inv.invoice_id, self.date(inv.invoice_date),
                self.date(inv.due_date) if inv.due_date else "On receipt"]
        vals += [x["po"]] if x["po"] else []
        cw = 100
        x0 = W - 50 - cw * len(heads)
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.7)
        for k, (hd, v) in enumerate(zip(heads, vals)):
            c.rect(x0 + cw * k, H - 200, cw, 40, stroke=1, fill=0)
            c.line(x0 + cw * k, H - 180, x0 + cw * (k + 1), H - 180)
            self.text(c, x0 + cw * k + cw / 2, H - 174, hd, self.bold, 8, align="c")
            self.text(c, x0 + cw * k + cw / 2, H - 194, v, size=9, align="c")
        _bill_to(self, c, 50, H - 190, "Customer")

    def table_header(self, c, y):
        c.setFillColor(colors.HexColor("#7a3e2b"))
        c.rect(48, y - 6, W - 96, 18, stroke=0, fill=1)
        for key, title, x, al in self.columns:
            self.text(c, x, y, title, self.bold, align=al, color=colors.white)

    def row(self, c, y, li, idx):
        super().row(c, y, li, idx)
        c.setLineWidth(0.3)
        c.rect(48, y - 6, W - 96, self.row_h, stroke=1, fill=0)

    def totals(self, c, y):
        rows = [(a, f"{self.sym}{b}") for a, b in self.totals_lines()]
        rows.append(("Balance Due", f"{self.sym}{self.num(self.inv.total)}"))
        c.setLineWidth(0.7)
        c.rect(350, y - 16 * len(rows) + 6, W - 398, 16 * len(rows) + 4, stroke=1, fill=0)
        for k, (a, b) in enumerate(rows):
            last = k == len(rows) - 1
            self.text(c, 358, y - 16 * k, a, self.bold if last else self.font)
            self.text(c, W - 56, y - 16 * k, b, self.bold if last else self.font,
                      align="r")
        self.text(c, 50, 60, f"Payment terms: {self.x['terms']}. Please quote the "
                  "invoice number with your remittance.", size=8)


# --- layout 5: European letter -----------------------------------------------
class Letter(Layout):
    columns = [("no", "Pos.", 52, "l"), ("desc", "Description", 82, "l"),
               ("qty", "Quantity", 370, "r"), ("unit", "Unit price", 460, "r"),
               ("amount", "Line total", W - 56, "r")]
    desc_width = 260
    first_top = 500

    def first_header(self, c):
        inv, x = self.inv, self.x
        self.text(c, W - 50, H - 60, inv.vendor_name, self.bold, 14, align="r")
        for k, line in enumerate(x["vaddr"]):
            self.text(c, W - 50, H - 76 - 11 * k, line, size=8, align="r")
        sender = f"{inv.vendor_name} - {' - '.join(x['vaddr'][:2])}"
        self.text(c, 50, H - 140, sender, "Helvetica-Oblique", 6.5)
        c.line(50, H - 143, 290, H - 143)
        for k, line in enumerate(x["customer"]):
            self.text(c, 50, H - 158 - 13 * k, line, size=10)
        kv = [("Invoice number", inv.invoice_id),
              ("Invoice date", self.date(inv.invoice_date)),
              ("Payment due", self.date(inv.due_date) if inv.due_date
               else "Payable on receipt")]
        if x["po"]:
            kv.append(("Customer ref.", x["po"]))
        kv.append(("Currency", inv.currency))
        for k, (a, b) in enumerate(kv):
            self.text(c, 360, H - 158 - 13 * k, a, size=8.5, color=colors.grey)
            self.text(c, W - 50, H - 158 - 13 * k, b, size=8.5, align="r")
        self.text(c, 50, H - 250, f"Invoice {inv.invoice_id}", self.bold, 15)
        self.text(c, 50, H - 266, "We invoice the following goods and services:",
                  size=9)

    def totals(self, c, y):
        cur = self.inv.currency
        rows = [("Net amount", f"{self.num(self.inv.subtotal)} {cur}")]
        rows += [(n, f"{self.num(v)} {cur}") for n, v in self.x["tax_lines"]]
        for k, (a, b) in enumerate(rows):
            self.text(c, 440, y - 15 * k, a, align="r")
            self.text(c, W - 56, y - 15 * k, b, align="r")
        yy = y - 15 * len(rows) - 6
        c.setLineWidth(1)
        c.line(330, yy + 12, W - 48, yy + 12)
        self.text(c, 440, yy, "Total due", self.bold, 10, align="r")
        self.text(c, W - 56, yy, f"{self.num(self.inv.total)} {cur}", self.bold, 10,
                  align="r")
        c.line(330, yy - 4, W - 48, yy - 4)
        c.line(330, yy - 6, W - 48, yy - 6)
        terms = self.x["terms"] or "see above"
        self.text(c, 50, 70, f"Terms of payment: {terms}. Thank you for your order.",
                  size=8)


LAYOUT_CLASSES = {1: Classic, 2: Band, 3: Mono, 4: Boxed, 5: Letter}


def _paginate(n_rows: int, lay: Layout) -> list[int]:
    """Rows per page; the totals block must fit after the last page's rows."""
    pages, left, first = [], n_rows, True
    while True:
        top = lay.first_top if first else lay.cont_top
        cap = int((top - 22 - lay.bottom) // lay.row_h)
        if left <= cap:
            if (cap - left) * lay.row_h >= lay.totals_h:
                pages.append(left)
                return pages
            take = max(left - 3, 0)  # carry 3 rows so totals share their page
        else:
            take = cap
        pages.append(take)
        left -= take
        first = False


def render_pdf(inv: Invoice, layout: int, path: Path) -> int:
    """Render ``inv`` with layout 1..5 to ``path``; return the page count."""
    lay = LAYOUT_CLASSES[layout](inv, layout)
    plan = _paginate(len(inv.line_items), lay)
    n = len(plan)
    c = Canvas(str(path), pagesize=letter, invariant=1)
    c.setTitle(f"Invoice {inv.invoice_id}")
    c.setAuthor(inv.vendor_name or "")
    idx = 0
    for p, count in enumerate(plan):
        if p == 0:
            lay.first_header(c)
            y = lay.first_top
        else:
            lay.cont_header(c, p + 1, n)
            y = lay.cont_top
        lay.table_header(c, y)
        y -= 22
        for _ in range(count):
            lay.row(c, y, inv.line_items[idx], idx)
            y -= lay.row_h
            idx += 1
        if p == n - 1:
            lay.totals(c, y - 14)
        else:
            lay.carry(c, y)
        lay.footer(c, p + 1, n)
        c.showPage()
    c.save()
    return n


def render_scanned(pdf: Path, png: Path, seed: int) -> None:
    """Rasterize a one-page PDF at 150 dpi and degrade it like a scan:
    rotate 1-3 degrees either way, add Gaussian noise, blur, JPEG round-trip."""
    import numpy as np
    import pypdfium2 as pdfium
    from PIL import Image, ImageFilter

    rng = random.Random(seed)
    doc = pdfium.PdfDocument(str(pdf))
    try:
        if len(doc) != 1:
            raise ValueError(f"scanned variant needs a 1-page PDF, got {len(doc)}")
        img = doc[0].render(scale=150 / 72).to_pil().convert("L")
    finally:
        doc.close()
    angle = rng.uniform(1.0, 3.0) * rng.choice([-1, 1])
    img = img.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=235)
    img = img.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.5, 0.9)))
    arr = np.asarray(img, dtype=np.float32)
    noise = np.random.default_rng(seed).normal(0.0, rng.uniform(8, 14), arr.shape)
    arr = np.clip(arr * rng.uniform(0.90, 0.97) + noise + 6, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=rng.randint(45, 65))
    buf.seek(0)
    Image.open(buf).convert("L").save(png, format="PNG", optimize=True)
