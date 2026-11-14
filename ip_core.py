"""
ip_core.py - Core networking module (Member 1, Phase 1 / Project Activity 3)

Shared backend for the CLI (ip_diagnostic.py) and GUI (ip_diagnostic_gui.py).

Architecture (hybrid, per the project plan):
    Addressing layer  : ipify    -> explicit IPv4 (api.ipify.org) and IPv6 (api6.ipify.org)
    Enrichment layer  : ipapi.co -> ISP, ASN, city, region, country, country code

Public API
----------
get_public_ip_info() -> dict

Result dict keys (always present):
    ipv4, ipv6, city, region, country, country_code, isp, asn, errors

Defaults when a lookup fails:
    ipv4 = "Unavailable", ipv6 = "Not Detected", everything else = "Unknown"

The function never raises on network problems. Every failure (timeout,
connection error, HTTP 429, non-200, bad JSON) is caught and added to the
"errors" list as a readable string.

NOTE for CLI/GUI authors: on an IPv4-only network, "errors" will contain
IPv6 entries even though nothing is wrong. Do not show "errors" as an error
banner by default.

Phase 2 (Activity 4) will extend this module: BL-01 (NAT), BL-02 (failover),
BL-05 (reverse DNS and latency).
"""

import ipaddress

import requests

TIMEOUT = 5  # seconds per request
HEADERS = {"User-Agent": "ip-diagnostic/1.0"}

IPIFY_V4_URL = "https://api.ipify.org?format=json"
IPIFY_V6_URL = "https://api6.ipify.org?format=json"
IPAPI_URL = "https://ipapi.co/{ip}/json/"
IPAPI_SELF_URL = "https://ipapi.co/json/"

UNAVAILABLE_V4 = "Unavailable"
UNAVAILABLE_V6 = "Not Detected"
UNKNOWN = "Unknown"


class NetworkError(Exception):
    """Single exception type for every HTTP/network failure."""


def _http_get(url, timeout=TIMEOUT):
    """GET a URL and return the response, or raise NetworkError."""
    try:
        resp = requests.get(url, timeout=timeout, headers=HEADERS)
    except requests.Timeout:
        raise NetworkError("timed out")
    except requests.ConnectionError:
        raise NetworkError("connection failed")
    except requests.RequestException as exc:
        raise NetworkError(str(exc))

    if resp.status_code == 429:
        raise NetworkError("rate limited (HTTP 429)")
    if resp.status_code != 200:
        raise NetworkError(f"HTTP {resp.status_code}")
    return resp


def _get_ip(url, version, errors):
    """Ask ipify for an address. Returns the IP string, or None on failure."""
    try:
        ip = _http_get(url).json()["ip"]
        if ipaddress.ip_address(ip).version != version:
            raise ValueError(f"expected IPv{version}, got a different version")
        return ip
    except NetworkError as exc:
        errors.append(f"IPv{version} via ipify: {exc}")
    except (ValueError, KeyError) as exc:
        errors.append(f"IPv{version} via ipify: bad response ({exc})")
    return None


def _get_metadata(ip, errors):
    """Ask ipapi.co for ISP/ASN/location. Returns a dict, or None on failure."""
    url = IPAPI_URL.format(ip=ip) if ip else IPAPI_SELF_URL
    try:
        data = _http_get(url).json()
        if data.get("error"):  # ipapi.co reports some errors inside a 200 body
            raise NetworkError(data.get("reason") or "ipapi.co returned an error")
        return data
    except NetworkError as exc:
        errors.append(f"metadata via ipapi.co: {exc}")
    except (ValueError, AttributeError) as exc:
        errors.append(f"metadata via ipapi.co: bad response ({exc})")
    return None


def get_public_ip_info():
    """Collect public IPv4/IPv6 plus ISP, ASN and location. Never raises."""
    errors = []
    results = {
        "ipv4": UNAVAILABLE_V4,
        "ipv6": UNAVAILABLE_V6,
        "city": UNKNOWN,
        "region": UNKNOWN,
        "country": UNKNOWN,
        "country_code": UNKNOWN,
        "isp": UNKNOWN,
        "asn": UNKNOWN,
        "errors": errors,
    }

    v4 = _get_ip(IPIFY_V4_URL, 4, errors)
    if v4:
        results["ipv4"] = v4

    v6 = _get_ip(IPIFY_V6_URL, 6, errors)
    if v6:
        results["ipv6"] = v6

    data = _get_metadata(v4 or v6, errors)
    if data:
        results["city"] = data.get("city") or UNKNOWN
        results["region"] = data.get("region") or UNKNOWN
        results["country"] = data.get("country_name") or UNKNOWN
        results["country_code"] = data.get("country_code") or UNKNOWN
        results["isp"] = data.get("org") or UNKNOWN
        results["asn"] = data.get("asn") or UNKNOWN

    return results


if __name__ == "__main__":
    import json

    print(json.dumps(get_public_ip_info(), indent=2))
