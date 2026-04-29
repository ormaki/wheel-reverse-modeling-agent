# Local Setup

## Current handoff

- Main progress record: `HANDOFF_20260323.md`
- Older reference: `HANDOFF_20260317.md`
- Active modeling direction:
  - keep the guarded-section / hybrid-region revolve base
  - preserve rear-face groove recovery
  - continue additive spoke reconstruction
  - avoid returning to full-body multi-solid reconstruction

## Verified local environment

- Date: `2026-03-23`
- Python: `3.10.9`
- Verified imports:
  - `numpy`
  - `trimesh`
  - `cadquery`
  - `OCP`
  - `matplotlib`
  - `scipy`
  - `shapely`
  - `openai`

## Setup

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_env.ps1
```

This creates `.venv` and installs the packages from `requirements.txt`.

## Run commands

Preview only:

```powershell
.\.venv\Scripts\python.exe -X utf8 stl_to_step_pipeline.py input/wheel.stl --preview-only --no-preview-window
```

Headless full pipeline:

```powershell
.\run_pipeline_headless.ps1
```

Equivalent direct command:

```powershell
.\.venv\Scripts\python.exe -X utf8 stl_to_step_pipeline.py input/wheel.stl --auto-confirm --no-preview-window
```

## Validation status

Validated on `2026-03-23`:

- Preview command completed successfully.
- Headless full pipeline completed successfully and generated:
  - `output/wheel_20260323_130145.step`
  - `output/wheel_20260323_130145_perception.png`
  - `output/wheel_20260323_130145_spokeless.png`
  - `output/wheel_20260323_130145_hub_grooves.png`
- The project-local `.venv` and `run_pipeline_headless.ps1` were also verified end-to-end:
  - `output/wheel_env_check.step`
  - `output/wheel_env_check_perception.png`
  - `output/wheel_env_check_spokeless.png`
  - `output/wheel_env_check_hub_grooves.png`

ASCII-path STEP checks:

- `output/wheel_20260318_rear_true_aligned_v2.step`
  - `read_status = 1`
  - `solid_count = 1`
  - `valid = True`
- `output/wheel_20260322_hybrid_region_v2.step`
  - `read_status = 1`
  - `solid_count = 1`
  - `valid = False`
- `output/wheel_20260323_130145.step`
  - `read_status = 1`
  - `solid_count = 1`
  - `valid = False`
- `output/wheel_env_check.step`
  - `read_status = 1`
  - `solid_count = 1`
  - `valid = False`

The current environment is runnable. The remaining blocker is the known hybrid/additive modeling branch, not dependency setup.
