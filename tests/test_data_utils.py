"""Tests for scripts/data_utils (cleansing, validation, JSON/XML, logs, auto-processing)."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.data_utils import (
    DataCleaner,
    FileProcessor,
    FileValidator,
    JsonXmlConverter,
    LogAnalyzer,
)


class CleaningTest(unittest.TestCase):
    def test_strip_null_email_dedupe(self):
        c = DataCleaner(dedupe_keys=["id"])
        rows = [
            {"id": "1", "name": "  Ada ", "email": "ADA@EXAMPLE.COM", "city": "London"},
            {"id": "2", "name": "Alan", "email": "bad-email", "city": "N/A"},
            {"id": "1", "name": "Ada", "email": "ada@example.com", "city": "London"},
            {"id": "", "name": "", "email": "", "city": ""},
        ]
        out = list(c.clean_stream(rows))
        self.assertEqual(len(out), 2)  # dupe + empty dropped
        self.assertEqual(out[0]["email"], "ada@example.com")
        self.assertEqual(out[0]["name"], "Ada")
        self.assertIsNone(out[1]["city"])  # N/A -> None
        self.assertIsNone(out[1]["email"])  # invalid -> None

    def test_clean_csv_file_streaming(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.csv"
            dst = Path(tmp) / "out.csv"
            src.write_text("id,name,email\n1, Ada ,ADA@X.COM\n2,,N/A\n", encoding="utf-8")
            n = DataCleaner().clean_csv_file(str(src), str(dst))
            self.assertEqual(n, 2)
            self.assertIn("ada@x.com", dst.read_text(encoding="utf-8"))

    def test_coerce_types(self):
        out = DataCleaner.coerce_types({"id": " 7 ", "price": "12.5", "x": "abc"}, {"id": int, "price": float})
        self.assertEqual(out, {"id": 7, "price": 12.5, "x": "abc"})


class ValidationTest(unittest.TestCase):
    def test_csv_header_and_row_errors(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "a.csv"
            p.write_text("id,name\n1,Ada\n,Missing\n", encoding="utf-8")
            v = FileValidator(required_columns=["id", "name"])
            errs = list(v.iter_csv_errors(str(p)))
            self.assertTrue(any("empty required field 'id'" in e for e in errs))
            bad = Path(tmp) / "b.csv"
            bad.write_text("id\n1\n", encoding="utf-8")
            self.assertFalse(v.validate(str(bad)).ok)

    def test_json_and_missing_file(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "a.json"
            p.write_text(json.dumps([{"id": 1}, {"x": 2}]), encoding="utf-8")
            v = FileValidator()
            res = v.validate(str(p), required_fields=["id"])
            self.assertFalse(res.ok)
            self.assertEqual(res.rows_checked, 2)
            self.assertFalse(v.validate(str(Path(tmp) / "nope.csv")).ok)


class FormatsTest(unittest.TestCase):
    def test_json_xml_roundtrip(self):
        c = JsonXmlConverter()
        data = [{"id": 1, "name": "Ada"}, {"id": 2, "name": "Alan"}]
        xml = c.json_to_xml_doc(data, root="users")
        back = c.xml_to_json(xml)
        # XML is stringly-typed: numbers come back as strings
        self.assertEqual(back, [{"id": "1", "name": "Ada"}, {"id": "2", "name": "Alan"}])

    def test_dict_xml(self):
        c = JsonXmlConverter()
        d = {"name": "Ada", "tags": ["a", "b"]}
        xml = c.dict_to_xml(d, root="user")
        out = c.xml_to_dict(xml)
        self.assertEqual(out["user"]["name"], "Ada")

    def test_stream_csv_as_json(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "a.csv"
            p.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
            rows = list(JsonXmlConverter.stream_csv_as_json(str(p)))
            self.assertEqual(rows, [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}])


class LogAnalysisTest(unittest.TestCase):
    SAMPLE = (
        "2026-09-20 09:00:00 [INFO] 192.168.1.2 - GET /api/users 200 10ms\n"
        "2026-09-20 09:01:00 [ERROR] 192.168.1.3 - GET /api/orders 500 FAILED user_id=1001\n"
        "2026-09-20 09:02:00 [WARN] 192.168.1.2 - GET /health 429 slow-response 900ms\n"
        "not a log line\n"
    )

    def test_parse_and_analyze(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "app.log"
            p.write_text(self.SAMPLE, encoding="utf-8")
            az = LogAnalyzer()
            rec = az.parse_line(self.SAMPLE.splitlines()[0])
            self.assertIsNotNone(rec)
            self.assertEqual(rec.status, 200)
            self.assertIsNone(az.parse_line("not a log line"))
            s = az.analyze(str(p))
            self.assertEqual(s["total"], 3)
            self.assertEqual(s["malformed"], 1)
            self.assertEqual(s["by_level"]["ERROR"], 1)
            self.assertEqual(len(list(az.iter_errors(str(p)))), 1)
            self.assertEqual(az.write_errors(str(p), str(Path(tmp) / "e.txt")), 1)


class ProcessorTest(unittest.TestCase):
    def test_auto_routes_by_extension(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            inp, proc, quar = Path(tmp) / "in", Path(tmp) / "done", Path(tmp) / "q"
            inp.mkdir()
            (inp / "a.csv").write_text("id,name\n1, Ada \n", encoding="utf-8")
            (inp / "b.json").write_text(json.dumps([{"id": 1, "name": " x "}]), encoding="utf-8")
            (inp / "c.xml").write_text("<root><name>Ada</name></root>", encoding="utf-8")
            (inp / "d.log").write_text(
                "2026-09-20 09:00:00 [INFO] 192.168.1.2 - GET /api/users 200 10ms\n", encoding="utf-8")
            (inp / "e.xyz").write_text("??", encoding="utf-8")
            (inp / "bad.json").write_text("{oops", encoding="utf-8")
            fp = FileProcessor(str(inp), str(proc), str(quar))
            results = {Path(r.source).name: r for r in fp.process_all()}
            self.assertEqual(results["a.csv"].status, "processed")
            self.assertTrue((proc / "a.clean.csv").exists())
            self.assertEqual(results["b.json"].status, "processed")
            self.assertEqual(results["c.xml"].status, "processed")
            self.assertTrue((proc / "c.json").exists())
            self.assertEqual(results["d.log"].status, "processed")
            self.assertEqual(results["e.xyz"].status, "quarantined")
            self.assertEqual(results["bad.json"].status, "quarantined")


if __name__ == "__main__":
    unittest.main()
