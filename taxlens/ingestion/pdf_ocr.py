"""
PDF / image invoice pipeline (outline).

On-premise stack (no cloud OCR):
- PDF text: PyMuPDF (fitz) or pdfplumber for text layers.
- Scanned PDF / images: Tesseract OCR via pytesseract + Pillow.

This module defines the contract; install optional extras per environment.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class InvoiceFields:
    seller_name: str | None = None
    buyer_name: str | None = None
    invoice_no: str | None = None
    invoice_date: str | None = None
    tax_id_seller: str | None = None
    tax_id_buyer: str | None = None
    amount_before_vat: float | None = None
    vat_amount: float | None = None
    total_amount: float | None = None
    raw_ocr_text: str | None = None


def extract_invoice_pdf(path: Path | str) -> InvoiceFields:
    """
    Placeholder: integrate PyMuPDF text extraction + regex / layout heuristics.
    For scanned docs, route to extract_invoice_image pipeline.
    """
    _ = Path(path)
    return InvoiceFields(raw_ocr_text="[PDF pipeline not installed — see README]")


def extract_invoice_image(path: Path | str) -> InvoiceFields:
    """
    Placeholder: pytesseract.image_to_string + field parsers.
    """
    _ = Path(path)
    return InvoiceFields(raw_ocr_text="[OCR pipeline not installed — see README]")


def normalize_invoice(fields: InvoiceFields) -> dict[str, Any]:
    return {k: v for k, v in fields.__dict__.items() if v is not None}
