from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from memory_gateway.db import Base
from memory_gateway.schemas import FeedbackRequest, SearchRequest
from memory_gateway.security import authenticate_api_key
from memory_gateway.service import (
    approve_learning_proposal,
    extract_lessons,
    search_memories,
    seed_demo_data,
    submit_feedback,
)
from memory_gateway.types import MemoryType


def print_memory_list(title: str, memories) -> None:
    print(f"\n== {title} ==")
    for memory in memories:
        print(f"- {memory.id} [{memory.memory_type}] score={memory.score}: {memory.content}")


def main() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, future=True)
    backend = authenticate_api_key("backend-demo-key")
    guest = authenticate_api_key("guest-demo-key")
    admin = authenticate_api_key("admin-demo-key")
    assert backend and guest and admin

    with Session() as session:
        seed_demo_data(session)

        query = "What database should this agent memory project use for vector retrieval?"
        backend_before = search_memories(
            session,
            backend,
            SearchRequest(
                query=query,
                project_id="memory-gateway",
                memory_types=[MemoryType.CONTEXT, MemoryType.PREFERENCE, MemoryType.LESSON],
                top_k=5,
            ),
        )
        guest_before = search_memories(
            session,
            guest,
            SearchRequest(
                query=query,
                project_id="memory-gateway",
                memory_types=[MemoryType.CONTEXT, MemoryType.PREFERENCE, MemoryType.LESSON],
                top_k=5,
            ),
        )
        print_memory_list("backend_agent can see project memories", backend_before.memories)
        print_memory_list("guest_agent only sees public memories", guest_before.memories)

        feedback = submit_feedback(
            session,
            backend,
            FeedbackRequest(
                task_id="demo-task-001",
                rating=1,
                correction=(
                    "Do not recommend SQLite for this project. It requires multi-user "
                    "collaboration and vector retrieval, so prefer Postgres with pgvector."
                ),
                expected_behavior="Recommend Postgres + pgvector for the memory gateway storage layer.",
                error_type="wrong_database_choice",
                project_id="memory-gateway",
            ),
        )
        proposals = extract_lessons(session, backend, feedback.id)
        proposal = proposals[0]
        print("\n== learned proposal is pending ==")
        print(f"- {proposal.id} [{proposal.status}]: {proposal.content}")

        pending_search = search_memories(
            session,
            backend,
            SearchRequest(
                query="avoid sqlite use postgres pgvector",
                project_id="memory-gateway",
                memory_types=[MemoryType.LESSON],
                top_k=5,
            ),
        )
        print_memory_list("pending lesson is not retrievable", pending_search.memories)

        approved = approve_learning_proposal(session, admin, proposal.id)
        print("\n== admin approved learned lesson ==")
        print(f"- approved_memory_id={approved.approved_memory_id}")

        backend_after = search_memories(
            session,
            backend,
            SearchRequest(
                query="avoid sqlite use postgres pgvector",
                project_id="memory-gateway",
                memory_types=[MemoryType.LESSON],
                top_k=5,
            ),
        )
        guest_after = search_memories(
            session,
            guest,
            SearchRequest(
                query="avoid sqlite use postgres pgvector",
                project_id="memory-gateway",
                memory_types=[MemoryType.LESSON],
                top_k=5,
            ),
        )
        print_memory_list("approved lesson influences backend_agent", backend_after.memories)
        print_memory_list("guest_agent cannot see project lesson", guest_after.memories)
        session.commit()


if __name__ == "__main__":
    main()
