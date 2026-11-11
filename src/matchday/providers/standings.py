"""Optional public ESPN standings; never substitute missing or mismatched tables."""

import hashlib
import json
import re
import ssl
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import certifi
from bs4 import BeautifulSoup

from .api_football import ProviderError, normal


def parse_standings(html, fixture):
    soup = BeautifulSoup(html, "html.parser")
    # Refuse a previous season's table even if both clubs still appear in it.
    kickoff = datetime.fromisoformat(fixture["kickoff"])
    start = kickoff.year if kickoff.month >= 7 else kickoff.year - 1
    season = f"{start}-{str(start + 1)[-2:]}"
    if not soup.title or season not in soup.title.get_text():
        raise ProviderError("Standings season does not match fixture")
    tables = soup.select("table")
    candidates = []
    for index, teams in enumerate(tables[:-1]):
        rows = teams.select("tbody tr")
        if not rows or not rows[0].select_one(".team-position"):
            continue
        stats = tables[index + 1]
        headers = [th.get_text(strip=True) for th in stats.select("thead th")]
        if headers.count("P") != 1:
            continue
        points_column = headers.index("P")
        stat_rows = stats.select("tbody tr")
        ids = [row.get("data-idx") for row in stat_rows]
        if None in ids or len(set(ids)) != len(ids) or len(rows) != len(stat_rows):
            continue
        by_id = dict(zip(ids, stat_rows))
        matched = {}
        for row in rows:
            name = row.select_one("abbr[title]")
            rank = row.select_one(".team-position")
            cells = by_id.get(row.get("data-idx"))
            if name is None or rank is None or cells is None:
                continue
            cells = cells.select("td")
            if len(cells) != len(headers):
                continue
            for side in ("home", "away"):
                resolved = fixture.get("provenance", {}).get("espn_event", {}).get("teams", {})
                expected_id = resolved.get(side, {}).get("id")
                row_ids = {m.group(1) for a in row.select("a[href]")
                           if (m := re.search(r"/team/_/id/(\d+)(?:/|$)", a["href"]))}
                matches = str(expected_id) in row_ids if expected_id else normal(name["title"]) == normal(fixture[side])
                if matches:
                    if side in matched:
                        raise ProviderError("Ambiguous standings team")
                    try:
                        position = int(rank.get_text(strip=True))
                        points = int(cells[points_column].get_text(strip=True))
                    except ValueError:
                        raise ProviderError("Invalid standings values") from None
                    if position <= 0:
                        raise ProviderError("Invalid standings position")
                    matched[side] = {"position": position, "points": points}
        if len(matched) == 2:
            candidates.append(matched)
    if len(candidates) != 1:
        raise ProviderError("No unique standings table for both teams")
    return candidates[0]


class StandingsSource:
    def __init__(self, source, competitions, cache_dir, ttl=21600, opener=urlopen,
                 unlabelled_leagues=()):
        self.source, self.competitions = source, competitions
        self.cache_dir, self.ttl, self.opener = Path(cache_dir), ttl, opener
        self.unlabelled_leagues = unlabelled_leagues

    def load(self, now=None):
        now = now or datetime.now(UTC)
        result = self.source.load(now)
        for fixture in result["fixtures"]:
            if fixture["competition"] == "Calendar" and self.unlabelled_leagues:
                matches = []
                for candidate in self.unlabelled_leagues:
                    if not re.fullmatch(r"[a-z]+\.[a-z0-9]+", candidate):
                        continue
                    date = datetime.fromisoformat(fixture["kickoff"]).astimezone(UTC).strftime("%Y%m%d")
                    score_url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{candidate}/scoreboard?dates={date}"
                    cache = self.cache_dir / (hashlib.sha256(score_url.encode()).hexdigest() + ".json")
                    try:
                        if not cache.exists() or time.time() - cache.stat().st_mtime >= self.ttl:
                            with self.opener(score_url, timeout=20, context=ssl.create_default_context(cafile=certifi.where())) as response:
                                data = response.read(2_000_001)
                            if len(data) > 2_000_000:
                                raise ProviderError("Scoreboard response too large")
                            payload = json.loads(data)
                            if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
                                raise ProviderError("Invalid scoreboard payload")
                            self.cache_dir.mkdir(parents=True, exist_ok=True)
                            temporary = cache.with_suffix(".tmp")
                            temporary.write_bytes(data)
                            temporary.replace(cache)
                        payload = json.loads(cache.read_bytes())
                        for match in match_scoreboard(payload, fixture, candidate):
                            matches.append(dict(match, url=score_url))
                    except (URLError, OSError, TimeoutError, ProviderError, ValueError):
                        continue
                if len(matches) == 1:
                    fixture["competition"] = matches[0]["league"]
                    fixture.setdefault("provenance", {})["espn_event"] = matches[0]
                else:
                    result.setdefault("warnings", []).append("competition_unverified")
            league = self.competitions.get(fixture["competition"])
            if not league or not re.fullmatch(r"[a-z]+\.[a-z0-9]+", league):
                continue
            url = f"https://www.espn.com/soccer/standings/_/league/{league}"
            path = self.cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".html")
            try:
                if not path.exists() or time.time() - path.stat().st_mtime >= self.ttl:
                    with self.opener(
                        url, timeout=20,
                        context=ssl.create_default_context(cafile=certifi.where()),
                    ) as response:
                        data = response.read(2_000_001)
                    if len(data) > 2_000_000:
                        raise ProviderError("Standings response too large")
                    parse_standings(data, fixture)
                    self.cache_dir.mkdir(parents=True, exist_ok=True)
                    temporary = path.with_suffix(".tmp")
                    temporary.write_bytes(data)
                    temporary.replace(path)
                standings = parse_standings(path.read_bytes(), fixture)
            except (URLError, OSError, TimeoutError, ProviderError) as exc:
                result.setdefault("warnings", []).append(f"standings_unavailable: {exc}")
                continue
            for side in ("home", "away"):
                fixture[f"{side}_standing"] = standings[side]
            fixture["standings_competition"] = fixture["competition"]
            fixture.setdefault("provenance", {})["standings"] = {
                "provider": "ESPN", "url": url,
                "fetched_at": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
            }
            result["warnings"] = [
                warning for warning in result.get("warnings", [])
                if warning != "standings_unavailable"
            ]
        return result


def match_scoreboard(payload, fixture, league):
    """Identify competition only from an exact same-time home/away event, never membership alone."""
    from ..domain import timestamp

    if not any(item.get('slug') == league for item in payload.get('leagues', [])):
        return []
    found = []
    for event in payload.get('events', []):
        try:
            if abs((timestamp(event['date']) - timestamp(fixture['kickoff'])).total_seconds()) > 60:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        for competition in event.get('competitions', []):
            teams = {}
            for entry in competition.get('competitors', []):
                side, team = entry.get('homeAway'), entry.get('team', {})
                if side not in {'home', 'away'}:
                    continue
                aliases = {normal(team[k]) for k in
                           ('displayName', 'shortDisplayName', 'name', 'abbreviation') if team.get(k)}
                if normal(fixture[side]) in aliases and str(team.get('id', '')).isdigit():
                    if side in teams:
                        teams = {}
                        break
                    teams[side] = {'id': str(team['id']), 'name': team.get('displayName')}
            if set(teams) == {'home', 'away'}:
                found.append({'event_id': str(event.get('id', '')), 'league': league, 'teams': teams})
    return found
