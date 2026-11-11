"""Experimental, smoothed team goal-rate Poisson baseline. Not a betting model."""

import math

from .domain import timestamp


def predict(history, home, away, cutoff, minimum=3, maximum=None):
    rows = [m for m in history if timestamp(m["played_at"]) < cutoff]
    for m in rows:
        for key in ("home_goals", "away_goals"):
            if type(m[key]) is not int or m[key] < 0:
                raise ValueError("Goals must be non-negative integers")

    def team_rates(team):
        games = [m for m in rows if team in (m["home"], m["away"])]
        if maximum is not None:
            games = sorted(games, key=lambda m: timestamp(m["played_at"]), reverse=True)[:maximum]
        if len(games) < minimum:
            return None
        scored = sum(m["home_goals"] if m["home"] == team else m["away_goals"] for m in games)
        conceded = sum(m["away_goals"] if m["home"] == team else m["home_goals"] for m in games)
        # Two pseudo-matches at 1.3 goals prevent extreme zero rates in small samples.
        return (scored + 2.6) / (len(games) + 2), (conceded + 2.6) / (len(games) + 2), len(games)

    h, a = team_rates(home), team_rates(away)
    if h is None or a is None:
        return None
    lh, la = (h[0] + a[1]) / 2, (a[0] + h[1]) / 2
    ph = [math.exp(-lh) * lh**k / math.factorial(k) for k in range(30)]
    pa = [math.exp(-la) * la**k / math.factorial(k) for k in range(30)]
    probabilities = [0.0, 0.0, 0.0]
    best = (0.0, 0, 0)
    for i, p in enumerate(ph):
        for j, q in enumerate(pa):
            joint = p * q
            probabilities[0 if i > j else 1 if i == j else 2] += joint
            best = max(best, (joint, i, j))
    total = sum(probabilities)
    return {
        "home_win": probabilities[0] / total,
        "draw": probabilities[1] / total,
        "away_win": probabilities[2] / total,
        "most_likely_score": f"{best[1]}-{best[2]}",
        "home_samples": h[2],
        "away_samples": a[2],
        "method": "smoothed-poisson-v0",
        "training_cutoff": cutoff.isoformat(),
        "experimental": True,
    }


def backtest(history):
    ordered = sorted(history, key=lambda m: timestamp(m["played_at"]))
    scores, baseline = [], []
    for match in ordered:
        cutoff = timestamp(match["played_at"])
        result = predict(ordered, match["home"], match["away"], cutoff)
        if result is None:
            continue
        target = (
            0
            if match["home_goals"] > match["away_goals"]
            else 1
            if match["home_goals"] == match["away_goals"]
            else 2
        )
        probs = [result["home_win"], result["draw"], result["away_win"]]
        scores.append(sum((p - int(k == target)) ** 2 for k, p in enumerate(probs)))
        baseline.append(sum((1 / 3 - int(k == target)) ** 2 for k in range(3)))
    return {
        "evaluated_matches": len(scores),
        "brier_score": sum(scores) / len(scores) if scores else None,
        "uniform_baseline_brier": sum(baseline) / len(baseline) if baseline else None,
        "protocol": "walk-forward; strictly earlier kickoffs; lower Brier is better",
        "limitation": "Baseline ignores team strength adjustments, injuries, lineups and home advantage.",
    }
