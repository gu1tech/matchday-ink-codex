import json
from datetime import UTC, datetime

import pytest
from PIL import Image

from matchday.domain import next_fixture, timestamp, validate_fixture
from matchday.prediction import backtest, predict
from matchday.render import PALETTE, encode_frame, render
from matchday.service import Dashboard
from matchday.weather import forecast


def fixture(**overrides):
    base = dict(
        id="demo",
        home="Galatasaray",
        away="Example",
        competition="DEMO",
        kickoff="2030-07-01T20:00:00Z",
        venue="Example stadium",
        status="TIMED",
        source="synthetic",
        demo=True,
    )
    return dict(base, **overrides)


def history():
    return [
        dict(
            home="A",
            away="B",
            home_goals=i % 3,
            away_goals=(i + 1) % 2,
            played_at=f"2025-01-{i + 1:02d}T18:00:00Z",
        )
        for i in range(12)
    ]


def test_timezone_required():
    with pytest.raises(ValueError):
        timestamp("2026-11-01T20:00:00")


def test_cancelled_rejected():
    with pytest.raises(ValueError):
        validate_fixture(fixture(status="CANCELLED"))


def test_next_fixture_sorted_and_past_excluded():
    now = timestamp("2029-01-01T00:00:00Z")
    early = fixture(kickoff="2030-01-01T00:00:00Z")
    assert next_fixture([fixture(), early, fixture(kickoff="2020-01-01T00:00:00Z")], now) == early
    assert next_fixture([], now) is None


def test_coordinates_require_pair():
    with pytest.raises(ValueError):
        validate_fixture(fixture(latitude=41.1))


def test_dublin_dst():
    from zoneinfo import ZoneInfo

    assert timestamp("2030-07-01T20:00:00Z").astimezone(ZoneInfo("Europe/Dublin")).hour == 21
    assert timestamp("2030-01-01T20:00:00Z").astimezone(ZoneInfo("Europe/Dublin")).hour == 20


def test_render_uses_only_hardware_palette():
    image = render(fixture())
    assert image.size == (296, 128)
    assert {image.getpixel((x, y)) for x in range(296) for y in range(128)} <= set(PALETTE)
    assert len(encode_frame(image)) == 9472


def test_frame_orientation_and_colour_order():
    image = Image.new("RGB", (296, 128), PALETTE[1])
    # First physical byte encodes logical pixels (0,127), (0,126), (0,125), (0,124).
    for y, c in zip((127, 126, 125, 124), PALETTE):
        image.putpixel((0, y), c)
    frame = encode_frame(image)
    assert frame[0] == 0b00011011
    assert frame[1] == 0b01010101
    image.putpixel((295, 0), PALETTE[3])
    assert encode_frame(image)[-1] & 3 == 3


def test_unknown_palette_rejected():
    with pytest.raises(ValueError):
        encode_frame(Image.new("RGB", (296, 128), (0, 255, 0)))


def test_prediction_no_future_leakage():
    rows = history()
    cutoff = timestamp("2025-01-10T18:00:00Z")
    result = predict(rows, "A", "B", cutoff)
    rows[-1]["home_goals"] = 99
    rows[9]["away_goals"] = 99  # Equal kickoff must also be excluded.
    assert predict(rows, "A", "B", cutoff) == result
    assert result["home_samples"] == 9
    assert abs(sum(result[k] for k in ("home_win", "draw", "away_win")) - 1) < 1e-10


def test_prediction_missing_history_not_fabricated():
    assert predict([], "A", "B", datetime.now(UTC)) is None
    assert backtest([])["evaluated_matches"] == 0
    assert backtest([])["brier_score"] is None


def test_walk_forward_evaluates_only_after_warmup():
    result = backtest(history())
    assert result["evaluated_matches"] == 9
    assert 0 <= result["brier_score"] <= 2


def test_last_good_snapshot_survives_corrupt_schedule(tmp_path):
    path = tmp_path / "schedule.json"
    path.write_text(json.dumps({"demo": True, "fixtures": [fixture()]}))
    dashboard = Dashboard(path)
    assert dashboard.refresh()
    first = dashboard.read()[0]
    path.write_text("broken")
    assert not dashboard.refresh()
    snapshot, error = dashboard.read()
    assert snapshot[0]["fixture"] == first[0]["fixture"]
    assert snapshot[0]["stale"] is True
    assert snapshot[1] != first[1]  # Visible stale badge.
    assert error == "JSONDecodeError"


