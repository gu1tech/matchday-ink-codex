# Experimental prediction

The probabilities and score come from Python, not a language model. OpenAI only writes a short explanation from supplied facts.

Use up to ten verified completed matches per team from the same competition and season, strictly before the target kickoff. At least three per team are required. Extra-time and penalty outcomes are excluded from the 90-minute training sample.

For N games, goals for GF and goals against GA:

```text
attack  = (GF + 2.6) / (N + 2)
defence = (GA + 2.6) / (N + 2)
expected_home_goals = (home_attack + away_defence) / 2
expected_away_goals = (away_attack + home_defence) / 2
```

Independent Poisson distributions over 0–29 goals generate score probabilities. Sum cells for home/draw/away; choose the highest individual cell for the score prediction. The most likely score need not agree with the outcome having the largest aggregate probability. Display percentages are rounded to total 100.

Limitations: no opponent-strength adjustment, calibrated home advantage, injuries, lineups or demonstrated predictive accuracy. Coverage quality describes input coverage/freshness, not model confidence. Synthetic backtests test mechanics, not real-world performance.

OpenAI uses structured output, bounded output tokens, a request timeout and no SDK retries. Results cache for 24 hours per fixture/model/prompt/kickoff. Failed automatic calls cool down for an hour; manual retries have a one-minute guard. This is not a once-per-fixture billing guarantee. The legacy daily wording describes current AI controls, while device rollover separately follows match completion.
