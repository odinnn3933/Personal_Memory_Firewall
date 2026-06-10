from __future__ import annotations

import pytest

from memory_gateway.db import MemoryRecord, SharePackRecord
from memory_gateway.runtime.context import compose_context
from memory_gateway.runtime.ingestion import approve_inbox_item, ingest_memory
from memory_gateway.runtime.share import (
    compose_share_pack,
    create_share_pack,
    preview_share_pack,
    revoke_share_pack,
)
from memory_gateway.schemas import (
    ContextComposeRequest,
    InboxApproveRequest,
    IngestRequest,
    SharePackComposeRequest,
    SharePackCreateRequest,
    SharePackPreviewRequest,
)
from memory_gateway.security import authenticate_api_key
from memory_gateway.service import InvalidState, PermissionDenied
from memory_gateway.types import AuditAction, MemoryType, MemoryZone, ProposalStatus, SharePackStatus, Visibility


def _approve_work_memory(session, admin, content: str, project_id: str = "memory-gateway") -> str:
    result = ingest_memory(
        session,
        admin,
        IngestRequest(
            content=content,
            project_id=project_id,
            auto_approve_public_low=False,
        ),
    )
    assert result.inbox_item
    approved = approve_inbox_item(
        session,
        admin,
        result.inbox_item.id,
        InboxApproveRequest(memory_zone=MemoryZone.WORK_CONTEXT, project_id=project_id),
    )
    assert approved.approved_memory_id
    return approved.approved_memory_id


def test_share_pack_preview_excludes_forbidden_memory(session):
    admin = authenticate_api_key("admin-demo-key")
    assert admin
    _approve_work_memory(
        session,
        admin,
        "Project requirement: memory-gateway onboarding should mention FastAPI and Postgres.",
    )
    personal = ingest_memory(
        session,
        admin,
        IngestRequest(
            content="Alice is my close friend and should not appear in project onboarding.",
            auto_approve_public_low=False,
        ),
    )
    assert personal.inbox_item
    approve_inbox_item(
        session,
        admin,
        personal.inbox_item.id,
        InboxApproveRequest(memory_zone=MemoryZone.PERSONAL_CONTEXT),
    )

    preview = preview_share_pack(
        session,
        admin,
        SharePackPreviewRequest(
            project_id="memory-gateway",
            task="Onboard a collaborator to memory-gateway storage and stack decisions.",
            allowed_zones=[
                MemoryZone.WORK_CONTEXT,
                MemoryZone.PERSONAL_CONTEXT,
                MemoryZone.PAYMENT_REFERENCE,
            ],
        ),
    )

    assert "FastAPI" in preview.prompt_context
    assert "Alice" not in preview.prompt_context
    assert preview.scope.allowed_zones == [MemoryZone.WORK_CONTEXT]
    assert all(card.zone == MemoryZone.WORK_CONTEXT for card in preview.source_cards)
    assert "Personal, sensitive, payment" in preview.excluded_summary[0]


def test_share_pack_create_token_hash_and_guest_compose(session):
    admin = authenticate_api_key("admin-demo-key")
    guest = authenticate_api_key("guest-demo-key")
    assert admin and guest

    _approve_work_memory(
        session,
        admin,
        "Project decision: memory-gateway uses Postgres with pgvector for retrieval.",
    )

    denied = compose_context(
        session,
        guest,
        ContextComposeRequest(
            task="Which storage should memory-gateway use?",
            project_id="memory-gateway",
            zones=[MemoryZone.WORK_CONTEXT],
            include_graph=False,
        ),
    )
    assert "Postgres with pgvector" not in denied.prompt_context
    assert denied.denied_zones

    created = create_share_pack(
        session,
        admin,
        SharePackCreateRequest(
            project_id="memory-gateway",
            name="Backend onboarding",
            recipient_label="new teammate",
            task="Onboard a new backend teammate to memory-gateway.",
            max_uses=2,
        ),
    )
    token = created.share_pack.token
    assert token and token.startswith("sp_")
    stored = session.get(SharePackRecord, created.share_pack.id)
    assert stored
    assert stored.token_hash != token

    shared = compose_share_pack(
        session,
        guest,
        created.share_pack.id,
        SharePackComposeRequest(
            share_token=token,
            task="Which storage should memory-gateway use?",
        ),
    )
    assert "Postgres" in shared.prompt_context
    assert "Project Memory Share Pack" in shared.prompt_context
    assert shared.share_pack.use_count == 1
    assert shared.share_pack.token is None


