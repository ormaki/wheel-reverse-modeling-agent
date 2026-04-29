import cadquery as cq
from typing import Optional, List, Tuple
import numpy as np
import os

from models.agent_protocol import AgentResult, AgentTask, ArtifactRecord, TaskType
from models.wheel_features import WheelFeatures, HubFeatures, SpokeFeatures, RimFeatures, SpokeType
from skills.modeling_skill import ModelingSkill, ModelingSkillResult


class ModelingAgent:
    def __init__(
        self,
        features: WheelFeatures,
        skill: Optional[ModelingSkill] = None,
        config: Optional[dict] = None,
    ):
        self.features = features
        self.result: Optional[cq.Workplane] = None
        self.skill = skill or ModelingSkill()
        self.config = config or {}
    
    def _create_hub(self) -> cq.Workplane:
        hub = self.features.hub
        
        hub_height = max(hub.height, 20.0)
        hub_outer_radius = hub.outer_diameter / 2
        hub_inner_radius = hub.inner_diameter / 2
        
        hub_solid = (
            cq.Workplane("XY")
            .circle(hub_outer_radius)
            .extrude(hub_height)
        )
        
        hub_solid = hub_solid.translate((0, 0, -hub_height/2))
        
        if hub_inner_radius > 0 and hub_inner_radius < hub_outer_radius:
            try:
                hub_solid = (
                    hub_solid
                    .faces(">Z")
                    .workplane()
                    .circle(hub_inner_radius)
                    .cutBlind(-hub_height)
                )
            except Exception:
                pass
        
        if hub.bolt_hole_count > 0 and hub.bolt_hole_pcd > 0:
            try:
                all_faces = hub_solid.faces()
                if all_faces.size() > 0:
                    hub_solid = (
                        all_faces
                        .workplane()
                        .polarArray(
                            radius=hub.bolt_hole_pcd / 2,
                            startAngle=0,
                            angle=360,
                            count=hub.bolt_hole_count
                        )
                        .circle(hub.bolt_hole_diameter / 2)
                        .cutThruAll()
                    )
            except Exception:
                pass
        
        return hub_solid
    
    def _create_rim_from_profile(self) -> Optional[cq.Workplane]:
        rim = self.features.rim
        main_profile = rim.main_profile
        
        if not main_profile or len(main_profile) < 10:
            return None
        
        profile_points = []
        for p in main_profile:
            if isinstance(p, dict):
                r = p.get('radius', 0)
                h = p.get('height', 0)
            else:
                r = p.radius
                h = p.height
            profile_points.append((r, h))
        
        if len(profile_points) < 10:
            return None
        
        sorted_points = sorted(profile_points, key=lambda p: p[1])
        
        import numpy as np
        radii = np.array([p[0] for p in sorted_points])
        heights = np.array([p[1] for p in sorted_points])
        
        num_points = 100
        height_min, height_max = heights.min(), heights.max()
        height_bins = np.linspace(height_min, height_max, num_points + 1)
        
        simplified = []
        for i in range(num_points):
            mask = (heights >= height_bins[i]) & (heights < height_bins[i + 1])
            if mask.sum() > 0:
                h = heights[mask].max()
                r = radii[mask].max()
                simplified.append((r, h))
        
        simplified = sorted(simplified, key=lambda p: p[1])
        
        if len(simplified) < 6:
            return None
        
        try:
            outer_pts = [(max(r, 0.1), 0, h) for r, h in simplified]
            
            outer_pts.insert(0, (0.1, 0, simplified[0][1]))
            outer_pts.append((0.1, 0, simplified[-1][1]))
            
            outer_wire = cq.Workplane("XZ").polyline(outer_pts).close()
            
            rim_solid = outer_wire.revolve(axisStart=(0, 0, 0), axisEnd=(0, 0, 1))
            
            return rim_solid
            
        except Exception as e:
            print(f"Profile rim creation failed: {e}")
            return None
    
    def _create_rim_fallback(self) -> cq.Workplane:
        rim = self.features.rim
        overall_width = self.features.overall_width
        
        actual_width = max(min(rim.width, overall_width * 0.8), 20.0)
        
        outer_radius = rim.outer_diameter / 2
        inner_radius = rim.inner_diameter / 2
        
        if inner_radius >= outer_radius * 0.95:
            inner_radius = outer_radius * 0.7
        
        rim_solid = (
            cq.Workplane("XY")
            .circle(outer_radius)
            .circle(inner_radius)
            .extrude(actual_width)
        )
        
        rim_solid = rim_solid.translate((0, 0, -actual_width/2))
        
        return rim_solid
    
    def _create_rim(self) -> cq.Workplane:
        if self.config.get("rim_strategy") == "fallback_priority":
            return self._create_rim_fallback()
        rim_from_profile = self._create_rim_from_profile()
        
        if rim_from_profile is not None:
            return rim_from_profile
        
        return self._create_rim_fallback()
    
    def _create_spoke(self, spoke_index: int) -> cq.Workplane:
        spokes = self.features.spokes
        hub = self.features.hub
        rim = self.features.rim
        
        angle = (360 / spokes.count) * spoke_index + spokes.angle_offset
        
        hub_radius = hub.outer_diameter / 2
        rim_inner_radius = rim.inner_diameter / 2
        
        spoke_length = rim_inner_radius - hub_radius - 5
        
        if spoke_length <= 0:
            spoke_length = (rim.outer_diameter - hub.outer_diameter) / 2 - 5
        
        spoke_width = max(spokes.width, 8.0)
        spoke_thickness = max(spokes.thickness, 5.0)
        
        try:
            spoke = (
                cq.Workplane("XY")
                .transformed(rotate=(0, 0, angle))
                .moveTo(hub_radius + 2, -spoke_width / 2)
                .line(spoke_length, 0)
                .line(0, spoke_width)
                .line(-spoke_length, 0)
                .close()
                .extrude(spoke_thickness)
            )
        except Exception:
            spoke = (
                cq.Workplane("XY")
                .transformed(rotate=(0, 0, angle))
                .rect(spoke_length, spoke_width)
                .extrude(spoke_thickness)
            )
            spoke = spoke.translate((hub_radius + spoke_length / 2, 0, 0))
        
        return spoke
    
    def _create_spokes(self) -> cq.Workplane:
        spokes = self.features.spokes
        hub = self.features.hub
        rim = self.features.rim
        
        if spokes.type == SpokeType.SOLID:
            inner_radius = hub.outer_diameter / 2 + 2
            outer_radius = rim.inner_diameter / 2 - 2
            
            if outer_radius <= inner_radius:
                outer_radius = rim.outer_diameter / 2 - 5
            
            spoke_disc = (
                cq.Workplane("XY")
                .circle(outer_radius)
                .circle(inner_radius)
                .extrude(spokes.thickness)
            )
            return spoke_disc
        
        all_spokes = None
        for i in range(spokes.count):
            spoke = self._create_spoke(i)
            if all_spokes is None:
                all_spokes = spoke
            else:
                all_spokes = all_spokes.union(spoke)
        
        return all_spokes
    
    def build_model(self) -> cq.Workplane:
        hub = self._create_hub()
        rim = self._create_rim()
        spokes = self._create_spokes()
        
        hub_bbox = hub.val().BoundingBox()
        hub_z_center = (hub_bbox.zmax + hub_bbox.zmin) / 2
        
        if spokes is not None:
            spokes_bbox = spokes.val().BoundingBox()
            spokes_z_center = (spokes_bbox.zmax + spokes_bbox.zmin) / 2
            spokes = spokes.translate((0, 0, hub_z_center - spokes_z_center))
        
        if spokes is not None:
            wheel = hub.union(spokes).union(rim)
        else:
            wheel = hub.union(rim)
        
        if self.features.fillet_radius > 0:
            try:
                wheel = wheel.edges("|Z").fillet(self.features.fillet_radius)
            except Exception:
                pass
        
        self.result = wheel
        return wheel
    
    def export_step(self, output_path: str) -> None:
        if self.result is None:
            self.build_model()
        
        cq.exporters.export(self.result, output_path)
    
    def export_stl(self, output_path: str) -> None:
        if self.result is None:
            self.build_model()
        
        cq.exporters.export(self.result, output_path)
    
    @classmethod
    def from_json(cls, json_path: str, config: Optional[dict] = None) -> 'ModelingAgent':
        features = WheelFeatures.from_json(json_path)
        return cls(features, config=config)

    def run_modeling_skill(
        self,
        output_format: str = "step",
        output_path: Optional[str] = None,
    ) -> ModelingSkillResult:
        return self.skill.run(
            self,
            output_format=output_format,
            output_path=output_path,
        )

    def handle_task(self, task: AgentTask, context: dict) -> AgentResult:
        if task.type != TaskType.BUILD_MODEL:
            return AgentResult(
                task_id=task.id,
                sender="ModelingAgent",
                success=False,
                output_type="unsupported_task",
                reason=f"ModelingAgent cannot handle task type {task.type.value}",
            )

        output_format = task.payload.get("output_format", "step")
        output_path = task.payload.get("output_path")
        if not output_path:
            suffix = "step" if output_format.lower() == "step" else "stl"
            output_path = os.path.join(".", "output", f"wheel_model.{suffix}")

        self.run_modeling_skill(
            output_format=output_format,
            output_path=output_path,
        )

        next_task = AgentTask(
            type=TaskType.EVALUATE_MODEL,
            sender="ModelingAgent",
            receiver="EvaluationAgent",
            iteration=task.iteration,
            parent_task_id=task.id,
            payload={
                "stl_path": task.payload["stl_path"],
                "features_path": task.payload["features_path"],
                "model_path": output_path,
                "output_dir": os.path.dirname(output_path),
                "output_format": output_format,
                "enable_optimization": task.payload.get("enable_optimization", True),
            },
        )

        return AgentResult(
            task_id=task.id,
            sender="ModelingAgent",
            success=True,
            output_type="model_built",
            payload={
                "model_path": output_path,
                "output_format": output_format.lower(),
            },
            artifacts=[ArtifactRecord(name="output_model", path=output_path)],
            next_tasks=[next_task],
        )


