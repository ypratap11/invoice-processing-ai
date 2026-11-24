"""Seeded generator of truth invoices, including the audit's hard cases.

Every value is invented: vendor and customer names, addresses (``.example``
e-mail domains, 555-01xx phone numbers) and items. Truth values are what a
careful human would key from the printed document:

* a discount is a negative line item; ``sum(line.amount) == subtotal``;
* ``subtotal + tax_total == total`` except for ``bad_total`` documents, whose
  truth total is the printed (wrong) total;
* ``multi_tax``: ``tax_total`` is the sum of the printed tax lines;
* ``non_usd``: currency is the ISO code; amounts are numeric even when
  printed ``1.234,56`` (those documents also carry the tag ``decimal_comma``);
* ``dmy_date``: dates are printed day-first; truth is the real date;
* a few documents print no due date ("Due on receipt") -> truth ``None``.

``generate_invoices`` returns :class:`GenInvoice` objects: real ``Invoice``
instances that also carry print-only details (customer, tax lines, number and
date formats) used by :mod:`audit.generate.render`. ``save_invoice`` writes
only the ``Invoice`` fields.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from audit.schema import Invoice, LineItem

LAYOUTS = (1, 2, 3, 4, 5)
CENT = Decimal("0.01")


def q2(v: Decimal) -> Decimal:
    return v.quantize(CENT, rounding=ROUND_HALF_UP)


def doc_id_for(i: int) -> str:
    return f"gen-{i + 1:03d}"


def layout_for(i: int) -> int:
    """Layout used for the i-th (0-based) generated document."""
    return LAYOUTS[i % len(LAYOUTS)]


@dataclass
class GenInvoice(Invoice):
    customer: tuple[str, ...] = ()        # bill-to block lines
    vendor_address: tuple[str, ...] = ()
    tax_lines: list[tuple[str, Decimal]] = field(default_factory=list)
    po_number: str | None = None
    terms: str = ""
    decimal_comma: bool = False
    date_style: str = "mdy"               # "mdy" | "dmy"


# --- the 40-document plan -------------------------------------------------
# (tags, currency, extra) ; extra keys: comma (decimal_comma), nodue
_PLAN: list[tuple[tuple[str, ...], str, dict]] = [
    (("multipage",), "USD", {}),                                    # 001
    (("multipage", "discount"), "USD", {}),                         # 002
    (("multipage", "multi_tax"), "USD", {}),                        # 003
    (("multipage", "non_usd", "dmy_date"), "EUR", {"comma": 1}),    # 004
    (("multipage",), "USD", {"nodue": 1}),                          # 005
    (("multipage", "discount"), "USD", {}),                         # 006
    (("discount",), "USD", {}),                                     # 007
    (("discount", "scanned"), "USD", {}),                           # 008
    (("discount",), "USD", {}),                                     # 009
    (("discount", "scanned"), "USD", {}),                           # 010
    (("discount",), "USD", {}),                                     # 011
    (("discount",), "USD", {}),                                     # 012
    (("multi_tax",), "USD", {}),                                    # 013
    (("multi_tax", "scanned"), "USD", {}),                          # 014
    (("multi_tax",), "USD", {}),                                    # 015
    (("multi_tax",), "USD", {"nodue": 1}),                          # 016
    (("multi_tax", "non_usd", "dmy_date"), "INR", {}),              # 017
    (("multi_tax", "non_usd", "dmy_date"), "INR", {}),              # 018
    (("non_usd", "dmy_date"), "EUR", {"comma": 1}),                 # 019
    (("non_usd", "dmy_date", "scanned"), "EUR", {"comma": 1}),      # 020
    (("non_usd", "dmy_date"), "EUR", {}),                           # 021
    (("non_usd", "dmy_date"), "GBP", {}),                           # 022
    (("non_usd", "dmy_date", "discount"), "GBP", {}),               # 023
    (("non_usd", "dmy_date"), "INR", {}),                           # 024
    (("non_usd", "dmy_date", "scanned"), "GBP", {}),                # 025
    (("dmy_date",), "USD", {}),                                     # 026
    (("dmy_date", "scanned"), "USD", {}),                           # 027
    (("dmy_date",), "USD", {}),                                     # 028
    (("dmy_date", "scanned"), "USD", {}),                           # 029
    (("dmy_date",), "USD", {}),                                     # 030
    (("dmy_date",), "USD", {}),                                     # 031
    (("bad_total",), "USD", {}),                                    # 032
    (("bad_total", "scanned"), "USD", {}),                          # 033
    (("bad_total", "discount"), "USD", {}),                         # 034
    (("bad_total", "non_usd", "dmy_date"), "EUR", {"comma": 1}),    # 035
    (("scanned",), "USD", {"nodue": 1}),                            # 036
    (("scanned",), "USD", {}),                                      # 037
    ((), "USD", {}),                                                # 038
    ((), "USD", {"nodue": 1}),                                      # 039
    ((), "USD", {}),                                                # 040
]

# --- invented names ---------------------------------------------------------
_VENDORS = [
    ("Quillfeather Office Supply", "office"), ("Marrowgate Fasteners", "hardware"),
    ("Tindle & Oakridge Consulting", "services"), ("Bluefen Catering Co.", "catering"),
    ("Corvane Print Works", "printing"), ("Halloway Janitorial Group", "cleaning"),
    ("Pemberly Lab Instruments", "lab"), ("Driftmere Freight Lines", "logistics"),
    ("Saffronvale Stationers", "office"), ("Kestrel Bolt & Bearing", "hardware"),
    ("Orrin Vasquez Advisory", "services"), ("Larkspur Kitchen Provisions", "catering"),
    ("Inkwell Meadow Press", "printing"), ("Brisbin Facility Care", "cleaning"),
    ("Gallowmere Scientific", "lab"), ("Cobbleton Haulage", "logistics"),
    ("Thistledown Paper Goods", "office"), ("Ferrowick Industrial Parts", "hardware"),
    ("Penhallow Data Studio", "services"), ("Wrenfield Events Kitchen", "catering"),
    ("Moss & Mallory Signage", "printing"), ("Clearbrook Sanitation", "cleaning"),
    ("Ambergrove Bioreagents", "lab"), ("Sterling Ashby Couriers", "logistics"),
    ("Nettlecombe Desk Supply", "office"), ("Grindell Hydraulics", "hardware"),
    ("Varnell Systems Integration", "services"), ("Hollin Farmhouse Foods", "catering"),
    ("Pressmark Lithographic", "printing"), ("Ostrander Cleaning Crew", "cleaning"),
    ("Quenby Precision Optics", "lab"), ("Rookwood Cartage", "logistics"),
    ("Blythe Corner Supplies", "office"), ("Tallisker Machine Shop", "hardware"),
    ("Ellery Quarles Training", "services"), ("Pipersfield Bakehouse", "catering"),
    ("Carrow Digital Imaging", "printing"), ("Whitlock Window Cleaning", "cleaning"),
    ("Loxley Analytical", "lab"), ("Fennimore Removals", "logistics"),
]

_CUSTOMERS = [
    ("Harborline Medical Group", "1180 Calder Avenue, Suite 400", "Portland, OR 97209"),
    ("Northvale School District", "77 Birchmont Road", "Duluth, MN 55803"),
    ("Pellwood Architects LLP", "9 Greyfriars Lane", "Leeds LS1 4QW"),
    ("Junebrook Hotels Ltd", "220 Marlow Street", "Bristol BS1 6HG"),
    ("Kalinda Retail Pvt Ltd", "14 MG Ring Road, 3rd Floor", "Bengaluru 560001"),
    ("Ostwind Maschinenbau GmbH", "Lindenstrasse 42", "80331 Muenchen"),
    ("Corrigan Family Dental", "455 Willow Creek Blvd", "Austin, TX 78704"),
    ("Brantley Civic Theatre", "31 Commerce Square", "Richmond, VA 23219"),
    ("Valmont Biotech Inc.", "6200 Research Parkway", "San Diego, CA 92121"),
    ("Tessaro Logistics SRL", "Via Alberata 18", "20121 Milano"),
    ("Greywater Credit Union", "800 Front Street", "Boise, ID 83702"),
    ("Mirefield Parish Council", "The Old Forge, High Street", "York YO1 7HB"),
]

_CATALOG = {
    "office": (["Copy paper A4 80gsm", "Ballpoint pens blue", "Gel pens black",
                "Lever arch files", "Sticky notes 76x76", "Desk organiser",
                "Whiteboard markers", "Stapler heavy duty", "Toner cartridge",
                "Envelopes C5", "Archive boxes", "Highlighters assorted"],
               ["box of 10", "box of 50", "pack of 12", "case of 5", "single"],
               (2, 90)),
    "hardware": (["Hex bolt zinc", "Lock nut nylon", "Flat washer", "Socket cap screw",
                  "Ball bearing 6204", "Threaded rod", "Spring washer", "Wing nut",
                  "Coach screw", "Shim plate"],
                 ["M6", "M8", "M10", "M12", "M16"], (1, 60)),
    "services": (["Process review workshop", "Data migration support",
                  "Project management", "Requirements analysis", "Solution design",
                  "On-site training day", "Report development", "Security assessment",
                  "Systems testing", "Change management"],
                 ["senior", "standard", "junior", "remote", "on-site"], (85, 240)),
    "catering": (["Breakfast platter", "Sandwich tray", "Fruit bowl", "Coffee service",
                  "Hot lunch buffet", "Pastry selection", "Juice carafe",
                  "Salad station", "Dessert tray", "Vegetarian wraps"],
                 ["serves 10", "serves 20", "serves 30", "per person", "half tray"],
                 (4, 180)),
    "printing": (["Business cards", "Tri-fold brochures", "Vinyl banner",
                  "Letterhead", "Foam board signs", "Presentation folders",
                  "Window decals", "Product labels", "Event posters", "Notepads"],
                 ["full colour", "two colour", "matte", "gloss", "premium stock"],
                 (15, 400)),
    "cleaning": (["Office deep clean", "Carpet shampoo", "Window cleaning",
                  "Restroom sanitising", "Floor buffing", "Waste removal",
                  "Kitchen degrease", "Upholstery clean", "Hand soap refill",
                  "Paper towel supply"],
                 ["per visit", "level 1", "level 2", "weekly", "monthly"], (25, 650)),
    "lab": (["Nitrile gloves", "Pipette tips 200ul", "Centrifuge tubes 15ml",
             "Petri dishes", "Buffer solution pH7", "Microscope slides",
             "Filter paper", "Cuvettes", "Sample vials", "Lab wipes"],
            ["case of 10", "pack of 100", "pack of 500", "sterile", "bulk"], (9, 320)),
    "logistics": (["Pallet freight", "Express courier", "Same-day delivery",
                   "Crating service", "Warehouse storage", "Fuel surcharge",
                   "Liftgate service", "Customs paperwork", "Insurance cover",
                   "Return shipment"],
                  ["zone A", "zone B", "zone C", "per pallet", "per kg"], (12, 520)),
}

_DISCOUNT_DESCS = ["Volume discount", "Loyalty discount", "Promotional credit",
                   "Early payment discount", "Credit for damaged goods"]

_STREETS = ["Fernhill Road", "Quarry Lane", "Ashcombe Way", "Millrace Drive",
            "Tanner Street", "Orchard Row", "Larch Court", "Beacon Hill Road"]
_US_CITIES = ["Columbus, OH 43215", "Madison, WI 53703", "Tucson, AZ 85701",
              "Raleigh, NC 27601", "Omaha, NE 68102", "Spokane, WA 99201"]
_CITY = {"EUR": ["1012 AB Amsterdam", "D02 X285 Dublin", "75011 Paris"],
         "GBP": ["Manchester M1 2AB", "Norwich NR2 1TD", "Cardiff CF10 1EP"],
         "INR": ["Pune 411001", "Chennai 600002", "Hyderabad 500081"]}

_US_TAX = [("State sales tax", "6.25"), ("City tax", "1.75"), ("County tax", "1.00"),
           ("Transit district tax", "0.50")]
_TAX_ONE = {"USD": [("Sales tax", "8.25"), ("Sales tax", "7.00"), ("Tax", "6.00"),
                    ("Sales tax", "9.50")],
            "EUR": [("VAT", "21"), ("VAT", "23"), ("VAT", "20")],
            "GBP": [("VAT", "20")],
            "INR": [("IGST", "18")]}

_ID_FORMATS = ["INV-{y}-{n:04d}", "{n:05d}", "A{k}-{n:05d}", "SI/{y2}/{n:04d}",
               "{y}{n:04d}", "INV{n:06d}", "CN-{n:04d}-{k}", "B{y2}-{n:03d}"]


def _make_lines(rng: random.Random, sector: str, n: int) -> list[LineItem]:
    bases, variants, (lo, hi) = _CATALOG[sector]
    combos = [f"{b} - {v}" for b in bases for v in variants]
    rng.shuffle(combos)
    lines = []
    for desc in combos[:n]:
        if sector == "services" and rng.random() < 0.6:
            qty = Decimal(rng.choice(["1.5", "2", "4", "6.5", "8", "12", "16", "0.5"]))
            desc = desc + " (hours)"
        else:
            qty = Decimal(rng.choice([1, 1, 2, 3, 4, 5, 6, 10, 12, 20, 24, 50]))
        unit = q2(Decimal(rng.randint(lo * 100, hi * 100)) / 100)
        lines.append(LineItem(desc, qty, unit, q2(qty * unit)))
    return lines


def generate_invoices(seed: int = 20261123, n: int = 40) -> list[Invoice]:
    rng = random.Random(seed)
    out: list[Invoice] = []
    used_ids: set[str] = set()
    for i in range(n):
        tags, currency, extra = _PLAN[i % len(_PLAN)]
        vendor, sector = _VENDORS[i % len(_VENDORS)]
        if i >= len(_VENDORS):  # only when n > 40
            vendor = f"{vendor} {i // len(_VENDORS) + 1}"
        comma = bool(extra.get("comma"))
        tags = list(tags) + (["decimal_comma"] if comma else [])

        if "multipage" in tags:
            n_lines = rng.randint(25, 40)
        elif "scanned" in tags:
            n_lines = rng.randint(2, 9)
        else:
            n_lines = rng.randint(2, 12)
        lines = _make_lines(rng, sector, n_lines)

        if "discount" in tags:
            gross = sum(li.amount for li in lines)
            pct = rng.choice([Decimal("5"), Decimal("7.5"), Decimal("10"), Decimal("12")])
            amt = q2(gross * pct / 100)
            desc = f"{rng.choice(_DISCOUNT_DESCS)} ({format(pct.normalize(), 'f')}%)"
            if rng.random() < 0.5:  # printed with qty 1 and a negative rate
                disc = LineItem(desc, Decimal("1"), -amt, -amt)
            else:                   # printed with qty/rate blank
                disc = LineItem(desc, None, None, -amt)
            lines.insert(rng.randint(len(lines) // 2, len(lines)), disc)

        subtotal = sum(li.amount for li in lines)
        if "multi_tax" in tags:
            if currency == "INR":
                rates = [("CGST", "9"), ("SGST", "9")]
            else:
                k = rng.choice([2, 2, 3])
                rates = [_US_TAX[0]] + rng.sample(_US_TAX[1:], k - 1)
        else:
            rates = [rng.choice(_TAX_ONE[currency])]
        tax_lines = [(f"{name} {rate}%", q2(subtotal * Decimal(rate) / 100))
                     for name, rate in rates]
        tax_total = sum(t for _, t in tax_lines)
        total = subtotal + tax_total
        if "bad_total" in tags:
            delta = rng.choice([Decimal("10.00"), Decimal("-1.00"), Decimal("100.00"),
                                Decimal("0.90")])
            total = total + delta

        inv_date = date(2026, 1, 1) + timedelta(days=rng.randint(0, 300))
        if extra.get("nodue"):
            due, terms = None, "Due on receipt"
        else:
            days = rng.choice([15, 30, 30, 45, 60])
            due, terms = inv_date + timedelta(days=days), f"Net {days}"

        while True:
            fmt = rng.choice(_ID_FORMATS)
            inv_id = fmt.format(y=inv_date.year, y2=inv_date.year % 100,
                                n=rng.randint(1, 9999),
                                k=rng.randint(1, 9))
            if inv_id not in used_ids:
                used_ids.add(inv_id)
                break

        cust = _CUSTOMERS[rng.randrange(len(_CUSTOMERS))]
        city = rng.choice(_US_CITIES if currency == "USD" else _CITY[currency])
        slug = "".join(ch for ch in vendor.lower().split()[0] if ch.isalpha())
        vaddr = (f"{rng.randint(10, 9800)} {rng.choice(_STREETS)}", city,
                 f"billing@{slug}.example",
                 f"Tel. 555-01{rng.randint(10, 99)}")
        po = f"PO-{rng.randint(10000, 99999)}" if rng.random() < 0.6 else None

        out.append(GenInvoice(
            vendor_name=vendor, invoice_id=inv_id, invoice_date=inv_date, due_date=due,
            currency=currency, subtotal=subtotal, tax_total=tax_total, total=total,
            line_items=lines, tags=tags, customer=cust, vendor_address=vaddr,
            tax_lines=tax_lines, po_number=po, terms=terms, decimal_comma=comma,
            date_style="dmy" if "dmy_date" in tags else "mdy",
        ))
    return out
