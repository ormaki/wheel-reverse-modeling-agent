# MiMo Claw Deployment Guide

This guide explains how to run the wheel reverse-modeling multi-agent project in MiMo Claw while protecting the original local files.

## 1. Use GitHub As The Deployment Source

Repository:

```text
https://github.com/ormaki/wheel-reverse-modeling-agent
```

Replication assets:

```text
https://github.com/ormaki/wheel-reverse-modeling-agent/releases/tag/replication-assets-v1
```

In MiMo Claw, import or clone the GitHub repository. Do not upload the whole local folder directly, because local folders contain virtual environments, backups, render caches, and large generated files that are not needed for deployment.

## 2. Restore Large Assets

After cloning the repository in the Claw workspace, download:

```text
wheel-reverse-modeling-replication-assets-v1.zip
```

Extract it into the repository root. The expected restored files are:

```text
input/wheel.stl
output/extrudeLoopT193_prodHubCutsFixedRimIn12.step
output/extrudeLoopT193_prodHubCutsFixedRimIn12.stl
output/extrudeLoopT193_prodHubCutsFixedRimIn12.meta.json
output/wheel_base_from_features_nospokes_20260422_135255_features.json
output/wheel_base_from_features_nospokes_20260422_135255.step
output/_member_src_submesh_2.stl
```

These files are excluded from Git because the original STL is larger than GitHub's normal file-size limit and generated model artifacts should not be mixed into source commits.

## 3. Create A Protected Workspace

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\prepare_mimo_workspace.ps1
```

This creates:

```text
input_readonly/
output_mimo/
experiments/
```

`input_readonly/` contains a read-only copy of the source STL. Use it as the agent's input source when you want strong protection against accidental modification.

## 4. Install Dependencies

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_env.ps1
```

The project expects a Python environment with packages from `requirements.txt`, including `numpy`, `trimesh`, `scipy`, `shapely`, `matplotlib`, `cadquery`, `openai`, and `pydantic`.

## 5. Safe Branch Workflow

Before asking Claw to modify code, create a branch:

```powershell
git checkout -b mimo/<task-name>
```

Recommended rule for Claw prompts:

```text
Work only on this branch. Do not modify input/wheel.stl or input_readonly/. Write generated models to output_mimo/. Do not use git reset, git clean, or destructive checkout commands. Explain all changed files before commit.
```

## 6. Recommended Agent Prompt

Paste this into MiMo Claw when starting:

```text
You are working on a multi-agent wheel reverse-modeling project. First read AGENTS.md, ACTIVE_MAINCHAIN_POLICY.md, CLEANUP_MINIMAL_README.md, and specs/agents/README.md. Protect source files. Do not edit input/wheel.stl or input_readonly/. Keep generated CAD outputs in output_mimo/. Use a new git branch for changes. Do not run destructive git commands. If a candidate model has not passed visual evaluation, mark it as candidate only.
```

## 7. What Can Be Modified Safely

Safe to edit:

```text
agents/
skills/
tools/
models/
runtime/
prompts/
scripts/
*.py
*.md
```

Avoid editing unless explicitly needed:

```text
input/
input_readonly/
output/
specs/*.docx
```

Generated outputs should go to:

```text
output_mimo/
experiments/
```

## 8. Recovery Plan

If something goes wrong:

1. Do not overwrite the source STL.
2. Check `git status`.
3. Move generated files out of the source tree if needed.
4. Use normal Git review commands such as `git diff`, not destructive reset commands.
5. If the workspace is badly damaged, clone the GitHub repository again and re-extract the Release asset package.
