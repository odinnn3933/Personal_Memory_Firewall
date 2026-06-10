from __future__ import annotations

from typing import Any

from memory_gateway.client import MemoryGatewayClient, format_memories_for_prompt


try:
    from crewai.tools import BaseTool
except Exception:  # pragma: no cover - optional dependency guard
    BaseTool = object  # type: ignore[assignment]


class MemorySearchTool(BaseTool):
    name: str = "permissioned_memory_search"
    description: str = "Search approved memories visible to the current agent."

    def __init__(self, client: MemoryGatewayClient | None = None, project_id: str = "memory-gateway"):
        super().__init__()
        self.client = client or MemoryGatewayClient()
        self.project_id = project_id

    def _run(self, query: str) -> str:
        result = self.client.search(
            query=query,
            project_id=self.project_id,
            memory_types=["context", "preference", "procedure", "lesson"],
        )
        return format_memories_for_prompt(result["memories"])


class MemoryFeedbackTool(BaseTool):
    name: str = "permissioned_memory_feedback"
    description: str = "Submit feedback that can later be converted into approved lessons."

    def __init__(self, client: MemoryGatewayClient | None = None, project_id: str = "memory-gateway"):
        super().__init__()
        self.client = client or MemoryGatewayClient()
        self.project_id = project_id

    def _run(
        self,
        task_id: str,
        rating: int,
        correction: str,
        error_type: str = "wrong_decision",
        expected_behavior: str = "",
    ) -> str:
        feedback = self.client.submit_feedback(
            task_id=task_id,
            rating=rating,
            correction=correction,
            error_type=error_type,
            expected_behavior=expected_behavior,
            project_id=self.project_id,
        )
        return f"Feedback submitted: {feedback['id']}"


class LessonExtractionTool(BaseTool):
    name: str = "permissioned_lesson_extraction"
    description: str = "Extract a pending learned memory proposal from feedback."

    def __init__(self, client: MemoryGatewayClient | None = None):
        super().__init__()
        self.client = client or MemoryGatewayClient()

    def _run(self, feedback_id: str) -> dict[str, Any]:
        return {"proposals": self.client.extract_lessons(feedback_id)}

