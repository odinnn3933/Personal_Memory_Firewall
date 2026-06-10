from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from memory_gateway.db import Base
from memory_gateway.runtime.context import compose_approved_context_request, compose_context, request_context
from memory_gateway.runtime.ingestion import approve_inbox_item, ingest_memory
from memory_gateway.runtime.memories import memory_detail
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
    assert admin and backend

    with Session() as session:
        seed_demo_data(session)

        capture = ingest_memory(
            session,
            admin,
            IngestRequest(
                content="Alice is my close friend. We usually play basketball together on weekends.",
                auto_approve_public_low=False,
            ),
        )
        assert capture.inbox_item
        print("\n== capture classified ==")
        print(f"zone: {capture.inbox_item.suggested_zone}")
        print(f"type: {capture.inbox_item.suggested_memory_type}")
        print(f"summary: {capture.inbox_item.semantic_summary}")

        approved = approve_inbox_item(
            session,
            admin,
            capture.inbox_item.id,
            InboxApproveRequest(memory_zone=MemoryZone.PERSONAL_CONTEXT),
        )
        assert approved.approved_memory_id
        detail = memory_detail(session, admin, approved.approved_memory_id)
        print("\n== relationship facts ==")
        for fact in detail.facts:
            print(f"{fact.relation_type}: {fact.subtitle}")

        denied = compose_context(
            session,
            backend,
            ContextComposeRequest(
                task="Who is Alice to the user?",
                zones=[MemoryZone.PERSONAL_CONTEXT],
                include_graph=False,
            ),
        )
        print("\n== without grant ==")
        print(denied.prompt_context)

        request = request_context(
            session,
            backend,
            ContextRequestRequest(
                task="Who is Alice to the user?",
                task_id="relationship-demo",
                purpose="Need personal relationship context.",
                zones=[MemoryZone.PERSONAL_CONTEXT],
                include_graph=False,
            ),
        )
        assert request.grant
        approve_access_grant(session, admin, request.grant.id)
        ready = compose_approved_context_request(session, backend, request.grant.id)
        assert ready.context
        print("\n== with approved personal_context grant ==")
        print(ready.context.prompt_context)

        assert "Alice" in ready.context.prompt_context
        assert "## Relationships" in ready.context.prompt_context
        print("\nRELATIONSHIP MEMORY DEMO PASS")


if __name__ == "__main__":
    main()
