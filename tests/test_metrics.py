from datetime import timedelta

import pytest

from matchday.domain import timestamp
from matchday.metrics import prediction_metrics

NOW = timestamp("2026-11-05T12:00:00Z")


def result(samples=10, age=0, values=(0.336, 0.336, 0.328)):
    return {
        "prediction": dict(
            zip(("home_win", "draw", "away_win"), values),
            home_samples=samples,
            away_samples=samples,
        ),
        "history_sources": [
            {"fetched_at": (NOW - timedelta(seconds=age)).isoformat()} for _ in range(2)
        ],
    }


def test_rounding_preserves_exactly_one_hundred_percent():
    m = prediction_metrics(result(), NOW)
    assert (m["home"], m["draw"], m["away"]) == (34, 33, 33)
    assert sum(m[k] for k in ("home", "draw", "away")) == 100


@pytest.mark.parametrize(
    "samples,age,quality",
    [
        (10, 21600, "high"),
        (10, 21601, "medium"),
        (5, 86400, "medium"),
        (4, 0, "low"),
        (10, 86401, "low"),
        (10, -1, "low"),
    ],
)
def test_quality_is_explicit_sample_and_freshness_policy(samples, age, quality):
    assert prediction_metrics(result(samples, age), NOW)["quality"] == quality


def test_unknown_provenance_cannot_receive_high_quality():
    r = result()
    r["history_sources"] = []
    assert prediction_metrics(r, NOW)["quality"] == "low"
    with pytest.raises(ValueError):
        prediction_metrics(result(values=(float("nan"), 0.5, 0.5)), NOW)
