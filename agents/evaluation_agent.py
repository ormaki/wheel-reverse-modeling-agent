import numpy as np
import trimesh
import json
import os
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import cadquery as cq

from models.agent_protocol import AgentResult, AgentTask, ArtifactRecord, TaskType


class DifferenceType(str, Enum):
    DIMENSION_MISMATCH = "dimension_mismatch"
    SHAPE_DEVIATION = "shape_deviation"
    FEATURE_MISSING = "feature_missing"
    PROFILE_ERROR = "profile_error"
    SYMMETRY_ISSUE = "symmetry_issue"
    SURFACE_QUALITY = "surface_quality"


class Severity(str, Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    ACCEPTABLE = "acceptable"


@dataclass
class DifferenceReport:
    difference_type: DifferenceType
    severity: Severity
    component: str
    description: str
    expected_value: Any
    actual_value: Any
    deviation_percent: float
    suggestion: str
    location: Optional[Tuple[float, float, float]] = None
    visualization_data: Optional[Dict] = None


@dataclass
class EvaluationResult:
    overall_score: float
    is_acceptable: bool
    differences: List[DifferenceReport]
    summary: str
    recommendations: List[str]


class EvaluationAgent:
    def __init__(self, stl_path: str, step_path: str, features_path: str, config: Optional[Dict] = None):
        self.stl_path = stl_path
        self.step_path = step_path
        self.features_path = features_path
        
        self.config = config or {}
        self.dimension_tolerance = self.config.get('dimension_tolerance', 0.05)
        self.profile_tolerance = self.config.get('profile_tolerance', 3.0)
        self.hausdorff_threshold = self.config.get('hausdorff_threshold', 5.0)
        self.eval_seed = int(self.config.get("eval_seed", 42))
        self._rng = np.random.default_rng(self.eval_seed)
        
        self.stl_mesh: Optional[trimesh.Trimesh] = None
        self.stl_vertices: Optional[np.ndarray] = None
        self.step_mesh: Optional[trimesh.Trimesh] = None
        self.step_vertices: Optional[np.ndarray] = None
        self.features: Optional[Dict] = None
        
        self.differences: List[DifferenceReport] = []
        
        self._load_data()

    def _seeded_choice(self, population_size: int, sample_size: int, seed_offset: int = 0) -> np.ndarray:
        sample_size = min(int(sample_size), int(population_size))
        if sample_size <= 0:
            return np.asarray([], dtype=int)
        rng = np.random.default_rng(int(self.eval_seed) + int(seed_offset))
        return rng.choice(int(population_size), int(sample_size), replace=False)
    
    def _load_data(self) -> None:
        print("[EvaluationAgent] 加载数据...")
        
        self.stl_mesh, self.stl_vertices = self._load_vertices_from_mesh_path(self.stl_path)
        
        if len(self.stl_vertices) > 50000:
            indices = self._seeded_choice(len(self.stl_vertices), 50000, seed_offset=11)
            self.stl_vertices = self.stl_vertices[indices]
        
        with open(self.features_path, 'r', encoding='utf-8') as f:
            self.features = json.load(f)
        
        self._load_step_vertices()
        
        print(f"[EvaluationAgent] STL顶点数: {len(self.stl_vertices)}")
        print(f"[EvaluationAgent] STEP顶点数: {len(self.step_vertices) if self.step_vertices is not None else 0}")
    
    def _load_vertices_from_mesh_path(self, mesh_path: str) -> Tuple[Optional[trimesh.Trimesh], np.ndarray]:
        loaded_mesh = trimesh.load(mesh_path)
        coerced_mesh = self._coerce_mesh(loaded_mesh)
        if coerced_mesh is None:
            raise ValueError(f"Unable to load mesh vertices from {mesh_path}")

        triangles = getattr(coerced_mesh, "triangles", None)
        if triangles is not None and len(triangles) > 0:
            vertices = np.asarray(triangles, dtype=float).reshape(-1, 3)
        else:
            vertices = np.asarray(getattr(coerced_mesh, "vertices", np.empty((0, 3))), dtype=float)
        return coerced_mesh, vertices

    def _load_mesh_vertices_from_stl(self, stl_path: str, sample_size: int) -> None:
        self.step_mesh, self.step_vertices = self._load_vertices_from_mesh_path(stl_path)

        if len(self.step_vertices) > sample_size:
            indices = self._seeded_choice(len(self.step_vertices), sample_size, seed_offset=23)
            self.step_vertices = self.step_vertices[indices]

    def _load_step_vertices(self, sample_size: int = 20000) -> None:
        try:
            step_stem, _ = os.path.splitext(self.step_path)
            temp_stl = f"{step_stem}_eval_temp.stl"
            step_model = cq.importers.importStep(self.step_path)
            step_model.export(temp_stl, tolerance=0.1, angularTolerance=0.1)
            
            self.step_mesh, self.step_vertices = self._load_vertices_from_mesh_path(temp_stl)
            
            if len(self.step_vertices) > sample_size:
                indices = self._seeded_choice(len(self.step_vertices), sample_size, seed_offset=29)
                self.step_vertices = self.step_vertices[indices]
            
            if os.path.exists(temp_stl):
                os.remove(temp_stl)
                
        except Exception as e:
            print(f"[EvaluationAgent] STEP加载失败: {e}")
            self.step_mesh = None
            self.step_vertices = None
    
    def _load_step_vertices(self, sample_size: int = 20000) -> None:
        step_stem, _ = os.path.splitext(self.step_path)
        temp_stl = f"{step_stem}_eval_temp.stl"
        max_eval_stl_bytes = int(self.config.get("max_eval_stl_bytes", 280 * 1024 * 1024))
        tolerance_schedule = self.config.get(
            "step_export_tolerances",
            [(0.8, 0.8), (1.2, 1.2), (1.8, 1.8)],
        )

        last_error = None
        for tolerance, angular_tolerance in tolerance_schedule:
            try:
                if os.path.exists(temp_stl):
                    os.remove(temp_stl)

                step_model = cq.importers.importStep(self.step_path)
                step_model.export(
                    temp_stl,
                    tolerance=float(tolerance),
                    angularTolerance=float(angular_tolerance),
                )

                if os.path.exists(temp_stl) and os.path.getsize(temp_stl) > max_eval_stl_bytes:
                    raise MemoryError(
                        f"temporary STL too large: {os.path.getsize(temp_stl) / (1024 * 1024):.1f} MiB"
                    )

                self._load_mesh_vertices_from_stl(temp_stl, sample_size)
                if self.step_vertices is not None and len(self.step_vertices) > 0:
                    return
            except Exception as exc:
                last_error = exc
                self.step_mesh = None
                self.step_vertices = None
            finally:
                if os.path.exists(temp_stl):
                    try:
                        os.remove(temp_stl)
                    except OSError:
                        pass

        fallback_candidates = []
        fallback_from_config = self.config.get("step_mesh_fallback_path")
        if fallback_from_config:
            fallback_candidates.append(str(fallback_from_config))
        fallback_candidates.append(f"{step_stem}_compare.stl")

        for fallback_path in fallback_candidates:
            if not fallback_path or not os.path.exists(fallback_path):
                continue
            try:
                if os.path.getsize(fallback_path) > max_eval_stl_bytes:
                    continue
                self._load_mesh_vertices_from_stl(fallback_path, sample_size)
                if self.step_vertices is not None and len(self.step_vertices) > 0:
                    print(f"[EvaluationAgent] STEP fallback mesh loaded: {fallback_path}")
                    return
            except Exception as exc:
                last_error = exc
                self.step_mesh = None
                self.step_vertices = None

        print(f"[EvaluationAgent] STEP鍔犺浇澶辫触: {last_error}")
        self.step_mesh = None
        self.step_vertices = None

    def _coerce_mesh(self, loaded_mesh: Any) -> Optional[trimesh.Trimesh]:
        if isinstance(loaded_mesh, trimesh.Trimesh):
            return loaded_mesh
        if isinstance(loaded_mesh, trimesh.Scene):
            meshes = [
                geometry
                for geometry in loaded_mesh.geometry.values()
                if isinstance(geometry, trimesh.Trimesh) and len(geometry.vertices) > 0
            ]
            if meshes:
                return trimesh.util.concatenate(meshes)
        return None

    def _sample_surface_points(
        self,
        tri_mesh: Optional[trimesh.Trimesh],
        fallback_vertices: Optional[np.ndarray],
        sample_size: int = 35000,
    ) -> np.ndarray:
        if tri_mesh is not None and getattr(tri_mesh, "faces", None) is not None and len(tri_mesh.faces) > 0:
            state = np.random.get_state()
            try:
                seed_offset = int(len(getattr(tri_mesh, "faces", []))) + int(sample_size)
                np.random.seed(int(self.eval_seed) + seed_offset)
                sampled_points, _ = trimesh.sample.sample_surface(tri_mesh, sample_size)
            finally:
                np.random.set_state(state)
            return np.asarray(sampled_points)

        if fallback_vertices is None or len(fallback_vertices) == 0:
            return np.zeros((0, 3))

        if len(fallback_vertices) > sample_size:
            indices = self._seeded_choice(len(fallback_vertices), sample_size, seed_offset=37)
            return np.asarray(fallback_vertices)[indices]

        return np.asarray(fallback_vertices)

    def _wheel_axis_order(self) -> Tuple[int, int, int]:
        if self.stl_mesh is not None:
            extents = np.asarray(self.stl_mesh.bounds[1] - self.stl_mesh.bounds[0], dtype=float)
        else:
            extents = np.asarray(np.ptp(self.stl_vertices, axis=0), dtype=float)

        axial_axis = int(np.argmin(extents))
        radial_axes = [axis for axis in range(3) if axis != axial_axis]
        radial_axes = sorted(radial_axes, key=lambda axis: extents[axis], reverse=True)
        return radial_axes[0], radial_axes[1], axial_axis

    def _principal_wheel_frame(self, points: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        if points is None or len(points) == 0:
            return np.zeros(3, dtype=float), np.eye(3, dtype=float)

        points = np.asarray(points, dtype=float)
        center = 0.5 * (points.min(axis=0) + points.max(axis=0))
        centered = points - center
        covariance = np.cov(centered.T)
        eigenvalues, eigenvectors = np.linalg.eigh(covariance)
        order = np.argsort(eigenvalues)[::-1]
        basis = np.asarray(eigenvectors[:, order], dtype=float)

        radial_major = basis[:, 0]
        radial_minor = basis[:, 1]
        axial_axis = basis[:, 2]
        basis = np.column_stack((radial_major, radial_minor, axial_axis))
        if np.linalg.det(basis) < 0:
            basis[:, 1] *= -1.0
        return center, basis

    def _canonicalize_wheel_points(self, points: np.ndarray) -> np.ndarray:
        if points is None or len(points) == 0:
            return np.zeros((0, 3))
        center, basis = self._principal_wheel_frame(points)
        transformed = (np.asarray(points, dtype=float) - center) @ basis
        transformed_center = 0.5 * (transformed.min(axis=0) + transformed.max(axis=0))
        return transformed - transformed_center

    def _rotate_points_about_axial(self, points: np.ndarray, angle_deg: float) -> np.ndarray:
        if points is None or len(points) == 0:
            return np.zeros((0, 3))
        rotation = self._rotation_matrix("z", np.deg2rad(float(angle_deg)))
        return np.asarray(points, dtype=float) @ rotation.T

    def _apply_axis_signs(self, points: np.ndarray, signs: Tuple[float, float, float]) -> np.ndarray:
        if points is None or len(points) == 0:
            return np.zeros((0, 3))
        signs_arr = np.asarray(signs, dtype=float).reshape(1, 3)
        transformed = np.asarray(points, dtype=float) * signs_arr
        transformed_center = 0.5 * (transformed.min(axis=0) + transformed.max(axis=0))
        return transformed - transformed_center

    def _reorder_wheel_points(self, points: np.ndarray) -> np.ndarray:
        if points is None or len(points) == 0:
            return np.zeros((0, 3))

        return self._canonicalize_wheel_points(points)

    def _rotation_matrix(self, axis: str, angle_rad: float) -> np.ndarray:
        c = np.cos(angle_rad)
        s = np.sin(angle_rad)
        if axis == "x":
            return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]], dtype=float)
        if axis == "y":
            return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]], dtype=float)
        return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=float)

    def _project_canonical_points(self, points: np.ndarray, view_mode: str) -> np.ndarray:
        points = np.asarray(points, dtype=float)
        if len(points) == 0:
            return np.zeros((0, 2))

        if view_mode == "front":
            return points[:, [0, 1]]
        if view_mode == "side":
            return points[:, [0, 2]]
        if view_mode == "iso":
            rotation = self._rotation_matrix("z", np.deg2rad(35.0)) @ self._rotation_matrix("x", np.deg2rad(-25.0))
            rotated = points @ rotation.T
            return rotated[:, [0, 1]]
        raise ValueError(f"Unsupported view mode: {view_mode}")

    def _project_points(self, points: np.ndarray, view_mode: str) -> np.ndarray:
        reordered = self._reorder_wheel_points(points)
        return self._project_canonical_points(reordered, view_mode)

    def _plot_projected_points(
        self,
        ax,
        points_2d: np.ndarray,
        color: str,
        label: str,
        point_size: float = 0.35,
        alpha: float = 0.32,
    ) -> None:
        if points_2d is None or len(points_2d) == 0:
            return
        ax.scatter(points_2d[:, 0], points_2d[:, 1], s=point_size, alpha=alpha, c=color, label=label, linewidths=0)

    def _set_projection_limits(self, ax, points_list: List[np.ndarray], zoom: float = 1.0) -> None:
        valid_points = [points for points in points_list if points is not None and len(points) > 0]
        if not valid_points:
            return

        merged = np.vstack(valid_points)
        mins = merged.min(axis=0)
        maxs = merged.max(axis=0)
        center = 0.5 * (mins + maxs)
        span = np.max(maxs - mins)
        span = max(span / max(zoom, 1e-6), 1.0)
        half_span = span * 0.52

        ax.set_xlim(center[0] - half_span, center[0] + half_span)
        ax.set_ylim(center[1] - half_span, center[1] + half_span)
        ax.set_aspect("equal")
        ax.grid(False)
        ax.set_xticks([])
        ax.set_yticks([])

    def _trim_projected_radius(self, points_2d: np.ndarray, keep_ratio: Optional[float]) -> np.ndarray:
        if keep_ratio is None or points_2d is None or len(points_2d) == 0:
            return points_2d

        radii = np.linalg.norm(points_2d, axis=1)
        max_radius = np.max(radii) if len(radii) else 0.0
        if max_radius <= 0:
            return points_2d

        keep_mask = radii <= (max_radius * keep_ratio)
        trimmed = points_2d[keep_mask]
        return trimmed if len(trimmed) > 0 else points_2d

    def _filter_canonical_radial_band(
        self,
        points: np.ndarray,
        max_ratio: float = 0.72,
        min_ratio: float = 0.0,
    ) -> np.ndarray:
        if points is None or len(points) == 0:
            return np.zeros((0, 3), dtype=float)

        pts = np.asarray(points, dtype=float)
        radii = np.linalg.norm(pts[:, :2], axis=1)
        max_radius = float(np.max(radii)) if len(radii) else 0.0
        if max_radius <= 1e-6:
            return pts

        low = max(0.0, float(min_ratio)) * max_radius
        high = max(low + 1e-6, float(max_ratio)) * max_radius
        mask = (radii >= low) & (radii <= high)
        filtered = pts[mask]
        return filtered if len(filtered) > 0 else pts

    def _bbox_center_3d(self, points: np.ndarray) -> np.ndarray:
        if points is None or len(points) == 0:
            return np.zeros(3, dtype=float)
        pts = np.asarray(points, dtype=float)
        return 0.5 * (pts.min(axis=0) + pts.max(axis=0))

    def _derive_spoke_band_limits(self, points_2d: np.ndarray) -> Tuple[float, float]:
        radii = np.linalg.norm(points_2d, axis=1) if points_2d is not None and len(points_2d) > 0 else np.zeros(0)
        if len(radii) == 0:
            return 0.0, 0.0

        global_params = self.features.get("global_params", {}) if isinstance(self.features, dict) else {}
        if not isinstance(global_params, dict):
            global_params = {}

        hub_radius = float(global_params.get("hub_radius", 0.0) or 0.0)
        window_inner_reference_r = float(global_params.get("window_inner_reference_r", 0.0) or 0.0)
        rim_max_radius = float(global_params.get("rim_max_radius", 0.0) or 0.0)

        inner_radius = window_inner_reference_r if window_inner_reference_r > 0.0 else hub_radius * 1.18
        outer_radius = rim_max_radius * 0.90 if rim_max_radius > 0.0 else 0.0

        if inner_radius <= 0.0:
            inner_radius = float(np.percentile(radii, 28.0))
        if outer_radius <= inner_radius + 5.0:
            outer_radius = float(np.percentile(radii, 82.0))
        if outer_radius <= inner_radius + 5.0:
            outer_radius = float(np.percentile(radii, 88.0))

        return float(inner_radius), float(outer_radius)

    def _filter_spoke_band(self, points_2d: np.ndarray) -> np.ndarray:
        if points_2d is None or len(points_2d) == 0:
            return points_2d

        inner_radius, outer_radius = self._derive_spoke_band_limits(points_2d)
        if outer_radius <= inner_radius + 1.0:
            return points_2d

        radii = np.linalg.norm(points_2d, axis=1)
        band_mask = (radii >= inner_radius) & (radii <= outer_radius)
        trimmed = points_2d[band_mask]
        return trimmed if len(trimmed) > 0 else points_2d

    def _estimate_spoke_sector_angle(self, stl_band: np.ndarray, step_band: np.ndarray, bins: int = 72) -> float:
        sources = [pts for pts in (stl_band, step_band) if pts is not None and len(pts) > 0]
        if not sources:
            return 0.0

        edges = np.linspace(-180.0, 180.0, max(12, int(bins)) + 1)

        def _hist(points: np.ndarray) -> np.ndarray:
            if points is None or len(points) == 0:
                return np.zeros(len(edges) - 1, dtype=float)
            angles = np.degrees(np.arctan2(points[:, 1], points[:, 0]))
            hist, _ = np.histogram(angles, bins=edges)
            return hist.astype(float)

        stl_hist = _hist(stl_band)
        step_hist = _hist(step_band)
        mismatch = np.abs(stl_hist - step_hist)
        density = stl_hist + step_hist
        score = mismatch + (0.15 * density)
        best_idx = int(np.argmax(score)) if len(score) else 0
        return float(0.5 * (edges[best_idx] + edges[best_idx + 1]))

    def _estimate_axial_rotation_offset(self, stl_band: np.ndarray, step_band: np.ndarray, bins: int = 180) -> float:
        if stl_band is None or step_band is None or len(stl_band) == 0 or len(step_band) == 0:
            return 0.0

        edges = np.linspace(-180.0, 180.0, max(36, int(bins)) + 1)

        def _hist(points: np.ndarray) -> np.ndarray:
            angles = np.degrees(np.arctan2(points[:, 1], points[:, 0]))
            hist, _ = np.histogram(angles, bins=edges)
            hist = hist.astype(float)
            total = np.sum(hist)
            return hist / total if total > 0 else hist

        stl_hist = _hist(stl_band)
        step_hist = _hist(step_band)
        if len(stl_hist) == 0 or len(step_hist) == 0:
            return 0.0

        best_shift = 0
        best_score = -np.inf
        for shift in range(len(step_hist)):
            shifted = np.roll(step_hist, shift)
            score = float(np.dot(stl_hist, shifted))
            if score > best_score:
                best_score = score
                best_shift = shift

        return float(best_shift * (360.0 / len(step_hist)))

    def _projection_overlap_score(self, ref_points: np.ndarray, cand_points: np.ndarray, bins: int = 120) -> float:
        if ref_points is None or cand_points is None or len(ref_points) == 0 or len(cand_points) == 0:
            return -1.0

        merged = np.vstack([ref_points, cand_points])
        mins = merged.min(axis=0)
        maxs = merged.max(axis=0)
        center = 0.5 * (mins + maxs)
        span = float(max(np.max(maxs - mins), 1.0))

        ref_norm = (ref_points - center) / span
        cand_norm = (cand_points - center) / span
        hist_range = [[-0.6, 0.6], [-0.6, 0.6]]

        hist_ref, _, _ = np.histogram2d(ref_norm[:, 0], ref_norm[:, 1], bins=bins, range=hist_range)
        hist_cand, _, _ = np.histogram2d(cand_norm[:, 0], cand_norm[:, 1], bins=bins, range=hist_range)
        if hist_ref.sum() > 0:
            hist_ref = hist_ref / hist_ref.sum()
        if hist_cand.sum() > 0:
            hist_cand = hist_cand / hist_cand.sum()
        return float(np.minimum(hist_ref, hist_cand).sum())

    def _align_step_to_stl_visual(self, stl_points: np.ndarray, step_points: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        if stl_points is None or step_points is None or len(stl_points) == 0 or len(step_points) == 0:
            return step_points, {"axial_rotation_deg": 0.0, "axis_signs": (1.0, 1.0, 1.0), "score": -1.0}

        stl_front = self._project_canonical_points(stl_points, "front")
        stl_front_band = self._filter_spoke_band(stl_front)
        stl_side = self._project_canonical_points(stl_points, "side")
        stl_iso = self._project_canonical_points(stl_points, "iso")
        stl_focus = self._filter_canonical_radial_band(stl_points, max_ratio=0.74, min_ratio=0.06)
        stl_focus_side = self._project_canonical_points(stl_focus, "side")
        stl_focus_front = self._project_canonical_points(stl_focus, "front")
        stl_focus_center = self._bbox_center_3d(stl_focus)

        best_points = step_points
        best_meta = {
            "axial_rotation_deg": 0.0,
            "axis_signs": (1.0, 1.0, 1.0),
            "score": -1.0,
            "translation": (0.0, 0.0, 0.0),
        }

        sign_candidates = [
            (1.0, 1.0, 1.0),
            (1.0, 1.0, -1.0),
            (1.0, -1.0, 1.0),
            (1.0, -1.0, -1.0),
            (-1.0, 1.0, 1.0),
            (-1.0, 1.0, -1.0),
            (-1.0, -1.0, 1.0),
            (-1.0, -1.0, -1.0),
        ]

        for signs in sign_candidates:
            signed_points = self._apply_axis_signs(step_points, signs)
            step_front_pre = self._project_canonical_points(signed_points, "front")
            step_front_band_pre = self._filter_spoke_band(step_front_pre)
            axial_rotation_deg = self._estimate_axial_rotation_offset(stl_front_band, step_front_band_pre)
            rotated_points = self._rotate_points_about_axial(signed_points, axial_rotation_deg)
            step_focus = self._filter_canonical_radial_band(rotated_points, max_ratio=0.74, min_ratio=0.06)
            translation = stl_focus_center - self._bbox_center_3d(step_focus)
            translated_points = rotated_points + translation
            translated_focus = self._filter_canonical_radial_band(translated_points, max_ratio=0.74, min_ratio=0.06)

            step_front = self._project_canonical_points(translated_points, "front")
            step_front_band = self._filter_spoke_band(step_front)
            step_side = self._project_canonical_points(translated_points, "side")
            step_iso = self._project_canonical_points(translated_points, "iso")
            step_focus_side = self._project_canonical_points(translated_focus, "side")
            step_focus_front = self._project_canonical_points(translated_focus, "front")

            score = (
                1.35 * self._projection_overlap_score(stl_front_band, step_front_band, bins=140)
                + 1.35 * self._projection_overlap_score(stl_focus_side, step_focus_side, bins=130)
                + 0.95 * self._projection_overlap_score(stl_side, step_side, bins=120)
                + 0.70 * self._projection_overlap_score(stl_focus_front, step_focus_front, bins=130)
                + 0.40 * self._projection_overlap_score(stl_iso, step_iso, bins=120)
            )
            if score > best_meta["score"]:
                best_points = translated_points
                best_meta = {
                    "axial_rotation_deg": float(axial_rotation_deg),
                    "axis_signs": signs,
                    "score": float(score),
                    "translation": tuple(float(v) for v in translation),
                }

        return best_points, best_meta

    def _filter_spoke_sector(self, points_2d: np.ndarray, center_angle_deg: float, half_span_deg: float = 18.0) -> np.ndarray:
        if points_2d is None or len(points_2d) == 0:
            return points_2d

        angles = np.degrees(np.arctan2(points_2d[:, 1], points_2d[:, 0]))
        deltas = np.abs((angles - float(center_angle_deg) + 180.0) % 360.0 - 180.0)
        sector_mask = deltas <= float(half_span_deg)
        trimmed = points_2d[sector_mask]
        return trimmed if len(trimmed) > 0 else points_2d

    def _rotate_2d_points(self, points_2d: np.ndarray, angle_deg: float) -> np.ndarray:
        if points_2d is None or len(points_2d) == 0:
            return np.zeros((0, 2), dtype=float)
        theta = np.deg2rad(float(angle_deg))
        rotation = np.array(
            [[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]],
            dtype=float,
        )
        return np.asarray(points_2d, dtype=float) @ rotation.T

    def _expected_spoke_count(self) -> int:
        spokes = self.features.get("spokes", {}) if isinstance(self.features, dict) else {}
        if not isinstance(spokes, dict):
            return 10
        count = int(spokes.get("count", 0) or 0)
        return count if count >= 3 else 10

    def _smooth_circular_histogram(self, values: np.ndarray, radius: int = 2) -> np.ndarray:
        hist = np.asarray(values, dtype=float)
        if len(hist) == 0 or radius <= 0:
            return hist
        kernel = np.ones((2 * radius) + 1, dtype=float)
        kernel /= np.sum(kernel)
        padded = np.concatenate([hist[-radius:], hist, hist[:radius]])
        smoothed = np.convolve(padded, kernel, mode="same")
        return smoothed[radius:-radius]

    def _estimate_single_spoke_angle(self, stl_band: np.ndarray, step_band: np.ndarray, bins: Optional[int] = None) -> float:
        sources = [pts for pts in (stl_band, step_band) if pts is not None and len(pts) > 0]
        if not sources:
            return 0.0

        spoke_count = self._expected_spoke_count()
        bins = int(bins or max(180, spoke_count * 48))
        edges = np.linspace(-180.0, 180.0, bins + 1)

        def _hist(points: np.ndarray) -> np.ndarray:
            if points is None or len(points) == 0:
                return np.zeros(len(edges) - 1, dtype=float)
            angles = np.degrees(np.arctan2(points[:, 1], points[:, 0]))
            hist, _ = np.histogram(angles, bins=edges)
            return hist.astype(float)

        stl_hist = self._smooth_circular_histogram(_hist(stl_band), radius=2)
        step_hist = self._smooth_circular_histogram(_hist(step_band), radius=2)
        combined = stl_hist + step_hist
        if len(combined) == 0:
            return 0.0

        peak_indices = []
        for idx in range(len(combined)):
            prev_idx = (idx - 1) % len(combined)
            next_idx = (idx + 1) % len(combined)
            if combined[idx] >= combined[prev_idx] and combined[idx] > combined[next_idx]:
                peak_indices.append(idx)

        if peak_indices:
            best_idx = max(peak_indices, key=lambda idx: combined[idx])
        else:
            best_idx = int(np.argmax(combined))

        return float(0.5 * (edges[best_idx] + edges[best_idx + 1]))

    def _extract_single_spoke_closeup(
        self,
        points_2d: np.ndarray,
        center_angle_deg: float,
        half_span_deg: float = 9.0,
        radial_expand: float = 0.08,
    ) -> np.ndarray:
        if points_2d is None or len(points_2d) == 0:
            return np.zeros((0, 2), dtype=float)

        inner_radius, outer_radius = self._derive_spoke_band_limits(points_2d)
        radii = np.linalg.norm(points_2d, axis=1)
        angles = np.degrees(np.arctan2(points_2d[:, 1], points_2d[:, 0]))
        deltas = np.abs((angles - float(center_angle_deg) + 180.0) % 360.0 - 180.0)

        inner_limit = max(0.0, inner_radius * (1.0 - radial_expand))
        outer_limit = outer_radius * (1.0 + radial_expand)
        mask = (deltas <= float(half_span_deg)) & (radii >= inner_limit) & (radii <= outer_limit)
        selected = points_2d[mask]
        if len(selected) == 0:
            mask = deltas <= float(half_span_deg * 1.5)
            selected = points_2d[mask]
        if len(selected) == 0:
            selected = points_2d

        rotated = self._rotate_2d_points(selected, -center_angle_deg)
        if len(rotated) == 0:
            return rotated

        q_low = np.percentile(rotated, 1.0, axis=0)
        q_high = np.percentile(rotated, 99.0, axis=0)
        bbox_mask = np.all((rotated >= q_low) & (rotated <= q_high), axis=1)
        trimmed = rotated[bbox_mask]
        return trimmed if len(trimmed) > 0 else rotated

    def _extract_single_spoke_points_3d(
        self,
        points_3d: np.ndarray,
        center_angle_deg: float,
        half_span_deg: float = 9.0,
        radial_expand: float = 0.10,
    ) -> np.ndarray:
        if points_3d is None or len(points_3d) == 0:
            return np.zeros((0, 3), dtype=float)

        pts = np.asarray(points_3d, dtype=float)
        front = self._project_canonical_points(pts, "front")
        inner_radius, outer_radius = self._derive_spoke_band_limits(front)
        radii = np.linalg.norm(pts[:, :2], axis=1)
        angles = np.degrees(np.arctan2(pts[:, 1], pts[:, 0]))
        deltas = np.abs((angles - float(center_angle_deg) + 180.0) % 360.0 - 180.0)

        inner_limit = max(0.0, inner_radius * (1.0 - radial_expand))
        outer_limit = outer_radius * (1.0 + radial_expand)
        mask = (deltas <= float(half_span_deg)) & (radii >= inner_limit) & (radii <= outer_limit)
        selected = pts[mask]

        if len(selected) < 80:
            expanded_mask = (
                deltas <= float(half_span_deg * 1.55)
            ) & (
                radii >= max(0.0, inner_radius * (1.0 - (radial_expand * 1.8)))
            ) & (
                radii <= outer_radius * (1.0 + (radial_expand * 1.8))
            )
            selected = pts[expanded_mask]

        return selected if len(selected) > 0 else pts

    def _project_single_spoke_closeup(
        self,
        points_3d: np.ndarray,
        center_angle_deg: float,
        view_mode: str,
    ) -> np.ndarray:
        selected = self._extract_single_spoke_points_3d(points_3d, center_angle_deg)
        if selected is None or len(selected) == 0:
            return np.zeros((0, 2), dtype=float)

        rotated = self._rotate_points_about_axial(selected, -center_angle_deg)
        projected = self._project_canonical_points(rotated, view_mode)
        if projected is None or len(projected) == 0:
            return np.zeros((0, 2), dtype=float)

        q_low = np.percentile(projected, 1.0, axis=0)
        q_high = np.percentile(projected, 99.0, axis=0)
        bbox_mask = np.all((projected >= q_low) & (projected <= q_high), axis=1)
        trimmed = projected[bbox_mask]
        return trimmed if len(trimmed) > 0 else projected

    def _orient_closeup_pair(self, ref_points_2d: np.ndarray, cand_points_2d: np.ndarray) -> Tuple[np.ndarray, np.ndarray, float]:
        valid_sets = [pts for pts in (ref_points_2d, cand_points_2d) if pts is not None and len(pts) > 0]
        if not valid_sets:
            return (
                np.zeros((0, 2), dtype=float),
                np.zeros((0, 2), dtype=float),
                0.0,
            )

        merged = np.vstack(valid_sets)
        common_center = 0.5 * (merged.min(axis=0) + merged.max(axis=0))

        ref_centered = np.asarray(ref_points_2d, dtype=float) - common_center if ref_points_2d is not None and len(ref_points_2d) > 0 else np.zeros((0, 2), dtype=float)
        cand_centered = np.asarray(cand_points_2d, dtype=float) - common_center if cand_points_2d is not None and len(cand_points_2d) > 0 else np.zeros((0, 2), dtype=float)

        basis_source = ref_centered if len(ref_centered) >= 8 else (cand_centered if len(cand_centered) >= 8 else merged - common_center)
        covariance = np.cov(basis_source.T)
        eigenvalues, eigenvectors = np.linalg.eigh(covariance)
        major_axis = np.asarray(eigenvectors[:, int(np.argmax(eigenvalues))], dtype=float)
        angle_deg = float(np.degrees(np.arctan2(major_axis[1], major_axis[0])))

        ref_rotated = self._rotate_2d_points(ref_centered, -angle_deg)
        cand_rotated = self._rotate_2d_points(cand_centered, -angle_deg)

        span_ref = ref_rotated.max(axis=0) - ref_rotated.min(axis=0) if len(ref_rotated) > 0 else np.zeros(2, dtype=float)
        span_cand = cand_rotated.max(axis=0) - cand_rotated.min(axis=0) if len(cand_rotated) > 0 else np.zeros(2, dtype=float)
        span = np.maximum(span_ref, span_cand)
        if span[1] > span[0]:
            ref_rotated = self._rotate_2d_points(ref_rotated, -90.0)
            cand_rotated = self._rotate_2d_points(cand_rotated, -90.0)
            angle_deg += 90.0

        return ref_rotated, cand_rotated, angle_deg

    def _align_point_clouds(self) -> Tuple[np.ndarray, np.ndarray]:
        stl_center = self.stl_vertices.mean(axis=0)
        step_center = self.step_vertices.mean(axis=0)
        
        stl_aligned = self.stl_vertices - stl_center
        step_aligned = self.step_vertices - step_center
        
        return stl_aligned, step_aligned
    
    def evaluate_dimensions(self) -> List[DifferenceReport]:
        print("\n[EvaluationAgent] 评估尺寸差异...")
        reports = []
        
        stl_bbox = self.stl_mesh.bounds
        stl_dims = stl_bbox[1] - stl_bbox[0]
        
        expected_diameter = self.features.get('overall_diameter', 0)
        expected_width = self.features.get('overall_width', 0)
        
        actual_diameter = max(stl_dims[0], stl_dims[1])
        actual_width = stl_dims[2]
        
        diameter_diff = abs(actual_diameter - expected_diameter) / max(expected_diameter, 1) * 100
        if diameter_diff > self.dimension_tolerance * 100:
            severity = Severity.CRITICAL if diameter_diff > 10 else Severity.MAJOR
            reports.append(DifferenceReport(
                difference_type=DifferenceType.DIMENSION_MISMATCH,
                severity=severity,
                component="整体",
                description=f"整体直径偏差 {diameter_diff:.1f}%",
                expected_value=f"{expected_diameter:.2f} mm",
                actual_value=f"{actual_diameter:.2f} mm",
                deviation_percent=diameter_diff,
                suggestion="调整感知智能体的整体尺寸检测算法，检查旋转轴识别是否正确"
            ))
        
        width_diff = abs(actual_width - expected_width) / max(expected_width, 1) * 100
        if width_diff > self.dimension_tolerance * 100:
            severity = Severity.MAJOR if width_diff > 10 else Severity.MINOR
            reports.append(DifferenceReport(
                difference_type=DifferenceType.DIMENSION_MISMATCH,
                severity=severity,
                component="整体",
                description=f"整体宽度偏差 {width_diff:.1f}%",
                expected_value=f"{expected_width:.2f} mm",
                actual_value=f"{actual_width:.2f} mm",
                deviation_percent=width_diff,
                suggestion="检查轴向尺寸提取逻辑，确保使用正确的旋转轴方向"
            ))
        
        hub = self.features.get('hub', {})
        hub_outer = hub.get('outer_diameter', 0)
        hub_height = hub.get('height', 0)
        
        rim = self.features.get('rim', {})
        rim_outer = rim.get('outer_diameter', 0)
        rim_width = rim.get('width', 0)
        
        if rim_outer > 0 and hub_outer > 0:
            expected_ratio = rim_outer / hub_outer
            actual_ratio = actual_diameter / (hub_outer if hub_outer > 0 else 1)
            ratio_diff = abs(expected_ratio - actual_ratio) / expected_ratio * 100
            
            if ratio_diff > 5:
                reports.append(DifferenceReport(
                    difference_type=DifferenceType.DIMENSION_MISMATCH,
                    severity=Severity.MAJOR,
                    component="轮毂/轮辋比例",
                    description=f"轮毂与轮辋直径比例偏差 {ratio_diff:.1f}%",
                    expected_value=f"比例 {expected_ratio:.2f}",
                    actual_value=f"比例 {actual_ratio:.2f}",
                    deviation_percent=ratio_diff,
                    suggestion="重新检测轮毂区域边界，调整轮辋起始点识别阈值"
                ))
        
        self.differences.extend(reports)
        return reports
    
    def evaluate_profile(self) -> List[DifferenceReport]:
        print("\n[EvaluationAgent] 评估轮廓差异...")
        reports = []
        
        main_profile = self.features.get('rim', {}).get('main_profile', [])
        if not main_profile:
            reports.append(DifferenceReport(
                difference_type=DifferenceType.FEATURE_MISSING,
                severity=Severity.CRITICAL,
                component="轮辋轮廓",
                description="缺少主轮廓数据",
                expected_value="轮廓点列表",
                actual_value="空",
                deviation_percent=100,
                suggestion="确保感知智能体正确提取并保存轮廓数据"
            ))
            self.differences.extend(reports)
            return reports
        
        stl_center = self.stl_vertices.mean(axis=0)
        stl_relative = self.stl_vertices - stl_center
        
        profile_2d = np.array([[p['radius'], p['height']] for p in main_profile])
        stl_2d = stl_relative[:, [0, 2]]
        
        distances = []
        for p in profile_2d:
            point_distances = np.linalg.norm(stl_2d - p, axis=1)
            distances.append(np.min(point_distances))
        
        distances = np.array(distances)
        avg_distance = distances.mean()
        max_distance = distances.max()
        
        if avg_distance > self.profile_tolerance:
            severity = Severity.CRITICAL if avg_distance > 10 else Severity.MAJOR
            reports.append(DifferenceReport(
                difference_type=DifferenceType.PROFILE_ERROR,
                severity=severity,
                component="轮辋轮廓",
                description=f"轮廓平均偏差 {avg_distance:.2f} mm，最大偏差 {max_distance:.2f} mm",
                expected_value=f"偏差 < {self.profile_tolerance} mm",
                actual_value=f"平均偏差 {avg_distance:.2f} mm",
                deviation_percent=avg_distance / self.profile_tolerance * 100,
                suggestion="增加轮廓采样密度，优化特征点检测算法，考虑使用更精细的切片策略",
                visualization_data={
                    'profile_points': profile_2d.tolist(),
                    'distances': distances.tolist(),
                    'avg_distance': avg_distance,
                    'max_distance': max_distance
                }
            ))
        
        poor_points = sum(1 for d in distances if d > 5.0)
        if poor_points > len(distances) * 0.1:
            poor_indices = [i for i, d in enumerate(distances) if d > 5.0]
            reports.append(DifferenceReport(
                difference_type=DifferenceType.SHAPE_DEVIATION,
                severity=Severity.MAJOR,
                component="轮辋细节",
                description=f"{poor_points}个轮廓点偏差超过5mm ({poor_points/len(distances)*100:.1f}%)",
                expected_value="偏差点 < 10%",
                actual_value=f"偏差点 {poor_points/len(distances)*100:.1f}%",
                deviation_percent=poor_points/len(distances)*100,
                suggestion="检查这些区域的特征点提取，可能存在转角或凹陷未被正确捕捉",
                visualization_data={'poor_indices': poor_indices[:20]}
            ))
        
        self.differences.extend(reports)
        return reports
    
    def evaluate_hausdorff(self) -> List[DifferenceReport]:
        print("\n[EvaluationAgent] 评估豪斯多夫距离...")
        reports = []
        
        if self.step_vertices is None:
            reports.append(DifferenceReport(
                difference_type=DifferenceType.FEATURE_MISSING,
                severity=Severity.CRITICAL,
                component="STEP模型",
                description="无法加载STEP模型顶点",
                expected_value="有效顶点数据",
                actual_value="None",
                deviation_percent=100,
                suggestion="检查STEP文件是否正确生成"
            ))
            self.differences.extend(reports)
            return reports
        
        stl_aligned, step_aligned = self._align_point_clouds()
        
        forward_distances = []
        sample_size = min(5000, len(stl_aligned))
        sample_indices = self._seeded_choice(len(stl_aligned), sample_size, seed_offset=41)
        
        for idx in sample_indices:
            point = stl_aligned[idx]
            distances = np.linalg.norm(step_aligned - point, axis=1)
            forward_distances.append(np.min(distances))
        
        backward_distances = []
        sample_size = min(5000, len(step_aligned))
        sample_indices = self._seeded_choice(len(step_aligned), sample_size, seed_offset=43)
        
        for idx in sample_indices:
            point = step_aligned[idx]
            distances = np.linalg.norm(stl_aligned - point, axis=1)
            backward_distances.append(np.min(distances))
        
        hausdorff = max(np.max(forward_distances), np.max(backward_distances))
        avg_forward = np.mean(forward_distances)
        avg_backward = np.mean(backward_distances)
        avg_hausdorff = (avg_forward + avg_backward) / 2
        
        print(f"  豪斯多夫距离: {hausdorff:.3f} mm")
        print(f"  平均前向距离: {avg_forward:.3f} mm")
        print(f"  平均反向距离: {avg_backward:.3f} mm")
        
        if hausdorff > self.hausdorff_threshold:
            severity = Severity.CRITICAL if hausdorff > 20 else Severity.MAJOR
            reports.append(DifferenceReport(
                difference_type=DifferenceType.SHAPE_DEVIATION,
                severity=severity,
                component="整体模型",
                description=f"豪斯多夫距离 {hausdorff:.2f} mm 超过阈值 {self.hausdorff_threshold} mm",
                expected_value=f"< {self.hausdorff_threshold} mm",
                actual_value=f"{hausdorff:.2f} mm",
                deviation_percent=hausdorff / self.hausdorff_threshold * 100,
                suggestion="整体形状存在较大偏差，建议检查：1)旋转轴识别 2)轮廓提取 3)建模参数",
                visualization_data={
                    'hausdorff': hausdorff,
                    'avg_forward': avg_forward,
                    'avg_backward': avg_backward,
                    'forward_distances': forward_distances[:1000],
                    'backward_distances': backward_distances[:1000]
                }
            ))
        
        if avg_hausdorff > 3.0:
            reports.append(DifferenceReport(
                difference_type=DifferenceType.SHAPE_DEVIATION,
                severity=Severity.MAJOR,
                component="整体模型",
                description=f"平均形状偏差 {avg_hausdorff:.2f} mm 较大",
                expected_value="< 3.0 mm",
                actual_value=f"{avg_hausdorff:.2f} mm",
                deviation_percent=avg_hausdorff / 3.0 * 100,
                suggestion="模型整体存在系统性偏差，可能需要调整建模策略或特征提取参数"
            ))
        
        self.differences.extend(reports)
        return reports
    
    def evaluate_spokes(self) -> List[DifferenceReport]:
        print("\n[EvaluationAgent] 评估辐条...")
        reports = []
        
        spokes = self.features.get('spokes', {})
        spoke_count = spokes.get('count', 0)
        spoke_type = spokes.get('type', 'unknown')
        
        if spoke_count < 3:
            reports.append(DifferenceReport(
                difference_type=DifferenceType.FEATURE_MISSING,
                severity=Severity.CRITICAL,
                component="辐条",
                description=f"辐条数量异常: {spoke_count}",
                expected_value=">= 3",
                actual_value=str(spoke_count),
                deviation_percent=100,
                suggestion="辐条检测算法需要优化，检查角度分布分析逻辑"
            ))
        
        stl_center = self.stl_vertices.mean(axis=0)
        centered = self.stl_vertices - stl_center
        
        heights = centered[:, 2]
        mid_height = (heights.max() + heights.min()) / 2
        height_tolerance = (heights.max() - heights.min()) * 0.2
        
        mid_slice = centered[np.abs(heights - mid_height) < height_tolerance]
        
        if len(mid_slice) > 100:
            xy_points = mid_slice[:, :2]
            angles = np.arctan2(xy_points[:, 1], xy_points[:, 0])
            
            num_bins = 72
            hist, _ = np.histogram(angles, bins=num_bins, range=(-np.pi, np.pi))
            
            peaks = []
            for i in range(1, len(hist) - 1):
                if hist[i] > hist[i-1] and hist[i] > hist[i+1] and hist[i] > hist.mean():
                    peaks.append(i)
            
            detected_spokes = len(peaks)
            
            if abs(detected_spokes - spoke_count) > 1:
                reports.append(DifferenceReport(
                    difference_type=DifferenceType.SHAPE_DEVIATION,
                    severity=Severity.MAJOR,
                    component="辐条",
                    description=f"辐条数量不匹配: 检测到 {detected_spokes}，提取 {spoke_count}",
                    expected_value=str(spoke_count),
                    actual_value=str(detected_spokes),
                    deviation_percent=abs(detected_spokes - spoke_count) / max(spoke_count, 1) * 100,
                    suggestion="辐条检测算法可能误判，建议调整峰值检测阈值"
                ))
        
        self.differences.extend(reports)
        return reports
    
    def evaluate_symmetry(self) -> List[DifferenceReport]:
        print("\n[EvaluationAgent] 评估对称性...")
        reports = []
        
        rotation_axis = self.features.get('rotation_axis', [0, 0, 1])
        
        stl_center = self.stl_vertices.mean(axis=0)
        centered = self.stl_vertices - stl_center
        
        num_sections = 8
        section_errors = []
        
        for i in range(num_sections):
            angle1 = 2 * np.pi * i / num_sections
            angle2 = 2 * np.pi * (i + 1) / num_sections
            
            mask1 = self._get_angle_section_mask(centered, angle1, angle1 + np.pi/4)
            mask2 = self._get_angle_section_mask(centered, angle2, angle2 + np.pi/4)
            
            if mask1.sum() > 100 and mask2.sum() > 100:
                section1 = centered[mask1]
                section2 = centered[mask2]
                
                radii1 = np.linalg.norm(section1[:, :2], axis=1)
                radii2 = np.linalg.norm(section2[:, :2], axis=1)
                
                mean_diff = abs(radii1.mean() - radii2.mean())
                section_errors.append(mean_diff)
        
        if section_errors:
            avg_error = np.mean(section_errors)
            max_error = np.max(section_errors)
            
            if max_error > 5.0:
                reports.append(DifferenceReport(
                    difference_type=DifferenceType.SYMMETRY_ISSUE,
                    severity=Severity.MAJOR,
                    component="整体对称性",
                    description=f"旋转对称性偏差较大: 最大 {max_error:.2f} mm",
                    expected_value="< 5.0 mm",
                    actual_value=f"最大 {max_error:.2f} mm",
                    deviation_percent=max_error / 5.0 * 100,
                    suggestion="模型存在不对称问题，检查旋转轴是否正确识别"
                ))
        
        self.differences.extend(reports)
        return reports
    
    def _get_angle_section_mask(self, points: np.ndarray, angle_start: float, angle_end: float) -> np.ndarray:
        angles = np.arctan2(points[:, 1], points[:, 0])
        
        if angle_end > np.pi:
            mask = (angles >= angle_start) | (angles < angle_end - 2*np.pi)
        else:
            mask = (angles >= angle_start) & (angles < angle_end)
        
        return mask
    
    def generate_feedback(self) -> Dict[str, Any]:
        print("\n[EvaluationAgent] 生成反馈报告...")
        
        critical_issues = [d for d in self.differences if d.severity == Severity.CRITICAL]
        major_issues = [d for d in self.differences if d.severity == Severity.MAJOR]
        minor_issues = [d for d in self.differences if d.severity == Severity.MINOR]
        
        perception_adjustments = []
        modeling_adjustments = []
        
        for diff in self.differences:
            if diff.difference_type in [DifferenceType.DIMENSION_MISMATCH, DifferenceType.PROFILE_ERROR]:
                perception_adjustments.append({
                    'component': diff.component,
                    'issue': diff.description,
                    'suggestion': diff.suggestion,
                    'priority': 'high' if diff.severity in [Severity.CRITICAL, Severity.MAJOR] else 'medium'
                })
            
            if diff.difference_type in [DifferenceType.SHAPE_DEVIATION, DifferenceType.SYMMETRY_ISSUE]:
                modeling_adjustments.append({
                    'component': diff.component,
                    'issue': diff.description,
                    'suggestion': diff.suggestion,
                    'priority': 'high' if diff.severity in [Severity.CRITICAL, Severity.MAJOR] else 'medium'
                })
        
        overall_score = 100 - (len(critical_issues) * 30 + len(major_issues) * 10 + len(minor_issues) * 3)
        overall_score = max(0, overall_score)
        
        feedback = {
            'overall_score': overall_score,
            'is_acceptable': len(critical_issues) == 0 and len(major_issues) <= 2,
            'summary': self._generate_summary(critical_issues, major_issues, minor_issues),
            'statistics': {
                'critical_count': len(critical_issues),
                'major_count': len(major_issues),
                'minor_count': len(minor_issues),
                'total_issues': len(self.differences)
            },
            'perception_adjustments': perception_adjustments,
            'modeling_adjustments': modeling_adjustments,
            'detailed_differences': [
                {
                    'type': d.difference_type.value,
                    'severity': d.severity.value,
                    'component': d.component,
                    'description': d.description,
                    'expected': d.expected_value,
                    'actual': d.actual_value,
                    'deviation_percent': d.deviation_percent,
                    'suggestion': d.suggestion
                }
                for d in self.differences
            ]
        }
        
        return feedback
    
    def _generate_summary(self, critical: List, major: List, minor: List) -> str:
        lines = []
        
        if critical:
            lines.append(f"[CRITICAL] 发现 {len(critical)} 个严重问题:")
            for c in critical:
                lines.append(f"   - {c.component}: {c.description}")
        
        if major:
            lines.append(f"[MAJOR] 发现 {len(major)} 个主要问题:")
            for m in major:
                lines.append(f"   - {m.component}: {m.description}")
        
        if minor:
            lines.append(f"[MINOR] 发现 {len(minor)} 个轻微问题")
        
        if not lines:
            lines.append("[OK] 模型质量良好，未发现明显问题")
        
        return "\n".join(lines)
    
    def visualize_comparison(self, output_path: str) -> str:
        print("\n[EvaluationAgent] 生成对比可视化...")
        
        fig, axes = plt.subplots(2, 2, figsize=(14, 12))
        
        stl_center = self.stl_vertices.mean(axis=0)
        stl_relative = self.stl_vertices - stl_center
        
        ax1 = axes[0, 0]
        ax1.scatter(stl_relative[:, 0], stl_relative[:, 2], s=0.1, alpha=0.3, label='STL', c='blue')
        ax1.set_xlabel('X (mm)')
        ax1.set_ylabel('Z (mm)')
        ax1.set_title('STL侧视图 (X-Z平面)')
        ax1.legend()
        ax1.set_aspect('equal')
        
        ax2 = axes[0, 1]
        main_profile = self.features.get('rim', {}).get('main_profile', [])
        if main_profile:
            profile_2d = np.array([[p['radius'], p['height']] for p in main_profile])
            ax2.scatter(profile_2d[:, 0], profile_2d[:, 1], s=1, c='red', label='提取轮廓')
            ax2.scatter(stl_relative[:, 0], stl_relative[:, 2], s=0.05, alpha=0.1, c='blue', label='STL')
            ax2.set_xlabel('半径 (mm)')
            ax2.set_ylabel('高度 (mm)')
            ax2.set_title('轮廓对比')
            ax2.legend()
        
        ax3 = axes[1, 0]
        if self.step_vertices is not None:
            step_center = self.step_vertices.mean(axis=0)
            step_relative = self.step_vertices - step_center
            ax3.scatter(step_relative[:, 0], step_relative[:, 2], s=0.1, alpha=0.3, label='STEP', c='green')
        ax3.set_xlabel('X (mm)')
        ax3.set_ylabel('Z (mm)')
        ax3.set_title('STEP模型侧视图 (X-Z平面)')
        ax3.legend()
        ax3.set_aspect('equal')
        
        ax4 = axes[1, 1]
        if self.step_vertices is not None and main_profile:
            ax4.scatter(stl_relative[:, 0], stl_relative[:, 2], s=0.05, alpha=0.3, label='STL', c='blue')
            step_center = self.step_vertices.mean(axis=0)
            step_relative = self.step_vertices - step_center
            ax4.scatter(step_relative[:, 0], step_relative[:, 2], s=0.05, alpha=0.3, label='STEP', c='green')
            ax4.set_xlabel('X (mm)')
            ax4.set_ylabel('Z (mm)')
            ax4.set_title('STL vs STEP 叠加对比')
            ax4.legend()
            ax4.set_aspect('equal')
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        print(f"[EvaluationAgent] 可视化已保存: {output_path}")
        return output_path
    
    def visualize_comparison(self, output_path: str) -> str:
        print("\n[EvaluationAgent] 生成多视图对比可视化...")

        visual_sample_size = int(self.config.get("visual_sample_size", 32000))
        stl_points_raw = self._sample_surface_points(self.stl_mesh, self.stl_vertices, sample_size=visual_sample_size)
        step_points_raw = self._sample_surface_points(self.step_mesh, self.step_vertices, sample_size=visual_sample_size)

        stl_points = self._canonicalize_wheel_points(stl_points_raw)
        step_points = self._canonicalize_wheel_points(step_points_raw)

        step_points, align_meta = self._align_step_to_stl_visual(stl_points, step_points)
        axial_rotation_deg = float(align_meta.get("axial_rotation_deg", 0.0))
        axis_signs = tuple(align_meta.get("axis_signs", (1.0, 1.0, 1.0)))

        front_stl = self._project_canonical_points(stl_points, "front")
        front_step = self._project_canonical_points(step_points, "front")
        spoke_band_stl = self._filter_spoke_band(front_stl)
        spoke_band_step = self._filter_spoke_band(front_step)
        spoke_sector_angle = self._estimate_single_spoke_angle(spoke_band_stl, spoke_band_step)

        view_defs = [
            ("front", "Front View", 1.0, None),
            ("spoke_sector", f"Single Spoke Close-up ({spoke_sector_angle:.0f}°)", 1.0, None),
            ("side", "Side View", 1.0, None),
            ("iso", "Isometric View", 1.0, None),
        ]
        column_defs = [("STL", True, False), ("STEP", False, True), ("Overlay", True, True)]

        fig, axes = plt.subplots(len(view_defs), len(column_defs), figsize=(16, 19))
        fig.suptitle(
            f"STL / STEP Multi-view Comparison\nSTL samples={len(stl_points)}  STEP samples={len(step_points)}  axial_align={axial_rotation_deg:.1f} deg  signs={axis_signs}",
            fontsize=15,
        )

        if len(view_defs) == 1:
            axes = np.asarray([axes])

        for row_index, (view_mode, view_label, zoom, keep_ratio) in enumerate(view_defs):
            if view_mode == "spoke_sector":
                stl_proj = self._project_single_spoke_closeup(stl_points, spoke_sector_angle, "front")
                step_proj = self._project_single_spoke_closeup(step_points, spoke_sector_angle, "front")
                stl_proj, step_proj, spoke_orient_deg = self._orient_closeup_pair(stl_proj, step_proj)
            else:
                stl_proj = self._trim_projected_radius(self._project_canonical_points(stl_points, view_mode), keep_ratio)
                step_proj = self._trim_projected_radius(self._project_canonical_points(step_points, view_mode), keep_ratio)
                spoke_orient_deg = 0.0

            for col_index, (column_label, show_stl, show_step) in enumerate(column_defs):
                ax = axes[row_index, col_index]
                point_size = 1.15 if view_mode == "spoke_sector" else 0.35
                alpha = 0.62 if view_mode == "spoke_sector" else 0.32

                if show_stl:
                    self._plot_projected_points(ax, stl_proj, color="#1f77b4", label="STL", point_size=point_size, alpha=alpha)
                if show_step:
                    self._plot_projected_points(ax, step_proj, color="#2ca02c", label="STEP", point_size=point_size, alpha=alpha)

                self._set_projection_limits(ax, [stl_proj, step_proj], zoom=zoom)
                if view_mode == "spoke_sector":
                    ax.set_title(f"{view_label} · {column_label}\norient={spoke_orient_deg:.1f}°")
                else:
                    ax.set_title(f"{view_label} · {column_label}")
                if row_index == 0 and (show_stl or show_step):
                    ax.legend(loc="upper right", markerscale=10, frameon=False)

        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()

        print(f"[EvaluationAgent] 多视图可视化已保存: {output_path}")
        return output_path

    def run_full_evaluation(self) -> EvaluationResult:
        print("=" * 60)
        print("[EvaluationAgent] 开始全面评估")
        print("=" * 60)
        
        self.differences = []
        
        self.evaluate_dimensions()
        self.evaluate_profile()
        self.evaluate_hausdorff()
        self.evaluate_spokes()
        self.evaluate_symmetry()
        
        feedback = self.generate_feedback()
        
        result = EvaluationResult(
            overall_score=feedback['overall_score'],
            is_acceptable=feedback['is_acceptable'],
            differences=self.differences,
            summary=feedback['summary'],
            recommendations=feedback['perception_adjustments'] + feedback['modeling_adjustments']
        )
        
        print("\n" + "=" * 60)
        print("[EvaluationAgent] 评估完成")
        print("=" * 60)
        print(f"\n总体得分: {result.overall_score}/100")
        print(f"是否可接受: {'是' if result.is_acceptable else '否'}")
        try:
            print(f"\n{result.summary}")
        except UnicodeEncodeError:
            safe_summary = result.summary.encode("gbk", errors="replace").decode("gbk")
            print(f"\n{safe_summary}")
        
        return result
    
    def export_report(self, output_path: str) -> None:
        feedback = self.generate_feedback()
        
        def _json_default(obj):
            if isinstance(obj, np.generic):
                return obj.item()
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(feedback, f, indent=2, ensure_ascii=False, default=_json_default)
        
        print(f"[EvaluationAgent] 报告已导出: {output_path}")


    def handle_task(self, task: AgentTask, context: Dict[str, Any]) -> AgentResult:
        if task.type != TaskType.EVALUATE_MODEL:
            return AgentResult(
                task_id=task.id,
                sender="EvaluationAgent",
                success=False,
                output_type="unsupported_task",
                reason=f"EvaluationAgent cannot handle task type {task.type.value}",
            )

        report_name = "evaluation_report.json" if task.iteration == 0 else f"evaluation_report_iter{task.iteration}.json"
        viz_name = "evaluation_comparison.png" if task.iteration == 0 else f"evaluation_comparison_iter{task.iteration}.png"
        report_path = os.path.join(task.payload["output_dir"], report_name)
        viz_path = os.path.join(task.payload["output_dir"], viz_name)

        result = self.run_full_evaluation()
        self.export_report(report_path)
        self.visualize_comparison(viz_path)

        differences_payload = [
            {
                "difference_type": diff.difference_type.value,
                "severity": diff.severity.value,
                "component": diff.component,
                "description": diff.description,
                "expected_value": diff.expected_value,
                "actual_value": diff.actual_value,
                "deviation_percent": float(diff.deviation_percent),
                "suggestion": diff.suggestion,
            }
            for diff in result.differences
        ]

        artifacts = [
            ArtifactRecord(name="evaluation_report", path=report_path),
            ArtifactRecord(name="evaluation_visualization", path=viz_path),
        ]

        if not task.payload.get("enable_optimization", True):
            return AgentResult(
                task_id=task.id,
                sender="EvaluationAgent",
                success=True,
                output_type="runtime_complete",
                payload={
                    "overall_score": float(result.overall_score),
                    "is_acceptable": result.is_acceptable,
                    "results": {
                        "features_json": task.payload["features_path"],
                        "output_model": task.payload["model_path"],
                        "evaluation_report": report_path,
                        "evaluation_visualization": viz_path,
                        "runtime_state": os.path.join(task.payload["output_dir"], "runtime", "state_snapshot.json"),
                    },
                },
                artifacts=artifacts,
            )

        next_task = AgentTask(
            type=TaskType.OPTIMIZE_SYSTEM,
            sender="EvaluationAgent",
            receiver="OptimizationAgent",
            iteration=task.iteration,
            parent_task_id=task.id,
            payload={
                "stl_path": task.payload["stl_path"],
                "features_path": task.payload["features_path"],
                "model_path": task.payload["model_path"],
                "output_dir": task.payload["output_dir"],
                "output_format": task.payload["output_format"],
                "evaluation": {
                    "overall_score": float(result.overall_score),
                    "is_acceptable": result.is_acceptable,
                    "summary": result.summary,
                    "recommendations": result.recommendations,
                    "differences": differences_payload,
                },
            },
        )

        return AgentResult(
            task_id=task.id,
            sender="EvaluationAgent",
            success=True,
            output_type="evaluation_completed",
            payload={
                "overall_score": float(result.overall_score),
                "is_acceptable": result.is_acceptable,
                "summary": result.summary,
                "recommendations": result.recommendations,
                "differences": differences_payload,
            },
            artifacts=artifacts,
            next_tasks=[next_task],
        )


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="评估智能体 - 分析建模与原始STL的差异")
    parser.add_argument("--stl", default="input/wheel.stl", help="STL文件路径")
    parser.add_argument("--step", default="output/wheel_model.step", help="STEP文件路径")
    parser.add_argument("--features", default="output/wheel_features.json", help="特征JSON文件路径")
    parser.add_argument("--output", default="output", help="输出目录")
    
    args = parser.parse_args()
    
    os.makedirs(args.output, exist_ok=True)
    
    agent = EvaluationAgent(
        stl_path=args.stl,
        step_path=args.step,
        features_path=args.features
    )
    
    result = agent.run_full_evaluation()
    
    agent.export_report(os.path.join(args.output, "evaluation_report.json"))
    agent.visualize_comparison(os.path.join(args.output, "evaluation_comparison.png"))


if __name__ == "__main__":
    main()
