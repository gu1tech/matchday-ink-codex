import json
from datetime import timedelta
from io import BytesIO

from matchday.domain import timestamp
from matchday.lifecycle import MatchLifecycle
from matchday.service import Dashboard

START = timestamp("2030-11-07T18:00:00Z")
EVENT = {"event_id": "123", "league": "tur.1", "teams": {"home": {"id": "1"}, "away": {"id": "2"}}}


def fixture(id="current", start=START):
    return dict(
        id=id,
        home="Home",
        away="Away",
        kickoff=start.isoformat(),
        competition="tur.1",
        venue="Venue",
        source="test",
        status="TIMED",
        demo=False,
        provenance={"espn_event": EVENT},
    )


def payload(done=False):
    return {
        "header": {
            "id": "123",
            "competitions": [
                {
                    "competitors": [
                        {"homeAway": "home", "team": {"id": "1"}},
                        {"homeAway": "away", "team": {"id": "2"}},
                    ],
                    "status": {"type": {"completed": done, "state": "post" if done else "in"}},
                }
            ],
        }
    }


def test_five_minute_buffer_starts_after_verified_completion_and_survives_restart(tmp_path):
    calls = []

    def opener(*args, **kwargs):
        calls.append(1)
        return BytesIO(json.dumps(payload(True)).encode())

    life = MatchLifecycle(tmp_path, opener)
    life.save({"fixture": fixture()})
    assert life.check(fixture(), START)["hold"]
    assert not calls
    end = START + timedelta(minutes=115)
    assert life.check(fixture(), end)["phase"] == "buffer"
    restarted = MatchLifecycle(tmp_path, opener)
    assert restarted.check(fixture(), end + timedelta(minutes=4, seconds=59))["hold"]
    assert not restarted.check(fixture(), end + timedelta(minutes=5))["hold"]
    assert len(calls) == 1


def test_live_extra_time_and_feed_failure_never_become_assumed_full_time(tmp_path):
    def opener(*args, **kwargs):
        return BytesIO(json.dumps(payload(False)).encode())

    life = MatchLifecycle(tmp_path, opener)
    assert life.check(fixture(), START + timedelta(minutes=140))["phase"] == "in_progress"

    def failed(*args, **kwargs):
        raise OSError("offline")

    life.opener = failed
    state = life.check(fixture(), START + timedelta(minutes=160))
    assert state["hold"] and state["phase"] == "status_unavailable"


def test_periodic_refresh_keeps_current_match_through_full_time_buffer(tmp_path):
    schedule = tmp_path / "schedule.json"
    schedule.write_text(
        json.dumps(
            {
                "demo": False,
                "source_updated_at": START.isoformat(),
                "fixtures": [fixture(), fixture("next", START + timedelta(days=4))],
            }
        )
    )

    def opener(*args, **kwargs):
        return BytesIO(json.dumps(payload(True)).encode())

    life = MatchLifecycle(tmp_path, opener)
    dashboard = Dashboard(schedule, lifecycle=life)
    assert dashboard.refresh(START - timedelta(seconds=1))
    assert dashboard.refresh(START)
    assert dashboard.read()[0][0]["fixture"]["id"] == "current"
    end = START + timedelta(minutes=115)
    assert dashboard.refresh(end)
    # A backend restart must not let next_fixture() skip an ongoing buffer.
    dashboard = Dashboard(schedule, lifecycle=MatchLifecycle(tmp_path, opener))
    assert dashboard.refresh(end + timedelta(minutes=4, seconds=59))
    assert dashboard.read()[0][0]["fixture"]["id"] == "current"
    assert dashboard.refresh(end + timedelta(minutes=5))
    assert dashboard.read()[0][0]["fixture"]["id"] == "next"
