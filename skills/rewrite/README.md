# Rewritten Wheel Skills

These are method-focused rewrites for the three wheel reverse-modeling skills:

- `modeling-skill.md`
- `perception-skill.md`
- `visual-evaluation-skill.md`

They are based on the cleaned mainchain policy and the pinned current modeling entrypoint:

- `tools/build_current_wheel_model.py`
- `ACTIVE_MAINCHAIN_POLICY.md`

## Why These Are Here

The active global Codex skill directory is outside the current writable workspace. Directly replacing:

- `C:/Users/28455/.codex/skills/modeling-skill/SKILL.md`
- `C:/Users/28455/.codex/skills/perception-skill/SKILL.md`
- `C:/Users/28455/.codex/skills/visual-evaluation-skill/SKILL.md`

was blocked by the current sandbox policy, so these rewritten versions are staged here in the project.

## Intended Replacement

When filesystem permissions allow, copy each staged markdown file to the matching global skill directory as `SKILL.md`.

The rewrites intentionally describe the method and decision rules instead of relying only on file paths. They also explicitly block the major rejected strategy families:

- `actual_z`
- self-made PCD/counterbore/front-groove cuts
- per-shape production cuts
- old endpoint-cap and connector-fragment experiments
- old visual-only groove patches
- simple cylinder rim-boundary cleanup
- whole-wheel heavy compound booleans

The modeling skill names `tools/build_current_wheel_model.py` as the active entrypoint.
