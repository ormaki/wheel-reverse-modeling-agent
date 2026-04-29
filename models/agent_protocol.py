from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


class TaskType(str, Enum):
    COORDINATE = "coordinate"
    EXTRACT_FEATURES = "extract_features"
    BUILD_MODEL = "build_model"
    EVALUATE_MODEL = "evaluate_model"
    OPTIMIZE_SYSTEM = "optimize_system"
    COMPLETE = "complete"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ArtifactRecord(BaseModel):
    name: str
    path: str


class UserGoal(BaseModel):
    objective: str
    stl_path: str
    output_dir: str = "./output"
    output_format: str = "step"
    enable_optimization: bool = True
    enable_llm_planning: bool = False
    llm_model: Optional[str] = None
    max_iterations: int = 3
    target_score: float = 80.0
    constraints: List[str] = Field(default_factory=list)
    deliverables: List[str] = Field(default_factory=list)


class AgentTask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    type: TaskType
    sender: str
    receiver: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    iteration: int = 0
    parent_task_id: Optional[str] = None
    created_at: str = Field(default_factory=utc_now_iso)
    status: TaskStatus = TaskStatus.PENDING


class AgentResult(BaseModel):
    task_id: str
    sender: str
    success: bool
    output_type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    artifacts: List[ArtifactRecord] = Field(default_factory=list)
    next_tasks: List[AgentTask] = Field(default_factory=list)
    reason: Optional[str] = None
    created_at: str = Field(default_factory=utc_now_iso)


class RuntimeEvent(BaseModel):
    event_type: str
    actor: str
    detail: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)


class RuntimeStateSnapshot(BaseModel):
    goal: Dict[str, Any]
    queue_size: int
    current_iteration: int
    completed_tasks: int
    latest_artifacts: Dict[str, str] = Field(default_factory=dict)
    latest_scores: Dict[str, float] = Field(default_factory=dict)
    latest_decisions: Dict[str, str] = Field(default_factory=dict)
    latest_plan: Dict[str, Any] = Field(default_factory=dict)
    runtime_status: str
    last_event_at: str = Field(default_factory=utc_now_iso)
