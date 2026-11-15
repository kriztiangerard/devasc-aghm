# GUI QA Results

Tester: Angelique Rosen A. Cortez
Branch tested: feature/frontend
Commit tested: 30893f0
Environment: macOS
Test method: Manual live testing

| Test | Result | Observation |
|---|---|---|
| Online data display | PASS | IPv4, ISP, ASN, location, and country code displayed. |
| Refresh | PASS | Results returned and status timestamp updated. |
| Window responsiveness | PASS | Window remained movable during loading. |
| Button disabling | PASS | Refresh and Copy were disabled during loading and re-enabled afterward. |
| Copy Report | PASS | Pasted report matched displayed values and included a timestamp. |
| Offline handling | PASS | Unavailable/Unknown values and an amber warning displayed without crashing. |
| Connection recovery | PASS | After reconnecting and refreshing, data returned with a green success status. |

## UI Issue — Open
Severity: Minor
The offline warning text is clipped at the right edge.
Expected: The full warning is readable through wrapping or a details view.

## Not Yet Verified
- Live IPv6-enabled connectivity
- GUI behavior during an API rate-limit response
- Final integration on main