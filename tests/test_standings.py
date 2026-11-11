from pathlib import Path

import pytest

from matchday.providers.api_football import ProviderError
from matchday.providers.standings import parse_standings

HTML = (Path(__file__).parent / "fixtures/espn-standings.html").read_text()
FIXTURE = {"home": "Galatasaray", "away": "VfB Stuttgart", "kickoff": "2026-11-03T17:45:00+00:00"}


def test_synthetic_table_rows():
    result = parse_standings(HTML, FIXTURE)
    assert result == {"home": {"position": 4, "points": 17}, "away": {"position": 8, "points": 9}}


def test_previous_season_is_rejected():
    with pytest.raises(ProviderError, match="season"):
        parse_standings(HTML.replace("2026-27", "2025-26"), FIXTURE)


def test_unknown_opponent_is_not_fuzzy_matched():
    with pytest.raises(ProviderError, match="unique"):
        parse_standings(HTML, {**FIXTURE, "away": "Stuttgart II"})


def test_misaligned_stat_row_is_rejected():
    with pytest.raises(ProviderError, match="unique"):
        parse_standings(HTML.replace('data-idx="22"', 'data-idx="5"'), FIXTURE)


def test_competition_requires_exact_event_not_just_same_teams_in_league():
    from matchday.providers.standings import match_scoreboard
    fixture = {'home': 'Club A', 'away': 'Short B', 'kickoff': '2030-11-07T16:00:00Z'}
    payload = {'leagues': [{'slug': 'test.1'}], 'events': [{
        'id': '999', 'date': '2030-11-07T16:00Z', 'competitions': [{'competitors': [
            {'homeAway': 'home', 'team': {'id': '1', 'displayName': 'Club A'}},
            {'homeAway': 'away', 'team': {'id': '2', 'displayName': 'Full B',
                                          'abbreviation': 'Short B'}},
        ]}],
    }]}
    matches = match_scoreboard(payload, fixture, 'test.1')
    assert len(matches) == 1
    assert matches[0]['teams']['away']['id'] == '2'
    assert match_scoreboard(payload, {**fixture, 'kickoff': '2030-11-08T16:00Z'}, 'test.1') == []
    assert match_scoreboard(payload, {**fixture, 'away': 'Unknown B'}, 'test.1') == []
    assert match_scoreboard(payload, fixture, 'test.cup') == []


def test_standings_resolved_identity_handles_provider_name_variants():
    fixture = {**FIXTURE, 'away': 'Different display name'}
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(HTML, 'html.parser')
    row = next(r for r in soup.select('tbody tr')
               if r.select_one('abbr[title="VfB Stuttgart"]'))
    import re
    team_id = next(re.search(r'/team/_/id/(\d+)', a['href']).group(1)
                   for a in row.select('a[href]') if re.search(r'/team/_/id/(\d+)', a['href']))
    fixture['provenance'] = {'espn_event': {'teams': {'away': {'id': team_id}}}}
    result = parse_standings(HTML, fixture)
    assert result['away'] == {'position': 8, 'points': 9}
