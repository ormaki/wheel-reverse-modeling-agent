# Minimal Wheel Modeling Workspace

This workspace was cleaned on 2026-04-28 after the T193 wheel model was accepted as the current high-quality candidate.

## Backup

Archived files were moved, not deleted:

- `_cleanup_backup_20260428_185700/`
- Manifest: `_cleanup_backup_20260428_185700/cleanup_manifest.json`

Use the backup directory to recover old trial scripts, logs, images, and intermediate candidate outputs if needed.

## Current Candidate

The retained production candidate is:

- `output/extrudeLoopT193_prodHubCutsFixedRimIn12.step`
- `output/extrudeLoopT193_prodHubCutsFixedRimIn12.stl`
- `output/extrudeLoopT193_prodHubCutsFixedRimIn12.meta.json`

The retained base assets are:

- `output/wheel_base_from_features_nospokes_20260422_135255.step`
- `output/wheel_base_from_features_nospokes_20260422_135255_features.json`
- `output/_member_src_submesh_2.stl`

## Active Code Chain

Use this file as the active modeling entrypoint:

- `tools/build_current_wheel_model.py`

It pins the currently accepted T193 route and intentionally does not expose old trial switches.

Keep these files as supporting implementation/evaluation code:

- `stl_to_step_pipeline.py`
- `pipeline_modeling_codegen.py`
- `pipeline_noncore.py`
- `tools/run_spoke_extrude_refine_array_model.py`
- `tools/run_section_diff_spoke_rebuild.py`
- `tools/run_single_spoke_mesh_to_cad.py`
- `tools/run_spoke_side_extrude_model.py`
- `tools/diagnose_member_spoke_overlap.py`
- `tools/diagnose_single_spoke_radial_error.py`
- `tools/diagnose_template_member_radial_error.py`
- `tools/run_visual_evaluation_stage.py`
- `tools/diagnose_visual_spoke_differences.py`
- `tools/run_modelonly_patch_eval.py`

## Architecture Files

The architecture and runtime folders remain in place:

- `main.py`
- `agents/`
- `models/`
- `skills/`
- `prompts/`
- `runtime/`
- `specs/`
- `requirements.txt`
- `setup_env.ps1`

## Notes

Old branch experiments, visual trial outputs, log files, and report-generation helpers are intentionally archived to avoid accidentally reusing invalid approaches. The current active script still contains the latest production-hub-cut migration work, but T193 remains the retained accepted artifact.

## Main-Chain Pruning Notes

Additional main-chain pruning was started after the workspace cleanup:

- `tools/build_current_wheel_model.py` is now the clean active entrypoint for the accepted route.
- Direct CLI use of `tools/run_spoke_extrude_refine_array_model.py` is blocked unless called through the clean entrypoint's private guard flag.
- The old CLI switches for self-made post-spoke PCD holes, counterbores, and synthetic front hub grooves were removed from `tools/run_spoke_extrude_refine_array_model.py`.
- The active post-detail route is now the production hub-cut path only: `--post-use-production-hub-cuts`.
- Rejected per-shape detail-cut helpers now fail immediately if called, so a future agent cannot silently reuse them.
- The `actual_z` perception/modeling path is archived as a dead route. `stl_to_step_pipeline.py` now emits empty `actual_z` payloads, and `pipeline_modeling_codegen.py` clears any old `actual_z` fields before building motif spokes.

Remaining large implementation files still contain historical code. They are not the active decision surface. Future cleanup should archive them behind the clean entrypoint once command execution is available again.

The previous versions of the edited files are preserved under:

- `_cleanup_backup_20260428_185700/code_before_mainchain_prune/`
