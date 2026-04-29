"""Modeling code generation extracted from the main STL-to-STEP pipeline."""


"""
LEGACY IMPLEMENTATION SURFACE.

Do not mine this file for alternative spoke, groove, actual_z, or revolve strategies.
The active accepted route is pinned in tools/build_current_wheel_model.py.
Historical branches remain here only until they can be moved behind a clean implementation boundary.
"""


def generate_cadquery_code(json_features):
    """Generate the current production CadQuery program for one feature payload."""
    print("[*] Module B: ?????? CadQuery ???...")
    return _mock_llm_response(json_features)

def _mock_llm_response(features):
    """
    [??????] ??????????????????
    ?????olyline Rim, Loft Spoke, Robust Fallback??
    """
    # 1. ??????????
    params = features['global_params']
    
    # --- ?? ??????????? Hub ?????? ---
    current_hub_r = params.get("hub_radius", 0)
    safe_hub_r = max(
        params.get("bore_radius", 30.0) + 6.0,
        params.get("pcd_radius", 57.0) + params.get("hole_radius", 7.5) + 2.0
    )
    if current_hub_r > safe_hub_r * 1.6 or current_hub_r < params.get("bore_radius", 30.0) + 2.0:
        print(f"[!] ???: hub_radius ???????({current_hub_r})?????????PCD ?????...")
        params["hub_radius"] = round(safe_hub_r, 2)
        print(f"[*] ??????????????????? -> Hub Radius: {params['hub_radius']} mm")
    else:
        print(f"[*] ??????????????????? -> Hub Radius: {current_hub_r} mm")
    # ----------------------------------------
    
    rim_prof = features['rim_profile']
    
    # ??????????????????????
    R_val = params['rim_max_radius']
    W_val = params['rim_width']
    T_rim_val = params.get('rim_thickness', 5.0)
    
    # ??????????(?????)
    w_raw = params.get('spoke_width', 20.0)
    t_raw = params.get('spoke_thickness', 15.0)
    W_spoke_val = max(15.0, min(w_raw, 40.0))
    T_spoke_val = max(10.0, min(t_raw, 30.0))
    
    # Hub & PCD Params (Use defaults if missing)
    hub_thick_val = params.get('hub_thickness', 40.0)
    hub_z_val = params.get('hub_z_offset', 0.0)
    hub_r_val = params.get('hub_radius', R_val*0.15)
    
    # New Perception Params
    hub_top_z_val = params.get('hub_top_z', hub_z_val + hub_thick_val)
    hub_face_z_val = params.get('hub_face_z', hub_top_z_val)
    hub_crown_height_val = params.get('hub_crown_height', max(0.0, hub_top_z_val - hub_face_z_val))
    hub_outer_draft_val = params.get('hub_outer_draft', 0.0)
    hub_front_inset_val = params.get('hub_front_inset')
    dish_depth_val = params.get('dish_depth', 0.0)
    pocket_r_val = params.get('pocket_radius')
    pocket_top_z_val = params.get('pocket_top_z')
    pocket_top_inset_val = params.get('pocket_top_inset')
    pocket_floor_z_val = params.get('pocket_floor_z')
    pocket_depth_val = params.get('pocket_depth')
    pocket_floor_r_val = params.get('pocket_floor_radius')
    window_inner_ref_r_val = params.get('window_inner_reference_r')
    
    # Spoke Tapering (Draft Angle)
    w_spoke_root = W_spoke_val * 1.2
    w_spoke_tip = W_spoke_val * 0.8
    
    pcd_r_val = params.get('pcd_radius', 57.0)
    hole_r_val = params.get('hole_radius', 7.5)
    hole_cnt_val = params.get('hole_count', 5)
    pcd_phase_val = params.get('pcd_phase_angle', 0.0) # ????????
    
    N_val = params.get('spoke_num', 5)
    bore_r_val = params.get('bore_radius', 30.0)
    
    # ??????
    real_pts = rim_prof.get('points', [])
    pts_data = [tuple(p) for p in real_pts] if real_pts else []
    
    # ??? Spoke Voids
    spoke_voids = features.get('spoke_voids', [])
    spoke_voids_data = spoke_voids
    window_inner_reference_radii_data = features.get('window_inner_reference_radii', [])
    window_local_keepouts_data = features.get('window_local_keepouts', [])
    window_local_root_outer_radii_data = features.get('window_local_root_outer_radii', [])
    spoke_regions_data = features.get('spoke_regions', [])
    spoke_sections_data = features.get('spoke_sections', [])
    spoke_tip_sections_data = features.get('spoke_tip_sections', [])
    spoke_motif_topology_data = features.get('spoke_motif_topology', {})
    spoke_motif_sections_data = features.get('spoke_motif_sections', [])
    canonical_spoke_templates_data = features.get('canonical_spoke_templates', [])
    lug_boss_regions_data = features.get('lug_boss_regions', [])
    spoke_root_regions_data = features.get('spoke_root_regions', [])
    center_core_region_data = features.get('center_core_region', {})
    hub_bottom_groove_regions_data = features.get('hub_bottom_groove_regions', [])
    guarded_section_region_data = features.get('guarded_section_region', {})
    spokeless_guarded_section_region_data = features.get('spokeless_guarded_section_region', {})
    spokeless_guarded_section_regions_data = features.get('spokeless_guarded_section_regions', [])
    spokeless_reference_fragments_data = features.get('spokeless_reference_fragments', {})
    spokeless_profile_regions_data = features.get('spokeless_profile_regions', [])
    spokeless_baseline_regions_data = features.get('spokeless_baseline_regions', [])
    spokeless_nospoke_regions_data = features.get('spokeless_nospoke_regions', [])
    disable_spokes_modeling = bool(features.get('disable_spokes_modeling', False))

    # ????????????
    spoke_face = features.get('spoke_face', {})
    spoke_face_boundary = spoke_face.get('boundary', [])
    spoke_face_boundary_data = [tuple(p) for p in spoke_face_boundary] if spoke_face_boundary else []
    
    # ??? Hub Profile
    hub_prof = features.get('hub_profile', {})
    hub_pts = hub_prof.get('points', [])
    if hub_pts:
        hub_profile_outer_r = max([p[0] for p in hub_pts])
        if hub_profile_outer_r > params["hub_radius"] * 1.35:
            print(
                f"[!] Hub profile contaminated by oversized radius ({hub_profile_outer_r:.2f} mm). "
                "Falling back to cylindrical hub body."
            )
            hub_pts = []
    hub_pts_data = [tuple(p) for p in hub_pts]
    rotary_face_prof = features.get('rotary_face_profile', {})
    rotary_face_pts = rotary_face_prof.get('points', [])
    rotary_face_pts_data = [tuple(p) for p in rotary_face_pts] if rotary_face_pts else []
    
    # 2. ????? (????????)
    code = f"""
import cadquery as cq
import builtins
import math
import numpy as np
import matplotlib.pyplot as plt
from shapely.geometry import Polygon, MultiPolygon, Point, LineString, MultiLineString, GeometryCollection
from shapely.ops import unary_union

def safe_print(*args, **kwargs):
    try:
        builtins.print(*args, **kwargs)
    except (OSError, ValueError):
        pass

print = safe_print

# Data Injection
json_data = {{
    "rim_profile": {{"points": {pts_data}}},
    "spoke_face": {{"boundary": {spoke_face_boundary_data}, "z": {spoke_face.get('z', hub_z_val)}}},
    "spoke_voids": {spoke_voids_data},
    "window_inner_reference_radii": {window_inner_reference_radii_data},
    "window_local_keepouts": {window_local_keepouts_data},
    "window_local_root_outer_radii": {window_local_root_outer_radii_data},
    "spoke_regions": {spoke_regions_data},
    "spoke_sections": {spoke_sections_data},
    "spoke_tip_sections": {spoke_tip_sections_data},
    "spoke_motif_topology": {spoke_motif_topology_data},
    "spoke_motif_sections": {spoke_motif_sections_data},
    "canonical_spoke_templates": {canonical_spoke_templates_data},
    "lug_boss_regions": {lug_boss_regions_data},
    "spoke_root_regions": {spoke_root_regions_data},
    "center_core_region": {center_core_region_data},
    "hub_bottom_groove_regions": {hub_bottom_groove_regions_data},
    "hub_profile": {{"points": {hub_pts_data}}},
    "rotary_face_profile": {{"points": {rotary_face_pts_data}}},
    "guarded_section_region": {guarded_section_region_data},
    "spokeless_guarded_section_region": {spokeless_guarded_section_region_data},
    "spokeless_guarded_section_regions": {spokeless_guarded_section_regions_data},
    "spokeless_reference_fragments": {spokeless_reference_fragments_data},
    "spokeless_profile_regions": {spokeless_profile_regions_data},
    "spokeless_baseline_regions": {spokeless_baseline_regions_data},
    "spokeless_nospoke_regions": {spokeless_nospoke_regions_data},
    "prefer_fragmented_spokeless_base": {repr(bool(features.get("prefer_fragmented_spokeless_base", False)))},
    "disable_spokes_modeling": {repr(disable_spokes_modeling)},
    "spokeless_hybrid_region": {features.get("spokeless_hybrid_region", {})},
    "spokeless_hybrid_profile": {features.get("spokeless_hybrid_profile", [])},
    "debug_output_root": {repr(features.get("debug_output_root", ""))},
    "fast_spoke_validation_mode": {repr(bool(features.get("fast_spoke_validation_mode", False)))},
    "global_params": {{
        "rim_thickness": {T_rim_val},
        "rim_max_radius": {R_val},
        "rim_width": {W_val},
        "hub_z_offset": {hub_z_val},
        "hub_thickness": {hub_thick_val},
        "spoke_num": {N_val},
        "hole_count": {hole_cnt_val},
        "hub_radius": {hub_r_val},
        "bore_radius": {bore_r_val},
        "pcd_radius": {pcd_r_val},
        "hole_radius": {hole_r_val},
        "pcd_phase_angle": {pcd_phase_val},
        "pocket_radius": {pocket_r_val},
        "hub_top_z": {hub_top_z_val},
        "hub_face_z": {hub_face_z_val},
        "hub_outer_face_z": {params.get('hub_outer_face_z')},
        "hub_crown_height": {hub_crown_height_val},
        "hub_outer_draft": {hub_outer_draft_val},
        "hub_front_inset": {hub_front_inset_val},
        "center_relief_z": {params.get('center_relief_z')},
        "dish_depth": {dish_depth_val},
        "window_inner_reference_r": {window_inner_ref_r_val},
        "pocket_top_z": {pocket_top_z_val},
        "pocket_top_inset": {pocket_top_inset_val},
        "pocket_floor_z": {pocket_floor_z_val},
        "pocket_depth": {pocket_depth_val},
        "pocket_floor_radius": {pocket_floor_r_val},
        "hub_bottom_groove_floor_z": {params.get('hub_bottom_groove_floor_z')},
        "hub_bottom_groove_top_z": {params.get('hub_bottom_groove_top_z')}
    }}
}}

# 1. Unpack Data
pts = json_data["rim_profile"]["points"]
spoke_face_boundary = json_data["spoke_face"]["boundary"]
spoke_face_z = json_data["spoke_face"].get("z", 0.0)
hub_pts = json_data["hub_profile"]["points"]
rotary_face_pts = json_data.get("rotary_face_profile", {{}}).get("points", [])
guarded_section_region = json_data.get("guarded_section_region", {{}})
spokeless_guarded_section_region = json_data.get("spokeless_guarded_section_region", {{}})
spokeless_guarded_section_regions = json_data.get("spokeless_guarded_section_regions", [])
spokeless_reference_fragments = json_data.get("spokeless_reference_fragments", {{}})
spokeless_profile_regions = json_data.get("spokeless_profile_regions", [])
spokeless_baseline_regions = json_data.get("spokeless_baseline_regions", [])
spokeless_nospoke_regions = json_data.get("spokeless_nospoke_regions", [])
prefer_fragmented_spokeless_base = bool(json_data.get("prefer_fragmented_spokeless_base", False))
disable_spokes_modeling = bool(json_data.get("disable_spokes_modeling", False))
spokeless_hybrid_region = json_data.get("spokeless_hybrid_region", {{}})
spokeless_hybrid_profile = json_data.get("spokeless_hybrid_profile", [])
voids = json_data["spoke_voids"]
window_inner_ref_radii = json_data.get("window_inner_reference_radii", [])
window_local_keepouts = json_data.get("window_local_keepouts", [])
window_local_root_outer_radii = json_data.get("window_local_root_outer_radii", [])
spoke_regions = json_data["spoke_regions"]
spoke_section_groups = json_data["spoke_sections"]
spoke_tip_section_groups = json_data["spoke_tip_sections"]
spoke_motif_topology = json_data.get("spoke_motif_topology", {{}})
spoke_motif_groups = json_data.get("spoke_motif_sections", [])
canonical_spoke_templates = json_data.get("canonical_spoke_templates", [])
lug_boss_regions = json_data.get("lug_boss_regions", [])
spoke_root_regions = json_data.get("spoke_root_regions", [])
center_core_region = json_data.get("center_core_region", {{}})
hub_bottom_groove_regions = json_data.get("hub_bottom_groove_regions", [])
debug_output_root = json_data.get("debug_output_root", "")
fast_spoke_validation_mode = bool(json_data.get("fast_spoke_validation_mode", False))
params = json_data["global_params"]
if spoke_face_z <= 0:
    spoke_face_z = params.get("hub_top_z", params.get("hub_z_offset", 0.0) + 10.0)
enable_guarded_section_modeling = bool(guarded_section_region)
enable_rotary_rim_shoulder = True
enable_local_rotary_center = True
canonical_spoke_templates_by_slot = {{
    int(template_payload.get("slot_index", idx)): template_payload
    for idx, template_payload in enumerate(canonical_spoke_templates or [])
    if isinstance(template_payload, dict)
}}
canonical_local_section_templates_by_slot = None

if guarded_section_region:
    print("[*] Guarded section center available. Perception-driven center revolve preferred.")
if rotary_face_pts:
    print("[*] Rotary face profile retained for controlled local refinement.")
if spoke_motif_groups:
    print(
        f"[*] Spoke motif payload available: "
        f"type={{spoke_motif_topology.get('motif_type', 'unknown')}}, "
        f"motifs={{len(spoke_motif_groups)}}"
    )
if disable_spokes_modeling:
    print("[*] Spoke modeling disabled. Building stable hub/rim baseline without spoke solids or window cuts.")

hub_groove_debug_bodies = []

def safe_cut(base, cutter, label):
    if base is None or cutter is None:
        return base
    try:
        candidate = base.cut(cutter)
        if not body_has_valid_shape(candidate):
            print(f"[!] {{label}} cut discarded: invalid shape")
            return base
        return candidate
    except Exception as exc:
        print(f"[!] {{label}} cut failed: {{exc}}")
        return base

def safe_union(base, other, label):
    if base is None:
        return other if body_has_valid_shape(other) else base
    if other is None:
        return base
    try:
        candidate = base.union(other)
        if not body_has_valid_shape(candidate):
            try:
                glued_candidate = base.union(other, glue=True)
            except Exception:
                glued_candidate = None
            if glued_candidate is not None and body_has_valid_shape(glued_candidate):
                print(f"[*] {{label}} union healed by glue=True")
                return glued_candidate
            try:
                cleaned_candidate = candidate.clean()
            except Exception:
                cleaned_candidate = None
            if cleaned_candidate is not None and body_has_valid_shape(cleaned_candidate):
                print(f"[*] {{label}} union healed by clean()")
                return cleaned_candidate
            print(f"[!] {{label}} union discarded: invalid shape")
            return base
        return candidate
    except Exception as exc:
        try:
            glued_candidate = base.union(other, glue=True)
        except Exception:
            glued_candidate = None
        if glued_candidate is not None and body_has_valid_shape(glued_candidate):
            print(f"[*] {{label}} union recovered after exception via glue=True")
            return glued_candidate
        try:
            cleaned_base = base.clean()
            cleaned_other = other.clean()
            cleaned_candidate = cleaned_base.union(cleaned_other, glue=True)
        except Exception:
            cleaned_candidate = None
        if cleaned_candidate is not None and body_has_valid_shape(cleaned_candidate):
            print(f"[*] {{label}} union recovered after exception via clean()+glue")
            return cleaned_candidate
        print(f"[!] {{label}} union failed: {{exc}}")
        return base

def safe_intersect(base, other, label):
    if base is None or other is None:
        return None
    try:
        candidate = base.intersect(other)
        if not body_has_valid_shape(candidate):
            print(f"[!] {{label}} intersect discarded: invalid shape")
            return None
        return candidate
    except Exception as exc:
        print(f"[!] {{label}} intersect failed: {{exc}}")
        return None

def body_has_valid_shape(body, require_single_solid=False, min_volume=1e-3):
    if body is None:
        return False
    try:
        solids = body.solids().vals()
    except Exception:
        solids = []

    shapes = list(solids)
    if not shapes:
        try:
            val = body.val()
            shapes = [val]
        except Exception:
            return False

    if require_single_solid and len(shapes) != 1:
        return False

    for shape in shapes:
        try:
            if shape is None or shape.isNull():
                return False
            if hasattr(shape, "isValid") and (not shape.isValid()):
                return False
            if hasattr(shape, "Volume") and float(shape.Volume()) <= float(min_volume):
                return False
        except Exception:
            return False
    return True

def solid_count_of_body(body):
    if body is None:
        return 0
    try:
        return len(body.solids().vals())
    except Exception:
        try:
            body.val()
            return 1
        except Exception:
            return 0

def radial_extent_of_body(body):
    if body is None:
        return 0.0
    try:
        solids = body.solids().vals()
        if solids:
            max_extent = 0.0
            for solid in solids:
                bbox = solid.BoundingBox()
                max_extent = max(
                    max_extent,
                    abs(bbox.xmin), abs(bbox.xmax),
                    abs(bbox.ymin), abs(bbox.ymax)
                )
            return max_extent
    except Exception:
        pass
    try:
        bbox = body.val().BoundingBox()
        return max(
            abs(bbox.xmin), abs(bbox.xmax),
            abs(bbox.ymin), abs(bbox.ymax)
        )
    except Exception:
        return 0.0

def body_bbox(body):
    if body is None:
        return None
    try:
        solids = body.solids().vals()
    except Exception:
        solids = []
    try:
        if solids:
            xmin = min(float(solid.BoundingBox().xmin) for solid in solids)
            xmax = max(float(solid.BoundingBox().xmax) for solid in solids)
            ymin = min(float(solid.BoundingBox().ymin) for solid in solids)
            ymax = max(float(solid.BoundingBox().ymax) for solid in solids)
            zmin = min(float(solid.BoundingBox().zmin) for solid in solids)
            zmax = max(float(solid.BoundingBox().zmax) for solid in solids)
            return (xmin, xmax, ymin, ymax, zmin, zmax)
    except Exception:
        pass
    try:
        bb = body.val().BoundingBox()
        return (
            float(bb.xmin), float(bb.xmax),
            float(bb.ymin), float(bb.ymax),
            float(bb.zmin), float(bb.zmax)
        )
    except Exception:
        return None

def sort_components_by_radial_extent(components):
    active_components = [component for component in (components or []) if component is not None]
    try:
        active_components.sort(
            key=lambda component: float(radial_extent_of_body(component) or 0.0)
        )
    except Exception:
        pass
    return active_components

def bboxes_overlap(box_a, box_b, margin=0.8):
    if box_a is None or box_b is None:
        return True
    ax0, ax1, ay0, ay1, az0, az1 = box_a
    bx0, bx1, by0, by1, bz0, bz1 = box_b
    if ax1 + margin < bx0 or bx1 + margin < ax0:
        return False
    if ay1 + margin < by0 or by1 + margin < ay0:
        return False
    if az1 + margin < bz0 or bz1 + margin < az0:
        return False
    return True

def bbox_overlap_volume(box_a, box_b, margin=0.0):
    if box_a is None or box_b is None:
        return 0.0
    ax0, ax1, ay0, ay1, az0, az1 = box_a
    bx0, bx1, by0, by1, bz0, bz1 = box_b
    overlap_x = max(0.0, min(ax1 + margin, bx1 + margin) - max(ax0 - margin, bx0 - margin))
    overlap_y = max(0.0, min(ay1 + margin, by1 + margin) - max(ay0 - margin, by0 - margin))
    overlap_z = max(0.0, min(az1 + margin, bz1 + margin) - max(az0 - margin, bz0 - margin))
    return float(overlap_x * overlap_y * overlap_z)

def body_volume(body):
    if body is None:
        return None
    try:
        solids = body.solids().vals()
        if solids:
            return float(sum(float(solid.Volume()) for solid in solids))
    except Exception:
        pass
    try:
        return float(body.val().Volume())
    except Exception:
        return None

def face_count_of_body(body):
    if body is None:
        return 0
    try:
        return len(body.faces().vals())
    except Exception:
        try:
            val = body.val()
            return len(val.Faces())
        except Exception:
            return 0

def select_largest_solid_body(body, label):
    if body is None:
        return None
    try:
        solids = body.solids().vals()
    except Exception:
        solids = []
    if not solids:
        return body
    if len(solids) <= 1:
        return body
    try:
        largest_solid = max(solids, key=lambda solid: float(solid.Volume()))
        print(f"[*] {{label}} sanitized: keeping largest solid out of {{len(solids)}} fragments")
        return cq.Workplane("XY").newObject([largest_solid])
    except Exception as exc:
        print(f"[!] {{label}} sanitize failed: {{exc}}")
        return body

def finalize_member_body(body, label):
    body = select_largest_solid_body(body, label)
    if body is None:
        return None
    try:
        cleaned = body.clean()
    except Exception:
        cleaned = None
    if cleaned is not None and body_has_valid_shape(cleaned, require_single_solid=True):
        body = select_largest_solid_body(cleaned, f"{{label}} clean")
    if not body_has_valid_shape(body, require_single_solid=True):
        print(f"[!] {{label}} rejected: member body is not a valid single solid")
        return None
    try:
        return cq.Workplane("XY").newObject([body.findSolid()])
    except Exception:
        return body

def retain_significant_member_fragments(body, label, max_solids=2):
    if body is None:
        return None
    try:
        solids = body.solids().vals()
    except Exception:
        solids = []
    if len(solids) <= max(1, int(max_solids or 1)):
        return body

    fragment_rows = []
    for solid in solids:
        try:
            bbox = solid.BoundingBox()
            extent = max(
                abs(float(bbox.xmin)), abs(float(bbox.xmax)),
                abs(float(bbox.ymin)), abs(float(bbox.ymax))
            )
            z_span = max(0.0, float(bbox.zmax) - float(bbox.zmin))
            volume = float(solid.Volume())
        except Exception:
            continue
        if volume <= 1e-3:
            continue
        fragment_rows.append({{
            "solid": solid,
            "volume": volume,
            "extent": extent,
            "z_span": z_span
        }})

    if len(fragment_rows) <= max(1, int(max_solids or 1)):
        return body

    max_volume = max(float(row["volume"]) for row in fragment_rows)
    max_extent = max(float(row["extent"]) for row in fragment_rows)
    max_z_span = max(float(row["z_span"]) for row in fragment_rows)

    fragment_rows.sort(
        key=lambda row: (float(row["volume"]), float(row["extent"]), float(row["z_span"])),
        reverse=True
    )

    kept_rows = []
    for row in fragment_rows:
        volume_ratio = float(row["volume"]) / max(1e-6, max_volume)
        extent_ratio = float(row["extent"]) / max(1e-6, max_extent)
        z_ratio = float(row["z_span"]) / max(1e-6, max_z_span)
        keep_row = (
            (not kept_rows) or
            volume_ratio >= 0.18 or
            extent_ratio >= 0.95 or
            (extent_ratio >= 0.82 and z_ratio >= 0.45)
        )
        if keep_row:
            kept_rows.append(row)
        if len(kept_rows) >= max(1, int(max_solids or 1)):
            break

    if not kept_rows:
        return body

    try:
        retained_body = cq.Workplane("XY").newObject([row["solid"] for row in kept_rows])
        print(
            f"[*] {{label}} fragment retention reduced solids: "
            f"kept={{len(kept_rows)}}/{{len(fragment_rows)}}"
        )
        return retained_body
    except Exception as exc:
        print(f"[!] {{label}} fragment retention failed: {{exc}}")
        return body

def explode_body_to_single_solids(body):
    if body is None:
        return []
    try:
        solids = body.solids().vals()
    except Exception:
        solids = []
    if solids:
        return [cq.Workplane("XY").newObject([solid]) for solid in solids]
    return [body]

def merge_member_into_components(
    components,
    member_body,
    member_label,
    allow_nearby_standalone=False,
    preferred_component_indices=None
):
    if member_body is None:
        return list(components or []), False, len(components or [])

    active_components = list(components or [])
    member_fragments = explode_body_to_single_solids(member_body)
    if not member_fragments:
        return active_components, False, len(active_components)

    merged_any = False
    for fragment_idx, member_fragment in enumerate(member_fragments):
        working_fragment = member_fragment
        fragment_box = body_bbox(working_fragment)
        touched_indices = []
        candidate_components = []
        for idx, component in enumerate(active_components):
            if component is None:
                continue
            component_solid_count = solid_count_of_body(component)
            if component_solid_count <= 0:
                continue
            component_box = body_bbox(component)
            if not bboxes_overlap(component_box, fragment_box, margin=1.6):
                continue
            overlap_score = bbox_overlap_volume(component_box, fragment_box, margin=1.2)
            candidate_components.append((overlap_score, idx, component, component_box, component_solid_count))

        preferred_order = None
        if preferred_component_indices:
            preferred_order = {{
                int(component_idx): order_idx
                for order_idx, component_idx in enumerate(preferred_component_indices)
            }}
        if preferred_order:
            candidate_components.sort(
                key=lambda item: (
                    int(preferred_order.get(int(item[1]), 9999)),
                    -float(item[0]),
                    int(item[1])
                )
            )
        else:
            candidate_components.sort(key=lambda item: (item[0], -item[1]), reverse=True)
        for _, idx, component, component_box, component_solid_count in candidate_components:
            base_volume = body_volume(component)
            base_face_count = face_count_of_body(component)
            base_extent = radial_extent_of_body(component)
            fragment_extent = radial_extent_of_body(working_fragment)
            candidate = safe_union(component, working_fragment, f"{{member_label}} fragment {{fragment_idx}} attach {{idx}}")
            candidate_solid_count = solid_count_of_body(candidate)
            candidate_volume = body_volume(candidate)
            candidate_face_count = face_count_of_body(candidate)
            candidate_extent = radial_extent_of_body(candidate)
            volume_gain = None
            if base_volume is not None and candidate_volume is not None:
                volume_gain = candidate_volume - base_volume
            face_gain = candidate_face_count - base_face_count
            extent_ok = (
                candidate_extent is None or
                max(base_extent or 0.0, fragment_extent or 0.0) <= 0.0 or
                candidate_extent + 0.8 >= max(base_extent or 0.0, fragment_extent or 0.0)
            )
            meaningful_change = (
                candidate_solid_count != component_solid_count or
                face_gain > 0 or
                (volume_gain is not None and volume_gain > 1e-3)
            )
            gain_ok = (
                volume_gain is None or
                volume_gain > -1e-3 or
                face_gain >= 0
            )
            attached_as_single = (
                candidate_solid_count == 1 and
                body_has_valid_shape(candidate) and
                extent_ok and
                gain_ok and
                meaningful_change
            )
            attached_as_compound = False
            if attached_as_single or attached_as_compound:
                working_fragment = candidate
                touched_indices.append(idx)
                if attached_as_compound:
                    print(
                        f"[*] {{member_label}} fragment {{fragment_idx}} retained as compound attach "
                        f"to component {{idx}} (solids={{candidate_solid_count}})"
                    )
                break
            if (
                candidate_solid_count > 1 and
                body_has_valid_shape(candidate) and
                extent_ok and
                gain_ok and
                meaningful_change
            ):
                print(
                    f"[!] {{member_label}} fragment {{fragment_idx}} rejected compound attach "
                    f"on component {{idx}}: base_solids={{component_solid_count}}, "
                    f"candidate_solids={{candidate_solid_count}}"
                )
                trimmed_fragment = safe_cut(
                    working_fragment,
                    component,
                    f"{{member_label}} fragment {{fragment_idx}} compound reject trim {{idx}}"
                )
                if (
                    trimmed_fragment is not None and
                    solid_count_of_body(trimmed_fragment) == 1 and
                    body_has_valid_shape(trimmed_fragment, require_single_solid=True)
                ):
                    original_volume = body_volume(working_fragment)
                    trimmed_volume = body_volume(trimmed_fragment)
                    if (
                        original_volume is None or
                        trimmed_volume is None or
                        trimmed_volume >= max(80.0, original_volume * 0.20)
                    ):
                        working_fragment = trimmed_fragment
                        fragment_box = body_bbox(working_fragment)
                        print(
                            f"[*] {{member_label}} fragment {{fragment_idx}} trimmed after compound reject "
                            f"on component {{idx}}"
                        )

        if not touched_indices:
            if candidate_components and allow_nearby_standalone:
                active_components.append(working_fragment)
                merged_any = True
                print(
                    f"[*] {{member_label}} fragment {{fragment_idx}} retained as nearby standalone component "
                    f"(candidates={{len(candidate_components)}})"
                )
                continue
            if candidate_components:
                print(
                    f"[!] {{member_label}} fragment {{fragment_idx}} remained detached despite "
                    f"{{len(candidate_components)}} nearby base candidates"
                )
                continue
            print(f"[!] {{member_label}} fragment {{fragment_idx}} did not attach to any base component")
            continue

        if len(touched_indices) == 1 and touched_indices[0] > 0:
            primary_idx = touched_indices[0]
            primary_component = active_components[primary_idx]
            for idx, component in enumerate(active_components):
                if idx == primary_idx or component is None:
                    continue
                overlap_body = safe_intersect(
                    working_fragment,
                    component,
                    f"{{member_label}} fragment {{fragment_idx}} targeted overlap {{idx}}"
                )
                overlap_volume = body_volume(overlap_body)
                if overlap_volume is None or overlap_volume <= 1000.0:
                    continue
                trimmed_fragment = safe_cut(
                    working_fragment,
                    component,
                    f"{{member_label}} fragment {{fragment_idx}} targeted trim {{idx}}"
                )
                if trimmed_fragment is None:
                    continue
                if solid_count_of_body(trimmed_fragment) != 1:
                    continue
                if not body_has_valid_shape(trimmed_fragment, require_single_solid=True):
                    continue
                retained_overlap = body_volume(
                    safe_intersect(
                        trimmed_fragment,
                        primary_component,
                        f"{{member_label}} fragment {{fragment_idx}} targeted trim verify {{idx}}"
                    )
                )
                if retained_overlap is None or retained_overlap <= 50.0:
                    continue
                working_fragment = trimmed_fragment
                print(
                    f"[*] {{member_label}} fragment {{fragment_idx}} targeted-trimmed overlap with component {{idx}}: "
                    f"volume={{float(overlap_volume):.2f}}"
                )

        print(f"[*] {{member_label}} fragment {{fragment_idx}} attached to components {{touched_indices}}")
        surviving_components = [
            component
            for idx, component in enumerate(active_components)
            if idx not in touched_indices
        ]
        surviving_components.append(working_fragment)
        active_components = surviving_components
        merged_any = True

    return active_components, merged_any, len(active_components)

def prefer_single_solid_union(base, other, label):
    if other is None:
        return base
    merged = safe_union(base, other, label)
    if solid_count_of_body(merged) != 1:
        print(f"[!] {{label}} discarded: merged body is not a single solid")
        return base
    if radial_extent_of_body(merged) + 0.5 < radial_extent_of_body(base):
        print(f"[!] {{label}} discarded: merged body lost radial extent")
        return base
    return merged

def attempt_outer_bridge_merge(base, other, label):
    if base is None or other is None:
        return base
    base_box = body_bbox(base)
    other_box = body_bbox(other)
    if base_box is None or other_box is None:
        return base

    base_extent = float(radial_extent_of_body(base) or 0.0)
    other_extent = float(radial_extent_of_body(other) or 0.0)
    if base_extent <= 0.0 or other_extent <= 0.0:
        return base

    bridge_source = other
    bridge_target = base
    source_box = other_box
    target_box = base_box
    source_extent = other_extent
    target_extent = base_extent
    if body_volume(base) is not None and body_volume(other) is not None:
        if float(body_volume(base)) < float(body_volume(other)):
            bridge_source = base
            bridge_target = other
            source_box = base_box
            target_box = other_box
            source_extent = base_extent
            target_extent = other_extent

    sx0, sx1, sy0, sy1, sz0, sz1 = source_box
    tx0, tx1, ty0, ty1, tz0, tz1 = target_box
    z0 = max(float(sz0), float(tz0))
    z1 = min(float(sz1), float(tz1))
    if z1 <= z0 + 1.2:
        return base

    center_x = (float(sx0) + float(sx1)) * 0.5
    center_y = (float(sy0) + float(sy1)) * 0.5
    center_angle = math.degrees(math.atan2(center_y, center_x))
    corner_angles = []
    corner_radii = []
    for x_val, y_val in (
        (float(sx0), float(sy0)),
        (float(sx0), float(sy1)),
        (float(sx1), float(sy0)),
        (float(sx1), float(sy1)),
    ):
        corner_angles.append(math.degrees(math.atan2(y_val, x_val)))
        corner_radii.append(math.hypot(x_val, y_val))
    if not corner_radii:
        return base

    def angle_delta_deg(a_deg, b_deg):
        delta = (float(a_deg) - float(b_deg) + 180.0) % 360.0 - 180.0
        return abs(delta)

    half_span = max(
        4.0,
        min(18.0, max(angle_delta_deg(angle_val, center_angle) for angle_val in corner_angles) + 1.5)
    )
    inner_r = max(0.0, min(corner_radii) - 8.0)
    outer_r = max(float(target_extent), max(corner_radii)) + 3.0
    if outer_r <= inner_r + 3.0:
        return base

    bridge_poly = largest_polygon(
        normalize_polygon(
            build_tapered_bridge_polygon(
                center_angle,
                inner_r,
                outer_r,
                max(2.4, half_span * 0.55),
                half_span
            )
        ),
        min_area=20.0
    )
    if bridge_poly is None:
        return base
    bridge_coords = [
        (round(float(x_val), 3), round(float(y_val), 3))
        for x_val, y_val in list(bridge_poly.exterior.coords)
    ]
    if len(bridge_coords) < 4:
        return base
    bridge_body = build_polygon_prism(bridge_coords, z0, z1 - z0)
    if bridge_body is None:
        return base

    staged = safe_union(bridge_target, bridge_body, f"{{label}} bridge target")
    if not body_has_valid_shape(staged):
        return base
    merged = safe_union(staged, bridge_source, f"{{label}} bridge source")
    if solid_count_of_body(merged) != 1:
        return base
    if not body_has_valid_shape(merged, require_single_solid=True):
        return base
    print(
        f"[*] {{label}} bridge-merged via tapered sector: "
        f"angle={{center_angle:.2f}}, inner={{inner_r:.2f}}, outer={{outer_r:.2f}}"
    )
    return merged

def consolidate_overlapping_components(components, label, min_overlap_volume=500.0):
    active_components = [component for component in (components or []) if component is not None]
    if len(active_components) <= 1:
        return active_components

    while len(active_components) > 1:
        overlap_pairs = []
        for i in range(len(active_components)):
            for j in range(i + 1, len(active_components)):
                overlap_body = safe_intersect(
                    active_components[i],
                    active_components[j],
                    f"{{label}} overlap {{i}}-{{j}}"
                )
                overlap_volume = body_volume(overlap_body)
                if overlap_volume is None or overlap_volume <= float(min_overlap_volume):
                    continue
                overlap_pairs.append((float(overlap_volume), i, j))
        if not overlap_pairs:
            nearby_pairs = []
            for i in range(len(active_components)):
                for j in range(i + 1, len(active_components)):
                    box_i = body_bbox(active_components[i])
                    box_j = body_bbox(active_components[j])
                    if not bboxes_overlap(box_i, box_j, margin=2.4):
                        continue
                    nearby_score = bbox_overlap_volume(box_i, box_j, margin=2.4)
                    nearby_pairs.append((float(nearby_score), i, j))
            if not nearby_pairs:
                break
            nearby_pairs.sort(key=lambda item: item[0], reverse=True)
            merged_once = False
            for nearby_score, i, j in nearby_pairs:
                component_i = active_components[i]
                component_j = active_components[j]
                merged = prefer_single_solid_union(
                    component_i,
                    component_j,
                    f"{{label}} nearby merge {{i}}-{{j}}"
                )
                survivor_idx = i
                drop_idx = j
                if merged is component_i:
                    merged = prefer_single_solid_union(
                        component_j,
                        component_i,
                        f"{{label}} nearby merge {{j}}-{{i}}"
                    )
                    survivor_idx = j
                    drop_idx = i
                    if merged is component_j:
                        bridged = attempt_outer_bridge_merge(
                            component_i,
                            component_j,
                            f"{{label}} nearby bridge {{i}}-{{j}}"
                        )
                        if bridged is component_i:
                            bridged = attempt_outer_bridge_merge(
                                component_j,
                                component_i,
                                f"{{label}} nearby bridge {{j}}-{{i}}"
                            )
                            survivor_idx = j
                            drop_idx = i
                            if bridged is component_j:
                                continue
                        merged = bridged
                if not body_has_valid_shape(merged, require_single_solid=True):
                    continue
                active_components[survivor_idx] = merged
                del active_components[drop_idx]
                print(
                    f"[*] {{label}} merged nearby components {{i}} and {{j}}: "
                    f"score={{nearby_score:.2f}}, remaining={{len(active_components)}}"
                )
                merged_once = True
                break
            if not merged_once:
                break
            continue

        overlap_pairs.sort(key=lambda item: item[0], reverse=True)
        merged_once = False
        for overlap_volume, i, j in overlap_pairs:
            component_i = active_components[i]
            component_j = active_components[j]
            merged = prefer_single_solid_union(
                component_i,
                component_j,
                f"{{label}} merge {{i}}-{{j}}"
            )
            survivor_idx = i
            drop_idx = j
            if merged is component_i:
                merged = prefer_single_solid_union(
                    component_j,
                    component_i,
                    f"{{label}} merge {{j}}-{{i}}"
                )
                survivor_idx = j
                drop_idx = i
                if merged is component_j:
                    print(
                        f"[!] {{label}} retained overlap between components "
                        f"{{i}} and {{j}}: volume={{overlap_volume:.2f}}"
                    )
                    overlap_body = safe_intersect(
                        component_i,
                        component_j,
                        f"{{label}} trim overlap {{i}}-{{j}}"
                    )
                    if overlap_body is None:
                        continue
                    trim_candidates = []
                    volume_i = body_volume(component_i) or 0.0
                    volume_j = body_volume(component_j) or 0.0
                    if volume_i >= volume_j:
                        trim_candidates = [i, j]
                    else:
                        trim_candidates = [j, i]
                    trimmed = None
                    trimmed_idx = None
                    for trim_idx in trim_candidates:
                        candidate_source = active_components[trim_idx]
                        candidate_trimmed = safe_cut(
                            candidate_source,
                            overlap_body,
                            f"{{label}} trim component {{trim_idx}}"
                        )
                        if candidate_trimmed is None:
                            continue
                        if solid_count_of_body(candidate_trimmed) != 1:
                            continue
                        if not body_has_valid_shape(candidate_trimmed, require_single_solid=True):
                            continue
                        source_volume = body_volume(candidate_source)
                        trimmed_volume = body_volume(candidate_trimmed)
                        if (
                            source_volume is not None and
                            trimmed_volume is not None and
                            (source_volume - trimmed_volume) < min(25.0, overlap_volume * 0.05)
                        ):
                            continue
                        trimmed = candidate_trimmed
                        trimmed_idx = trim_idx
                        break
                    if trimmed is None or trimmed_idx is None:
                        continue
                    active_components[trimmed_idx] = trimmed
                    print(
                        f"[*] {{label}} trimmed overlap from component {{trimmed_idx}} "
                        f"for pair {{i}}-{{j}}: volume={{overlap_volume:.2f}}"
                    )
                    merged_once = True
                    break
            if not body_has_valid_shape(merged, require_single_solid=True):
                print(
                    f"[!] {{label}} merge {{i}}-{{j}} rejected: merged body invalid "
                    f"(overlap={{overlap_volume:.2f}})"
                )
                continue
            active_components[survivor_idx] = merged
            del active_components[drop_idx]
            print(
                f"[*] {{label}} merged overlapping components {{i}} and {{j}}: "
                f"volume={{overlap_volume:.2f}}, remaining={{len(active_components)}}"
            )
            merged_once = True
            break
        if not merged_once:
            break

    return active_components

def safe_assemble(parts, label, allow_compound_fallback=True):
    solids = []
    for part in parts:
        if part is None:
            continue
        try:
            part_solids = part.solids().vals()
            if part_solids:
                solids.extend(part_solids)
                continue
        except Exception:
            pass
        try:
            solids.append(part.val())
        except Exception as exc:
            print(f"[!] {{label}} part extraction failed: {{exc}}")

    if not solids:
        raise ValueError(f"No solids available for {{label}}")

    assembled = cq.Workplane("XY").newObject([solids[0]])
    for idx, solid in enumerate(solids[1:], start=1):
        try:
            assembled = assembled.union(cq.Workplane("XY").newObject([solid]))
        except Exception as exc:
            print(f"[!] {{label}} union segment {{idx}} failed: {{exc}}")

    try:
        result_bbox = assembled.val().BoundingBox()
        result_extent = max(
            abs(result_bbox.xmin), abs(result_bbox.xmax),
            abs(result_bbox.ymin), abs(result_bbox.ymax)
        )
        expected_extent = max(
            max(abs(solid.BoundingBox().xmin), abs(solid.BoundingBox().xmax), abs(solid.BoundingBox().ymin), abs(solid.BoundingBox().ymax))
            for solid in solids
        )
        if result_extent + 1.0 < expected_extent:
            raise ValueError(f"assembled extent shrank from {{expected_extent:.2f}} to {{result_extent:.2f}}")
        return assembled
    except Exception as exc:
        if not allow_compound_fallback:
            raise
        print(f"[!] {{label}} fallback to compound assembly: {{exc}}")
        compound = cq.Compound.makeCompound(solids)
        return cq.Workplane("XY").newObject([compound])

def direct_compound_assembly(parts, label):
    solids = []
    for part in parts:
        if part is None:
            continue
        try:
            part_solids = part.solids().vals()
            if part_solids:
                solids.extend(part_solids)
                continue
        except Exception:
            pass
        try:
            solids.append(part.val())
        except Exception as exc:
            print(f"[!] {{label}} part extraction failed: {{exc}}")
    if not solids:
        raise ValueError(f"No solids available for {{label}}")
    compound = cq.Compound.makeCompound(solids)
    print(f"[*] {{label}} emitted as direct compound with {{len(solids)}} solids")
    return cq.Workplane("XY").newObject([compound])

def build_annulus_prism(inner_r, outer_r, z_bottom, z_top):
    if outer_r <= inner_r + 0.4 or z_top <= z_bottom + 0.4:
        return None
    try:
        wp = cq.Workplane("XY").workplane(offset=float(z_bottom)).circle(float(outer_r))
        if inner_r > 0.05:
            wp = wp.circle(float(inner_r))
        return wp.extrude(float(z_top) - float(z_bottom))
    except Exception as exc:
        print(f"[!] annulus prism build failed: {{exc}}")
        return None

def make_lug_pocket_cutter(center_x, center_y, top_z, floor_z, outer_r, floor_r):
    if top_z <= floor_z + 0.25 or outer_r <= floor_r + 0.25:
        return None, None
    try:
        outer_wall = cq.Solid.makeCone(
            floor_r,
            outer_r,
            top_z - floor_z,
            pnt=(center_x, center_y, floor_z),
            dir=(0, 0, 1)
        )
        floor_cutter = (
            cq.Workplane("XY")
            .workplane(offset=floor_z)
            .center(center_x, center_y)
            .circle(floor_r)
            .extrude((top_z - floor_z) + 0.6)
        )
        return cq.Workplane("XY").newObject([outer_wall]), floor_cutter
    except Exception as exc:
        print(f"[!] Lug pocket cutter build failed: {{exc}}")
        return None, None

def circle_points(radius, count=180):
    pts = []
    for i in range(count):
        ang = 2.0 * math.pi * i / count
        pts.append((radius * math.cos(ang), radius * math.sin(ang)))
    pts.append(pts[0])
    return pts

def normalize_polygon(poly):
    if poly.is_empty:
        return poly
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly

def iter_polygons(geom):
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    return []

def largest_polygon(geom, min_area=5.0):
    polys = []
    for poly in iter_polygons(geom):
        if not poly.is_empty and poly.area >= min_area:
            polys.append(poly)
    if not polys:
        return None
    return max(polys, key=lambda poly: poly.area)

def build_polygon_prism(coords, z0, height):
    if not coords or len(coords) < 4 or height <= 0:
        return None
    try:
        return (
            cq.Workplane("XY")
            .workplane(offset=z0)
            .polyline(coords).close()
            .extrude(height)
        )
    except Exception as exc:
        print(f"[!] Polygon prism build failed: {{exc}}")
        return None

def resample_closed_loop(coords, target_count=48):
    if not coords or len(coords) < 4:
        return []
    pts = [(float(x), float(y)) for x, y in coords]
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return []

    lengths = [0.0]
    total = 0.0
    for idx in range(len(pts)):
        x1, y1 = pts[idx]
        x2, y2 = pts[(idx + 1) % len(pts)]
        seg_len = math.hypot(x2 - x1, y2 - y1)
        total += seg_len
        lengths.append(total)

    if total <= 1e-6:
        return []

    sampled = []
    step = total / max(3, int(target_count))
    for sample_idx in range(int(target_count)):
        target_len = sample_idx * step
        seg_idx = 0
        while seg_idx < len(pts) and lengths[seg_idx + 1] < target_len:
            seg_idx += 1
        x1, y1 = pts[seg_idx]
        x2, y2 = pts[(seg_idx + 1) % len(pts)]
        seg_start = lengths[seg_idx]
        seg_end = lengths[seg_idx + 1]
        if seg_end <= seg_start + 1e-9:
            t = 0.0
        else:
            t = (target_len - seg_start) / (seg_end - seg_start)
        sampled.append((x1 + ((x2 - x1) * t), y1 + ((y2 - y1) * t)))
    return sampled

def canonicalize_member_loop(coords, member_angle_deg):
    if not coords or len(coords) < 4:
        return []
    pts = [(float(x), float(y)) for x, y in coords]
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return []

    signed_area = 0.0
    for idx in range(len(pts)):
        x1, y1 = pts[idx]
        x2, y2 = pts[(idx + 1) % len(pts)]
        signed_area += (x1 * y2) - (x2 * y1)
    if signed_area < 0.0:
        pts.reverse()

    angle_rad = math.radians(float(member_angle_deg or 0.0))
    radial_dir = np.asarray([math.cos(angle_rad), math.sin(angle_rad)], dtype=float)
    tangential_dir = np.asarray([-math.sin(angle_rad), math.cos(angle_rad)], dtype=float)

    def anchor_key(idx):
        point = np.asarray(pts[idx], dtype=float)
        radial_val = float(np.dot(point, radial_dir))
        tangent_val = float(np.dot(point, tangential_dir))
        return (
            round(radial_val, 6),
            round(-tangent_val, 6),
            round(tangent_val, 6)
        )

    start_idx = min(range(len(pts)), key=anchor_key)
    pts = pts[start_idx:] + pts[:start_idx]
    pts.append(pts[0])
    return [[round(float(x), 3), round(float(y), 3)] for x, y in pts]

def world_loop_to_member_local(coords, member_angle_deg):
    world_loop = canonicalize_member_loop(coords, member_angle_deg)
    if len(world_loop) < 4:
        return []

    angle_rad = math.radians(float(member_angle_deg or 0.0))
    radial_dir = np.asarray([math.cos(angle_rad), math.sin(angle_rad)], dtype=float)
    tangential_dir = np.asarray([-math.sin(angle_rad), math.cos(angle_rad)], dtype=float)

    local_pts = []
    for x_val, y_val in world_loop[:-1]:
        point = np.asarray([float(x_val), float(y_val)], dtype=float)
        radial_val = float(np.dot(point, radial_dir))
        tangent_val = float(np.dot(point, tangential_dir))
        local_pts.append((round(radial_val, 3), round(tangent_val, 3)))

    if len(local_pts) < 3:
        return []
    local_pts.append(local_pts[0])
    return local_pts

def closed_loop_signed_area(loop_points):
    if loop_points is None or len(loop_points) < 3:
        return 0.0
    pts = [(float(x), float(y)) for x, y in loop_points]
    area = 0.0
    for idx in range(len(pts)):
        x1, y1 = pts[idx]
        x2, y2 = pts[(idx + 1) % len(pts)]
        area += (x1 * y2) - (x2 * y1)
    return area * 0.5

def align_resampled_loop(reference_loop, candidate_loop, allow_reverse=True):
    # Align a sampled loop to a reference loop by choosing the best cyclic shift/orientation.
    if reference_loop is None or candidate_loop is None:
        return candidate_loop
    if len(reference_loop) != len(candidate_loop) or len(reference_loop) < 3:
        return candidate_loop

    ref = [(float(x), float(y)) for x, y in reference_loop]
    cand = [(float(x), float(y)) for x, y in candidate_loop]
    count = len(ref)

    if not allow_reverse:
        ref_area = closed_loop_signed_area(ref)
        cand_area = closed_loop_signed_area(cand)
        if abs(ref_area) > 1e-6 and abs(cand_area) > 1e-6 and (ref_area * cand_area) < 0.0:
            cand = list(reversed(cand))

    best_score = None
    best_loop = list(cand)
    reverse_options = (False, True) if allow_reverse else (False,)
    for reverse in reverse_options:
        working = list(reversed(cand)) if reverse else list(cand)
        for shift in range(count):
            score = 0.0
            for idx in range(count):
                rx, ry = ref[idx]
                cx, cy = working[(idx + shift) % count]
                dx = rx - cx
                dy = ry - cy
                score += (dx * dx) + (dy * dy)
            if best_score is None or score < best_score:
                best_score = score
                best_loop = [working[(idx + shift) % count] for idx in range(count)]
    return best_loop

def build_polygon_transition_cutter(lower_coords, upper_coords, z0, z1):
    if not lower_coords or not upper_coords or z1 <= z0 + 0.4:
        return None
    try:
        lower_loop = resample_closed_loop(lower_coords, target_count=48)
        upper_loop = resample_closed_loop(upper_coords, target_count=48)
        if len(lower_loop) < 8 or len(upper_loop) < 8:
            return None
        upper_loop = align_resampled_loop(lower_loop, upper_loop)
        return (
            cq.Workplane("XY")
            .workplane(offset=z0)
            .polyline(lower_loop).close()
            .workplane(offset=(z1 - z0))
            .polyline(upper_loop).close()
            .loft(combine=True, ruled=True)
        )
    except Exception as exc:
        print(f"[!] Polygon transition cutter build failed: {{exc}}")
        return None

def build_local_section_wire(section_payload, loop_points):
    if not loop_points or len(loop_points) < 4:
        return None
    plane_origin = section_payload.get("plane_origin", [])
    plane_normal = section_payload.get("plane_normal", [])
    plane_x_dir = section_payload.get("plane_x_dir", [])
    if len(plane_origin) < 3 or len(plane_normal) < 3 or len(plane_x_dir) < 3:
        return None
    try:
        plane = cq.Plane(
            origin=(float(plane_origin[0]), float(plane_origin[1]), float(plane_origin[2])),
            xDir=(float(plane_x_dir[0]), float(plane_x_dir[1]), float(plane_x_dir[2])),
            normal=(float(plane_normal[0]), float(plane_normal[1]), float(plane_normal[2]))
        )
        return (
            cq.Workplane(plane)
            .polyline([(float(x), float(y)) for x, y in loop_points]).close()
            .wires().val()
        )
    except Exception as exc:
        print(f"[!] Local section wire build failed: {{exc}}")
        return None

def get_canonical_local_section_templates():
    global canonical_local_section_templates_by_slot
    if canonical_local_section_templates_by_slot is None:
        canonical_local_section_templates_by_slot = derive_canonical_local_section_templates(spoke_motif_groups)
        if canonical_local_section_templates_by_slot:
            print(
                f"[*] Canonical local spoke section templates derived: "
                f"{{len(canonical_local_section_templates_by_slot)}} slots"
            )
            for slot_idx, template_payload in sorted(canonical_local_section_templates_by_slot.items()):
                try:
                    print(
                        f"[*] Canonical local slot {{slot_idx}} coverage: "
                        f"R={{float(template_payload.get('template_r_min', 0.0)):.2f}}->"
                        f"{{float(template_payload.get('template_r_max', 0.0)):.2f}}, "
                        f"members={{int(template_payload.get('member_count', 0))}}"
                    )
                except Exception:
                    continue
    return canonical_local_section_templates_by_slot or {{}}

def canonicalize_local_section_loop(loop_points):
    if not loop_points or len(loop_points) < 4:
        return []
    pts = [(float(x), float(y)) for x, y in loop_points]
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return []

    signed_area = 0.0
    for idx in range(len(pts)):
        x1, y1 = pts[idx]
        x2, y2 = pts[(idx + 1) % len(pts)]
        signed_area += (x1 * y2) - (x2 * y1)
    if signed_area < 0.0:
        pts.reverse()

    start_idx = min(
        range(len(pts)),
        key=lambda idx: (
            round(float(pts[idx][1]), 6),
            round(float(pts[idx][0]), 6),
            round(-float(pts[idx][0]), 6)
        )
    )
    pts = pts[start_idx:] + pts[:start_idx]
    pts.append(pts[0])
    return [[round(float(x), 3), round(float(y), 3)] for x, y in pts]

def prepare_local_section_template_loop(section_payload, target_count=48):
    loop_points = section_payload.get("points_local", []) or []
    if len(loop_points) < 4:
        return []
    loop_points = stabilize_local_section_loop(section_payload, loop_points)
    loop_points = rebuild_local_section_loop_from_y_samples(loop_points)
    loop_points = canonicalize_local_section_loop(loop_points)
    if len(loop_points) < 4:
        return []
    sampled = resample_closed_loop(loop_points, target_count=target_count)
    return sampled if len(sampled) >= 8 else []

def prepare_local_section_template_loop_raw(section_payload, target_count=64):
    loop_points = section_payload.get("points_local", []) or []
    if len(loop_points) < 4:
        return []
    try:
        local_poly = largest_polygon(normalize_polygon(Polygon(loop_points)), min_area=2.0)
    except Exception:
        local_poly = None
    if local_poly is not None and (not local_poly.is_empty):
        loop_points = list(local_poly.exterior.coords)
    loop_points = canonicalize_local_section_loop(loop_points)
    if len(loop_points) < 4:
        return []
    sampled = resample_closed_loop(loop_points, target_count=target_count)
    if len(sampled) < 8:
        return []
    sampled = [(round(float(x), 3), round(float(y), 3)) for x, y in sampled]
    sampled.append(sampled[0])
    return sampled

def derive_canonical_local_section_templates(motif_payloads, target_count=48):
    slot_stacks = {{}}

    def section_stack_metrics(stack):
        radii = []
        widths = []
        centers = []
        areas = []
        detail_scores = []
        for section in stack or []:
            loop = (section.get("points_local_raw", []) or section.get("points_local", [])) if isinstance(section, dict) else []
            if len(loop) < 8:
                continue
            pts = [(float(x), float(y)) for x, y in loop]
            if pts[0] == pts[-1]:
                pts = pts[:-1]
            if len(pts) < 3:
                continue
            try:
                poly = Polygon(pts)
            except Exception:
                poly = None
            if poly is None or poly.is_empty or poly.area <= 1e-6:
                continue
            xs = [float(x) for x, _ in pts]
            widths.append(max(xs) - min(xs))
            centers.append((max(xs) + min(xs)) * 0.5)
            areas.append(float(poly.area))
            radii.append(float(section.get("station_r", 0.0)))
            try:
                detail_scores.append(float((poly.length * poly.length) / max(1e-6, poly.area)))
            except Exception:
                pass
        if len(radii) < 3:
            return None
        roughness = 0.0
        for values, weight in (
            (widths, 1.00),
            (centers, 0.65),
            (areas, 0.35),
        ):
            arr = np.asarray(values, dtype=float)
            if arr.size >= 3:
                roughness += float(np.mean(np.abs(np.diff(arr, n=2)))) * float(weight)
        return {{
            "r_min": float(min(radii)),
            "r_max": float(max(radii)),
            "span": float(max(radii) - min(radii)),
            "section_count": int(len(radii)),
            "roughness": float(roughness),
            "detail_score": float(np.median(np.asarray(detail_scores, dtype=float))) if detail_scores else 0.0,
        }}

    for motif_payload in motif_payloads or []:
        for member_payload in motif_payload.get("members", []) or []:
            slot_index = int(member_payload.get("slot_index", 0))
            ordered_sections = sorted(
                [section for section in (member_payload.get("sections", []) or []) if isinstance(section, dict)],
                key=lambda section: float(section.get("station_r", 0.0))
            )
            section_stack = []
            previous_loop = None
            previous_raw_loop = None
            for section_payload in ordered_sections:
                sampled_loop = prepare_local_section_template_loop(section_payload, target_count=target_count)
                if len(sampled_loop) < 8:
                    continue
                if previous_loop is not None:
                    sampled_loop = align_resampled_loop(previous_loop, sampled_loop, allow_reverse=False)
                previous_loop = sampled_loop
                raw_loop = prepare_local_section_template_loop_raw(section_payload, target_count=max(64, target_count))
                if len(raw_loop) < 8:
                    raw_loop = sampled_loop
                if previous_raw_loop is not None:
                    raw_loop = align_resampled_loop(previous_raw_loop, raw_loop, allow_reverse=False)
                previous_raw_loop = raw_loop
                section_stack.append({{
                    "station_r": float(section_payload.get("station_r", 0.0)),
                    "points_local": sampled_loop,
                    "points_local_raw": raw_loop
                }})
            if len(section_stack) < 3:
                continue
            slot_stacks.setdefault(slot_index, []).append(section_stack)

    templates = {{}}
    for slot_index, member_stacks in slot_stacks.items():
        if len(member_stacks) < 2:
            continue
        stack_metrics = []
        for stack in member_stacks:
            metrics = section_stack_metrics(stack)
            if metrics is None:
                continue
            metrics["stack"] = stack
            stack_metrics.append(metrics)
        if len(stack_metrics) < 2:
            continue
        max_r_max = max(item["r_max"] for item in stack_metrics)
        max_span = max(item["span"] for item in stack_metrics)
        preferred_metrics = [
            item for item in stack_metrics
            if item["r_max"] >= max_r_max - 8.0 and item["span"] >= max_span * 0.82
        ]
        donor_metric = min(
            preferred_metrics if preferred_metrics else stack_metrics,
            key=lambda item: (
                -item["detail_score"],
                item["roughness"],
                -item["span"],
                -item["r_max"]
            )
        )
        member_stacks = [item["stack"] for item in (preferred_metrics if preferred_metrics else stack_metrics)]

        section_templates = [
            {{
                "station_r": round(float(section.get("station_r", 0.0)), 3),
                "points_local": [
                    [round(float(x), 3), round(float(y), 3)]
                    for x, y in (section.get("points_local_raw", []) or section.get("points_local", []) or [])
                ],
                "points_local_raw": [
                    [round(float(x), 3), round(float(y), 3)]
                    for x, y in (section.get("points_local_raw", []) or section.get("points_local", []) or [])
                ],
                "support_count": int(len(member_stacks))
            }}
            for section in donor_metric.get("stack", [])
            if isinstance(section, dict)
        ]

        if len(section_templates) < 3:
            continue

        templates[int(slot_index)] = {{
            "slot_index": int(slot_index),
            "section_templates": section_templates,
            "donor_sections": [
                {{
                    "station_r": round(float(section.get("station_r", 0.0)), 3),
                    "points_local": [
                        [round(float(x), 3), round(float(y), 3)]
                        for x, y in (section.get("points_local_raw", []) or section.get("points_local", []) or [])
                    ],
                    "points_local_raw": [
                        [round(float(x), 3), round(float(y), 3)]
                        for x, y in (section.get("points_local_raw", []) or section.get("points_local", []) or [])
                    ]
                }}
                for section in (donor_metric.get("stack", []) if isinstance(donor_metric, dict) else [])
                if isinstance(section, dict)
            ],
            "member_count": int(len(member_stacks)),
            "template_r_min": round(float(min(float(section.get("station_r", 0.0)) for section in section_templates)), 3),
            "template_r_max": round(float(max(float(section.get("station_r", 0.0)) for section in section_templates)), 3)
        }}

    return templates

def stabilize_local_section_loop(section_payload, loop_points):
    if not loop_points or len(loop_points) < 4:
        return loop_points
    try:
        actual_slice_derived = bool(section_payload.get("_actual_slice_derived"))
        pts = [(float(x), float(y)) for x, y in loop_points]
        xs = [x for x, _ in pts]
        if not xs:
            return loop_points
        current_center = (max(xs) + min(xs)) * 0.5
        current_width = max(xs) - min(xs)
        if current_width <= 1e-6:
            return loop_points

        target_center = section_payload.get("smoothed_target_center_x")
        if target_center is None:
            target_center = section_payload.get("target_center_x")
        if target_center is None:
            target_center = current_center
        target_center = current_center + ((float(target_center) - current_center) * 0.35)

        target_width = section_payload.get("smoothed_target_width")
        if target_width is None:
            target_width = section_payload.get("target_width")
        if target_width is None:
            target_width = current_width
        target_width = max(1.0, float(target_width))

        if actual_slice_derived:
            desired_width_hi = max(target_width * 1.22, target_width + 1.2)
            desired_width_lo = max(0.8, target_width * 0.80)
        else:
            desired_width_hi = max(target_width * 1.35, target_width + 2.0)
            desired_width_lo = max(0.8, target_width * 0.72)
        if current_width > desired_width_hi:
            width_scale = desired_width_hi / current_width
        elif current_width < desired_width_lo:
            width_scale = desired_width_lo / current_width
        else:
            width_scale = 1.0
        if actual_slice_derived:
            width_scale = max(0.72, min(1.05, float(width_scale)))
        else:
            width_scale = max(0.82, min(1.08, float(width_scale)))

        stabilized = []
        for x_val, y_val in pts:
            shifted_x = target_center + ((x_val - current_center) * width_scale)
            stabilized.append((shifted_x, y_val))
        return stabilized
    except Exception:
        return loop_points

def rebuild_local_section_loop_from_y_samples(loop_points, sample_count=17):
    if not loop_points or len(loop_points) < 4:
        return loop_points
    try:
        poly = largest_polygon(normalize_polygon(Polygon(loop_points)), min_area=2.0)
    except Exception:
        poly = None
    if poly is None or poly.is_empty:
        return loop_points

    coords = list(poly.exterior.coords)
    if len(coords) < 4:
        return loop_points
    xs = [float(x) for x, _ in coords[:-1]]
    ys = [float(y) for _, y in coords[:-1]]
    if not xs or not ys:
        return loop_points
    y_min = min(ys)
    y_max = max(ys)
    x_min = min(xs)
    x_max = max(xs)
    if y_max <= y_min + 0.35 or x_max <= x_min + 0.35:
        return loop_points

    target_count = max(9, int(sample_count))
    y_levels = np.linspace(y_min, y_max, target_count)
    samples = []
    for y_level in y_levels:
        probe = LineString([
            (x_min - 2.0, float(y_level)),
            (x_max + 2.0, float(y_level))
        ])
        try:
            hit = poly.intersection(probe)
        except Exception:
            continue
        x_hits = []

        def collect_x(geom):
            if geom is None or geom.is_empty:
                return
            if isinstance(geom, Point):
                x_hits.append(float(geom.x))
                return
            if isinstance(geom, LineString):
                for x_val, _ in list(geom.coords):
                    x_hits.append(float(x_val))
                return
            if isinstance(geom, MultiLineString) or isinstance(geom, GeometryCollection):
                for sub in geom.geoms:
                    collect_x(sub)
                return
            if hasattr(geom, "geoms"):
                for sub in geom.geoms:
                    collect_x(sub)

        collect_x(hit)
        if len(x_hits) < 2:
            continue
        samples.append((float(y_level), min(x_hits), max(x_hits)))

    if len(samples) < 6:
        return loop_points

    left_vals = np.asarray([item[1] for item in samples], dtype=float)
    right_vals = np.asarray([item[2] for item in samples], dtype=float)
    if len(left_vals) >= 5:
        window = 5
    elif len(left_vals) >= 3:
        window = 3
    else:
        window = 1
    if window >= 3:
        kernel = np.ones(window, dtype=float) / float(window)
        left_vals = np.convolve(np.pad(left_vals, (window // 2, window // 2), mode="edge"), kernel, mode="valid")
        right_vals = np.convolve(np.pad(right_vals, (window // 2, window // 2), mode="edge"), kernel, mode="valid")

    outline = []
    for idx, (y_level, _, _) in enumerate(samples):
        outline.append((round(float(left_vals[idx]), 4), round(float(y_level), 4)))
    for idx in range(len(samples) - 1, -1, -1):
        y_level = samples[idx][0]
        outline.append((round(float(right_vals[idx]), 4), round(float(y_level), 4)))
    if len(outline) < 6:
        return loop_points
    outline.append(outline[0])
    return outline

def clone_local_section_profile(section_payload, station_r, target_center_x=None, target_width=None):
    cloned = dict(section_payload)
    try:
        station_r = float(station_r)
    except Exception:
        return cloned
    plane_origin = list(cloned.get("plane_origin", []))
    plane_normal = cloned.get("plane_normal", [])
    if len(plane_origin) >= 3 and len(plane_normal) >= 2:
        plane_origin[0] = round(float(plane_normal[0]) * station_r, 3)
        plane_origin[1] = round(float(plane_normal[1]) * station_r, 3)
        cloned["plane_origin"] = plane_origin
    cloned["station_r"] = round(station_r, 2)
    if target_center_x is not None:
        cloned["target_center_x"] = float(target_center_x)
        cloned["smoothed_target_center_x"] = float(target_center_x)
    if target_width is not None:
        target_width = max(1.0, float(target_width))
        cloned["target_width"] = target_width
        cloned["smoothed_target_width"] = target_width
    return cloned

def clip_void_profile_to_band(coords, inner_r, outer_r, keepout_geom=None):
    if not coords or len(coords) < 4:
        return []
    if outer_r <= inner_r + 1.0:
        return []
    try:
        void_poly = normalize_polygon(Polygon(coords))
        if void_poly.is_empty or void_poly.area < 10.0:
            return []

        outer_disk = normalize_polygon(Polygon(circle_points(outer_r, count=240)))
        inner_disk = normalize_polygon(Polygon(circle_points(max(0.0, inner_r), count=240)))
        annulus = normalize_polygon(outer_disk.difference(inner_disk))
        clipped = normalize_polygon(void_poly.intersection(annulus))
        if keepout_geom is not None and not keepout_geom.is_empty:
            clipped = normalize_polygon(clipped.difference(keepout_geom))
        clipped_poly = largest_polygon(clipped, min_area=20.0)
        if clipped_poly is None:
            return []

        profile = [[round(float(x), 3), round(float(y), 3)] for x, y in list(clipped_poly.exterior.coords)]
        if len(profile) < 4:
            return []
        if profile[0] != profile[-1]:
            profile.append(profile[0])
        return profile
    except Exception as exc:
        print(f"[!] Void profile radial clip failed: {{exc}}")
        return []

def build_world_z_profile_wire(profile_payload):
    if not isinstance(profile_payload, dict):
        return None
    pts = profile_payload.get("points", []) or []
    if len(pts) < 4:
        return None
    try:
        z_level = float(profile_payload.get("z", 0.0))
    except Exception:
        return None
    loop = [(float(x), float(y)) for x, y in pts]
    if loop[0] == loop[-1]:
        loop = loop[:-1]
    if len(loop) < 3:
        return None
    try:
        return (
            cq.Workplane("XY")
            .workplane(offset=z_level)
            .polyline(loop).close()
            .wires().val()
        )
    except Exception as exc:
        print(f"[!] Z-profile wire build failed: {{exc}}")
        return None

def build_member_loft_from_z_profiles(z_profiles, member_label, member_angle_deg):
    prepared_profiles = []
    previous_loop = None
    for profile in z_profiles:
        try:
            z_level = float(profile.get("z", 0.0))
        except Exception:
            continue
        target_count = 64
        sampled_loop = resample_closed_loop(profile.get("points", []), target_count=target_count)
        if len(sampled_loop) < 8:
            continue
        sampled_loop = canonicalize_member_loop(sampled_loop + [sampled_loop[0]], member_angle_deg)
        if len(sampled_loop) < 9:
            continue
        sampled_loop = [(float(x), float(y)) for x, y in sampled_loop[:-1]]
        if previous_loop is not None:
            sampled_loop = align_resampled_loop(
            previous_loop,
            sampled_loop,
            allow_reverse=False
        )
        previous_loop = sampled_loop
        prepared_profiles.append({{
            "z": z_level,
            "points": sampled_loop + [sampled_loop[0]]
        }})

    if len(prepared_profiles) < 4:
        return None

    def profile_stack_bbox(profile_stack):
        xs = []
        ys = []
        zs = []
        for stack_profile in profile_stack or []:
            try:
                z_level = float(stack_profile.get("z", 0.0))
            except Exception:
                continue
            points = stack_profile.get("points", []) or []
            for point in points:
                try:
                    px = float(point[0])
                    py = float(point[1])
                except Exception:
                    continue
                xs.append(px)
                ys.append(py)
                zs.append(z_level)
        if not xs or not ys or not zs:
            return None
        return (
            float(min(xs)), float(max(xs)),
            float(min(ys)), float(max(ys)),
            float(min(zs)), float(max(zs))
        )

    def profile_stack_radial_extent(profile_stack):
        max_radius = 0.0
        for stack_profile in profile_stack or []:
            for point in stack_profile.get("points", []) or []:
                try:
                    px = float(point[0])
                    py = float(point[1])
                except Exception:
                    continue
                max_radius = max(max_radius, math.hypot(px, py))
        return float(max_radius)

    def is_chunk_body_plausible(chunk_body, chunk_profiles, chunk_index):
        if chunk_body is None or not body_has_valid_shape(chunk_body, require_single_solid=True):
            return False

        expected_box = profile_stack_bbox(chunk_profiles)
        actual_box = body_bbox(chunk_body)
        if expected_box is None or actual_box is None:
            return False

        ex0, ex1, ey0, ey1, ez0, ez1 = expected_box
        ax0, ax1, ay0, ay1, az0, az1 = actual_box

        expected_x_span = max(1e-3, float(ex1 - ex0))
        expected_y_span = max(1e-3, float(ey1 - ey0))
        expected_z_span = max(1e-3, float(ez1 - ez0))
        actual_x_span = max(0.0, float(ax1 - ax0))
        actual_y_span = max(0.0, float(ay1 - ay0))
        actual_z_span = max(0.0, float(az1 - az0))
        z_overlap = max(0.0, min(float(az1), float(ez1)) - max(float(az0), float(ez0)))
        member_z_min = float(prepared_profiles[0].get("z", ez0)) if prepared_profiles else float(ez0)
        member_z_max = float(prepared_profiles[-1].get("z", ez1)) if prepared_profiles else float(ez1)
        member_z_span = max(1.0, float(member_z_max) - float(member_z_min))
        terminal_band = max(2.2, member_z_span * 0.12)
        terminal_like = (
            min(abs(float(ez0) - member_z_min), abs(float(az0) - member_z_min)) <= terminal_band or
            min(abs(member_z_max - float(ez1)), abs(member_z_max - float(az1))) <= terminal_band
        )

        expected_radius = profile_stack_radial_extent(chunk_profiles)
        actual_radius = radial_extent_of_body(chunk_body)

        z_margin = max(2.4, expected_z_span * 0.45)
        xy_margin = max(3.5, max(expected_x_span, expected_y_span) * 0.3)
        radial_limit = max(expected_radius + 18.0, expected_radius * 1.12)
        x_span_limit = max(expected_x_span + 18.0, expected_x_span * 2.8)
        y_span_limit = max(expected_y_span + 18.0, expected_y_span * 2.8)
        z_span_limit = max(22.0, expected_z_span * 6.0)
        min_z_overlap = max(0.2, min(2.0, expected_z_span * 0.35))
        if terminal_like:
            min_z_overlap = min(min_z_overlap, max(0.02, expected_z_span * 0.18))

        z_ok = (
            z_overlap >= min_z_overlap and
            actual_z_span <= z_span_limit and
            float(az0) <= float(ez1) + z_margin and
            float(az1) >= float(ez0) - z_margin
        )
        radius_ok = actual_radius <= radial_limit
        span_ok = (
            actual_x_span <= x_span_limit and
            actual_y_span <= y_span_limit
        )
        overlap_ok = bboxes_overlap(expected_box, actual_box, margin=xy_margin)
        terminal_micro_ok = (
            terminal_like and
            overlap_ok and
            radius_ok and
            span_ok and
            actual_z_span <= max(1.4, expected_z_span * 3.5) and
            z_overlap >= max(0.02, expected_z_span * 0.18)
        )

        if terminal_micro_ok or (z_ok and radius_ok and span_ok and overlap_ok):
            return True

        print(
            f"[!] {{member_label}} chunk {{chunk_index}} rejected: "
            f"expected_bbox=({{ex0:.2f}},{{ex1:.2f}},{{ey0:.2f}},{{ey1:.2f}},{{ez0:.2f}},{{ez1:.2f}}), "
            f"actual_bbox=({{ax0:.2f}},{{ax1:.2f}},{{ay0:.2f}},{{ay1:.2f}},{{az0:.2f}},{{az1:.2f}}), "
            f"expected_radius={{expected_radius:.2f}}, actual_radius={{actual_radius:.2f}}, "
            f"x_span_limit={{x_span_limit:.2f}}, y_span_limit={{y_span_limit:.2f}}, "
            f"z_margin={{z_margin:.2f}}, z_overlap={{z_overlap:.2f}}, z_span_limit={{z_span_limit:.2f}}"
        )
        return False

    loft_wires = []
    for profile in prepared_profiles:
        wire = build_world_z_profile_wire(profile)
        if wire is not None:
            loft_wires.append(wire)

    def build_chunked_multi_wire_body(profile_stack, chunk_size=6, overlap=2):
        if len(profile_stack) < 4:
            return None
        chunk_records = []
        start_idx = 0
        step = max(2, int(chunk_size) - int(overlap))
        chunk_index = 0

        def loft_body_from_profiles(candidate_profiles):
            candidate_wires = []
            for candidate_profile in candidate_profiles:
                candidate_wire = build_world_z_profile_wire(candidate_profile)
                if candidate_wire is not None:
                    candidate_wires.append(candidate_wire)
            if len(candidate_wires) < 3:
                return None
            try:
                candidate_solid = cq.Solid.makeLoft(candidate_wires, ruled=False)
                candidate_body = cq.Workplane("XY").newObject([candidate_solid])
                if body_has_valid_shape(candidate_body, require_single_solid=True):
                    return candidate_body
            except Exception:
                pass
            try:
                candidate_solid = cq.Solid.makeLoft(candidate_wires, ruled=True)
                candidate_body = cq.Workplane("XY").newObject([candidate_solid])
                if body_has_valid_shape(candidate_body, require_single_solid=True):
                    return candidate_body
            except Exception:
                pass
            return None

        def trim_chunk_body_to_expected_bounds(chunk_body, candidate_profiles, candidate_index):
            expected_box = profile_stack_bbox(candidate_profiles)
            if chunk_body is None or expected_box is None:
                return None
            ex0, ex1, ey0, ey1, ez0, ez1 = expected_box
            expected_x_span = max(1.0, float(ex1 - ex0))
            expected_y_span = max(1.0, float(ey1 - ey0))
            expected_z_span = max(1.0, float(ez1 - ez0))
            xy_margin = max(4.5, max(expected_x_span, expected_y_span) * 0.28)
            z_margin = max(3.0, expected_z_span * 0.55)
            center_x = (float(ex0) + float(ex1)) * 0.5
            center_y = (float(ey0) + float(ey1)) * 0.5
            center_z = (float(ez0) + float(ez1)) * 0.5
            keep_box = (
                cq.Workplane("XY")
                .center(center_x, center_y)
                .workplane(offset=center_z)
                .box(
                    float(expected_x_span + (xy_margin * 2.0)),
                    float(expected_y_span + (xy_margin * 2.0)),
                    float(expected_z_span + (z_margin * 2.0)),
                    centered=(True, True, True)
                )
            )
            trimmed = safe_intersect(
                chunk_body,
                keep_box,
                f"{{member_label}} chunk {{candidate_index}} trim"
            )
            if trimmed is None:
                return None
            try:
                cleaned = trimmed.clean()
                if body_has_valid_shape(cleaned):
                    trimmed = cleaned
            except Exception:
                pass
            return select_largest_solid_body(trimmed, f"{{member_label}} chunk {{candidate_index}} trim")

        def append_chunk_record(candidate_profiles, candidate_index, depth=0):
            if len(candidate_profiles) < 3:
                return 0
            chunk_body = loft_body_from_profiles(candidate_profiles)
            if is_chunk_body_plausible(chunk_body, candidate_profiles, candidate_index):
                try:
                    chunk_records.append({{
                        "chunk_index": candidate_index,
                        "body": cq.Workplane("XY").newObject([chunk_body.findSolid()]),
                        "expected_box": profile_stack_bbox(candidate_profiles),
                        "profile_count": int(len(candidate_profiles))
                    }})
                    return 1
                except Exception:
                    return 0

            trimmed_body = trim_chunk_body_to_expected_bounds(chunk_body, candidate_profiles, candidate_index)
            if is_chunk_body_plausible(trimmed_body, candidate_profiles, f"{{candidate_index}}t"):
                try:
                    chunk_records.append({{
                        "chunk_index": f"{{candidate_index}}t",
                        "body": cq.Workplane("XY").newObject([trimmed_body.findSolid()]),
                        "expected_box": profile_stack_bbox(candidate_profiles),
                        "profile_count": int(len(candidate_profiles))
                    }})
                    print(
                        f"[*] {{member_label}} chunk {{candidate_index}} recovered by expected-bounds trim "
                        f"(profiles={{len(candidate_profiles)}})"
                    )
                    return 1
                except Exception:
                    pass

            if depth < 1 and len(candidate_profiles) > 5:
                sub_count = len(candidate_profiles)
                left_size = max(3, min(sub_count - 1, int(math.ceil(sub_count * 0.67))))
                right_start = max(1, sub_count - left_size)
                left_profiles = candidate_profiles[:left_size]
                right_profiles = candidate_profiles[right_start:]
                if len(left_profiles) >= 3 and len(right_profiles) >= 3 and right_start < sub_count:
                    print(
                        f"[*] {{member_label}} chunk {{candidate_index}} subdividing after rejection "
                        f"(profiles={{sub_count}}, depth={{depth + 1}})"
                    )
                    kept_count = 0
                    kept_count += append_chunk_record(left_profiles, f"{{candidate_index}}a", depth + 1)
                    kept_count += append_chunk_record(right_profiles, f"{{candidate_index}}b", depth + 1)
                    if kept_count > 0:
                        return kept_count

            if chunk_body is not None:
                print(
                    f"[*] {{member_label}} chunk {{candidate_index}} discarded before compound assembly "
                    f"(profiles={{len(candidate_profiles)}})"
                )
            return 0

        while start_idx < len(profile_stack) - 1:
            end_idx = min(len(profile_stack), start_idx + int(chunk_size))
            if (end_idx - start_idx) < 3:
                if chunk_records:
                    break
                return None
            chunk_profiles = profile_stack[start_idx:end_idx]
            append_chunk_record(chunk_profiles, int(chunk_index), depth=0)
            chunk_index += 1
            if end_idx >= len(profile_stack):
                break
            start_idx += step
        if not chunk_records:
            return None

        def bbox_xy_overlap_ratio(box_a, box_b):
            if box_a is None or box_b is None:
                return 0.0
            ax0, ax1, ay0, ay1, _, _ = box_a
            bx0, bx1, by0, by1, _, _ = box_b
            overlap_x = max(0.0, min(float(ax1), float(bx1)) - max(float(ax0), float(bx0)))
            overlap_y = max(0.0, min(float(ay1), float(by1)) - max(float(ay0), float(by0)))
            overlap_area = float(overlap_x * overlap_y)
            area_a = max(1e-6, (float(ax1) - float(ax0)) * (float(ay1) - float(ay0)))
            area_b = max(1e-6, (float(bx1) - float(bx0)) * (float(by1) - float(by0)))
            return overlap_area / max(1e-6, min(area_a, area_b))

        def bbox_z_gap(box_a, box_b):
            if box_a is None or box_b is None:
                return 1e9
            _, _, _, _, az0, az1 = box_a
            _, _, _, _, bz0, bz1 = box_b
            if float(az1) < float(bz0):
                return float(bz0) - float(az1)
            if float(bz1) < float(az0):
                return float(az0) - float(bz1)
            return 0.0

        for chunk_record in chunk_records:
            chunk_record["bbox"] = body_bbox(chunk_record.get("body"))
            chunk_box = chunk_record.get("bbox")
            if chunk_box is None:
                chunk_record["bbox_proxy"] = 0.0
            else:
                cx0, cx1, cy0, cy1, cz0, cz1 = chunk_box
                chunk_record["bbox_proxy"] = max(0.0, float(cx1) - float(cx0)) * max(0.0, float(cy1) - float(cy0)) * max(0.0, float(cz1) - float(cz0))

        member_z_min = float(profile_stack[0].get("z", 0.0))
        member_z_max = float(profile_stack[-1].get("z", 0.0))
        member_z_span = max(1.0, member_z_max - member_z_min)
        terminal_band = max(2.2, member_z_span * 0.12)
        chunk_bbox_proxies = [float(item.get("bbox_proxy", 0.0)) for item in chunk_records if float(item.get("bbox_proxy", 0.0)) > 1e-6]
        median_chunk_bbox_proxy = float(np.median(np.asarray(chunk_bbox_proxies, dtype=float))) if chunk_bbox_proxies else 0.0

        pruned_chunk_records = []
        redundant_terminal_chunk_count = 0
        for idx, chunk_record in enumerate(chunk_records):
            chunk_box = chunk_record.get("bbox")
            expected_box = chunk_record.get("expected_box")
            if chunk_box is None or expected_box is None:
                pruned_chunk_records.append(chunk_record)
                continue

            _, _, _, _, ez0, ez1 = expected_box
            _, _, _, _, az0, az1 = chunk_box
            actual_z_span = max(0.0, float(az1) - float(az0))
            expected_z_span = max(0.0, float(ez1) - float(ez0))
            chunk_bbox_proxy = float(chunk_record.get("bbox_proxy", 0.0))
            terminal_like = (
                (min(abs(float(az0) - member_z_min), abs(float(ez0) - member_z_min)) <= terminal_band) or
                (min(abs(member_z_max - float(az1)), abs(member_z_max - float(ez1))) <= terminal_band)
            )
            thin_like = actual_z_span <= max(1.0, expected_z_span * 1.55, member_z_span * 0.045)
            small_like = chunk_bbox_proxy <= max(6500.0, median_chunk_bbox_proxy * 0.38)

            redundant_neighbor = None
            for neighbor in (
                pruned_chunk_records[-1] if pruned_chunk_records else None,
                chunk_records[idx + 1] if idx + 1 < len(chunk_records) else None
            ):
                if neighbor is None:
                    continue
                neighbor_box = neighbor.get("bbox")
                neighbor_bbox_proxy = float(neighbor.get("bbox_proxy", 0.0))
                if neighbor_box is None or neighbor_bbox_proxy <= 0.0:
                    continue
                overlap_ratio = bbox_xy_overlap_ratio(chunk_box, neighbor_box)
                z_gap = bbox_z_gap(chunk_box, neighbor_box)
                if overlap_ratio >= 0.62 and z_gap <= max(2.0, actual_z_span * 3.0) and neighbor_bbox_proxy >= (chunk_bbox_proxy * 1.35):
                    redundant_neighbor = neighbor
                    break

            if terminal_like and thin_like and small_like and redundant_neighbor is not None:
                redundant_terminal_chunk_count += 1
                print(
                    f"[*] {{member_label}} chunk {{chunk_record['chunk_index']}} pruned as redundant terminal slice "
                    f"(z_span={{actual_z_span:.2f}}, bbox_proxy={{chunk_bbox_proxy:.1f}})"
                )
                continue

            pruned_chunk_records.append(chunk_record)

        if pruned_chunk_records:
            chunk_records = pruned_chunk_records

        if redundant_terminal_chunk_count > 0:
            print(
                f"[*] {{member_label}} chunk cleanup: "
                f"pruned_terminal={{redundant_terminal_chunk_count}}, "
                f"remaining={{len(chunk_records)}}"
            )

        if len(chunk_records) == 1:
            only_chunk = chunk_records[0].get("body")
            if body_has_valid_shape(only_chunk):
                print(
                    f"[*] {{member_label}} z-loft built as single chunked multi-wire body "
                    f"(chunks=1, wires={{len(profile_stack)}})"
                )
                return only_chunk
            return None

        chunk_parts = [item.get("body") for item in chunk_records if item.get("body") is not None]
        try:
            compound_body = direct_compound_assembly(
                chunk_parts,
                f"{{member_label}} z-loft chunk compound"
            )
            print(
                f"[*] {{member_label}} z-loft emitted as direct chunk compound "
                f"(chunks={{len(chunk_parts)}}, wires={{len(profile_stack)}})"
            )
            return compound_body
        except Exception as compound_exc:
            print(f"[!] {{member_label}} direct chunk compound failed: {{compound_exc}}")
            return direct_compound_assembly(chunk_parts, f"{{member_label}} z-loft chunk fallback compound")

    if len(loft_wires) >= 4 and len(loft_wires) <= 10:
        try:
            solid = cq.Solid.makeLoft(loft_wires, ruled=False)
            multi_wire_body = cq.Workplane("XY").newObject([solid])
            if body_has_valid_shape(multi_wire_body, require_single_solid=True):
                print(f"[*] {{member_label}} z-loft built as single multi-wire solid (wires={{len(loft_wires)}})")
                return multi_wire_body
        except Exception as multi_loft_exc:
            print(f"[!] {{member_label}} z-loft single multi-wire failed: {{multi_loft_exc}}")
            try:
                solid = cq.Solid.makeLoft(loft_wires, ruled=True)
                multi_wire_body = cq.Workplane("XY").newObject([solid])
                if body_has_valid_shape(multi_wire_body, require_single_solid=True):
                    print(f"[*] {{member_label}} z-loft built as single multi-wire ruled solid (wires={{len(loft_wires)}})")
                    return multi_wire_body
            except Exception as ruled_multi_loft_exc:
                print(f"[!] {{member_label}} z-loft single multi-wire ruled failed: {{ruled_multi_loft_exc}}")

    chunked_multi_wire_body = build_chunked_multi_wire_body(prepared_profiles, chunk_size=6, overlap=1)
    if chunked_multi_wire_body is not None:
        return chunked_multi_wire_body

    spoke_body = None
    segment_count = 0
    skipped_segment_count = 0

    def build_pair_loft(lower_loop, upper_loop, z0, z1, ruled=False):
        return (
            cq.Workplane("XY")
            .workplane(offset=float(z0))
            .polyline(lower_loop).close()
            .workplane(offset=(float(z1) - float(z0)))
            .polyline(upper_loop).close()
            .loft(combine=True, ruled=ruled)
        )

    for profile_a, profile_b in zip(prepared_profiles[:-1], prepared_profiles[1:]):
        if profile_b["z"] <= profile_a["z"] + 0.4:
            continue
        lower_loop = [(float(x), float(y)) for x, y in (profile_a.get("points", []) or [])[:-1]]
        upper_loop = [(float(x), float(y)) for x, y in (profile_b.get("points", []) or [])[:-1]]
        if len(lower_loop) < 8 or len(upper_loop) < 8:
            skipped_segment_count += 1
            continue
        segment_body = None
        try:
            segment_body = build_pair_loft(lower_loop, upper_loop, profile_a["z"], profile_b["z"], ruled=False)
        except Exception as smooth_exc:
            try:
                segment_body = build_pair_loft(lower_loop, upper_loop, profile_a["z"], profile_b["z"], ruled=True)
                print(f"[*] {{member_label}} z-loft pair recovered with ruled loft")
            except Exception as ruled_exc:
                mid_z = (float(profile_a["z"]) + float(profile_b["z"])) * 0.5
                midpoint_loop = []
                for (ax, ay), (bx, by) in zip(lower_loop, upper_loop):
                    midpoint_loop.append((
                        round((float(ax) + float(bx)) * 0.5, 3),
                        round((float(ay) + float(by)) * 0.5, 3)
                    ))
                try:
                    lower_mid = build_pair_loft(lower_loop, midpoint_loop, profile_a["z"], mid_z, ruled=True)
                    mid_upper = build_pair_loft(midpoint_loop, upper_loop, mid_z, profile_b["z"], ruled=True)
                    segment_body = safe_union(
                        lower_mid,
                        mid_upper,
                        f"{{member_label}} z-loft midpoint rescue"
                    )
                    print(f"[*] {{member_label}} z-loft pair recovered with midpoint rescue")
                except Exception as rescue_exc:
                    print(
                        f"[!] {{member_label}} z-loft pair skipped: "
                        f"smooth={{smooth_exc}}; ruled={{ruled_exc}}; rescue={{rescue_exc}}"
                    )
                    skipped_segment_count += 1
                    continue

        if segment_body is None:
            skipped_segment_count += 1
            continue

        if spoke_body is None:
            spoke_body = segment_body
        else:
            spoke_body = safe_union(spoke_body, segment_body, f"{{member_label}} z-loft segment")
        segment_count += 1

    if spoke_body is None or segment_count == 0:
        return None
    if skipped_segment_count > 0:
        print(f"[*] {{member_label}} z-loft built with skipped_segments={{skipped_segment_count}}")
    # Do not collapse to the largest solid here. For real XY@Z stacks, tiny
    # terminal contact solids are exactly the geometry we need to preserve.
    try:
        cleaned = spoke_body.clean()
        if body_has_valid_shape(cleaned):
            return cleaned
    except Exception:
        pass
    return spoke_body

def build_member_root_overlap_pad(member_payload, z_profiles, member_label):
    if not isinstance(member_payload, dict):
        return None
    member_payload["_root_overlap_pad_mode"] = None
    try:
        member_index = int(member_payload.get("member_index"))
    except Exception:
        return None
    if member_index < 0 or member_index >= len(spoke_root_regions):
        return None

    root_region_payload = spoke_root_regions[member_index]
    root_region_pts = root_region_payload.get("points", []) if isinstance(root_region_payload, dict) else root_region_payload
    if len(root_region_pts) < 4:
        return None

    try:
        root_poly = largest_polygon(normalize_polygon(Polygon(root_region_pts)), min_area=12.0)
    except Exception:
        root_poly = None
    if root_poly is None or root_poly.is_empty:
        return None

    prepared_profiles = [profile for profile in (z_profiles or []) if isinstance(profile, dict)]
    if len(prepared_profiles) < 4:
        return None
    prepared_profiles = sorted(prepared_profiles, key=lambda profile: float(profile.get("z", 0.0)))

    seed_profiles = prepared_profiles[: min(8, len(prepared_profiles))]
    root_outer_candidates = []
    z_seed = []
    for profile in seed_profiles:
        try:
            z_seed.append(float(profile.get("z", 0.0)))
        except Exception:
            continue
        pts = profile.get("points", []) or []
        if len(pts) < 4:
            continue
        try:
            root_outer_candidates.append(min(math.hypot(float(x), float(y)) for x, y in pts[:-1]))
        except Exception:
            continue
    if not root_outer_candidates or not z_seed:
        return None

    root_outer_r = float(np.percentile(np.asarray(root_outer_candidates, dtype=float), 35.0)) + 1.8
    root_inner_r = max(float(params.get("bore_radius", 0.0)) + 0.8, root_outer_r - 18.0)
    if root_outer_r <= root_inner_r + 1.2:
        return None

    annulus_outer = Polygon(circle_points(root_outer_r, 180))
    annulus_inner = Polygon(circle_points(root_inner_r, 180))
    try:
        root_band_poly = normalize_polygon(root_poly.intersection(annulus_outer).difference(annulus_inner))
        root_band_poly = largest_polygon(root_band_poly, min_area=10.0)
    except Exception:
        root_band_poly = None
    fallback_mode = None
    if root_band_poly is None or root_band_poly.is_empty:
        region_radii = []
        try:
            region_radii = [
                math.hypot(float(x), float(y))
                for x, y in root_region_pts[:-1]
            ]
        except Exception:
            region_radii = []
        sparse_profile_fallback = len(prepared_profiles) <= 40
        if region_radii and sparse_profile_fallback:
            try:
                region_radius_arr = np.asarray(region_radii, dtype=float)
                fallback_inner_r = max(
                    float(params.get("bore_radius", 0.0)) + 0.8,
                    float(np.percentile(region_radius_arr, 55.0)) - 0.9
                )
                fallback_outer_r = min(
                    float(np.percentile(region_radius_arr, 98.0)) + 0.9,
                    root_outer_r + 4.0
                )
                if fallback_outer_r > fallback_inner_r + 1.0:
                    fallback_outer = Polygon(circle_points(fallback_outer_r, 180))
                    fallback_inner = Polygon(circle_points(fallback_inner_r, 180))
                    root_band_poly = normalize_polygon(
                        root_poly.intersection(fallback_outer).difference(fallback_inner)
                    )
                    root_band_poly = largest_polygon(root_band_poly, min_area=6.0)
                    if root_band_poly is not None and not root_band_poly.is_empty:
                        root_inner_r = fallback_inner_r
                        root_outer_r = fallback_outer_r
                        fallback_mode = "region_clip"
            except Exception:
                root_band_poly = None
    if root_band_poly is None or root_band_poly.is_empty:
        try:
            root_band_poly = largest_polygon(root_poly, min_area=12.0)
            if root_band_poly is not None and not root_band_poly.is_empty:
                fallback_mode = "full_region"
        except Exception:
            root_band_poly = None
    if root_band_poly is None or root_band_poly.is_empty:
        return None

    pad_loop = [(round(float(x), 3), round(float(y), 3)) for x, y in list(root_band_poly.exterior.coords)]
    if len(pad_loop) < 4:
        return None

    z_low = min(z_seed) - 1.6
    z_high = min(min(z_seed) + 3.2, max(z_seed) + 0.8)
    pad_height = max(1.4, z_high - z_low)
    try:
        pad_body = (
            cq.Workplane("XY")
            .workplane(offset=float(z_low))
            .polyline(pad_loop).close()
            .extrude(float(pad_height))
        )
        pad_body = cq.Workplane("XY").newObject([pad_body.findSolid()])
        if body_has_valid_shape(pad_body):
            member_payload["_root_overlap_pad_mode"] = fallback_mode or "profile_clip"
            print(
                f"[*] {{member_label}} root overlap pad prepared: "
                f"R={{root_inner_r:.2f}}->{{root_outer_r:.2f}}, "
                f"Z={{z_low:.2f}}->{{z_low + pad_height:.2f}}, "
                f"mode={{fallback_mode or 'profile_clip'}}"
            )
            return pad_body
    except Exception as root_pad_exc:
        print(f"[!] {{member_label}} root overlap pad failed: {{root_pad_exc}}")
    return None

def prepare_member_actual_z_loft_profiles(member_payload, member_label):
    upstream_prefer_local_section = bool(member_payload.get("actual_z_prefer_local_section")) if isinstance(member_payload, dict) else False
    upstream_stack_mode = str(member_payload.get("actual_z_stack_mode") or "") if isinstance(member_payload, dict) else ""
    try:
        upstream_profile_count = int(member_payload.get("actual_z_profile_count", 0)) if isinstance(member_payload, dict) else 0
    except Exception:
        upstream_profile_count = 0

    def set_loft_route_meta(stack_mode=None, prefer_local_section=None, profile_count=None):
        if not isinstance(member_payload, dict):
            return
        if prefer_local_section is not None:
            member_payload["_actual_z_loft_prefer_local_section"] = bool(prefer_local_section)
        if stack_mode is not None:
            member_payload["_actual_z_loft_stack_mode"] = str(stack_mode)
        if profile_count is not None:
            try:
                member_payload["_actual_z_loft_profile_count"] = int(profile_count)
            except Exception:
                member_payload["_actual_z_loft_profile_count"] = 0

    if isinstance(member_payload, dict):
        set_loft_route_meta(
            stack_mode=upstream_stack_mode if upstream_stack_mode else "uninitialized",
            prefer_local_section=upstream_prefer_local_section,
            profile_count=upstream_profile_count
        )
    actual_profiles = sorted(
        [profile for profile in (member_payload.get("actual_z_profiles", []) or []) if isinstance(profile, dict)],
        key=lambda item: float(item.get("z", 0.0))
    )
    if len(actual_profiles) < 4:
        set_loft_route_meta(
            stack_mode="insufficient_raw",
            prefer_local_section=upstream_prefer_local_section,
            profile_count=len(actual_profiles)
        )
        return []

    tip_section_count = len(member_payload.get("tip_sections", []) or [])
    count_floor = 12
    coverage_floor = 0.72
    start_gap_limit = 4.2
    end_gap_limit = 8.8 if tip_section_count >= 2 else 7.6

    def stack_quality(stack):
        if not stack:
            return None
        try:
            target_z_low, target_z_high = derive_member_vertical_limits(member_payload)
            target_z_span = max(1.0, float(target_z_high) - float(target_z_low))
        except Exception:
            return None
        z_low = float(stack[0].get("z", 0.0))
        z_high = float(stack[-1].get("z", 0.0))
        z_span = max(0.0, z_high - z_low)
        return {{
            "count": len(stack),
            "coverage_ratio": z_span / target_z_span,
            "start_gap": max(0.0, z_low - float(target_z_low)),
            "end_gap": max(0.0, float(target_z_high) - z_high)
        }}

    def stack_soft_ok(metrics):
        if metrics is None:
            return False
        return (
            int(metrics.get("count", 0)) >= int(count_floor) and
            float(metrics.get("coverage_ratio", 0.0)) >= float(coverage_floor) and
            float(metrics.get("start_gap", 0.0)) <= float(start_gap_limit) and
            float(metrics.get("end_gap", 0.0)) <= float(end_gap_limit)
        )

    try:
        raw_metrics = stack_quality(actual_profiles)
        if not stack_soft_ok(raw_metrics):
            print(
                f"[*] {{member_label}} actual-direct gated off: "
                f"count={{raw_metrics['count'] if raw_metrics else len(actual_profiles)}}, "
                f"coverage={{raw_metrics['coverage_ratio']:.2f if raw_metrics else 0.0}}, "
                f"start_gap={{raw_metrics['start_gap']:.2f if raw_metrics else 0.0}}, "
                f"end_gap={{raw_metrics['end_gap']:.2f if raw_metrics else 0.0}}"
            )
            set_loft_route_meta(
                stack_mode="raw_gated_off",
                prefer_local_section=upstream_prefer_local_section,
                profile_count=len(actual_profiles)
            )
            return []
    except Exception:
        pass

    member_angle_deg = float(member_payload.get("angle", 0.0))
    angle_rad = math.radians(float(member_angle_deg or 0.0))
    tangential_dir = np.asarray([-math.sin(angle_rad), math.cos(angle_rad)], dtype=float)

    prepared = []
    previous_loop = None
    for profile in actual_profiles:
        pts = profile.get("points", []) or []
        if len(pts) < 4:
            continue
        try:
            poly = largest_polygon(normalize_polygon(Polygon(pts)), min_area=12.0)
        except Exception:
            poly = None
        if poly is None or poly.is_empty:
            continue
        coords = canonicalize_member_loop(list(poly.exterior.coords), member_angle_deg)
        if len(coords) < 4:
            continue
        sampled = resample_closed_loop(coords, target_count=64)
        if len(sampled) < 8:
            continue
        if previous_loop is not None:
            sampled = align_resampled_loop(previous_loop, sampled, allow_reverse=False)
        previous_loop = sampled
        sampled_loop = sampled + [sampled[0]]
        try:
            sampled_poly = largest_polygon(normalize_polygon(Polygon(sampled_loop)), min_area=12.0)
        except Exception:
            sampled_poly = None
        if sampled_poly is None or sampled_poly.is_empty:
            continue
        centroid = sampled_poly.centroid
        sampled_coords = list(sampled_poly.exterior.coords)
        radii = [math.hypot(float(x), float(y)) for x, y in sampled_coords[:-1]]
        tangential_values = [
            float(np.dot(np.asarray([float(x), float(y)], dtype=float), tangential_dir))
            for x, y in sampled_coords[:-1]
        ]
        if not radii or not tangential_values:
            continue
        prepared.append({{
            "z": round(float(profile.get("z", 0.0)), 3),
            "points": [(round(float(x), 3), round(float(y), 3)) for x, y in sampled_loop],
            "area": float(sampled_poly.area),
            "r_min": float(min(radii)),
            "r_max": float(max(radii)),
            "width": float(max(tangential_values) - min(tangential_values)),
            "center_t": float(np.dot(np.asarray([float(centroid.x), float(centroid.y)], dtype=float), tangential_dir)),
            "terminal_contact": bool(profile.get("terminal_contact")),
            "preserve_detail": bool(profile.get("preserve_detail")) or bool(profile.get("terminal_contact"))
        }})

    if len(prepared) < 4:
        set_loft_route_meta(
            stack_mode="prepared_insufficient",
            prefer_local_section=upstream_prefer_local_section,
            profile_count=len(prepared)
        )
        return []

    global_z_min = float(min(item["z"] for item in prepared))
    global_z_max = float(max(item["z"] for item in prepared))
    global_z_span = max(1.0, global_z_max - global_z_min)
    terminal_band = max(2.8, global_z_span * 0.18)
    terminal_soft_band = max(3.6, global_z_span * 0.26)

    def entry_is_terminal(entry, soft=False):
        if bool(entry.get("terminal_contact")):
            return True
        try:
            z_val = float(entry.get("z", 0.0))
        except Exception:
            return False
        band = terminal_soft_band if soft else terminal_band
        return (
            (z_val - global_z_min) <= band or
            (global_z_max - z_val) <= band
        )

    for entry in prepared:
        if entry_is_terminal(entry):
            entry["terminal_contact"] = True
            entry["preserve_detail"] = True

    def recompute_profile_metrics(entry):
        pts = entry.get("points", []) or []
        if len(pts) < 4:
            return entry
        try:
            poly = largest_polygon(normalize_polygon(Polygon(pts)), min_area=12.0)
        except Exception:
            poly = None
        if poly is None or poly.is_empty:
            return entry
        centroid = poly.centroid
        coords = list(poly.exterior.coords)
        radii = [math.hypot(float(x), float(y)) for x, y in coords[:-1]]
        tangential_values = [
            float(np.dot(np.asarray([float(x), float(y)], dtype=float), tangential_dir))
            for x, y in coords[:-1]
        ]
        if not radii or not tangential_values:
            return entry
        entry["area"] = float(poly.area)
        entry["r_min"] = float(min(radii))
        entry["r_max"] = float(max(radii))
        entry["width"] = float(max(tangential_values) - min(tangential_values))
        entry["center_t"] = float(np.dot(np.asarray([float(centroid.x), float(centroid.y)], dtype=float), tangential_dir))
        entry["points"] = [(round(float(x), 3), round(float(y), 3)) for x, y in coords]
        return entry

    central_entries = [
        item for item in prepared
        if np.percentile(np.asarray([float(p["z"]) for p in prepared], dtype=float), 15.0)
        <= float(item["z"]) <=
        np.percentile(np.asarray([float(p["z"]) for p in prepared], dtype=float), 85.0)
    ]
    baseline_entries = central_entries if len(central_entries) >= 6 else prepared
    median_area = float(np.median(np.asarray([float(item["area"]) for item in baseline_entries], dtype=float)))
    median_width = float(np.median(np.asarray([float(item["width"]) for item in baseline_entries], dtype=float)))

    def is_reasonably_full(entry):
        return (
            float(entry["area"]) >= max(40.0, median_area * 0.42)
            and float(entry["width"]) >= max(8.0, median_width * 0.72)
        )

    repaired_count = 0
    for idx in range(1, len(prepared) - 1):
        entry = prepared[idx]
        if entry_is_terminal(entry, soft=True):
            continue
        area_small = float(entry["area"]) < max(40.0, median_area * 0.24)
        width_small = float(entry["width"]) < max(8.0, median_width * 0.58)
        if not (area_small or width_small):
            continue
        prev = None
        nxt = None
        for back_idx in range(idx - 1, max(-1, idx - 4), -1):
            if is_reasonably_full(prepared[back_idx]):
                prev = prepared[back_idx]
                break
        for fwd_idx in range(idx + 1, min(len(prepared), idx + 4)):
            if is_reasonably_full(prepared[fwd_idx]):
                nxt = prepared[fwd_idx]
                break
        if prev is None or nxt is None:
            continue
        if float(nxt["z"]) <= float(prev["z"]) + 0.25:
            continue
        lower_loop = resample_closed_loop(prev["points"], target_count=64)
        upper_loop = resample_closed_loop(nxt["points"], target_count=64)
        if len(lower_loop) < 8 or len(upper_loop) < 8:
            continue
        upper_loop = align_resampled_loop(lower_loop, upper_loop, allow_reverse=False)
        blend_ratio = (float(entry["z"]) - float(prev["z"])) / max(1e-6, float(nxt["z"]) - float(prev["z"]))
        rebuilt = []
        for (ax, ay), (bx, by) in zip(lower_loop, upper_loop):
            rebuilt.append((
                round(((1.0 - blend_ratio) * float(ax)) + (blend_ratio * float(bx)), 3),
                round(((1.0 - blend_ratio) * float(ay)) + (blend_ratio * float(by)), 3)
            ))
        rebuilt.append(rebuilt[0])
        entry["points"] = rebuilt
        entry["repaired"] = True
        recompute_profile_metrics(entry)
        repaired_count += 1

    filtered = [prepared[0]]
    rejected_count = 0
    for entry in prepared[1:]:
        prev = filtered[-1]
        dz = float(entry["z"]) - float(prev["z"])
        if dz <= 0.15:
            rejected_count += 1
            continue
        entry_terminal = entry_is_terminal(entry, soft=True) or bool(entry.get("preserve_detail"))
        prev_terminal = entry_is_terminal(prev, soft=True) or bool(prev.get("preserve_detail"))
        terminal_lenient = entry_terminal or prev_terminal
        max_rmin_jump = 34.0 if terminal_lenient else 14.0
        max_rmax_jump = 52.0 if terminal_lenient else 18.0
        max_center_t_jump = (
            max(22.0, float(prev["width"]) * 1.65)
            if terminal_lenient else
            max(9.0, float(prev["width"]) * 0.82)
        )
        expands_support = (
            float(entry["r_min"]) < float(prev["r_min"]) - 1.4 or
            float(entry["r_max"]) > float(prev["r_max"]) + 1.4 or
            float(entry["area"]) > (float(prev["area"]) * 1.12)
        )
        if abs(float(entry["r_min"]) - float(prev["r_min"])) > max_rmin_jump:
            if not (terminal_lenient and expands_support):
                rejected_count += 1
                continue
        if abs(float(entry["r_max"]) - float(prev["r_max"])) > max_rmax_jump:
            if not (terminal_lenient and expands_support):
                rejected_count += 1
                continue
        if abs(float(entry["center_t"]) - float(prev["center_t"])) > max_center_t_jump:
            if not (
                terminal_lenient and
                expands_support and
                abs(float(entry["center_t"]) - float(prev["center_t"])) <= max(34.0, float(prev["width"]) * 2.15)
            ):
                rejected_count += 1
                continue
        filtered.append(entry)

    runs = []
    current_run = []
    for entry in filtered:
        if not current_run:
            current_run = [entry]
            continue
        if float(entry["z"]) <= float(current_run[-1]["z"]) + 8.8:
            current_run.append(entry)
        else:
            runs.append(current_run)
            current_run = [entry]
    if current_run:
        runs.append(current_run)
    if not runs:
        set_loft_route_meta(
            stack_mode="prepared_empty",
            prefer_local_section=upstream_prefer_local_section,
            profile_count=0
        )
        return []

    best_run = max(
        runs,
        key=lambda run: (
            float(run[-1]["z"]) - float(run[0]["z"]),
            len(run),
            sum(float(item["area"]) for item in run)
        )
    )
    if len(best_run) < 4:
        set_loft_route_meta(
            stack_mode="prepared_insufficient",
            prefer_local_section=upstream_prefer_local_section,
            profile_count=len(best_run)
        )
        return []

    fallback_used = False
    try:
        run_metrics = stack_quality(best_run)
        if not stack_soft_ok(run_metrics):
            fallback_run = prepared
            fallback_metrics = stack_quality(fallback_run)
            if stack_soft_ok(fallback_metrics):
                best_run = fallback_run
                fallback_used = True
                print(
                    f"[*] {{member_label}} actual-direct fallback to full XY@Z stack: "
                    f"count={{fallback_metrics['count']}}, coverage={{fallback_metrics['coverage_ratio']:.2f}}, "
                    f"start_gap={{fallback_metrics['start_gap']:.2f}}, end_gap={{fallback_metrics['end_gap']:.2f}}"
                )
            else:
                print(
                    f"[*] {{member_label}} actual-direct prepared run rejected: "
                    f"count={{run_metrics['count'] if run_metrics else len(best_run)}}, "
                    f"coverage={{run_metrics['coverage_ratio']:.2f if run_metrics else 0.0}}, "
                    f"start_gap={{run_metrics['start_gap']:.2f if run_metrics else 0.0}}, "
                    f"end_gap={{run_metrics['end_gap']:.2f if run_metrics else 0.0}}"
                )
                set_loft_route_meta(
                    stack_mode="prepared_rejected",
                    prefer_local_section=upstream_prefer_local_section,
                    profile_count=len(best_run)
                )
                return []
    except Exception:
        pass

    def reduce_profile_run(run_entries, max_count=28):
        if len(run_entries) <= max_count:
            return list(run_entries), 0

        terminal_keep = min(8, max(4, max_count // 4))
        kept_indices = set(range(min(terminal_keep, len(run_entries))))
        kept_indices.update(range(max(0, len(run_entries) - terminal_keep), len(run_entries)))
        for idx, entry in enumerate(run_entries):
            if entry_is_terminal(entry, soft=True) or bool(entry.get("preserve_detail")):
                kept_indices.add(idx)
        if len(kept_indices) > max_count:
            max_count = len(kept_indices)
        if len(kept_indices) >= len(run_entries):
            return list(run_entries), 0

        score_rows = []
        target_z_step = max(1.2, (float(run_entries[-1]["z"]) - float(run_entries[0]["z"])) / max(1, max_count - 1))
        median_area_local = float(np.median(np.asarray([float(item["area"]) for item in run_entries], dtype=float)))
        median_width_local = float(np.median(np.asarray([float(item["width"]) for item in run_entries], dtype=float)))

        for idx in range(1, len(run_entries) - 1):
            curr = run_entries[idx]
            prev = run_entries[idx - 1]
            nxt = run_entries[idx + 1]
            local_score = 0.0
            local_score += abs(float(nxt["area"]) - float(prev["area"])) / max(24.0, median_area_local * 0.35)
            local_score += abs(float(nxt["width"]) - float(prev["width"])) / max(4.0, median_width_local * 0.22)
            local_score += abs(float(nxt["r_min"]) - float(prev["r_min"])) / 3.5
            local_score += abs(float(nxt["r_max"]) - float(prev["r_max"])) / 4.5
            local_score += abs(float(nxt["center_t"]) - float(prev["center_t"])) / max(2.0, median_width_local * 0.18)
            local_score += min(1.2, (float(curr["z"]) - float(prev["z"])) / max(0.8, target_z_step)) * 0.15
            if entry_is_terminal(curr, soft=True):
                local_score += 6.0
            if bool(curr.get("preserve_detail")):
                local_score += 4.0
            if abs(float(curr["r_min"]) - float(prev["r_min"])) > max(2.0, median_width_local * 0.10):
                local_score += 1.4
            if abs(float(curr["r_max"]) - float(prev["r_max"])) > max(2.4, median_width_local * 0.12):
                local_score += 1.6
            if abs(float(curr["area"]) - float(prev["area"])) > max(18.0, median_area_local * 0.12):
                local_score += 1.2
            if curr.get("repaired"):
                local_score += 0.25
            score_rows.append((local_score, idx))

        score_rows.sort(key=lambda item: item[0], reverse=True)
        for _, idx in score_rows:
            if len(kept_indices) >= max_count:
                break
            kept_indices.add(idx)

        if len(kept_indices) < max_count:
            fill_candidates = np.linspace(0, len(run_entries) - 1, max_count)
            for idx in [int(round(val)) for val in fill_candidates]:
                kept_indices.add(max(0, min(len(run_entries) - 1, idx)))
                if len(kept_indices) >= max_count:
                    break

        reduced = [run_entries[idx] for idx in sorted(kept_indices)]
        return reduced, max(0, len(run_entries) - len(reduced))

    desired_max_count = len(best_run) if len(best_run) <= 72 else min(72, max(24, int(math.ceil(len(best_run) * 0.85))))
    best_run, collapsed_count = reduce_profile_run(best_run, max_count=desired_max_count)
    if collapsed_count > 0:
        print(
            f"[*] {{member_label}} actual-direct profile run reduced: "
            f"kept={{len(best_run)}}, collapsed={{collapsed_count}}"
        )

    print(
        f"[*] {{member_label}} direct XY@Z z-loft profiles prepared: "
        f"kept={{len(best_run)}}, rejected={{rejected_count}}, "
        f"repaired={{repaired_count}}, "
        f"Z={{float(best_run[0]['z']):.2f}}->{{float(best_run[-1]['z']):.2f}}"
    )
    resolved_prefer_local_section = bool(upstream_prefer_local_section or fallback_used)
    if upstream_stack_mode:
        resolved_stack_mode = upstream_stack_mode
    elif fallback_used:
        resolved_stack_mode = "direct_full_stack_fallback"
    else:
        resolved_stack_mode = "direct_prepared_clean"
    set_loft_route_meta(
        stack_mode=resolved_stack_mode,
        prefer_local_section=resolved_prefer_local_section,
        profile_count=len(best_run)
    )
    return [
        {{
            "z": float(item["z"]),
            "points": item["points"],
            "terminal_contact": bool(item.get("terminal_contact")),
            "preserve_detail": bool(item.get("preserve_detail"))
        }}
        for item in best_run
    ]

def prepare_member_actual_z_loft_profiles(member_payload, member_label):
    member_payload["_actual_z_loft_prefer_local_section"] = False
    member_payload["_actual_z_loft_stack_mode"] = "archived_actual_z_path"
    member_payload["_actual_z_loft_profile_count"] = 0
    return []


def member_local_loop_to_world(coords, member_angle_deg):
    if not coords or len(coords) < 4:
        return []

    pts = [(float(x), float(y)) for x, y in coords]
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return []

    angle_rad = math.radians(float(member_angle_deg or 0.0))
    radial_dir = np.asarray([math.cos(angle_rad), math.sin(angle_rad)], dtype=float)
    tangential_dir = np.asarray([-math.sin(angle_rad), math.cos(angle_rad)], dtype=float)

    world_pts = []
    for radial_val, tangential_val in pts:
        world_point = (radial_dir * float(radial_val)) + (tangential_dir * float(tangential_val))
        world_pts.append((round(float(world_point[0]), 3), round(float(world_point[1]), 3)))

    if len(world_pts) < 3:
        return []
    world_loop = canonicalize_member_loop(world_pts + [world_pts[0]], member_angle_deg)
    return world_loop if len(world_loop) >= 4 else []

def build_member_canonical_template_profile_spoke(member_payload, template_payload, member_label):
    template_profiles = []
    if isinstance(template_payload, dict):
        template_profiles = (
            template_payload.get("donor_profiles", [])
            or template_payload.get("profiles", [])
            or []
        )
    member_angle_deg = float(member_payload.get("angle", 0.0))
    if len(template_profiles) < 3:
        return None

    z_profiles = []
    previous_local = None
    for profile in sorted(template_profiles, key=lambda item: float(item.get("z", 0.0))):
        pts_local = profile.get("points_local", []) if isinstance(profile, dict) else []
        if len(pts_local) < 4:
            continue
        sampled_local = resample_closed_loop(pts_local, target_count=42)
        if len(sampled_local) < 8:
            continue
        if previous_local is not None:
            sampled_local = align_resampled_loop(
                previous_local,
                sampled_local,
                allow_reverse=False
            )
        previous_local = sampled_local
        world_loop = member_local_loop_to_world(sampled_local + [sampled_local[0]], member_angle_deg)
        if len(world_loop) < 4:
            continue
        try:
            z_val = round(float(profile.get("z", 0.0)), 3)
        except Exception:
            continue
        z_profiles.append({{
            "z": z_val,
            "points": world_loop
        }})

    if len(z_profiles) < 3:
        return None
    return build_member_loft_from_z_profiles(z_profiles, f"{{member_label}} canonical-template", member_angle_deg)

def build_member_section_template_hybrid(section_body, template_body, member_payload, member_label):
    if section_body is None or template_body is None:
        return None

    section_payloads = [
        section for section in (member_payload.get("sections", []) or [])
        if isinstance(section, dict)
    ]
    station_radii = sorted(
        float(section.get("station_r", 0.0))
        for section in section_payloads
        if float(section.get("station_r", 0.0)) > 0.0
    )
    if len(station_radii) < 4:
        return None

    root_extension_count = len([
        section for section in section_payloads
        if str(section.get("extension_side") or "") == "root"
    ])
    tip_extension_count = len([
        section for section in section_payloads
        if str(section.get("extension_side") or "") in ("tip", "donor_tip", "template_tip")
    ])

    z_bottom, z_top = derive_member_vertical_limits(member_payload)
    z_bottom -= 1.2
    z_top += 1.2

    keep_idx = min(2, len(station_radii) - 2)
    root_keep_outer = float(station_radii[keep_idx]) + 0.8
    tip_keep_inner = float(station_radii[-(keep_idx + 1)]) - 0.8
    if tip_keep_inner <= root_keep_outer + 4.0:
        return None

    root_cutter = build_annulus_prism(max(0.0, float(params["bore_radius"]) - 1.0), root_keep_outer, z_bottom, z_top)
    mid_cutter = build_annulus_prism(max(0.0, root_keep_outer - 0.6), tip_keep_inner + 0.6, z_bottom, z_top)
    tip_cutter = build_annulus_prism(tip_keep_inner, float(params["rim_max_radius"]) + 1.0, z_bottom, z_top)
    if root_cutter is None or mid_cutter is None or tip_cutter is None:
        return None

    root_part = safe_intersect(section_body, root_cutter, f"{{member_label}} hybrid root keep")
    tip_part = safe_intersect(section_body, tip_cutter, f"{{member_label}} hybrid tip keep")
    root_template = safe_intersect(template_body, root_cutter, f"{{member_label}} hybrid root template")
    tip_template = safe_intersect(template_body, tip_cutter, f"{{member_label}} hybrid tip template")
    mid_section = safe_intersect(section_body, mid_cutter, f"{{member_label}} hybrid mid section")
    mid_template = safe_intersect(template_body, mid_cutter, f"{{member_label}} hybrid mid template")
    if mid_section is None or mid_template is None:
        return None

    mid_part = safe_intersect(mid_section, mid_template, f"{{member_label}} hybrid mid intersect")
    if mid_part is None:
        return None

    if root_template is not None and root_extension_count < 2 and root_part is None:
        root_part = root_template
    if tip_template is not None and tip_extension_count < 2 and tip_part is None:
        tip_part = tip_template

    hybrid_body = mid_part
    if root_part is not None:
        hybrid_body = safe_union(hybrid_body, root_part, f"{{member_label}} hybrid root union")
    if tip_part is not None:
        hybrid_body = safe_union(hybrid_body, tip_part, f"{{member_label}} hybrid tip union")
    return finalize_member_body(hybrid_body, f"{{member_label}} hybrid assembled final")

def adapt_template_loop_to_section_payload(section_payload, template_loop, target_count=48):
    if not template_loop or len(template_loop) < 4:
        return []
    loop_points = canonicalize_local_section_loop(template_loop)
    if len(loop_points) < 4:
        return []
    loop_points = stabilize_local_section_loop(section_payload, loop_points)
    loop_points = rebuild_local_section_loop_from_y_samples(loop_points)
    loop_points = canonicalize_local_section_loop(loop_points)
    if len(loop_points) < 4:
        return []
    sampled = resample_closed_loop(loop_points, target_count=target_count)
    if len(sampled) < 8:
        return []
    sampled = [(round(float(x), 3), round(float(y), 3)) for x, y in sampled]
    sampled.append(sampled[0])
    return sampled

def transplant_local_section_loop_to_section_payload(section_payload, source_loop, previous_loop=None, target_count=64):
    # Map a donor/template local loop into the target section without rebuilding away its local detail.
    if not source_loop or len(source_loop) < 4:
        return []

    loop_points = canonicalize_local_section_loop(source_loop)
    if len(loop_points) < 4:
        return []

    source_samples = [(float(x), float(y)) for x, y in loop_points[:-1]]
    if len(source_samples) < 3:
        return []

    source_xs = [x for x, _ in source_samples]
    source_ys = [y for _, y in source_samples]
    source_center_x = (max(source_xs) + min(source_xs)) * 0.5
    source_width = max(1.0, max(source_xs) - min(source_xs))
    source_center_y = (max(source_ys) + min(source_ys)) * 0.5
    source_height = max(1.0, max(source_ys) - min(source_ys))

    target_center_x = section_payload.get("target_center_x")
    if target_center_x is None:
        target_center_x = section_payload.get("local_center_x")
    if target_center_x is None:
        target_center_x = source_center_x
    target_center_x = float(target_center_x)

    target_width = section_payload.get("target_width")
    if target_width is None:
        target_width = section_payload.get("local_width")
    if target_width is None:
        target_width = source_width
    target_width = max(1.0, float(target_width))

    # Keep donor back-face relief as-is in local Y; only remap tangential placement/width.
    target_center_y = source_center_y
    width_scale = max(0.92, min(1.12, target_width / max(source_width, 1e-6)))
    height_scale = 1.0

    transformed = []
    for x_val, y_val in source_samples:
        mapped_x = target_center_x + ((float(x_val) - source_center_x) * width_scale)
        mapped_y = target_center_y + ((float(y_val) - source_center_y) * height_scale)
        transformed.append((mapped_x, mapped_y))

    sampled = resample_closed_loop(transformed + [transformed[0]], target_count=target_count)
    if len(sampled) < 8:
        return []

    if previous_loop and len(previous_loop) >= 4:
        prev_ref = canonicalize_local_section_loop(previous_loop)
        if len(prev_ref) >= 4:
            prev_ref = [(float(x), float(y)) for x, y in prev_ref[:-1]]
            sampled = align_resampled_loop(prev_ref, sampled, allow_reverse=False)

    sampled = [(round(float(x), 3), round(float(y), 3)) for x, y in sampled]
    sampled.append(sampled[0])
    return sampled

def blend_local_section_loops(loop_a, loop_b, blend_ratio, target_count=48, allow_reverse=False):
    if not loop_a or not loop_b or len(loop_a) < 4 or len(loop_b) < 4:
        return []
    try:
        ratio = max(0.0, min(1.0, float(blend_ratio)))
    except Exception:
        ratio = 0.5

    pts_a = canonicalize_local_section_loop(loop_a)
    pts_b = canonicalize_local_section_loop(loop_b)
    if len(pts_a) < 4 or len(pts_b) < 4:
        return []

    samples_a = resample_closed_loop(pts_a, target_count=target_count)
    samples_b = resample_closed_loop(pts_b, target_count=target_count)
    if len(samples_a) < 8 or len(samples_b) < 8:
        return []
    samples_b = align_resampled_loop(samples_a, samples_b, allow_reverse=bool(allow_reverse))

    blended = []
    for (ax, ay), (bx, by) in zip(samples_a, samples_b):
        blended.append((
            ((1.0 - ratio) * float(ax)) + (ratio * float(bx)),
            ((1.0 - ratio) * float(ay)) + (ratio * float(by))
        ))
    try:
        blended_poly = largest_polygon(normalize_polygon(Polygon(blended + [blended[0]])), min_area=2.0)
    except Exception:
        blended_poly = None
    if blended_poly is not None and (not blended_poly.is_empty):
        blended = list(blended_poly.exterior.coords)
    blended = canonicalize_local_section_loop(blended + [blended[0]] if blended and blended[0] != blended[-1] else blended)
    if len(blended) < 4:
        return []
    blended = resample_closed_loop(blended, target_count=target_count)
    if len(blended) < 8:
        return []
    blended = [(round(float(x), 3), round(float(y), 3)) for x, y in blended]
    blended.append(blended[0])
    return blended

def interpolate_template_loop_for_station(template_sections, station_r, previous_loop=None):
    ordered_templates = sorted(
        [section for section in (template_sections or []) if isinstance(section, dict)],
        key=lambda section: float(section.get("station_r", 0.0))
    )
    if len(ordered_templates) < 2:
        return []
    try:
        station_r = float(station_r)
    except Exception:
        return []

    lower_section = ordered_templates[0]
    upper_section = ordered_templates[-1]
    for left_section, right_section in zip(ordered_templates[:-1], ordered_templates[1:]):
        left_r = float(left_section.get("station_r", 0.0))
        right_r = float(right_section.get("station_r", 0.0))
        if left_r <= station_r <= right_r:
            lower_section = left_section
            upper_section = right_section
            break
        if station_r < left_r:
            lower_section = left_section
            upper_section = right_section
            break

    lower_loop = lower_section.get("points_local_raw", []) or lower_section.get("points_local", [])
    upper_loop = upper_section.get("points_local_raw", []) or upper_section.get("points_local", [])
    if len(lower_loop) < 4 and len(upper_loop) < 4:
        return []
    if len(lower_loop) < 4:
        lower_loop = upper_loop
    if len(upper_loop) < 4:
        upper_loop = lower_loop

    lower_r = float(lower_section.get("station_r", 0.0))
    upper_r = float(upper_section.get("station_r", 0.0))
    if upper_r <= lower_r + 1e-6:
        blended_loop = canonicalize_local_section_loop(lower_loop)
    else:
        blend_ratio = (station_r - lower_r) / max(1e-6, upper_r - lower_r)
        blended_loop = blend_local_section_loops(lower_loop, upper_loop, blend_ratio)

    if previous_loop and len(previous_loop) >= 4 and len(blended_loop) >= 4:
        prev_ref = canonicalize_local_section_loop(previous_loop)
        blend_ref = canonicalize_local_section_loop(blended_loop)
        if len(prev_ref) >= 4 and len(blend_ref) >= 4:
            aligned = align_resampled_loop(
                [(float(x), float(y)) for x, y in prev_ref[:-1]],
                [(float(x), float(y)) for x, y in blend_ref[:-1]],
                allow_reverse=False
            )
            if len(aligned) >= 8:
                blended_loop = [(round(float(x), 3), round(float(y), 3)) for x, y in aligned]
                blended_loop.append(blended_loop[0])
    return blended_loop

def build_section_wire_stack_loft(section_wires, member_label, loft_tag, section_payloads=None):
    if not section_wires or len(section_wires) < 3:
        return None
    if not section_payloads or len(section_payloads) != len(section_wires):
        section_payloads = [None for _ in section_wires]

    def wire_bbox_metrics(wire):
        try:
            bb = wire.BoundingBox()
        except Exception:
            return None
        x_len = float(max(0.0, bb.xmax - bb.xmin))
        y_len = float(max(0.0, bb.ymax - bb.ymin))
        z_len = float(max(0.0, bb.zmax - bb.zmin))
        diag = math.sqrt(max(1e-9, (x_len * x_len) + (y_len * y_len) + (z_len * z_len)))
        return {{
            "x": x_len,
            "y": y_len,
            "z": z_len,
            "diag": diag
        }}

    def build_rescue_pair_body(wire_a, wire_b, payload_a, payload_b):
        if payload_a is None or payload_b is None:
            return None

        loop_a = payload_a.get("_loft_loop_points", []) if isinstance(payload_a, dict) else []
        loop_b = payload_b.get("_loft_loop_points", []) if isinstance(payload_b, dict) else []
        if len(loop_a) < 4 or len(loop_b) < 4:
            return None

        try:
            r_a = float((payload_a or {{}}).get("station_r", 0.0))
            r_b = float((payload_b or {{}}).get("station_r", 0.0))
        except Exception:
            return None

        if abs(r_b - r_a) < 1e-3:
            return None

        gap_r = abs(r_b - r_a)
        side_a = str((payload_a or {{}}).get("extension_side") or "")
        side_b = str((payload_b or {{}}).get("extension_side") or "")
        terminal_pair = (
            bool((payload_a or {{}}).get("terminal_contact")) or
            bool((payload_b or {{}}).get("terminal_contact")) or
            side_a.endswith("_terminal") or
            side_b.endswith("_terminal") or
            side_a.startswith("tip") or
            side_b.startswith("tip")
        )
        actual_slice_pair = (
            bool((payload_a or {{}}).get("_actual_slice_derived")) or
            bool((payload_b or {{}}).get("_actual_slice_derived")) or
            side_a.endswith("_actual") or
            side_b.endswith("_actual") or
            side_a == "actual_stack" or
            side_b == "actual_stack"
        )
        large_gap_pair = gap_r >= 4.0
        tip_bridge_pair = (
            terminal_pair or
            side_a.startswith("tip") or
            side_b.startswith("tip") or
            side_a.startswith("bridge") or
            side_b.startswith("bridge")
        )
        if not tip_bridge_pair and not large_gap_pair:
            return None

        # Allow rescue only when the failed pair already comes from real
        # actual-slice/terminal sections. This avoids planar cap fallbacks while
        # still letting two measured end sections bridge when direct loft fails.
        if (terminal_pair or side_a.startswith("tip") or side_b.startswith("tip")) and (not actual_slice_pair):
            return None

        tip_like_pair = side_a.startswith("tip") or side_b.startswith("tip")
        target_count = 88 if (terminal_pair or tip_like_pair or actual_slice_pair) else (64 if large_gap_pair else 56)
        if terminal_pair and actual_slice_pair:
            rescue_ratios = [0.2, 0.4, 0.6, 0.8] if gap_r > 1.2 else [0.25, 0.5, 0.75]
        elif terminal_pair or tip_like_pair or actual_slice_pair:
            rescue_ratios = [0.25, 0.5, 0.75] if gap_r > 1.8 else [0.5]
        elif large_gap_pair:
            rescue_ratios = [0.33, 0.67]
        else:
            rescue_ratios = [0.5] if gap_r <= 2.5 else [0.35, 0.65]
        rescue_wires = [wire_a]

        origin_a = list((payload_a or {{}}).get("plane_origin", []) or [])
        origin_b = list((payload_b or {{}}).get("plane_origin", []) or [])

        for ratio in rescue_ratios:
            bridge_loop = blend_local_section_loops(
                loop_a,
                loop_b,
                ratio,
                target_count=target_count,
                allow_reverse=bool(actual_slice_pair or terminal_pair)
            )
            if len(bridge_loop) < 8:
                print(
                    f"[!] {{member_label}} {{loft_tag}} pair rescue skipped invalid bridge loop "
                    f"(ext={{side_a}}->{{side_b}}, ratio={{float(ratio):.2f}})"
                )
                continue

            bridge_r = r_a + ((r_b - r_a) * float(ratio))
            bridge_xs = [float(x) for x, _ in bridge_loop[:-1]]
            bridge_payload = clone_local_section_profile(
                payload_b,
                bridge_r,
                target_center_x=((max(bridge_xs) + min(bridge_xs)) * 0.5) if bridge_xs else None,
                target_width=(max(bridge_xs) - min(bridge_xs)) if bridge_xs else None
            )
            if len(origin_a) >= 3 and len(origin_b) >= 3:
                bridge_payload["plane_origin"] = [
                    round(float(origin_a[axis]) + ((float(origin_b[axis]) - float(origin_a[axis])) * float(ratio)), 3)
                    for axis in range(3)
                ]
            if terminal_pair and actual_slice_pair:
                bridge_payload["extension_side"] = "pair_rescue_actual_terminal"
            elif terminal_pair:
                bridge_payload["extension_side"] = "pair_rescue_terminal"
            elif tip_bridge_pair:
                bridge_payload["extension_side"] = "pair_rescue_tip_bridge"
            else:
                bridge_payload["extension_side"] = "pair_rescue_gap"
            bridge_payload["terminal_contact"] = terminal_pair
            bridge_payload["preserve_detail"] = True
            if actual_slice_pair:
                bridge_payload["_actual_slice_derived"] = True
            bridge_payload["_loft_loop_points"] = bridge_loop

            bridge_wire = build_local_section_wire(bridge_payload, bridge_loop)
            if bridge_wire is not None:
                rescue_wires.append(bridge_wire)
            else:
                print(
                    f"[!] {{member_label}} {{loft_tag}} pair rescue bridge wire build failed "
                    f"(ext={{side_a}}->{{side_b}}, ratio={{float(ratio):.2f}})"
                )

        rescue_wires.append(wire_b)
        if len(rescue_wires) < 3:
            print(
                f"[!] {{member_label}} {{loft_tag}} pair rescue abandoned: "
                f"no intermediate bridge wires built (ext={{side_a}}->{{side_b}})"
            )
            return None

        try:
            rescue_solid = cq.Solid.makeLoft(rescue_wires, ruled=False)
            print(
                f"[*] {{member_label}} {{loft_tag}} pair rescue succeeded "
                f"(ext={{side_a}}->{{side_b}}, wires={{len(rescue_wires)}})"
            )
            return cq.Workplane("XY").newObject([rescue_solid])
        except Exception as rescue_exc:
            try:
                rescue_solid = cq.Solid.makeLoft(rescue_wires, ruled=True)
                print(
                    f"[*] {{member_label}} {{loft_tag}} pair rescue recovered with ruled loft "
                    f"(ext={{side_a}}->{{side_b}}, wires={{len(rescue_wires)}})"
                )
                return cq.Workplane("XY").newObject([rescue_solid])
            except Exception as ruled_rescue_exc:
                print(
                    f"[!] {{member_label}} pair rescue {{loft_tag}} failed: "
                    f"smooth={{rescue_exc}}; ruled={{ruled_rescue_exc}}; ext={{side_a}}->{{side_b}}"
                )
                return None

    filtered_wires = []
    filtered_metrics = []
    filtered_payloads = []
    for wire, payload in zip(section_wires, section_payloads):
        metrics = wire_bbox_metrics(wire)
        if metrics is None:
            continue
        if not filtered_wires:
            filtered_wires.append(wire)
            filtered_metrics.append(metrics)
            filtered_payloads.append(payload)
            continue
        prev = filtered_metrics[-1]
        jump_x = abs(metrics["x"] - prev["x"]) / max(1e-6, prev["x"])
        jump_y = abs(metrics["y"] - prev["y"]) / max(1e-6, prev["y"])
        jump_diag = abs(metrics["diag"] - prev["diag"]) / max(1e-6, prev["diag"])
        extension_side = str((payload or {{}}).get("extension_side") or "")
        preserve_terminal = (
            bool((payload or {{}}).get("terminal_contact")) or
            extension_side.endswith("_terminal") or
            extension_side.startswith("tip") or
            extension_side.startswith("root")
        )
        abrupt_shape_jump = (
            jump_x > 1.25 or
            jump_y > 1.25 or
            (jump_diag > 1.45 and (jump_x > 0.28 or jump_y > 0.28))
        )
        if abrupt_shape_jump:
            if preserve_terminal:
                print(
                    f"[*] {{member_label}} {{loft_tag}} preserved abrupt terminal section: "
                    f"dx={{jump_x:.2f}}, dy={{jump_y:.2f}}, dd={{jump_diag:.2f}}, ext={{extension_side}}"
                )
            else:
                print(
                    f"[!] {{member_label}} {{loft_tag}} skipped abrupt section: "
                    f"dx={{jump_x:.2f}}, dy={{jump_y:.2f}}, dd={{jump_diag:.2f}}"
                )
                continue
        filtered_wires.append(wire)
        filtered_metrics.append(metrics)
        filtered_payloads.append(payload)

    if len(filtered_wires) >= 3:
        section_wires = filtered_wires
        section_payloads = filtered_payloads

    wire_count = len(section_wires)
    if wire_count <= 8:
        try:
            loft_solid = cq.Solid.makeLoft(section_wires, ruled=False)
            print(
                f"[*] {{member_label}} {{loft_tag}} built as single multi-wire solid "
                f"(wires={{wire_count}})"
            )
            return cq.Workplane("XY").newObject([loft_solid])
        except Exception as multi_loft_exc:
            print(f"[!] {{member_label}} single multi-wire {{loft_tag}} failed: {{multi_loft_exc}}")
            try:
                loft_solid = cq.Solid.makeLoft(section_wires, ruled=True)
                print(
                    f"[*] {{member_label}} {{loft_tag}} built as single multi-wire ruled solid "
                    f"(wires={{wire_count}})"
                )
                return cq.Workplane("XY").newObject([loft_solid])
            except Exception as ruled_multi_loft_exc:
                print(f"[!] {{member_label}} single multi-wire ruled {{loft_tag}} failed: {{ruled_multi_loft_exc}}")

    loft_body = None
    for seg_idx, (wire_a, wire_b) in enumerate(zip(section_wires[:-1], section_wires[1:])):
        payload_a = section_payloads[seg_idx] if seg_idx < len(section_payloads) else None
        payload_b = section_payloads[seg_idx + 1] if (seg_idx + 1) < len(section_payloads) else None
        try:
            seg_solid = cq.Solid.makeLoft([wire_a, wire_b], ruled=False)
            seg_body = cq.Workplane("XY").newObject([seg_solid])
            if loft_body is None:
                loft_body = seg_body
            else:
                loft_body = safe_union(loft_body, seg_body, f"{{member_label}} {{loft_tag}} segment")
        except Exception as seg_loft_exc:
            try:
                seg_solid = cq.Solid.makeLoft([wire_a, wire_b], ruled=True)
                seg_body = cq.Workplane("XY").newObject([seg_solid])
                if loft_body is None:
                    loft_body = seg_body
                else:
                    loft_body = safe_union(loft_body, seg_body, f"{{member_label}} {{loft_tag}} segment ruled")
                print(f"[*] {{member_label}} pair segment {{loft_tag}} recovered with ruled loft")
            except Exception as ruled_seg_loft_exc:
                side_a = str((payload_a or {{}}).get("extension_side") or "")
                side_b = str((payload_b or {{}}).get("extension_side") or "")
                rescue_body = build_rescue_pair_body(wire_a, wire_b, payload_a, payload_b)
                if rescue_body is not None:
                    if loft_body is None:
                        loft_body = rescue_body
                    else:
                        loft_body = safe_union(loft_body, rescue_body, f"{{member_label}} {{loft_tag}} segment rescue")
                    continue
                print(
                    f"[!] {{member_label}} pair segment {{loft_tag}} failed: "
                    f"smooth={{seg_loft_exc}}; ruled={{ruled_seg_loft_exc}}; "
                    f"ext={{side_a}}->{{side_b}}"
                )
                continue

    return loft_body

def smooth_local_section_loop_sequence(section_entries, blend=0.58):
    if not section_entries or len(section_entries) < 5:
        return section_entries

    try:
        point_counts = [
            len((entry.get("loop_points", []) or [])[:-1] if len(entry.get("loop_points", []) or []) >= 5 else (entry.get("loop_points", []) or []))
            for entry in section_entries
            if isinstance(entry, dict)
        ]
    except Exception:
        point_counts = []
    point_counts = [count for count in point_counts if count >= 8]
    if not point_counts:
        return section_entries
    target_count = int(min(point_counts))
    if target_count < 8:
        return section_entries

    loop_arrays = []
    original_arrays = []
    payloads = []
    for entry in section_entries:
        if not isinstance(entry, dict):
            continue
        payload = entry.get("section_payload")
        loop_points = entry.get("loop_points", []) or []
        if len(loop_points) < 4:
            return section_entries
        sampled = resample_closed_loop(loop_points, target_count=target_count)
        if len(sampled) < 8:
            return section_entries
        if loop_arrays:
            sampled = align_resampled_loop(loop_arrays[-1], sampled, allow_reverse=False)
        sampled_arr = np.asarray(sampled, dtype=float)
        original_arrays.append(np.asarray(sampled, dtype=float))
        loop_arrays.append(sampled_arr)
        payloads.append(payload)

    if len(loop_arrays) < 5:
        return section_entries

    loop_stack = np.stack(loop_arrays, axis=0)
    original_stack = np.stack(original_arrays, axis=0)
    window = min(5, len(loop_arrays) if len(loop_arrays) % 2 == 1 else len(loop_arrays) - 1)
    if window < 3:
        return section_entries
    polyorder = 2 if window >= 5 else 1

    for pt_idx in range(loop_stack.shape[1]):
        for coord_idx in range(2):
            series = loop_stack[:, pt_idx, coord_idx]
            try:
                smooth_series = savgol_filter(series, window_length=window, polyorder=polyorder, mode="interp")
            except Exception:
                smooth_series = series
            loop_stack[:, pt_idx, coord_idx] = ((1.0 - float(blend)) * series) + (float(blend) * smooth_series)

    for entry_idx, payload in enumerate(payloads):
        extension_side = str((payload or {{}}).get("extension_side") or "")
        if entry_idx in (0, len(payloads) - 1) or extension_side.startswith("donor_") or extension_side == "bridge":
            loop_stack[entry_idx] = original_stack[entry_idx]

    smoothed_entries = []
    for entry_idx, payload in enumerate(payloads):
        loop_points = [
            (round(float(x), 3), round(float(y), 3))
            for x, y in loop_stack[entry_idx].tolist()
        ]
        loop_points.append(loop_points[0])
        smoothed_entries.append({{
            "section_payload": payload,
            "loop_points": loop_points
        }})
    return smoothed_entries

def prepare_actual_local_section_loop(section_payload, template_loop=None, previous_loop=None, target_count=36):
    pts_local = section_payload.get("points_local", []) or []
    if len(pts_local) < 4:
        return []

    try:
        local_poly = largest_polygon(normalize_polygon(Polygon(pts_local)), min_area=2.0)
    except Exception:
        local_poly = None

    if local_poly is not None and (not local_poly.is_empty):
        loop_points = list(local_poly.exterior.coords)
    else:
        loop_points = pts_local

    loop_points = canonicalize_local_section_loop(loop_points)
    if len(loop_points) < 4:
        return []

    extension_side = str(section_payload.get("extension_side") or "")
    actual_slice_derived = bool(section_payload.get("_actual_slice_derived"))
    terminal_contact = (
        bool(section_payload.get("terminal_contact")) or
        extension_side.endswith("_terminal") or
        extension_side.startswith("tip")
    )
    preserve_detail = bool(section_payload.get("preserve_detail")) or terminal_contact
    if actual_slice_derived:
        preserve_detail = True

    xs = [float(x) for x, _ in loop_points[:-1]]
    current_width = max(xs) - min(xs) if xs else 0.0
    current_center = ((max(xs) + min(xs)) * 0.5) if xs else 0.0
    try:
        target_width = float(section_payload.get("target_width", 0.0) or 0.0)
    except Exception:
        target_width = 0.0
    try:
        target_center = float(section_payload.get("target_center_x", current_center) or current_center)
    except Exception:
        target_center = current_center
    width_ratio = (current_width / max(1e-6, target_width)) if target_width > 1e-6 else 1.0
    center_error = abs(float(current_center) - float(target_center))

    if preserve_detail:
        should_stabilize = (
            width_ratio < 0.50 or width_ratio > 1.90 or
            center_error > max(6.0, target_width * 0.72)
        )
        should_rebuild = (
            len(loop_points) < 6 or
            width_ratio < 0.38 or width_ratio > 2.40 or
            center_error > max(8.0, target_width * 0.95)
        )
    else:
        should_stabilize = (
            len(loop_points) < 8 or
            width_ratio < 0.70 or width_ratio > 1.40 or
            center_error > max(3.6, target_width * 0.42)
        )
        should_rebuild = (
            len(loop_points) < 6 or
            width_ratio < 0.56 or width_ratio > 1.68 or
            center_error > max(5.0, target_width * 0.65)
        )

    actual_loop_bad = False
    try:
        local_poly_check = largest_polygon(normalize_polygon(Polygon(loop_points)), min_area=2.0)
        if local_poly_check is None or local_poly_check.is_empty:
            actual_loop_bad = True
        else:
            actual_loop_bad = (not local_poly_check.is_valid) or (float(local_poly_check.area) < 4.0)
    except Exception:
        actual_loop_bad = True

    if actual_slice_derived:
        should_stabilize = bool(
            actual_loop_bad or
            len(loop_points) < 10 or
            width_ratio < 0.58 or width_ratio > 1.45 or
            center_error > max(4.4, target_width * 0.54)
        )
        should_rebuild = bool(
            actual_loop_bad or
            len(loop_points) < 8 or
            width_ratio < 0.46 or width_ratio > 1.78 or
            center_error > max(6.0, target_width * 0.72)
        )

    if should_stabilize:
        loop_points = stabilize_local_section_loop(section_payload, loop_points)
        loop_points = canonicalize_local_section_loop(loop_points)
    if should_rebuild:
        loop_points = rebuild_local_section_loop_from_y_samples(loop_points)
        loop_points = canonicalize_local_section_loop(loop_points)
    if len(loop_points) < 4:
        return []

    sampled_target = int(target_count)
    if actual_slice_derived or terminal_contact:
        sampled_target = max(sampled_target, 72)
    elif preserve_detail:
        sampled_target = max(sampled_target, 56)
    sampled = resample_closed_loop(loop_points, target_count=sampled_target)
    if len(sampled) < 8:
        return []

    if template_loop and len(template_loop) >= 4:
        template_ref = canonicalize_local_section_loop(template_loop)
        if len(template_ref) >= 4:
            template_ref = [(float(x), float(y)) for x, y in template_ref[:-1]]
            sampled = align_resampled_loop(
                template_ref,
                sampled,
                allow_reverse=bool(actual_slice_derived or terminal_contact)
            )

    if previous_loop and len(previous_loop) >= 4:
        prev_ref = canonicalize_local_section_loop(previous_loop)
        if len(prev_ref) >= 4:
            prev_ref = [(float(x), float(y)) for x, y in prev_ref[:-1]]
            sampled = align_resampled_loop(
                prev_ref,
                sampled,
                allow_reverse=bool(actual_slice_derived or terminal_contact)
            )

    sampled = [(round(float(x), 3), round(float(y), 3)) for x, y in sampled]
    sampled.append(sampled[0])
    return sampled

def build_member_actual_local_section_loft_spoke(member_payload, template_payload, member_label):
    print(f"[*] entering pure actual local-section build: {{member_label}}")
    combined_sections = []
    for source_name, raw_sections in (
        ("body", member_payload.get("sections", []) or []),
        ("tip", member_payload.get("tip_sections", []) or []),
    ):
        for section in raw_sections:
            if not isinstance(section, dict):
                continue
            cloned = dict(section)
            cloned["_actual_section_source"] = source_name
            if source_name == "tip" and not str(cloned.get("extension_side") or ""):
                cloned["extension_side"] = "tip_actual"
            if source_name == "tip":
                cloned["terminal_contact"] = True
                cloned["preserve_detail"] = True
            combined_sections.append(cloned)

    ordered_sections = sorted(
        [
            section for section in combined_sections
            if isinstance(section, dict) and float(section.get("station_r", 0.0)) > 0.0
        ],
        key=lambda section: float(section.get("station_r", 0.0))
    )
    if len(ordered_sections) < 3:
        return None

    body_ordered_sections = sorted(
        [
            section for section in (member_payload.get("sections", []) or [])
            if isinstance(section, dict) and float(section.get("station_r", 0.0)) > 0.0
        ],
        key=lambda section: float(section.get("station_r", 0.0))
    )
    tip_ordered_sections = sorted(
        [
            section for section in (member_payload.get("tip_sections", []) or [])
            if isinstance(section, dict) and float(section.get("station_r", 0.0)) > 0.0
        ],
        key=lambda section: float(section.get("station_r", 0.0))
    )

    working_sections = list(ordered_sections)
    actual_z_profiles = sorted(
        [profile for profile in (member_payload.get("actual_z_profiles", []) or []) if isinstance(profile, dict)],
        key=lambda profile: float(profile.get("z", 0.0))
    )
    member_angle_deg = float(member_payload.get("angle", 0.0))
    member_index = member_payload.get("member_index")
    actual_root_ext_count = len([
        section for section in ordered_sections
        if str(section.get("extension_side") or "") == "root"
    ])
    actual_tip_ext_count = len([
        section for section in ordered_sections
        if (
            str(section.get("extension_side") or "").startswith("tip")
            or str(section.get("_actual_section_source") or "") == "tip"
        )
    ])
    working_root_ext_count = actual_root_ext_count
    working_tip_ext_count = actual_tip_ext_count
    disable_donor_root_actual = bool(member_payload.get("_disable_donor_root_actual"))
    disable_donor_tip_actual = bool(member_payload.get("_disable_donor_tip_actual"))
    disable_actual_body_fill = bool(member_payload.get("_disable_actual_body_fill"))

    def derive_actual_profile_extension(target_r, anchor_payload, extension_side):
        if len(actual_z_profiles) < 4:
            return None
        try:
            target_r = float(target_r)
        except Exception:
            return None

        samples = []

        def collect_y_values(geom, y_values):
            if geom is None or geom.is_empty:
                return
            if isinstance(geom, Point):
                y_values.append(float(geom.y))
                return
            if isinstance(geom, LineString):
                for _, y_val in list(geom.coords):
                    y_values.append(float(y_val))
                return
            if isinstance(geom, MultiLineString):
                for sub_geom in geom.geoms:
                    collect_y_values(sub_geom, y_values)
                return
            if isinstance(geom, GeometryCollection):
                for sub_geom in geom.geoms:
                    collect_y_values(sub_geom, y_values)
                return
            if hasattr(geom, "geoms"):
                for sub_geom in geom.geoms:
                    collect_y_values(sub_geom, y_values)

        for profile in actual_z_profiles:
            world_loop = profile.get("points", []) if isinstance(profile, dict) else []
            if len(world_loop) < 4:
                continue
            local_loop = world_loop_to_member_local(world_loop, member_angle_deg)
            if len(local_loop) < 4:
                continue
            try:
                local_poly = largest_polygon(normalize_polygon(Polygon(local_loop)), min_area=8.0)
            except Exception:
                local_poly = None
            if local_poly is None or local_poly.is_empty:
                continue
            coords = list(local_poly.exterior.coords)
            if len(coords) < 4:
                continue
            radial_vals = [float(x_val) for x_val, _ in coords[:-1]]
            tangential_vals = [float(y_val) for _, y_val in coords[:-1]]
            if not radial_vals or not tangential_vals:
                continue
            if target_r < min(radial_vals) - 0.45 or target_r > max(radial_vals) + 0.45:
                continue
            probe = LineString([
                (float(target_r), min(tangential_vals) - 2.0),
                (float(target_r), max(tangential_vals) + 2.0)
            ])
            hit = local_poly.intersection(probe)
            y_values = []
            collect_y_values(hit, y_values)
            if len(y_values) < 2:
                continue
            try:
                z_val = float(profile.get("z", 0.0))
            except Exception:
                continue
            samples.append((z_val, min(y_values), max(y_values)))

        if len(samples) < 4:
            return None

        samples.sort(key=lambda item: item[0])
        base_z = float(samples[0][0])
        left_points = []
        right_points = []
        for z_val, y_min, y_max in samples:
            local_z = round(float(z_val) - base_z, 3)
            left_points.append((round(float(y_min), 3), local_z))
            right_points.append((round(float(y_max), 3), local_z))

        loop_points = left_points + list(reversed(right_points))
        if len(loop_points) < 6:
            return None
        if loop_points[0] != loop_points[-1]:
            loop_points.append(loop_points[0])
        loop_points = canonicalize_local_section_loop(loop_points)
        if len(loop_points) < 4:
            return None
        sampled_loop = resample_closed_loop(loop_points, target_count=48)
        if len(sampled_loop) < 8:
            return None
        sampled_loop = [(round(float(x), 3), round(float(y), 3)) for x, y in sampled_loop]
        sampled_loop.append(sampled_loop[0])
        xs = [float(x) for x, _ in sampled_loop[:-1]]
        ys = [float(y) for _, y in sampled_loop[:-1]]
        donor_tip_extension = str(extension_side or "").startswith("donor_tip")
        donor_root_extension = str(extension_side or "").startswith("donor_root")
        donor_terminal_extension = donor_tip_extension or donor_root_extension
        if donor_terminal_extension and xs:
            anchor_stats = measure_local_loop_stats(anchor_payload)
            if anchor_stats is not None:
                sampled_center = ((max(xs) + min(xs)) * 0.5) if xs else 0.0
                sampled_width = (max(xs) - min(xs)) if xs else 0.0
                anchor_center = float(anchor_stats["center_x"])
                anchor_width = max(1.0, float(anchor_stats["width"]))
                target_width = min(sampled_width, max(anchor_width * 1.08, anchor_width + 0.8))
                center_limit = max(2.2, anchor_width * 0.16)
                width_scale = min(1.0, target_width / max(1e-6, sampled_width))
                if sampled_center > anchor_center + center_limit:
                    target_center = anchor_center + center_limit
                elif sampled_center < anchor_center - center_limit:
                    target_center = anchor_center - center_limit
                else:
                    target_center = sampled_center
                center_shift = float(target_center) - float(sampled_center)
                if width_scale < 0.995 or width_scale > 1.005 or abs(center_shift) > 0.15:
                    clamped_loop = []
                    for x_val, y_val in sampled_loop[:-1]:
                        mapped_x = float(target_center) + ((float(x_val) - float(sampled_center)) * float(width_scale))
                        clamped_loop.append((round(mapped_x, 3), round(float(y_val), 3)))
                    if clamped_loop:
                        clamped_loop.append(clamped_loop[0])
                        sampled_loop = canonicalize_local_section_loop(clamped_loop)
                        if len(sampled_loop) >= 4:
                            xs = [float(x) for x, _ in sampled_loop[:-1]]
                            ys = [float(y) for _, y in sampled_loop[:-1]]
        cloned = clone_local_section_profile(
            anchor_payload,
            float(target_r),
            target_center_x=((max(xs) + min(xs)) * 0.5) if xs else None,
            target_width=(max(xs) - min(xs)) if xs else None
        )
        plane_origin = list(cloned.get("plane_origin", []))
        if len(plane_origin) >= 3:
            plane_origin[2] = round(base_z, 3)
            cloned["plane_origin"] = plane_origin
        cloned["extension_side"] = extension_side
        cloned["template_loop_override"] = sampled_loop
        cloned["points_local"] = sampled_loop
        cloned["points_local_raw"] = sampled_loop
        cloned["_actual_slice_derived"] = True
        cloned["preserve_detail"] = True
        if (
            str(extension_side or "").startswith("root") or
            str(extension_side or "").startswith("tip") or
            "donor_root" in str(extension_side or "") or
            "donor_tip" in str(extension_side or "")
        ):
            cloned["terminal_contact"] = True
        if ys:
            cloned["local_height"] = round(max(ys) - min(ys), 3)
        cloned["target_z_band"] = [round(float(samples[0][0]), 3), round(float(samples[-1][0]), 3)]
        return cloned

    def measure_local_loop_stats(section_payload):
        loop_pts = section_payload.get("points_local", []) or []
        if len(loop_pts) < 4:
            return None
        pts = loop_pts[:-1] if len(loop_pts) >= 5 else loop_pts
        if len(pts) < 3:
            return None
        xs = [float(x) for x, _ in pts]
        ys = [float(y) for _, y in pts]
        if not xs or not ys:
            return None
        return {{
            "center_x": (max(xs) + min(xs)) * 0.5,
            "width": max(0.8, max(xs) - min(xs)),
            "height": max(0.8, max(ys) - min(ys))
        }}

    def accepts_actual_override(anchor_payload, derived_payload):
        anchor_stats = measure_local_loop_stats(anchor_payload)
        derived_stats = measure_local_loop_stats(derived_payload)
        if anchor_stats is None or derived_stats is None:
            return False
        derived_terminal = (
            bool(derived_payload.get("terminal_contact")) or
            bool(derived_payload.get("_actual_slice_derived")) or
            str(derived_payload.get("extension_side") or "").startswith("donor_") or
            str(derived_payload.get("extension_side") or "").endswith("_terminal") or
            str(derived_payload.get("extension_side") or "").startswith("tip")
        )
        width_ratio = float(derived_stats["width"]) / max(0.8, float(anchor_stats["width"]))
        height_ratio = float(derived_stats["height"]) / max(0.8, float(anchor_stats["height"]))
        center_shift = abs(float(derived_stats["center_x"]) - float(anchor_stats["center_x"]))
        width_min = 0.34 if derived_terminal else 0.40
        width_max = 2.25 if derived_terminal else 1.95
        height_min = 0.28 if derived_terminal else 0.34
        height_max = 2.60 if derived_terminal else 2.25
        center_limit = max(6.6, float(anchor_stats["width"]) * 1.05) if derived_terminal else max(5.0, float(anchor_stats["width"]) * 0.82)
        if width_ratio < width_min or width_ratio > width_max:
            return False
        if height_ratio < height_min or height_ratio > height_max:
            return False
        if center_shift > center_limit:
            return False
        return True

    # Replace measured section loops with profiles reconstructed from actual XY@Z slices.
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

    if len(actual_z_profiles) >= 4:
        first_actual = body_ordered_sections[0] if body_ordered_sections else ordered_sections[0]
        last_actual = body_ordered_sections[-1] if body_ordered_sections else ordered_sections[-1]
        first_actual_r = float(first_actual.get("station_r", 0.0))
        last_actual_r = float(last_actual.get("station_r", 0.0))

        if working_root_ext_count < 2 and (not disable_donor_root_actual):
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
                    if (
                        derived_section is not None and
                        accepts_actual_override(first_actual, derived_section)
                    ):
                        injected_actual_root.append(derived_section)
                if injected_actual_root:
                    working_sections = injected_actual_root + working_sections
                    working_root_ext_count += len(injected_actual_root)
                    print(
                        f"[*] {{member_label}} injected donor_root_actual: "
                        f"count={{len(injected_actual_root)}}, "
                        f"R={{float(injected_actual_root[0].get('station_r', 0.0)):.2f}}->"
                        f"{{float(injected_actual_root[-1].get('station_r', 0.0)):.2f}}"
                    )

        skip_donor_tip_injection = (
            len(tip_ordered_sections) >= 2 and
            working_root_ext_count <= 4 and
            len(actual_z_profiles) >= 40
        )
        if skip_donor_tip_injection:
            print(
                f"[*] {{member_label}} skipped donor_tip_actual injection: "
                f"tip_sections={{len(tip_ordered_sections)}}, "
                f"root_ext={{working_root_ext_count}}, actual_z={{len(actual_z_profiles)}}"
            )
        if (
            (tip_ordered_sections or working_tip_ext_count < 2) and
            (not skip_donor_tip_injection) and
            (not disable_donor_tip_actual)
        ):
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
                    if (
                        derived_section is not None and
                        accepts_actual_override(last_actual, derived_section)
                    ):
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
                        f"[*] {{member_label}} injected donor_tip_actual: "
                        f"count={{len(injected_actual_tip)}}, "
                        f"R={{float(injected_actual_tip[0].get('station_r', 0.0)):.2f}}->"
                        f"{{float(injected_actual_tip[-1].get('station_r', 0.0)):.2f}}, "
                        f"trimmed_tip_outer={{donor_tip_outer_r:.2f}}"
                    )

        working_sections = sorted(
            [section for section in working_sections if isinstance(section, dict)],
            key=lambda section: float(section.get("station_r", 0.0))
        )

        if len(working_sections) >= 2 and (not disable_actual_body_fill):
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
                    f"[*] {{member_label}} injected actual body fill sections: "
                    f"count={{inserted_actual_body_count}}, sections={{len(working_sections)}}"
                )

        heavy_rootless_actual_fill = (
            working_root_ext_count <= 0 and
            len(actual_z_profiles) >= 40 and
            len(working_sections) >= 30
        )
        heavy_low_root_actual_fill = (
            working_root_ext_count > 0 and
            working_root_ext_count <= 4 and
            len(actual_z_profiles) >= 40 and
            len(working_sections) >= 34
        )
        if heavy_rootless_actual_fill or heavy_low_root_actual_fill:
            actual_body_fill_sections = []
            retained_sections = []
            for section in working_sections:
                extension_side = str(section.get("extension_side") or "")
                if extension_side == "actual_body_fill":
                    actual_body_fill_sections.append(section)
                else:
                    retained_sections.append(section)
            if len(actual_body_fill_sections) >= 8:
                keep_fill_count = max(4, min(6, int(math.ceil(len(actual_body_fill_sections) * 0.5))))
                keep_indices = sorted({{
                    max(0, min(len(actual_body_fill_sections) - 1, int(round(val))))
                    for val in np.linspace(0, len(actual_body_fill_sections) - 1, keep_fill_count)
                }})
                trimmed_fill_sections = [actual_body_fill_sections[idx] for idx in keep_indices]
                working_sections = sorted(
                    retained_sections + trimmed_fill_sections,
                    key=lambda section: float(section.get("station_r", 0.0))
                )
                trim_label = "rootless" if heavy_rootless_actual_fill else "low-root"
                print(
                    f"[*] {{member_label}} trimmed heavy {{trim_label}} actual body fill: "
                    f"kept={{len(trimmed_fill_sections)}}/{{len(actual_body_fill_sections)}}, "
                    f"sections={{len(working_sections)}}"
                )

    deduped_sections = []
    collapsed_count = 0
    for section in working_sections:
        if not deduped_sections:
            deduped_sections.append(section)
            continue

        prev_section = deduped_sections[-1]
        try:
            prev_r = float(prev_section.get("station_r", 0.0))
            curr_r = float(section.get("station_r", 0.0))
        except Exception:
            deduped_sections.append(section)
            continue

        prev_side = str(prev_section.get("extension_side") or "")
        curr_side = str(section.get("extension_side") or "")
        prev_terminal = (
            bool(prev_section.get("terminal_contact")) or
            prev_side.endswith("_terminal") or
            prev_side.startswith("tip")
        )
        curr_terminal = (
            bool(section.get("terminal_contact")) or
            curr_side.endswith("_terminal") or
            curr_side.startswith("tip")
        )
        near_duplicate = abs(curr_r - prev_r) <= (0.55 if (prev_terminal or curr_terminal) else 0.25)
        side_compatible = (
            prev_side == curr_side or
            (prev_terminal and curr_terminal) or
            (prev_side.startswith("tip") and curr_side.startswith("tip")) or
            (
                (bool(prev_section.get("_actual_slice_derived")) or bool(section.get("_actual_slice_derived"))) and
                (prev_terminal or curr_terminal or prev_side.startswith("donor_tip") or curr_side.startswith("donor_tip"))
            )
        )
        if near_duplicate and side_compatible:
            prev_pts = prev_section.get("points_local", []) or prev_section.get("points_local_raw", []) or []
            curr_pts = section.get("points_local", []) or section.get("points_local_raw", []) or []
            prev_actual = bool(prev_section.get("_actual_slice_derived"))
            curr_actual = bool(section.get("_actual_slice_derived"))
            prefer_current = (
                (curr_actual and (not prev_actual)) or
                curr_terminal or
                (len(curr_pts) > len(prev_pts)) or
                (curr_r >= prev_r)
            )
            if prefer_current:
                deduped_sections[-1] = section
            collapsed_count += 1
            continue

        deduped_sections.append(section)

    if collapsed_count:
        print(f"[*] {{member_label}} pure actual local-section collapsed near-duplicate sections: {{collapsed_count}}")
    working_sections = deduped_sections

    print(
        f"[*] {{member_label}} pure actual local-section input: "
        f"sections={{len(working_sections)}}, body={{len(member_payload.get('sections', []) or [])}}, "
        f"tip={{len(member_payload.get('tip_sections', []) or [])}}, "
        f"actual_z={{len(actual_z_profiles)}}, overrides={{actual_override_count}}"
    )

    section_loop_entries = []
    previous_loop = None
    previous_payload = None

    for section_payload in working_sections:
        loop_points = prepare_actual_local_section_loop(
            section_payload,
            template_loop=None,
            previous_loop=previous_loop,
            target_count=(
                72 if (
                    bool(section_payload.get("_actual_slice_derived")) or
                    bool(section_payload.get("terminal_contact")) or
                    str(section_payload.get("extension_side") or "").startswith("tip") or
                    str(section_payload.get("extension_side") or "").endswith("_terminal")
                ) else (
                    56 if (bool(section_payload.get("preserve_detail")) or str(section_payload.get("extension_side") or "").endswith("_terminal")) else 36
                )
            )
        )
        if len(loop_points) < 4:
            continue

        if previous_loop is not None and previous_payload is not None:
            try:
                prev_r = float(previous_payload.get("station_r", 0.0))
                curr_r = float(section_payload.get("station_r", 0.0))
            except Exception:
                prev_r = 0.0
                curr_r = 0.0
            gap_r = curr_r - prev_r
            prev_side = str(previous_payload.get("extension_side") or "")
            curr_side = str(section_payload.get("extension_side") or "")
            prev_terminal = (
                bool(previous_payload.get("terminal_contact")) or
                prev_side.endswith("_terminal") or
                prev_side.startswith("tip")
            )
            curr_terminal = (
                bool(section_payload.get("terminal_contact")) or
                curr_side.endswith("_terminal") or
                curr_side.startswith("tip")
            )
            prev_root_like = (
                prev_side == "root" or
                prev_side.startswith("donor_root")
            )
            curr_root_like = (
                curr_side == "root" or
                curr_side.startswith("donor_root")
            )
            prev_actual_like = (
                bool(previous_payload.get("_actual_slice_derived")) or
                prev_side == "actual_stack" or
                prev_side == "actual_body_fill"
            )
            curr_actual_like = (
                bool(section_payload.get("_actual_slice_derived")) or
                curr_side == "actual_stack" or
                curr_side == "actual_body_fill"
            )
            tip_transition = prev_side.startswith("tip") != curr_side.startswith("tip")
            prev_stats = measure_local_loop_stats(previous_payload)
            curr_stats = measure_local_loop_stats(section_payload)
            width_ratio = None
            center_shift = None
            if prev_stats is not None and curr_stats is not None:
                width_ratio = max(
                    float(prev_stats["width"]),
                    float(curr_stats["width"])
                ) / max(
                    0.8,
                    min(float(prev_stats["width"]), float(curr_stats["width"]))
                )
                center_shift = abs(float(prev_stats["center_x"]) - float(curr_stats["center_x"]))
            root_first_actual_transition = (
                (not tip_transition) and
                prev_side.startswith("donor_root_actual") and
                curr_side == "actual_stack" and
                gap_r >= 3.4 and
                gap_r <= 6.4 and
                (prev_terminal or curr_terminal) and
                prev_root_like and
                curr_actual_like and
                (not curr_root_like) and
                width_ratio is not None and
                width_ratio <= 1.62 and
                center_shift is not None and
                center_shift <= 2.8
            )
            if root_first_actual_transition:
                bridge_ratio = 0.33
                bridge_loop = blend_local_section_loops(
                    previous_loop,
                    loop_points,
                    bridge_ratio,
                    target_count=56,
                    allow_reverse=False
                )
                if len(bridge_loop) >= 8:
                    bridge_r = prev_r + ((curr_r - prev_r) * bridge_ratio)
                    bridge_xs = [float(x) for x, _ in bridge_loop[:-1]]
                    bridge_payload = clone_local_section_profile(
                        section_payload,
                        bridge_r,
                        target_center_x=((max(bridge_xs) + min(bridge_xs)) * 0.5) if bridge_xs else None,
                        target_width=(max(bridge_xs) - min(bridge_xs)) if bridge_xs else None
                    )
                    origin_a = list(previous_payload.get("plane_origin", []) or [])
                    origin_b = list(section_payload.get("plane_origin", []) or [])
                    if len(origin_a) >= 3 and len(origin_b) >= 3:
                        bridge_payload["plane_origin"] = [
                            round(float(origin_a[axis]) + ((float(origin_b[axis]) - float(origin_a[axis])) * float(bridge_ratio)), 3)
                            for axis in range(3)
                        ]
                    bridge_payload["extension_side"] = "bridge_root_actual"
                    bridge_payload["terminal_contact"] = True
                    bridge_payload["preserve_detail"] = True
                    bridge_payload["_actual_slice_derived"] = True
                    bridge_loop = stabilize_local_section_loop(bridge_payload, bridge_loop)
                    bridge_loop = rebuild_local_section_loop_from_y_samples(bridge_loop, sample_count=13)
                    bridge_loop = canonicalize_local_section_loop(bridge_loop)
                    if len(bridge_loop) < 8:
                        continue
                    bridge_xs = [float(x) for x, _ in bridge_loop[:-1]]
                    if bridge_xs:
                        bridge_payload["target_center_x"] = (max(bridge_xs) + min(bridge_xs)) * 0.5
                        bridge_payload["target_width"] = max(bridge_xs) - min(bridge_xs)
                    bridge_payload["template_loop_override"] = bridge_loop
                    bridge_payload["points_local"] = bridge_loop
                    bridge_payload["points_local_raw"] = bridge_loop
                    bridge_payload["_loft_loop_points"] = bridge_loop
                    bridge_ok = (
                        accepts_actual_override(previous_payload, bridge_payload) and
                        accepts_actual_override(section_payload, bridge_payload)
                    )
                    if bridge_ok:
                        section_loop_entries.append({{
                            "section_payload": bridge_payload,
                            "loop_points": bridge_loop
                        }})
                        print(
                            f"[*] {{member_label}} inserted root-first_actual bridge: "
                            f"R={{bridge_r:.2f}}, gap={{gap_r:.2f}}, ext={{prev_side}}->{{curr_side}}"
                        )

        section_payload = dict(section_payload)
        section_payload["_loft_loop_points"] = loop_points
        section_loop_entries.append({{
            "section_payload": section_payload,
            "loop_points": loop_points
        }})
        previous_loop = loop_points
        previous_payload = section_payload

    if len(section_loop_entries) < 3:
        return None

    # Preserve measured section detail for strict slice-to-loft restoration.
    # Sequence smoothing washed out the single-spoke closeup in retryai.
    strict_slice_loft_mode = True
    if not strict_slice_loft_mode:
        section_loop_entries = smooth_local_section_loop_sequence(section_loop_entries)

    section_wires = []
    section_wire_payloads = []
    for loop_entry in section_loop_entries:
        section_payload = loop_entry.get("section_payload")
        loop_points = loop_entry.get("loop_points", []) or []
        wire = build_local_section_wire(section_payload, loop_points)
        if wire is None:
            continue
        section_wires.append(wire)
        section_wire_payloads.append(section_payload)

    if len(section_wires) < 3:
        return None

    try:
        loft_body = build_section_wire_stack_loft(
            section_wires,
            member_label,
            "pure actual local-section loft",
            section_payloads=section_wire_payloads
        )
        if loft_body is None:
            return None
        # Keep the dominant 1-2 fragments so strict additive merge still has a
        # chance to attach true terminal contact, but do not let noisy fragment
        # clouds bypass the single-body pipeline as a direct compound.
        try:
            cleaned = loft_body.clean()
            if body_has_valid_shape(cleaned):
                loft_body = cleaned
        except Exception:
            pass
        loft_body = retain_significant_member_fragments(
            loft_body,
            f"{{member_label}} pure actual local-section loft",
            max_solids=2
        )
        try:
            cleaned = loft_body.clean()
            if body_has_valid_shape(cleaned):
                loft_body = cleaned
        except Exception:
            pass
        return loft_body
    except Exception as exc:
        print(f"[!] {{member_label}} pure actual local-section loft failed: {{exc}}")
        return None

def build_member_canonical_section_loft_spoke(member_payload, template_payload, member_label):
    template_sections = template_payload.get("section_templates", []) if isinstance(template_payload, dict) else []
    if len(template_sections) < 3:
        return None

    member_sections = sorted(
        [section for section in (member_payload.get("sections", []) or []) if isinstance(section, dict)],
        key=lambda section: float(section.get("station_r", 0.0))
    )
    if len(member_sections) < 3:
        return None

    loft_sections = []
    previous_loop = None
    for section_payload in member_sections:
        template_loop = interpolate_template_loop_for_station(
            template_sections,
            section_payload.get("station_r", 0.0),
            previous_loop=previous_loop
        )
        loop_points = transplant_local_section_loop_to_section_payload(
            section_payload,
            template_loop,
            previous_loop=previous_loop
        )
        if len(loop_points) < 4:
            continue
        loft_sections.append((section_payload, loop_points))
        previous_loop = loop_points

    if len(loft_sections) < 3:
        return None

    section_wires = []
    for section_payload, loop_points in loft_sections:
        wire = build_local_section_wire(section_payload, loop_points)
        if wire is None:
            continue
        section_wires.append(wire)

    if len(section_wires) < 3:
        return None

    try:
        loft_body = build_section_wire_stack_loft(section_wires, member_label, "canonical local-section loft")
        if loft_body is None:
            return None
        return finalize_member_body(
            loft_body,
            f"{{member_label}} canonical local-section loft final"
        )
    except Exception as exc:
        print(f"[!] {{member_label}} canonical local-section loft failed: {{exc}}")
        return None

def derive_member_vertical_limits(member_payload):
    z_values = []
    for section in member_payload.get("sections", []) or []:
        plane_origin = section.get("plane_origin", []) or []
        pts_local = section.get("points_local", []) or []
        if len(plane_origin) < 3 or len(pts_local) < 4:
            continue
        base_z = float(plane_origin[2])
        samples = pts_local[:-1] if len(pts_local) >= 5 else pts_local
        for _, local_z in samples:
            z_values.append(base_z + float(local_z))
    if len(z_values) >= 6:
        z_arr = np.asarray(z_values, dtype=float)
        lower = float(np.percentile(z_arr, 8.0))
        upper = float(np.percentile(z_arr, 92.0))
        if upper > lower + 1.0:
            return lower, upper
        return float(np.min(z_arr)), float(np.max(z_arr))
    fallback_bottom = hub_z_val - 0.5
    fallback_top = max(
        spoke_face_z + 0.8,
        float(params.get("hub_face_z", hub_z_val + 8.0)) + 0.4
    )
    return fallback_bottom, fallback_top

def build_dual_split_member_payloads(member_payload):
    body_sections = sorted(
        [
            dict(section) for section in (member_payload.get("sections", []) or [])
            if isinstance(section, dict) and float(section.get("station_r", 0.0)) > 0.0
        ],
        key=lambda section: float(section.get("station_r", 0.0))
    )
    tip_sections = sorted(
        [
            dict(section) for section in (member_payload.get("tip_sections", []) or [])
            if isinstance(section, dict) and float(section.get("station_r", 0.0)) > 0.0
        ],
        key=lambda section: float(section.get("station_r", 0.0))
    )
    actual_z_profiles = member_payload.get("actual_z_profiles", []) or []
    actual_root_ext_count = len([
        section for section in body_sections
        if str(section.get("extension_side") or "") == "root"
    ])
    if len(body_sections) < 10 or len(tip_sections) < 2 or len(actual_z_profiles) < 40:
        return []

    first_r = float(body_sections[0].get("station_r", 0.0))
    last_r = float(body_sections[-1].get("station_r", 0.0))
    radius_span = last_r - first_r
    if radius_span < 72.0:
        return []

    tip_start_r = float(tip_sections[0].get("station_r", last_r))
    split_floor = first_r + (radius_span * 0.45)
    split_cap = last_r - 12.0
    split_r = max(split_floor, tip_start_r - 18.0)
    split_r = min(split_cap, split_r)
    overlap_r = max(6.0, min(10.0, radius_span * 0.07))

    inner_sections = [
        dict(section)
        for section in body_sections
        if float(section.get("station_r", 0.0)) <= split_r + overlap_r
    ]
    outer_sections = [
        dict(section)
        for section in body_sections
        if float(section.get("station_r", 0.0)) >= split_r - overlap_r
    ]
    outer_tip_sections = [
        dict(section)
        for section in tip_sections
        if float(section.get("station_r", 0.0)) >= split_r - overlap_r
    ]

    if len(inner_sections) < 4 or (len(outer_sections) + len(outer_tip_sections)) < 4:
        return []

    inner_payload = dict(member_payload)
    inner_payload["sections"] = inner_sections
    inner_payload["tip_sections"] = []
    inner_payload["_disable_donor_tip_actual"] = True
    inner_payload["_dual_split_role"] = "inner"
    inner_payload["_dual_split_r"] = split_r

    outer_payload = dict(member_payload)
    outer_payload["sections"] = outer_sections
    outer_payload["tip_sections"] = outer_tip_sections
    outer_payload["_disable_donor_root_actual"] = True
    outer_payload["_dual_split_role"] = "outer"
    outer_payload["_dual_split_r"] = split_r

    # Only keep the dual-split route when the member can produce a real
    # inner segment for the hub side. Outer-only "splits" add expensive
    # boolean work but do not improve attachment stability.
    if actual_root_ext_count <= 0:
        return []

    return [
        ("outer", outer_payload),
        ("inner", inner_payload),
    ]

def build_spokeless_spoke_members(motif_payloads):
    member_bodies = []
    failed_members = []
    expected_member_count = 0
    for motif_payload in motif_payloads or []:
        motif_index = motif_payload.get("motif_index", "?")
        for member_payload in motif_payload.get("members", []) or []:
            expected_member_count += 1
            member_index = member_payload.get("member_index", "?")
            member_body = build_motif_member_spoke(member_payload, motif_payload)
            if member_body is None:
                print(f"[!] motif {{motif_index}} member {{member_index}} discarded: pure actual-slice loft only")
                failed_members.append(int(member_index) if str(member_index).isdigit() else member_index)
                continue
            # Keep all valid spoke fragments here. They are merged fragment-by-fragment
            # into hub/rim later, and truncating to the largest solid discards exactly
            # the terminal contact pieces we are trying to preserve.
            try:
                cleaned_member_body = member_body.clean()
                if body_has_valid_shape(cleaned_member_body):
                    member_body = cleaned_member_body
            except Exception:
                pass
            if not body_has_valid_shape(member_body):
                failed_members.append(int(member_index) if str(member_index).isdigit() else member_index)
                continue
            member_bodies.append((
                f"motif_{{motif_index}}_member_{{member_index}}",
                member_body,
                member_payload,
                motif_payload
            ))
    if failed_members or len(member_bodies) != expected_member_count:
        raise ValueError(
            f"Strict actual-direct spoke loft incomplete: built={{len(member_bodies)}}/{{expected_member_count}}, "
            f"failed={{failed_members}}"
        )
    return member_bodies

def build_region_keepout(regions, buffer_radius=0.0, min_area=20.0):
    polys = []
    for region in regions:
        pts_region = region.get("points", []) if isinstance(region, dict) else region
        if len(pts_region) < 4:
            continue
        try:
            poly = normalize_polygon(Polygon(pts_region))
        except Exception:
            continue
        if poly.is_empty or poly.area < min_area:
            continue
        polys.append(poly)

    if not polys:
        return None

    try:
        keepout = normalize_polygon(unary_union(polys))
        if keepout.is_empty:
            return None
        if buffer_radius > 0.05:
            keepout = normalize_polygon(keepout.buffer(float(buffer_radius)))
        return keepout
    except Exception as exc:
        print(f"[!] Region keepout build failed: {{exc}}")
        return None

def continuous_angle_window_local(angles_deg):
    if not angles_deg:
        return None
    angles = sorted([(float(angle) % 360.0) for angle in angles_deg])
    if len(angles) == 1:
        return angles[0], angles[0], 0.0

    gaps = []
    for idx in range(len(angles) - 1):
        gaps.append(angles[idx + 1] - angles[idx])
    gaps.append((angles[0] + 360.0) - angles[-1])

    gap_idx = int(np.argmax(gaps))
    start_angle = angles[(gap_idx + 1) % len(angles)]
    end_angle = angles[gap_idx]
    if end_angle <= start_angle:
        end_angle += 360.0
    return start_angle, end_angle, end_angle - start_angle

def sector_polygon_local(start_angle_deg, end_angle_deg, radius):
    if radius <= 0:
        return Polygon()
    while end_angle_deg <= start_angle_deg:
        end_angle_deg += 360.0
    steps = max(12, int((end_angle_deg - start_angle_deg) / 4.0))
    pts = [(0.0, 0.0)]
    for i in range(steps + 1):
        ang = math.radians(start_angle_deg + ((end_angle_deg - start_angle_deg) * i / steps))
        pts.append((radius * math.cos(ang), radius * math.sin(ang)))
    pts.append((0.0, 0.0))
    return Polygon(pts)

def build_ring_sector(start_angle_deg, end_angle_deg, inner_r, outer_r):
    # Create an annular sector polygon for generated CadQuery code.
    if outer_r <= inner_r + 0.3:
        return Polygon()
    wedge = normalize_geom(sector_polygon(start_angle_deg, end_angle_deg, outer_r))
    if wedge.is_empty:
        return wedge
    if inner_r > 0.0:
        wedge = normalize_geom(
            wedge.difference(circle_polygon(max(0.0, inner_r), 180))
        )
    return wedge

def build_tapered_bridge_polygon(center_angle_deg, inner_r, outer_r, inner_half_span_deg, outer_half_span_deg):
    # Create a tapered wedge polygon for generated CadQuery code.
    if outer_r <= inner_r + 0.3:
        return Polygon()
    try:
        center_angle_deg = float(center_angle_deg)
        inner_r = float(inner_r)
        outer_r = float(outer_r)
        inner_half_span_deg = max(0.45, float(inner_half_span_deg))
        outer_half_span_deg = max(inner_half_span_deg + 0.2, float(outer_half_span_deg))

        inner_steps = max(4, int((inner_half_span_deg * 2.0) / 0.8))
        outer_steps = max(6, int((outer_half_span_deg * 2.0) / 0.8))
        pts = []

        for idx in range(inner_steps + 1):
            ang_deg = (center_angle_deg - inner_half_span_deg) + ((2.0 * inner_half_span_deg * idx) / inner_steps)
            ang = math.radians(ang_deg)
            pts.append((inner_r * math.cos(ang), inner_r * math.sin(ang)))

        for idx in range(outer_steps, -1, -1):
            ang_deg = (center_angle_deg - outer_half_span_deg) + ((2.0 * outer_half_span_deg * idx) / outer_steps)
            ang = math.radians(ang_deg)
            pts.append((outer_r * math.cos(ang), outer_r * math.sin(ang)))

        if len(pts) < 4:
            return Polygon()
        pts.append(pts[0])
        return normalize_geom(Polygon(pts))
    except Exception:
        return Polygon()

def build_ring_sector(start_angle_deg, end_angle_deg, inner_r, outer_r):
    # Create an annular sector polygon for generated CadQuery code.
    if outer_r <= inner_r + 0.3:
        return Polygon()
    wedge = normalize_geom(sector_polygon(start_angle_deg, end_angle_deg, outer_r))
    if wedge.is_empty:
        return wedge
    if inner_r > 0.0:
        wedge = normalize_geom(
            wedge.difference(circle_polygon(max(0.0, inner_r), 180))
        )
    return wedge

def build_tapered_bridge_polygon(center_angle_deg, inner_r, outer_r, inner_half_span_deg, outer_half_span_deg):
    # Create a tapered wedge polygon for generated CadQuery code.
    if outer_r <= inner_r + 0.3:
        return Polygon()
    try:
        center_angle_deg = float(center_angle_deg)
        inner_r = float(inner_r)
        outer_r = float(outer_r)
        inner_half_span_deg = max(0.45, float(inner_half_span_deg))
        outer_half_span_deg = max(inner_half_span_deg + 0.2, float(outer_half_span_deg))

        inner_steps = max(4, int((inner_half_span_deg * 2.0) / 0.8))
        outer_steps = max(6, int((outer_half_span_deg * 2.0) / 0.8))
        pts = []

        for idx in range(inner_steps + 1):
            ang_deg = (center_angle_deg - inner_half_span_deg) + ((2.0 * inner_half_span_deg * idx) / inner_steps)
            ang = math.radians(ang_deg)
            pts.append((inner_r * math.cos(ang), inner_r * math.sin(ang)))

        for idx in range(outer_steps, -1, -1):
            ang_deg = (center_angle_deg - outer_half_span_deg) + ((2.0 * outer_half_span_deg * idx) / outer_steps)
            ang = math.radians(ang_deg)
            pts.append((outer_r * math.cos(ang), outer_r * math.sin(ang)))

        if len(pts) < 4:
            return Polygon()
        pts.append(pts[0])
        return normalize_geom(Polygon(pts))
    except Exception:
        return Polygon()

def build_ring_sector(start_angle_deg, end_angle_deg, inner_r, outer_r):
    if outer_r <= inner_r + 0.3:
        return Polygon()
    wedge = normalize_polygon(sector_polygon_local(start_angle_deg, end_angle_deg, outer_r))
    if wedge.is_empty:
        return wedge
    if inner_r > 0.0:
        wedge = normalize_polygon(
            wedge.difference(Polygon(circle_points(max(0.0, inner_r), 180)))
        )
    return wedge

def build_tapered_bridge_polygon(center_angle_deg, inner_r, outer_r, inner_half_span_deg, outer_half_span_deg):
    if outer_r <= inner_r + 0.3:
        return Polygon()
    try:
        center_angle_deg = float(center_angle_deg)
        inner_r = float(inner_r)
        outer_r = float(outer_r)
        inner_half_span_deg = max(0.45, float(inner_half_span_deg))
        outer_half_span_deg = max(inner_half_span_deg + 0.2, float(outer_half_span_deg))

        inner_steps = max(4, int((inner_half_span_deg * 2.0) / 0.8))
        outer_steps = max(6, int((outer_half_span_deg * 2.0) / 0.8))
        pts = []

        for idx in range(inner_steps + 1):
            ang_deg = (center_angle_deg - inner_half_span_deg) + ((2.0 * inner_half_span_deg * idx) / inner_steps)
            ang = math.radians(ang_deg)
            pts.append((inner_r * math.cos(ang), inner_r * math.sin(ang)))

        for idx in range(outer_steps, -1, -1):
            ang_deg = (center_angle_deg - outer_half_span_deg) + ((2.0 * outer_half_span_deg * idx) / outer_steps)
            ang = math.radians(ang_deg)
            pts.append((outer_r * math.cos(ang), outer_r * math.sin(ang)))

        if len(pts) < 4:
            return Polygon()
        pts.append(pts[0])
        return normalize_polygon(Polygon(pts))
    except Exception:
        return Polygon()

def derive_unified_center_outer_radius(window_inner_ref_radii, params, boss_regions):
    local_window_refs = []
    for value in window_inner_ref_radii:
        if value is None:
            continue
        try:
            radius_val = float(value)
        except Exception:
            continue
        if radius_val > 0.0:
            local_window_refs.append(radius_val)

    global_window_ref = params.get("window_inner_reference_r")
    window_target = None
    if local_window_refs:
        try:
            window_ref_arr = np.asarray(local_window_refs, dtype=float)
            window_target = float(np.percentile(window_ref_arr, 50.0)) - 0.2
        except Exception:
            window_target = None
    elif global_window_ref is not None:
        try:
            global_radius_val = float(global_window_ref)
            if global_radius_val > 0.0:
                window_target = global_radius_val - 0.25
        except Exception:
            window_target = None

    boss_outer_candidates = []
    for region in boss_regions:
        pts = region.get("points", []) if isinstance(region, dict) else []
        if len(pts) < 4:
            continue
        radii = [math.hypot(x, y) for x, y in pts[:-1]]
        if radii:
            boss_outer_candidates.append(max(radii))

    boss_floor = None
    if boss_outer_candidates:
        boss_floor = float(np.median(np.asarray(boss_outer_candidates, dtype=float))) + 1.0

    if window_target is None:
        return boss_floor
    if boss_floor is None:
        return float(window_target)
    return float(max(window_target, boss_floor))

def dedupe_profile_points(points, min_radius=None, max_radius=None):
    cleaned = []
    for point in points:
        if len(point) < 2:
            continue
        radius_val = float(point[0])
        z_val = float(point[1])
        if min_radius is not None and radius_val < float(min_radius) - 0.2:
            continue
        if max_radius is not None and radius_val > float(max_radius) + 0.2:
            continue
        cleaned.append([radius_val, z_val])

    if len(cleaned) < 4:
        return []

    cleaned.sort(key=lambda item: item[0], reverse=True)
    deduped = []
    for radius_val, z_val in cleaned:
        if deduped and abs(radius_val - deduped[-1][0]) < 0.08:
            deduped[-1][1] = max(deduped[-1][1], z_val)
            continue
        if deduped and radius_val >= deduped[-1][0]:
            radius_val = deduped[-1][0] - 0.05
        deduped.append([round(radius_val, 3), round(z_val, 3)])

    return deduped if len(deduped) >= 4 else []

def build_rotary_band(points, min_radius, max_radius, base_z, label):
    band_pts = dedupe_profile_points(points, min_radius=min_radius, max_radius=max_radius)
    if len(band_pts) < 4:
        return None

    outer_r = float(band_pts[0][0])
    inner_r = float(band_pts[-1][0])
    if outer_r <= inner_r + 0.5:
        return None

    min_top_z = min([float(p[1]) for p in band_pts])
    floor_z = min(float(base_z), min_top_z - 0.4)
    profile_wire = [[outer_r, floor_z]]
    profile_wire.extend([[float(radius_val), max(floor_z + 0.2, float(z_val))] for radius_val, z_val in band_pts])
    profile_wire.append([inner_r, floor_z])

    try:
        closed_wire = list(profile_wire)
        if closed_wire[0] != closed_wire[-1]:
            closed_wire.append(closed_wire[0])
        if disable_spokes_modeling:
            return cq.Workplane("XZ").polyline(closed_wire).close().revolve(360, (0, 0, 0), (0, 1, 0))
        try:
            return cq.Workplane("XZ").spline(closed_wire).close().revolve(360, (0, 0, 0), (0, 1, 0))
        except Exception:
            return cq.Workplane("XZ").polyline(closed_wire).close().revolve(360, (0, 0, 0), (0, 1, 0))
    except Exception as exc:
        print(f"[!] {{label}} rotary band revolve failed: {{exc}}")
        return None

def build_rotary_from_envelopes(poly, clip_min_r, clip_max_r, label):
    if poly is None or poly.is_empty:
        return None
    try:
        bounds = poly.bounds
        z_low = float(bounds[1]) - 1.0
        z_high = float(bounds[3]) + 1.0
        radii = np.linspace(float(clip_min_r), float(clip_max_r), 220)
        upper = []
        lower = []

        def collect_z(geom, acc):
            if geom is None or geom.is_empty:
                return
            if isinstance(geom, Point):
                acc.append(float(geom.y))
                return
            if isinstance(geom, LineString):
                for _, z_val in list(geom.coords):
                    acc.append(float(z_val))
                return
            if isinstance(geom, MultiLineString):
                for sub in geom.geoms:
                    collect_z(sub, acc)
                return
            if isinstance(geom, GeometryCollection):
                for sub in geom.geoms:
                    collect_z(sub, acc)
                return
            if hasattr(geom, "geoms"):
                for sub in geom.geoms:
                    collect_z(sub, acc)

        for radius_val in radii:
            probe = LineString([(float(radius_val), z_low), (float(radius_val), z_high)])
            hit = poly.intersection(probe)
            hit_z = []
            collect_z(hit, hit_z)
            if len(hit_z) < 2:
                continue
            top_z = float(max(hit_z))
            bottom_z = float(min(hit_z))
            if top_z <= bottom_z + 0.15:
                continue
            upper.append([round(float(radius_val), 3), round(top_z, 3)])
            lower.append([round(float(radius_val), 3), round(bottom_z, 3)])

        if len(upper) < 12 or len(lower) < 12:
            return None

        loop = []
        loop.extend([[float(r), float(z)] for r, z in reversed(upper)])
        loop.extend([[float(r), float(z)] for r, z in lower])

        cleaned = []
        for radius_val, z_val in loop:
            if cleaned and math.hypot(radius_val - cleaned[-1][0], z_val - cleaned[-1][1]) < 0.05:
                continue
            cleaned.append([round(float(radius_val), 3), round(float(z_val), 3)])

        if len(cleaned) < 8:
            return None
        if cleaned[0] != cleaned[-1]:
            cleaned.append(cleaned[0])

        if disable_spokes_modeling:
            return cq.Workplane("XZ").polyline(cleaned).close().revolve(360, (0, 0, 0), (0, 1, 0))
        try:
            return cq.Workplane("XZ").spline(cleaned).close().revolve(360, (0, 0, 0), (0, 1, 0))
        except Exception:
            return cq.Workplane("XZ").polyline(cleaned).close().revolve(360, (0, 0, 0), (0, 1, 0))
    except Exception as exc:
        print(f"[!] {{label}} envelope revolve failed: {{exc}}")
        return None

def build_rotary_from_section_region(region, min_radius, max_radius, label):
    outer = region.get("outer", []) if isinstance(region, dict) else []
    holes = region.get("holes", []) if isinstance(region, dict) else []
    if len(outer) < 4:
        return None

    try:
        outer_poly = Polygon(outer, holes)
        outer_poly = normalize_polygon(outer_poly)
    except Exception as exc:
        print(f"[!] {{label}} section region invalid: {{exc}}")
        return None

    if outer_poly.is_empty:
        return None

    clip_min_r = max(0.0, float(min_radius))
    clip_max_r = max(clip_min_r + 0.5, float(max_radius))
    bounds = outer_poly.bounds
    clip_box = Polygon([
        (clip_min_r, bounds[1] - 2.0),
        (clip_max_r, bounds[1] - 2.0),
        (clip_max_r, bounds[3] + 2.0),
        (clip_min_r, bounds[3] + 2.0)
    ])
    clipped = normalize_polygon(outer_poly.intersection(clip_box))
    clipped_poly = largest_polygon(clipped, min_area=20.0)
    if clipped_poly is None:
        return None

    try:
        bounds = clipped_poly.bounds
        if bounds[2] <= bounds[0] + 0.5 or bounds[3] <= bounds[1] + 0.5:
            return None

        simplify_tol = max(0.08, min(0.25, (bounds[2] - bounds[0]) / 900.0))
        simplified_geom = normalize_polygon(clipped_poly.simplify(simplify_tol, preserve_topology=True))
        simplified_poly = largest_polygon(simplified_geom, min_area=20.0)
        if simplified_poly is None:
            simplified_poly = clipped_poly

        def prepare_ring(coords):
            pts = [(float(x), float(y)) for x, y in list(coords)]
            if len(pts) < 4:
                return []
            if pts[0] == pts[-1]:
                pts = pts[:-1]
            if len(pts) < 3:
                return []

            start_idx = min(
                range(len(pts)),
                key=lambda i: (
                    round(pts[i][0], 6),
                    -round(pts[i][1], 6)
                )
            )
            loop = pts[start_idx:] + pts[:start_idx]
            loop.append(loop[0])

            cleaned = []
            for radius_val, z_val in loop:
                radius_val = min(clip_max_r, max(clip_min_r, float(radius_val)))
                z_val = float(z_val)
                if cleaned and math.hypot(radius_val - cleaned[-1][0], z_val - cleaned[-1][1]) < 0.05:
                    continue
                cleaned.append([round(radius_val, 3), round(z_val, 3)])

            if len(cleaned) < 4:
                return []
            if cleaned[0] != cleaned[-1]:
                cleaned.append(cleaned[0])
            return cleaned

        outer_loop = prepare_ring(simplified_poly.exterior.coords)
        if len(outer_loop) < 4:
            return None

        body = None
        try:
            body = cq.Workplane("XZ").polyline(outer_loop).close().revolve(360, (0, 0, 0), (0, 1, 0))
        except Exception as raw_exc:
            print(f"[!] {{label}} raw section revolve failed: {{raw_exc}}")

        for interior in simplified_poly.interiors:
            hole_loop = prepare_ring(interior.coords)
            if len(hole_loop) < 4:
                continue
            try:
                hole_body = cq.Workplane("XZ").polyline(hole_loop).close().revolve(360, (0, 0, 0), (0, 1, 0))
            except Exception as hole_exc:
                print(f"[!] {{label}} section hole revolve failed: {{hole_exc}}")
                continue
            body = safe_cut(body, hole_body, f"{{label}} section hole")

        try:
            solid_count = len(body.solids().vals()) if body is not None else 0
        except Exception:
            solid_count = 0
        if body is not None and solid_count == 1:
            return body

        if body is not None:
            print(f"[*] {{label}} section revolve produced {{solid_count}} solids. Switching to envelope fallback.")

        fallback_body = build_rotary_from_envelopes(simplified_poly, clip_min_r, clip_max_r, label)
        if fallback_body is not None:
            return fallback_body
        return body
    except Exception as exc:
        print(f"[!] {{label}} section revolve failed: {{exc}}")
        return None

def derive_rotary_outer_start(spoke_regions, voids, rim_pts, params):
    candidates = []
    for region in spoke_regions:
        pts = region.get("points", []) if isinstance(region, dict) else region
        if len(pts) < 4:
            continue
        radii = [math.hypot(x, y) for x, y in pts[:-1]]
        if radii:
            candidates.append(max(radii))

    for region in voids:
        pts = region.get("points", []) if isinstance(region, dict) else region
        if len(pts) < 4:
            continue
        radii = [math.hypot(x, y) for x, y in pts[:-1]]
        if radii:
            candidates.append(max(radii))

    if candidates:
        return min(
            max(candidates) + 0.4,
            max([float(p[0]) for p in rim_pts], default=params["rim_max_radius"]) - 1.0
        )

    return max(
        params["rim_max_radius"] - max(12.0, params["rim_thickness"] * 5.0),
        params["hub_radius"] + 20.0
    )

def apply_center_boss_relief(
    hub_body,
    relief_z,
    hub_top_z,
    core_region,
    boss_regions,
    root_regions,
    bore_radius=None,
    protected_inner_r=None
):
    if relief_z is None or hub_top_z <= relief_z + 0.2:
        return hub_body
    if not boss_regions:
        return hub_body

    keep_polys = []
    max_keep_r = 0.0
    core_keep_outer_r = 0.0
    boss_inner_keep_r = None

    core_pts = core_region.get("points", []) if isinstance(core_region, dict) else []
    if len(core_pts) >= 4:
        try:
            core_poly = normalize_polygon(Polygon(core_pts))
            if not core_poly.is_empty and core_poly.area > 30.0:
                core_radii = [math.hypot(x, y) for x, y in list(core_poly.exterior.coords)[:-1]]
                if core_radii:
                    core_outer_r = max(core_radii)
                    if bore_radius is not None and core_outer_r > float(bore_radius) + 0.8:
                        lip_span = max(0.8, core_outer_r - float(bore_radius))
                        lip_outer_r = min(
                            core_outer_r,
                            float(bore_radius) + max(1.2, min(3.2, lip_span * 0.38))
                        )
                        lip_band = normalize_polygon(
                            core_poly.intersection(Polygon(circle_points(lip_outer_r, 180)))
                        )
                        lip_band = normalize_polygon(
                            lip_band.difference(Polygon(circle_points(max(0.0, float(bore_radius) - 0.35), 180)))
                        )
                        lip_candidates = [
                            poly for poly in iter_polygons(lip_band)
                            if not poly.is_empty and poly.area > 8.0
                        ]
                        if lip_candidates:
                            for lip_poly in lip_candidates:
                                keep_polys.append(lip_poly)
                                lip_radii = [math.hypot(x, y) for x, y in list(lip_poly.exterior.coords)[:-1]]
                                max_keep_r = max(
                                    max_keep_r,
                                    max(lip_radii)
                                )
                                core_keep_outer_r = max(core_keep_outer_r, max(lip_radii))
                    else:
                        keep_polys.append(core_poly)
                        max_keep_r = max(
                            max_keep_r,
                            max(core_radii)
                        )
                        core_keep_outer_r = max(core_keep_outer_r, max(core_radii))
        except Exception:
            pass

    for region in boss_regions:
        pts = region.get("points", []) if isinstance(region, dict) else []
        if len(pts) < 4:
            continue
        try:
            boss_poly = normalize_polygon(Polygon(pts))
        except Exception:
            continue
        if boss_poly.is_empty or boss_poly.area < 40.0:
            continue
        keep_polys.append(boss_poly)
        boss_radii = [math.hypot(x, y) for x, y in list(boss_poly.exterior.coords)[:-1]]
        max_keep_r = max(
            max_keep_r,
            max(boss_radii)
        )
        if boss_radii:
            boss_inner_candidate = min(boss_radii)
            boss_inner_keep_r = boss_inner_candidate if boss_inner_keep_r is None else min(boss_inner_keep_r, boss_inner_candidate)

    for region in root_regions:
        pts = region.get("points", []) if isinstance(region, dict) else []
        if len(pts) < 4:
            continue
        try:
            root_poly = normalize_polygon(Polygon(pts))
        except Exception:
            continue
        if root_poly.is_empty or root_poly.area < 25.0:
            continue
        keep_polys.append(root_poly)
        max_keep_r = max(
            max_keep_r,
            max([math.hypot(x, y) for x, y in list(root_poly.exterior.coords)[:-1]])
        )

    if len(keep_polys) < 2 or max_keep_r <= 0.0:
        return hub_body

    try:
        keep_geom = unary_union(keep_polys)
        limit_geom = normalize_polygon(Polygon(circle_points(max_keep_r + 0.8, 220)))
        relief_geom = limit_geom.difference(keep_geom)
        if protected_inner_r is not None and float(protected_inner_r) > 0.0:
            relief_geom = normalize_polygon(
                relief_geom.difference(Polygon(circle_points(float(protected_inner_r), 220)))
            )
        if bore_radius is not None and boss_inner_keep_r is not None:
            inner_anchor_r = max(core_keep_outer_r, float(bore_radius))
            boss_gap = max(0.0, float(boss_inner_keep_r) - inner_anchor_r)
            if boss_gap > 0.9:
                relief_inner_cutoff_r = max(
                    inner_anchor_r + 0.25,
                    float(boss_inner_keep_r) - max(0.8, min(2.5, boss_gap * 0.72))
                )
                relief_geom = normalize_polygon(
                    relief_geom.difference(Polygon(circle_points(relief_inner_cutoff_r, 220)))
                )
        relief_height = max(0.6, (hub_top_z - relief_z) + 0.8)

        relief_polys = []
        for poly in iter_polygons(relief_geom):
            if poly.is_empty or poly.area < 12.0:
                continue
            relief_polys.append(poly)

        if not relief_polys:
            return hub_body

        for idx, poly in enumerate(relief_polys):
            relief_coords = [[round(float(x), 3), round(float(y), 3)] for x, y in list(poly.exterior.coords)]
            if relief_coords and relief_coords[0] != relief_coords[-1]:
                relief_coords.append(relief_coords[0])
            cutter = build_polygon_prism(relief_coords, relief_z, relief_height)
            if cutter is not None:
                hub_body = safe_cut(hub_body, cutter, f"center relief {{idx}}")
    except Exception as exc:
        print(f"[!] Center boss relief failed: {{exc}}")

    return hub_body

def apply_unified_center_valley_relief(
    hub_body,
    floor_z,
    hub_top_z,
    root_regions,
    boss_regions=None,
    bore_radius=None,
    outer_relief_r=None,
    window_inner_ref_radii=None
):
    if floor_z is None or hub_top_z is None or outer_relief_r is None:
        return hub_body
    if hub_top_z <= floor_z + 0.2:
        return hub_body
    if not root_regions:
        return hub_body

    root_specs = []
    for region in root_regions:
        pts = region.get("points", []) if isinstance(region, dict) else []
        if len(pts) < 4:
            continue
        try:
            root_poly = normalize_polygon(Polygon(pts))
        except Exception:
            continue
        if root_poly.is_empty or root_poly.area < 18.0:
            continue
        coords = list(root_poly.exterior.coords)
        radii = [math.hypot(x, y) for x, y in coords[:-1]]
        if not radii:
            continue
        centroid = root_poly.centroid
        root_specs.append({{
            "center_angle": math.degrees(math.atan2(centroid.y, centroid.x)) % 360.0,
            "inner_r": min(radii),
            "outer_r": max(radii)
        }})

    if len(root_specs) < 3:
        return hub_body

    boss_specs = []
    for region in boss_regions or []:
        center_xy = region.get("center") if isinstance(region, dict) else None
        pts = region.get("points", []) if isinstance(region, dict) else []
        if not (isinstance(center_xy, (list, tuple)) and len(center_xy) >= 2 and len(pts) >= 4):
            continue
        try:
            cx = float(center_xy[0])
            cy = float(center_xy[1])
            local_radii = [math.hypot(float(x) - cx, float(y) - cy) for x, y in pts[:-1]]
            if not local_radii:
                continue
            boss_specs.append({{
                "center_angle": math.degrees(math.atan2(cy, cx)) % 360.0,
                "outer_r": math.hypot(cx, cy) + float(np.percentile(np.asarray(local_radii, dtype=float), 40.0))
            }})
        except Exception:
            continue

    root_specs.sort(key=lambda item: item["center_angle"])
    relief_height = max(0.6, (hub_top_z - floor_z) + 0.8)
    valley_cut_count = 0
    local_window_refs = []
    for value in window_inner_ref_radii or []:
        try:
            value_f = float(value)
        except Exception:
            continue
        if value_f > 0.0:
            local_window_refs.append(value_f)
    valley_outer_target = float(outer_relief_r) + 0.55
    if local_window_refs:
        try:
            valley_outer_target = max(
                valley_outer_target,
                float(np.percentile(np.asarray(local_window_refs, dtype=float), 65.0)) - 0.05
            )
        except Exception:
            pass

    def angle_in_gap(candidate_angle, start_angle, end_angle):
        angle_val = float(candidate_angle) % 360.0
        start_val = float(start_angle) % 360.0
        end_val = float(end_angle)
        while angle_val < start_val:
            angle_val += 360.0
        return start_val <= angle_val <= end_val

    for idx, spec in enumerate(root_specs):
        next_spec = root_specs[(idx + 1) % len(root_specs)]
        next_angle = next_spec["center_angle"]
        while next_angle <= spec["center_angle"]:
            next_angle += 360.0
        gap_angle = next_angle - spec["center_angle"]
        if gap_angle < 8.0:
            continue

        valley_center = spec["center_angle"] + (gap_angle * 0.5)
        gap_bosses = [
            boss for boss in boss_specs
            if angle_in_gap(boss["center_angle"], spec["center_angle"], next_angle)
        ]
        if gap_bosses:
            boss_outer_limit = max([float(boss["outer_r"]) for boss in gap_bosses])
            valley_inner_r = boss_outer_limit + 0.55
            valley_half_span = max(1.0, min(2.0, gap_angle * 0.13))
        else:
            valley_inner_r = float(bore_radius) + 0.35 if bore_radius is not None else 0.0
            valley_half_span = max(1.2, min(2.8, gap_angle * 0.16))
        valley_outer_r = float(valley_outer_target)
        if valley_outer_r <= valley_inner_r + 0.8:
            continue

        valley_poly = build_ring_sector(
            valley_center - valley_half_span,
            valley_center + valley_half_span,
            valley_inner_r,
            valley_outer_r
        )
        valley_poly = normalize_polygon(valley_poly)
        if valley_poly.is_empty or valley_poly.area < 10.0:
            continue

        valley_coords = [[round(float(x), 3), round(float(y), 3)] for x, y in list(valley_poly.exterior.coords)]
        if valley_coords and valley_coords[0] != valley_coords[-1]:
            valley_coords.append(valley_coords[0])
        cutter = build_polygon_prism(valley_coords, floor_z, relief_height)
        if cutter is None:
            continue
        hub_body = safe_cut(hub_body, cutter, f"unified center valley {{idx}}")
        valley_cut_count += 1

    print(f"[*] Unified center valleys cut: {{valley_cut_count}}")
    return hub_body

def apply_hub_bottom_groove_relief(
    hub_body,
    groove_regions,
    floor_z,
    top_z,
    bore_radius=None,
    rear_face_z=None
):
    if not groove_regions or floor_z is None or top_z is None:
        return hub_body
    groove_height = float(top_z) - float(floor_z)
    if groove_height <= 0.8:
        return hub_body

    def sample_profile_z(profile_pts, radius_val):
        if not profile_pts or len(profile_pts) < 2:
            return None
        try:
            radius_val = float(radius_val)
            ordered = sorted(
                [(float(r), float(z)) for r, z in profile_pts if r is not None and z is not None],
                key=lambda item: item[0]
            )
            if len(ordered) < 2:
                return None
            if radius_val <= ordered[0][0]:
                return ordered[0][1]
            if radius_val >= ordered[-1][0]:
                return ordered[-1][1]
            for idx in range(len(ordered) - 1):
                r0, z0 = ordered[idx]
                r1, z1 = ordered[idx + 1]
                if r1 <= r0:
                    continue
                if r0 <= radius_val <= r1:
                    t = (radius_val - r0) / (r1 - r0)
                    return z0 + ((z1 - z0) * t)
        except Exception:
            return None
        return None

    def derive_effective_groove_z_range(groove_pts, groove_data=None):
        try:
            groove_poly = normalize_polygon(Polygon(groove_pts))
        except Exception:
            return float(floor_z), float(top_z)
        if groove_poly.is_empty:
            return float(floor_z), float(top_z)

        coords = list(groove_poly.exterior.coords)
        radii = [math.hypot(x, y) for x, y in coords[:-1]]
        if not radii:
            return float(floor_z), float(top_z)

        probe_radii = sorted(set([
            float(np.percentile(np.asarray(radii, dtype=float), q))
            for q in (15.0, 40.0, 65.0, 85.0)
        ]))
        surface_samples = []
        for radius_probe in probe_radii:
            local_z = sample_profile_z(rotary_face_pts, radius_probe)
            if local_z is None:
                local_z = sample_profile_z(hub_profile_pts, radius_probe)
            if local_z is not None:
                surface_samples.append(float(local_z))

        if not surface_samples:
            return float(floor_z), float(top_z)

        local_surface_front_z = max(surface_samples)
        local_surface_rear_z = min(surface_samples)
        perceived_open_z = None
        perceived_deep_z = None
        if isinstance(groove_data, dict):
            if groove_data.get("opening_z") is not None:
                try:
                    perceived_open_z = float(groove_data.get("opening_z"))
                except Exception:
                    perceived_open_z = None
            if groove_data.get("deep_z") is not None:
                try:
                    perceived_deep_z = float(groove_data.get("deep_z"))
                except Exception:
                    perceived_deep_z = None

        if (
            perceived_open_z is not None
            and perceived_deep_z is not None
            and perceived_deep_z > perceived_open_z + 0.3
        ):
            if rear_face_z is not None:
                rear_open_reference = min(perceived_open_z, float(rear_face_z) + 0.18)
                effective_floor_z = min(float(rear_face_z) + 0.08, rear_open_reference) - 0.04
            else:
                effective_floor_z = min(perceived_open_z, local_surface_rear_z + 0.2) - 0.04

            effective_top_z = perceived_deep_z + 0.08
            effective_top_z = min(local_surface_front_z - 0.2, effective_top_z)
            if effective_top_z <= effective_floor_z + 0.8:
                effective_top_z = min(
                    local_surface_front_z - 0.15,
                    effective_floor_z + max(0.9, (perceived_deep_z - perceived_open_z) + 0.3)
                )
        else:
            target_depth = max(1.2, min(float(groove_height), 3.0))
            if rear_face_z is not None:
                target_depth = max(4.2, min(float(groove_height) + 0.6, 6.2))
                rear_open_z = float(rear_face_z)
                effective_floor_z = rear_open_z - 0.12
                effective_top_z = min(local_surface_front_z - 0.35, rear_open_z + target_depth)
                if effective_top_z <= effective_floor_z + 0.8:
                    effective_top_z = effective_floor_z + max(0.9, target_depth)
            else:
                effective_top_z = local_surface_rear_z + 0.18
                effective_floor_z = effective_top_z - target_depth
                if effective_floor_z >= local_surface_front_z - 0.25:
                    effective_floor_z = effective_top_z - max(0.9, target_depth)
                if effective_floor_z <= local_surface_rear_z - 2.5:
                    effective_floor_z = local_surface_rear_z - 0.35

        try:
            bbox = hub_body.val().BoundingBox()
            effective_floor_z = max(float(bbox.zmin) + 0.5, effective_floor_z)
            effective_top_z = min(float(bbox.zmax) + 0.25, effective_top_z)
        except Exception:
            pass

        if effective_top_z <= effective_floor_z + 0.8:
            return float(floor_z), float(top_z)
        return float(effective_floor_z), float(effective_top_z)

    def project_opening_points_to_rear_face(opening_pts, deep_pts, groove_data=None):
        if not opening_pts or len(opening_pts) < 4 or not deep_pts or len(deep_pts) < 4:
            return opening_pts
        if rear_face_z is None or not isinstance(groove_data, dict):
            return opening_pts

        try:
            opening_z = groove_data.get("opening_z")
            deep_z = groove_data.get("deep_z")
            if opening_z is None or deep_z is None:
                return opening_pts
            opening_z = float(opening_z)
            deep_z = float(deep_z)
            rear_z = float(rear_face_z)
        except Exception:
            return opening_pts

        if opening_z <= rear_z + 0.08 or deep_z <= opening_z + 0.35:
            return opening_pts

        try:
            opening_loop = resample_closed_loop(opening_pts, target_count=48)
            deep_loop = resample_closed_loop(deep_pts, target_count=48)
        except Exception:
            return opening_pts

        if len(opening_loop) < 8 or len(deep_loop) < 8:
            return opening_pts

        projection_scale = (opening_z - rear_z) / max(0.35, deep_z - opening_z)
        projection_scale = max(0.04, min(0.55, float(projection_scale)))
        projected = []
        min_inner_r = (float(bore_radius) + 0.2) if bore_radius is not None else 0.0

        for open_pt, deep_pt in zip(opening_loop[:-1], deep_loop[:-1]):
            ox, oy = float(open_pt[0]), float(open_pt[1])
            dx, dy = float(deep_pt[0]), float(deep_pt[1])
            px = ox + ((ox - dx) * projection_scale)
            py = oy + ((oy - dy) * projection_scale)
            projected_r = math.hypot(px, py)
            if projected_r < min_inner_r:
                base_r = max(1e-6, math.hypot(ox, oy))
                scale = min_inner_r / base_r
                px = ox * scale
                py = oy * scale
            projected.append([round(px, 3), round(py, 3)])

        if projected and projected[0] != projected[-1]:
            projected.append(list(projected[0]))

        try:
            projected_poly = largest_polygon(
                normalize_polygon(Polygon(projected)),
                min_area=10.0
            )
            if projected_poly is None:
                return opening_pts
            projected_coords = [[round(float(x), 3), round(float(y), 3)] for x, y in list(projected_poly.exterior.coords)]
            if projected_coords and projected_coords[0] != projected_coords[-1]:
                projected_coords.append(list(projected_coords[0]))
            if len(projected_coords) >= 4:
                return projected_coords
        except Exception:
            return opening_pts

        return opening_pts

    def build_groove_top_profile(groove_pts):
        try:
            groove_poly = normalize_polygon(Polygon(groove_pts))
        except Exception:
            return None
        if groove_poly.is_empty or float(groove_poly.area) < 10.0:
            return None

        coords = list(groove_poly.exterior.coords)
        if len(coords) < 4:
            return None

        radii = [math.hypot(x, y) for x, y in coords[:-1]]
        if not radii:
            return None
        angle_window = continuous_angle_window_local([
            math.degrees(math.atan2(y, x)) % 360.0
            for x, y in coords[:-1]
        ])
        if angle_window is None:
            return None

        lower_inner_r = float(min(radii))
        lower_outer_r = float(max(radii))
        radial_span = max(1.2, lower_outer_r - lower_inner_r)
        top_inner_r = max(
            (float(bore_radius) + 0.15) if bore_radius is not None else 0.0,
            lower_inner_r - max(1.8, min(3.4, radial_span * 0.65))
        )
        top_outer_r = lower_outer_r + max(3.4, min(6.8, radial_span * 1.25))
        angle_pad = max(2.6, min(5.8, float(angle_window[2]) * 0.42))
        top_geom = normalize_polygon(
            build_ring_sector(
                float(angle_window[0]) - angle_pad,
                float(angle_window[1]) + angle_pad,
                top_inner_r,
                top_outer_r
            )
        )
        top_poly = largest_polygon(top_geom, min_area=12.0)
        if top_poly is None:
            return None
        top_coords = [[float(x), float(y)] for x, y in list(top_poly.exterior.coords)]
        if not top_coords:
            return None
        if top_coords[0] != top_coords[-1]:
            top_coords.append(list(top_coords[0]))
        return top_coords if len(top_coords) >= 4 else None

    groove_cut_count = 0
    groove_noop_count = 0
    groove_effective_ranges = []
    for idx, region in enumerate(groove_regions):
        groove_data = region if isinstance(region, dict) else {{}}
        groove_pts = groove_data.get("points", []) if groove_data else region
        opening_pts = groove_data.get("opening_points", groove_pts) if groove_data else groove_pts
        deep_pts = groove_data.get("deep_points", groove_pts) if groove_data else groove_pts
        opening_pts = project_opening_points_to_rear_face(opening_pts, deep_pts, groove_data)
        if len(groove_pts) < 4:
            continue
        effective_floor_z, effective_top_z = derive_effective_groove_z_range(opening_pts, groove_data)
        effective_height = float(effective_top_z) - float(effective_floor_z)
        if effective_height <= 0.8:
            continue
        cutter = None
        if len(opening_pts) >= 4 and len(deep_pts) >= 4:
            cutter = build_polygon_transition_cutter(opening_pts, deep_pts, float(effective_floor_z), float(effective_top_z))
        if cutter is None:
            top_profile = build_groove_top_profile(opening_pts)
            if top_profile is not None:
                cutter = build_polygon_prism(top_profile, float(effective_floor_z), effective_height + 0.45)
        if cutter is None:
            cutter = build_polygon_prism(opening_pts, float(effective_floor_z), effective_height + 0.4)
        if cutter is None:
            continue
        try:
            hub_groove_debug_bodies.append(cutter)
        except Exception:
            pass
        vol_before = body_volume(hub_body)
        cut_body = safe_cut(hub_body, cutter, f"hub bottom groove {{idx}}")
        vol_after = body_volume(cut_body)
        if vol_before is not None and vol_after is not None and (vol_before - vol_after) <= 0.5:
            groove_noop_count += 1
            print(
                f"[!] hub bottom groove {{idx}} produced negligible volume change: "
                f"delta={{round(vol_before - vol_after, 4)}}"
            )
            continue
        hub_body = cut_body
        groove_cut_count += 1
        groove_effective_ranges.append((float(effective_floor_z), float(effective_top_z)))

    effective_desc = ""
    if groove_effective_ranges:
        floor_vals = [item[0] for item in groove_effective_ranges]
        top_vals = [item[1] for item in groove_effective_ranges]
        effective_desc = (
            f", effective Z={{round(min(floor_vals), 2)}} -> {{round(max(top_vals), 2)}}"
        )
    print(
        f"[*] Hub rear-face grooves cut: {{groove_cut_count}} "
        f"(Z={{round(float(floor_z), 2)}} -> {{round(float(top_z), 2)}}{{effective_desc}}, no-op={{groove_noop_count}})"
    )
    return hub_body

def build_spoke_regions(face_boundary, voids, hub_r):
    if not face_boundary or len(face_boundary) < 4:
        return []

    face_poly = normalize_polygon(Polygon(face_boundary))
    if face_poly.is_empty:
        return []

    cutters = []
    for v in voids:
        v_pts = v.get("points", [])
        if len(v_pts) < 4:
            continue
        cutter_poly = normalize_polygon(Polygon(v_pts))
        if not cutter_poly.is_empty and cutter_poly.area > 50.0:
            cutters.append(cutter_poly)

    hub_cut = normalize_polygon(Polygon(circle_points(hub_r + 0.5, 120)))
    spoke_region = face_poly.difference(hub_cut)
    if cutters:
        spoke_region = spoke_region.difference(unary_union(cutters))
    spoke_region = normalize_polygon(spoke_region)

    spoke_polys = []
    for poly in iter_polygons(spoke_region):
        coords = list(poly.exterior.coords)
        if len(coords) < 4 or poly.area < 300.0:
            continue

        radii = [math.hypot(x, y) for x, y in coords[:-1]]
        if not radii:
            continue

        min_r = min(radii)
        max_r = max(radii)
        if min_r > hub_r + 20.0:
            continue
        if max_r < hub_r + 40.0:
            continue

        spoke_polys.append([[round(float(x), 3), round(float(y), 3)] for x, y in coords])

    return spoke_polys

def outer_strip_polygon(region_pts, floor_r=None, depth=None, min_area=12.0):
    if not region_pts or len(region_pts) < 4:
        return None

    region_poly = normalize_polygon(Polygon(region_pts))
    if region_poly.is_empty:
        return None

    coords = list(region_poly.exterior.coords)
    radii = [math.hypot(x, y) for x, y in coords[:-1]]
    if not radii:
        return None

    min_r = min(radii)
    max_r = max(radii)
    radial_span = max_r - min_r
    if radial_span < 3.0:
        return None

    if depth is None:
        depth = max(6.0, min(16.0, radial_span * 0.28))
    depth = max(3.0, min(depth, radial_span - 0.5))

    if floor_r is None:
        floor_r = max_r - depth
    floor_r = max(min_r + 0.25, min(max_r - 0.25, floor_r))

    strip_geom = normalize_polygon(
        region_poly.difference(Polygon(circle_points(floor_r, 180)))
    )
    strip_poly = largest_polygon(strip_geom, min_area=min_area)
    if strip_poly is None:
        return None

    strip_poly = normalize_polygon(strip_poly.simplify(0.15, preserve_topology=True))
    strip_coords = [[round(float(x), 3), round(float(y), 3)] for x, y in list(strip_poly.exterior.coords)]
    if strip_coords and strip_coords[0] != strip_coords[-1]:
        strip_coords.append(strip_coords[0])
    return strip_coords if len(strip_coords) >= 4 else None

def build_tip_section_loft(region_pts, section_group, index):
    if not region_pts or len(region_pts) < 4:
        return None

    base_radii = [math.hypot(x, y) for x, y in region_pts[:-1]]
    if not base_radii:
        return None

    base_inner_r = min(base_radii)
    base_outer_r = max(base_radii)
    base_span = max(1.0, base_outer_r - base_inner_r)
    tip_outer_ceiling_r = min(base_outer_r + 1.0, params["rim_max_radius"] - params["rim_thickness"] + 0.5)
    anchor_depth = max(5.0, min(8.0, base_span * 0.18))
    anchor_profile = outer_strip_polygon(
        region_pts,
        floor_r=base_outer_r - anchor_depth,
        depth=anchor_depth,
        min_area=18.0
    )
    if not anchor_profile:
        return None

    sections = []
    for section in section_group:
        pts = section.get("points", [])
        if len(pts) < 4:
            continue

        try:
            clipped_geom = normalize_geom(
                Polygon(pts).intersection(circle_polygon(tip_outer_ceiling_r, 180))
            )
        except Exception:
            clipped_geom = None

        clipped_poly = largest_polygon(clipped_geom, min_area=8.0) if clipped_geom is not None else None
        if clipped_poly is None:
            continue

        clipped_pts = canonicalize_loop(list(clipped_poly.exterior.coords))
        if len(clipped_pts) < 4:
            continue

        radii = [math.hypot(x, y) for x, y in clipped_pts[:-1]]
        if not radii:
            continue

        section_outer_r = max(radii)
        if section_outer_r < base_outer_r - 1.25:
            continue
        band_depth = max(4.0, min(7.0, (section_outer_r - base_outer_r) + 5.0))
        floor_r = max(base_outer_r - 1.0, section_outer_r - band_depth)
        band_profile = outer_strip_polygon(
            clipped_pts,
            floor_r=floor_r,
            depth=band_depth,
            min_area=10.0
        )
        if not band_profile:
            continue

        sections.append({{
            "z": float(section.get("z", 0.0)),
            "points": band_profile,
            "outer_r": section_outer_r
        }})

    sections.sort(key=lambda section: section["z"])
    if len(sections) == 0:
        return None

    top_section_seed = sections[-1]
    top_z = top_section_seed["z"]
    if spoke_face_z > 0:
        top_z = min(top_z, spoke_face_z)
    filtered_sections = [section for section in sections if section["z"] >= (top_z - 0.95)]
    if len(filtered_sections) == 0:
        filtered_sections = [top_section_seed]
    sections = filtered_sections

    anchor_z = max(spoke_z0 + 0.6, top_z - 0.18)
    if anchor_z >= top_z:
        anchor_z = top_z - 0.12

    sections.insert(0, {{
        "z": anchor_z,
        "points": anchor_profile,
        "outer_r": base_outer_r
    }})
    sections.sort(key=lambda section: section["z"])

    tip_solid = None
    segment_count = 0
    for section_a, section_b in zip(sections[:-1], sections[1:]):
        if section_b["z"] <= section_a["z"] + 0.5:
            continue
        try:
            loft_wp = (
                cq.Workplane("XY")
                .workplane(offset=section_a["z"])
                .polyline(section_a["points"]).close()
            )
            loft_wp = (
                loft_wp
                .workplane(offset=section_b["z"] - section_a["z"])
                .polyline(section_b["points"]).close()
            )
            loft_segment = loft_wp.loft(combine=True)
            loft_segment = cq.Workplane("XY").newObject([loft_segment.findSolid()])
            if tip_solid is None:
                tip_solid = loft_segment
                segment_count += 1
            else:
                merged_tip = safe_union(tip_solid, loft_segment, f"spoke {{index}} tip segment")
                if merged_tip is not tip_solid:
                    tip_solid = merged_tip
                    segment_count += 1
        except Exception as segment_exc:
            print(f"[!] Spoke {{index}} tip loft failed between Z={{section_a['z']}} and Z={{section_b['z']}}: {{segment_exc}}")

    if tip_solid is None or segment_count == 0:
        top_section = sections[-1]
        try:
            cap_top = top_section["z"] - 0.02
            cap_bottom = max(spoke_z0 + 0.4, cap_top - 0.38)
            cap_height = max(0.25, cap_top - cap_bottom)
            tip_solid = (
                cq.Workplane("XY")
                .workplane(offset=cap_bottom)
                .polyline(top_section["points"]).close()
                .extrude(cap_height)
            )
            tip_solid = cq.Workplane("XY").newObject([tip_solid.findSolid()])
            segment_count = 1
        except Exception as cap_exc:
            print(f"[!] Spoke {{index}} tip cap fallback failed: {{cap_exc}}")
            return None

    return cq.Workplane("XY").newObject([tip_solid.findSolid()])

def build_motif_member_spoke(member_payload, motif_payload):
    member_payload["actual_z_profiles"] = []
    member_payload["actual_z_prefer_local_section"] = False
    member_payload["actual_z_stack_mode"] = "archived_actual_z_path"
    member_payload["actual_z_profile_count"] = 0
    region_pts = member_payload.get("region", [])
    member_index = member_payload.get("member_index", "?")
    motif_index = motif_payload.get("motif_index", "?")
    member_label = f"motif {{motif_index}} member {{member_index}}"
    if len(region_pts) < 4:
        return None

    actual_z_loft_profiles = prepare_member_actual_z_loft_profiles(member_payload, member_label)
    actual_z_stack_mode = str(member_payload.get("_actual_z_loft_stack_mode") or "uninitialized")
    root_overlap_pad_mode = None
    try:
        actual_z_profile_count = int(member_payload.get("_actual_z_loft_profile_count", len(actual_z_loft_profiles)))
    except Exception:
        actual_z_profile_count = int(len(actual_z_loft_profiles))
    root_overlap_pad = None
    if len(actual_z_loft_profiles) >= 4:
        root_overlap_pad = build_member_root_overlap_pad(
            member_payload,
            actual_z_loft_profiles,
            member_label
        )
        root_overlap_pad_mode = str(member_payload.get("_root_overlap_pad_mode") or "")
        if root_overlap_pad is not None:
            if root_overlap_pad_mode != "region_clip":
                member_payload["_disable_donor_root_actual"] = True

    prefer_local_section_first = False
    actual_local_section_body = None
    local_section_attempted = False

    if root_overlap_pad is not None:
        print(
            f"[*] {{member_label}} root-anchored routing prefers local-section first: "
            f"mode={{actual_z_stack_mode}}, profiles={{actual_z_profile_count}}"
        )
        actual_local_section_body = build_member_actual_local_section_loft_spoke(
            member_payload,
            motif_payload,
            member_label
        )
        local_section_attempted = True
        if actual_local_section_body is not None:
            actual_local_section_body = safe_union(
                root_overlap_pad,
                actual_local_section_body,
                f"{{member_label}} root-anchored local-section union"
            )
            anchored_local_section_solids = solid_count_of_body(actual_local_section_body)
            if root_overlap_pad_mode == "region_clip" and anchored_local_section_solids > 1:
                print(
                    f"[!] {{member_label}} region-clip root pad produced fragmented local-section; "
                    f"falling back to donor-root capable routing"
                )
                actual_local_section_body = None
                local_section_attempted = False
            elif root_overlap_pad_mode == "region_clip" and anchored_local_section_solids == 1:
                actual_local_section_body = retain_significant_member_fragments(
                    actual_local_section_body,
                    f"{{member_label}} region-clip anchored local-section",
                    max_solids=1
                )
                anchored_local_section_solids = solid_count_of_body(actual_local_section_body)
            print(
                f"[*] {{member_label}} root-anchored local-section built: "
                f"solids={{anchored_local_section_solids}}"
            )
            if actual_local_section_body is not None and anchored_local_section_solids <= 3:
                return actual_local_section_body
        print(f"[!] {{member_label}} root-anchored local-section incomplete; probing actual-direct z-loft")

    if len(actual_z_loft_profiles) >= 4:
        actual_z_loft_body = build_member_loft_from_z_profiles(
            actual_z_loft_profiles,
            f"{{member_label}} actual-direct primary",
            float(member_payload.get("angle", 0.0))
        )
        if actual_z_loft_body is not None:
            actual_z_loft_solid_count = solid_count_of_body(actual_z_loft_body)
            if actual_z_loft_solid_count <= 3:
                if root_overlap_pad is not None:
                    actual_z_loft_body = safe_union(
                        root_overlap_pad,
                        actual_z_loft_body,
                        f"{{member_label}} actual-direct root pad union"
                    )
                print(
                    f"[*] {{member_label}} actual-direct z-loft path selected: "
                    f"mode={{actual_z_stack_mode}}, profiles={{actual_z_profile_count}}, solids={{actual_z_loft_solid_count}}"
                )
                return actual_z_loft_body
            if (not local_section_attempted) and actual_z_loft_solid_count >= 4:
                print(
                    f"[*] {{member_label}} z-loft fragmentation detected: "
                    f"solids={{actual_z_loft_solid_count}}; testing local-section alternative"
                )
                actual_local_section_body = build_member_actual_local_section_loft_spoke(
                    member_payload,
                    motif_payload,
                    member_label
                )
                local_section_attempted = True
                if actual_local_section_body is not None and root_overlap_pad is not None:
                    actual_local_section_body = safe_union(
                        root_overlap_pad,
                        actual_local_section_body,
                        f"{{member_label}} local-section root pad union"
                    )
                local_section_solid_count = solid_count_of_body(actual_local_section_body)
                if (
                    actual_local_section_body is not None and
                    local_section_solid_count > 0 and
                    local_section_solid_count <= max(2, actual_z_loft_solid_count - 1)
                ):
                    print(
                        f"[*] {{member_label}} switching to local-section alternative: "
                        f"z_loft_solids={{actual_z_loft_solid_count}}, "
                        f"local_section_solids={{local_section_solid_count}}"
                    )
                    return actual_local_section_body
                print(
                    f"[*] {{member_label}} keeping z-loft primary after local-section check: "
                    f"z_loft_solids={{actual_z_loft_solid_count}}, "
                    f"local_section_solids={{local_section_solid_count}}"
                )
            actual_z_loft_body = retain_significant_member_fragments(
                actual_z_loft_body,
                f"{{member_label}} actual-direct primary",
                max_solids=3
            )
            print(
                f"[*] {{member_label}} actual-direct z-loft path retained with fragments: "
                f"mode={{actual_z_stack_mode}}, profiles={{actual_z_profile_count}}, solids={{actual_z_loft_solid_count}}"
            )
            return actual_z_loft_body
        print(f"[!] {{member_label}} actual-direct primary z-loft failed")

    if not local_section_attempted:
        actual_local_section_body = build_member_actual_local_section_loft_spoke(
            member_payload,
            motif_payload,
            member_label
        )
        local_section_attempted = True
        if actual_local_section_body is not None:
            if root_overlap_pad is not None:
                actual_local_section_body = safe_union(
                    root_overlap_pad,
                    actual_local_section_body,
                    f"{{member_label}} fallback local-section root pad union"
                )
            print(f"[*] {{member_label}} pure actual local-section path selected")
            return actual_local_section_body

    if len(actual_z_loft_profiles) < 4:
        print(
            f"[!] {{member_label}} actual-direct z-profile stack unavailable: "
            f"count={{len(actual_z_loft_profiles)}}, mode={{actual_z_stack_mode}}"
        )
        return None
    actual_z_loft_body = build_member_loft_from_z_profiles(
        actual_z_loft_profiles,
        f"{{member_label}} actual-direct fallback",
        float(member_payload.get("angle", 0.0))
    )
    if actual_z_loft_body is None:
        print(f"[!] {{member_label}} actual-direct fallback z-loft failed")
        return None
    if root_overlap_pad is not None:
        actual_z_loft_body = safe_union(
            root_overlap_pad,
            actual_z_loft_body,
            f"{{member_label}} fallback z-loft root pad union"
        )
    return actual_z_loft_body

def build_motif_group_bridge(motif_payload):
    if motif_payload.get("motif_type") == "paired_spoke":
        return None
    members = motif_payload.get("members", []) or []
    if len(members) < 2:
        return None

    member_polys = []
    top_z_candidates = []
    for member in members:
        region_pts = member.get("region", [])
        if len(region_pts) < 4:
            continue
        try:
            region_poly = normalize_polygon(Polygon(region_pts))
        except Exception:
            region_poly = None
        if region_poly is None or region_poly.is_empty or region_poly.area < 20.0:
            continue
        member_polys.append(region_poly)
        for section in member.get("sections", []) or []:
            try:
                top_z_candidates.append(float(section.get("z", 0.0)))
            except Exception:
                continue

    if len(member_polys) < 2:
        return None

    merged_poly = normalize_polygon(unary_union(member_polys))
    merged_outer = largest_polygon(merged_poly, min_area=50.0)
    if merged_outer is None:
        return None

    radii = [math.hypot(x, y) for x, y in list(merged_outer.exterior.coords)[:-1]]
    if not radii:
        return None

    inner_r = min(radii)
    outer_r = max(radii)
    span = max(1.0, outer_r - inner_r)
    bridge_outer_r = min(outer_r - 2.0, inner_r + max(12.0, min(24.0, span * 0.28)))
    bridge_inner_r = max(params["hub_radius"] - 1.0, inner_r - 1.5)
    if bridge_outer_r <= bridge_inner_r + 1.0:
        return None

    bridge_outline = [[round(float(x), 3), round(float(y), 3)] for x, y in list(merged_outer.exterior.coords)]
    if bridge_outline and bridge_outline[0] != bridge_outline[-1]:
        bridge_outline.append(bridge_outline[0])
    bridge_profile = clip_void_profile_to_band(bridge_outline, bridge_inner_r, bridge_outer_r, None)
    if len(bridge_profile) < 4:
        return None

    bridge_top = max(top_z_candidates) if top_z_candidates else max(spoke_face_z, params.get("hub_face_z", hub_z_val + 8.0))
    bridge_bottom = max(hub_z_val + 2.0, bridge_top - 4.5)
    try:
        return (
            cq.Workplane("XY")
            .workplane(offset=bridge_bottom)
            .polyline(bridge_profile).close()
            .extrude(max(0.8, bridge_top - bridge_bottom))
        )
    except Exception as bridge_exc:
        print(f"[!] motif {{motif_payload.get('motif_index', '?')}} bridge failed: {{bridge_exc}}")
        return None

def build_spoke_motif_overlay(motif_payloads):
    if not motif_payloads:
        return [], 0, 0

    motif_bodies = []
    built_motif_count = 0
    built_member_count = 0

    for motif_payload in motif_payloads:
        motif_body = None
        motif_member_count = 0
        members = motif_payload.get("members", []) or []
        for member_payload in members:
            member_body = build_motif_member_spoke(member_payload, motif_payload)
            if member_body is None:
                continue
            if motif_body is None:
                motif_body = member_body
            else:
                merged_member = safe_union(
                    motif_body,
                    member_body,
                    f"motif {{motif_payload.get('motif_index', '?')}} member union"
                )
                if merged_member is motif_body:
                    continue
                motif_body = merged_member
            motif_member_count += 1

        if motif_body is None or motif_member_count == 0:
            continue

        bridge_body = build_motif_group_bridge(motif_payload)
        if bridge_body is not None:
            motif_body = safe_union(
                motif_body,
                bridge_body,
                f"motif {{motif_payload.get('motif_index', '?')}} bridge merge"
            )

        motif_bodies.append(motif_body)
        built_motif_count += 1
        built_member_count += motif_member_count

    return motif_bodies, built_motif_count, built_member_count

def build_repeated_spoke_motif_overlay(motif_payloads):
    if not motif_payloads:
        return [], 0, 0

    motif_bodies, built_motif_count, built_member_count = build_spoke_motif_overlay([motif_payloads[0]])
    if not motif_bodies:
        return [], 0, 0

    representative_body = motif_bodies[0]
    motif_count = len(motif_payloads)
    member_count = int((motif_payloads[0].get("member_count", 0) or built_member_count) * motif_count)
    if motif_count <= 1:
        return [representative_body], 1, member_count

    repeated_bodies = [representative_body]
    angle_step = 360.0 / float(motif_count)
    for motif_idx in range(1, motif_count):
        try:
            rotated = (
                cq.Workplane("XY")
                .newObject([representative_body.val()])
                .rotate((0, 0, 0), (0, 0, 1), angle_step * motif_idx)
            )
            repeated_bodies.append(rotated)
        except Exception as rotate_exc:
            print(f"[!] motif additive rotate {{motif_idx}} failed: {{rotate_exc}}")
    return repeated_bodies, len(repeated_bodies), member_count

# 2. Generate Unified Rotary Blank (preferred) with split-body fallback
t_rim_val = params["rim_thickness"]
wheel_min_z = min([p[1] for p in pts]) if pts else (params["hub_z_offset"] - params.get("hub_thickness", 40.0))
rim_max_z = max([p[1] for p in pts]) if pts else params.get("hub_top_z", params["hub_z_offset"] + params.get("hub_thickness", 40.0))
rip_max_r = max([p[0] for p in pts]) if pts else params["rim_max_radius"]
unified_axis_mode = False
pure_guarded_section_revolve_mode = False
spokeless_guarded_revolve_mode = False
spokeless_hybrid_revolve_mode = False
strict_additive_spoke_mode = True
no_spoke_rim_region_active = False
no_spoke_hub_region_active = False
no_spoke_hub_section_region = None
wheel_body = None
rim = None

if disable_spokes_modeling and (spokeless_guarded_section_regions or spokeless_nospoke_regions):
    try:
        rim_region_source = spokeless_guarded_section_regions if spokeless_guarded_section_regions else spokeless_nospoke_regions
        rim_region_source_label = "actual spoke-free section" if spokeless_guarded_section_regions else "reconstructed spoke-free profiles"
        rim_region_desc = None
        for region_idx, region_payload in enumerate(rim_region_source):
            outer_loop = region_payload.get("outer", []) if isinstance(region_payload, dict) else []
            if len(outer_loop) < 4:
                continue
            radii = []
            for point in outer_loop:
                if not isinstance(point, (list, tuple)) or len(point) < 2:
                    continue
                try:
                    radii.append(float(point[0]))
                except Exception:
                    continue
            if not radii:
                continue
            desc = {{
                "index": int(region_idx),
                "outer_r": max(radii),
                "inner_r": min(radii),
                "radial_span": max(radii) - min(radii),
                "area": float(len(outer_loop))
            }}
            if rim_region_desc is None or (
                desc["outer_r"], desc["radial_span"], desc["area"]
            ) > (
                rim_region_desc["outer_r"], rim_region_desc["radial_span"], rim_region_desc["area"]
            ):
                rim_region_desc = desc

        if rim_region_desc is not None:
            region_payload = rim_region_source[int(rim_region_desc["index"])]
            rim = build_rotary_from_section_region(
                {{
                    "outer": list(region_payload.get("outer", [])),
                    "holes": list(region_payload.get("holes", []))
                }},
                0.0,
                rip_max_r,
                "spokeless no-spoke rim body"
            )
            if rim is not None:
                no_spoke_rim_region_active = True
                print(
                    f"[*] No-spoke rim body generated from the {{rim_region_source_label}} "
                    f"(hub-side fragments ignored={{max(0, len(rim_region_source) - 1)}})."
                )
            else:
                print("[!] No-spoke rim fragment revolve failed. Falling back to separate rim profile reconstruction.")

            hub_region_desc = None
            for region_idx, region_payload in enumerate(rim_region_source):
                if int(region_idx) == int(rim_region_desc["index"]):
                    continue
                outer_loop = region_payload.get("outer", []) if isinstance(region_payload, dict) else []
                if len(outer_loop) < 4:
                    continue
                radii = []
                for point in outer_loop:
                    if not isinstance(point, (list, tuple)) or len(point) < 2:
                        continue
                    try:
                        radii.append(float(point[0]))
                    except Exception:
                        continue
                if not radii:
                    continue
                desc = {{
                    "index": int(region_idx),
                    "outer_r": max(radii),
                    "inner_r": min(radii),
                    "radial_span": max(radii) - min(radii),
                    "area": float(len(outer_loop))
                }}
                if desc["outer_r"] >= rim_region_desc["inner_r"] - 1.0:
                    continue
                if hub_region_desc is None or (
                    desc["outer_r"], desc["radial_span"], desc["area"]
                ) > (
                    hub_region_desc["outer_r"], hub_region_desc["radial_span"], hub_region_desc["area"]
                ):
                    hub_region_desc = desc

            if hub_region_desc is not None:
                no_spoke_hub_section_region = rim_region_source[int(hub_region_desc["index"])]
        else:
            print("[!] No-spoke fragmented section baseline unavailable. Falling back to separate rim/hub reconstruction.")
    except Exception as spokeless_nospoke_exc:
        print(f"[!] No-spoke rim fragment build failed: {{spokeless_nospoke_exc}}")
elif (not disable_spokes_modeling) and (not spokeless_guarded_section_regions) and spokeless_baseline_regions:
    try:
        spokeless_bodies = []
        for region_idx, region_payload in enumerate(spokeless_baseline_regions):
            spokeless_revolve_region = {{
                "outer": list(region_payload.get("outer", [])),
                "holes": []
            }}
            region_body = build_rotary_from_section_region(
                spokeless_revolve_region,
                0.0,
                rip_max_r,
                f"spokeless baseline section body {{region_idx}}"
            )
            if region_body is not None:
                spokeless_bodies.append(region_body)
        if spokeless_bodies:
            wheel_body = safe_assemble(spokeless_bodies, "spokeless baseline section body")
            print("[*] Spoke-free baseline regions reduced to hub and rim only for no-spoke export.")
            unified_axis_mode = True
            pure_guarded_section_revolve_mode = True
            spokeless_guarded_revolve_mode = True
    except Exception as spokeless_baseline_exc:
        print(f"[!] Spokeless baseline section body failed: {{spokeless_baseline_exc}}")
elif (not disable_spokes_modeling) and spokeless_guarded_section_regions:
    try:
        actual_region_source = spokeless_guarded_section_regions
        rim_region_desc = None
        hub_region_desc = None
        for region_idx, region_payload in enumerate(actual_region_source):
            outer_loop = region_payload.get("outer", []) if isinstance(region_payload, dict) else []
            if len(outer_loop) < 4:
                continue
            radii = []
            for point in outer_loop:
                if not isinstance(point, (list, tuple)) or len(point) < 2:
                    continue
                try:
                    radii.append(float(point[0]))
                except Exception:
                    continue
            if not radii:
                continue
            desc = {{
                "index": int(region_idx),
                "outer_r": max(radii),
                "inner_r": min(radii),
                "radial_span": max(radii) - min(radii),
                "area": float(len(outer_loop))
            }}
            if rim_region_desc is None or (
                desc["outer_r"], desc["radial_span"], desc["area"]
            ) > (
                rim_region_desc["outer_r"], rim_region_desc["radial_span"], rim_region_desc["area"]
            ):
                rim_region_desc = desc

        if rim_region_desc is not None:
            for region_idx, region_payload in enumerate(actual_region_source):
                if int(region_idx) == int(rim_region_desc["index"]):
                    continue
                outer_loop = region_payload.get("outer", []) if isinstance(region_payload, dict) else []
                if len(outer_loop) < 4:
                    continue
                radii = []
                for point in outer_loop:
                    if not isinstance(point, (list, tuple)) or len(point) < 2:
                        continue
                    try:
                        radii.append(float(point[0]))
                    except Exception:
                        continue
                if not radii:
                    continue
                desc = {{
                    "index": int(region_idx),
                    "outer_r": max(radii),
                    "inner_r": min(radii),
                    "radial_span": max(radii) - min(radii),
                    "area": float(len(outer_loop))
                }}
                if desc["outer_r"] >= rim_region_desc["inner_r"] - 1.0:
                    continue
                if hub_region_desc is None or (
                    desc["outer_r"], desc["radial_span"], desc["area"]
                ) > (
                    hub_region_desc["outer_r"], hub_region_desc["radial_span"], hub_region_desc["area"]
                ):
                    hub_region_desc = desc

        additive_rim_body = None
        additive_hub_body = None
        if rim_region_desc is not None:
            rim_region_payload = actual_region_source[int(rim_region_desc["index"])]
            additive_rim_body = build_rotary_from_section_region(
                {{
                    "outer": list(rim_region_payload.get("outer", [])),
                    "holes": list(rim_region_payload.get("holes", []))
                }},
                0.0,
                rip_max_r,
                "spokeless additive rim body"
            )
        if hub_region_desc is not None:
            hub_region_payload = actual_region_source[int(hub_region_desc["index"])]
            additive_hub_body = build_rotary_from_section_region(
                {{
                    "outer": list(hub_region_payload.get("outer", [])),
                    "holes": list(hub_region_payload.get("holes", []))
                }},
                0.0,
                rip_max_r,
                "spokeless additive hub body"
            )

        if additive_rim_body is not None and additive_hub_body is not None:
            rim = additive_rim_body
            wheel_body = additive_hub_body
            unified_axis_mode = True
            pure_guarded_section_revolve_mode = True
            spokeless_guarded_revolve_mode = True
            print("[*] Spoke-free actual-section hub/rim fragments generated. Additive spokes will reconnect them.")
        else:
            spokeless_bodies = []
            for region_idx, region_payload in enumerate(actual_region_source):
                spokeless_revolve_region = {{
                    "outer": list(region_payload.get("outer", [])),
                    "holes": []
                }}
                region_body = build_rotary_from_section_region(
                    spokeless_revolve_region,
                    0.0,
                    rip_max_r,
                    f"spokeless guarded section body {{region_idx}}"
                )
                if region_body is not None:
                    spokeless_bodies.append(region_body)
            if spokeless_bodies:
                wheel_body = safe_assemble(spokeless_bodies, "spokeless guarded section body")
                print("[*] Spokeless guarded section body generated from window-centered section")
                unified_axis_mode = True
                pure_guarded_section_revolve_mode = True
                spokeless_guarded_revolve_mode = True
                print("[*] Spokeless revolve base active. Spokes will be added, not recovered by window cuts.")
    except Exception as spokeless_body_exc:
        print(f"[!] Spokeless guarded section body failed: {{spokeless_body_exc}}")
elif (not disable_spokes_modeling) and prefer_fragmented_spokeless_base and spokeless_profile_regions:
    try:
        spokeless_bodies = []
        for region_idx, region_payload in enumerate(spokeless_profile_regions):
            spokeless_revolve_region = {{
                "outer": list(region_payload.get("outer", [])),
                "holes": []
            }}
            region_body = build_rotary_from_section_region(
                spokeless_revolve_region,
                0.0,
                rip_max_r,
                f"spokeless profile section body {{region_idx}}"
            )
            if region_body is not None:
                spokeless_bodies.append(region_body)
        if spokeless_bodies:
            wheel_body = safe_assemble(spokeless_bodies, "spokeless profile section body")
            print("[*] Fragmented spoke-free envelope sections preserved. Building disconnected base fragments before additive spokes.")
            unified_axis_mode = True
            pure_guarded_section_revolve_mode = True
            spokeless_guarded_revolve_mode = True
            print("[*] Fragmented spokeless revolve base active. Spokes will reconnect hub and rim.")
    except Exception as spokeless_body_exc:
        print(f"[!] Fragmented spokeless profile-section body failed: {{spokeless_body_exc}}")
elif (not disable_spokes_modeling) and spokeless_hybrid_region and spokeless_hybrid_region.get("outer"):
    try:
        wheel_body = build_rotary_from_section_region(
            {{
                "outer": list(spokeless_hybrid_region.get("outer", [])),
                "holes": list(spokeless_hybrid_region.get("holes", []))
            }},
            0.0,
            rip_max_r,
            "spokeless hybrid section body"
        )
        if wheel_body is not None:
            print("[*] Spokeless hybrid section body generated from full guarded section + local spoke-free replacement")
            unified_axis_mode = True
            pure_guarded_section_revolve_mode = True
            spokeless_guarded_revolve_mode = True
            spokeless_hybrid_revolve_mode = True
            print("[*] Spokeless hybrid revolve base active. Spokes will be added, not recovered by window cuts.")
    except Exception as spokeless_hybrid_exc:
        print(f"[!] Spokeless hybrid section body failed: {{spokeless_hybrid_exc}}")
elif (not disable_spokes_modeling) and spokeless_guarded_section_region:
    try:
        spokeless_revolve_region = {{
            "outer": list(spokeless_guarded_section_region.get("outer", [])),
            "holes": []
        }}
        wheel_body = build_rotary_from_section_region(
            spokeless_revolve_region,
            0.0,
            rip_max_r,
            "spokeless guarded section body"
        )
        if wheel_body is not None:
            print("[*] Spokeless guarded section body generated from window-centered section")
            unified_axis_mode = True
            pure_guarded_section_revolve_mode = True
            spokeless_guarded_revolve_mode = True
            print("[*] Spokeless revolve base active. Spokes will be added, not recovered by window cuts.")
    except Exception as spokeless_body_exc:
        print(f"[!] Spokeless guarded section body failed: {{spokeless_body_exc}}")

if (not disable_spokes_modeling) and (not unified_axis_mode) and enable_guarded_section_modeling and guarded_section_region:
    try:
        guarded_revolve_region = {{
            "outer": list(guarded_section_region.get("outer", [])),
            "holes": []
        }}
        wheel_body = build_rotary_from_section_region(
            guarded_revolve_region,
            0.0,
            rip_max_r,
            "guarded section full body"
        )
        if wheel_body is not None:
            print("[*] Unified guarded section body generated from full preview section")
            unified_axis_mode = True
            pure_guarded_section_revolve_mode = True
            print("[*] Unified full-body modeling enabled. Reverting to perception-driven full rotary reconstruction.")
            print("[*] Pure guarded-section revolve base active. Non-rotary features will be applied after revolve.")
    except Exception as unified_body_exc:
        print(f"[!] Unified guarded section body failed: {{unified_body_exc}}")

if (rim is None) and ((not unified_axis_mode) or ((not disable_spokes_modeling) and spokeless_guarded_revolve_mode and (not spokeless_hybrid_revolve_mode))):
    inner_pts = []
    for p in pts:
        inner_pts.append([p[0] - t_rim_val, p[1]])
    inner_pts.reverse()
    closed_profile = pts + inner_pts
    if disable_spokes_modeling:
        rim = cq.Workplane("XZ").polyline(closed_profile).close().revolve(360, (0, 0, 0), (0, 1, 0))
    else:
        rim = cq.Workplane("XZ").spline(closed_profile).close().revolve(360, (0, 0, 0), (0, 1, 0))

if (not unified_axis_mode) and (not no_spoke_rim_region_active) and enable_rotary_rim_shoulder and len(rotary_face_pts) >= 8:
    try:
        rotary_outer_start_r_raw = derive_rotary_outer_start(spoke_regions, voids, pts, params)
        rotary_overlap_inset = max(2.0, min(4.5, params["rim_thickness"] * 0.15))
        rotary_outer_start_r = max(
            params["hub_radius"] + 25.0,
            rotary_outer_start_r_raw - rotary_overlap_inset
        )
        rotary_rim_cap = build_rotary_band(
            rotary_face_pts,
            rotary_outer_start_r,
            rip_max_r,
            rim_max_z - max(1.5, min(5.0, params["rim_thickness"])),
            "rotary rim shoulder"
        )
        if rotary_rim_cap is not None:
            rim = prefer_single_solid_union(rim, rotary_rim_cap, "rotary rim shoulder merge")
            print(
                f"[*] Rotary rim shoulder merged from R>={{round(rotary_outer_start_r, 2)}} "
                f"(raw={{round(rotary_outer_start_r_raw, 2)}})"
            )
    except Exception as rotary_rim_exc:
        print(f"[!] Rotary rim shoulder merge failed: {{rotary_rim_exc}}")

# 3. Generate Hub (Direct Perception-Driven Reconstruction)
hub_z_val = params["hub_z_offset"]
hub_top_z = params.get("hub_top_z")
if hub_top_z is None and len(hub_pts) > 2:
    hub_top_z = max([p[1] for p in hub_pts])
if hub_top_z is None:
    hub_top_z = hub_z_val + params.get("hub_thickness", 40.0)
hub_top_z = max(hub_z_val + 5.0, float(hub_top_z))
hub_t_val = max(5.0, hub_top_z - hub_z_val)
center_relief_z = params.get("center_relief_z")
if center_relief_z is not None:
    center_relief_z = float(center_relief_z)
pocket_top_z = params.get("pocket_top_z")
pocket_floor_z = params.get("pocket_floor_z")
pocket_outer_r = params.get("pocket_radius")
pocket_floor_r = params.get("pocket_floor_radius")
hub_bottom_groove_floor_z = params.get("hub_bottom_groove_floor_z")
hub_bottom_groove_top_z = params.get("hub_bottom_groove_top_z")
pocket_entry_z = None
has_measured_pockets = all(
    value is not None
    for value in (pocket_top_z, pocket_floor_z, pocket_outer_r, pocket_floor_r)
)
if has_measured_pockets:
    pocket_top_z = min(hub_top_z, float(pocket_top_z))
    pocket_floor_z = max(hub_z_val + 1.0, min(pocket_top_z - 0.5, float(pocket_floor_z)))
    pocket_outer_r = float(pocket_outer_r)
    pocket_floor_r = min(float(pocket_floor_r), pocket_outer_r - 0.5)
    pocket_entry_z = float(pocket_top_z)
    pocket_entry_candidates = []
    for key in ("hub_face_z", "hub_outer_face_z"):
        face_z = params.get(key)
        if face_z is None:
            continue
        try:
            pocket_entry_candidates.append(min(hub_top_z, float(face_z)))
        except Exception:
            continue
    if pocket_entry_candidates:
        pocket_entry_z = min(hub_top_z, max(pocket_entry_z, max(pocket_entry_candidates)))
        if pocket_entry_z > pocket_top_z + 0.05:
            print(
                f"[*] Lug pocket opening plane lifted from Z={{round(pocket_top_z, 2)}} "
                f"to Z={{round(pocket_entry_z, 2)}} using perceived hub face levels"
            )
if hub_bottom_groove_floor_z is not None:
    hub_bottom_groove_floor_z = float(hub_bottom_groove_floor_z)
if hub_bottom_groove_top_z is not None:
    hub_bottom_groove_top_z = min(hub_top_z, float(hub_bottom_groove_top_z))
hub_profile_pts = [list(p) for p in hub_pts]
rotary_center_body = None
section_center_body = None
section_center_limit_r = None
full_guarded_hub_active = False
if enable_guarded_section_modeling and guarded_section_region:
    try:
        center_core_outer_r = 0.0
        core_pts_local = center_core_region.get("points", []) if isinstance(center_core_region, dict) else []
        if len(core_pts_local) >= 4:
            center_core_outer_r = max([math.hypot(x, y) for x, y in core_pts_local[:-1]])
        root_outer_candidates = []
        for root_region in spoke_root_regions:
            pts_root = root_region.get("points", []) if isinstance(root_region, dict) else []
            if len(pts_root) < 4:
                continue
            root_radii = [math.hypot(x, y) for x, y in pts_root[:-1]]
            if root_radii:
                root_outer_candidates.append(max(root_radii))

        section_center_limit_r = max(
            params["bore_radius"] + 3.0,
            center_core_outer_r + 2.8
        )
        if center_core_outer_r > 0.0 and root_outer_candidates:
            root_outer_ref = float(np.median(np.asarray(root_outer_candidates, dtype=float)))
            root_gap = max(0.0, root_outer_ref - center_core_outer_r)
            if root_gap > 4.0:
                root_outer_target_r = root_outer_ref - max(
                    0.28,
                    min(0.72, root_gap * 0.035)
                )
                section_center_limit_r = max(
                    section_center_limit_r,
                    center_core_outer_r + max(
                        3.4,
                        min(root_gap * 0.96, root_gap - 0.45)
                    ),
                    root_outer_target_r
                )
        if disable_spokes_modeling:
            section_center_limit_r = max(
                section_center_limit_r,
                params["hub_radius"] - 0.55
            )
            section_center_limit_r = min(
                params["hub_radius"] - 0.25,
                section_center_limit_r
            )
        else:
            section_center_limit_r = min(
                params["hub_radius"] - 1.4,
                section_center_limit_r
            )
        section_center_body = build_rotary_from_section_region(
            guarded_section_region,
            0.0,
            section_center_limit_r,
            "guarded section center"
        )
        if solid_count_of_body(section_center_body) == 1:
            print(f"[*] Guarded section center body generated to R={{round(section_center_limit_r, 2)}}")
        else:
            if section_center_body is not None:
                print("[!] Guarded section center body discarded: multi-solid or invalid result")
            section_center_body = None
    except Exception as section_center_exc:
        print(f"[!] Guarded section center body failed: {{section_center_exc}}")

if enable_local_rotary_center and section_center_body is None and len(rotary_face_pts) >= 8:
    try:
        center_core_outer_r = 0.0
        core_pts_local = center_core_region.get("points", []) if isinstance(center_core_region, dict) else []
        if len(core_pts_local) >= 4:
            center_core_outer_r = max([math.hypot(x, y) for x, y in core_pts_local[:-1]])
        root_outer_candidates = []
        for root_region in spoke_root_regions:
            pts_root = root_region.get("points", []) if isinstance(root_region, dict) else []
            if len(pts_root) < 4:
                continue
            root_radii = [math.hypot(x, y) for x, y in pts_root[:-1]]
            if root_radii:
                root_outer_candidates.append(max(root_radii))

        rotary_center_limit_r = max(
            params["bore_radius"] + 2.0,
            center_core_outer_r + 2.5
        )
        if center_core_outer_r > 0.0 and root_outer_candidates:
            root_outer_ref = float(np.median(np.asarray(root_outer_candidates, dtype=float)))
            root_gap = max(0.0, root_outer_ref - center_core_outer_r)
            if root_gap > 4.0:
                rotary_center_limit_r = center_core_outer_r + max(
                    2.5,
                    min(root_gap * 0.74, root_gap - 1.8)
                )
        rotary_center_limit_r = min(
            params["hub_radius"] - 1.0,
            rotary_center_limit_r
        )
        rotary_center_body = build_rotary_band(
            rotary_face_pts,
            params["bore_radius"],
            rotary_center_limit_r,
            hub_z_val,
            "rotary center"
        )
        if rotary_center_body is not None:
            print(f"[*] Rotary center body generated to R={{round(rotary_center_limit_r, 2)}}")
    except Exception as rotary_center_exc:
        print(f"[!] Rotary center body failed: {{rotary_center_exc}}")

hub_body = wheel_body if unified_axis_mode else None
if (not unified_axis_mode) and disable_spokes_modeling and no_spoke_hub_section_region is not None:
    try:
        hub_body = build_rotary_from_section_region(
            {{
                "outer": list(no_spoke_hub_section_region.get("outer", [])),
                "holes": list(no_spoke_hub_section_region.get("holes", []))
            }},
            0.0,
            rip_max_r,
            "spokeless no-spoke hub body"
        )
        if solid_count_of_body(hub_body) == 1:
            no_spoke_hub_region_active = True
            print("[*] No-spoke hub body generated from the actual spoke-free section.")
        else:
            hub_body = None
    except Exception as no_spoke_hub_exc:
        print(f"[!] No-spoke hub fragment build failed: {{no_spoke_hub_exc}}")
if (not unified_axis_mode) and (hub_body is None) and len(hub_profile_pts) > 2:
    try:
        profile_wire = list(hub_profile_pts)
        if profile_wire[0] != profile_wire[-1]:
            profile_wire.append(profile_wire[0])
        if disable_spokes_modeling:
            hub_body = cq.Workplane("XZ").polyline(profile_wire).close().revolve(360, (0,0,0), (0,1,0))
        else:
            try:
                hub_body = cq.Workplane("XZ").spline(profile_wire).close().revolve(360, (0,0,0), (0,1,0))
            except Exception:
                hub_body = cq.Workplane("XZ").polyline(profile_wire).close().revolve(360, (0,0,0), (0,1,0))
    except Exception as exc:
        print(f"[!] Hub revolve failed: {{exc}}")

if hub_body is None:
    hub_body = (
        cq.Workplane("XY")
        .workplane(offset=hub_z_val)
        .circle(params["hub_radius"])
        .extrude(hub_t_val)
    )

if (
    disable_spokes_modeling and
    (not no_spoke_hub_region_active) and
    (not unified_axis_mode) and
    section_center_body is not None and
    section_center_limit_r is not None and
    float(section_center_limit_r) >= (params["hub_radius"] - 0.9) and
    solid_count_of_body(section_center_body) == 1
):
    hub_body = section_center_body
    full_guarded_hub_active = True
    print(
        f"[*] No-spoke mode: guarded section revolve adopted as full hub baseline "
        f"to R={{round(section_center_limit_r, 2)}}"
    )

if disable_spokes_modeling:
    print(f"[*] No-spoke debug: hub solids after base build = {{solid_count_of_body(hub_body)}}")

if (not unified_axis_mode) and section_center_body is not None and (not full_guarded_hub_active) and (not no_spoke_hub_region_active):
    replaced_center_body = None
    replace_shell_source = None
    try:
        replace_overlap = 0.22
        replace_prep_r = max(
            params["bore_radius"] + 1.5,
            float(section_center_limit_r) - replace_overlap
        )
        if replace_prep_r <= float(section_center_limit_r) - 0.05:
            replace_prep = (
                cq.Workplane("XY")
                .workplane(offset=hub_z_val - 1.5)
                .circle(replace_prep_r)
                .extrude(hub_t_val + 4.0)
            )
            hub_outer_shell = safe_cut(hub_body, replace_prep, "guarded center shell prep")
            candidate_hub = prefer_single_solid_union(
                hub_outer_shell,
                section_center_body,
                "guarded center replace merge"
            )
            if solid_count_of_body(candidate_hub) == 1:
                replaced_center_body = candidate_hub
                replace_shell_source = "cut-shell"
    except Exception as guarded_replace_exc:
        print(f"[!] Guarded center shell replacement failed: {{guarded_replace_exc}}")

    if replaced_center_body is None:
        try:
            outer_shell_band = build_rotary_band(
                hub_profile_pts,
                max(params["bore_radius"] + 1.5, float(section_center_limit_r) - 0.35),
                params["hub_radius"] + 0.2,
                hub_z_val,
                "guarded center outer shell"
            )
            if outer_shell_band is not None:
                candidate_hub = prefer_single_solid_union(
                    outer_shell_band,
                    section_center_body,
                    "guarded center outer shell merge"
                )
                if solid_count_of_body(candidate_hub) == 1:
                    replaced_center_body = candidate_hub
                    replace_shell_source = "band-shell"
        except Exception as guarded_band_exc:
            print(f"[!] Guarded center outer shell band failed: {{guarded_band_exc}}")

    if replaced_center_body is not None:
        hub_body = replaced_center_body
        print(
            f"[*] Guarded center shell replacement merged to R={{round(section_center_limit_r, 2)}} "
            f"(source={{replace_shell_source or 'unknown'}})"
        )
    else:
        print("[*] Guarded center shell replacement unavailable. Falling back to protected center merge.")
        hub_body = prefer_single_solid_union(hub_body, section_center_body, "guarded section center merge")

if (not unified_axis_mode) and section_center_body is None and rotary_center_body is not None:
    if hub_body is None:
        hub_body = rotary_center_body
    else:
        hub_body = prefer_single_solid_union(hub_body, rotary_center_body, "rotary center merge")

if disable_spokes_modeling:
    print(f"[*] No-spoke debug: hub solids after center reconstruction = {{solid_count_of_body(hub_body)}}")

guarded_center_active = (not unified_axis_mode) and ((section_center_body is not None) or no_spoke_hub_region_active)

if unified_axis_mode:
    bore_cutter = (
        cq.Workplane("XY")
        .workplane(offset=hub_z_val - 1.0)
        .circle(params["bore_radius"])
        .extrude(hub_t_val + 2.0)
    )
    hub_body = safe_cut(hub_body, bore_cutter, "center bore")

if unified_axis_mode:
    unified_center_floor_z = None
    if pocket_top_z is not None:
        unified_center_floor_z = float(pocket_top_z)
    elif center_relief_z is not None:
        unified_center_floor_z = float(center_relief_z)
    unified_center_outer_r = derive_unified_center_outer_radius(
        window_inner_ref_radii,
        params,
        lug_boss_regions
    )
    if spokeless_guarded_revolve_mode:
        print("[*] Spokeless revolve base active. Deferring local center valley relief until spoke merge is stable.")
    elif unified_center_floor_z is not None and unified_center_outer_r is not None:
        if pure_guarded_section_revolve_mode:
            print("[*] Pure guarded-section revolve base active. Applying local non-rotary center relief after revolve.")
        print("[*] Unified annular center relief disabled. Using local valley relief only.")
        hub_body = apply_unified_center_valley_relief(
            hub_body,
            unified_center_floor_z,
            hub_top_z,
            spoke_root_regions,
            lug_boss_regions,
            params["bore_radius"],
            unified_center_outer_r,
            window_inner_ref_radii
        )
    else:
        print("[*] Unified center transition relief skipped: insufficient perception data")
else:
    protected_center_relief_r = None
    if guarded_center_active:
        print("[*] Guarded center replacement active. Skipping center boss relief to preserve continuous perception-driven revolve.")
    elif section_center_body is not None:
        try:
            protected_center_relief_r = max(
                params["bore_radius"] + 1.0,
                float(section_center_limit_r) - 0.08
            )
        except Exception:
            protected_center_relief_r = None
    elif rotary_center_body is not None:
        try:
            protected_center_relief_r = max(
                params["bore_radius"] + 1.0,
                float(rotary_center_limit_r) - 0.35
            )
        except Exception:
            protected_center_relief_r = None
    if not guarded_center_active:
        hub_body = apply_center_boss_relief(
            hub_body,
            center_relief_z,
            hub_top_z,
            center_core_region,
            lug_boss_regions,
            spoke_root_regions,
            params["bore_radius"],
            protected_center_relief_r
        )

if not unified_axis_mode:
    # Cut Center Bore with an absolute cutter, avoiding fragile face projection
    bore_cutter = (
        cq.Workplane("XY")
        .workplane(offset=hub_z_val - 1.0)
        .circle(params["bore_radius"])
        .extrude(hub_t_val + 2.0)
    )
    hub_body = safe_cut(hub_body, bore_cutter, "center bore")

if (not hub_bottom_groove_regions):
    print("[*] Hub rear-face grooves unavailable from perception data. Synthetic groove fallback disabled.")

if hub_bottom_groove_regions and debug_output_root:
    save_hub_face_groove_debug_plot(
        f"{{debug_output_root}}_hub_grooves.png",
        hub_bottom_groove_regions,
        lug_boss_regions,
        center_core_region,
        params["bore_radius"]
    )

def apply_post_revolve_hub_cuts(body):
    pcd_r = params["pcd_radius"]
    hole_r = params["hole_radius"]
    phase = params["pcd_phase_angle"]
    hole_count = max(1, int(params.get("hole_count", params["spoke_num"])))
    if pure_guarded_section_revolve_mode:
        print("[*] Pure guarded-section revolve base active. Applying PCD pockets and bolt-hole cuts after revolve.")
    for i in range(hole_count):
        angle_deg = phase + (360.0 / hole_count) * i
        angle_rad = angle_deg * 3.141592653589793 / 180.0
        x = pcd_r * math.cos(angle_rad)
        y = pcd_r * math.sin(angle_rad)
        lug_pocket_wall = None
        lug_pocket_floor = None
        if has_measured_pockets:
            lug_pocket_wall, lug_pocket_floor = make_lug_pocket_cutter(
                x, y, pocket_entry_z if pocket_entry_z is not None else pocket_top_z, pocket_floor_z, pocket_outer_r, pocket_floor_r
            )
        if guarded_center_active:
            lug_pocket_floor = None
        if lug_pocket_wall is not None:
            body = safe_cut(body, lug_pocket_wall, f"lug pocket {{i}} outer wall")
        if lug_pocket_floor is not None:
            body = safe_cut(body, lug_pocket_floor, f"lug pocket {{i}} floor")
        hole_cutter = (
            cq.Workplane("XY")
            .workplane(offset=hub_z_val - 1.0)
            .center(x, y)
            .circle(hole_r)
            .extrude(hub_t_val + 2.0)
        )
        body = safe_cut(body, hole_cutter, f"pcd hole {{i}}")

    if hub_bottom_groove_regions and hub_bottom_groove_floor_z is not None and hub_bottom_groove_top_z is not None:
        print("[*] Applying rear hub-face grooves after lug-pocket and bolt-hole cuts.")
        body = apply_hub_bottom_groove_relief(
            body,
            hub_bottom_groove_regions,
            hub_bottom_groove_floor_z,
            hub_bottom_groove_top_z,
            params["bore_radius"],
            hub_z_val
        )
    return body

if disable_spokes_modeling:
    print("[*] No-spoke baseline isolation active. Skipping post-revolve PCD/pocket/groove cuts.")
elif fast_spoke_validation_mode:
    print("[*] Fast spoke validation mode active. Skipping post-revolve hub cuts for spoke-focused comparison.")
elif (not spokeless_guarded_revolve_mode) or spokeless_hybrid_revolve_mode:
    hub_body = apply_post_revolve_hub_cuts(hub_body)

# 4. Generate Spokes / Windows
spokes_disc = None
if unified_axis_mode:
    if disable_spokes_modeling:
        if pure_guarded_section_revolve_mode:
            print("[*] Pure guarded-section revolve base active. Spoke generation disabled; preserving stable hub/rim baseline.")
        if spokeless_guarded_revolve_mode:
            print("[*] Spokeless revolve base active. Returning spoke-free baseline without additive spokes.")
        if spokeless_guarded_revolve_mode and rim is not None:
            result = safe_assemble([rim, hub_body], "spokeless no-spoke final assembly")
        else:
            result = hub_body
    else:
        if pure_guarded_section_revolve_mode:
            print("[*] Pure guarded-section revolve base active. Applying spoke/window cuts after revolve.")
        additive_ready = bool(spoke_motif_groups)
        if strict_additive_spoke_mode and additive_ready:
            print("[*] Strict additive-spoke mode active. Forcing motif additive branch and disabling window subtraction.")
            spokeless_guarded_revolve_mode = True
        if spokeless_guarded_revolve_mode:
            print("[*] Spokeless revolve base active. Skipping subtractive spoke window cuts.")
            motif_type = spoke_motif_topology.get("motif_type", "unknown") if isinstance(spoke_motif_topology, dict) else "unknown"
            if spoke_motif_groups:
                try:
                    spokeless_members = build_spokeless_spoke_members(spoke_motif_groups)
                    if spokeless_members:
                        # Current priority is point-cloud fidelity and export completion.
                        # With simplified pure actual local-section members, re-attempt
                        # spoke-to-base booleans for small single/dual-solid members first
                        # so the exported surface sheds internal overlap faces. Larger
                        # residual fragment groups still fall back to a direct compound.
                        non_boolean_spoke_compound_mode = False
                        aggressive_spokeless_compound_mode = False
                        hub_cuts_applied_before_spoke_compound = False
                        if (
                            (not fast_spoke_validation_mode) and
                            (not spokeless_hybrid_revolve_mode) and
                            (not non_boolean_spoke_compound_mode)
                        ):
                            print("[*] Applying post-revolve hub cuts to base before direct spoke compound assembly.")
                            hub_body = apply_post_revolve_hub_cuts(hub_body)
                            hub_cuts_applied_before_spoke_compound = True
                        working_components = [hub_body]
                        if rim is not None:
                            working_components.append(rim)
                        base_component_count = len(working_components)
                        compound_spoke_parts = []
                        merged_member_count = 0
                        compound_staged_member_count = 0
                        merged_bridge_count = 0
                        attempted_member_count = len(spokeless_members)
                        ordered_spokeless_members = sorted(
                            spokeless_members,
                            key=lambda item: (
                                len(item[2].get("actual_z_profiles", []) or []),
                                body_volume(item[1]) or 0.0
                            ),
                            reverse=True
                        )
                        rejected_spokeless_members = []
                        for member_index, member_body, member_payload, motif_payload in ordered_spokeless_members:
                            if aggressive_spokeless_compound_mode:
                                member_fragments = explode_body_to_single_solids(member_body)
                                if member_fragments:
                                    compound_spoke_parts.extend(member_fragments)
                                    merged_member_count += 1
                                    non_boolean_spoke_compound_mode = True
                                    print(
                                        f"[*] spokeless additive member {{member_index}} routed directly to compound assembly: "
                                        f"fragments={{len(member_fragments)}}"
                                    )
                                else:
                                    rejected_spokeless_members.append((member_index, member_body, member_payload, motif_payload))
                                    print(
                                        f"[!] spokeless additive member {{member_index}} discarded before compound staging: "
                                        f"member_solids={{solid_count_of_body(member_body)}}"
                                    )
                                continue
                            dual_split_payloads = build_dual_split_member_payloads(member_payload)
                            if dual_split_payloads:
                                trial_components = list(working_components)
                                dual_split_ok = True
                                dual_split_merged_parts = 0
                                split_r = float(dual_split_payloads[0][1].get("_dual_split_r", 0.0))
                                print(
                                    f"[*] spokeless additive member {{member_index}} dual-split attempt: "
                                    f"split_r={{split_r:.2f}}, parts={{len(dual_split_payloads)}}"
                                )
                                for split_role, split_payload in dual_split_payloads:
                                    trial_components = sort_components_by_radial_extent(trial_components)
                                    split_label = f"spokeless additive member {{member_index}} {{split_role}}"
                                    split_body = build_member_actual_local_section_loft_spoke(
                                        split_payload,
                                        motif_payload,
                                        split_label
                                    )
                                    if split_body is None:
                                        dual_split_ok = False
                                        print(f"[!] {{split_label}} dual-split build failed")
                                        break
                                    trial_components, split_merged, _ = merge_member_into_components(
                                        trial_components,
                                        split_body,
                                        split_label,
                                        allow_nearby_standalone=(split_role == "outer"),
                                        preferred_component_indices=([1, 0] if split_role == "outer" else [0, 1])
                                    )
                                    if not split_merged:
                                        dual_split_ok = False
                                        print(f"[!] {{split_label}} dual-split merge failed")
                                        break
                                    trial_components = sort_components_by_radial_extent(trial_components)
                                    dual_split_merged_parts += 1
                                if dual_split_ok and dual_split_merged_parts == len(dual_split_payloads):
                                    working_components = trial_components
                                    merged_member_count += 1
                                    print(
                                        f"[*] spokeless additive member {{member_index}} dual-split merged: "
                                        f"parts={{dual_split_merged_parts}}, components={{len(working_components)}}"
                                    )
                                    continue
                                print(f"[!] spokeless additive member {{member_index}} dual-split fell back to single-body path")
                            member_solid_count = solid_count_of_body(member_body)
                            if non_boolean_spoke_compound_mode:
                                member_fragments = explode_body_to_single_solids(member_body)
                                if member_fragments:
                                    compound_spoke_parts.extend(member_fragments)
                                    merged_member_count += 1
                                    print(
                                        f"[*] spokeless additive member {{member_index}} appended as compound fragments: "
                                        f"count={{len(member_fragments)}}"
                                    )
                                else:
                                    rejected_spokeless_members.append((member_index, member_body, member_payload, motif_payload))
                                continue
                            if member_solid_count > 2:
                                member_fragments = explode_body_to_single_solids(member_body)
                                if member_fragments:
                                    compound_spoke_parts.extend(member_fragments)
                                    compound_staged_member_count += 1
                                    print(
                                        f"[*] spokeless additive member {{member_index}} staged for direct compound fallback: "
                                        f"fragments={{len(member_fragments)}}, member_solids={{member_solid_count}}"
                                    )
                                else:
                                    rejected_spokeless_members.append((member_index, member_body, member_payload, motif_payload))
                                    print(
                                        f"[!] spokeless additive member {{member_index}} discarded before boolean merge: "
                                        f"member_solids={{member_solid_count}}"
                                    )
                                continue
                            working_components, member_merged, component_count_after_merge = merge_member_into_components(
                                working_components,
                                member_body,
                                f"spokeless additive member {{member_index}}",
                                allow_nearby_standalone=False
                            )
                            if member_merged:
                                merged_member_count += 1
                            else:
                                member_fragments = explode_body_to_single_solids(member_body)
                                if member_fragments:
                                    compound_spoke_parts.extend(member_fragments)
                                    compound_staged_member_count += 1
                                    print(
                                        f"[*] spokeless additive member {{member_index}} staged for direct compound fallback: "
                                        f"fragments={{len(member_fragments)}}, component_count={{len(working_components)}}"
                                    )
                                else:
                                    rejected_spokeless_members.append((member_index, member_body, member_payload, motif_payload))
                                    print(
                                        f"[!] spokeless additive member {{member_index}} discarded in pure loft mode: "
                                        f"component_count={{len(working_components)}}"
                                    )
                        if rejected_spokeless_members and len(working_components) <= base_component_count:
                            print(
                                f"[*] Retrying {{len(rejected_spokeless_members)}} rejected spoke members "
                                f"against the unified base body"
                            )
                            for member_index, member_body, member_payload, motif_payload in rejected_spokeless_members:
                                working_components, member_merged, component_count_after_merge = merge_member_into_components(
                                    working_components,
                                    member_body,
                                    f"spokeless additive member {{member_index}} retry",
                                    allow_nearby_standalone=False
                                )
                                if member_merged:
                                    merged_member_count += 1
                                    print(f"[*] spokeless additive member {{member_index}} recovered on retry")
                                else:
                                    member_fragments = explode_body_to_single_solids(member_body)
                                    if member_fragments:
                                        compound_spoke_parts.extend(member_fragments)
                                        compound_staged_member_count += 1
                                        print(
                                            f"[*] spokeless additive member {{member_index}} retry staged for direct compound fallback: "
                                            f"fragments={{len(member_fragments)}}"
                                        )
                        working_components = consolidate_overlapping_components(
                            working_components,
                            "spokeless additive component consolidation",
                            min_overlap_volume=500.0
                        )
                        if compound_spoke_parts:
                            non_boolean_spoke_compound_mode = True
                        if non_boolean_spoke_compound_mode and compound_spoke_parts:
                            working_components.extend(compound_spoke_parts)
                            print(
                                f"[*] Direct compound fallback active for staged spoke members: "
                                f"members={{compound_staged_member_count}}, spoke_parts={{len(compound_spoke_parts)}}"
                            )
                        if non_boolean_spoke_compound_mode:
                            working_body = direct_compound_assembly(
                                working_components,
                                "spokeless additive final assembly"
                            )
                        else:
                            try:
                                working_body = safe_assemble(
                                    working_components,
                                    "spokeless additive final assembly",
                                    allow_compound_fallback=False
                                )
                            except Exception as exc:
                                print(
                                    f"[!] Spokeless additive strict assembly failed; "
                                    f"falling back to direct compound: {{exc}}"
                                )
                                working_body = direct_compound_assembly(
                                    working_components,
                                    "spokeless additive final assembly fallback"
                                )
                        working_solid_count = solid_count_of_body(working_body)
                        print(
                            f"[*] Spokeless additive spoke members prepared: "
                            f"type={{motif_type}}, members={{attempted_member_count}}, merged={{merged_member_count}}, "
                            f"staged={{compound_staged_member_count}}, "
                            f"solids={{working_solid_count}}"
                        )
                        if merged_bridge_count > 0:
                            print(
                                f"[*] Spokeless rim-bridge helpers prepared: merged={{merged_bridge_count}}, "
                                f"components={{len(working_components)}}"
                            )
                        covered_member_count = merged_member_count + compound_staged_member_count
                        if covered_member_count <= 0:
                            raise ValueError("Spokeless additive spoke members did not produce any retained geometry.")
                        if covered_member_count != attempted_member_count:
                            raise ValueError(
                                f"Strict actual-direct spoke coverage incomplete: "
                                f"covered={{covered_member_count}}/{{attempted_member_count}}, "
                                f"merged={{merged_member_count}}, staged={{compound_staged_member_count}}"
                            )
                        hub_body = working_body
                        print(f"[*] Spokeless additive component count after merge: {{len(working_components)}}")
                        rim = None
                        if not spokeless_hybrid_revolve_mode:
                            if fast_spoke_validation_mode:
                                print("[*] Fast spoke validation mode active. Deferred hub cuts after additive spoke merge.")
                            elif hub_cuts_applied_before_spoke_compound:
                                print("[*] Post-revolve hub cuts already applied to base before additive spoke compound merge.")
                            else:
                                hub_body = apply_post_revolve_hub_cuts(hub_body)
                    else:
                        raise ValueError("Spokeless additive spoke members were not created from motif groups")
                except Exception as spokeless_motif_exc:
                    import traceback
                    safe_print(traceback.format_exc().rstrip())
                    print(f"[!] Spokeless additive spoke members failed: {{spokeless_motif_exc}}")
                    raise
        elif not strict_additive_spoke_mode:
            window_cut_count = 0
            local_keepout_count = 0
            guarded_lower_stage_count = 0
            # Window depth should be driven by the hub/backface relationship, not by lug-pocket floor.
            # Tying it to pocket_floor_z was leaving a large uncut slab behind the visible windows.
            window_cut_bottom = max(hub_z_val - 1.0, wheel_min_z + 5.0)
            window_cut_bottom = min(window_cut_bottom, rim_max_z - 5.0)
            window_cut_height = max(5.0, (rim_max_z - window_cut_bottom) + 2.0)
            window_cut_top = window_cut_bottom + window_cut_height
            root_outer_r_vals = []
            spoke_inner_r_vals = []
            spoke_outer_r_vals = []
            for region in spoke_root_regions:
                pts_region = region.get("points", []) if isinstance(region, dict) else region
                if len(pts_region) < 4:
                    continue
                radii = [math.hypot(x, y) for x, y in pts_region[:-1]]
                if radii:
                    root_outer_r_vals.append(max(radii))
            for region in spoke_regions:
                pts_region = region.get("points", []) if isinstance(region, dict) else region
                if len(pts_region) < 4:
                    continue
                radii = [math.hypot(x, y) for x, y in pts_region[:-1]]
                if radii:
                    spoke_inner_r_vals.append(min(radii))
                    spoke_outer_r_vals.append(max(radii))

            if root_outer_r_vals and spoke_outer_r_vals:
                root_transition_pad = 0.0
                if spoke_inner_r_vals:
                    root_transition_pad = max(
                        0.0,
                        float(np.median(np.asarray(spoke_inner_r_vals, dtype=float))) -
                        float(np.median(np.asarray(root_outer_r_vals, dtype=float)))
                    )
                root_guard_r = max(root_outer_r_vals) + 1.2
                spoke_guard_r = float(np.median(np.asarray(spoke_inner_r_vals, dtype=float))) + 1.0 if spoke_inner_r_vals else root_guard_r
                hub_guard_r = params["hub_radius"] + 0.8
                window_inner_r = max(root_guard_r, spoke_guard_r, hub_guard_r)
                window_outer_r = min(spoke_outer_r_vals) - 1.0
            elif spoke_inner_r_vals and spoke_outer_r_vals:
                window_inner_r = max(
                    params["hub_radius"] + 0.8,
                    float(np.median(np.asarray(spoke_inner_r_vals, dtype=float))) + 1.0
                )
                window_outer_r = min(spoke_outer_r_vals) - 1.0
            else:
                window_inner_r = params["hub_radius"] + 2.0
                window_outer_r = params["rim_max_radius"] - max(8.0, params["rim_thickness"] * 3.0)

            section_window_inner_r = params.get("window_inner_reference_r")
            if section_window_inner_r is not None:
                window_inner_r = max(window_inner_r, float(section_window_inner_r))
            window_inner_r = max(params["bore_radius"] + 6.0, window_inner_r)
            window_outer_r = min(params["rim_max_radius"] - 6.0, window_outer_r)
            center_keepout = build_region_keepout(
                lug_boss_regions + spoke_root_regions,
                buffer_radius=root_transition_pad if 'root_transition_pad' in locals() else 0.0,
                min_area=18.0
            )
            keepout_desc = "none"
            if center_keepout is not None and not center_keepout.is_empty:
                keepout_desc = f"buffer={{round(root_transition_pad if 'root_transition_pad' in locals() else 0.0, 2)}}"
            print(f"[*] Unified window cut band: Z={{round(window_cut_bottom, 2)}} -> {{round(rim_max_z, 2)}}, R={{round(window_inner_r, 2)}} -> {{round(window_outer_r, 2)}}, keepout={{keepout_desc}}")
            motif_type = spoke_motif_topology.get("motif_type", "unknown") if isinstance(spoke_motif_topology, dict) else "unknown"
            window_member_keepouts = []
            if spoke_motif_groups:
                print(
                    f"[*] Motif-driven spoke keepouts disabled for additive-spoke mode: type={{motif_type}}"
                )
            window_transition_z = unified_center_floor_z if 'unified_center_floor_z' in locals() else None
            if window_transition_z is None:
                window_transition_z = pocket_top_z
            if window_transition_z is None:
                window_transition_z = center_relief_z
            if window_transition_z is None:
                window_transition_z = window_cut_bottom + (window_cut_height * 0.55)
            window_transition_z = max(window_cut_bottom + 1.0, min(window_cut_top - 1.0, float(window_transition_z)))
        if not spokeless_guarded_revolve_mode:
            for i, void in enumerate(voids):
                void_pts = void.get("points", [])
                if len(void_pts) < 4:
                    continue
                try:
                    local_window_inner_r = window_inner_r
                    if i < len(window_inner_ref_radii):
                        local_ref_r = window_inner_ref_radii[i]
                        if local_ref_r is not None:
                            local_window_inner_r = max(local_window_inner_r, float(local_ref_r))

                    lower_stage_keepout = center_keepout
                    local_keepout_regions = window_local_keepouts[i] if i < len(window_local_keepouts) else []
                    if local_keepout_regions:
                        local_keepout = build_region_keepout(
                            local_keepout_regions,
                            buffer_radius=root_transition_pad if 'root_transition_pad' in locals() else 0.0,
                            min_area=12.0
                        )
                        if local_keepout is not None and not local_keepout.is_empty:
                            lower_stage_keepout = local_keepout
                            local_keepout_count += 1

                    clipped_void_pts = clip_void_profile_to_band(
                        void_pts,
                        local_window_inner_r,
                        window_outer_r,
                        None
                    )
                    if len(clipped_void_pts) < 4:
                        continue

                    lower_window_inner_r = local_window_inner_r
                    if i < len(window_local_root_outer_radii):
                        local_root_outer_r = window_local_root_outer_radii[i]
                        if local_root_outer_r is not None:
                            local_root_gap = max(0.0, float(local_window_inner_r) - float(local_root_outer_r))
                            if local_root_gap > 0.35:
                                lower_window_inner_r = min(
                                    window_outer_r - 1.5,
                                    local_window_inner_r + max(0.6, local_root_gap * 0.45)
                                )

                    lower_stage_cutter = None
                    if lower_window_inner_r > local_window_inner_r + 0.2 and window_transition_z > window_cut_bottom + 1.0:
                        lower_void_pts = clip_void_profile_to_band(
                            void_pts,
                            lower_window_inner_r,
                            window_outer_r,
                            lower_stage_keepout
                        )
                        lower_stage_height = max(0.0, window_transition_z - window_cut_bottom)
                        if len(lower_void_pts) >= 4 and lower_stage_height > 0.8:
                            lower_stage_cutter = build_polygon_transition_cutter(
                                lower_void_pts,
                                clipped_void_pts,
                                window_cut_bottom,
                                window_transition_z
                            )
                            if lower_stage_cutter is None:
                                lower_stage_cutter = build_polygon_prism(lower_void_pts, window_cut_bottom, lower_stage_height)

                    upper_stage_z = window_transition_z if lower_stage_cutter is not None else window_cut_bottom
                    upper_stage_height = max(0.0, window_cut_top - upper_stage_z)
                    if upper_stage_height <= 0.8:
                        continue
                    upper_stage_cutter = build_polygon_prism(clipped_void_pts, upper_stage_z, upper_stage_height)
                    if upper_stage_cutter is None:
                        continue

                    if lower_stage_cutter is not None:
                        hub_body = safe_cut(hub_body, lower_stage_cutter, f"spoke window lower {{i}}")
                        guarded_lower_stage_count += 1
                    hub_body = safe_cut(hub_body, upper_stage_cutter, f"spoke window {{i}}")
                    window_cut_count += 1
                except Exception as window_exc:
                    print(f"[!] Spoke window {{i}} cut failed: {{window_exc}}")
            print(
                f"[*] Unified spoke windows cut: {{window_cut_count}} "
                f"(local keepouts={{local_keepout_count}}, guarded lower stages={{guarded_lower_stage_count}})"
            )
            if pure_guarded_section_revolve_mode and spoke_motif_groups:
                additive_motif_count = 0
                additive_member_count = 0
                try:
                    motif_bodies, built_motif_count, built_member_count = build_repeated_spoke_motif_overlay(spoke_motif_groups)
                    if motif_bodies:
                        for motif_idx, motif_body in enumerate(motif_bodies):
                            merged_body = prefer_single_solid_union(
                                hub_body,
                                motif_body,
                                f"motif additive spoke {{motif_idx}}"
                            )
                            if merged_body is hub_body:
                                continue
                            hub_body = merged_body
                            additive_motif_count += 1
                        additive_member_count = built_member_count
                    print(
                        f"[*] Motif-driven additive spokes merged after window cuts: "
                        f"motifs={{additive_motif_count}}/{{built_motif_count}}, members={{additive_member_count}}"
                    )
                except Exception as motif_overlay_exc:
                    print(f"[!] Motif-driven additive spokes failed: {{motif_overlay_exc}}")
        elif strict_additive_spoke_mode and (not additive_ready):
            print("[!] Strict additive-spoke mode enabled but motif groups unavailable; window subtraction skipped.")
        if spokeless_guarded_revolve_mode and rim is not None:
            result = safe_assemble([rim, hub_body], "spokeless final assembly")
        else:
            result = hub_body
else:
    pass

if (not unified_axis_mode) and disable_spokes_modeling:
    print("[*] Structural spoke engine disabled. Returning stable hub/rim baseline only.")
    print(
        f"[*] No-spoke baseline solid counts: "
        f"rim={{solid_count_of_body(rim)}}, hub={{solid_count_of_body(hub_body)}}"
    )
    result = safe_assemble([rim, hub_body], "no-spoke final assembly")
elif not unified_axis_mode:
    # 4. Generate Spokes (Structural Bridge Mode)
    hub_r = params["hub_radius"]
    spoke_z0 = hub_z_val - 0.25
    spoke_h_val = hub_t_val + 0.5
    spoke_core_top_z = rim_max_z - 0.8
    if spoke_face_z > 0:
        spoke_core_top_z = min(spoke_core_top_z, spoke_face_z - 0.35)
    spoke_core_top_z = max(spoke_z0 + 8.0, spoke_core_top_z)
    spoke_core_h_val = max(3.0, spoke_core_top_z - spoke_z0)
    spokes_disc = None

    print(f"[*] Executing Structural Spoke Engine... Voids: {{len(voids)}}")
    try:
        derived_regions = []
        for region in spoke_regions:
            pts_region = region.get("points", [])
            if len(pts_region) >= 4:
                derived_regions.append(pts_region)

        if len(derived_regions) == 0:
            derived_regions = build_spoke_regions(spoke_face_boundary, voids, hub_r)

        print(f"[*] Structural spoke regions derived: {{len(derived_regions)}}")
        if len(derived_regions) == 0:
            raise ValueError("No spoke regions available")

        tip_loft_count = 0
        print("[*] Stable region extrusion active. Applying guarded pre-extracted tip lofts where possible.")
        print(f"[*] Stable spoke core top Z: {{round(spoke_core_top_z, 2)}}")
        for i, region in enumerate(derived_regions):
            spoke_solid = (
                cq.Workplane("XY")
                .workplane(offset=spoke_z0)
                .polyline(region).close()
                .extrude(spoke_core_h_val)
            )
            if i < len(spoke_tip_section_groups):
                tip_group = spoke_tip_section_groups[i].get("sections", [])
                try:
                    tip_loft = build_tip_section_loft(region, tip_group, i)
                    if tip_loft is not None:
                        merged_spoke = safe_union(spoke_solid, tip_loft, f"spoke {{i}} tip loft")
                        if merged_spoke is not spoke_solid:
                            spoke_solid = merged_spoke
                            tip_loft_count += 1
                except Exception as tip_exc:
                    print(f"[!] Spoke {{i}} tip loft failed: {{tip_exc}}")
            if spokes_disc is None:
                spokes_disc = spoke_solid
            else:
                spokes_disc = safe_union(spokes_disc, spoke_solid, f"spoke {{i}}")

        print(f"[*] Spoke tip lofts applied: {{tip_loft_count}}")
        if spokes_disc is None:
            raise ValueError("Spoke solids were not created")
    except Exception as e:
        print(f"[!] Structural Spoke Engine Failed: {{e}}. Switching to fallback spoke engine...")
        rim_inner_limit_r = params["rim_max_radius"]
        for p in pts:
            rim_inner_limit_r = min(rim_inner_limit_r, p[0] - t_rim_val)

        slot_length = max(20.0, rim_inner_limit_r - hub_r)
        slot_width = max(12.0, params.get("spoke_width", 20.0) * 0.7)
        slot_radius = hub_r + (slot_length * 0.5)
        spokes_disc = (
            cq.Workplane("XY")
            .workplane(offset=spoke_z0)
            .transformed(rotate=cq.Vector(0, 0, params["pcd_phase_angle"]))
            .polarArray(slot_radius, 0, 360, params["spoke_num"])
            .slot2D(slot_length, slot_width)
            .extrude(spoke_h_val)
        )

    # 5. Final Assembly
    result = safe_assemble([rim, hub_body, spokes_disc], "final assembly")
    """
    return code
