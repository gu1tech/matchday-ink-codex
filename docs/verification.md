# Review-copy verification

Prepared on 11 November 2026. These checks apply to this Desktop review copy, not the running device deployment.

| Check | Result |
| --- | --- |
| Python tests | 92 passed; no skips reported |
| Ruff: source, tests, scripts | Passed |
| Python wheel and source distribution | Built successfully |
| Non-editable package install outside checkout | Demo and rendering passed |
| Installed-package HTTP smoke | Health, dashboard, frame and renamed polling header passed |
| Output image and frame | 296 × 128; 9472-byte framebuffer |
| ESP32-C3 firmware build | Passed, esp32 core 3.3.12, CDCOnBoot=cdc |
| Firmware flash usage | 1,158,809 bytes (88%) |
| Firmware static RAM | 57,720 bytes (17%) |
| Candidate credential screening | No actual keys or personal LAN addresses found by targeted scan; synthetic test key retained |
| Git history | Not included in this clean export; original history was not audited or rewritten |
| GitHub CI | Defined, not run remotely |
| Renamed macOS LaunchAgents | Not installed or exercised |
| Fresh end-to-end device installation | Not performed on this candidate |
| Physical deployment | Existing installation left unchanged |

The code change beyond branding extracts atomic JSON persistence into `storage.py`, removing a core-to-AI dependency. Branding, Arduino sketch, helper symbols, HTTP headers, USB commands and settings namespace now use Matchday Ink. Existing devices require a paired firmware/server upgrade and Wi-Fi reprovisioning. Historical provider, weather and standalone commentary paths are retained, not silently deleted.

Images are labelled development previews. A real final-product photograph and final owner review remain desirable before publication. Current AI caching remains 24 hours; this export does not change that policy.

Final upload audit: removed Finder metadata, replaced the copied standings page with a hand-authored synthetic HTML fixture, and translated remaining example/fallback text into English. Local documentation links and embedded print-project metadata passed targeted checks.
