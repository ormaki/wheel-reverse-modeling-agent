from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple

import cadquery as cq
import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial import cKDTree


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.evaluation_agent import EvaluationAgent


OLD_PREAMBLE = """                        # Current priority is point-cloud fidelity and export completion.
                        # Preserve the actual-direct spoke fragments as a direct compound
                        # instead of spending the entire runtime in spoke-to-base booleans.
                        non_boolean_spoke_compound_mode = True
                        hub_cuts_applied_before_spoke_compound = False
                        if (
                            (not fast_spoke_validation_mode) and
                            (not spokeless_hybrid_revolve_mode) and
                            non_boolean_spoke_compound_mode
                        ):
"""


NEW_PREAMBLE = """                        # Current priority is point-cloud fidelity and export completion.
                        # With simplified pure actual local-section members, re-attempt
                        # spoke-to-base booleans for single-solid members first so the
                        # exported surface sheds internal overlap faces. Complex residual
                        # fragments still fall back to a direct compound.
                        non_boolean_spoke_compound_mode = False
                        hub_cuts_applied_before_spoke_compound = False
                        if (
                            (not fast_spoke_validation_mode) and
                            (not spokeless_hybrid_revolve_mode) and
                            (not non_boolean_spoke_compound_mode)
                        ):
"""


OLD_LOOP_CHUNK = """                        for member_index, member_body, member_payload, motif_payload in ordered_spokeless_members:
                            if non_boolean_spoke_compound_mode:
                                member_fragments = explode_body_to_single_solids(member_body)
                                if member_fragments:
                                    compound_spoke_parts.extend(member_fragments)
                                    merged_member_count += 1
                                    print(
                                        f"[*] spokeless additive member {member_index} appended as compound fragments: "
                                        f"count={len(member_fragments)}"
                                    )
                                else:
                                    rejected_spokeless_members.append((member_index, member_body, member_payload, motif_payload))
                                continue
                            working_components, member_merged, component_count_after_merge = merge_member_into_components(
"""


NEW_LOOP_CHUNK = """                        for member_index, member_body, member_payload, motif_payload in ordered_spokeless_members:
                            member_solid_count = solid_count_of_body(member_body)
                            if non_boolean_spoke_compound_mode:
                                member_fragments = explode_body_to_single_solids(member_body)
                                if member_fragments:
                                    compound_spoke_parts.extend(member_fragments)
                                    merged_member_count += 1
                                    print(
                                        f"[*] spokeless additive member {member_index} appended as compound fragments: "
                                        f"count={len(member_fragments)}"
                                    )
                                else:
                                    rejected_spokeless_members.append((member_index, member_body, member_payload, motif_payload))
                                continue
                            if member_solid_count > 1:
                                member_fragments = explode_body_to_single_solids(member_body)
                                if member_fragments:
                                    compound_spoke_parts.extend(member_fragments)
                                    compound_staged_member_count += 1
                                    print(
                                        f"[*] spokeless additive member {member_index} staged for direct compound fallback: "
                                        f"fragments={len(member_fragments)}, member_solids={member_solid_count}"
                                    )
                                else:
                                    rejected_spokeless_members.append((member_index, member_body, member_payload, motif_payload))
                                    print(
                                        f"[!] spokeless additive member {member_index} discarded before boolean merge: "
                                        f"member_solids={member_solid_count}"
                                    )
                                continue
                            working_components, member_merged, component_count_after_merge = merge_member_into_components(
"""


OLD_CENTER_RELIEF_BLOCK = """    unified_center_outer_r = derive_unified_center_outer_radius(
        window_inner_ref_radii,
        params,
        lug_boss_regions
    )
    if spokeless_guarded_revolve_mode:
        print("[*] Spokeless revolve base active. Deferring local center valley relief until spoke merge is stable.")
    elif unified_center_floor_z is not None and unified_center_outer_r is not None:
"""


NEW_CENTER_RELIEF_BLOCK = """    unified_center_outer_r = derive_unified_center_outer_radius(
        window_inner_ref_radii,
        params,
        lug_boss_regions
    )
    deferred_center_valley_relief = False
    if spokeless_guarded_revolve_mode:
        if unified_center_floor_z is not None and unified_center_outer_r is not None:
            deferred_center_valley_relief = True
        print("[*] Spokeless revolve base active. Deferring local center valley relief until spoke merge is stable.")
    elif unified_center_floor_z is not None and unified_center_outer_r is not None:
"""


OLD_POST_ASSEMBLY_BLOCK = """                        working_solid_count = solid_count_of_body(working_body)
"""


NEW_POST_ASSEMBLY_BLOCK = """                        if (
                            deferred_center_valley_relief and
                            unified_center_floor_z is not None and
                            unified_center_outer_r is not None and
                            solid_count_of_body(working_body) == 1
                        ):
                            print("[*] Applying deferred local center valley relief after additive spoke merge.")
                            relieved_working_body = apply_unified_center_valley_relief(
                                working_body,
                                unified_center_floor_z,
                                hub_top_z,
                                spoke_root_regions,
                                lug_boss_regions,
                                params["bore_radius"],
                                unified_center_outer_r,
                                window_inner_ref_radii
                            )
                            relieved_solid_count = solid_count_of_body(relieved_working_body)
                            if relieved_working_body is not None and relieved_solid_count == 1:
                                working_body = relieved_working_body
                            else:
                                print(
                                    f"[!] Deferred local center valley relief rejected: "
                                    f"solids={relieved_solid_count}"
                                )
                        working_solid_count = solid_count_of_body(working_body)
"""


OLD_NO_BOSS_VALLEY_INNER_BLOCK = """            valley_inner_r = float(bore_radius) + 0.35 if bore_radius is not None else 0.0
            valley_half_span = max(1.2, min(2.8, gap_angle * 0.16))
"""


NEW_NO_BOSS_VALLEY_INNER_ANNULAR_BLOCK = """            default_inner_r = float(bore_radius) + 0.35 if bore_radius is not None else 0.0
            try:
                root_outer_floor = min(
                    float(spec.get("outer_r", default_inner_r)),
                    float(next_spec.get("outer_r", default_inner_r))
                ) + 0.35
                valley_inner_r = max(default_inner_r, root_outer_floor)
            except Exception:
                valley_inner_r = default_inner_r
            valley_half_span = max(1.2, min(2.8, gap_angle * 0.16))
"""


OLD_VALLEY_CUT_BLOCK = """        cutter = build_polygon_prism(valley_coords, floor_z, relief_height)
        if cutter is None:
            continue
        hub_body = safe_cut(hub_body, cutter, f"unified center valley {idx}")
        valley_cut_count += 1
"""


NEW_VALLEY_CUT_DEBUG_BLOCK = """        print(
            f"[*] unified center valley candidate {idx}: "
            f"center={valley_center % 360.0:.2f}, inner={valley_inner_r:.2f}, "
            f"outer={valley_outer_r:.2f}, half_span={valley_half_span:.2f}"
        )
        cutter = build_polygon_prism(valley_coords, floor_z, relief_height)
        if cutter is None:
            print(f"[!] unified center valley {idx} skipped: cutter build failed")
            continue
        hub_body = safe_cut(hub_body, cutter, f"unified center valley {idx}")
        print(f"[*] unified center valley {idx} processed")
        valley_cut_count += 1
"""


