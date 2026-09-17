"""Behavioral evals for the ABAB state engine. Test decisions, not wording."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
        / "research"
        / "abab-meta-research"
        / "scripts"
    ),
)

from abab_state import (  # noqa: E402
    Evidence,
    Experiment,
    Hypothesis,
    World,
    analog_ok,
    apply_mutation,
    discriminate,
    experiment_dominates,
    learn_payload,
    next_a,
    preserve_rivals,
    priority,
    record_experiment_outcome,
    source_weight,
    stop_reason,
)


def _h(**kw) -> Hypothesis:
    base = dict(
        id="h1",
        claim="bottleneck is X",
        mechanism="X",
        falsifiers=["ablate X"],
        eig=0.6,
        impact=0.8,
        decision_change=0.7,
        transferability=0.5,
        cost=1.0,
    )
    base.update(kw)
    return Hypothesis(**base)


def test_ig_prefers_cheap_decision_changing_edges():
    cheap = _h(id="cheap", cost=0.5, eig=0.5)
    expensive = _h(id="exp", cost=8.0, eig=0.9, decision_change=0.2)
    assert priority(cheap) > priority(expensive)


def test_80_20_perf_spawns_minimal_experiment_not_rewrite():
    w = World(
        objective="fastest 80/20 in repo",
        baseline="bench=100ms",
        metrics=["p50_ms"],
        hypotheses=[_h(id="hot", mechanism="sort inner loop", cost=2.5, eig=0.3)],
        wave=4,
    )
    assert experiment_dominates(w)
    a = next_a(w)
    assert a.mode == "implementation"


def test_misleading_vocabulary_reframe_is_as_job():
    w = World(objective="make the orb more RTX", hypotheses=[])
    a = next_a(w)
    assert a.reframe


def test_falsify_surviving_claim_is_no_update():
    w = World(objective="falsify claim C", hypotheses=[_h(status="open")])
    w2 = apply_mutation(w, "NO_UPDATE", {"note": "discriminating test passed"})
    assert w2.no_update_streak == 1
    w3 = apply_mutation(w2, "NO_UPDATE", {})
    w4 = apply_mutation(w3, "NO_UPDATE", {})
    assert w4.stopped
    assert w4.stop_reason == "repeated_no_update"


def test_deep_budget_stops_when_experiment_dominates():
    w = World(
        objective="deep research",
        deep=True,
        wave_budget=25,
        wave=5,
        hypotheses=[_h(id="m", mechanism="cache", cost=3.0, eig=0.2)],
    )
    # apply mutations to increment wave past 3 with dominate
    w.wave = 3
    reason = stop_reason(w)
    assert reason == "experiment_dominates"


def test_cross_domain_requires_mechanism_map():
    assert analog_ok("runahead execution", "speculative fetch", mapped=True)
    assert not analog_ok("agent waiting", "OS scheduler", mapped=False)


def test_c_compresses_to_tiny_slice_via_spawn_experiment():
    w = World(objective="broad discovery", hypotheses=[_h(id="m", mechanism="batching")])
    w2 = apply_mutation(
        w,
        "SPAWN_EXPERIMENT",
        {
            "experiment": Experiment(
                id="e1",
                hypothesis_id="m",
                intervention="batch 8 calls",
                baseline="serial",
                prediction="p50 -30%",
                metric="p50_ms",
                ablation="batch=1",
                holdout="other endpoint",
                rollback="revert",
                promotion="p50 drop without error-rate rise",
            )
        },
    )
    assert w2.experiments[0].intervention == "batch 8 calls"
    assert "rewrite architecture" not in w2.experiments[0].intervention


def test_rivals_preserved_until_discriminating_test():
    a = _h(id="A", claim="cause A", falsifiers=["kill A"])
    b = _h(id="B", claim="cause B", falsifiers=["kill B"])
    w = World(objective="x", hypotheses=[a, b])
    w = preserve_rivals(w, "A", "B")
    assert all(h.status == "rival" for h in w.hypotheses)
    assert discriminate(a, b) in ("kill A", "kill B")


def test_failed_experiment_redirects_a_via_slow_loop():
    w = World(
        objective="opt",
        hypotheses=[_h(id="m")],
        experiments=[
            Experiment(
                id="e1",
                hypothesis_id="m",
                intervention="patch",
                baseline="old",
                prediction="+10%",
                metric="t",
            )
        ],
    )
    w2 = record_experiment_outcome(w, "e1", "revert", {"t": 1.01})
    assert w2.loop == "slow"
    assert w2.hypotheses[0].status == "open"
    a = next_a(w2)
    assert a.target_uncertainty


def test_secondary_sources_weigh_less_than_measurements():
    assert source_weight("measurement") > source_weight("secondary")


def test_learn_skips_unmeasured_runs():
    w = World(objective="x", hypotheses=[_h()])
    p = learn_payload(w)
    assert p["skip_if_no_measurement"] is True
    assert p["require_task_validation_before_default"] is True


def test_budget_is_cap_not_quota():
    w = World(objective="x", wave=8, wave_budget=8, hypotheses=[_h()])
    assert stop_reason(w) == "budget_exhausted"
    w2 = World(
        objective="x",
        wave=2,
        wave_budget=25,
        hypotheses=[_h(eig=0.01, impact=0.01, decision_change=0.01, transferability=0.01)],
    )
    assert stop_reason(w2) in ("eig_collapsed", "cannot_change_decision")
