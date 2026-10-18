# Evaluation report

Logs: data\agent_20261018_152640\log.jsonl

Trials with an outcome: **25 of 25 planned**

## Pass criteria (fixed before the data)

| Criterion | Result | Target | |
|---|---|---|---|
| C1 falls in the GREEN zone | 0 | <= 0 | PASS |
| C2a accuracy on clear trials (P < 10% or > 70%) | 100% of 14 | >= 85% | PASS |
| C2b falls inside the 90% interval of the predicted number | 12 falls | 6-11 (sum of P 8.5) | FAIL |
| C3 Brier score | 0.125 | <= 0.2 | PASS |
| C4 trials with an outcome | 25 | >= 20 | PASS |

**Overall: FAIL**

## Metrics

- Overall accuracy (P >= 50% predicts a fall; not a criterion, Test 2 had 82%): 84% (25 trials); Brier score: 0.125
- Falls: 12 observed, 8.5 predicted (sum of P), 90% interval 6-11
- Clear trials (P < 10% or > 70%): 14, accuracy 100%

| Zone | Trials | Falls | Fall rate | Mean P(fall) |
|---|---|---|---|---|
| GREEN | 8 | 0 | 0% | 3% |
| YELLOW | 9 | 4 | 44% | 25% |
| RED | 8 | 8 | 100% | 75% |

### Calibration

| P(fall) range | Trials | Mean predicted | Observed fall rate |
|---|---|---|---|
| 0%-10% | 9 | 4% | 0% |
| 10%-30% | 5 | 20% | 40% |
| 30%-50% | 3 | 39% | 67% |
| 50%-70% | 3 | 60% | 100% |
| 70%-90% | 3 | 80% | 100% |
| 90%-100% | 2 | 92% | 100% |

### Operations

- Placement error (boxes that stood, |check deviation|): mean 0.6 cm, median 0.6 cm, max 1.7 cm; 10/13 within 1 cm
- Decision time on AWS Lambda (round trip): median 7.6 s, max 11.1 s (25 decisions)
- Retakes: 0; f/p questions: 0; laptop fallbacks: 0; outcomes corrected by the worker: 0

## Failure-case candidates

- falls in GREEN: none
- wrong prediction: T01, T16, T17, T25
- largest |P - outcome|: T16, T17, T01
- outcome corrected by the worker: none
- placed > 1.5 cm off: T06
- laptop fallback: none
- retake or f/p question: none
