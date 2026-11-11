"""API-Football v3 adapter; fixture identities and seasons come from the provider."""

import hashlib
import json
import ssl
import time
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

import certifi

from ..domain import timestamp, validate_fixture

BASE_URL = "https://v3.football.api-sports.io"


class ProviderError(RuntimeError):
    pass


class Client:
    def __init__(self, key, cache_dir, ttl=3600, opener=urlopen):
        if not key:
            raise ProviderError("API_FOOTBALL_KEY is not configured")
        self.key, self.cache_dir, self.ttl, self.opener = key, Path(cache_dir), ttl, opener

    def get(self, endpoint, **params):
        if endpoint not in {"teams", "fixtures", "standings", "status"}:
            raise ValueError("Unsupported provider endpoint")
        url = BASE_URL + "/" + endpoint + "?" + urlencode(sorted(params.items()))
        path = self.cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".json")
        if path.exists() and time.time() - path.stat().st_mtime < self.ttl:
            raw = json.loads(path.read_text())
        else:
            request = Request(url, headers={"x-apisports-key": self.key})
            try:
                with self.opener(
                    request, timeout=20, context=ssl.create_default_context(cafile=certifi.where())
                ) as response:
                    raw = json.load(response)
            except HTTPError as exc:
                raise ProviderError(f"Provider HTTP {exc.code} at {endpoint}") from None
            except (URLError, TimeoutError, OSError):
                raise ProviderError(f"Provider connection/TLS failure at {endpoint}") from None
            # Never log provider error text: it may echo request metadata.
            if raw.get("errors"):
                raise ProviderError(
                    f"Provider rejected {endpoint}; check key, quota and season access"
                )
            if raw.get("paging", {}).get("total", 1) > 1:
                raise ProviderError("Incomplete paginated response; refusing partial data")
            if not isinstance(raw.get("response"), (list, dict)):
                raise ProviderError("Invalid provider response")
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix("." + uuid4().hex + ".tmp")
            tmp.write_text(json.dumps(raw))
            tmp.replace(path)
        if raw.get("errors"):
            raise ProviderError("Cached provider response contains an error")
        self.last_fetched_at = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        return raw["response"]


def normal(value):
    return "".join(
        c for c in unicodedata.normalize("NFKD", value).casefold() if not unicodedata.combining(c)
    ).replace("ı", "i")


def official(row):
    return (
        "friendly" not in row["league"]["name"].casefold()
        and "friendlies" not in row["league"]["name"].casefold()
    )


def recent_form(rows, team_id, now):
    seen, completed = set(), []
    for row in sorted(rows, key=lambda r: timestamp(r["fixture"]["date"]), reverse=True):
        identity = row["fixture"]["id"]
        if identity in seen or not official(row) or timestamp(row["fixture"]["date"]) >= now:
            continue
        seen.add(identity)
        if row["fixture"]["status"]["short"] not in {"FT", "AET", "PEN"}:
            continue
        sides = row["teams"]
        if team_id not in {sides["home"]["id"], sides["away"]["id"]}:
            continue
        side = "home" if sides["home"]["id"] == team_id else "away"
        opposite = "away" if side == "home" else "home"
        if sides[side].get("winner") is True:
            result = "G"
        elif sides[opposite].get("winner") is True:
            result = "M"
        else:
            goals = row.get("goals", {})
            if type(goals.get(side)) is not int or type(goals.get(opposite)) is not int:
                continue
            if row["fixture"]["status"]["short"] == "PEN":
                continue  # Missing shootout winner is not a draw.
            result = (
                "G"
                if goals[side] > goals[opposite]
                else "M"
                if goals[side] < goals[opposite]
                else "B"
            )
        completed.append((result, str(identity)))
        if len(completed) == 5:
            ordered = list(reversed(completed))
            return [r for r, _ in ordered], [identity for _, identity in ordered]
    return None, []


