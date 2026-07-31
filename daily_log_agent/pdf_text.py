import io
from typing import Optional

import pdfplumber


def extract_text(pdf_bytes: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages).strip()


def extract_table_text(pdf_bytes: bytes) -> Optional[str]:
    """Best-effort: renders the first detected table as an aligned monospace
    text block (e.g. the Daily Log's Subject/Topics/Assignments table).
    Returns None if no table is found, or if pdf_bytes isn't a readable PDF -
    this is meant as a fallback-of-a-fallback, so it must never raise."""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                table = page.extract_table()
                if table:
                    return _format_table(table)
    except Exception:
        return None
    return None


def _format_table(rows: list) -> str:
    cleaned = [["" if cell is None else str(cell).strip() for cell in row] for row in rows]
    col_count = max(len(row) for row in cleaned)
    cleaned = [row + [""] * (col_count - len(row)) for row in cleaned]
    widths = [max(len(row[i]) for row in cleaned) for i in range(col_count)]

    lines = [" | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) for row in cleaned]
    if len(lines) > 1:
        lines.insert(1, "-+-".join("-" * w for w in widths))
    return "\n".join(lines)
