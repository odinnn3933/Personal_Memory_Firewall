from __future__ import annotations

from memory_gateway.runtime.context import compose_approved_context_request, compose_context, request_context
from memory_gateway.runtime.ingestion import approve_inbox_item, ingest_memory
from memory_gateway.runtime.memories import memory_detail
from memory_gateway.schemas import ContextComposeRequest, ContextRequestRequest, InboxApproveRequest, IngestRequest
from memory_gateway.security import authenticate_api_key
from memory_gateway.service import approve_access_grant
from memory_gateway.types import MemoryType, MemoryZone


def test_friend_relationship_requires_personal_grant(session):
    admin = authenticate_api_key("admin-demo-key")
    backend = authenticate_api_key("backend-demo-key")
    assert admin and backend

    captured = ingest_memory(
        session,
        admin,
        IngestRequest(
            content="Alice is my close friend. We usually play basketball together on weekends.",
            auto_approve_public_low=False,
        ),
    )
    assert captured.inbox_item
    assert captured.inbox_item.suggested_zone == MemoryZone.PERSONAL_CONTEXT
    assert captured.inbox_item.suggested_memory_type == MemoryType.RELATIONSHIP

    approved = approve_inbox_item(
        session,
        admin,
        captured.inbox_item.id,
        InboxApproveRequest(memory_zone=MemoryZone.PERSONAL_CONTEXT),
    )
    assert approved.approved_memory_id

    detail = memory_detail(session, admin, approved.approved_memory_id)
    assert detail.memory.memory_type == MemoryType.RELATIONSHIP
    assert any(fact.fact_type == "relationship" and fact.relation_type == "FRIEND_OF" for fact in detail.facts)

    denied = compose_context(
        session,
        backend,
        ContextComposeRequest(
            task="Who is Alice to the user?",
            zones=[MemoryZone.PERSONAL_CONTEXT],
            include_graph=False,
        ),
    )
    assert "Alice is my close friend" not in denied.prompt_context
    assert denied.denied_zones

    pending = request_context(
        session,
        backend,
        ContextRequestRequest(
            task="Who is Alice to the user?",
            task_id="relationship-personal-test",
            purpose="Need personal relationship context.",
            zones=[MemoryZone.PERSONAL_CONTEXT],
            include_graph=False,
        ),
    )
    assert pending.grant
    approve_access_grant(session, admin, pending.grant.id)
    ready = compose_approved_context_request(session, backend, pending.grant.id)
    assert ready.context
    assert "## Relationships" in ready.context.prompt_context
    assert "Alice" in ready.context.prompt_context


def test_work_relationship_is_project_scoped(session):
    admin = authenticate_api_key("admin-demo-key")
    backend = authenticate_api_key("backend-demo-key")
    assert admin and backend

    captured = ingest_memory(
        session,
        admin,
        IngestRequest(
            content="Bob is my colleague on the memory-gateway backend team.",
            project_id="memory-gateway",
            auto_approve_public_low=False,
        ),
    )
    assert captured.inbox_item
    assert captured.inbox_item.suggested_zone == MemoryZone.WORK_CONTEXT
    assert captured.inbox_item.suggested_memory_type == MemoryType.RELATIONSHIP

    approved = approve_inbox_item(
        session,
        admin,
        captured.inbox_item.id,
        InboxApproveRequest(memory_zone=MemoryZone.WORK_CONTEXT, project_id="memory-gateway"),
    )
    assert approved.approved_memory_id

    wrong_project = compose_context(
        session,
        backend,
        ContextComposeRequest(
            task="Who is Bob?",
            project_id="travel-planner",
            zones=[MemoryZone.WORK_CONTEXT],
            include_graph=False,
        ),
    )
    assert "Bob is my colleague" not in wrong_project.prompt_context

    pending = request_context(
        session,
        backend,
        ContextRequestRequest(
            task="Who is Bob?",
            task_id="relationship-work-test",
            purpose="Need project relationship context.",
            project_id="memory-gateway",
            zones=[MemoryZone.WORK_CONTEXT],
            include_graph=False,
        ),
    )
    assert pending.grant
    approve_access_grant(session, admin, pending.grant.id)
    ready = compose_approved_context_request(session, backend, pending.grant.id)
    assert ready.context
    assert "Bob" in ready.context.prompt_context
    assert "## Relationships" in ready.context.prompt_context
