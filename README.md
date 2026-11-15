# Public IP Diagnostic Tool

A small Python utility for technicians that shows the machine's current **public IPv4 and IPv6 addresses** together with network metadata: **ISP, ASN, location (city, region, country) and country code**.

It comes in two forms that share one networking core:

- a **command-line script** for terminals and SSH sessions
- a **desktop GUI** (tkinter) for quick use in the field

> Built for Project Activity 3: Social Coding & IP, in response to an engineering department request for a technician-facing diagnostic prototype.

---

## Features

- Detects public **IPv4** and **IPv6** separately, so dual-stack networks are reported correctly
- Shows **ISP / organization, ASN, city, region, country and country code**
- Desktop GUI with **Refresh Data** and **Copy Report** (timestamped text report for pasting into tickets)
- GUI stays responsive: lookups run in a background thread
- Handles failures without crashing: IPv4-only networks, rate limits, timeouts and offline machines
- No API keys and no UI framework dependencies (tkinter ships with Python)

## How it works

The app uses a hybrid, two-layer design:

| Layer | Service | Purpose |
|---|---|---|
| Addressing | [ipify](https://www.ipify.org/) (`api.ipify.org`, `api6.ipify.org`) | Explicit IPv4 and IPv6 address detection |
| Enrichment | [ipapi.co](https://ipapi.co/) | ISP, ASN and geolocation for the detected address |

All networking lives in `ip_core.py`. The CLI and the GUI both call `get_public_ip_info()` and only handle presentation, so they always show the same data.

```
ip_diagnostic.py  ─┐
                   ├──>  ip_core.get_public_ip_info()  ──>  ipify, ipapi.co
ip_diagnostic_gui.py ─┘
```

`get_public_ip_info()` never raises on network problems. It returns a dictionary with the keys `ipv4`, `ipv6`, `city`, `region`, `country`, `country_code`, `isp`, `asn` and `errors` (a list of readable failure messages). Failed lookups fall back to `Unavailable` (IPv4), `Not Detected` (IPv6) or `Unknown` (everything else).

> On an IPv4-only network the `errors` list will contain an IPv6 entry even though nothing is wrong, so front ends should not show `errors` as an error banner by default. The GUI shows only IPv4 and metadata failures.

## Repository structure

| File | Description |
|---|---|
| `ip_core.py` | Shared networking module (ipify + ipapi.co) |
| `ip_diagnostic.py` | Command-line interface |
| `ip_diagnostic_gui.py` | tkinter desktop application |
| `requirements.txt` | Python dependencies |

## Requirements

- Python 3.8 or newer
- [`requests`](https://pypi.org/project/requests/) (`requests>=2.31`)
- tkinter, for the GUI only. It is included with Python on Windows and macOS. On Debian/Ubuntu install it with:

  ```bash
  sudo apt install python3-tk
  ```

## Installation

```bash
git clone <repository-url>
cd <repository-folder>
pip install -r requirements.txt
```

## Usage

### Desktop GUI

```bash
python ip_diagnostic_gui.py
```

- **Refresh Data** runs the lookup again.
- **Copy Report** copies a timestamped text report to the clipboard.
- The status bar shows the update time, or what went wrong (warnings wrap so they can be read in full).

Example report:

```
=== PUBLIC IP DIAGNOSTIC REPORT ===
Generated    : 2026-11-15 10:42:07
IPv4 Address : 203.0.113.5
IPv6 Address : Not Detected
ISP / Org    : Example ISP
ASN          : AS64500
Location     : Dasmarinas, Calabarzon, Philippines
Country Code : PH
```

### Command line

```bash
python ip_diagnostic.py
```

### Use the core module in your own code

```python
from ip_core import get_public_ip_info

info = get_public_ip_info()
print(info["ipv4"], info["isp"], info["asn"])
```

Or print everything as JSON:

```bash
python ip_core.py
```

## Testing status

Tested so far with the network simulated (mocked `requests.get`) under a virtual display:

- normal lookup
- ipapi.co rate limit (HTTP 429)
- fully offline (all requests time out)
- GUI updates from the background thread, and long warning messages staying inside the window

**Still to do (QA checklist):** runs on real networks and on an IPv6-enabled connection, plus the IPv4-only and offline configurations on real hardware.

## Known limitations

- ipapi.co's free tier is rate-limited (about 1,000 requests per day), so heavy use can return HTTP 429. The metadata fields then show `Unknown`.
- `ip_core.py` makes its three requests one after another with a 5-second timeout each, so a fully offline refresh can take about 15 seconds. The GUI stays responsive meanwhile.
- No VPN, proxy or Tor detection yet.
- Status warnings use the core's technical wording (for example `HTTP 429`).

## Team and responsibilities

| Member | Role | Main deliverable |
|---|---|---|
| Member 1: [name] | Backend & Core Networking Lead | `ip_core.py` |
| Member 2: [name] | Frontend & Desktop UI Lead | `ip_diagnostic_gui.py` |
| Member 3: [name] | CLI, Automation & Diagnostics Engineer | `ip_diagnostic.py` |
| Member 4: [name] | Scrum Leader / Security, Monitoring & QA Lead | QA tests, `requirements.txt`, documentation |

## Contributing

- Do not commit directly to `main`. Work on a feature branch, for example `feature/core-api`, `feature/gui-tkinter`, `feature/cli-output` or `qa/tests-docs`.
- Open a pull request; at least one teammate must review it before it is merged.
- Write descriptive commit messages that say what changed and why.

## Roadmap (Project Activity 4 backlog)

| ID | Item |
|---|---|
| BL-01 | Local interface and NAT / CGNAT comparison |
| BL-02 | API failover and redundancy (ipify, ipapi.co, BigDataCloud, Cloudflare trace) |
| BL-03 | CLI flags and machine-readable export (`--json`, `--csv`) |
| BL-04 | VPN, proxy and Tor detection |
| BL-05 | Reverse DNS (PTR) and latency benchmarking |
| BL-06 | Continuous monitoring and IP change alerting |
| BL-07 | Arbitrary target IP / hostname lookup mode |
| BL-08 | Modern desktop UI and dark mode |
| BL-09 | Interactive target IP lookup and search bar in the GUI |
| BL-10 | Embedded geolocation map preview |
| BL-11 | System tray mode and IP change notifications |
| BL-12 | Per-field copy buttons and export dialog (PDF, JSON, CSV) |

## Acknowledgements

Public IP data is provided by [ipify](https://www.ipify.org/) and [ipapi.co](https://ipapi.co/). Please follow their terms of use and rate limits.

## License

[Add a license here, for example MIT, once the team has agreed on one.]