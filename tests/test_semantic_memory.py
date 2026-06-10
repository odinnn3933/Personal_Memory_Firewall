from __future__ import annotations

from memory_gateway.runtime.context import compose_context
from memory_gateway.runtime.ingestion import (
    approve_inbox_separate,
    approve_inbox_update,
    ingest_memory,
)
from memory_gateway.runtime.semantic import (
    generate_memory_summary,
    list_decision_examples,
    retrieve_summary_candidates,
)
from memory_gateway.schemas import ContextComposeRequest, InboxApproveRequest, IngestRequest
from memory_gateway.security import authenticate_api_key
from memory_gateway.service import approve_access_grant, request_access_grant
from memory_gateway.schemas import GrantRequest
from memory_gateway.types import MemoryZone


def test_semantic_summary_is_generated_and_saved(session):
    admin = authenticate_api_key("admin-demo-key")
    assert admin

    semantic = generate_memory_summary(
        session,
        admin,
        "I prefer concise technical explanations.",
        None,
        MemoryZone.PUBLIC_PROFILE,
    )
    assert semantic.summary
    assert semantic.used_redacted_preview

    result = ingest_memory(
        session,
        admin,
        IngestRequest(content="I prefer concise technical explanations."),
    )
    assert result.memory
    assert result.memory.semantic_summary
    assert result.memory.semantic_entities


def test_summary_candidates_respect_project_scope(session):
    admin = authenticate_api_key("admin-demo-key")
    assert admin

    semantic = generate_memory_summary(
        session,
        admin,
        "Which database should memory-gateway use for vector retrieval?",
        "travel-planner",
        MemoryZone.WORK_CONTEXT,
    )
    candidates = retrieve_summary_candidates(
        session,
        admin,
        semantic,
        "travel-planner",
        MemoryZone.WORK_CONTEXT,
        top_k=10,
    )
    assert all(candidate.memory_id != "mem_project_database" for candidate in candidates)


def test_llm_judge_update_records_decision_example(session, monkeypatch):
    admin = authenticate_api_key("admin-demo-key")
    assert admin

    old = ingest_memory(
        session,
        admin,
        IngestRequest(content="I live 15 km from the office.", auto_approve_public_low=False),
    )
    assert old.inbox_item
    approved_old = approve_inbox_separate(
        session,
        admin,
        old.inbox_item.id,
        InboxApproveRequest(memory_zone=MemoryZone.PERSONAL_CONTEXT),
    )

    from memory_gateway.runtime import semantic as semantic_module

    def fake_call_chat_json(profile, *, system, user):
        if "Decide whether" in system:
            return {
                "relationship": "update",
                "confidence": 0.91,
                "candidate_memory_id": approved_old.approved_memory_id,
                "reason": "The new memory replaces the older commute distance.",
                "recommended_action": "approve_update",
            }
        return {
            "summary": "User currently lives 3 km from the office after moving recently.",
            "entities": ["user", "office", "commute distance"],
            "triggers": ["commute", "office distance"],
            "facts": [
                {
                    "subject": "user",
                    "predicate": "current_commute_distance_to_office",
                    "object": "3 km",
                }
            ],
            "confidence": 0.9,
        }

    monkeypatch.setattr(semantic_module, "_call_chat_json", fake_call_chat_json)

    update = ingest_memory(
        session,
        admin,
        IngestRequest(
            content="I moved recently. I now live 3 km from the office.",
            model_profile_id="ollama-local",
            auto_approve_public_low=False,
        ),
    )
    assert update.inbox_item
    assert update.inbox_item.proposal_kind.value == "update"
    assert update.inbox_item.llm_relationship == "update"
    assert update.inbox_item.needs_user_decision is True

    approved_update = approve_inbox_update(
        session,
        admin,
        update.inbox_item.id,
        InboxApproveRequest(
            memory_zone=MemoryZone.PERSONAL_CONTEXT,
            supersede_memory_id=approved_old.approved_memory_id,
        ),
    )
    examples = list_decision_examples(
        session,
        admin,
        project_id=None,
        zone=MemoryZone.PERSONAL_CONTEXT,
    )
    assert approved_update.approved_memory_id
    assert any(example.user_decision == "approve_update" for example in examples)


def test_summary_first_context_uses_new_memory_after_update(session):
    admin = authenticate_api_key("admin-demo-key")
    backend = authenticate_api_key("backend-demo-key")
    assert admin and backend

    old = ingest_memory(
        session,
        admin,
        IngestRequest(content="I live 15 km from the office.", auto_approve_public_low=False),
    )
    assert old.inbox_item
    approved_old = approve_inbox_separate(
        session,
        admin,
        old.inbox_item.id,
        InboxApproveRequest(memory_zone=MemoryZone.PERSONAL_CONTEXT),
    )
    new = ingest_memory(
        session,
        admin,
        IngestRequest(content="I moved recently. I now live 3 km from the office.", auto_approve_public_low=False),
    )
    assert new.inbox_item
    approve_inbox_update(
        session,
        admin,
        new.inbox_item.id,
        InboxApproveRequest(
            memory_zone=MemoryZone.PERSONAL_CONTEXT,
            supersede_memory_id=approved_old.approved_memory_id,
        ),
    )
    grant = request_access_grant(
        session,
        backend,
        GrantRequest(
            task_id="semantic-context-test",
            purpose="Need personal context for commute answer.",
            allowed_zones=[MemoryZone.PERSONAL_CONTEXT],
        ),
    )
    approved_grant = approve_access_grant(session, admin, grant.id)
    assert approved_grant.token

    context = compose_context(
        session,
        backend,
        ContextComposeRequest(
            task="How far does the user currently live from the office?",
            zones=[MemoryZone.PERSONAL_CONTEXT],
            grant_token=approved_grant.token,
            include_graph=False,
            retrieval_mode="summary_first",
        ),
    )
    assert "3 km" in context.prompt_context
    assert "15 km" not in context.prompt_context
    assert context.matched_summaries
