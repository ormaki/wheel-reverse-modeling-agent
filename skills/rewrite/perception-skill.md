---
name: perception-skill
description: Extract wheel geometry features for the cleaned wheel reverse-modeling mainchain. Use when Codex needs to produce or inspect feature data for the accepted modeling route while avoiding archived actual_z and speculative spoke/groove perception branches.
---

# Perception Skill

## Purpose

Use this skill to produce feature data that supports the cleaned modeling route. The goal is not to preserve every experimental perception signal; it is to extract the geometry needed by the accepted model construction method.

Feature extraction should serve the clean route:

- base hub/rim geometry
- spoke motif/member layout
- stable section/refine profiles
- production hub detail inputs
- rim profile for final outer-boundary cleanup

## Active Method

1. Load the source STL and align it consistently.
2. Extract global wheel dimensions: bore, hub, rim radius, rim profile, Z bounds.
3. Extract hub detail measurements needed by production cuts: PCD radius, hole radius, phase, pocket top/floor, pocket radius, rear hub-face groove regions.
4. Extract spoke motif layout and member sections for the accepted spoke-base/refine route.
5. Keep section data tied to root, mid, and tail behavior.
6. Export a feature JSON compatible with the clean modeling entrypoint.
7. Do not emit active `actual_z_profiles`; that path is archived.

## Current Source Of Truth

The retained current features are:

- `output/wheel_base_from_features_nospokes_20260422_135255_features.json`

Use them as the baseline unless the user asks to re-run perception from STL.

## Important Geometry Signals

Prioritize these signals because the accepted model depends on them:

- `global_params` for bore, hub, rim, PCD, pocket, and Z values
- `rim_profile` for curved exterior cleanup
- `spoke_motif_sections` for spoke count, slot layout, member angle, and radial sections
- `hub_bottom_groove_regions` for rear hub-face groove cuts
- lug-pocket measurements for production hub detail cuts

## Rejected Or Archived Signals

Do not revive these as active modeling inputs without a new design decision:

- `actual_z_profiles`
- `actual_z_prefer_local_section`
- `actual_z_stack_mode`
- speculative local Z stacks for spoke lofting
- visual-only groove patches as feature truth
- old endpoint-cap or connector-fragment labels
- synthetic fallback groove regions

If old feature files contain these fields, treat them as legacy residue. Current modeling should clear or ignore them.

## Quality Checks

Before handing features to modeling, check:

- PCD count, radius, and phase are plausible.
- Rim profile has enough Z/radius samples for curved boundary cleanup.
- Spoke sections cover root, mid, and tail rather than only mid-span.
- Hub pocket and rear groove inputs exist if production hub details are expected.
- Feature JSON does not encourage `actual_z` modeling.

## Output Expectations

When perception is run or modified, report:

- input STL
- output feature JSON
- whether hub details were extracted
- whether rim profile and spoke section coverage are adequate
- any missing feature that may affect the clean modeling route
