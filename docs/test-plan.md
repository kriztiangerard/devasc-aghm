# QA Test Plan – IPv4/IPv6 Diagnostic Application

Prepared by: Angelique Rosen A. Cortez
Role: Member 4 – Scrum Leader / Security, Monitoring & QA Lead

## Objective
Verify that the CLI and GUI display public IP information
and handle unavailable connections without crashing.

## Test Cases

| ID | Scenario | Expected Result | Actual Result | Status |
|---|---|---|---|---|
| QA-01 | Run with IPv4 connectivity | Displays a valid public IPv4 address. | — | Not Executed |
| QA-02 | Run with IPv6 connectivity | Displays a valid public IPv6 address. | — | Not Executed |
| QA-03 | Run without IPv6 connectivity | Shows an IPv6 unavailable message and continues working. | — | Not Executed |
| QA-04 | Run without internet | Displays clear failure messages without crashing. | — | Not Executed |
| QA-05 | Refresh GUI results | Updates the results and re-enables the Refresh button. | — | Not Executed |
| QA-06 | Move the GUI during retrieval | Window remains responsive. | — | Not Executed |
| QA-07 | Copy the diagnostic report | Copied text matches the displayed results. | — | Not Executed |
| QA-08 | Metadata API fails | Available IP addresses remain visible; unavailable metadata is indicated. | — | Not Executed |

## Execution Notes
Record actual results only after running the application.
Attach screenshots or issue links when available.
Mark tests Blocked if the required network environment is unavailable.