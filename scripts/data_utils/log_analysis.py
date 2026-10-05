"""Log analysis in pure Python (OOP + generators).

Parses the same diary format written by scripts/generate_logs.py:
    2026-09-20 09:00:00 [INFO] 192.168.1.5 - GET /api/users 200 123ms
"""
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional

LOG_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<time>\d{2}:\d{2}:\d{2})\s+"
    r"\[(?P<level>[A-Z]+)\]\s+(?P<ip>\d+\.\d+\.\d+\.\d+)\s+-\s+"
    r"(?P<method>[A-Z]+)\s+(?P<endpoint>\S+)\s+(?P<status>\d{3})\b(?P<rest>.*)$"
)


@dataclass
class LogRecord:
    timestamp: str
    level: str
    ip: str
    method: str
    endpoint: str
    status: int
    message: str


class LogAnalyzer:
    """Streaming log parser + summarizer."""

    @staticmethod
    def parse_line(line: str) -> Optional[LogRecord]:
        m = LOG_RE.match(line.strip())
        if not m:
            return None
        d = m.groupdict()
        return LogRecord(
            timestamp=f"{d['date']} {d['time']}",
            level=d["level"],
            ip=d["ip"],
            method=d["method"],
            endpoint=d["endpoint"],
            status=int(d["status"]),
            message=d["rest"].strip(),
        )

    # -- generators ----------------------------------------------------
    def stream(self, path: str) -> Iterator[LogRecord]:
        """Yield parsed records one-by-one (skips malformed lines)."""
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                rec = self.parse_line(line)
                if rec is not None:
                    yield rec

    def iter_errors(self, path: str) -> Iterator[LogRecord]:
        for rec in self.stream(path):
            if rec.level == "ERROR":
                yield rec

    def iter_by_level(self, path: str, level: str) -> Iterator[LogRecord]:
        for rec in self.stream(path):
            if rec.level == level:
                yield rec

    # -- summary --------------------------------------------------------
    def analyze(self, path: str) -> Dict:
        total = 0
        malformed = 0
        levels: Counter = Counter()
        ips: Counter = Counter()
        endpoints: Counter = Counter()
        statuses: Counter = Counter()
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = self.parse_line(line)
                if rec is None:
                    malformed += 1
                    continue
                total += 1
                levels[rec.level] += 1
                ips[rec.ip] += 1
                endpoints[rec.endpoint] += 1
                statuses[str(rec.status)] += 1
        return {
            "file": str(path),
            "total": total,
            "malformed": malformed,
            "by_level": dict(levels),
            "top_ips": ips.most_common(5),
            "top_endpoints": endpoints.most_common(5),
            "status_counts": dict(sorted(statuses.items())),
        }

    def write_errors(self, src: str, dst: str) -> int:
        """Copy ERROR lines to a report file. Returns lines written."""
        n = 0
        with open(src, encoding="utf-8", errors="replace") as fin, \
                open(dst, "w", encoding="utf-8") as fout:
            for line in fin:
                if "[ERROR]" in line:
                    fout.write(line if line.endswith("\n") else line + "\n")
                    n += 1
        return n

    @staticmethod
    def format_summary(summary: Dict) -> str:
        lines: List[str] = [
            f"File: {summary['file']}",
            f"Total parsed: {summary['total']} (malformed: {summary['malformed']})",
            f"By level: {summary['by_level']}",
            f"Status counts: {summary['status_counts']}",
            "Top IPs:",
        ]
        lines += [f"  {ip}: {c}" for ip, c in summary["top_ips"]]
        lines += ["Top endpoints:"]
        lines += [f"  {ep}: {c}" for ep, c in summary["top_endpoints"]]
        return "\n".join(lines)
