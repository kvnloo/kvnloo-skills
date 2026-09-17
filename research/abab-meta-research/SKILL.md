---
name: abab-meta-research
description: "Use when running ABAB adaptive research loops."
version: 0.1.0
author: Kevin Rajan (kvnloo), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Research, Autoresearch, Falsification, Architecture, Optimization]
    category: research
    related_skills:
      - grounded-citations
      - academic-literature-reviews
      - high-parallel-evidence-tournaments
      - simulation-autoresearch
      - arxiv
      - plan
requires_toolsets: [terminal]
---

# ABAB Meta-Research

Adaptive two-timescale research: A improves the investigation strategy, B
executes it and mutates a compact evidence graph, C (optional) compresses a
surviving mechanism into the smallest falsifiable experiment. This is not
search-then-summarize. Maximize validated understanding per time, compute, and
complexity.

Do not duplicate `grounded-citations`, `academic-literature-reviews`,
`high-parallel-evidence-tournaments`, or `simulation-autoresearch`. Load those
when the current A-strategy needs them.

## When to Use

- Architecture, mechanism, or poorly-named problem research
- Code optimization / autoresearch with a measurable baseline
- Adversarial claim checks that may return `NO_UPDATE`
- Cross-domain structural analog search
- Deep multi-wave investigation with an adaptive stop

Don't use for: a single known-doc lookup, a plan-only request (`plan`), or a
literature review that only needs `academic-literature-reviews`.

## Prerequisites

- Hermes tools: `terminal`, `read_file`, `write_file`, `search_files`,
  `delegate_task` when parallel B-lanes help
- Skill dir: this folder. Engine:
  `python3 scripts/abab_state.py` is imported by tests; persist JSON with the
  same schema in `.hermes/abab/<slug>.json` under the active workspace
- Optional: `/learn` after a run that produced **measured** keep/revert
  outcomes — never from strategy prose alone

## How to Run

Parse the user line:

- `/abab <problem>` — default budget 8 waves, stop early
- `--deep` or `--waves 25` — budget 25, still stop on collapsed IG
- `--speed` — budget 4, prefer C as soon as a mechanism exists
- `--falsify <claim>` — start in falsification; `NO_UPDATE` is success if the
  claim survives discriminating tests
- `--architecture <problem>` — start mode architecture, still allow C

1. Write initial world JSON (objective, constraints, metrics, baseline).
2. Each wave: A (`next_a`) then B (evidence, one synthesis mutation) then
   maybe C.
3. Compact heartbeat only (see Quick Reference). No wave novels.
4. Stop via `stop_reason`. Budget is a cap, not a quota.

## Quick Reference

```
priority = eig × impact × decision_change × transferability / cost
mutations: ADD MERGE SPLIT UPGRADE DOWNGRADE PRUNE DEFER CONTRADICT
           SPAWN_EXPERIMENT SPAWN_RESEARCH_BRANCH NO_UPDATE
loops: FAST = bounded candidate → filters → verify → PROMOTE/REJECT
       SLOW = patterns → graph → highest-value uncertainty → new FAST agenda
C when experiment value > further research value
```

Heartbeat keys: CURRENT MODEL, WHAT CHANGED, WHY, WHAT FAILED, GRAPH DELTA,
HIGHEST-VALUE UNCERTAINTY, NEXT MOVE.

Final grades: established, strongly_supported, promising_unverified,
disconfirmed, unknown.

## Procedure

1. **Lock the decision.** Objective, constraints, target metrics, baseline.
   Noun → mechanism. If vocabulary is misleading, reframe before searching.
2. **A.** Highest-information next investigation. Produce: target uncertainty,
   assumption, reframe, mechanism, neighbors, evidence needed, counterexample,
   falsifier, source classes, stop. Prefer tests that distinguish rivals.
3. **B.** Execute. Parallel `delegate_task` lanes may fetch; they must not
   mutate the world. One synthesis step applies exactly one mutation (including
   `NO_UPDATE`). Source order: measurements > primary papers/code > official
   docs > engineering analysis > secondary summaries.
4. **Graph.** Keep competing hypotheses until a discriminating test exists.
   Do not collapse on consistent-with-A evidence.
5. **Slow loop** on contradiction, plateau, surprise, graph-changing find, or
   repeated experiment revert. Slow loop changes agenda, never promotion bar.
6. **C** only when a surviving mechanism is cheaper to test than to research.
   Causal compression: large idea → smallest intervention → predicted metric
   move → controlled measurement. Code path: baseline → instrument → bottleneck
   → one hypothesis → minimal patch → micro + paired bench → ablation →
   holdout → checkpoint or revert. Prefer wall-clock and success metrics.
7. **Cross-domain.** Translate to structural mechanisms (waiting → scheduling
   → runahead → slack stealing). Transfer only if the causal mechanism maps.
   Vocabulary rhyme is not a map.
8. **Stop** on resolved objective, decision-invariant remainder, experiment
   dominating literature, repeated `NO_UPDATE`, collapsed IG, or budget.
9. **Close.** Best causal model, important evidence, contradictions, minimal
   implied intervention, validation plan, remainder, highest-value next
   experiment. Offer `/learn` only if `learn_payload.require_task_validation_before_default`
   can be satisfied with real measurements.

Deep-mode wave bands (hints, skip/return freely): 1–5 classify/reframe;
6–10 mechanisms/counterexamples; 11–15 representations/compression;
16–20 architecture/scheduling/speculation; 21–25 determinants, baselines, C.

## Pitfalls

- Search → summarize → search
- Ever-growing source lists with no mutation
- Forcing 25 waves after convergence
- Fake confidence from stacked secondary sources
- Analogies on nouns, not mechanisms
- Architecture rewrites before a minimal experiment
- Self-validation by the process that proposed the hypothesis
- Claiming novelty because a search was shallow
- Letting B-workers write the authoritative graph
- Feeding `/learn` unmeasured trajectories

## Verification

```bash
pytest tests/test_abab_state.py tests/test_abab_skill.py -q
```

Load `references/state.md` for the JSON schema, `references/algorithm.md` for
A/B/C and anti-patterns, `references/learn-bridge.md` for `/learn`.
