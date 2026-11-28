"""BL-07 automated tests for arbitrary target lookup.

All DNS and HTTP operations are mocked for reproducible offline testing.
"""

import csv
import io
import json
import runpy
import socket
from unittest.mock import MagicMock, patch

import pytest
import requests

import ip_core
import ip_diagnostic


METADATA = {
    "city": "Example City",
    "region": "Example Region",
    "country_name": "United States",
    "country_code": "US",
    "org": "Example ISP",
    "asn": "AS15169",
}

TARGET_DATA = {
    "target": "8.8.8.8",
    "ip": "8.8.8.8",
    "city": "Example City",
    "region": "Example Region",
    "country": "United States",
    "country_code": "US",
    "isp": "Example ISP",
    "asn": "AS15169",
    "errors": [],
}

SELF_DATA = {
    "ipv4": "203.0.113.10",
    "ipv6": "2001:db8::1",
    "city": "Manila",
    "region": "Metro Manila",
    "country": "Philippines",
    "country_code": "PH",
    "isp": "Example ISP",
    "asn": "AS64500",
    "errors": [],
}


def response(data=None, status=200):
    result = MagicMock()
    result.status_code = status
    result.json.return_value = data
    return result


def dns_record(address):
    if ":" in address:
        return (
            socket.AF_INET6, socket.SOCK_STREAM,
            socket.IPPROTO_TCP, "", (address, 0, 0, 0),
        )
    return (
        socket.AF_INET, socket.SOCK_STREAM,
        socket.IPPROTO_TCP, "", (address, 0),
    )


def parse_csv(output):
    rows = list(csv.DictReader(io.StringIO(output)))
    assert len(rows) == 1
    return rows[0]


# TC01-TC02: Literal IPv4 and IPv6 lookup.

@pytest.mark.parametrize("address", [
    "8.8.8.8",
    "2001:4860:4860::8888",
])
def test_literal_ip(address):
    with patch("ip_core.socket.getaddrinfo") as dns, \
         patch("ip_core.requests.get",
               return_value=response(METADATA)) as http:

        result = ip_core.lookup_ip(address)
        dns.assert_not_called()
        assert f"/{address}/json/" in http.call_args.args[0]

    assert result == {
        **TARGET_DATA, "target": address, "ip": address,
    }


# TC03-TC05: IPv4, IPv6-only and dual-stack hostnames.

@pytest.mark.parametrize("addresses,expected", [
    (["8.8.8.8"], "8.8.8.8"),
    (["2001:4860:4860::8888"], "2001:4860:4860::8888"),
    (["2001:4860:4860::8888", "8.8.8.8"], "8.8.8.8"),
])
def test_hostname_resolution(addresses, expected):
    with patch(
        "ip_core.socket.getaddrinfo",
        return_value=[dns_record(ip) for ip in addresses],
    ) as dns, patch(
        "ip_core.requests.get",
        return_value=response(METADATA),
    ) as http:

        result = ip_core.lookup_ip("example.com")

        dns.assert_called_once_with(
            "example.com", None,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )

        assert f"/{expected}/json/" in http.call_args.args[0]

    assert result["target"] == "example.com"
    assert result["ip"] == expected
    assert result["errors"] == []


# TC06: Whitespace normalization.

@pytest.mark.parametrize("target", [
    " 8.8.8.8 ",
    "\t8.8.8.8\n",
])
def test_whitespace(target):
    with patch("ip_core.requests.get",
               return_value=response(METADATA)):
        result = ip_core.lookup_ip(target)

    assert result["target"] == "8.8.8.8"
    assert result["ip"] == "8.8.8.8"


# TC07: Invalid targets must not reach DNS or HTTP.

@pytest.mark.parametrize("target", [
    "", "   ", None, 123,
    "999.999.999.999",
    "192.168.1",
    "2001:db8:::1",
    "https://example.com",
    "example.com/path",
    "example.com:443",
    "bad host.example",
    "-example.com",
    "example-.com",
    "example..com",
    "example.com..",
    "example_com",
    "a" * 64 + ".com",
    "fe80::1%en0",
    "example.com?query=1",
    "user@example.com",
])
def test_invalid_target(target):
    with patch("ip_core.socket.getaddrinfo") as dns, \
         patch("ip_core.requests.get") as http:

        result = ip_core.lookup_ip(target)
        dns.assert_not_called()
        http.assert_not_called()

    assert result["ip"] == ip_core.UNKNOWN
    assert result["errors"]


# TC08-TC09: DNS failure and empty DNS results.

@pytest.mark.parametrize("dns_failure", [True, False])
def test_dns_failure(dns_failure):
    with patch(
        "ip_core.socket.getaddrinfo",
        side_effect=socket.gaierror() if dns_failure else None,
        return_value=[],
    ), patch("ip_core.requests.get") as http:

        result = ip_core.lookup_ip("nonexistent.invalid")
        http.assert_not_called()

    assert result["ip"] == ip_core.UNKNOWN
    assert any("could not resolve" in e for e in result["errors"])


