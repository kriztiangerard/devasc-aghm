# CLI QA Results

Tester: Angelique Rosen A. Cortez
Branch: feature/cli-output
Commit tested: 865b7b7
Environment: macOS, Python 3.14.7, pytest 9.2.0

## Automated Tests
Command: python -m pytest -v
Result: 12 passed in 0.81 seconds.
- 7 backend tests
- 5 CLI tests

## Live Online Test — PASS
- Displayed public IPv4, ISP, ASN, and location.
- IPv6 displayed "Not Detected".
- No traceback; exit status 0.

## Live Offline Test — PASS
Wi-Fi was confirmed Off before execution.
- IPv4 displayed "Unavailable".
- Metadata displayed "Unknown".
- Displayed a notice that no public IP was detected.
- No traceback; exit status 0.
- Wi-Fi was turned back on afterward.

## Minor UI Finding
Offline location displays "Unknown, Unknown, Unknown (Unknown)".
Suggested improvement: display "Unknown" once.

## Not Yet Verified
- Live IPv6-enabled connectivity
- GUI integration