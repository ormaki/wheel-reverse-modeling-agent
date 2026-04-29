---
name: visual-evaluation-skill
description: Evaluate wheel CAD outputs against the source STL for the cleaned wheel reverse-modeling mainchain. Use when Codex needs to judge whether a candidate STEP/STL improves or regresses root/tail connections, spoke grooves, hub details, or rim-boundary cleanup.
---

# Visual Evaluation Skill

## Purpose

Use this skill as the acceptance gate for wheel modeling. Metrics are useful signals, but visual inspection drives decisions. The current accepted route exists because repeated visual reviews identified failure modes that numeric overlap alone missed.

Evaluation should answer: does the candidate look like the reference wheel in the places that matter?

## Active Method

1. Compare the candidate STEP/STL against the reference STL.
2. Generate full-wheel front, side, and spoke-focused diagnostics.
3. Inspect root, mid, and tail separately.
4. Check hub details after spokes: PCD holes, lug pockets, and rear hub-face grooves.
5. Check final outer rim boundary from side views for penetration or leftover protrusions.
6. Compare against the retained accepted T193 candidate unless the user names another baseline.
7. Use metrics to support visual judgment, not replace it.

## Current Accepted Baseline

Use this baseline for regressions unless the user says otherwise:

- `output/extrudeLoopT193_prodHubCutsFixedRimIn12.step`
- `output/extrudeLoopT193_prodHubCutsFixedRimIn12.stl`
- `output/extrudeLoopT193_prodHubCutsFixedRimIn12.meta.json`

## Standard Evaluation

Use the fixed visual stage when checking a candidate:

```powershell
pwsh -NoProfile -Command ".\.venv\Scripts\python.exe tools\run_visual_evaluation_stage.py --features output\wheel_base_from_features_nospokes_20260422_135255_features.json --reference-stl input\wheel.stl --candidate-step output\candidate.step --candidate-stl output\candidate.stl --output-dir output\eval_stage_candidate --visual-sample-size 30000 --sample-count 65000 --seed 42 --diff-threshold-mm 2.4"
```

If only STEP exists, omit `--candidate-stl` and let the stage export a temporary STL.

## What To Inspect

Always inspect visuals, not just JSON metrics:

- full front comparison
- side comparison
- spoke zoom
- member overlays
- worst-member profiles
- polar heatmap

Interpret colors consistently:

- STL-only geometry means CAD is missing material.
- STEP-only geometry means CAD has extra material or penetration.

## Defect Interpretation

- Root or tail planar cutoffs usually mean the spoke span or trim still terminates too early.
- Tail/rim protrusion usually means final rim-curve boundary cleanup is insufficient or not applied after assembly.
- Missing middle groove shape usually belongs in the section/refine route, not an independent groove cutter.
- Missing lug pockets or rear grooves means production hub detail cuts did not land on the correct hub/body stage.
- Improvements in one view do not pass if side views reveal penetration or broken continuity.

## Rejected Evaluation Habits

Avoid these:

- judging only by `spoke_overlap`
- accepting a candidate from one front screenshot
- ignoring side-view outer rim penetration
- treating visual-only old groove patches as ground truth
- comparing against old failed T-series candidates as if they were baselines

## Acceptance Gate

A candidate is acceptable only when:

- it does not visually regress against T193 or the user-named baseline
- root and tail connections are continuous enough for the target model
- mid-spoke shape and groove behavior are coherent
- hub details appear after spoke addition
- side views do not show meaningful outer rim penetration
- remaining defects are small, named, and not systematic

## Output Expectations

Report:

- candidate paths
- baseline used
- key metrics
- visual verdict
- specific remaining defects, if any

If visual assets were not generated or inspected, say so directly.