OLD_ACTUAL_OVERRIDE_BLOCK = """    # Replace measured section loops with profiles reconstructed from actual XY@Z slices.
    # This keeps spoke body/detail coherent instead of mixing projected fallback loops.
    actual_override_count = 0
    if len(actual_z_profiles) >= 4:
        rebuilt_sections = []
        for section_payload in working_sections:
            extension_side = str(section_payload.get("extension_side") or "")
            if extension_side.startswith("donor_"):
                rebuilt_sections.append(section_payload)
                continue
            try:
                station_r = float(section_payload.get("station_r", 0.0))
            except Exception:
                station_r = 0.0
            derived_section = derive_actual_profile_extension(
                station_r,
                section_payload,
                extension_side if extension_side else "actual_stack"
            )
            if derived_section is not None and accepts_actual_override(section_payload, derived_section):
                if extension_side and not str(derived_section.get("extension_side") or "").startswith("donor_"):
                    derived_section["extension_side"] = extension_side
                rebuilt_sections.append(derived_section)
                actual_override_count += 1
            else:
                rebuilt_sections.append(section_payload)
        if rebuilt_sections:
            working_sections = rebuilt_sections
"""


NEW_DISABLE_ACTUAL_OVERRIDE_BLOCK = """    # Keep measured radial sections intact for this experiment.
    actual_override_count = 0
"""


NEW_ROOT_FROM_FIRST_ACTUAL_OVERRIDE_BLOCK = """    # Rebuild sections from actual XY@Z slices, but make root extensions
    # inherit the first real body section instead of the template root scaffold.
    actual_override_count = 0
    if len(actual_z_profiles) >= 4:
        rebuilt_sections = []
        first_actual_for_root = body_ordered_sections[0] if body_ordered_sections else ordered_sections[0]
        for section_payload in working_sections:
            extension_side = str(section_payload.get("extension_side") or "")
            if extension_side.startswith("donor_"):
                rebuilt_sections.append(section_payload)
                continue
            try:
                station_r = float(section_payload.get("station_r", 0.0))
            except Exception:
                station_r = 0.0

            override_anchor = section_payload
            override_extension_side = extension_side if extension_side else "actual_stack"
            accept_anchor = section_payload
            if extension_side.startswith("root"):
                override_anchor = first_actual_for_root
                override_extension_side = "actual_stack"
                accept_anchor = first_actual_for_root

            derived_section = derive_actual_profile_extension(
                station_r,
                override_anchor,
                override_extension_side
            )
            if derived_section is not None and accepts_actual_override(accept_anchor, derived_section):
                if extension_side and not str(derived_section.get("extension_side") or "").startswith("donor_"):
                    derived_section["extension_side"] = extension_side
                rebuilt_sections.append(derived_section)
                actual_override_count += 1
            else:
                rebuilt_sections.append(section_payload)
        if rebuilt_sections:
            working_sections = rebuilt_sections
"""


OLD_ACTUAL_BODY_FILL_BLOCK = """        if len(working_sections) >= 2:
            densified_sections = []
            inserted_actual_body_count = 0
            for section_idx, section in enumerate(working_sections):
                densified_sections.append(section)
                if section_idx >= len(working_sections) - 1:
                    continue

                next_section = working_sections[section_idx + 1]
                try:
                    section_r = float(section.get("station_r", 0.0))
                    next_r = float(next_section.get("station_r", 0.0))
                except Exception:
                    continue

                gap_r = next_r - section_r
                if gap_r <= 4.8:
                    continue

                section_side = str(section.get("extension_side") or "")
                next_side = str(next_section.get("extension_side") or "")
                tip_or_terminal_transition = (
                    section_side.startswith("tip") or
                    next_side.startswith("tip") or
                    section_side.startswith("donor_tip") or
                    next_side.startswith("donor_tip")
                )
                if tip_or_terminal_transition:
                    continue

                fill_count = max(1, min(3, int(math.ceil(gap_r / 5.5)) - 1))
                if fill_count <= 0:
                    continue

                for target_r in np.linspace(section_r, next_r, fill_count + 2)[1:-1]:
                    anchor_payload = section if abs(float(target_r) - section_r) <= abs(next_r - float(target_r)) else next_section
                    derived_section = derive_actual_profile_extension(
                        float(target_r),
                        anchor_payload,
                        "actual_body_fill"
                    )
                    if derived_section is None:
                        continue
                    derived_section["preserve_detail"] = True
                    derived_section["_actual_slice_derived"] = True
                    if (
                        accepts_actual_override(section, derived_section) or
                        accepts_actual_override(next_section, derived_section)
                    ):
                        densified_sections.append(derived_section)
                        inserted_actual_body_count += 1

            if inserted_actual_body_count > 0:
                working_sections = sorted(
                    densified_sections,
                    key=lambda section: float(section.get("station_r", 0.0))
                )
                print(
                    f"[*] {member_label} injected actual body fill sections: "
                    f"count={inserted_actual_body_count}, sections={len(working_sections)}"
                )
"""


CURRENT_ACTUAL_BODY_FILL_BLOCK = OLD_ACTUAL_BODY_FILL_BLOCK.replace(
    "        if len(working_sections) >= 2:\n",
    "        if len(working_sections) >= 2 and (not disable_actual_body_fill):\n",
    1,
)


NEW_DISABLE_ACTUAL_BODY_FILL_BLOCK = """        inserted_actual_body_count = 0
"""


OLD_DONOR_ROOT_BLOCK = """        if working_root_ext_count < 2:
            root_target_inner = max(float(params["bore_radius"]) + 1.2, first_actual_r - 12.0)
            if isinstance(member_index, int) and 0 <= member_index < len(spoke_root_regions):
                root_region_payload = spoke_root_regions[member_index]
                root_region_pts = root_region_payload.get("points", []) if isinstance(root_region_payload, dict) else root_region_payload
                if len(root_region_pts) >= 4:
                    try:
                        root_radii = [math.hypot(float(x), float(y)) for x, y in root_region_pts[:-1]]
                    except Exception:
                        root_radii = []
                    if root_radii:
                        root_target_inner = max(
                            float(params["bore_radius"]) + 1.2,
                            float(np.percentile(np.asarray(root_radii, dtype=float), 8.0)) - 0.4
                        )
            root_target_outer = first_actual_r - 0.4
            if root_target_outer > root_target_inner + 1.2:
                root_positions = []
                dense_count = max(4, min(8, int(math.ceil((root_target_outer - root_target_inner) / 2.2)) + 1))
                for candidate_r in np.linspace(root_target_inner, root_target_outer, dense_count):
                    candidate_r = float(candidate_r)
                    if candidate_r <= root_target_inner:
                        continue
                    root_positions.append(candidate_r)
                if not root_positions:
                    root_positions = [float(val) for val in np.linspace(root_target_inner, root_target_outer, 3)]
                injected_actual_root = []
                for target_r in root_positions:
                    derived_section = derive_actual_profile_extension(
                        float(target_r),
                        first_actual,
                        "donor_root_actual"
                    )
                    if derived_section is not None:
                        injected_actual_root.append(derived_section)
                if injected_actual_root:
                    working_sections = injected_actual_root + working_sections
                    working_root_ext_count += len(injected_actual_root)
                    print(
                        f"[*] {member_label} injected donor_root_actual: "
                        f"count={len(injected_actual_root)}, "
                        f"R={float(injected_actual_root[0].get('station_r', 0.0)):.2f}->"
                        f"{float(injected_actual_root[-1].get('station_r', 0.0)):.2f}"
                    )
"""


