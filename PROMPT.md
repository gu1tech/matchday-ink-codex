# Build your own Matchday Ink

This is a reusable project brief written after development, not the original prompt or a verbatim development transcript. It captures the requirements and lessons from the project. Copy the prompt below into your coding assistant and adapt the hardware and operating system first.

A prompt alone cannot guarantee identical code, correct wiring, physical fit, current provider compatibility or predictive accuracy. Review generated changes and verify each stage. Never paste real credentials into the assistant.

## Recommended starting prompt

Copy this short prompt and attach this file as the technical brief. In an existing
checkout, also point the assistant to `README.md`, `src/matchday/`, `firmware/MatchdayInk/`
and `tests/`. In a new project, provide the hardware details below.

```text
Help me build Matchday Ink, a readable ESP32-C3 e-paper football companion.
I am a hobbyist learning AI-assisted engineering; explain important tradeoffs
so I can review and understand the work.

Use the attached technical brief and, if available, the existing repository.
The required first milestone is an offline, clearly labelled demo: a 296 x 128
four-colour preview and a valid 9472-byte framebuffer. Live data, hardware
provisioning and optional AI follow after that milestone is reviewed.

First inspect the available context and give me a concise plan, assumptions,
blocking questions, intended files and verification commands. Do not edit yet.
Once I approve the plan, implement the agreed milestone in reviewable changes.
Preserve any running installation. Never publish, flash hardware, expose
credentials or make paid API calls without my explicit instruction.

Deliver runnable files and English setup notes. Report changed files, checks
actually run, results and unresolved limitations. If tools or hardware are
unavailable, give me the exact manual checks instead of claiming success.
```

## Technical brief

The following is project context, not a requirement to complete every feature in
one run. The core display, data integrity and recovery behaviour are required.
OpenAI commentary and enclosure work are optional stages. Agree the current
milestone before implementation, and leave implementation choices open where
no hardware or compatibility constraint dictates them.


