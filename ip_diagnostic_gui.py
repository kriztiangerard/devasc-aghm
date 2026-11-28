"""Desktop interface for the Public IP Diagnostic Utility.

Supports self-diagnostics and arbitrary IPv4, IPv6, and hostname
lookups through the shared networking backend, using a modern
CustomTkinter card-based UI with Light/Dark mode and loading animations.

Network requests execute in background workers. GUI widgets
are updated exclusively by the main GUI thread.
"""

import ipaddress
import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

import customtkinter as ctk
from exporter import build_export_payload, export_csv, export_json, export_pdf
from ip_core import UNKNOWN, get_public_ip_info, lookup_ip
from map_panel import GeolocationMapCard

# --------------------------------------------------------------------------
# Configuration & Palettes
# --------------------------------------------------------------------------
WINDOW_WIDTH = 980
MIN_HEIGHT = 600
STATUS_WRAP = WINDOW_WIDTH - 40

# Original Activity 3 Light palette (preserved for regression compatibility)
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

DARK_COLORS = {
    "bg": "#181C20",
    "card": "#23282E",
    "border": "#343B44",
    "title": "#F0F4F8",
    "muted": "#9AA5B1",
    "label": "#7CC4FA",
    "value": "#E4E7EB",
    "ok": "#4ADE80",
    "warn": "#FBBF24",
    "error": "#F87171",
}

FIELD_DEFINITIONS = [
    ("Public IPv4:", "ipv4"),
    ("Public IPv6:", "ipv6"),
    ("ISP / Org:", "isp"),
    ("ASN:", "asn"),
    ("Location:", "location"),
    ("Country Code:", "country_code"),
]

TARGET_FIELD_DEFINITIONS = [
    ("Target", "target"),
    ("Resolved IP", "ip"),
    ("IP Version", "version"),
    ("ISP / Organization", "isp"),
    ("ASN", "asn"),
    ("Location", "location"),
    ("Country Code", "country_code"),
]


# --------------------------------------------------------------------------
# CustomTkinter Compatibility Wrappers (supports .config() & .configure())
# --------------------------------------------------------------------------
class _CompatCTkLabel(ctk.CTkLabel):
    def config(self, **kwargs):
        return self.configure(**kwargs)


class _CompatCTkButton(ctk.CTkButton):
    def config(self, **kwargs):
        return self.configure(**kwargs)


class _CompatCTkEntry(ctk.CTkEntry):
    def config(self, **kwargs):
        return self.configure(**kwargs)


def _palette_for(app):
    return DARK_COLORS if getattr(app, "_theme_mode", "light") == "dark" else COLORS


# --------------------------------------------------------------------------
# Adapters: ip_core result dicts -> GUI display dicts
# --------------------------------------------------------------------------
def fetch_network_data():
    """Call ip_core.get_public_ip_info() and reshape the result for the UI."""
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


