"""Report charts, drawn only from the committed results JSON.

    python -m audit.report.charts            # writes audit/report/*.png

``make_charts(results_dir, out_dir)`` writes:
  before_after.png  field accuracy (lenient), silent-error and missing-value rates and
                    invoices fully correct, docai-before vs docai-after
  models.png        invoices fully correct (lenient), silent errors, review rate, cost per
                    invoice and median latency for docai-after / gemini-after (and
                    local-after if a results file exists; the local run was deferred)
A chart whose inputs are missing is skipped. ``field_accuracy`` values may be None
(a field scored in no document); such bars are left out and labelled "n/a".
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO / "audit" / "results"
OUT_DIR = REPO / "audit" / "report"

FIELDS = ["vendor_name", "invoice_id", "invoice_date", "due_date", "currency",
          "subtotal", "tax_total", "total",
          "line.description", "line.quantity", "line.unit_price", "line.amount"]
LABELS = {"vendor_name": "Vendor", "invoice_id": "Invoice no.", "invoice_date": "Invoice date",
          "due_date": "Due date", "currency": "Currency", "subtotal": "Subtotal",
          "tax_total": "Tax", "total": "Total", "line.description": "Line description",
          "line.quantity": "Line quantity", "line.unit_price": "Line unit price",
          "line.amount": "Line amount"}
MODEL_RUNS = [("docai-after", "App (Document AI)\nafter fixes"),
              ("gemini-after", "Gemini 3.8 Flash\n+ same checks"),
              ("local-after", "Local model\n+ same checks")]

# Reference palette (dataviz skill, light mode): blue, orange, aqua; recessive ink.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
BEFORE = "#a3a29c"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3de", "#fcfcfb"


def _load(results_dir: Path, run: str) -> dict | None:
    p = Path(results_dir) / f"{run}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.title.set_color(INK)


def _pct(v):
    return None if v is None else 100.0 * v


def before_after(before: dict, after: dict, dest: Path) -> Path:
    fb = before["aggregate_lenient"]["field_accuracy"]
    fa = after["aggregate_lenient"]["field_accuracy"]
    fields = [f for f in FIELDS if f in fb or f in fa]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.2), gridspec_kw={"width_ratios": [2.1, 1.3]},
                                   facecolor=SURFACE)
    h = 0.38
    ys = list(range(len(fields)))[::-1]
    for (data, colour, label, off) in ((fb, BEFORE, "Before", h / 2), (fa, SERIES[0], "After fixes", -h / 2)):
        for y, f in zip(ys, fields):
            v = _pct(data.get(f))
            if v is None:
                ax1.text(1, y + off, "n/a", va="center", fontsize=7, color=INK2)
                continue
            ax1.barh(y + off, v, height=h - 0.04, color=colour, label=label if y == ys[0] else None)
            ax1.text(v + 1, y + off, f"{v:.0f}", va="center", fontsize=7, color=INK2)
    ax1.set_yticks(ys, [LABELS.get(f, f) for f in fields])
    ax1.set_xlim(0, 112)
    ax1.set_xlabel("Field accuracy, lenient (% of scored values correct)", fontsize=8, color=INK2)
    ax1.set_title("Field accuracy: the app before vs after fixes", fontsize=10, loc="left")
    ax1.legend(frameon=False, fontsize=8, loc="lower right")
    ax1.xaxis.grid(True, color=GRID, linewidth=0.6)
    ax1.set_axisbelow(True)
    _style(ax1)

    rows = [("Silent errors\n(% of fields)", before["aggregate_lenient"]["silent_errors"]["rate"] * 100,
             after["aggregate_lenient"]["silent_errors"]["rate"] * 100),
            ("Missing\nvalues (% of\nfields)", before["aggregate_lenient"]["missing"]["rate"] * 100,
             after["aggregate_lenient"]["missing"]["rate"] * 100),
            ("Invoices\nfully correct\n(%)", before["aggregate_lenient"]["invoice_fully_correct_pct"],
             after["aggregate_lenient"]["invoice_fully_correct_pct"])]
    x = range(len(rows))
    top = max(max(b, a) for _, b, a in rows) or 1
    for i, (name, b, a) in enumerate(rows):
        ax2.bar(i - 0.2, b, width=0.38, color=BEFORE, label="Before" if i == 0 else None)
        ax2.bar(i + 0.2, a, width=0.38, color=SERIES[0], label="After fixes" if i == 0 else None)
        for xx, v in ((i - 0.2, b), (i + 0.2, a)):
            ax2.text(xx, v + top * 0.01, f"{v:.1f}", ha="center", va="bottom", fontsize=7, color=INK2)
    ax2.set_ylim(0, top * 1.12)
    ax2.set_xticks(list(x), [r[0] for r in rows])
    ax2.set_title("Lenient scoring, 53 invoices", fontsize=10, loc="left")
    ax2.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax2.set_axisbelow(True)
    _style(ax2)
    fig.tight_layout()
    fig.savefig(dest, dpi=160, facecolor=SURFACE)
    plt.close(fig)
    return dest


def models(runs: list[tuple[str, str, dict]], dest: Path) -> Path:
    metrics = [
        ("Invoices fully correct\n(%, lenient)", lambda r: r["aggregate_lenient"]["invoice_fully_correct_pct"], "{:.1f}"),
        ("Silent errors\n(count, lenient)", lambda r: r["aggregate_lenient"]["silent_errors"]["count"], "{:.0f}"),
        ("Review rate\n(% of invoices)", lambda r: 100 * r["aggregate_lenient"]["review_rate"], "{:.1f}"),
        ("Cost per invoice\n(US cents)", lambda r: 100 * r["summary"]["api_cost_usd"] / max(r["summary"]["n_docs"], 1), "{:.2f}"),
        ("Median latency\n(seconds)", lambda r: r["summary"].get("median_latency_s") or 0.0, "{:.1f}"),
    ]
    fig, axes = plt.subplots(1, len(metrics), figsize=(11, 3.4), facecolor=SURFACE)
    for ax, (title, fn, fmt) in zip(axes, metrics):
        vals = [fn(r) for _, _, r in runs]
        for i, v in enumerate(vals):
            ax.bar(i, v, width=0.6, color=SERIES[i % len(SERIES)])
            ax.text(i, v, fmt.format(v), ha="center", va="bottom", fontsize=8, color=INK)
        ax.set_xticks(range(len(runs)), [""] * len(runs))
        ax.set_title(title, fontsize=9, loc="left")
        top = max(vals) if vals and max(vals) > 0 else 1
        ax.set_ylim(0, top * 1.2)
        ax.yaxis.grid(True, color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
        _style(ax)
    handles = [plt.Rectangle((0, 0), 1, 1, color=SERIES[i % len(SERIES)]) for i in range(len(runs))]
    fig.legend(handles, [lab.replace("\n", " ") for _, lab, _ in runs], loc="lower center",
               ncol=len(runs), frameon=False, fontsize=8)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(dest, dpi=160, facecolor=SURFACE)
    plt.close(fig)
    return dest


def make_charts(results_dir, out_dir) -> list[Path]:
    results_dir, out_dir = Path(results_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    before, after = _load(results_dir, "docai-before"), _load(results_dir, "docai-after")
    if before and after:
        written.append(before_after(before, after, out_dir / "before_after.png"))
    runs = [(n, lab, r) for n, lab in MODEL_RUNS if (r := _load(results_dir, n))]
    if runs:
        written.append(models(runs, out_dir / "models.png"))
    return written


if __name__ == "__main__":
    for p in make_charts(RESULTS_DIR, OUT_DIR):
        print(p.relative_to(REPO).as_posix())
