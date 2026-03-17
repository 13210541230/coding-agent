from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from agent_platform.artifact_store import ArtifactStore
from agent_platform.memory_system import MemorySystem


class ContextEngine:
    def __init__(self, store: ArtifactStore, memory: MemorySystem, max_files: int = 6, max_lessons: int = 3, max_tokens: int = 8000):
        self.store = store
        self.memory = memory
        self.max_files = max_files
        self.max_lessons = max_lessons
        self.max_tokens = max_tokens

    def build(self, task: dict, repo_root: Path) -> dict:
        candidates = list(repo_root.glob("**/*.py"))[: self.max_files]
        files = [str(p.relative_to(repo_root)) for p in candidates]
        lessons = self.memory.retrieve_relevant_lessons(task, max_lessons=self.max_lessons)
        return {
            "task": task,
            "repo_files": files,
            "lessons": lessons,
            "artifacts": {
                "analysis": self.store.read_text("artifacts/analysis.md"),
                "plan": self.store.read_json("artifacts/plan.json", default={}),
            },
            "limits": {
                "max_files": self.max_files,
                "max_lessons": self.max_lessons,
                "max_tokens": self.max_tokens,
            },
        }


class ContextEngineV2:
    """上下文构建引擎 V3 - 集成 fast-context 和 context-mode"""

    def __init__(
        self,
        store: ArtifactStore,
        memory: MemorySystem,
        max_files: int = 8,
        max_tokens: int = 6000
    ):
        self.store = store
        self.memory = memory
        self.max_files = max_files
        self.max_tokens = max_tokens
        self._extractor_prompt = """
提取关键信息（不超过 200 字）：
1. 这个文件的核心功能
2. 主要的类/函数（3个以内）
3. 与任务相关的关键信息
"""

    def build(self, task: dict[str, Any], repo_root: Path) -> dict[str, Any]:
        """构建上下文，总 token 控制在 max_tokens 以内"""
        # 1. 语义搜索相关文件
        relevant_files = self._search_relevant_files(task, repo_root)

        # 2. 读取文件摘要
        file_summaries = self._load_files_summarized(relevant_files, repo_root)

        # 3. 读取相关 lessons
        lessons = self.memory.retrieve_relevant_lessons(task)

        # 4. 估算 token
        estimated_tokens = self._estimate_tokens(file_summaries, lessons)

        return {
            "task": {
                "id": task.get("id"),
                "title": task.get("title"),
                "description": task.get("description"),
                "complexity": task.get("complexity", "small")
            },
            "relevant_files": file_summaries,
            "lessons": lessons,
            "estimated_tokens": min(estimated_tokens, self.max_tokens)
        }

    def _search_relevant_files(self, task: dict[str, Any], repo_root: Path) -> list[str]:
        """搜索相关文件（后续集成 fast-context）"""
        # 暂时用简单的 glob，后续替换为 fast-context 调用
        # TODO: 集成 fast-context MCP
        query = f"{task.get('title', '')} {task.get('description', '')}"
        # results = fast_context_search(query=query, project_path=str(repo_root), max_results=self.max_files)
        # return [r["file"] for r in results]

        # 临时实现
        candidates = list(repo_root.glob("**/*.py"))[:self.max_files]
        return [str(p.relative_to(repo_root)) for p in candidates]

    def _load_files_summarized(self, files: list[str], repo_root: Path) -> list[dict[str, str]]:
        """加载文件摘要（后续集成 context-mode）"""
        summaries = []
        for f in files[:self.max_files]:
            full_path = repo_root / f
            if not full_path.exists():
                continue

            # 后续用 context-mode 处理
            # summary = ctx_execute_file(
            #     path=str(full_path),
            #     language="auto",
            #     code=self._extractor_prompt
            # )

            # 临时实现：读取前 20 行
            try:
                with open(full_path, encoding="utf-8") as fp:
                    lines = [line.strip() for line in fp.readlines()[:20] if line.strip()]
                summary = "\n".join(lines[:5])  # 最多取 5 行
            except Exception:
                summary = ""

            summaries.append({
                "file": f,
                "summary": summary
            })
        return summaries

    def _estimate_tokens(self, file_summaries: list[dict], lessons: list[dict]) -> int:
        """估算 token 数量"""
        total = 0
        for s in file_summaries:
            total += len(s["summary"]) // 4  # 粗略估算：1 token ≈ 4 字符
        for l in lessons:
            total += len(str(l)) // 4
        return min(total, self.max_tokens)
