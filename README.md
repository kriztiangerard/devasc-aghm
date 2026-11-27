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

## BL-07 — Arbitrary Target IP Lookup

BL-07 extends the Public IP & Network Diagnostic Utility to retrieve
network metadata for a user-specified IPv4 address, IPv6 address,
or DNS hostname instead of only the user's own public IP address.

### Usage

Look up an IPv4 address:

```bash
python ip_diagnostic.py --target 8.8.8.8
```

Look up an IPv6 address:

```bash
python ip_diagnostic.py --target 2001:4860:4860::8888
```

Look up a hostname:

```bash
python ip_diagnostic.py --target google.com
```

Export target results as JSON:

```bash
python ip_diagnostic.py --target example.com --json
```

Export target results as CSV:

```bash
python ip_diagnostic.py --target 1.1.1.1 --csv
```

Save target results to files:

```bash
python ip_diagnostic.py --target example.com --json > target.json
python ip_diagnostic.py --target 8.8.8.8 --csv > target.csv
```

Running the application without `--target` retains the original
self-diagnostic behavior:

```bash
python ip_diagnostic.py
```

Display available CLI arguments:

```bash
python ip_diagnostic.py --help
```

### Supported Target Inputs

- Literal IPv4 addresses.
- Literal IPv6 addresses.
- DNS hostnames, including IPv6-only hostnames.
- Internationalized hostnames through IDNA conversion.
- Valid hostnames with a trailing DNS root dot.
- Inputs with surrounding whitespace.

IPv4 is preferred when a hostname resolves to both IPv4 and IPv6
addresses. IPv6 is selected when no IPv4 address is available.

Malformed IP addresses, empty inputs, URLs, invalid hostname
characters, ports, and scoped IPv6 addresses are rejected.

### Target Report Fields

| Field | Description |
| --- | --- |
| target | Requested IP address or hostname |
| ip | Resolved or normalized IP address |
| city | Provider-reported city |
| region | Provider-reported region |
| country | Provider-reported country |
| country_code | Country code |
| isp | ISP or network organization |
| asn | Autonomous System Number |
| errors | Validation, resolution, or provider errors |

The human-readable report also displays the resolved IP version.

JSON and CSV exports preserve the backend result fields. The errors
list is JSON-encoded inside the corresponding CSV cell.

Progress messages and warnings are sent to stderr when JSON or CSV
output is requested, keeping stdout machine-readable.

### Error Handling and Exit Codes

| Exit code | Meaning |
| --- | --- |
| 0 | Diagnostic completed or target IP successfully resolved |
| 1 | Target validation, DNS resolution, or unexpected execution failure |
| 2 | Invalid command-line arguments |

A resolved IP remains available even if metadata providers fail.
Unavailable metadata fields use the `Unknown` fallback value.

Invalid or unresolvable targets return exit code 1 and meaningful
error information. JSON and CSV output remains available for these
expected lookup failures.

### Backend Architecture

BL-07 reuses the shared networking backend in `ip_core.py`.

| Function | Responsibility |
| --- | --- |
| `_validate_target(target)` | Validate and normalize IP addresses and hostnames |
| `_resolve_target_hostname(hostname)` | Resolve IPv4 and IPv6 DNS records |
| `lookup_ip(target)` | Coordinate target validation, resolution, and metadata retrieval |
| `_lookup_metadata(ip, errors)` | Reuse existing metadata provider failover |
| `_apply_meta(results, meta)` | Populate metadata and fallback values |

The metadata retrieval mechanism uses ipapi.co as the primary
provider and ipwho.is as the fallback provider.

BL-07 does not introduce another HTTP client or duplicate the
existing provider implementation.

### CLI Architecture

The CLI implementation is located in `ip_diagnostic.py`.

| Function | Responsibility |
| --- | --- |
| `parse_args(argv)` | Parse target and export arguments |
| `format_target_report(info)` | Format human-readable target results |
| `format_json(info)` | Reuse BL-03 JSON serialization |
| `format_csv(info)` | Reuse BL-03 CSV serialization |
| `main(argv)` | Select diagnostic mode, output format, and exit status |

The original self-diagnostic formatter and backend entry point
remain available.

### Integration Reference for BL-09

The GUI can reuse the public backend function directly:

```python
from ip_core import lookup_ip

result = lookup_ip("example.com")
```

The returned dictionary contains the requested target, resolved
IP address, metadata fields, and an errors list.

GUI implementations should perform network requests in a background
worker to avoid blocking the Tkinter event loop. Widget updates
should remain on the main GUI thread.

The GUI should distinguish between an unresolved target and a
resolved target with unavailable metadata.

### Automated Testing

Dedicated BL-07 tests:

```bash
python -m pytest test_target_lookup.py -v
```

Complete regression suite:

```bash
python -m pytest -v
```

BL-07 tests mock DNS and HTTP operations for deterministic,
offline verification.

### Implementation Verification

Verification date: November 26, 2026.

Environment: macOS, Python 3.9.6, pytest 8.4.2.

| Test suite | Passed | Failed |
| --- | ---: | ---: |
| BL-07 target lookup | 59 | 0 |
| BL-03 CLI export | 19 | 0 |
| Core networking | 17 | 0 |
| Original CLI | 5 | 0 |
| Total integrated tests | 100 | 0 |

Live verification:

| Scenario | Result |
| --- | --- |
| Literal IPv4 lookup | PASS |
| Literal IPv6 lookup | PASS |
| Hostname lookup | PASS |
| Target JSON export | PASS |
| Target CSV export | PASS |
| Invalid IPv4 rejection | PASS |
| Unresolvable hostname | PASS |
| Empty target rejection | PASS |
| Original self-diagnostic | PASS |

