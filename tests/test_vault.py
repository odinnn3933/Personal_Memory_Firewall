from __future__ import annotations

from datetime import timedelta

import pytest

from memory_gateway.db import AccessGrantRecord, AuditEventRecord
from memory_gateway.schemas import (
    CaptureAnalyzeRequest,
    CaptureCommitRequest,
    GrantRequest,
    VaultSearchRequest,
)
from memory_gateway.security import authenticate_api_key
from memory_gateway.service import (
    PermissionDenied,
    analyze_capture,
    approve_access_grant,
    commit_capture,
    request_access_grant,
    revoke_access_grant,
    token_hash,
    utcnow,
    vault_search,
)
from memory_gateway.types import ContentKind, GrantStatus, MemoryType, MemoryZone


def test_capture_analyzer_classifies_zones(session):
    admin = authenticate_api_key("admin-demo-key")
    assert admin

    work = analyze_capture(
        session,
        admin,
        CaptureAnalyzeRequest(content="Project meeting decided the backend API contract."),
    )
    personal = analyze_capture(
        session,
        admin,
        CaptureAnalyzeRequest(content="For travel, I prefer aisle seats and morning flights."),
    )
    payment = analyze_capture(
        session,
        admin,
        CaptureAnalyzeRequest(content="Use Visa card for payment, CVV 123"),
    )
    image = analyze_capture(
        session,
        admin,
        CaptureAnalyzeRequest(content="screenshot of a receipt", content_kind=ContentKind.IMAGE),
    )

    assert work.suggested_zone == MemoryZone.WORK_CONTEXT
    assert personal.suggested_zone == MemoryZone.PERSONAL_CONTEXT
    assert payment.suggested_zone == MemoryZone.PAYMENT_REFERENCE
    assert image.suggested_zone == MemoryZone.PERSONAL_CONTEXT


def test_redaction_prevents_raw_payment_storage(session):
    admin = authenticate_api_key("admin-demo-key")
    assert admin

    response = commit_capture(
        session,
        admin,
        CaptureCommitRequest(
            content="Visa card 4111 1111 1111 1111 CVV 123 token=abc123",
            memory_zone=MemoryZone.PAYMENT_REFERENCE,
            memory_type=MemoryType.PROCEDURE,
            project_id="memory-gateway",
        ),
    )

    assert response.memory
    assert "4111" not in response.memory.content
    assert "abc123" not in response.memory.content
    assert "[REDACTED_CARD]" in response.memory.content
    assert response.memory.redacted


def test_zone_default_sensitivity_is_applied_on_commit(session):
    admin = authenticate_api_key("admin-demo-key")
    assert admin

    response = commit_capture(
        session,
        admin,
        CaptureCommitRequest(
            content="Project policy: all memory access must be audited.",
            memory_zone=MemoryZone.WORK_CONTEXT,
            memory_type=MemoryType.CONTEXT,
            project_id="memory-gateway",
        ),
    )

    assert response.memory
    assert response.memory.sensitivity.value == "medium"


def test_vault_requires_grant_for_work_context(session):
    admin = authenticate_api_key("admin-demo-key")
    backend = authenticate_api_key("backend-demo-key")
    assert admin and backend

    commit_capture(
        session,
        admin,
        CaptureCommitRequest(
            content="Project policy: use audit logs for every memory access.",
            memory_zone=MemoryZone.WORK_CONTEXT,
            memory_type=MemoryType.CONTEXT,
            project_id="memory-gateway",
        ),
    )

    with pytest.raises(PermissionDenied):
        vault_search(
            session,
            backend,
            VaultSearchRequest(
                query="audit logs",
                project_id="memory-gateway",
                zones=[MemoryZone.WORK_CONTEXT],
            ),
        )

    grant = request_access_grant(
        session,
        backend,
            GrantRequest(
                task_id="task-1",
                purpose="Need project policy for implementation.",
                allowed_zones=[MemoryZone.WORK_CONTEXT],
                project_id="memory-gateway",
            ),
    )
    approved = approve_access_grant(session, admin, grant.id)

    result = vault_search(
        session,
        backend,
        VaultSearchRequest(
            query="audit logs",
            project_id="memory-gateway",
            zones=[MemoryZone.WORK_CONTEXT],
            grant_token=approved.token,
        ),
    )

    assert any("audit logs" in memory.content for memory in result.memories)


def test_grant_scope_expiry_and_revoke(session):
    admin = authenticate_api_key("admin-demo-key")
    backend = authenticate_api_key("backend-demo-key")
    assert admin and backend

    grant = request_access_grant(
        session,
        backend,
            GrantRequest(
                task_id="task-2",
                purpose="Need work context only.",
                allowed_zones=[MemoryZone.WORK_CONTEXT],
                project_id="memory-gateway",
            ),
    )
    approved = approve_access_grant(session, admin, grant.id)
    assert approved.token

    with pytest.raises(PermissionDenied):
        vault_search(
            session,
            backend,
            VaultSearchRequest(
                query="payment",
                project_id="memory-gateway",
                zones=[MemoryZone.PAYMENT_REFERENCE],
                grant_token=approved.token,
            ),
        )

    record = session.get(AccessGrantRecord, grant.id)
    record.expires_at = utcnow() - timedelta(seconds=1)
    with pytest.raises(PermissionDenied):
        vault_search(
            session,
            backend,
            VaultSearchRequest(
                query="project",
                project_id="memory-gateway",
                zones=[MemoryZone.WORK_CONTEXT],
                grant_token=approved.token,
            ),
        )
    assert record.status == GrantStatus.EXPIRED

    grant_2 = request_access_grant(
        session,
        backend,
            GrantRequest(
                task_id="task-3",
                purpose="Need work context again.",
                allowed_zones=[MemoryZone.WORK_CONTEXT],
                project_id="memory-gateway",
            ),
    )
    approved_2 = approve_access_grant(session, admin, grant_2.id)
    revoke_access_grant(session, admin, grant_2.id)
    with pytest.raises(PermissionDenied):
        vault_search(
            session,
            backend,
            VaultSearchRequest(
                query="project",
                project_id="memory-gateway",
                zones=[MemoryZone.WORK_CONTEXT],
                grant_token=approved_2.token,
            ),
        )


def test_grant_token_is_hashed_and_audited(session):
    admin = authenticate_api_key("admin-demo-key")
    backend = authenticate_api_key("backend-demo-key")
    assert admin and backend

    grant = request_access_grant(
        session,
        backend,
            GrantRequest(
                task_id="task-token",
                purpose="Need work memory.",
                allowed_zones=[MemoryZone.WORK_CONTEXT],
                project_id="memory-gateway",
            ),
    )
    approved = approve_access_grant(session, admin, grant.id)
    record = session.get(AccessGrantRecord, grant.id)

    assert approved.token
    assert record.token_hash == token_hash(approved.token)
    assert record.token_hash != approved.token
    assert session.query(AuditEventRecord).count() >= 2
