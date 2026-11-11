"""Display estimates and data coverage labels; these are not accuracy ratings."""

import math

from .domain import timestamp


def prediction_metrics(result, now):
    if not result:
        return None
    prediction = result["prediction"]
    values = [prediction[key] for key in ("home_win", "draw", "away_win")]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
           or not 0 <= v <= 1 for v in values) or abs(sum(values) - 1) > 1e-6:
        raise ValueError("Invalid prediction probabilities")
    percentages = [math.floor(v * 100) for v in values]
    # Largest remainders keep the three displayed percentages at exactly 100%.
    order = sorted(range(3), key=lambda i: values[i] * 100 - percentages[i], reverse=True)
    for i in order[:100 - sum(percentages)]:
        percentages[i] += 1
    samples = min(prediction["home_samples"], prediction["away_samples"])
    ages = []
    for source in result.get("history_sources", []):
        try:
            ages.append((now - timestamp(source["fetched_at"])).total_seconds())
        except (KeyError, TypeError, ValueError):
            ages.append(float("inf"))
    age = max(ages) if len(ages) >= 2 else float("inf")
    quality = "low"
    if 0 <= age <= 21600 and samples >= 10:
        quality = "high"
    elif 0 <= age <= 86400 and samples >= 5:
        quality = "medium"
    return dict(zip(("home", "draw", "away"), percentages), quality=quality,
                score=prediction.get("most_likely_score", "—"),
                minimum_samples=samples, history_age_seconds=age if math.isfinite(age) else None,
                quality_policy="coverage-freshness-v1",
                quality_meaning="Data coverage and freshness, not prediction accuracy")
