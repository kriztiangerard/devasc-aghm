"""Automated tests for the Public IP Diagnostic CLI."""

from unittest.mock import patch

from ip_diagnostic import format_report, main


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


def test_normal_output():
    """All expected network fields appear in the report."""
    report = format_report(SAMPLE_DATA)

    assert "203.0.113.10" in report
    assert "2001:db8::1" in report
    assert "Example ISP" in report
    assert "AS64500" in report
    assert "Manila, Metro Manila, Philippines (PH)" in report


def test_missing_ipv6():
    """Missing IPv6 is displayed without crashing."""
    data = {**SAMPLE_DATA, "ipv6": "Not Detected"}

    report = format_report(data)

    assert "Public IPv6 Address : Not Detected" in report


def test_missing_metadata():
    """Missing metadata uses safe default values."""
    data = {
        "ipv4": "203.0.113.10",
        "ipv6": "Not Detected",
        "isp": None,
        "asn": None,
        "city": None,
        "region": None,
        "country": None,
        "country_code": None,
    }

    report = format_report(data)

    assert "ISP / Organization  : Unknown" in report
    assert "ASN                 : Unknown" in report
    assert "Unknown, Unknown, Unknown (Unknown)" in report


def test_offline_network(capsys):
    """An offline result displays a helpful notice."""
    data = {
        **SAMPLE_DATA,
        "ipv4": "Unavailable",
        "ipv6": "Not Detected",
        "isp": "Unknown",
        "asn": "Unknown",
    }

    with patch("ip_diagnostic.get_public_ip_info", return_value=data):
        result = main()

    output = capsys.readouterr().out

    assert result == 0
    assert "No public IP address could be detected" in output


def test_unexpected_backend_error(capsys):
    """An unexpected backend error does not crash the CLI."""
    with patch(
        "ip_diagnostic.get_public_ip_info",
        side_effect=RuntimeError("Test backend error"),
    ):
        result = main()

    output = capsys.readouterr().out

    assert result == 1
    assert "Unable to complete network diagnostic" in output
