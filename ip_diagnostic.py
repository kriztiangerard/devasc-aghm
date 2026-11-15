"""Command-line interface for the Public IP Diagnostic Utility.

This module retrieves network information through ip_core.py and presents
the results as a readable terminal report.

Responsibilities:
    - Request network information from the shared backend.
    - Format IPv4, IPv6, ISP, ASN, and location details.
    - Display fallback values when information is unavailable.
    - Report unexpected errors and return an appropriate exit status.

Future CLI features, such as JSON and CSV output, can be added here
without duplicating the backend's network retrieval logic.
"""

from ip_core import get_public_ip_info


def format_report(info):
    """Convert backend network information into a readable text report.

    Args:
        info (dict): Network information returned by
            ip_core.get_public_ip_info(). Expected keys include
            ipv4, ipv6, isp, asn, city, region, country,
            and country_code.

    Returns:
        str: A formatted report containing the network details.

    Missing or empty values use readable fallback labels:
    "Unavailable" for IPv4, "Not Detected" for IPv6,
    and "Unknown" for other network information.
    """
    # Combine location fields while replacing missing values with "Unknown".
    location = ", ".join(
        str(info.get(key) or "Unknown")
        for key in ("city", "region", "country")
    )
    country_code = info.get("country_code") or "Unknown"

    # Keep terminal formatting separate from backend API retrieval.
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
    """Retrieve network information and display the CLI report.

    Calls the shared backend, formats the returned dictionary,
    and displays a notice if both public IP addresses are unavailable.

    Returns:
        int: 0 when the diagnostic completes, including when no public
        IP is detected; 1 if an unexpected backend exception occurs.

    Future command-line argument parsing can be added here.
    """
    print("Gathering network information, please wait...\n")

    # Reuse the backend instead of making API requests in the CLI.
    try:
        info = get_public_ip_info()
    except Exception as exc:
        print(f"Unable to complete network diagnostic: {exc}")
        return 1

    print(format_report(info))

    # Inform the user when the backend could not detect either IP address.
    if info.get("ipv4") == "Unavailable" and info.get("ipv6") == "Not Detected":
        print("\nNotice: No public IP address could be detected.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
