from __future__ import annotations


class HumanIntervention:
    def should_trigger(self, same_error_count: int, same_file_edit_count: int, identical_stacktrace: bool) -> bool:
        return same_error_count > 2 or same_file_edit_count > 3 or identical_stacktrace

    def build_message(self, error: str, attempts: list[str]) -> str:
        joined = "\n".join(f"{i + 1}. {a}" for i, a in enumerate(attempts))
        return f"Agent stuck.\nError: {error}\nAttempts:\n{joined}"
