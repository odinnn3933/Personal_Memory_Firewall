from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from memory_gateway.db import Base
from memory_gateway.runtime.context import compose_context
from memory_gateway.runtime.ingestion import approve_inbox_item, approve_inbox_update, ingest_memory
from memory_gateway.schemas import ContextComposeRequest, GrantRequest, InboxApproveRequest, IngestRequest
from memory_gateway.security import authenticate_api_key
from memory_gateway.service import approve_access_grant, request_access_grant, seed_demo_data
from memory_gateway.types import MemoryZone


def show(title: str) -> None:
    print(f"\n== {title} ==")


def main() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, future=True)
    admin = authenticate_api_key("admin-demo-key")
    backend = authenticate_api_key("backend-demo-key")
    assert admin and backend

    with Session() as session:
        seed_demo_data(session)

        first = ingest_memory(
            session,
            admin,
            IngestRequest(
                content="I live 15 km from the office.",
                auto_approve_public_low=False,
            ),
        )
        assert first.inbox_item
        first_approved = approve_inbox_item(
            session,
            admin,
            first.inbox_item.id,
            InboxApproveRequest(memory_zone=MemoryZone.PERSONAL_CONTEXT),
        )
        show("old memory approved")
        print({"memory_id": first_approved.approved_memory_id, "preview": first.inbox_item.redacted_preview})

        update = ingest_memory(
            session,
            admin,
            IngestRequest(
                content="I moved recently. I now live 3 km from the office.",
                auto_approve_public_low=False,
            ),
        )
        assert update.inbox_item
        show("update detected")
        print(
            {
                "proposal_kind": update.inbox_item.proposal_kind.value,
                "conflicts": update.inbox_item.conflict_memory_ids,
                "supersedes": update.inbox_item.supersedes_memory_id,
            }
        )

        approved_update = approve_inbox_update(
            session,
            admin,
            update.inbox_item.id,
            InboxApproveRequest(
                memory_zone=MemoryZone.PERSONAL_CONTEXT,
                supersede_memory_id=update.inbox_item.supersedes_memory_id,
            ),
        )
        show("new memory approved")
        print({"new_memory_id": approved_update.approved_memory_id})

        grant = request_access_grant(
            session,
            backend,
            GrantRequest(
                task_id="lifecycle-demo",
                purpose="Need current commute distance.",
                allowed_zones=[MemoryZone.PERSONAL_CONTEXT],
            ),
        )
        approved_grant = approve_access_grant(session, admin, grant.id)
        assert approved_grant.token

        context = compose_context(
            session,
            backend,
            ContextComposeRequest(
                task="How far does the user live from the office?",
                zones=[MemoryZone.PERSONAL_CONTEXT],
                grant_token=approved_grant.token,
                include_graph=False,
            ),
        )
        show("composed context")
        print(context.prompt_context)


if __name__ == "__main__":
    main()