All nine live scenarios passed manual inspection.

Live HTTP 429 responses from the primary metadata provider were
observed during hostname and CSV lookups. Metadata retrieval
continued successfully through the existing failover mechanism.

Python syntax validation and Git diff checks also passed.

### Verification Notes and Limitations

- Metadata availability depends on external providers and their
  rate limits.
- IP geolocation is approximate and does not identify a precise
  physical location.
- Hostnames may resolve to different addresses over time.
- One resolved address is selected per hostname lookup.
- Looking up an IPv6 target does not independently verify local
  IPv6 connectivity.
- The test environment emitted an existing urllib3 LibreSSL
  compatibility warning. Automated tests and live requests
  completed successfully despite this warning.
- GUI target search and interactive lookup are addressed
  separately under BL-09.

## BL-09 — Interactive Target Lookup and GUI Search

### Interactive CLI

Start an interactive target lookup session:

```bash
python ip_diagnostic.py --interactive
```

Supported inputs:

- IPv4 address: `8.8.8.8`
- IPv6 address: `2001:4860:4860::8888`
- Hostname: `google.com`

Users can perform multiple lookups without restarting the
application. Enter `exit` or `quit` to end the session.
EOF and Ctrl+C also terminate the session gracefully.

Interactive mode cannot be combined with `--target`,
`--json`, or `--csv`.

Invalid inputs and failed lookups display error messages
without terminating the interactive session.

### Desktop GUI

Launch the application:

```bash
python ip_diagnostic_gui.py
```

The application initially displays the user's public
network details.

To perform a target lookup:

1. Enter an IPv4 address, IPv6 address, or hostname.
2. Click Search or press Enter.
3. Review the target lookup results.
4. Click Copy Report to copy the displayed diagnostic report.
5. Click My Public IP to return to self-diagnostic mode.

Target lookup results include:

- Original target
- Resolved IP address
- IP version
- ISP or organization
- Autonomous System Number (ASN)
- Geographic location
- Country code

Network requests run in a background thread to avoid
blocking the GUI. Request controls are disabled while
a lookup is in progress to prevent conflicting requests.

The status message distinguishes successful lookups,
nonfatal warnings, and failed lookups.

### Integration

BL-09 reuses the shared BL-07 `lookup_ip()` function
from `ip_core.py`. It does not introduce a separate
target lookup backend.

Existing self-diagnostic functionality and BL-03
machine-readable exports remain supported.

No new third-party application dependencies are required.
The desktop GUI requires a Python installation with
working Tcl/Tk bindings.

### Automated Testing

Run the dedicated BL-09 tests:

```bash
python -m pytest test_interactive_lookup.py -v
```

Run the complete regression suite:

```bash
python -m pytest -v
```

### Developer Verification

Verification date: November 26, 2026.

| Verification | Result |
|---|---|
| Dedicated BL-09 automated tests | 42/42 passed |
| Full regression suite | 142/142 passed |
| Live interactive CLI | Passed |
| GUI startup and layout | Passed |
| GUI IPv4 target lookup | Passed |
| GUI IPv6 target lookup | Passed |
| GUI hostname lookup | Passed |
| Copy self-diagnostic report | Passed |

Automated tests were executed using the original Python
3.9.6 virtual environment. Live GUI smoke tests were
performed using Homebrew Python 3.12.16 with Tk 9.1.0.

### Verification Notes

- IP metadata and geographic location depend on external
  providers and may vary between requests.
- Provider failures may produce warnings even when a
  fallback provider successfully retrieves metadata.
- A local macOS Python/Tkinter compatibility issue
  required a temporary runtime workaround during
  developer GUI testing. This is not an application
  dependency or a recommended production configuration.
- Comprehensive manual GUI testing and independent
  acceptance criteria verification remain assigned to QA.

### BL-09 — GUI Status Visibility QA Fix

**Developer retest date:** November 27, 2026

The GUI layout was refined to address the QA finding where
status messages disappeared when the window height was reduced.

Changes:
- Reserved a dedicated status area at the bottom of the window.
- Removed the results scrollbar and compacted result row spacing.
- Preserved the original minimum window size of 580 × 580.
- Added a conditional status scrollbar for overflowing warnings
  and errors.
- Added a deferred scrollbar refresh to ensure automatic visibility.
- Preserved the original color scheme and centered status text.

Verification:
- BL-09 dedicated tests: 57 passed.
- Full regression suite: 157 passed.
- Native layout checks: 6 passed across self and target modes.
- Native status checks: 6 passed for warnings, errors, and recovery.
- Representative long result values fit without clipping.
- Live GUI retesting completed by the developer.

Independent QA approval and backend integration remain pending.

### BL-09 — Backend Integration Retest

**Developer retest date:** November 27, 2026

Integrated the latest main branch containing the backend fix
for malformed API responses and provider failover (58c4f33).

Integration results:
- No merge conflicts.
- Core networking: 60/60 tests passed.
- Original CLI: 5/5 tests passed.
- BL-03: 19/19 tests passed.
- BL-07: 59/59 tests passed.
- BL-09: 57/57 tests passed.
- Full regression suite: 200/200 tests passed.
- Live GUI integration retest completed successfully.
- Previously verified GUI layout and status visibility preserved.
- Existing LibreSSL warning remains non-blocking.

Status: Ready for independent QA retesting and approval.