```text
Act as my engineering collaborator and teacher. Help me build Matchday Ink:
a small, self-hosted football companion using an ESP32-C3 and an e-paper display.

First inspect the existing repository, if present. Explain the current state,
ask only questions that block progress, and propose the smallest maintainable
solution. If a working installation exists, prepare changes separately and do
not replace its firmware, credentials or running service without my instruction.

PRODUCT
- Initially support Galatasaray, not arbitrary teams unless their sources and
  competition identities are verified.
- Show the next fixture, team names, same-competition rank/points, and local
  kickoff date/time. Default timezone: Europe/Dublin, including daylight saving.
- Use English for code, UI, documentation and errors.
- Keep the small screen readable: no stadium, weather or detailed team crests.
- Show compact connectivity and data-freshness indicators.
- Continuous USB power; no battery, cloud hosting or OTA requirement.

HARDWARE
- ESP32-C3 SuperMini.
- Waveshare 2.9-inch e-Paper Module (G), four colours, 296 x 128 logical pixels.
- SPI mapping: CLK=6, DIN=7, CS=10, DC=3, RST=4, BUSY=5,
  VCC=3.3V and shared GND. Verify against the actual board/module before wiring.
- Host renders the display and encodes the physical panel order into a strict
  9472-byte, 2-bit-per-pixel framebuffer. Confirm encoding against the vendor
  driver; do not infer packing merely from the logical resolution.
- Use Arduino CLI and a documented, pinned ESP32 core. The reference build uses
  core 3.3.12 with esp32:esp32:esp32c3:CDCOnBoot=cdc.

SOFTWARE
- Use a small Python package with pyproject.toml, src layout and a CLI.
- Separate data adapters, fixture validation, lifecycle policy, prediction,
  rendering, persistence, HTTP service and USB provisioning.
- Prefer small modules and standard library components over extra frameworks.
- Provide /health, /preview.png, /v1/dashboard and /v1/frame.bin.
- Provide an explicit offline demo with synthetic fixtures labelled DEMO.
- Never silently replace unavailable live data with synthetic values.
- Preserve source timestamps, identities and provenance. A cache read must not
  pretend the upstream data was freshly verified.

DATA
- Investigate current public sources before coding against them. The reference
  project uses a Fixtur.es calendar and ESPN adapters. These may change.
- Validate exact team/event identity, season, competition and timezone.
- Missing standings remain unavailable. Do not use another competition's table.
- Cache responsibly, use bounded response sizes/timeouts, and retain last-good
  data on provider failures.

UPDATE POLICY
- Keep the current match displayed after kickoff.
- Begin completion checks near expected full time; the reference first check is
  kickoff +105 minutes, followed by one-minute status polling.
- Require verified completed/post status, never assume a match ended based only
  on elapsed time. Account for extra time, penalties and unavailable status.
- Switch five minutes after the server first observes confirmed completion.
  Explain that polling/provider delays can make this later than five minutes
  after the whistle.
- Persist lifecycle state so a restart does not bypass the buffer.
- Separate provider cache frequency, device polling and paid AI requests.

DEVICE RELIABILITY
- Provision Wi-Fi and the server URL over USB through a loopback setup page.
  Scan SSIDs so the user only needs to select a network and enter its password.
- Store device configuration persistently and reconnect after power loss.
- Download into a separate buffer, validate the response, then replace the
  cached frame atomically. Invalid downloads retain the last valid screen.
- Skip unchanged frames and retain a three-minute physical-refresh guard.
- Bound BUSY waits. Distinguish received-frame and drawn-frame diagnostics.
  A log message does not prove that the physical panel updated: request visual
  confirmation for hardware acceptance.
- Use consistent Matchday Ink naming. If changing an existing wire protocol or
  settings namespace, document migration or reprovisioning explicitly.

OPTIONAL AI
- Python owns numerical probabilities and the most likely score. OpenAI may
  explain supplied facts; it must not invent the numerical forecast.
- A reference baseline uses up to ten completed same-competition matches per
  team, with at least three per team and strictly earlier matches only.
- Reference smoothing: attack=(goals_for+2.6)/(N+2),
  defence=(goals_against+2.6)/(N+2).
  Expected home goals=(home attack+away defence)/2, and vice versa for away.
  Independent Poisson distributions produce outcome and score probabilities.
- Explain the limitations: no calibrated home advantage, opponent-strength
  adjustment, injury/lineup inputs or established predictive accuracy.
- Keep API keys private on the server, never on the ESP32 or in Git.
- Verify the current official API documentation before implementing the client.
- Use validated structured output, bounded output, explicit timeouts, safe
  error messages and controlled retries. Treat provider text as untrusted data.
- Keep the core display working when AI fails. Distinguish authentication,
  permissions, model availability, quota/rate limiting and output validation.
- State the paid-call policy accurately. The reference project caches for
  24 hours per fixture/model/prompt; do not claim once-per-match billing unless
  that policy is actually implemented and tested.
- Clearly identify whether baseline-only mode works independently of AI
  enablement. Do not imply this if the implementation still couples them.

ENCLOSURE
- Optional: a compact three-part enclosure with symmetric front margins,
  rounded edges, separate front/back, and a one-piece perforated body.
- Printer: Bambu Lab A1, 0.4 mm nozzle, PLA Matte.
- No front-facing screws or logo requirement.
- Confirm actual PCB, socket, connector and screw dimensions before modelling.
- Use small fit coupons first. Do not promise fit from a render or mesh check.
- Reuse the repository's curated CAD when available. The reference assembly
  uses separate glued mounting feet to align its ESP32 carrier; disclose this
  repair rather than claiming the original mounting holes fit universally.

WORKFLOW AND ACCEPTANCE
1. Inspect and propose scope; list assumptions and unverified requirements.
2. Deliver an offline synthetic demo and deterministic renderer.
3. Add validated live sources and failure handling.
4. Test lifecycle transitions with an injected clock and synthetic responses.
5. Add device provisioning, persistence, caching and bounded display control.
6. Add optional forecast/explanation with mocked API tests and explicit cost
   controls. Do not make paid calls or print credentials during ordinary tests.
7. Package and install outside the checkout to verify bundled assets.
8. Compile firmware; distinguish compilation from flashing and physical tests.
9. Document setup, troubleshooting, architecture, third-party notices and
   AI collaboration. Add CI but claim success only after it actually runs.
10. Ask me to verify the physical device, restart recovery and real setup path.

For each meaningful change, explain the problem, the change, the verification
and remaining uncertainty. Prefer focused tests of behaviour and failures.
Never fabricate test results, historical commits, development duration,
customer impact, predictive accuracy or power measurements.

Keep an evidence log separating implemented, locally tested, hardware-tested
and planned work. Help me understand and review the implementation so I can
explain the system myself.
```

## Focused follow-up prompts

After reviewing the plan:

```text
Implement the offline demo milestone only. Keep live providers and paid APIs
out of this change. Run the renderer tests and verify the exported palette,
image dimensions and framebuffer length. Tell me where to inspect the preview.
```

When reproducing a display problem:

```text
The browser preview changed, but the physical display still shows the old UI.
Inspect src/matchday/service.py, src/matchday/device_setup.py and
firmware/MatchdayInk/MatchdayInk.ino. I will supply redacted device status and
what I observe on the screen. Separate download, scheduling and draw failures;
do not assume a completion message proves a physical refresh. Propose a minimal
fix, run relevant checks, and give me a hardware verification procedure.
```

Before publication:

```text
Review the candidate for credential exposure, broken setup instructions and
unsupported claims. Check README links and packaged assets. List findings by
severity with file references. Do not upload anything. Separate verified results
from checks that still require my device or a fresh installation.
```

## Prompt design reference

Reviewed against [OpenAI's prompting guide](https://learn.chatgpt.com/docs/prompting)
on 11 November 2026. The starter separates goal, context, output and boundaries;
the follow-ups narrow changes and require verification. The longer technical
brief supplies project-specific constraints. This is our interpretation of the
guidance, not an OpenAI-approved or certified prompt. Review actual results and
refine the prompt when they miss the acceptance criteria.

## Differences to expect

This brief describes a target and references the existing implementation; it is not a bit-for-bit reproduction recipe. The repository is the source of truth for current behaviour. For example, the current baseline and commentary share the AI enablement path, and the current CAD set contains exported artifacts rather than a full parametric regeneration pipeline.

For the supported setup, use [Getting started](docs/getting-started.md). For the actual collaboration and observed lessons, see [Development with Codex](docs/ai-assisted-development.md).
