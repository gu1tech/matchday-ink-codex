# Case study: download succeeded, display stayed unchanged

## Evidence and scope

This case is reconstructed from the project development conversation and code changes. It is a personal hardware incident, not an enterprise customer incident. No original timestamped support ticket or complete serial-log archive is included, so no resolution-time metric is claimed.

## Symptom and impact

The owner reported that the physical screen still showed the old `EST` and `Q: High` labels after the layout had changed. The backend preview and a software completion message were insufficient evidence that the panel had updated. The device remained readable, but showed the wrong interface version.

## Investigation

The investigation separated server rendering, frame download, refresh scheduling and physical display control. It also accounted for unchanged-frame suppression and the three-minute refresh guard.

The working explanation was that treating BUSY as idle could report completion without proving the panel had entered its refresh cycle. This was a driver/control-path hypothesis, not a measured electrical root cause: no logic-analyser trace was captured.

## Changes

- Added separate received-frame and drawn-frame hashes to distinguish download from draw state.
- Added a force-redraw command, still respecting the refresh guard.
- Changed the driver to require BUSY assertion after the refresh command, followed by completion, with bounded waits.

These changes improve evidence and failure detection; they do not make a software status message equivalent to optical verification.

## Verification and outcome

The owner explicitly confirmed that the new layout appeared after the corrective work. This established recovery on that assembled device. Native helper tests and firmware compilation provide additional software checks but do not reproduce the electrical fault or replace the owner's physical observation.

## Lesson

Success must be defined at the user's boundary. A successful download and a completion log are intermediate signals; the acceptance criterion was the correct image on the physical screen. Future diagnostic work should retain redacted timestamps and correlate each stage so the evidence is easier to audit.
