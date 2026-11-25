"""
ip_core.py - Core networking module (Member 1)

Shared by the CLI (ip_diagnostic.py) and GUI (ip_diagnostic_gui.py).

Public API
----------
get_public_ip_info(include_extras=False) -> dict
lookup_ip(target)                        -> dict   (BL-07 helper for Member 3)
get_local_addresses()                    -> dict   (BL-01)
detect_nat(local_ip, public_ip)          -> str    (BL-01)
reverse_dns(ip)                          -> str    (BL-05)

Result dict keys (agreed shape, always present):
    ipv4, ipv6, city, region, country, country_code, isp, asn
Extra keys:
    errors      list[str]   - human-readable problems, empty if all good
    sources     dict        - which provider answered each field
    latency_ms  dict        - round-trip time per successful call (BL-05)
    (include_extras=True adds: local_ipv4, local_ipv6, nat_status, ptr)

Nothing in here raises on network problems; failures end up in "errors".
"""

import ipaddress
import socket
import time

import requests

TIMEOUT = 5  # seconds per request
HEADERS = {"User-Agent": "ip-diagnostic/1.0"}

UNAVAILABLE_V4 = "Unavailable"
UNAVAILABLE_V6 = "Not Detected"
UNKNOWN = "Unknown"

CGNAT_NET = ipaddress.ip_network("100.64.0.0/10")


# --------------------------------------------------------------------------
# Network exception handler
# --------------------------------------------------------------------------
class NetworkError(Exception):
    """Single exception type for every HTTP/network failure."""


def _http_get(url, timeout=TIMEOUT):
    """GET a URL. Returns (response, latency_ms) or raises NetworkError."""
    start = time.perf_counter()
    try:
        resp = requests.get(url, timeout=timeout, headers=HEADERS)
    except requests.Timeout:
        raise NetworkError("timed out")
    except requests.ConnectionError:
        raise NetworkError("connection failed")
    except requests.RequestException as exc:
        raise NetworkError(str(exc))
    latency = round((time.perf_counter() - start) * 1000, 1)

    if resp.status_code == 429:
        raise NetworkError("rate limited (HTTP 429)")
    if resp.status_code != 200:
        raise NetworkError(f"HTTP {resp.status_code}")
    return resp, latency


# --------------------------------------------------------------------------
# Response parsers
# --------------------------------------------------------------------------
def _parse_json_ip(resp):
    return resp.json()["ip"]


def _parse_text_ip(resp):
    return resp.text.strip()


def _parse_trace_ip(resp):
    for line in resp.text.splitlines():
        if line.startswith("ip="):
            return line[3:].strip()
    raise ValueError("no ip= line in trace output")


# Ordered by priority. First one that works wins (BL-02 failover).
IPV4_PROVIDERS = [
    ("ipify", "https://api.ipify.org?format=json", _parse_json_ip),
    ("icanhazip", "https://ipv4.icanhazip.com", _parse_text_ip),
    ("cloudflare", "https://1.1.1.1/cdn-cgi/trace", _parse_trace_ip),
]
IPV6_PROVIDERS = [
    ("ipify", "https://api6.ipify.org?format=json", _parse_json_ip),
    ("icanhazip", "https://ipv6.icanhazip.com", _parse_text_ip),
]


def _resolve_ip(version, providers, errors):
    """Try each provider until one returns a valid IP of the right version.
    Returns (ip | None, source | None, latency_ms | None)."""
    for name, url, parser in providers:
        try:
            resp, latency = _http_get(url)
            ip = parser(resp)
            if ipaddress.ip_address(ip).version != version:
                raise ValueError(f"returned IPv{ipaddress.ip_address(ip).version}")
            return ip, name, latency
        except NetworkError as exc:
            errors.append(f"IPv{version} via {name}: {exc}")
        except (ValueError, KeyError) as exc:
            errors.append(f"IPv{version} via {name}: bad response ({exc})")
    return None, None, None


# --------------------------------------------------------------------------
# Metadata (ISP / ASN / location) with failover
# --------------------------------------------------------------------------
def _meta_ipapi(ip):
    url = f"https://ipapi.co/{ip}/json/" if ip else "https://ipapi.co/json/"
    resp, latency = _http_get(url)
    d = resp.json()
    if d.get("error"):
        raise NetworkError(d.get("reason") or "ipapi.co returned an error")
    return {
        "city": d.get("city"),
        "region": d.get("region"),
        "country": d.get("country_name"),
        "country_code": d.get("country_code"),
        "isp": d.get("org"),
        "asn": d.get("asn"),
    }, latency


