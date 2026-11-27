"""Offline unit tests for ip_core.py (all HTTP is mocked)."""

from unittest.mock import MagicMock, patch

import pytest
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
    with patch("ip_core.socket.getaddrinfo", side_effect=OSError()):
        res = ip_core.lookup_ip("not-a-real-host.invalid")
    assert res["errors"]
    assert res["ip"] == ip_core.UNKNOWN


# Activity 4 additional backlog coverage

def test_reverse_dns_success():
    with patch("ip_core.socket.gethostbyaddr",
               return_value=("dns.google", [], ["8.8.8.8"])):
        assert ip_core.reverse_dns("8.8.8.8") == "dns.google"


def test_reverse_dns_failure():
    with patch("ip_core.socket.gethostbyaddr",
               side_effect=OSError()):
        assert ip_core.reverse_dns("8.8.8.8") == "No PTR record"


def test_lookup_ip_success():
    with patch("ip_core.requests.get",
               return_value=fake_resp(json_data=IPAPI_OK)):
        result = ip_core.lookup_ip("203.0.113.5")

    assert result["ip"] == "203.0.113.5"
    assert result["asn"] == "AS64500"
    assert result["country_code"] == "PH"
    assert result["errors"] == []


def test_provider_latency_tracking():
    mapping = {
        "api.ipify.org": fake_resp(
            json_data={"ip": "203.0.113.5"}),
        "api6.ipify.org": fake_resp(
            json_data={"ip": "2001:db8::1"}),
        "ipapi.co": fake_resp(json_data=IPAPI_OK),
    }

    with patch("ip_core.requests.get",
               side_effect=router(mapping)):
        info = ip_core.get_public_ip_info()

    assert info["sources"]["ipv4"] == "ipify"
    assert info["sources"]["ipv6"] == "ipify"
    assert info["sources"]["metadata"] == "ipapi.co"

    for provider in ("ipify", "ipify-v6", "ipapi.co"):
        assert provider in info["latency_ms"]
        assert info["latency_ms"][provider] >= 0


def test_include_extras():
    mapping = {
        "api.ipify.org": fake_resp(
            json_data={"ip": "203.0.113.5"}),
        "ipapi.co": fake_resp(json_data=IPAPI_OK),
    }

    with patch("ip_core.requests.get",
               side_effect=router(mapping)), \
         patch("ip_core.get_local_addresses",
               return_value={
                   "local_ipv4": "192.168.1.10",
                   "local_ipv6": None,
               }), \
         patch("ip_core.reverse_dns",
               return_value="example.test"):

        info = ip_core.get_public_ip_info(
            include_extras=True)

    assert info["local_ipv4"] == "192.168.1.10"
    assert info["local_ipv6"] is None
    assert "Behind NAT" in info["nat_status"]
    assert info["ptr"] == "example.test"


def test_cloudflare_ipv4_failover():
    mapping = {
        "api.ipify.org": fake_resp(status=500),
        "ipv4.icanhazip.com": fake_resp(status=500),
        "cdn-cgi/trace": fake_resp(
            text="ip=203.0.113.5\n"),
        "ipapi.co": fake_resp(json_data=IPAPI_OK),
    }

    with patch("ip_core.requests.get",
               side_effect=router(mapping)):
        info = ip_core.get_public_ip_info()

    assert info["ipv4"] == "203.0.113.5"
    assert info["sources"]["ipv4"] == "cloudflare"


def test_ipv6_provider_failover():
    mapping = {
        "api.ipify.org": fake_resp(
            json_data={"ip": "203.0.113.5"}),
        "api6.ipify.org": fake_resp(status=500),
        "ipv6.icanhazip.com": fake_resp(
            text="2001:db8::1"),
        "ipapi.co": fake_resp(json_data=IPAPI_OK),
    }

    with patch("ip_core.requests.get",
               side_effect=router(mapping)):
        info = ip_core.get_public_ip_info()

    assert info["ipv6"] == "2001:db8::1"
    assert info["sources"]["ipv6"] == "icanhazip"


