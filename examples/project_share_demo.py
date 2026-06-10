from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from memory_gateway.db import Base
from memory_gateway.runtime.context import compose_context
from memory_gateway.runtime.ingestion import approve_inbox_item, ingest_memory
from memory_gateway.runtime.share import compose_share_pack, create_share_pack, revoke_share_pack
from memory_gateway.schemas import (
    ContextComposeRequest,
    InboxApproveRequest,
    IngestRequest,
    SharePackComposeRequest,
    SharePackCreateRequest,
)
from memory_gateway.security import authenticate_api_key
from memory_gateway.service import InvalidState, seed_demo_data
from memory_gateway.types import MemoryZone


def _approve(session, admin, content: str, zone: MemoryZone, project_id: str | None = None) -> str:
    captured = ingest_memory(
        session,
        admin,
        IngestRequest(content=content, project_id=project_id, auto_approve_public_low=False),
    )
    assert captured.inbox_item
    approved = approve_inbox_item(
        session,
        admin,
        captured.inbox_item.id,
        InboxApproveRequest(memory_zone=zone, project_id=project_id),
    )
    assert approved.approved_memory_id
    return approved.approved_memory_id


def main() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, future=True)
    admin = authenticate_api_key("admin-demo-key")
    guest = authenticate_api_key("guest-demo-key")
    assert admin and guest

    with Session() as session:
        seed_demo_data(session)
        _approve(
            session,
            admin,
            "Project requirement: memory-gateway must use FastAPI, Postgres, and pgvector.",
            MemoryZone.WORK_CONTEXT,
            "memory-gateway",
        )
        _approve(
            session,
            admin,
            "Bob is my colleague on the memory-gateway backend team.",
            MemoryZone.WORK_CONTEXT,
            "memory-gateway",
        )
        _approve(
            session,
            admin,
            "Alice is my close friend and this personal relationship is not for project onboarding.",
            MemoryZone.PERSONAL_CONTEXT,
            None,
        )
        _approve(
            session,
            admin,
            "For booking, payment card 4242 4242 4242 4242 requires confirmation.",
            MemoryZone.PAYMENT_REFERENCE,
            "memory-gateway",
        )

        print("\n== guest without grant cannot read work_context ==")
        denied = compose_context(
            session,
            guest,
            ContextComposeRequest(
                task="Onboard me to the memory-gateway project.",
                project_id="memory-gateway",
                zones=[MemoryZone.WORK_CONTEXT],
                include_graph=False,
            ),
        )
        assert "FastAPI, Postgres, and pgvector" not in denied.prompt_context
        assert denied.denied_zones
        print(denied.prompt_context)

        print("\n== admin creates project share pack ==")
        created = create_share_pack(
            session,
            admin,
            SharePackCreateRequest(
                project_id="memory-gateway",
                name="Memory Gateway onboarding pack",
                recipient_label="new collaborator",
                task="Onboard a collaborator to memory-gateway architecture and team context.",
                max_uses=3,
            ),
        )
        assert created.share_pack.token
        print(f"share_pack_id: {created.share_pack.id}")
        print(f"token returned once: {created.share_pack.token[:12]}...")

        print("\n== guest uses share token for prompt-ready onboarding context ==")
        shared = compose_share_pack(
            session,
            guest,
            created.share_pack.id,
            SharePackComposeRequest(
                share_token=created.share_pack.token,
                task="What should I know before contributing to memory-gateway?",
            ),
        )
        print(shared.prompt_context)
        assert "FastAPI" in shared.prompt_context
        assert "Postgres" in shared.prompt_context
        assert "pgvector" in shared.prompt_context
        assert "Bob" in shared.prompt_context
        assert "Alice" not in shared.prompt_context
        assert "4242" not in shared.prompt_context
        assert "Project Memory Share Pack" in shared.prompt_context

        print("\n== revoke share pack and prove token is dead ==")
        revoke_share_pack(session, admin, created.share_pack.id)
        try:
            compose_share_pack(
                session,
                guest,
                created.share_pack.id,
                SharePackComposeRequest(
                    share_token=created.share_pack.token,
                    task="Try to reuse revoked share token.",
                ),
            )
        except InvalidState as error:
            print(f"revoked compose blocked: {error}")
        else:
            raise AssertionError("revoked share pack should not compose")

        print("\nPROJECT SHARE DEMO PASS")


if __name__ == "__main__":
    main()
