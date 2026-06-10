from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import memory_gateway.service as service
from memory_gateway.db import Base, MemoryRecord
from memory_gateway.graph import GraphHealth, GraphQueryResult, GraphWriteResult
from memory_gateway.schemas import CaptureCommitRequest, GraphCardOut, GraphSearchRequest, GrantRequest
from memory_gateway.security import authenticate_api_key
from memory_gateway.types import MemoryType, MemoryZone, Sensitivity


class DemoGraphClient:
    def __init__(self) -> None:
        self.indexed_memory_ids: list[str] = []

    def health(self) -> GraphHealth:
        return GraphHealth(True, True)

    def upsert_memory(self, memory: MemoryRecord) -> GraphWriteResult:
        self.indexed_memory_ids.append(memory.id)
        return GraphWriteResult(True, 1)

    def mark_memory_inactive(self, memory_id: str) -> GraphWriteResult:
        if memory_id in self.indexed_memory_ids:
            self.indexed_memory_ids.remove(memory_id)
        return GraphWriteResult(True, 1)

    def mark_tenant_inactive(self, tenant_id: str) -> GraphWriteResult:
        self.indexed_memory_ids.clear()
        return GraphWriteResult(True, 1)

    def search(
        self,
        tenant_id: str,
        query: str,
        allowed_memory_ids: list[str],
        top_k: int,
    ) -> GraphQueryResult:
        visible = [memory_id for memory_id in self.indexed_memory_ids if memory_id in allowed_memory_ids]
        if not visible:
            return GraphQueryResult(True, [])
        return GraphQueryResult(
            True,
            [
                GraphCardOut(
                    id="demo-postgres-pgvector",
                    title="memory-gateway -> Postgres + pgvector",
                    subtitle="Long-term memory storage should prefer Postgres + pgvector.",
                    entity_type="tool",
                    relation_type="REQUIRES",
                    zone=MemoryZone.WORK_CONTEXT,
                    sensitivity=Sensitivity.MEDIUM,
                    source_count=1,
                    source_memory_ids=[visible[0]],
                    why_visible="demo",
                    risk_note="demo",
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


def main() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, future=True)
    service.get_graph_client = lambda: DemoGraphClient()  # type: ignore[assignment]
    graph_client = service.get_graph_client()
    service.get_graph_client = lambda: graph_client  # type: ignore[assignment]

    with Session() as session:
        service.seed_demo_data(session)
        admin = authenticate_api_key("admin-demo-key")
        backend = authenticate_api_key("backend-demo-key")
        assert admin and backend

        committed = service.commit_capture(
            session,
            admin,
            CaptureCommitRequest(
                content="Project requirement: long-term memory storage should prefer Postgres + pgvector.",
                memory_zone=MemoryZone.WORK_CONTEXT,
                memory_type=MemoryType.CONTEXT,
                project_id="memory-gateway",
            ),
        )
        assert committed.memory
        print("1. Saved work memory and indexed graph source:", committed.memory.id)

        try:
            service.graph_search(
                session,
                backend,
                GraphSearchRequest(
                    query="postgres pgvector",
                    project_id="memory-gateway",
                    zones=[MemoryZone.WORK_CONTEXT],
                ),
            )
        except service.PermissionDenied as error:
            print("2. Backend agent without grant is blocked:", error)

        grant = service.request_access_grant(
            session,
            backend,
            GrantRequest(
                task_id="graph-demo",
                purpose="Need permissioned graph context for storage recommendation.",
                allowed_zones=[MemoryZone.WORK_CONTEXT],
                project_id="memory-gateway",
            ),
        )
        approved = service.approve_access_grant(session, admin, grant.id)
        result = service.graph_search(
            session,
            backend,
            GraphSearchRequest(
                query="postgres pgvector",
                project_id="memory-gateway",
                zones=[MemoryZone.WORK_CONTEXT],
                grant_token=approved.token,
            ),
        )
        print("3. Approved graph cards:", [card.title for card in result.cards])

        service.revoke_access_grant(session, admin, grant.id)
        try:
            service.graph_search(
                session,
                backend,
                GraphSearchRequest(
                    query="postgres pgvector",
                    project_id="memory-gateway",
                    zones=[MemoryZone.WORK_CONTEXT],
                    grant_token=approved.token,
                ),
            )
        except service.PermissionDenied as error:
            print("4. Revoked grant is blocked:", error)


if __name__ == "__main__":
    main()