def fetch_target_data(target):
    """Adapt the shared BL-07 lookup result for the desktop interface."""
    info = lookup_ip(target)
    resolved_ip = info.get("ip") or UNKNOWN

    try:
        version = f"IPv{ipaddress.ip_address(resolved_ip).version}"
    except ValueError:
        version = UNKNOWN

    place = [info.get(key) for key in ("city", "region", "country")]
    place = [str(value) for value in place if value and value != UNKNOWN]

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
            warnings.append("Unavailable metadata: " + ", ".join(missing))

    return data, warnings, failed


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------
class IPDiagnosticApp(ctk.CTk):
    """Modern desktop application supporting self and target lookup modes."""

    def __init__(self):
        ctk.set_appearance_mode("Light")
        ctk.set_default_color_theme("green")
        super().__init__()

        self.title("IP Network Diagnostic Utility")
        self.geometry(f"{WINDOW_WIDTH}x{MIN_HEIGHT}")
        self.minsize(860, 580)
        self.resizable(True, True)

        self.font_family = self._pick_font()
        self._theme_mode = "light"
        self._last_status_kind = "muted"
        self.last_updated = None
        self._closing = False
        self._busy = False
        self._mode = "self"
        self._warnings = []
        self._failed = False
        self._results = queue.Queue()
        self._poll_id = None

        self.create_widgets()
        self._apply_theme_colors()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll_id = self.after(100, self._poll_results)

        self.refresh_data()

    def _pick_font(self):
        available = set(tkfont.families())
        for name in ("Segoe UI", "Helvetica Neue", "Ubuntu", "DejaVu Sans", "Arial"):
            if name in available:
                return name
        return "TkDefaultFont"

    def create_widgets(self):
        """Build the CustomTkinter card layout, dark mode toggle, and loading bar."""
        # Header with Dark Mode switch
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(16, 6))

        header_top = ctk.CTkFrame(header, fg_color="transparent")
        header_top.pack(fill="x")

        title_col = ctk.CTkFrame(header_top, fg_color="transparent")
        title_col.pack(side="left", fill="x", expand=True)

        self.title_label = ctk.CTkLabel(
            title_col,
            text="Public IP & Network Diagnostic",
            font=ctk.CTkFont(family=self.font_family, size=19, weight="bold"),
            anchor="w",
        )
        self.title_label.pack(fill="x")

        self.subtitle_label = ctk.CTkLabel(
            title_col,
            text="Look up your network or an arbitrary target",
            font=ctk.CTkFont(family=self.font_family, size=11),
            anchor="w",
        )
        self.subtitle_label.pack(fill="x")

        self.theme_switch = ctk.CTkSwitch(
            header_top,
            text="Dark Mode",
            font=ctk.CTkFont(family=self.font_family, size=11, weight="bold"),
            command=self.toggle_theme,
        )
        self.theme_switch.pack(side="right", padx=(12, 0))

        # Smooth indeterminate loading bar
        self.progress_bar = ctk.CTkProgressBar(self, mode="indeterminate", height=5)
        self.progress_bar.pack(fill="x", padx=24, pady=(6, 4))
        self.progress_bar.set(1)

        # Search controls
        search = ctk.CTkFrame(self, fg_color="transparent")
        search.pack(fill="x", padx=24, pady=(4, 6))
        search.columnconfigure(0, weight=1)

        self.target_var = tk.StringVar()

        self.target_entry = _CompatCTkEntry(
            search,
            textvariable=self.target_var,
            placeholder_text="Enter an IPv4 address, IPv6 address, or hostname",
            font=ctk.CTkFont(family=self.font_family, size=12),
            height=36,
        )
        self.target_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.target_entry.bind("<Return>", self._on_search_enter)

        self.search_btn = _CompatCTkButton(
            search,
            text="Search",
            font=ctk.CTkFont(family=self.font_family, size=12, weight="bold"),
            width=100,
            height=36,
            command=self.search_target,
        )
        self.search_btn.grid(row=0, column=1, sticky="ew")

        # Reserve footer space before allocating the main content area
        self.status_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.status_frame.pack(side="bottom", fill="x", padx=24, pady=(4, 12))

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

        self.status_text.configure(yscrollcommand=self._update_status_scrollbar)
        self.status_text.pack(side="left", fill="both", expand=True)
        self.status_text.tag_configure("status", justify="center")
        self._set_status("Ready", COLORS["muted"])

        # Action buttons
        self.buttons_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.buttons_frame.pack(side="bottom", fill="x", padx=24, pady=(6, 4))
        self.buttons_frame.columnconfigure(0, weight=1)
        self.buttons_frame.columnconfigure(1, weight=1)
        self.buttons_frame.columnconfigure(2, weight=1)

        self.refresh_btn = _CompatCTkButton(
            self.buttons_frame,
            text="My Public IP",
            font=ctk.CTkFont(family=self.font_family, size=12, weight="bold"),
            height=36,
            command=self.refresh_data,
        )
        self.refresh_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.copy_btn = _CompatCTkButton(
            self.buttons_frame,
            text="Copy Report",
            font=ctk.CTkFont(family=self.font_family, size=12, weight="bold"),
            height=36,
            command=self.copy_report,
        )
        self.copy_btn.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.export_btn = _CompatCTkButton(
            self.buttons_frame,
            text="Export...",
            font=ctk.CTkFont(family=self.font_family, size=12, weight="bold"),
            height=36,
            command=self.open_export_dialog,
        )
        self.export_btn.grid(row=0, column=2, sticky="ew", padx=(6, 0))

        # Main content container (Card area)
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=24, pady=6)

        self.card = ctk.CTkFrame(
            self.content_frame,
            corner_radius=12,
            border_width=1,
        )
        self.card.pack(side="left", fill="both", expand=True)

        self.map_card = GeolocationMapCard(
            self.content_frame,
            font_family=self.font_family,
        )
        self.map_card.pack(side="right", fill="both", expand=True, padx=(14, 0))

        self.fields = {}
        self._render_fields("self")

        self.bind("<Configure>", self._on_resize)

    def toggle_theme(self):
        """Switch between Light and Dark appearance modes."""
        self._theme_mode = "dark" if self.theme_switch.get() == 1 else "light"
        ctk.set_appearance_mode("Dark" if self._theme_mode == "dark" else "Light")
        self._apply_theme_colors()

    def _apply_theme_colors(self):
        c = _palette_for(self)
        self.configure(fg_color=c["bg"])
        self.title_label.configure(text_color=c["title"])
        self.subtitle_label.configure(text_color=c["muted"])
        self.card.configure(fg_color=c["card"], border_color=c["border"])
        self.status_text.configure(
            background=c["bg"],
            foreground=c.get(self._last_status_kind, c["muted"]),
        )
        self._recolor_card_children()
        if getattr(self, "map_card", None) is not None:
            self.map_card.apply_palette(c)

    def _recolor_card_children(self):
        c = _palette_for(self)
        if hasattr(self, "_card_heading_label"):
            self._card_heading_label.configure(text_color=c["title"])
        if hasattr(self, "_card_separator"):
            self._card_separator.configure(fg_color=c["border"])
        for lbl in getattr(self, "_field_name_labels", []):
            lbl.configure(text_color=c["label"])
        for lbl in self.fields.values():
            lbl.configure(text_color=c["value"])

    def _update_status_scrollbar(self, first, last):
        """Show the status scrollbar only when text overflows."""
        self.status_scrollbar.set(first, last)
        needs_scroll = float(first) > 0.0 or float(last) < 1.0
        is_visible = self.status_scrollbar.winfo_manager() == "pack"

        if needs_scroll and not is_visible:
            self.status_scrollbar.pack(side="right", fill="y", before=self.status_text)
        elif not needs_scroll and is_visible:
            self.status_scrollbar.pack_forget()

    def _on_resize(self, event):
        """Keep field values wrapped within the available width."""
        if event.widget is not self:
            return
        for label in self.fields.values():
            label.config(wraplength=max(180, event.width - 280))

    def _render_fields(self, mode):
        """Display fields appropriate to the selected lookup mode."""
        for child in self.card.winfo_children():
            child.destroy()

        self.fields = {}
        self._field_name_labels = []
        self._mode = mode
        c = _palette_for(self)

        definitions = TARGET_FIELD_DEFINITIONS if mode == "target" else FIELD_DEFINITIONS
        heading = "Target lookup results" if mode == "target" else "Your network details"

        self.card.columnconfigure(0, weight=0)
        self.card.columnconfigure(1, weight=1)
        self.card.columnconfigure(2, weight=0)

        self._card_heading_label = ctk.CTkLabel(
            self.card,
            text=heading,
            font=ctk.CTkFont(family=self.font_family, size=14, weight="bold"),
            text_color=c["title"],
            anchor="w",
        )
        self._card_heading_label.grid(
            row=0, column=0, columnspan=3, sticky="w", padx=16, pady=(14, 6)
        )

        self._card_separator = ctk.CTkFrame(self.card, height=1, fg_color=c["border"])
        self._card_separator.grid(
            row=1, column=0, columnspan=3, sticky="ew", padx=16, pady=(0, 8)
        )

        for row, (label_text, key) in enumerate(definitions, start=2):
            name_lbl = ctk.CTkLabel(
                self.card,
                text=label_text.rstrip(":"),
                font=ctk.CTkFont(family=self.font_family, size=12, weight="bold"),
                text_color=c["label"],
                anchor="w",
            )
            name_lbl.grid(row=row, column=0, sticky="nw", pady=5, padx=(16, 14))
            self._field_name_labels.append(name_lbl)

            value = _CompatCTkLabel(
                self.card,
                text=UNKNOWN,
                font=ctk.CTkFont(family="Consolas", size=12),
                text_color=c["value"],
                wraplength=max(180, self.winfo_width() - 280),
                justify="right",
                anchor="e",
            )
            value.grid(row=row, column=1, sticky="ne", pady=5, padx=(0, 8))

            copy_btn = _CompatCTkButton(
                self.card,
                text="Copy",
                width=56,
                height=24,
                font=ctk.CTkFont(family=self.font_family, size=10, weight="bold"),
                fg_color=("gray82", "gray26"),
                text_color=("gray10", "gray90"),
                hover_color=("gray72", "gray36"),
            )
            copy_btn.configure(
                command=lambda k=key, b=copy_btn: self.copy_single_field(k, b)
            )
            copy_btn.grid(row=row, column=2, sticky="e", pady=4, padx=(0, 14))
            self.fields[key] = value

    def _on_search_enter(self, event):
        self.search_target()
        return "break"

    def search_target(self):
        if self._busy or self._closing:
            return

        target = self.target_var.get().strip()
        if not target:
            self._last_status_kind = "error"
            self._set_status("Target must not be empty.", _palette_for(self)["error"])
            self.target_entry.focus_set()
            return

        self._start_request("target", target)

    def refresh_data(self):
        if self._busy or self._closing:
            return
        self.target_var.set("")
        self._start_request("self")

    def _set_busy(self, busy):
        self._busy = busy
        state = "disabled" if busy else "normal"
        for widget in (
            self.target_entry,
            self.search_btn,
            self.refresh_btn,
            self.copy_btn,
        ):
            widget.config(state=state)
        if getattr(self, "export_btn", None) is not None:
            self.export_btn.config(state=state)

    def _start_request(self, mode, target=None):
        if self._busy or self._closing:
            return

        self._set_busy(True)
        self._render_fields(mode)

        self.last_updated = None
        self._warnings = []
        self._failed = False

        if getattr(self, "progress_bar", None) is not None:
            self.progress_bar.start()

        for key, label in self.fields.items():
            label.config(text=target if key == "target" else "Fetching...")

        message = (
            f"Looking up {target}..."
            if mode == "target"
            else "Querying network endpoints..."
        )
        self._last_status_kind = "muted"
        self._set_status(message, _palette_for(self)["muted"])

        try:
            threading.Thread(
                target=self._worker,
                args=(mode, target),
                daemon=True,
            ).start()
        except Exception as exc:
            self._update_ui({}, [f"Unable to start request: {exc}"], True)

    def _worker(self, mode, target=None):
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
                    warnings = ["No public IP address could be detected."]
        except Exception as exc:
            definitions = (
                TARGET_FIELD_DEFINITIONS if mode == "target" else FIELD_DEFINITIONS
            )
            data = {key: UNKNOWN for _, key in definitions}
            if mode == "target":
                data["target"] = target or UNKNOWN
            warnings = [f"Unexpected error: {exc}"]
            failed = True

        self._results.put((data, warnings, failed))

    def _poll_results(self):
        if self._closing:
            return

        try:
            data, warnings, failed = self._results.get_nowait()
        except queue.Empty:
            pass
        else:
            self._update_ui(data, warnings, failed)

        if not self._closing:
            self._poll_id = self.after(100, self._poll_results)

    def _update_ui(self, data, warnings, failed=False):
        for key, label in self.fields.items():
            label.config(text=data.get(key) or UNKNOWN)

        self._warnings = list(warnings)
        self._failed = failed
        self.last_updated = datetime.now()

        if getattr(self, "progress_bar", None) is not None:
            self.progress_bar.stop()
            self.progress_bar.set(1)

        self._set_busy(False)

        if getattr(self, "map_card", None) is not None:
            active_ip = (
                data.get("ip")
                if self._mode == "target"
                else (
                    data.get("ipv4")
                    if data.get("ipv4") not in (None, "Unavailable", UNKNOWN)
                    else data.get("ipv6")
                )
            )
            self.map_card.update_from_result(
                active_ip,
                data.get("location"),
                failed=failed,
            )

        stamp = self.last_updated.strftime("%H:%M:%S")
        palette = _palette_for(self)

        if failed:
            heading = (
                "Target lookup failed"
                if self._mode == "target"
                else "Network diagnostic failed"
            )
            details = "; ".join(warnings) or "No result available."
            self._last_status_kind = "error"
            self._set_status(f"{heading}: {details}", palette["error"])
        elif warnings:
            self._last_status_kind = "warn"
            self._set_status(
                f"Updated {stamp} with warnings: " + "; ".join(warnings),
                palette["warn"],
            )
        else:
            message = (
                "Target lookup completed successfully"
                if self._mode == "target"
                else "Network details updated successfully"
            )
            self._last_status_kind = "ok"
            self._set_status(f"{message} at {stamp}.", palette["ok"])

    def build_report(self):
        stamp = (self.last_updated or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")

        if self._mode == "target":
            title = "=== TARGET IP DIAGNOSTIC REPORT ==="
            definitions = TARGET_FIELD_DEFINITIONS
        else:
            title = "=== PUBLIC IP DIAGNOSTIC REPORT ==="
            definitions = FIELD_DEFINITIONS

        lines = [title, f"Generated: {stamp}"]
        for label_text, key in definitions:
            value = self.fields[key].cget("text")
            lines.append(f"{label_text.rstrip(':')}: {value}")

        if self._failed:
            lines.append("Status: Failed")
        if self._warnings:
            lines.append("Warnings / Errors:")
            lines.extend(f"- {warning}" for warning in self._warnings)

        return "\n".join(lines) + "\n"

    def copy_single_field(self, key, btn):
        if self._busy or self._closing:
            return
        try:
            value = self.fields[key].cget("text")
            self.clipboard_clear()
            self.clipboard_append(value)
            self.update_idletasks()
            self._last_status_kind = "ok"
            self._set_status(
                f"Copied {key.replace('_', ' ').upper()} to clipboard.",
                _palette_for(self)["ok"],
            )
            btn.configure(text="Copied!")
            self.after(
                1200,
                lambda: btn.configure(text="Copy") if btn.winfo_exists() else None,
            )
        except tk.TclError as exc:
            self._last_status_kind = "error"
            self._set_status(
                f"Unable to copy field: {exc}", _palette_for(self)["error"]
            )

    def copy_report(self):
        if self._busy or self._closing:
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(self.build_report())
            self.update_idletasks()
            messagebox.showinfo("Copied", "Diagnostic report copied to clipboard!")
        except tk.TclError as exc:
            self._last_status_kind = "error"
            self._set_status(
                f"Unable to copy report: {exc}", _palette_for(self)["error"]
            )

    def open_export_dialog(self):
        if self._busy or self._closing:
            return

        definitions = (
            TARGET_FIELD_DEFINITIONS if self._mode == "target" else FIELD_DEFINITIONS
        )
        fields_data = {
            label_text.rstrip(":"): self.fields[key].cget("text")
            for label_text, key in definitions
        }
        payload = build_export_payload(
            mode=self._mode,
            fields_data=fields_data,
            timestamp=self.last_updated,
            warnings=self._warnings,
            failed=self._failed,
        )

        filepath = filedialog.asksaveasfilename(
            title="Export Diagnostic Report",
            defaultextension=".pdf",
            filetypes=[
                ("PDF Report", "*.pdf"),
                ("JSON File", "*.json"),
                ("CSV Spreadsheet", "*.csv"),
            ],
        )
        if not filepath:
            return

        try:
            lower = filepath.lower()
            if lower.endswith(".json"):
                export_json(payload, filepath)
            elif lower.endswith(".csv"):
                export_csv(payload, filepath)
            else:
                export_pdf(payload, filepath)
            self._last_status_kind = "ok"
            self._set_status(
                f"Report exported to {filepath}", _palette_for(self)["ok"]
            )
        except OSError as exc:
            messagebox.showerror("Export Failed", f"Could not save report:\n{exc}")

    def _set_status(self, text, color):
        self.status_text.configure(state="normal", foreground=color)
        self.status_text.delete("1.0", "end")
        self.status_text.insert("1.0", text, "status")
        self.status_text.configure(state="disabled")
        self.status_text.yview_moveto(0)
        self.after(50, self._refresh_status_scrollbar)

    def _refresh_status_scrollbar(self):
        if self._closing:
            return
        self.status_text.update_idletasks()
        first, last = self.status_text.yview()
        self._update_status_scrollbar(first, last)

    def _on_close(self):
        self._closing = True
        if getattr(self, "_poll_id", None) is not None:
            try:
                self.after_cancel(self._poll_id)
            except tk.TclError:
                pass
        self.destroy()


if __name__ == "__main__":
    app = IPDiagnosticApp()
    app.mainloop()