NEW_DISABLE_DONOR_ROOT_BLOCK = ""


OLD_DONOR_TIP_BLOCK = """        if tip_ordered_sections or working_tip_ext_count < 2:
            tip_target_inner = last_actual_r + 0.4
            tip_target_outer = max(
                max((float(section.get("station_r", 0.0)) for section in tip_ordered_sections), default=last_actual_r),
                max((float(section.get("station_r", 0.0)) for section in working_sections), default=last_actual_r),
                last_actual_r + 10.0
            )
            if tip_target_outer > tip_target_inner + 1.2:
                tip_positions = []
                dense_count = max(4, min(8, int(math.ceil((tip_target_outer - tip_target_inner) / 2.2)) + 1))
                for candidate_r in np.linspace(tip_target_inner, tip_target_outer, dense_count):
                    candidate_r = float(candidate_r)
                    if candidate_r >= tip_target_outer:
                        continue
                    tip_positions.append(candidate_r)
                if not tip_positions:
                    tip_positions = [float(val) for val in np.linspace(tip_target_inner, tip_target_outer, 3)]
                injected_actual_tip = []
                for target_r in tip_positions:
                    derived_section = derive_actual_profile_extension(
                        float(target_r),
                        last_actual,
                        "donor_tip_actual"
                    )
                    if derived_section is not None:
                        injected_actual_tip.append(derived_section)
                if injected_actual_tip:
                    donor_tip_outer_r = max(float(section.get("station_r", 0.0)) for section in injected_actual_tip)
                    retained_sections = []
                    for section in working_sections:
                        extension_side = str(section.get("extension_side") or "")
                        is_original_tip = (
                            extension_side.startswith("tip") and
                            not bool(section.get("_actual_slice_derived"))
                        )
                        try:
                            section_r = float(section.get("station_r", 0.0))
                        except Exception:
                            section_r = 0.0
                        if is_original_tip and section_r <= donor_tip_outer_r + 0.6:
                            continue
                        retained_sections.append(section)
                    working_sections = retained_sections + injected_actual_tip
                    working_tip_ext_count += len(injected_actual_tip)
                    print(
                        f"[*] {member_label} injected donor_tip_actual: "
                        f"count={len(injected_actual_tip)}, "
                        f"R={float(injected_actual_tip[0].get('station_r', 0.0)):.2f}->"
                        f"{float(injected_actual_tip[-1].get('station_r', 0.0)):.2f}, "
                        f"trimmed_tip_outer={donor_tip_outer_r:.2f}"
                    )
"""


NEW_DISABLE_DONOR_TIP_BLOCK = ""


OLD_FIRST_ACTUAL_BLOCK = """    if len(actual_z_profiles) >= 4:
        first_actual = body_ordered_sections[0] if body_ordered_sections else ordered_sections[0]
        last_actual = body_ordered_sections[-1] if body_ordered_sections else ordered_sections[-1]
        first_actual_r = float(first_actual.get("station_r", 0.0))
        last_actual_r = float(last_actual.get("station_r", 0.0))
"""


NEW_DROP_ROOT_EXTENSION_FIRST_ACTUAL_BLOCK = """    if len(actual_z_profiles) >= 4:
        retained_sections = []
        dropped_root_section_count = 0
        for section in working_sections:
            extension_side = str(section.get("extension_side") or "")
            is_template_root_extension = (
                extension_side.startswith("root") and
                not bool(section.get("_actual_slice_derived"))
            )
            if is_template_root_extension:
                dropped_root_section_count += 1
                continue
            retained_sections.append(section)
        if dropped_root_section_count > 0 and retained_sections:
            working_sections = retained_sections
            print(
                f"[*] {member_label} dropped template root extension sections: "
                f"count={dropped_root_section_count}, sections={len(working_sections)}"
            )
        first_actual = body_ordered_sections[0] if body_ordered_sections else ordered_sections[0]
        last_actual = body_ordered_sections[-1] if body_ordered_sections else ordered_sections[-1]
        first_actual_r = float(first_actual.get("station_r", 0.0))
        last_actual_r = float(last_actual.get("station_r", 0.0))
"""


NEW_TRIM_ROOT_EXTENSION_FIRST_ACTUAL_BLOCK_TEMPLATE = """    if len(actual_z_profiles) >= 4:
        root_sections = []
        non_root_sections = []
        for section in working_sections:
            extension_side = str(section.get("extension_side") or "")
            is_template_root_extension = (
                extension_side.startswith("root") and
                not bool(section.get("_actual_slice_derived"))
            )
            if is_template_root_extension:
                root_sections.append(section)
            else:
                non_root_sections.append(section)

        trimmed_root_section_count = 0
        if len(root_sections) > {keep_count}:
            root_sections = sorted(
                root_sections,
                key=lambda section: float(section.get("station_r", 0.0))
            )[-{keep_count}:]
            trimmed_root_section_count = len(working_sections) - len(non_root_sections) - len(root_sections)

        if root_sections or non_root_sections:
            working_sections = non_root_sections + root_sections
        if trimmed_root_section_count > 0:
            print(
                f"[*] {member_label} trimmed template root extension sections: "
                f"removed={trimmed_root_section_count}, kept={len(root_sections)}, sections={len(working_sections)}"
            )

        first_actual = body_ordered_sections[0] if body_ordered_sections else ordered_sections[0]
        last_actual = body_ordered_sections[-1] if body_ordered_sections else ordered_sections[-1]
        first_actual_r = float(first_actual.get("station_r", 0.0))
        last_actual_r = float(last_actual.get("station_r", 0.0))
"""


