# Agent Platform

A workflow-driven code-agent orchestration platform where **the system controls flow** and LLM/executors perform reasoning and patch generation.

## Highlights

- Multi-stage workflows (`analysis`, `planning`, `execution_loop`, `review`)
- Artifact-driven stage handoffs
- Stateful resume from `state/workflow_state.json`
- Executor routing (`codex`, `claude_code`)
- Context building with bounded inputs
- Memory retrieval for repeated-error prevention
- Retry + reflection + human intervention escalation
- Configurable executor/model routing for cost control

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e . --no-build-isolation
agent-platform init-workspace workspace
agent-platform run --workspace workspace --workflow full_dev
```

## Testing

```bash
# Run directly from source
pytest -q
```

Optional editable install (offline-friendly, no extra runtime deps):

```bash
pip install -e . --no-build-isolation
```

## Executor & Model Cost Configuration

You can control executor selection (`codex` vs `claude_code`) and model cost strategy in two ways:

1. Workspace config file: `artifacts/executor_config.json`
2. CLI overrides for one run

Example config file:

```json
{
  "default_executor": "codex",
  "executor_routing_mode": "complexity",
  "budget_mode": "low_cost",
  "stage_models": {
    "analysis": "gpt-5.4",
    "planning": "gpt-5.4"
  }
}
```

CLI override example:

```bash
agent-platform run \
  --workspace workspace \
  --workflow full_dev \
  --default-executor claude_code \
  --executor-routing-mode fixed \
  --budget-mode low_cost
```

Task-level override is also supported in `tasks/task_queue.json`:
- `executor`: force `codex` or `claude_code`
- `model`: force a concrete model name for that task
