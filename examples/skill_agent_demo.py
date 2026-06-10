from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from memory_gateway.db import Base
from memory_gateway.schemas import CaptureCommitRequest, GrantRequest, VaultSearchRequest
from memory_gateway.security import authenticate_api_key
from memory_gateway.service import (
    approve_access_grant,
    commit_capture,
    request_access_grant,
    seed_demo_data,
    vault_search,
)
from memory_gateway.types import MemoryType, MemoryZone


def main() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, future=True)
    admin = authenticate_api_key("admin-demo-key")
    backend = authenticate_api_key("backend-demo-key")
    assert admin and backend

    with Session() as session:
        seed_demo_data(session)
        commit_capture(
            session,
            admin,
            CaptureCommitRequest(
                content="Work memory: when editing APIs, preserve backward compatibility.",
                memory_zone=MemoryZone.WORK_CONTEXT,
                memory_type=MemoryType.PROCEDURE,
                project_id="memory-gateway",
                tags=["api", "compatibility"],
            ),
        )

        print("\n== skill step 1: request minimum grant ==")
        grant = request_access_grant(
            session,
            backend,
            GrantRequest(
                task_id="skill-demo-001",
                purpose="Need work_context to edit API behavior safely.",
                allowed_zones=[MemoryZone.WORK_CONTEXT],
                project_id="memory-gateway",
            ),
        )
        print(grant.model_dump())

        print("\n== skill step 2: user approves in desktop/admin surface ==")
        approved = approve_access_grant(session, admin, grant.id)
        print({"grant_id": approved.id, "token_present": bool(approved.token)})

        print("\n== skill step 3: agent searches with grant token ==")
        result = vault_search(
            session,
            backend,
            VaultSearchRequest(
                query="API backward compatibility",
                project_id="memory-gateway",
                zones=[MemoryZone.WORK_CONTEXT],
                grant_token=approved.token,
            ),
        )
        for memory in result.memories:
            print(f"- {memory.memory_zone}: {memory.content}")


if __name__ == "__main__":
    main()
