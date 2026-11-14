"""Offline unit tests for ip_core.py (Phase 1). All HTTP is mocked."""

from unittest.mock import MagicMock, patch

import requests

import ip_core

REQUIRED_KEYS = {"ipv4", "ipv6", "city", "region", "country",
                 "country_code", "isp", "asn", "errors"}

IPAPI_OK = {
    "ip": "203.0.113.5", "city": "Manila", "region": "Metro Manila",
    "country_name": "Philippines", "country_code": "PH",
    "org": "Example ISP", "asn": "AS64500",
}


def fake_resp(status=200, json_data=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_data
    return r


def router(mapping):
    """requests.get stand-in; matches on URL substring, else connection error."""
    def _get(url, **kwargs):
        for key, value in mapping.items():
            if key in url:
                return value
        raise requests.ConnectionError("no route")
    return _get


def run(mapping=None, side_effect=None):
    effect = side_effect or router(mapping or {})
    with patch("ip_core.requests.get", side_effect=effect):
        return ip_core.get_public_ip_info()


def test_happy_path_dual_stack():
    info = run({
        "api.ipify.org": fake_resp(json_data={"ip": "203.0.113.5"}),
        "api6.ipify.org": fake_resp(json_data={"ip": "2001:db8::1"}),
        "ipapi.co": fake_resp(json_data=IPAPI_OK),
    })
    assert REQUIRED_KEYS <= info.keys()
    assert info["ipv4"] == "203.0.113.5"
    assert info["ipv6"] == "2001:db8::1"
    assert info["asn"] == "AS64500"
    assert info["country_code"] == "PH"
    assert info["errors"] == []


def test_ipv6_missing_is_not_detected():
    info = run({
        "api.ipify.org": fake_resp(json_data={"ip": "203.0.113.5"}),
        "ipapi.co": fake_resp(json_data=IPAPI_OK),
    })
    assert info["ipv4"] == "203.0.113.5"
    assert info["ipv6"] == ip_core.UNAVAILABLE_V6


def test_offline_returns_defaults_without_raising():
    info = run(side_effect=requests.ConnectionError())
    assert REQUIRED_KEYS <= info.keys()
    assert info["ipv4"] == ip_core.UNAVAILABLE_V4
    assert info["isp"] == ip_core.UNKNOWN
    assert info["errors"]


def test_timeout_is_caught():
    info = run(side_effect=requests.Timeout())
    assert any("timed out" in e for e in info["errors"])


def test_ipify_http_error_is_recorded():
    info = run({
        "api.ipify.org": fake_resp(status=500),
        "ipapi.co": fake_resp(json_data=IPAPI_OK),
    })
    assert info["ipv4"] == ip_core.UNAVAILABLE_V4
    assert any("HTTP 500" in e for e in info["errors"])


def test_ipapi_rate_limit_keeps_ip_and_defaults_metadata():
    info = run({
        "api.ipify.org": fake_resp(json_data={"ip": "203.0.113.5"}),
        "ipapi.co": fake_resp(status=429),
    })
    assert info["ipv4"] == "203.0.113.5"
    assert info["isp"] == ip_core.UNKNOWN
    assert any("429" in e for e in info["errors"])


def test_wrong_ip_version_rejected():
    info = run({
        "api.ipify.org": fake_resp(json_data={"ip": "2001:db8::1"}),  # v6 from v4 endpoint
        "ipapi.co": fake_resp(json_data=IPAPI_OK),
    })
    assert info["ipv4"] == ip_core.UNAVAILABLE_V4
