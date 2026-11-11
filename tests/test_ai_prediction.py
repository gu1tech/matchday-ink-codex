import json
from datetime import timedelta
from types import SimpleNamespace

import pytest

from matchday.ai_prediction import AISettings, PredictionEngine, generate_analysis
from matchday.domain import timestamp
from matchday.providers.api_football import ProviderError
from matchday.providers.history import completed_matches
from matchday.service import Dashboard

NOW = timestamp("2026-11-05T12:00:00Z")
KEY = "sk-test-not-a-real-key-1234567890"


def fixture(**overrides):
    return dict(id="verified-event", home="Home Club", away="Away Club", competition="tur.1",
                kickoff="2026-11-07T16:00:00Z", demo=False, venue="Venue", status="TIMED",
                source="test source", **overrides)


class History:
    calls = 0

    def load(self, fixture, now):
        self.calls += 1
        return {"team_ids": {"home": "1", "away": "2"}, "sources": [{"provider": "test"}],
                "matches": [{"home": "1", "away": "2", "home_goals": i % 3,
                             "away_goals": i % 2, "played_at": (now - timedelta(days=i + 1)).isoformat()}
                            for i in range(10)]}


def analysis(facts, config):
    assert config["api_key"] == KEY
    assert "api_key" not in json.dumps(facts)
    return {"summary": "Closely matched", "explanation": "Small sample; uncalibrated model.",
            "usage": {"total_tokens": 100}, "response_id": "test-response"}


def enabled(tmp_path):
    settings = AISettings(tmp_path)
    settings.save(KEY, "gpt-4.1-mini", True)
    return settings


def test_key_stays_private_and_never_appears_in_public_status(tmp_path):
    settings = enabled(tmp_path)
    assert settings.config_path.stat().st_mode & 0o777 == 0o600
    assert settings.config_path.parent.stat().st_mode & 0o777 == 0o700
    assert settings.status()["configured"]
    assert KEY not in json.dumps(settings.status())
    settings.save("", "gpt-4.1-mini", False)
    assert settings.config()["api_key"] == KEY
    assert not settings.status()["enabled"]


def test_disabled_or_stale_data_never_spends_api_credits(tmp_path):
    def forbidden(*args):
        pytest.fail("API must not run")

    engine = PredictionEngine(tmp_path, History(), forbidden)
    assert engine.run(fixture(), now=NOW)[0]["state"] == "disabled"
    enabled(tmp_path)
    assert engine.run(fixture(), stale=True, now=NOW)[0]["state"] == "waiting"
    assert engine.run(None, now=NOW)[0]["state"] == "waiting"


def test_one_analysis_is_reused_across_refreshes_and_server_restarts(tmp_path):
    settings = enabled(tmp_path)
    history = History()
    calls = []

    def generator(facts, config):
        calls.append(facts)
        return analysis(facts, config)

    engine = PredictionEngine(tmp_path, history, generator)
    assert engine.requested()
    _, first = engine.run(fixture(), now=NOW)
    assert first["prediction"]["home_samples"] == 10
    assert not engine.requested()
    settings.request()
    assert engine.requested()
    assert engine.run(fixture(), now=NOW + timedelta(hours=23))[1] == first
    restarted = PredictionEngine(tmp_path, history, generator)
    assert restarted.run(fixture(), now=NOW + timedelta(hours=23))[1] == first
    assert len(calls) == history.calls == 1
    assert restarted.run(fixture(), now=NOW + timedelta(days=1))[1] != first
    assert len(calls) == 2


def test_new_fixture_never_reuses_previous_match_prediction(tmp_path):
    enabled(tmp_path)
    calls = []

    def generator(facts, config):
        calls.append(facts)
        return analysis(facts, config)

    engine = PredictionEngine(tmp_path, History(), generator)
    engine.run(fixture(), now=NOW)
    changed = dict(fixture(), id="next-event", away="Different Club")
    _, result = engine.run(changed, now=NOW)
    assert result["fixture"]["id"] == "next-event"
    assert len(calls) == 2


def test_missing_history_does_not_invent_prediction_or_call_openai(tmp_path):
    enabled(tmp_path)

    class Empty:
        def load(self, fixture, now):
            return {"matches": [], "team_ids": {"home": "1", "away": "2"}}

    def forbidden(*args):
        pytest.fail("No paid call without enough history")

    status, result = PredictionEngine(tmp_path, Empty(), forbidden).run(fixture(), now=NOW)
    assert status["state"] == "insufficient_data" and result is None


def test_errors_are_redacted_and_attempts_throttled_even_after_restart(tmp_path):
    enabled(tmp_path)
    calls = []

    def failure(*args):
        calls.append(1)
        raise RuntimeError("request body contains " + KEY)

    engine = PredictionEngine(tmp_path, History(), failure)
    status, result = engine.run(fixture(), now=NOW)
    assert result is None and status["state"] == "error"
    assert KEY not in json.dumps(status)
    engine = PredictionEngine(tmp_path, History(), failure)
    assert engine.run(fixture(), now=NOW + timedelta(minutes=59))[0]["state"] == "retry_later"
    assert len(calls) == 1


