from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from memory_gateway.db import Base
from memory_gateway.runtime.context import compose_context
from memory_gateway.runtime.ingestion import approve_inbox_item, ingest_memory
from memory_gateway.schemas import ContextComposeRequest, GrantRequest, InboxApproveRequest, IngestRequest
from memory_gateway.security import authenticate_api_key
from memory_gateway.service import approve_access_grant, request_access_grant, seed_demo_data
from memory_gateway.types import MemoryZone


def main() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, future=True)
    admin = authenticate_api_key("admin-demo-key")
    backend = authenticate_api_key("backend-demo-key")
    guest = authenticate_api_key("guest-demo-key")
    assert admin and backend and guest

    with Session() as session:
        seed_demo_data(session)
        capture = ingest_memory(
            session,
            admin,
            IngestRequest(
                content="Project requirement: long-term memory storage must use Postgres and pgvector.",
                project_id="memory-gateway",
            ),
        )
        assert capture.inbox_item
        approve_inbox_item(session, admin, capture.inbox_item.id, InboxApproveRequest())

        task = "Recommend storage for long-term agent memory."
        guest_context = compose_context(
            session,
            guest,
            ContextComposeRequest(
                task=task,
                project_id="memory-gateway",
                zones=[MemoryZone.WORK_CONTEXT],
                include_graph=False,
            ),
        )
        print("\n== guest_agent ==")
        print(guest_context.prompt_context)

        grant = request_access_grant(
            session,
            backend,
            GrantRequest(
                task_id="agent-demo",
                purpose="Need work_context to answer project storage question.",
                allowed_zones=[MemoryZone.WORK_CONTEXT],
                project_id="memory-gateway",
            ),
        )
        approved = approve_access_grant(session, admin, grant.id)
        assert approved.token
        backend_context = compose_context(
            session,
            backend,
            ContextComposeRequest(
                task=task,
                project_id="memory-gateway",
                zones=[MemoryZone.WORK_CONTEXT],
                grant_token=approved.token,
                include_graph=False,
            ),
        )
        print("\n== backend_agent with grant ==")
        print(backend_context.prompt_context)


if __name__ == "__main__":
    main()