class AdvancedModelingAgent(ModelingAgent):
    def _create_curved_spoke(self, spoke_index: int) -> cq.Workplane:
        spokes = self.features.spokes
        hub = self.features.hub
        rim = self.features.rim
        
        angle = (360 / spokes.count) * spoke_index + spokes.angle_offset
        
        start_radius = hub.outer_diameter / 2 + 5
        end_radius = rim.inner_diameter / 2 - 5
        
        if end_radius <= start_radius:
            end_radius = rim.outer_diameter / 2 - 5
        
        curve_angle = 10
        
        import math
        points = []
        num_points = 15
        for i in range(num_points + 1):
            t = i / num_points
            r = start_radius + (end_radius - start_radius) * t
            theta = math.radians(angle + curve_angle * math.sin(math.pi * t))
            x = r * math.cos(theta)
            y = r * math.sin(theta)
            points.append((x, y))
        
        spoke = (
            cq.Workplane("XY")
            .polyline(points)
            .offset(spokes.width / 2, kind="arc")
            .close()
            .extrude(spokes.thickness)
        )
        
        return spoke
    
    def _create_spokes(self) -> cq.Workplane:
        spokes = self.features.spokes
        
        if self.config.get("spoke_strategy") == "linear":
            return super()._create_spokes()

        if spokes.type == SpokeType.SOLID:
            return super()._create_spokes()
        
        all_spokes = None
        for i in range(spokes.count):
            try:
                spoke = self._create_curved_spoke(i)
            except Exception:
                spoke = self._create_spoke(i)
            
            if all_spokes is None:
                all_spokes = spoke
            else:
                all_spokes = all_spokes.union(spoke)
        
        return all_spokes
    
    def _create_ventilation_holes(self) -> Optional[cq.Workplane]:
        spokes = self.features.spokes
        hub = self.features.hub
        
        if spokes.type != SpokeType.HOLLOW:
            return None
        
        hole_radius = spokes.width * 0.3
        hole_count = spokes.count
        
        holes = None
        for i in range(hole_count):
            angle = (360 / hole_count) * i
            radius = (hub.outer_diameter + self.features.rim.inner_diameter) / 4
            
            hole = (
                cq.Workplane("XY")
                .transformed(rotate=(0, 0, angle))
                .moveTo(radius, 0)
                .circle(hole_radius)
                .extrude(spokes.thickness + 2)
            )
            
            if holes is None:
                holes = hole
            else:
                holes = holes.union(hole)
        
        return holes
    
    def build_model(self) -> cq.Workplane:
        wheel = super().build_model()
        
        ventilation_holes = self._create_ventilation_holes()
        if ventilation_holes is not None:
            wheel = wheel.cut(ventilation_holes)
        
        self.result = wheel
        return wheel
