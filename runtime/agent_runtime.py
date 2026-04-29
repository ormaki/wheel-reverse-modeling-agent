from __future__ import annotations

import json
import os
from typing import Any, Dict

from agents.coordinator_agent import CoordinatorAgent
from agents.evaluation_agent import EvaluationAgent
from agents.modeling_agent import AdvancedModelingAgent
from agents.optimization_agent import OptimizationAgent
from agents.perception_agent import PerceptionAgent
from llm import LLMPolicyEngine
from models.agent_protocol import AgentResult, AgentTask, RuntimeEvent, RuntimeStateSnapshot, TaskStatus, TaskType, UserGoal
from runtime.message_bus import MessageBus


class AgentRuntime:
    def __init__(
        self,
        output_dir: str = "./output",
        max_iterations: int = 3,
        target_score: float = 80.0,
        enable_llm_planning: bool = False,
        llm_model: str | None = None,
    ):
        self.output_dir = output_dir
        self.max_iterations = max_iterations
        self.target_score = target_score
        self.enable_llm_planning = enable_llm_planning
        self.llm_model = llm_model
        self.runtime_dir = os.path.join(output_dir, "runtime")
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.runtime_dir, exist_ok=True)

        self.bus = MessageBus(self.runtime_dir)
        self.policy_engine = LLMPolicyEngine(
            runtime_dir=self.runtime_dir,
            enabled=self.enable_llm_planning,
            model=self.llm_model,
        )
        self.state_path = os.path.join(self.runtime_dir, "state_snapshot.json")
        self.results_path = os.path.join(self.runtime_dir, "results.json")
        self.plan_path = os.path.join(self.runtime_dir, "latest_plan.json")
        self.goal: Dict[str, Any] = {}
        self.shared_state: Dict[str, Any] = {
            "goal": {},
            "current_iteration": 0,
            "completed_tasks": 0,
            "latest_artifacts": {},
            "latest_scores": {},
            "latest_decisions": {},
            "latest_plan": {},
            "task_history": [],
            "result_history": [],
            "status": "idle",
        }

    def run(
        self,
        stl_path: str,
        output_format: str = "step",
        enable_optimization: bool = True,
    ) -> Dict[str, str]:
        user_goal = UserGoal(
            objective="Convert STL to CAD model through the multi-agent runtime.",
            stl_path=stl_path,
            output_dir=self.output_dir,
            output_format=output_format,
            enable_optimization=enable_optimization,
            enable_llm_planning=self.enable_llm_planning,
            llm_model=self.llm_model,
            max_iterations=self.max_iterations,
            target_score=self.target_score,
        )
        return self.run_goal(user_goal)

    def run_goal(self, user_goal: UserGoal) -> Dict[str, str]:
        self.policy_engine = LLMPolicyEngine(
            runtime_dir=self.runtime_dir,
            enabled=bool(user_goal.enable_llm_planning),
            model=user_goal.llm_model,
        )
        self.goal = user_goal.model_dump(mode="json")
        self.shared_state["goal"] = dict(self.goal)
        self.shared_state["status"] = "running"
        self.shared_state["latest_decisions"]["llm_planning"] = "enabled" if self.policy_engine.available() else "disabled"
        self._log_event("runtime_started", "AgentRuntime", self.goal)

        self.bus.publish(
            AgentTask(
                type=TaskType.COORDINATE,
                sender="User",
                receiver="CoordinatorAgent",
                payload={
                    "mode": "start",
                    "goal": self.goal,
                },
                iteration=0,
            )
        )
        self._persist_state()

        while self.bus.size() > 0:
            task = self.bus.pop_next()
            if task is None:
                break

            task.status = TaskStatus.RUNNING
            self.shared_state["task_history"].append(task.model_dump(mode="json"))
            self._log_event(
                "task_started",
                task.receiver,
                {"task_id": task.id, "task_type": task.type.value, "iteration": task.iteration},
            )

            result = self._execute_task(task)
            self.shared_state["result_history"].append(result.model_dump(mode="json"))

            if not result.success:
                self.shared_state["status"] = "failed"
                self._log_event(
                    "task_failed",
                    result.sender,
                    {"task_id": task.id, "reason": result.reason or "unknown"},
                )
                self._persist_state()
                raise RuntimeError(result.reason or f"{result.sender} failed")

            task.status = TaskStatus.COMPLETED
            self.shared_state["completed_tasks"] += 1
            self._apply_result(task, result)

            tasks_to_queue = self._resolve_follow_up_tasks(task, result)
            for next_task in tasks_to_queue:
                self.bus.publish(next_task)

            self._log_event(
                "task_completed",
                result.sender,
                {"task_id": task.id, "output_type": result.output_type},
            )
            self._persist_state()

            if task.receiver == "CoordinatorAgent" and result.output_type == "runtime_complete":
                self.shared_state["status"] = "completed"
                self._persist_state()
                return result.payload.get("results", {})

        self.shared_state["status"] = "completed"
        self._persist_state()
        return self._build_results()

    def _resolve_follow_up_tasks(self, task: AgentTask, result: AgentResult) -> list[AgentTask]:
        if task.receiver == "CoordinatorAgent":
            return result.next_tasks

        return [
            AgentTask(
                type=TaskType.COORDINATE,
                sender=result.sender,
                receiver="CoordinatorAgent",
                iteration=task.iteration,
                parent_task_id=task.id,
                payload={
                    "mode": "handle_result",
                    "worker_task": task.model_dump(mode="json"),
                    "worker_result": result.model_dump(mode="json"),
                },
            )
        ]

    def _execute_task(self, task: AgentTask) -> AgentResult:
        if task.receiver == "CoordinatorAgent":
            agent = CoordinatorAgent(
                target_score=self.target_score,
                max_iterations=self.max_iterations,
                policy_engine=self.policy_engine,
            )
            return agent.handle_task(task, self.shared_state)

        if task.receiver == "PerceptionAgent":
            agent = PerceptionAgent(
                stl_path=task.payload["stl_path"],
                config=task.payload.get("config"),
            )
            return agent.handle_task(task, self.shared_state)

        if task.receiver == "ModelingAgent":
            agent = AdvancedModelingAgent.from_json(
                task.payload["features_path"],
                config=task.payload.get("modeling_config"),
            )
            return agent.handle_task(task, self.shared_state)

        if task.receiver == "EvaluationAgent":
            agent = EvaluationAgent(
                stl_path=task.payload["stl_path"],
                step_path=task.payload["model_path"],
                features_path=task.payload["features_path"],
                config=task.payload.get("config"),
            )
            return agent.handle_task(task, self.shared_state)

        if task.receiver == "OptimizationAgent":
            agent = OptimizationAgent(
                target_score=self.target_score,
                max_iterations=self.max_iterations,
                policy_engine=self.policy_engine,
            )
            return agent.handle_task(task, self.shared_state)

        raise ValueError(f"Unsupported task receiver: {task.receiver}")

    def _apply_result(self, task: AgentTask, result: AgentResult) -> None:
        if task.receiver == "CoordinatorAgent":
            if "next_iteration" in result.payload:
                self.shared_state["current_iteration"] = int(result.payload["next_iteration"])
            planning_source = result.payload.get("planning_source")
            if planning_source:
                self.shared_state["latest_decisions"]["coordinator"] = str(planning_source)
            if "planner_context" in result.payload:
                self.shared_state["latest_plan"]["coordinator"] = result.payload["planner_context"]
            self.shared_state["latest_artifacts"]["runtime_state"] = self.state_path
            return

        for artifact in result.artifacts:
            self.shared_state["latest_artifacts"][artifact.name] = artifact.path

        if result.output_type == "features_extracted":
            summary = result.payload.get("feature_summary", {})
            self.shared_state["latest_scores"]["feature_overall_diameter"] = float(
                summary.get("overall_diameter", 0.0)
            )

        if result.output_type in {"evaluation_completed", "runtime_complete"}:
            score = float(result.payload.get("overall_score", 0.0))
            self.shared_state["latest_scores"]["overall_score"] = score
            self.shared_state["current_iteration"] = task.iteration

        if result.output_type == "optimization_plan":
            self.shared_state["current_iteration"] = int(result.payload.get("next_iteration", task.iteration))
            planning_source = result.payload.get("planning_source")
            if planning_source:
                self.shared_state["latest_decisions"]["optimization"] = str(planning_source)
            if "planner_context" in result.payload:
                self.shared_state["latest_plan"]["optimization"] = result.payload["planner_context"]

        if result.output_type == "runtime_complete":
            planning_source = result.payload.get("planning_source")
            if planning_source:
                self.shared_state["latest_decisions"]["completion"] = str(planning_source)
            if "planner_context" in result.payload:
                self.shared_state["latest_plan"]["completion"] = result.payload["planner_context"]

        self.shared_state["latest_artifacts"]["runtime_state"] = self.state_path

    def _build_results(self) -> Dict[str, str]:
        results: Dict[str, str] = {}
        artifact_map = {
            "features_json": "features_json",
            "output_model": "output_model",
            "evaluation_report": "evaluation_report",
            "evaluation_visualization": "evaluation_visualization",
            "runtime_state": "runtime_state",
        }
        for public_name, artifact_name in artifact_map.items():
            artifact_path = self.shared_state["latest_artifacts"].get(artifact_name)
            if artifact_path:
                results[public_name] = artifact_path
        return results

    def _persist_state(self) -> None:
        snapshot = RuntimeStateSnapshot(
            goal=self.goal,
            queue_size=self.bus.size(),
            current_iteration=int(self.shared_state["current_iteration"]),
            completed_tasks=int(self.shared_state["completed_tasks"]),
            latest_artifacts=dict(self.shared_state["latest_artifacts"]),
            latest_scores={k: float(v) for k, v in self.shared_state["latest_scores"].items()},
            latest_decisions=dict(self.shared_state["latest_decisions"]),
            latest_plan=dict(self.shared_state["latest_plan"]),
            runtime_status=self.shared_state["status"],
        )
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(snapshot.model_dump(mode="json"), f, indent=2, ensure_ascii=False)
        with open(self.results_path, "w", encoding="utf-8") as f:
            json.dump(self.shared_state["result_history"], f, indent=2, ensure_ascii=False)
        with open(self.plan_path, "w", encoding="utf-8") as f:
            json.dump(self.shared_state["latest_plan"], f, indent=2, ensure_ascii=False)

    def _log_event(self, event_type: str, actor: str, detail: Dict[str, Any]) -> None:
        self.bus.log_event(RuntimeEvent(event_type=event_type, actor=actor, detail=detail))
