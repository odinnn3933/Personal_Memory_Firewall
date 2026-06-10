from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from memory_gateway.db import Base
from memory_gateway.runtime.context import compose_context
from memory_gateway.schemas import ContextComposeRequest, GrantRequest
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

        request = ContextComposeRequest(
            task="Choose the database for long-term memory retrieval.",
            project_id="memory-gateway",
            zones=[MemoryZone.PUBLIC_PROFILE, MemoryZone.WORK_CONTEXT],
            include_graph=False,
        )
        denied = compose_context(session, backend, request)
        show("without grant")
        print(denied.prompt_context)

        grant = request_access_grant(
            session,
            backend,
            GrantRequest(
                task_id="ctx-demo",
                purpose="Need work_context to choose project database.",
                allowed_zones=[MemoryZone.WORK_CONTEXT],
                project_id="memory-gateway",
            ),
        )
        approved = approve_access_grant(session, admin, grant.id)
        assert approved.token

        allowed = compose_context(
            session,
            backend,
            request.model_copy(update={"grant_token": approved.token}),
        )
        show("with grant")
        print(allowed.prompt_context)
        show("sources")
        for card in allowed.source_cards:
            print(f"- {card.id}: {card.title} score={card.score}")


if __name__ == "__main__":
    main()