NEW_CONSERVATIVE_ACTUAL_BODY_FILL_BLOCK = """        if len(working_sections) >= 2:
            densified_sections = []
            inserted_actual_body_count = 0
            for section_idx, section in enumerate(working_sections):
                densified_sections.append(section)
                if section_idx >= len(working_sections) - 1:
                    continue

                next_section = working_sections[section_idx + 1]
                try:
                    section_r = float(section.get("station_r", 0.0))
                    next_r = float(next_section.get("station_r", 0.0))
                except Exception:
                    continue

                gap_r = next_r - section_r
                if gap_r <= 6.2:
                    continue

                section_side = str(section.get("extension_side") or "")
                next_side = str(next_section.get("extension_side") or "")
                tip_or_terminal_transition = (
                    section_side.startswith("tip") or
                    next_side.startswith("tip") or
                    section_side.startswith("donor_tip") or
                    next_side.startswith("donor_tip")
                )
                if tip_or_terminal_transition:
                    continue

                fill_count = 1 if gap_r <= 11.5 else 2
                if fill_count <= 0:
                    continue

                for target_r in np.linspace(section_r, next_r, fill_count + 2)[1:-1]:
                    anchor_payload = section if abs(float(target_r) - section_r) <= abs(next_r - float(target_r)) else next_section
                    derived_section = derive_actual_profile_extension(
                        float(target_r),
                        anchor_payload,
                        "actual_body_fill"
                    )
                    if derived_section is None:
                        continue
                    derived_section["preserve_detail"] = True
                    derived_section["_actual_slice_derived"] = True
                    if (
                        accepts_actual_override(section, derived_section) or
                        accepts_actual_override(next_section, derived_section)
                    ):
                        densified_sections.append(derived_section)
                        inserted_actual_body_count += 1

            if inserted_actual_body_count > 0:
                working_sections = sorted(
                    densified_sections,
                    key=lambda section: float(section.get("station_r", 0.0))
                )
                print(
                    f"[*] {member_label} injected conservative actual body fill sections: "
                    f"count={inserted_actual_body_count}, sections={len(working_sections)}"
                )
"""


NEW_SPARSE_ACTUAL_BODY_FILL_BLOCK = """        if len(working_sections) >= 2:
            densified_sections = []
            inserted_actual_body_count = 0
            for section_idx, section in enumerate(working_sections):
                densified_sections.append(section)
                if section_idx >= len(working_sections) - 1:
                    continue

                next_section = working_sections[section_idx + 1]
                try:
                    section_r = float(section.get("station_r", 0.0))
                    next_r = float(next_section.get("station_r", 0.0))
                except Exception:
                    continue

                gap_r = next_r - section_r
                if gap_r <= 8.6:
                    continue

                section_side = str(section.get("extension_side") or "")
                next_side = str(next_section.get("extension_side") or "")
                tip_or_terminal_transition = (
                    section_side.startswith("tip") or
                    next_side.startswith("tip") or
                    section_side.startswith("donor_tip") or
                    next_side.startswith("donor_tip")
                )
                if tip_or_terminal_transition:
                    continue

                target_r = float((section_r + next_r) * 0.5)
                anchor_payload = section if abs(target_r - section_r) <= abs(next_r - target_r) else next_section
                derived_section = derive_actual_profile_extension(
                    target_r,
                    anchor_payload,
                    "actual_body_fill"
                )
                if derived_section is None:
                    continue
                derived_section["preserve_detail"] = True
                derived_section["_actual_slice_derived"] = True
                if (
                    accepts_actual_override(section, derived_section) or
                    accepts_actual_override(next_section, derived_section)
                ):
                    densified_sections.append(derived_section)
                    inserted_actual_body_count += 1

            if inserted_actual_body_count > 0:
                working_sections = sorted(
                    densified_sections,
                    key=lambda section: float(section.get("station_r", 0.0))
                )
                print(
                    f"[*] {member_label} injected sparse actual body fill sections: "
                    f"count={inserted_actual_body_count}, sections={len(working_sections)}"
                )
"""


OLD_ACTUAL_EXTENSION_BASE_Z_LINE = """        samples.sort(key=lambda item: item[0])
        base_z = float(samples[0][0])
"""


OLD_ACTUAL_Y_BAND_BLOCK = """            hit = local_poly.intersection(probe)
            y_values = []
            collect_y_values(hit, y_values)
            if len(y_values) < 2:
                continue
            try:
                z_val = float(profile.get("z", 0.0))
            except Exception:
                continue
            samples.append((z_val, min(y_values), max(y_values)))
"""


NEW_ANCHORED_ACTUAL_Y_BAND_BLOCK = """            hit = local_poly.intersection(probe)
            y_values = []
            collect_y_values(hit, y_values)
            if len(y_values) < 2:
                continue

            expected_center = 0.0
            expected_width = 0.0
            try:
                anchor_pts = anchor_payload.get("points_local", []) or anchor_payload.get("points_local_raw", []) or []
                anchor_xs = [float(x_val) for x_val, _ in anchor_pts[:-1] if len(anchor_pts) >= 5] or [float(x_val) for x_val, _ in anchor_pts]
                if anchor_xs:
                    expected_center = (max(anchor_xs) + min(anchor_xs)) * 0.5
                    expected_width = max(anchor_xs) - min(anchor_xs)
            except Exception:
                expected_center = 0.0
                expected_width = 0.0

            try:
                target_center_hint = float(anchor_payload.get("target_center_x", expected_center) or expected_center)
            except Exception:
                target_center_hint = expected_center
            if abs(target_center_hint) < max(0.6, abs(expected_center) * 0.5):
                target_center_hint = expected_center
            expected_center = float(target_center_hint)

            try:
                target_width_hint = float(anchor_payload.get("target_width", expected_width) or expected_width)
            except Exception:
                target_width_hint = expected_width
            if target_width_hint > 0.6:
                expected_width = target_width_hint

            sorted_y = sorted(float(val) for val in y_values)
            clusters = []
            current_cluster = [sorted_y[0]]
            cluster_gap = max(0.85, min(2.8, expected_width * 0.18)) if expected_width > 0.0 else 1.25
            for y_val in sorted_y[1:]:
                if abs(y_val - current_cluster[-1]) <= cluster_gap:
                    current_cluster.append(y_val)
                else:
                    if len(current_cluster) >= 2:
                        clusters.append((min(current_cluster), max(current_cluster)))
                    current_cluster = [y_val]
            if len(current_cluster) >= 2:
                clusters.append((min(current_cluster), max(current_cluster)))
            if not clusters:
                continue

            def score_interval(interval):
                lo, hi = interval
                width = max(1e-6, float(hi) - float(lo))
                center = (float(lo) + float(hi)) * 0.5
                center_penalty = abs(center - expected_center)
                width_penalty = 0.0
                if expected_width > 0.8:
                    width_penalty = abs(width - expected_width) / max(expected_width, 1e-6)
                    if width > expected_width * 1.7:
                        width_penalty += 2.0
                return center_penalty + (width_penalty * max(1.6, expected_width * 0.08))

            best_interval = min(clusters, key=score_interval)
            try:
                z_val = float(profile.get("z", 0.0))
            except Exception:
                continue
            samples.append((z_val, float(best_interval[0]), float(best_interval[1])))
"""


