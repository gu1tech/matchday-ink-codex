import argparse
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from .domain import next_fixture
from .render import encode_frame, render


def main():
    parser = argparse.ArgumentParser(description="Matchday Ink")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("render", "serve"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--schedule", type=Path, required=True)
        cmd.add_argument("--timezone", default="Europe/Dublin")
        if name == "render":
            cmd.add_argument("--output", type=Path, default=Path("build"))
        else:
            cmd.add_argument("--host", default="127.0.0.1")
            cmd.add_argument("--port", type=int, default=8000)
            cmd.add_argument("--interval", type=int, default=3600)
            cmd.add_argument("--weather", action="store_true")
    live = sub.add_parser("serve-live", help="Serve verified provider data; no demo fallback")
    live.add_argument("--settings", type=Path, default=Path("settings.toml"))
    live.add_argument("--host", default="127.0.0.1")
    live.add_argument("--port", type=int, default=8000)
    sync = sub.add_parser("sync", help="Fetch a verified live schedule snapshot")
    sync.add_argument("--settings", type=Path, default=Path("settings.toml"))
    sync.add_argument("--output", type=Path, default=Path("data/cache/live-schedule.json"))
    demo = sub.add_parser("demo")
    demo.add_argument("--output", type=Path, default=Path("build/demo.json"))
    bt = sub.add_parser("backtest")
    bt.add_argument("history", type=Path)
    ai = sub.add_parser("comment")
    ai.add_argument("facts", type=Path)
    ai.add_argument("--cache", type=Path, default=Path("data/cache/ai"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.command in {"serve-live", "sync"}:
        from .config import live_source
        from .providers.api_football import ProviderError

        try:
            source, zone, interval = live_source(args.settings)
            if args.command == "sync":
                raw = source.load()
                args.output.parent.mkdir(parents=True, exist_ok=True)
                temporary = args.output.with_suffix(".tmp")
                temporary.write_text(json.dumps(raw, indent=2, ensure_ascii=False))
                temporary.replace(args.output)
                print(args.output)
            else:
                from .ai_prediction import PredictionEngine
                from .lifecycle import MatchLifecycle
                from .service import Dashboard, serve

                serve(Dashboard(timezone=zone, source=source,
                                prediction_engine=PredictionEngine(args.settings.resolve().parent),
                                lifecycle=MatchLifecycle(args.settings.resolve().parent)),
                      args.host, args.port, interval)
        except (ProviderError, FileNotFoundError, KeyError, ValueError) as exc:
            parser.exit(2, f"Live setup unavailable: {exc}\n")
    elif args.command == "demo":
        from datetime import timedelta

        now = datetime.now(UTC)
        kickoff = (now + timedelta(days=3)).replace(hour=20, minute=0, second=0, microsecond=0)
        value = {
            "demo": True,
            "source_updated_at": now.isoformat(),
            "fixtures": [
                {
                    "id": "synthetic-demo",
                    "home_form": ["G", "G", "B", "G", "M"],
                    "home_standing": {"position": 1, "points": 28},
                    "away_standing": {"position": 7, "points": 18},
                    "standings_competition": "Süper Lig (DEMO)",
                    "away_form": ["B", "M", "G", "B", "G"],
                    "home": "Galatasaray",
                    "away": "Example United",
                    "competition": "SUPER LIG - DEMO",
                    "kickoff": kickoff.isoformat(),
                    "venue": "EXAMPLE STADIUM",
                    "latitude": None,
                    "longitude": None,
                    "status": "TIMED",
                    "source": "Synthetic layout example, not a real fixture",
                    "demo": True,
                }
            ],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(value, indent=2))
        print(args.output)
    elif args.command == "render":
        raw = json.loads(args.schedule.read_text())
        fixture = next_fixture(raw["fixtures"], datetime.now(UTC))
        im = render(fixture, args.timezone)
        args.output.mkdir(parents=True, exist_ok=True)
        im.save(args.output / "dashboard.png")
        from PIL import Image

        im.resize((1184, 512), Image.Resampling.NEAREST).save(args.output / "dashboard-preview.png")
        frame = encode_frame(im)
        (args.output / "frame.bin").write_bytes(frame)
        lines = [
            ", ".join(f"0x{b:02x}" for b in frame[i : i + 16]) for i in range(0, len(frame), 16)
        ]
        (args.output / "boot_frame.h").write_text(
            "#pragma once\n#include <stdint.h>\n"
            + "static const bool BOOT_FRAME_IS_DEMO = "
            + str(bool(raw.get("demo"))).lower()
            + ";\n"
            + "static const uint8_t BOOT_FRAME[9472] = {\n"
            + ",\n".join(lines)
            + "\n};\n"
        )
        print(args.output)
    elif args.command == "serve":
        from .service import Dashboard, serve

        serve(
            Dashboard(args.schedule, args.timezone, args.weather),
            args.host,
            args.port,
            args.interval,
        )
    elif args.command == "backtest":
        from .prediction import backtest

        print(json.dumps(backtest(json.loads(args.history.read_text())), indent=2))
    elif args.command == "comment":
        from .commentary import comment

        print(json.dumps(comment(json.loads(args.facts.read_text()), args.cache), indent=2))


if __name__ == "__main__":
    main()