def _meta_ipwho(ip):
    resp, latency = _http_get(f"https://ipwho.is/{ip}")
    d = resp.json()
    if not d.get("success", True):
        raise NetworkError(d.get("message") or "ipwho.is returned an error")
    conn = d.get("connection") or {}
    asn = conn.get("asn")
    return {
        "city": d.get("city"),
        "region": d.get("region"),
        "country": d.get("country"),
        "country_code": d.get("country_code"),
        "isp": conn.get("isp") or conn.get("org"),
        "asn": f"AS{asn}" if asn else None,
    }, latency


def _lookup_metadata(ip, errors):
    """Returns (meta dict | None, source | None, latency_ms | None)."""
    providers = [("ipapi.co", _meta_ipapi)]
    if ip:  # ipwho.is needs an explicit IP
        providers.append(("ipwho.is", _meta_ipwho))
    for name, fn in providers:
        try:
            meta, latency = fn(ip)
            return meta, name, latency
        except NetworkError as exc:
            errors.append(f"metadata via {name}: {exc}")
        except (ValueError, KeyError, AttributeError) as exc:
            errors.append(f"metadata via {name}: bad response ({exc})")
    return None, None, None


def _apply_meta(results, meta):
    for key in ("city", "region", "country", "country_code", "isp", "asn"):
        results[key] = (meta or {}).get(key) or UNKNOWN


# --------------------------------------------------------------------------
# BL-01: local interfaces & NAT comparison
# --------------------------------------------------------------------------
def _local_address(family, probe):
    """Find the outbound local address. UDP connect() sends no packets."""
    try:
        with socket.socket(family, socket.SOCK_DGRAM) as s:
            s.settimeout(2)
            s.connect((probe, 80))
            return s.getsockname()[0]
    except OSError:
        return None


def get_local_addresses():
    return {
        "local_ipv4": _local_address(socket.AF_INET, "8.8.8.8"),
        "local_ipv6": _local_address(socket.AF_INET6, "2001:4860:4860::8888"),
    }


def detect_nat(local_ip, public_ip):
    """Classify the local vs public IPv4 relationship."""
    if not local_ip or not public_ip:
        return "Unknown"
    try:
        local = ipaddress.ip_address(local_ip)
        if local == ipaddress.ip_address(public_ip):
            return "No NAT (public IP on interface)"
        if local in CGNAT_NET:
            return "Carrier-Grade NAT (CGNAT) likely"
        if local.is_private:
            return "Behind NAT (private LAN address)"
    except ValueError:
        pass
    return "Unknown"


# --------------------------------------------------------------------------
# BL-05: reverse DNS
# --------------------------------------------------------------------------
def reverse_dns(ip):
    try:
        return socket.gethostbyaddr(ip)[0]
    except (socket.herror, socket.gaierror, OSError):
        return "No PTR record"


# --------------------------------------------------------------------------
# Main entry points
# --------------------------------------------------------------------------
def get_public_ip_info(include_extras=False):
    """Collect public IPv4/IPv6 + ISP/ASN/location. Never raises."""
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
        "sources": {},
        "latency_ms": {},
    }

    v4, src4, lat4 = _resolve_ip(4, IPV4_PROVIDERS, errors)
    if v4:
        results["ipv4"] = v4
        results["sources"]["ipv4"] = src4
        results["latency_ms"][src4] = lat4

    v6, src6, lat6 = _resolve_ip(6, IPV6_PROVIDERS, errors)
    if v6:
        results["ipv6"] = v6
        results["sources"]["ipv6"] = src6
        results["latency_ms"][f"{src6}-v6"] = lat6

    meta, src_m, lat_m = _lookup_metadata(v4 or v6, errors)
    _apply_meta(results, meta)
    if src_m:
        results["sources"]["metadata"] = src_m
        results["latency_ms"][src_m] = lat_m

    if include_extras:
        results.update(get_local_addresses())
        results["nat_status"] = detect_nat(results["local_ipv4"], v4)
        results["ptr"] = reverse_dns(v4 or v6) if (v4 or v6) else "N/A"

    return results


def lookup_ip(target):
    """Metadata for any IP or hostname (BL-07). Never raises."""
    errors = []
    results = {
        "target": target,
        "ip": UNKNOWN,
        "city": UNKNOWN,
        "region": UNKNOWN,
        "country": UNKNOWN,
        "country_code": UNKNOWN,
        "isp": UNKNOWN,
        "asn": UNKNOWN,
        "errors": errors,
    }
    try:
        ip = str(ipaddress.ip_address(target))
    except ValueError:
        try:
            ip = socket.gethostbyname(target)
        except OSError:
            errors.append(f"could not resolve '{target}'")
            return results
    results["ip"] = ip
    meta, _, _ = _lookup_metadata(ip, errors)
    _apply_meta(results, meta)
    return results


if __name__ == "__main__":
    import json

    print(json.dumps(get_public_ip_info(include_extras=True), indent=2))
