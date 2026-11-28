"""Desktop interface for the Public IP Diagnostic Utility.

Supports self-diagnostics and arbitrary IPv4, IPv6 and hostname
lookups through the shared networking backend.

Network requests execute in background workers. Tkinter widgets
are updated exclusively by the main GUI thread.
"""

import ipaddress
import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk
from tkinter import font as tkfont

from ip_core import UNKNOWN, get_public_ip_info, lookup_ip

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
WINDOW_WIDTH = 520
MIN_HEIGHT = 480
STATUS_WRAP = WINDOW_WIDTH - 40  # window width minus 20 px padding on each side

COLORS = {
    "bg": "#F4F6F8",
    "card": "#FFFFFF",
    "border": "#D5DCE3",
    "title": "#1A2530",
    "muted": "#5A6B7C",
    "label": "#3A5A7C",
    "value": "#2A3439",
    "ok": "#1E7B3A",
    "warn": "#B26A00",
    "error": "#B3261E",
}

# (label shown in the UI, key in the data dict)
FIELD_DEFINITIONS = [
    ("Public IPv4:", "ipv4"),
    ("Public IPv6:", "ipv6"),
    ("ISP / Org:", "isp"),
    ("ASN:", "asn"),
    ("Location:", "location"),
    ("Country Code:", "country_code"),
]


# --------------------------------------------------------------------------
# Adapter: ip_core result dict -> what the window shows
# --------------------------------------------------------------------------
def fetch_network_data():
    """
    Call ip_core.get_public_ip_info() and reshape the result for the UI.

    Returns (data, warnings):
      data     - dict with one string per key in FIELD_DEFINITIONS
      warnings - short strings worth showing to the user

    ip_core puts every failure in info["errors"], including the harmless
    "no IPv6 route" case on IPv4-only networks. As ip_core's notes advise,
    those are not shown as a banner: only IPv4 and metadata failures are.
    """
    info = get_public_ip_info()

    place = [info["city"], info["region"], info["country"]]
    place = [p for p in place if p and p != "Unknown"]

    data = {
        "ipv4": info["ipv4"],
        "ipv6": info["ipv6"],
        "isp": info["isp"],
        "asn": info["asn"],
        "location": ", ".join(place) or "Unknown",
        "country_code": info["country_code"],
    }

    warnings = [
        err for err in info.get("errors", [])
        if err.startswith("IPv4") or err.startswith("metadata")
    ]
    return data, warnings


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------


TARGET_FIELD_DEFINITIONS = [
    ("Target", "target"),
    ("Resolved IP", "ip"),
    ("IP Version", "version"),
    ("ISP / Organization", "isp"),
    ("ASN", "asn"),
    ("Location", "location"),
    ("Country Code", "country_code"),
]


def fetch_target_data(target):
    """Adapt the shared BL-07 lookup result for the desktop interface.

    Returns:
        tuple: (display data, warnings, failed)

    A resolved IP with unavailable metadata is treated as a
    partial result rather than a failed target lookup.
    """
    info = lookup_ip(target)
    resolved_ip = info.get("ip") or UNKNOWN

    try:
        version = f"IPv{ipaddress.ip_address(resolved_ip).version}"
    except ValueError:
        version = UNKNOWN

    place = [
        info.get(key)
        for key in ("city", "region", "country")
    ]
    place = [str(value) for value in place
             if value and value != UNKNOWN]

    data = {
        "target": info.get("target") or target or UNKNOWN,
        "ip": resolved_ip,
        "version": version,
        "isp": info.get("isp") or UNKNOWN,
        "asn": info.get("asn") or UNKNOWN,
        "location": ", ".join(place) or UNKNOWN,
        "country_code": info.get("country_code") or UNKNOWN,
    }

    warnings = list(info.get("errors") or [])
    failed = resolved_ip == UNKNOWN

    if failed and not warnings:
        warnings.append("Target could not be resolved.")

    if not failed:
        missing = [
            key for key in ("isp", "asn", "location", "country_code")
            if data[key] == UNKNOWN
        ]

        if missing:
            warnings.append(
                "Unavailable metadata: " + ", ".join(missing)
            )

    return data, warnings, failed


