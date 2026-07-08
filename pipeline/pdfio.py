"""PDF input support — render the first page to a PNG the pipeline can eat.

Civil-record documents are single-page in practice; when a multi-page PDF
arrives we take page 1 and tell the caller how many pages were ignored.
pypdfium2 is pure-wheel (no poppler/system deps), so this works identically
on the Windows dev box and inside the deployment container.
"""
from __future__ import annotations

from pathlib import Path

PDF_SUFFIXES = {".pdf"}


def is_pdf(path: str | Path) -> bool:
    return Path(path).suffix.lower() in PDF_SUFFIXES


def pdf_first_page_png(pdf_path: str | Path, out_png: str | Path, dpi: int = 220) -> int:
    """Render page 1 of `pdf_path` to `out_png`. Returns total page count."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        n_pages = len(pdf)
        if n_pages == 0:
            raise ValueError(f"PDF has no pages: {pdf_path}")
        page = pdf[0]
        bitmap = page.render(scale=dpi / 72)
        pil = bitmap.to_pil()
        Path(out_png).parent.mkdir(parents=True, exist_ok=True)
        pil.save(str(out_png))
    finally:
        pdf.close()
    return n_pages