def test_manual_retry_is_bounded_and_cannot_replay_after_restart(tmp_path):
    settings = enabled(tmp_path)
    calls = []

    def failure(*args):
        calls.append(1)
        raise RuntimeError("failure")

    engine = PredictionEngine(tmp_path, History(), failure)
    engine.run(fixture(), now=NOW)
    settings.request(manual=True)
    engine.run(fixture(), now=NOW + timedelta(seconds=30))
    assert len(calls) == 1
    settings.request(manual=True)
    engine.run(fixture(), now=NOW + timedelta(seconds=61))
    assert len(calls) == 2
    restarted = PredictionEngine(tmp_path, History(), failure)
    restarted.run(fixture(), now=NOW + timedelta(minutes=2))
    assert len(calls) == 2


def test_quota_error_records_only_allowlisted_provider_code(tmp_path):
    enabled(tmp_path)

    class RateLimitError(Exception):
        code = "insufficient_quota"

    def failure(*args):
        raise RateLimitError(KEY)

    engine = PredictionEngine(tmp_path, History(), failure)
    status, result = engine.run(fixture(), now=NOW)
    assert result is None and status["provider_code"] == "insufficient_quota"
    assert "credits" in status["message"]
    status, _ = engine.run(fixture(), now=NOW + timedelta(minutes=5))
    assert "credits" in status["message"] and KEY not in json.dumps(status)


def test_openai_request_uses_structured_output_and_no_remote_storage():
    captured = {}

    def parse(**kwargs):
        captured.update(kwargs)
        parsed = kwargs["text_format"](summary="Home edge", explanation="Small sample; uncalibrated.")
        return SimpleNamespace(output_parsed=parsed, id="test", usage=None)

    client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    result = generate_analysis({"baseline": {"home_win": 0.6}}, {"model": "test"}, client)
    assert result["summary"] == "Home edge"
    assert captured["store"] is False and captured["max_output_tokens"] == 300
    assert KEY not in captured["input"]


@pytest.mark.parametrize("summary", ["Home 99%", "Win 2-0", "A" * 33, "", "Home\nedge"])
def test_invalid_ai_short_notes_are_rejected(summary):
    def parse(**kwargs):
        return SimpleNamespace(output_parsed=kwargs["text_format"](
            summary=summary, explanation="Small sample."), id="test", usage=None)

    with pytest.raises(ValueError):
        generate_analysis({}, {"model": "test"}, SimpleNamespace(responses=SimpleNamespace(parse=parse)))


def event(identity="one", date="2026-11-01T12:00:00Z", completed=True, name="STATUS_FULL_TIME", score=2):
    return {"id": identity, "date": date, "season": {"year": 2026}, "competitions": [{
        "status": {"type": {"completed": completed, "name": name}},
        "competitors": [{"homeAway": "home", "team": {"id": "1"}, "score": {"value": score}},
                        {"homeAway": "away", "team": {"id": "2"}, "score": {"value": 1}}]}]}


def test_history_refuses_live_future_extra_time_invalid_and_duplicate_rows():
    payload = {"team": {"id": "1"}, "season": {"year": 2026}, "events": [
        event(), event(), event("live", completed=False), event("extra", name="STATUS_FINAL_AET"),
        event("future", date="2026-11-06T12:00:00Z"), event("negative", score=-1),
        event("fraction", score=1.5)]}
    rows = completed_matches(payload, "1", NOW, 2026)
    assert len(rows) == 1 and rows[0]["id"] == "one"
    assert rows[0]["home_goals"] == 2
    with pytest.raises(ProviderError):
        completed_matches(payload, "wrong", NOW, 2026)
    with pytest.raises(ProviderError):
        completed_matches(payload, "1", NOW, 2025)


def test_prediction_reaches_dashboard_and_render_without_exposing_key(tmp_path):
    enabled(tmp_path)
    path = tmp_path / "schedule.json"
    from datetime import UTC, datetime
    now = datetime.now(UTC)
    f = dict(fixture(), kickoff=(now + timedelta(days=2)).isoformat())
    path.write_text(json.dumps({"demo": False, "source_updated_at": now.isoformat(), "fixtures": [f]}))
    dashboard = Dashboard(path, prediction_engine=PredictionEngine(tmp_path, History(), analysis))
    assert dashboard.refresh()
    snapshot, error = dashboard.read()
    assert error is None and snapshot[0]["ai_note"].startswith("Closely matched · ")
    assert snapshot[0]["prediction"]["experimental"]
    assert len(snapshot[1]) == 9472
    assert KEY not in json.dumps(snapshot[0])
