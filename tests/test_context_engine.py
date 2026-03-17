
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from agent_platform.artifact_store import ArtifactStore
from agent_platform.context_engine import ContextEngineV2
from agent_platform.memory_system import MemorySystem


@pytest.fixture
def temp_workspace():
    """创建临时工作空间"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def artifact_store(temp_workspace):
    """创建 ArtifactStore 实例"""
    return ArtifactStore(temp_workspace)


@pytest.fixture
def memory_system(artifact_store):
    """创建 MemorySystem 实例"""
    return MemorySystem(artifact_store)


@pytest.fixture
def context_engine(artifact_store, memory_system):
    """创建 ContextEngineV2 实例"""
    return ContextEngineV2(artifact_store, memory_system, max_files=3)


class TestContextEngineV2:
    """测试 ContextEngineV2"""

    def test_build_context(self, context_engine, temp_workspace):
        """测试构建上下文"""
        # 创建测试文件
        test_file = temp_workspace / "test.py"
        test_file.write_text("""
def test_function():
    return "test"

class TestClass:
    def method(self):
        pass
""")

        task = {
            "id": "task_001",
            "title": "Test task",
            "description": "Test context engine"
        }

        context = context_engine.build(task, temp_workspace)

        assert context["task"]["title"] == "Test task"
        assert "relevant_files" in context
        assert len(context["relevant_files"]) >= 0
        assert "lessons" in context
        assert "estimated_tokens" in context

    def test_estimate_tokens(self, context_engine):
        """测试估算 token"""
        file_summaries = [{"summary": "Test summary 1"}, {"summary": "Test summary 2"}]
        lessons = [{"problem": "test"}]

        tokens = context_engine._estimate_tokens(file_summaries, lessons)
        assert tokens > 0

    def test_load_files_summarized(self, context_engine, temp_workspace):
        """测试加载文件摘要"""
        test_file1 = temp_workspace / "file1.py"
        test_file1.write_text("def func1(): pass\nclass Class1: pass")

        test_file2 = temp_workspace / "file2.py"
        test_file2.write_text("def func2(): pass\nclass Class2: pass")

        summaries = context_engine._load_files_summarized(
            ["file1.py", "file2.py"],
            temp_workspace
        )

        assert len(summaries) == 2
        assert summaries[0]["file"] == "file1.py"
        assert summaries[1]["file"] == "file2.py"

    def test_search_relevant_files(self, context_engine, temp_workspace):
        """测试搜索相关文件"""
        for i in range(5):
            test_file = temp_workspace / f"test{i}.py"
            test_file.write_text(f"def func{i}(): pass")

        files = context_engine._search_relevant_files(
            {"title": "test", "description": "test"},
            temp_workspace
        )

        assert len(files) <= context_engine.max_files

