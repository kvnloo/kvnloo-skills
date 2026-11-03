---
name: comparative-visual-build-audits
description: "Use when auditing visual builds against target evidence."
version: 2.0.0
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [visual-qa, ui, games, 3d, motion, evidence, critique]
    category: software-development
    related_skills: [multi-agent-release-readiness, fail-closed-code-review]
---

# Comparative Visual Build Audits

Evidence-driven criticism of an integrated visual build: game worlds, cinematics, interactive 3D, motion-heavy product UI. Decide whether the candidate improved on the prior build, whether it meets the target bar, why it misses, and which exact changes buy the most visible improvement. The job is not to reward effort.

## When to Use

- Comparing a new build with prior captures and a reference or target bar.
- A strict "pass or fail" visual verdict is requested.
- Running or judging a labels-hidden A/B panel ([references/labels-hidden-juries.md](references/labels-hidden-juries.md)).
- A build passes its automated checks but "still looks wrong".

Don't use for: functional QA of a web app with no visual target, or proving a code change works (pstack [`principle-prove-it-works`](https://github.com/cursor/plugins/tree/main/pstack/skills/principle-prove-it-works)).

## Core Rules

1. **Two separate questions.** Candidate vs prior measures improvement. Candidate vs target measures the bar. Beating a weak baseline is not meeting the target.
2. **Technical green is not visual green.** E2E checks, latency budgets, clean consoles and non-black frames prove function, not composition or motion quality.
3. **Transitions need motion evidence.** Do not infer camera continuity, weight, anticipation or impact from a settled still.
4. **Full frame first.** Judge composition, value and silhouette on the whole frame, then halves or quadrants, then small matched tiles. A tile pass cannot certify the frame; a tile fail cannot override a full-frame verdict on layout.
5. **Inspect the active source.** A visible problem can be structural, timing-related, or caused by presentation code that is declared but never called. Find the live call site.
6. **Borrow principles, not assets.** Use references for hierarchy, value, depth, pacing, staging and motion grammar. Never recommend copying pixels, characters or proprietary designs. When asked to match a specific live demo, inspect what technique it actually uses (network, shaders, renderer settings) before substituting a similar-looking one.
7. **Honor read-only scope.** If asked only for a verdict, write no contact sheets, reports or patches into the repository. Put temporary frames in a temp directory and delete them.
8. **Be direct when strictness is requested.** No courtesy credit, hedged pass or praise before the verdict.

## Evidence Matrix

| Evidence | What it can prove |
|---|---|
| Candidate stills at a named viewport | Composition, value hierarchy, silhouettes, UI overlap, legibility |
| Prior stills at the same viewport | Direction and size of improvement |
| Motion or video | Cuts, camera continuity, locomotion, parallax, timing and payoff |
| Target or reference frames | Craft principles and the target bar |
| Active rendering source | Structural causes, timing windows, live versus dead systems |
| Verification reports | Function, performance, capture honesty |

If viewports differ, say so before comparing scale or legibility.

## Revision Integrity

- Separate the captured revision, the current live candidate and the shipped artifact. Issue separate verdicts when they differ.
- Record commit, dirty state, capture time and a served-build fingerprint. Recheck before finalizing. If any moved, old evidence is scoped to its revision.
- If a hot reload or rebuild happens mid-sequence, stop. Do not mix frames from two builds in one motion claim.
- Audit harness-side checks: a hard-coded `integrity: true` or an unconditional pass is not evidence.
- Renderer counters after a post-processing chain can describe only the final full-screen pass. Sample per pass before using draw-call or triangle counts.
- Compare framed destinations with traversable bounds and collision. A landmark the player cannot reach is set dressing, not route clarity.

## Procedure

1. **Lock scope.** Candidate files, prior evidence, references, source areas, viewport, tone, and whether the pass is read-only. Done when all are listed.
2. **Read each candidate frame by role.** Focal subject; foreground, midground, background; value path; silhouette and eyeline; route and destination; repetition; contact and grounding; UI-safe regions and minimum text size; what the frame says with all text removed. Record screen positions, not adjectives.
3. **Compare with prior** on the same rubric and viewport: what improved, what just got busier, what weakness survived, and whether the gain comes from a low baseline.
4. **Extract principles from references.** Group by craft class (composition, lighting and value, action staging, close-ups, UI negative space). Turn each into an original-build principle with an observable exit condition. Label source limits: an upscaled capture cannot show native texture detail; an edited trailer cannot show uninterrupted play or performance; an offline film cannot show real-time feasibility.
5. **Inspect motion.** Cuts versus motivated bridges, screen-position continuity, camera easing and horizon, foot plants versus speed, parallax, action phases (anticipation, launch, contact, recoil, settle), and when UI leaves and returns. Compare candidate and prior at matched timestamps or matched phases. If direct video analysis is unavailable, sample frames at fixed intervals over the full duration plus denser windows around events; see the jury reference for a tested recipe.
6. **Cross-check source.** Look for orphaned alternate scenes, small repeated archetype sets, declared but unused camera controls, phase channels assigned but never read by the render tick, "hit-stop" while animation clocks still advance, radial particles where direction matters, effect lifetimes shorter than the capture window, and animation driven by wall time instead of movement. Classify each miss as capture miss, timing weakness or structural weakness.
7. **Score.** 0 to 10 per area on a rubric that fits the build. Compute weighted totals with a tool. Rank blockers by how much fixing them changes a viewer's read, not by ease.
8. **Prescribe exact fixes** with observable outcomes and timing or layout constraints, for example "hide menus during the action; add 100-140 ms anticipation, a contact-tied hold, a directional trail, recoil, then settle before UI returns". Never "add polish".

## Verdict Shape

Lead with: candidate beats prior (yes or no, one sentence); strict target verdict (PASS, FIX-FIRST or FAIL); overall score with rubric table; evidence from candidate, prior, references, motion and source; ranked blockers; exact fixes; files changed and evidence limits. Template: [templates/strict-visual-verdict.md](templates/strict-visual-verdict.md).

## Pitfalls

- Courtesy credit for a large diff, or calling a build target-quality because the baseline was empty.
- Treating a named phase interval as rendered behavior without tracing its pose and camera channels.
- Accepting a phase pack stitched from different actions as one causal sequence.
- Judging transitions from before and after stills only.
- Calling a very high-resolution still photoreal from detailed tiles when the full frame shows the wrong layout or objects.
- Spending the report on process narration instead of the verdict.

## Verification

- [ ] Every requested frame and comparison set inspected.
- [ ] Motion claims backed by video or by active timing source.
- [ ] Source claims cite live call sites or confirmed absence.
- [ ] Technical and visual verdicts kept separate; score matches written severity.
- [ ] No repository files written under read-only scope; temp frames deleted.

## Credits

Distilled from the author's private visual review notes. Reference media used during those reviews is not included and is not licensed by this repository.
