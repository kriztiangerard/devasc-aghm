"""Command-line interface for the Public IP Diagnostic Utility.

This module retrieves network information through ip_core.py and presents
the results as a readable terminal report.

Responsibilities:
    - Request network information from the shared backend.
    - Format IPv4, IPv6, ISP, ASN, and location details.
    - Display fallback values when information is unavailable.
    - Report unexpected errors and return an appropriate exit status.

Supports human-readable text, JSON, and CSV output without
duplicating the backend's network retrieval logic.
"""

import argparse
import csv
import io
import json
import sys

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


def parse_args(argv=None):
    """Parse CLI arguments and enforce mutually exclusive export formats."""
    parser = argparse.ArgumentParser(
        description="Public IP & Network Diagnostic Utility"
    )

    formats = parser.add_mutually_exclusive_group()

    formats.add_argument(
        "--json",
        action="store_true",
        help="Output diagnostic results as JSON.",
    )

    formats.add_argument(
        "--csv",
        action="store_true",
        help="Output diagnostic results as CSV.",
    )

    return parser.parse_args(argv)


def format_json(info):
    """Serialize the complete backend result as valid JSON."""
    return json.dumps(info, indent=2, ensure_ascii=False)


def format_csv(info):
    """Serialize diagnostic data as CSV with a header and one data row.

    Nested dictionaries and lists are JSON-encoded to preserve their
    contents within individual CSV cells.
    """
    output = io.StringIO(newline="")

    row = {
        key: json.dumps(value, ensure_ascii=False)
        if isinstance(value, (dict, list))
        else value
        for key, value in info.items()
    }

    writer = csv.DictWriter(
        output,
        fieldnames=list(info.keys()),
        lineterminator="\n",
    )

    writer.writeheader()
    writer.writerow(row)

    return output.getvalue()


def main(argv=()):
    """Retrieve network information and display the selected output format.

    Args:
        argv: Command-line arguments. An empty sequence uses text mode.
              None reads arguments from the actual command line.

    Returns:
        int: 0 when the diagnostic completes, including when no public
        IP is detected; 1 if an unexpected exception occurs.

    Invalid command-line arguments are handled by argparse.
    """
    args = parse_args(argv)
    export_mode = args.json or args.csv

    # Keep machine-readable stdout free from progress and error messages.
    message_stream = sys.stderr if export_mode else sys.stdout

    print(
        "Gathering network information, please wait...\n",
        file=message_stream,
    )

    try:
        # Reuse the shared backend for every output format.
        info = get_public_ip_info()

        if args.json:
            print(format_json(info))
        elif args.csv:
            sys.stdout.write(format_csv(info))
        else:
            print(format_report(info))

    except Exception as exc:
        print(
            f"Unable to complete network diagnostic: {exc}",
            file=message_stream,
        )
        return 1

    # Keep offline notices separate from machine-readable output.
    if info.get("ipv4") == "Unavailable" and info.get("ipv6") == "Not Detected":
        print(
            "\nNotice: No public IP address could be detected.",
            file=message_stream,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
