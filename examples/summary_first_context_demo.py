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
    assert admin and backend

    with Session() as session:
        seed_demo_data(session)
        capture = ingest_memory(
            session,
            admin,
            IngestRequest(
                content="Project decision: memory-gateway should use Postgres and pgvector for long-term memory retrieval.",
                project_id="memory-gateway",
                auto_approve_public_low=False,
            ),
        )
        assert capture.inbox_item
        approve_inbox_item(
            session,
            admin,
            capture.inbox_item.id,
            InboxApproveRequest(memory_zone=MemoryZone.WORK_CONTEXT, project_id="memory-gateway"),
        )
        grant = request_access_grant(
            session,
            backend,
            GrantRequest(
                task_id="summary-first-demo",
                purpose="Need work memory for storage recommendation.",
                allowed_zones=[MemoryZone.WORK_CONTEXT],
                project_id="memory-gateway",
            ),
        )
        approved = approve_access_grant(session, admin, grant.id)
        assert approved.token
        context = compose_context(
            session,
            backend,
            ContextComposeRequest(
                task="Which database and vector retrieval stack should this project use?",
                project_id="memory-gateway",
                zones=[MemoryZone.WORK_CONTEXT],
                grant_token=approved.token,
                include_graph=False,
                retrieval_mode="summary_first",
            ),
        )
        print("\n== matched summaries ==")
        for candidate in context.matched_summaries:
            print(f"- {candidate.memory_id}: {candidate.summary} ({candidate.score})")
        print("\n== prompt context ==")
        print(context.prompt_context)


if __name__ == "__main__":
    main()