def patch_generated_code(
    source_text: str,
    max_direct_merge_member_solids: int = 1,
    apply_deferred_center_relief: bool = False,
    deferred_center_relief_annular: bool = False,
    debug_deferred_center_relief: bool = False,
    disable_actual_section_overrides: bool = False,
    disable_actual_body_fill: bool = False,
    conservative_actual_body_fill: bool = False,
    sparse_actual_body_fill: bool = False,
    disable_donor_root_actual: bool = False,
    disable_donor_tip_actual: bool = False,
    drop_template_root_sections: bool = False,
    keep_template_root_sections: int | None = None,
    root_override_from_first_actual: bool = False,
    anchored_actual_y_band: bool = False,
    actual_body_z_trim_percentile: float | None = None,
    actual_stack_z_trim_only: bool = False,
) -> str:
    code = source_text.replace("\r\n", "\n")
    merge_threshold = max(1, int(max_direct_merge_member_solids))
    new_loop_chunk = NEW_LOOP_CHUNK.replace(
        "if member_solid_count > 1:",
        f"if member_solid_count > {merge_threshold}:",
    )
    if OLD_PREAMBLE in code:
        code = code.replace(OLD_PREAMBLE, NEW_PREAMBLE, 1)
    elif (
        NEW_PREAMBLE not in code and
        not (
            "Current priority is point-cloud fidelity and export completion." in code and
            "non_boolean_spoke_compound_mode = False" in code
        )
    ):
        raise RuntimeError("Additive spoke preamble anchor was not found in generated code.")

    if OLD_LOOP_CHUNK in code:
        code = code.replace(OLD_LOOP_CHUNK, new_loop_chunk, 1)
    elif NEW_LOOP_CHUNK in code:
        if merge_threshold != 1:
            code = code.replace(NEW_LOOP_CHUNK, new_loop_chunk, 1)
    elif "member_solid_count = solid_count_of_body(member_body)" not in code:
        raise RuntimeError("Additive spoke loop anchor was not found in generated code.")
    if disable_donor_root_actual:
        if OLD_DONOR_ROOT_BLOCK not in code:
            raise RuntimeError("Donor-root actual block was not found in generated code.")
        code = code.replace(OLD_DONOR_ROOT_BLOCK, NEW_DISABLE_DONOR_ROOT_BLOCK, 1)
    if disable_donor_tip_actual:
        if OLD_DONOR_TIP_BLOCK not in code:
            raise RuntimeError("Donor-tip actual block was not found in generated code.")
        code = code.replace(OLD_DONOR_TIP_BLOCK, NEW_DISABLE_DONOR_TIP_BLOCK, 1)
    if anchored_actual_y_band:
        if OLD_ACTUAL_Y_BAND_BLOCK not in code:
            raise RuntimeError("Actual Y-band block was not found in generated code.")
        code = code.replace(OLD_ACTUAL_Y_BAND_BLOCK, NEW_ANCHORED_ACTUAL_Y_BAND_BLOCK, 1)
    if drop_template_root_sections:
        if OLD_FIRST_ACTUAL_BLOCK not in code:
            raise RuntimeError("First-actual block was not found in generated code.")
        code = code.replace(OLD_FIRST_ACTUAL_BLOCK, NEW_DROP_ROOT_EXTENSION_FIRST_ACTUAL_BLOCK, 1)
    elif keep_template_root_sections is not None:
        if OLD_FIRST_ACTUAL_BLOCK not in code:
            raise RuntimeError("First-actual block was not found in generated code.")
        keep_count = max(0, int(keep_template_root_sections))
        new_block = (
            NEW_DROP_ROOT_EXTENSION_FIRST_ACTUAL_BLOCK
            if keep_count == 0
            else NEW_TRIM_ROOT_EXTENSION_FIRST_ACTUAL_BLOCK_TEMPLATE.replace("{keep_count}", str(keep_count))
        )
        code = code.replace(OLD_FIRST_ACTUAL_BLOCK, new_block, 1)
    if disable_actual_section_overrides:
        if OLD_ACTUAL_OVERRIDE_BLOCK not in code:
            raise RuntimeError("Actual section-override block was not found in generated code.")
        code = code.replace(OLD_ACTUAL_OVERRIDE_BLOCK, NEW_DISABLE_ACTUAL_OVERRIDE_BLOCK, 1)
    elif root_override_from_first_actual:
        if OLD_ACTUAL_OVERRIDE_BLOCK not in code:
            raise RuntimeError("Actual section-override block was not found in generated code.")
        code = code.replace(OLD_ACTUAL_OVERRIDE_BLOCK, NEW_ROOT_FROM_FIRST_ACTUAL_OVERRIDE_BLOCK, 1)
    actual_body_fill_anchor = None
    if OLD_ACTUAL_BODY_FILL_BLOCK in code:
        actual_body_fill_anchor = OLD_ACTUAL_BODY_FILL_BLOCK
    elif CURRENT_ACTUAL_BODY_FILL_BLOCK in code:
        actual_body_fill_anchor = CURRENT_ACTUAL_BODY_FILL_BLOCK
    if disable_actual_body_fill:
        if actual_body_fill_anchor is None:
            raise RuntimeError("Actual body-fill block was not found in generated code.")
        code = code.replace(actual_body_fill_anchor, NEW_DISABLE_ACTUAL_BODY_FILL_BLOCK, 1)
    elif sparse_actual_body_fill:
        if actual_body_fill_anchor is None:
            raise RuntimeError("Actual body-fill block was not found in generated code.")
        replacement = NEW_SPARSE_ACTUAL_BODY_FILL_BLOCK
        if actual_body_fill_anchor is CURRENT_ACTUAL_BODY_FILL_BLOCK:
            replacement = replacement.replace(
                "        if len(working_sections) >= 2:\n",
                "        if len(working_sections) >= 2 and (not disable_actual_body_fill):\n",
                1,
            )
        code = code.replace(actual_body_fill_anchor, replacement, 1)
    elif conservative_actual_body_fill:
        if actual_body_fill_anchor is None:
            raise RuntimeError("Actual body-fill block was not found in generated code.")
        replacement = NEW_CONSERVATIVE_ACTUAL_BODY_FILL_BLOCK
        if actual_body_fill_anchor is CURRENT_ACTUAL_BODY_FILL_BLOCK:
            replacement = replacement.replace(
                "        if len(working_sections) >= 2:\n",
                "        if len(working_sections) >= 2 and (not disable_actual_body_fill):\n",
                1,
            )
        code = code.replace(actual_body_fill_anchor, replacement, 1)
    if actual_body_z_trim_percentile is not None:
        trim_percentile = float(actual_body_z_trim_percentile)
        if trim_percentile > 0.0:
            if OLD_ACTUAL_EXTENSION_BASE_Z_LINE not in code:
                raise RuntimeError("Actual extension base-Z anchor was not found in generated code.")
            trim_percentile = max(0.0, min(45.0, trim_percentile))
            trim_labels = '("actual_stack",)' if actual_stack_z_trim_only else '("actual_stack", "actual_body_fill")'
            new_base_z_block = f"""        samples.sort(key=lambda item: item[0])
        body_trim_label = str(extension_side or "")
        if body_trim_label in {trim_labels}:
            try:
                trim_floor_z = float(np.percentile(np.asarray([item[0] for item in samples], dtype=float), {trim_percentile:.3f}))
                trimmed_samples = [item for item in samples if float(item[0]) >= trim_floor_z]
                if len(trimmed_samples) >= 4:
                    samples = trimmed_samples
            except Exception:
                pass
        base_z = float(samples[0][0])
"""
            code = code.replace(OLD_ACTUAL_EXTENSION_BASE_Z_LINE, new_base_z_block, 1)
    if apply_deferred_center_relief:
        if OLD_CENTER_RELIEF_BLOCK not in code:
            raise RuntimeError("Deferred center-relief anchor block was not found in generated code.")
        if OLD_POST_ASSEMBLY_BLOCK not in code:
            raise RuntimeError("Post-assembly solid-count block was not found in generated code.")
        code = code.replace(OLD_CENTER_RELIEF_BLOCK, NEW_CENTER_RELIEF_BLOCK, 1)
        code = code.replace(OLD_POST_ASSEMBLY_BLOCK, NEW_POST_ASSEMBLY_BLOCK, 1)
        if deferred_center_relief_annular:
            if OLD_NO_BOSS_VALLEY_INNER_BLOCK not in code:
                raise RuntimeError("No-boss valley inner-radius block was not found in generated code.")
            code = code.replace(OLD_NO_BOSS_VALLEY_INNER_BLOCK, NEW_NO_BOSS_VALLEY_INNER_ANNULAR_BLOCK, 1)
        if debug_deferred_center_relief:
            if OLD_VALLEY_CUT_BLOCK not in code:
                raise RuntimeError("Valley cut block was not found in generated code.")
            code = code.replace(OLD_VALLEY_CUT_BLOCK, NEW_VALLEY_CUT_DEBUG_BLOCK, 1)
    return code