def test_share_pack_revoke_and_max_use_blocks_access(session):
    admin = authenticate_api_key("admin-demo-key")
    guest = authenticate_api_key("guest-demo-key")
    assert admin and guest
    _approve_work_memory(session, admin, "Project procedure: use pull request review before release.")

    created = create_share_pack(
        session,
        admin,
        SharePackCreateRequest(project_id="memory-gateway", max_uses=1),
    )
    token = created.share_pack.token
    assert token
    compose_share_pack(
        session,
        guest,
        created.share_pack.id,
        SharePackComposeRequest(share_token=token),
    )
    with pytest.raises(InvalidState):
        compose_share_pack(
            session,
            guest,
            created.share_pack.id,
            SharePackComposeRequest(share_token=token),
        )

    second = create_share_pack(
        session,
        admin,
        SharePackCreateRequest(project_id="memory-gateway", max_uses=5),
    )
    second_token = second.share_pack.token
    assert second_token
    revoked = revoke_share_pack(session, admin, second.share_pack.id)
    assert revoked.status == SharePackStatus.REVOKED
    with pytest.raises(InvalidState):
        compose_share_pack(
            session,
            guest,
            second.share_pack.id,
            SharePackComposeRequest(share_token=second_token),
        )


def test_share_pack_project_isolation_and_superseded_exclusion(session):
    admin = authenticate_api_key("admin-demo-key")
    guest = authenticate_api_key("guest-demo-key")
    assert admin and guest
    old_id = _approve_work_memory(
        session,
        admin,
        "Project decision: memory-gateway temporarily uses SQLite.",
    )
    new_id = _approve_work_memory(
        session,
        admin,
        "Project decision: travel-planner uses a calendar API.",
        project_id="travel-planner",
    )
    old = session.get(MemoryRecord, old_id)
    assert old
    old.status = ProposalStatus.SUPERSEDED.value
    old.superseded_by_id = "replacement"
    session.flush()

    created = create_share_pack(
        session,
        admin,
        SharePackCreateRequest(
            project_id="travel-planner",
            task="Onboard a collaborator to travel-planner.",
        ),
    )
    token = created.share_pack.token
    assert token
    shared = compose_share_pack(
        session,
        guest,
        created.share_pack.id,
        SharePackComposeRequest(share_token=token, task="Which API does travel-planner use?"),
    )
    assert "calendar API" in shared.prompt_context
    assert "SQLite" not in shared.prompt_context
    assert all(card.id != old_id for card in shared.source_cards)
    assert any(card.id == new_id for card in shared.source_cards)


def test_share_pack_invalid_token_and_audit(session):
    admin = authenticate_api_key("admin-demo-key")
    guest = authenticate_api_key("guest-demo-key")
    assert admin and guest
    _approve_work_memory(session, admin, "Project requirement: share packs must be auditable.")

    preview = preview_share_pack(
        session,
        admin,
        SharePackPreviewRequest(project_id="memory-gateway"),
    )
    created = create_share_pack(
        session,
        admin,
        SharePackCreateRequest(project_id="memory-gateway"),
    )
    assert preview.audit_id
    with pytest.raises(PermissionDenied):
        compose_share_pack(
            session,
            guest,
            created.share_pack.id,
            SharePackComposeRequest(share_token="sp_wrong"),
        )
    token = created.share_pack.token
    assert token
    compose_share_pack(
        session,
        guest,
        created.share_pack.id,
        SharePackComposeRequest(share_token=token),
    )
    revoke_share_pack(session, admin, created.share_pack.id)

    from memory_gateway.db import AuditEventRecord
    from sqlalchemy import select

    actions = {
        row.action
        for row in session.scalars(
            select(AuditEventRecord).where(AuditEventRecord.resource_type == "share_pack")
        )
    }
    assert AuditAction.SHARE_PREVIEW.value in actions
    assert AuditAction.SHARE_CREATE.value in actions
    assert AuditAction.SHARE_COMPOSE.value in actions
    assert AuditAction.SHARE_REVOKE.value in actions
