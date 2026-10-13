Matched questions: 200

| Condition | Accuracy | Gained / lost vs baseline | Exact McNemar p | Paired bootstrap 95% CI (pp) |
|---|---|---|---|---|
| 1 sample, 1,024 tokens, temp 0 (historical baseline) | 60.5% | 0 / 0 | — | — |
| Pipeline: first of 3 samples, 2,048 tokens, temp 0.7 | 78.5% | 42 / 6 | 1e-07 | [12.0, 24.5] |
| Pipeline: 3 samples x 2,048 tokens, vote, rescue, retrieval arbitration | 81.5% | 46 / 4 | 4.5e-10 | [15.0, 27.5] |
| 1 sample, 2,048 tokens, temp 0 | 75.5% | 35 / 5 | 1.4e-06 | [9.5, 21.0] |
| 1 sample, 4,096 tokens, temp 0 | 84.5% | 51 / 3 | 2.9e-12 | [18.0, 30.5] |
