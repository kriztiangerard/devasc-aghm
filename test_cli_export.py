"""Activity 4 automated tests for BL-03 CLI export functionality."""

import csv
import io
import json
import runpy
import sys
from unittest.mock import patch

import pytest

from ip_diagnostic import main, format_csv, format_json


SAMPLE_DATA = {
    "ipv4": "203.0.113.10",
    "ipv6": "2001:db8::1",
    "isp": "Example ISP",
    "asn": "AS64500",
    "city": "Manila",
    "region": "Metro Manila",
    "country": "Philippines",
    "country_code": "PH",
    "errors": [],
}


def read_csv(output):
    """Parse CSV output and require exactly one diagnostic row."""
    rows = list(csv.DictReader(io.StringIO(output)))
    assert len(rows) == 1
    return rows[0]


def test_default_text_output(capsys):
    """BL03-TC01: Default output preserves the text report."""
    with patch(
        "ip_diagnostic.get_public_ip_info",
        return_value=SAMPLE_DATA,
    ):
        assert main([]) == 0

    captured = capsys.readouterr()

    assert "PUBLIC IP & NETWORK DIAGNOSTIC UTILITY" in captured.out
    assert "203.0.113.10" in captured.out
    assert "Example ISP" in captured.out
    assert captured.err == ""


def test_json_export(capsys):
    """BL03-TC02: JSON stdout contains the complete backend result."""
    with patch(
        "ip_diagnostic.get_public_ip_info",
        return_value=SAMPLE_DATA,
    ):
        assert main(["--json"]) == 0

    captured = capsys.readouterr()

    assert json.loads(captured.out) == SAMPLE_DATA
    assert "Gathering network information" in captured.err


def test_csv_export(capsys):
    """BL03-TC03: CSV contains correct headers and one data row."""
    with patch(
        "ip_diagnostic.get_public_ip_info",
        return_value=SAMPLE_DATA,
    ):
        assert main(["--csv"]) == 0

    captured = capsys.readouterr()
    row = read_csv(captured.out)

    assert list(row.keys()) == list(SAMPLE_DATA.keys())

    for key, value in SAMPLE_DATA.items():
        if isinstance(value, list):
            assert json.loads(row[key]) == value
        else:
            assert row[key] == value

    assert "Gathering network information" in captured.err


def test_csv_special_characters():
    """BL03-TC04: CSV preserves commas, quotes, and line breaks."""
    data = {
        **SAMPLE_DATA,
        "isp": 'Example, "Network" Inc.',
        "city": "First line\nSecond line",
    }

    row = read_csv(format_csv(data))

    assert row["isp"] == data["isp"]
    assert row["city"] == data["city"]


@pytest.mark.parametrize("output_format", ["json", "csv"])
def test_nested_backend_fields(output_format):
    """BL03-TC05: Activity 4 backend fields remain exportable."""
    data = {
        **SAMPLE_DATA,
        "errors": ["IPv6 unavailable"],
        "sources": {"ipv4": "ipify"},
        "latency_ms": {"ipify": 120.5},
    }

    if output_format == "json":
        assert json.loads(format_json(data)) == data
    else:
        row = read_csv(format_csv(data))

        for key in ("errors", "sources", "latency_ms"):
            assert json.loads(row[key]) == data[key]


def test_conflicting_export_flags(capsys):
    """BL03-TC06: JSON and CSV flags cannot be combined."""
    with patch("ip_diagnostic.get_public_ip_info") as backend:
        with pytest.raises(SystemExit) as exc:
            main(["--json", "--csv"])

        backend.assert_not_called()

    captured = capsys.readouterr()

    assert exc.value.code == 2
    assert captured.out == ""
    assert "not allowed with argument" in captured.err


def test_unknown_argument(capsys):
    """BL03-TC07: Unsupported flags are rejected."""
    with patch("ip_diagnostic.get_public_ip_info") as backend:
        with pytest.raises(SystemExit) as exc:
            main(["--invalid"])

        backend.assert_not_called()

    captured = capsys.readouterr()

    assert exc.value.code == 2
    assert "unrecognized arguments" in captured.err


