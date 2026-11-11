import os
import tomllib
from pathlib import Path

from dotenv import dotenv_values

from .providers.api_football import APIFootballSource, Client


def live_source(settings):
    path = Path(settings)
    raw = tomllib.loads(path.read_text())
    football = raw["football"]
    refresh = raw["refresh"]
    interval = refresh["seconds"]
    if type(interval) is not int or interval < 180:
        raise ValueError("Refresh seconds must be an integer >=180")
    if raw.get("provider", "api-football") == "calendar":
        from .providers.calendar_feed import CalendarSource

        source = CalendarSource(
            raw["calendar"]["url"],
            football["team_name"],
            path.parent / refresh.get("cache_directory", "data/cache/calendar"),
            refresh.get("cache_seconds", 21600),
        )
        if raw.get("standings", {}).get("competitions"):
            from .providers.standings import StandingsSource

            source = StandingsSource(
                source, raw["standings"]["competitions"],
                path.parent / refresh.get("cache_directory", "data/cache/calendar") / "standings",
                raw["standings"].get("cache_seconds", 3600),
                unlabelled_leagues=raw["standings"].get("unlabelled_leagues", []),
            )
        return source, raw["display"]["timezone"], interval
    if raw.get("provider", "api-football") != "api-football":
        raise ValueError("Unsupported data provider")
    local = dotenv_values(path.parent / ".env")
    key_name = football.get("api_key_environment", "API_FOOTBALL_KEY")
    key = os.environ.get(key_name) or local.get(key_name)
    cache = path.parent / refresh.get("cache_directory", "data/cache/api-football")
    client = Client(key, cache, ttl=refresh.get("cache_seconds", 3600))
    source = APIFootballSource(
        client,
        football["team_name"],
        football["country"],
        football.get("next_count", 20),
        football.get("history_count", 30),
    )
    return source, raw["display"]["timezone"], interval
