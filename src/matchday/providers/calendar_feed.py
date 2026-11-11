"""Public iCalendar fixture source. No account, IDs, seasons or match values required."""

import re
import ssl
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

import certifi
from icalendar import Calendar

from ..domain import validate_fixture
from .api_football import ProviderError, normal


def parse_calendar(data, team_name, url, now, fetched_at):
    calendar = Calendar.from_ical(data)
    candidates, unknown_dates = [], []
    latest = {}
    for index, event in enumerate(calendar.walk("VEVENT")):
        uid = str(event.get("UID") or f"missing-{index}")
        changed = event.decoded("LAST-MODIFIED", event.decoded("DTSTAMP", None))
        changed_at = changed.timestamp() if isinstance(changed, datetime) and changed.tzinfo else 0
        revision = (int(event.get("SEQUENCE", 0)), changed_at)
        if uid not in latest or revision >= latest[uid][0]:
            latest[uid] = (revision, event)
    for _, event in latest.values():
        if str(event.get("STATUS", "")).upper() == "CANCELLED":
            continue
        summary = str(event.get("SUMMARY", "")).strip()
        code = re.search(r"\s+\[([^]]+)\]\s*$", summary)
        title = summary[: code.start()] if code else summary
        home, separator, away = title.partition(" - ")
        if not separator or normal(team_name) not in {normal(home), normal(away)}:
            continue
        if event.get("RRULE"):
            raise ProviderError(
                "Recurring match events require expansion; refusing incomplete schedule"
            )
        start = event.decoded("DTSTART", None)
        if start is None:
            continue
        if not isinstance(start, datetime) or start.tzinfo is None:
            day = start.date() if isinstance(start, datetime) else start
            if day >= now.date():
                unknown_dates.append(day)
            continue
        start = start.astimezone(UTC)
        if start <= now:
            continue
        if str(event.get("STATUS", "CONFIRMED")).upper() != "CONFIRMED":
            unknown_dates.append(start.date())
            continue
        candidates.append((start, event, home, away, code.group(1) if code else None))
    if not candidates:
        raise ProviderError("Calendar has no verified future timed match")
    start, event, home, away, competition = min(candidates, key=lambda x: x[0])
    if any(day <= start.date() for day in unknown_dates):
        raise ProviderError("An earlier match has an unconfirmed kickoff; refusing to skip it")
    generated = event.decoded("DTSTAMP", None)
    if not isinstance(generated, datetime) or generated.tzinfo is None:
        generated = fetched_at
    generated = generated.astimezone(UTC)
    source_time = min(generated, fetched_at)
    result = {
        "id": str(event.get("UID") or start.isoformat() + home + away),
        "home": home.strip(),
        "away": away.strip(),
        "competition": competition or "Calendar",
        "kickoff": start.isoformat(),
        "venue": str(event.get("LOCATION") or "Belirtilmedi"),
        "status": "TIMED",
        "source": url,
        "demo": False,
        "latitude": None,
        "longitude": None,
        "provenance": {
            "provider": "Fixtur.es iCalendar",
            "url": url,
            "fetched_at": fetched_at.isoformat(),
            "calendar_generated_at": generated.isoformat(),
            "calendar_summary": str(event.get("SUMMARY")),
        },
    }
    validate_fixture(result)
    return {
        "demo": False,
        "provider": "Fixtur.es iCalendar",
        "source_updated_at": source_time.isoformat(),
        "source_verified_at": fetched_at.isoformat(),
        "fixtures": [result],
        "warnings": ["form_unavailable", "standings_unavailable"],
    }


class CalendarSource:
    def __init__(self, url, team_name, cache_dir, ttl=21600, opener=urlopen):
        parts = urlparse(url)
        if (
            parts.scheme != "https"
            or parts.hostname != "ics.fixtur.es"
            or parts.username
            or parts.password
        ):
            raise ValueError("This adapter accepts only the public HTTPS Fixtur.es calendar host")
        self.url, self.team_name, self.cache_dir, self.ttl, self.opener = (
            url,
            team_name,
            Path(cache_dir),
            ttl,
            opener,
        )

    def load(self, now=None):
        import hashlib

        now = now or datetime.now(UTC)
        path = self.cache_dir / (hashlib.sha256(self.url.encode()).hexdigest() + ".ics")
        if not path.exists() or time.time() - path.stat().st_mtime >= self.ttl:
            try:
                with self.opener(
                    self.url, timeout=20, context=ssl.create_default_context(cafile=certifi.where())
                ) as response:
                    data = response.read(2_000_001)
            except (URLError, OSError, TimeoutError):
                raise ProviderError(
                    "Calendar download failed; retaining last verified screen"
                ) from None
            if len(data) > 2_000_000:
                raise ProviderError("Calendar response too large")
            # Validate before replacing last downloaded content.
            parse_calendar(data, self.team_name, self.url, now, now)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_bytes(data)
            temporary.replace(path)
        return parse_calendar(
            path.read_bytes(),
            self.team_name,
            self.url,
            now,
            datetime.fromtimestamp(path.stat().st_mtime, UTC),
        )
