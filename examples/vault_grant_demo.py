from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from memory_gateway.db import Base
from memory_gateway.schemas import (
    CaptureAnalyzeRequest,
    CaptureCommitRequest,
    GrantRequest,
    VaultSearchRequest,
)
from memory_gateway.security import authenticate_api_key
from memory_gateway.service import (
    analyze_capture,
    approve_access_grant,
    commit_capture,
    request_access_grant,
    seed_demo_data,
    vault_search,
)
from memory_gateway.types import ContentKind, MemoryType, MemoryZone


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

        copied_work_text = (
            "Project Memory Firewall requirement: agents may use work context only after "
            "short-lived approval. Backend implementation should use audit logs."
        )
        analysis = analyze_capture(
            session,
            admin,
            CaptureAnalyzeRequest(
                content=copied_work_text,
                content_kind=ContentKind.TEXT,
                project_id="memory-gateway",
                source_title="Project notes",
            ),
        )
        show("desktop analyzes copied work text")
        print(analysis.model_dump())

        committed = commit_capture(
            session,
            admin,
            CaptureCommitRequest(
                content=copied_work_text,
                memory_zone=analysis.suggested_zone,
                memory_type=analysis.suggested_memory_type,
                project_id="memory-gateway",
                tags=analysis.tags,
                source_title="Project notes",
            ),
        )
        show("user confirms save to work_context")
        print(committed.memory.model_dump() if committed.memory else committed.proposal.model_dump())

        show("backend agent cannot read work_context without grant")
        try:
            vault_search(
                session,
                backend,
                VaultSearchRequest(
                    query="short-lived approval audit logs",
                    project_id="memory-gateway",
                    zones=[MemoryZone.WORK_CONTEXT],
                ),
            )
        except Exception as error:
            print(type(error).__name__, str(error))

        grant = request_access_grant(
            session,
            backend,
            GrantRequest(
                task_id="work-task-001",
                purpose="Use project requirements while implementing the backend.",
                allowed_zones=[MemoryZone.WORK_CONTEXT],
                project_id="memory-gateway",
            ),
        )
        approved = approve_access_grant(session, admin, grant.id)
        show("user approves short-lived grant")
        print({"grant_id": approved.id, "zones": approved.allowed_zones, "token_present": bool(approved.token)})

        result = vault_search(
            session,
            backend,
            VaultSearchRequest(
                query="short-lived approval audit logs",
                project_id="memory-gateway",
                zones=[MemoryZone.WORK_CONTEXT],
                grant_token=approved.token,
            ),
        )
        show("backend agent can now retrieve work_context")
        for memory in result.memories:
            print(f"- {memory.id} [{memory.memory_zone}] {memory.content}")

        payment_text = "For booking flights, payment must require user confirmation. Visa card 4111 1111 1111 1111 CVV 123"
        payment_analysis = analyze_capture(
            session,
            admin,
            CaptureAnalyzeRequest(content=payment_text, project_id="memory-gateway"),
        )
        payment_commit = commit_capture(
            session,
            admin,
            CaptureCommitRequest(
                content=payment_text,
                memory_zone=MemoryZone.PAYMENT_REFERENCE,
                memory_type=MemoryType.PROCEDURE,
                project_id="memory-gateway",
                tags=payment_analysis.tags,
            ),
        )
        show("payment reference is redacted before storage")
        stored = payment_commit.memory
        assert stored
        print(stored.content)


if __name__ == "__main__":
    main()
