"""Automated file processing (OOP + generators).

Watches an input folder, cleans/validates/converts each file by
extension, and routes it to processed/ or quarantine/.

Routing:
  .csv -> clean -> processed/*.clean.csv
  .json -> validate (+ optional clean for list-of-objects) -> processed/
  .xml -> convert to JSON -> processed/*.json
  .log -> analyze -> processed/*_summary.txt (+ errors file)
  other -> quarantine/
"""
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from .cleaning import DataCleaner
from .formats import JsonXmlConverter
from .log_analysis import LogAnalyzer
from .validation import FileValidator


@dataclass
class ProcessResult:
    source: str
    dest: str
    status: str  # "processed" | "quarantined" | "skipped"
    rows: int = 0
    errors: int = 0
    note: str = ""


class FileProcessor:
    def __init__(
        self,
        input_dir: str = "data/landing/raw",
        processed_dir: str = "data/landing/processed",
        quarantine_dir: str = "data/landing/quarantine",
        cleaner: Optional[DataCleaner] = None,
        validator: Optional[FileValidator] = None,
        converter: Optional[JsonXmlConverter] = None,
        analyzer: Optional[LogAnalyzer] = None,
    ):
        self.input_dir = Path(input_dir)
        self.processed_dir = Path(processed_dir)
        self.quarantine_dir = Path(quarantine_dir)
        self.cleaner = cleaner or DataCleaner()
        self.validator = validator or FileValidator()
        self.converter = converter or JsonXmlConverter()
        self.analyzer = analyzer or LogAnalyzer()
        for d in (self.input_dir, self.processed_dir, self.quarantine_dir):
            d.mkdir(parents=True, exist_ok=True)

    # -- generators ----------------------------------------------------
    def scan(self) -> Iterator[Path]:
        """Yield files waiting in the input dir (sorted, constant memory)."""
        if not self.input_dir.exists():
            return
        for p in sorted(self.input_dir.iterdir()):
            if p.is_file() and not p.name.startswith("."):
                yield p

    def process_all(self) -> Iterator[ProcessResult]:
        for path in self.scan():
            yield self.process_file(str(path))

    # -- per-file dispatch ----------------------------------------------
    def process_file(self, path: str) -> ProcessResult:
        p = Path(path)
        ext = p.suffix.lower()
        if ext == ".csv":
            return self._process_csv(p)
        if ext == ".json":
            return self._process_json(p)
        if ext == ".xml":
            return self._process_xml(p)
        if ext == ".log":
            return self._process_log(p)
        dest = self.quarantine_dir / p.name
        shutil.copy2(p, dest)
        return ProcessResult(str(p), str(dest), "quarantined", note=f"unsupported extension {ext!r}")

    def _process_csv(self, p: Path) -> ProcessResult:
        dest = self.processed_dir / f"{p.stem}.clean.csv"
        try:
            rows = self.cleaner.clean_csv_file(str(p), str(dest))
        except Exception as exc:  # noqa: BLE001 - route bad files to quarantine
            q = self.quarantine_dir / p.name
            shutil.copy2(p, q)
            return ProcessResult(str(p), str(q), "quarantined", errors=1, note=str(exc))
        return ProcessResult(str(p), str(dest), "processed", rows=rows)

    def _process_json(self, p: Path) -> ProcessResult:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            q = self.quarantine_dir / p.name
            shutil.copy2(p, q)
            return ProcessResult(str(p), str(q), "quarantined", errors=1, note=f"invalid JSON: {exc}")
        rows = data if isinstance(data, list) else [data]
        cleaned = list(self.cleaner.clean_stream(r for r in rows if isinstance(r, dict)))
        dest = self.processed_dir / p.name
        dest.write_text(json.dumps(cleaned if isinstance(data, list) else (cleaned[0] if cleaned else {}), indent=2),
                        encoding="utf-8")
        return ProcessResult(str(p), str(dest), "processed", rows=len(cleaned))

    def _process_xml(self, p: Path) -> ProcessResult:
        dest = self.processed_dir / f"{p.stem}.json"
        try:
            self.converter.xml_file_to_json_file(str(p), str(dest))
        except Exception as exc:  # noqa: BLE001
            q = self.quarantine_dir / p.name
            shutil.copy2(p, q)
            return ProcessResult(str(p), str(q), "quarantined", errors=1, note=f"invalid XML: {exc}")
        return ProcessResult(str(p), str(dest), "processed", rows=1)

    def _process_log(self, p: Path) -> ProcessResult:
        summary = self.analyzer.analyze(str(p))
        dest = self.processed_dir / f"{p.stem}_summary.txt"
        dest.write_text(LogAnalyzer.format_summary(summary), encoding="utf-8")
        self.analyzer.write_errors(str(p), str(self.processed_dir / f"{p.stem}_errors.txt"))
        return ProcessResult(str(p), str(dest), "processed",
                             rows=summary["total"], errors=summary["by_level"].get("ERROR", 0))
