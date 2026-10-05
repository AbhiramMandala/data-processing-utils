"""Data cleansing utilities (OOP + generators)."""
import re
from typing import Dict, Iterable, Iterator, List, Optional, Sequence

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_NULL_TOKENS = {"", "null", "none", "n/a", "na", "nan", "nil", "-"}


class DataCleaner:
    """Clean tabular records (dicts) row-by-row.

    Args:
        strip_strings: trim leading/trailing whitespace on all str values.
        null_tokens: case-insensitive strings treated as missing (→ None).
        normalize_email: strip + lowercase fields named email/e-mail.
        drop_empty_records: skip rows where every value is None.
        dedupe_keys: if set, drop repeat rows with same key tuple.
    """

    def __init__(
        self,
        strip_strings: bool = True,
        null_tokens: Sequence[str] = tuple(_NULL_TOKENS),
        normalize_email: bool = True,
        drop_empty_records: bool = True,
        dedupe_keys: Optional[Sequence[str]] = None,
    ):
        self.strip_strings = strip_strings
        self.null_tokens = {t.lower() for t in null_tokens}
        self.normalize_email = normalize_email
        self.drop_empty_records = drop_empty_records
        self.dedupe_keys = tuple(dedupe_keys) if dedupe_keys else None

    # -- single values / records -------------------------------------
    def clean_value(self, value, field: str = ""):
        if isinstance(value, str):
            v = value.strip() if self.strip_strings else value
            if v.lower() in self.null_tokens:
                return None
            if self.normalize_email and field.lower() in ("email", "e-mail", "e_mail"):
                v = v.lower()
                if v and not _EMAIL_RE.match(v):
                    return None  # invalid email -> missing
            return v if v != "" else None
        return value

    def clean_record(self, record: Dict) -> Optional[Dict]:
        cleaned = {k: self.clean_value(v, field=str(k)) for k, v in record.items()}
        if self.drop_empty_records and all(v is None for v in cleaned.values()):
            return None
        return cleaned

    # -- streaming (generators) --------------------------------------
    def clean_stream(self, records: Iterable[Dict]) -> Iterator[Dict]:
        """Yield cleaned records one-by-one (constant memory)."""
        seen = set()
        for rec in records:
            out = self.clean_record(rec)
            if out is None:
                continue
            if self.dedupe_keys:
                key = tuple(out.get(k) for k in self.dedupe_keys)
                if key in seen:
                    continue
                seen.add(key)
            yield out

    def clean_csv_file(self, src: str, dst: str, encoding: str = "utf-8") -> int:
        """Clean a CSV file streaming row-by-row. Returns data-row count."""
        import csv

        rows_written = 0
        with open(src, newline="", encoding=encoding) as fin:
            reader = csv.DictReader(fin)
            if not reader.fieldnames:
                raise ValueError(f"{src}: empty CSV or missing header")
            with open(dst, "w", newline="", encoding=encoding) as fout:
                writer = csv.DictWriter(fout, fieldnames=reader.fieldnames)
                writer.writeheader()
                for row in self.clean_stream(reader):
                    writer.writerow({k: ("" if v is None else v) for k, v in row.items()})
                    rows_written += 1
        return rows_written

    @staticmethod
    def deduplicate(records: Iterable[Dict], keys: Sequence[str]) -> Iterator[Dict]:
        """Yield records with duplicates (on `keys`) removed, order kept."""
        seen = set()
        for rec in records:
            key = tuple(rec.get(k) for k in keys)
            if key not in seen:
                seen.add(key)
                yield rec

    @staticmethod
    def drop_columns(records: Iterable[Dict], columns: Sequence[str]) -> Iterator[Dict]:
        cols = set(columns)
        for rec in records:
            yield {k: v for k, v in rec.items() if k not in cols}

    @staticmethod
    def coerce_types(record: Dict, schema: Dict[str, type]) -> Dict:
        """Best-effort cast of fields (e.g. {"id": int, "price": float})."""
        out = dict(record)
        for field, typ in schema.items():
            val = out.get(field)
            if val is None or isinstance(val, typ):
                continue
            try:
                if typ is int:
                    out[field] = int(float(str(val).strip()))
                elif typ is float:
                    out[field] = float(str(val).strip())
                elif typ is str:
                    out[field] = str(val).strip()
            except (ValueError, TypeError):
                out[field] = None
        return out
