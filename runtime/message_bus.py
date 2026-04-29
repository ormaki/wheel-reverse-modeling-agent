from __future__ import annotations

import json
import os
from typing import List, Optional

from models.agent_protocol import AgentTask, RuntimeEvent


class MessageBus:
    def __init__(self, runtime_dir: str):
        self.runtime_dir = runtime_dir
        self.queue: List[AgentTask] = []
        self.events_path = os.path.join(runtime_dir, "events.jsonl")
        self.queue_path = os.path.join(runtime_dir, "queue_snapshot.json")
        os.makedirs(runtime_dir, exist_ok=True)

    def publish(self, task: AgentTask) -> None:
        self.queue.append(task)
        self._persist_queue()

    def pop_next(self) -> Optional[AgentTask]:
        if not self.queue:
            return None
        task = self.queue.pop(0)
        self._persist_queue()
        return task

    def size(self) -> int:
        return len(self.queue)

    def log_event(self, event: RuntimeEvent) -> None:
        with open(self.events_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n")

    def _persist_queue(self) -> None:
        with open(self.queue_path, "w", encoding="utf-8") as f:
            json.dump(
                [task.model_dump(mode="json") for task in self.queue],
                f,
                indent=2,
                ensure_ascii=False,
            )
