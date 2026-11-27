"""BL-11: Tray controls, GUI hide/restore, and notifications."""

import argparse
import logging
from pathlib import Path
import subprocess
import sys
import threading

import pystray
from PIL import Image, ImageDraw

from ip_monitor import IPMonitor, positive_interval


LOGGER = logging.getLogger("ip_tray")


def create_icon():
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.line((32, 18, 32, 42), fill="black", width=5)
    draw.line((12, 42, 52, 42), fill="black", width=5)

    for x, y in ((32, 14), (12, 46), (52, 46)):
        draw.rectangle(
            (x - 7, y - 7, x + 7, y + 7),
            fill="black",
        )
    return image


class TrayMonitor:
    def __init__(self, interval=60):
        self.interval = interval
        self.stop_event = threading.Event()
        self.worker = None
        self.closing = False
        self.gui_process = None

        self.icon = pystray.Icon(
            "ip_diagnostic",
            create_icon(),
            "IP Diagnostic Utility",
            menu=pystray.Menu(
                pystray.MenuItem(
                    self.status_text,
                    lambda icon, item: None,
                    enabled=False,
                ),
                pystray.MenuItem("Show Window", self.show_window),
                pystray.MenuItem("Hide Window", self.hide_window),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "Start Monitoring",
                    self.start,
                    enabled=lambda item: (
                        not self.closing and not self.is_running()
                    ),
                ),
                pystray.MenuItem(
                    "Stop Monitoring",
                    self.stop,
                    enabled=lambda item: (
                        self.is_running()
                        and not self.stop_event.is_set()
                    ),
                ),
                pystray.MenuItem(
                    "Test Notification", self.test_notification
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", self.exit),
            ),
        )

    def is_running(self):
        return self.worker is not None and self.worker.is_alive()

    def status_text(self, item):
        if self.is_running():
            if self.stop_event.is_set():
                return "Monitoring: stopping..."
            return "Monitoring: running"
        return "Monitoring: stopped"

    def _send_gui(self, command):
        """Send a command to the child GUI through its input pipe."""
        process = self.gui_process
        if process is None or process.poll() is not None:
            return False

        try:
            process.stdin.write(command + "\n")
            process.stdin.flush()
            return True
        except (BrokenPipeError, OSError, ValueError):
            LOGGER.exception("Unable to send GUI command")
            return False

    def show_window(self, icon=None, item=None):
        if self.closing:
            return

        if (
            self.gui_process is not None
            and self.gui_process.poll() is None
        ):
            self._send_gui("show")
            return

        if self.gui_process is not None:
            if self.gui_process.stdin is not None:
                self.gui_process.stdin.close()

        host = Path(__file__).resolve().with_name("ip_gui_host.py")

        try:
            self.gui_process = subprocess.Popen(
                [sys.executable, str(host)],
                stdin=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            LOGGER.info("GUI process started")
        except OSError:
            LOGGER.exception("Unable to launch GUI")

    def hide_window(self, icon=None, item=None):
        self._send_gui("hide")

    def notify(self, title, message):
        try:
            if sys.platform == "darwin":
                script = (
                    "on run argv\n"
                    "display notification (item 2 of argv) "
                    "with title (item 1 of argv)\n"
                    "end run\n"
                )
                subprocess.run(
                    ["osascript", "-", title, message],
                    input=script,
                    text=True,
                    capture_output=True,
                    check=True,
                    timeout=10,
                )
            elif self.icon.HAS_NOTIFICATION:
                self.icon.notify(message, title)
            else:
                LOGGER.warning("Desktop notifications unsupported")
        except (OSError, subprocess.SubprocessError):
            LOGGER.exception("Unable to deliver notification")

    def on_change(self, field, previous, current):
        if self.closing or self.stop_event.is_set():
            return
        self.notify(
            "Public IP changed",
            f"{field.upper()}: {previous} → {current}",
        )

    def monitor_loop(self):
        try:
            IPMonitor(on_change=self.on_change).run(
                interval=self.interval,
                stop_event=self.stop_event,
            )
        except Exception:
            LOGGER.exception("Monitoring stopped unexpectedly")
        finally:
            LOGGER.info("Monitoring worker finished")

    def start(self, icon=None, item=None):
        if self.closing or self.is_running():
            return

        self.stop_event.clear()
        self.worker = threading.Thread(
            target=self.monitor_loop,
            name="ip-monitor",
            daemon=True,
        )
        self.worker.start()
        self.icon.update_menu()
        LOGGER.info("Monitoring started")

    def stop(self, icon=None, item=None):
        self.stop_event.set()
        self.icon.update_menu()
        LOGGER.info(
            "Stop requested; any active lookup will finish first"
        )

        if self.worker is not None:
            threading.Thread(
                target=self._refresh_after_stop,
                args=(self.worker,),
                daemon=True,
            ).start()

    def _refresh_after_stop(self, worker):
        worker.join()
        if not self.closing:
            self.icon.update_menu()

    def test_notification(self, icon=None, item=None):
        if not self.closing:
            threading.Thread(
                target=self.notify,
                args=(
                    "IP Diagnostic Utility",
                    "Test notification — no IP change was simulated.",
                ),
                daemon=True,
            ).start()

    def exit(self, icon=None, item=None):
        self.closing = True
        self.stop_event.set()
        self._send_gui("quit")
        self.icon.stop()

    def _cleanup_gui(self):
        process = self.gui_process
        if process is None:
            return

        try:
            self._send_gui("quit")
            if process.stdin is not None:
                process.stdin.close()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            LOGGER.warning("GUI did not exit; terminating child")
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        except (OSError, ValueError):
            LOGGER.exception("GUI cleanup failed")

    def run(self):
        try:
            self.icon.run()
        finally:
            self.closing = True
            self.stop_event.set()
            self._cleanup_gui()
            if self.worker is not None:
                self.worker.join(timeout=1)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Public IP monitoring from the system tray."
    )
    parser.add_argument(
        "--interval",
        type=positive_interval,
        default=60,
        help="Seconds between completed checks (default: 60).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    TrayMonitor(interval=args.interval).run()


if __name__ == "__main__":
    main()