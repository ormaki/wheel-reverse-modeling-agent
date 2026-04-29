from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

import cadquery as cq

if TYPE_CHECKING:
    from agents.modeling_agent import ModelingAgent


@dataclass
class ModelingSkillResult:
    model: cq.Workplane
    output_path: Optional[str]
    output_format: str


class ModelingSkill:
    """Parameterized CAD modeling skill used by the modeling agent."""

    def run(
        self,
        agent: "ModelingAgent",
        output_format: str = "step",
        output_path: Optional[str] = None,
    ) -> ModelingSkillResult:
        normalized_format = output_format.lower()
        if normalized_format not in {"step", "stl"}:
            raise ValueError(f"Unsupported output format: {output_format}")

        model = agent.build_model()

        if output_path:
            if normalized_format == "step":
                agent.export_step(output_path)
            else:
                agent.export_stl(output_path)

        return ModelingSkillResult(
            model=model,
            output_path=output_path,
            output_format=normalized_format,
        )