class IPDiagnosticApp(tk.Tk):
    """Desktop application supporting self and target lookup modes."""

    def __init__(self):
        super().__init__()

        self.title("IP Network Diagnostic Utility")
        self.geometry("620x600")
        self.minsize(580, 580)
        self.resizable(True, True)

        self.style = ttk.Style(self)

        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")

        self.font_family = self._pick_font()
        self.last_updated = None
        self._closing = False
        self._busy = False
        self._mode = "self"
        self._warnings = []
        self._failed = False
        self._results = queue.Queue()

        self.configure_styles()
        self.create_widgets()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll_results)

        # Preserve the original startup self-diagnostic behavior.
        self.refresh_data()

    def _pick_font(self):
        """Select an available cross-platform font."""
        available = set(tkfont.families())

        for name in (
            "Segoe UI",
            "Helvetica Neue",
            "Ubuntu",
            "DejaVu Sans",
            "Arial",
        ):
            if name in available:
                return name

        return "TkDefaultFont"

    def configure_styles(self):
        """Apply the existing Activity 3 color palette."""
        f, c = self.font_family, COLORS

        self.configure(background=c["bg"])

        self.style.configure(
            "TFrame",
            background=c["bg"],
        )
        self.style.configure(
            "Header.TLabel",
            font=(f, 17, "bold"),
            background=c["bg"],
            foreground=c["title"],
        )
        self.style.configure(
            "SubHeader.TLabel",
            font=(f, 10),
            background=c["bg"],
            foreground=c["muted"],
        )
        self.style.configure(
            "Card.TFrame",
            background=c["card"],
            relief="solid",
            borderwidth=1,
            bordercolor=c["border"],
        )
        self.style.configure(
            "CardTitle.TLabel",
            font=(f, 12, "bold"),
            background=c["card"],
            foreground=c["title"],
        )
        self.style.configure(
            "FieldLabel.TLabel",
            font=(f, 10, "bold"),
            background=c["card"],
            foreground=c["label"],
        )
        self.style.configure(
            "FieldValue.TLabel",
            font=(f, 10),
            background=c["card"],
            foreground=c["value"],
        )
        self.style.configure(
            "Search.TEntry",
            padding=8,
            fieldbackground=c["card"],
            foreground=c["value"],
        )
        self.style.configure(
            "Action.TButton",
            font=(f, 10, "bold"),
            padding=8,
        )
        self.style.configure(
            "Status.TLabel",
            font=(f, 9),
            background=c["bg"],
            foreground=c["muted"],
        )

    def create_widgets(self):
        """Build the BL-09 search and results layout."""
        header = ttk.Frame(self, padding=(24, 14, 24, 6))
        header.pack(fill="x")

        ttk.Label(
            header,
            text="Public IP & Network Diagnostic",
            style="Header.TLabel",
            anchor="center",
        ).pack(fill="x")

        ttk.Label(
            header,
            text="Look up your network or an arbitrary target",
            style="SubHeader.TLabel",
            anchor="center",
        ).pack(fill="x", pady=(5, 0))

        # Search controls.
        search = ttk.Frame(self, padding=(24, 4, 24, 4))
        search.pack(fill="x")
        search.columnconfigure(0, weight=1)

        self.target_var = tk.StringVar()

        self.target_entry = ttk.Entry(
            search,
            textvariable=self.target_var,
            style="Search.TEntry",
            font=(self.font_family, 11),
        )
        self.target_entry.grid(
            row=0, column=0, sticky="ew", padx=(0, 8)
        )
        self.target_entry.bind("<Return>", self._on_search_enter)

        self.search_btn = ttk.Button(
            search,
            text="Search",
            style="Action.TButton",
            command=self.search_target,
        )
        self.search_btn.grid(row=0, column=1, sticky="ew")

        ttk.Label(
            search,
            text="Enter an IPv4 address, IPv6 address, or hostname.",
            style="SubHeader.TLabel",
        ).grid(
            row=1, column=0, columnspan=2,
            sticky="w", pady=(5, 0)
        )

        # Allocate results space after reserving the footer.
        self.card = ttk.Frame(
            self,
            style="Card.TFrame",
            padding=12,
        )

        self.fields = {}
        self._render_fields("self")

        # Preserve self-refresh and clipboard functionality.
        buttons = ttk.Frame(self, padding=(24, 5, 24, 5))
        # Packed after the status area to preserve footer space.
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)

        self.refresh_btn = ttk.Button(
            buttons,
            text="My Public IP",
            style="Action.TButton",
            command=self.refresh_data,
        )
        self.refresh_btn.grid(
            row=0, column=0, sticky="ew", padx=(0, 5)
        )

        self.copy_btn = ttk.Button(
            buttons,
            text="Copy Report",
            style="Action.TButton",
            command=self.copy_report,
        )
        self.copy_btn.grid(
            row=0, column=1, sticky="ew", padx=(5, 0)
        )

        # Reserve footer space before allocating the results area.
        self.status_frame = ttk.Frame(
            self, padding=(24, 3, 24, 8)
        )
        self.status_frame.pack(side="bottom", fill="x")

        self.status_text = tk.Text(
            self.status_frame,
            height=3,
            width=1,
            wrap="word",
            font=(self.font_family, 9),
            background=COLORS["bg"],
            foreground=COLORS["muted"],
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=4,
            pady=3,
        )

        self.status_scrollbar = ttk.Scrollbar(
            self.status_frame,
            orient="vertical",
            command=self.status_text.yview,
        )

        self.status_text.configure(
            yscrollcommand=self._update_status_scrollbar
        )

        self.status_text.pack(
            side="left", fill="both", expand=True
        )

        self.status_text.tag_configure(
            "status", justify="center"
        )
        self._set_status("Ready", COLORS["muted"])

        buttons.pack(side="bottom", fill="x")

        # The results area receives the remaining window space.
        self.card.pack(
            fill="both", expand=True, padx=24, pady=6
        )

        self.bind("<Configure>", self._on_resize)

    def _update_status_scrollbar(self, first, last):
        """Show the status scrollbar only when text overflows."""
        self.status_scrollbar.set(first, last)

        needs_scroll = float(first) > 0.0 or float(last) < 1.0
        is_visible = self.status_scrollbar.winfo_manager() == "pack"

        if needs_scroll and not is_visible:
            self.status_scrollbar.pack(
                side="right",
                fill="y",
                before=self.status_text,
            )
        elif not needs_scroll and is_visible:
            self.status_scrollbar.pack_forget()

    def _on_resize(self, event):
        """Keep status and field values within the available width."""
        if event.widget is not self:
            return

        for label in self.fields.values():
            label.config(
                wraplength=max(180, event.width - 280)
            )

    def _render_fields(self, mode):
        """Display fields appropriate to the selected lookup mode."""
        for child in self.card.winfo_children():
            child.destroy()

        self.fields = {}
        self._mode = mode

        definitions = (
            TARGET_FIELD_DEFINITIONS
            if mode == "target"
            else FIELD_DEFINITIONS
        )

        heading = (
            "Target lookup results"
            if mode == "target"
            else "Your network details"
        )

        self.card.columnconfigure(0, weight=0)
        self.card.columnconfigure(1, weight=1)

        ttk.Label(
            self.card,
            text=heading,
            style="CardTitle.TLabel",
        ).grid(
            row=0, column=0, columnspan=2,
            sticky="w", pady=(0, 6)
        )

        ttk.Separator(
            self.card, orient="horizontal"
        ).grid(
            row=1, column=0, columnspan=2,
            sticky="ew", pady=(0, 4)
        )

        for row, (label_text, key) in enumerate(
            definitions, start=2
        ):
            ttk.Label(
                self.card,
                text=label_text.rstrip(":"),
                style="FieldLabel.TLabel",
            ).grid(
                row=row, column=0, sticky="nw",
                pady=4, padx=(0, 15)
            )

            value = ttk.Label(
                self.card,
                text=UNKNOWN,
                style="FieldValue.TLabel",
                wraplength=max(180, self.winfo_width() - 280),
                justify="right",
                anchor="e",
            )
            value.grid(
                row=row, column=1, sticky="ne", pady=4
            )

            self.fields[key] = value

    def _on_search_enter(self, event):
        """Submit a search using the Enter key."""
        self.search_target()
        return "break"

    def search_target(self):
        """Start a target lookup using the current search input."""
        if self._busy or self._closing:
            return

        target = self.target_var.get().strip()

        if not target:
            self._set_status(
                "Target must not be empty.",
                COLORS["error"],
            )
            self.target_entry.focus_set()
            return

        self._start_request("target", target)

    def refresh_data(self):
        """Return to self-diagnostic mode and refresh network data."""
        if self._busy or self._closing:
            return

        self.target_var.set("")
        self._start_request("self")

    def _set_busy(self, busy):
        """Prevent overlapping requests and copying unfinished results."""
        self._busy = busy
        state = "disabled" if busy else "normal"

        for widget in (
            self.target_entry,
            self.search_btn,
            self.refresh_btn,
            self.copy_btn,
        ):
            widget.config(state=state)

    def _start_request(self, mode, target=None):
        """Prepare the UI and launch a background request."""
        if self._busy or self._closing:
            return

        self._set_busy(True)
        self._render_fields(mode)

        self.last_updated = None
        self._warnings = []
        self._failed = False

        for key, label in self.fields.items():
            label.config(
                text=target if key == "target" else "Fetching..."
            )

        message = (
            f"Looking up {target}..."
            if mode == "target"
            else "Querying network endpoints..."
        )
        self._set_status(message, COLORS["muted"])

        try:
            threading.Thread(
                target=self._worker,
                args=(mode, target),
                daemon=True,
            ).start()
        except Exception as exc:
            self._update_ui(
                {},
                [f"Unable to start request: {exc}"],
                True,
            )

    def _worker(self, mode, target=None):
        """Run networking off the main thread without touching widgets."""
        try:
            if mode == "target":
                data, warnings, failed = fetch_target_data(target)
            else:
                data, warnings = fetch_network_data()

                failed = (
                    data.get("ipv4") == "Unavailable"
                    and data.get("ipv6") == "Not Detected"
                )

                if failed and not warnings:
                    warnings = [
                        "No public IP address could be detected."
                    ]

        except Exception as exc:
            definitions = (
                TARGET_FIELD_DEFINITIONS
                if mode == "target"
                else FIELD_DEFINITIONS
            )

            data = {
                key: UNKNOWN for _, key in definitions
            }

            if mode == "target":
                data["target"] = target or UNKNOWN

            warnings = [f"Unexpected error: {exc}"]
            failed = True

        self._results.put((data, warnings, failed))

    def _poll_results(self):
        """Apply completed worker results on the main GUI thread."""
        if self._closing:
            return

        try:
            data, warnings, failed = self._results.get_nowait()
        except queue.Empty:
            pass
        else:
            self._update_ui(data, warnings, failed)

        if not self._closing:
            self.after(100, self._poll_results)

    def _update_ui(self, data, warnings, failed=False):
        """Display results and restore controls after a request."""
        for key, label in self.fields.items():
            label.config(text=data.get(key) or UNKNOWN)

        self._warnings = list(warnings)
        self._failed = failed
        self.last_updated = datetime.now()

        self._set_busy(False)

        stamp = self.last_updated.strftime("%H:%M:%S")

        if failed:
            heading = (
                "Target lookup failed"
                if self._mode == "target"
                else "Network diagnostic failed"
            )
            details = "; ".join(warnings) or "No result available."

            self._set_status(
                f"{heading}: {details}",
                COLORS["error"],
            )

        elif warnings:
            self._set_status(
                f"Updated {stamp} with warnings: "
                + "; ".join(warnings),
                COLORS["warn"],
            )

        else:
            message = (
                "Target lookup completed successfully"
                if self._mode == "target"
                else "Network details updated successfully"
            )

            self._set_status(
                f"{message} at {stamp}.",
                COLORS["ok"],
            )

    def build_report(self):
        """Build a clipboard report from the currently displayed mode."""
        stamp = (
            self.last_updated or datetime.now()
        ).strftime("%Y-%m-%d %H:%M:%S")

        if self._mode == "target":
            title = "=== TARGET IP DIAGNOSTIC REPORT ==="
            definitions = TARGET_FIELD_DEFINITIONS
        else:
            title = "=== PUBLIC IP DIAGNOSTIC REPORT ==="
            definitions = FIELD_DEFINITIONS

        lines = [
            title,
            f"Generated: {stamp}",
        ]

        for label_text, key in definitions:
            value = self.fields[key].cget("text")
            lines.append(
                f"{label_text.rstrip(':')}: {value}"
            )

        if self._failed:
            lines.append("Status: Failed")

        if self._warnings:
            lines.append("Warnings / Errors:")
            lines.extend(
                f"- {warning}" for warning in self._warnings
            )

        return "\n".join(lines) + "\n"

    def copy_report(self):
        """Copy the current diagnostic report to the clipboard."""
        if self._busy or self._closing:
            return

        try:
            self.clipboard_clear()
            self.clipboard_append(self.build_report())
            self.update_idletasks()

            messagebox.showinfo(
                "Copied",
                "Diagnostic report copied to clipboard!",
            )
        except tk.TclError as exc:
            self._set_status(
                f"Unable to copy report: {exc}",
                COLORS["error"],
            )

    def _set_status(self, text, color):
        """Update the status message using the shared color palette."""
        self.status_text.configure(
            state="normal", foreground=color
        )
        self.status_text.delete("1.0", "end")
        self.status_text.insert("1.0", text, "status")
        self.status_text.configure(state="disabled")
        self.status_text.yview_moveto(0)
        self.after(50, self._refresh_status_scrollbar)

    def _refresh_status_scrollbar(self):
        """Recheck scrollbar visibility after text layout."""
        if self._closing:
            return

        self.status_text.update_idletasks()
        first, last = self.status_text.yview()
        self._update_status_scrollbar(first, last)

    def _on_close(self):
        """Close the window without waiting for daemon workers."""
        self._closing = True
        self.after_cancel(self._poll_id)
        self.destroy()


if __name__ == "__main__":
    app = IPDiagnosticApp()
    app.mainloop()