def test_default_output_remains_compatible():
    with patch("ip_core.requests.get",
               side_effect=requests.ConnectionError()):
        info = ip_core.get_public_ip_info()

    assert REQUIRED_KEYS <= info.keys()
    assert "errors" in info

    for key in ("local_ipv4", "local_ipv6",
                "nat_status", "ptr"):
        assert key not in info
# ACT4-CORE-001 malformed response regression coverage

@pytest.mark.parametrize("payload", [
    None,
    [],
    "unexpected",
    12345,
    {},
    {"unexpected": "value"},
    {"ip": None},
    {"ip": 12345},
    {"ip": True},
    {"ip": []},
    {"ip": {}},
    {"ip": ""},
    {"ip": "   "},
    {"ip": "invalid-ip"},
])
def test_malformed_ipv4_primary_falls_back(payload):
    mapping = {
        "api.ipify.org": fake_resp(json_data=payload),
        "ipv4.icanhazip.com": fake_resp(text="203.0.113.5"),
        "ipapi.co": fake_resp(json_data=IPAPI_OK),
    }

    with patch("ip_core.requests.get", side_effect=router(mapping)):
        info = ip_core.get_public_ip_info()

    assert info["ipv4"] == "203.0.113.5"
    assert info["sources"]["ipv4"] == "icanhazip"
    assert "icanhazip" in info["latency_ms"]
    assert any(
        "IPv4 via ipify: bad response" in error
        for error in info["errors"]
    )


@pytest.mark.parametrize("payload", [
    None,
    [],
    {"ip": None},
    {"ip": 12345},
    {"ip": "invalid-ip"},
])
def test_malformed_ipv6_primary_falls_back(payload):
    mapping = {
        "api.ipify.org": fake_resp(
            json_data={"ip": "203.0.113.5"}),
        "api6.ipify.org": fake_resp(json_data=payload),
        "ipv6.icanhazip.com": fake_resp(text="2001:db8::1"),
        "ipapi.co": fake_resp(json_data=IPAPI_OK),
    }

    with patch("ip_core.requests.get", side_effect=router(mapping)):
        info = ip_core.get_public_ip_info()

    assert info["ipv6"] == "2001:db8::1"
    assert info["sources"]["ipv6"] == "icanhazip"
    assert "icanhazip-v6" in info["latency_ms"]
    assert any(
        "IPv6 via ipify: bad response" in error
        for error in info["errors"]
    )


def test_all_ip_providers_malformed():
    mapping = {
        "api.ipify.org": fake_resp(json_data=None),
        "ipv4.icanhazip.com": fake_resp(text="invalid"),
        "cdn-cgi/trace": fake_resp(text="invalid trace"),
        "api6.ipify.org": fake_resp(json_data=[]),
        "ipv6.icanhazip.com": fake_resp(text="invalid"),
        "ipapi.co": fake_resp(json_data=None),
    }

    with patch("ip_core.requests.get", side_effect=router(mapping)):
        info = ip_core.get_public_ip_info()

    assert info["ipv4"] == ip_core.UNAVAILABLE_V4
    assert info["ipv6"] == ip_core.UNAVAILABLE_V6
    assert info["isp"] == ip_core.UNKNOWN
    assert info["sources"] == {}
    assert info["latency_ms"] == {}
    assert len(info["errors"]) == 6


def test_invalid_json_decoding_falls_back():
    malformed = fake_resp()
    malformed.json.side_effect = ValueError("invalid JSON")

    mapping = {
        "api.ipify.org": malformed,
        "ipv4.icanhazip.com": fake_resp(text="203.0.113.5"),
        "ipapi.co": fake_resp(json_data=IPAPI_OK),
    }

    with patch("ip_core.requests.get", side_effect=router(mapping)):
        info = ip_core.get_public_ip_info()

    assert info["ipv4"] == "203.0.113.5"
    assert info["sources"]["ipv4"] == "icanhazip"
    assert any(
        "invalid JSON" in error
        for error in info["errors"]
    )


