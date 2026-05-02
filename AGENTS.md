# Agent Safety Rules

These rules are intended for MiMo Claw or any coding agent operating on this repository.

## Non-Destructive Workflow

- Do not edit or delete the original source STL in `input/`.
- Do not edit files inside `input_readonly/` if that directory exists.
- Do not overwrite accepted baseline artifacts unless the user explicitly asks for it.
- Do not run destructive Git commands such as `git reset --hard`, `git clean -fd`, or checkout-based rollback without explicit user approval.
- Do not commit generated caches, virtual environments, large modeling outputs, or temporary render folders.

## Required Working Pattern

1. Create a new branch before making changes.
2. Keep generated CAD outputs in `output_mimo/` or `output/`.
3. Keep experiments in `experiments/<date-or-task>/` when possible.
4. Treat these files as baseline/reference assets:
   - `input/wheel.stl`
   - `output/extrudeLoopT193_prodHubCutsFixedRimIn12.step`
   - `output/extrudeLoopT193_prodHubCutsFixedRimIn12.stl`
   - `output/extrudeLoopT193_prodHubCutsFixedRimIn12.meta.json`
   - `output/wheel_base_from_features_nospokes_20260422_135255_features.json`
   - `output/wheel_base_from_features_nospokes_20260422_135255.step`
5. Before changing modeling logic, read:
   - `ACTIVE_MAINCHAIN_POLICY.md`
   - `CLEANUP_MINIMAL_README.md`
   - `specs/agents/README.md`
   - `skills/rewrite/modeling-skill.md`
   - `skills/rewrite/perception-skill.md`
   - `skills/rewrite/visual-evaluation-skill.md`

## Source Protection

If the task requires local execution, first run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\prepare_mimo_workspace.ps1
```

This creates `input_readonly/`, `output_mimo/`, and `experiments/`, and marks copied input assets as read-only.

## Completion Checklist

- Explain exactly which files were changed.
- Keep generated files out of Git unless they are small, intentional documentation assets.
- Report any failures or incomplete steps.
- If a model is only a candidate and has not passed visual evaluation, say so explicitly.
