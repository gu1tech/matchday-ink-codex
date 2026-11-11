import math
import unicodedata
from datetime import UTC, datetime


def timestamp(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Timestamps must include a timezone")
    return dt.astimezone(UTC)


def ascii_text(value):
    value = str(value).replace("ı", "i").replace("İ", "I")
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()


def validate_fixture(raw):
    required = ("id", "home", "away", "competition", "kickoff", "venue", "source")
    for key in required:
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            raise ValueError(f"Missing or invalid fixture field: {key}")
    timestamp(raw["kickoff"])
    if raw.get("status") not in {"SCHEDULED", "TIMED"}:
        raise ValueError("Only scheduled/timed matches can be displayed as upcoming")
    if not isinstance(raw.get("demo"), bool):
        raise ValueError("Explicit demo boolean required")
    # Coordinates must describe the actual stadium, including away matches.
    lat, lon = raw.get("latitude"), raw.get("longitude")
    if lat is not None or lon is not None:
        if any(
            isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v)
            for v in (lat, lon)
        ):
            raise ValueError("Both finite stadium coordinates required")
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("Invalid stadium coordinates")
    for key in ("home_form", "away_form"):
        value = raw.get(key)
        if value is not None and (
            not isinstance(value, list)
            or len(value) != 5
            or any(v not in {"G", "B", "M"} for v in value)
        ):
            raise ValueError("Form must contain exactly five G/B/M results, oldest first")
    for key in ("home_standing", "away_standing"):
        standing = raw.get(key)
        if standing is not None:
            if (
                not isinstance(standing, dict)
                or type(standing.get("position")) is not int
                or standing["position"] < 1
                or type(standing.get("points")) is not int
            ):
                raise ValueError("Standing requires a positive integer position and integer points")
            if (
                not isinstance(raw.get("standings_competition"), str)
                or not raw["standings_competition"].strip()
            ):
                raise ValueError("Standings competition context required")
    return dict(raw)


def next_fixture(fixtures, now):
    valid = [validate_fixture(f) for f in fixtures]
    upcoming = [f for f in valid if timestamp(f["kickoff"]) > now]
    return min(upcoming, key=lambda f: timestamp(f["kickoff"])) if upcoming else None
