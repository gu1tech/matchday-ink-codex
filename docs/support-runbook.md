# Support runbook

Use this guide to isolate a fault before changing configuration or reflashing firmware. This is a single-user LAN application; there is no production SLA.

## Establish impact

Ask what changed, when the problem began, whether the browser preview is current, and whether the physical display changed. Separate the match data, AI explanation, network connection and physical panel. Record timestamps with timezone. A retained e-paper image is expected when power or connectivity is lost.

Never request an API key, Wi-Fi password, complete private settings file or unredacted serial dump in a public issue.

## 1. Check server readiness

Run on the server computer:

```sh
curl --fail --silent --show-error http://127.0.0.1:8765/health
```

Expected: a JSON response with `ready: true`. This only means a snapshot exists; it does not prove upstream freshness or a physical display update. If unavailable, check the process, listening port and service error log. Do not start a second server on an occupied port.

## 2. Check data and rendered output

Open `/v1/dashboard` and `/preview.png` on the same server. Compare fixture identity, kickoff, provenance timestamps, `stale` state and lifecycle state. Do not equate `generated_at` with a newly verified provider response.

A match retained after kickoff may be correct: the service waits for confirmed completion and a five-minute buffer. If status is unavailable, keeping the current match is safer than guessing a result.

Check the frame without dumping its binary content:

```sh
curl --fail --silent --show-error http://127.0.0.1:8765/v1/frame.bin -o /tmp/matchday-check-frame.bin
wc -c < /tmp/matchday-check-frame.bin
```

Expected: 9472 bytes. Correct length alone does not prove correct pixels or driver behaviour.

## 3. Isolate network versus device

If localhost works but the device cannot download, check Mac sleep, LAN address changes, firewall rules and whether both devices share an accessible network. The ESP32 requires 2.4 GHz Wi-Fi. A localhost address cannot be used by the device to reach the Mac.

Inspect status through the loopback setup page. When USB diagnostics are connected, compare received and drawn frame hashes. A new received hash with an old drawn hash places the failure after download. Identical hashes can legitimately skip a refresh. Respect the three-minute physical-refresh guard. Visual confirmation remains the final check.

## 4. Isolate optional AI

A fixture can display correctly while AI is unavailable. Inspect the local AI status rather than repeatedly saving settings or retrying paid calls.

| Observed class | Investigation | Action |
| --- | --- | --- |
| Authentication error | Key revoked, wrong credential, configuration not saved | Replace privately; never ask for the value in an issue |
| Permission/model error | Account/project access to configured model | Verify model selection and permissions |
| Rate-limit/quota error | Distinguish a transient rate limit from exhausted credits using safe provider code | Check billing/limits; respect cooldown |
| Timeout/connection error | Host connectivity and service availability | Keep core display working; retry after cooldown |
| Structured-output rejection | Returned content fails local size/ASCII/schema checks | Reproduce with a mocked response; do not render unchecked output |
| Insufficient history | Fewer than three verified completed games per team | Show unavailable; do not manufacture probabilities |

These are diagnostic categories; the current UI groups some failures into generic messages. Successful calls retain response ID and token usage. Failed calls currently retain a safe class/provider code but not a request ID or latency. That observability gap is a follow-up, not an implemented capability.

## Escalation record

Include:

- Component versions, board/display variant and operating system.
- Impact, start time, recent changes and expected versus observed behaviour.
- Smallest reproduction, with synthetic data where possible.
- Endpoint status, relevant redacted timestamps and safe error class/code.
- Which boundaries were checked and the outcome of each check.
- Workaround, proposed fix and exact verification still needed.

Do not attach API keys, authorization headers, Wi-Fi credentials, private network scans or complete provider request bodies. Review even locally generated diagnostics before sharing.

## Customer-facing update example

The following is an illustrative communication template, not a historical customer ticket:

> The fixture preview is available, but the physical display has not yet shown the new frame. We are checking the refresh stage separately from the download. Please leave the device powered on; there is no need to re-enter your API key. We will confirm recovery by checking both the frame status and the screen itself.

After a fix, verify the original symptom and a relevant failure path, then update the runbook or test that could prevent recurrence. Avoid declaring resolution from an HTTP success alone.
