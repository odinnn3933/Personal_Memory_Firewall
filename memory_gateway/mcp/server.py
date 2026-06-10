from __future__ import annotations

from typing import Any

from memory_gateway.client import MemoryGatewayClient


def _client(api_key: str, base_url: str = "http://localhost:8000") -> MemoryGatewayClient:
    return MemoryGatewayClient(base_url=base_url, api_key=api_key)


try:
    from mcp.server.fastmcp import FastMCP
except Exception:  # pragma: no cover - optional dependency guard
    FastMCP = None  # type: ignore[assignment]


if FastMCP:
    mcp = FastMCP("personal-memory-firewall")

    @mcp.tool()
    def memory_list_zones(
        api_key: str = "backend-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> list[dict[str, Any]]:
        """List memory zones and whether each zone requires a grant."""
        return _client(api_key, base_url).list_zones()

    @mcp.tool()
    def memory_list_projects(
        api_key: str = "backend-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> list[dict[str, Any]]:
        """List projects visible to the current agent."""
        return _client(api_key, base_url).list_projects()

    @mcp.tool()
    def memory_search(
        query: str,
        project_id: str | None = "memory-gateway",
        memory_types: list[str] | None = None,
        top_k: int = 5,
        api_key: str = "backend-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        return _client(api_key, base_url).search(query, project_id, memory_types, top_k)

    @mcp.tool()
    def memory_ingest(
        content: str,
        project_id: str | None = "memory-gateway",
        source: str = "api",
        content_kind: str = "text",
        auto_approve_public_low: bool = True,
        api_key: str = "backend-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        """Ingest selected or API-submitted content into the review inbox or public memory."""
        return _client(api_key, base_url).ingest(
            content=content,
            project_id=project_id,
            source=source,
            content_kind=content_kind,
            auto_approve_public_low=auto_approve_public_low,
        )

    @mcp.tool()
    def memory_list_inbox(
        status: str = "pending_review",
        api_key: str = "admin-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> list[dict[str, Any]]:
        """List memory inbox items waiting for user/admin review."""
        return _client(api_key, base_url).list_inbox(status)

    @mcp.tool()
    def memory_approve_inbox(
        inbox_id: str,
        memory_zone: str | None = None,
        memory_type: str | None = None,
        project_id: str | None = "memory-gateway",
        api_key: str = "admin-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        """Approve an inbox item into searchable memory."""
        return _client(api_key, base_url).approve_inbox_item(
            inbox_id=inbox_id,
            memory_zone=memory_zone,
            memory_type=memory_type,
            project_id=project_id,
        )

    @mcp.tool()
    def memory_compose_context(
        task: str,
        zones: list[str],
        grant_token: str | None = None,
        project_id: str | None = "memory-gateway",
        memory_types: list[str] | None = None,
        max_tokens: int = 1200,
        include_graph: bool = True,
        top_k: int = 8,
        api_key: str = "backend-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        """Return a prompt-ready, permission-filtered context package for the task."""
        return _client(api_key, base_url).compose_context(
            task=task,
            project_id=project_id,
            zones=zones,
            grant_token=grant_token,
            memory_types=memory_types,
            max_tokens=max_tokens,
            include_graph=include_graph,
            top_k=top_k,
        )

    @mcp.tool()
    def memory_request_context(
        task: str,
        zones: list[str],
        grant_token: str | None = None,
        project_id: str | None = "memory-gateway",
        task_id: str | None = None,
        purpose: str | None = None,
        memory_types: list[str] | None = None,
        max_tokens: int = 1200,
        include_graph: bool = True,
        top_k: int = 8,
        ttl_minutes: int | None = None,
        api_key: str = "backend-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        """Request prompt-ready context; returns context immediately or a pending grant request."""
        return _client(api_key, base_url).request_context(
            task=task,
            project_id=project_id,
            zones=zones,
            grant_token=grant_token,
            memory_types=memory_types,
            max_tokens=max_tokens,
            include_graph=include_graph,
            top_k=top_k,
            task_id=task_id,
            purpose=purpose,
            ttl_minutes=ttl_minutes,
        )

    @mcp.tool()
    def memory_get_context_request(
        grant_id: str,
        api_key: str = "backend-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        """Poll a context request. Returns prompt context once the desktop user approves it."""
        return _client(api_key, base_url).get_context_request(grant_id)

    @mcp.tool()
    def memory_compose_approved_context(
        grant_id: str,
        api_key: str = "backend-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        """Compose prompt-ready context from an already approved context request without exposing a grant token."""
        return _client(api_key, base_url).compose_approved_context(grant_id)

    @mcp.tool()
    def memory_preview_share_pack(
        project_id: str = "memory-gateway",
        name: str = "Project onboarding share",
        recipient_label: str = "",
        task: str = "Onboard me to this project.",
        allowed_memory_types: list[str] | None = None,
        max_tokens: int = 1600,
        top_k: int = 12,
        api_key: str = "admin-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        """Preview a scoped project onboarding context before creating a revocable share token."""
        return _client(api_key, base_url).preview_share_pack(
            project_id=project_id,
            name=name,
            recipient_label=recipient_label,
            task=task,
            allowed_memory_types=allowed_memory_types,
            max_tokens=max_tokens,
            top_k=top_k,
        )

    @mcp.tool()
    def memory_create_share_pack(
        project_id: str = "memory-gateway",
        name: str = "Project onboarding share",
        recipient_label: str = "",
        task: str = "Onboard me to this project.",
        allowed_memory_types: list[str] | None = None,
        ttl_days: int = 7,
        max_uses: int = 20,
        api_key: str = "admin-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        """Create a revocable, expiring Project Memory Share Pack token. The token is returned once."""
        return _client(api_key, base_url).create_share_pack(
            project_id=project_id,
            name=name,
            recipient_label=recipient_label,
            task=task,
            allowed_memory_types=allowed_memory_types,
            ttl_days=ttl_days,
            max_uses=max_uses,
        )

    @mcp.tool()
    def memory_compose_share_pack(
        share_pack_id: str,
        share_token: str,
        task: str = "Onboard me to this project.",
        max_tokens: int = 1600,
        top_k: int = 12,
        api_key: str = "guest-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        """Use a Share Pack token to retrieve prompt-ready project onboarding context."""
        return _client(api_key, base_url).compose_share_pack(
            share_pack_id=share_pack_id,
            share_token=share_token,
            task=task,
            max_tokens=max_tokens,
            top_k=top_k,
        )

    @mcp.tool()
    def memory_list_share_packs(
        status: str | None = None,
        api_key: str = "admin-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> list[dict[str, Any]]:
        """List Project Memory Share Packs for review and revocation."""
        return _client(api_key, base_url).list_share_packs(status)

    @mcp.tool()
    def memory_revoke_share_pack(
        share_pack_id: str,
        api_key: str = "admin-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        """Revoke a Project Memory Share Pack so its token can no longer compose context."""
        return _client(api_key, base_url).revoke_share_pack(share_pack_id)

    @mcp.tool()
    def memory_list_memories(
        project_id: str | None = None,
        zone: str | None = None,
        memory_type: str | None = None,
        status: str | None = "approved",
        query: str | None = None,
        limit: int = 100,
        api_key: str = "admin-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        """List memories for user/admin review in the memory editor."""
        return _client(api_key, base_url).list_memories(
            project_id=project_id,
            zone=zone,
            memory_type=memory_type,
            status=status,
            query=query,
            limit=limit,
        )

    @mcp.tool()
    def memory_get_memory(
        memory_id: str,
        api_key: str = "admin-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        """Get memory details, facts, timeline, and audit summary."""
        return _client(api_key, base_url).get_memory(memory_id)

    @mcp.tool()
    def memory_extraction_preview(
        content: str,
        project_id: str | None = None,
        content_kind: str = "text",
        memory_zone: str | None = None,
        memory_type: str | None = None,
        api_key: str = "admin-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        """Preview redaction, fact extraction, duplicate/conflict/update detection before approval."""
        return _client(api_key, base_url).extraction_preview(
            content=content,
            project_id=project_id,
            content_kind=content_kind,
            memory_zone=memory_zone,
            memory_type=memory_type,
        )

    @mcp.tool()
    def memory_semantic_summarize(
        content: str,
        project_id: str | None = None,
        memory_zone: str = "public_profile",
        model_profile_id: str | None = None,
        api_key: str = "admin-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        """Generate a redacted semantic summary, entities, triggers, and facts."""
        return _client(api_key, base_url).semantic_summarize(
            content=content,
            project_id=project_id,
            memory_zone=memory_zone,
            model_profile_id=model_profile_id,
        )

    @mcp.tool()
    def memory_semantic_judge(
        content: str,
        project_id: str | None = None,
        memory_zone: str = "public_profile",
        model_profile_id: str | None = None,
        top_k: int = 5,
        api_key: str = "admin-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        """Compare a new redacted memory summary against existing summaries and judge its relationship."""
        return _client(api_key, base_url).semantic_judge(
            content=content,
            project_id=project_id,
            memory_zone=memory_zone,
            model_profile_id=model_profile_id,
            top_k=top_k,
        )

    @mcp.tool()
    def memory_rebuild_summaries(
        model_profile_id: str | None = None,
        api_key: str = "admin-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        """Rebuild semantic summaries for approved memories."""
        return _client(api_key, base_url).rebuild_summaries(model_profile_id)

    @mcp.tool()
    def memory_list_decision_examples(
        project_id: str | None = None,
        zone: str | None = None,
        limit: int = 50,
        api_key: str = "admin-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> list[dict[str, Any]]:
        """List user decision examples used as few-shot memory judgment hints."""
        return _client(api_key, base_url).list_decision_examples(project_id, zone, limit)

    @mcp.tool()
    def memory_write_proposal(
        content: str,
        project_id: str | None = "memory-gateway",
        memory_type: str = "context",
        visibility: str = "project",
        api_key: str = "backend-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        return _client(api_key, base_url).propose_memory(
            content=content,
            project_id=project_id,
            memory_type=memory_type,
            visibility=visibility,
        )

    @mcp.tool()
    def memory_analyze_capture(
        content: str,
        content_kind: str = "text",
        project_id: str | None = "memory-gateway",
        api_key: str = "admin-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        return _client(api_key, base_url).analyze_capture(
            content=content,
            content_kind=content_kind,
            project_id=project_id,
        )

    @mcp.tool()
    def memory_commit_capture(
        content: str,
        memory_zone: str,
        memory_type: str = "context",
        project_id: str | None = "memory-gateway",
        api_key: str = "admin-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        return _client(api_key, base_url).commit_capture(
            content=content,
            memory_zone=memory_zone,
            memory_type=memory_type,
            project_id=project_id,
        )

    @mcp.tool()
    def memory_request_grant(
        task_id: str,
        purpose: str,
        allowed_zones: list[str],
        project_id: str | None = "memory-gateway",
        ttl_minutes: int | None = None,
        api_key: str = "backend-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        return _client(api_key, base_url).request_grant(
            task_id=task_id,
            purpose=purpose,
            allowed_zones=allowed_zones,
            project_id=project_id,
            ttl_minutes=ttl_minutes,
        )

    @mcp.tool()
    def memory_get_grant(
        grant_id: str,
        api_key: str = "backend-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        """Read the status of a grant request. Tokens are only returned on approval responses."""
        return _client(api_key, base_url).get_grant(grant_id)

    @mcp.tool()
    def memory_approve_grant(
        grant_id: str,
        ttl_minutes: int | None = None,
        api_key: str = "admin-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        return _client(api_key, base_url).approve_grant(grant_id, ttl_minutes)

    @mcp.tool()
    def memory_vault_search(
        query: str,
        zones: list[str],
        grant_token: str | None = None,
        project_id: str | None = "memory-gateway",
        memory_types: list[str] | None = None,
        top_k: int = 5,
        api_key: str = "backend-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        return _client(api_key, base_url).search_with_grant(
            query=query,
            project_id=project_id,
            zones=zones,
            grant_token=grant_token,
            memory_types=memory_types,
            top_k=top_k,
        )

    @mcp.tool()
    def memory_graph_health(
        api_key: str = "backend-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        """Check whether the Neo4j graph layer is available."""
        return _client(api_key, base_url).graph_health()

    @mcp.tool()
    def memory_graph_search(
        query: str,
        zones: list[str],
        grant_token: str | None = None,
        project_id: str | None = "memory-gateway",
        top_k: int = 5,
        api_key: str = "backend-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        """Search permission-filtered graph memory cards with the same grant rules as vault search."""
        return _client(api_key, base_url).graph_search(
            query=query,
            project_id=project_id,
            zones=zones,
            grant_token=grant_token,
            top_k=top_k,
        )

    @mcp.tool()
    def memory_list_model_profiles(
        api_key: str = "admin-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> list[dict[str, Any]]:
        """List BYOM model profiles configured for memory processing."""
        return _client(api_key, base_url).list_model_profiles()

    @mcp.tool()
    def memory_classify_with_model(
        content: str,
        project_id: str | None = "memory-gateway",
        model_profile_id: str | None = None,
        api_key: str = "admin-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        """Classify a capture through the configured BYOM profile with redaction and policy guards."""
        return _client(api_key, base_url).classify_with_model(
            content=content,
            project_id=project_id,
            model_profile_id=model_profile_id,
        )

    @mcp.tool()
    def memory_submit_feedback(
        task_id: str,
        rating: int,
        correction: str,
        error_type: str = "wrong_decision",
        expected_behavior: str = "",
        project_id: str | None = "memory-gateway",
        api_key: str = "backend-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        return _client(api_key, base_url).submit_feedback(
            task_id=task_id,
            rating=rating,
            correction=correction,
            error_type=error_type,
            expected_behavior=expected_behavior,
            project_id=project_id,
        )

    @mcp.tool()
    def memory_context_feedback(
        task_id: str,
        rating: int,
        correction: str,
        error_type: str = "wrong_context",
        expected_behavior: str = "",
        project_id: str | None = "memory-gateway",
        api_key: str = "backend-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        """Submit feedback after a composed context package was insufficient or wrong."""
        return _client(api_key, base_url).submit_feedback(
            task_id=task_id,
            rating=rating,
            correction=correction,
            error_type=error_type,
            expected_behavior=expected_behavior,
            project_id=project_id,
        )

    @mcp.tool()
    def memory_extract_lessons(
        feedback_id: str,
        api_key: str = "backend-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> list[dict[str, Any]]:
        return _client(api_key, base_url).extract_lessons(feedback_id)

    @mcp.tool()
    def memory_approve_lesson(
        proposal_id: str,
        api_key: str = "admin-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        return _client(api_key, base_url).approve_lesson(proposal_id)

    @mcp.tool()
    def memory_explain(
        memory_id: str,
        project_id: str | None = "memory-gateway",
        api_key: str = "backend-demo-key",
        base_url: str = "http://localhost:8000",
    ) -> dict[str, Any]:
        return _client(api_key, base_url).explain(memory_id, project_id)


def main() -> None:
    if not FastMCP:
        raise RuntimeError("Install optional dependency with: python -m pip install -e .[mcp]")
    mcp.run()


if __name__ == "__main__":
    main()