def shared_standings(rows, home_id, away_id):
    for block in rows:
        league = block.get("league", {})
        for table in league.get("standings", []):
            matches = {r["team"]["id"]: r for r in table if r["team"]["id"] in {home_id, away_id}}
            # Compare ranks only within the same table/group.
            if len(matches) == 2:
                result = []
                for team_id in (home_id, away_id):
                    r = matches[team_id]
                    if type(r.get("rank")) is not int or type(r.get("points")) is not int:
                        return None
                    result.append({"position": r["rank"], "points": r["points"]})
                return result, league["name"]
    return None


class APIFootballSource:
    def __init__(self, client, team_name, country, next_count=20, history_count=30):
        self.client, self.team_name, self.country = client, team_name, country
        self.next_count, self.history_count = next_count, history_count
        self.team_id = None

    def resolve_team(self):
        if self.team_id is None:
            rows = self.client.get("teams", search=self.team_name)
            matches = [
                r["team"]
                for r in rows
                if normal(r["team"]["name"]) == normal(self.team_name)
                and normal(r["team"].get("country", "")) == normal(self.country)
            ]
            if len(matches) != 1:
                raise ProviderError(
                    "Team search is ambiguous or empty; configure the exact provider name"
                )
            self.team_id = matches[0]["id"]
        return self.team_id

    def load(self, now=None):
        now = now or datetime.now(UTC)
        team_id = self.resolve_team()
        rows = self.client.get("fixtures", team=team_id, next=self.next_count, timezone="UTC")
        candidates = [
            r
            for r in rows
            if official(r)
            and r["fixture"]["status"]["short"] == "NS"
            and timestamp(r["fixture"]["date"]) > now
        ]
        fixture_fetched_at = getattr(self.client, "last_fetched_at", now)
        warnings = []
        if not candidates:
            # An empty response might be a plan/coverage limitation, not an empty schedule.
            raise ProviderError(
                "No verified upcoming official fixture; check coverage and current-season access"
            )
        row = min(candidates, key=lambda r: timestamp(r["fixture"]["date"]))
        home, away = row["teams"]["home"], row["teams"]["away"]
        league, fixture = row["league"], row["fixture"]
        result = {
            "id": str(fixture["id"]),
            "home": home["name"],
            "away": away["name"],
            "competition": league["name"],
            "kickoff": timestamp(fixture["date"]).isoformat(),
            "venue": fixture.get("venue", {}).get("name") or "Not supplied",
            "status": "TIMED",
            "source": f"API-Football fixture {fixture['id']}",
            "demo": False,
            "latitude": None,
            "longitude": None,
            "league_id": league["id"],
            "season": league["season"],
            "home_team_id": home["id"],
            "away_team_id": away["id"],
            "provenance": {
                "provider": "API-Football",
                "fetched_at": fixture_fetched_at.isoformat(),
                "form_scope": "last five completed official matches across competitions",
            },
        }
        for prefix, team in (("home", home), ("away", away)):
            try:
                history = self.client.get(
                    "fixtures", team=team["id"], last=self.history_count, timezone="UTC"
                )
                form, identities = recent_form(history, team["id"], now)
                result[prefix + "_form"] = form
                result["provenance"][prefix + "_form_fixture_ids"] = identities
                if form is None:
                    warnings.append(prefix + "_form_incomplete")
            except ProviderError:
                warnings.append(prefix + "_form_unavailable")
        try:
            tables = self.client.get("standings", league=league["id"], season=league["season"])
            selected = shared_standings(tables, home["id"], away["id"])
            if selected:
                standings, name = selected
                result["home_standing"], result["away_standing"] = standings
                result["standings_competition"] = name
            else:
                warnings.append("no_shared_competition_table")
        except ProviderError:
            warnings.append("standings_unavailable")
        validate_fixture(result)
        return {
            "demo": False,
            "source_updated_at": fixture_fetched_at.isoformat(),
            "fixtures": [result],
            "provider": "API-Football",
            "warnings": warnings,
        }
