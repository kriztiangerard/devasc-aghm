# devasc-aghm

Development repository.

## BL-03 — CLI Flags and Machine-Readable Export

Implemented for Project Activity 4.

The command-line interface supports human-readable text, JSON,
and CSV output. Machine-readable formats allow diagnostic results
to be saved, processed by scripts, and integrated into automation
workflows.

### Setup

Create and activate a Python virtual environment, then install
the project dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

No additional dependencies are required for CLI export.
The implementation uses Python's standard library modules:
`argparse`, `json`, `csv`, `io`, and `sys`.

### CLI Usage

Display the default human-readable diagnostic report:

```bash
python ip_diagnostic.py
```

Display diagnostic results as JSON:

```bash
python ip_diagnostic.py --json
```

Display diagnostic results as CSV:

```bash
python ip_diagnostic.py --csv
```

Save diagnostic results to files:

```bash
python ip_diagnostic.py --json > diagnostic.json
python ip_diagnostic.py --csv > diagnostic.csv
```

Display available command-line arguments:

```bash
python ip_diagnostic.py --help
```

The `--json` and `--csv` flags are mutually exclusive.
They cannot be used together.

### Output Formats

| Format | Description |
| --- | --- |
| Text | Original human-readable terminal report. |
| JSON | Complete backend result serialized as a JSON object. |
| CSV | Header row and one diagnostic data row. |

JSON preserves the original backend field names and values,
including nested dictionaries and lists.

CSV uses backend field names as column headers. Nested dictionaries
and lists are JSON-encoded within individual cells. Null values
are represented as empty CSV cells.

In export mode, diagnostic data is written to standard output
(stdout). Progress messages, offline notices, and unexpected
errors are written to standard error (stderr), keeping exported
files machine-readable.

### Exit Codes

| Exit Code | Meaning |
| --- | --- |
| 0 | Diagnostic completed, including unavailable network information. |
| 1 | Unexpected diagnostic or serialization error. |
| 2 | Invalid command-line arguments. |

An exit code of 0 does not guarantee that all network information
was retrieved. Automation scripts should also inspect the returned
data and its `errors` field.

### Implementation and Maintenance

All CLI export functionality is implemented in `ip_diagnostic.py`.

| Function | Responsibility |
| --- | --- |
| `parse_args()` | Parses and validates command-line arguments. |
| `format_report()` | Generates the human-readable report. |
| `format_json()` | Serializes backend results as JSON. |
| `format_csv()` | Serializes backend results as CSV. |
| `main()` | Coordinates retrieval, formatting, and error handling. |

The CLI continues to use `get_public_ip_info()` from `ip_core.py`.
Network retrieval is not duplicated within the CLI.

Additional backend fields are automatically included in JSON and
CSV exports. Future CLI arguments can be added to `parse_args()`,
while additional output formats can be implemented as separate
formatting functions.

### Automated Testing

Run the BL-03 test suite:

```bash
python -m pytest test_cli_export.py -v
```

Run all project tests:

```bash
python -m pytest -v
```

BL-03 tests cover default output, JSON and CSV serialization,
special characters, nested data, invalid arguments, missing
metadata, offline conditions, unexpected errors, CLI help,
script entry-point execution, and file redirection.

### Verification Results

- BL-03 automated tests: 19 passed.
- Existing Activity 3 regression tests: 12 passed.
- Full automated suite: 31 passed, 0 failed.
- Live text, JSON, and CSV output verified.
- Live IPv4 and IPv6 detection verified in both export formats.
- Conflicting export flags correctly returned exit code 2.

### Known Limitations

Network information depends on external API availability.
Separate diagnostic executions may return different metadata.

During live verification, ISP metadata was unavailable in one
JSON execution but available in the CSV execution. Both exports
remained valid and parseable.

The tested macOS Python 3.9.6 environment also produced an existing
urllib3 LibreSSL compatibility warning. This warning did not cause
any automated test failures.

BL-07 target lookup and BL-09 GUI target search are separate
Activity 4 backlog items.
