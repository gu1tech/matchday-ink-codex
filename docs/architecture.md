# Architecture

## Responsibilities

- `domain.py`: fixture validation and upcoming-fixture selection.
- `providers/`: calendar, standings and historical-result adapters. API-Football remains an optional legacy adapter, not the recommended path.
- `lifecycle.py`: persisted active fixture and observed full-time buffer.
- `scheduling.py`: server-directed device polling policy.
- `prediction.py`: deterministic smoothed Poisson model.
- `ai_prediction.py`: optional explanation, private configuration, cache and bounded retries.
- `storage.py`: shared atomic JSON persistence, independent of AI.
- `render.py`: fonts, fitting, palette and physical framebuffer encoding.
- `service.py`: synchronized dashboard snapshots and HTTP endpoints.
- `device_setup.py`: loopback setup UI and USB provisioning.
- `firmware/MatchdayInk`: device networking, persistent configuration, cache and vendor display driver.

The setup page currently remains embedded in Python. Extracting static assets is a possible follow-up, not a prerequisite for this small service. Legacy weather and explicit commentary commands remain for compatibility but are outside the supported setup path.

## Data lifecycle

The server checks every 300 seconds by default. Provider caches are distinct: calendar six hours, standings one hour, historical schedules six hours. Cache reads do not renew upstream verification timestamps.

Once kickoff passes, the active fixture remains displayed. Completion polling starts at kickoff +105 minutes and repeats every minute. Only validated completed/post status releases the fixture, five minutes after completion is first observed. Extra time and unavailable status do not become guessed completion times. Restart state is persisted.

The device receives server-directed polling delays. Failed downloads retry without discarding the last valid image. E-paper refreshes have a 180-second minimum guard. Incoming and drawn frame hashes describe separate stages; telemetry cannot prove optical success.

## HTTP contract

| Endpoint | Response |
| --- | --- |
| `/` | Browser preview |
| `/preview.png` | 296 × 128 PNG |
| `/v1/frame.bin` | 9472 bytes; 2 bits/pixel in physical panel order |
| `/v1/dashboard` | Fixture, provenance, freshness, lifecycle and optional forecast |
| `/health` | Service health; unavailable before a valid snapshot |

The release uses `X-Matchday-Ink-Fresh-For` and `X-Matchday-Ink-Poll-After` headers and `MATCHDAY_INK_*` USB commands. Server and firmware must be upgraded together. The dashboard schema version is 1.

## Failure boundaries

Optional AI must not prevent fixture rendering. Invalid identity, season or timestamps must not become plausible-looking values. Download failure preserves the last valid framebuffer. Server restarts restore lifecycle state. HTTP is intended for a trusted LAN only; setup binds to loopback and uses request tokens. This is not a hardened multi-user hosted service.
