from __future__ import annotations

from memory_gateway.runtime.context import compose_approved_context_request, request_context
from memory_gateway.runtime.ingestion import (
    approve_inbox_item,
    approve_inbox_separate,
    approve_inbox_update,
    ingest_memory,
    preview_extraction,
)
from memory_gateway.runtime.memories import (
    list_memories_for_editor,
    memory_detail,
    patch_memory,
    restore_memory,
    supersede_memory,
)
from memory_gateway.service import delete_memory
from memory_gateway.schemas import (
    ContextRequestRequest,
    ExtractionPreviewRequest,
    InboxApproveRequest,
    IngestRequest,
    MemoryPatchRequest,
    MemoryRestoreRequest,
    MemorySupersedeRequest,
)
from memory_gateway.security import authenticate_api_key
from memory_gateway.types import InboxProposalKind, MemoryZone


def test_memory_editor_edit_supersede_restore_timeline(session):
    admin = authenticate_api_key("admin-demo-key")
    assert admin

    created = ingest_memory(
        session,
        admin,
        IngestRequest(
            content="Project requirement: use Postgres for durable memory storage.",
            project_id="memory-gateway",
        ),
    )
    assert created.inbox_item
    approved = approve_inbox_item(session, admin, created.inbox_item.id, InboxApproveRequest())
    assert approved.approved_memory_id

    listed = list_memories_for_editor(
        session,
        admin,
        project_id="memory-gateway",
        status="approved",
        query="Postgres",
    )
    assert any(memory.id == approved.approved_memory_id for memory in listed.memories)

    edited = patch_memory(
        session,
        admin,
        approved.approved_memory_id,
        MemoryPatchRequest(
            content="Project requirement: use Postgres and pgvector for durable memory storage.",
            reason="Add vector requirement.",
        ),
    )
    assert "pgvector" in edited.memory.content
    assert any(event.event == "edited" for event in edited.timeline)

    replacement = supersede_memory(
        session,
        admin,
        approved.approved_memory_id,
        MemorySupersedeRequest(
            content="Project requirement: use Postgres, pgvector, and audit logs for durable memory storage.",
            reason="New approved platform standard.",
        ),
    )
    assert replacement.memory.id != approved.approved_memory_id
    old_detail = memory_detail(session, admin, approved.approved_memory_id)
    assert old_detail.memory.status == "superseded"
    assert old_detail.memory.superseded_by_id == replacement.memory.id

    restored = restore_memory(
        session,
        admin,
        approved.approved_memory_id,
        MemoryRestoreRequest(reason="Rollback for test."),
    )
    assert restored.memory.status == "approved"
    assert any(event.event == "restored" for event in restored.timeline)

    delete_memory(session, admin, restored.memory.id)
    deleted = list_memories_for_editor(
        session,
        admin,
        project_id="memory-gateway",
        status="deleted",
        query="Postgres",
    )
    assert any(memory.id == restored.memory.id and memory.status == "deleted" for memory in deleted.memories)

    restored_again = restore_memory(
        session,
        admin,
        restored.memory.id,
        MemoryRestoreRequest(reason="Undo delete for test."),
    )
    assert restored_again.memory.status == "approved"


def test_context_request_polling_returns_context_after_approval(session):
    admin = authenticate_api_key("admin-demo-key")
    backend = authenticate_api_key("backend-demo-key")
    assert admin and backend

    pending = request_context(
        session,
        backend,
        ContextRequestRequest(
            task="Which database should the memory-gateway project use?",
            task_id="polling-test",
            project_id="memory-gateway",
            zones=[MemoryZone.WORK_CONTEXT],
        ),
    )
    assert pending.status == "pending_grant"
    assert pending.grant

    still_pending = compose_approved_context_request(session, backend, pending.grant.id)
    assert still_pending.status == "pending_grant"

    from memory_gateway.service import approve_access_grant

    approve_access_grant(session, admin, pending.grant.id)
    ready = compose_approved_context_request(session, backend, pending.grant.id)
    assert ready.status == "ready"
    assert ready.context
    assert "postgres" in ready.context.prompt_context.lower()


def test_extraction_preview_and_explicit_update_or_separate(session):
    admin = authenticate_api_key("admin-demo-key")
    assert admin

    first = ingest_memory(
        session,
        admin,
        IngestRequest(content="I live 15 km from the office.", auto_approve_public_low=False),
    )
    assert first.inbox_item
    approved = approve_inbox_item(
        session,
        admin,
        first.inbox_item.id,
        InboxApproveRequest(memory_zone=MemoryZone.PERSONAL_CONTEXT),
    )
    assert approved.approved_memory_id

    preview = preview_extraction(
        session,
        admin,
        ExtractionPreviewRequest(
            content="I moved recently. I now live 3 km from the office.",
            memory_zone=MemoryZone.PERSONAL_CONTEXT,
        ),
    )
    assert preview.relationship.proposal_kind == InboxProposalKind.UPDATE
    assert approved.approved_memory_id in preview.relationship.conflict_memory_ids

    update = ingest_memory(
        session,
        admin,
        IngestRequest(
            content="I moved recently. I now live 3 km from the office.",
            auto_approve_public_low=False,
        ),
    )
    assert update.inbox_item
    assert update.inbox_item.human_reason
    assert "Old:" in update.inbox_item.diff_summary
    assert "New:" in update.inbox_item.diff_summary
    approved_update = approve_inbox_update(
        session,
        admin,
        update.inbox_item.id,
        InboxApproveRequest(memory_zone=MemoryZone.PERSONAL_CONTEXT),
    )
    assert approved_update.approved_memory_id
    old_detail = memory_detail(session, admin, approved.approved_memory_id)
    assert old_detail.memory.status == "superseded"

    separate = ingest_memory(
        session,
        admin,
        IngestRequest(content="I now live 3 km from the office.", auto_approve_public_low=False),
    )
    assert separate.inbox_item
    approved_separate = approve_inbox_separate(
        session,
        admin,
        separate.inbox_item.id,
        InboxApproveRequest(memory_zone=MemoryZone.PERSONAL_CONTEXT),
    )
    assert approved_separate.status.value == "approved"
