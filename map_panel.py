"""BL-10: Embedded OpenStreetMap geolocation preview card for the GUI."""

import ipaddress
import threading
from typing import Optional, Tuple

import customtkinter as ctk
import requests
import tkintermapview

TIMEOUT = 5
HEADERS = {"User-Agent": "ip-diagnostic/1.0"}


def _is_valid_public_ip(value: Optional[str]) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        addr = ipaddress.ip_address(value.strip())
        return addr.is_global and not addr.is_multicast
    except ValueError:
        return False


def fetch_coordinates(ip: Optional[str]) -> Tuple[Optional[float], Optional[float]]:
    """Resolve (latitude, longitude) for an IP using ipwho.is with ipapi.co fallback."""
    if not _is_valid_public_ip(ip):
        return None, None

    # Primary: ipwho.is
    try:
        resp = requests.get(f"https://ipwho.is/{ip}", headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success", True):
                lat, lon = data.get("latitude"), data.get("longitude")
                if lat is not None and lon is not None:
                    return float(lat), float(lon)
    except (requests.RequestException, ValueError, TypeError):
        pass

    # Fallback: ipapi.co
    try:
        resp = requests.get(
            f"https://ipapi.co/{ip}/json/", headers=HEADERS, timeout=TIMEOUT
        )
        if resp.status_code == 200:
            data = resp.json()
            if not data.get("error"):
                lat, lon = data.get("latitude"), data.get("longitude")
                if lat is not None and lon is not None:
                    return float(lat), float(lon)
    except (requests.RequestException, ValueError, TypeError):
        pass

    return None, None


class GeolocationMapCard(ctk.CTkFrame):
    """Card widget embedding an interactive OpenStreetMap preview."""

    def __init__(self, master, font_family="Segoe UI", **kwargs):
        super().__init__(master, corner_radius=12, border_width=1, **kwargs)

        self._request_seq = 0

        self.heading_label = ctk.CTkLabel(
            self,
            text="Geolocation Map Preview",
            font=ctk.CTkFont(family=font_family, size=14, weight="bold"),
            anchor="w",
        )
        self.heading_label.pack(fill="x", padx=16, pady=(14, 6))

        self.separator = ctk.CTkFrame(self, height=1)
        self.separator.pack(fill="x", padx=16, pady=(0, 10))

        self.map_widget = tkintermapview.TkinterMapView(
            self,
            width=360,
            height=290,
            corner_radius=10,
        )
        self.map_widget.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        self.map_widget.set_tile_server(
            "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png"
        )
        self.map_widget.set_position(14.5995, 120.9842)
        self.map_widget.set_zoom(4)

        self.coord_status = ctk.CTkLabel(
            self,
            text="Awaiting coordinates...",
            font=ctk.CTkFont(family=font_family, size=11),
            anchor="w",
        )
        self.coord_status.pack(fill="x", padx=16, pady=(0, 12))

    def apply_palette(self, palette: dict):
        self.configure(fg_color=palette["card"], border_color=palette["border"])
        self.heading_label.configure(text_color=palette["title"])
        self.separator.configure(fg_color=palette["border"])
        self.coord_status.configure(text_color=palette["muted"])

    def update_from_result(
        self,
        ip: Optional[str],
        location: Optional[str],
        failed: bool = False,
    ):
        """Resolve coordinates off the UI thread and pin the map."""
        self._request_seq += 1
        seq = self._request_seq
        self.map_widget.delete_all_marker()

        if failed or not _is_valid_public_ip(ip):
            self.coord_status.configure(text="Map preview unavailable for this lookup.")
            return

        self.coord_status.configure(text=f"Locating {ip}...")

        def _worker():
            lat, lon = fetch_coordinates(ip)
            try:
                self.after(0, self._apply_location, seq, lat, lon, location)
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_location(
        self,
        seq: int,
        lat: Optional[float],
        lon: Optional[float],
        location: Optional[str],
    ):
        if seq != self._request_seq:
            return

        self.map_widget.delete_all_marker()
        label_text = location if location and location != "Unknown" else "Detected IP"

        if lat is not None and lon is not None:
            self.map_widget.set_position(lat, lon)
            self.map_widget.set_zoom(11)
            self.map_widget.set_marker(lat, lon, text=label_text)
            self.coord_status.configure(
                text=f"Pinned: {label_text} ({lat:.4f}, {lon:.4f})"
            )
            return

        # Fallback: geocode by city/region/country string if coordinates failed
        if location and location != "Unknown":
            try:
                marker = self.map_widget.set_address(location, marker=True)
                if marker:
                    self.map_widget.set_zoom(10)
                    self.coord_status.configure(text=f"Pinned (approx.): {location}")
                    return
            except Exception:
                pass

        self.coord_status.configure(text="Coordinates unavailable for map preview.")