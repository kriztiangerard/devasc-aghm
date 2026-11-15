"""
ip_diagnostic_gui.py
Public IP Diagnostic Tool - Desktop GUI (Project Activity 3, Blueprint B)

Shows the machine's public IPv4 / IPv6 address plus ISP, ASN and
geolocation metadata in a small tkinter window.

Design notes
- All networking lives in ip_core.py (Member 1); this file only displays it.
  Keep ip_core.py in the same folder. `requests` is needed by ip_core.
- All network calls run in a background thread so the UI never freezes.
- Worker threads never touch widgets or Tk; they put results on a queue
  that the main thread polls with `after()` (the thread-safe pattern).
- Addressing layer : ipify  (handled inside ip_core)
- Enrichment layer : ipapi.co (handled inside ip_core)
"""

import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk
from tkinter import font as tkfont

from ip_core import get_public_ip_info

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
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
class IPDiagnosticApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Public IP Diagnostic Tool")
        self.geometry("520x480")
        self.resizable(False, False)

        self.style = ttk.Style(self)
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")

        self.font_family = self._pick_font()
        self.last_updated = None
        self._closing = False
        self._results = queue.Queue()

        self.configure_styles()
        self.create_widgets()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll_results)
        self.refresh_data()

    # ---- setup ------------------------------------------------------------
    def _pick_font(self):
        """Segoe UI on Windows; fall back to a font that exists elsewhere."""
        available = set(tkfont.families())
        for name in ("Segoe UI", "Helvetica Neue", "Ubuntu", "DejaVu Sans", "Arial"):
            if name in available:
                return name
        return "TkDefaultFont"

    def configure_styles(self):
        f, c = self.font_family, COLORS
        self.configure(background=c["bg"])
        self.style.configure("TFrame", background=c["bg"])
        self.style.configure("Header.TLabel", font=(f, 14, "bold"),
                             background=c["bg"], foreground=c["title"])
        self.style.configure("SubHeader.TLabel", font=(f, 9),
                             background=c["bg"], foreground=c["muted"])
        self.style.configure("Card.TFrame", background=c["card"], relief="solid",
                             borderwidth=1, bordercolor=c["border"])
        self.style.configure("FieldLabel.TLabel", font=(f, 9, "bold"),
                             background=c["card"], foreground=c["label"])
        self.style.configure("FieldValue.TLabel", font=(f, 10),
                             background=c["card"], foreground=c["value"])
        self.style.configure("Action.TButton", font=(f, 9, "bold"), padding=6)
        self.style.configure("Status.TLabel", font=(f, 9),
                             background=c["bg"], foreground=c["muted"])

    def create_widgets(self):
        # Header
        header = ttk.Frame(self, padding=(20, 15, 20, 10))
        header.pack(fill="x")
        ttk.Label(header, text="Network Interface Diagnostic",
                  style="Header.TLabel").pack(anchor="w")
        ttk.Label(header, text="Real-time Public IPv4/IPv6 Addressing & Metadata",
                  style="SubHeader.TLabel").pack(anchor="w")

        # Data card
        card = ttk.Frame(self, style="Card.TFrame", padding=15)
        card.pack(fill="both", expand=True, padx=20, pady=10)
        card.columnconfigure(1, weight=1)

        self.fields = {}
        for row, (label_text, key) in enumerate(FIELD_DEFINITIONS):
            ttk.Label(card, text=label_text, style="FieldLabel.TLabel").grid(
                row=row, column=0, sticky="nw", pady=6, padx=(5, 10))
            value = ttk.Label(card, text="Fetching...", style="FieldValue.TLabel",
                              wraplength=320, justify="left")
            value.grid(row=row, column=1, sticky="w", pady=6)
            self.fields[key] = value

        # Buttons
        buttons = ttk.Frame(self, padding=(20, 10, 20, 5))
        buttons.pack(fill="x")
        self.refresh_btn = ttk.Button(buttons, text="Refresh Data",
                                      style="Action.TButton", command=self.refresh_data)
        self.refresh_btn.pack(side="left", padx=(0, 10))
        self.copy_btn = ttk.Button(buttons, text="Copy Report",
                                   style="Action.TButton", command=self.copy_report)
        self.copy_btn.pack(side="left")

        # Status bar
        self.status_label = ttk.Label(self, text="Ready", style="Status.TLabel",
                                      padding=(20, 0, 20, 12))
        self.status_label.pack(anchor="w", fill="x")

    # ---- actions ----------------------------------------------------------
    def refresh_data(self):
        """Start a background fetch; ignored if one is already running."""
        if str(self.refresh_btn.cget("state")) == "disabled":
            return
        self.refresh_btn.config(state="disabled")
        self.copy_btn.config(state="disabled")
        self._set_status("Querying network endpoints...", COLORS["muted"])
        for label in self.fields.values():
            label.config(text="Fetching...")
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        """Runs off the main thread. Must not touch any widget."""
        try:
            data, warnings = fetch_network_data()
        except Exception as exc:  # last-resort guard so the UI never stays locked
            data = {key: "Error" for _, key in FIELD_DEFINITIONS}
            warnings = [f"Unexpected error: {exc}"]
        self._results.put((data, warnings))

    def _poll_results(self):
        """Main-thread timer: pick up finished worker results."""
        if self._closing:
            return
        try:
            data, warnings = self._results.get_nowait()
        except queue.Empty:
            pass
        else:
            self._update_ui(data, warnings)
        self.after(100, self._poll_results)

    def _update_ui(self, data, warnings):
        for key, label in self.fields.items():
            label.config(text=data.get(key, "Unknown"))
        self.refresh_btn.config(state="normal")
        self.copy_btn.config(state="normal")
        self.last_updated = datetime.now()
        stamp = self.last_updated.strftime("%H:%M:%S")
        if warnings:
            self._set_status(f"Updated {stamp} with issues: " + "; ".join(warnings),
                             COLORS["warn"])
        else:
            self._set_status(f"Data updated successfully at {stamp}.", COLORS["ok"])

    def build_report(self):
        stamp = (self.last_updated or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
        value = lambda key: self.fields[key].cget("text")
        return (
            "=== PUBLIC IP DIAGNOSTIC REPORT ===\n"
            f"Generated    : {stamp}\n"
            f"IPv4 Address : {value('ipv4')}\n"
            f"IPv6 Address : {value('ipv6')}\n"
            f"ISP / Org    : {value('isp')}\n"
            f"ASN          : {value('asn')}\n"
            f"Location     : {value('location')}\n"
            f"Country Code : {value('country_code')}\n"
        )

    def copy_report(self):
        self.clipboard_clear()
        self.clipboard_append(self.build_report())
        self.update()  # keep clipboard contents after the window closes (X11)
        messagebox.showinfo("Copied", "Diagnostic report copied to clipboard!")

    # ---- helpers ----------------------------------------------------------
    def _set_status(self, text, color):
        self.status_label.config(text=text, foreground=color)

    def _on_close(self):
        self._closing = True
        self.destroy()


if __name__ == "__main__":
    app = IPDiagnosticApp()
    app.mainloop()