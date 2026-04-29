from __future__ import annotations

from typing import Any, Dict, Tuple


ALLOWED_PERCEPTION_KEYS = {
    "num_slices": int,
    "feature_threshold": float,
    "radius_threshold": float,
    "spoke_detection_sensitivity": float,
}

ALLOWED_MODELING_KEYS = {
    "spoke_strategy": {"curved", "linear"},
    "rim_strategy": {"profile_priority", "fallback_priority"},
}


def coordinator_rulebook() -> dict:
    return {
        "hard_constraints": [
            "只能在现有任务协议允许的接收者之间路由任务。",
            "不能跳过 Perception -> Modeling -> Evaluation 的主执行顺序。",
            "不能直接修改 STL 或绕开现有工具执行层。",
            "LLM 只能给出建议，最终决策必须通过规则校验。",
        ],
        "allowed_next_agents": [
            "PerceptionAgent",
            "ModelingAgent",
            "EvaluationAgent",
            "OptimizationAgent",
            "complete",
        ],
        "allowed_adjustments": {
            "perception": sorted(ALLOWED_PERCEPTION_KEYS),
            "modeling": sorted(ALLOWED_MODELING_KEYS),
        },
    }


def optimization_rulebook(target_score: float, max_iterations: int) -> dict:
    return {
        "hard_constraints": [
            f"若 overall_score >= {target_score:.1f} 或 is_acceptable 为真，则优先结束运行。",
            f"若 iteration >= {max_iterations}，不得继续迭代。",
            "只能输出 iterate 或 complete 两类优化决策。",
            "感知和建模调整必须来自白名单配置项。",
        ],
        "allowed_decisions": ["iterate", "complete"],
        "allowed_adjustments": {
            "perception": sorted(ALLOWED_PERCEPTION_KEYS),
            "modeling": sorted(ALLOWED_MODELING_KEYS),
        },
    }


def sanitize_adjustments(
    perception_adjustments: Dict[str, Any] | None,
    modeling_adjustments: Dict[str, Any] | None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    perception_clean: Dict[str, Any] = {}
    modeling_clean: Dict[str, Any] = {}

    for key, caster in ALLOWED_PERCEPTION_KEYS.items():
        if not perception_adjustments or key not in perception_adjustments:
            continue
        try:
            perception_clean[key] = caster(perception_adjustments[key])
        except (TypeError, ValueError):
            continue

    for key, allowed_values in ALLOWED_MODELING_KEYS.items():
        if not modeling_adjustments or key not in modeling_adjustments:
            continue
        value = str(modeling_adjustments[key]).strip().lower()
        if value in allowed_values:
            modeling_clean[key] = value

    return perception_clean, modeling_clean
