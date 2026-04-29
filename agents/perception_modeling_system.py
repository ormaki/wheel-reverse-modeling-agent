import os
from typing import Dict

from agents.modeling_agent import ModelingAgent
from agents.perception_agent import PerceptionAgent


class PerceptionModelingSystem:
    """Two-agent system: PerceptionAgent + ModelingAgent."""

    def __init__(self, output_dir: str = "./output"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def run(self, stl_path: str, output_format: str = "step") -> Dict[str, str]:
        features_path = os.path.join(self.output_dir, "wheel_features.json")

        perception_agent = PerceptionAgent(stl_path=stl_path)
        perception_result = perception_agent.run_perception_skill(output_path=features_path)

        if output_format.lower() == "step":
            output_model_path = os.path.join(self.output_dir, "wheel_model.step")
        else:
            output_model_path = os.path.join(self.output_dir, "wheel_model.stl")

        modeling_agent = ModelingAgent(features=perception_result.features)
        modeling_agent.run_modeling_skill(
            output_format=output_format,
            output_path=output_model_path,
        )

        return {
            "features_json": features_path,
            "output_model": output_model_path,
        }
