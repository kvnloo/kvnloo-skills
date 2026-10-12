# ABAB world JSON

Persist under `.hermes/abab/<slug>.json`. Do not dump full source texts; store
references (URL, path, commit, DOI).

```
objective, constraints[], metrics[], baseline
concepts{}, mechanisms{}, contradictions[], unresolved[]
hypotheses[]: id, claim, mechanism, predictions[], falsifiers[],
  eig, impact, decision_change, transferability, cost, status, rival_of
evidence[]: id, claim, source, source_class, scope, confidence, counter
experiments[]: hypothesis, intervention, baseline, prediction, metric,
  control, ablation, holdout, rollback, promotion, outcome, measured
strategy_log[], dead_ends[], no_update_streak, wave, wave_budget, deep, loop
```

`source_class`: measurement | primary | official | analysis | secondary

Hypothesis status: open | rival | pruned | promoted | deferred

Engine: `scripts/abab_state.py` (`priority`, `next_a`, `apply_mutation`,
`stop_reason`, `learn_payload`).
