from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from memory_gateway.db import Base
from memory_gateway.runtime.context import compose_approved_context_request, compose_context, request_context
from memory_gateway.runtime.ingestion import approve_inbox_item, ingest_memory
from memory_gateway.schemas import ContextComposeRequest, ContextRequestRequest, InboxApproveRequest, IngestRequest
from memory_gateway.security import authenticate_api_key
from memory_gateway.service import approve_access_grant, seed_demo_data
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
        relationship = ingest_memory(
            session,
            admin,
            IngestRequest(
                content="Alice is my close friend. We usually play basketball together on weekends.",
                auto_approve_public_low=False,
            ),
        )
        assert relationship.inbox_item
        approve_inbox_item(
            session,
            admin,
            relationship.inbox_item.id,
            InboxApproveRequest(memory_zone=MemoryZone.PERSONAL_CONTEXT),
        )

        print("\n== backend agent requests work_context ==")
        work_request = request_context(
            session,
            backend,
            ContextRequestRequest(
                task="Choose storage for the memory-gateway project.",
                task_id="agent-flow-work",
                purpose="Need project memory before making an architecture recommendation.",
                project_id="memory-gateway",
                zones=[MemoryZone.WORK_CONTEXT],
                include_graph=False,
            ),
        )
        assert work_request.status == "pending_grant"
        assert work_request.grant
        print(f"pending grant: {work_request.grant.id}")

        before = compose_approved_context_request(session, backend, work_request.grant.id)
        assert before.status == "pending_grant"
        print("agent polling before approval:", before.status)

        approve_access_grant(session, admin, work_request.grant.id)
        work_ready = compose_approved_context_request(session, backend, work_request.grant.id)
        assert work_ready.status == "ready"
        assert work_ready.context
        assert "Postgres" in work_ready.context.prompt_context
        print("\n== approved work context ==")
        print(work_ready.context.prompt_context)

        print("\n== guest/no grant cannot read protected relationship ==")
        denied = compose_context(
            session,
            guest,
            ContextComposeRequest(
                task="Who is Alice to the user?",
                zones=[MemoryZone.PERSONAL_CONTEXT],
                include_graph=False,
            ),
        )
        assert "Alice is my close friend" not in denied.prompt_context
        assert "## Relationships" not in denied.prompt_context
        print(denied.prompt_context)

        print("\n== backend requests personal relationship context ==")
        personal_request = request_context(
            session,
            backend,
            ContextRequestRequest(
                task="Who is Alice to the user?",
                task_id="agent-flow-personal",
                purpose="Need personal relationship context for the current social task.",
                zones=[MemoryZone.PERSONAL_CONTEXT],
                include_graph=False,
            ),
        )
        assert personal_request.grant
        approve_access_grant(session, admin, personal_request.grant.id)
        personal_ready = compose_approved_context_request(session, backend, personal_request.grant.id)
        assert personal_ready.context
        assert "Alice" in personal_ready.context.prompt_context
        assert "## Relationships" in personal_ready.context.prompt_context
        print(personal_ready.context.prompt_context)

        print("\nAGENT REQUEST FLOW DEMO PASS")


if __name__ == "__main__":
    main()
