from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from memory_gateway.db import Base
from memory_gateway.runtime.ingestion import approve_inbox_item, ingest_memory, list_inbox_items
from memory_gateway.schemas import InboxApproveRequest, IngestRequest
from memory_gateway.security import authenticate_api_key
from memory_gateway.service import seed_demo_data


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

        agent_capture = ingest_memory(
            session,
            backend,
            IngestRequest(
                content="Project decision: API clients should call /v1/context/compose before raw search.",
                project_id="memory-gateway",
            ),
        )
        show("agent-submitted memory")
        print(agent_capture.display.title if agent_capture.display else "sent to inbox")

        pending = list_inbox_items(session, admin)
        show("pending inbox")
        for item in pending:
            print(f"- {item.id}: {item.suggested_zone} / {item.suggested_memory_type}")

        approved = approve_inbox_item(session, admin, pending[0].id, InboxApproveRequest())
        show("approved")
        print(f"{approved.id} -> memory {approved.approved_memory_id}")


if __name__ == "__main__":
    main()
