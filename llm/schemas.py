from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class RuleBoundDecision(BaseModel):
    decision: Literal["dispatch", "iterate", "complete", "fallback"] = "fallback"
    next_agent: Optional[str] = None
    rationale: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    stage_focus: str = ""
    task_brief: str = ""
    evaluation_focus: List[str] = Field(default_factory=list)
    risk_flags: List[str] = Field(default_factory=list)
    stop_conditions: List[str] = Field(default_factory=list)
    constraints_checked: List[str] = Field(default_factory=list)
    perception_adjustments: Dict[str, Any] = Field(default_factory=dict)
    modeling_adjustments: Dict[str, Any] = Field(default_factory=dict)
    stop_reason: Optional[str] = None


class LLMTraceRecord(BaseModel):
    planner: str
    used_llm: bool
    model: Optional[str] = None
    request: Dict[str, Any] = Field(default_factory=dict)
    response: Dict[str, Any] = Field(default_factory=dict)
    applied: bool = False
    reason: str = ""