def build_spoke_zoom(agent: EvaluationAgent, output_path: Path) -> None:
    visual_sample_size = int(agent.config.get("visual_sample_size", 32000))
    stl_points_raw = agent._sample_surface_points(agent.stl_mesh, agent.stl_vertices, sample_size=visual_sample_size)
    step_points_raw = agent._sample_surface_points(agent.step_mesh, agent.step_vertices, sample_size=visual_sample_size)

    stl_points = agent._canonicalize_wheel_points(stl_points_raw)
    step_points = agent._canonicalize_wheel_points(step_points_raw)
    step_points, align_meta = agent._align_step_to_stl_visual(stl_points, step_points)

    front_stl = agent._project_canonical_points(stl_points, "front")
    front_step = agent._project_canonical_points(step_points, "front")
    spoke_band_stl = agent._filter_spoke_band(front_stl)
    spoke_band_step = agent._filter_spoke_band(front_step)
    spoke_angle = agent._estimate_single_spoke_angle(spoke_band_stl, spoke_band_step)

    stl_spoke = agent._extract_single_spoke_closeup(front_stl, spoke_angle)
    step_spoke = agent._extract_single_spoke_closeup(front_step, spoke_angle)
    stl_spoke, step_spoke, orient_deg = agent._orient_closeup_pair(stl_spoke, step_spoke)

    fig, axes = plt.subplots(1, 3, figsize=(16, 5.8))
    panels = [
        ("STL single spoke", True, False),
        ("STEP single spoke", False, True),
        ("Overlay single spoke", True, True),
    ]

    for ax, (title, show_stl, show_step) in zip(axes, panels):
        if show_stl:
            agent._plot_projected_points(ax, stl_spoke, color="#1f77b4", label="STL", point_size=1.3, alpha=0.65)
        if show_step:
            agent._plot_projected_points(ax, step_spoke, color="#2ca02c", label="STEP", point_size=1.3, alpha=0.65)
        agent._set_projection_limits(ax, [stl_spoke, step_spoke], zoom=1.0)
        ax.set_title(
            f"{title}\nangle={spoke_angle:.1f} deg orient={orient_deg:.1f} deg align={align_meta.get('axial_rotation_deg', 0.0):.1f} deg"
        )
        if show_stl or show_step:
            ax.legend(loc="upper right", frameon=False, markerscale=8)

    plt.tight_layout()
    plt.savefig(output_path, dpi=170, bbox_inches="tight")
    plt.close(fig)


def percentile(values: np.ndarray, q: float) -> float:
    if values is None or len(values) == 0:
        return float("nan")
    return float(np.percentile(values, q))


def compute_metrics(agent: EvaluationAgent) -> Dict[str, Any]:
    visual_sample_size = int(agent.config.get("visual_sample_size", 32000))
    stl_points_raw = agent._sample_surface_points(agent.stl_mesh, agent.stl_vertices, sample_size=visual_sample_size)
    step_points_raw = agent._sample_surface_points(agent.step_mesh, agent.step_vertices, sample_size=visual_sample_size)

    stl_points = agent._canonicalize_wheel_points(stl_points_raw)
    step_points = agent._canonicalize_wheel_points(step_points_raw)
    step_points, align_meta = agent._align_step_to_stl_visual(stl_points, step_points)

    front_stl = agent._project_canonical_points(stl_points, "front")
    front_step = agent._project_canonical_points(step_points, "front")
    side_stl = agent._project_canonical_points(stl_points, "side")
    side_step = agent._project_canonical_points(step_points, "side")

    spoke_band_stl = agent._filter_spoke_band(front_stl)
    spoke_band_step = agent._filter_spoke_band(front_step)
    spoke_angle = agent._estimate_single_spoke_angle(spoke_band_stl, spoke_band_step)
    stl_spoke = agent._extract_single_spoke_closeup(front_stl, spoke_angle)
    step_spoke = agent._extract_single_spoke_closeup(front_step, spoke_angle)
    stl_spoke, step_spoke, orient_deg = agent._orient_closeup_pair(stl_spoke, step_spoke)

    step_tree = cKDTree(step_points) if len(step_points) else None
    stl_tree = cKDTree(stl_points) if len(stl_points) else None
    forward_dist = step_tree.query(stl_points, k=1)[0] if step_tree is not None and len(stl_points) else np.array([])
    backward_dist = stl_tree.query(step_points, k=1)[0] if stl_tree is not None and len(step_points) else np.array([])

    return {
        "front_overlap": float(agent._projection_overlap_score(front_stl, front_step, bins=140)),
        "side_overlap": float(agent._projection_overlap_score(side_stl, side_step, bins=130)),
        "spoke_overlap": float(agent._projection_overlap_score(stl_spoke, step_spoke, bins=120)),
        "nn_mean_fwd_mm": float(np.mean(forward_dist)) if len(forward_dist) else float("nan"),
        "nn_mean_bwd_mm": float(np.mean(backward_dist)) if len(backward_dist) else float("nan"),
        "nn_p95_fwd_mm": percentile(forward_dist, 95.0),
        "nn_p95_bwd_mm": percentile(backward_dist, 95.0),
        "nn_max_fwd_mm": float(np.max(forward_dist)) if len(forward_dist) else float("nan"),
        "nn_max_bwd_mm": float(np.max(backward_dist)) if len(backward_dist) else float("nan"),
        "axial_rotation_deg": float(align_meta.get("axial_rotation_deg", 0.0)),
        "axis_signs": list(align_meta.get("axis_signs", (1.0, 1.0, 1.0))),
        "align_score": float(align_meta.get("score", float("nan"))),
        "translation": list(align_meta.get("translation", (0.0, 0.0, 0.0))),
        "spoke_angle_deg": float(spoke_angle),
        "spoke_orient_deg": float(orient_deg),
        "stl_samples": int(len(stl_points)),
        "step_samples": int(len(step_points)),
    }


