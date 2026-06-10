from __future__ import annotations

import pytest

import memory_gateway.service as service
from memory_gateway.graph import GraphHealth, GraphQueryResult, GraphWriteResult, extract_graph_candidates
from memory_gateway.db import MemoryRecord
from memory_gateway.schemas import CaptureCommitRequest, GraphCardOut, GraphSearchRequest, GrantRequest
from memory_gateway.security import authenticate_api_key
from memory_gateway.types import MemoryType, MemoryZone, ProposalStatus, Sensitivity, Visibility


class FakeGraphClient:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.reason = None if available else "neo4j unavailable"
        self.search_allowed_ids: list[str] = []
        self.upserted: list[str] = []
        self.inactive: list[str] = []

    def health(self) -> GraphHealth:
        return GraphHealth(self.available, True, self.reason)

    def upsert_memory(self, memory: MemoryRecord) -> GraphWriteResult:
        self.upserted.append(memory.id)
        return GraphWriteResult(self.available, 1 if self.available else 0, self.reason)

    def mark_memory_inactive(self, memory_id: str) -> GraphWriteResult:
        self.inactive.append(memory_id)
        return GraphWriteResult(self.available, 1 if self.available else 0, self.reason)

    def mark_tenant_inactive(self, tenant_id: str) -> GraphWriteResult:
        return GraphWriteResult(self.available, 1 if self.available else 0, self.reason)

    def search(
        self,
        tenant_id: str,
        query: str,
        allowed_memory_ids: list[str],
        top_k: int,
    ) -> GraphQueryResult:
        self.search_allowed_ids = allowed_memory_ids
        if not self.available:
            return GraphQueryResult(False, [], self.reason)
        if not allowed_memory_ids:
            return GraphQueryResult(True, [])
        return GraphQueryResult(
            True,
            [
                GraphCardOut(
                    id="rel-test",
                    title="memory-gateway -> Postgres",
                    subtitle="memory-gateway requires Postgres + pgvector.",
                    entity_type="tool",
                    relation_type="REQUIRES",
                    zone=MemoryZone.WORK_CONTEXT,
                    sensitivity=Sensitivity.MEDIUM,
                    source_count=1,
                    source_memory_ids=[allowed_memory_ids[0]],
                    why_visible="fake",
                    risk_note="fake",
                )
            ],
        )

    def explain_entity(
        self,
        tenant_id: str,
        entity_id: str,
        allowed_memory_ids: list[str],
        top_k: int = 10,
    ) -> GraphQueryResult:
        return self.search(tenant_id, entity_id, allowed_memory_ids, top_k)


def test_graph_extractor_from_work_memory():
    memory = MemoryRecord(
        id="mem-test",
        tenant_id="demo",
        project_id="memory-gateway",
        visibility=Visibility.PROJECT.value,
        memory_type=MemoryType.CONTEXT.value,
        memory_zone=MemoryZone.WORK_CONTEXT.value,
        content="Project requirement: long-term memory storage should use Postgres + pgvector.",
        tags=[],
        sensitivity=Sensitivity.MEDIUM.value,
        source="test",
        embedding=[],
        status=ProposalStatus.APPROVED.value,
    )

    candidates = extract_graph_candidates(memory)

    assert any(candidate.object_name == "Postgres" for candidate in candidates)
    assert any(candidate.object_name == "pgvector" for candidate in candidates)
    assert {candidate.relation_type for candidate in candidates} == {"REQUIRES"}


def test_payment_graph_candidate_is_reference_only():
    memory = MemoryRecord(
        id="mem-pay",
        tenant_id="demo",
        project_id="memory-gateway",
        visibility=Visibility.PROJECT.value,
        memory_type=MemoryType.PROCEDURE.value,
        memory_zone=MemoryZone.PAYMENT_REFERENCE.value,
        content="Use [REDACTED_CARD] and [REDACTED_CVV].",
        tags=[],
        sensitivity=Sensitivity.HIGH.value,
        source="test",
        embedding=[],
        status=ProposalStatus.APPROVED.value,
    )

    candidates = extract_graph_candidates(memory)

    assert len(candidates) == 1
    assert candidates[0].object_type == "payment_reference"
    assert "REDACTED_CARD" not in candidates[0].summary


def test_graph_search_uses_grant_and_sql_acl(monkeypatch, session):
    fake = FakeGraphClient()
    monkeypatch.setattr(service, "get_graph_client", lambda: fake)
    admin = authenticate_api_key("admin-demo-key")
    backend = authenticate_api_key("backend-demo-key")
    assert admin and backend
    committed = service.commit_capture(
        session,
        admin,
        CaptureCommitRequest(
            content="Project requirement: long-term memory storage should use Postgres + pgvector.",
            memory_zone=MemoryZone.WORK_CONTEXT,
            memory_type=MemoryType.CONTEXT,
            project_id="memory-gateway",
        ),
    )
    assert committed.memory
    assert committed.memory.id in fake.upserted

    with pytest.raises(service.PermissionDenied):
        service.graph_search(
            session,
            backend,
            GraphSearchRequest(
                query="postgres",
                project_id="memory-gateway",
                zones=[MemoryZone.WORK_CONTEXT],
            ),
        )

    grant = service.request_access_grant(
        session,
        backend,
            GrantRequest(
                task_id="graph-task",
                purpose="Need work graph memory.",
                allowed_zones=[MemoryZone.WORK_CONTEXT],
                project_id="memory-gateway",
            ),
    )
    approved = service.approve_access_grant(session, admin, grant.id)
    result = service.graph_search(
        session,
        backend,
        GraphSearchRequest(
            query="postgres",
            project_id="memory-gateway",
            zones=[MemoryZone.WORK_CONTEXT],
            grant_token=approved.token,
        ),
    )

    assert result.graph_available
    assert len(result.cards) == 1
    assert committed.memory.id in fake.search_allowed_ids
    assert result.cards[0].source_memory_ids[0] in fake.search_allowed_ids
    assert result.cards[0].why_visible.startswith("Visible because every source memory")

    service.revoke_access_grant(session, admin, grant.id)
    with pytest.raises(service.PermissionDenied):
        service.graph_search(
            session,
            backend,
            GraphSearchRequest(
                query="postgres",
                project_id="memory-gateway",
                zones=[MemoryZone.WORK_CONTEXT],
                grant_token=approved.token,
            ),
        )


def test_graph_unavailable_degrades(monkeypatch, session):
    fake = FakeGraphClient(available=False)
    monkeypatch.setattr(service, "get_graph_client", lambda: fake)

    health = service.graph_health()

    assert not health.graph_available
    assert health.reason == "neo4j unavailable"
