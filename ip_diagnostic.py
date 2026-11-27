"""Command-line interface for the Public IP Diagnostic Utility.

This module retrieves network information through ip_core.py and presents
the results as a readable terminal report.

Responsibilities:
    - Request network information from the shared backend.
    - Format IPv4, IPv6, ISP, ASN, and location details.
    - Display fallback values when information is unavailable.
    - Report unexpected errors and return an appropriate exit status.

Supports self-diagnostics and arbitrary IPv4, IPv6, or hostname
lookups through human-readable text, JSON, and CSV output without
duplicating the backend's network retrieval logic.

Interactive target lookup sessions support repeated lookups
without restarting the application.
"""

import argparse
import csv
import io
import ipaddress
import json
import sys

from ip_core import UNKNOWN, get_public_ip_info, lookup_ip


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


def format_target_report(info):
    """Convert arbitrary target lookup results into readable text.

    Unlike the self-diagnostic report, this report displays the
    requested target and its resolved IP address.
    """
    resolved_ip = info.get("ip") or UNKNOWN

    try:
        version = f"IPv{ipaddress.ip_address(resolved_ip).version}"
    except ValueError:
        version = UNKNOWN

    location = ", ".join(
        str(info.get(key) or UNKNOWN)
        for key in ("city", "region", "country")
    )

    country_code = info.get("country_code") or UNKNOWN

    lines = [
        "=" * 60,
        "          TARGET IP & NETWORK LOOKUP (CLI)",
        "=" * 60,
        f"  Target              : {info.get('target') or UNKNOWN}",
        f"  Resolved IP Address : {resolved_ip}",
        f"  IP Version          : {version}",
        f"  ISP / Organization  : {info.get('isp') or UNKNOWN}",
        f"  ASN                 : {info.get('asn') or UNKNOWN}",
        f"  Location            : {location} ({country_code})",
        "=" * 60,
    ]

    return "\n".join(lines)


def parse_args(argv=None):
    """Parse target lookup and mutually exclusive export arguments."""
    parser = argparse.ArgumentParser(
        description="Public IP & Network Diagnostic Utility"
    )

    parser.add_argument(
        "--target",
        metavar="IP_OR_HOSTNAME",
        help=(
            "Look up an arbitrary IPv4 address, IPv6 address, "
            "or hostname instead of your own public IP."
        ),
    )

    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Start an interactive target lookup session.",
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

    args = parser.parse_args(argv)

    # Interactive sessions produce multiple human-readable reports.
    # Keep them separate from single-result machine-readable exports.
    if args.interactive and (
        args.target is not None or args.json or args.csv
    ):
        parser.error(
            "--interactive cannot be combined with "
            "--target, --json, or --csv."
        )

    return args


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


def interactive_lookup():
    """Run repeated target lookups within one terminal session.

    Reuses the BL-07 backend and report formatter. Failed lookups
    do not terminate the session, allowing users to correct their
    input and try again.

    Returns:
        int: 0 when the interactive session ends normally.
    """
    print("\n=== INTERACTIVE TARGET LOOKUP ===")
    print("Enter an IPv4 address, IPv6 address, or hostname.")
    print("Type 'exit' or 'quit' to leave.\n")

    while True:
        try:
            target = input("Target: ").strip()

            if target.lower() in ("exit", "quit"):
                break

            if not target:
                print("Error: Target must not be empty.\n")
                continue

            print(f"Looking up target: {target!r}, please wait...\n")

            try:
                info = lookup_ip(target)
                print(format_target_report(info))

                if not info.get("ip") or info.get("ip") == UNKNOWN:
                    print("\nError: Target lookup failed.")

                    for error in info.get("errors", []):
                        print(f"  - {error}")
                else:
                    for error in info.get("errors", []):
                        print(f"Warning: {error}")

            except Exception as exc:
                print(f"Unable to complete target lookup: {exc}")

            print()

        except (EOFError, KeyboardInterrupt):
            print()
            break

    print("Interactive lookup ended.")
    return 0


def main(argv=()):
    """Run a self-diagnostic, target lookup, or interactive session.

    Args:
        argv: Command-line arguments. An empty sequence uses the
              original self-diagnostic mode.
              None reads arguments from the actual command line.

    Returns:
        int: 0 when the diagnostic completes; 1 when target
        validation, resolution, or an unexpected exception fails.

    Invalid command-line arguments are handled by argparse.
    Metadata failures do not invalidate an otherwise resolved IP.
    """
    args = parse_args(argv)

    if args.interactive:
        return interactive_lookup()

    export_mode = args.json or args.csv
    target_mode = args.target is not None

    # Keep machine-readable stdout free from diagnostic messages.
    message_stream = sys.stderr if export_mode else sys.stdout

    if target_mode:
        print(
            f"Looking up target: {args.target!r}, please wait...\n",
            file=message_stream,
        )
    else:
        print(
            "Gathering network information, please wait...\n",
            file=message_stream,
        )

    try:
        # Select the shared backend based on the requested mode.
        if target_mode:
            info = lookup_ip(args.target)
        else:
            info = get_public_ip_info()

        # Reuse the BL-03 serializers for both diagnostic modes.
        if args.json:
            print(format_json(info))
        elif args.csv:
            sys.stdout.write(format_csv(info))
        elif target_mode:
            print(format_target_report(info))
        else:
            print(format_report(info))

    except Exception as exc:
        print(
            f"Unable to complete network diagnostic: {exc}",
            file=message_stream,
        )
        return 1

    if target_mode:
        # Validation and DNS failures leave the resolved IP unknown.
        if not info.get("ip") or info.get("ip") == UNKNOWN:
            print(
                "\nError: Target lookup failed.",
                file=message_stream,
            )

            for error in info.get("errors", []):
                print(f"  - {error}", file=message_stream)

            return 1

        # A resolved IP remains useful even when metadata is incomplete.
        for error in info.get("errors", []):
            print(f"Warning: {error}", file=message_stream)

        return 0

    # Preserve the original self-diagnostic offline behavior.
    if info.get("ipv4") == "Unavailable" and info.get("ipv6") == "Not Detected":
        print(
            "\nNotice: No public IP address could be detected.",
            file=message_stream,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
