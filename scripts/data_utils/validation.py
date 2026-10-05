"""File validation utilities (OOP + generators)."""
import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence


@dataclass
class ValidationResult:
    ok: bool
    errors: List[str] = field(default_factory=list)
    rows_checked: int = 0


class FileValidator:
    """Validate files before they enter the pipeline.

    Args:
        allowed_extensions: e.g. {".csv", ".json", ".xml", ".log"}.
        max_size_mb: reject files larger than this (None = no limit).
        required_columns: for CSVs, columns that must exist in the header.
    """

    def __init__(
        self,
        allowed_extensions: Sequence[str] = (".csv", ".json", ".xml", ".log"),
        max_size_mb: Optional[float] = 100.0,
        required_columns: Sequence[str] = (),
    ):
        self.allowed_extensions = {e.lower() for e in allowed_extensions}
        self.max_size_mb = max_size_mb
        self.required_columns = list(required_columns)

    # -- basic checks -------------------------------------------------
    def check_exists_size_ext(self, path: str) -> List[str]:
        errors: List[str] = []
        p = Path(path)
        if not p.exists():
            return [f"{path}: file does not exist"]
        if not p.is_file():
            return [f"{path}: not a regular file"]
        if p.suffix.lower() not in self.allowed_extensions:
            errors.append(f"{path}: extension {p.suffix!r} not in {sorted(self.allowed_extensions)}")
        if self.max_size_mb is not None:
            size_mb = p.stat().st_size / (1024 * 1024)
            if size_mb > self.max_size_mb:
                errors.append(f"{path}: size {size_mb:.1f}MB exceeds {self.max_size_mb}MB")
        return errors

    def validate_csv_header(self, path: str, required: Optional[Sequence[str]] = None) -> ValidationResult:
        req = list(required) if required is not None else self.required_columns
        try:
            with open(path, newline="", encoding="utf-8") as f:
                header = next(csv.reader(f), None)
        except OSError as exc:
            return ValidationResult(False, [f"{path}: cannot read ({exc})"])
        if not header:
            return ValidationResult(False, [f"{path}: empty file / missing header"])
        missing = [c for c in req if c not in header]
        if missing:
            return ValidationResult(False, [f"{path}: missing columns {missing}"])
        return ValidationResult(True, [], 0)

    # -- streaming record validation ----------------------------------
    def iter_csv_errors(
        self, path: str, schema: Optional[Dict[str, type]] = None, required: Optional[Sequence[str]] = None
    ) -> Iterator[str]:
        """Yield one error string per bad CSV row (generator: constant memory)."""
        req = list(required) if required is not None else self.required_columns
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                yield f"{path}: missing header"
                return
            missing = [c for c in req if c not in reader.fieldnames]
            if missing:
                yield f"{path}: header missing columns {missing}"
                return
            for n, row in enumerate(reader, start=2):  # line numbers (header=1)
                for col in req:
                    if not (row.get(col) or "").strip():
                        yield f"{path}:{n}: empty required field {col!r}"
                if schema:
                    for col, typ in schema.items():
                        val = (row.get(col) or "").strip()
                        if not val:
                            continue
                        try:
                            typ(val)
                        except ValueError:
                            yield f"{path}:{n}: field {col!r}={val!r} is not {typ.__name__}"

    def validate_json_records(self, data, required_fields: Sequence[str] = ()) -> ValidationResult:
        rows = data if isinstance(data, list) else [data]
        errors: List[str] = []
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                errors.append(f"row {i}: not an object")
                continue
            for fld in required_fields:
                if fld not in row or row[fld] in (None, ""):
                    errors.append(f"row {i}: missing/empty field {fld!r}")
        return ValidationResult(not errors, errors, len(rows))

    # -- dispatcher ----------------------------------------------------
    def validate(self, path: str, **kwargs) -> ValidationResult:
        errors = self.check_exists_size_ext(path)
        if errors and "does not exist" in errors[0]:
            return ValidationResult(False, errors)
        p = Path(path)
        suffix = p.suffix.lower()
        rows = 0
        if suffix == ".csv":
            hdr = self.validate_csv_header(path, kwargs.get("required_columns"))
            errors += hdr.errors
            schema = kwargs.get("schema")
            row_errors = list(self.iter_csv_errors(path, schema=schema,
                                                   required=kwargs.get("required_columns", self.required_columns)))
            errors += row_errors
            with open(path, encoding="utf-8") as _f:
                rows = max(0, sum(1 for _ in _f) - 1)
        elif suffix == ".json":
            try:
                data = json.loads(Path(path).read_text(encoding="utf-8"))
                res = self.validate_json_records(data, kwargs.get("required_fields", ()))
                errors += res.errors
                rows = res.rows_checked
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"{path}: invalid JSON ({exc})")
        elif suffix == ".xml":
            try:
                import xml.etree.ElementTree as ET

                ET.parse(str(p))
            except ET.ParseError as exc:
                errors.append(f"{path}: invalid XML ({exc})")
        return ValidationResult(not errors, errors, rows)