# TC10: Internationalized hostname conversion.

def test_internationalized_hostname():
    with patch(
        "ip_core.socket.getaddrinfo",
        return_value=[dns_record("8.8.8.8")],
    ) as dns, patch(
        "ip_core.requests.get",
        return_value=response(METADATA),
    ):
        result = ip_core.lookup_ip("bücher.example")

    assert dns.call_args.args[0] == "xn--bcher-kva.example"
    assert result["target"] == "bücher.example"
    assert result["ip"] == "8.8.8.8"


# TC11: Metadata provider failover.

def test_metadata_failover():
    secondary = {
        "success": True,
        "country": "United States",
        "country_code": "US",
        "connection": {
            "isp": "Fallback ISP",
            "asn": 15169,
        },
    }

    with patch(
        "ip_core.requests.get",
        side_effect=[
            response(status=429),
            response(secondary),
        ],
    ) as http:
        result = ip_core.lookup_ip("8.8.8.8")

    assert http.call_count == 2
    assert "ipapi.co/8.8.8.8" in http.call_args_list[0].args[0]
    assert "ipwho.is/8.8.8.8" in http.call_args_list[1].args[0]
    assert result["ip"] == "8.8.8.8"
    assert result["isp"] == "Fallback ISP"
    assert result["asn"] == "AS15169"
    assert any("429" in e for e in result["errors"])


# TC12: All metadata providers fail.

@pytest.mark.parametrize("failure", [
    requests.ConnectionError,
    requests.Timeout,
])
def test_metadata_failure(failure):
    with patch("ip_core.requests.get",
               side_effect=failure()) as http:
        result = ip_core.lookup_ip("8.8.8.8")

    assert http.call_count == 2
    assert result["ip"] == "8.8.8.8"
    assert len(result["errors"]) == 2

    for key in (
        "city", "region", "country",
        "country_code", "isp", "asn",
    ):
        assert result[key] == ip_core.UNKNOWN


# TC13: Incomplete metadata.

def test_incomplete_metadata():
    with patch(
        "ip_core.requests.get",
        return_value=response({"country_code": "US"}),
    ):
        result = ip_core.lookup_ip("8.8.8.8")

    assert result["ip"] == "8.8.8.8"
    assert result["country_code"] == "US"
    assert result["isp"] == ip_core.UNKNOWN
    assert result["asn"] == ip_core.UNKNOWN
    assert result["city"] == ip_core.UNKNOWN


# TC14: Human-readable target report.

@pytest.mark.parametrize("address,version", [
    ("8.8.8.8", "IPv4"),
    ("2001:4860:4860::8888", "IPv6"),
])
def test_text_report(address, version, capsys):
    data = {
        **TARGET_DATA, "target": address, "ip": address,
    }

    with patch("ip_diagnostic.lookup_ip",
               return_value=data) as lookup, \
         patch("ip_diagnostic.get_public_ip_info") as own:

        assert ip_diagnostic.main(["--target", address]) == 0
        lookup.assert_called_once_with(address)
        own.assert_not_called()

    output = capsys.readouterr()
    assert "TARGET IP & NETWORK LOOKUP" in output.out
    assert address in output.out
    assert version in output.out
    assert "Example ISP" in output.out
    assert "AS15169" in output.out
    assert "United States" in output.out
    assert output.err == ""


# TC15-TC16: JSON and CSV target exports.

@pytest.mark.parametrize("flag", ["--json", "--csv"])
def test_target_export(flag, capsys):
    with patch("ip_diagnostic.lookup_ip",
               return_value=TARGET_DATA):
        assert ip_diagnostic.main(
            ["--target", "8.8.8.8", flag]
        ) == 0

    output = capsys.readouterr()

    if flag == "--json":
        assert json.loads(output.out) == TARGET_DATA
    else:
        row = parse_csv(output.out)
        assert list(row) == list(TARGET_DATA)

        for key, value in TARGET_DATA.items():
            if isinstance(value, list):
                assert json.loads(row[key]) == value
            else:
                assert row[key] == value

    assert "Looking up target" in output.err


# TC17: Invalid and unresolvable target CLI failures.

@pytest.mark.parametrize("flags", [
    [], ["--json"], ["--csv"],
])
@pytest.mark.parametrize("target,error", [
    ("999.999.999.999", "Invalid IP address"),
    ("nonexistent.invalid", "could not resolve"),
])
def test_failed_target(flags, target, error, capsys):
    with patch("ip_core.socket.getaddrinfo",
               side_effect=socket.gaierror()), \
         patch("ip_core.requests.get") as http:

        assert ip_diagnostic.main(
            ["--target", target] + flags
        ) == 1

        http.assert_not_called()

    output = capsys.readouterr()

    if flags == ["--json"]:
        data = json.loads(output.out)
        assert data["ip"] == ip_core.UNKNOWN
        assert any(error in e for e in data["errors"])
        assert error in output.err

    elif flags == ["--csv"]:
        row = parse_csv(output.out)
        assert row["ip"] == ip_core.UNKNOWN
        assert any(error in e for e in json.loads(row["errors"]))
        assert error in output.err

    else:
        assert "Target lookup failed" in output.out
        assert error in output.out


