# Wheel Reverse Modeling Agent System

This project explores a multi-agent workflow for reverse modeling a 3D wheel hub from STL/point-cloud inputs. The system decomposes the task into staged perception, parametric modeling, evaluation, and iterative optimization so that the modeling process can be recorded, reviewed, and improved.

## Core Workflow

- `CoordinatorAgent`: breaks user goals into staged tasks and dispatches work.
- `PerceptionAgent`: extracts wheel geometry features such as rim, hub, PCD holes, spokes, and section profiles.
- `ModelingAgent`: generates parametric modeling scripts and exports candidate STEP/STL models.
- `Evaluation/Optimization`: compares reconstructed models with reference geometry and feeds issues back into the next iteration.

## Repository Layout

- `agents/`: agent orchestration and task modules.
- `skills/`: project-specific skills for perception, modeling, and visual evaluation.
- `tools/`: helper scripts for geometry analysis, reconstruction, and evaluation.
- `specs/`: thesis drafts, figures, and project documentation.
- `prompts/`: prompts used by the agent workflow.
- `main.py`, `run_pipeline.py`, `run_full_pipeline.py`: entry points for running the workflow.

## Notes

Large local assets such as the original STL input, generated STEP outputs, virtual environments, temporary render folders, and cleanup backups are intentionally excluded from Git. This keeps the repository suitable for GitHub while preserving the source code, documentation, and representative thesis artifacts.

## Reproduce On Another Computer

1. Clone this repository:

   ```powershell
   git clone https://github.com/ormaki/wheel-reverse-modeling-agent.git
   cd wheel-reverse-modeling-agent
   ```

2. Download the replication asset package from the GitHub Release page:

   <https://github.com/ormaki/wheel-reverse-modeling-agent/releases/tag/replication-assets-v1>

3. Extract `wheel-reverse-modeling-replication-assets-v1.zip` directly into the repository root. After extraction, these paths should exist:

   - `input/wheel.stl`
   - `output/extrudeLoopT193_prodHubCutsFixedRimIn12.step`
   - `output/extrudeLoopT193_prodHubCutsFixedRimIn12.stl`
   - `output/extrudeLoopT193_prodHubCutsFixedRimIn12.meta.json`
   - `output/wheel_base_from_features_nospokes_20260422_135255_features.json`
   - `output/wheel_base_from_features_nospokes_20260422_135255.step`
   - `output/_member_src_submesh_2.stl`

4. Create the local Python environment:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\setup_env.ps1
   ```

5. Run or inspect the project using the scripts in this repository. For the original pipeline setup, see `LOCAL_SETUP.md`.