@pytest.mark.parametrize("payload", [
    None,
    [],
    "unexpected",
    12345,
    {},
    {"city": None},
    {"city": "   "},
    {"city": []},
    {"org": {}},
    {"asn": 12345},
])
def test_malformed_metadata_primary_falls_back(payload):
    mapping = {
        "api.ipify.org": fake_resp(
            json_data={"ip": "203.0.113.5"}),
        "ipapi.co": fake_resp(json_data=payload),
        "ipwho.is": fake_resp(json_data={
            "success": True,
            "city": "Manila",
            "country": "Philippines",
            "country_code": "PH",
            "connection": {
                "asn": 64500,
                "isp": "Example ISP",
            },
        }),
    }

    with patch("ip_core.requests.get", side_effect=router(mapping)):
        info = ip_core.get_public_ip_info()

    assert info["sources"]["metadata"] == "ipwho.is"
    assert info["isp"] == "Example ISP"
    assert info["asn"] == "AS64500"
    assert "ipwho.is" in info["latency_ms"]
    assert any(
        "metadata via ipapi.co: bad response" in error
        for error in info["errors"]
    )


@pytest.mark.parametrize("connection", [
    [],
    "invalid",
    12345,
    False,
    {"asn": []},
    {"asn": {}},
    {"asn": True},
    {"asn": "invalid"},
    {"isp": []},
])
def test_malformed_metadata_connection_returns_defaults(connection):
    mapping = {
        "api.ipify.org": fake_resp(
            json_data={"ip": "203.0.113.5"}),
        "ipapi.co": fake_resp(json_data=None),
        "ipwho.is": fake_resp(json_data={
            "success": True,
            "connection": connection,
        }),
    }

    with patch("ip_core.requests.get", side_effect=router(mapping)):
        info = ip_core.get_public_ip_info()

    assert info["ipv4"] == "203.0.113.5"
    assert info["isp"] == ip_core.UNKNOWN
    assert info["asn"] == ip_core.UNKNOWN
    assert "metadata" not in info["sources"]
    assert "ipwho.is" not in info["latency_ms"]
    assert any(
        "metadata via ipwho.is: bad response" in error
        for error in info["errors"]
    )


def test_all_metadata_providers_malformed():
    mapping = {
        "api.ipify.org": fake_resp(
            json_data={"ip": "203.0.113.5"}),
        "ipapi.co": fake_resp(json_data=None),
        "ipwho.is": fake_resp(json_data=[]),
    }

    with patch("ip_core.requests.get", side_effect=router(mapping)):
        info = ip_core.get_public_ip_info()

    assert info["ipv4"] == "203.0.113.5"

    for key in (
        "city", "region", "country",
        "country_code", "isp", "asn"
    ):
        assert info[key] == ip_core.UNKNOWN

    assert "metadata" not in info["sources"]
    assert any("metadata via ipapi.co" in e for e in info["errors"])
    assert any("metadata via ipwho.is" in e for e in info["errors"])


def test_valid_partial_metadata_remains_supported():
    mapping = {
        "api.ipify.org": fake_resp(
            json_data={"ip": "203.0.113.5"}),
        "ipapi.co": fake_resp(json_data={
            "city": None,
            "org": "Example ISP",
        }),
    }

    with patch("ip_core.requests.get", side_effect=router(mapping)):
        info = ip_core.get_public_ip_info()

    assert info["sources"]["metadata"] == "ipapi.co"
    assert info["isp"] == "Example ISP"
    assert info["city"] == ip_core.UNKNOWN


def test_target_lookup_malformed_metadata():
    mapping = {
        "ipapi.co": fake_resp(json_data=None),
        "ipwho.is": fake_resp(json_data=[]),
    }

    with patch("ip_core.requests.get", side_effect=router(mapping)):
        result = ip_core.lookup_ip("8.8.8.8")

    assert result["ip"] == "8.8.8.8"
    assert result["isp"] == ip_core.UNKNOWN
    assert result["asn"] == ip_core.UNKNOWN
    assert len(result["errors"]) == 2
