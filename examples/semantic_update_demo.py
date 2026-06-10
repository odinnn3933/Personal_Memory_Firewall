from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from memory_gateway.db import Base
from memory_gateway.runtime.context import compose_context
from memory_gateway.runtime.ingestion import approve_inbox_separate, approve_inbox_update, ingest_memory
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
    assert admin and backend

    with Session() as session:
        seed_demo_data(session)
        old = ingest_memory(
            session,
            admin,
            IngestRequest(content="I live 15 km from the office.", auto_approve_public_low=False),
        )
        assert old.inbox_item
        approved_old = approve_inbox_separate(
            session,
            admin,
            old.inbox_item.id,
            InboxApproveRequest(memory_zone=MemoryZone.PERSONAL_CONTEXT),
        )

        new = ingest_memory(
            session,
            admin,
            IngestRequest(content="I moved recently. I now live 3 km from the office.", auto_approve_public_low=False),
        )
        assert new.inbox_item
        print("\n== semantic judgment ==")
        print(
            {
                "summary": new.inbox_item.semantic_summary,
                "relationship": new.inbox_item.llm_relationship,
                "confidence": new.inbox_item.llm_confidence,
                "candidate_ids": new.inbox_item.candidate_memory_ids,
            }
        )

        approve_inbox_update(
            session,
            admin,
            new.inbox_item.id,
            InboxApproveRequest(
                memory_zone=MemoryZone.PERSONAL_CONTEXT,
                supersede_memory_id=approved_old.approved_memory_id,
            ),
        )
        grant = request_access_grant(
            session,
            backend,
            GrantRequest(
                task_id="semantic-update-demo",
                purpose="Need personal context for commute answer.",
                allowed_zones=[MemoryZone.PERSONAL_CONTEXT],
            ),
        )
        approved_grant = approve_access_grant(session, admin, grant.id)
        assert approved_grant.token
        context = compose_context(
            session,
            backend,
            ContextComposeRequest(
                task="How far does the user currently live from the office?",
                zones=[MemoryZone.PERSONAL_CONTEXT],
                grant_token=approved_grant.token,
                include_graph=False,
            ),
        )
        print("\n== composed context ==")
        print(context.prompt_context)


if __name__ == "__main__":
    main()
