---
name: modeling-skill
description: Build the accepted wheel CAD model in the wheel reverse-modeling project using the cleaned mainchain route. Use when Codex needs to generate or adjust wheel STEP/STL output from extracted wheel features while avoiding archived spoke, groove, actual_z, and boolean experiment branches.
---

# Modeling Skill

## Purpose

Use this skill to build the wheel CAD model through the current cleaned mainchain. The skill is method-first: preserve the accepted modeling route, keep the active decision surface narrow, and avoid mining legacy files for alternative geometry strategies.

The accepted route is a pinned spoke-base/refine workflow with production hub detail cuts and final rim-curve boundary cleanup. Historical experiments remain in the repository only as implementation residue or backup context.

## Active Method

1. Start from the clean modeling entrypoint.
2. Use the retained base hub/rim model and retained feature JSON as the source of truth.
3. Build spokes from the accepted rectangular base plus section/refine replacement route.
4. Keep root and tail span broad enough to remain connected to hub and rim.
5. Apply production hub details after spoke construction, not self-made post-spoke PCD/counterbore/groove cuts.
6. Apply the outer boundary using the rim profile curve, not a simple cylinder.
7. Export STEP and STL plus metadata.
8. Evaluate visually before accepting any new artifact.

## Active Entry Point

Use the clean wrapper as the public modeling entrypoint:

```powershell
pwsh -NoProfile -Command ".\.venv\Scripts\python.exe tools\build_current_wheel_model.py --output-stem current_wheel_model"
```

The legacy execution engine is intentionally guarded against direct CLI use. Do not bypass that guard. If modeling changes are needed, update the clean entrypoint or create a small clean module behind it.

## Accepted Artifact

Treat this as the current accepted reference candidate unless the user explicitly asks to replace it:

- `output/extrudeLoopT193_prodHubCutsFixedRimIn12.step`
- `output/extrudeLoopT193_prodHubCutsFixedRimIn12.stl`
- `output/extrudeLoopT193_prodHubCutsFixedRimIn12.meta.json`

## What To Preserve

- The clean route pinned by `tools/build_current_wheel_model.py`
- The retained no-spoke base model and feature JSON
- The production lug-pocket, bolt-hole, and rear hub-face groove behavior
- The final rim-curve boundary cleanup
- The visual-evaluation loop as the acceptance gate

## Rejected Strategy Families

Do not revive these without an explicit new design decision:

- `actual_z` spoke lofting or consumption of `actual_z_profiles`
- self-made post-spoke PCD hole cuts
- self-made post-spoke counterbores
- synthetic front hub annular groove cuts
- per-shape production hub cuts
- old template-only endpoint cap experiments
- old visual-only groove patch experiments
- progressive fuse / connector-fragment experiments
- cylinder outer-boundary trims for final rim exterior
- whole-wheel heavy compound boolean cuts

## When Changing Modeling

If the user reports a defect, diagnose it against the clean route first:

- Root/tail truncation means the spoke base/refine span or final trim is wrong.
- Outer penetration means the final rim-curve cleanup is too loose or applied at the wrong stage.
- Missing lug pockets, PCD holes, or rear grooves means production hub detail timing or inputs are wrong.
- Mid-spoke groove shape issues belong in the section/refine profile path, not in a separate ad hoc groove cutter.

Prefer a small, named change to the clean route over adding another branch to the legacy engine.

## Output Expectations

For a deliverable modeling run, report:

- STEP path
- STL path
- metadata path
- what geometry changed
- whether visual evaluation has passed

If visual evaluation was not run, say that plainly.
