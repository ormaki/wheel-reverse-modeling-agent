from __future__ import annotations

from importlib import import_module


_EXPORTS = {
    "PerceptionAgent": (".perception_agent", "PerceptionAgent"),
    "ModelingAgent": (".modeling_agent", "ModelingAgent"),
    "AdvancedModelingAgent": (".modeling_agent", "AdvancedModelingAgent"),
    "AgentCoordinator": (".coordinator", "AgentCoordinator"),
    "CoordinatorAgent": (".coordinator_agent", "CoordinatorAgent"),
    "EvaluationAgent": (".evaluation_agent", "EvaluationAgent"),
    "EvaluationResult": (".evaluation_agent", "EvaluationResult"),
    "DifferenceReport": (".evaluation_agent", "DifferenceReport"),
    "DifferenceType": (".evaluation_agent", "DifferenceType"),
    "Severity": (".evaluation_agent", "Severity"),
    "OptimizationAgent": (".optimization_agent", "OptimizationAgent"),
    "PerceptionModelingSystem": (".perception_modeling_system", "PerceptionModelingSystem"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _EXPORTS[name]
    module = import_module(module_name, __name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value

