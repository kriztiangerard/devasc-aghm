"""BL-04: VPN, proxy, Tor, relay, and hosting detection.

Providers:
    VPNAPI.io — VPN, proxy, Tor, and relay flags.
    ipapi.is  — explicit datacenter/hosting classification.

Environment variables:
    VPNAPI_KEY
    IPAPI_IS_KEY

Run:
    python ip_privacy.py --target 8.8.8.8
    python ip_privacy.py

Provider classifications are indicators, not guarantees.
Unknown results must not be interpreted as No.
"""

import argparse
import ipaddress
import json
import os

import requests


UNKNOWN = "Unknown"
TIMEOUT = 5
PROVIDER = "vpnapi.io"


def check_privacy(target, api_key=None):
    """Check VPNAPI.io flags for one public IPv4/IPv6 address.

    Returns Yes/No only for explicitly boolean response fields.
    Missing or invalid fields remain Unknown.

    This function covers VPNAPI.io fields only. The CLI combines
    this result with check_hosting().
    """
    result = {
        "ip": UNKNOWN,
        "vpn": UNKNOWN,
        "proxy": UNKNOWN,
        "tor": UNKNOWN,
        "relay": UNKNOWN,
        "hosting": UNKNOWN,
        "source": None,
        "status": "unavailable",
        "errors": [],
    }

    if not isinstance(target, str):
        result["errors"].append(
            "Target must be an IPv4 or IPv6 address."
        )
        return result

    try:
        address = ipaddress.ip_address(target.strip())
    except ValueError:
        result["errors"].append("Invalid IP address.")
        return result

    result["ip"] = str(address)

    if "%" in target or not address.is_global or address.is_multicast:
        result["errors"].append(
            "A public, unscoped IP address is required."
        )
        return result

    key = (
        api_key
        if api_key is not None
        else os.getenv("VPNAPI_KEY", "")
    )

    if not isinstance(key, str) or not key.strip():
        result["errors"].append(
            "VPNAPI_KEY is not configured."
        )
        return result

    try:
        response = requests.get(
            f"https://vpnapi.io/api/{address}",
            params={"key": key.strip()},
            timeout=TIMEOUT,
        )
    except requests.Timeout:
        result["errors"].append(
            "Privacy lookup timed out."
        )
        return result
    except requests.RequestException:
        # Do not expose request URLs or API keys through exceptions.
        result["errors"].append(
            "Privacy service connection failed."
        )
        return result

    if response.status_code != 200:
        message = {
            401: "Privacy service authentication failed.",
            403: "Privacy service access denied.",
            429: "Privacy service rate limit reached.",
        }.get(
            response.status_code,
            f"Privacy service returned HTTP {response.status_code}.",
        )

        result["errors"].append(message)
        return result

    try:
        data = response.json()
    except ValueError:
        result["errors"].append(
            "Privacy service returned invalid JSON."
        )
        return result

    if not isinstance(data, dict):
        result["errors"].append(
            "Privacy response must be an object."
        )
        return result

    if data.get("error") or data.get("message"):
        result["errors"].append(
            "Privacy service reported an error."
        )
        return result

    try:
        returned_ip = ipaddress.ip_address(data.get("ip"))
    except (ValueError, TypeError):
        returned_ip = None

    if returned_ip != address:
        result["errors"].append(
            "Privacy response contains a missing or mismatched IP."
        )
        return result

    security = data.get("security")

    if not isinstance(security, dict):
        result["errors"].append(
            "Privacy response has no valid security object."
        )
        return result

    result["source"] = PROVIDER
    missing = []

    for field in ("vpn", "proxy", "tor", "relay"):
        value = security.get(field)

        if type(value) is bool:
            result[field] = "Yes" if value else "No"
        else:
            missing.append(field)

    if missing:
        result["errors"].append(
            "Unverified security fields: " + ", ".join(missing)
        )

    verified = [
        result[field] != UNKNOWN
        for field in ("vpn", "proxy", "tor", "relay")
    ]

    if all(verified):
        result["status"] = "complete"
    elif any(verified):
        result["status"] = "partial"

    return result


