"""
=============================================================================
STL Reverse Engineering Pipeline (Auto-Wheel)
=============================================================================
?????
    1. ???????? STL ???
    2. ????????(Pose Alignment)
    3. ?????? (Perception Module):
       - ??????? (Rim Profile) + RDP ????????
       - ??????? (Spoke Sections) + Loft ??
       - ????????????? (Dynamic Dimensioning)
    4. ????????(Modeling Module):
       - ??? CadQuery ??? (Mock Mode / LLM Mode)
       - ???????(Polyline Rim + Loft Spoke + Fallback Mechanisms)
    5. ??? STEP ??????

???? Trae AI Assistant
???: 2026-03-08
???: v2.5 (Robust Production)
=============================================================================
"""
LEGACY IMPLEMENTATION SURFACE.

Do not mine this file for alternative spoke, groove, actual_z, or revolve strategies.
The active accepted route is pinned in tools/build_current_wheel_model.py.
Historical branches remain here only until they can be moved behind a clean implementation boundary.

"""
"""

import argparse
import builtins
import os
import sys
import json
import re
import math
import site
import time

_extra_site_paths = []
try:
    _user_site = site.getusersitepackages()
    if _user_site:
        _extra_site_paths.append(_user_site)
except Exception:
    pass

_extra_site_paths.append(
    os.path.join(
        os.path.expanduser("~"),
        "AppData",
        "Roaming",
        "Python",
        f"Python{sys.version_info.major}{sys.version_info.minor}",
        "site-packages"
    )
)

for _site_path in _extra_site_paths:
    if _site_path and os.path.isdir(_site_path) and _site_path not in sys.path:
        sys.path.append(_site_path)

import numpy as np
import trimesh
import cadquery as cq
try:
    from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
    from OCP.Interface import Interface_Static
    from OCP.IFSelect import IFSelect_RetDone
    OCP_STEP_EXPORT_AVAILABLE = True
except Exception:
    STEPControl_Writer = None
    STEPControl_AsIs = None
    Interface_Static = None
    IFSelect_RetDone = None
    OCP_STEP_EXPORT_AVAILABLE = False
from scipy.signal import savgol_filter
from scipy.interpolate import splprep, splev
from shapely.geometry import Point, Polygon, MultiPolygon, MultiLineString, LineString, GeometryCollection
from shapely.ops import unary_union, linemerge, polygonize
from shapely.prepared import prep
from pipeline_modeling_codegen import generate_cadquery_code
from pipeline_noncore import (
    create_perception_preview,
    create_spokeless_section_preview,
    downsample_curve,
    ensure_timestamped_step_path,
    generate_evaluation_comparison_bundle,
    save_hub_face_groove_debug_plot,
)


def safe_print(*args, **kwargs):
    try:
        builtins.print(*args, **kwargs)
    except (OSError, ValueError):
        pass

# =============================================================================
# 1. ????????(Helper Algorithms)
# =============================================================================

def rdp_simplify(points, epsilon):
    """
    Ramer-Douglas-Peucker (RDP) ????????????????????????
    ???????????????????????????????
    """
    if len(points) < 3:
        return points
    
    points_arr = np.array(points)
    start = points_arr[0]
    end = points_arr[-1]
    
    line_vec = end - start
    line_len = np.linalg.norm(line_vec)
    
    dmax = 0.0
    index = 0
    
    if line_len == 0:
        for i in range(1, len(points) - 1):
            d = np.linalg.norm(points_arr[i] - start)
            if d > dmax:
                index = i
                dmax = d
    else:
        # ?????????????????
        for i in range(1, len(points) - 1):
            p = points_arr[i]
            # 2D Cross product equivalent
            cross_prod = (end[0] - start[0]) * (start[1] - p[1]) - (start[1] - end[1]) * (start[0] - p[0])
            d = abs(cross_prod) / line_len
            if d > dmax:
                index = i
                dmax = d
            
    if dmax > epsilon:
        rec_results1 = rdp_simplify(points[:index+1], epsilon)
        rec_results2 = rdp_simplify(points[index:], epsilon)
        return rec_results1[:-1] + rec_results2
    else:
        return [points[0], points[-1]]

def optimize_profile_points(points, target_min=40, target_max=80):
    """
    ???? RDP ???????????epsilon ???????????????????????
    """
    if len(points) <= target_max:
        return points
        
    epsilon = 0.1
    max_iter = 10
    
    print(f"[*] ?????????? ????? {len(points)} ...")
    
    for _ in range(max_iter):
        simplified = rdp_simplify(points, epsilon)
        count = len(simplified)
        
        if target_min <= count <= target_max:
            print(f"[*] ??????: {len(points)} -> {count} (epsilon={epsilon:.2f})")
            return simplified
        
        if count > target_max:
            epsilon *= 1.5 # ?????????????
        else:
            if count < target_min and epsilon > 0.01:
                 epsilon /= 2.0 # ?????????????
            else:
                print(f"[*] ??????: {len(points)} -> {count} (epsilon={epsilon:.2f})")
                return simplified
            
    return simplified

def regularize_rim_profile_points(points, target_min=28, target_max=48):
    """Smooth a rim profile conservatively and remove high-frequency waviness."""
    if not points:
        return []
    profile = [[float(p[0]), float(p[1])] for p in points]
    profile = sorted(profile, key=lambda item: item[1])
    if len(profile) < 6:
        return [[round(x, 3), round(z, 3)] for x, z in profile]

    z_vals = np.asarray([item[1] for item in profile], dtype=float)
    x_vals = np.asarray([item[0] for item in profile], dtype=float)

    def smooth_axis(values, preferred_window):
        if len(values) < 5:
            return np.asarray(values, dtype=float)
        window = min(int(preferred_window), len(values) if len(values) % 2 == 1 else len(values) - 1)
        if window < 5:
            window = 5 if len(values) >= 5 else len(values)
        if window % 2 == 0:
            window -= 1
        if window < 5:
            return np.asarray(values, dtype=float)
        polyorder = 2 if window >= 5 else 1
        return savgol_filter(np.asarray(values, dtype=float), window_length=window, polyorder=polyorder)

    x_smooth = smooth_axis(x_vals, 17)
    x_smooth = smooth_axis(x_smooth, 9)
    smoothed = [[float(x), float(z)] for x, z in zip(x_smooth, z_vals)]

    dewiggled = [smoothed[0]]
    for idx in range(1, len(smoothed) - 1):
        prev_x, prev_z = dewiggled[-1]
        curr_x, curr_z = smoothed[idx]
        next_x, next_z = smoothed[idx + 1]
        local_span_z = abs(next_z - prev_z)
        local_amp = abs(curr_x - ((prev_x + next_x) * 0.5))
        if local_span_z <= 6.0 and local_amp <= 0.22:
            dewiggled.append([float((prev_x + next_x) * 0.5), float(curr_z)])
        else:
            dewiggled.append([curr_x, curr_z])
    dewiggled.append(smoothed[-1])

    simplified = optimize_profile_points(dewiggled, target_min=target_min, target_max=target_max)
    if len(simplified) > target_max:
        simplified = sorted(simplified, key=lambda item: item[1])
        z_src = np.asarray([item[1] for item in simplified], dtype=float)
        x_src = np.asarray([item[0] for item in simplified], dtype=float)
        if len(z_src) >= 4 and float(np.max(z_src) - np.min(z_src)) > 1e-6:
            sample_count = max(target_min, min(target_max, 40))
            z_dst = np.linspace(float(np.min(z_src)), float(np.max(z_src)), sample_count)
            x_dst = np.interp(z_dst, z_src, x_src)
            simplified = [[float(x), float(z)] for x, z in zip(x_dst, z_dst)]
    return [[round(float(x), 3), round(float(z), 3)] for x, z in simplified]

def regularize_hub_profile_points(points, base_z=None, target_min=16, target_max=28):
    """Regularize a hub cross-section while preserving the overall dish shape."""
    if not points:
        return []

    profile = [[float(p[0]), float(p[1])] for p in points]
    if len(profile) < 5:
        return [[round(float(r), 3), round(float(z), 3)] for r, z in profile]

    if base_z is None:
        base_z = min([float(p[1]) for p in profile])
    base_z = float(base_z)

    profile = sorted(profile, key=lambda item: item[0], reverse=True)
    outer_anchor = [float(profile[0][0]), base_z]
    inner_anchor = [float(profile[-1][0]), base_z]

    crown = []
    for radius_val, z_val in profile[1:-1]:
        crown.append([float(radius_val), max(base_z + 0.1, float(z_val))])

    if len(crown) < 3:
        return [
            [round(outer_anchor[0], 3), round(outer_anchor[1], 3)],
            [round(inner_anchor[0], 3), round(inner_anchor[1], 3)]
        ]

    r_vals = np.asarray([p[0] for p in crown], dtype=float)
    z_vals = np.asarray([p[1] for p in crown], dtype=float)
    if len(z_vals) >= 5:
        window = min(9, len(z_vals) if len(z_vals) % 2 == 1 else len(z_vals) - 1)
        if window >= 5:
            z_vals = savgol_filter(z_vals, window_length=window, polyorder=2, mode="interp")
    z_vals = np.maximum(z_vals, base_z + 0.1)

    smoothed = [[float(r), float(z)] for r, z in zip(r_vals, z_vals)]
    simplified = optimize_profile_points(smoothed, target_min=target_min, target_max=target_max)

    cleaned = [[round(outer_anchor[0], 3), round(outer_anchor[1], 3)]]
    last_r = outer_anchor[0]
    for radius_val, z_val in simplified:
        radius_val = float(radius_val)
        z_val = max(base_z + 0.1, float(z_val))
        if radius_val >= last_r - 0.05:
            radius_val = last_r - 0.05
        if radius_val <= inner_anchor[0] + 0.05:
            continue
        cleaned.append([round(radius_val, 3), round(z_val, 3)])
        last_r = radius_val
    cleaned.append([round(inner_anchor[0], 3), round(inner_anchor[1], 3)])

    return cleaned

# =============================================================================
# 2. ?????? (Perception Module)
# =============================================================================

def normalize_geom(geom):
    """Normalize invalid Shapely output without losing useful geometry."""
    if geom is None:
        return Polygon()
    if geom.is_empty:
        return geom
    if not geom.is_valid:
        geom = geom.buffer(0)
    return geom

def circle_polygon(radius, count=180):
    """Build a polygonal circle for robust clipping operations."""
    if radius <= 0:
        return Polygon()
    pts = []
    for i in range(count):
        ang = (2.0 * math.pi * i) / count
        pts.append((radius * math.cos(ang), radius * math.sin(ang)))
    pts.append(pts[0])
    return Polygon(pts)

def sector_polygon(start_angle_deg, end_angle_deg, radius):
    """Create a wedge polygon between two angles around the origin."""
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
    """Create an annular sector polygon in the perception module."""
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
    """Create a tapered wedge polygon with a narrower inner opening and a wider outer shoulder."""
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

def iter_polygons(geom):
    """Yield polygon members from Polygon or MultiPolygon results."""
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    return []

def largest_polygon(geom, min_area=5.0):
    """Return the largest polygon member above a minimum area threshold."""
    polys = []
    for poly in iter_polygons(geom):
        if not poly.is_empty and float(poly.area) >= float(min_area):
            polys.append(poly)
    if not polys:
        return None
    return max(polys, key=lambda poly: poly.area)

def canonicalize_loop(coords):
    """Normalize loop orientation and start point for more stable lofting."""
    if coords is None:
        return []
    pts = [(float(x), float(y)) for x, y in coords]
    if len(pts) < 4:
        return []
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return []

    signed_area = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        signed_area += (x1 * y2) - (x2 * y1)
    if signed_area < 0:
        pts.reverse()

    start_idx = min(
        range(len(pts)),
        key=lambda i: (
            round(math.hypot(pts[i][0], pts[i][1]), 6),
            round(math.atan2(pts[i][1], pts[i][0]), 6)
        )
    )
    pts = pts[start_idx:] + pts[:start_idx]
    pts.append(pts[0])
    return [[round(float(x), 3), round(float(y), 3)] for x, y in pts]

def canonicalize_member_loop(coords, member_angle_deg):
    """Normalize a spoke loop using the member's radial/tangential frame."""
    base_loop = canonicalize_loop(coords)
    if len(base_loop) < 4:
        return []

    pts = [(float(x), float(y)) for x, y in base_loop[:-1]]
    if len(pts) < 3:
        return []

    try:
        angle_rad = math.radians(float(member_angle_deg))
    except Exception:
        angle_rad = 0.0

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

def resample_closed_loop_outer(coords, target_count=48):
    """Uniformly resample a closed loop for stable cross-member template averaging."""
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

def align_resampled_loop_outer(reference_loop, candidate_loop, allow_reverse=True):
    """Align a sampled loop to a reference loop by cyclic shift and optional orientation flip."""
    if not reference_loop or not candidate_loop:
        return candidate_loop
    if len(reference_loop) != len(candidate_loop) or len(reference_loop) < 3:
        return candidate_loop

    ref = [(float(x), float(y)) for x, y in reference_loop]
    cand = [(float(x), float(y)) for x, y in candidate_loop]
    count = len(ref)

    def loop_error(loop_pts):
        err = 0.0
        for (rx, ry), (cx, cy) in zip(ref, loop_pts):
            dx = cx - rx
            dy = cy - ry
            err += (dx * dx) + (dy * dy)
        return err

    best_loop = cand
    best_err = float("inf")
    orientations = [cand]
    if allow_reverse:
        orientations.append(list(reversed(cand)))

    for orientation in orientations:
        for shift_idx in range(count):
            shifted = orientation[shift_idx:] + orientation[:shift_idx]
            err = loop_error(shifted)
            if err < best_err:
                best_err = err
                best_loop = shifted

    return best_loop

def world_loop_to_member_local(coords, member_angle_deg):
    """Project a world-space spoke loop into the member's radial/tangential frame."""
    world_loop = canonicalize_member_loop(coords, member_angle_deg)
    if len(world_loop) < 4:
        return []

    try:
        angle_rad = math.radians(float(member_angle_deg))
    except Exception:
        angle_rad = 0.0

    radial_dir = np.asarray([math.cos(angle_rad), math.sin(angle_rad)], dtype=float)
    tangential_dir = np.asarray([-math.sin(angle_rad), math.cos(angle_rad)], dtype=float)
    local_pts = []
    for x_val, y_val in world_loop[:-1]:
        point = np.asarray([float(x_val), float(y_val)], dtype=float)
        radial_val = float(np.dot(point, radial_dir))
        tangent_val = float(np.dot(point, tangential_dir))
        local_pts.append([round(radial_val, 3), round(tangent_val, 3)])

    if len(local_pts) < 3:
        return []
    local_pts.append(local_pts[0])
    return local_pts

def continuous_angle_window(angles_deg):
    """Return the smallest continuous angle window covering the given angles."""
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

def normalize_half_turn_angle(angle_deg):
    """Map an angle onto [0, 180) because radial section planes repeat every 180 degrees."""
    return float(angle_deg) % 180.0

def half_turn_angle_distance(angle_a_deg, angle_b_deg):
    """Angular distance on a 180-degree periodic domain."""
    diff = abs(normalize_half_turn_angle(angle_a_deg) - normalize_half_turn_angle(angle_b_deg))
    return min(diff, 180.0 - diff)

def build_pcd_exclusion_angles(hole_count, phase_angle_deg):
    """Return the unique section-plane angles that pass through lug holes."""
    if int(hole_count) <= 0:
        return []
    raw_angles = []
    for hole_idx in range(int(hole_count)):
        raw_angles.append(normalize_half_turn_angle(float(phase_angle_deg) + ((360.0 / int(hole_count)) * hole_idx)))

    unique_angles = []
    for angle_deg in sorted(raw_angles):
        if not any(half_turn_angle_distance(angle_deg, existing) < 1e-3 for existing in unique_angles):
            unique_angles.append(angle_deg)
    return unique_angles

def generate_guarded_section_angles(angle_count, hole_count=0, phase_angle_deg=0.0, exclusion_half_width_deg=7.0):
    """Generate section angles that avoid passing through PCD holes whenever possible."""
    target_count = max(1, int(angle_count))
    excluded_angles = build_pcd_exclusion_angles(hole_count, phase_angle_deg)
    if not excluded_angles:
        return list(np.linspace(0.0, 180.0, target_count, endpoint=False)), {
            "guarded": False,
            "excluded_angles": [],
            "preview_angle": 0.0,
            "exclusion_half_width_deg": 0.0
        }

    preferred_offset = normalize_half_turn_angle(float(phase_angle_deg) + (180.0 / max(1, int(hole_count))) * 0.5)
    dense_count = max(target_count * 12, 180)
    width_schedule = [1.0, 0.85, 0.7, 0.55, 0.4, 0.25]

    for width_factor in width_schedule:
        current_width = float(exclusion_half_width_deg) * width_factor
        candidates = []
        for idx in range(dense_count):
            angle_deg = normalize_half_turn_angle(preferred_offset + ((180.0 * idx) / dense_count))
            min_dist = min([half_turn_angle_distance(angle_deg, excluded) for excluded in excluded_angles])
            if min_dist >= current_width:
                candidates.append((angle_deg, min_dist))

        candidates.sort(key=lambda item: item[0])
        deduped = []
        for angle_deg, min_dist in candidates:
            if deduped and abs(angle_deg - deduped[-1][0]) < 0.35:
                if min_dist > deduped[-1][1]:
                    deduped[-1] = (angle_deg, min_dist)
            else:
                deduped.append((angle_deg, min_dist))

        if len(deduped) < target_count:
            continue

        if target_count == 1:
            center_candidate = max(
                deduped,
                key=lambda item: (
                    item[1],
                    -half_turn_angle_distance(item[0], preferred_offset)
                )
            )
            selected_angles = [center_candidate[0]]
        else:
            sample_positions = np.linspace(0, len(deduped) - 1, target_count)
            picked = []
            for pos in sample_positions:
                candidate = deduped[int(round(float(pos)))][0]
                if not picked or half_turn_angle_distance(candidate, picked[-1]) > 0.35:
                    picked.append(candidate)
            while len(picked) < target_count and deduped:
                for angle_deg, _ in sorted(
                    deduped,
                    key=lambda item: (
                        -item[1],
                        half_turn_angle_distance(item[0], preferred_offset)
                    )
                ):
                    if all(half_turn_angle_distance(angle_deg, existing) > 0.35 for existing in picked):
                        picked.append(angle_deg)
                    if len(picked) >= target_count:
                        break
            selected_angles = sorted([normalize_half_turn_angle(angle) for angle in picked[:target_count]])

        return selected_angles, {
            "guarded": True,
            "excluded_angles": [round(float(angle), 3) for angle in excluded_angles],
            "preview_angle": round(float(selected_angles[0]), 3),
            "exclusion_half_width_deg": round(current_width, 3)
        }

    fallback_angles = list(np.linspace(0.0, 180.0, target_count, endpoint=False))
    return fallback_angles, {
        "guarded": False,
        "excluded_angles": [round(float(angle), 3) for angle in excluded_angles],
        "preview_angle": round(float(fallback_angles[0]), 3),
        "exclusion_half_width_deg": 0.0
    }

def extract_rotated_section_points(mesh, plane_angle_deg):
    """Extract positive-radius [r, z] section points from a plane rotated around the Z axis."""
    theta = math.radians(float(plane_angle_deg))
    plane_normal = [-math.sin(theta), math.cos(theta), 0.0]
    section = mesh.section(plane_origin=[0, 0, 0], plane_normal=plane_normal)
    if not section:
        return []
    base_axis = np.array([math.cos(theta), math.sin(theta), 0.0], dtype=float)

    def collect_halfplane_payload(radial_axis, max_radius=None):
        lines_2d = []
        z_values = []
        points_rz = []
        for entity in section.entities:
            pts = section.vertices[entity.points]
            local_pts = []
            for point in pts:
                radial_pos = float(np.dot(point[:3], radial_axis))
                if max_radius is not None and abs(radial_pos) > float(max_radius) + 10.0:
                    continue
                z_val = float(point[2])
                local_pts.append((radial_pos, z_val))
                z_values.append(z_val)
                if radial_pos > 0.0:
                    points_rz.append([round(radial_pos, 3), round(z_val, 3)])
            if len(local_pts) >= 2:
                lines_2d.append(local_pts)

        region_payloads = []
        if lines_2d and z_values:
            try:
                merged = linemerge(MultiLineString(lines_2d))
                polygons = list(polygonize(merged))
            except Exception:
                polygons = []

            if polygons:
                z_min = min(z_values) - 5.0
                z_max = max(z_values) + 5.0
                radial_limit = float(max_radius if max_radius is not None else max([abs(x) for line in lines_2d for x, _ in line])) + 10.0
                half_plane = Polygon([
                    (0.0, z_min),
                    (radial_limit, z_min),
                    (radial_limit, z_max),
                    (0.0, z_max)
                ])

                def iter_local_polygons(geom):
                    if geom is None or geom.is_empty:
                        return []
                    if isinstance(geom, Polygon):
                        return [geom]
                    if isinstance(geom, MultiPolygon):
                        return list(geom.geoms)
                    if isinstance(geom, GeometryCollection):
                        polys = []
                        for sub_geom in geom.geoms:
                            polys.extend(iter_local_polygons(sub_geom))
                        return polys
                    return []

                for poly in polygons:
                    clipped = normalize_geom(poly.intersection(half_plane))
                    for clipped_poly in iter_local_polygons(clipped):
                        if clipped_poly.is_empty or clipped_poly.area < 25.0:
                            continue
                        outer = canonicalize_loop(list(clipped_poly.exterior.coords))
                        if len(outer) < 4:
                            continue
                        region_payloads.append({
                            "outer": outer,
                            "holes": []
                        })

        descriptors = [describe_section_region_span(region) for region in region_payloads]
        descriptors = [desc for desc in descriptors if desc is not None]
        max_outer_r = max([desc["outer_r"] for desc in descriptors], default=0.0)
        total_area = sum([desc["area"] for desc in descriptors])
        score = (
            round(float(max_outer_r), 6),
            round(float(total_area), 6),
            int(len(region_payloads)),
            int(len(points_rz))
        )
        return {
            "points": points_rz,
            "regions": region_payloads,
            "score": score
        }

    candidates = [
        collect_halfplane_payload(base_axis),
        collect_halfplane_payload(-base_axis)
    ]
    best = max(candidates, key=lambda item: item["score"])
    return best["points"]

def extract_rotated_section_regions(mesh, plane_angle_deg, max_radius=None):
    """Extract all positive-radius closed section regions from a guarded radial plane."""
    theta = math.radians(float(plane_angle_deg))
    plane_normal = [-math.sin(theta), math.cos(theta), 0.0]
    section = mesh.section(plane_origin=[0, 0, 0], plane_normal=plane_normal)
    if not section:
        return []
    base_axis = np.array([math.cos(theta), math.sin(theta), 0.0], dtype=float)

    def collect_regions(radial_axis):
        lines_2d = []
        z_values = []
        for entity in section.entities:
            pts = section.vertices[entity.points]
            local_pts = []
            for point in pts:
                radial_pos = float(np.dot(point[:3], radial_axis))
                if max_radius is not None and abs(radial_pos) > float(max_radius) + 10.0:
                    continue
                z_val = float(point[2])
                local_pts.append((radial_pos, z_val))
                z_values.append(z_val)
            if len(local_pts) >= 2:
                lines_2d.append(local_pts)

        if not lines_2d or not z_values:
            return [], (0.0, 0.0, 0)

        try:
            merged = linemerge(MultiLineString(lines_2d))
            polygons = list(polygonize(merged))
        except Exception:
            polygons = []

        if not polygons:
            return [], (0.0, 0.0, 0)

        z_min = min(z_values) - 5.0
        z_max = max(z_values) + 5.0
        radial_limit = float(max_radius if max_radius is not None else max([abs(x) for line in lines_2d for x, _ in line])) + 10.0
        half_plane = Polygon([
            (0.0, z_min),
            (radial_limit, z_min),
            (radial_limit, z_max),
            (0.0, z_max)
        ])

        positive_candidates = []

        def iter_local_polygons(geom):
            if geom is None or geom.is_empty:
                return []
            if isinstance(geom, Polygon):
                return [geom]
            if isinstance(geom, MultiPolygon):
                return list(geom.geoms)
            if isinstance(geom, GeometryCollection):
                polys = []
                for sub_geom in geom.geoms:
                    polys.extend(iter_local_polygons(sub_geom))
                return polys
            return []

        for poly in polygons:
            clipped = normalize_geom(poly.intersection(half_plane))
            for clipped_poly in iter_local_polygons(clipped):
                if clipped_poly.is_empty or clipped_poly.area < 25.0:
                    continue
                positive_candidates.append(clipped_poly)

        region_payloads = []
        for poly in sorted(positive_candidates, key=lambda poly: poly.area, reverse=True):
            outer = canonicalize_loop(list(poly.exterior.coords))
            if len(outer) < 4:
                continue

            holes = []
            for interior in poly.interiors:
                hole_loop = canonicalize_loop(list(interior.coords))
                if len(hole_loop) >= 4:
                    holes.append(hole_loop)

            region_payloads.append({
                "outer": outer,
                "holes": holes
            })

        descriptors = [describe_section_region_span(region) for region in region_payloads]
        descriptors = [desc for desc in descriptors if desc is not None]
        max_outer_r = max([desc["outer_r"] for desc in descriptors], default=0.0)
        total_area = sum([desc["area"] for desc in descriptors])
        return region_payloads, (
            round(float(max_outer_r), 6),
            round(float(total_area), 6),
            int(len(region_payloads))
        )

    region_sets = [
        collect_regions(base_axis),
        collect_regions(-base_axis)
    ]
    best_regions, _ = max(region_sets, key=lambda item: item[1])
    return best_regions

def extract_rotated_section_region(mesh, plane_angle_deg, max_radius=None):
    """Extract the largest positive-radius closed section region from a guarded radial plane."""
    regions = extract_rotated_section_regions(mesh, plane_angle_deg, max_radius=max_radius)
    return regions[0] if regions else {}

def sample_radial_upper_envelope(points, min_radius=0.0, max_radius=None, bin_count=160, percentile=98.0):
    """Extract a top envelope z(r) curve from raw XZ section points."""
    if points is None:
        return []
    pts = np.asarray(points, dtype=float)
    if pts.ndim != 2 or pts.shape[1] < 2 or len(pts) < 10:
        return []

    radii = pts[:, 0]
    zs = pts[:, 1]
    if max_radius is None:
        max_radius = float(np.max(radii))
    if max_radius <= min_radius + 1e-6:
        return []

    bins = np.linspace(float(min_radius), float(max_radius), int(bin_count) + 1)
    centers = (bins[:-1] + bins[1:]) * 0.5
    digitized = np.digitize(radii, bins)

    profile = []
    for idx, radius_val in enumerate(centers, start=1):
        bin_z = zs[digitized == idx]
        if len(bin_z) < 2:
            continue
        z_val = float(np.percentile(bin_z, percentile))
        profile.append([round(float(radius_val), 3), round(z_val, 3)])
    return profile

def sample_radial_lower_envelope(points, min_radius=0.0, max_radius=None, bin_count=160, percentile=2.0):
    """Extract a bottom envelope z(r) curve from raw XZ section points."""
    if points is None:
        return []
    pts = np.asarray(points, dtype=float)
    if pts.ndim != 2 or pts.shape[1] < 2 or len(pts) < 10:
        return []

    radii = pts[:, 0]
    zs = pts[:, 1]
    if max_radius is None:
        max_radius = float(np.max(radii))
    if max_radius <= min_radius + 1e-6:
        return []

    bins = np.linspace(float(min_radius), float(max_radius), int(bin_count) + 1)
    centers = (bins[:-1] + bins[1:]) * 0.5
    digitized = np.digitize(radii, bins)

    profile = []
    for idx, radius_val in enumerate(centers, start=1):
        bin_z = zs[digitized == idx]
        if len(bin_z) < 2:
            continue
        z_val = float(np.percentile(bin_z, percentile))
        profile.append([round(float(radius_val), 3), round(z_val, 3)])
    return profile

def split_profile_by_radius_gap(profile, max_gap=6.0):
    """Split a sampled [radius, z] profile into contiguous radius segments."""
    if not profile:
        return []
    pts = [[float(p[0]), float(p[1])] for p in profile if len(p) >= 2]
    if len(pts) < 2:
        return [pts] if pts else []
    pts.sort(key=lambda item: item[0])
    segments = [[pts[0]]]
    for point in pts[1:]:
        if float(point[0]) - float(segments[-1][-1][0]) > float(max_gap):
            segments.append([point])
        else:
            segments[-1].append(point)
    return [segment for segment in segments if len(segment) >= 2]

def interpolate_profile_z(profile, radius_val):
    """Linearly interpolate z on a sampled [radius, z] profile."""
    if not profile or len(profile) < 2:
        return None
    try:
        radius_val = float(radius_val)
    except Exception:
        return None

    pts = [[float(p[0]), float(p[1])] for p in profile if len(p) >= 2]
    if len(pts) < 2:
        return None

    pts.sort(key=lambda item: item[0])
    if radius_val < pts[0][0] or radius_val > pts[-1][0]:
        return None

    for idx in range(len(pts) - 1):
        r0, z0 = pts[idx]
        r1, z1 = pts[idx + 1]
        if r0 <= radius_val <= r1:
            if abs(r1 - r0) < 1e-9:
                return float(max(z0, z1))
            t = (radius_val - r0) / (r1 - r0)
            return float(z0 + ((z1 - z0) * t))
    return None

def sample_polygon_upper_profile(poly, min_radius, max_radius, sample_count=180):
    """Sample the upper envelope of a 2D polygon using vertical probes."""
    if poly is None or poly.is_empty:
        return []
    try:
        bounds = poly.bounds
        z_low = float(bounds[1]) - 1.0
        z_high = float(bounds[3]) + 1.0
        radii = np.linspace(float(min_radius), float(max_radius), int(sample_count))
        profile = []

        def collect_z(geom, out):
            if geom is None or geom.is_empty:
                return
            if isinstance(geom, Point):
                out.append(float(geom.y))
                return
            if isinstance(geom, LineString):
                coords = list(geom.coords)
                for _, z_val in coords:
                    out.append(float(z_val))
                return
            if isinstance(geom, MultiLineString):
                for sub in geom.geoms:
                    collect_z(sub, out)
                return
            if isinstance(geom, GeometryCollection):
                for sub in geom.geoms:
                    collect_z(sub, out)
                return
            if hasattr(geom, "geoms"):
                for sub in geom.geoms:
                    collect_z(sub, out)

        for radius_val in radii:
            probe = LineString([(float(radius_val), z_low), (float(radius_val), z_high)])
            hit = poly.intersection(probe)
            hit_z = []
            collect_z(hit, hit_z)
            if hit_z:
                profile.append([round(float(radius_val), 3), round(float(max(hit_z)), 3)])
        return profile
    except Exception:
        return []

def suppress_guarded_section_nonrotary_grooves(
    region,
    reference_profile,
    min_radius,
    max_radius,
    min_drop=1.1,
    target_offset=0.22,
    max_patch_width=24.0
):
    """
    Fill narrow upper-boundary valleys in the guarded section that sit well below
    the multi-angle rotary reference. These valleys are typically non-axisymmetric
    local features that should not survive the 360-degree revolve.
    """
    if not isinstance(region, dict):
        return region, {"patch_count": 0, "sample_count": 0}
    outer = region.get("outer", [])
    holes = region.get("holes", [])
    if len(outer) < 4 or not reference_profile:
        return region, {"patch_count": 0, "sample_count": 0}

    try:
        source_poly = normalize_geom(Polygon(outer, holes))
    except Exception:
        return region, {"patch_count": 0, "sample_count": 0}

    if source_poly.is_empty:
        return region, {"patch_count": 0, "sample_count": 0}

    clip_min_r = max(0.0, float(min_radius))
    clip_max_r = max(clip_min_r + 1.0, float(max_radius))
    upper_profile = sample_polygon_upper_profile(source_poly, clip_min_r, clip_max_r, sample_count=220)
    if len(upper_profile) < 12:
        return region, {"patch_count": 0, "sample_count": len(upper_profile)}

    deltas = []
    for radius_val, current_z in upper_profile:
        ref_z = interpolate_profile_z(reference_profile, radius_val)
        if ref_z is None:
            deltas.append(None)
            continue
        target_z = float(ref_z) - float(target_offset)
        deltas.append(max(0.0, target_z - float(current_z)))

    patches = []
    start_idx = None
    for idx, delta in enumerate(deltas):
        active = delta is not None and delta >= float(min_drop)
        if active and start_idx is None:
            start_idx = idx
        elif (not active) and start_idx is not None:
            patches.append((start_idx, idx - 1))
            start_idx = None
    if start_idx is not None:
        patches.append((start_idx, len(upper_profile) - 1))

    fill_polys = []
    for start_idx, end_idx in patches:
        if end_idx <= start_idx:
            continue
        seg = upper_profile[start_idx:end_idx + 1]
        if len(seg) < 3:
            continue
        width = float(seg[-1][0]) - float(seg[0][0])
        if width <= 0.8 or width > float(max_patch_width):
            continue

        lower_curve = []
        upper_curve = []
        for radius_val, current_z in seg:
            ref_z = interpolate_profile_z(reference_profile, radius_val)
            if ref_z is None:
                continue
            target_z = float(ref_z) - float(target_offset)
            if target_z <= float(current_z) + 0.15:
                continue
            lower_curve.append((float(radius_val), float(current_z)))
            upper_curve.append((float(radius_val), float(target_z)))

        if len(lower_curve) < 3 or len(upper_curve) < 3:
            continue

        patch_pts = list(lower_curve)
        patch_pts.extend(list(reversed(upper_curve)))
        patch_pts.append(patch_pts[0])
        try:
            patch_poly = normalize_geom(Polygon(patch_pts))
        except Exception:
            continue
        if patch_poly.is_empty or patch_poly.area < 4.0:
            continue
        fill_polys.append(patch_poly)

    if not fill_polys:
        return region, {"patch_count": 0, "sample_count": len(upper_profile)}

    try:
        filled_geom = normalize_geom(source_poly.union(unary_union(fill_polys)))
        main_poly = largest_polygon(filled_geom, min_area=25.0)
        if main_poly is None:
            return region, {"patch_count": 0, "sample_count": len(upper_profile)}

        sanitized_region = {
            "outer": canonicalize_loop(list(main_poly.exterior.coords)),
            "holes": []
        }
        for interior in main_poly.interiors:
            hole_loop = canonicalize_loop(list(interior.coords))
            if len(hole_loop) >= 4:
                sanitized_region["holes"].append(hole_loop)
        return sanitized_region, {
            "patch_count": len(fill_polys),
            "sample_count": len(upper_profile)
        }
    except Exception:
        return region, {"patch_count": 0, "sample_count": len(upper_profile)}

def suppress_section_lower_bound_nonrotary_reliefs(
    region,
    min_radius,
    max_radius,
    target_floor_z,
    min_raise=1.1,
    target_offset=0.22,
    max_patch_width=24.0
):
    """
    Fill narrow lower-boundary lifts inside a section that sit well above the
    intended rotary rear-face floor. These lifts usually come from local,
    non-axisymmetric rear pockets that should not survive a 360-degree revolve.
    """
    if not isinstance(region, dict):
        return region, {"patch_count": 0, "sample_count": 0}
    outer = region.get("outer", [])
    holes = region.get("holes", [])
    if len(outer) < 4:
        return region, {"patch_count": 0, "sample_count": 0}

    try:
        source_poly = normalize_geom(Polygon(outer, holes))
    except Exception:
        return region, {"patch_count": 0, "sample_count": 0}

    if source_poly.is_empty:
        return region, {"patch_count": 0, "sample_count": 0}

    clip_min_r = max(0.0, float(min_radius))
    clip_max_r = max(clip_min_r + 1.0, float(max_radius))
    support_margin = min(10.0, max(4.0, (clip_max_r - clip_min_r) * 0.42))
    sample_min_r = max(0.0, clip_min_r - support_margin)
    sample_max_r = clip_max_r + support_margin
    bounds = source_poly.bounds
    z_low = float(bounds[1]) - 1.0
    z_high = float(bounds[3]) + 1.0
    radii = np.linspace(sample_min_r, sample_max_r, 260)
    lower_profile = []

    def collect_z(geom, out):
        if geom is None or geom.is_empty:
            return
        if isinstance(geom, Point):
            out.append(float(geom.y))
            return
        if isinstance(geom, LineString):
            for _, z_val in list(geom.coords):
                out.append(float(z_val))
            return
        if isinstance(geom, MultiLineString):
            for sub in geom.geoms:
                collect_z(sub, out)
            return
        if isinstance(geom, GeometryCollection):
            for sub in geom.geoms:
                collect_z(sub, out)
            return
        if hasattr(geom, "geoms"):
            for sub in geom.geoms:
                collect_z(sub, out)

    for radius_val in radii:
        probe = LineString([(float(radius_val), z_low), (float(radius_val), z_high)])
        hit = source_poly.intersection(probe)
        hit_z = []
        collect_z(hit, hit_z)
        if len(hit_z) < 2:
            continue
        lower_profile.append((float(radius_val), float(min(hit_z))))

    band_profile = [
        (float(radius_val), float(current_z))
        for radius_val, current_z in lower_profile
        if (clip_min_r - 0.05) <= float(radius_val) <= (clip_max_r + 0.05)
    ]
    if len(band_profile) < 12:
        return region, {"patch_count": 0, "sample_count": len(band_profile)}

    target_z = float(target_floor_z) + float(target_offset)
    deltas = [max(0.0, float(current_z) - target_z) for _, current_z in band_profile]

    patches = []
    start_idx = None
    for idx, delta in enumerate(deltas):
        active = delta >= float(min_raise)
        if active and start_idx is None:
            start_idx = idx
        elif (not active) and start_idx is not None:
            patches.append((start_idx, idx - 1))
            start_idx = None
    if start_idx is not None:
        patches.append((start_idx, len(lower_profile) - 1))

    fill_polys = []
    for start_idx, end_idx in patches:
        if end_idx <= start_idx:
            continue
        seg = band_profile[start_idx:end_idx + 1]
        if len(seg) < 3:
            continue
        width = float(seg[-1][0]) - float(seg[0][0])
        if width <= 0.8 or width > float(max_patch_width):
            continue

        left_support = [
            pt for pt in lower_profile
            if float(pt[0]) < float(seg[0][0]) - 0.05
        ]
        right_support = [
            pt for pt in lower_profile
            if float(pt[0]) > float(seg[-1][0]) + 0.05
        ]
        left_support = left_support[-4:]
        right_support = right_support[:4]
        support_pts = list(left_support) + list(right_support)
        use_support_interp = len(left_support) >= 2 and len(right_support) >= 2 and len(support_pts) >= 4
        support_r = [float(r_val) for r_val, _ in support_pts]
        support_z = [float(z_val) for _, z_val in support_pts]

        target_curve = []
        current_curve = []
        for radius_val, current_z in seg:
            if target_z >= float(current_z) - 0.15:
                continue
            if use_support_interp:
                interp_target_z = float(np.interp(float(radius_val), support_r, support_z))
                blended_target_z = max(float(target_z), interp_target_z)
            else:
                blended_target_z = float(target_z)
            target_curve.append((float(radius_val), float(blended_target_z)))
            current_curve.append((float(radius_val), float(current_z)))

        if len(target_curve) < 3 or len(current_curve) < 3:
            continue

        patch_pts = list(target_curve)
        patch_pts.extend(list(reversed(current_curve)))
        patch_pts.append(patch_pts[0])
        try:
            patch_poly = normalize_geom(Polygon(patch_pts))
        except Exception:
            continue
        if patch_poly.is_empty or patch_poly.area < 4.0:
            continue
        fill_polys.append(patch_poly)

    if not fill_polys:
        return region, {"patch_count": 0, "sample_count": len(band_profile)}

    try:
        filled_geom = normalize_geom(source_poly.union(unary_union(fill_polys)))
        main_poly = largest_polygon(filled_geom, min_area=25.0)
        if main_poly is None:
            return region, {"patch_count": 0, "sample_count": len(band_profile)}

        sanitized_region = {
            "outer": canonicalize_loop(list(main_poly.exterior.coords)),
            "holes": []
        }
        for interior in main_poly.interiors:
            hole_loop = canonicalize_loop(list(interior.coords))
            if len(hole_loop) >= 4:
                sanitized_region["holes"].append(hole_loop)
        return sanitized_region, {
            "patch_count": len(fill_polys),
            "sample_count": len(lower_profile)
        }
    except Exception:
        return region, {"patch_count": 0, "sample_count": len(band_profile)}

def estimate_window_inner_reference_radius(mesh, spoke_voids, hub_radius, outer_limit_r):
    """Use spoke-free radial sections through window centers to estimate safe inner cut radii."""
    if mesh is None or not spoke_voids:
        return None, {"section_count": 0, "per_void_reference_radii": []}

    def measure_single_void(spoke_void):
        pts = spoke_void.get("points", []) if isinstance(spoke_void, dict) else spoke_void
        if len(pts) < 4:
            return None, None

        try:
            void_poly = Polygon(pts)
            centroid = void_poly.centroid
            section_angle = normalize_half_turn_angle(math.degrees(math.atan2(centroid.y, centroid.x)))
            section_pts = extract_rotated_section_points(mesh, section_angle)
            if len(section_pts) < 40:
                return None, section_angle

            profile = sample_radial_upper_envelope(
                section_pts,
                min_radius=max(0.0, float(hub_radius) - 2.0),
                max_radius=float(outer_limit_r),
                bin_count=180,
                percentile=98.5
            )
            if len(profile) < 20:
                return None, section_angle

            profile_arr = np.asarray(profile, dtype=float)
            radii = profile_arr[:, 0]
            z_vals = profile_arr[:, 1]
            if len(z_vals) >= 7:
                window_len = min(len(z_vals) if len(z_vals) % 2 == 1 else len(z_vals) - 1, 11)
                if window_len >= 5:
                    z_vals = savgol_filter(z_vals, window_length=window_len, polyorder=2)

            face_mask = (radii >= float(hub_radius)) & (radii <= min(float(outer_limit_r), float(hub_radius) + 18.0))
            valley_mask = (radii >= float(hub_radius) + 6.0) & (radii <= min(float(outer_limit_r), float(hub_radius) + 55.0))
            if np.count_nonzero(face_mask) < 4 or np.count_nonzero(valley_mask) < 6:
                return None, section_angle

            face_z = float(np.percentile(z_vals[face_mask], 92))
            valley_z = float(np.percentile(z_vals[valley_mask], 12))
            drop = face_z - valley_z
            if drop < 4.0:
                return None, section_angle

            trigger_z = face_z - (drop * 0.32)
            valley_indices = np.where(valley_mask)[0]
            start_idx = None
            for idx in valley_indices:
                if z_vals[idx] <= trigger_z:
                    next_idx = min(idx + 1, len(z_vals) - 1)
                    if z_vals[next_idx] <= (trigger_z + 0.6):
                        start_idx = idx
                        break

            if start_idx is None:
                return None, section_angle

            return float(radii[start_idx]), section_angle
        except Exception:
            return None, None

    reference_samples = []
    angle_samples = []
    per_void_reference_radii = []

    for spoke_void in spoke_voids:
        local_radius, local_angle = measure_single_void(spoke_void)
        per_void_reference_radii.append(round(float(local_radius), 2) if local_radius is not None else None)
        if local_radius is not None:
            reference_samples.append(float(local_radius))
            angle_samples.append(float(local_angle))

    if not reference_samples:
        return None, {
            "section_count": 0,
            "per_void_reference_radii": per_void_reference_radii
        }

    valid_radii = np.asarray(reference_samples, dtype=float)
    ref_radius = float(np.median(valid_radii))
    stabilized_radii = list(per_void_reference_radii)
    stabilization_count = 0
    if len(valid_radii) >= 4:
        high_side_offsets = np.maximum(0.0, valid_radii - ref_radius)
        global_high_allow = max(0.9, float(np.percentile(high_side_offsets, 80)) * 1.25)
        valid_count = len(stabilized_radii)
        for idx, radius_val in enumerate(stabilized_radii):
            if radius_val is None:
                continue
            neighbor_vals = []
            for step in range(1, valid_count):
                prev_idx = (idx - step) % valid_count
                prev_val = stabilized_radii[prev_idx]
                if prev_val is not None:
                    neighbor_vals.append(float(prev_val))
                    if len(neighbor_vals) >= 2:
                        break
            for step in range(1, valid_count):
                next_idx = (idx + step) % valid_count
                next_val = stabilized_radii[next_idx]
                if next_val is not None:
                    neighbor_vals.append(float(next_val))
                    if len(neighbor_vals) >= 4:
                        break
            if len(neighbor_vals) < 3:
                continue
            local_median = float(np.median(np.asarray(neighbor_vals, dtype=float)))
            local_offsets = np.abs(np.asarray(neighbor_vals, dtype=float) - local_median)
            local_allow = max(0.8, float(np.percentile(local_offsets, 75)) * 1.6)
            upper_limit = min(ref_radius + global_high_allow, local_median + local_allow)
            if float(radius_val) > upper_limit + 0.35:
                stabilized_radii[idx] = round(upper_limit, 2)
                stabilization_count += 1

    stats = {
        "section_count": int(len(reference_samples)),
        "angles": [round(float(angle), 2) for angle in angle_samples],
        "sample_min_r": round(float(np.min(reference_samples)), 2),
        "sample_max_r": round(float(np.max(reference_samples)), 2),
        "sample_median_r": round(ref_radius, 2),
        "per_void_reference_radii_raw": per_void_reference_radii,
        "per_void_reference_radii": stabilized_radii,
        "stabilized_count": int(stabilization_count)
    }
    return ref_radius, stats

def angular_distance_deg(angle_a_deg, angle_b_deg):
    """Shortest angular distance on a full 360-degree circle."""
    diff = abs((float(angle_a_deg) - float(angle_b_deg) + 180.0) % 360.0 - 180.0)
    return diff

def circular_mean_degrees(angles_deg):
    """Compute a stable mean angle on a full 360-degree circle."""
    if not angles_deg:
        return 0.0
    sin_sum = 0.0
    cos_sum = 0.0
    for angle_deg in angles_deg:
        ang = math.radians(float(angle_deg) % 360.0)
        sin_sum += math.sin(ang)
        cos_sum += math.cos(ang)
    if abs(sin_sum) <= 1e-9 and abs(cos_sum) <= 1e-9:
        return float(angles_deg[0]) % 360.0
    return math.degrees(math.atan2(sin_sum, cos_sum)) % 360.0

def describe_planar_region(region, min_area=20.0):
    """Extract stable angular/radial descriptors from a 2D perception region."""
    pts_region = region.get("points", []) if isinstance(region, dict) else region
    if len(pts_region) < 4:
        return None
    try:
        poly = normalize_geom(Polygon(pts_region))
    except Exception:
        return None
    if poly.is_empty or poly.area < float(min_area):
        return None

    coords = list(poly.exterior.coords)
    if len(coords) < 4:
        return None

    radii = [math.hypot(x, y) for x, y in coords[:-1]]
    if not radii:
        return None

    centroid = poly.centroid
    centroid_angle = math.degrees(math.atan2(centroid.y, centroid.x)) % 360.0
    angle_window = continuous_angle_window([
        math.degrees(math.atan2(y, x)) % 360.0
        for x, y in coords[:-1]
    ])

    return {
        "points": canonicalize_loop(coords),
        "angle": centroid_angle,
        "span": angle_window[2] if angle_window else 0.0,
        "inner_r": float(min(radii)),
        "outer_r": float(max(radii))
    }

def describe_section_region_payload(region, min_area=20.0):
    """Describe an [r, z] section-region payload extracted from a rotated plane."""
    if not isinstance(region, dict):
        return None
    outer = region.get("outer", [])
    holes = region.get("holes", [])
    if len(outer) < 4:
        return None
    try:
        poly = normalize_geom(Polygon(outer, holes))
    except Exception:
        return None
    if poly.is_empty or poly.area < float(min_area):
        return None
    coords = list(poly.exterior.coords)
    if len(coords) < 4:
        return None
    radii = [float(x) for x, _ in coords[:-1]]
    z_vals = [float(z) for _, z in coords[:-1]]
    if not radii or not z_vals:
        return None
    centroid = poly.centroid
    upper_profile, lower_profile = sample_section_region_envelopes(
        {
            "outer": canonicalize_loop(coords),
            "holes": [canonicalize_loop(list(interior.coords)) for interior in poly.interiors]
        },
        min(radii),
        max(radii),
        sample_count=120
    )
    return {
        "inner_r": float(min(radii)),
        "outer_r": float(max(radii)),
        "z_min": float(min(z_vals)),
        "z_max": float(max(z_vals)),
        "radial_span": float(max(radii) - min(radii)),
        "z_span": float(max(z_vals) - min(z_vals)),
        "area": float(poly.area),
        "centroid_r": float(centroid.x),
        "centroid_z": float(centroid.y),
        "upper_profile": upper_profile,
        "lower_profile": lower_profile
    }

def derive_spokeless_reference_fragments(spokeless_regions, params=None):
    """Pick likely hub/rim reference fragments from a disconnected spoke-free section."""
    params = params or {}
    descriptors = []
    for idx, region in enumerate(spokeless_regions or []):
        desc = describe_section_region_payload(region, min_area=20.0)
        if desc is None:
            continue
        desc["index"] = int(idx)
        descriptors.append(desc)

    if not descriptors:
        return {"regions": [], "hub_region_index": None, "rim_region_index": None, "mid_region_index": None}

    hub_radius = float(params.get("hub_radius", 0.0) or 0.0)
    pcd_radius = float(params.get("pcd_radius", 0.0) or 0.0)
    hole_radius = float(params.get("hole_radius", 0.0) or 0.0)
    hub_limit_r = max(70.0, hub_radius * 1.55, pcd_radius + hole_radius + 22.0)

    hub_candidates = [desc for desc in descriptors if desc["outer_r"] <= hub_limit_r]
    if not hub_candidates:
        hub_candidates = sorted(descriptors, key=lambda item: item["outer_r"])[: min(2, len(descriptors))]
    hub_region_index = max(
        hub_candidates,
        key=lambda item: (item["radial_span"], item["area"], item["z_max"])
    )["index"] if hub_candidates else None

    rim_candidates = [
        desc for desc in descriptors
        if desc["index"] != hub_region_index
    ]
    if not rim_candidates:
        rim_candidates = list(descriptors)
    rim_candidates = sorted(
        rim_candidates,
        key=lambda item: (item["outer_r"], item["radial_span"], item["area"]),
        reverse=True
    )
    rim_region_index = rim_candidates[0]["index"] if rim_candidates else None

    mid_candidates = [
        desc for desc in descriptors
        if desc["index"] not in {hub_region_index, rim_region_index}
    ]
    mid_region_index = max(
        mid_candidates,
        key=lambda item: (item["area"], item["radial_span"], item["outer_r"])
    )["index"] if mid_candidates else None

    return {
        "regions": descriptors,
        "hub_region_index": hub_region_index,
        "rim_region_index": rim_region_index,
        "mid_region_index": mid_region_index
    }

def derive_spoke_band_limits(spoke_regions, params=None):
    """Estimate the radial band actually occupied by spokes on the wheel face."""
    params = params or {}
    descs = []
    for region in spoke_regions or []:
        desc = describe_planar_region(region, min_area=80.0)
        if desc is not None:
            descs.append(desc)
    inner_ref = params.get("window_inner_reference_r")
    if inner_ref is not None:
        band_inner = float(inner_ref)
    elif descs:
        band_inner = float(np.percentile([desc["inner_r"] for desc in descs], 20))
    else:
        band_inner = max(float(params.get("hub_radius", 0.0)) + 4.0, float(params.get("bore_radius", 0.0)) + 8.0)

    if descs:
        band_outer = float(np.percentile([desc["outer_r"] for desc in descs], 85))
    else:
        band_outer = band_inner + 80.0

    if band_outer <= band_inner + 4.0:
        band_outer = band_inner + 30.0
    return round(band_inner, 3), round(band_outer, 3)

def describe_section_region_span(region):
    """Extract a lightweight radial-span descriptor directly from a raw section-region loop."""
    if not isinstance(region, dict):
        return None
    outer = region.get("outer", []) or []
    if len(outer) < 4:
        return None
    coords = []
    for point in outer:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        coords.append((float(point[0]), float(point[1])))
    if len(coords) < 4:
        return None
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    radii = [float(x) for x, _ in coords[:-1]]
    if not radii:
        return None
    area = 0.0
    for idx in range(len(coords) - 1):
        x1, y1 = coords[idx]
        x2, y2 = coords[idx + 1]
        area += (x1 * y2) - (x2 * y1)
    return {
        "inner_r": float(min(radii)),
        "outer_r": float(max(radii)),
        "radial_span": float(max(radii) - min(radii)),
        "area": abs(float(area)) * 0.5
    }

def should_prefer_fragmented_spokeless_base(spokeless_regions, band_inner, band_outer, min_gap=12.0):
    """Keep disconnected spoke-free fragments disconnected when the spoke band has real radial gaps."""
    descriptors = []
    for region in spokeless_regions or []:
        desc = describe_section_region_span(region)
        if desc is None:
            continue
        inner_r = float(desc["inner_r"])
        outer_r = float(desc["outer_r"])
        area = float(desc["area"])
        radial_span = float(desc["radial_span"])
        if area < 30.0 or radial_span < 3.0 or outer_r <= inner_r + 1.0:
            continue
        descriptors.append({
            "inner_r": inner_r,
            "outer_r": outer_r
        })

    if len(descriptors) < 2:
        return False

    band_inner = float(band_inner)
    band_outer = float(band_outer)
    if band_outer <= band_inner + 0.5:
        return False

    if any(
        desc["inner_r"] <= band_inner + 4.0 and desc["outer_r"] >= band_outer - 4.0
        for desc in descriptors
    ):
        return False

    band_min = band_inner - 4.0
    band_max = band_outer + 12.0
    intervals = []
    for desc in descriptors:
        start = max(desc["inner_r"], band_min)
        end = min(desc["outer_r"], band_max)
        if end > start + 1.5:
            intervals.append([start, end])

    if len(intervals) < 2:
        return False

    merged = []
    for start, end in sorted(intervals, key=lambda item: item[0]):
        if not merged or start > merged[-1][1] + 1.0:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)

    if len(merged) < 2:
        return False

    max_gap = max(
        float(merged[idx + 1][0]) - float(merged[idx][1])
        for idx in range(len(merged) - 1)
    )
    return bool(max_gap >= float(min_gap))

def build_hybrid_profile(
    base_profile,
    replacement_profile,
    band_inner,
    band_outer,
    reference_fragments=None,
    profile_key="upper_profile",
    max_gap=6.0,
    chain_gap=18.0,
    band_pad=2.5
):
    """Replace the band-connected portion of the base profile with real local section support."""
    if not base_profile:
        return []
    if not replacement_profile or band_outer <= band_inner + 0.5:
        return [[round(float(r), 3), round(float(z), 3)] for r, z in base_profile]

    support_segments = []
    for segment in split_profile_by_radius_gap(replacement_profile, max_gap=max_gap):
        if len(segment) < 2:
            continue
        support_segments.append({
            "points": [[float(r), float(z)] for r, z in segment],
            "source": "replacement"
        })

    if isinstance(reference_fragments, dict):
        regions = reference_fragments.get("regions", []) or []
        fragment_keys = (
            ("hub_region_index", "hub_fragment"),
            ("mid_region_index", "mid_fragment"),
            ("rim_region_index", "rim_fragment")
        )
        for index_key, source_name in fragment_keys:
            region_index = reference_fragments.get(index_key)
            if region_index is None:
                continue
            desc = next(
                (
                    item for item in regions
                    if int(item.get("index", -1)) == int(region_index)
                ),
                None
            )
            if desc is None:
                continue
            fragment_profile = desc.get(profile_key, []) or []
            for segment in split_profile_by_radius_gap(fragment_profile, max_gap=max_gap):
                if len(segment) < 2:
                    continue
                support_segments.append({
                    "points": [[float(r), float(z)] for r, z in segment],
                    "source": source_name
                })

    if not support_segments:
        return [[round(float(r), 3), round(float(z), 3)] for r, z in base_profile]

    for segment in support_segments:
        points = segment["points"]
        segment["r_min"] = float(points[0][0])
        segment["r_max"] = float(points[-1][0])

    support_segments.sort(key=lambda item: (item["r_min"], item["r_max"]))

    seed_min = float(band_inner) - float(band_pad)
    seed_max = float(band_outer) + float(band_pad)
    seed_indices = [
        idx for idx, segment in enumerate(support_segments)
        if float(segment["r_max"]) >= seed_min and float(segment["r_min"]) <= seed_max
    ]
    if not seed_indices:
        band_mid = (float(band_inner) + float(band_outer)) * 0.5
        closest_idx = min(
            range(len(support_segments)),
            key=lambda idx: abs(
                ((float(support_segments[idx]["r_min"]) + float(support_segments[idx]["r_max"])) * 0.5) - band_mid
            )
        )
        seed_indices = [closest_idx]

    active_left = min(seed_indices)
    active_right = max(seed_indices)
    while active_left > 0:
        prev_seg = support_segments[active_left - 1]
        curr_seg = support_segments[active_left]
        if float(curr_seg["r_min"]) - float(prev_seg["r_max"]) > float(chain_gap):
            break
        active_left -= 1
    while active_right < len(support_segments) - 1:
        curr_seg = support_segments[active_right]
        next_seg = support_segments[active_right + 1]
        if float(next_seg["r_min"]) - float(curr_seg["r_max"]) > float(chain_gap):
            break
        active_right += 1

    active_segments = support_segments[active_left:active_right + 1]
    active_inner = float(active_segments[0]["r_min"])
    active_outer = float(active_segments[-1]["r_max"])

    def interpolate_segmented(radius_val):
        for segment_meta in active_segments:
            segment = segment_meta["points"]
            r_min = float(segment[0][0])
            r_max = float(segment[-1][0])
            if r_min <= float(radius_val) <= r_max:
                return interpolate_profile_z(segment, radius_val)
        for seg_idx in range(len(active_segments) - 1):
            left_seg = active_segments[seg_idx]["points"]
            right_seg = active_segments[seg_idx + 1]["points"]
            left_r = float(left_seg[-1][0])
            right_r = float(right_seg[0][0])
            if right_r <= left_r + 0.5:
                continue
            gap_start = max(float(active_inner), left_r)
            gap_end = min(float(active_outer), right_r)
            if gap_end <= gap_start + 0.5:
                continue
            if gap_start <= float(radius_val) <= gap_end:
                t = (float(radius_val) - left_r) / max(right_r - left_r, 1e-6)
                left_z = float(left_seg[-1][1])
                right_z = float(right_seg[0][1])
                return left_z + ((right_z - left_z) * t)
        return None
    hybrid = []
    for radius_val, base_z in base_profile:
        r = float(radius_val)
        z = float(base_z)
        if float(active_inner) <= r <= float(active_outer):
            repl_z = interpolate_segmented(r)
            if repl_z is not None:
                z = float(repl_z)
        hybrid.append([round(r, 3), round(z, 3)])
    return hybrid

def sample_section_region_envelopes(region, min_radius, max_radius, sample_count=220):
    """Sample upper/lower envelopes from a section-region payload."""
    if not isinstance(region, dict):
        return [], []
    outer = region.get("outer", []) or []
    holes = region.get("holes", []) or []
    if len(outer) < 4:
        return [], []
    try:
        poly = normalize_geom(Polygon(outer, holes))
    except Exception:
        return [], []
    if poly is None or poly.is_empty:
        return [], []
    try:
        bounds = poly.bounds
        z_low = float(bounds[1]) - 1.0
        z_high = float(bounds[3]) + 1.0
        radii = np.linspace(float(min_radius), float(max_radius), int(sample_count))
        upper = []
        lower = []

        def collect_z(geom, out):
            if geom is None or geom.is_empty:
                return
            if isinstance(geom, Point):
                out.append(float(geom.y))
                return
            if isinstance(geom, LineString):
                for _, z_val in list(geom.coords):
                    out.append(float(z_val))
                return
            if isinstance(geom, MultiLineString):
                for sub in geom.geoms:
                    collect_z(sub, out)
                return
            if isinstance(geom, GeometryCollection):
                for sub in geom.geoms:
                    collect_z(sub, out)
                return
            if hasattr(geom, "geoms"):
                for sub in geom.geoms:
                    collect_z(sub, out)

        for radius_val in radii:
            probe = LineString([(float(radius_val), z_low), (float(radius_val), z_high)])
            hit = poly.intersection(probe)
            hit_z = []
            collect_z(hit, hit_z)
            if len(hit_z) < 2:
                continue
            upper.append([round(float(radius_val), 3), round(float(max(hit_z)), 3)])
            lower.append([round(float(radius_val), 3), round(float(min(hit_z)), 3)])
        return upper, lower
    except Exception:
        return [], []

def build_section_region_from_envelopes(upper_profile, lower_profile, min_separation=0.15):
    """Reconstruct a closed section-region payload from sampled upper/lower envelopes."""
    if not upper_profile or not lower_profile:
        return {}
    upper_pts = [[float(r), float(z)] for r, z in upper_profile if len([r, z]) >= 2]
    lower_pts = [[float(r), float(z)] for r, z in lower_profile if len([r, z]) >= 2]
    if len(upper_pts) < 4 or len(lower_pts) < 4:
        return {}

    merged_radii = sorted({round(float(r), 3) for r, _ in upper_pts} | {round(float(r), 3) for r, _ in lower_pts})
    upper_out = []
    lower_out = []
    for radius_val in merged_radii:
        upper_z = interpolate_profile_z(upper_pts, radius_val)
        lower_z = interpolate_profile_z(lower_pts, radius_val)
        if upper_z is None or lower_z is None:
            continue
        if float(upper_z) <= float(lower_z) + float(min_separation):
            continue
        upper_out.append([round(float(radius_val), 3), round(float(upper_z), 3)])
        lower_out.append([round(float(radius_val), 3), round(float(lower_z), 3)])

    if len(upper_out) < 4 or len(lower_out) < 4:
        return {}

    loop = []
    loop.extend([[float(r), float(z)] for r, z in reversed(upper_out)])
    loop.extend([[float(r), float(z)] for r, z in lower_out])
    cleaned = []
    for radius_val, z_val in loop:
        if cleaned and math.hypot(float(radius_val) - cleaned[-1][0], float(z_val) - cleaned[-1][1]) < 0.05:
            continue
        cleaned.append([round(float(radius_val), 3), round(float(z_val), 3)])
    if len(cleaned) < 8:
        return {}
    if cleaned[0] != cleaned[-1]:
        cleaned.append(cleaned[0])
    return {"outer": cleaned, "holes": []}

def build_fragmented_section_regions_from_profiles(upper_profile, lower_profile, max_gap=5.0, min_overlap=2.0):
    """Reconstruct disconnected section regions from independently segmented upper/lower envelopes."""
    upper_segments = [
        [[float(r), float(z)] for r, z in segment]
        for segment in split_profile_by_radius_gap(upper_profile or [], max_gap=max_gap)
        if len(segment) >= 2
    ]
    lower_segments = [
        [[float(r), float(z)] for r, z in segment]
        for segment in split_profile_by_radius_gap(lower_profile or [], max_gap=max_gap)
        if len(segment) >= 2
    ]
    if not upper_segments or not lower_segments:
        return []

    regions = []
    used_lower = set()
    for upper_segment in upper_segments:
        upper_min = float(upper_segment[0][0])
        upper_max = float(upper_segment[-1][0])
        best_match = None
        for lower_idx, lower_segment in enumerate(lower_segments):
            lower_min = float(lower_segment[0][0])
            lower_max = float(lower_segment[-1][0])
            overlap_min = max(upper_min, lower_min)
            overlap_max = min(upper_max, lower_max)
            overlap_span = float(overlap_max - overlap_min)
            if overlap_span <= float(min_overlap):
                continue
            score = (
                overlap_span,
                -abs(((upper_min + upper_max) * 0.5) - ((lower_min + lower_max) * 0.5))
            )
            if best_match is None or score > best_match[0]:
                best_match = (score, lower_idx, lower_segment, overlap_min, overlap_max)
        if best_match is None:
            continue

        _, lower_idx, lower_segment, overlap_min, overlap_max = best_match
        if lower_idx in used_lower:
            continue

        sample_radii = sorted({
            round(float(r), 3)
            for r, _ in upper_segment
            if overlap_min - 1e-3 <= float(r) <= overlap_max + 1e-3
        } | {
            round(float(r), 3)
            for r, _ in lower_segment
            if overlap_min - 1e-3 <= float(r) <= overlap_max + 1e-3
        })
        if not sample_radii or sample_radii[0] > overlap_min + 0.25:
            sample_radii.insert(0, round(float(overlap_min), 3))
        if sample_radii[-1] < overlap_max - 0.25:
            sample_radii.append(round(float(overlap_max), 3))

        paired_upper = []
        paired_lower = []
        for radius_val in sample_radii:
            upper_z = interpolate_profile_z(upper_segment, radius_val)
            lower_z = interpolate_profile_z(lower_segment, radius_val)
            if upper_z is None or lower_z is None:
                continue
            paired_upper.append([round(float(radius_val), 3), round(float(upper_z), 3)])
            paired_lower.append([round(float(radius_val), 3), round(float(lower_z), 3)])

        region = build_section_region_from_envelopes(paired_upper, paired_lower)
        span_desc = describe_section_region_span(region)
        if region and span_desc and span_desc["radial_span"] >= 3.0 and span_desc["area"] >= 20.0:
            regions.append(region)
            used_lower.add(lower_idx)

    return regions

def select_spokeless_baseline_regions(spokeless_regions):
    """Keep only the innermost hub fragment and outermost rim fragment for no-spoke baselines."""
    descriptors = []
    for idx, region in enumerate(spokeless_regions or []):
        desc = describe_section_region_span(region)
        if desc is None:
            continue
        desc["index"] = int(idx)
        descriptors.append(desc)

    if not descriptors:
        return []

    hub_desc = min(
        descriptors,
        key=lambda item: (item["inner_r"], item["outer_r"], -item["area"])
    )
    rim_candidates = [item for item in descriptors if item["index"] != hub_desc["index"]]
    rim_desc = max(
        rim_candidates if rim_candidates else descriptors,
        key=lambda item: (item["outer_r"], item["radial_span"], item["area"])
    )

    selected_indices = [hub_desc["index"]]
    if rim_desc["index"] != hub_desc["index"]:
        selected_indices.append(rim_desc["index"])

    selected_regions = []
    for region_idx in selected_indices:
        if 0 <= int(region_idx) < len(spokeless_regions):
            selected_regions.append(spokeless_regions[int(region_idx)])
    return selected_regions

def select_spokeless_nospoke_regions(spokeless_regions, params=None):
    """Keep the rim fragment plus all hub-side fragments needed for a stable no-spoke revolve baseline."""
    params = params or {}
    descriptors = []
    for idx, region in enumerate(spokeless_regions or []):
        desc = describe_section_region_span(region)
        if desc is None:
            continue
        desc["index"] = int(idx)
        descriptors.append(desc)

    if not descriptors:
        return []

    rim_desc = max(
        descriptors,
        key=lambda item: (item["outer_r"], item["radial_span"], item["area"])
    )

    hub_radius = float(params.get("hub_radius", 0.0) or 0.0)
    pcd_radius = float(params.get("pcd_radius", 0.0) or 0.0)
    hole_radius = float(params.get("hole_radius", 0.0) or 0.0)
    window_inner_r = float(params.get("window_inner_reference_r", 0.0) or 0.0)

    hub_outer_limit = max(
        70.0,
        hub_radius * 1.38 if hub_radius > 0.0 else 0.0,
        pcd_radius + hole_radius + 22.0 if pcd_radius > 0.0 else 0.0,
        window_inner_r + 8.0 if window_inner_r > 0.0 else 0.0
    )
    hub_outer_limit = min(
        hub_outer_limit,
        float(rim_desc["inner_r"]) - 6.0 if rim_desc["inner_r"] > 12.0 else hub_outer_limit
    )

    hub_candidates = [
        item for item in descriptors
        if item["index"] != rim_desc["index"]
        and item["outer_r"] <= hub_outer_limit + 1e-6
        and item["area"] >= 20.0
    ]

    if not hub_candidates:
        inner_candidates = [item for item in descriptors if item["index"] != rim_desc["index"]]
        if inner_candidates:
            hub_candidates = sorted(
                inner_candidates,
                key=lambda item: (item["outer_r"], item["radial_span"], item["area"])
            )[:1]

    selected_indices = [item["index"] for item in sorted(hub_candidates, key=lambda item: (item["outer_r"], item["inner_r"]))]
    if rim_desc["index"] not in selected_indices:
        selected_indices.append(rim_desc["index"])

    selected_regions = []
    for region_idx in selected_indices:
        if 0 <= int(region_idx) < len(spokeless_regions):
            selected_regions.append(spokeless_regions[int(region_idx)])
    return selected_regions

def _iter_linear_geoms(geom):
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, LineString):
        return [geom]
    if isinstance(geom, MultiLineString):
        return list(geom.geoms)
    if isinstance(geom, GeometryCollection):
        lines = []
        for sub_geom in geom.geoms:
            lines.extend(_iter_linear_geoms(sub_geom))
        return lines
    return []

def extract_region_tangent_span(region, center_angle_deg, station_r, half_length=120.0):
    """Measure the footprint span of a spoke region on a radial section plane."""
    pts_region = region.get("points", []) if isinstance(region, dict) else region
    if len(pts_region) < 4:
        return None
    try:
        region_poly = normalize_geom(Polygon(pts_region))
    except Exception:
        return None
    if region_poly.is_empty:
        return None

    theta = math.radians(float(center_angle_deg))
    radial = np.asarray([math.cos(theta), math.sin(theta)], dtype=float)
    tangent = np.asarray([-math.sin(theta), math.cos(theta)], dtype=float)
    origin = radial * float(station_r)
    p0 = origin - (tangent * float(half_length))
    p1 = origin + (tangent * float(half_length))
    probe = LineString([(float(p0[0]), float(p0[1])), (float(p1[0]), float(p1[1]))])
    intersection = normalize_geom(region_poly.intersection(probe))
    line_geoms = _iter_linear_geoms(intersection)
    if not line_geoms:
        return None

    best_span = None
    best_len = 0.0
    for line in line_geoms:
        coords = list(line.coords)
        if len(coords) < 2:
            continue
        local_x = []
        for x, y in coords:
            vec = np.asarray([float(x), float(y)], dtype=float) - origin
            local_x.append(float(np.dot(vec, tangent)))
        span_len = max(local_x) - min(local_x)
        if span_len > best_len:
            best_len = span_len
            best_span = (min(local_x), max(local_x))
    return best_span

def project_mesh_section_to_spoke_plane(section_slice, plane_origin, tangent_vec):
    """Project a 3D mesh section onto a local spoke section plane (tangent-Z coordinates)."""
    if section_slice is None:
        return []
    origin = np.asarray(plane_origin, dtype=float)
    tangent = np.asarray(tangent_vec, dtype=float)
    tangent_norm = np.linalg.norm(tangent)
    if tangent_norm <= 1e-9:
        return []
    tangent = tangent / tangent_norm

    local_lines = []
    for entity in section_slice.entities:
        pts = np.asarray(section_slice.vertices[entity.points], dtype=float)
        if pts.shape[0] < 2:
            continue
        local_pts = []
        for pt in pts:
            rel = pt - origin
            local_pts.append((float(np.dot(rel, tangent)), float(rel[2] - origin[2])))
        if len(local_pts) >= 2:
            local_lines.append(local_pts)
    if not local_lines:
        return []

    try:
        merged = linemerge(MultiLineString(local_lines))
        polygons = list(polygonize(merged))
    except Exception:
        polygons = []
    return [normalize_geom(poly) for poly in polygons if not poly.is_empty]

def select_local_spoke_section_polygon(local_polygons, target_span=None, target_z_band=None, min_area=20.0, relaxed=False, extension_side=None):
    """Pick the local-plane polygon most likely to be the spoke member cross-section."""
    def clip_local_poly_to_target(local_poly):
        if local_poly is None or local_poly.is_empty or target_span is None:
            clipped_poly = local_poly
        else:
            try:
                target_min = float(min(target_span))
                target_max = float(max(target_span))
                target_width = max(0.5, target_max - target_min)
                coords = list(local_poly.exterior.coords)
                if len(coords) < 4:
                    clipped_poly = local_poly
                else:
                    ys = [float(y) for _, y in coords[:-1]]
                    if not ys:
                        clipped_poly = local_poly
                    else:
                        if relaxed:
                            x_pad = max(1.4, min(8.0, target_width * 0.55))
                            y_pad = max(5.0, min(18.0, target_width * 0.95))
                        else:
                            x_pad = max(1.0, min(3.4, target_width * 0.22))
                            y_pad = max(4.0, min(14.0, target_width * 0.65))
                        clip_box = Polygon([
                            (target_min - x_pad, min(ys) - y_pad),
                            (target_max + x_pad, min(ys) - y_pad),
                            (target_max + x_pad, max(ys) + y_pad),
                            (target_min - x_pad, max(ys) + y_pad),
                            (target_min - x_pad, min(ys) - y_pad),
                        ])
                        clipped = normalize_geom(local_poly.intersection(clip_box))
                        clipped_poly = largest_polygon(clipped, min_area=max(8.0, float(min_area) * 0.35))
                        if clipped_poly is None:
                            return None
            except Exception:
                clipped_poly = local_poly
        if clipped_poly is None or clipped_poly.is_empty or target_z_band is None:
            return clipped_poly
        try:
            z_min = float(min(target_z_band))
            z_max = float(max(target_z_band))
            coords = list(clipped_poly.exterior.coords)
            if len(coords) < 4:
                return clipped_poly
            xs = [float(x) for x, _ in coords[:-1]]
            ys = [float(y) for _, y in coords[:-1]]
            if not xs or not ys:
                return clipped_poly
            if relaxed:
                y_pad = max(1.2, min(6.0, (z_max - z_min) * 0.18 + 0.6))
            else:
                y_pad = max(0.8, min(3.2, (z_max - z_min) * 0.08))
            clip_box = Polygon([
                (min(xs) - 2.0, z_min - y_pad),
                (max(xs) + 2.0, z_min - y_pad),
                (max(xs) + 2.0, z_max + y_pad),
                (min(xs) - 2.0, z_max + y_pad),
                (min(xs) - 2.0, z_min - y_pad),
            ])
            clipped = normalize_geom(clipped_poly.intersection(clip_box))
            clipped_poly = largest_polygon(clipped, min_area=max(8.0, float(min_area) * 0.35))
            return clipped_poly if clipped_poly is not None else local_poly
        except Exception:
            return clipped_poly

    candidates = []
    target_center = None
    target_width = None
    target_z_center = None
    target_z_span = None
    if target_span is not None:
        target_center = (float(target_span[0]) + float(target_span[1])) * 0.5
        target_width = max(0.5, float(target_span[1]) - float(target_span[0]))
    if target_z_band is not None:
        target_z_center = (float(target_z_band[0]) + float(target_z_band[1])) * 0.5
        target_z_span = max(1.0, float(target_z_band[1]) - float(target_z_band[0]))

    for poly in local_polygons:
        poly = clip_local_poly_to_target(poly)
        if poly is None or poly.is_empty or poly.area < float(min_area):
            continue
        coords = list(poly.exterior.coords)
        if len(coords) < 4:
            continue
        xs = [float(x) for x, _ in coords[:-1]]
        ys = [float(y) for _, y in coords[:-1]]
        if not xs or not ys:
            continue
        x_span = max(xs) - min(xs)
        y_span = max(ys) - min(ys)
        if x_span < 1.0 or y_span < (2.0 if str(extension_side or "") == "root" else 3.0):
            continue

        x_mid = (max(xs) + min(xs)) * 0.5
        score = float(poly.area) * 0.06
        if min(xs) <= 0.0 <= max(xs):
            score += 120.0
        score -= abs(x_mid) * (10.0 if str(extension_side or "") == "root" else 18.0)
        if str(extension_side or "") == "root":
            score += y_span * 1.5

        if target_center is not None and target_width is not None:
            overlap = max(0.0, min(max(xs), target_span[1]) - max(min(xs), target_span[0]))
            union = max(max(xs), target_span[1]) - min(min(xs), target_span[0])
            overlap_ratio = overlap / max(union, 1e-6)
            width_ratio = x_span / max(target_width, 1e-6)
            width_error = abs(x_span - target_width)
            center_error = abs(x_mid - target_center)
            score += overlap_ratio * 900.0
            if str(extension_side or "") == "root":
                score -= center_error * 16.0
                score -= width_error * 4.0
            else:
                score -= center_error * 28.0
                score -= width_error * 10.0
            if relaxed:
                if str(extension_side or "") == "root":
                    if width_ratio > 2.6:
                        score -= (width_ratio - 2.6) * 36.0
                    if width_ratio > 6.0 and overlap_ratio < 0.18:
                        score -= 280.0
                elif width_ratio > 1.75:
                    score -= (width_ratio - 1.75) * 85.0
                if str(extension_side or "") != "root" and width_ratio > 4.8 and overlap_ratio < 0.28:
                    score -= 650.0
            else:
                if str(extension_side or "") == "root":
                    if width_ratio > 2.0:
                        score -= (width_ratio - 2.0) * 55.0
                    if width_ratio > 5.0 and overlap_ratio < 0.24:
                        score -= 420.0
                else:
                    if width_ratio > 1.25:
                        score -= (width_ratio - 1.25) * 140.0
                    if width_ratio > 3.5 and overlap_ratio < 0.35:
                        score -= 900.0

        if target_z_center is not None and target_z_span is not None:
            y_mid = (max(ys) + min(ys)) * 0.5
            y_ratio = y_span / max(target_z_span, 1e-6)
            y_center_error = abs(y_mid - target_z_center)
            score -= y_center_error * (2.0 if str(extension_side or "") == "root" else 6.0)
            if relaxed:
                if str(extension_side or "") == "root":
                    if y_ratio > 3.4:
                        score -= (y_ratio - 3.4) * 16.0
                    if y_ratio > 6.0:
                        score -= 90.0
                elif y_ratio > 1.75:
                    score -= (y_ratio - 1.75) * 45.0
                if str(extension_side or "") != "root" and y_ratio > 3.2:
                    score -= 220.0
            else:
                if str(extension_side or "") == "root":
                    if y_ratio > 2.6:
                        score -= (y_ratio - 2.6) * 28.0
                    if y_ratio > 5.0:
                        score -= 160.0
                else:
                    if y_ratio > 1.25:
                        score -= (y_ratio - 1.25) * 90.0
                    if y_ratio > 2.4:
                        score -= 420.0

        candidates.append((score, poly))

    if not candidates:
        return None
    return normalize_geom(max(candidates, key=lambda item: item[0])[1])

def build_local_spoke_section_record(
    mesh,
    member_region,
    center_angle_deg,
    station_r,
    target_z_band,
    span_region=None,
    min_area=24.0,
    half_length=None,
    relaxed=False,
    extension_side=None
):
    try:
        station_r = float(station_r)
    except Exception:
        return None

    theta = math.radians(float(center_angle_deg))
    plane_normal = np.asarray([math.cos(theta), math.sin(theta), 0.0], dtype=float)
    plane_x_dir = np.asarray([-math.sin(theta), math.cos(theta), 0.0], dtype=float)
    plane_origin = np.asarray([
        plane_normal[0] * station_r,
        plane_normal[1] * station_r,
        0.0
    ], dtype=float)

    try:
        section_slice = mesh.section(
            plane_origin=plane_origin.tolist(),
            plane_normal=plane_normal.tolist()
        )
    except Exception:
        section_slice = None
    if not section_slice:
        return None

    local_polygons = project_mesh_section_to_spoke_plane(
        section_slice,
        plane_origin,
        plane_x_dir
    )
    if not local_polygons:
        return None

    if half_length is None:
        half_length = max(120.0, station_r * 0.85)

    target_span = None
    if span_region is not None:
        target_span = extract_region_tangent_span(
            span_region,
            center_angle_deg,
            station_r,
            half_length=float(half_length)
        )
    if target_span is None:
        target_span = extract_region_tangent_span(
            member_region,
            center_angle_deg,
            station_r,
            half_length=float(half_length)
        )
    if target_span is None:
        return None

    section_poly = select_local_spoke_section_polygon(
        local_polygons,
        target_span=target_span,
        target_z_band=target_z_band,
        min_area=float(min_area),
        relaxed=bool(relaxed),
        extension_side=extension_side
    )
    if section_poly is None and relaxed:
        retry_min_area = max(8.0, float(min_area) * 0.45)
        section_poly = select_local_spoke_section_polygon(
            local_polygons,
            target_span=target_span,
            target_z_band=None,
            min_area=retry_min_area,
            relaxed=True,
            extension_side=extension_side
        )
    if section_poly is None and relaxed and span_region is not None:
        fallback_span = extract_region_tangent_span(
            member_region,
            center_angle_deg,
            station_r,
            half_length=float(half_length)
        )
        if fallback_span is not None:
            retry_min_area = max(8.0, float(min_area) * 0.40)
            section_poly = select_local_spoke_section_polygon(
                local_polygons,
                target_span=fallback_span,
                target_z_band=None,
                min_area=retry_min_area,
                relaxed=True,
                extension_side=extension_side
            )
    if section_poly is None:
        return None

    local_width_est = max(1.0, float(abs(target_span[1] - target_span[0])))
    simplify_tol = max(0.06, min(0.16, local_width_est * 0.010))
    try:
        section_poly = normalize_geom(section_poly.simplify(simplify_tol, preserve_topology=True))
    except Exception:
        pass
    if section_poly is None or section_poly.is_empty:
        return None

    local_coords = canonicalize_loop(list(section_poly.exterior.coords))
    if len(local_coords) < 4:
        return None

    local_xs = [float(pt[0]) for pt in local_coords]
    local_ys = [float(pt[1]) for pt in local_coords]
    if not local_xs or not local_ys:
        return None

    return {
        "station_r": round(float(station_r), 2),
        "plane_origin": [
            round(float(plane_origin[0]), 3),
            round(float(plane_origin[1]), 3),
            round(float(plane_origin[2]), 3)
        ],
        "plane_normal": [
            round(float(plane_normal[0]), 6),
            round(float(plane_normal[1]), 6),
            0.0
        ],
        "plane_x_dir": [
            round(float(plane_x_dir[0]), 6),
            round(float(plane_x_dir[1]), 6),
            0.0
        ],
        "points_local": local_coords,
        "target_span": [
            round(float(target_span[0]), 3),
            round(float(target_span[1]), 3)
        ],
        "target_width": round(float(abs(target_span[1] - target_span[0])), 3),
        "target_center_x": round(float((target_span[0] + target_span[1]) * 0.5), 3),
        "local_width": round(float(max(local_xs) - min(local_xs)), 3),
        "local_height": round(float(max(local_ys) - min(local_ys)), 3),
        "local_center_x": round(float((max(local_xs) + min(local_xs)) * 0.5), 3),
        "target_z_band": [
            round(float(target_z_band[0]), 3),
            round(float(target_z_band[1]), 3)
        ] if target_z_band is not None else [],
        "extension_side": extension_side if extension_side else None
    }

def extend_spoke_section_records_with_actual_slices(
    mesh,
    member_region,
    center_angle_deg,
    section_records,
    target_z_band,
    inner_target_r=None,
    outer_target_r=None,
    root_points=None,
    tip_sections=None
):
    ordered_sections = sorted(
        [section for section in (section_records or []) if isinstance(section, dict)],
        key=lambda section: float(section.get("station_r", 0.0))
    )
    if len(ordered_sections) < 2:
        return ordered_sections

    projected_strip = build_projected_section_strip(
        ordered_sections,
        extend_inner_r=inner_target_r,
        extend_outer_r=outer_target_r,
        inner_width_scale=1.03,
        outer_width_scale=1.06
    )
    if projected_strip is None or projected_strip.is_empty:
        return ordered_sections

    strip_coords = [
        [round(float(x), 3), round(float(y), 3)]
        for x, y in list(projected_strip.exterior.coords)
    ]
    if len(strip_coords) < 4:
        return ordered_sections
    main_span_poly = normalize_geom(Polygon(strip_coords))
    if main_span_poly.is_empty:
        return ordered_sections

    first_station_r = float(ordered_sections[0].get("station_r", 0.0))
    last_station_r = float(ordered_sections[-1].get("station_r", 0.0))
    radius_span = max(1.0, last_station_r - first_station_r)
    half_length = max(120.0, last_station_r * 0.85)
    extra_sections = []
    root_span_poly = main_span_poly
    tip_span_poly = main_span_poly

    if root_points and len(root_points) >= 4:
        try:
            root_poly = largest_polygon(normalize_geom(Polygon(root_points)), min_area=8.0)
        except Exception:
            root_poly = None
        if root_poly is not None and (not root_poly.is_empty):
            try:
                root_span_poly = largest_polygon(
                    normalize_geom(unary_union([
                        main_span_poly,
                        root_poly.buffer(max(1.4, radius_span * 0.040), join_style=2)
                    ])),
                    min_area=8.0
                ) or root_span_poly
            except Exception:
                pass

    projected_tip_strip = build_projected_section_strip(
        tip_sections,
        extend_outer_r=outer_target_r,
        outer_width_scale=1.12
    )
    if projected_tip_strip is not None and (not projected_tip_strip.is_empty):
        try:
            tip_span_poly = largest_polygon(
                normalize_geom(unary_union([
                    main_span_poly,
                    projected_tip_strip.buffer(max(0.8, radius_span * 0.018), join_style=2)
                ])),
                min_area=8.0
            ) or tip_span_poly
        except Exception:
            pass
    elif member_region and len(member_region) >= 4:
        try:
            member_poly = largest_polygon(normalize_geom(Polygon(member_region)), min_area=8.0)
        except Exception:
            member_poly = None
        if member_poly is not None and (not member_poly.is_empty):
            try:
                tip_span_poly = largest_polygon(
                    normalize_geom(unary_union([
                        main_span_poly,
                        member_poly.buffer(max(0.6, radius_span * 0.012), join_style=2)
                    ])),
                    min_area=8.0
                ) or tip_span_poly
            except Exception:
                pass

    first_height = float(ordered_sections[0].get("local_height", 0.0) or 0.0)
    last_height = float(ordered_sections[-1].get("local_height", 0.0) or 0.0)

    def append_samples(target_r, use_inner_side):
        if target_r is None:
            return
        target_r = float(target_r)
        boundary_r = first_station_r if use_inner_side else last_station_r
        gap = (boundary_r - target_r) if use_inner_side else (target_r - boundary_r)
        if gap <= 0.45:
            return
        if use_inner_side:
            step_count = 2
            if gap > 2.5:
                step_count = 3
            if gap > 6.0:
                step_count = 4
            if gap > 10.0:
                step_count = 5
        else:
            step_count = 1
            if gap > 4.0:
                step_count = 2
            if gap > 8.5:
                step_count = 3
        if use_inner_side:
            target_positions = np.linspace(target_r, boundary_r, step_count + 1)[:-1]
        else:
            target_positions = np.linspace(boundary_r, target_r, step_count + 1)[1:]
        for sample_idx, sample_r in enumerate(target_positions):
            terminal_sample = bool(sample_idx == 0) if use_inner_side else bool(sample_idx == (len(target_positions) - 1))
            if use_inner_side:
                sample_band = None
            elif target_z_band is not None and len(target_z_band) >= 2:
                base_low = float(min(target_z_band))
                base_high = float(max(target_z_band))
                boundary_height = first_height if use_inner_side else last_height
                z_pad = max(1.6, boundary_height * (0.42 if use_inner_side else (0.34 if terminal_sample else 0.24)))
                sample_band = (base_low - z_pad, base_high + z_pad)
            else:
                sample_band = target_z_band
            span_poly = root_span_poly if use_inner_side else tip_span_poly
            span_region = None
            if span_poly is not None and (not span_poly.is_empty):
                active_span_poly = span_poly
                if terminal_sample:
                    try:
                        active_span_poly = largest_polygon(
                            normalize_geom(span_poly.buffer(max(1.0, radius_span * (0.030 if use_inner_side else 0.024)), join_style=2)),
                            min_area=8.0
                        ) or span_poly
                    except Exception:
                        active_span_poly = span_poly
                span_region = {
                    "points": [
                        [round(float(x), 3), round(float(y), 3)]
                        for x, y in list(active_span_poly.exterior.coords)
                    ]
                }
            extension_side = "root" if use_inner_side else "tip"
            if terminal_sample:
                extension_side = "root_terminal" if use_inner_side else "tip_terminal"
            section_record = build_local_spoke_section_record(
                mesh,
                member_region,
                center_angle_deg,
                float(sample_r),
                sample_band,
                span_region=span_region,
                min_area=(8.0 if terminal_sample else (10.0 if use_inner_side else 18.0)),
                half_length=max(140.0 if use_inner_side else half_length, radius_span * ((1.85 if terminal_sample else 1.6) if use_inner_side else (1.24 if terminal_sample else 1.1))),
                relaxed=True,
                extension_side=extension_side
            )
            if section_record is not None:
                if terminal_sample:
                    section_record["terminal_contact"] = True
                    section_record["preserve_detail"] = True
                extra_sections.append(section_record)

    append_samples(inner_target_r, use_inner_side=True)
    append_samples(outer_target_r, use_inner_side=False)

    if not extra_sections:
        return ordered_sections

    merged = ordered_sections + extra_sections
    dedup = {}
    for section in merged:
        try:
            key = round(float(section.get("station_r", 0.0)), 2)
        except Exception:
            continue
        if key not in dedup:
            dedup[key] = section
            continue
        current_width = float(section.get("local_width", 0.0) or 0.0)
        prev_width = float(dedup[key].get("local_width", 0.0) or 0.0)
        if current_width > prev_width:
            dedup[key] = section

    return sorted(dedup.values(), key=lambda section: float(section.get("station_r", 0.0)))

def infer_spoke_motif_topology(spoke_regions, spoke_voids):
    """Infer repeat order and grouped spoke motifs from angular gap structure."""
    spoke_entries = []
    for idx, region in enumerate(spoke_regions or []):
        desc = describe_planar_region(region, min_area=40.0)
        if desc is None:
            continue
        desc["index"] = idx
        spoke_entries.append(desc)

    void_entries = []
    for idx, region in enumerate(spoke_voids or []):
        desc = describe_planar_region(region, min_area=30.0)
        if desc is None:
            continue
        desc["index"] = idx
        void_entries.append(desc)

    if not spoke_entries:
        return {
            "spoke_count": 0,
            "window_count": len(void_entries),
            "repeat_order": 0,
            "motif_count": 0,
            "members_per_motif": 0,
            "motif_type": "unknown",
            "gap_threshold_deg": None,
            "gap_stats": {},
            "groups": [],
            "boundary_gap_indices": []
        }

    spoke_entries = sorted(spoke_entries, key=lambda item: float(item["angle"]))
    angles = [float(item["angle"]) for item in spoke_entries]
    gap_values = []
    for idx, angle_val in enumerate(angles):
        next_angle = angles[(idx + 1) % len(angles)]
        gap_val = (next_angle - angle_val) % 360.0
        if gap_val <= 0.0:
            gap_val += 360.0
        gap_values.append(float(gap_val))

    boundary_gap_indices = []
    gap_threshold = None
    gap_stats = {
        "min_gap_deg": round(float(min(gap_values)), 3),
        "max_gap_deg": round(float(max(gap_values)), 3),
        "median_gap_deg": round(float(np.median(np.asarray(gap_values, dtype=float))), 3)
    }

    def build_groups_from_boundary_indices(boundary_indices):
        if not boundary_indices:
            return [[idx] for idx in range(len(spoke_entries))]
        n = len(spoke_entries)
        boundary_set = set(boundary_indices)
        start_idx = (boundary_indices[0] + 1) % n
        traversal = []
        idx = start_idx
        for _ in range(n):
            traversal.append(idx)
            idx = (idx + 1) % n
        built_groups = []
        current_group = []
        for local_idx in traversal:
            current_group.append(local_idx)
            if local_idx in boundary_set and current_group:
                built_groups.append(current_group)
                current_group = []
        if current_group:
            built_groups.append(current_group)
        return built_groups

    if len(gap_values) >= 4:
        gap_arr = np.asarray(gap_values, dtype=float)
        sorted_gap_vals = np.sort(gap_arr)
        best_split = None
        for split_idx in range(1, len(sorted_gap_vals)):
            lower = sorted_gap_vals[:split_idx]
            upper = sorted_gap_vals[split_idx:]
            if len(lower) < 2 or len(upper) < 1:
                continue
            threshold = float((lower[-1] + upper[0]) * 0.5)
            large_mask = gap_arr >= threshold
            large_count = int(np.count_nonzero(large_mask))
            small_count = int(len(gap_arr) - large_count)
            if small_count < 2 or large_count < 1 or large_count > max(1, len(gap_arr) // 2):
                continue
            small_mean = float(np.mean(gap_arr[~large_mask]))
            large_mean = float(np.mean(gap_arr[large_mask]))
            ratio = large_mean / max(1e-6, small_mean)
            separation = (large_mean - small_mean) / max(1e-6, float(np.std(gap_arr)) + 1e-6)
            balance = min(small_count, large_count) / max(small_count, large_count)
            score = (ratio * 1.8) + separation + (balance * 0.25)
            if best_split is None or score > best_split["score"]:
                best_split = {
                    "threshold": threshold,
                    "ratio": ratio,
                    "separation": separation,
                    "large_mask": large_mask,
                    "score": score,
                    "small_mean": small_mean,
                    "large_mean": large_mean
                }

        if best_split is not None and best_split["ratio"] >= 1.22 and best_split["separation"] >= 0.85:
            gap_threshold = float(best_split["threshold"])
            boundary_gap_indices = [
                idx for idx, gap_val in enumerate(gap_values)
                if gap_val >= gap_threshold
            ]
            gap_stats.update({
                "small_gap_mean_deg": round(float(best_split["small_mean"]), 3),
                "large_gap_mean_deg": round(float(best_split["large_mean"]), 3),
                "gap_ratio": round(float(best_split["ratio"]), 3),
                "gap_separation": round(float(best_split["separation"]), 3)
            })

    groups = build_groups_from_boundary_indices(boundary_gap_indices)

    if len(groups) == len(spoke_entries) and len(void_entries) >= len(spoke_entries):
        gap_mid_angles = []
        for idx, angle_val in enumerate(angles):
            next_angle = angles[(idx + 1) % len(angles)]
            gap_val = (next_angle - angle_val) % 360.0
            if gap_val <= 0.0:
                gap_val += 360.0
            gap_mid_angles.append((angle_val + (gap_val * 0.5)) % 360.0)

        gap_to_void = {}
        used_void_indices = set()
        for gap_idx, gap_mid_angle in enumerate(gap_mid_angles):
            best_void_idx = None
            best_dist = None
            for void_idx, entry in enumerate(void_entries):
                if void_idx in used_void_indices:
                    continue
                dist = angular_distance_deg(float(entry["angle"]), gap_mid_angle)
                if best_dist is None or dist < best_dist:
                    best_dist = dist
                    best_void_idx = void_idx
            if best_void_idx is not None:
                used_void_indices.add(best_void_idx)
                gap_to_void[gap_idx] = void_entries[best_void_idx]

        matched_void_spans = np.asarray(
            [float(entry["span"]) for entry in gap_to_void.values() if entry.get("span") is not None],
            dtype=float
        )
        if len(matched_void_spans) >= 4:
            sorted_void_spans = np.sort(matched_void_spans)
            best_void_split = None
            for split_idx in range(1, len(sorted_void_spans)):
                lower = sorted_void_spans[:split_idx]
                upper = sorted_void_spans[split_idx:]
                if len(lower) < 2 or len(upper) < 2:
                    continue
                threshold = float((lower[-1] + upper[0]) * 0.5)
                large_gap_candidates = []
                small_spans = []
                large_spans = []
                for gap_idx, entry in gap_to_void.items():
                    span_val = float(entry["span"])
                    if span_val >= threshold:
                        large_gap_candidates.append(gap_idx)
                        large_spans.append(span_val)
                    else:
                        small_spans.append(span_val)
                if len(large_gap_candidates) < 2 or len(large_gap_candidates) > max(1, len(spoke_entries) // 2):
                    continue
                small_mean = float(np.mean(np.asarray(small_spans, dtype=float)))
                large_mean = float(np.mean(np.asarray(large_spans, dtype=float)))
                ratio = large_mean / max(1e-6, small_mean)
                separation = (large_mean - small_mean) / max(1e-6, float(np.std(matched_void_spans)) + 1e-6)
                score = (ratio * 2.0) + separation
                if best_void_split is None or score > best_void_split["score"]:
                    best_void_split = {
                        "threshold": threshold,
                        "large_gap_indices": sorted(large_gap_candidates),
                        "small_mean": small_mean,
                        "large_mean": large_mean,
                        "ratio": ratio,
                        "separation": separation,
                        "score": score
                    }

            if best_void_split is not None and best_void_split["ratio"] >= 1.22 and best_void_split["separation"] >= 0.9:
                void_based_groups = build_groups_from_boundary_indices(best_void_split["large_gap_indices"])
                if len(void_based_groups) < len(groups):
                    groups = void_based_groups
                    boundary_gap_indices = list(best_void_split["large_gap_indices"])
                    gap_threshold = float(best_void_split["threshold"])
                    gap_stats.update({
                        "void_small_span_mean_deg": round(float(best_void_split["small_mean"]), 3),
                        "void_large_span_mean_deg": round(float(best_void_split["large_mean"]), 3),
                        "void_gap_ratio": round(float(best_void_split["ratio"]), 3),
                        "void_gap_separation": round(float(best_void_split["separation"]), 3)
                    })

    group_payloads = []
    group_sizes = []
    for group_idx, group in enumerate(groups):
        member_entries = [spoke_entries[idx] for idx in group]
        member_angles = [float(item["angle"]) for item in member_entries]
        member_indices = [int(item["index"]) for item in member_entries]
        spans = [float(item["span"]) for item in member_entries]
        radii_outer = [float(item["outer_r"]) for item in member_entries]
        radii_inner = [float(item["inner_r"]) for item in member_entries]
        angle_window = continuous_angle_window(member_angles)
        if angle_window is None:
            group_start = min(member_angles)
            group_end = max(member_angles)
            group_span = group_end - group_start
        else:
            group_start, group_end, group_span = angle_window
        group_payloads.append({
            "group_index": int(group_idx),
            "member_indices": member_indices,
            "member_angles": [round(float(angle), 3) for angle in member_angles],
            "member_count": int(len(member_indices)),
            "group_angle": round(float(circular_mean_degrees(member_angles)), 3),
            "group_start_angle": round(float(group_start % 360.0), 3),
            "group_end_angle": round(float(group_end % 360.0), 3),
            "group_span_deg": round(float(group_span), 3),
            "member_span_mean_deg": round(float(np.mean(np.asarray(spans, dtype=float))), 3),
            "inner_r": round(float(min(radii_inner)), 3),
            "outer_r": round(float(max(radii_outer)), 3)
        })
        group_sizes.append(len(member_indices))

    if not group_sizes:
        motif_count = 0
        members_per_motif = 0
        motif_type = "unknown"
    else:
        motif_count = len(group_sizes)
        uniform_grouping = len(set(group_sizes)) == 1
        if motif_count == len(spoke_entries):
            members_per_motif = 1
            motif_type = "single_spoke"
        elif uniform_grouping and group_sizes[0] == 2:
            members_per_motif = 2
            motif_type = "paired_spoke"
        elif uniform_grouping:
            members_per_motif = int(group_sizes[0])
            motif_type = f"grouped_spoke_{members_per_motif}"
        else:
            members_per_motif = round(float(np.mean(np.asarray(group_sizes, dtype=float))), 2)
            motif_type = "mixed_grouped_spoke"

    return {
        "spoke_count": int(len(spoke_entries)),
        "window_count": int(len(void_entries)),
        "repeat_order": int(motif_count if motif_count > 0 else len(spoke_entries)),
        "motif_count": int(motif_count),
        "members_per_motif": members_per_motif,
        "motif_type": motif_type,
        "gap_threshold_deg": round(float(gap_threshold), 3) if gap_threshold is not None else None,
        "gap_stats": gap_stats,
        "groups": group_payloads,
        "boundary_gap_indices": [int(idx) for idx in boundary_gap_indices]
    }

def extract_projected_section_sample(section_payload):
    if not isinstance(section_payload, dict):
        return None

    pts_local = section_payload.get("points_local", []) or []
    plane_origin = section_payload.get("plane_origin", []) or []
    plane_x_dir = section_payload.get("plane_x_dir", []) or []
    if len(pts_local) < 4 or len(plane_origin) < 2 or len(plane_x_dir) < 2:
        return None

    samples = pts_local[:-1] if len(pts_local) >= 5 else pts_local
    try:
        x_vals = [float(x) for x, _ in samples]
    except Exception:
        return None
    if not x_vals:
        return None

    x_min = min(x_vals)
    x_max = max(x_vals)
    target_span = section_payload.get("target_span", []) or []
    if len(target_span) >= 2:
        try:
            target_min = float(min(target_span))
            target_max = float(max(target_span))
            target_width = max(0.5, target_max - target_min)
            target_pad = max(1.0, min(5.0, target_width * 0.32))
            clipped_min = max(x_min, target_min - target_pad)
            clipped_max = min(x_max, target_max + target_pad)
            if clipped_max > clipped_min + 0.35:
                x_min = clipped_min
                x_max = clipped_max
        except Exception:
            pass

    if x_max <= x_min + 0.35:
        return None

    origin_xy = np.asarray([float(plane_origin[0]), float(plane_origin[1])], dtype=float)
    tangent_dir = np.asarray([float(plane_x_dir[0]), float(plane_x_dir[1])], dtype=float)
    tangent_norm = np.linalg.norm(tangent_dir)
    if tangent_norm <= 1e-9:
        return None
    tangent_dir = tangent_dir / tangent_norm
    left_xy = origin_xy + (tangent_dir * x_min)
    right_xy = origin_xy + (tangent_dir * x_max)
    station_r = float(section_payload.get("station_r", math.hypot(float(origin_xy[0]), float(origin_xy[1]))))
    width = float(np.linalg.norm(right_xy - left_xy))
    if width <= 0.35:
        return None

    return {
        "station_r": station_r,
        "left_xy": left_xy,
        "right_xy": right_xy,
        "center_xy": (left_xy + right_xy) * 0.5,
        "tangent_dir": tangent_dir,
        "width": width
    }


def extend_projected_section_sample(sample, target_r, width_scale=1.0):
    if not isinstance(sample, dict):
        return None
    try:
        target_r = float(target_r)
    except Exception:
        return None

    center_xy = np.asarray(sample.get("center_xy", [0.0, 0.0]), dtype=float)
    tangent_dir = np.asarray(sample.get("tangent_dir", [0.0, 0.0]), dtype=float)
    tangent_norm = np.linalg.norm(tangent_dir)
    center_norm = np.linalg.norm(center_xy)
    if tangent_norm <= 1e-9 or center_norm <= 1e-9:
        return None

    tangent_dir = tangent_dir / tangent_norm
    radial_dir = center_xy / center_norm
    half_width = max(0.4, float(sample.get("width", 0.8)) * 0.5 * max(0.75, float(width_scale)))
    target_center = radial_dir * target_r
    left_xy = target_center - (tangent_dir * half_width)
    right_xy = target_center + (tangent_dir * half_width)
    return {
        "station_r": target_r,
        "left_xy": left_xy,
        "right_xy": right_xy,
        "center_xy": target_center,
        "tangent_dir": tangent_dir,
        "width": float(np.linalg.norm(right_xy - left_xy))
    }


def build_projected_section_strip(
    section_payloads,
    extend_inner_r=None,
    extend_outer_r=None,
    inner_width_scale=1.04,
    outer_width_scale=1.08
):
    samples = []
    for section_payload in section_payloads or []:
        sample = extract_projected_section_sample(section_payload)
        if sample is None:
            continue
        samples.append(sample)

    if len(samples) < 2:
        return None

    samples.sort(key=lambda item: item["station_r"])
    first_sample = samples[0]
    last_sample = samples[-1]

    try:
        if extend_inner_r is not None and float(extend_inner_r) < first_sample["station_r"] - 0.25:
            extended_first = extend_projected_section_sample(
                first_sample,
                float(extend_inner_r),
                width_scale=float(inner_width_scale)
            )
            if extended_first is not None:
                samples = [extended_first] + samples
        if extend_outer_r is not None and float(extend_outer_r) > last_sample["station_r"] + 0.25:
            extended_last = extend_projected_section_sample(
                last_sample,
                float(extend_outer_r),
                width_scale=float(outer_width_scale)
            )
            if extended_last is not None:
                samples = samples + [extended_last]
    except Exception:
        pass

    outline = []
    for sample in samples:
        outline.append((round(float(sample["left_xy"][0]), 3), round(float(sample["left_xy"][1]), 3)))
    for sample in reversed(samples):
        outline.append((round(float(sample["right_xy"][0]), 3), round(float(sample["right_xy"][1]), 3)))
    if len(outline) < 4:
        return None
    outline.append(outline[0])

    try:
        strip_poly = normalize_geom(Polygon(outline))
    except Exception:
        return None
    if strip_poly is None or strip_poly.is_empty or float(strip_poly.area) < 8.0:
        return None
    return strip_poly


def build_member_actual_slice_guide(
    region_points,
    member_sections=None,
    root_points=None,
    tip_sections=None,
    buffer_pad=0.8,
    guide_inner_r=None,
    guide_outer_r=None,
    relaxed=False
):
    geoms = []
    region_limit = None
    if region_points and len(region_points) >= 4:
        try:
            region_poly = normalize_geom(Polygon(region_points))
        except Exception:
            region_poly = None
        if region_poly is not None and (not region_poly.is_empty) and float(region_poly.area) >= 8.0:
            region_limit = region_poly.buffer(max(0.34, float(buffer_pad) * 0.42), join_style=2)

    if root_points and len(root_points) >= 4:
        try:
            root_poly = normalize_geom(Polygon(root_points))
        except Exception:
            root_poly = None
        if root_poly is not None and (not root_poly.is_empty) and float(root_poly.area) >= 8.0:
            geoms.append(root_poly.buffer(max(0.36, float(buffer_pad) * 0.70), join_style=2))

    projected_member_strip = build_projected_section_strip(
        member_sections,
        extend_inner_r=guide_inner_r,
        extend_outer_r=guide_outer_r,
        inner_width_scale=(1.16 if relaxed else 1.08),
        outer_width_scale=(1.18 if relaxed else 1.10)
    )
    if projected_member_strip is not None and (not projected_member_strip.is_empty):
        geoms.append(
            projected_member_strip.buffer(
                max(0.24 if relaxed else 0.18, float(buffer_pad) * (0.34 if relaxed else 0.24)),
                join_style=2
            )
        )

    tip_inner_seed = None
    if guide_outer_r is not None:
        radial_seed_span = max(
            18.0,
            min(
                36.0,
                ((float(guide_outer_r) - float(guide_inner_r if guide_inner_r is not None else 0.0)) * 0.42) + 4.0
            )
        )
        tip_inner_seed = max(
            float(guide_inner_r if guide_inner_r is not None else 0.0),
            float(guide_outer_r) - radial_seed_span
        )
    projected_tip_strip = build_projected_section_strip(
        tip_sections,
        extend_inner_r=tip_inner_seed,
        extend_outer_r=guide_outer_r,
        inner_width_scale=(1.32 if relaxed else 1.20),
        outer_width_scale=(1.34 if relaxed else 1.22)
    )
    if projected_tip_strip is not None and (not projected_tip_strip.is_empty):
        geoms.append(
            projected_tip_strip.buffer(
                max(0.38 if relaxed else 0.28, float(buffer_pad) * (0.48 if relaxed else 0.34)),
                join_style=2
            )
        )

    if not geoms:
        return region_limit if region_limit is not None and (not region_limit.is_empty) else None
    try:
        merged = normalize_geom(unary_union(geoms))
        if region_limit is not None and (not region_limit.is_empty):
            overlap_limit = region_limit.intersection(
                merged.buffer(max(0.54 if relaxed else 0.38, float(buffer_pad) * (0.76 if relaxed else 0.58)), join_style=2)
            )
            merged = normalize_geom(unary_union([merged, overlap_limit]))
        merged = normalize_geom(
            merged.buffer(max(0.18 if relaxed else 0.12, float(buffer_pad) * (0.30 if relaxed else 0.20)), join_style=2)
            .buffer(-max(0.09 if relaxed else 0.06, float(buffer_pad) * (0.12 if relaxed else 0.08)), join_style=2)
        )
        return merged if merged is not None and (not merged.is_empty) else None
    except Exception:
        return None

def build_member_actual_z_slice_guide(
    member_sections,
    z_level,
    member_angle_deg,
    guide_inner_r=None,
    guide_outer_r=None,
    region_points=None,
    base_guide=None,
    root_points=None,
    tip_sections=None,
    terminal_relax=0.0
):
    section_low_values = []
    section_high_values = []
    root_clip_support = None
    tip_clip_support = None
    terminal_relax = float(terminal_relax or 0.0)

    def sample_span(section_payload, target_z):
        pts_local = section_payload.get("points_local", []) or []
        plane_origin = section_payload.get("plane_origin", []) or []
        plane_x_dir = section_payload.get("plane_x_dir", []) or []
        if len(pts_local) < 4 or len(plane_origin) < 3 or len(plane_x_dir) < 2:
            return None

        try:
            local_poly = largest_polygon(normalize_geom(Polygon(pts_local)), min_area=2.0)
        except Exception:
            local_poly = None
        if local_poly is None or local_poly.is_empty:
            return None

        target_span = section_payload.get("target_span", []) or []
        if len(target_span) >= 2:
            try:
                target_min = float(min(target_span))
                target_max = float(max(target_span))
                target_width = max(0.5, target_max - target_min)
                target_pad = max(0.8, min(4.0, target_width * 0.28))
                clip_box = Polygon([
                    (target_min - target_pad, -1000.0),
                    (target_max + target_pad, -1000.0),
                    (target_max + target_pad, 1000.0),
                    (target_min - target_pad, 1000.0),
                    (target_min - target_pad, -1000.0),
                ])
                clipped_poly = largest_polygon(normalize_geom(local_poly.intersection(clip_box)), min_area=2.0)
                if clipped_poly is not None and (not clipped_poly.is_empty):
                    local_poly = clipped_poly
            except Exception:
                pass

        coords = list(local_poly.exterior.coords)
        if len(coords) < 4:
            return None
        xs = [float(x) for x, _ in coords[:-1]]
        ys = [float(y) for _, y in coords[:-1]]
        if not xs or not ys:
            return None

        origin_z = float(plane_origin[2])
        local_z_level = float(target_z) - origin_z
        if local_z_level < min(ys) - 0.12 or local_z_level > max(ys) + 0.12:
            return None

        probe = LineString([
            (min(xs) - 2.0, float(local_z_level)),
            (max(xs) + 2.0, float(local_z_level))
        ])
        hit = local_poly.intersection(probe)
        x_samples = []

        def collect_x(geom):
            if geom is None or geom.is_empty:
                return
            if isinstance(geom, Point):
                x_samples.append(float(geom.x))
                return
            if isinstance(geom, LineString):
                for x_val, _ in list(geom.coords):
                    x_samples.append(float(x_val))
                return
            if isinstance(geom, MultiLineString):
                for sub in geom.geoms:
                    collect_x(sub)
                return
            if isinstance(geom, GeometryCollection):
                for sub in geom.geoms:
                    collect_x(sub)
                return
            if hasattr(geom, "geoms"):
                for sub in geom.geoms:
                    collect_x(sub)

        collect_x(hit)
        if len(x_samples) < 2:
            return None

        x_min = min(x_samples)
        x_max = max(x_samples)
        if x_max <= x_min + 0.35:
            return None

        origin_xy = np.asarray([float(plane_origin[0]), float(plane_origin[1])], dtype=float)
        x_dir_xy = np.asarray([float(plane_x_dir[0]), float(plane_x_dir[1])], dtype=float)
        norm = np.linalg.norm(x_dir_xy)
        if norm <= 1e-9:
            return None
        x_dir_xy = x_dir_xy / norm

        left_xy = origin_xy + (x_dir_xy * float(x_min))
        right_xy = origin_xy + (x_dir_xy * float(x_max))
        station_r = float(section_payload.get("station_r", math.hypot(origin_xy[0], origin_xy[1])))
        return station_r, left_xy, right_xy

    def relocate_span(span_entry, target_r):
        try:
            _, left_xy, right_xy = span_entry
            left = np.asarray(left_xy, dtype=float)
            right = np.asarray(right_xy, dtype=float)
            midpoint = (left + right) * 0.5
            offset_left = left - midpoint
            offset_right = right - midpoint
            mid_norm = float(np.linalg.norm(midpoint))
            if mid_norm <= 1e-9:
                angle_rad = math.radians(float(member_angle_deg or 0.0))
                new_mid = np.asarray([
                    math.cos(angle_rad) * float(target_r),
                    math.sin(angle_rad) * float(target_r)
                ], dtype=float)
            else:
                new_mid = (midpoint / mid_norm) * float(target_r)
            return (
                float(target_r),
                np.asarray(new_mid + offset_left, dtype=float),
                np.asarray(new_mid + offset_right, dtype=float)
            )
        except Exception:
            return None

    samples = []
    for section_payload in member_sections or []:
        pts_local = section_payload.get("points_local", []) or []
        plane_origin = section_payload.get("plane_origin", []) or []
        if len(pts_local) >= 4 and len(plane_origin) >= 3:
            local_samples = pts_local[:-1] if len(pts_local) >= 5 else pts_local
            try:
                ys = [float(y_val) for _, y_val in local_samples]
            except Exception:
                ys = []
            if ys:
                base_z = float(plane_origin[2])
                section_low_values.append(base_z + min(ys))
                section_high_values.append(base_z + max(ys))
        span_entry = sample_span(section_payload, z_level)
        if span_entry is None:
            continue
        samples.append(span_entry)

    samples.sort(key=lambda item: item[0])
    guide_samples = list(samples)
    below_section_band = bool(section_low_values) and float(z_level) < (min(section_low_values) - 0.05)
    above_section_band = bool(section_high_values) and float(z_level) > (max(section_high_values) + 0.05)

    def extend_samples(boundary_target_r, use_inner_side):
        nonlocal guide_samples
        if boundary_target_r is None or not guide_samples:
            return
        boundary_target_r = float(boundary_target_r)
        boundary_sample = guide_samples[0] if use_inner_side else guide_samples[-1]
        boundary_r = float(boundary_sample[0])
        gap = (boundary_r - boundary_target_r) if use_inner_side else (boundary_target_r - boundary_r)
        if gap <= 0.35:
            return
        step_count = 1
        if gap > 4.0:
            step_count = 2
        if gap > 9.0:
            step_count = 3
        if gap > 14.0:
            step_count = 4
        if gap > 20.0:
            step_count = 5
        if use_inner_side:
            target_positions = np.linspace(boundary_target_r, boundary_r, step_count + 1)[:-1]
        else:
            target_positions = np.linspace(boundary_r, boundary_target_r, step_count + 1)[1:]
        extensions = []
        for target_r in target_positions:
            ext_sample = relocate_span(boundary_sample, float(target_r))
            if ext_sample is not None:
                extensions.append(ext_sample)
        if not extensions:
            return
        guide_samples = (extensions + guide_samples) if use_inner_side else (guide_samples + extensions)

    guide_parts = []
    if len(guide_samples) >= 2:
        extend_samples(guide_inner_r, use_inner_side=True)
        extend_samples(guide_outer_r, use_inner_side=False)

        outline = []
        for _, left_xy, _ in guide_samples:
            outline.append((round(float(left_xy[0]), 3), round(float(left_xy[1]), 3)))
        for _, _, right_xy in reversed(guide_samples):
            outline.append((round(float(right_xy[0]), 3), round(float(right_xy[1]), 3)))
        if len(outline) >= 6:
            if outline[0] != outline[-1]:
                outline.append(outline[0])
            try:
                guide_poly = largest_polygon(normalize_geom(Polygon(outline)), min_area=8.0)
            except Exception:
                guide_poly = None
            if guide_poly is not None and (not guide_poly.is_empty):
                guide_parts.append(guide_poly)

    if guide_samples:
        guide_radius_span = max(1.0, float(guide_samples[-1][0]) - float(guide_samples[0][0]))
        inner_anchor_r = float(guide_samples[0][0])
        outer_anchor_r = float(guide_samples[-1][0])
    else:
        inner_anchor_r = float(guide_inner_r if guide_inner_r is not None else 0.0)
        outer_anchor_r = float(guide_outer_r if guide_outer_r is not None else inner_anchor_r + 12.0)
        guide_radius_span = max(1.0, outer_anchor_r - inner_anchor_r)

    if root_points and len(root_points) >= 4:
        try:
            root_poly = largest_polygon(normalize_geom(Polygon(root_points)), min_area=8.0)
        except Exception:
            root_poly = None
        if root_poly is not None and (not root_poly.is_empty) and (not above_section_band):
            root_outer_r = min(
                float(outer_anchor_r),
                float(inner_anchor_r) + max(10.0, min(26.0, guide_radius_span * 0.26 + 3.0))
            )
            root_inner_r = max(0.0, float(guide_inner_r if guide_inner_r is not None else 0.0) - 1.6)
            try:
                root_band = normalize_geom(circle_polygon(root_outer_r, 180))
                if root_inner_r > 0.5:
                    root_band = normalize_geom(root_band.difference(circle_polygon(root_inner_r, 120)))
                root_patch = largest_polygon(normalize_geom(root_poly.intersection(root_band)), min_area=8.0)
            except Exception:
                root_patch = None
            if root_patch is not None and (not root_patch.is_empty):
                guide_parts.append(root_patch.buffer(0.35, join_style=2))
                root_clip_support = root_patch.buffer(2.2, join_style=2)

    tip_inner_seed = max(
        float(inner_anchor_r),
        float(outer_anchor_r) - max(18.0, min(42.0, guide_radius_span * 0.46 + 5.0 + (terminal_relax * 6.0)))
    )
    projected_tip_strip = build_projected_section_strip(
        tip_sections,
        extend_inner_r=tip_inner_seed,
        extend_outer_r=guide_outer_r,
        inner_width_scale=(1.28 + min(0.42, terminal_relax * 0.22)),
        outer_width_scale=(1.36 + min(0.58, terminal_relax * 0.28))
    )
    if projected_tip_strip is not None and (not projected_tip_strip.is_empty) and (not below_section_band):
        tip_inner_r = max(
            float(inner_anchor_r) - max(0.8, 0.8 + (terminal_relax * 1.4)),
            float(outer_anchor_r) - max(16.0, min(38.0, guide_radius_span * 0.42 + 4.5 + (terminal_relax * 7.0)))
        )
        tip_outer_r = float(guide_outer_r if guide_outer_r is not None else outer_anchor_r) + 6.5 + min(10.0, terminal_relax * 4.5)
        try:
            tip_band = normalize_geom(circle_polygon(tip_outer_r + 0.8, 180))
            if tip_inner_r > 0.5:
                tip_band = normalize_geom(tip_band.difference(circle_polygon(tip_inner_r, 120)))
            tip_patch = largest_polygon(normalize_geom(projected_tip_strip.intersection(tip_band)), min_area=8.0)
        except Exception:
            tip_patch = None
        if tip_patch is not None and (not tip_patch.is_empty):
            guide_parts.append(tip_patch.buffer(1.35 + min(1.6, terminal_relax * 0.85), join_style=2))
            tip_clip_support = tip_patch.buffer(7.0 + min(5.0, terminal_relax * 2.6), join_style=2)

    if not guide_parts:
        return None, None
    guide_poly = largest_polygon(normalize_geom(unary_union(guide_parts)), min_area=8.0)
    if guide_poly is None or guide_poly.is_empty:
        return None, None

    has_terminal_support = (
        root_clip_support is not None and (not root_clip_support.is_empty)
    ) or (
        tip_clip_support is not None and (not tip_clip_support.is_empty)
    )

    if (not has_terminal_support) and float(terminal_relax) < 0.72 and region_points and len(region_points) >= 4:
        try:
            region_poly = largest_polygon(
                normalize_geom(Polygon(region_points).buffer(1.2, join_style=2)),
                min_area=8.0
            )
        except Exception:
            region_poly = None
        if region_poly is not None and (not region_poly.is_empty):
            clip_geoms = [region_poly]
            if root_clip_support is not None and (not root_clip_support.is_empty):
                clip_geoms.append(root_clip_support)
            if tip_clip_support is not None and (not tip_clip_support.is_empty):
                clip_geoms.append(tip_clip_support)
            try:
                clip_region = largest_polygon(normalize_geom(unary_union(clip_geoms)), min_area=8.0)
            except Exception:
                clip_region = region_poly
            clipped = largest_polygon(normalize_geom(guide_poly.intersection(clip_region)), min_area=8.0)
            if clipped is not None and (not clipped.is_empty):
                guide_poly = clipped

    if (not has_terminal_support) and float(terminal_relax) < 0.72 and base_guide is not None and (not base_guide.is_empty):
        base_clip_geoms = [base_guide.buffer(1.45, join_style=2)]
        if root_clip_support is not None and (not root_clip_support.is_empty):
            base_clip_geoms.append(root_clip_support.buffer(0.75, join_style=2))
        if tip_clip_support is not None and (not tip_clip_support.is_empty):
            base_clip_geoms.append(tip_clip_support.buffer(0.75, join_style=2))
        try:
            base_clip = largest_polygon(normalize_geom(unary_union(base_clip_geoms)), min_area=8.0)
        except Exception:
            base_clip = base_guide
        if base_clip is not None and (not base_clip.is_empty):
            clipped = largest_polygon(
                normalize_geom(guide_poly.intersection(base_clip)),
                min_area=8.0
            )
            if clipped is not None and (not clipped.is_empty):
                guide_poly = clipped

    if guide_poly is None or guide_poly.is_empty or float(guide_poly.area) < 8.0:
        return None, None

    section_low = min(section_low_values) if section_low_values else None
    section_high = max(section_high_values) if section_high_values else None
    if (
        base_guide is not None and (not base_guide.is_empty) and
        float(terminal_relax) >= 0.72 and
        section_low is not None and section_high is not None
    ):
        terminal_window = max(4.8, (float(section_high) - float(section_low)) * (0.30 + min(0.10, terminal_relax * 0.03)))
        terminal_buffer = max(3.4, 2.2 + (float(terminal_relax) * 3.4))
        terminal_parts = []

        if float(z_level) >= float(section_high) - terminal_window:
            outer_band_inner = max(
                0.0,
                float(outer_anchor_r) - max(28.0, min(52.0, guide_radius_span * 0.64 + 8.0 + (terminal_relax * 6.0)))
            )
            outer_band_outer = float(guide_outer_r if guide_outer_r is not None else outer_anchor_r) + 12.0 + min(12.0, terminal_relax * 5.0)
            try:
                outer_band = normalize_geom(circle_polygon(outer_band_outer, 180))
                if outer_band_inner > 0.5:
                    outer_band = normalize_geom(outer_band.difference(circle_polygon(outer_band_inner, 120)))
                outer_rescue = largest_polygon(
                    normalize_geom(base_guide.buffer(terminal_buffer, join_style=2).intersection(outer_band)),
                    min_area=8.0
                )
            except Exception:
                outer_rescue = None
            if outer_rescue is not None and (not outer_rescue.is_empty):
                terminal_parts.append(outer_rescue)
            elif region_points and len(region_points) >= 4:
                try:
                    region_poly = largest_polygon(
                        normalize_geom(Polygon(region_points).buffer(terminal_buffer, join_style=2)),
                        min_area=8.0
                    )
                    outer_rescue = largest_polygon(
                        normalize_geom(region_poly.intersection(outer_band)),
                        min_area=8.0
                    ) if region_poly is not None and (not region_poly.is_empty) else None
                except Exception:
                    outer_rescue = None
                if outer_rescue is not None and (not outer_rescue.is_empty):
                    terminal_parts.append(outer_rescue)

        if float(z_level) <= float(section_low) + terminal_window:
            inner_band_outer = min(
                float(outer_anchor_r),
                float(inner_anchor_r) + max(14.0, min(30.0, guide_radius_span * 0.36 + 4.0))
            )
            inner_band_inner = max(0.0, float(guide_inner_r if guide_inner_r is not None else inner_anchor_r) - 2.4)
            try:
                inner_band = normalize_geom(circle_polygon(inner_band_outer, 180))
                if inner_band_inner > 0.5:
                    inner_band = normalize_geom(inner_band.difference(circle_polygon(inner_band_inner, 120)))
                inner_rescue = largest_polygon(
                    normalize_geom(base_guide.buffer(terminal_buffer, join_style=2).intersection(inner_band)),
                    min_area=8.0
                )
            except Exception:
                inner_rescue = None
            if inner_rescue is not None and (not inner_rescue.is_empty):
                terminal_parts.append(inner_rescue)
            elif region_points and len(region_points) >= 4:
                try:
                    region_poly = largest_polygon(
                        normalize_geom(Polygon(region_points).buffer(terminal_buffer, join_style=2)),
                        min_area=8.0
                    )
                    inner_rescue = largest_polygon(
                        normalize_geom(region_poly.intersection(inner_band)),
                        min_area=8.0
                    ) if region_poly is not None and (not region_poly.is_empty) else None
                except Exception:
                    inner_rescue = None
                if inner_rescue is not None and (not inner_rescue.is_empty):
                    terminal_parts.append(inner_rescue)

        if terminal_parts:
            try:
                rescued = largest_polygon(
                    normalize_geom(unary_union([guide_poly] + terminal_parts)),
                    min_area=8.0
                )
            except Exception:
                rescued = guide_poly
            if rescued is not None and (not rescued.is_empty):
                guide_poly = rescued

    theta = math.radians(float(member_angle_deg))
    tangential_dir = np.asarray([-math.sin(theta), math.cos(theta)], dtype=float)
    coords = list(guide_poly.exterior.coords)
    tangential_values = [
        float(np.dot(np.asarray([float(x), float(y)], dtype=float), tangential_dir))
        for x, y in coords[:-1]
    ]
    width_hint = None
    if tangential_values:
        width_hint = float(max(tangential_values) - min(tangential_values))
    return guide_poly, width_hint

def describe_member_xy_profile(loop_points, member_angle_deg, min_area=6.0):
    if not loop_points or len(loop_points) < 4:
        return None
    try:
        poly = largest_polygon(normalize_geom(Polygon(loop_points)), min_area=float(min_area))
    except Exception:
        poly = None
    if poly is None or poly.is_empty:
        return None
    coords = list(poly.exterior.coords)
    if len(coords) < 4:
        return None
    try:
        theta = math.radians(float(member_angle_deg))
        tangential_dir = np.asarray([-math.sin(theta), math.cos(theta)], dtype=float)
    except Exception:
        tangential_dir = np.asarray([0.0, 1.0], dtype=float)
    radii = [math.hypot(float(x), float(y)) for x, y in coords[:-1]]
    if not radii:
        return None
    tangential_values = [
        float(np.dot(np.asarray([float(x), float(y)], dtype=float), tangential_dir))
        for x, y in coords[:-1]
    ]
    centroid = poly.centroid
    return {
        "poly": poly,
        "coords": coords,
        "area": float(poly.area),
        "r_min": float(min(radii)),
        "r_max": float(max(radii)),
        "radial_span": float(max(radii) - min(radii)),
        "width": float((max(tangential_values) - min(tangential_values)) if tangential_values else 0.0),
        "centroid_r": float(math.hypot(float(centroid.x), float(centroid.y))),
        "centroid_angle": float(math.degrees(math.atan2(float(centroid.y), float(centroid.x))) % 360.0),
    }

def extract_member_guided_submesh(
    mesh,
    guide_geom,
    z_min,
    z_max,
    radial_inner=None,
    radial_outer=None,
    member_angle_deg=None,
    region_points=None,
    root_points=None,
    expected_span=None,
    expected_width=None,
    guide_buffer=1.2,
    min_faces=24
):
    """Extract a spoke-local triangle subset so XY@Z slicing no longer competes with the full wheel mesh."""
    if mesh is None or guide_geom is None or guide_geom.is_empty:
        return None

    try:
        vertices = np.asarray(mesh.vertices, dtype=float)
        faces = np.asarray(mesh.faces, dtype=int)
    except Exception:
        return None

    if vertices.size == 0 or faces.size == 0:
        return None

    z_low = float(min(z_min, z_max)) - 12.0
    z_high = float(max(z_min, z_max)) + 12.0
    query_geom = normalize_geom(guide_geom.buffer(float(guide_buffer), join_style=2))
    if query_geom is None or query_geom.is_empty:
        return None
    prepared_query = prep(query_geom)

    radial_dir = None
    tangential_dir = None
    local_bounds = None
    if member_angle_deg is not None:
        try:
            theta = math.radians(float(member_angle_deg))
            radial_dir = np.asarray([math.cos(theta), math.sin(theta)], dtype=float)
            tangential_dir = np.asarray([-math.sin(theta), math.cos(theta)], dtype=float)
        except Exception:
            radial_dir = None
            tangential_dir = None

    if radial_dir is not None and tangential_dir is not None:
        local_loops = []
        for loop_pts in (region_points, root_points):
            if loop_pts and len(loop_pts) >= 4:
                try:
                    local_loop = world_loop_to_member_local(loop_pts, float(member_angle_deg))
                except Exception:
                    local_loop = []
                if len(local_loop) >= 4:
                    local_loops.append(local_loop)
        if local_loops:
            local_r_vals = []
            local_t_vals = []
            for local_loop in local_loops:
                for point_r, point_t in local_loop[:-1]:
                    local_r_vals.append(float(point_r))
                    local_t_vals.append(float(point_t))
            if local_r_vals and local_t_vals:
                local_r_min = min(local_r_vals)
                local_r_max = max(local_r_vals)
                local_t_min = min(local_t_vals)
                local_t_max = max(local_t_vals)
                radial_pad_inner = 4.0
                radial_pad_outer = max(8.0, min(22.0, float(expected_span or (local_r_max - local_r_min)) * 0.28 + 2.2))
                tangential_pad = max(2.0, min(7.5, float(expected_width or (local_t_max - local_t_min)) * 0.30 + 1.2))
                local_bounds = (
                    local_r_min - radial_pad_inner,
                    local_r_max + radial_pad_outer,
                    local_t_min - tangential_pad,
                    local_t_max + tangential_pad
                )

    face_vertices = vertices[faces]
    tri_z_min = np.min(face_vertices[:, :, 2], axis=1)
    tri_z_max = np.max(face_vertices[:, :, 2], axis=1)
    candidate_mask = (tri_z_max >= z_low) & (tri_z_min <= z_high)
    candidate_indices = np.nonzero(candidate_mask)[0]
    if candidate_indices.size == 0:
        return None

    if radial_inner is not None or radial_outer is not None:
        candidate_face_vertices = face_vertices[candidate_indices]
        centroids_xy = np.mean(candidate_face_vertices[:, :, :2], axis=1)
        centroid_r = np.hypot(centroids_xy[:, 0], centroids_xy[:, 1])
        radial_mask = np.ones(candidate_indices.shape[0], dtype=bool)
        if radial_inner is not None:
            radial_mask &= (centroid_r >= (float(radial_inner) - 5.5))
        if radial_outer is not None:
            radial_mask &= (centroid_r <= (float(radial_outer) + 7.5))
        candidate_indices = candidate_indices[radial_mask]
        if candidate_indices.size == 0:
            return None

    keep_faces = []
    for face_idx in candidate_indices.tolist():
        tri = face_vertices[int(face_idx)]
        tri_xy = tri[:, :2]
        centroid_xy = np.mean(tri_xy, axis=0)
        if local_bounds is not None and radial_dir is not None and tangential_dir is not None:
            centroid_vec = np.asarray([float(centroid_xy[0]), float(centroid_xy[1])], dtype=float)
            local_r = float(np.dot(centroid_vec, radial_dir))
            local_t = float(np.dot(centroid_vec, tangential_dir))
            if (
                local_r < local_bounds[0] or local_r > local_bounds[1] or
                local_t < local_bounds[2] or local_t > local_bounds[3]
            ):
                vertex_local_hit = False
                for vx, vy in tri_xy:
                    vertex_vec = np.asarray([float(vx), float(vy)], dtype=float)
                    vertex_r = float(np.dot(vertex_vec, radial_dir))
                    vertex_t = float(np.dot(vertex_vec, tangential_dir))
                    if (
                        local_bounds[0] <= vertex_r <= local_bounds[1] and
                        local_bounds[2] <= vertex_t <= local_bounds[3]
                    ):
                        vertex_local_hit = True
                        break
                if not vertex_local_hit:
                    continue
        try:
            centroid_pt = Point(float(centroid_xy[0]), float(centroid_xy[1]))
        except Exception:
            centroid_pt = None

        if centroid_pt is not None and prepared_query.contains(centroid_pt):
            keep_faces.append(int(face_idx))
            continue

        vertex_hit = False
        for vx, vy in tri_xy:
            try:
                if prepared_query.contains(Point(float(vx), float(vy))):
                    vertex_hit = True
                    break
            except Exception:
                continue
        if vertex_hit:
            keep_faces.append(int(face_idx))
            continue

        try:
            tri_poly = Polygon([
                (float(tri_xy[0][0]), float(tri_xy[0][1])),
                (float(tri_xy[1][0]), float(tri_xy[1][1])),
                (float(tri_xy[2][0]), float(tri_xy[2][1]))
            ])
            tri_poly = normalize_geom(tri_poly)
        except Exception:
            tri_poly = None

        if tri_poly is not None and (not tri_poly.is_empty):
            try:
                overlap_area = float(tri_poly.intersection(query_geom).area)
            except Exception:
                overlap_area = 0.0
            tri_area = max(1e-6, float(getattr(tri_poly, "area", 0.0)))
            if overlap_area >= max(0.18, tri_area * 0.08):
                keep_faces.append(int(face_idx))

    if len(keep_faces) < int(min_faces):
        return None

    try:
        submesh = mesh.submesh([np.asarray(keep_faces, dtype=int)], append=True, repair=False)
    except Exception:
        return None

    if isinstance(submesh, (list, tuple)):
        submesh = submesh[0] if submesh else None
    if submesh is None:
        return None
    try:
        if len(getattr(submesh, "faces", [])) < int(min_faces):
            return None
    except Exception:
        return None
    return submesh

def extract_member_actual_z_slice_profile(
    mesh,
    z_level,
    guide_geom,
    region_points,
    member_angle_deg,
    expected_inner_r,
    expected_outer_r,
    expected_width=None,
    min_area=16.0,
    boundary_relax=0.0
):
    if mesh is None or guide_geom is None or guide_geom.is_empty:
        return []
    try:
        section = mesh.section(plane_origin=[0.0, 0.0, float(z_level)], plane_normal=[0.0, 0.0, 1.0])
    except Exception:
        section = None
    if not section:
        return []

    slice_lines = []
    for entity in section.entities:
        try:
            pts = np.asarray(section.vertices[entity.points], dtype=float)
        except Exception:
            continue
        if pts.shape[0] < 2:
            continue
        line = LineString([(float(x), float(y)) for x, y in pts[:, :2]])
        if line.is_empty or float(line.length) <= 0.2:
            continue
        slice_lines.append(line)
    if not slice_lines:
        return []

    try:
        merged_lines = linemerge(MultiLineString(slice_lines))
        slice_polygons = list(polygonize(merged_lines))
    except Exception:
        slice_polygons = []
    if not slice_polygons:
        return []

    region_poly = None
    if region_points and len(region_points) >= 4:
        try:
            region_poly = normalize_geom(Polygon(region_points))
        except Exception:
            region_poly = None

    expected_span = max(1.0, float(expected_outer_r) - float(expected_inner_r))
    expected_mid_r = (float(expected_inner_r) + float(expected_outer_r)) * 0.5
    tangential_dir = np.asarray(
        [-math.sin(math.radians(float(member_angle_deg))), math.cos(math.radians(float(member_angle_deg)))],
        dtype=float
    )
    boundary_relax = max(0.0, min(1.0, float(boundary_relax)))
    angle_tolerance = max(10.0, min(28.0, expected_span * 0.08 + 10.0)) + (boundary_relax * 18.0)
    width_lower = None
    width_upper = None
    if expected_width is not None:
        try:
            width_lower = max(3.2, float(expected_width) * (0.34 - (boundary_relax * 0.10)))
            width_upper = max(
                float(expected_width) * (1.60 + (boundary_relax * 0.85)),
                float(expected_width) + 7.0 + (boundary_relax * 12.0)
            )
        except Exception:
            width_lower = None
            width_upper = None

    def iter_candidate_polygons(geom):
        if geom is None or geom.is_empty:
            return
        if isinstance(geom, Polygon):
            yield geom
            return
        if isinstance(geom, MultiPolygon):
            for sub in geom.geoms:
                if sub is not None and (not sub.is_empty):
                    yield sub
            return
        if isinstance(geom, GeometryCollection):
            for sub in geom.geoms:
                if isinstance(sub, Polygon) and (not sub.is_empty):
                    yield sub
                elif isinstance(sub, MultiPolygon):
                    for item in sub.geoms:
                        if item is not None and (not item.is_empty):
                            yield item
            return
        if hasattr(geom, "geoms"):
            for sub in geom.geoms:
                if isinstance(sub, Polygon) and (not sub.is_empty):
                    yield sub

    candidate_records = []
    for raw_poly in slice_polygons:
        try:
            clipped_geom = normalize_geom(raw_poly.intersection(guide_geom))
        except Exception:
            clipped_geom = None
        if clipped_geom is None or clipped_geom.is_empty:
            continue
        for clipped_poly in iter_candidate_polygons(clipped_geom):
            clipped_poly = largest_polygon(clipped_poly, min_area=min_area)
            if clipped_poly is None or clipped_poly.is_empty or float(clipped_poly.area) < float(min_area):
                continue
            metrics = describe_member_xy_profile(list(clipped_poly.exterior.coords), member_angle_deg, min_area=min_area)
            if metrics is None:
                continue
            coords = metrics["coords"]
            radii = [math.hypot(float(x), float(y)) for x, y in coords[:-1]]
            radial_span = float(metrics["radial_span"])
            min_radial_span = max(4.0, expected_span * (0.38 - (boundary_relax * 0.16)))
            if radial_span < min_radial_span:
                continue
            tangential_span = float(metrics["width"])
            if width_lower is not None and tangential_span < width_lower:
                continue
            if width_upper is not None and tangential_span > width_upper:
                continue
            angle_error = angular_distance_deg(float(metrics["centroid_angle"]), member_angle_deg)
            if angle_error > angle_tolerance:
                continue
            overlap_area = 0.0
            overlap_ratio = 0.0
            if region_poly is not None and (not region_poly.is_empty):
                try:
                    overlap_area = float(clipped_poly.intersection(region_poly.buffer(1.0, join_style=2)).area)
                    overlap_ratio = overlap_area / max(1.0, float(clipped_poly.area))
                except Exception:
                    overlap_area = 0.0
                    overlap_ratio = 0.0
            outer_support = max(0.0, float(metrics["r_max"]) - float(expected_outer_r))
            inner_support = max(0.0, float(expected_inner_r) - float(metrics["r_min"]))
            support_limit = max(16.0, min(36.0, expected_span * 0.22 + 4.0)) + (boundary_relax * 24.0)
            if outer_support > support_limit:
                continue
            if inner_support > support_limit:
                continue
            inner_deficit = max(0.0, float(metrics["r_min"]) - float(expected_inner_r))
            outer_deficit = max(0.0, float(expected_outer_r) - float(metrics["r_max"]))
            total_deficit = inner_deficit + outer_deficit
            coverage_deficit_limit = max(32.0, min(74.0, expected_span * 0.50 + 10.0)) + (boundary_relax * 32.0)
            side_deficit_limit = max(18.0, min(42.0, expected_span * 0.28 + 5.0)) + (boundary_relax * 22.0)
            if inner_deficit > side_deficit_limit:
                continue
            if outer_deficit > side_deficit_limit:
                continue
            if total_deficit > coverage_deficit_limit:
                continue
            min_overlap_ratio = max(0.0, 0.06 - (boundary_relax * 0.08))
            min_overlap_area = 0.0 if boundary_relax >= 0.82 else max(0.2, float(min_area) * (0.16 - (boundary_relax * 0.12)))
            if overlap_ratio < min_overlap_ratio and overlap_area < min_overlap_area:
                continue
            width_penalty = 0.0
            if expected_width is not None:
                try:
                    width_penalty = abs(float(tangential_span) - float(expected_width))
                except Exception:
                    width_penalty = 0.0
            span_penalty = abs(float(radial_span) - float(expected_span))
            center_r_penalty = abs(float(metrics["centroid_r"]) - float(expected_mid_r))
            support_penalty = (inner_support + outer_support)
            deficit_penalty = (inner_deficit + outer_deficit)
            score = (
                (overlap_ratio * 220.0)
                + (overlap_area * 0.12)
                + (float(clipped_poly.area) * 0.02)
                - (angle_error * 4.0)
                - (width_penalty * 1.10)
                - (span_penalty * 0.70)
                - (center_r_penalty * 0.25)
                - (support_penalty * 8.0)
                - (deficit_penalty * 7.5)
            )
            candidate_records.append((score, clipped_poly))

    if not candidate_records:
        return []
    only_poly = max(candidate_records, key=lambda item: item[0])[1]
    coords = canonicalize_member_loop(list(only_poly.exterior.coords), member_angle_deg)
    return coords if len(coords) >= 4 else []

def extract_member_actual_z_profile_stack(
    mesh,
    member_region_points,
    member_sections,
    member_tip_sections,
    member_angle_deg,
    root_points=None,
    sample_count=7,
    meta_out=None
):
    if isinstance(meta_out, dict):
        meta_out.clear()
        meta_out.update({
            "prefer_local_section": False,
            "stack_mode": "uninitialized",
            "profile_count": 0,
            "source_label": "none",
        })

    def update_meta(stack_mode=None, profiles=None, prefer_local_section=None, source_label=None):
        if not isinstance(meta_out, dict):
            return
        if stack_mode is not None:
            meta_out["stack_mode"] = str(stack_mode)
        if profiles is not None:
            meta_out["profile_count"] = int(len(profiles or []))
        if prefer_local_section is not None:
            meta_out["prefer_local_section"] = bool(prefer_local_section)
        if source_label is not None:
            meta_out["source_label"] = str(source_label)

    if mesh is None or len(member_sections or []) < 3 or len(member_region_points or []) < 4:
        update_meta(stack_mode="invalid-input", profiles=[], source_label="invalid")
        return []

    try:
        region_radii = [math.hypot(float(x), float(y)) for x, y in member_region_points[:-1]]
    except Exception:
        region_radii = []
    if not region_radii:
        update_meta(stack_mode="invalid-region", profiles=[], source_label="invalid")
        return []
    expected_inner_r = float(min(region_radii))
    expected_outer_r = float(max(region_radii))
    projected_widths = []
    for section_payload in member_sections or []:
        projected_sample = extract_projected_section_sample(section_payload)
        if projected_sample is None:
            continue
        try:
            projected_widths.append(float(projected_sample.get("width", 0.0)))
        except Exception:
            continue
    expected_width = None
    if projected_widths:
        expected_width = float(np.median(np.asarray(projected_widths, dtype=float)))

    section_station_radii = []
    for section_payload in member_sections or []:
        try:
            section_station_radii.append(float(section_payload.get("station_r", 0.0)))
        except Exception:
            continue
    tip_station_radii = []
    for section_payload in member_tip_sections or []:
        try:
            tip_station_radii.append(float(section_payload.get("station_r", 0.0)))
        except Exception:
            continue

    expected_span = max(1.0, expected_outer_r - expected_inner_r)
    guide_inner_r = float(expected_inner_r)
    guide_outer_r = float(expected_outer_r)
    if section_station_radii:
        first_station_r = min(section_station_radii)
        last_station_r = max(section_station_radii)
        inner_extend = max(7.0, min(14.0, expected_span * 0.15 + 1.8))
        outer_extend = max(18.0, min(36.0, expected_span * 0.36 + 4.0))
        guide_inner_r = min(float(guide_inner_r), max(0.0, first_station_r - inner_extend))
        guide_outer_r = max(float(guide_outer_r), last_station_r + outer_extend)
    if root_points and len(root_points) >= 4:
        try:
            root_radii = [math.hypot(float(x), float(y)) for x, y in root_points[:-1]]
        except Exception:
            root_radii = []
        if root_radii:
            guide_inner_r = min(
                float(guide_inner_r),
                max(
                    0.0,
                    float(np.percentile(np.asarray(root_radii, dtype=float), 8.0)) - max(2.0, min(5.2, expected_span * 0.07 + 1.0))
                )
            )
    if tip_station_radii:
        guide_outer_r = max(
            float(max(tip_station_radii)) + max(12.0, min(24.0, expected_span * 0.28 + 2.8)),
            guide_outer_r if guide_outer_r is not None else 0.0
        )
    guide_outer_r = max(
        float(guide_outer_r),
            float(expected_outer_r) + max(18.0, min(34.0, expected_span * 0.34 + 3.8))
    )

    z_lows = []
    z_highs = []
    all_z_values = []
    target_band_lows = []
    target_band_highs = []
    for section_payload in member_sections or []:
        pts_local = section_payload.get("points_local", []) or []
        plane_origin = section_payload.get("plane_origin", []) or []
        if len(pts_local) < 4 or len(plane_origin) < 3:
            continue
        base_z = float(plane_origin[2])
        local_samples = pts_local[:-1] if len(pts_local) >= 5 else pts_local
        ys = [float(y_val) for _, y_val in local_samples]
        if not ys:
            continue
        z_lows.append(base_z + min(ys))
        z_highs.append(base_z + max(ys))
        all_z_values.extend([base_z + y_val for y_val in ys])
        target_z_band = section_payload.get("target_z_band", []) or []
        if len(target_z_band) >= 2:
            try:
                target_band_lows.append(float(min(target_z_band)))
                target_band_highs.append(float(max(target_z_band)))
            except Exception:
                pass

    if len(z_lows) < 3 or len(z_highs) < 3:
        update_meta(stack_mode="insufficient-sections", profiles=[], source_label="invalid")
        return []

    robust_z_start = float(min(z_lows))
    robust_z_end = float(max(z_highs))
    if all_z_values:
        try:
            z_arr = np.asarray(all_z_values, dtype=float)
            robust_z_start = float(np.percentile(z_arr, 8.0))
            robust_z_end = float(np.percentile(z_arr, 92.0))
        except Exception:
            robust_z_start = float(min(z_lows))
            robust_z_end = float(max(z_highs))

    if target_band_lows and target_band_highs:
        try:
            target_start = float(min(target_band_lows))
            target_end = float(max(target_band_highs))
            z_start = max(target_start, robust_z_start - 1.4)
            z_end = min(target_end, robust_z_end + 1.4)
        except Exception:
            z_start = robust_z_start
            z_end = robust_z_end
    else:
        z_start = robust_z_start
        z_end = robust_z_end

    if z_end <= z_start + 2.0:
        update_meta(stack_mode="degenerate-z-span", profiles=[], source_label="invalid")
        return []
    base_z_start = float(z_start)
    base_z_end = float(z_end)
    target_z_span = max(1.0, float(base_z_end) - float(base_z_start))

    source_mesh = mesh
    source_mesh_label = "full-wheel"
    guide_hint_mesh = None
    guide_hint_label = "full-wheel-guide"
    submesh_guide_geom = build_member_actual_slice_guide(
        member_region_points,
        member_sections=member_sections,
        root_points=root_points,
        tip_sections=member_tip_sections,
        buffer_pad=2.05,
        guide_inner_r=guide_inner_r,
        guide_outer_r=guide_outer_r,
        relaxed=True
    )
    if submesh_guide_geom is not None and (not submesh_guide_geom.is_empty):
        guided_submesh = extract_member_guided_submesh(
            mesh,
            submesh_guide_geom,
            z_start,
            z_end,
            radial_inner=max(0.0, guide_inner_r - 4.5),
            radial_outer=guide_outer_r + 10.0,
            member_angle_deg=float(member_angle_deg),
            region_points=member_region_points,
            root_points=root_points,
            expected_span=expected_span,
            expected_width=expected_width,
            guide_buffer=3.2,
            min_faces=28
        )
        if guided_submesh is not None:
            try:
                submesh_vertices = np.asarray(guided_submesh.vertices, dtype=float)
            except Exception:
                submesh_vertices = np.empty((0, 3), dtype=float)
            if submesh_vertices.shape[0] >= 8:
                submesh_z = submesh_vertices[:, 2]
                try:
                    z_start = min(float(z_start), float(np.percentile(submesh_z, 1.0)))
                    z_end = max(float(z_end), float(np.percentile(submesh_z, 99.0)))
                except Exception:
                    z_start = min(float(z_start), float(np.min(submesh_z)))
                    z_end = max(float(z_end), float(np.max(submesh_z)))
                guide_hint_mesh = guided_submesh
                guide_hint_label = f"guided-window[{len(guided_submesh.faces)}f]"

    def build_candidate_z_samples(active_mesh, z_low, z_high):
        candidate_density = max(17, int(sample_count) + 14)
        if active_mesh is not mesh:
            candidate_density = max(candidate_density, int(sample_count) + 24)
        samples = {round(float(z_val), 3) for z_val in np.linspace(float(z_low), float(z_high), candidate_density)}
        edge_step = max(0.55, min(1.45, target_z_span / 20.0))
        for offset in (0.0, edge_step, edge_step * 2.0, edge_step * 3.0, edge_step * 4.0, edge_step * 5.0):
            samples.add(round(float(base_z_start) + float(offset), 3))
            samples.add(round(float(base_z_end) - float(offset), 3))
        samples.add(round(float(min(z_lows)), 3))
        samples.add(round(float(max(z_highs)), 3))
        for section in member_tip_sections or []:
            if not isinstance(section, dict) or "z" not in section:
                continue
            try:
                samples.add(round(float(section["z"]), 3))
            except Exception:
                continue
        if all_z_values:
            try:
                z_arr = np.asarray(all_z_values, dtype=float)
                for q in (5, 10, 20, 35, 50, 65, 80, 90, 95):
                    samples.add(round(float(np.percentile(z_arr, q)), 3))
            except Exception:
                pass
        if active_mesh is not mesh:
            try:
                source_z_arr = np.asarray(active_mesh.vertices, dtype=float)[:, 2]
                for q in (1, 5, 12, 25, 40, 60, 75, 88, 95, 99):
                    samples.add(round(float(np.percentile(source_z_arr, q)), 3))
            except Exception:
                pass
        return sorted(samples)

    active_hint_mesh = guide_hint_mesh if guide_hint_mesh is not None else mesh
    if guide_hint_mesh is not None:
        source_mesh_label = f"{guide_hint_label}+full-wheel-slice"
    candidate_z = build_candidate_z_samples(active_hint_mesh, z_start, z_end)

    def boundary_relax_for_z(z_level):
        try:
            edge_band = max(2.6, target_z_span * 0.38)
            edge_distance = min(
                abs(float(z_level) - float(base_z_start)),
                abs(float(base_z_end) - float(z_level))
            )
            relax = 1.0 - min(1.0, max(0.0, edge_distance / edge_band))
            return max(0.0, min(1.0, float(relax)))
        except Exception:
            return 0.0

    def enrich_profile_record(profile_entry):
        if profile_entry is None:
            return None
        metrics = describe_member_xy_profile(profile_entry.get("points", []), float(member_angle_deg), min_area=6.0)
        if metrics is None:
            return None
        metrics["inner_deficit"] = max(0.0, float(metrics["r_min"]) - float(expected_inner_r))
        metrics["outer_deficit"] = max(0.0, float(expected_outer_r) - float(metrics["r_max"]))
        metrics["coverage_deficit"] = float(metrics["inner_deficit"] + metrics["outer_deficit"])
        profile_entry["metrics"] = metrics
        return profile_entry

    def extract_profile_record(z_level, active_guide_geom, width_hint, profile_min_area=16.0, boundary_relax_override=None):
        if active_guide_geom is None or active_guide_geom.is_empty:
            return None
        boundary_relax = boundary_relax_for_z(z_level) if boundary_relax_override is None else float(boundary_relax_override)
        relaxed_guide_inner_r = guide_inner_r
        relaxed_guide_outer_r = guide_outer_r
        if relaxed_guide_inner_r is not None and boundary_relax >= 0.72:
            relaxed_guide_inner_r = max(0.0, float(relaxed_guide_inner_r) - min(6.0, boundary_relax * 4.0))
        if relaxed_guide_outer_r is not None and boundary_relax >= 0.72:
            relaxed_guide_outer_r = float(relaxed_guide_outer_r) + min(12.0, boundary_relax * 8.0)
        slice_guide_geom, slice_width_hint = build_member_actual_z_slice_guide(
            member_sections,
            float(z_level),
            float(member_angle_deg),
            guide_inner_r=relaxed_guide_inner_r,
            guide_outer_r=relaxed_guide_outer_r,
            region_points=member_region_points,
            base_guide=active_guide_geom,
            root_points=root_points,
            tip_sections=member_tip_sections,
            terminal_relax=boundary_relax
        )
        if slice_guide_geom is None or slice_guide_geom.is_empty:
            return None
        profile = extract_member_actual_z_slice_profile(
            source_mesh,
            float(z_level),
            slice_guide_geom,
            member_region_points,
            float(member_angle_deg),
            expected_inner_r,
            expected_outer_r,
            expected_width=(slice_width_hint if slice_width_hint is not None else width_hint),
            min_area=max(6.0, float(profile_min_area) * (0.72 if boundary_relax >= 0.55 else 1.0)),
            boundary_relax=boundary_relax
        )
        if len(profile) < 4:
            return None
        return enrich_profile_record({
            "z": round(float(z_level), 3),
            "points": profile
        })

    def refine_jump_profiles(collected, active_guide_geom, width_hint):
        if len(collected) < 3:
            return collected

        def profile_metrics(profile_entry):
            metrics = profile_entry.get("metrics") if isinstance(profile_entry, dict) else None
            if metrics is not None:
                return metrics
            enriched = enrich_profile_record(profile_entry)
            return enriched.get("metrics") if enriched is not None else None

        existing_z = {round(float(item.get("z", 0.0)), 3) for item in collected}
        insertions = []
        metrics_cache = [profile_metrics(item) for item in collected]
        for idx, (profile_a, profile_b) in enumerate(zip(collected[:-1], collected[1:])):
            z_a = float(profile_a.get("z", 0.0))
            z_b = float(profile_b.get("z", 0.0))
            if z_b <= z_a + 1.0:
                continue
            metrics_a = metrics_cache[idx]
            metrics_b = metrics_cache[idx + 1]
            if metrics_a is None or metrics_b is None:
                continue
            area_ratio = abs(metrics_b["area"] - metrics_a["area"]) / max(1.0, metrics_a["area"])
            centroid_jump = abs(metrics_b["centroid_r"] - metrics_a["centroid_r"])
            inner_jump = abs(metrics_b["r_min"] - metrics_a["r_min"])
            if area_ratio < 0.18 and centroid_jump < 6.0 and inner_jump < 10.0:
                continue
            mid_positions = [0.5]
            if (z_b - z_a) > 5.0:
                mid_positions = [0.33, 0.66]
            for blend in mid_positions:
                probe_z = round(z_a + ((z_b - z_a) * float(blend)), 3)
                if probe_z in existing_z:
                    continue
                profile_entry = extract_profile_record(probe_z, active_guide_geom, width_hint)
                if profile_entry is None:
                    continue
                existing_z.add(probe_z)
                insertions.append(profile_entry)

        if not insertions:
            return collected

        combined = list(collected) + insertions
        combined.sort(key=lambda item: float(item.get("z", 0.0)))
        deduped = []
        seen_z = set()
        for entry in combined:
            z_key = round(float(entry.get("z", 0.0)), 3)
            if z_key in seen_z:
                continue
            seen_z.add(z_key)
            deduped.append(entry)
        return deduped

    def fill_large_profile_gaps(collected, active_guide_geom, width_hint):
        if active_guide_geom is None or active_guide_geom.is_empty or len(collected) < 2:
            return collected

        existing_z = {round(float(item.get("z", 0.0)), 3) for item in collected}
        inserts = []
        gap_limit = max(4.4, target_z_span * 0.12)

        for profile_a, profile_b in zip(collected[:-1], collected[1:]):
            z_a = float(profile_a.get("z", 0.0))
            z_b = float(profile_b.get("z", 0.0))
            gap = z_b - z_a
            if gap <= gap_limit:
                continue
            subdivisions = max(2, int(math.ceil(gap / gap_limit)))
            for probe_z in np.linspace(z_a, z_b, subdivisions + 1)[1:-1]:
                z_key = round(float(probe_z), 3)
                if z_key in existing_z:
                    continue
                profile_entry = extract_profile_record(
                    probe_z,
                    active_guide_geom,
                    width_hint,
                    profile_min_area=9.0,
                    boundary_relax_override=0.68
                )
                if profile_entry is None:
                    continue
                existing_z.add(z_key)
                inserts.append(profile_entry)

        if not inserts:
            return collected

        merged = list(collected) + inserts
        merged.sort(key=lambda item: float(item.get("z", 0.0)))
        return merged

    def rescue_terminal_profiles(collected, active_guide_geom, width_hint, candidate_z_samples):
        if active_guide_geom is None or active_guide_geom.is_empty:
            return collected
        if len(collected) < 2:
            return collected

        existing_z = {round(float(item.get("z", 0.0)), 3) for item in collected}
        inserts = []
        first_z = float(collected[0].get("z", 0.0))
        last_z = float(collected[-1].get("z", 0.0))
        edge_band = max(4.8, target_z_span * 0.42)

        def probe_terminal(z_values):
            for z_val in z_values:
                z_key = round(float(z_val), 3)
                if z_key in existing_z:
                    continue
                profile_entry = extract_profile_record(
                    z_val,
                    active_guide_geom,
                    width_hint,
                    profile_min_area=6.0,
                    boundary_relax_override=1.45
                )
                if profile_entry is None:
                    continue
                existing_z.add(z_key)
                inserts.append(profile_entry)

        if (first_z - float(base_z_start)) > 1.0:
            lower_candidates = [
                z_val for z_val in candidate_z_samples
                if float(base_z_start) - 0.05 <= float(z_val) < min(first_z, float(base_z_start) + edge_band + 0.2)
            ]
            lower_dense = np.linspace(
                float(base_z_start) - 0.08,
                min(first_z, float(base_z_start) + edge_band + 0.22),
                40
            )
            lower_candidates = sorted({
                round(float(z_val), 3)
                for z_val in list(lower_candidates) + list(lower_dense)
            })
            probe_terminal(lower_candidates[:64])

        if (float(base_z_end) - last_z) > 1.0:
            upper_candidates = [
                z_val for z_val in candidate_z_samples
                if max(last_z, float(base_z_end) - edge_band - 0.35) < float(z_val) <= float(base_z_end) + 0.12
            ]
            upper_dense = np.linspace(
                max(last_z, float(base_z_end) - edge_band - 0.18),
                float(base_z_end) + 0.10,
                40
            )
            upper_candidates = sorted({
                round(float(z_val), 3)
                for z_val in list(upper_candidates) + list(upper_dense)
            })
            probe_terminal(upper_candidates[-64:])

        if not inserts:
            return collected

        merged = list(collected) + inserts
        merged.sort(key=lambda item: float(item.get("z", 0.0)))
        return refine_jump_profiles(merged, active_guide_geom, width_hint)

    def repair_profile_outliers(collected, active_guide_geom, width_hint):
        if active_guide_geom is None or active_guide_geom.is_empty or len(collected) < 5:
            return collected

        width_values = []
        area_values = []
        for item in collected:
            metrics = item.get("metrics") if isinstance(item, dict) else None
            if metrics is None:
                enriched = enrich_profile_record(item)
                metrics = enriched.get("metrics") if enriched is not None else None
            if metrics is None:
                continue
            width_values.append(float(metrics["width"]))
            area_values.append(float(metrics["area"]))
        if not width_values or not area_values:
            return collected

        median_width = float(np.median(np.asarray(width_values, dtype=float)))
        median_area = float(np.median(np.asarray(area_values, dtype=float)))
        repaired = []
        repair_count = 0

        for idx, item in enumerate(collected):
            metrics = item.get("metrics") if isinstance(item, dict) else None
            if metrics is None:
                enriched = enrich_profile_record(item)
                metrics = enriched.get("metrics") if enriched is not None else None
            if metrics is None:
                repaired.append(item)
                continue

            neighbor_widths = []
            neighbor_areas = []
            for neighbor_idx in (idx - 1, idx + 1):
                if 0 <= neighbor_idx < len(collected):
                    neighbor_metrics = collected[neighbor_idx].get("metrics")
                    if neighbor_metrics is None:
                        enriched_neighbor = enrich_profile_record(collected[neighbor_idx])
                        neighbor_metrics = enriched_neighbor.get("metrics") if enriched_neighbor is not None else None
                    if neighbor_metrics is not None:
                        neighbor_widths.append(float(neighbor_metrics["width"]))
                        neighbor_areas.append(float(neighbor_metrics["area"]))

            neighbor_width = float(np.median(np.asarray(neighbor_widths, dtype=float))) if neighbor_widths else median_width
            neighbor_area = float(np.median(np.asarray(neighbor_areas, dtype=float))) if neighbor_areas else median_area

            width_outlier = float(metrics["width"]) > max(median_width * 1.24, neighbor_width * 1.18, median_width + 2.0)
            area_outlier = float(metrics["area"]) > max(median_area * 1.34, neighbor_area * 1.20, median_area + 6.0)
            if not (width_outlier or area_outlier):
                repaired.append(item)
                continue

            replacement = extract_profile_record(
                float(item.get("z", 0.0)),
                active_guide_geom,
                width_hint,
                profile_min_area=12.0,
                boundary_relax_override=min(0.28, boundary_relax_for_z(float(item.get("z", 0.0))))
            )
            if replacement is None or replacement.get("metrics") is None:
                repaired.append(item)
                continue

            old_metrics = metrics
            new_metrics = replacement["metrics"]
            old_score = (
                abs(float(old_metrics["width"]) - neighbor_width)
                + (abs(float(old_metrics["area"]) - neighbor_area) * 0.10)
                + (float(old_metrics["coverage_deficit"]) * 3.0)
            )
            new_score = (
                abs(float(new_metrics["width"]) - neighbor_width)
                + (abs(float(new_metrics["area"]) - neighbor_area) * 0.10)
                + (float(new_metrics["coverage_deficit"]) * 3.0)
            )
            if new_score + 0.10 < old_score:
                repaired.append(replacement)
                repair_count += 1
            else:
                repaired.append(item)

        if repair_count:
            try:
                print(f"[*] Member actual XY@Z outlier repair: repaired={repair_count}")
            except Exception:
                pass
        return repaired

    def profile_stack_metrics(collected):
        if not collected:
            return None
        z_vals = [float(item.get("z", 0.0)) for item in collected]
        z_span = max(z_vals) - min(z_vals) if len(z_vals) >= 2 else 0.0
        max_gap = 0.0
        if len(z_vals) >= 2:
            max_gap = max((z_b - z_a) for z_a, z_b in zip(z_vals[:-1], z_vals[1:]))
        start_gap = max(0.0, min(z_vals) - float(base_z_start))
        end_gap = max(0.0, float(base_z_end) - max(z_vals))
        coverage_ratio = z_span / max(1.0, target_z_span)
        terminal_band = max(2.2, target_z_span * 0.14)
        connection_tol = max(8.0, min(18.0, expected_span * 0.10 + 2.0))
        widths = []
        areas = []
        full_support_hits = 0
        terminal_hits_start = 0
        terminal_hits_end = 0
        local_width_jump = 0.0
        last_width = None
        terminal_deficit_limit = max(connection_tol * 3.2, connection_tol + 18.0)
        for item in collected:
            metrics = item.get("metrics") if isinstance(item, dict) else None
            if metrics is None:
                enriched = enrich_profile_record(item)
                metrics = enriched.get("metrics") if enriched is not None else None
            if metrics is None:
                continue
            widths.append(float(metrics["width"]))
            areas.append(float(metrics["area"]))
            if float(metrics["coverage_deficit"]) <= connection_tol:
                full_support_hits += 1
            z_val = float(item.get("z", 0.0))
            if float(metrics["coverage_deficit"]) <= terminal_deficit_limit:
                if z_val <= float(base_z_start) + terminal_band:
                    terminal_hits_start += 1
                if z_val >= float(base_z_end) - terminal_band:
                    terminal_hits_end += 1
            if last_width is not None:
                local_width_jump = max(local_width_jump, abs(float(metrics["width"]) - last_width))
            last_width = float(metrics["width"])

        width_median = float(np.median(np.asarray(widths, dtype=float))) if widths else 0.0
        area_median = float(np.median(np.asarray(areas, dtype=float))) if areas else 0.0
        max_width_ratio = (max(widths) / max(1.0, width_median)) if widths else 0.0
        max_area_ratio = (max(areas) / max(1.0, area_median)) if areas else 0.0
        full_support_ratio = (float(full_support_hits) / float(len(collected))) if collected else 0.0
        return {
            "count": len(collected),
            "z_min": min(z_vals),
            "z_max": max(z_vals),
            "z_span": z_span,
            "coverage_ratio": coverage_ratio,
            "start_gap": start_gap,
            "end_gap": end_gap,
            "max_gap": max_gap,
            "terminal_hits_start": terminal_hits_start,
            "terminal_hits_end": terminal_hits_end,
            "full_support_ratio": full_support_ratio,
            "width_median": width_median,
            "area_median": area_median,
            "max_width_ratio": max_width_ratio,
            "max_area_ratio": max_area_ratio,
            "max_local_width_jump": local_width_jump,
        }

    def describe_stack_gate_failures(
        metrics,
        *,
        count_floor=None,
        coverage_floor=None,
        edge_gap_limit=None,
        max_gap_limit=None,
        require_terminal_hits=False,
        support_floor=None,
        width_ratio_limit=None,
        area_ratio_limit=None,
        local_width_jump_floor=None,
        local_width_jump_ratio=None
    ):
        if metrics is None:
            return ["metrics-missing"]

        reasons = []
        if count_floor is not None and int(metrics.get("count", 0)) < int(count_floor):
            reasons.append(f"count<{int(count_floor)}")
        if coverage_floor is not None and float(metrics.get("coverage_ratio", 0.0)) < float(coverage_floor):
            reasons.append(f"coverage<{float(coverage_floor):.2f}")
        if edge_gap_limit is not None:
            if float(metrics.get("start_gap", 0.0)) > float(edge_gap_limit):
                reasons.append(f"start-gap>{float(edge_gap_limit):.2f}")
            if float(metrics.get("end_gap", 0.0)) > float(edge_gap_limit):
                reasons.append(f"end-gap>{float(edge_gap_limit):.2f}")
        if max_gap_limit is not None and float(metrics.get("max_gap", 0.0)) > float(max_gap_limit):
            reasons.append(f"max-gap>{float(max_gap_limit):.2f}")
        if require_terminal_hits:
            if int(metrics.get("terminal_hits_start", 0)) < 1:
                reasons.append("terminal-start-miss")
            if int(metrics.get("terminal_hits_end", 0)) < 1:
                reasons.append("terminal-end-miss")
        if support_floor is not None and float(metrics.get("full_support_ratio", 0.0)) < float(support_floor):
            reasons.append(f"support<{float(support_floor):.2f}")
        if width_ratio_limit is not None and float(metrics.get("max_width_ratio", 0.0)) > float(width_ratio_limit):
            reasons.append(f"width-ratio>{float(width_ratio_limit):.2f}")
        if area_ratio_limit is not None and float(metrics.get("max_area_ratio", 0.0)) > float(area_ratio_limit):
            reasons.append(f"area-ratio>{float(area_ratio_limit):.2f}")
        if local_width_jump_floor is not None:
            local_jump_limit = float(local_width_jump_floor)
            if local_width_jump_ratio is not None:
                local_jump_limit = max(
                    local_jump_limit,
                    float(metrics.get("width_median", 0.0)) * float(local_width_jump_ratio)
                )
            if float(metrics.get("max_local_width_jump", 0.0)) > local_jump_limit:
                reasons.append(f"width-jump>{local_jump_limit:.2f}")
        return reasons

    def collect_profiles(active_guide_geom, width_hint, candidate_z_samples, profile_min_area=16.0):
        if active_guide_geom is None or active_guide_geom.is_empty:
            return []
        collected = []
        for z_level in candidate_z_samples:
            profile_entry = extract_profile_record(
                z_level,
                active_guide_geom,
                width_hint,
                profile_min_area=profile_min_area
            )
            if profile_entry is not None:
                collected.append(profile_entry)
        collected.sort(key=lambda item: float(item.get("z", 0.0)))
        collected = refine_jump_profiles(collected, active_guide_geom, width_hint)
        collected = fill_large_profile_gaps(collected, active_guide_geom, width_hint)
        collected = rescue_terminal_profiles(collected, active_guide_geom, width_hint, candidate_z_samples)
        collected = fill_large_profile_gaps(collected, active_guide_geom, width_hint)
        collected = repair_profile_outliers(collected, active_guide_geom, width_hint)
        return collected

    def build_collection_guide(active_mesh):
        return build_member_actual_slice_guide(
            member_region_points,
            member_sections=member_sections,
            root_points=root_points,
            tip_sections=member_tip_sections,
            buffer_pad=(1.74 if active_mesh is not mesh else 1.20),
            guide_inner_r=guide_inner_r,
            guide_outer_r=guide_outer_r,
            relaxed=(active_mesh is not mesh)
        )

    guide_geom = build_collection_guide(active_hint_mesh)
    profiles = collect_profiles(guide_geom, expected_width, candidate_z, profile_min_area=16.0)

    if len(profiles) < 5:
        relaxed_guide_geom = build_member_actual_slice_guide(
            member_region_points,
            member_sections=member_sections,
            root_points=root_points,
            tip_sections=member_tip_sections,
            buffer_pad=1.75,
            guide_inner_r=guide_inner_r,
            guide_outer_r=guide_outer_r,
            relaxed=True
        )
        relaxed_width_hint = (float(expected_width) * 1.08) if expected_width is not None else None
        relaxed_profiles = collect_profiles(
            relaxed_guide_geom,
            relaxed_width_hint,
            candidate_z,
            profile_min_area=10.0
        )
        if relaxed_profiles:
            merged = {}
            for item in profiles:
                z_key = round(float(item.get("z", 0.0)), 3)
                merged[z_key] = item
            for item in relaxed_profiles:
                z_key = round(float(item.get("z", 0.0)), 3)
                if z_key in merged:
                    continue
                merged[z_key] = item
            profiles = [merged[key] for key in sorted(merged.keys())]

    # Strict source policy: if guided member source is rejected, do not fallback
    # to broad full-wheel slicing for this member.
    strict_guided_member_source = True
    should_fallback_to_full_mesh = False
    accepted_via_strict_retry = False
    source_rejection_reasons = []
    deferred_partial_profiles = None
    if guide_hint_mesh is not None:
        if len(profiles) < 8:
            should_fallback_to_full_mesh = True
            source_rejection_reasons.append("count<8")
        else:
            metrics = profile_stack_metrics(profiles)
            source_rejection_reasons.extend(
                describe_stack_gate_failures(
                    metrics,
                    count_floor=8,
                    coverage_floor=0.68,
                    edge_gap_limit=6.2,
                    require_terminal_hits=True,
                    support_floor=0.36,
                    width_ratio_limit=1.58,
                    area_ratio_limit=1.78
                )
            )
            should_fallback_to_full_mesh = bool(source_rejection_reasons)

    if should_fallback_to_full_mesh and strict_guided_member_source:
        strict_retry_guide = build_member_actual_slice_guide(
            member_region_points,
            member_sections=member_sections,
            root_points=root_points,
            tip_sections=member_tip_sections,
            buffer_pad=2.45,
            guide_inner_r=max(0.0, guide_inner_r - 2.0) if guide_inner_r is not None else None,
            guide_outer_r=(guide_outer_r + 8.0) if guide_outer_r is not None else None,
            relaxed=True
        )
        strict_retry_profiles = collect_profiles(
            strict_retry_guide,
            (float(expected_width) * 1.10) if expected_width is not None else None,
            build_candidate_z_samples(mesh, base_z_start, base_z_end),
            profile_min_area=9.0
        )
        strict_retry_metrics = profile_stack_metrics(strict_retry_profiles)
        strict_retry_reasons = describe_stack_gate_failures(
            strict_retry_metrics,
            count_floor=7,
            coverage_floor=0.62,
            edge_gap_limit=7.4,
            max_gap_limit=max(6.2, target_z_span * 0.38),
            require_terminal_hits=True,
            support_floor=0.24,
            width_ratio_limit=1.64,
            area_ratio_limit=1.84
        ) if strict_retry_metrics is not None else ["metrics-missing"]
        if strict_retry_profiles and not strict_retry_reasons:
            try:
                print(
                    f"[*] Member actual XY@Z strict retry accepted: "
                    f"profiles={len(strict_retry_profiles)}, "
                    f"coverage={strict_retry_metrics['coverage_ratio']:.2f}, "
                    f"term={strict_retry_metrics['terminal_hits_start']}/{strict_retry_metrics['terminal_hits_end']}"
                )
            except Exception:
                pass
            profiles = strict_retry_profiles
            should_fallback_to_full_mesh = False
            accepted_via_strict_retry = True
        else:
            strict_retry_partial_ok = (
                strict_retry_metrics is not None and
                int(strict_retry_metrics.get("count", 0)) >= 24 and
                float(strict_retry_metrics.get("coverage_ratio", 0.0)) >= 0.80 and
                float(strict_retry_metrics.get("start_gap", 0.0)) <= 1.6 and
                float(strict_retry_metrics.get("full_support_ratio", 0.0)) >= 0.36
            )
            strict_retry_area_only_ok = (
                strict_retry_metrics is not None and
                int(strict_retry_metrics.get("count", 0)) >= 32 and
                float(strict_retry_metrics.get("coverage_ratio", 0.0)) >= 0.90 and
                float(strict_retry_metrics.get("start_gap", 0.0)) <= 1.8 and
                float(strict_retry_metrics.get("end_gap", 0.0)) <= 1.8 and
                float(strict_retry_metrics.get("full_support_ratio", 0.0)) >= 0.42 and
                float(strict_retry_metrics.get("max_width_ratio", 0.0)) <= 1.36 and
                float(strict_retry_metrics.get("max_area_ratio", 0.0)) <= 1.88 and
                bool(strict_retry_reasons) and
                all(str(reason).startswith("area-ratio>") for reason in (strict_retry_reasons or []))
            )
            try:
                retry_count = int(strict_retry_metrics["count"]) if strict_retry_metrics is not None else 0
                retry_coverage = float(strict_retry_metrics["coverage_ratio"]) if strict_retry_metrics is not None else 0.0
                retry_start_gap = float(strict_retry_metrics["start_gap"]) if strict_retry_metrics is not None else 0.0
                retry_end_gap = float(strict_retry_metrics["end_gap"]) if strict_retry_metrics is not None else 0.0
                retry_term_start = int(strict_retry_metrics["terminal_hits_start"]) if strict_retry_metrics is not None else 0
                retry_term_end = int(strict_retry_metrics["terminal_hits_end"]) if strict_retry_metrics is not None else 0
                print(
                    f"[*] Member actual XY@Z guided-window rejected: {guide_hint_label}, "
                    f"reasons={','.join(source_rejection_reasons) if source_rejection_reasons else 'unknown'}, "
                    f"strict retry metrics="
                    f"{retry_count}/{retry_coverage:.2f}/{retry_start_gap:.2f}/{retry_end_gap:.2f}/{retry_term_start}/{retry_term_end}, "
                    f"strict retry failed={','.join(strict_retry_reasons) if strict_retry_reasons else 'unknown'} -> returning empty member stack"
                )
            except Exception:
                pass
            if (strict_retry_partial_ok or strict_retry_area_only_ok) and strict_retry_profiles:
                terminal_retry_miss = any(reason == "terminal-end-miss" for reason in (strict_retry_reasons or []))
                terminal_source_miss = any(reason == "terminal-end-miss" for reason in (source_rejection_reasons or []))
                if strict_retry_area_only_ok:
                    try:
                        print("[*] Member actual XY@Z strict retry area-only stack retained")
                    except Exception:
                        pass
                    update_meta(
                        stack_mode="strict_retry_area_only",
                        profiles=strict_retry_profiles,
                        prefer_local_section=True,
                        source_label=guide_hint_label
                    )
                    return strict_retry_profiles
                if terminal_retry_miss or terminal_source_miss:
                    deferred_partial_profiles = strict_retry_profiles
                    should_fallback_to_full_mesh = True
                    try:
                        print("[*] Member actual XY@Z strict retry partial stack deferred while broad guide attempts terminal recovery")
                    except Exception:
                        pass
                else:
                    try:
                        print("[*] Member actual XY@Z strict retry partial stack retained for local-section overrides")
                    except Exception:
                        pass
                    update_meta(
                        stack_mode="strict_retry_partial",
                        profiles=strict_retry_profiles,
                        prefer_local_section=True,
                        source_label=guide_hint_label
                    )
                    return strict_retry_profiles
            if deferred_partial_profiles is not None:
                pass
            else:
                update_meta(stack_mode="guided_window_rejected", profiles=[], source_label=guide_hint_label)
                return []

    if should_fallback_to_full_mesh:
        try:
            print(
                f"[*] Member actual XY@Z guided-window rejected: {guide_hint_label}, "
                f"reasons={','.join(source_rejection_reasons) if source_rejection_reasons else 'unknown'}, "
                f"falling back to broad full-wheel guide"
            )
        except Exception:
            pass
        guide_hint_mesh = None
        guide_hint_label = "full-wheel-guide"
        z_start = base_z_start
        z_end = base_z_end
        candidate_z = build_candidate_z_samples(mesh, z_start, z_end)
        guide_geom = build_collection_guide(mesh)
        profiles = collect_profiles(guide_geom, expected_width, candidate_z, profile_min_area=16.0)
        if len(profiles) < 5:
            relaxed_guide_geom = build_member_actual_slice_guide(
                member_region_points,
                member_sections=member_sections,
                root_points=root_points,
                tip_sections=member_tip_sections,
                buffer_pad=1.45,
                guide_inner_r=guide_inner_r,
                guide_outer_r=guide_outer_r,
                relaxed=True
            )
            relaxed_width_hint = (float(expected_width) * 1.08) if expected_width is not None else None
            relaxed_profiles = collect_profiles(
                relaxed_guide_geom,
                relaxed_width_hint,
                candidate_z,
                profile_min_area=10.0
            )
            if relaxed_profiles:
                merged = {}
                for item in profiles:
                    z_key = round(float(item.get("z", 0.0)), 3)
                    merged[z_key] = item
                for item in relaxed_profiles:
                    z_key = round(float(item.get("z", 0.0)), 3)
                    if z_key in merged:
                        continue
                    merged[z_key] = item
                profiles = [merged[key] for key in sorted(merged.keys())]

    if len(profiles) < 3:
        if deferred_partial_profiles:
            try:
                print("[*] Member actual XY@Z broad guide failed; reusing deferred partial stack for local-section overrides")
            except Exception:
                pass
            update_meta(
                stack_mode="deferred_partial_broad_failed",
                profiles=deferred_partial_profiles,
                prefer_local_section=True,
                source_label="deferred-guided-window"
            )
            return deferred_partial_profiles
        update_meta(stack_mode="broad-guide-empty", profiles=[], source_label="full-wheel-guide")
        return []

    metrics = profile_stack_metrics(profiles)
    if metrics is not None:
        takeover_rejection_reasons = describe_stack_gate_failures(
            metrics,
            count_floor=7,
            coverage_floor=0.66,
            edge_gap_limit=6.2,
            max_gap_limit=max(8.4, target_z_span * 0.46),
            require_terminal_hits=True,
            support_floor=0.34,
            width_ratio_limit=1.52,
            area_ratio_limit=1.72
        )
        poor_takeover = bool(takeover_rejection_reasons)
        if poor_takeover:
            allowed_partial_reasons = []
            for reason in takeover_rejection_reasons:
                if reason == "terminal-end-miss":
                    continue
                if str(reason).startswith("max-gap>"):
                    continue
                if (
                    str(reason).startswith("area-ratio>") and
                    float(metrics.get("max_width_ratio", 0.0)) <= 1.36 and
                    float(metrics.get("max_area_ratio", 0.0)) <= 1.76 and
                    float(metrics.get("full_support_ratio", 0.0)) >= 0.44
                ):
                    continue
                allowed_partial_reasons.append(reason)
            partial_override_ok = (
                int(metrics.get("count", 0)) >= 24 and
                float(metrics.get("coverage_ratio", 0.0)) >= 0.80 and
                float(metrics.get("full_support_ratio", 0.0)) >= 0.42 and
                float(metrics.get("start_gap", 0.0)) <= 1.6 and
                len(allowed_partial_reasons) == 0
            )
            print(
                f"[*] Member actual XY@Z stack rejected: "
                f"count={metrics['count']}, coverage={metrics['coverage_ratio']:.2f}, "
                f"start_gap={metrics['start_gap']:.2f}, end_gap={metrics['end_gap']:.2f}, "
                f"max_gap={metrics['max_gap']:.2f}, "
                f"term={metrics['terminal_hits_start']}/{metrics['terminal_hits_end']}, "
                f"support={metrics['full_support_ratio']:.2f}, "
                f"width_ratio={metrics['max_width_ratio']:.2f}, "
                f"area_ratio={metrics['max_area_ratio']:.2f}, "
                f"width_jump={metrics['max_local_width_jump']:.2f}, "
                f"reasons={','.join(takeover_rejection_reasons)}"
            )
            if partial_override_ok:
                print("[*] Member actual XY@Z partial stack retained for local-section overrides")
                update_meta(
                    stack_mode="broad_partial_override",
                    profiles=profiles,
                    prefer_local_section=True,
                    source_label=source_mesh_label
                )
                return profiles
            if deferred_partial_profiles:
                print("[*] Member actual XY@Z broad guide still poor; reusing deferred partial stack for local-section overrides")
                update_meta(
                    stack_mode="deferred_partial_reused",
                    profiles=deferred_partial_profiles,
                    prefer_local_section=True,
                    source_label="deferred-guided-window"
                )
                return deferred_partial_profiles
            update_meta(stack_mode="broad-guide-rejected", profiles=[], source_label=source_mesh_label)
            return []

    try:
        print(
            f"[*] Member actual XY@Z source: {source_mesh_label}, "
            f"profiles={len(profiles)}, Z={float(profiles[0]['z']):.2f}->{float(profiles[-1]['z']):.2f}"
        )
        if metrics is not None:
            print(
                f"[*] Member actual XY@Z quality: coverage={metrics['coverage_ratio']:.2f}, "
                f"start_gap={metrics['start_gap']:.2f}, end_gap={metrics['end_gap']:.2f}, "
                f"term={metrics['terminal_hits_start']}/{metrics['terminal_hits_end']}, "
                f"support={metrics['full_support_ratio']:.2f}, "
                f"width_ratio={metrics['max_width_ratio']:.2f}, "
                f"area_ratio={metrics['max_area_ratio']:.2f}"
            )
    except Exception:
        pass

    if profiles:
        metric_rows = [
            item.get("metrics") if isinstance(item, dict) else None
            for item in profiles
        ]
        width_values = [
            float(metrics["width"])
            for metrics in metric_rows
            if isinstance(metrics, dict) and metrics.get("width") is not None
        ]
        area_values = [
            float(metrics["area"])
            for metrics in metric_rows
            if isinstance(metrics, dict) and metrics.get("area") is not None
        ]
        median_width = float(np.median(np.asarray(width_values, dtype=float))) if width_values else 0.0
        median_area = float(np.median(np.asarray(area_values, dtype=float))) if area_values else 0.0
        terminal_band = max(2.8, target_z_span * 0.16)
        width_change_floor = max(3.2, median_width * 0.16)
        area_change_floor = max(18.0, median_area * 0.16)
        radial_change_floor = max(2.4, expected_span * 0.045)

        for idx, item in enumerate(profiles):
            try:
                z_val = float(item.get("z", 0.0))
            except Exception:
                z_val = 0.0
            terminal_contact = (
                z_val <= float(base_z_start) + terminal_band or
                z_val >= float(base_z_end) - terminal_band
            )
            preserve_detail = bool(terminal_contact)
            metrics = metric_rows[idx] if idx < len(metric_rows) else None
            if not preserve_detail and isinstance(metrics, dict):
                for neighbor_idx in (idx - 1, idx + 1):
                    if neighbor_idx < 0 or neighbor_idx >= len(metric_rows):
                        continue
                    neighbor_metrics = metric_rows[neighbor_idx]
                    if not isinstance(neighbor_metrics, dict):
                        continue
                    if (
                        abs(float(metrics["width"]) - float(neighbor_metrics["width"])) >= width_change_floor or
                        abs(float(metrics["area"]) - float(neighbor_metrics["area"])) >= area_change_floor or
                        abs(float(metrics["r_min"]) - float(neighbor_metrics["r_min"])) >= radial_change_floor or
                        abs(float(metrics["r_max"]) - float(neighbor_metrics["r_max"])) >= radial_change_floor
                    ):
                        preserve_detail = True
                        break
            item["terminal_contact"] = bool(item.get("terminal_contact") or terminal_contact)
            item["preserve_detail"] = bool(item.get("preserve_detail") or preserve_detail)
            item["profile_source"] = str(item.get("profile_source") or "actual_xy_z")

    if accepted_via_strict_retry:
        resolved_stack_mode = "strict_retry_accepted"
    elif guide_hint_mesh is not None:
        resolved_stack_mode = "guided_window_clean"
    else:
        resolved_stack_mode = "full_wheel_clean"
    update_meta(
        stack_mode=resolved_stack_mode,
        profiles=profiles,
        prefer_local_section=False,
        source_label=source_mesh_label
    )
    return profiles

def derive_actual_spoke_member_z_profiles(
    mesh,
    spoke_regions,
    spoke_sections,
    spoke_tip_sections,
    spoke_root_regions,
    spoke_motif_topology
):
    member_profiles = []
    for member_idx, region_payload in enumerate(spoke_regions or []):
        region_points = region_payload.get("points", []) if isinstance(region_payload, dict) else region_payload
        section_group = (
            spoke_sections[member_idx].get("sections", [])
            if member_idx < len(spoke_sections) and isinstance(spoke_sections[member_idx], dict)
            else []
        )
        tip_group = (
            spoke_tip_sections[member_idx].get("sections", [])
            if member_idx < len(spoke_tip_sections) and isinstance(spoke_tip_sections[member_idx], dict)
            else []
        )
        root_points = None
        if member_idx < len(spoke_root_regions):
            root_payload = spoke_root_regions[member_idx]
            root_points = root_payload.get("points", []) if isinstance(root_payload, dict) else root_payload

        region_desc = describe_planar_region(region_payload, min_area=20.0)
        member_angle = float(region_desc["angle"]) if region_desc is not None else 0.0
        profile_meta = {}
        profiles = extract_member_actual_z_profile_stack(
            mesh,
            region_points,
            section_group,
            tip_group,
            member_angle,
            root_points=root_points,
            sample_count=21,
            meta_out=profile_meta
        )
        if profiles:
            z_vals = []
            inner_r_vals = []
            outer_r_vals = []
            for item in profiles:
                try:
                    z_vals.append(float(item.get("z", 0.0)))
                    pts = item.get("points", []) or []
                    if len(pts) < 4:
                        continue
                    rs = [math.hypot(float(x), float(y)) for x, y in pts[:-1]]
                    if rs:
                        inner_r_vals.append(float(min(rs)))
                        outer_r_vals.append(float(max(rs)))
                except Exception:
                    continue
            if z_vals:
                print(
                    f"[*] Spoke {member_idx} actual XY@Z profiles: count={len(profiles)}, "
                    f"Z={min(z_vals):.2f}->{max(z_vals):.2f}, "
                    f"R={min(inner_r_vals) if inner_r_vals else 0.0:.2f}->{max(outer_r_vals) if outer_r_vals else 0.0:.2f}"
                )
        else:
            print(f"[*] Spoke {member_idx} actual XY@Z profiles: count=0")
        member_profiles.append({
            "profiles": profiles,
            "prefer_local_section": bool(profile_meta.get("prefer_local_section")),
            "stack_mode": str(profile_meta.get("stack_mode") or ("empty" if not profiles else "unknown")),
            "profile_count": int(profile_meta.get("profile_count", len(profiles or []))),
            "source_label": str(profile_meta.get("source_label") or "")
        })
    return member_profiles

def derive_actual_spoke_member_z_profiles(*args, **kwargs):
    spoke_regions = kwargs.get("spoke_regions")
    if spoke_regions is None and len(args) >= 2:
        spoke_regions = args[1]
    return [
        {"profiles": [], "disabled_reason": "archived_actual_z_path"}
        for _ in (spoke_regions or [])
    ]


def derive_spoke_motif_section_groups(spoke_motif_topology, spoke_regions, spoke_sections, spoke_tip_sections, spoke_actual_z_profiles=None):
    """Bundle grouped spoke members and their section stacks into motif-level payloads."""
    if not isinstance(spoke_motif_topology, dict):
        return []
    motifs = []
    for group in spoke_motif_topology.get("groups", []):
        member_indices = [int(idx) for idx in group.get("member_indices", [])]
        if not member_indices:
            continue
        group_angle = float(group.get("group_angle", 0.0))
        members = []
        offsets = []
        for member_idx in member_indices:
            if member_idx >= len(spoke_regions):
                continue
            region = spoke_regions[member_idx]
            region_desc = describe_planar_region(region, min_area=20.0)
            member_angle = float(region_desc["angle"]) if region_desc is not None else group_angle
            signed_offset = ((member_angle - group_angle + 540.0) % 360.0) - 180.0
            offsets.append((member_idx, signed_offset))
            members.append({
                "member_index": int(member_idx),
                "angle": round(float(member_angle), 3),
                "signed_offset_deg": round(float(signed_offset), 3),
                "region": region.get("points", []) if isinstance(region, dict) else region,
                "sections": (
                    spoke_sections[member_idx].get("sections", [])
                    if member_idx < len(spoke_sections) and isinstance(spoke_sections[member_idx], dict)
                    else []
                ),
                "tip_sections": (
                    spoke_tip_sections[member_idx].get("sections", [])
                    if member_idx < len(spoke_tip_sections) and isinstance(spoke_tip_sections[member_idx], dict)
                    else []
                ),
                "actual_z_profiles": (
                    spoke_actual_z_profiles[member_idx].get("profiles", [])
                    if spoke_actual_z_profiles and member_idx < len(spoke_actual_z_profiles) and isinstance(spoke_actual_z_profiles[member_idx], dict)
                    else []
                ),
                "actual_z_prefer_local_section": (
                    bool(spoke_actual_z_profiles[member_idx].get("prefer_local_section"))
                    if spoke_actual_z_profiles and member_idx < len(spoke_actual_z_profiles) and isinstance(spoke_actual_z_profiles[member_idx], dict)
                    else False
                ),
                "actual_z_stack_mode": (
                    str(spoke_actual_z_profiles[member_idx].get("stack_mode") or "")
                    if spoke_actual_z_profiles and member_idx < len(spoke_actual_z_profiles) and isinstance(spoke_actual_z_profiles[member_idx], dict)
                    else ""
                ),
                "actual_z_profile_count": (
                    int(spoke_actual_z_profiles[member_idx].get("profile_count", 0))
                    if spoke_actual_z_profiles and member_idx < len(spoke_actual_z_profiles) and isinstance(spoke_actual_z_profiles[member_idx], dict)
                    else 0
                )
            })

        if not members:
            continue

        ordered_offsets = [item[0] for item in sorted(offsets, key=lambda item: item[1])]
        member_slot_map = {member_idx: slot_idx for slot_idx, member_idx in enumerate(ordered_offsets)}
        for member in members:
            member["slot_index"] = int(member_slot_map.get(int(member["member_index"]), 0))

        motifs.append({
            "motif_index": int(group.get("group_index", len(motifs))),
            "motif_type": spoke_motif_topology.get("motif_type", "unknown"),
            "group_angle": round(float(group_angle), 3),
            "member_count": int(len(members)),
            "members": members
        })
    return motifs

def derive_canonical_spoke_templates(spoke_motif_sections, target_count=48, z_tolerance=0.9):
    """Build per-slot canonical spoke templates from actual XY@Z slice stacks."""
    slot_stacks = {}

    def profile_stack_metrics(stack):
        z_vals = []
        areas = []
        radial_centers = []
        tangential_centers = []
        for profile in stack or []:
            loop = profile.get("points_local", []) if isinstance(profile, dict) else []
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
            ys = [float(y) for _, y in pts]
            z_vals.append(float(profile.get("z", 0.0)))
            areas.append(float(poly.area))
            radial_centers.append((max(xs) + min(xs)) * 0.5)
            tangential_centers.append((max(ys) + min(ys)) * 0.5)
        if len(z_vals) < 3:
            return None
        roughness = 0.0
        for values, weight in (
            (areas, 1.00),
            (radial_centers, 0.55),
            (tangential_centers, 0.35),
        ):
            arr = np.asarray(values, dtype=float)
            if arr.size >= 3:
                roughness += float(np.mean(np.abs(np.diff(arr, n=2)))) * float(weight)
        z_arr = np.asarray(z_vals, dtype=float)
        return {
            "z_min": float(np.min(z_arr)),
            "z_max": float(np.max(z_arr)),
            "z_span": float(np.max(z_arr) - np.min(z_arr)),
            "profile_count": int(len(z_vals)),
            "roughness": float(roughness),
        }

    for motif_payload in spoke_motif_sections or []:
        motif_type = motif_payload.get("motif_type", "unknown")
        for member_payload in motif_payload.get("members", []) or []:
            actual_profiles = member_payload.get("actual_z_profiles", []) or []
            if len(actual_profiles) < 3:
                continue
            slot_index = int(member_payload.get("slot_index", 0))
            member_angle = float(member_payload.get("angle", 0.0))
            normalized_profiles = []
            reference_loop = None
            for profile in sorted(actual_profiles, key=lambda item: float(item.get("z", 0.0))):
                pts = profile.get("points", []) if isinstance(profile, dict) else []
                if len(pts) < 4:
                    continue
                local_loop = world_loop_to_member_local(pts, member_angle)
                if len(local_loop) < 4:
                    continue
                sampled_loop = resample_closed_loop_outer(local_loop, target_count=target_count)
                if len(sampled_loop) < 8:
                    continue
                if reference_loop is None:
                    reference_loop = sampled_loop
                else:
                    sampled_loop = align_resampled_loop_outer(
                        reference_loop,
                        sampled_loop,
                        allow_reverse=False
                    )
                normalized_profiles.append({
                    "z": float(profile.get("z", 0.0)),
                    "points_local": sampled_loop
                })
            if len(normalized_profiles) < 3:
                continue
            slot_entry = slot_stacks.setdefault(slot_index, {
                "slot_index": slot_index,
                "motif_type": motif_type,
                "member_stacks": []
            })
            slot_entry["member_stacks"].append(normalized_profiles)

    templates = []
    for slot_index in sorted(slot_stacks.keys()):
        slot_entry = slot_stacks[slot_index]
        member_stacks = slot_entry.get("member_stacks", [])
        if len(member_stacks) < 2:
            continue

        stack_metrics = []
        for stack in member_stacks:
            metrics = profile_stack_metrics(stack)
            if metrics is None:
                continue
            metrics["stack"] = stack
            stack_metrics.append(metrics)
        if len(stack_metrics) < 2:
            continue

        max_profile_count = max(item["profile_count"] for item in stack_metrics)
        max_z_span = max(item["z_span"] for item in stack_metrics)
        preferred_metrics = [
            item for item in stack_metrics
            if item["profile_count"] >= max_profile_count - 1 and item["z_span"] >= max_z_span * 0.92
        ]
        donor_metric = min(
            preferred_metrics if preferred_metrics else stack_metrics,
            key=lambda item: (
                item["roughness"],
                -item["z_span"],
                -item["profile_count"]
            )
        )
        member_stacks = [item["stack"] for item in (preferred_metrics if preferred_metrics else stack_metrics)]

        z_values = []
        for stack in member_stacks:
            for profile in stack:
                z_values.append(float(profile.get("z", 0.0)))
        if len(z_values) < 3:
            continue

        z_values.sort()
        z_clusters = []
        for z_val in z_values:
            if not z_clusters or z_val > z_clusters[-1][-1] + z_tolerance:
                z_clusters.append([z_val])
            else:
                z_clusters[-1].append(z_val)

        min_support = max(2, min(3, len(member_stacks)))
        template_profiles = []
        for cluster in z_clusters:
            cluster_center = float(np.median(np.asarray(cluster, dtype=float)))
            support_loops = []
            support_z = []
            reference_loop = None
            for stack in member_stacks:
                best_profile = None
                best_delta = None
                for profile in stack:
                    delta = abs(float(profile.get("z", 0.0)) - cluster_center)
                    if best_delta is None or delta < best_delta:
                        best_profile = profile
                        best_delta = delta
                if best_profile is None or best_delta is None or best_delta > z_tolerance:
                    continue
                candidate_loop = [
                    (float(x), float(y))
                    for x, y in best_profile.get("points_local", [])
                ]
                if len(candidate_loop) < 8:
                    continue
                if reference_loop is None:
                    reference_loop = candidate_loop
                else:
                    candidate_loop = align_resampled_loop_outer(
                        reference_loop,
                        candidate_loop,
                        allow_reverse=False
                    )
                support_loops.append(candidate_loop)
                support_z.append(float(best_profile.get("z", cluster_center)))

            if len(support_loops) < min_support:
                continue

            donor_profile = None
            donor_delta = None
            for profile in donor_metric.get("stack", []):
                delta = abs(float(profile.get("z", 0.0)) - cluster_center)
                if donor_delta is None or delta < donor_delta:
                    donor_profile = profile
                    donor_delta = delta
            if donor_profile is None or donor_delta is None or donor_delta > z_tolerance:
                continue
            loop_points = [
                [round(float(x), 3), round(float(y), 3)]
                for x, y in (donor_profile.get("points_local", []) or [])
            ]
            if len(loop_points) < 8:
                continue
            if loop_points[0] != loop_points[-1]:
                loop_points.append(loop_points[0])
            template_profiles.append({
                "z": round(float(donor_profile.get("z", cluster_center)), 3),
                "points_local": loop_points,
                "support_count": int(len(support_loops))
            })

        template_profiles.sort(key=lambda item: float(item.get("z", 0.0)))
        if len(template_profiles) < 3:
            continue

        templates.append({
            "slot_index": int(slot_index),
            "motif_type": slot_entry.get("motif_type", "unknown"),
            "member_count": int(len(member_stacks)),
            "profile_count": int(len(template_profiles)),
            "profiles": template_profiles,
            "donor_profiles": [
                {
                    "z": round(float(profile.get("z", 0.0)), 3),
                    "points_local": [
                        [round(float(x), 3), round(float(y), 3)]
                        for x, y in (profile.get("points_local", []) or [])
                    ]
                }
                for profile in donor_metric.get("stack", [])
                if isinstance(profile, dict)
            ]
        })

    return templates

def filter_spoke_section_records(section_records):
    """Discard local spoke sections that drift far away from the member midline."""
    if not section_records or len(section_records) < 4:
        return section_records

    ratios = []
    for section in section_records:
        target_width = section.get("target_width")
        local_width = section.get("local_width")
        if target_width is None or local_width is None:
            continue
        if float(target_width) <= 1e-6:
            continue
        ratios.append(float(local_width) / float(target_width))

    if not ratios:
        return section_records

    median_ratio = float(np.median(np.asarray(ratios, dtype=float)))
    filtered = []
    for section in section_records:
        if section.get("extension_side"):
            filtered.append(section)
            continue
        target_width = section.get("target_width")
        local_width = section.get("local_width")
        local_center_x = section.get("local_center_x")
        target_center_x = section.get("target_center_x", 0.0)
        if target_width is None or local_width is None or local_center_x is None:
            filtered.append(section)
            continue
        target_width = max(0.5, float(target_width))
        local_width = float(local_width)
        center_error = abs(float(local_center_x) - float(target_center_x))
        width_ratio = local_width / target_width

        hard_center_reject = (
            center_error > max(6.0, target_width * 0.9) and
            width_ratio > 1.45
        )
        hard_width_reject = (
            local_width > max(target_width * 2.6, target_width + 18.0)
        )
        adaptive_reject = (
            width_ratio > max(2.4, median_ratio * 1.55) and
            center_error > max(4.0, target_width * 0.45)
        )

        if hard_center_reject or hard_width_reject or adaptive_reject:
            continue
        filtered.append(section)

    return filtered if len(filtered) >= 3 else section_records

def derive_window_local_keepouts(spoke_voids, spoke_root_regions, lug_boss_regions):
    """Match each window to its nearby root/boss patches so Module B can protect those connections locally."""
    if not spoke_voids:
        return [], []

    root_entries = []
    for idx, region in enumerate(spoke_root_regions):
        desc = describe_planar_region(region, min_area=18.0)
        if desc is None:
            continue
        desc["key"] = ("root", idx)
        root_entries.append(desc)

    boss_entries = []
    for idx, region in enumerate(lug_boss_regions):
        desc = describe_planar_region(region, min_area=18.0)
        if desc is None:
            continue
        desc["key"] = ("boss", idx)
        boss_entries.append(desc)

    keepout_groups = []
    local_root_outer_radii = []
    boss_angle_cutoff = max(18.0, (360.0 / max(1, len(spoke_voids))) * 0.9)

    for spoke_void in spoke_voids:
        void_desc = describe_planar_region(spoke_void, min_area=24.0)
        if void_desc is None:
            keepout_groups.append([])
            local_root_outer_radii.append(None)
            continue

        void_angle = float(void_desc["angle"])
        selected = []
        selected_keys = set()
        local_root_outer = None

        if root_entries:
            root_sorted = sorted(
                root_entries,
                key=lambda item: (
                    angular_distance_deg(item["angle"], void_angle),
                    -item["outer_r"]
                )
            )
            for item in root_sorted[:min(2, len(root_sorted))]:
                selected.append({"points": item["points"]})
                selected_keys.add(item["key"])
                local_root_outer = item["outer_r"] if local_root_outer is None else max(local_root_outer, item["outer_r"])

        if boss_entries:
            boss_sorted = sorted(
                boss_entries,
                key=lambda item: (
                    angular_distance_deg(item["angle"], void_angle),
                    -item["outer_r"]
                )
            )
            for item in boss_sorted[:min(2, len(boss_sorted))]:
                if angular_distance_deg(item["angle"], void_angle) > boss_angle_cutoff:
                    continue
                if item["key"] in selected_keys:
                    continue
                selected.append({"points": item["points"]})
                selected_keys.add(item["key"])

        keepout_groups.append(selected)
        local_root_outer_radii.append(round(float(local_root_outer), 2) if local_root_outer is not None else None)

    return keepout_groups, local_root_outer_radii

def extract_hub_bottom_groove_regions(
    mesh,
    hole_count,
    phase_angle_deg,
    bore_radius,
    pcd_radius,
    hole_radius,
    hub_radius,
    pocket_radius,
    pocket_floor_z,
    pocket_top_z,
    hub_z_offset,
    hub_face_z,
    center_core_region
):
    """Extract the five rear hub-face relief pockets between adjacent lug holes."""
    if mesh is None or int(hole_count) <= 0:
        return [], {}
    if any(
        value is None
        for value in (
            bore_radius,
            pcd_radius,
            hole_radius,
            hub_radius,
            pocket_radius,
            pocket_floor_z,
            pocket_top_z,
            hub_z_offset,
            hub_face_z,
        )
    ):
        return [], {}

    try:
        clip_outer_r = min(float(hub_radius) + 3.0, float(pcd_radius) + float(pocket_radius) - 1.0)
        clip_outer_r = max(clip_outer_r, float(bore_radius) + 10.0)
        clip_geom = circle_polygon(clip_outer_r, count=220)
        rear_face_z = float(hub_z_offset)

        def angle_distance_deg(a_deg, b_deg):
            return abs(((float(a_deg) - float(b_deg) + 180.0) % 360.0) - 180.0)

        def angle_in_window(angle_deg, start_deg, end_deg, pad_deg=0.0):
            start_val = float(start_deg)
            end_val = float(end_deg)
            while end_val <= start_val:
                end_val += 360.0
            angle_val = float(angle_deg)
            while angle_val < start_val - float(pad_deg):
                angle_val += 360.0
            return (start_val - float(pad_deg)) <= angle_val <= (end_val + float(pad_deg))

        def collect_opening_line_entries(sample_z, allow_closed=False):
            section = mesh.section(
                plane_origin=[0.0, 0.0, float(sample_z)],
                plane_normal=[0.0, 0.0, 1.0]
            )
            if not section:
                return []

            clipped_lines = []
            for entity in section.entities:
                pts = section.vertices[entity.points]
                line = LineString(pts[:, :2])
                clipped_line = line.intersection(clip_geom)
                if clipped_line.is_empty:
                    continue
                if isinstance(clipped_line, LineString):
                    if clipped_line.length > 0.5:
                        clipped_lines.append(clipped_line)
                elif hasattr(clipped_line, "geoms"):
                    for sub_geom in clipped_line.geoms:
                        if isinstance(sub_geom, LineString) and sub_geom.length > 0.5:
                            clipped_lines.append(sub_geom)

            line_entries = []
            for line in clipped_lines:
                coords = [(float(x), float(y)) for x, y in list(line.coords)]
                if len(coords) < 4:
                    continue
                is_closed = math.hypot(coords[0][0] - coords[-1][0], coords[0][1] - coords[-1][1]) <= 0.8
                radii = [math.hypot(x, y) for x, y in coords]
                if not radii:
                    continue
                angle_window = continuous_angle_window([
                    math.degrees(math.atan2(y, x)) % 360.0
                    for x, y in coords
                ])
                if angle_window is None or float(angle_window[2]) < 10.0:
                    continue
                centroid = line.centroid
                min_r = float(min(radii))
                max_r = float(max(radii))
                if min_r <= float(bore_radius) + 6.0:
                    continue
                if max_r <= float(pcd_radius) - 2.0:
                    continue
                if is_closed:
                    if not allow_closed:
                        continue
                    if (max_r - min_r) < 4.0:
                        continue
                line_entries.append({
                    "coords": coords,
                    "centroid_angle": math.degrees(math.atan2(centroid.y, centroid.x)) % 360.0,
                    "length": float(line.length),
                    "min_r": min_r,
                    "max_r": max_r,
                    "closed": bool(is_closed),
                    "start_angle": float(angle_window[0]),
                    "end_angle": float(angle_window[1]),
                    "span": float(angle_window[2])
                })
            return sorted(line_entries, key=lambda item: float(item["centroid_angle"]))

        def build_opening_polygon_from_line(line_coords):
            if not line_coords or len(line_coords) < 4:
                return []

            coords = [(float(x), float(y)) for x, y in line_coords]
            if math.hypot(coords[0][0] - coords[-1][0], coords[0][1] - coords[-1][1]) <= 0.8:
                closed = canonicalize_loop(coords)
                return closed if len(closed) >= 4 else []

            radii = [math.hypot(x, y) for x, y in coords]
            if not radii:
                return []
            close_r = min(
                clip_outer_r - 0.1,
                max(float(np.percentile(np.asarray(radii, dtype=float), 96.0)), max(radii))
            )
            start_angle = math.degrees(math.atan2(coords[-1][1], coords[-1][0])) % 360.0
            end_angle = math.degrees(math.atan2(coords[0][1], coords[0][0])) % 360.0
            delta = end_angle - start_angle
            while delta <= -180.0:
                delta += 360.0
            while delta > 180.0:
                delta -= 360.0
            arc_steps = max(10, int(abs(delta) / 2.5))
            arc_pts = []
            for step_idx in range(1, arc_steps):
                ang = math.radians(start_angle + ((delta * step_idx) / arc_steps))
                arc_pts.append((close_r * math.cos(ang), close_r * math.sin(ang)))

            ring_pts = coords + arc_pts + [coords[0]]
            try:
                groove_poly = largest_polygon(normalize_geom(Polygon(ring_pts)), min_area=20.0)
                if groove_poly is None:
                    return []
                groove_coords = canonicalize_loop(list(groove_poly.exterior.coords))
                return groove_coords if len(groove_coords) >= 4 else []
            except Exception:
                return []

        def match_line_entries_to_regions(line_entries, base_regions, pad_deg=8.0):
            matched = {}
            used_entry_indices = set()
            for region_idx, base_region in enumerate(base_regions):
                groove_center = float(base_region.get("angle", 0.0))
                groove_start = float(base_region.get("start_angle", groove_center - 18.0))
                groove_end = float(base_region.get("end_angle", groove_center + 18.0))
                best_line_idx = None
                best_score = None
                for entry_idx, entry in enumerate(line_entries):
                    if entry_idx in used_entry_indices:
                        continue
                    centroid_angle = float(entry.get("centroid_angle", groove_center))
                    span_pad = max(float(pad_deg), float(entry.get("span", 0.0)) * 0.12)
                    if not angle_in_window(centroid_angle, groove_start, groove_end, pad_deg=span_pad):
                        continue
                    score = (
                        float(entry.get("length", 0.0))
                        + max(0.0, float(entry.get("max_r", 0.0)) - float(entry.get("min_r", 0.0)))
                        - (angle_distance_deg(centroid_angle, groove_center) * 1.8)
                    )
                    if best_score is None or score > best_score:
                        best_score = score
                        best_line_idx = entry_idx
                if best_line_idx is not None:
                    used_entry_indices.add(best_line_idx)
                    matched[region_idx] = line_entries[best_line_idx]
            return matched

        def build_line_region_map(matched, base_regions, fallback_regions, prefer_raw_outer=False):
            region_map = {}
            collected_radii = []
            for region_idx, entry in matched.items():
                raw_coords = build_opening_polygon_from_line(entry.get("coords", []))
                if len(raw_coords) < 4:
                    continue

                try:
                    raw_poly = largest_polygon(normalize_geom(Polygon(raw_coords)), min_area=20.0)
                except Exception:
                    raw_poly = None
                if raw_poly is None:
                    continue

                base_region = base_regions[region_idx]
                groove_center = float(base_region.get("angle", entry.get("centroid_angle", 0.0)))
                groove_start = float(base_region.get("start_angle", groove_center - 18.0))
                groove_end = float(base_region.get("end_angle", groove_center + 18.0))
                fallback_region = fallback_regions[region_idx] if region_idx < len(fallback_regions) else base_region
                fallback_pts = fallback_region.get("points", base_region.get("points", []))
                fallback_radii = [
                    math.hypot(x, y) for x, y in fallback_pts[:-1]
                ] if len(fallback_pts) >= 4 else []
                raw_radii = [math.hypot(x, y) for x, y in list(raw_poly.exterior.coords)[:-1]]
                if not raw_radii:
                    continue

                if prefer_raw_outer:
                    inner_clip_r = max(
                        float(bore_radius) + 3.2,
                        min(raw_radii) - 1.6
                    )
                    outer_clip_r = min(
                        float(clip_outer_r),
                        max(raw_radii) + 2.8,
                        float(hub_radius) + 2.0
                    )
                    angle_pad = 2.4
                else:
                    fallback_inner_r = min(fallback_radii) if fallback_radii else min(raw_radii)
                    fallback_outer_r = max(fallback_radii) if fallback_radii else max(raw_radii)
                    inner_clip_r = max(
                        float(bore_radius) + 2.4,
                        min(min(raw_radii), fallback_inner_r) - 0.9
                    )
                    outer_clip_r = min(
                        float(clip_outer_r),
                        max(max(raw_radii), fallback_outer_r) + 1.2
                    )
                    angle_pad = 1.0

                if outer_clip_r <= inner_clip_r + 1.2:
                    continue

                sector_clip = normalize_geom(
                    build_ring_sector(
                        groove_start - angle_pad,
                        groove_end + angle_pad,
                        inner_clip_r,
                        outer_clip_r
                    )
                )
                candidate_poly = largest_polygon(
                    normalize_geom(raw_poly.intersection(sector_clip)),
                    min_area=18.0
                )
                if candidate_poly is None:
                    candidate_poly = raw_poly
                if candidate_poly is None:
                    continue

                candidate_coords = canonicalize_loop(list(candidate_poly.exterior.coords))
                if len(candidate_coords) < 4:
                    continue
                region_map[region_idx] = candidate_coords
                collected_radii.extend([
                    math.hypot(x, y) for x, y in candidate_coords[:-1]
                ])
            return region_map, collected_radii

        search_floor_z = rear_face_z + 0.2
        search_top_z = min(
            float(hub_face_z) - 2.8,
            float(pocket_top_z) - 1.8,
            rear_face_z + max(12.0, min(18.0, (float(hub_face_z) - rear_face_z) * 0.72))
        )
        if search_top_z <= search_floor_z + 1.2:
            search_top_z = search_floor_z + 6.0
        z_candidates = np.linspace(search_floor_z, search_top_z, 24)
        valid_candidates = []

        for sample_z in z_candidates:
            section = mesh.section(plane_origin=[0.0, 0.0, float(sample_z)], plane_normal=[0.0, 0.0, 1.0])
            if not section:
                continue

            clipped_lines = []
            for entity in section.entities:
                pts = section.vertices[entity.points]
                line = LineString(pts[:, :2])
                clipped_line = line.intersection(clip_geom)
                if clipped_line.is_empty:
                    continue
                if isinstance(clipped_line, LineString):
                    if clipped_line.length > 0.15:
                        clipped_lines.append(clipped_line)
                elif hasattr(clipped_line, "geoms"):
                    for sub_geom in clipped_line.geoms:
                        if isinstance(sub_geom, LineString) and sub_geom.length > 0.15:
                            clipped_lines.append(sub_geom)

            if not clipped_lines:
                continue

            try:
                slice_polys = list(polygonize(linemerge(MultiLineString(clipped_lines))))
            except Exception:
                continue

            boss_entries = []
            local_core_outer_r = None
            for poly in slice_polys:
                poly = normalize_geom(poly)
                if poly.is_empty or float(poly.area) < 80.0:
                    continue
                centroid = poly.centroid
                centroid_r = math.hypot(centroid.x, centroid.y)
                if centroid_r <= float(bore_radius) + 3.5:
                    coords = list(poly.exterior.coords)
                    if len(coords) >= 4:
                        radii = [math.hypot(x, y) for x, y in coords[:-1]]
                        if radii:
                            candidate_core_r = float(max(radii))
                            if local_core_outer_r is None or candidate_core_r > local_core_outer_r:
                                local_core_outer_r = candidate_core_r
                    continue
                if centroid_r < float(pcd_radius) - 6.0 or centroid_r > float(pcd_radius) + 6.0:
                    continue

                coords = list(poly.exterior.coords)
                if len(coords) < 4:
                    continue
                radii = [math.hypot(x, y) for x, y in coords[:-1]]
                if not radii:
                    continue

                angle_window = continuous_angle_window([
                    math.degrees(math.atan2(y, x)) % 360.0
                    for x, y in coords[:-1]
                ])
                if angle_window is None:
                    continue

                boss_entries.append({
                    "angle": math.degrees(math.atan2(centroid.y, centroid.x)) % 360.0,
                    "start_angle": float(angle_window[0]),
                    "end_angle": float(angle_window[1]),
                    "span": float(angle_window[2]),
                    "inner_r": float(min(radii)),
                    "outer_r": float(max(radii)),
                    "area": float(poly.area)
                })

            if len(boss_entries) < int(hole_count) or local_core_outer_r is None:
                continue

            boss_entries = sorted(boss_entries, key=lambda item: (-item["area"], item["inner_r"]))
            selected = boss_entries[:int(hole_count)]
            selected.sort(key=lambda item: item["angle"])
            inner_edge_r = float(np.median(np.asarray([item["inner_r"] for item in selected], dtype=float)))
            groove_inner_r = max(float(local_core_outer_r) + 0.55, float(bore_radius) + 1.2)
            groove_outer_r = min(
                float(inner_edge_r) - 0.55,
                float(pcd_radius) - max(0.8, float(hole_radius) * 0.55)
            )
            if groove_outer_r <= groove_inner_r + 1.8:
                continue

            groove_regions = []
            angle_gaps = []
            total_area = 0.0
            for idx, entry in enumerate(selected):
                next_entry = selected[(idx + 1) % len(selected)]
                next_start = float(next_entry["start_angle"])
                while next_start <= float(entry["end_angle"]):
                    next_start += 360.0
                free_gap = next_start - float(entry["end_angle"])
                angle_gaps.append(free_gap)
                if free_gap < 8.0:
                    continue

                margin = max(1.2, min(2.8, free_gap * 0.16))
                groove_start = float(entry["end_angle"]) + margin
                groove_end = next_start - margin
                if groove_end <= groove_start + 3.2:
                    continue

                groove_center = (groove_start + groove_end) * 0.5
                free_half_span = max(1.6, (groove_end - groove_start) * 0.5)
                inner_half_span = max(4.0, min(6.4, free_half_span * 0.26))
                outer_half_span = max(inner_half_span + 3.0, min(14.0, free_half_span * 0.58))
                sector_outer = normalize_geom(sector_polygon(groove_start, groove_end, groove_outer_r))
                sector_geom = normalize_geom(
                    sector_outer.difference(circle_polygon(groove_inner_r, 180))
                )
                tapered_geom = normalize_geom(
                    build_tapered_bridge_polygon(
                        groove_center,
                        groove_inner_r,
                        groove_outer_r,
                        inner_half_span,
                        outer_half_span
                    )
                )
                groove_limit = normalize_geom(
                    build_ring_sector(
                        groove_start,
                        groove_end,
                        max(0.0, groove_inner_r - 0.45),
                        groove_outer_r + 0.9
                    )
                )
                groove_geom = normalize_geom(
                    tapered_geom.intersection(groove_limit)
                )
                groove_poly = largest_polygon(groove_geom, min_area=35.0)
                if groove_poly is None:
                    groove_poly = largest_polygon(sector_geom, min_area=35.0)
                if groove_poly is None:
                    continue
                groove_coords = canonicalize_loop(list(groove_poly.exterior.coords))
                if len(groove_coords) < 4:
                    continue
                groove_regions.append({
                    "points": groove_coords,
                    "angle": round(float(groove_center % 360.0), 3),
                    "start_angle": round(float(groove_start % 360.0), 3),
                    "end_angle": round(float(groove_end % 360.0), 3)
                })
                total_area += float(groove_poly.area)

            if len(groove_regions) < max(3, int(hole_count) - 1):
                continue

            valid_candidates.append({
                "z": float(sample_z),
                "entries": selected,
                "groove_regions": groove_regions,
                "inner_r": float(groove_inner_r),
                "outer_r": float(groove_outer_r),
                "total_area": float(total_area),
                "gap_std": float(np.std(np.asarray(angle_gaps, dtype=float))) if angle_gaps else 999.0
            })

        if not valid_candidates:
            return [], {}

        best_candidate = max(
            valid_candidates,
            key=lambda item: (
                item["total_area"],
                -item["gap_std"],
                -abs(item["z"] - (float(rear_face_z) + 2.6))
            )
        )
        opening_candidate = min(valid_candidates, key=lambda item: item["z"])
        depth_candidates = [
            item for item in valid_candidates
            if float(item["total_area"]) >= float(best_candidate["total_area"]) * 0.32
        ]
        if not depth_candidates:
            depth_candidates = list(valid_candidates)
        deepest_candidate = max(
            depth_candidates,
            key=lambda item: (
                item["z"],
                item["total_area"],
                -item["gap_std"]
            )
        )
        best_regions = sorted(best_candidate["groove_regions"], key=lambda item: float(item.get("angle", 0.0)))
        opening_regions = sorted(opening_candidate["groove_regions"], key=lambda item: float(item.get("angle", 0.0)))
        deepest_regions = sorted(deepest_candidate["groove_regions"], key=lambda item: float(item.get("angle", 0.0)))

        opening_line_region_map = {}
        opening_line_z = None
        opening_line_candidates = []
        line_search_start_z = rear_face_z + 0.08
        line_search_top_z = min(float(search_top_z), rear_face_z + 2.4)
        if line_search_top_z > line_search_start_z + 0.15:
            for sample_z in np.linspace(line_search_start_z, line_search_top_z, 12):
                line_entries = collect_opening_line_entries(sample_z)
                if not line_entries:
                    continue
                matched = {}
                used_entry_indices = set()
                for region_idx, base_region in enumerate(best_regions):
                    groove_center = float(base_region.get("angle", 0.0))
                    groove_start = float(base_region.get("start_angle", groove_center - 18.0))
                    groove_end = float(base_region.get("end_angle", groove_center + 18.0))
                    best_line_idx = None
                    best_score = None
                    for entry_idx, entry in enumerate(line_entries):
                        if entry_idx in used_entry_indices:
                            continue
                        centroid_angle = float(entry.get("centroid_angle", groove_center))
                        if not angle_in_window(centroid_angle, groove_start, groove_end, pad_deg=8.0):
                            continue
                        score = (
                            float(entry.get("length", 0.0))
                            + max(0.0, float(entry.get("max_r", 0.0)) - float(entry.get("min_r", 0.0)))
                            - (angle_distance_deg(centroid_angle, groove_center) * 1.8)
                        )
                        if best_score is None or score > best_score:
                            best_score = score
                            best_line_idx = entry_idx
                    if best_line_idx is not None:
                        used_entry_indices.add(best_line_idx)
                        matched[region_idx] = line_entries[best_line_idx]
                if len(matched) >= max(3, int(hole_count) - 2):
                    opening_line_candidates.append({
                        "z": float(sample_z),
                        "matched": matched,
                        "coverage": int(len(matched)),
                        "total_length": float(sum(item["length"] for item in matched.values()))
                    })

        if opening_line_candidates:
            best_line_candidate = sorted(
                opening_line_candidates,
                key=lambda item: (-item["coverage"], item["z"], -item["total_length"])
            )[0]
            opening_line_z = float(best_line_candidate["z"])
            print(
                f"[*] Rear groove opening line selected at Z={opening_line_z:.2f} "
                f"(rear face {rear_face_z:.2f}, coverage {best_line_candidate['coverage']})"
            )
            opening_line_region_map, _ = build_line_region_map(
                best_line_candidate["matched"],
                best_regions,
                deepest_regions,
                prefer_raw_outer=True
            )

        deep_line_region_map = {}
        deep_line_z = None
        deep_line_candidates = []
        deep_line_search_start_z = max(
            (opening_line_z if opening_line_z is not None else float(opening_candidate["z"])) + 0.8,
            float(deepest_candidate["z"]) - 2.6
        )
        deep_line_search_top_z = min(float(search_top_z), float(deepest_candidate["z"]) + 0.5)
        if deep_line_search_top_z > deep_line_search_start_z + 0.25:
            for sample_z in np.linspace(deep_line_search_start_z, deep_line_search_top_z, 10):
                line_entries = collect_opening_line_entries(sample_z, allow_closed=True)
                if not line_entries:
                    continue
                matched = match_line_entries_to_regions(line_entries, best_regions, pad_deg=6.5)
                if len(matched) >= max(3, int(hole_count) - 2):
                    deep_line_candidates.append({
                        "z": float(sample_z),
                        "matched": matched,
                        "coverage": int(len(matched)),
                        "total_length": float(sum(item["length"] for item in matched.values()))
                    })

        if deep_line_candidates:
            best_deep_line_candidate = sorted(
                deep_line_candidates,
                key=lambda item: (-item["coverage"], -item["z"], -item["total_length"])
            )[0]
            deep_line_z = float(best_deep_line_candidate["z"])
            print(
                f"[*] Rear groove deep line selected at Z={deep_line_z:.2f} "
                f"(coverage {best_deep_line_candidate['coverage']})"
            )
            deep_line_region_map, _ = build_line_region_map(
                best_deep_line_candidate["matched"],
                best_regions,
                deepest_regions,
                prefer_raw_outer=False
            )

        groove_regions = []
        opening_radii = []
        for idx, base_region in enumerate(best_regions):
            opening_region = opening_regions[idx] if idx < len(opening_regions) else base_region
            deepest_region = deepest_regions[idx] if idx < len(deepest_regions) else base_region
            opening_points = opening_line_region_map.get(
                idx,
                opening_region.get("points", base_region.get("points", []))
            )
            if opening_points:
                opening_radii.extend([math.hypot(x, y) for x, y in opening_points[:-1]])
            groove_regions.append({
                "points": opening_points,
                "opening_points": opening_points,
                "deep_points": deep_line_region_map.get(
                    idx,
                    deepest_region.get("points", base_region.get("points", []))
                ),
                "angle": round(float(base_region.get("angle", 0.0)), 3),
                "opening_z": round(float(opening_line_z if opening_line_z is not None else opening_candidate["z"]), 2),
                "deep_z": round(float(deep_line_z if deep_line_z is not None else deepest_candidate["z"]), 2)
            })

        return groove_regions, {
            "sample_z": round(float(opening_line_z if opening_line_z is not None else opening_candidate["z"]), 2),
            "floor_z": round(float(rear_face_z), 2),
            "top_z": round(float(deepest_candidate["z"]), 2),
            "inner_r": round(float(min(opening_radii) if opening_radii else opening_candidate["inner_r"]), 2),
            "outer_r": round(float(max(opening_radii) if opening_radii else opening_candidate["outer_r"]), 2),
            "count": int(len(groove_regions))
        }
    except Exception as exc:
        print(f"[!] Hub bottom groove extraction failed: {exc}")
        return [], {}

def extract_axisymmetric_face_profile(
    mesh,
    min_radius,
    max_radius,
    base_z,
    angle_count=24,
    radial_bin_count=180,
    hole_count=0,
    phase_angle_deg=0.0
):
    """Estimate the axisymmetric front-face profile by aggregating many radial sections."""
    if max_radius <= min_radius + 1.0:
        return [], {}

    angle_samples, guard_stats = generate_guarded_section_angles(
        angle_count,
        hole_count=hole_count,
        phase_angle_deg=phase_angle_deg,
        exclusion_half_width_deg=7.0
    )
    radial_bins = np.linspace(float(min_radius), float(max_radius), int(radial_bin_count) + 1)
    radial_centers = (radial_bins[:-1] + radial_bins[1:]) * 0.5
    radial_samples = [[] for _ in range(len(radial_centers))]
    valid_sections = 0

    for angle_deg in angle_samples:
        theta = math.radians(float(angle_deg))
        plane_normal = [-math.sin(theta), math.cos(theta), 0.0]
        radial_slice = mesh.section(plane_origin=[0, 0, 0], plane_normal=plane_normal)
        if not radial_slice:
            continue

        section_points = []
        for entity in radial_slice.entities:
            pts = radial_slice.vertices[entity.points]
            section_points.extend(pts)
        if len(section_points) < 20:
            continue

        section_points = np.asarray(section_points, dtype=float)
        rs = np.hypot(section_points[:, 0], section_points[:, 1])
        zs = section_points[:, 2]
        mask = (
            (rs >= (float(min_radius) - 0.5)) &
            (rs <= (float(max_radius) + 0.5)) &
            (zs >= (float(base_z) - 2.0))
        )
        if np.count_nonzero(mask) < 20:
            continue

        rs = rs[mask]
        zs = zs[mask]
        digitized = np.digitize(rs, radial_bins)
        local_hits = 0

        for bin_idx in range(1, len(radial_bins)):
            bin_zs = zs[digitized == bin_idx]
            if len(bin_zs) < 2:
                continue
            top_z = float(np.percentile(bin_zs, 97))
            radial_samples[bin_idx - 1].append(top_z)
            local_hits += 1

        if local_hits >= max(8, int(radial_bin_count * 0.18)):
            valid_sections += 1

    min_hits = max(4, int(angle_count * 0.2))
    profile = []
    spreads = []
    for radius_val, z_samples in zip(radial_centers, radial_samples):
        if len(z_samples) < min_hits:
            continue
        z_arr = np.asarray(z_samples, dtype=float)
        spread = float(np.ptp(z_arr))
        percentile = 38.0 if spread < 4.0 else 30.0
        z_val = float(np.percentile(z_arr, percentile))
        spreads.append(spread)
        profile.append([float(radius_val), z_val])

    if len(profile) >= 9:
        curve_arr = np.asarray(profile, dtype=float)
        z_vals = curve_arr[:, 1]
        window = min(15, len(z_vals) if len(z_vals) % 2 == 1 else len(z_vals) - 1)
        if window >= 5:
            z_vals = savgol_filter(z_vals, window_length=window, polyorder=2, mode="interp")
        profile = [
            [round(float(r), 3), round(float(z), 3)]
            for r, z in zip(curve_arr[:, 0], z_vals)
        ]
    else:
        profile = [[round(float(r), 3), round(float(z), 3)] for r, z in profile]

    stats = {
        "valid_sections": int(valid_sections),
        "radial_bins_with_hits": int(len(profile)),
        "median_spread": round(float(np.median(np.asarray(spreads, dtype=float))), 3) if spreads else 0.0,
        "guarded": bool(guard_stats.get("guarded", False)),
        "excluded_angles": guard_stats.get("excluded_angles", []),
        "preview_angle": guard_stats.get("preview_angle", 0.0),
        "exclusion_half_width_deg": guard_stats.get("exclusion_half_width_deg", 0.0)
    }
    return profile, stats

def shift_curve_z(points, shift_val):
    """Shift 2D [radius, z] preview curves into model-space."""
    shifted = []
    for point in points or []:
        if len(point) < 2:
            continue
        shifted.append([round(float(point[0]), 3), round(float(point[1]) + float(shift_val), 3)])
    return shifted

def shift_section_region_z(region, shift_val):
    """Shift a section-region payload into model-space."""
    if not isinstance(region, dict):
        return {}
    shifted = {"outer": shift_curve_z(region.get("outer", []), shift_val)}
    holes = []
    for hole in region.get("holes", []):
        holes.append(shift_curve_z(hole, shift_val))
    shifted["holes"] = holes
    return shifted

def shift_hub_bottom_groove_regions_z(groove_regions, shift_val):
    """Shift rear hub-groove metadata into model-space."""
    shifted_regions = []
    for region in groove_regions or []:
        if not isinstance(region, dict):
            shifted_regions.append(region)
            continue
        shifted_region = dict(region)
        for z_key in ("opening_z", "deep_z"):
            if shifted_region.get(z_key) is not None:
                shifted_region[z_key] = round(float(shifted_region[z_key]) + float(shift_val), 2)
        shifted_regions.append(shifted_region)
    return shifted_regions

def extract_features_from_stl(stl_path, return_preview=False, lightweight_preview=False):
    """
    Extract the geometric features needed for downstream CAD reconstruction.
    """
    print(f"[*] Module A: ?????? STL ??? {stl_path}...")
    
    if not os.path.exists(stl_path):
        raise FileNotFoundError(f"STL file not found: {stl_path}")
        
    # ??????
    mesh = trimesh.load_mesh(stl_path)
    if isinstance(mesh, trimesh.Scene):
        if len(mesh.geometry) == 0:
            raise ValueError("Loaded STL is empty.")
        mesh = trimesh.util.concatenate(tuple(mesh.geometry.values()))

    # -------------------------------------------------------------------------
    # ?? 1: ??????(Pose Alignment)
    # -------------------------------------------------------------------------
    print("[*] ???? ????????...")
    try:
        # 1. ???
        mesh.apply_translation(-mesh.centroid)
        # 2. ????????
        mesh.apply_transform(mesh.principal_inertia_transform)
        # 3. ??????? (????? ?????Z ??
        extents = mesh.extents
        axis_idx = np.argmin(extents) # 0=X, 1=Y, 2=Z
        
        if axis_idx != 2:
            print(f"[*] ???????????: {['X','Y','Z'][axis_idx]} -> Z...")
            mat = np.eye(4)
            if axis_idx == 0: 
                theta = -np.pi / 2
                c, s = np.cos(theta), np.sin(theta)
                mat[:3, :3] = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
            elif axis_idx == 1: 
                theta = np.pi / 2
                c, s = np.cos(theta), np.sin(theta)
                mat[:3, :3] = np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
            mesh.apply_transform(mat)
    except Exception as e:
        print(f"[!] Axis alignment failed: {e}. Using original orientation.")

    # ??????????????
    extents = mesh.extents
    sorted_extents = sorted(extents)
    rim_width = float(sorted_extents[0])     # ????????
    max_diameter = float(sorted_extents[2])  # ??????????
    rim_max_radius = max_diameter / 2.0
    
    # -------------------------------------------------------------------------
    # ?? 2: ??????? (Rim Profile Extraction)
    # -------------------------------------------------------------------------
    print("[*] ????? XZ ?????????????????..")
    
    section = mesh.section(plane_origin=[0,0,0], plane_normal=[0,1,0]) # ??XZ ???
    rim_profile_points = []
    rim_thickness_values = []
    rim_profile_z_shift = 0.0
    orthographic_section_points_raw = []
    orthographic_face_profile_raw = []
    rotary_face_profile_raw = []
    rotary_profile_stats = {}
    preview_section_angle_deg = 0.0
    preview_guard_stats = {}
    guarded_section_region_raw = {}
    spokeless_section_points_raw = []
    spokeless_upper_profile_raw = []
    spokeless_lower_profile_raw = []
    spokeless_guarded_section_region_raw = {}
    spokeless_guarded_section_regions_raw = []
    spokeless_section_angle_deg = None
    spokeless_profile_regions = []
    spokeless_baseline_regions = []
    spokeless_nospoke_regions = []
    prefer_fragmented_spokeless_base = False
    
    if section:
        # ??????
        raw_pts = []
        for entity in section.entities:
            pts = section.vertices[entity.points]
            for p in pts:
                if p[0] > 0: # ???????(X>0)
                    raw_pts.append((p[0], p[2]))

        if raw_pts:
            orthographic_section_points_raw = downsample_curve(raw_pts, max_points=5000)
            orthographic_face_profile_raw = sample_radial_upper_envelope(
                raw_pts,
                min_radius=0.0,
                max_radius=rim_max_radius,
                bin_count=220,
                percentile=98.0
            )
            raw_pts = np.array(raw_pts)
            # ??????????(??????
            current_max_radius = np.max(raw_pts[:, 0])
            hub_threshold = current_max_radius * 0.25
            mask = raw_pts[:, 0] > (hub_threshold + 5.0)
            filtered_pts = raw_pts[mask]
            
            if len(filtered_pts) > 0:
                # Z??????????? (Envelope)
                min_z, max_z = np.min(filtered_pts[:, 1]), np.max(filtered_pts[:, 1])
                z_bins = np.linspace(min_z, max_z, 201)
                bin_indices = np.digitize(filtered_pts[:, 1], z_bins)
                
                envelope_pts = []
                for i in range(1, len(z_bins)):
                    mask = bin_indices == i
                    if not np.any(mask): continue
                    
                    bin_pts = filtered_pts[mask]
                    outer_x = float(np.percentile(bin_pts[:, 0], 97.0))
                    envelope_pts.append([outer_x, float(np.median(bin_pts[:, 1]))])
                    
                    # ??????? Max X - Min X
                    thickness = np.max(bin_pts[:, 0]) - np.min(bin_pts[:, 0])
                    if 2.0 < thickness < 40.0: # ????????
                        rim_thickness_values.append(thickness)
                
                # ??Z ???
                envelope_pts = sorted(envelope_pts, key=lambda p: p[1])
                
                # Z??????????(?????
                mono_pts = []
                last_z = -float('inf')
                for p in envelope_pts:
                    if p[1] > last_z + 0.5: # ????Z ???
                        mono_pts.append(p)
                        last_z = p[1]
                
                # ?????
                clean_pts = []
                if mono_pts:
                    clean_pts.append(mono_pts[0])
                    for i in range(1, len(mono_pts)):
                        prev = clean_pts[-1]
                        curr = mono_pts[i]
                        if np.hypot(float(curr[0]) - float(prev[0]), float(curr[1]) - float(prev[1])) > 1.0: # ????????
                            clean_pts.append(curr)
                
                envelope_pts = clean_pts
                
                # Savitzky-Golay ???
                if len(envelope_pts) > 10:
                    try:
                        pts_arr = np.array(envelope_pts)
                        x_smooth = savgol_filter(pts_arr[:, 0], window_length=11, polyorder=3)
                        envelope_pts = list(zip(x_smooth, pts_arr[:, 1]))
                        print("[*] Applied Savitzky-Golay smoothing to rim envelope")
                    except: pass

                # Z?????(Centering)
                z_coords = [p[1] for p in envelope_pts]
                if z_coords:
                    z_center = (min(z_coords) + max(z_coords)) / 2.0
                    rim_profile_z_shift = float(-z_center)
                    envelope_pts = [(p[0], p[1] - z_center) for p in envelope_pts]
                    print(f"[*] Recentered rim profile in Z by {-z_center:.2f} mm")

                rim_profile_points = regularize_rim_profile_points(
                    envelope_pts,
                    target_min=30,
                    target_max=44
                )
                if rim_profile_points:
                    print(f"[*] Regularized rim profile generated: {len(rim_profile_points)} points")
                else:
                    envelope_pts = optimize_profile_points(envelope_pts, target_min=30, target_max=44)
                    rim_profile_points = [[round(float(p[0]), 3), round(float(p[1]), 3)] for p in envelope_pts]

    # ??????????
    rim_thickness = float(np.median(rim_thickness_values)) if rim_thickness_values else 5.0
    print(f"[*] ?????????? {rim_thickness:.2f} mm")

    # -------------------------------------------------------------------------
    # ?? 3: ?????? (Visual Interceptor)
    # -------------------------------------------------------------------------
    if rim_profile_points:
        print("[*] Legacy rim-only preview suppressed. Unified perception preview will be shown after full extraction.")

    # -------------------------------------------------------------------------
    # ?? 4: ??????????(Parametric Spoke Only)
    # -------------------------------------------------------------------------
    print("[*] ?????????????(Parametric Mode)...")
    
    # ?????????????????????? 
    spoke_width = max(rim_max_radius * 0.05, min(30.0, rim_max_radius * 0.15)) 
    spoke_thickness = max(rim_max_radius * 0.05, min(20.0, rim_max_radius * 0.12)) 

    print(f"[*] ?????????? Width={spoke_width:.2f}, Thickness={spoke_thickness:.2f}")

    # -------------------------------------------------------------------------
    # ?? 5: ????CD?????? (Refined Hub & PCD from Mounting Pad)
    # -------------------------------------------------------------------------
    print("[*] ????????????? (Mounting Pad Analysis)...")
    
    # Default Fallbacks
    hub_thickness = 30.0
    hub_z_offset = -rim_width / 2.0 
    hub_radius = rim_max_radius * 0.25
    bore_radius = 30.0
    pcd_radius = 57.15
    hole_radius = 7.5
    hole_count = 5
    derived_params = {}
    try: 
        # 1. ???? Z ?????(???????????)
        scan_radius = 80.0
        verts = mesh.vertices
        # ????XY ???????????< scan_radius ???
        mask_hub = np.linalg.norm(verts[:, :2], axis=1) < scan_radius
        hub_verts = verts[mask_hub]
        
        if len(hub_verts) > 0:
            z_min_hub = np.min(hub_verts[:, 2])
            z_max_hub = np.max(hub_verts[:, 2])
            hub_thickness = float(z_max_hub - z_min_hub)
            hub_z_offset = float(z_min_hub)
            print(f"[*] ???????: Thickness={hub_thickness:.2f}, Z_Offset={hub_z_offset:.2f}")
            
        # 2. ????????????????????? 2mm ?????????????????
        pad_z = hub_z_offset + 2.0
        slice_3d = mesh.section(plane_origin=[0, 0, pad_z], plane_normal=[0, 0, 1])
        
        if slice_3d:
            lines_2d = []
            for entity in slice_3d.entities:
                line_points = slice_3d.vertices[entity.points]
                pts_2d = line_points[:, :2]
                lines_2d.append(pts_2d)
                
            if lines_2d:
                multiline = MultiLineString([l for l in lines_2d])
                merged = linemerge(multiline)
                polygons = list(polygonize(merged))
                
                if polygons:
                    # ????????? (0,0) ?????????????????????(Mounting Pad)?????
                    pad_poly = max(polygons, key=lambda p: p.area)
                    
                    # 3. ??????????? Hub Radius?????????????????????????
                    ext_coords = np.array(pad_poly.exterior.coords)
                    dists = np.sqrt(np.sum(ext_coords**2, axis=1))
                    max_dist = np.max(dists)
                    
                    # ??????????????????????????????????????
                    hub_radius = round(max_dist + 5.0, 2)
                    print(f"[*] ?????: ?????????????? -> {hub_radius} mm")
                    
                    # 4. ??????????? PCD ??Center Bore?????????????????
                    holes = []
                    for interior in pad_poly.interiors:
                        poly_hole = Polygon(interior)
                        if poly_hole.area > 20.0:
                            centroid = poly_hole.centroid
                            dist_to_center = np.hypot(centroid.x, centroid.y)
                            r = np.sqrt(poly_hole.area / np.pi)
                            # ?? ??????x ??y ????????????
                            holes.append({"dist": dist_to_center, "r": r, "x": centroid.x, "y": centroid.y})
                    
                    if holes:
                        # ?????????????CD??????
                        center_holes = [h for h in holes if h["dist"] < 15.0]
                        if center_holes:
                            bore_hole = max(center_holes, key=lambda h: h["r"])
                            bore_radius = round(bore_hole["r"], 2)
                            print(f"[*] ?????: ?????????????-> {bore_radius} mm")
                        
                        pcd_holes = [h for h in holes if h["dist"] > 20.0 and h["dist"] < hub_radius * 0.9]
                        if pcd_holes:
                            avg_pcd = sum([h["dist"] for h in pcd_holes]) / len(pcd_holes)
                            avg_r = sum([h["r"] for h in pcd_holes]) / len(pcd_holes)
                            pcd_radius = round(avg_pcd, 2)
                            hole_radius = round(avg_r, 2)
                            hole_count = len(pcd_holes)
                            
                            # ?? ?????????????PCD ???????????
                            import math
                            first_hole = pcd_holes[0]
                            phase_rad = math.atan2(first_hole["y"], first_hole["x"])
                            pcd_phase_angle = round(math.degrees(phase_rad), 2)
                            # ?????global_params
                            derived_params["pcd_phase_angle"] = pcd_phase_angle
                            
                            print(
                                f"[*] Refined PCD detection: {hole_count} holes at radius "
                                f"{pcd_radius} mm, phase {pcd_phase_angle} deg"
                            )

    except Exception as e:
        print(f"[!] ?????????????? {e}")

    measured_hub_radius = float(hub_radius)
    inferred_hub_radius = max(
        bore_radius + 6.0,
        pcd_radius + hole_radius + 2.0,
        pcd_radius * 1.18 if hole_count > 0 else bore_radius + 10.0
    )
    if measured_hub_radius > inferred_hub_radius * 1.6 or measured_hub_radius < bore_radius + 2.0:
        hub_radius = round(inferred_hub_radius, 2)
        print(
            f"[*] Hub radius sanitized: {measured_hub_radius:.2f} -> {hub_radius:.2f} mm "
            f"(PCD-guided safe radius)"
        )
    else:
        hub_radius = round(measured_hub_radius, 2)

    try:
        preview_angles, preview_guard_stats = generate_guarded_section_angles(
            1,
            hole_count=hole_count,
            phase_angle_deg=derived_params.get("pcd_phase_angle", 0.0),
            exclusion_half_width_deg=8.0
        )
        preview_section_angle_deg = float(preview_angles[0]) if preview_angles else 0.0
        rotated_preview_points = extract_rotated_section_points(mesh, preview_section_angle_deg)
        guarded_section_region_raw = extract_rotated_section_region(mesh, preview_section_angle_deg, max_radius=rim_max_radius)
        if rotated_preview_points:
            orthographic_section_points_raw = downsample_curve(rotated_preview_points, max_points=5000)
            orthographic_face_profile_raw = sample_radial_upper_envelope(
                rotated_preview_points,
                min_radius=0.0,
                max_radius=rim_max_radius,
                bin_count=220,
                percentile=98.0
            )
            if preview_guard_stats.get("guarded", False):
                print(
                    f"[*] Preview section rotated to {preview_section_angle_deg:.2f} deg "
                    f"to avoid PCD-hole angles {preview_guard_stats.get('excluded_angles', [])}"
                )
    except Exception as preview_section_exc:
        print(f"[!] Guarded preview section extraction failed: {preview_section_exc}")

    # -------------------------------------------------------------------------
    # ?? 6: ?????????????(Radar Scanning for Voids - Scale Invariant)
    # -------------------------------------------------------------------------
    print("[*] ????????????????? (Scale-Invariant Radar Scan)...")
    spoke_voids = []
    best_boundary_points = []
    best_main_poly = None
    spoke_regions = []
    spoke_sections = []
    spoke_tip_sections = []
    lug_boss_regions = []
    spoke_root_regions = []
    center_core_region = {"points": []}
    hub_bottom_groove_regions = []
    window_inner_reference_radii = []
    
    try:
        # 1. ????????
        z_start = hub_z_offset + 10.0
        z_end = 0.0 
        if z_end < z_start: z_end = z_start + 40.0
        z_levels = np.linspace(z_start, z_end, 8)
        
        best_interiors = []
        best_z = 0.0
        
        # 2. ??????????
        for z in z_levels:
            slice_3d = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
            if not slice_3d: continue
            
            lines_2d = []
            for entity in slice_3d.entities:
                line_points = slice_3d.vertices[entity.points]
                pts_2d = line_points[:, :2]
                lines_2d.append(pts_2d)
            
            if not lines_2d: continue

            multiline = MultiLineString([l for l in lines_2d])
            merged = linemerge(multiline)
            polygons = list(polygonize(merged))
            
            if not polygons: continue
            
            main_poly = max(polygons, key=lambda p: p.area)
            if not main_poly.interiors: continue
            
            # --- 1. ???????????(Scale-invariant Filtering) ---
            # ??????????????
            interiors_list = list(main_poly.interiors)
            areas = [Polygon(i).area for i in interiors_list]
            if not areas: continue
            
            max_area = max(areas)
            
            # ??????????????????????????????????????????????
            # ????????????????20% ??????????? (PCD?????????????
            dynamic_threshold = max_area * 0.20
            
            valid_interiors = []
            for i, area in zip(interiors_list, areas):
                # ???????????????????????????(50mm^2)
                if area >= dynamic_threshold and area > 50.0:
                    # ???????????????????
                    poly = Polygon(i)
                    dist = poly.centroid.distance(Point(0,0))
                    coords = np.array(i.coords)
                    radii = np.hypot(coords[:, 0], coords[:, 1])
                    max_r = np.max(radii)
                    if (
                        dist < rim_max_radius * 0.95
                        and dist > bore_radius * 1.5
                        and max_r > rim_max_radius * 0.75
                    ):
                        valid_interiors.append(i)
            
            # ??????????????????
            if len(valid_interiors) > len(best_interiors):
                best_interiors = valid_interiors
                best_boundary_points = [[round(float(x), 3), round(float(y), 3)] for x, y in np.array(main_poly.exterior.coords)]
                best_main_poly = Polygon(
                    main_poly.exterior.coords,
                    [list(interior.coords) for interior in main_poly.interiors]
                )
                best_z = z
                print(f"[*] ?????: ??Z={z:.1f} ??????????????? {len(best_interiors)} ????????")
            elif len(valid_interiors) == len(best_interiors) and len(valid_interiors) > 0:
                # ??????????????????
                area_curr = sum([Polygon(i).area for i in valid_interiors])
                area_best = sum([Polygon(i).area for i in best_interiors])
                if area_curr > area_best:
                    best_interiors = valid_interiors
                    best_boundary_points = [[round(float(x), 3), round(float(y), 3)] for x, y in np.array(main_poly.exterior.coords)]
                    best_main_poly = Polygon(
                        main_poly.exterior.coords,
                        [list(interior.coords) for interior in main_poly.interiors]
                    )
                    best_z = z
                    print(f"[*] ?????: ??Z={z:.1f} ??????????????? (Area: {area_curr:.0f})")

        # 4. ????????????????????
        if best_interiors:
            print(f"[*] ?????????? Z={best_z:.1f}, ????? {len(best_interiors)}")
            
            for interior in best_interiors:
                coords = np.array(interior.coords)
                
                try:
                    # ????????
                    tck, u = splprep([coords[:, 0], coords[:, 1]], s=3.0, per=True)
                    u_new = np.linspace(0, 1, 60)
                    smooth_x, smooth_y = splev(u_new, tck)
                    pts_list = [[round(float(x), 3), round(float(y), 3)] for x, y in zip(smooth_x, smooth_y)]
                    
                    if pts_list[0] != pts_list[-1]: pts_list.append(pts_list[0])
                    spoke_voids.append({"points": pts_list})
                    
                except Exception as e:
                    # Fallback
                    step = max(1, len(coords) // 40)
                    sampled = coords[::step]
                    pts_list = [[round(float(x), 3), round(float(y), 3)] for x, y in sampled]
                    if pts_list[0] != pts_list[-1]: pts_list.append(pts_list[0])
                    spoke_voids.append({"points": pts_list})
        
        print(f"[*] ????????????????????: {len(spoke_voids)}")
        if best_boundary_points and best_boundary_points[0] != best_boundary_points[-1]:
            best_boundary_points.append(best_boundary_points[0])

        if best_main_poly is not None and len(spoke_voids) >= 3:
            try:
                rim_inner_candidates = [p[0] - rim_thickness for p in rim_profile_points if p[0] > rim_thickness]
                rim_inner_limit_r = min(rim_inner_candidates) if rim_inner_candidates else (rim_max_radius - rim_thickness)
                spoke_outer_limit_r = max(hub_radius + 8.0, min(rim_inner_limit_r + 0.75, rim_max_radius - 1.0))
                spoke_inner_limit_r = max(bore_radius + 2.0, hub_radius - 1.0)
                region_specs = []

                face_geom = normalize_geom(best_main_poly)
                if face_geom.is_empty:
                    raise ValueError("best_main_poly is empty after normalization")

                face_band = normalize_geom(
                    face_geom
                    .intersection(circle_polygon(spoke_outer_limit_r, 180))
                    .difference(circle_polygon(spoke_inner_limit_r, 120))
                )
                if face_band.is_empty:
                    raise ValueError("face band collapsed during spoke region extraction")

                void_angle_pairs = []
                for spoke_void in spoke_voids:
                    pts = spoke_void.get("points", [])
                    if len(pts) < 4:
                        continue
                    void_poly = normalize_geom(Polygon(pts))
                    if void_poly.is_empty or void_poly.area < 50.0:
                        continue
                    centroid = void_poly.centroid
                    angle = math.degrees(math.atan2(centroid.y, centroid.x)) % 360.0
                    void_angle_pairs.append((angle, void_poly))

                void_angle_pairs.sort(key=lambda item: item[0])
                for idx, (start_angle, _) in enumerate(void_angle_pairs):
                    end_angle = void_angle_pairs[(idx + 1) % len(void_angle_pairs)][0]
                    wedge = normalize_geom(sector_polygon(start_angle, end_angle, spoke_outer_limit_r + 10.0))
                    region_geom = normalize_geom(face_band.intersection(wedge))

                    candidates = []
                    for poly in iter_polygons(region_geom):
                        if poly.is_empty or poly.area < 180.0:
                            continue
                        coords = list(poly.exterior.coords)
                        radii = [math.hypot(x, y) for x, y in coords[:-1]]
                        if not radii:
                            continue
                        if min(radii) > spoke_inner_limit_r + 6.0:
                            continue
                        if max(radii) < spoke_outer_limit_r - 6.0:
                            continue
                        candidates.append(poly)

                    if not candidates:
                        continue

                    spoke_poly = max(candidates, key=lambda poly: poly.area)
                    spoke_poly = normalize_geom(spoke_poly.simplify(0.8, preserve_topology=True))
                    poly_coords = list(spoke_poly.exterior.coords)
                    coords = [[round(float(x), 3), round(float(y), 3)] for x, y in poly_coords]
                    if coords and coords[0] != coords[-1]:
                        coords.append(coords[0])
                    if len(coords) >= 4:
                        spoke_regions.append({"points": coords})
                        poly_radii = [math.hypot(x, y) for x, y in poly_coords[:-1]]
                        max_r = max(poly_radii)
                        min_r = min(poly_radii)
                        outer_floor_r = max_r - min(14.0, max(6.0, (max_r - min_r) * 0.22))
                        outer_angles = [
                            math.degrees(math.atan2(y, x)) % 360.0
                            for x, y in poly_coords[:-1]
                            if math.hypot(x, y) >= outer_floor_r
                        ]
                        if len(outer_angles) < 2:
                            outer_angles = [
                                math.degrees(math.atan2(y, x)) % 360.0
                                for x, y in poly_coords[:-1]
                            ]
                        angle_window = continuous_angle_window(outer_angles)
                        if angle_window is not None:
                            start_angle, end_angle, span_angle = angle_window
                            region_specs.append({
                                "start_angle": start_angle,
                                "end_angle": end_angle,
                                "span_angle": span_angle,
                                "base_outer_r": max_r,
                                "base_inner_r": min_r
                            })

                print(
                    f"[*] Structural spoke regions extracted: {len(spoke_regions)} "
                    f"(inner={spoke_inner_limit_r:.2f}, outer={spoke_outer_limit_r:.2f})"
                )

                if region_specs:
                    section_groups = [[] for _ in range(len(region_specs))]
                    tip_section_groups = [[] for _ in range(len(region_specs))]
                    region_descs = [
                        describe_planar_region(region, min_area=40.0)
                        for region in spoke_regions
                    ]
                    dense_station_counts = []
                    spoke_section_lower_z = max(
                        float(hub_z_offset) - 2.5,
                        float(best_z) - max(18.0, float(hub_thickness) * 1.05)
                    )
                    spoke_section_upper_z = float(best_z) + max(
                        2.5,
                        min(6.0, float(hub_thickness) * 0.08)
                    )
                    print(
                        f"[*] Local spoke section Z band: "
                        f"{spoke_section_lower_z:.2f} -> {spoke_section_upper_z:.2f}"
                    )

                    for idx, spec in enumerate(region_specs):
                        if idx >= len(spoke_regions):
                            continue
                        base_desc = region_descs[idx] if idx < len(region_descs) else None
                        if base_desc is None:
                            continue

                        root_floor_r = max(
                            float(hole_radius) + 6.0,
                            float(pcd_radius) + float(hole_radius) + 0.8 if float(pcd_radius) > 0.0 else hub_radius - 6.0
                        )
                        station_inner_r = max(root_floor_r, float(base_desc["inner_r"]) - 1.2)
                        station_outer_r = min(spoke_outer_limit_r + 2.4, float(base_desc["outer_r"]) + 1.2)
                        root_target_r = max(
                            root_floor_r,
                            station_inner_r - max(4.8, min(11.0, (station_outer_r - station_inner_r) * 0.22 + 1.2))
                        )
                        tip_target_r = min(
                            spoke_outer_limit_r + 10.0,
                            station_outer_r + max(7.0, min(18.0, (station_outer_r - station_inner_r) * 0.30 + 2.0))
                        )
                        if idx < len(spoke_root_regions):
                            root_region_payload = spoke_root_regions[idx]
                            root_region_pts = (
                                root_region_payload.get("points", [])
                                if isinstance(root_region_payload, dict)
                                else root_region_payload
                            )
                            if len(root_region_pts) >= 4:
                                try:
                                    root_radii = [math.hypot(float(x), float(y)) for x, y in root_region_pts[:-1]]
                                    if root_radii:
                                        root_outer_r = max(root_radii)
                                        root_inner_r = float(np.percentile(np.asarray(root_radii, dtype=float), 10.0))
                                        station_inner_r = min(
                                            station_inner_r,
                                            max(root_floor_r, root_outer_r - 1.2)
                                        )
                                        root_target_r = min(
                                            root_target_r,
                                        max(
                                            root_floor_r,
                                            root_inner_r + 0.2
                                        )
                                    )
                                except Exception:
                                    pass
                        if station_outer_r <= station_inner_r + 8.0:
                            continue

                        station_count = max(10, min(14, int((station_outer_r - station_inner_r) / 7.0) + 7))
                        dense_station_counts.append(station_count)
                        station_radii = [float(r) for r in np.linspace(station_inner_r, station_outer_r, station_count)]

                        center_angle_deg = float(base_desc["angle"])
                        theta = math.radians(center_angle_deg)
                        plane_normal = np.asarray([math.cos(theta), math.sin(theta), 0.0], dtype=float)
                        plane_x_dir = np.asarray([-math.sin(theta), math.cos(theta), 0.0], dtype=float)

                        tip_threshold_r = station_outer_r - max(8.0, min(16.0, (station_outer_r - station_inner_r) * 0.22))

                        for station_r in station_radii:
                            section_record = build_local_spoke_section_record(
                                mesh,
                                spoke_regions[idx],
                                center_angle_deg,
                                station_r,
                                target_z_band=(spoke_section_lower_z, spoke_section_upper_z),
                                span_region=spoke_regions[idx],
                                min_area=24.0,
                                half_length=max(120.0, station_outer_r * 0.8)
                            )
                            if section_record is None:
                                continue
                            section_groups[idx].append(section_record)

                        filtered_sections = filter_spoke_section_records(section_groups[idx])
                        provisional_tip_candidates = [
                            dict(section_record)
                            for section_record in filtered_sections
                            if float(section_record.get("station_r", 0.0)) >= tip_threshold_r
                        ]
                        if len(provisional_tip_candidates) < 2 and len(filtered_sections) >= 2:
                            provisional_tip_candidates = [
                                dict(section_record)
                                for section_record in filtered_sections[-min(4, len(filtered_sections)):]
                            ]

                        filtered_sections = extend_spoke_section_records_with_actual_slices(
                            mesh,
                            spoke_regions[idx],
                            center_angle_deg,
                            filtered_sections,
                            (spoke_section_lower_z, spoke_section_upper_z),
                            inner_target_r=root_target_r,
                            outer_target_r=tip_target_r,
                            root_points=root_region_pts if idx < len(spoke_root_regions) and len(root_region_pts) >= 4 else None,
                            tip_sections=provisional_tip_candidates
                        )
                        filtered_sections = filter_spoke_section_records(filtered_sections)
                        if filtered_sections:
                            try:
                                current_outer_r = max(float(section.get("station_r", 0.0)) for section in filtered_sections)
                            except Exception:
                                current_outer_r = 0.0
                            if current_outer_r < tip_target_r - 5.0:
                                retry_tip_candidates = [
                                    dict(section_record)
                                    for section_record in filtered_sections
                                    if float(section_record.get("station_r", 0.0)) >= max(tip_threshold_r - 6.0, current_outer_r - 10.0)
                                ]
                                if len(retry_tip_candidates) < 2 and len(filtered_sections) >= 2:
                                    retry_tip_candidates = [
                                        dict(section_record)
                                        for section_record in filtered_sections[-min(5, len(filtered_sections)):]
                                    ]
                                retry_sections = extend_spoke_section_records_with_actual_slices(
                                    mesh,
                                    spoke_regions[idx],
                                    center_angle_deg,
                                    filtered_sections,
                                    (spoke_section_lower_z, spoke_section_upper_z),
                                    inner_target_r=root_target_r,
                                    outer_target_r=tip_target_r,
                                    root_points=root_region_pts if idx < len(spoke_root_regions) and len(root_region_pts) >= 4 else None,
                                    tip_sections=retry_tip_candidates
                                )
                                retry_sections = filter_spoke_section_records(retry_sections)
                                if retry_sections:
                                    filtered_sections = retry_sections
                        if filtered_sections:
                            try:
                                section_radii_dbg = [float(section.get("station_r", 0.0)) for section in filtered_sections]
                                root_ext_count = len([section for section in filtered_sections if section.get("extension_side") == "root"])
                                tip_ext_count = len([section for section in filtered_sections if section.get("extension_side") == "tip"])
                                print(
                                    f"[*] Spoke {idx} section coverage: count={len(filtered_sections)}, "
                                    f"R={min(section_radii_dbg):.2f}->{max(section_radii_dbg):.2f}, "
                                    f"root_ext={root_ext_count}, tip_ext={tip_ext_count}"
                                )
                            except Exception:
                                pass
                        section_groups[idx] = filtered_sections
                        tip_candidates = [
                            dict(section_record)
                            for section_record in filtered_sections
                            if float(section_record.get("station_r", 0.0)) >= tip_threshold_r
                        ]
                        if len(tip_candidates) < 2 and len(filtered_sections) >= 2:
                            tip_candidates = [dict(section_record) for section_record in filtered_sections[-min(3, len(filtered_sections)):]]
                        tip_section_groups[idx] = tip_candidates

                    if dense_station_counts:
                        print(
                            f"[*] Orthogonal spoke section layers: "
                            f"{min(dense_station_counts)}..{max(dense_station_counts)} stations/member"
                        )

                    spoke_sections = [{"sections": sections} for sections in section_groups]
                    valid_section_count = len([group for group in spoke_sections if len(group["sections"]) >= 3])
                    print(
                        f"[*] Multi-section spoke slices extracted: {valid_section_count}/"
                        f"{len(spoke_sections)} spokes"
                    )
                    spoke_tip_sections = [{"sections": sections} for sections in tip_section_groups]
                    valid_tip_count = len([group for group in spoke_tip_sections if len(group["sections"]) >= 2])
                    print(
                        f"[*] Spoke tip sections extracted: {valid_tip_count}/"
                        f"{len(spoke_tip_sections)} spokes"
                    )

                    if spoke_voids:
                        void_candidates = []
                        for idx, spoke_void in enumerate(spoke_voids):
                            pts_void = spoke_void.get("points", []) if isinstance(spoke_void, dict) else spoke_void
                            if len(pts_void) < 4:
                                continue
                            desc = describe_planar_region(spoke_void, min_area=30.0)
                            if desc is None:
                                continue
                            try:
                                area_val = float(normalize_geom(Polygon(pts_void)).area)
                            except Exception:
                                area_val = 0.0
                            void_candidates.append((area_val, idx, desc))
                        if void_candidates:
                            _, _, best_void_desc = max(void_candidates, key=lambda item: item[0])
                            spokeless_section_angle_deg = float(best_void_desc["angle"])
                            spokeless_section_points_raw = extract_rotated_section_points(
                                mesh,
                                spokeless_section_angle_deg
                            )
                            if spokeless_section_points_raw:
                                spokeless_upper_profile_raw = sample_radial_upper_envelope(
                                    spokeless_section_points_raw,
                                    min_radius=0.0,
                                    max_radius=rim_max_radius,
                                    bin_count=220,
                                    percentile=98.0
                                )
                                spokeless_lower_profile_raw = sample_radial_lower_envelope(
                                    spokeless_section_points_raw,
                                    min_radius=0.0,
                                    max_radius=rim_max_radius,
                                    bin_count=220,
                                    percentile=2.0
                                )
                            spokeless_guarded_section_regions_raw = extract_rotated_section_regions(
                                mesh,
                                spokeless_section_angle_deg,
                                max_radius=rim_max_radius
                            )
                            if spokeless_guarded_section_regions_raw:
                                spokeless_guarded_section_region_raw = spokeless_guarded_section_regions_raw[0]
                                print(
                                    f"[*] Spokeless guarded section extracted at "
                                    f"{spokeless_section_angle_deg:.2f} deg from window-centered slice"
                                )
            except Exception as e:
                print(f"[!] Structural spoke region extraction failed: {e}")
                spoke_regions = []
                spoke_sections = []
                spoke_tip_sections = []

    except Exception as e:
        print(f"[!] ???????????: {e}")
        spoke_voids = []
        best_boundary_points = []
        best_main_poly = None
        spoke_regions = []
        spoke_sections = []
        spoke_tip_sections = []

    if lightweight_preview:
        print("[*] Lightweight preview extraction active. Skipping heavy hub/spoke detail passes.")

        hub_profile_pts = []
        rotary_face_profile_raw = []
        rotary_profile_stats = {
            "valid_sections": 0,
            "radial_bins_with_hits": 0,
            "median_spread": 0.0,
            "guarded": bool(preview_guard_stats.get("guarded", False)),
            "excluded_angles": preview_guard_stats.get("excluded_angles", []),
            "preview_angle": preview_guard_stats.get("preview_angle", 0.0),
            "exclusion_half_width_deg": preview_guard_stats.get("exclusion_half_width_deg", 0.0),
        }

        try:
            rotary_min_r = max(0.0, bore_radius - 1.0)
            rotary_max_r = max(
                rim_max_radius - 0.5,
                max([float(p[0]) for p in rim_profile_points], default=rim_max_radius)
            )
            rotary_face_profile_raw, rotary_profile_stats = extract_axisymmetric_face_profile(
                mesh,
                rotary_min_r,
                rotary_max_r,
                hub_z_offset,
                angle_count=12,
                radial_bin_count=120,
                hole_count=hole_count,
                phase_angle_deg=derived_params.get("pcd_phase_angle", 0.0)
            )
            if rotary_face_profile_raw:
                print(
                    f"[*] Lightweight rotary face profile extracted: {len(rotary_face_profile_raw)} samples "
                    f"from {rotary_profile_stats.get('valid_sections', 0)} sections"
                )
        except Exception as preview_rotary_exc:
            print(f"[!] Lightweight rotary face extraction failed: {preview_rotary_exc}")
            rotary_face_profile_raw = []
            rotary_profile_stats = {
                "valid_sections": 0,
                "radial_bins_with_hits": 0,
                "median_spread": 0.0,
                "guarded": bool(preview_guard_stats.get("guarded", False)),
                "excluded_angles": preview_guard_stats.get("excluded_angles", []),
                "preview_angle": preview_guard_stats.get("preview_angle", 0.0),
                "exclusion_half_width_deg": preview_guard_stats.get("exclusion_half_width_deg", 0.0),
            }

        if not rotary_face_profile_raw:
            rotary_face_profile_raw = list(orthographic_face_profile_raw)

        try:
            slice_xz = mesh.section(plane_origin=[0, 0, 0], plane_normal=[0, 1, 0])
            if slice_xz:
                points = []
                for entity in slice_xz.entities:
                    pts = slice_xz.vertices[entity.points]
                    points.extend(pts)
                points = np.asarray(points, dtype=float)
                if len(points) > 0:
                    min_x = bore_radius
                    max_x = hub_radius
                    mask = (points[:, 0] >= min_x) & (points[:, 0] <= max_x)
                    roi_points = points[mask]
                    if len(roi_points) > 0:
                        num_bins = 36
                        bins = np.linspace(min_x, max_x, num_bins)
                        digitized = np.digitize(roi_points[:, 0], bins)
                        top_curve = []
                        for i in range(1, len(bins)):
                            bin_pts = roi_points[digitized == i]
                            if len(bin_pts) > 0:
                                max_z = np.max(bin_pts[:, 2])
                                mean_x = np.mean(bin_pts[:, 0])
                                top_curve.append([mean_x, max_z])
                        top_curve = sorted(top_curve, key=lambda p: p[0], reverse=True)
                        if top_curve:
                            hub_profile_pts.append([max_x, hub_z_offset])
                            hub_profile_pts.extend(top_curve)
                            hub_profile_pts.append([min_x, hub_z_offset])
                            hub_profile_pts = [
                                [round(float(p[0]), 3), round(float(p[1]), 3)]
                                for p in hub_profile_pts
                            ]
                            hub_profile_pts = regularize_hub_profile_points(hub_profile_pts, base_z=hub_z_offset)
        except Exception as preview_hub_exc:
            print(f"[!] Lightweight hub profile extraction failed: {preview_hub_exc}")
            hub_profile_pts = []

        model_z_shift = float(rim_profile_z_shift)
        hub_z_offset = round(float(hub_z_offset) + model_z_shift, 2)
        best_z_model = round(float(best_z) + model_z_shift, 2) if 'best_z' in locals() else hub_z_offset
        hub_profile_pts = [[round(float(p[0]), 3), round(float(p[1]) + model_z_shift, 3)] for p in hub_profile_pts]
        orthographic_section_points = shift_curve_z(orthographic_section_points_raw, model_z_shift)
        orthographic_face_profile = shift_curve_z(orthographic_face_profile_raw, model_z_shift)
        rotary_face_profile = shift_curve_z(rotary_face_profile_raw, model_z_shift)
        guarded_section_region = shift_section_region_z(guarded_section_region_raw, model_z_shift)
        spokeless_section_points = shift_curve_z(spokeless_section_points_raw, model_z_shift)
        spokeless_upper_profile = shift_curve_z(spokeless_upper_profile_raw, model_z_shift)
        spokeless_lower_profile = shift_curve_z(spokeless_lower_profile_raw, model_z_shift)
        spokeless_guarded_section_region = shift_section_region_z(spokeless_guarded_section_region_raw, model_z_shift)
        spokeless_guarded_section_regions = [
            shift_section_region_z(region, model_z_shift)
            for region in (spokeless_guarded_section_regions_raw or [])
            if region
        ]
        spokeless_reference_fragments = derive_spokeless_reference_fragments(
            spokeless_guarded_section_regions,
            derived_params
        )
        preview_band_inner_r, preview_band_outer_r = derive_spoke_band_limits(spoke_regions, derived_params)
        prefer_fragmented_spokeless_base = should_prefer_fragmented_spokeless_base(
            spokeless_guarded_section_regions,
            preview_band_inner_r,
            preview_band_outer_r
        )
        guarded_upper_profile, guarded_lower_profile = sample_section_region_envelopes(
            guarded_section_region,
            0.0,
            rim_max_radius,
            sample_count=220
        )
        spokeless_hybrid_profile = build_hybrid_profile(
            guarded_upper_profile or rotary_face_profile,
            spokeless_upper_profile,
            preview_band_inner_r,
            preview_band_outer_r,
            reference_fragments=spokeless_reference_fragments,
            profile_key="upper_profile"
        )
        spokeless_hybrid_lower_profile = build_hybrid_profile(
            guarded_lower_profile,
            spokeless_lower_profile,
            preview_band_inner_r,
            preview_band_outer_r,
            reference_fragments=spokeless_reference_fragments,
            profile_key="lower_profile"
        )
        spokeless_profile_regions = build_fragmented_section_regions_from_profiles(
            spokeless_upper_profile,
            spokeless_lower_profile
        )
        spokeless_baseline_regions = select_spokeless_baseline_regions(spokeless_profile_regions)
        spokeless_nospoke_regions = select_spokeless_nospoke_regions(
            spokeless_profile_regions,
            derived_params
        )
        spokeless_hybrid_region = build_section_region_from_envelopes(
            spokeless_hybrid_profile,
            spokeless_hybrid_lower_profile
        )
        if len(spokeless_profile_regions) >= 2:
            prefer_fragmented_spokeless_base = True
        if spokeless_reference_fragments.get("regions"):
            summary_parts = []
            for desc in spokeless_reference_fragments["regions"]:
                marks = []
                if desc["index"] == spokeless_reference_fragments.get("hub_region_index"):
                    marks.append("H")
                if desc["index"] == spokeless_reference_fragments.get("rim_region_index"):
                    marks.append("R")
                if desc["index"] == spokeless_reference_fragments.get("mid_region_index"):
                    marks.append("M")
                tag = f"[{'/'.join(marks)}]" if marks else ""
                summary_parts.append(
                    f"{desc['index']}{tag}:R={desc['inner_r']:.1f}->{desc['outer_r']:.1f},Z={desc['z_min']:.1f}->{desc['z_max']:.1f}"
                )
            print("[*] Spoke-free section fragments: " + " | ".join(summary_parts))
        if prefer_fragmented_spokeless_base:
            print("[*] Spoke-free base remains disconnected across the spoke band. Fragmented revolve base will be preferred.")

        lightweight_global_params = {
            "rim_width": round(rim_width, 2),
            "rim_max_radius": round(rim_max_radius, 2),
            "rim_thickness": round(rim_thickness, 2),
            "rim_profile_z_shift": round(model_z_shift, 2),
            "spoke_width": round(spoke_width, 2),
            "spoke_thickness": round(spoke_thickness, 2),
            "hub_thickness": round(hub_thickness, 2),
            "hub_z_offset": round(hub_z_offset, 2),
            "hub_radius": round(hub_radius, 2),
            "bore_radius": round(bore_radius, 2),
            "pcd_radius": round(pcd_radius, 2),
            "hole_radius": round(hole_radius, 2),
            "hole_count": int(hole_count),
            "spoke_num": int(len(spoke_voids)) if len(spoke_voids) > 0 else int(hole_count),
            "pcd_phase_angle": round(derived_params.get("pcd_phase_angle", 0.0), 2),
        }

        collected_features = {
            "global_params": dict(lightweight_global_params),
            "rim_profile": {"points": rim_profile_points},
            "spoke_face": {
                "boundary": best_boundary_points,
                "z": best_z_model
            },
            "spoke_voids": spoke_voids,
            "spoke_regions": spoke_regions,
            "hub_profile": {"points": hub_profile_pts},
            "rotary_face_profile": {"points": rotary_face_profile},
            "guarded_section_region": guarded_section_region,
            "spokeless_section_points": spokeless_section_points,
            "spokeless_upper_profile": spokeless_upper_profile,
            "spokeless_lower_profile": spokeless_lower_profile,
            "spokeless_guarded_section_region": spokeless_guarded_section_region,
            "spokeless_guarded_section_regions": spokeless_guarded_section_regions,
            "spokeless_reference_fragments": spokeless_reference_fragments,
            "spokeless_profile_regions": spokeless_profile_regions,
            "spokeless_baseline_regions": spokeless_baseline_regions,
            "spokeless_nospoke_regions": spokeless_nospoke_regions,
            "prefer_fragmented_spokeless_base": prefer_fragmented_spokeless_base,
            "spokeless_hybrid_profile": spokeless_hybrid_profile,
            "spokeless_hybrid_region": spokeless_hybrid_region,
            "spoke_motif_topology": {},
        }

        preview_data = {
            "orthographic_section_points": orthographic_section_points,
            "orthographic_face_profile": orthographic_face_profile,
            "rotary_face_profile": rotary_face_profile,
            "rotary_profile_stats": rotary_profile_stats,
            "preview_section_angle_deg": round(float(preview_section_angle_deg), 3),
            "spokeless_section_angle_deg": round(float(spokeless_section_angle_deg), 3) if spokeless_section_angle_deg is not None else None,
            "spokeless_section_points": spokeless_section_points,
            "spokeless_upper_profile": spokeless_upper_profile,
            "spokeless_lower_profile": spokeless_lower_profile,
            "spokeless_guarded_section_region": spokeless_guarded_section_region,
            "spokeless_guarded_section_regions": spokeless_guarded_section_regions,
            "spokeless_reference_fragments": spokeless_reference_fragments,
            "spokeless_profile_regions": spokeless_profile_regions,
            "spokeless_baseline_regions": spokeless_baseline_regions,
            "spokeless_nospoke_regions": spokeless_nospoke_regions,
            "prefer_fragmented_spokeless_base": prefer_fragmented_spokeless_base,
            "spokeless_hybrid_profile": spokeless_hybrid_profile,
            "spokeless_hybrid_region": spokeless_hybrid_region,
            "guarded_section_region": guarded_section_region,
            "rim_profile": rim_profile_points,
            "hub_profile": hub_profile_pts,
            "spoke_regions": spoke_regions,
            "spoke_voids": spoke_voids,
            "spoke_motif_topology": {},
            "global_params": dict(lightweight_global_params)
        }
        if return_preview:
            return collected_features, preview_data
        return collected_features

    # -------------------------------------------------------------------------
    # ?? 7: ?????????? (Hub Profile Extraction)
    # -------------------------------------------------------------------------
    print("[*] ???????????? (Hub Profile Analysis)...")
    hub_profile_pts = []
    hub_profile_stats = {}
    hub_profile_override = False
    try:
        print("[*] ??????????????????????????????????...")

        min_x = bore_radius if 'bore_radius' in locals() else 30.0
        max_x = hub_radius if 'hub_radius' in locals() else 60.0
        safe_profile_limit = max(
            min_x + 10.0,
            pcd_radius + hole_radius + 6.0,
            pcd_radius * 1.12 if hole_count > 0 else min_x + 16.0
        )
        if max_x > safe_profile_limit * 1.35:
            print(f"[*] Hub profile radius clipped: {max_x:.2f} -> {safe_profile_limit:.2f} mm")
            max_x = safe_profile_limit
        base_z = hub_z_offset if 'hub_z_offset' in locals() else 20.0

        angle_samples, hub_guard_stats = generate_guarded_section_angles(
            12,
            hole_count=hole_count,
            phase_angle_deg=derived_params.get("pcd_phase_angle", 0.0),
            exclusion_half_width_deg=7.0
        )
        radial_bins = np.linspace(min_x, max_x, 61)
        radial_centers = (radial_bins[:-1] + radial_bins[1:]) * 0.5
        radial_samples = [[] for _ in range(len(radial_centers))]
        valid_profile_sections = 0

        for angle_deg in angle_samples:
            theta = math.radians(float(angle_deg))
            plane_normal = [-math.sin(theta), math.cos(theta), 0.0]
            radial_slice = mesh.section(plane_origin=[0, 0, 0], plane_normal=plane_normal)
            if not radial_slice:
                continue

            section_points = []
            for entity in radial_slice.entities:
                pts = radial_slice.vertices[entity.points]
                section_points.extend(pts)

            if len(section_points) < 20:
                continue

            section_points = np.asarray(section_points, dtype=float)
            rs = np.hypot(section_points[:, 0], section_points[:, 1])
            zs = section_points[:, 2]
            mask = (
                (rs >= (min_x - 0.5)) &
                (rs <= (max_x + 0.5)) &
                (zs >= (base_z - 0.5))
            )
            if np.count_nonzero(mask) < 20:
                continue

            rs = rs[mask]
            zs = zs[mask]
            digitized = np.digitize(rs, radial_bins)
            local_hits = 0

            for bin_idx in range(1, len(radial_bins)):
                bin_zs = zs[digitized == bin_idx]
                if len(bin_zs) < 2:
                    continue
                top_z = float(np.percentile(bin_zs, 96))
                if top_z <= base_z + 0.2:
                    continue
                radial_samples[bin_idx - 1].append(top_z)
                local_hits += 1

            if local_hits >= 10:
                valid_profile_sections += 1

        aggregated_curve = []
        for radius_val, z_samples in zip(radial_centers, radial_samples):
            if len(z_samples) == 0:
                continue
            z_val = float(np.percentile(np.asarray(z_samples, dtype=float), 72))
            aggregated_curve.append([float(radius_val), z_val])

        if len(aggregated_curve) >= 10:
            curve_arr = np.asarray(aggregated_curve, dtype=float)
            z_vals = curve_arr[:, 1]
            if len(z_vals) >= 7:
                window = min(11, len(z_vals) if len(z_vals) % 2 == 1 else len(z_vals) - 1)
                if window >= 5:
                    z_vals = savgol_filter(z_vals, window_length=window, polyorder=2, mode="interp")
            z_vals = np.maximum(z_vals, base_z + 0.15)

            top_curve = [
                [round(float(r), 3), round(float(z), 3)]
                for r, z in zip(curve_arr[:, 0], z_vals)
            ]
            top_curve = sorted(top_curve, key=lambda p: p[0], reverse=True)

            outer_r = top_curve[0][0]
            inner_r = top_curve[-1][0]
            hub_profile_pts = [[outer_r, round(float(base_z), 3)]]
            hub_profile_pts.extend(top_curve)
            hub_profile_pts.append([inner_r, round(float(base_z), 3)])
            hub_profile_pts = regularize_hub_profile_points(hub_profile_pts, base_z=base_z)

            hub_profile_stats = {
                "section_count": int(valid_profile_sections),
                "profile_outer_r": round(float(outer_r), 3),
                "profile_inner_r": round(float(inner_r), 3),
                "profile_top_z": round(float(np.max(z_vals)), 3),
                "guarded": bool(hub_guard_stats.get("guarded", False))
            }
            hub_profile_override = True
            print(
                f"[*] Multi-angle hub profile extracted: {len(top_curve)} samples "
                f"from {valid_profile_sections} valid sections"
            )
            if hub_guard_stats.get("guarded", False):
                print(
                    f"[*] Hub profile sections avoided PCD-hole angles "
                    f"{hub_guard_stats.get('excluded_angles', [])}"
                )
    except Exception as hub_profile_exc:
        print(f"[!] Multi-angle hub profile extraction failed: {hub_profile_exc}")

    if not hub_profile_override:
        try: 
            print("[*] ???????????????????????????????...") 
            
            # 1. ???????????(????????????????????) 
            min_x = bore_radius if 'bore_radius' in locals() else 30.0
            max_x = hub_radius if 'hub_radius' in locals() else 60.0
            safe_profile_limit = max(min_x + 8.0, pcd_radius + hole_radius + 4.0)
            if max_x > safe_profile_limit * 1.4:
                print(f"[*] Hub profile radius clipped: {max_x:.2f} -> {safe_profile_limit:.2f} mm")
                max_x = safe_profile_limit
            base_z = hub_z_offset if 'hub_z_offset' in locals() else 20.0
            
            # 2. ??3D ?????????? (XZ ???, Y=0) 
            slice_xz = mesh.section(plane_origin=[0, 0, 0], plane_normal=[0, 1, 0]) 
            
            if slice_xz: 
                # ????????????????? 
                points = [] 
                for entity in slice_xz.entities: 
                    pts = slice_xz.vertices[entity.points] 
                    points.extend(pts) 
                points = np.array(points) 
                
                # 3. ???????????(Cylindrical Mask)?????? X ??????????????? 
                mask = (points[:, 0] >= min_x) & (points[:, 0] <= max_x) 
                roi_points = points[mask] 
                
                if len(roi_points) > 0: 
                    # 4. ???????????(Top Surface Curve) 
                    # ??X ?????? 50 ??????????????????? Z ?????? 
                    # ????????????????????????????????????????????
                    num_bins = 50 
                    bins = np.linspace(min_x, max_x, num_bins) 
                    digitized = np.digitize(roi_points[:, 0], bins) 
                    
                    top_curve = [] 
                    for i in range(1, len(bins)): 
                        bin_pts = roi_points[digitized == i] 
                        if len(bin_pts) > 0: 
                            max_z = np.max(bin_pts[:, 2]) # ?????? 
                            mean_x = np.mean(bin_pts[:, 0]) 
                            top_curve.append([mean_x, max_z]) 
                    
                    # 5. ????????CadQuery ??????????(?????? X ?????) 
                    top_curve = sorted(top_curve, key=lambda p: p[0], reverse=True) 
                    
                    hub_profile_pts = []
                    hub_profile_pts.append([max_x, base_z]) # ???????? 
                    
                    # ???????????? 
                    for p in top_curve: 
                        hub_profile_pts.append([p[0], p[1]]) 
                        
                    hub_profile_pts.append([min_x, base_z]) # ???????? 
                    
                    # ???????????????
                    hub_profile_pts = [[round(float(p[0]), 3), round(float(p[1]), 3)] for p in hub_profile_pts]
                    hub_profile_pts = regularize_hub_profile_points(hub_profile_pts, base_z=base_z)
    
                    print(f"[*] Fallback hub profile extracted: {len(hub_profile_pts)} points")
                    
        except Exception as e: 
            print(f"[!] ?????????????? {e}")

    # -------------------------------------------------------------------------
    # ?? 8: ????????3D ?????? (Zero-Magic-Number Perception)
    # -------------------------------------------------------------------------
    print("[*] ????? 3D ????????(Zero-Magic-Number Analysis)...")
    
    try:
        # =========================================================
        # ?? ?????????3D ???????????(Zero-Magic-Number Perception)
        # =========================================================
        
        # ??????????????????????
        bore_r = bore_radius
        hub_r = hub_radius
        hub_z = hub_z_offset
        pcd_r = pcd_radius
        
        # 1. ???????????????3D ???
        # ????????Z > hub_z ???????????bore_r ??hub_r ???
        hub_verts = []
        # ?????? trimesh ???????????
        vs = mesh.vertices
        # ??????????????
        rs = np.hypot(vs[:, 0], vs[:, 1])
        # ????
        mask = (rs >= bore_r) & (rs <= hub_r) & (vs[:, 2] >= hub_z)
        hub_verts = vs[mask]
        
        if len(hub_verts) > 0:
            # ???????A????????????????
            true_top_z = float(np.max(hub_verts[:, 2]))
            
            # ???????B????????????????????????????????????
            # ??? 1.1 ????????????????????????? 10% ???????
            mask_bore = (rs[mask] <= bore_r * 1.1)
            bore_verts = hub_verts[mask_bore]
            
            # ????????? (hub_z + 5mm)
            mask_front = bore_verts[:, 2] > (hub_z + 5.0)
            front_bore_verts = bore_verts[mask_front]
            
            if len(front_bore_verts) > 0:
                true_inner_z = float(np.min(front_bore_verts[:, 2]))
            else:
                true_inner_z = true_top_z # ????
            
            # ?????????????????
            true_dish_depth = true_top_z - true_inner_z
            
            # ????????????
            derived_params["hub_top_z"] = round(true_top_z, 2)
            derived_params["dish_depth"] = round(true_dish_depth, 2)
            print(f"[*] ??????? ???????? Z={true_top_z:.2f}, ????????={true_dish_depth:.2f} mm")
            
            # 2. ??????????????(Lug Pocket Radius)
            # ???????????????????????
            slice_z = true_top_z - (true_dish_depth * 0.5) if true_dish_depth > 2.0 else true_top_z - 5.0
            slice_mid = mesh.section(plane_origin=[0, 0, slice_z], plane_normal=[0, 0, 1])
            
            pocket_radii = []
            if slice_mid:
                # ?????
                lines = []
                for entity in slice_mid.entities:
                    line_points = slice_mid.vertices[entity.points]
                    pts_2d = line_points[:, :2]
                    lines.append(pts_2d)
                
                if lines:
                    multiline = MultiLineString([l for l in lines])
                    merged = linemerge(multiline)
                    polygons = list(polygonize(merged))
                    
                    if polygons:
                        # ?????????????????
                        main_poly = max(polygons, key=lambda p: p.area)
                        
                        for interior in main_poly.interiors:
                            poly = Polygon(interior)
                            centroid = poly.centroid
                            dist = np.hypot(centroid.x, centroid.y)
                            
                            # ?????????????????PCD ?????(10% ????)
                            if abs(dist - pcd_r) < pcd_r * 0.1:
                                r_eff = np.sqrt(poly.area / np.pi)
                                pocket_radii.append(r_eff)
            
            if pocket_radii:
                # ???????????
                r_mean = float(np.mean(pocket_radii))
                derived_params["pocket_radius"] = round(r_mean, 2)
                print(f"[*] ??????? ?????????={derived_params['pocket_radius']} mm")
            else:
                print("[*] Lug pocket radius was not measured reliably; pocket feature will stay measurement-gated.")

            if hole_count > 0:
                pocket_outer_r = derived_params.get("pocket_radius")
                if pocket_outer_r is None:
                    pocket_outer_r = 0.0
                pocket_outer_r = float(pocket_outer_r)
                pocket_top_samples = []
                pocket_floor_samples = []
                for hole_idx in range(int(hole_count)):
                    theta = math.radians(
                        float(derived_params.get("pcd_phase_angle", 0.0)) +
                        (360.0 / max(1, int(hole_count))) * hole_idx
                    )
                    cx = pcd_r * math.cos(theta)
                    cy = pcd_r * math.sin(theta)
                    local_r = np.hypot(vs[:, 0] - cx, vs[:, 1] - cy)
                    local_mask = (
                        (local_r <= (pocket_outer_r + 8.0)) &
                        (vs[:, 2] >= (hub_z - 0.5)) &
                        (vs[:, 2] <= (true_top_z + 0.5))
                    )
                    if np.count_nonzero(local_mask) < 60:
                        continue

                    local_z = vs[local_mask, 2]
                    local_band_r = local_r[local_mask]

                    mouth_mask = (
                        (local_band_r >= max(hole_radius + 6.0, pocket_outer_r - 2.0)) &
                        (local_band_r <= (pocket_outer_r + 2.5))
                    )
                    if np.count_nonzero(mouth_mask) >= 30:
                        pocket_top_samples.append(float(np.percentile(local_z[mouth_mask], 92)))

                    floor_mask = (
                        (local_band_r >= max(hole_radius + 2.0, pocket_outer_r * 0.62)) &
                        (local_band_r <= max(hole_radius + 3.5, pocket_outer_r * 0.84))
                    )
                    if np.count_nonzero(floor_mask) >= 30:
                        pocket_floor_samples.append(float(np.percentile(local_z[floor_mask], 65)))

                if pocket_top_samples and pocket_floor_samples:
                    pocket_top_z = float(np.median(np.asarray(pocket_top_samples, dtype=float)))
                    pocket_floor_z = float(np.median(np.asarray(pocket_floor_samples, dtype=float)))
                    if pocket_top_z > pocket_floor_z + 1.0:
                        pocket_floor_radius_samples = []
                        pocket_floor_face_z_samples = []
                        pocket_profile_upper_limit = pocket_top_z - max(4.0, (pocket_top_z - pocket_floor_z) * 0.35)
                        for hole_idx in range(int(hole_count)):
                            theta = math.radians(
                                float(derived_params.get("pcd_phase_angle", 0.0)) +
                                (360.0 / max(1, int(hole_count))) * hole_idx
                            )
                            cx = pcd_r * math.cos(theta)
                            cy = pcd_r * math.sin(theta)
                            local_r = np.hypot(vs[:, 0] - cx, vs[:, 1] - cy)
                            local_mask = (
                                (local_r >= max(hole_radius + 0.2, 0.0)) &
                                (local_r <= (pocket_outer_r + 2.5)) &
                                (vs[:, 2] >= (hub_z - 0.5)) &
                                (vs[:, 2] <= (pocket_top_z + 0.5))
                            )
                            if np.count_nonzero(local_mask) < 80:
                                continue

                            radial_edges = np.linspace(max(hole_radius + 0.3, 0.0), pocket_outer_r + 2.0, 13)
                            plateau_bins = []
                            for edge_lo, edge_hi in zip(radial_edges[:-1], radial_edges[1:]):
                                ring_mask = local_mask & (local_r >= edge_lo) & (local_r < edge_hi)
                                if np.count_nonzero(ring_mask) < 18:
                                    continue
                                ring_z = vs[ring_mask, 2]
                                ring_top_z = float(np.percentile(ring_z, 95))
                                if ring_top_z <= pocket_profile_upper_limit:
                                    plateau_bins.append((((edge_lo + edge_hi) * 0.5), ring_top_z))

                            if plateau_bins:
                                outer_plateau_r = max([item[0] for item in plateau_bins])
                                outer_band_z = [
                                    item[1] for item in plateau_bins
                                    if item[0] >= (outer_plateau_r - 1.2)
                                ]
                                if outer_band_z:
                                    pocket_floor_radius_samples.append(float(outer_plateau_r))
                                    pocket_floor_face_z_samples.append(float(np.median(np.asarray(outer_band_z, dtype=float))))

                        if pocket_floor_face_z_samples:
                            pocket_floor_z = float(np.median(np.asarray(pocket_floor_face_z_samples, dtype=float)))
                        if pocket_floor_radius_samples:
                            derived_params["pocket_floor_radius"] = round(
                                float(np.median(np.asarray(pocket_floor_radius_samples, dtype=float))),
                                2
                            )

                        derived_params["pocket_top_z"] = round(pocket_top_z, 2)
                        derived_params["pocket_floor_z"] = round(pocket_floor_z, 2)
                        derived_params["pocket_depth"] = round(pocket_top_z - pocket_floor_z, 2)
                        print(
                            f"[*] Lug pocket depth measured: top Z={pocket_top_z:.2f}, "
                            f"floor Z={pocket_floor_z:.2f}, depth={pocket_top_z - pocket_floor_z:.2f} mm"
                        )
                        if "pocket_floor_radius" in derived_params:
                            print(f"[*] Lug pocket floor radius measured: R={derived_params['pocket_floor_radius']:.2f} mm")

            radial_span = max(0.0, hub_r - bore_r)
            outer_face_sector_tops = []
            if radial_span > 3.0:
                outer_band_inner = max(
                    bore_r + (radial_span * 0.62),
                    hub_r - (radial_span * 0.28)
                )
                outer_band_outer = hub_r + 0.8
                annulus_mask = (
                    (rs >= outer_band_inner) &
                    (rs <= outer_band_outer) &
                    (vs[:, 2] >= (hub_z + 4.0))
                )
                if np.count_nonzero(annulus_mask) >= 120:
                    annulus_angles = np.arctan2(vs[:, 1], vs[:, 0])
                    sector_count = max(24, int(hole_count) * 8 if hole_count > 0 else 24)
                    sector_edges = np.linspace(-math.pi, math.pi, sector_count + 1)
                    for sector_idx in range(sector_count):
                        sector_mask = annulus_mask & (annulus_angles >= sector_edges[sector_idx]) & (annulus_angles < sector_edges[sector_idx + 1])
                        if np.count_nonzero(sector_mask) < 12:
                            continue
                        sector_z = vs[sector_mask, 2]
                        outer_face_sector_tops.append(float(np.percentile(sector_z, 94)))

            if outer_face_sector_tops:
                sorted_sector_tops = np.sort(np.asarray(outer_face_sector_tops, dtype=float))
                upper_count = max(6, len(sorted_sector_tops) // 3)
                hub_outer_face_z = float(np.median(sorted_sector_tops[-upper_count:]))
                hub_outer_face_z = max(hub_z + 4.0, min(true_top_z, hub_outer_face_z))
                derived_params["hub_outer_face_z"] = round(hub_outer_face_z, 2)
                print(
                    f"[*] Hub outer face measured: Z={hub_outer_face_z:.2f} "
                    f"from {len(sorted_sector_tops)} annulus sectors"
                )

            face_candidates = []
            if "hub_outer_face_z" in derived_params:
                face_candidates.append(float(derived_params["hub_outer_face_z"]))
            if 'best_z' in locals():
                face_candidates.append(float(best_z))
            if "pocket_top_z" in derived_params:
                face_candidates.append(float(derived_params["pocket_top_z"]))
            if len(hub_profile_pts) > 6:
                outer_profile_samples = [float(p[1]) for p in hub_profile_pts[1:7]]
                face_candidates.append(float(np.percentile(np.asarray(outer_profile_samples, dtype=float), 70)))

            if face_candidates:
                if "hub_outer_face_z" in derived_params:
                    hub_face_z = float(derived_params["hub_outer_face_z"])
                else:
                    hub_face_z = float(np.median(np.asarray(face_candidates, dtype=float)))
                hub_face_z = max(hub_z + 4.0, min(true_top_z, hub_face_z))
                derived_params["hub_face_z"] = round(hub_face_z, 2)
                derived_params["hub_top_z"] = round(true_top_z, 2)
                derived_params["hub_crown_height"] = round(max(0.0, true_top_z - hub_face_z), 2)
                print(
                    f"[*] Hub face constrained: face Z={hub_face_z:.2f}, "
                    f"peak Z={true_top_z:.2f}"
                )

            window_inner_reference_radii = []
            if spoke_voids:
                window_ref_radius, window_ref_stats = estimate_window_inner_reference_radius(
                    mesh,
                    spoke_voids,
                    hub_radius,
                    min(rim_max_radius - 2.0, hub_radius + 70.0)
                )
                window_inner_reference_radii = window_ref_stats.get("per_void_reference_radii", [])
                if window_ref_radius is not None:
                    derived_params["window_inner_reference_r"] = round(window_ref_radius, 2)
                    print(
                        f"[*] Window inner reference measured from spoke-free sections: "
                        f"R={window_ref_radius:.2f} mm from {window_ref_stats.get('section_count', 0)} sections"
                    )
                    if window_ref_stats.get("stabilized_count", 0) > 0:
                        print(
                            f"[*] Window inner references stabilized on "
                            f"{window_ref_stats.get('stabilized_count', 0)} outlier windows"
                        )

            if hole_count > 0 and "pocket_top_z" in derived_params and "hub_face_z" in derived_params:
                boss_low_z = float(derived_params["pocket_top_z"])
                boss_high_z = float(derived_params["hub_face_z"])
                if boss_high_z > boss_low_z + 0.25:
                    center_relief_z_raw = boss_low_z + ((boss_high_z - boss_low_z) * 0.42)
                    center_relief_z_raw = max(boss_low_z + 0.15, min(boss_high_z - 0.08, center_relief_z_raw))
                    relief_slice = mesh.section(plane_origin=[0, 0, center_relief_z_raw], plane_normal=[0, 0, 1])
                    if relief_slice:
                        relief_lines = []
                        for entity in relief_slice.entities:
                            relief_pts = relief_slice.vertices[entity.points]
                            relief_lines.append(relief_pts[:, :2])

                        relief_polygons = list(polygonize(linemerge(MultiLineString(relief_lines)))) if relief_lines else []
                        if relief_polygons:
                            relief_main_poly = normalize_geom(max(relief_polygons, key=lambda p: p.area))
                            pocket_outer_r = float(derived_params.get("pocket_radius", hole_radius + 4.0))
                            hole_spacing = 2.0 * pcd_r * math.sin(math.pi / max(1, int(hole_count)))
                            boss_clip_r = max(pocket_outer_r + 4.0, hole_spacing * 0.36)
                            boss_clip_r = min(boss_clip_r, hole_spacing * 0.48)
                            boss_clip_r = max(boss_clip_r, pocket_outer_r + 2.5)

                            extracted_bosses = []
                            boss_global_radii = []
                            for hole_idx in range(int(hole_count)):
                                theta = math.radians(
                                    float(derived_params.get("pcd_phase_angle", 0.0)) +
                                    (360.0 / max(1, int(hole_count))) * hole_idx
                                )
                                cx = pcd_r * math.cos(theta)
                                cy = pcd_r * math.sin(theta)
                                local_clip = Point(cx, cy).buffer(boss_clip_r, resolution=96)
                                local_geom = normalize_geom(relief_main_poly.intersection(local_clip))

                                boss_candidates = []
                                for poly in iter_polygons(local_geom):
                                    if poly.is_empty or poly.area < 80.0:
                                        continue
                                    coords = list(poly.exterior.coords)
                                    local_radii = [math.hypot(x - cx, y - cy) for x, y in coords[:-1]]
                                    if not local_radii or max(local_radii) < pocket_outer_r + 1.0:
                                        continue
                                    boss_candidates.append(poly)

                                if not boss_candidates:
                                    continue

                                boss_poly = normalize_geom(max(boss_candidates, key=lambda p: p.area).simplify(0.45, preserve_topology=True))
                                boss_coords = canonicalize_loop(list(boss_poly.exterior.coords))
                                if len(boss_coords) < 4:
                                    continue

                                extracted_bosses.append({
                                    "center": [round(float(cx), 3), round(float(cy), 3)],
                                    "points": boss_coords
                                })
                                boss_global_radii.extend([math.hypot(x, y) for x, y in boss_coords[:-1]])

                            if extracted_bosses and boss_global_radii:
                                boss_inner_limit_r = min(boss_global_radii)
                                center_core_limit_r = max(bore_r + 2.5, boss_inner_limit_r - 1.2)
                                center_core_geom = normalize_geom(relief_main_poly.intersection(circle_polygon(center_core_limit_r, 180)))
                                center_candidates = []
                                for poly in iter_polygons(center_core_geom):
                                    if poly.is_empty or poly.area < 60.0:
                                        continue
                                    center_candidates.append(poly)

                                if center_candidates:
                                    center_poly = max(
                                        center_candidates,
                                        key=lambda poly: (poly.area, -poly.centroid.distance(Point(0.0, 0.0)))
                                    )
                                    center_coords = canonicalize_loop(list(center_poly.exterior.coords))
                                    if len(center_coords) >= 4:
                                        center_core_region = {"points": center_coords}

                                root_regions_local = []
                                for region in spoke_regions:
                                    region_pts = region.get("points", [])
                                    if len(region_pts) < 4:
                                        continue
                                    region_angles = [
                                        math.degrees(math.atan2(y, x)) % 360.0
                                        for x, y in region_pts[:-1]
                                    ]
                                    angle_window = continuous_angle_window(region_angles)
                                    if angle_window is None:
                                        continue
                                    start_angle, end_angle, span_angle = angle_window
                                    root_padding_angle = max(1.0, min(2.2, span_angle * 0.16))
                                    root_outer_limit_r = min(hub_r + 4.0, max(pocket_outer_r + 6.0, center_core_limit_r + 20.0))
                                    root_wedge = normalize_geom(
                                        sector_polygon(
                                            start_angle - root_padding_angle,
                                            end_angle + root_padding_angle,
                                            root_outer_limit_r
                                        )
                                    )
                                    root_geom = normalize_geom(
                                        relief_main_poly
                                        .intersection(root_wedge)
                                        .intersection(circle_polygon(root_outer_limit_r, 180))
                                    )
                                    root_candidates = []
                                    for poly in iter_polygons(root_geom):
                                        if poly.is_empty or poly.area < 45.0:
                                            continue
                                        root_candidates.append(poly)
                                    if not root_candidates:
                                        continue
                                    root_poly = max(root_candidates, key=lambda poly: poly.area)
                                    if root_poly is None:
                                        continue
                                    root_coords = canonicalize_loop(list(root_poly.exterior.coords))
                                    if len(root_coords) >= 4:
                                        root_regions_local.append({"points": root_coords})

                                lug_boss_regions = extracted_bosses
                                spoke_root_regions = root_regions_local
                                derived_params["center_relief_z"] = round(center_relief_z_raw, 2)
                                print(
                                    f"[*] Center boss patches extracted: {len(lug_boss_regions)} "
                                    f"at Z={center_relief_z_raw:.2f}"
                                )
                                if spoke_root_regions:
                                    print(f"[*] Center spoke-root patches extracted: {len(spoke_root_regions)}")

            print(
                f"[*] Rear groove extraction args: hole_count={hole_count}, "
                f"phase={derived_params.get('pcd_phase_angle', 0.0)}, "
                f"bore_r={round(float(bore_r), 2) if bore_r is not None else 'n/a'}, "
                f"pcd_r={round(float(pcd_r), 2) if pcd_r is not None else 'n/a'}, "
                f"hole_radius={round(float(hole_radius), 2) if hole_radius is not None else 'n/a'}, "
                f"hub_r={round(float(hub_r), 2) if hub_r is not None else 'n/a'}, "
                f"pocket_r={round(float(derived_params.get('pocket_radius')), 2) if derived_params.get('pocket_radius') is not None else 'n/a'}, "
                f"rear_z={round(float(hub_z_offset), 2) if hub_z_offset is not None else 'n/a'}, "
                f"hub_face_z={round(float(derived_params.get('hub_face_z')), 2) if derived_params.get('hub_face_z') is not None else 'n/a'}, "
                f"pocket_floor_z={round(float(derived_params.get('pocket_floor_z')), 2) if derived_params.get('pocket_floor_z') is not None else 'n/a'}"
            )
            groove_regions_local, groove_stats = extract_hub_bottom_groove_regions(
                mesh,
                hole_count,
                derived_params.get("pcd_phase_angle", 0.0),
                bore_r,
                pcd_r,
                hole_radius,
                hub_r,
                derived_params.get("pocket_radius"),
                derived_params.get("pocket_floor_z"),
                derived_params.get("pocket_top_z"),
                hub_z_offset,
                derived_params.get("hub_face_z"),
                center_core_region
            )
            print(f"[*] Rear groove extraction returned {len(groove_regions_local)} regions")
            if groove_regions_local:
                groove_floor_z = groove_stats.get("floor_z")
                groove_top_z = groove_stats.get("top_z")
                hub_bottom_groove_regions = groove_regions_local
                if groove_floor_z is not None:
                    derived_params["hub_bottom_groove_floor_z"] = groove_floor_z
                if groove_top_z is not None:
                    derived_params["hub_bottom_groove_top_z"] = groove_top_z
                print(
                    f"[*] Hub rear-face grooves extracted: {groove_stats.get('count', len(hub_bottom_groove_regions))} "
                    f"at Z={groove_stats.get('sample_z', 'n/a')} "
                    f"(depth {groove_stats.get('floor_z', 'n/a')} -> {groove_stats.get('top_z', 'n/a')}, "
                    f"R={groove_stats.get('inner_r', 'n/a')} -> {groove_stats.get('outer_r', 'n/a')})"
                )

                if spokeless_guarded_section_regions_raw:
                    try:
                        groove_radii = []
                        for groove_region in hub_bottom_groove_regions:
                            groove_pts = groove_region.get("opening_points") or groove_region.get("points") or []
                            if len(groove_pts) < 4:
                                continue
                            groove_radii.extend([
                                math.hypot(x, y) for x, y in groove_pts[:-1]
                            ])

                        if groove_radii:
                            groove_min_r = max(float(bore_r) + 1.2, min(groove_radii) - 0.8)
                            groove_max_r = max(groove_min_r + 4.0, max(groove_radii) + 1.1)
                            groove_target_floor_z = groove_floor_z if groove_floor_z is not None else hub_z_offset
                            groove_relief_patch_count = 0
                            sanitized_spokeless_regions = []

                            for region_payload in spokeless_guarded_section_regions_raw:
                                outer_loop = region_payload.get("outer", []) if isinstance(region_payload, dict) else []
                                if len(outer_loop) < 4:
                                    sanitized_spokeless_regions.append(region_payload)
                                    continue
                                region_radii = [
                                    float(point[0])
                                    for point in outer_loop
                                    if isinstance(point, (list, tuple)) and len(point) >= 2
                                ]
                                if not region_radii:
                                    sanitized_spokeless_regions.append(region_payload)
                                    continue

                                region_min_r = min(region_radii)
                                region_max_r = max(region_radii)
                                is_hub_candidate = (
                                    region_min_r <= groove_max_r + 3.0 and
                                    region_max_r <= max(float(hub_r) + 20.0, groove_max_r + 18.0)
                                )
                                if not is_hub_candidate:
                                    sanitized_spokeless_regions.append(region_payload)
                                    continue

                                sanitized_region, groove_relief_stats = suppress_section_lower_bound_nonrotary_reliefs(
                                    region_payload,
                                    groove_min_r,
                                    groove_max_r,
                                    groove_target_floor_z,
                                    min_raise=0.9,
                                    target_offset=0.22,
                                    max_patch_width=30.0
                                )
                                groove_relief_patch_count += int(groove_relief_stats.get("patch_count", 0))
                                sanitized_spokeless_regions.append(sanitized_region)

                            if groove_relief_patch_count > 0:
                                spokeless_guarded_section_regions_raw = sanitized_spokeless_regions
                                if spokeless_guarded_section_regions_raw:
                                    spokeless_guarded_section_region_raw = spokeless_guarded_section_regions_raw[0]
                                print(
                                    f"[*] Spoke-free hub rear-face relief suppressed before revolve: "
                                    f"patches={groove_relief_patch_count}, "
                                    f"R={round(groove_min_r, 2)} -> {round(groove_max_r, 2)}"
                                )
                    except Exception as spokeless_relief_exc:
                        print(f"[!] Spoke-free hub rear-face relief suppression failed: {spokeless_relief_exc}")
            else:
                print("[*] Hub rear-face grooves mesh extraction produced no usable pockets. Synthetic fallback disabled.")

    except Exception as e:
        print(f"[!] 3D ?????????: {e}")

    target_hub_top_z = float(derived_params.get("hub_top_z", hub_z_offset + hub_thickness))
    if len(hub_profile_pts) >= 4:
        profile_base_z = float(hub_z_offset)
        current_profile_top_z = max([float(p[1]) for p in hub_profile_pts])
        if current_profile_top_z > profile_base_z + 0.5 and abs(target_hub_top_z - current_profile_top_z) > 0.15:
            scale = (target_hub_top_z - profile_base_z) / max(1e-6, current_profile_top_z - profile_base_z)
            aligned_profile = []
            for idx, pt in enumerate(hub_profile_pts):
                radius_val = float(pt[0])
                z_val = float(pt[1])
                if idx in (0, len(hub_profile_pts) - 1) and abs(z_val - profile_base_z) <= 0.25:
                    aligned_profile.append([round(radius_val, 3), round(profile_base_z, 3)])
                else:
                    new_z = profile_base_z + ((z_val - profile_base_z) * scale)
                    aligned_profile.append([round(radius_val, 3), round(min(target_hub_top_z, new_z), 3)])
            hub_profile_pts = aligned_profile
            hub_profile_stats["profile_top_z_aligned"] = round(target_hub_top_z, 3)
            print(
                f"[*] Hub profile aligned to measured top Z: "
                f"{current_profile_top_z:.2f} -> {target_hub_top_z:.2f} mm"
            )

    hub_face_z_raw = derived_params.get("hub_face_z")
    if len(hub_profile_pts) >= 6 and hub_face_z_raw is not None:
        face_target_z = float(hub_face_z_raw)
        peak_target_z = float(derived_params.get("hub_top_z", face_target_z))
        top_curve = [[float(p[0]), float(p[1])] for p in hub_profile_pts[1:-1]]
        if len(top_curve) >= 4:
            transition_count = max(3, min(8, len(top_curve) // 5))
            reinforced_curve = []
            for idx, (radius_val, z_val) in enumerate(top_curve):
                if idx < transition_count:
                    blend = 1.0 - (idx / max(1, transition_count - 1))
                    corrected_z = z_val + (max(0.0, face_target_z - z_val) * blend)
                    reinforced_curve.append([round(radius_val, 3), round(min(peak_target_z, corrected_z), 3)])
                else:
                    reinforced_curve.append([round(radius_val, 3), round(z_val, 3)])
            hub_profile_pts = [
                [round(float(hub_profile_pts[0][0]), 3), round(float(hub_profile_pts[0][1]), 3)],
                *reinforced_curve,
                [round(float(hub_profile_pts[-1][0]), 3), round(float(hub_profile_pts[-1][1]), 3)]
            ]

    try:
        rotary_min_r = max(0.0, bore_radius - 1.0)
        rotary_max_r = max(
            rim_max_radius - 0.5,
            max([float(p[0]) for p in rim_profile_points], default=rim_max_radius)
        )
        rotary_face_profile_raw, rotary_profile_stats = extract_axisymmetric_face_profile(
            mesh,
            rotary_min_r,
            rotary_max_r,
            hub_z_offset,
            angle_count=24,
            radial_bin_count=180,
            hole_count=hole_count,
            phase_angle_deg=derived_params.get("pcd_phase_angle", 0.0)
        )
        if rotary_face_profile_raw:
            print(
                f"[*] Unified rotary face profile extracted: {len(rotary_face_profile_raw)} samples "
                f"from {rotary_profile_stats.get('valid_sections', 0)} sections"
            )
            if rotary_profile_stats.get("guarded", False):
                print(
                    f"[*] Unified rotary profile avoided PCD-hole angles "
                    f"{rotary_profile_stats.get('excluded_angles', [])}"
                )
    except Exception as rotary_profile_exc:
        print(f"[!] Unified rotary face extraction failed: {rotary_profile_exc}")
        rotary_face_profile_raw = []
        rotary_profile_stats = {}

    if guarded_section_region_raw and rotary_face_profile_raw:
        try:
            groove_min_r = max(0.0, float(bore_radius) + 0.8)
            groove_max_r = derived_params.get("window_inner_reference_r")
            if groove_max_r is None or float(groove_max_r) <= groove_min_r + 6.0:
                groove_max_r = max(float(hub_radius) + 14.0, groove_min_r + 12.0)
            groove_max_r = min(float(rim_max_radius) * 0.46, float(groove_max_r) + 1.2)
            guarded_section_region_raw, groove_fix_stats = suppress_guarded_section_nonrotary_grooves(
                guarded_section_region_raw,
                rotary_face_profile_raw,
                groove_min_r,
                groove_max_r,
                min_drop=0.95,
                target_offset=0.18,
                max_patch_width=26.0
            )
            if groove_fix_stats.get("patch_count", 0) > 0:
                print(
                    f"[*] Guarded section groove suppression applied: "
                    f"patches={groove_fix_stats.get('patch_count', 0)}, "
                    f"R={round(groove_min_r, 2)} -> {round(groove_max_r, 2)}"
                )
        except Exception as groove_fix_exc:
            print(f"[!] Guarded section groove suppression failed: {groove_fix_exc}")

    def shift_section_groups(section_groups, shift_val):
        shifted_groups = []
        for group in section_groups:
            shifted_sections = []
            for section in group.get("sections", []):
                shifted_section = dict(section)
                if "target_z_band" in section and len(section.get("target_z_band", [])) >= 2:
                    shifted_section["target_z_band"] = [
                        round(float(section["target_z_band"][0]) + shift_val, 3),
                        round(float(section["target_z_band"][1]) + shift_val, 3)
                    ]
                if "z" in section:
                    shifted_section["z"] = round(float(section.get("z", 0.0)) + shift_val, 2)
                if "plane_origin" in section and len(section.get("plane_origin", [])) >= 3:
                    origin = list(section.get("plane_origin", []))
                    origin[2] = round(float(origin[2]) + shift_val, 3)
                    shifted_section["plane_origin"] = origin
                shifted_sections.append(shifted_section)
            shifted_groups.append({"sections": shifted_sections})
        return shifted_groups

    def shift_actual_z_profile_groups(profile_groups, shift_val):
        shifted_groups = []
        for group in profile_groups or []:
            shifted_profiles = []
            profiles = group.get("profiles", []) if isinstance(group, dict) else []
            for profile in profiles:
                pts = profile.get("points", []) if isinstance(profile, dict) else []
                if len(pts) < 4:
                    continue
                shifted_profile = {
                    "z": round(float(profile.get("z", 0.0)) + shift_val, 3),
                    "points": [
                        [round(float(x), 3), round(float(y), 3)]
                        for x, y in pts
                    ]
                }
                if isinstance(profile, dict):
                    if profile.get("terminal_contact") is not None:
                        shifted_profile["terminal_contact"] = bool(profile.get("terminal_contact"))
                    if profile.get("preserve_detail") is not None:
                        shifted_profile["preserve_detail"] = bool(profile.get("preserve_detail"))
                    if profile.get("profile_source") is not None:
                        shifted_profile["profile_source"] = str(profile.get("profile_source"))
                shifted_profiles.append(shifted_profile)
            shifted_group = {"profiles": shifted_profiles}
            if isinstance(group, dict):
                if group.get("prefer_local_section") is not None:
                    shifted_group["prefer_local_section"] = bool(group.get("prefer_local_section"))
                if group.get("stack_mode") is not None:
                    shifted_group["stack_mode"] = str(group.get("stack_mode"))
                if group.get("profile_count") is not None:
                    try:
                        shifted_group["profile_count"] = int(group.get("profile_count"))
                    except Exception:
                        shifted_group["profile_count"] = int(len(shifted_profiles))
                if group.get("source_label") is not None:
                    shifted_group["source_label"] = str(group.get("source_label"))
            shifted_groups.append(shifted_group)
        return shifted_groups

    model_z_shift = float(rim_profile_z_shift)
    hub_z_offset = round(float(hub_z_offset) + model_z_shift, 2)
    best_z_model = round(float(best_z) + model_z_shift, 2) if 'best_z' in locals() else hub_z_offset
    hub_profile_pts = [[round(float(p[0]), 3), round(float(p[1]) + model_z_shift, 3)] for p in hub_profile_pts]
    orthographic_section_points = shift_curve_z(orthographic_section_points_raw, model_z_shift)
    orthographic_face_profile = shift_curve_z(orthographic_face_profile_raw, model_z_shift)
    rotary_face_profile = shift_curve_z(rotary_face_profile_raw, model_z_shift)
    guarded_section_region = shift_section_region_z(guarded_section_region_raw, model_z_shift)
    spokeless_section_points = shift_curve_z(spokeless_section_points_raw, model_z_shift)
    spokeless_upper_profile = shift_curve_z(spokeless_upper_profile_raw, model_z_shift)
    spokeless_lower_profile = shift_curve_z(spokeless_lower_profile_raw, model_z_shift)
    spokeless_guarded_section_region = shift_section_region_z(spokeless_guarded_section_region_raw, model_z_shift)
    spokeless_guarded_section_regions = [
        shift_section_region_z(region, model_z_shift)
        for region in (spokeless_guarded_section_regions_raw or [])
        if region
    ]
    spokeless_reference_fragments = derive_spokeless_reference_fragments(
        spokeless_guarded_section_regions,
        derived_params
    )
    preview_band_inner_r, preview_band_outer_r = derive_spoke_band_limits(spoke_regions, derived_params)
    prefer_fragmented_spokeless_base = should_prefer_fragmented_spokeless_base(
        spokeless_guarded_section_regions,
        preview_band_inner_r,
        preview_band_outer_r
    )
    guarded_upper_profile, guarded_lower_profile = sample_section_region_envelopes(
        guarded_section_region,
        0.0,
        rim_max_radius,
        sample_count=220
    )
    spokeless_hybrid_profile = build_hybrid_profile(
        guarded_upper_profile or rotary_face_profile,
        spokeless_upper_profile,
        preview_band_inner_r,
        preview_band_outer_r,
        reference_fragments=spokeless_reference_fragments,
        profile_key="upper_profile"
    )
    spokeless_hybrid_lower_profile = build_hybrid_profile(
        guarded_lower_profile,
        spokeless_lower_profile,
        preview_band_inner_r,
        preview_band_outer_r,
        reference_fragments=spokeless_reference_fragments,
        profile_key="lower_profile"
    )
    spokeless_profile_regions = build_fragmented_section_regions_from_profiles(
        spokeless_upper_profile,
        spokeless_lower_profile
    )
    spokeless_baseline_regions = select_spokeless_baseline_regions(spokeless_profile_regions)
    spokeless_nospoke_regions = select_spokeless_nospoke_regions(
        spokeless_profile_regions,
        derived_params
    )
    spokeless_hybrid_region = build_section_region_from_envelopes(
        spokeless_hybrid_profile,
        spokeless_hybrid_lower_profile
    )
    if len(spokeless_profile_regions) >= 2:
        prefer_fragmented_spokeless_base = True
    if spokeless_reference_fragments.get("regions"):
        summary_parts = []
        for desc in spokeless_reference_fragments["regions"]:
            marks = []
            if desc["index"] == spokeless_reference_fragments.get("hub_region_index"):
                marks.append("H")
            if desc["index"] == spokeless_reference_fragments.get("rim_region_index"):
                marks.append("R")
            if desc["index"] == spokeless_reference_fragments.get("mid_region_index"):
                marks.append("M")
            tag = f"[{'/'.join(marks)}]" if marks else ""
            summary_parts.append(
                f"{desc['index']}{tag}:R={desc['inner_r']:.1f}->{desc['outer_r']:.1f},Z={desc['z_min']:.1f}->{desc['z_max']:.1f}"
            )
        print("[*] Spoke-free section fragments: " + " | ".join(summary_parts))
    if prefer_fragmented_spokeless_base:
        print("[*] Spoke-free base remains disconnected across the spoke band. Fragmented revolve base will be preferred.")

    for key in ("hub_top_z", "hub_face_z", "hub_outer_face_z", "pocket_top_z", "pocket_floor_z", "center_relief_z", "hub_bottom_groove_floor_z", "hub_bottom_groove_top_z"):
        if key in derived_params:
            derived_params[key] = round(float(derived_params[key]) + model_z_shift, 2)

    rim_front_z = max([float(p[1]) for p in rim_profile_points]) if rim_profile_points else 0.0
    if "hub_face_z" in derived_params:
        derived_params["hub_front_inset"] = round(max(0.0, rim_front_z - float(derived_params["hub_face_z"])), 2)
    if "hub_top_z" in derived_params and "pocket_top_z" in derived_params:
        derived_params["pocket_top_inset"] = round(
            max(0.0, float(derived_params["hub_top_z"]) - float(derived_params["pocket_top_z"])),
            2
        )

    spoke_motif_topology = infer_spoke_motif_topology(spoke_regions, spoke_voids)
    spoke_sections_raw = spoke_sections
    spoke_tip_sections_raw = spoke_tip_sections
    # Re-enable true XY@Z member slice extraction. The stable-only shortcut skips
    # the exact slice source we need for terminal contact and bottom detail.
    stable_parametric_spoke_mode = False
    if stable_parametric_spoke_mode:
        print("[*] Stable parametric spoke mode active. Skipping heavy actual XY@Z stack extraction for this stage.")
        spoke_actual_z_profiles_raw = [{"profiles": []} for _ in (spoke_regions or [])]
    else:
        spoke_actual_z_profiles_raw = derive_actual_spoke_member_z_profiles(
            mesh,
            spoke_regions,
            spoke_sections_raw,
            spoke_tip_sections_raw,
            spoke_root_regions,
            spoke_motif_topology
        )
    spoke_sections = shift_section_groups(spoke_sections_raw, model_z_shift)
    spoke_tip_sections = shift_section_groups(spoke_tip_sections_raw, model_z_shift)
    spoke_actual_z_profiles = shift_actual_z_profile_groups(spoke_actual_z_profiles_raw, model_z_shift)
    spoke_actual_z_profiles = [
        {"profiles": [], "disabled_reason": "archived_actual_z_path"}
        for _ in (spoke_regions or [])
    ]
    hub_bottom_groove_regions = shift_hub_bottom_groove_regions_z(hub_bottom_groove_regions, model_z_shift)
    window_local_keepouts, window_local_root_outer_radii = derive_window_local_keepouts(
        spoke_voids,
        spoke_root_regions,
        lug_boss_regions
    )
    if window_local_keepouts:
        derived_keepout_count = sum(1 for group in window_local_keepouts if group)
        print(f"[*] Local window keepouts derived: {derived_keepout_count}/{len(window_local_keepouts)}")
    spoke_motif_sections = derive_spoke_motif_section_groups(
        spoke_motif_topology,
        spoke_regions,
        spoke_sections,
        spoke_tip_sections,
        spoke_actual_z_profiles
    )
    canonical_spoke_templates = derive_canonical_spoke_templates(spoke_motif_sections)
    actual_profile_count = 0
    actual_loft_ready_count = 0
    actual_local_section_ready_count = 0
    total_spoke_member_count = 0
    for motif_payload in spoke_motif_sections or []:
        for member_payload in motif_payload.get("members", []) or []:
            total_spoke_member_count += 1
            body_sections = [
                section for section in (member_payload.get("sections", []) or [])
                if isinstance(section, dict)
            ]
            tip_sections_member = [
                section for section in (member_payload.get("tip_sections", []) or [])
                if isinstance(section, dict)
            ]
            combined_sections = sorted(
                body_sections + tip_sections_member,
                key=lambda section: float(section.get("station_r", 0.0))
            )
            station_radii = [
                float(section.get("station_r", 0.0))
                for section in combined_sections
                if float(section.get("station_r", 0.0)) > 0.0
            ]
            region_pts = member_payload.get("region", []) or []
            region_radii = []
            try:
                region_radii = [
                    math.hypot(float(x), float(y))
                    for x, y in region_pts[:-1]
                ] if len(region_pts) >= 4 else []
            except Exception:
                region_radii = []
            expected_span = 0.0
            if region_radii:
                expected_span = float(max(region_radii) - min(region_radii))
            has_tip_coverage = bool(tip_sections_member) or any(
                str(section.get("extension_side") or "").startswith("tip")
                for section in combined_sections
            )
            has_root_coverage = bool(body_sections) or any(
                str(section.get("extension_side") or "") == "root"
                for section in combined_sections
            )
            radial_span = (
                float(max(station_radii) - min(station_radii))
                if len(station_radii) >= 2 else 0.0
            )
            if (
                len(combined_sections) >= 3
                and has_tip_coverage
                and has_root_coverage
                and radial_span >= max(6.0, expected_span * 0.52)
            ):
                actual_local_section_ready_count += 1
    if spoke_actual_z_profiles:
        actual_profile_count = sum(
            1 for item in spoke_actual_z_profiles
            if isinstance(item, dict) and len(item.get("profiles", []) or []) >= 3
        )
        actual_loft_ready_count = sum(
            1 for item in spoke_actual_z_profiles
            if isinstance(item, dict) and len(item.get("profiles", []) or []) >= 4
        )
        print(
            f"[*] Actual XY@Z spoke slice stacks extracted: "
            f"{actual_profile_count}/{len(spoke_actual_z_profiles)}"
        )
        print(
            f"[*] Actual-direct spoke loft readiness: "
            f"{actual_loft_ready_count}/{len(spoke_actual_z_profiles)}"
        )
    if total_spoke_member_count > 0:
        print(
            f"[*] Actual local-section spoke readiness: "
            f"{actual_local_section_ready_count}/{total_spoke_member_count}"
        )
    if canonical_spoke_templates:
        print(f"[*] Canonical spoke templates derived: {len(canonical_spoke_templates)} slots")
    print(
        f"[*] Spoke motif topology: type={spoke_motif_topology.get('motif_type', 'unknown')}, "
        f"spokes={spoke_motif_topology.get('spoke_count', 0)}, "
        f"motifs={spoke_motif_topology.get('motif_count', 0)}, "
        f"members={spoke_motif_topology.get('members_per_motif', 0)}"
    )
    if spoke_motif_sections:
        print(f"[*] Spoke motif section groups prepared: {len(spoke_motif_sections)}")

    # ?????????
    # ??? collected_features ????????????????????
    collected_features = {
        "global_params": {
            "rim_width": round(rim_width, 2),
            "rim_max_radius": round(rim_max_radius, 2),
            "rim_thickness": round(rim_thickness, 2),
            "rim_profile_z_shift": round(model_z_shift, 2),
            "spoke_width": round(spoke_width, 2),
            "spoke_thickness": round(spoke_thickness, 2),
            "hub_thickness": round(hub_thickness, 2),
            "hub_z_offset": round(hub_z_offset, 2),
            "hub_radius": round(hub_radius, 2),
            "bore_radius": round(bore_radius, 2),
            "pcd_radius": round(pcd_radius, 2),
            "hole_radius": round(hole_radius, 2),
            "hole_count": int(hole_count),
            "spoke_num": int(len(spoke_voids)) if len(spoke_voids) > 0 else int(hole_count),
            "pcd_phase_angle": round(derived_params.get("pcd_phase_angle", 0.0), 2),
            # New Fields (Use the local variables calculated in Step 8)
            "hub_top_z": round(derived_params.get("hub_top_z", hub_z_offset + hub_thickness), 2),
            "hub_face_z": round(
                derived_params.get("hub_face_z", derived_params.get("hub_top_z", hub_z_offset + hub_thickness)),
                2
            ),
            "hub_outer_face_z": round(
                derived_params.get("hub_outer_face_z", derived_params.get("hub_face_z", derived_params.get("hub_top_z", hub_z_offset + hub_thickness))),
                2
            ),
            "hub_crown_height": round(derived_params.get("hub_crown_height", 0.0), 2),
            "hub_outer_draft": round(derived_params.get("hub_outer_draft", 0.0), 2),
            "hub_front_inset": round(
                derived_params.get(
                    "hub_front_inset",
                    max(
                        0.0,
                        (max([float(p[1]) for p in rim_profile_points]) if rim_profile_points else 0.0) -
                        derived_params.get("hub_face_z", derived_params.get("hub_top_z", hub_z_offset + hub_thickness))
                    )
                ),
                2
            ),
            "center_relief_z": round(derived_params["center_relief_z"], 2) if "center_relief_z" in derived_params else None,
            "pocket_top_inset": round(derived_params["pocket_top_inset"], 2) if "pocket_top_inset" in derived_params else None,
            "dish_depth": round(derived_params.get("dish_depth", 0.0), 2),
            "window_inner_reference_r": round(derived_params["window_inner_reference_r"], 2) if "window_inner_reference_r" in derived_params else None,
            "pocket_radius": round(derived_params["pocket_radius"], 2) if "pocket_radius" in derived_params else None,
            "pocket_top_z": round(derived_params["pocket_top_z"], 2) if "pocket_top_z" in derived_params else None,
            "pocket_floor_z": round(derived_params["pocket_floor_z"], 2) if "pocket_floor_z" in derived_params else None,
            "pocket_depth": round(derived_params["pocket_depth"], 2) if "pocket_depth" in derived_params else None,
            "pocket_floor_radius": round(derived_params["pocket_floor_radius"], 2) if "pocket_floor_radius" in derived_params else None,
            "hub_bottom_groove_floor_z": round(derived_params["hub_bottom_groove_floor_z"], 2) if "hub_bottom_groove_floor_z" in derived_params else None,
            "hub_bottom_groove_top_z": round(derived_params["hub_bottom_groove_top_z"], 2) if "hub_bottom_groove_top_z" in derived_params else None
        },
        "rim_profile": { "points": rim_profile_points },
        "spoke_face": {
            "boundary": best_boundary_points,
            "z": best_z_model
        },
        "spoke_voids": spoke_voids,
        "window_inner_reference_radii": window_inner_reference_radii,
        "window_local_keepouts": window_local_keepouts,
        "window_local_root_outer_radii": window_local_root_outer_radii,
        "spoke_regions": spoke_regions,
        "spoke_sections": spoke_sections,
        "spoke_tip_sections": spoke_tip_sections,
        "spoke_actual_z_profiles": spoke_actual_z_profiles,
        "spoke_motif_sections": spoke_motif_sections,
        "canonical_spoke_templates": canonical_spoke_templates,
        "spoke_actual_profile_gate": {
            "strict_actual_only": True,
            "required_member_count": int(total_spoke_member_count or len(spoke_regions or [])),
            "accepted_profile_count": int(actual_profile_count),
            "loft_ready_member_count": int(actual_loft_ready_count),
            "local_section_ready_count": int(actual_local_section_ready_count),
            "ready": bool(total_spoke_member_count or len(spoke_regions or [])) and (
                int(actual_local_section_ready_count) >= int(total_spoke_member_count or len(spoke_regions or []))
            )
        },
        "hub_profile": { "points": hub_profile_pts },
        "rotary_face_profile": { "points": rotary_face_profile },
        "guarded_section_region": guarded_section_region,
        "spokeless_section_points": spokeless_section_points,
        "spokeless_upper_profile": spokeless_upper_profile,
        "spokeless_lower_profile": spokeless_lower_profile,
        "spokeless_guarded_section_region": spokeless_guarded_section_region,
        "spokeless_guarded_section_regions": spokeless_guarded_section_regions,
        "spokeless_reference_fragments": spokeless_reference_fragments,
        "spokeless_profile_regions": spokeless_profile_regions,
        "spokeless_baseline_regions": spokeless_baseline_regions,
        "spokeless_nospoke_regions": spokeless_nospoke_regions,
        "prefer_fragmented_spokeless_base": prefer_fragmented_spokeless_base,
        "spokeless_hybrid_profile": spokeless_hybrid_profile,
        "spokeless_hybrid_region": spokeless_hybrid_region,
        "spoke_motif_topology": spoke_motif_topology,
        "lug_boss_regions": lug_boss_regions,
        "spoke_root_regions": spoke_root_regions,
        "center_core_region": center_core_region,
        "hub_bottom_groove_regions": hub_bottom_groove_regions
    }
    
    print(">>> DEBUG Hub Profile Points:", collected_features["hub_profile"]["points"])
    preview_data = {
        "orthographic_section_points": orthographic_section_points,
        "orthographic_face_profile": orthographic_face_profile,
        "rotary_face_profile": rotary_face_profile,
        "rotary_profile_stats": rotary_profile_stats,
        "preview_section_angle_deg": round(float(preview_section_angle_deg), 3),
        "spokeless_section_angle_deg": round(float(spokeless_section_angle_deg), 3) if spokeless_section_angle_deg is not None else None,
        "spokeless_section_points": spokeless_section_points,
        "spokeless_upper_profile": spokeless_upper_profile,
        "spokeless_lower_profile": spokeless_lower_profile,
        "spokeless_guarded_section_region": spokeless_guarded_section_region,
        "spokeless_guarded_section_regions": spokeless_guarded_section_regions,
        "spokeless_reference_fragments": spokeless_reference_fragments,
        "spokeless_profile_regions": spokeless_profile_regions,
        "spokeless_baseline_regions": spokeless_baseline_regions,
        "spokeless_nospoke_regions": spokeless_nospoke_regions,
        "prefer_fragmented_spokeless_base": prefer_fragmented_spokeless_base,
        "spokeless_hybrid_profile": spokeless_hybrid_profile,
        "spokeless_hybrid_region": spokeless_hybrid_region,
        "rim_profile": rim_profile_points,
        "hub_profile": hub_profile_pts,
        "spoke_regions": spoke_regions,
        "spoke_voids": spoke_voids,
        "spoke_motif_topology": spoke_motif_topology,
        "global_params": dict(collected_features["global_params"])
    }
    if return_preview:
        return collected_features, preview_data
    return collected_features

# =============================================================================
# 3. ?????? (Modeling Module)
# =============================================================================


# =============================================================================
# 4. ????????(Main Pipeline)
# =============================================================================

def run_pipeline(
    stl_path,
    output_step_path,
    preview_image_path=None,
    show_preview_window=True,
    disable_spokes=False,
):
    print("="*60)
    print("  ????????????????(Auto-Wheel Reverse Engineering)")
    print("="*60)
    normalized_output_step_path = ensure_timestamped_step_path(output_step_path)
    if normalized_output_step_path != output_step_path:
        print(f"[*] STEP output path normalized to timestamped filename: {os.path.abspath(normalized_output_step_path)}")
    output_step_path = normalized_output_step_path

    output_dir = os.path.dirname(os.path.abspath(output_step_path))
    if output_dir and (not os.path.exists(output_dir)):
        os.makedirs(output_dir, exist_ok=True)

    if preview_image_path is None:
        preview_root, _ = os.path.splitext(output_step_path)
        preview_image_path = f"{preview_root}_perception.png"
    else:
        preview_root, _ = os.path.splitext(preview_image_path)
    features = None
    preview_data = None

    try:
        _, preview_data = extract_features_from_stl(
            stl_path,
            return_preview=True,
            lightweight_preview=True
        )
    except Exception as e:
        print(f"[!] Preview perception failed: {e}")
        import traceback
        safe_print(traceback.format_exc().rstrip())
        return

    try:
        create_perception_preview(preview_data, preview_image_path, show_window=show_preview_window)
    except Exception as preview_exc:
        print(f"[!] Failed to create perception preview: {preview_exc}")
        import traceback
        safe_print(traceback.format_exc().rstrip())
        return

    has_spokeless_preview = bool(
        preview_data.get("spokeless_section_points")
        or preview_data.get("spokeless_guarded_section_region")
        or preview_data.get("spokeless_guarded_section_regions")
    )
    if has_spokeless_preview:
        try:
            create_spokeless_section_preview(
                preview_data,
                f"{preview_root}_spokeless.png",
                show_window=show_preview_window,
                derive_spoke_band_limits_fn=derive_spoke_band_limits,
                build_hybrid_profile_fn=build_hybrid_profile,
                split_profile_by_radius_gap_fn=split_profile_by_radius_gap,
            )
        except Exception as spokeless_preview_exc:
            print(f"[!] Failed to create spoke-free section preview: {spokeless_preview_exc}")
            import traceback
            safe_print(traceback.format_exc().rstrip())
            return

    # Step 1b: Full perception for modeling
    try:
        features = extract_features_from_stl(stl_path, return_preview=False)
    except Exception as e:
        print(f"[!] Perception Failed: {e}")
        import traceback
        safe_print(traceback.format_exc().rstrip())
        return

    features["disable_spokes_modeling"] = bool(disable_spokes)
    features["fast_spoke_validation_mode"] = bool(
        False if disable_spokes else features.get("fast_spoke_validation_mode", False)
    )
    try:
        features["debug_output_root"] = os.path.splitext(os.path.abspath(output_step_path))[0]
    except Exception:
        features["debug_output_root"] = ""

    try:
        features_json_path = f"{os.path.splitext(os.path.abspath(output_step_path))[0]}_features.json"

        def _features_json_default(obj):
            if isinstance(obj, np.generic):
                return obj.item()
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

        with open(features_json_path, "w", encoding="utf-8") as f:
            json.dump(features, f, ensure_ascii=False, indent=2, default=_features_json_default)
        print(f"[*] Full perception features saved: {features_json_path}")
    except Exception as features_json_exc:
        print(f"[!] Failed to save full perception features JSON: {features_json_exc}")

    strict_spoke_gate = features.get("spoke_actual_profile_gate", {})
    if (
        not disable_spokes
        and isinstance(strict_spoke_gate, dict)
        and bool(strict_spoke_gate.get("strict_actual_only", False))
        and not bool(strict_spoke_gate.get("ready", False))
    ):
        print("\n[!] Strict actual-direct spoke gate blocked modeling.")
        print(
            f"[*] Accepted spoke slice stacks: "
            f"{int(strict_spoke_gate.get('accepted_profile_count', 0))}/"
            f"{int(strict_spoke_gate.get('required_member_count', 0))}"
        )
        print(
            f"[*] Loft-ready spoke members: "
            f"{int(strict_spoke_gate.get('loft_ready_member_count', 0))}/"
            f"{int(strict_spoke_gate.get('required_member_count', 0))}"
        )
        print(
            f"[*] Actual local-section ready members: "
            f"{int(strict_spoke_gate.get('local_section_ready_count', 0))}/"
            f"{int(strict_spoke_gate.get('required_member_count', 0))}"
        )
        print("[*] Modeling skipped. Template takeover remains disabled until every spoke can enter pure actual local-section or actual-direct loft.")
        return

    # Step 2: Modeling
    code = generate_cadquery_code(features)
    
    print("\n[*] Generated CadQuery code ready.")
    print(f"[*] Generated CadQuery code length: {len(code)} characters")
    try:
        generated_code_path = f"{os.path.splitext(os.path.abspath(output_step_path))[0]}.generated.py"
        with open(generated_code_path, "w", encoding="utf-8") as generated_file:
            generated_file.write(code)
        print(f"[*] Generated CadQuery code saved: {generated_code_path}")
    except Exception as generated_save_exc:
        print(f"[!] Failed to save generated CadQuery code: {generated_save_exc}")

    def collect_export_shapes(obj):
        if obj is None:
            return []
        if isinstance(obj, cq.Workplane):
            try:
                vals = obj.vals()
            except Exception:
                vals = []
            shapes = [val for val in vals if hasattr(val, "wrapped")]
            if shapes:
                return shapes
            try:
                val = obj.val()
                if hasattr(val, "wrapped"):
                    return [val]
            except Exception:
                return []
        elif hasattr(obj, "wrapped"):
            return [obj]
        return []

    def filter_valid_export_shapes(shapes, label):
        valid_shapes = []
        for idx, shape in enumerate(shapes or []):
            try:
                if shape is None or shape.isNull():
                    print(f"[!] {label} shape {idx} discarded: null")
                    continue
                if hasattr(shape, "isValid") and (not shape.isValid()):
                    print(f"[!] {label} shape {idx} discarded: invalid")
                    continue
                valid_shapes.append(shape)
            except Exception as exc:
                print(f"[!] {label} shape {idx} validation failed: {exc}")
        return valid_shapes

    def export_step_occ(obj, output_path):
        shapes = filter_valid_export_shapes(collect_export_shapes(obj), "STEP export")
        if not shapes:
            raise ValueError("No exportable CadQuery shapes were produced.")

        export_shape = shapes[0] if len(shapes) == 1 else cq.Compound.makeCompound(shapes)
        if hasattr(export_shape, "isValid") and (not export_shape.isValid()):
            raise ValueError("Export shape is invalid and was rejected before STEP write.")
        if OCP_STEP_EXPORT_AVAILABLE:
            Interface_Static.SetCVal_s("write.step.schema", "AP214IS")
            writer = STEPControl_Writer()
            writer.Transfer(export_shape.wrapped, STEPControl_AsIs)
            status = writer.Write(output_path)
            if int(status) != int(IFSelect_RetDone):
                raise RuntimeError(f"OCC STEP export failed with status {int(status)}")
        else:
            cq.exporters.export(export_shape, output_path)
        return export_shape
    
    # Step 3: Execution
    print(f"\n[*] ????? CadQuery ?????? STEP...")
    try:
        exec_namespace = {
            "save_hub_face_groove_debug_plot": save_hub_face_groove_debug_plot,
        }
        exec(code, exec_namespace, exec_namespace)
        
        if 'result' not in exec_namespace:
            raise ValueError("Generated code did not produce a 'result' variable.")
            
        result_obj = exec_namespace['result']
        
        # Export
        export_step_occ(result_obj, output_step_path)
        print(f"[*] ???! ????????: {os.path.abspath(output_step_path)}")

        groove_debug_bodies = exec_namespace.get("hub_groove_debug_bodies", [])
        if groove_debug_bodies:
            try:
                groove_debug_path = f"{os.path.splitext(os.path.abspath(output_step_path))[0]}_hub_grooves.step"
                export_step_occ(cq.Workplane("XY").newObject(groove_debug_bodies), groove_debug_path)
                print(f"[*] Hub groove cutter STEP exported: {groove_debug_path}")
            except Exception as groove_export_exc:
                print(f"[!] Hub groove cutter STEP export failed: {groove_export_exc}")

        try:
            compare_dir = os.path.join(
                output_dir,
                f"compare_{os.path.splitext(os.path.basename(output_step_path))[0]}"
            )
            comparison_artifacts = generate_evaluation_comparison_bundle(
                stl_path,
                output_step_path,
                features_json_path,
                compare_dir,
                sample_size=30000
            )
            if comparison_artifacts:
                print(f"[*] Comparison bundle saved: {compare_dir}")
        except Exception as comparison_exc:
            print(f"[!] Comparison bundle export failed: {comparison_exc}")
        
    except Exception as e:
        print(f"[!] ????????????? {e}")
        import traceback
        safe_print(traceback.format_exc().rstrip())

if __name__ == "__main__":
    if not os.path.exists("output"):
        os.makedirs("output")
        
    import time
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    default_input_stl = "input/wheel.stl"
    default_output_step = f"output/wheel_{timestamp}.step"

    parser = argparse.ArgumentParser(description="Auto wheel reverse-engineering pipeline")
    parser.add_argument("input_stl", nargs="?", default=default_input_stl, help="Path to input STL")
    parser.add_argument("--output-step", dest="output_step", default=default_output_step, help="Path to output STEP")
    parser.add_argument("--preview-image", dest="preview_image", default=None, help="Path to saved perception preview PNG")
    parser.add_argument("--no-preview-window", action="store_true", help="Do not open the matplotlib preview window")
    parser.add_argument("--disable-spokes", action="store_true", help="Disable spoke solids and spoke-window cuts; export a stable spoke-free hub/rim baseline")
    args = parser.parse_args()

    if not os.path.exists(args.input_stl):
        print(f"[!] Input file not found: {args.input_stl}")
        print("    Usage: python stl_to_step_pipeline.py <path_to_stl>")
    else:
        run_pipeline(
            args.input_stl,
            args.output_step,
            preview_image_path=args.preview_image,
            show_preview_window=not args.no_preview_window,
            disable_spokes=args.disable_spokes,
        )


