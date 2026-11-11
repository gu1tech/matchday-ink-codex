import json
from datetime import timedelta
from io import BytesIO

import pytest

from matchday.domain import timestamp
from matchday.providers.api_football import (
    APIFootballSource,
    Client,
    ProviderError,
    recent_form,
    shared_standings,
)

NOW = timestamp("2030-11-02T12:00:00Z")


def row(identity=1, status="NS", date=None, home=101, away=202, goals=(1, 0), league="Test league"):
    return {
        "fixture": {
            "id": identity,
            "date": (date or NOW + timedelta(days=2)).isoformat(),
            "status": {"short": status},
            "venue": {"name": "Provider stadium"},
        },
        "league": {"id": 909, "name": league, "season": 2029},
        "teams": {
            "home": {"id": home, "name": "Galatasaray", "winner": goals[0] > goals[1]},
            "away": {"id": away, "name": "Provider opponent", "winner": goals[1] > goals[0]},
        },
        "goals": {"home": goals[0], "away": goals[1]},
    }


class FakeClient:
    def __init__(self):
        self.calls = []

    def get(self, endpoint, **params):
        self.calls.append((endpoint, params))
        if endpoint == "teams":
            assert "country" not in params
            return [{"team": {"id": 101, "name": "Galatasaray", "country": "Turkey"}}]
        if endpoint == "standings":
            return [
                {
                    "league": {
                        "name": "Provider competition",
                        "standings": [
                            [
                                {"team": {"id": 101}, "rank": 2, "points": 23},
                                {"team": {"id": 202}, "rank": 9, "points": 12},
                            ]
                        ],
                    }
                }
            ]
        if "next" in params:
            return [
                row(9, date=NOW + timedelta(days=1), league="Friendlies Clubs"),
                row(8, status="PST", date=NOW + timedelta(hours=2)),
                row(7),
            ]
        target = params["team"]
        return [
            row(
                i + 20,
                status="FT",
                date=NOW - timedelta(days=i + 1),
                home=target,
                away=999,
                goals=(i % 3, 1),
            )
            for i in range(5)
        ]


def test_live_ids_season_names_and_points_come_from_provider():
    client = FakeClient()
    raw = APIFootballSource(client, "Galatasaray", "Turkey").load(NOW)
    f = raw["fixtures"][0]
    assert raw["demo"] is False and f["demo"] is False
    assert f["id"] == "7" and f["away"] == "Provider opponent"
    assert f["home_standing"] == {"position": 2, "points": 23}
    assert len(f["home_form"]) == 5
    assert ("standings", {"league": 909, "season": 2029}) in client.calls
    assert f["standings_competition"] == "Provider competition"


def test_empty_next_results_never_switch_to_demo():
    class Empty(FakeClient):
        def get(self, endpoint, **params):
            return [] if "next" in params else super().get(endpoint, **params)

    with pytest.raises(ProviderError, match="No verified upcoming"):
        APIFootballSource(Empty(), "Galatasaray", "Turkey").load(NOW)


def test_form_is_oldest_first_from_team_perspective():
    rows = [
        row(3, status="FT", date=NOW - timedelta(days=3), home=999, away=101, goals=(2, 0)),
        row(1, status="FT", date=NOW - timedelta(days=1), home=101, goals=(2, 0)),
        row(2, status="FT", date=NOW - timedelta(days=2), home=101, goals=(0, 0)),
        row(4, status="FT", date=NOW - timedelta(days=4), home=101, goals=(3, 1)),
        row(5, status="FT", date=NOW - timedelta(days=5), home=101, goals=(0, 1)),
    ]
    form, ids = recent_form(rows, 101, NOW)
    assert form == ["M", "G", "M", "B", "G"]
    assert ids == ["5", "4", "3", "2", "1"]
    assert recent_form(rows[:3], 101, NOW) == (None, [])


def test_split_groups_cannot_be_compared_as_one_table():
    tables = [
        {
            "league": {
                "name": "Cup groups",
                "standings": [
                    [{"team": {"id": 101}, "rank": 1, "points": 6}],
                    [{"team": {"id": 202}, "rank": 1, "points": 6}],
                ],
            }
        }
    ]
    assert shared_standings(tables, 101, 202) is None


def test_partial_form_and_table_errors_leave_real_fixture_intact():
    class Limited(FakeClient):
        def get(self, endpoint, **params):
            if endpoint == "standings" or "last" in params:
                raise ProviderError("Plan restriction")
            return super().get(endpoint, **params)

    raw = APIFootballSource(Limited(), "Galatasaray", "Turkey").load(NOW)
    f = raw["fixtures"][0]
    assert f["demo"] is False
    assert "home_form" not in f and "home_standing" not in f
    assert set(raw["warnings"]) == {
        "home_form_unavailable",
        "away_form_unavailable",
        "standings_unavailable",
    }


def test_provider_cache_avoids_repeated_requests_and_never_saves_key(tmp_path):
    calls = []

    def opener(request, **kwargs):
        calls.append(request)
        return BytesIO(
            json.dumps(
                {"errors": {}, "paging": {"total": 1}, "response": [{"team": {"id": 101}}]}
            ).encode()
        )

    client = Client("not-a-real-test-key", tmp_path, opener=opener)
    assert client.get("teams", search="Galatasaray") == client.get("teams", search="Galatasaray")
    assert len(calls) == 1
    assert "not-a-real-test-key" not in next(tmp_path.glob("*.json")).read_text()


def test_missing_key_and_api_error_are_not_cached(tmp_path):
    with pytest.raises(ProviderError, match="not configured"):
        Client("", tmp_path)

    def opener(*args, **kwargs):
        return BytesIO(
            json.dumps({"errors": {"plan": "restricted season"}, "response": []}).encode()
        )

    with pytest.raises(ProviderError, match="rejected"):
        Client("not-a-real-test-key", tmp_path, opener=opener).get("fixtures", next=20, team=101)
    assert list(tmp_path.iterdir()) == []
