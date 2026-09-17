# ABAB ↔ /learn

`/learn` (Hermes `agent/learn_prompt.py`) authors skills from described
workflows. ABAB must not call it on every wave.

Call `/learn` only when `learn_payload()` has `validated_experiments` and
`skip_if_no_measurement` is false. Pass:

- surviving strategies (A-reframes that led to keep)
- failed experiments and dead ends
- promoted mechanisms

`require_task_validation_before_default: true` — a new heuristic stays a
candidate until a later ABAB or task benchmark keeps it. No circular
self-modification.

Do not teach `/learn` to weaken ABAB's promotion bar.
