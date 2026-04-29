---
name: visual-evaluation-skill
description: Run the fixed visual evaluation stage for the wheel reverse-modeling project. Use when Codex needs to compare reference STL point clouds against candidate STEP/STL outputs, produce visual similarity metrics, generate spoke difference overlays, diagnose worst spoke members, or decide whether perception/modeling output passes visual acceptance in `D:\桌面\wheel_project-1b6e756c9770`.
---

# Visual Evaluation Skill

## Overview

Use this skill as the mandatory evaluation stage after perception and modeling. It does not replace either stage. It validates whether a generated wheel CAD output visually matches the reference STL, with special focus on spoke shape, mid-span width, root/tail connection behavior, and extra/missing CAD geometry.

The executable source of truth is:

- `D:\桌面\wheel_project-1b6e756c9770\tools\run_visual_evaluation_stage.py`
- `D:\桌面\wheel_project-1b6e756c9770\tools\diagnose_visual_spoke_differences.py`
- `D:\桌面\wheel_project-1b6e756c9770\agents\evaluation_agent.py`

## Primary Workflow

1. Confirm these inputs exist: reference STL, candidate STEP or STL, and the matching `wheel_features.json`.
2. Run `tools\run_visual_evaluation_stage.py` from the project root using `.venv\Scripts\python.exe`.
3. Treat the resulting `visual_evaluation_stage_summary.json` as the evaluation handoff artifact.
4. Inspect both metrics and visual diagnostics; do not judge quality from `spoke_overlap` alone.
5. If visual quality fails, use the worst-member diagnostics to drive the next modeling change.

## Standard Command

Use this command pattern for a candidate STEP with an existing STL export:

```powershell
.\.venv\Scripts\python.exe tools\run_visual_evaluation_stage.py `
  --features output\wheel_base_from_features_nospokes_20260422_135255_features.json `
  --reference-stl input\wheel.stl `
  --candidate-step output\candidate.step `
  --candidate-stl output\candidate.stl `
  --output-dir output\eval_stage_candidate `
  --visual-sample-size 30000 `
  --sample-count 65000 `
  --seed 42 `
  --diff-threshold-mm 2.4
```

If only STEP exists, omit `--candidate-stl`; the stage exports a temporary candidate STL under the output directory.

## Required Outputs

Every accepted evaluation run must produce:

- `visual_evaluation_stage_summary.json`
- `{candidate}_seed42.metrics.json` or equivalent metrics JSON when STEP is provided
- `evaluation_comparison.png`
- `evaluation_comparison_spoke_zoom.png`
- `visual_full_front_diff.png`
- `visual_polar_heatmap.png`
- `visual_member_overlays.png`
- `visual_worst_member_profiles.png`
- `visual_spoke_diagnostics.json`

## Interpretation Rules

- Use `spoke_overlap`, `front_overlap`, `side_overlap`, and nearest-neighbor errors as numerical signals, not final truth.
- Always inspect `visual_member_overlays.png` and `visual_worst_member_profiles.png` before deciding the next modeling edit.
- Blue points mean STL-only geometry, so the CAD is missing material there.
- Red points mean STEP-only geometry, so the CAD has extra material there.
- Prioritize recurring member/slot patterns over a single outlier.
- For spoke work, diagnose `root`, `mid`, and `tail` separately; mid-span visual mismatch is not solved by connection-area patching.

## Acceptance Gate

An output is not visually accepted just because the command finishes. It must satisfy:

- Metrics do not regress against the current best baseline unless the visual overlays clearly improve the targeted defect.
- Worst-member overlays no longer show large systematic missing/extra bands in the spoke mid-span.
- Root and tail connection defects are localized, not repeated across most members.
- The final response reports the artifact paths and the specific remaining visual defect if not accepted.

## Operating Rules

- Keep this stage separate from perception and modeling code changes.
- Do not tune only `spoke_overlap`; use the visual overlays to locate the geometric cause.
- Do not call old main-chain spoke methods unless the user explicitly asks; evaluate the active candidate produced by the current modeling route.
- When a command stalls, check for active Python processes before relaunching the same evaluation.
- Prefer deterministic settings: `--seed 42`, `--visual-sample-size 30000`, `--sample-count 65000`, `--diff-threshold-mm 2.4`.

## Current Project Baseline

The latest known best new-chain candidate at skill creation time was:

- `D:\桌面\wheel_project-1b6e756c9770\output\extrudeLoopN3_M2auto_B7.step`
- `spoke_overlap = 0.40180664427025004`
- `front_overlap = 0.6572`
- `side_overlap = 0.7384`

Use this only as a local comparison baseline; rerun the evaluation stage for fresh candidates.
