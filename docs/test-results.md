# Core Module QA Results

Tester: Angelique Rosen A. Cortez
Branch tested: feature/core-api
Commit tested: 11132af
Environment: macOS, Python 3.14.7, pytest 9.2.0
Command: python -m pytest -v

## Results

- Dual-stack success: PASS
- Missing IPv6 handling: PASS
- Offline handling: PASS
- Timeout handling: PASS
- IPv4 provider failover: PASS
- Metadata HTTP 429 fallback: PASS
- Incorrect IP version rejection: PASS
- NAT detection unit test: PASS
- Unresolvable hostname handling: PASS

Total: 9 passed in 0.70 seconds.

## Scope
HTTP requests were mocked. Actual network connectivity,
IPv6-only operation, and CLI/GUI integration remain untested.

## Live Network Test

Command: python ip_core.py

- Public IPv4 retrieval: PASS
- ISP, ASN, and location retrieval: PASS
- PTR retrieval: PASS
- IPv6 connection failure handling: PASS — displayed "Not Detected"
  and returned results without crashing.
- NAT status returned: Behind NAT (private LAN address)

Sources: ipify for IPv4; ipapi.co for metadata.

IPv6 connectivity was not verified.
CLI and GUI integration remain untested.
Public IP and PTR values are omitted from this report.