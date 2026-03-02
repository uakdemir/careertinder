import logging
from pathlib import Path

import pdfplumber

logger = logging.getLogger(__name__)


def extract_text_from_pdf(file_path: Path) -> str:
    """Extract text from a PDF file using pdfplumber.

    Handles multi-page PDFs and two-column layouts.
    Returns cleaned plain text with normalized whitespace.
    """
    pages_text: list[str] = []

    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
    except Exception:
        logger.exception("Failed to extract text from %s", file_path)
        raise

    full_text = "\n\n".join(pages_text)

    if not full_text.strip():
        logger.warning("No text extracted from %s. Consider using an OCR-processed version.", file_path)
        return ""

    # Normalize whitespace: collapse runs of spaces (but preserve newlines)
    lines = full_text.splitlines()
    cleaned_lines = [" ".join(line.split()) for line in lines]
    return "\n".join(cleaned_lines).strip()
