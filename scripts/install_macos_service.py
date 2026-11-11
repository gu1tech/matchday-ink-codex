"""Install per-user launchd services; keep runtime outside macOS protected Documents."""

import argparse
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frame-url", required=True)
    args = parser.parse_args()
    if not args.frame_url.startswith("http://"):
        parser.error("Use the existing trusted LAN frame URL")
    if not (ROOT / "settings.toml").is_file():
        parser.error("Copy settings.example.toml to settings.toml and configure it first")
    runtime = Path.home() / "Library/Application Support/MatchdayInk"
    logs = Path.home() / "Library/Logs/MatchdayInk"
    agents = Path.home() / "Library/LaunchAgents"
    for path in (runtime, logs, agents):
        path.mkdir(parents=True, exist_ok=True)
    runtime.chmod(0o700)
    logs.chmod(0o700)
    python = runtime / ".venv/bin/python"
    if not python.exists():
        subprocess.run([sys.executable, "-m", "venv", str(runtime / ".venv")], check=True)
    subprocess.run([str(python), "-m", "pip", "install", str(ROOT) + "[ai,device]"], check=True)
    shutil.copy2(ROOT / "settings.toml", runtime / "settings.toml")
    (runtime / "settings.toml").chmod(0o600)
    # Seed state only on first install. Never replace newer running-service state.
    if not (runtime / "data").exists():
        if (ROOT / "data").exists():
            shutil.copytree(ROOT / "data", runtime / "data")
        else:
            (runtime / "data").mkdir()
    private = runtime / "data/private"
    if private.exists():
        private.chmod(0o700)
        for path in private.iterdir():
            if path.is_file():
                path.chmod(0o600)
    jobs = {
        "data": [str(python), "-m", "matchday.cli", "serve-live", "--settings",
                 str(runtime / "settings.toml"), "--host", "0.0.0.0", "--port", "8765"],
        "setup": [str(python), "-m", "matchday.device_setup", "--frame-url", args.frame_url,
                  "--port", "8780", "--project", str(runtime)],
    }
    for name, command in jobs.items():
        label = f"com.gu1tech.matchdayink.{name}"
        payload = {
            "Label": label, "ProgramArguments": command, "WorkingDirectory": str(runtime),
            "RunAtLoad": True, "KeepAlive": True, "ThrottleInterval": 30,
            "ProcessType": "Background", "Umask": 0o077,
            "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
            "StandardOutPath": str(logs / f"{name}.log"),
            "StandardErrorPath": str(logs / f"{name}.error.log"),
        }
        path = agents / f"{label}.plist"
        with path.open("wb") as stream:
            plistlib.dump(payload, stream)
        path.chmod(0o600)
        subprocess.run(["plutil", "-lint", str(path)], check=True)
    print(f"Runtime ready: {runtime}")
    print("Stop old foreground services, then bootstrap both LaunchAgents in your GUI domain.")


if __name__ == "__main__":
    main()
