# Agent System Status

## Current State

This repository now contains two execution paths:

- Legacy pipeline path:
  `main.py --mode full`
- Runtime-driven agent system path:
  `main.py --mode runtime`
- User console path:
  `main.py --mode console --request "..."`
- Stage-driven build path:
  `main.py --mode stage --stage 01|02|03|04`

The runtime path is the active foundation for the real agent system build-out.
The user-facing entrypoint for that runtime is now `CoordinatorAgent`.
The user-facing control surface is `UserConsole`, which converts user requests into `UserGoal`.

## Runtime Architecture

Implemented components:

- `console/user_console.py`
  Converts a user request string into `UserGoal`, persists `user_goal.json`, and invokes the runtime through `run_goal()`.
- `agents/coordinator_agent.py`
  Owns the user goal, routes worker results, and decides the next internal task.
- `models/agent_protocol.py`
  Defines `UserGoal`, `AgentTask`, `AgentResult`, `RuntimeEvent`, and runtime snapshot schemas.
- `runtime/message_bus.py`
  Maintains the in-memory task queue and persists queue and event logs.
- `runtime/agent_runtime.py`
  Accepts a user goal through `run_goal()`, delegates workflow control to `CoordinatorAgent`, applies results to shared state, persists runtime snapshots, and closes the loop.
- `tools/stage_executor.py`
  Wraps the legacy pipeline as a safe stage executor. Stages 01-03 reuse the no-spoke baseline namespace and apply only the cumulative geometry needed for that stage; Stage 04 runs the full spoke build path.
- `agents/perception_agent.py`
  Supports `handle_task()` for feature extraction tasks.
- `agents/modeling_agent.py`
  Supports `handle_task()` for model-building tasks.
- `agents/evaluation_agent.py`
  Supports `handle_task()` for evaluation tasks.
- `agents/optimization_agent.py`
  Generates iteration decisions and follow-up tasks.
- `llm/policy_engine.py`
  Provides an optional LLM planning layer for coordinator and optimization decisions while enforcing hard rulebooks and adjustment whitelists.
- `llm/rulebook.py`
  Defines hard constraints, allowed next-agent transitions, and whitelisted adjustment keys for LLM-guided planning.

## Shared State And Observability

Runtime state is persisted to:

- `output/runtime/user_goal.json`
- `output/runtime/state_snapshot.json`
- `output/runtime/events.jsonl`
- `output/runtime/queue_snapshot.json`
- `output/runtime/results.json`
- `output/runtime/llm_decisions.jsonl` (when LLM planning is enabled)

These files are the current source of truth for framework status during execution.

Prompt-driven staged interaction assets are now maintained in:

- `prompts/README.md`
- `prompts/TEMPLATE.md`
- `prompts/01_revolve_body_prompt.md`
- `prompts/02_pcd_holes_prompt.md`
- `prompts/03_hub_grooves_prompt.md`
- `prompts/04_spokes_prompt.md`
- `prompts/NEW_THREAD_PROMPT.md`

These files are the source of truth for future thread-by-thread staged model generation.

Stage outputs are intended to accumulate as:

- Stage 01: revolve body only
- Stage 02: revolve body + PCD holes
- Stage 03: revolve body + PCD holes + hub grooves
- Stage 04: full spoke generation

## Current Loop

The runtime loop currently executes:

1. User goal enters `CoordinatorAgent`.
2. `CoordinatorAgent` dispatches `PerceptionAgent`.
3. Worker result returns to `CoordinatorAgent`.
4. `CoordinatorAgent` dispatches `ModelingAgent`, then `EvaluationAgent`, then `OptimizationAgent` as needed.
5. `CoordinatorAgent` is the only component allowed to end the run.

This is now task-driven, coordinator-mediated, and no worker agent is exposed as the user-facing control surface.
In console mode, the user talks to `UserConsole`; `UserConsole` talks to `CoordinatorAgent`; workers stay internal.

## Verification Snapshot

Validated on 2026-04-05 with the local virtual environment:

- `.\.venv\Scripts\python.exe .\main.py .\input\wheel.stl --mode runtime --no-optimize -o .\output -f step`
  Runtime completed and produced runtime state plus feature/model/evaluation artifacts.
- `.\.venv\Scripts\python.exe .\main.py .\input\wheel.stl --mode runtime --max-iterations 1 -o .\output -f step`
  Runtime executed an additional optimization-driven iteration and produced `iter1` artifacts.
- `.\.venv\Scripts\python.exe .\main.py .\input\wheel.stl --mode console --request "将 input/wheel.stl 转为 STEP，最多 1 轮优化" -o .\output -f step`
  Console parsed the user request into `UserGoal` and delegated execution through `CoordinatorAgent`.

Observed status:

- Task queue drains correctly.
- Event log captures agent transitions.
- Optimization loop is functional.
- Geometry quality is still poor; the runtime framework works, but the modeling/perception policy still needs improvement.
- Stage executor path is implemented and compiled.
- Stage 01 smoke test reached perception output and entered modeling, but did not finish within a 5+ minute local validation window; performance and dead-path filtering still need improvement.

## Gaps Still Open

- Agent registry is still implicit inside `AgentRuntime`; it should become pluggable.
- Optimization policy now supports optional LLM-guided iteration planning, but it still falls back to deterministic rules and only emits whitelisted adjustments.
- Shared state is persisted as JSON snapshots, not yet versioned memory objects.
- Tool layer is still embedded in agent classes; it should be extracted into `tools/`.
- `CoordinatorAgent` now supports an optional LLM planning layer, but the final transition logic is still guarded by hard rules and whitelisted configuration keys.
- `UserConsole` uses lightweight rule parsing; it is not yet a robust NL intent parser.

## Next Build Targets

1. Extract deterministic execution into `tools/`.
2. Add a richer user-goal parser so natural-language requests map cleanly into `UserGoal`.
3. Formalize repair policies and iteration stopping rules.
4. Add richer artifact versioning per iteration.
5. Add optional LLM-backed planning only above the deterministic tool layer.

