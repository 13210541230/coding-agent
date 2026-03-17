# agent_platform/model_router/default_catalog.py
from agent_platform.model_router.catalog import ModelEntry

DEFAULT_CATALOG: list[ModelEntry] = [
    # Claude Code — source: docs.anthropic.com/en/docs/about-claude/models 2026-03-17
    ModelEntry("claude-opus-4-6",    "claude_code", tier=1, context_window=1000000, tags=("reasoning", "code")),
    ModelEntry("claude-sonnet-4-6",  "claude_code", tier=2, context_window=1000000, tags=("code", "balanced")),
    ModelEntry("claude-haiku-4-5",   "claude_code", tier=3, context_window=200000,  tags=("fast", "router")),

    # Codex CLI — source: platform.openai.com/docs/models + user-verified CLI screen 2026-03-17
    ModelEntry("gpt-5.4",            "codex", tier=1, context_window=1050000, tags=("reasoning", "code", "default")),
    ModelEntry("gpt-5.3-codex",      "codex", tier=1, context_window=400000,  tags=("reasoning", "code")),
    ModelEntry("gpt-5.2-codex",      "codex", tier=2, context_window=400000,  tags=("code", "balanced")),
    ModelEntry("gpt-5.2",            "codex", tier=2, context_window=256000,  tags=("code", "balanced")),
    ModelEntry("gpt-5.1-codex-max",  "codex", tier=2, context_window=400000,  tags=("reasoning", "balanced")),
    ModelEntry("gpt-5.1-codex-mini", "codex", tier=3, context_window=400000,  tags=("fast", "router")),

    # mycodex — local fork of Codex CLI, identical model support
    ModelEntry("gpt-5.4",            "mycodex", tier=1, context_window=1050000, tags=("reasoning", "code", "default")),
    ModelEntry("gpt-5.3-codex",      "mycodex", tier=1, context_window=400000,  tags=("reasoning", "code")),
    ModelEntry("gpt-5.2-codex",      "mycodex", tier=2, context_window=400000,  tags=("code", "balanced")),
    ModelEntry("gpt-5.2",            "mycodex", tier=2, context_window=256000,  tags=("code", "balanced")),
    ModelEntry("gpt-5.1-codex-max",  "mycodex", tier=2, context_window=400000,  tags=("reasoning", "balanced")),
    ModelEntry("gpt-5.1-codex-mini", "mycodex", tier=3, context_window=400000,  tags=("fast", "router")),
]
