"""Completed ESPN league matches, identified by provider IDs, never guessed names."""

import hashlib
import json
import re
import ssl
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

import certifi

from ..domain import timestamp
from .api_football import ProviderError
from .standings import match_scoreboard


def completed_matches(payload, team_id, now, season):
    if str(payload.get("team", {}).get("id")) != str(team_id):
        raise ProviderError("History team identity mismatch")
    if str(payload.get("season", {}).get("year")) != str(season):
        raise ProviderError("History season mismatch")
    matches = {}
    for event in payload.get("events", []):
        for comp in event.get("competitions", []):
            status = comp.get("status", {}).get("type", {})
            # Exclude live games, extra time and shootouts: this baseline models 90-minute goals.
            if status.get("completed") is not True or status.get("name") != "STATUS_FULL_TIME":
                continue
            try:
                played = timestamp(comp.get("date") or event["date"])
                if played >= now or int(event["season"]["year"]) != season:
                    continue
                sides = {}
                for entry in comp["competitors"]:
                    side = entry["homeAway"]
                    if side not in {"home", "away"} or side in sides:
                        raise ValueError("Ambiguous history sides")
                    score = entry["score"]["value"]
                    if (isinstance(score, bool) or not isinstance(score, (int, float))
                            or not 0 <= score <= 30 or score != int(score)):
                        raise ValueError("Invalid final score")
                    sides[side] = (str(entry["team"]["id"]), int(score))
                if set(sides) != {"home", "away"} or str(team_id) not in {x[0] for x in sides.values()}:
                    continue
                identity = str(event["id"])
                row = {"id": identity, "played_at": played.isoformat(),
                       "home": sides["home"][0], "away": sides["away"][0],
                       "home_goals": sides["home"][1], "away_goals": sides["away"][1]}
                if identity in matches and matches[identity] != row:
                    raise ProviderError("Conflicting history event")
                matches[identity] = row
            except (KeyError, TypeError, ValueError):
                continue
    return sorted(matches.values(), key=lambda row: row["played_at"], reverse=True)[:10]


class HistorySource:
    def __init__(self, cache_dir, opener=urlopen):
        self.cache_dir, self.opener = Path(cache_dir), opener

    def get(self, url, now):
        path = self.cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".json")
        if not path.exists() or now.timestamp() - path.stat().st_mtime >= 21600:
            with self.opener(url, timeout=20,
                             context=ssl.create_default_context(cafile=certifi.where())) as response:
                data = response.read(2_000_001)
            if len(data) > 2_000_000:
                raise ProviderError("History response too large")
            json.loads(data)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_bytes(data)
            temporary.replace(path)
        return json.loads(path.read_bytes()), datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()

    def load(self, fixture, now):
        event = fixture.get("provenance", {}).get("espn_event")
        if not event:
            league = {"CL": "uefa.champions"}.get(fixture["competition"], fixture["competition"])
            if not re.fullmatch(r"[a-z]+\.[a-z0-9]+", league):
                raise ProviderError("Prediction competition is not verified")
            date = timestamp(fixture["kickoff"]).strftime("%Y%m%d")
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/scoreboard?dates={date}"
            payload, _ = self.get(url, now)
            found = match_scoreboard(payload, fixture, league)
            if len(found) != 1:
                raise ProviderError("Prediction fixture identity is not verified")
            event = found[0]
        league = event["league"]
        if not re.fullmatch(r"[a-z]+\.[a-z0-9]+", league):
            raise ProviderError("Invalid history league")
        cutoff = min(now, timestamp(fixture["kickoff"]))
        season = cutoff.year if cutoff.month >= 7 else cutoff.year - 1
        rows, sources, ids, counts = {}, [], {}, {}
        for side in ("home", "away"):
            identity = str(event["teams"][side]["id"])
            if not identity.isdigit():
                raise ProviderError("Invalid history team ID")
            ids[side] = identity
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/teams/{identity}/schedule?season={season}"
            payload, fetched = self.get(url, now)
            completed = completed_matches(payload, identity, cutoff, season)
            counts[side] = len(completed)
            for row in completed:
                if row["id"] in rows and rows[row["id"]] != row:
                    raise ProviderError("Conflicting history across teams")
                rows[row["id"]] = row
            sources.append({"provider": "ESPN", "url": url, "fetched_at": fetched})
        return {"matches": list(rows.values()), "team_ids": ids, "sample_counts": counts,
                "league": league, "sources": sources}
