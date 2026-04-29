from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from openai import OpenAI

from llm.rulebook import coordinator_rulebook, optimization_rulebook, sanitize_adjustments
from llm.schemas import LLMTraceRecord, RuleBoundDecision


class LLMPolicyEngine:
    def __init__(
        self,
        runtime_dir: str,
        enabled: bool = False,
        model: Optional[str] = None,
    ) -> None:
        self.runtime_dir = runtime_dir
        self.enabled = bool(enabled)
        self.model = model or os.getenv("WHEEL_AGENT_LLM_MODEL") or "gpt-4o-mini"
        self.trace_path = os.path.join(runtime_dir, "llm_decisions.jsonl")
        api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=api_key) if self.enabled and api_key else None

    def available(self) -> bool:
        return self.client is not None

    def plan_coordinator(
        self,
        *,
        mode: str,
        goal: Dict[str, Any],
        worker_result: Optional[Dict[str, Any]],
        shared_state: Dict[str, Any],
    ) -> Optional[RuleBoundDecision]:
        if not self.available():
            return None

        request_payload = {
            "mode": mode,
            "goal": goal,
            "worker_result": worker_result or {},
            "latest_scores": shared_state.get("latest_scores", {}),
            "latest_artifacts": shared_state.get("latest_artifacts", {}),
            "rulebook": coordinator_rulebook(),
        }
        system_prompt = (
            "你是轮毂建模系统中的规则约束型协调规划器。"
            "你只能在既有执行顺序和白名单配置项内提出建议，不能绕过规则。"
            "输出必须是 JSON。"
        )
        response = self._request_decision(system_prompt, request_payload)
        if response is None:
            return None

        perception_adjustments, modeling_adjustments = sanitize_adjustments(
            response.perception_adjustments,
            response.modeling_adjustments,
        )
        response.perception_adjustments = perception_adjustments
        response.modeling_adjustments = modeling_adjustments
        self._log_trace(
            LLMTraceRecord(
                planner="CoordinatorPlanner",
                used_llm=True,
                model=self.model,
                request=request_payload,
                response=response.model_dump(mode="json"),
                applied=True,
                reason="Coordinator planning candidate generated.",
            )
        )
        return response

    def plan_optimization(
        self,
        *,
        evaluation: Dict[str, Any],
        current_iteration: int,
        target_score: float,
        max_iterations: int,
    ) -> Optional[RuleBoundDecision]:
        if not self.available():
            return None

        request_payload = {
            "evaluation": evaluation,
            "current_iteration": current_iteration,
            "target_score": target_score,
            "max_iterations": max_iterations,
            "rulebook": optimization_rulebook(target_score, max_iterations),
        }
        system_prompt = (
            "你是轮毂建模系统中的规则约束型优化规划器。"
            "你只能在给定分数、迭代上限和白名单调整项内输出下一步建议。"
            "输出必须是 JSON。"
        )
        response = self._request_decision(system_prompt, request_payload)
        if response is None:
            return None

        perception_adjustments, modeling_adjustments = sanitize_adjustments(
            response.perception_adjustments,
            response.modeling_adjustments,
        )
        response.perception_adjustments = perception_adjustments
        response.modeling_adjustments = modeling_adjustments
        self._log_trace(
            LLMTraceRecord(
                planner="OptimizationPlanner",
                used_llm=True,
                model=self.model,
                request=request_payload,
                response=response.model_dump(mode="json"),
                applied=True,
                reason="Optimization planning candidate generated.",
            )
        )
        return response

    def _request_decision(self, system_prompt: str, request_payload: Dict[str, Any]) -> Optional[RuleBoundDecision]:
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": (
                            "请严格输出一个 JSON 对象，字段为："
                            "decision,next_agent,rationale,confidence,stage_focus,task_brief,"
                            "evaluation_focus,risk_flags,stop_conditions,constraints_checked,"
                            "perception_adjustments,modeling_adjustments,stop_reason。\n"
                            + json.dumps(request_payload, ensure_ascii=False)
                        ),
                    },
                ],
            )
            raw_content = completion.choices[0].message.content or "{}"
            parsed = self._extract_json(raw_content)
            return RuleBoundDecision.model_validate(parsed)
        except Exception as exc:
            self._log_trace(
                LLMTraceRecord(
                    planner="LLMPolicyEngine",
                    used_llm=False,
                    model=self.model,
                    request=request_payload,
                    response={},
                    applied=False,
                    reason=f"LLM request failed: {exc}",
                )
            )
            return None

    def _extract_json(self, raw_content: str) -> Dict[str, Any]:
        text = raw_content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("LLM response does not contain a JSON object.")
        return json.loads(text[start : end + 1])

    def _log_trace(self, record: LLMTraceRecord) -> None:
        os.makedirs(self.runtime_dir, exist_ok=True)
        with open(self.trace_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n")
