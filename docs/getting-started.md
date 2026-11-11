# Getting started

## 1. Prepare the hardware

Use the exact display variant and [wiring table](hardware.md). A USB data cable is required for flashing and setup. Disconnect power while wiring.

## 2. Install the server

From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[ai,device]'
cp settings.example.toml settings.toml
matchday-ink demo
matchday-ink render --schedule build/demo.json
```

Checkpoint: `build/dashboard-preview.png` shows a labelled synthetic fixture.

Start the live server in this terminal:

```sh
matchday-ink serve-live --settings settings.toml --host 0.0.0.0 --port 8765
```

Open http://127.0.0.1:8765/. Initial retrieval requires Internet access. A provider failure must not silently substitute demo data.

## 3. Flash the ESP32

Install Arduino CLI and the Espressif core:

```sh
arduino-cli core update-index --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core install esp32:esp32@3.3.12 --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli board list
arduino-cli compile --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc firmware/MatchdayInk
```

Replace `YOUR_SERIAL_PORT` below with the detected port:

```sh
arduino-cli upload --port YOUR_SERIAL_PORT --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc firmware/MatchdayInk
```

If the port is missing, hold BOOT, tap RESET, then release BOOT. Stop other serial monitors and the setup service before uploading. Do not erase flash during a normal upgrade: settings and the cached frame should remain.

`MatchdayInk` is the Arduino sketch name. Prebuilt release firmware is not included in this review copy; build from source using the pinned core.

## 4. Configure Wi-Fi

Find your Mac's LAN address in System Settings → Wi-Fi → Details → TCP/IP. In a second terminal, activate the virtual environment and run the following, replacing `YOUR_MAC_LAN_IP`:

```sh
source .venv/bin/activate
python -m matchday.device_setup --frame-url http://YOUR_MAC_LAN_IP:8765/v1/frame.bin --project . --port 8780
```

Open http://127.0.0.1:8780/. Select a scanned network, enter its password, and save. The ESP32 needs a compatible 2.4 GHz Wi-Fi network. The setup page is loopback-only; the frame server is reachable on the LAN. Allow the Python server through the macOS firewall on your trusted network if necessary.

Checkpoint: verify connectivity and a frame download in the page, then visually check the physical screen. An unchanged frame does not trigger another refresh, and physical refreshes have a three-minute minimum interval.

Timezone is configured in `settings.toml`, not currently a setup-page control. Galatasaray is the supported team; changing its name alone does not configure another team's sources.

## 5. Optional OpenAI explanation

Use the local setup page to save a key and enable analysis. Do not paste keys into source, issues, or screenshots. The key remains on the server. The statistical baseline does not need an OpenAI key; the current live orchestration enables forecasting and commentary together through the AI setting. API failures preserve the core match display.

## 6. Automatic macOS startup

Stop both foreground servers before enabling background jobs. With `settings.toml` present, run:

```sh
python scripts/install_macos_service.py --frame-url http://YOUR_MAC_LAN_IP:8765/v1/frame.bin
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.gu1tech.matchdayink.data.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.gu1tech.matchdayink.setup.plist
```

The installer creates a separate runtime under `~/Library/Application Support/MatchdayInk` and logs under `~/Library/Logs/MatchdayInk`. It installs the package there and seeds data on first installation only. Source edits require redeployment. Review the installer before running it; do not run alongside the previous development services on the same ports.

Checkpoint: verify both URLs, then test logout/login. Per-user startup occurs after login, not before it. Keep the Mac awake; a DHCP reservation avoids server-address changes.

## 7. Place the device

Move the ESP32 to a USB power supply. Confirm reconnection and the physical screen. On a server outage, the cached screen remains; it is not evidence of fresh data.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| No serial port | USB data cable; BOOT/RESET sequence; close other serial clients |
| Cannot connect to Wi-Fi | 2.4 GHz network, password, signal |
| Cannot download frame | Mac awake, correct LAN IP, firewall, same LAN |
| Old screen remains | Preview versus hardware; freshness icons; refresh guard; provider errors |
| Missing standings | Competition mapping, current season and exact team validation |
| AI unavailable | Local status, API billing/limits; do not repeatedly retry |
| Service starts with old code | Installed runtime is separate from source; redeploy deliberately |

## Upgrading an earlier prototype

This release renames the USB commands, HTTP headers and ESP32 settings namespace. Upgrade server and firmware together and provision Wi-Fi again. Existing prototype settings are not migrated automatically. The current assembled installation is not modified by preparing this repository.
