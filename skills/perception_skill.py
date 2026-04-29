from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from models.wheel_features import WheelFeatures

if TYPE_CHECKING:
    from agents.perception_agent import PerceptionAgent


@dataclass
class PerceptionSkillResult:
    features: WheelFeatures
    features_path: Optional[str] = None


class PerceptionSkill:
    """Feature extraction skill used by the perception agent."""

    def run(
        self,
        agent: "PerceptionAgent",
        output_path: Optional[str] = None,
    ) -> PerceptionSkillResult:
        features = agent.extract_features()

        if output_path:
            features.to_json(output_path)

        return PerceptionSkillResult(
            features=features,
            features_path=output_path,
        )
