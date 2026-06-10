from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from memory_gateway.db import Base
from memory_gateway.runtime.ingestion import approve_inbox_separate, ingest_memory
from memory_gateway.runtime.semantic import list_decision_examples
from memory_gateway.schemas import InboxApproveRequest, IngestRequest
from memory_gateway.security import authenticate_api_key
from memory_gateway.service import seed_demo_data
from memory_gateway.types import MemoryZone


def main() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, future=True)
    admin = authenticate_api_key("admin-demo-key")
    assert admin

    with Session() as session:
        seed_demo_data(session)
        first = ingest_memory(
            session,
            admin,
            IngestRequest(content="I prefer quiet window seats when booking flights.", auto_approve_public_low=False),
        )
        assert first.inbox_item
        approved_first = approve_inbox_separate(
            session,
            admin,
            first.inbox_item.id,
            InboxApproveRequest(memory_zone=MemoryZone.PERSONAL_CONTEXT),
        )

        from memory_gateway.runtime import semantic as semantic_module

        def fake_uncertain(profile, *, system, user):
            if "Decide whether" in system:
                return {
                    "relationship": "uncertain",
                    "confidence": 0.67,
                    "candidate_memory_id": approved_first.approved_memory_id,
                    "reason": "The memories both mention travel seats, but may apply to different transportation modes.",
                    "recommended_action": "ask_user",
                }
            return {
                "summary": "For trains, user prefers aisle seats near the exit.",
                "entities": ["user", "train", "seat preference"],
                "triggers": ["travel booking", "seat preference"],
                "facts": [
                    {"subject": "user", "predicate": "train_seat_preference", "object": "aisle near exit"}
                ],
                "confidence": 0.82,
            }

        original_call = semantic_module._call_chat_json
        semantic_module._call_chat_json = fake_uncertain
        try:
            second = ingest_memory(
                session,
                admin,
                IngestRequest(
                    content="For trains, I prefer aisle seats near the exit.",
                    model_profile_id="ollama-local",
                    auto_approve_public_low=False,
                ),
            )
        finally:
            semantic_module._call_chat_json = original_call
        assert second.inbox_item
        print("\n== user decision required ==")
        print(
            {
                "summary": second.inbox_item.semantic_summary,
                "relationship": second.inbox_item.llm_relationship,
                "needs_user_decision": second.inbox_item.needs_user_decision,
                "reason": second.inbox_item.llm_reason,
            }
        )

        approve_inbox_separate(
            session,
            admin,
            second.inbox_item.id,
            InboxApproveRequest(memory_zone=MemoryZone.PERSONAL_CONTEXT),
        )
        examples = list_decision_examples(
            session,
            admin,
            project_id=None,
            zone=MemoryZone.PERSONAL_CONTEXT,
        )
        print("\n== decision examples ==")
        for example in examples:
            print(f"- {example.user_decision}: {example.new_memory_summary}")


if __name__ == "__main__":
    main()
