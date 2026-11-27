"""BL-06: Continuous public IP monitoring.

Run:
    python ip_monitor.py
    python ip_monitor.py --interval 60

Uses the shared backend without modifying the CLI or GUI.
"""

import argparse
import ipaddress
import logging
import math
from threading import Event

from ip_core import get_public_ip_info


LOGGER = logging.getLogger("ip_monitor")


class IPMonitor:
    """Track the last valid address for each IP version.

    Failed lookups do not erase the baseline or trigger change alerts.
    on_change receives: (field, previous_address, current_address).
    """

    def __init__(self, fetch=None, on_change=None):
        self.fetch = fetch if fetch is not None else get_public_ip_info
        self.on_change = on_change
        self.last_valid = {}

    @staticmethod
    def _valid_address(value, version):
        if not isinstance(value, str):
            return None

        try:
            address = ipaddress.ip_address(value.strip())
        except ValueError:
            return None

        return str(address) if address.version == version else None

    def check_once(self):
        """Perform one lookup and return detected change events."""
        try:
            info = self.fetch()
            if not isinstance(info, dict):
                raise ValueError("Backend result must be a dictionary")
        except Exception as exc:
            LOGGER.warning("Lookup failed; baseline retained: %s", exc)
            return []

        changes = []

        for field, version in (("ipv4", 4), ("ipv6", 6)):
            current = self._valid_address(info.get(field), version)

            if current is None:
                LOGGER.info("%s unavailable; baseline retained", field)
                continue

            previous = self.last_valid.get(field)
            self.last_valid[field] = current

            if previous is None:
                LOGGER.info("%s baseline: %s", field, current)
            elif previous != current:
                change = {
                    "field": field,
                    "previous": previous,
                    "current": current,
                }
                changes.append(change)

                LOGGER.warning(
                    "%s changed: %s -> %s", field, previous, current
                )

                if self.on_change is not None:
                    try:
                        self.on_change(field, previous, current)
                    except Exception:
                        LOGGER.exception("IP-change callback failed")
            else:
                LOGGER.info("%s unchanged: %s", field, current)

        return changes

    def run(self, interval=60, stop_event=None):
        """Check immediately, then wait between completed lookups.

        A stop event interrupts the wait. An active backend request
        finishes according to the backend's timeout behavior.
        """
        if not math.isfinite(interval) or interval <= 0:
            raise ValueError("Interval must be a positive finite number")

        stop_event = stop_event if stop_event is not None else Event()

        while not stop_event.is_set():
            self.check_once()
            if stop_event.wait(interval):
                break


def positive_interval(value):
    try:
        interval = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "Interval must be a number"
        ) from None

    if not math.isfinite(interval) or interval <= 0:
        raise argparse.ArgumentTypeError(
            "Interval must be a positive finite number"
        )

    return interval


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Monitor public IP addresses and log changes."
    )
    parser.add_argument(
        "--interval",
        type=positive_interval,
        default=60,
        help="Seconds to wait between completed checks (default: 60).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    LOGGER.info(
        "Monitoring started; interval=%s seconds. Ctrl+C to stop.",
        args.interval,
    )

    try:
        IPMonitor().run(interval=args.interval)
    except KeyboardInterrupt:
        LOGGER.info("Monitoring stopped.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())