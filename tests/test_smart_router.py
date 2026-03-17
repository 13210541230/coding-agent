from __future__ import annotations
from agent_platform.model_router.smart_router import SmartRouter, AssessResult

def router():
    return SmartRouter()

def test_explicit_complexity_field_takes_priority():
    result = router().assess({"complexity": "large", "title": "fix typo"})
    assert result.complexity == "large"
    assert result.method == "explicit"

def test_large_keyword_in_title():
    result = router().assess({"title": "重构整个认证模块", "description": ""})
    assert result.complexity == "large"
    assert result.method == "rule"

def test_small_keyword_in_title():
    result = router().assess({"title": "fix typo in README", "description": ""})
    assert result.complexity == "small"
    assert result.method == "rule"

def test_large_keyword_in_description():
    result = router().assess({"title": "update code", "description": "refactor the entire auth system"})
    assert result.complexity == "large"

def test_long_description_triggers_large():
    result = router().assess({"title": "task", "description": "x" * 501})
    assert result.complexity == "large"

def test_short_description_triggers_small():
    # Use a description with no signal keywords so only length heuristic applies.
    result = router().assess({"title": "task", "description": "do a thing"})
    assert result.complexity == "small"
    assert result.method == "rule"

def test_empty_description_triggers_small():
    result = router().assess({"title": "task", "description": ""})
    assert result.complexity == "small"

def test_missing_description_triggers_small():
    result = router().assess({"title": "task"})
    assert result.complexity == "small"

def test_medium_description_no_keywords_defaults_medium():
    desc = "implement a new endpoint that returns user data" * 3  # ~150 chars, no signals
    result = router().assess({"title": "task", "description": desc})
    assert result.complexity == "medium"
    assert result.method == "default"

def test_assess_result_has_confidence():
    result = router().assess({"complexity": "small"})
    assert 0.0 <= result.confidence <= 1.0

def test_invalid_complexity_field_falls_through_to_rules():
    result = router().assess({"complexity": "huge", "title": "refactor auth"})
    assert result.complexity == "large"
    assert result.method == "rule"
