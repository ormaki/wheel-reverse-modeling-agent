# Active Mainchain Policy

Use this document when continuing the wheel reverse-modeling task.

## Active Entrypoint

Only use this as the modeling entrypoint:

- `tools/build_current_wheel_model.py`

It pins the accepted T193 route and hides rejected experiment switches.

## Accepted Current Artifact

- `output/extrudeLoopT193_prodHubCutsFixedRimIn12.step`
- `output/extrudeLoopT193_prodHubCutsFixedRimIn12.stl`
- `output/extrudeLoopT193_prodHubCutsFixedRimIn12.meta.json`

## Supporting Code

These files may be used as implementation support, but not as a menu of alternative strategies:

- `tools/run_spoke_extrude_refine_array_model.py`
- `stl_to_step_pipeline.py`
- `pipeline_modeling_codegen.py`

## Archived Or Rejected Strategy Families

Do not revive these without an explicit new design decision:

- `actual_z` spoke lofting and any downstream consumption of `actual_z_profiles`
- self-made post-spoke PCD hole cuts
- self-made post-spoke counterbores
- synthetic front hub annular groove cuts
- per-shape production hub cuts
- old template-only endpoint cap experiments
- old visual-only groove patch experiments
- old progressive fuse / connector-fragment experiments
- old cylinder outer-boundary trims for the final rim exterior
- old whole-wheel heavy compound boolean cuts

## Cleanup Direction

The remaining large files still contain historical code. Treat them as legacy execution engines until they can be split into clean modules:

- perception extraction
- base hub/rim generation
- accepted spoke base/refine generation
- production hub detail cuts
- final rim-curve boundary cleanup
- visual evaluation

Any future agent should extend the clean entrypoint or create a small clean module, not browse legacy files for another hidden branch.

`tools/run_spoke_extrude_refine_array_model.py` is guarded against direct CLI use. The clean entrypoint passes the private guard flag internally.
