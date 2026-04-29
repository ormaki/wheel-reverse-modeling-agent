from __future__ import annotations

import json
import os
import re
from typing import List, Optional

from models.agent_protocol import UserGoal
from runtime.agent_runtime import AgentRuntime


class UserConsole:
    def __init__(
        self,
        output_dir: str = "./output",
        max_iterations: int = 3,
        target_score: float = 80.0,
        enable_llm_planning: bool = False,
        llm_model: Optional[str] = None,
    ):
        self.output_dir = output_dir
        self.max_iterations = max_iterations
        self.target_score = target_score
        self.enable_llm_planning = enable_llm_planning
        self.llm_model = llm_model

    def build_goal(
        self,
        request: str,
        stl_path: str,
        output_format: str = "step",
        enable_optimization: bool = True,
    ) -> UserGoal:
        normalized_request = (request or "").strip()
        inferred_format = self._detect_output_format(normalized_request, output_format)
        inferred_optimization = self._detect_optimization_flag(normalized_request, enable_optimization)
        inferred_iterations = self._detect_max_iterations(normalized_request, self.max_iterations)
        inferred_target_score = self._detect_target_score(normalized_request, self.target_score)
        constraints = self._extract_constraints(normalized_request)
        deliverables = self._build_deliverables(inferred_format)

        objective = normalized_request or f"Process {os.path.basename(stl_path)} into a {inferred_format.upper()} model."

        return UserGoal(
            objective=objective,
            stl_path=stl_path,
            output_dir=self.output_dir,
            output_format=inferred_format,
            enable_optimization=inferred_optimization,
            enable_llm_planning=self.enable_llm_planning,
            llm_model=self.llm_model,
            max_iterations=inferred_iterations,
            target_score=inferred_target_score,
            constraints=constraints,
            deliverables=deliverables,
        )

    def run_request(
        self,
        request: str,
        stl_path: str,
        output_format: str = "step",
        enable_optimization: bool = True,
    ) -> dict:
        goal = self.build_goal(
            request=request,
            stl_path=stl_path,
            output_format=output_format,
            enable_optimization=enable_optimization,
        )
        self._persist_goal(goal)

        runtime = AgentRuntime(
            output_dir=goal.output_dir,
            max_iterations=goal.max_iterations,
            target_score=goal.target_score,
            enable_llm_planning=goal.enable_llm_planning,
            llm_model=goal.llm_model,
        )
        return runtime.run_goal(goal)

    def _persist_goal(self, goal: UserGoal) -> None:
        runtime_dir = os.path.join(goal.output_dir, "runtime")
        os.makedirs(runtime_dir, exist_ok=True)
        goal_path = os.path.join(runtime_dir, "user_goal.json")
        with open(goal_path, "w", encoding="utf-8") as f:
            json.dump(goal.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

    def _detect_output_format(self, request: str, fallback: str) -> str:
        lowered = request.lower()
        if " stl" in lowered or lowered.endswith("stl") or "输出stl" in request:
            return "stl"
        if " step" in lowered or lowered.endswith("step") or "输出step" in request:
            return "step"
        return fallback

    def _detect_optimization_flag(self, request: str, fallback: bool) -> bool:
        lowered = request.lower()
        disable_markers = [
            "不要优化",
            "不优化",
            "禁用优化",
            "no optimize",
            "without optimization",
        ]
        enable_markers = [
            "允许优化",
            "自动优化",
            "迭代",
            "optimization",
        ]
        if any(marker in lowered or marker in request for marker in disable_markers):
            return False
        if any(marker in lowered or marker in request for marker in enable_markers):
            return True
        return fallback

    def _detect_max_iterations(self, request: str, fallback: int) -> int:
        patterns = [
            r"最多\s*(\d+)\s*轮",
            r"最大\s*(\d+)\s*轮",
            r"max(?:imum)?\s+(\d+)\s+iterations?",
        ]
        for pattern in patterns:
            match = re.search(pattern, request, flags=re.IGNORECASE)
            if match:
                return max(0, int(match.group(1)))
        return fallback

    def _detect_target_score(self, request: str, fallback: float) -> float:
        patterns = [
            r"目标分数\s*(\d+(?:\.\d+)?)",
            r"目标评分\s*(\d+(?:\.\d+)?)",
            r"target score\s*(\d+(?:\.\d+)?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, request, flags=re.IGNORECASE)
            if match:
                return float(match.group(1))
        return fallback

    def _extract_constraints(self, request: str) -> List[str]:
        constraints: List[str] = []
        for raw_line in request.splitlines():
            line = raw_line.strip(" -\t")
            if not line:
                continue
            if line.startswith("约束") or line.startswith("限制") or line.lower().startswith("constraint"):
                constraints.append(line)
                continue
            if any(keyword in line for keyword in ["不要", "必须", "仅", "保留", "输出"]):
                constraints.append(line)
        return constraints

    def _build_deliverables(self, output_format: str) -> List[str]:
        model_name = "wheel_model.step" if output_format == "step" else "wheel_model.stl"
        return [
            "wheel_features.json",
            model_name,
            "evaluation_report.json",
            "evaluation_comparison.png",
            "runtime/state_snapshot.json",
        ]
