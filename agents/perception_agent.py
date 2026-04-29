import numpy as np
from stl import mesh
import trimesh
from typing import Tuple, Optional, List, Dict
import json
import os

from models.agent_protocol import AgentResult, AgentTask, ArtifactRecord, TaskType
from models.wheel_features import (
    WheelFeatures, HubFeatures, SpokeFeatures, RimFeatures, 
    RimProfilePoint, RimCrossSection, SpokeType
)
from skills.perception_skill import PerceptionSkill, PerceptionSkillResult


class PerceptionAgent:
    def __init__(
        self,
        stl_path: str,
        config: Optional[Dict] = None,
        skill: Optional[PerceptionSkill] = None,
    ):
        self.stl_path = stl_path
        self.mesh: Optional[trimesh.Trimesh] = None
        self.stl_mesh: Optional[mesh.Mesh] = None
        self.vertices: Optional[np.ndarray] = None
        self.faces: Optional[np.ndarray] = None
        
        self.config = config or {}
        self.num_slices = self.config.get('num_slices', 2000)
        self.feature_threshold = self.config.get('feature_threshold', 0.5)
        self.radius_threshold = self.config.get('radius_threshold', 0.8)
        
        self._rotation_axis: Optional[np.ndarray] = None
        self._centroid: Optional[np.ndarray] = None
        self._heights: Optional[np.ndarray] = None
        self._radii: Optional[np.ndarray] = None
        self.skill = skill or PerceptionSkill()
        
        self._load_mesh()
    
    def _load_mesh(self) -> None:
        self.stl_mesh = mesh.Mesh.from_file(self.stl_path)
        self.mesh = trimesh.load(self.stl_path)
        vertices = np.array(self.stl_mesh.vectors.reshape(-1, 3))
        
        max_vertices = 100000
        if len(vertices) > max_vertices:
            indices = np.random.choice(len(vertices), max_vertices, replace=False)
            indices = np.sort(indices)
            vertices = vertices[indices]
        
        self.vertices = vertices
    
    def _compute_centroid(self) -> np.ndarray:
        if self._centroid is None:
            self._centroid = self.vertices.mean(axis=0)
        return self._centroid
    
    def _find_rotation_axis(self) -> np.ndarray:
        if self._rotation_axis is not None:
            return self._rotation_axis
        
        centroid = self._compute_centroid()
        centered = self.vertices - centroid
        
        cov_matrix = np.cov(centered.T)
        eigenvalues, eigenvectors = np.linalg.eigh(cov_matrix)
        
        sorted_indices = np.argsort(eigenvalues)[::-1]
        eigenvalues = eigenvalues[sorted_indices]
        eigenvectors = eigenvectors[:, sorted_indices]
        
        rotation_axis = eigenvectors[:, 2]
        
        if rotation_axis[2] < 0:
            rotation_axis = -rotation_axis
        
        self._rotation_axis = rotation_axis
        return rotation_axis
    
    def _compute_heights_and_radii(self) -> Tuple[np.ndarray, np.ndarray]:
        if self._heights is not None and self._radii is not None:
            return self._heights, self._radii
        
        centroid = self._compute_centroid()
        axis = self._find_rotation_axis()
        centered = self.vertices - centroid
        
        heights = centered @ axis
        radial_vectors = centered - np.outer(heights, axis)
        radii = np.linalg.norm(radial_vectors, axis=1)
        
        self._heights = heights
        self._radii = radii
        
        return heights, radii
    
    def _detect_feature_points(self, heights: np.ndarray, radii: np.ndarray, 
                                tolerance: float = 1.0) -> List[RimProfilePoint]:
        profile_points = []
        
        if len(heights) < 3:
            return profile_points
        
        smoothed_radii = np.convolve(radii, np.ones(5)/5, mode='same')
        
        gradient = np.gradient(smoothed_radii)
        second_gradient = np.gradient(gradient)
        
        feature_indices = set()
        
        for i in range(2, len(gradient) - 2):
            if abs(gradient[i]) < 0.01:
                continue
            if gradient[i-1] > 0 and gradient[i] < 0:
                for offset in range(-int(tolerance), int(tolerance) + 1):
                    if 0 <= i + offset < len(heights):
                        feature_indices.add(i + offset)
            elif gradient[i-1] < 0 and gradient[i] > 0:
                for offset in range(-int(tolerance), int(tolerance) + 1):
                    if 0 <= i + offset < len(heights):
                        feature_indices.add(i + offset)
        
        for i in range(2, len(second_gradient) - 2):
            if abs(second_gradient[i]) > 0.02:
                feature_indices.add(i)
        
        for i in range(len(heights)):
            is_feature = i in feature_indices
            
            if i > 0:
                radius_change = abs(radii[i] - radii[i-1])
                if radius_change > self.feature_threshold:
                    is_feature = True
            
            if is_feature:
                if i > 0 and i < len(heights) - 1:
                    if radii[i] > radii[i-1] and radii[i] > radii[i+1]:
                        feature_type = "bump"
                    elif radii[i] < radii[i-1] and radii[i] < radii[i+1]:
                        feature_type = "valley"
                    else:
                        feature_type = "edge"
                else:
                    feature_type = "edge"
            else:
                feature_type = None
            
            profile_points.append(RimProfilePoint(
                radius=radii[i],
                height=heights[i],
                is_feature=is_feature,
                feature_type=feature_type
            ))
        
        return profile_points
    
    def _extract_radial_profile(self, num_slices: Optional[int] = None) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        if num_slices is None:
            num_slices = self.num_slices
        
        heights, radii = self._compute_heights_and_radii()
        
        height_min = heights.min()
        height_max = heights.max()
        height_bins = np.linspace(height_min, height_max, num_slices + 1)
        
        mean_radii = np.zeros(num_slices)
        max_radii = np.zeros(num_slices)
        min_radii = np.zeros(num_slices)
        std_radii = np.zeros(num_slices)
        counts = np.zeros(num_slices)
        
        for i in range(num_slices):
            mask = (heights >= height_bins[i]) & (heights < height_bins[i + 1])
            if mask.sum() > 0:
                slice_distances = radii[mask]
                mean_radii[i] = slice_distances.mean()
                max_radii[i] = slice_distances.max()
                min_radii[i] = slice_distances.min()
                std_radii[i] = slice_distances.std()
                counts[i] = mask.sum()
        
        valid_mask = counts > 10
        if valid_mask.sum() > 0:
            valid_heights = (height_bins[:-1] + height_bins[1:]) / 2
            return (valid_heights[valid_mask], mean_radii[valid_mask], 
                    max_radii[valid_mask], min_radii[valid_mask], std_radii[valid_mask])
        
        return height_bins[:-1], mean_radii, max_radii, min_radii, std_radii
    
    def _detect_hub_region(self, heights: np.ndarray, radii: np.ndarray) -> Tuple[float, float, float, float]:
        height_range = heights.max() - heights.min()
        height_mid = (heights.max() + heights.min()) / 2
        
        center_region_mask = np.abs(heights - height_mid) < height_range * 0.3
        center_radii = radii[center_region_mask]
        center_heights = heights[center_region_mask]
        
        if len(center_radii) < 100:
            center_radii = radii
            center_heights = heights
        
        sorted_indices = np.argsort(center_radii)
        bottom_20_percent = int(len(center_radii) * 0.2)
        
        small_radius_indices = sorted_indices[:bottom_20_percent]
        small_radius_heights = center_heights[small_radius_indices]
        small_radius_radii = center_radii[small_radius_indices]
        
        hub_radius = np.percentile(small_radius_radii, 90)
        
        hub_height_min = small_radius_heights.min()
        hub_height_max = small_radius_heights.max()
        hub_height_extent = abs(hub_height_max - hub_height_min)
        
        hub_height_extent = min(hub_height_extent, height_range * 0.3)
        
        hub_inner_radius = hub_radius * 0.3
        
        hub_center_height = (hub_height_min + hub_height_max) / 2
        
        return hub_radius * 2, hub_height_extent, hub_inner_radius, hub_center_height
    
    def _detect_rim_dimensions(self, heights: np.ndarray, radii: np.ndarray) -> Tuple[float, float, float, float]:
        if len(radii) < 10:
            return 0, 0, 0, 0
        
        sorted_by_radius = np.argsort(radii)[::-1]
        top_5_percent = int(len(radii) * 0.05)
        rim_indices = sorted_by_radius[:max(top_5_percent, 10)]
        
        rim_outer_radius = np.percentile(radii[rim_indices], 90)
        rim_heights = heights[rim_indices]
        
        rim_height_min = rim_heights.min()
        rim_height_max = rim_heights.max()
        rim_width = abs(rim_height_max - rim_height_min)
        
        if rim_width < 20:
            rim_width = abs(heights.max() - heights.min()) * 0.7
        
        rim_inner_radius = rim_outer_radius * 0.65
        
        lip_height = 0.0
        
        return rim_outer_radius * 2, rim_inner_radius * 2, rim_width, lip_height
    
    def _detect_spokes(self) -> Tuple[int, SpokeType, float, float]:
        heights, radii = self._compute_heights_and_radii()
        centroid = self._compute_centroid()
        axis = self._find_rotation_axis()
        centered = self.vertices - centroid
        
        height_range = heights.max() - heights.min()
        mid_height = (heights.max() + heights.min()) / 2
        height_tolerance = height_range * 0.15
        
        mid_slice_mask = np.abs(heights - mid_height) < height_tolerance
        mid_slice_points = centered[mid_slice_mask]
        
        if len(mid_slice_points) < 100:
            return 5, SpokeType.SOLID, 20.0, 5.0
        
        radial_mid = radii[mid_slice_mask]
        
        hub_radius_estimate = np.percentile(radial_mid, 10)
        rim_radius_estimate = np.percentile(radial_mid, 95)
        
        spoke_region_mask = (radial_mid > hub_radius_estimate * 1.5) & (radial_mid < rim_radius_estimate * 0.95)
        spoke_region_points = mid_slice_points[spoke_region_mask]
        
        if len(spoke_region_points) < 50:
            return 5, SpokeType.SOLID, 20.0, 5.0
        
        xy_points = spoke_region_points[:, :2]
        angles = np.arctan2(xy_points[:, 1], xy_points[:, 0])
        
        num_angular_bins = 72
        angular_bins = np.linspace(-np.pi, np.pi, num_angular_bins + 1)
        bin_counts = np.zeros(num_angular_bins)
        
        for i in range(num_angular_bins):
            mask = (angles >= angular_bins[i]) & (angles < angular_bins[i + 1])
            bin_counts[i] = mask.sum()
        
        smoothed_counts = np.convolve(bin_counts, np.ones(5)/5, mode='same')
        
        threshold = smoothed_counts.mean() * 1.2
        peaks = []
        for i in range(5, len(smoothed_counts) - 5):
            if (smoothed_counts[i] > threshold and
                smoothed_counts[i] > smoothed_counts[i-2] and 
                smoothed_counts[i] > smoothed_counts[i+2]):
                peaks.append(i)
        
        if len(peaks) >= 3:
            peak_intervals = np.diff(peaks)
            if len(peak_intervals) > 0:
                avg_interval = np.median(peak_intervals)
                expected_spokes = int(360 / (avg_interval * 360 / num_angular_bins))
                
                valid_spokes = [n for n in [3, 4, 5, 6, 7, 8, 9, 10, 12] if abs(n - expected_spokes) <= 2]
                if valid_spokes:
                    spoke_count = min(valid_spokes, key=lambda n: abs(n - expected_spokes))
                else:
                    spoke_count = max(3, min(12, expected_spokes))
            else:
                spoke_count = len(peaks)
        else:
            spoke_count = 5
        
        spoke_type = SpokeType.SPOKE
        
        avg_radius = radial_mid.mean()
        circumference = 2 * np.pi * avg_radius
        spoke_width = circumference / (spoke_count * 2.5)
        
        spoke_thickness = height_range * 0.15
        
        return spoke_count, spoke_type, spoke_width, max(5.0, spoke_thickness)
    
    def _detect_bolt_holes(self, hub_diameter: float) -> Tuple[int, float, float]:
        heights, radii = self._compute_heights_and_radii()
        centroid = self._compute_centroid()
        axis = self._find_rotation_axis()
        centered = self.vertices - centroid
        
        height_range = heights.max() - heights.min()
        
        hub_region_mask = radii < hub_diameter * 0.6
        
        hub_points = centered[hub_region_mask]
        if len(hub_points) < 50:
            return 5, 12.0, hub_diameter * 0.6
        
        xy_points = hub_points[:, :2]
        distances = np.linalg.norm(xy_points, axis=1)
        
        hub_radius = hub_diameter / 2
        bolt_ring_min = hub_radius * 0.4
        bolt_ring_max = hub_radius * 0.8
        
        bolt_ring_mask = (distances > bolt_ring_min) & (distances < bolt_ring_max)
        bolt_ring_points = xy_points[bolt_ring_mask]
        
        if len(bolt_ring_points) < 20:
            return 5, 12.0, (bolt_ring_min + bolt_ring_max)
        
        angles = np.arctan2(bolt_ring_points[:, 1], bolt_ring_points[:, 0])
        
        num_bins = 36
        hist, bin_edges = np.histogram(angles, bins=num_bins, range=(-np.pi, np.pi))
        
        peaks = []
        for i in range(1, len(hist) - 1):
            if hist[i] > hist[i-1] and hist[i] > hist[i+1] and hist[i] > hist.mean() * 0.8:
                peaks.append(i)
        
        if len(peaks) >= 3:
            bolt_count = len(peaks)
        else:
            bolt_count = 5
        
        bolt_pcd = (bolt_ring_min + bolt_ring_max)
        bolt_diameter = 12.0
        
        return bolt_count, bolt_diameter, bolt_pcd
    
    def _extract_angular_profiles(self, num_angles: int = 8) -> List[RimCrossSection]:
        centroid = self._compute_centroid()
        axis = self._find_rotation_axis()
        centered = self.vertices - centroid
        
        angles = np.linspace(0, 360, num_angles + 1)[:-1]
        cross_sections = []
        
        heights_all, radial_distances = self._compute_heights_and_radii()
        
        for angle in angles:
            rad = np.radians(angle)
            
            perp_x = np.array([-axis[1], axis[0], 0])
            if np.linalg.norm(perp_x) < 0.01:
                perp_x = np.array([1, 0, 0])
            perp_x = perp_x / np.linalg.norm(perp_x)
            perp_y = np.cross(axis, perp_x)
            
            direction = perp_x * np.cos(rad) + perp_y * np.sin(rad)
            
            projections = centered @ direction
            angle_tolerance = 0.15
            
            angle_mask = np.abs(projections) < (radial_distances * angle_tolerance)
            
            if angle_mask.sum() < 50:
                continue
            
            angle_heights = heights_all[angle_mask]
            angle_radii = radial_distances[angle_mask]
            
            num_bins = 100
            height_min, height_max = angle_heights.min(), angle_heights.max()
            height_bins = np.linspace(height_min, height_max, num_bins + 1)
            
            bin_heights = []
            bin_radii = []
            
            for i in range(num_bins):
                mask = (angle_heights >= height_bins[i]) & (angle_heights < height_bins[i + 1])
                if mask.sum() > 0:
                    bin_heights.append((height_bins[i] + height_bins[i + 1]) / 2)
                    bin_radii.append(angle_radii[mask].mean())
            
            if len(bin_heights) > 10:
                profile_points = self._detect_feature_points(
                    np.array(bin_heights), 
                    np.array(bin_radii)
                )
                
                cross_sections.append(RimCrossSection(
                    angle=float(angle),
                    profile_points=profile_points
                ))
        
        return cross_sections
    
    def _extract_main_profile(self) -> List[RimProfilePoint]:
        heights, radii, max_radii, min_radii, std_radii = self._extract_radial_profile(num_slices=self.num_slices)
        
        profile_points = self._detect_feature_points(
            heights, max_radii, 0.5
        )
        return profile_points
    
    def extract_features(self) -> WheelFeatures:
        centroid = self._compute_centroid()
        rotation_axis = self._find_rotation_axis()
        
        heights, radii = self._compute_heights_and_radii()
        
        overall_diameter = radii.max() * 2
        overall_width = heights.max() - heights.min()
        
        hub_diameter, hub_height, hub_inner_radius, hub_center_height = self._detect_hub_region(heights, radii)
        rim_outer_diameter, rim_inner_diameter, rim_width, lip_height = self._detect_rim_dimensions(heights, radii)
        
        spoke_count, spoke_type, spoke_width, spoke_thickness = self._detect_spokes()
        
        bolt_count, bolt_diameter, bolt_pcd = self._detect_bolt_holes(hub_diameter)
        
        cross_sections = self._extract_angular_profiles(num_angles=8)
        main_profile = self._extract_main_profile()
        
        hub = HubFeatures(
            inner_diameter=max(hub_inner_radius * 2, 30.0),
            outer_diameter=max(hub_diameter, 50.0),
            height=max(hub_height, 30.0),
            bolt_hole_count=bolt_count,
            bolt_hole_diameter=bolt_diameter,
            bolt_hole_pcd=bolt_pcd,
            center_hole_diameter=max(hub_inner_radius * 2, 25.0)
        )
        
        spokes = SpokeFeatures(
            count=spoke_count,
            type=spoke_type,
            width=max(spoke_width, 10.0),
            thickness=max(spoke_thickness, 5.0),
            pcd=hub.outer_diameter * 0.7
        )
        
        rim = RimFeatures(
            outer_diameter=rim_outer_diameter,
            inner_diameter=max(rim_inner_diameter, hub.outer_diameter * 1.2),
            width=min(rim_width, overall_width * 0.8),
            lip_height=lip_height,
            cross_sections=[s.model_dump() for s in cross_sections],
            main_profile=[p.model_dump() for p in main_profile]
        )
        
        features = WheelFeatures(
            overall_diameter=overall_diameter,
            overall_width=overall_width,
            hub=hub,
            spokes=spokes,
            rim=rim,
            center_offset=0.0,
            fillet_radius=3.0,
            rotation_axis=tuple(rotation_axis.tolist()),
            centroid=tuple(centroid.tolist())
        )
        
        return features
    
    def export_features_to_json(self, output_path: str) -> dict:
        features = self.extract_features()
        features.to_json(output_path)
        return features.model_dump(mode='json')

    def run_perception_skill(self, output_path: Optional[str] = None) -> PerceptionSkillResult:
        return self.skill.run(self, output_path=output_path)

    def handle_task(self, task: AgentTask, context: Dict) -> AgentResult:
        if task.type != TaskType.EXTRACT_FEATURES:
            return AgentResult(
                task_id=task.id,
                sender="PerceptionAgent",
                success=False,
                output_type="unsupported_task",
                reason=f"PerceptionAgent cannot handle task type {task.type.value}",
            )

        output_path = task.payload.get("output_path")
        if not output_path:
            output_path = os.path.join(".", "output", "wheel_features.json")

        skill_result = self.run_perception_skill(output_path=output_path)
        features = skill_result.features
        output_format = task.payload.get("model_output_format", "step")
        model_extension = "step" if output_format.lower() == "step" else "stl"
        model_output_name = "wheel_model"
        if task.iteration > 0:
            model_output_name = f"wheel_model_iter{task.iteration}"
        model_output_path = os.path.join(os.path.dirname(output_path), f"{model_output_name}.{model_extension}")

        next_task = AgentTask(
            type=TaskType.BUILD_MODEL,
            sender="PerceptionAgent",
            receiver="ModelingAgent",
            iteration=task.iteration,
            parent_task_id=task.id,
            payload={
                "features_path": output_path,
                "output_path": model_output_path,
                "output_format": output_format,
                "stl_path": task.payload["stl_path"],
                "enable_optimization": task.payload.get("enable_optimization", True),
                "modeling_config": task.payload.get("modeling_config", {}),
            },
        )

        return AgentResult(
            task_id=task.id,
            sender="PerceptionAgent",
            success=True,
            output_type="features_extracted",
            payload={
                "features_path": output_path,
                "feature_summary": {
                    "overall_diameter": features.overall_diameter,
                    "overall_width": features.overall_width,
                    "spoke_count": features.spokes.count,
                    "spoke_type": features.spokes.type.value,
                },
            },
            artifacts=[ArtifactRecord(name="features_json", path=output_path)],
            next_tasks=[next_task],
        )
