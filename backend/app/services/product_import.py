"""Bulk product import from CSV / Excel (FR-05).

Each row is validated with the same rules as a manual product (ProductIn via ProductImportRow) and created
through ProductService, so the same change hook fires. Invalid rows are skipped and reported.
"""

import io
import re
from typing import Any

import pandas as pd
from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas.products import ImportFailure, ImportResult, ProductImportRow
from app.services.products import ProductService

COLUMNS = ["name", "description", "price", "sizes", "colours", "stock", "photos"]
REQUIRED_COLUMNS = ["name", "price"]
TEMPLATE_CSV = (
    ",".join(COLUMNS) + "\n"
    "Cotton Panjabi,Comfortable everyday panjabi,1850,M|L|XL,White|Navy,24,https://example.com/panjabi.jpg\n"
)
# Spreadsheet column -> product field
_FIELD_FOR_COLUMN = {"stock": "stock_count"}
_COLUMN_FOR_FIELD = {"stock_count": "stock"}


class ImportFileError(Exception):
    """The whole file is unusable (wrong type, empty, missing columns, too big)."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _read_table(filename: str, data: bytes) -> pd.DataFrame:
    name = (filename or "").lower()
    try:
        if name.endswith(".csv"):
            return pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False, encoding="utf-8-sig")
        if name.endswith(".xlsx"):
            if not data.startswith(b"PK"):
                raise ImportFileError("This is not a valid .xlsx file")
            return pd.read_excel(io.BytesIO(data), dtype=str, keep_default_na=False, engine="openpyxl")
    except ImportFileError:
        raise
    except pd.errors.EmptyDataError:
        raise ImportFileError("The file is empty")
    except UnicodeDecodeError:
        raise ImportFileError("Could not read the CSV file. Save it as UTF-8 and try again")
    except Exception:
        raise ImportFileError("Could not read the file. Check that it is a valid CSV or .xlsx file")
    raise ImportFileError("Only .csv and .xlsx files are supported")


def parse_file(filename: str, data: bytes) -> list[tuple[int, dict[str, str]]]:
    """Return (row_number, raw values) for each non-blank row. Row 1 is the header, data starts at row 2."""
    s = get_settings()
    if not data:
        raise ImportFileError("The file is empty")
    if len(data) > s.max_import_mb * 1024 * 1024:
        raise ImportFileError(f"The file is larger than {s.max_import_mb} MB", 413)
    df = _read_table(filename, data)
    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ImportFileError(
            f"Missing required column(s): {', '.join(missing)}. Expected columns: {', '.join(COLUMNS)}"
        )
    rows: list[tuple[int, dict[str, str]]] = []
    for i, rec in enumerate(df.to_dict("records")):
        values = {c: str(rec.get(c, "") or "").strip() for c in COLUMNS}
        if any(values.values()):  # skip fully blank rows
            rows.append((i + 2, values))
    if not rows:
        raise ImportFileError("The file has no product rows")
    if len(rows) > s.max_import_rows:
        raise ImportFileError(f"The file has more than {s.max_import_rows} rows", 413)
    return rows


def _split(value: str, separators: str) -> list[str]:
    return [p.strip() for p in re.split(separators, value) if p.strip()]


def _normalise_int(value: str) -> str:
    """Excel can hand back whole numbers as '24.0'."""
    return re.sub(r"^(-?\d+)\.0+$", r"\1", value)


def to_product_fields(values: dict[str, str]) -> dict[str, Any]:
    return {
        "name": values["name"],
        "description": values["description"],
        "price": values["price"].replace(",", "") if values["price"] else values["price"],
        "sizes": _split(values["sizes"], r"[|,]"),
        "colours": _split(values["colours"], r"[|,]"),
        "stock_count": _normalise_int(values["stock"]) if values["stock"] else 0,
        "photos": _split(values["photos"], r"\|"),
    }


def _reasons(err: ValidationError) -> list[str]:
    out: list[str] = []
    for e in err.errors():
        field = str(e["loc"][0]) if e["loc"] else "row"
        column = _COLUMN_FOR_FIELD.get(field, field)
        msg = e["msg"]
        if field == "name" and e["type"] in ("string_too_short", "missing"):
            text = "missing name"
        elif field == "name" and "required" in msg:
            text = "missing name"
        elif msg.startswith("Value error, "):
            text = msg[len("Value error, ") :]
        elif msg.startswith("Input should be "):
            text = f"{column} must be {msg[len('Input should be '):]}"
        else:
            text = f"{column}: {msg}"
        if text not in out:
            out.append(text)
    return out


def import_rows(svc: ProductService, rows: list[tuple[int, dict[str, str]]]) -> ImportResult:
    failures: list[ImportFailure] = []
    imported = 0
    for row_number, values in rows:
        name = values["name"]
        try:
            fields = ProductImportRow(**to_product_fields(values)).model_dump()
        except ValidationError as e:
            failures.append(ImportFailure(row=row_number, name=name, reasons=_reasons(e)))
            continue
        try:
            svc.create(**fields)
            imported += 1
        except Exception:
            svc.db.rollback()
            failures.append(ImportFailure(row=row_number, name=name, reasons=["could not be saved"]))
    return ImportResult(rows_read=len(rows), imported=imported, failed=len(failures), failures=failures)
