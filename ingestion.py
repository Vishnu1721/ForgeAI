"""Bounded document extraction. Preview only; never creates a quote."""
import csv
import io
import zipfile
from pathlib import Path

MAX_BYTES = 2 * 1024 * 1024
MAX_TEXT = 20000

def tabular(rows):
    rows = iter(rows)
    header = next(rows, ())
    names = [str(x or "").strip().lower() for x in header]
    required = ("description", "quantity", "unit")
    if any(names.count(x) != 1 for x in required):
        raise ValueError("Expected unique description, quantity, unit columns")
    indices = [names.index(x) for x in required]
    result = []
    for row in rows:
        if not any(x is not None and str(x).strip() for x in row):
            continue
        if len(result) >= 200 or len(row) <= max(indices):
            raise ValueError("Too many rows or incomplete row")
        desc, qty, unit = (str(row[i] or "").strip() for i in indices)
        if not desc or any(c in desc for c in "\n\r;,") or not qty.isascii() or not qty.isdecimal() or not 0 < int(qty) <= 1000000 or unit.lower() not in ("kg", "l", "liter", "liters", "m"):
            raise ValueError("Invalid product row: " + str(len(result)+2))
        result.append(f"{qty} {unit} of {desc}")
    return "\n".join(result)

def document_text(filename, data):
    if not data or len(data) > MAX_BYTES:
        raise ValueError("File must be between 1 byte and 2 MiB")
    ext = Path(filename).suffix.lower()
    if ext == ".txt":
        text = data.decode("utf-8-sig")
    elif ext == ".csv":
        text = tabular(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
    elif ext == ".xlsx":
        from openpyxl import load_workbook
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if len(archive.infolist()) > 1000 or sum(i.file_size for i in archive.infolist()) > 16 * 1024 * 1024:
                raise ValueError("Workbook exceeds expanded size limit")
        book = load_workbook(io.BytesIO(data), read_only=True, data_only=False, keep_links=False)
        try:
            if len(book.worksheets) != 1:
                raise ValueError("Upload a single-sheet workbook")
            sheet = book.active
            if (sheet.max_row or 0) > 201 or (sheet.max_column or 0) > 30:
                raise ValueError("Workbook exceeds row or column limit")
            text = tabular(sheet.iter_rows(values_only=True))
        finally:
            book.close()
    elif ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted or len(reader.pages) > 20:
            raise ValueError("Encrypted PDFs or PDFs over 20 pages are unsupported")
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
            if sum(map(len, parts)) > MAX_TEXT:
                raise ValueError("Extracted text exceeds limit")
        text = "\n".join(parts)
    else:
        raise ValueError("Supported formats: TXT, CSV, XLSX, PDF")
    if not text.strip() or len(text) > MAX_TEXT:
        raise ValueError("No readable text or text exceeds 20,000 characters")
    return text.strip()
