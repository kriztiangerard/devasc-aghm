"""Offline unit tests for ip_core.py (all HTTP is mocked)."""

from unittest.mock import MagicMock, patch

import requests

import ip_core

REQUIRED_KEYS = {"ipv4", "ipv6", "city", "region", "country", "country_code", "isp", "asn"}


def fake_resp(status=200, json_data=None, text=""):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_data
    r.text = text
    return r


def router(mapping):
    """Build a requests.get stand-in keyed by URL substring."""
    def _get(url, **kwargs):
        for key, value in mapping.items():
            if key in url:
                if isinstance(value, Exception):
                    raise value
                return value
        raise requests.ConnectionError("no route")
    return _get


IPAPI_OK = {
    "ip": "203.0.113.5", "city": "Manila", "region": "Metro Manila",
    "country_name": "Philippines", "country_code": "PH",
    "org": "Example ISP", "asn": "AS64500",
}


def test_happy_path_dual_stack():
    mapping = {
        "api.ipify.org": fake_resp(json_data={"ip": "203.0.113.5"}),
        "api6.ipify.org": fake_resp(json_data={"ip": "2001:db8::1"}),
        "ipapi.co": fake_resp(json_data=IPAPI_OK),
    }
    with patch("ip_core.requests.get", side_effect=router(mapping)):
        info = ip_core.get_public_ip_info()
    assert REQUIRED_KEYS <= info.keys()
    assert info["ipv4"] == "203.0.113.5"
    assert info["ipv6"] == "2001:db8::1"
    assert info["asn"] == "AS64500"
    assert info["country_code"] == "PH"


def test_ipv6_only_missing_is_not_detected():
    mapping = {
        "api.ipify.org": fake_resp(json_data={"ip": "203.0.113.5"}),
        "ipapi.co": fake_resp(json_data=IPAPI_OK),
    }
    with patch("ip_core.requests.get", side_effect=router(mapping)):
        info = ip_core.get_public_ip_info()
    assert info["ipv4"] == "203.0.113.5"
    assert info["ipv6"] == ip_core.UNAVAILABLE_V6


def test_offline_returns_defaults_without_raising():
    with patch("ip_core.requests.get", side_effect=requests.ConnectionError()):
        info = ip_core.get_public_ip_info()
    assert REQUIRED_KEYS <= info.keys()
    assert info["ipv4"] == ip_core.UNAVAILABLE_V4
    assert info["isp"] == ip_core.UNKNOWN
    assert info["errors"]


def test_timeout_is_caught():
    with patch("ip_core.requests.get", side_effect=requests.Timeout()):
        info = ip_core.get_public_ip_info()
    assert any("timed out" in e for e in info["errors"])


def test_ipify_failover_to_icanhazip():
    mapping = {
        "api.ipify.org": fake_resp(status=500),
        "ipv4.icanhazip.com": fake_resp(text="203.0.113.5\n"),
        "ipapi.co": fake_resp(json_data=IPAPI_OK),
    }
    with patch("ip_core.requests.get", side_effect=router(mapping)):
        info = ip_core.get_public_ip_info()
    assert info["ipv4"] == "203.0.113.5"
    assert info["sources"]["ipv4"] == "icanhazip"


def test_ipapi_429_falls_back_to_ipwho():
    mapping = {
        "api.ipify.org": fake_resp(json_data={"ip": "203.0.113.5"}),
        "ipapi.co": fake_resp(status=429),
        "ipwho.is": fake_resp(json_data={
            "success": True, "city": "Manila", "region": "Metro Manila",
            "country": "Philippines", "country_code": "PH",
            "connection": {"asn": 64500, "isp": "Example ISP"},
        }),
    }
    with patch("ip_core.requests.get", side_effect=router(mapping)):
        info = ip_core.get_public_ip_info()
    assert info["sources"]["metadata"] == "ipwho.is"
    assert info["asn"] == "AS64500"
    assert any("429" in e for e in info["errors"])


def test_wrong_ip_version_rejected():
    mapping = {
        "api.ipify.org": fake_resp(json_data={"ip": "2001:db8::1"}),  # v6 from v4 endpoint
        "ipv4.icanhazip.com": fake_resp(text="203.0.113.5"),
        "ipapi.co": fake_resp(json_data=IPAPI_OK),
    }
    with patch("ip_core.requests.get", side_effect=router(mapping)):
        info = ip_core.get_public_ip_info()
    assert info["ipv4"] == "203.0.113.5"


def test_detect_nat():
    assert "No NAT" in ip_core.detect_nat("203.0.113.5", "203.0.113.5")
    assert "CGNAT" in ip_core.detect_nat("100.64.1.2", "203.0.113.5")
    assert "Behind NAT" in ip_core.detect_nat("192.168.1.10", "203.0.113.5")
    assert ip_core.detect_nat(None, "203.0.113.5") == "Unknown"


def test_lookup_ip_unresolvable_host():
    with patch("ip_core.socket.gethostbyname", side_effect=OSError()):
        res = ip_core.lookup_ip("not-a-real-host.invalid")
    assert res["errors"]
    assert res["ip"] == ip_core.UNKNOWN
