"""BL-12: Diagnostic report export helpers (PDF, JSON, CSV)."""

import csv
import json
from datetime import datetime
from typing import Dict, List, Optional

from fpdf import FPDF


def build_export_payload(
    mode: str,
    fields_data: Dict[str, str],
    timestamp: Optional[datetime] = None,
    warnings: Optional[List[str]] = None,
    failed: bool = False,
) -> dict:
    """Build a normalized export dictionary for self or target mode."""
    stamp = (timestamp or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "mode": mode,
        "generated": stamp,
        "status": "Failed" if failed else "Success",
        "fields": dict(fields_data),
        "warnings": list(warnings or []),
    }


def export_json(payload: dict, filepath: str) -> None:
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def export_csv(payload: dict, filepath: str) -> None:
    with open(filepath, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Field", "Value"])
        writer.writerow(["Mode", payload["mode"]])
        writer.writerow(["Generated", payload["generated"]])
        writer.writerow(["Status", payload["status"]])
        for key, value in payload["fields"].items():
            writer.writerow([key, value])
        if payload["warnings"]:
            writer.writerow(["Warnings", "; ".join(payload["warnings"])])


def _latin1_safe(text: str) -> str:
    return str(text).encode("latin-1", "replace").decode("latin-1")


def export_pdf(payload: dict, filepath: str) -> None:
    pdf = FPDF()
    pdf.add_page()

    title = (
        "Target IP Diagnostic Report"
        if payload["mode"] == "target"
        else "Public IP Diagnostic Report"
    )
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(95, 105, 115)
    pdf.cell(
        0,
        7,
        f"Generated: {payload['generated']}  |  Status: {payload['status']}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(4)

    # Table Header
    pdf.set_text_color(0, 0, 0)
    pdf.set_fill_color(230, 240, 234)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(55, 9, "Field", border=1, fill=True)
    pdf.cell(135, 9, "Value", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")

    # Table Rows
    pdf.set_font("Helvetica", "", 11)
    for key, value in payload["fields"].items():
        pdf.cell(55, 8, _latin1_safe(key), border=1)
        pdf.cell(
            135, 8, _latin1_safe(value), border=1, new_x="LMARGIN", new_y="NEXT"
        )

    # Warnings / Errors block
    if payload["warnings"]:
        pdf.ln(5)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(179, 38, 30)
        pdf.cell(0, 8, "Warnings / Errors:", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(40, 40, 40)
        for warning in payload["warnings"]:
            pdf.multi_cell(0, 6, f"- {_latin1_safe(warning)}")

    pdf.output(filepath)