# TC18: Metadata failure does not invalidate a resolved IP.

@pytest.mark.parametrize("flags", [
    [], ["--json"], ["--csv"],
])
def test_partial_failure(flags, capsys):
    with patch("ip_core.requests.get",
               side_effect=requests.ConnectionError()):
        assert ip_diagnostic.main(
            ["--target", "8.8.8.8"] + flags
        ) == 0

    output = capsys.readouterr()

    if flags == ["--json"]:
        assert json.loads(output.out)["ip"] == "8.8.8.8"
        assert "Warning:" in output.err
    elif flags == ["--csv"]:
        assert parse_csv(output.out)["ip"] == "8.8.8.8"
        assert "Warning:" in output.err
    else:
        assert "8.8.8.8" in output.out
        assert "Warning:" in output.out


# TC19: Unexpected backend exception.

@pytest.mark.parametrize("flag", ["--json", "--csv"])
def test_unexpected_exception(flag, capsys):
    with patch("ip_diagnostic.lookup_ip",
               side_effect=RuntimeError("Test failure")):
        assert ip_diagnostic.main(
            ["--target", "8.8.8.8", flag]
        ) == 1

    output = capsys.readouterr()
    assert output.out == ""
    assert "Unable to complete network diagnostic" in output.err
    assert "Test failure" in output.err


# TC20-TC21: Invalid CLI arguments.

@pytest.mark.parametrize("args,error", [
    (["--target"], "expected one argument"),
    (
        ["--target", "8.8.8.8", "--json", "--csv"],
        "not allowed with argument",
    ),
])
def test_invalid_arguments(args, error, capsys):
    with patch("ip_diagnostic.lookup_ip") as lookup, \
         patch("ip_diagnostic.get_public_ip_info") as own:

        with pytest.raises(SystemExit) as exc:
            ip_diagnostic.main(args)

        lookup.assert_not_called()
        own.assert_not_called()

    assert exc.value.code == 2
    assert error in capsys.readouterr().err


# TC22: CLI help.

def test_help(capsys):
    with patch("ip_diagnostic.lookup_ip") as lookup, \
         patch("ip_diagnostic.get_public_ip_info") as own:

        with pytest.raises(SystemExit) as exc:
            ip_diagnostic.main(["--help"])

        lookup.assert_not_called()
        own.assert_not_called()

    assert exc.value.code == 0
    output = capsys.readouterr().out

    for flag in ("--target", "--json", "--csv"):
        assert flag in output


# TC23: Original self-diagnostic behavior.

@pytest.mark.parametrize("flags", [
    [], ["--json"], ["--csv"],
])
def test_self_diagnostic(flags, capsys):
    with patch("ip_diagnostic.get_public_ip_info",
               return_value=SELF_DATA) as own, \
         patch("ip_diagnostic.lookup_ip") as lookup:

        assert ip_diagnostic.main(flags) == 0
        own.assert_called_once_with()
        lookup.assert_not_called()

    output = capsys.readouterr().out

    if flags == ["--json"]:
        assert json.loads(output) == SELF_DATA
    elif flags == ["--csv"]:
        assert parse_csv(output)["ipv4"] == SELF_DATA["ipv4"]
    else:
        assert "PUBLIC IP & NETWORK DIAGNOSTIC UTILITY" in output
        assert SELF_DATA["ipv4"] in output


# TC24: Actual CLI entry point.

@pytest.mark.parametrize("flag", ["--json", "--csv"])
def test_entry_point(flag, capsys):
    with patch(
        "sys.argv",
        ["ip_diagnostic.py", "--target", "8.8.8.8", flag],
    ), patch(
        "ip_core.lookup_ip", return_value=TARGET_DATA,
    ) as lookup:

        with pytest.raises(SystemExit) as exc:
            runpy.run_module("ip_diagnostic", run_name="__main__")

        lookup.assert_called_once_with("8.8.8.8")

    assert exc.value.code == 0
    output = capsys.readouterr().out

    if flag == "--json":
        assert json.loads(output) == TARGET_DATA
    else:
        assert parse_csv(output)["ip"] == "8.8.8.8"


# TC25: Export file redirection.

@pytest.mark.parametrize("flag", ["--json", "--csv"])
def test_file_redirection(flag, tmp_path):
    path = tmp_path / f"target.{flag[2:]}"

    with path.open("w", encoding="utf-8", newline="") as output, \
         patch("sys.stdout", output), \
         patch("ip_diagnostic.lookup_ip", return_value=TARGET_DATA):

        assert ip_diagnostic.main(
            ["--target", "8.8.8.8", flag]
        ) == 0

    content = path.read_text(encoding="utf-8")

    if flag == "--json":
        assert json.loads(content) == TARGET_DATA
    else:
        assert parse_csv(content)["ip"] == "8.8.8.8"