def test_live_schedule_requires_provenance(tmp_path):
    path = tmp_path / "schedule.json"
    path.write_text(json.dumps({"demo": False, "fixtures": [fixture(demo=False)]}))
    dashboard = Dashboard(path)
    assert not dashboard.refresh()
    assert dashboard.read()[0] is None


def test_weather_outside_horizon_never_requests():
    def fail(*args, **kwargs):
        raise AssertionError("Should not fetch")

    f = fixture(latitude=41.1, longitude=28.9)
    assert forecast(f, now=timestamp("2029-01-01T00:00:00Z"), opener=fail) is None


def test_weather_uses_nearest_kickoff_hour():
    from io import StringIO

    kickoff = timestamp("2030-07-01T20:00:00Z")
    raw = {
        "hourly": {
            "time": [kickoff.timestamp() - 3600, kickoff.timestamp()],
            "temperature_2m": [18, 16],
            "precipitation_probability": [10, 40],
        }
    }

    def opener(url, timeout):
        assert "timezone=UTC" in url
        assert "latitude=41.1" in url
        return StringIO(json.dumps(raw))

    result = forecast(
        fixture(latitude=41.1, longitude=28.9), now=timestamp("2030-07-01T00:00:00Z"), opener=opener
    )
    assert result["temperature_c"] == 16
    assert result["rain_probability"] == 40


def test_team_names_with_turkish_accents_fit_vertical_slots():
    from matchday.render import fitted

    text, face = fitted("İSTANBUL BAŞAKŞEHİR", 27, 278, minimum=17, weight="Bold", height=21)
    assert face.getbbox(text, anchor="lt")[3] <= 21
    assert face.getlength(text) <= 278


def test_scoreboard_long_names_stay_inside_team_columns():
    from matchday.render import fitted

    for value in ("GALATASARAY", "MANCHESTER UNITED", "BORUSSIA MÖNCHENGLADBACH"):
        text, face = fitted(value, 23, 116, minimum=13, weight="Bold")
        assert face.getlength(text) <= 116


def test_design_variants_keep_hardware_contract():
    for layout in ("stacked", "scoreboard"):
        image = render(
            fixture(away="Örnek Rakip"),
            weather={"temperature_c": 14, "rain_probability": 35},
            layout=layout,
        )
        assert len(encode_frame(image)) == 9472
        assert image.getpixel((0, 0)) == PALETTE[3]
        assert image.getpixel((0, 127)) == PALETTE[3]


def test_dashboard_omits_venue_and_weather():
    first = render(
        fixture(venue="One stadium"), weather={"temperature_c": 14, "rain_probability": 35}
    )
    second = render(
        fixture(venue="Different stadium"), weather={"temperature_c": -2, "rain_probability": 95}
    )
    assert first.tobytes() == second.tobytes()


def test_recent_form_requires_five_known_results():
    with pytest.raises(ValueError):
        validate_fixture(fixture(home_form=["G", "B"]))
    with pytest.raises(ValueError):
        validate_fixture(fixture(away_form=["G", "B", "M", "G", "X"]))
    assert validate_fixture(fixture(home_form=["G", "B", "M", "G", "G"]))["home_form"][-1] == "G"


def test_standings_need_integer_rank_points_and_competition():
    with pytest.raises(ValueError):
        validate_fixture(fixture(home_standing={"position": 1, "points": 28}))
    with pytest.raises(ValueError):
        validate_fixture(
            fixture(
                home_standing={"position": 0, "points": 28}, standings_competition="Demo league"
            )
        )
    assert (
        validate_fixture(
            fixture(
                home_standing={"position": 7, "points": 18}, standings_competition="Demo league"
            )
        )["home_standing"]["points"]
        == 18
    )


def test_verified_current_download_is_not_stale_just_because_calendar_unchanged(tmp_path):
    from datetime import timedelta
    now = datetime.now(UTC)
    path = tmp_path / 'schedule.json'
    path.write_text(json.dumps({
        'demo': False,
        'source_updated_at': (now - timedelta(days=3)).isoformat(),
        'source_verified_at': now.isoformat(),
        'fixtures': [fixture(demo=False)],
    }))
    dashboard = Dashboard(path)
    assert dashboard.refresh()
    assert dashboard.read()[0][0]['stale'] is False