def check_hosting(target, api_key=None):
    """Check ipapi.is's explicit datacenter classification.

    Hosting is Yes/No only when is_datacenter is a boolean.
    """
    result = {
        "hosting": UNKNOWN,
        "source": None,
        "errors": [],
    }

    if not isinstance(target, str) or "%" in target:
        result["errors"].append(
            "Invalid hosting lookup target."
        )
        return result

    try:
        address = ipaddress.ip_address(target.strip())
    except ValueError:
        result["errors"].append(
            "Invalid hosting lookup target."
        )
        return result

    if not address.is_global or address.is_multicast:
        result["errors"].append(
            "Hosting lookup requires a public IP."
        )
        return result

    key = (
        api_key
        if api_key is not None
        else os.getenv("IPAPI_IS_KEY", "")
    )

    if not isinstance(key, str) or not key.strip():
        result["errors"].append(
            "IPAPI_IS_KEY is not configured."
        )
        return result

    try:
        response = requests.get(
            "https://api.ipapi.is/",
            params={
                "q": str(address),
                "key": key.strip(),
            },
            timeout=TIMEOUT,
        )
    except requests.Timeout:
        result["errors"].append(
            "Hosting lookup timed out."
        )
        return result
    except requests.RequestException:
        result["errors"].append(
            "Hosting service connection failed."
        )
        return result

    if response.status_code != 200:
        message = {
            401: "Hosting service authentication failed.",
            403: "Hosting service access denied.",
            429: "Hosting service rate limit reached.",
        }.get(
            response.status_code,
            f"Hosting service returned HTTP {response.status_code}.",
        )

        result["errors"].append(message)
        return result

    try:
        data = response.json()
    except ValueError:
        result["errors"].append(
            "Hosting service returned invalid JSON."
        )
        return result

    if not isinstance(data, dict):
        result["errors"].append(
            "Hosting response must be an object."
        )
        return result

    if data.get("error") or data.get("error_code"):
        result["errors"].append(
            "Hosting service reported an error."
        )
        return result

    try:
        returned_ip = ipaddress.ip_address(data.get("ip"))
    except (ValueError, TypeError):
        returned_ip = None

    if returned_ip != address:
        result["errors"].append(
            "Hosting response contains a missing or mismatched IP."
        )
        return result

    flag = data.get("is_datacenter")

    if type(flag) is not bool:
        result["errors"].append(
            "Hosting classification is unavailable."
        )
        return result

    result["hosting"] = "Yes" if flag else "No"
    result["source"] = "ipapi.is"

    return result


def main(argv=None):
    """Run the combined privacy and hosting diagnostic."""
    parser = argparse.ArgumentParser(
        description=(
            "Check VPN, proxy, Tor, relay, and hosting "
            "indicators for a public IP."
        )
    )

    parser.add_argument(
        "--target",
        help=(
            "Public IPv4/IPv6 address; defaults to your "
            "detected public IP."
        ),
    )

    args = parser.parse_args(argv)
    target = args.target

    if target is None:
        from ip_core import get_public_ip_info

        try:
            info = get_public_ip_info()

            for field in ("ipv4", "ipv6"):
                candidate = info.get(field)

                try:
                    address = ipaddress.ip_address(candidate)
                except (ValueError, TypeError):
                    continue

                if (
                    isinstance(candidate, str)
                    and "%" not in candidate
                    and address.is_global
                    and not address.is_multicast
                ):
                    target = str(address)
                    break

        except Exception:
            print("Unable to retrieve a public IP address.")
            return 1

    result = check_privacy(target)
    result["hosting_source"] = None

    try:
        address = ipaddress.ip_address(result["ip"])
        valid_target = (
            address.is_global
            and not address.is_multicast
            and "%" not in result["ip"]
        )
    except (ValueError, TypeError):
        valid_target = False

    if valid_target:
        hosting = check_hosting(result["ip"])

        result["hosting"] = hosting["hosting"]
        result["hosting_source"] = hosting["source"]
        result["errors"].extend(hosting["errors"])

        fields = ("vpn", "proxy", "tor", "relay", "hosting")

        verified = [result[field] != UNKNOWN for field in fields]
        if all(verified):
            result["status"] = "complete"
        elif any(verified):
            result["status"] = "partial"
        else:
            result["status"] = "unavailable"

    print(json.dumps(result, indent=2))

    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
