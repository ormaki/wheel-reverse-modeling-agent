from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from llm import LLMPolicyEngine
from models.agent_protocol import AgentResult, AgentTask, ArtifactRecord, TaskType


class OptimizationAgent:
    def __init__(
        self,
        target_score: float = 80.0,
        max_iterations: int = 3,
        policy_engine: Optional[LLMPolicyEngine] = None,
    ):
        self.target_score = target_score
        self.max_iterations = max_iterations
        self.policy_engine = policy_engine

    def handle_task(self, task: AgentTask, context: Dict[str, Any]) -> AgentResult:
        evaluation = task.payload.get("evaluation", {})
        current_iteration = int(task.iteration)
        current_score = float(evaluation.get("overall_score", 0.0))
        is_acceptable = bool(evaluation.get("is_acceptable", False))
        output_dir = str(task.payload["output_dir"])

        if is_acceptable or current_score >= self.target_score:
            results = self._build_results(context)
            return AgentResult(
                task_id=task.id,
                sender="OptimizationAgent",
                success=True,
                output_type="runtime_complete",
                payload={
                    "decision": "complete",
                    "overall_score": current_score,
                    "results": results,
                },
                artifacts=[ArtifactRecord(name="runtime_state", path=os.path.join(output_dir, "runtime", "state_snapshot.json"))],
            )

        if current_iteration >= self.max_iterations:
            results = self._build_results(context)
            return AgentResult(
                task_id=task.id,
                sender="OptimizationAgent",
                success=True,
                output_type="runtime_complete",
                payload={
                    "decision": "stop_max_iterations",
                    "overall_score": current_score,
                    "results": results,
                },
                artifacts=[ArtifactRecord(name="runtime_state", path=os.path.join(output_dir, "runtime", "state_snapshot.json"))],
            )

        next_iteration = current_iteration + 1
        planning_source = "rules_only"
        llm_decision = None
        if self.policy_engine is not None:
            llm_decision = self.policy_engine.plan_optimization(
                evaluation=evaluation,
                current_iteration=current_iteration,
                target_score=self.target_score,
                max_iterations=self.max_iterations,
            )

        if llm_decision is not None:
            planning_source = "llm_rule_guarded"
            planner_context = {
                "stage_focus": llm_decision.stage_focus,
                "task_brief": llm_decision.task_brief,
                "evaluation_focus": llm_decision.evaluation_focus,
                "risk_flags": llm_decision.risk_flags,
                "stop_conditions": llm_decision.stop_conditions,
                "constraints_checked": llm_decision.constraints_checked,
                "confidence": llm_decision.confidence,
            }
            if llm_decision.decision == "complete":
                results = self._build_results(context)
                return AgentResult(
                    task_id=task.id,
                    sender="OptimizationAgent",
                    success=True,
                    output_type="runtime_complete",
                    payload={
                        "decision": llm_decision.stop_reason or "complete",
                        "overall_score": current_score,
                        "results": results,
                        "planning_source": planning_source,
                        "planning_rationale": llm_decision.rationale,
                        "planner_context": planner_context,
                    },
                    artifacts=[ArtifactRecord(name="runtime_state", path=os.path.join(output_dir, "runtime", "state_snapshot.json"))],
                )
            perception_adjustments = llm_decision.perception_adjustments
            modeling_adjustments = llm_decision.modeling_adjustments
        else:
            perception_adjustments, modeling_adjustments = self._plan_adjustments(evaluation)
            planner_context = {}

        next_tasks: List[AgentTask] = [
            AgentTask(
                type=TaskType.EXTRACT_FEATURES,
                sender="OptimizationAgent",
                receiver="PerceptionAgent",
                iteration=next_iteration,
                parent_task_id=task.id,
                payload={
                    "stl_path": task.payload["stl_path"],
                    "output_path": os.path.join(output_dir, f"wheel_features_iter{next_iteration}.json"),
                    "config": perception_adjustments,
                    "modeling_config": modeling_adjustments,
                    "model_output_format": task.payload["output_format"],
                    "enable_optimization": True,
                },
            )
        ]

        return AgentResult(
            task_id=task.id,
            sender="OptimizationAgent",
            success=True,
            output_type="optimization_plan",
            payload={
                "decision": "iterate",
                "current_score": current_score,
                "next_iteration": next_iteration,
                "perception_adjustments": perception_adjustments,
                "modeling_adjustments": modeling_adjustments,
                "planning_source": planning_source,
                "planning_rationale": llm_decision.rationale if llm_decision is not None else "",
                "planner_context": planner_context,
            },
            next_tasks=next_tasks,
        )

    def _plan_adjustments(self, evaluation: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
        differences = evaluation.get("differences", [])
        perception_adjustments: Dict[str, Any] = {}
        modeling_adjustments: Dict[str, Any] = {}

        for diff in differences:
            component = str(diff.get("component", "")).lower()
            difference_type = str(diff.get("difference_type", "")).lower()

            if "profile" in difference_type or "rim" in component:
                perception_adjustments["num_slices"] = 4000
                perception_adjustments["feature_threshold"] = 0.35

            if "dimension" in difference_type or "overall" in component:
                perception_adjustments["radius_threshold"] = 0.7

            if "spoke" in component:
                perception_adjustments["spoke_detection_sensitivity"] = 1.2
                modeling_adjustments["spoke_strategy"] = "curved"

            if "shape" in difference_type:
                modeling_adjustments["rim_strategy"] = "profile_priority"

        return perception_adjustments, modeling_adjustments

    def _build_results(self, context: Dict[str, Any]) -> Dict[str, str]:
        artifact_names = [
            "features_json",
            "output_model",
            "evaluation_report",
            "evaluation_visualization",
            "runtime_state",
        ]
        latest_artifacts = context.get("latest_artifacts", {})
        return {
            name: latest_artifacts[name]
            for name in artifact_names
            if name in latest_artifacts
        }
