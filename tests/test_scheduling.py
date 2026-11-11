import json
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest

from matchday.device_setup import config_command
from matchday.domain import timestamp
from matchday.scheduling import kickoff_due, poll_after
from matchday.service import Dashboard

KICKOFF = timestamp("2030-11-07T18:00:00Z")


def fixture(identity, kickoff):
    return dict(id=identity, kickoff=kickoff.isoformat(), home="Galatasaray", away=identity,
                competition="test", venue="test venue", source="test", demo=False, status="TIMED")


def test_deadline_is_kickoff_instead_of_daily_and_caps_safety_checks():
    state = {"fixture": fixture("first", KICKOFF), "stale": False}
    assert poll_after(state, KICKOFF - timedelta(days=2)) == 21600
    assert poll_after(state, KICKOFF - timedelta(hours=1)) == 3600
    assert poll_after(state, KICKOFF - timedelta(milliseconds=100)) == 1
    assert not kickoff_due(state, KICKOFF - timedelta(microseconds=1))
    assert kickoff_due(state, KICKOFF)
    assert poll_after(dict(state, stale=True), KICKOFF) == 60


def test_rollover_selects_next_match_at_exact_kickoff_without_waiting_for_ai(tmp_path):
    path = tmp_path / "schedule.json"
    first, second = fixture("first", KICKOFF), fixture("second", KICKOFF + timedelta(days=4))
    path.write_text(json.dumps({"demo": False, "source_updated_at": KICKOFF.isoformat(),
                               "fixtures": [first, second]}))
    dashboard = Dashboard(path)
    assert dashboard.refresh(KICKOFF - timedelta(seconds=1))
    assert dashboard.read()[0][0]["fixture"]["id"] == "first"

    class SlowAI:
        def run(self, *args):
            pytest.fail("Rollover must publish the next match without waiting for AI")

    dashboard.prediction_engine = SlowAI()
    assert not dashboard.rollover(KICKOFF - timedelta(microseconds=1))
    assert dashboard.rollover(KICKOFF)
    state, frame, _ = dashboard.read()[0]
    assert state["fixture"]["id"] == "second"
    assert state["ai_note"] is None and dashboard.ai_pending
    assert len(frame) == 9472
    assert not dashboard.rollover(KICKOFF + timedelta(seconds=1))


def test_failed_boundary_refresh_keeps_last_good_data_and_throttles_retry(tmp_path):
    path = tmp_path / "schedule.json"
    path.write_text(json.dumps({"demo": False, "source_updated_at": KICKOFF.isoformat(),
                               "fixtures": [fixture("first", KICKOFF)]}))
    dashboard = Dashboard(path)
    assert dashboard.refresh(KICKOFF - timedelta(seconds=1))
    path.write_text("broken")
    assert not dashboard.rollover(KICKOFF)
    snapshot, error = dashboard.read()
    assert snapshot[0]["stale"] and error == "JSONDecodeError"
    assert snapshot[0]["fixture"]["id"] == "first"
    # Fixing source doesn't bypass the one-minute failure backoff.
    path.write_text(json.dumps({"demo": False, "source_updated_at": KICKOFF.isoformat(),
                               "fixtures": [fixture("second", KICKOFF + timedelta(days=1))]}))
    assert not dashboard.rollover(KICKOFF + timedelta(seconds=59))
    assert dashboard.rollover(KICKOFF + timedelta(seconds=60))


def test_device_accepts_kickoff_mode_without_resending_password():
    assert config_command("Home", "password123", "http://192.168.1.2/v1/frame.bin", 0).endswith(b" 0\n")
    for interval in (True, -1, 1, 179, 86401):
        with pytest.raises(ValueError):
            config_command("Home", "password123", "http://192.168.1.2/v1/frame.bin", interval)


def test_native_device_polling_honours_boundary_and_handles_missing_headers(tmp_path):
    compiler = shutil.which("clang++") or shutil.which("g++")
    if not compiler:
        pytest.skip("C++ compiler unavailable")
    source = tmp_path / "poll.cpp"
    source.write_text('''#include "polling.h"
int main() {
  if (matchdayInkPollSeconds(0, 21600) != 21600) return 1;
  if (matchdayInkPollSeconds(0, 1) != 1) return 2;
  if (matchdayInkPollSeconds(86400, 30) != 30) return 3;
  if (matchdayInkPollSeconds(300, 21600) != 300) return 4;
  if (matchdayInkPollSeconds(0, 0) != 3600) return 5;
  if (matchdayInkPollSeconds(0, -1) != 3600) return 6;
  if (matchdayInkPollSeconds(0, 2147483647) != 3600) return 7;
  // Signed deadline comparison remains valid across millis wraparound.
  uint32_t now = 0xfffffff0u, due = now + matchdayInkPollSeconds(0, 1) * 1000u;
  if ((int32_t)(now - due) >= 0) return 8;
  if ((int32_t)((now + 1000u) - due) < 0) return 9;
}''')
    root = Path(__file__).resolve().parents[1]
    binary = tmp_path / "poll"
    subprocess.run([compiler, "-std=c++11", "-I", str(root / "firmware/MatchdayInk"),
                    str(source), "-o", str(binary)], check=True, capture_output=True)
    subprocess.run([str(binary)], check=True)
