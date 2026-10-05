"""CLI: run the data-processing utilities end to end.

Examples:
  python scripts/process_data.py --demo            # build sample files + run all 5 utilities
  python scripts/process_data.py --clean-csv data/samples/dirty_users.csv --out data/landing/processed/users.clean.csv
  python scripts/process_data.py --validate data/samples/dirty_users.csv
  python scripts/process_data.py --json-to-xml data/samples/users.json --out out.xml
  python scripts/process_data.py --xml-to-json data/samples/users.xml --out out.json
  python scripts/process_data.py --analyze-logs logs/app.log
  python scripts/process_data.py --auto --input data/landing/raw --processed data/landing/processed
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.data_utils import (  # noqa: E402
    DataCleaner,
    FileProcessor,
    FileValidator,
    JsonXmlConverter,
    LogAnalyzer,
)


def cmd_demo(_args) -> int:
    base = Path("data/samples")
    base.mkdir(parents=True, exist_ok=True)

    # 1. dirty CSV -> clean it
    dirty_csv = base / "dirty_users.csv"
    dirty_csv.write_text(
        "id,name,email,city\n"
        "1,  Ada Lovelace ,ADA@EXAMPLE.COM,London\n"
        "2,Alan Turing,alan@example.com,  Manchester \n"
        "3,,N/A,Leeds\n"
        "2,Alan Turing,alan@example.com,Manchester\n"
        ",,,\n",
        encoding="utf-8",
    )
    cleaner = DataCleaner(dedupe_keys=["id"])
    clean_csv = base / "users.clean.csv"
    n = cleaner.clean_csv_file(str(dirty_csv), str(clean_csv))
    print(f"[clean] {dirty_csv} -> {clean_csv} ({n} rows)")

    # 2. validate
    validator = FileValidator(required_columns=["id", "name", "email", "city"])
    res = validator.validate(str(dirty_csv), schema={"id": int})
    print(f"[validate] ok={res.ok} rows={res.rows_checked}")
    for e in res.errors[:5]:
        print(f"  - {e}")

    # 3. JSON <-> XML round-trip
    conv = JsonXmlConverter()
    users = json.loads((dirty_csv.parent / "users.clean.csv").read_text(encoding="utf-8") and "[]") \
        if False else [{"id": 1, "name": "Ada Lovelace", "email": "ada@example.com", "city": "London"}]
    sample_json = base / "users.json"
    sample_json.write_text(json.dumps(users, indent=2), encoding="utf-8")
    sample_xml = base / "users.xml"
    conv.json_file_to_xml_file(str(sample_json), str(sample_xml), root="users")
    back_json = base / "users_roundtrip.json"
    conv.xml_file_to_json_file(str(sample_xml), str(back_json))
    print(f"[formats] JSON -> XML -> JSON: {sample_json} -> {sample_xml} -> {back_json}")

    # 4. log analysis (makes logs/app.log if missing)
    log_path = Path("logs/app.log")
    if not log_path.exists() or log_path.stat().st_size == 0:
        import subprocess

        gen = Path("scripts/generate_logs.py")
        if gen.exists():
            subprocess.run([sys.executable, str(gen)], check=False)
        if not log_path.exists() or log_path.stat().st_size == 0:
            # Standalone copy has no generate_logs.py: write a tiny
            # sample log in the same diary format so the demo is self-contained.
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                "2026-09-20 09:00:00 [INFO] 192.168.1.10 - GET /api/orders 200 83ms\n"
                "2026-09-20 09:00:33 [ERROR] 192.168.1.19 - GET /api/users 429 FAILED user_id=1054\n"
                "2026-09-20 09:00:48 [WARN] 192.168.1.4 - GET /health 301 slow-response 812ms\n",
                encoding="utf-8",
            )
            print(f"[logs] no generator found, wrote sample {log_path}")
    analyzer = LogAnalyzer()
    summary = analyzer.analyze(str(log_path))
    print("[logs]\n" + LogAnalyzer.format_summary(summary))
    n_err = analyzer.write_errors(str(log_path), "logs/analysis_errors.txt")
    print(f"[logs] wrote {n_err} error lines -> logs/analysis_errors.txt")

    # 5. automated processing of a folder
    demo_in = Path("data/landing/raw")
    proc = FileProcessor(input_dir=str(demo_in))
    print(f"[auto] processing {demo_in} ...")
    count = 0
    for r in proc.process_all():
        print(f"  {r.status}: {Path(r.source).name} -> {Path(r.dest).name} rows={r.rows} {r.note}")
        count += 1
        if count >= 10:
            break
    if count == 0:
        print("  (input folder empty - run scripts/fetch_api.py first to add files)")
    print("demo done.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Data processing utilities (OOP + generators)")
    ap.add_argument("--demo", action="store_true", help="run full end-to-end demo")
    ap.add_argument("--clean-csv", help="input dirty CSV path")
    ap.add_argument("--validate", help="file path to validate")
    ap.add_argument("--json-to-xml", help="input .json path")
    ap.add_argument("--xml-to-json", help="input .xml path")
    ap.add_argument("--analyze-logs", help="input .log path")
    ap.add_argument("--auto", action="store_true", help="auto-process a folder")
    ap.add_argument("--input", default="data/landing/raw")
    ap.add_argument("--processed", default="data/landing/processed")
    ap.add_argument("--quarantine", default="data/landing/quarantine")
    ap.add_argument("--out", help="output path for single-file commands")
    args = ap.parse_args(argv)

    if args.demo or len(sys.argv) == 1:
        return cmd_demo(args)

    if args.clean_csv:
        out = args.out or str(Path(args.clean_csv).with_suffix(".clean.csv"))
        n = DataCleaner().clean_csv_file(args.clean_csv, out)
        print(f"Cleaned {n} rows -> {out}")
        return 0

    if args.validate:
        res = FileValidator().validate(args.validate)
        print(f"ok={res.ok} rows={res.rows_checked}")
        for e in res.errors:
            print(f"  - {e}")
        return 0 if res.ok else 1

    if args.json_to_xml:
        out = args.out or str(Path(args.json_to_xml).with_suffix(".xml"))
        JsonXmlConverter().json_file_to_xml_file(args.json_to_xml, out)
        print(f"Wrote {out}")
        return 0

    if args.xml_to_json:
        out = args.out or str(Path(args.xml_to_json).with_suffix(".json"))
        JsonXmlConverter().xml_file_to_json_file(args.xml_to_json, out)
        print(f"Wrote {out}")
        return 0

    if args.analyze_logs:
        summary = LogAnalyzer().analyze(args.analyze_logs)
        print(LogAnalyzer.format_summary(summary))
        return 0

    if args.auto:
        proc = FileProcessor(input_dir=args.input, processed_dir=args.processed,
                             quarantine_dir=args.quarantine)
        for r in proc.process_all():
            print(f"{r.status}: {r.source} -> {r.dest} rows={r.rows} {r.note}")
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