def execute_generated_code(code: str, virtual_file: Path) -> Dict[str, Any]:
    namespace: Dict[str, Any] = {
        "__file__": str(virtual_file),
        "__name__": "__main__",
    }
    compiled = compile(code, str(virtual_file), "exec")
    exec(compiled, namespace)
    return namespace


def post_fuse_small_solid_result(result: Any, namespace: Dict[str, Any], solid_limit: int) -> Tuple[Any, int]:
    solid_count_fn = namespace.get("solid_count_of_body")
    body_valid_fn = namespace.get("body_has_valid_shape")
    try:
        initial_solids = int(solid_count_fn(result)) if callable(solid_count_fn) else len(result.solids().vals())
    except Exception:
        return result, -1
    if initial_solids <= 1 or initial_solids > int(solid_limit):
        return result, initial_solids

    try:
        solids = list(result.solids().vals())
    except Exception:
        solids = []
    if len(solids) <= 1 or len(solids) > int(solid_limit):
        return result, initial_solids

    print(f"[*] Post-fusing small-solid result: solids={len(solids)}, limit={int(solid_limit)}")
    merged = cq.Workplane("XY").newObject([solids[0]])

    for idx, solid in enumerate(solids[1:], start=1):
        other = cq.Workplane("XY").newObject([solid])
        merged_this_solid = False
        for tag, kwargs in (("plain", {}), ("glue", {"glue": True})):
            try:
                candidate = merged.union(other, **kwargs)
                candidate_solids = int(solid_count_fn(candidate)) if callable(solid_count_fn) else len(candidate.solids().vals())
                valid_candidate = bool(body_valid_fn(candidate)) if callable(body_valid_fn) else candidate_solids > 0
                print(f"[*] post-fuse union {idx} {tag}: solids={candidate_solids}, valid={valid_candidate}")
                if valid_candidate and candidate_solids <= max(1, initial_solids - idx):
                    merged = candidate
                    merged_this_solid = True
                    break
            except Exception as exc:
                print(f"[!] post-fuse union {idx} {tag} failed: {exc}")
        if not merged_this_solid:
            print(f"[!] post-fuse abandoned at solid {idx}; preserving original result")
            return result, initial_solids

    try:
        cleaned = merged.clean()
        cleaned_solids = int(solid_count_fn(cleaned)) if callable(solid_count_fn) else len(cleaned.solids().vals())
        if cleaned_solids == 1 and (bool(body_valid_fn(cleaned)) if callable(body_valid_fn) else True):
            merged = cleaned
    except Exception:
        pass

    final_solids = int(solid_count_fn(merged)) if callable(solid_count_fn) else len(merged.solids().vals())
    if final_solids == 1:
        print("[*] Post-fuse small-solid result accepted: solids=1")
        return merged, final_solids

    print(f"[!] Post-fuse small-solid result rejected: solids={final_solids}")
    return result, initial_solids


