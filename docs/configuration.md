# Configuration

Copy `settings.example.toml` to ignored `settings.toml`. This is the canonical first-release example.

| Location | Content |
| --- | --- |
| `settings.toml` | Provider, team, timezone, cache and background-check settings |
| ESP32 NVS | Wi-Fi name/password, frame URL, polling mode |
| `data/private/openai.json` | Server-only OpenAI credentials and enablement |
| `data/cache/` | Provider snapshots, lifecycle and AI results |

The setup UI scans Wi-Fi and provisions the ESP32 over USB. It does not yet edit team/timezone settings or automatically discover a LAN address. Do not add such capabilities to documentation until implemented and tested.

Team name, calendar URL and competition mappings form one supported configuration. They are not independent generic team selectors. Missing or unsupported competition data stays unavailable.

OpenAI is optional. The current default model is `gpt-4.1-mini`; actual account availability and API charges depend on the user. No API key belongs on the ESP32. Private key files use restricted permissions. The legacy API-Football adapter reads `API_FOOTBALL_KEY` from the environment or a local `.env`; the recommended calendar path needs no football API key.

Do not commit `.env`, `settings.toml`, caches, private state, Wi-Fi screenshots or serial logs containing personal network information. Use a DHCP reservation for a stable server address.
