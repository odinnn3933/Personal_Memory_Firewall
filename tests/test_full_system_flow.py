from __future__ import annotations

from memory_gateway.runtime.context import compose_approved_context_request, compose_context, request_context
from memory_gateway.runtime.ingestion import (
    approve_inbox_item,
    approve_inbox_separate,
    approve_inbox_update,
    ingest_memory,
    reject_inbox_item,
)
from memory_gateway.runtime.memories import (
    list_memories_for_editor,
    memory_detail,
    restore_memory,
    supersede_memory,
)
from memory_gateway.runtime.semantic import list_decision_examples
from memory_gateway.schemas import (
    ContextComposeRequest,
    ContextRequestRequest,
    InboxApproveRequest,
    InboxRejectRequest,
    IngestRequest,
    MemoryRestoreRequest,
    MemorySupersedeRequest,
)
from memory_gateway.security import authenticate_api_key
from memory_gateway.service import approve_access_grant, delete_memory
from memory_gateway.types import MemoryZone


def test_full_system_flow_from_ingest_to_permissioned_context(session):
    admin = authenticate_api_key("admin-demo-key")
    backend = authenticate_api_key("backend-demo-key")
    assert admin and backend

    public = ingest_memory(
        session,
        admin,
        IngestRequest(content="I prefer concise bullet-point answers."),
    )
    assert public.auto_approved is True
    assert public.memory
    assert public.memory.memory_zone == MemoryZone.PUBLIC_PROFILE

    work = ingest_memory(
        session,
        admin,
        IngestRequest(
            content=(
                "Project requirement: the memory-gateway project must use Postgres "
                "and pgvector for long-term memory retrieval."
            ),
            project_id="memory-gateway",
            auto_approve_public_low=False,
        ),
    )
    assert work.inbox_item
    approved_work = approve_inbox_item(
        session,
        admin,
        work.inbox_item.id,
        InboxApproveRequest(memory_zone=MemoryZone.WORK_CONTEXT, project_id="memory-gateway"),
    )
    assert approved_work.approved_memory_id

    no_grant = compose_context(
        session,
        backend,
        ContextComposeRequest(
            task="What storage should memory-gateway use?",
            project_id="memory-gateway",
            zones=[MemoryZone.WORK_CONTEXT],
            include_graph=False,
        ),
    )
    assert no_grant.source_cards == []
    assert no_grant.denied_zones
    assert "Postgres" not in no_grant.prompt_context

    pending = request_context(
        session,
        backend,
        ContextRequestRequest(
            task="What storage should memory-gateway use?",
            task_id="full-flow-work-context",
            purpose="Need project memory to answer architecture question.",
            project_id="memory-gateway",
            zones=[MemoryZone.WORK_CONTEXT],
            include_graph=False,
        ),
    )
    assert pending.status == "pending_grant"
    assert pending.grant
    assert compose_approved_context_request(session, backend, pending.grant.id).status == "pending_grant"

    approve_access_grant(session, admin, pending.grant.id)
    ready = compose_approved_context_request(session, backend, pending.grant.id)
    assert ready.status == "ready"
    assert ready.context
    assert "Postgres" in ready.context.prompt_context
    assert ready.context.matched_summaries

    other_project = compose_context(
        session,
        backend,
        ContextComposeRequest(
            task="What storage should travel-planner use?",
            project_id="travel-planner",
            zones=[MemoryZone.WORK_CONTEXT],
            include_graph=False,
        ),
    )
    assert "memory-gateway project must use Postgres" not in other_project.prompt_context

    old_personal = ingest_memory(
        session,
        admin,
        IngestRequest(content="I live 15 km from the office.", auto_approve_public_low=False),
    )
    assert old_personal.inbox_item
    approved_old = approve_inbox_separate(
        session,
        admin,
        old_personal.inbox_item.id,
        InboxApproveRequest(memory_zone=MemoryZone.PERSONAL_CONTEXT),
    )
    assert approved_old.approved_memory_id

    updated_personal = ingest_memory(
        session,
        admin,
        IngestRequest(content="I moved recently. I now live 3 km from the office.", auto_approve_public_low=False),
    )
    assert updated_personal.inbox_item
    assert updated_personal.inbox_item.needs_user_decision is True
    assert updated_personal.inbox_item.supersedes_memory_id == approved_old.approved_memory_id

    approved_update = approve_inbox_update(
        session,
        admin,
        updated_personal.inbox_item.id,
        InboxApproveRequest(
            memory_zone=MemoryZone.PERSONAL_CONTEXT,
            supersede_memory_id=approved_old.approved_memory_id,
        ),
    )
    assert approved_update.approved_memory_id
    assert memory_detail(session, admin, approved_old.approved_memory_id).memory.status == "superseded"

    personal_pending = request_context(
        session,
        backend,
        ContextRequestRequest(
            task="How far does the user currently live from the office?",
            task_id="full-flow-personal-context",
            purpose="Need personal context for commute answer.",
            zones=[MemoryZone.PERSONAL_CONTEXT],
            include_graph=False,
        ),
    )
    assert personal_pending.grant
    approve_access_grant(session, admin, personal_pending.grant.id)
    personal_ready = compose_approved_context_request(session, backend, personal_pending.grant.id)
    assert personal_ready.context
    assert "3 km" in personal_ready.context.prompt_context
    assert "15 km" not in personal_ready.context.prompt_context

    rejected = ingest_memory(
        session,
        admin,
        IngestRequest(content="Temporary scratch note that should not be remembered.", auto_approve_public_low=False),
    )
    assert rejected.inbox_item
    reject_inbox_item(
        session,
        admin,
        rejected.inbox_item.id,
        InboxRejectRequest(reason="Scratch note."),
    )
    decisions = list_decision_examples(session, admin)
    assert any(example.user_decision == "reject" for example in decisions)
    assert any(example.user_decision == "approve_update" for example in decisions)

    replacement = supersede_memory(
        session,
        admin,
        approved_work.approved_memory_id,
        MemorySupersedeRequest(
            content="Project requirement: use Postgres, pgvector, and audit logs for memory retrieval.",
            reason="Full-flow lifecycle check.",
        ),
    )
    assert replacement.memory.status == "approved"
    old_work_detail = memory_detail(session, admin, approved_work.approved_memory_id)
    assert old_work_detail.memory.status == "superseded"

    delete_memory(session, admin, replacement.memory.id)
    deleted = list_memories_for_editor(
        session,
        admin,
        project_id="memory-gateway",
        status="deleted",
        query="audit logs",
    )
    assert any(memory.id == replacement.memory.id for memory in deleted.memories)

    restored = restore_memory(
        session,
        admin,
        replacement.memory.id,
        MemoryRestoreRequest(reason="Full-flow restore check."),
    )
    assert restored.memory.status == "approved"
