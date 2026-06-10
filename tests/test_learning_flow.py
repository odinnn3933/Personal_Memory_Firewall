from __future__ import annotations

from memory_gateway.schemas import FeedbackRequest, SearchRequest
from memory_gateway.security import authenticate_api_key
from memory_gateway.service import (
    approve_learning_proposal,
    extract_lessons,
    search_memories,
    submit_feedback,
)
from memory_gateway.types import MemoryType, ProposalStatus


def test_feedback_extract_approval_flow(session):
    backend = authenticate_api_key("backend-demo-key")
    admin = authenticate_api_key("admin-demo-key")
    guest = authenticate_api_key("guest-demo-key")
    assert backend and admin and guest

    feedback = submit_feedback(
        session,
        backend,
        FeedbackRequest(
            task_id="task-1",
            rating=1,
            correction="Prefer Postgres with pgvector instead of SQLite for this project.",
            expected_behavior="Use Postgres + pgvector.",
            error_type="wrong_database_choice",
            project_id="memory-gateway",
        ),
    )
    proposals = extract_lessons(session, backend, feedback.id)
    assert proposals[0].status == ProposalStatus.PENDING

    pending_result = search_memories(
        session,
        backend,
        SearchRequest(
            query="prefer postgres pgvector",
            project_id="memory-gateway",
            memory_types=[MemoryType.LESSON],
        ),
    )
    assert pending_result.memories == []

    approved = approve_learning_proposal(session, admin, proposals[0].id)
    assert approved.status == ProposalStatus.APPROVED
    assert approved.approved_memory_id

    backend_result = search_memories(
        session,
        backend,
        SearchRequest(
            query="prefer postgres pgvector",
            project_id="memory-gateway",
            memory_types=[MemoryType.LESSON],
        ),
    )
    assert [memory.id for memory in backend_result.memories] == [approved.approved_memory_id]

    guest_result = search_memories(
        session,
        guest,
        SearchRequest(
            query="prefer postgres pgvector",
            project_id="memory-gateway",
            memory_types=[MemoryType.LESSON],
        ),
    )
    assert guest_result.memories == []


def test_extract_can_read_feedback_before_commit(session):
    backend = authenticate_api_key("backend-demo-key")
    assert backend

    feedback = submit_feedback(
        session,
        backend,
        FeedbackRequest(
            task_id="task-uncommitted",
            rating=1,
            correction="Prefer explicit approval before storing learned lessons.",
            error_type="memory_pollution_risk",
            project_id="memory-gateway",
        ),
    )

    proposals = extract_lessons(session, backend, feedback.id)

    assert proposals[0].status == ProposalStatus.PENDING
    assert "Prefer explicit approval" in proposals[0].content


def test_approve_can_read_extracted_proposal_before_commit(session):
    backend = authenticate_api_key("backend-demo-key")
    admin = authenticate_api_key("admin-demo-key")
    assert backend and admin

    feedback = submit_feedback(
        session,
        backend,
        FeedbackRequest(
            task_id="task-approve-uncommitted",
            rating=1,
            correction="Avoid letting agents directly mutate approved memories.",
            error_type="memory_pollution_risk",
            project_id="memory-gateway",
        ),
    )
    proposal = extract_lessons(session, backend, feedback.id)[0]

    approved = approve_learning_proposal(session, admin, proposal.id)

    assert approved.status == ProposalStatus.APPROVED
    assert approved.approved_memory_id
