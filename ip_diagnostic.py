"""Command-line interface for the Public IP Diagnostic Utility."""

from ip_core import get_public_ip_info


def format_report(info):
    """Format network information into a readable terminal report."""
    location = ", ".join(
        str(info.get(key) or "Unknown")
        for key in ("city", "region", "country")
    )
    country_code = info.get("country_code") or "Unknown"

    lines = [
        "=" * 60,
        "       PUBLIC IP & NETWORK DIAGNOSTIC UTILITY (CLI)",
        "=" * 60,
        f"  Public IPv4 Address : {info.get('ipv4') or 'Unavailable'}",
        f"  Public IPv6 Address : {info.get('ipv6') or 'Not Detected'}",
        f"  ISP / Organization  : {info.get('isp') or 'Unknown'}",
        f"  ASN                 : {info.get('asn') or 'Unknown'}",
        f"  Location            : {location} ({country_code})",
        "=" * 60,
    ]

    return "\n".join(lines)


def main():
    """Run the network diagnostic and display its results."""
    print("Gathering network information, please wait...\n")

    try:
        info = get_public_ip_info()
    except Exception as exc:
        print(f"Unable to complete network diagnostic: {exc}")
        return 1

    print(format_report(info))

    if info.get("ipv4") == "Unavailable" and info.get("ipv6") == "Not Detected":
        print("\nNotice: No public IP address could be detected.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