@pytest.mark.parametrize("flag", ["--json", "--csv"])
def test_missing_metadata(flag, capsys):
    """BL03-TC08: Missing metadata does not break exports."""
    data = {
        **SAMPLE_DATA,
        "isp": None,
        "asn": None,
        "city": None,
    }

    with patch(
        "ip_diagnostic.get_public_ip_info",
        return_value=data,
    ):
        assert main([flag]) == 0

    captured = capsys.readouterr()

    if flag == "--json":
        assert json.loads(captured.out) == data
    else:
        row = read_csv(captured.out)

        assert row["isp"] == ""
        assert row["asn"] == ""
        assert row["city"] == ""


@pytest.mark.parametrize("flag", ["--json", "--csv"])
def test_offline_export(flag, capsys):
    """BL03-TC09: Offline notices do not contaminate exports."""
    data = {
        **SAMPLE_DATA,
        "ipv4": "Unavailable",
        "ipv6": "Not Detected",
        "errors": ["Network unavailable"],
    }

    with patch(
        "ip_diagnostic.get_public_ip_info",
        return_value=data,
    ):
        assert main([flag]) == 0

    captured = capsys.readouterr()

    if flag == "--json":
        assert json.loads(captured.out) == data
    else:
        row = read_csv(captured.out)

        assert row["ipv4"] == "Unavailable"
        assert row["ipv6"] == "Not Detected"
        assert json.loads(row["errors"]) == data["errors"]

    assert "No public IP address could be detected" in captured.err


@pytest.mark.parametrize("flag", ["--json", "--csv"])
def test_backend_error_in_export_mode(flag, capsys):
    """BL03-TC10: Unexpected errors use stderr and exit code 1."""
    with patch(
        "ip_diagnostic.get_public_ip_info",
        side_effect=RuntimeError("Test backend failure"),
    ):
        assert main([flag]) == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert "Unable to complete network diagnostic" in captured.err
    assert "Test backend failure" in captured.err


def test_help_command(capsys):
    """BL03-TC11: Help documents export flags without network calls."""
    with patch("ip_diagnostic.get_public_ip_info") as backend:
        with pytest.raises(SystemExit) as exc:
            main(["--help"])

        backend.assert_not_called()

    captured = capsys.readouterr()

    assert exc.value.code == 0
    assert "--json" in captured.out
    assert "--csv" in captured.out
    assert captured.err == ""


@pytest.mark.parametrize("flag", ["--json", "--csv"])
def test_cli_entry_point(flag, capsys):
    """BL03-TC12: Script entry point forwards actual CLI arguments."""
    with patch("sys.argv", ["ip_diagnostic.py", flag]):
        with patch(
            "ip_core.get_public_ip_info",
            return_value=SAMPLE_DATA,
        ):
            with pytest.raises(SystemExit) as exc:
                runpy.run_module(
                    "ip_diagnostic",
                    run_name="__main__",
                )

    captured = capsys.readouterr()

    assert exc.value.code == 0

    if flag == "--json":
        assert json.loads(captured.out) == SAMPLE_DATA
    else:
        assert read_csv(captured.out)["ipv4"] == SAMPLE_DATA["ipv4"]


@pytest.mark.parametrize("flag", ["--json", "--csv"])
def test_export_file_redirection(flag, tmp_path):
    """BL03-TC13: Redirected stdout produces a parseable file."""
    extension = flag[2:]
    output_file = tmp_path / f"diagnostic.{extension}"

    with output_file.open("w", encoding="utf-8", newline="") as output:
        with patch.object(sys, "stdout", output):
            with patch(
                "ip_diagnostic.get_public_ip_info",
                return_value=SAMPLE_DATA,
            ):
                assert main([flag]) == 0

    content = output_file.read_text(encoding="utf-8")

    if flag == "--json":
        assert json.loads(content) == SAMPLE_DATA
    else:
        assert read_csv(content)["ipv4"] == SAMPLE_DATA["ipv4"]
