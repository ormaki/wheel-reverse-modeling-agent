from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from llm import LLMPolicyEngine
from models.agent_protocol import AgentResult, AgentTask, TaskType, UserGoal


class CoordinatorAgent:
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
        if task.type != TaskType.COORDINATE:
            return AgentResult(
                task_id=task.id,
                sender="CoordinatorAgent",
                success=False,
                output_type="unsupported_task",
                reason=f"CoordinatorAgent cannot handle task type {task.type.value}",
            )

        mode = task.payload.get("mode", "start")
        if mode == "start":
            goal = UserGoal(**task.payload["goal"])
            return self._start_goal(task, goal)

        if mode == "handle_result":
            worker_result = task.payload["worker_result"]
            return self._handle_worker_result(task, worker_result, context)

        return AgentResult(
            task_id=task.id,
            sender="CoordinatorAgent",
            success=False,
            output_type="unsupported_mode",
            reason=f"Unsupported coordinator mode: {mode}",
        )

    def _start_goal(self, task: AgentTask, goal: UserGoal) -> AgentResult:
        planning_hint = self._llm_plan(
            mode="start",
            goal=goal.model_dump(mode="json"),
            worker_result=None,
            context={"goal": goal.model_dump(mode="json"), "latest_scores": {}, "latest_artifacts": {}},
        )
        output_name = "wheel_features.json"
        next_task = AgentTask(
            type=TaskType.EXTRACT_FEATURES,
            sender="CoordinatorAgent",
            receiver="PerceptionAgent",
            iteration=0,
            parent_task_id=task.id,
            payload={
                "stl_path": goal.stl_path,
                "output_path": os.path.join(goal.output_dir, output_name),
                "config": planning_hint.get("perception_adjustments", {}),
                "model_output_format": goal.output_format,
                "enable_optimization": goal.enable_optimization,
                "modeling_config": planning_hint.get("modeling_adjustments", {}),
                "planner_context": planning_hint.get("planner_context", {}),
            },
        )
        return AgentResult(
            task_id=task.id,
            sender="CoordinatorAgent",
            success=True,
            output_type="coordination_started",
            payload={
                "objective": goal.objective,
                "planning_source": planning_hint.get("planning_source", "rules_only"),
                "planning_rationale": planning_hint.get("rationale", ""),
                "planner_context": planning_hint.get("planner_context", {}),
            },
            next_tasks=[next_task],
        )

    def _handle_worker_result(
        self,
        task: AgentTask,
        worker_result: Dict[str, Any],
        context: Dict[str, Any],
    ) -> AgentResult:
        output_type = worker_result["output_type"]
        payload = worker_result.get("payload", {})
        goal = context.get("goal", {})
        output_dir = goal.get("output_dir", "./output")

        if output_type == "features_extracted":
            planning_hint = self._llm_plan(
                mode="features_extracted",
                goal=goal,
                worker_result=worker_result,
                context=context,
            )
            output_format = goal.get("output_format", "step")
            extension = "step" if output_format.lower() == "step" else "stl"
            model_name = "wheel_model" if task.iteration == 0 else f"wheel_model_iter{task.iteration}"
            next_task = AgentTask(
                type=TaskType.BUILD_MODEL,
                sender="CoordinatorAgent",
                receiver="ModelingAgent",
                iteration=task.iteration,
                parent_task_id=task.id,
                payload={
                    "features_path": payload["features_path"],
                    "output_path": os.path.join(output_dir, f"{model_name}.{extension}"),
                    "output_format": output_format,
                    "stl_path": goal["stl_path"],
                    "enable_optimization": goal.get("enable_optimization", True),
                    "modeling_config": planning_hint.get("modeling_adjustments", {}),
                    "planner_context": planning_hint.get("planner_context", {}),
                },
            )
            return AgentResult(
                task_id=task.id,
                sender="CoordinatorAgent",
                success=True,
                output_type="coordination_progress",
                payload={
                    "next_agent": "ModelingAgent",
                    "planning_source": planning_hint.get("planning_source", "rules_only"),
                    "planning_rationale": planning_hint.get("rationale", ""),
                    "planner_context": planning_hint.get("planner_context", {}),
                },
                next_tasks=[next_task],
            )

        if output_type == "model_built":
            planning_hint = self._llm_plan(
                mode="model_built",
                goal=goal,
                worker_result=worker_result,
                context=context,
            )
            report_dir = os.path.dirname(payload["model_path"])
            next_task = AgentTask(
                type=TaskType.EVALUATE_MODEL,
                sender="CoordinatorAgent",
                receiver="EvaluationAgent",
                iteration=task.iteration,
                parent_task_id=task.id,
                payload={
                    "stl_path": goal["stl_path"],
                    "features_path": context["latest_artifacts"]["features_json"],
                    "model_path": payload["model_path"],
                    "output_dir": report_dir,
                    "output_format": payload["output_format"],
                    "enable_optimization": goal.get("enable_optimization", True),
                    "planner_context": planning_hint.get("planner_context", {}),
                },
            )
            return AgentResult(
                task_id=task.id,
                sender="CoordinatorAgent",
                success=True,
                output_type="coordination_progress",
                payload={
                    "next_agent": "EvaluationAgent",
                    "planning_source": planning_hint.get("planning_source", "rules_only"),
                    "planning_rationale": planning_hint.get("rationale", ""),
                    "planner_context": planning_hint.get("planner_context", {}),
                },
                next_tasks=[next_task],
            )

        if output_type == "evaluation_completed":
            if not goal.get("enable_optimization", True):
                return self._complete(task, context, payload)

            planning_hint = self._llm_plan(
                mode="evaluation_completed",
                goal=goal,
                worker_result=worker_result,
                context=context,
            )
            next_task = AgentTask(
                type=TaskType.OPTIMIZE_SYSTEM,
                sender="CoordinatorAgent",
                receiver="OptimizationAgent",
                iteration=task.iteration,
                parent_task_id=task.id,
                payload={
                    "stl_path": goal["stl_path"],
                    "features_path": context["latest_artifacts"]["features_json"],
                    "model_path": context["latest_artifacts"]["output_model"],
                    "output_dir": output_dir,
                    "output_format": goal.get("output_format", "step"),
                    "evaluation": payload,
                    "planner_context": planning_hint.get("planner_context", {}),
                },
            )
            return AgentResult(
                task_id=task.id,
                sender="CoordinatorAgent",
                success=True,
                output_type="coordination_progress",
                payload={
                    "next_agent": "OptimizationAgent",
                    "planning_source": planning_hint.get("planning_source", "rules_only"),
                    "planning_rationale": planning_hint.get("rationale", ""),
                    "planner_context": planning_hint.get("planner_context", {}),
                },
                next_tasks=[next_task],
            )

        if output_type == "optimization_plan":
            decision = payload.get("decision")
            if decision == "iterate":
                next_iteration = int(payload["next_iteration"])
                planning_hint = self._llm_plan(
                    mode="optimization_plan",
                    goal=goal,
                    worker_result=worker_result,
                    context=context,
                )
                next_task = AgentTask(
                    type=TaskType.EXTRACT_FEATURES,
                    sender="CoordinatorAgent",
                    receiver="PerceptionAgent",
                    iteration=next_iteration,
                    parent_task_id=task.id,
                    payload={
                        "stl_path": goal["stl_path"],
                        "output_path": os.path.join(output_dir, f"wheel_features_iter{next_iteration}.json"),
                        "config": payload.get("perception_adjustments", {}),
                        "modeling_config": payload.get("modeling_adjustments", {}),
                        "model_output_format": goal.get("output_format", "step"),
                        "enable_optimization": True,
                        "planner_context": planning_hint.get("planner_context", {}),
                    },
                )
                return AgentResult(
                    task_id=task.id,
                    sender="CoordinatorAgent",
                    success=True,
                    output_type="coordination_progress",
                    payload={
                        "next_agent": "PerceptionAgent",
                        "next_iteration": next_iteration,
                        "planning_source": planning_hint.get("planning_source", "rules_only"),
                        "planning_rationale": planning_hint.get("rationale", ""),
                        "planner_context": planning_hint.get("planner_context", {}),
                    },
                    next_tasks=[next_task],
                )

            return self._complete(task, context, {"overall_score": context.get("latest_scores", {}).get("overall_score", 0.0)})

        if output_type == "runtime_complete":
            return self._complete(task, context, payload)

        return AgentResult(
            task_id=task.id,
            sender="CoordinatorAgent",
            success=False,
            output_type="unsupported_worker_output",
            reason=f"Unsupported worker output: {output_type}",
        )

    def _complete(self, task: AgentTask, context: Dict[str, Any], payload: Dict[str, Any]) -> AgentResult:
        return AgentResult(
            task_id=task.id,
            sender="CoordinatorAgent",
            success=True,
            output_type="runtime_complete",
            payload={
                "overall_score": float(payload.get("overall_score", context.get("latest_scores", {}).get("overall_score", 0.0))),
                "results": self._build_results(context),
                "planning_source": payload.get("planning_source", "rules_only"),
                "planner_context": payload.get("planner_context", {}),
            },
        )

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

    def _llm_plan(
        self,
        *,
        mode: str,
        goal: Dict[str, Any],
        worker_result: Optional[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        if self.policy_engine is None:
            return {"planning_source": "rules_only"}
        decision = self.policy_engine.plan_coordinator(
            mode=mode,
            goal=goal,
            worker_result=worker_result,
            shared_state=context,
        )
        if decision is None:
            return {"planning_source": "rules_only"}
        planner_context = {
            "stage_focus": decision.stage_focus,
            "task_brief": decision.task_brief,
            "evaluation_focus": decision.evaluation_focus,
            "risk_flags": decision.risk_flags,
            "stop_conditions": decision.stop_conditions,
            "constraints_checked": decision.constraints_checked,
            "confidence": decision.confidence,
        }
        return {
            "planning_source": "llm_rule_guarded",
            "rationale": decision.rationale,
            "perception_adjustments": decision.perception_adjustments,
            "modeling_adjustments": decision.modeling_adjustments,
            "planner_context": planner_context,
        }
