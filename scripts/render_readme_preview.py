"""Render an explicitly synthetic README fixture; no network or paid API calls."""

from pathlib import Path

from PIL import Image

from matchday.render import render

ROOT = Path(__file__).resolve().parents[1]


def main():
    fixture = {
        "home": "Galatasaray",
        "away": "Liverpool",
        "kickoff": "2030-11-07T20:00:00+00:00",
        "home_standing": {"position": 1, "points": 25},
        "away_standing": {"position": 2, "points": 23},
        "demo": True,
    }
    image = render(fixture, ai_note="Sample score: 1-1", connection=None)
    output = ROOT / "docs/images/display-preview.png"
    image.resize((1184, 512), Image.Resampling.NEAREST).save(output)
    print(output)


if __name__ == "__main__":
    main()