def main() -> None:
    parser = argparse.ArgumentParser(description="Patch and evaluate a generated wheel model without re-running perception.")
    parser.add_argument("--generated", required=True, help="Source generated.py path")
    parser.add_argument("--stl", default=str(ROOT / "input" / "wheel.stl"), help="Reference STL path")
    parser.add_argument("--features", required=True, help="Features JSON path")
    parser.add_argument("--output-dir", default=str(ROOT / "output"), help="Output directory")
    parser.add_argument("--label", default="retryal", help="Artifact label prefix")
    parser.add_argument("--visual-sample-size", type=int, default=30000, help="Visualization and metrics sample count")
    parser.add_argument(
        "--max-direct-merge-member-solids",
        type=int,
        default=1,
        help="Only members with this many solids or fewer attempt fragment-wise boolean merge; larger members use compound fallback.",
    )
    parser.add_argument(
        "--apply-deferred-center-relief",
        action="store_true",
        help="Re-apply deferred unified center valley relief after additive spoke merge when the merged body is a single solid.",
    )
    parser.add_argument(
        "--deferred-center-relief-annular",
        action="store_true",
        help="For deferred center relief, trim no-boss valleys as an annular band near the spoke-root outer radius instead of cutting from the bore outward.",
    )
    parser.add_argument(
        "--debug-deferred-center-relief",
        action="store_true",
        help="Emit per-valley debug logging for deferred center relief candidates and processed cuts.",
    )
    parser.add_argument(
        "--disable-actual-section-overrides",
        action="store_true",
        help="Keep measured radial spoke sections instead of replacing them with sections reconstructed from actual XY@Z slices.",
    )
    parser.add_argument(
        "--disable-actual-body-fill",
        action="store_true",
        help="Skip inserting intermediate body-fill sections reconstructed from actual XY@Z slices.",
    )
    parser.add_argument(
        "--conservative-actual-body-fill",
        action="store_true",
        help="Keep actual body-fill enabled but reduce fill density so only large gaps get bridged by a small number of derived sections.",
    )
    parser.add_argument(
        "--sparse-actual-body-fill",
        action="store_true",
        help="Use an even sparser actual body-fill strategy that inserts at most one midpoint section across only large radial gaps.",
    )
    parser.add_argument(
        "--disable-donor-root-actual",
        action="store_true",
        help="Disable donor_root_actual radial extrapolation near the hub so spoke roots rely on real sections instead of root-side donor widening.",
    )
    parser.add_argument(
        "--disable-donor-tip-actual",
        action="store_true",
        help="Disable donor_tip_actual radial extrapolation near the rim so spoke tips rely on captured tip sections instead of tip-side donor widening.",
    )
    parser.add_argument(
        "--drop-template-root-sections",
        action="store_true",
        help="Drop original template root extension sections when real XY@Z profiles exist, so spoke roots depend on actual sections instead of root-side scaffolding.",
    )
    parser.add_argument(
        "--keep-template-root-sections",
        type=int,
        default=None,
        help="When real XY@Z profiles exist, keep only this many nearest template root extension sections instead of preserving the whole root scaffold.",
    )
    parser.add_argument(
        "--root-override-from-first-actual",
        action="store_true",
        help="When rebuilding sections from actual XY@Z slices, make root extension sections inherit the first real body section instead of the original root template.",
    )
    parser.add_argument(
        "--anchored-actual-y-band",
        action="store_true",
        help="When a real XY@Z probe hits multiple Y bands, select the band closest to the anchor section instead of spanning the full min/max width.",
    )
    parser.add_argument(
        "--actual-body-z-trim-percentile",
        type=float,
        default=None,
        help="For actual_stack/actual_body_fill sections, trim away the lowest-Z slice tail below this percentile before building local-section loops.",
    )
    parser.add_argument(
        "--post-fuse-small-solid-limit",
        type=int,
        default=0,
        help="After generation, attempt pairwise booleans when the result has more than one and at most this many solids.",
    )
    parser.add_argument(
        "--actual-stack-z-trim-only",
        action="store_true",
        help="When trimming low-Z tails on actual-derived sections, apply the trim only to actual_stack overrides and leave actual_body_fill sections unchanged.",
    )
    args = parser.parse_args()

    generated_path = Path(args.generated).resolve()
    features_path = Path(args.features).resolve()
    stl_path = Path(args.stl).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"wheel_attach_{args.label}_{timestamp}"
    patched_generated_path = output_dir / f"{stem}.generated.py"
    step_path = output_dir / f"{stem}.step"
    compare_stl_path = output_dir / f"{stem}_compare.stl"
    metrics_path = output_dir / f"{stem}.metrics.json"
    compare_dir = output_dir / f"compare_{stem}"
    compare_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Source generated.py: {generated_path}")
    print(f"[*] Output stem: {stem}")
    print(f"[*] Max direct-merge member solids: {args.max_direct_merge_member_solids}")
    print(f"[*] Apply deferred center relief: {bool(args.apply_deferred_center_relief)}")
    print(f"[*] Deferred center relief annular mode: {bool(args.deferred_center_relief_annular)}")
    print(f"[*] Deferred center relief debug: {bool(args.debug_deferred_center_relief)}")
    print(f"[*] Disable actual section overrides: {bool(args.disable_actual_section_overrides)}")
    print(f"[*] Disable actual body fill: {bool(args.disable_actual_body_fill)}")
    print(f"[*] Conservative actual body fill: {bool(args.conservative_actual_body_fill)}")
    print(f"[*] Sparse actual body fill: {bool(args.sparse_actual_body_fill)}")
    print(f"[*] Disable donor root actual: {bool(args.disable_donor_root_actual)}")
    print(f"[*] Disable donor tip actual: {bool(args.disable_donor_tip_actual)}")
    print(f"[*] Drop template root sections: {bool(args.drop_template_root_sections)}")
    print(f"[*] Keep template root sections: {args.keep_template_root_sections}")
    print(f"[*] Root override from first actual: {bool(args.root_override_from_first_actual)}")
    print(f"[*] Anchored actual Y band: {bool(args.anchored_actual_y_band)}")
    print(f"[*] Actual body Z trim percentile: {args.actual_body_z_trim_percentile}")
    print(f"[*] Post-fuse small-solid limit: {int(args.post_fuse_small_solid_limit)}")
    print(f"[*] Actual-stack Z trim only: {bool(args.actual_stack_z_trim_only)}")

    source_text = generated_path.read_text(encoding="utf-8")
    patched_code = patch_generated_code(
        source_text,
        max_direct_merge_member_solids=args.max_direct_merge_member_solids,
        apply_deferred_center_relief=bool(args.apply_deferred_center_relief),
        deferred_center_relief_annular=bool(args.deferred_center_relief_annular),
        debug_deferred_center_relief=bool(args.debug_deferred_center_relief),
        disable_actual_section_overrides=bool(args.disable_actual_section_overrides),
        disable_actual_body_fill=bool(args.disable_actual_body_fill),
        conservative_actual_body_fill=bool(args.conservative_actual_body_fill),
        sparse_actual_body_fill=bool(args.sparse_actual_body_fill),
        disable_donor_root_actual=bool(args.disable_donor_root_actual),
        disable_donor_tip_actual=bool(args.disable_donor_tip_actual),
        drop_template_root_sections=bool(args.drop_template_root_sections),
        keep_template_root_sections=args.keep_template_root_sections,
        root_override_from_first_actual=bool(args.root_override_from_first_actual),
        anchored_actual_y_band=bool(args.anchored_actual_y_band),
        actual_body_z_trim_percentile=args.actual_body_z_trim_percentile,
        actual_stack_z_trim_only=bool(args.actual_stack_z_trim_only),
    )
    patched_generated_path.write_text(patched_code, encoding="utf-8", newline="\n")
    print(f"[*] Patched generated.py written: {patched_generated_path}")

    os.chdir(ROOT)
    namespace = execute_generated_code(patched_code, patched_generated_path)
    result = namespace.get("result")
    if result is None:
        raise RuntimeError("Patched generated code did not produce global `result`.")

    solid_count_fn = namespace.get("solid_count_of_body")
    result_solids = int(solid_count_fn(result)) if callable(solid_count_fn) else -1
    print(f"[*] Result solid count: {result_solids}")
    if int(args.post_fuse_small_solid_limit) > 1:
        result, result_solids = post_fuse_small_solid_result(
            result,
            namespace,
            int(args.post_fuse_small_solid_limit),
        )
        print(f"[*] Result solid count after post-fuse: {result_solids}")

    cq.exporters.export(result, str(step_path))
    print(f"[*] STEP exported: {step_path}")

    try:
        cq.exporters.export(
            result,
            str(compare_stl_path),
            tolerance=0.8,
            angularTolerance=0.8,
        )
        print(f"[*] Compare STL exported: {compare_stl_path}")
    except Exception as exc:
        print(f"[!] Compare STL export failed: {exc}")

    agent = EvaluationAgent(
        stl_path=str(stl_path),
        step_path=str(step_path),
        features_path=str(features_path),
        config={
            "visual_sample_size": int(args.visual_sample_size),
            "step_mesh_fallback_path": str(compare_stl_path) if compare_stl_path.exists() else None,
        },
    )
    comparison_path = compare_dir / "evaluation_comparison.png"
    agent.visualize_comparison(str(comparison_path))
    build_spoke_zoom(agent, compare_dir / "evaluation_comparison_spoke_zoom.png")

    metrics = compute_metrics(agent)
    metrics["step_path"] = str(step_path)
    metrics["generated_path"] = str(patched_generated_path)
    metrics["compare_dir"] = str(compare_dir)
    metrics["compare_stl_path"] = str(compare_stl_path) if compare_stl_path.exists() else None
    metrics["result_solids"] = result_solids

    metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    (compare_dir / "custom_metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")

    print("[*] Metrics summary:")
    for key in (
        "front_overlap",
        "side_overlap",
        "spoke_overlap",
        "nn_mean_fwd_mm",
        "nn_mean_bwd_mm",
        "nn_p95_fwd_mm",
        "nn_p95_bwd_mm",
        "result_solids",
    ):
        print(f"    {key}={metrics.get(key)}")
    print(f"[*] Metrics saved: {metrics_path}")
    print(f"[*] Compare bundle: {compare_dir}")


if __name__ == "__main__":
    main()
