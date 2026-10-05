# Data Processing Utilities (OOP + generators)

Standalone copy of the data cleansing, file validation, JSON/XML,
log analysis, and automated file-processing utilities.

## Layout

```
scripts/data_utils/   # cleaning, validation, formats, log_analysis, processor
scripts/process_data.py
tests/test_data_utils.py
data/samples/         # demo fixtures
out.*                 # sample outputs from earlier runs
```

## Run (from this folder, no install needed — stdlib only)

```
python -m unittest discover -s tests -v
python scripts/process_data.py --demo
python scripts/process_data.py --clean-csv data/samples/dirty_users.csv --out out.clean.csv
python scripts/process_data.py --validate data/samples/dirty_users.csv
python scripts/process_data.py --json-to-xml data/samples/users.json --out out.xml
python scripts/process_data.py --xml-to-json data/samples/users.xml --out out.json
python scripts/process_data.py --auto --input data/samples --processed processed_output
```

Note: `--demo` needs a log file. Point `--analyze-logs` at any log, or
copy one in as `logs/app.log`. The `--auto` example above works with no log.
