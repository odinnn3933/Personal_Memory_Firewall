from __future__ import annotations

from typing import Any, Callable

from memory_gateway.client import MemoryGatewayClient, format_memories_for_prompt


def memory_context_node(
    client: MemoryGatewayClient,
    *,
    project_id: str = "memory-gateway",
    query_key: str = "input",
    output_key: str = "memory_context",
    memory_types: list[str] | None = None,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Create a LangGraph-compatible node that injects approved memory context."""

    allowed_types = memory_types or ["context", "preference", "procedure", "lesson"]

    def node(state: dict[str, Any]) -> dict[str, Any]:
        query = str(state.get(query_key, ""))
        result = client.search(query, project_id=project_id, memory_types=allowed_types)
        return {
            **state,
            output_key: format_memories_for_prompt(result["memories"]),
            "memory_audit_id": result["audit_id"],
        }

    return node


def feedback_node(
    client: MemoryGatewayClient,
    *,
    project_id: str = "memory-gateway",
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Create a LangGraph-compatible node that submits end-of-task feedback."""

    def node(state: dict[str, Any]) -> dict[str, Any]:
        feedback = client.submit_feedback(
            task_id=str(state["task_id"]),
            rating=int(state.get("rating", 3)),
            correction=str(state.get("correction", "")),
            expected_behavior=str(state.get("expected_behavior", "")),
            error_type=str(state.get("error_type", "unknown")),
            project_id=project_id,
        )
        return {**state, "feedback_id": feedback["id"]}

    return node

