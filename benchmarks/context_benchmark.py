from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from memory_gateway.db import AccessGrantRecord, Base
from memory_gateway.runtime.context import compose_context
from memory_gateway.schemas import ContextComposeRequest, GrantRequest
from memory_gateway.security import authenticate_api_key
from memory_gateway.service import (
    approve_access_grant,
    benchmark_forbidden_leak_rate,
    request_access_grant,
    seed_demo_data,
    utcnow,
)
from memory_gateway.types import MemoryZone


def main() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, future=True)
    admin = authenticate_api_key("admin-demo-key")
    guest = authenticate_api_key("guest-demo-key")
    backend = authenticate_api_key("backend-demo-key")
    assert admin and guest and backend

    with Session() as session:
        seed_demo_data(session)
        result = benchmark_forbidden_leak_rate(session, guest, backend)

        grant = request_access_grant(
            session,
            backend,
            GrantRequest(
                task_id="context-bench",
                purpose="Measure context recall.",
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
                task="Which database and vector backend should this project use?",
                project_id="memory-gateway",
                zones=[MemoryZone.WORK_CONTEXT],
                grant_token=approved.token,
                include_graph=False,
            ),
        )
        lowered = context.prompt_context.lower()
        result["context_recall_accuracy"] = 1.0 if "postgres" in lowered and "pgvector" in lowered else 0.0
        result["prompt_context_has_sources"] = 1 if context.source_cards else 0

        record = session.get(AccessGrantRecord, grant.id)
        assert record
        record.expires_at = utcnow().replace(year=2000)
        expired_context = compose_context(
            session,
            backend,
            ContextComposeRequest(
                task="Which database and vector backend should this project use?",
                project_id="memory-gateway",
                zones=[MemoryZone.WORK_CONTEXT],
                grant_token=approved.token,
                include_graph=False,
            ),
        )
        result["expired_grant_access"] = 1 if "pgvector" in expired_context.prompt_context.lower() else 0
        print(result)


if __name__ == "__main__":
    main()
