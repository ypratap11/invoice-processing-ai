# Test-set sources

`manifest.csv` lists every document (`doc_id,source,file,license,tags`; tags are
`;`-separated). Truth for a document is `<its directory>/<doc_id>.json`
(schema: `audit/schema.py`). Load with `audit.generate.testset.load_testset()`.

## Generated subset — `generated/gen-001` … `gen-040` (40 documents)

Synthetic, produced by `audit/generate/generator.py` (seed `20261123`) and
`audit/generate/render.py`; rebuild with
`audit/.venv/Scripts/python -m audit.generate.build` (byte-identical output).
All vendor/customer names, addresses (`.example` e-mail, 555-01xx phones) and
items are invented. No third-party content.

Truth conventions (what a careful human would key from the printed page):
- discount = a negative line item; `sum(line.amount) == subtotal`;
  `subtotal + tax_total == total` except `bad_total` (truth total = the printed, wrong total);
- `multi_tax`: `tax_total` = sum of the printed tax lines;
- `non_usd`: currency = ISO code (EUR/GBP/INR); `decimal_comma` docs print `1.234,56`, truth is numeric;
- `dmy_date`: dates printed day-first; truth is the real date;
- 4 documents print no due date ("Due on receipt") -> truth `due_date = null`;
- discount lines printed with blank qty/unit price have truth `quantity`/`unit_price = null`.

Layout of `gen-NNN` = `((NNN-1) mod 5) + 1` (`generator.layout_for`):
1 classic, 2 colour band, 3 monospace statement, 4 boxed meta / qty-first / `($x)` negatives,
5 European letter (amounts suffixed with the currency code). Each layout is used 8 times.
`scanned` documents are PNGs: the PDF rasterised at 150 dpi, rotated 1–3° either way,
blurred, Gaussian noise, JPEG round-trip (`render.render_scanned`). All are single-page;
`multipage` documents are 2 pages (≤10 pages everywhere).

## Public subset — `public/pub-001` … `pub-013` (13 documents)

- **Dataset:** katanaml-org/invoices-donut-data-v1 (Hugging Face), `test` split, rows 0–12 in file order.
- **URL:** https://huggingface.co/datasets/katanaml-org/invoices-donut-data-v1
  (file `data/test-00000-of-00001-56af6bd5ff7eb34d.parquet`, downloaded 2026-11-23).
- **License:** MIT (dataset card). The invoice images derive from
  Kozłowski, M., & Weichbroth, P. (2021). *Samples of electronic invoices* (Version 2) [Data set].
  Mendeley Data. https://doi.org/10.17632/tnj49gpmtz.2 — license CC BY 4.0.
- **Citation:** Katana ML, *invoices-donut-data-v1* (Hugging Face dataset), based on
  Kozłowski & Weichbroth (2021), doi:10.17632/tnj49gpmtz.2.
- **Files:** the dataset's original JPEG bytes (2481×3508, A4 at 300 dpi), unmodified.

Caveat for the report: these invoices are themselves machine-generated (one
template, Faker-style names/addresses, real e-commerce product titles as item
descriptions), so they add a third-party layout, not real-world scans.

### Label conversion
`seller` first line -> `vendor_name` (seller label is name+address in one string);
`invoice_no` -> `invoice_id`; `invoice_date` (MM/DD/YYYY) -> ISO; no due date is printed ->
`due_date = null`; summary `$` -> `currency = USD`; `total_net_worth`/`total_vat`/`total_gross_worth`
-> `subtotal`/`tax_total`/`total`; items: `item_qty` -> quantity, `item_net_price` -> unit_price,
`item_net_worth` (the pre-VAT line value; it sums to the subtotal) -> amount. Amounts are printed
`1 234,56`, so all 13 are tagged `decimal_comma`.

### Verification and corrections
Every image was opened and every truth value (vendor, id, date, totals, each line's
description/qty/unit price/amount) checked by eye. All numeric labels and dates were correct.
Corrections (dataset label -> printed text):

| doc | field | dataset label | corrected (as printed) |
|---|---|---|---|
| pub-002 | line 2 description | `Jams World Hawaiian 0 Dress Rayon SZ.L` | `Jams World Hawaiian Dress Rayon sz.L` (an unrenderable glyph prints as a box; omitted) |
| pub-004 | line 1 description | `Jordan Hydro 2 (TD)-Child Size` | `Jordan Hydro 2 (TD)-Child Size 10c` |
| pub-005 | line 5 description | `Nintendo Wii Console 2 Remotes …` | `Nintendo Wii Console - 2 Remotes …` |
| pub-005 | line 6 description | `… Black Console 20GB …` | `… Black Console 20 GB …` |
| pub-005 | line 7 description | `… Japan Tested Working` | `… Japan Tested Working 55` |
| pub-009 | line 3 description | `… Okay Picturebook 00000000` | `… Okay Picturebook` (trailing glyphs print as boxes) |
| pub-010 | vendor_name | `Rodriguez-jackson` | `Rodriguez-Jackson` |
| pub-011 | line 1 description | `PlayStation 5 Console Disc Version PREORDER"00OO` | `PlayStation 5 Console Disc Version **PREORDER**` (trailing boxes omitted) |
| pub-011 | line 5 description | `… White "I TESTED Working 11194` | `… White " / TESTED Working 11194` |

### Vendor names
Each public truth `vendor_name` is the first line of the dataset's `seller` label (after the
corrections above). `tests/audit/test_generator.py` checks the truth files against this list.

| doc | vendor_name |
|---|---|
| pub-001 | Bradley-Andrade |
| pub-002 | Hopkins and Sons |
| pub-003 | Trujillo-Hunt |
| pub-004 | Nichols-Barajas |
| pub-005 | Smith-Cook |
| pub-006 | Kaiser, Hays and Cook |
| pub-007 | Smith Ltd |
| pub-008 | Gregory, Patterson and Fischer |
| pub-009 | Gordon, Alvarado and Jones |
| pub-010 | Rodriguez-Jackson |
| pub-011 | Potts, Reed and Miller |
| pub-012 | Conley Ltd |
| pub-013 | Stone-Waller |

Rows not used and why: test row 13 has a malformed label (missing `item_net_worth`, and
its gross total `1579 929,37` disagrees with net+VAT); row 22's `seller` is a tax id.
Both show the dataset labels are not trustworthy unverified, which is why only hand-checked
rows are included.
