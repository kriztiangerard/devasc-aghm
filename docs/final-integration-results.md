# Final Integration QA Results

Tester: Angelique Rosen A. Cortez
Date: November 15, 2026
Version tested: main, commit 172079c
Environment: macOS, Python 3.14.7, pytest 9.2.0

## Results

| Check | Result |
|---|---|
| Automated backend and CLI tests | PASS — 12 passed in 0.87 seconds |
| Live CLI output | PASS — available network information displayed |
| CLI exit status | PASS — 0 |
| GUI startup and online display | PASS |
| GUI refresh | PASS — results and timestamp updated |
| Copy Report | PASS — pasted report matched displayed data |

## Known Open Findings
- CLI offline location repeats "Unknown" — usability suggestion.
- GUI offline warning is clipped — minor UI defect.

## Limitations
- Live IPv6-enabled connectivity remains unverified.
- Offline and recovery checks passed on the earlier feature commits;
  they were not repeated during this final main smoke test.
- GUI rate-limit behavior was not manually verified.

## Conclusion
All executed checks passed. Known findings remain open.