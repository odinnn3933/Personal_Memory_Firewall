from __future__ import annotations

from memory_gateway.runtime.context import compose_context, request_context
from memory_gateway.runtime.ingestion import (
    approve_inbox_item,
    ingest_memory,
    list_inbox_items,
)
from memory_gateway.schemas import (
    ContextComposeRequest,
    ContextRequestRequest,
    GrantRequest,
    InboxApproveRequest,
    IngestRequest,
)
from memory_gateway.security import authenticate_api_key
from memory_gateway.service import approve_access_grant, request_access_grant
from memory_gateway.types import InboxProposalKind, InboxStatus, MemoryZone


def test_ingest_public_auto_approve_and_work_goes_to_inbox(session):
    admin = authenticate_api_key("admin-demo-key")
    assert admin

    public = ingest_memory(
        session,
        admin,
        IngestRequest(content="I prefer concise technical summaries."),
    )
    assert public.auto_approved is True
    assert public.memory
    assert public.memory.memory_zone == MemoryZone.PUBLIC_PROFILE

    work = ingest_memory(
        session,
        admin,
        IngestRequest(
            content="Project requirement: memory-gateway API changes must preserve compatibility.",
            project_id="memory-gateway",
        ),
    )
    assert work.auto_approved is False
    assert work.inbox_item
    assert work.inbox_item.status == InboxStatus.PENDING_REVIEW

    pending = list_inbox_items(session, admin)
    assert any(item.id == work.inbox_item.id for item in pending)

    approved = approve_inbox_item(
        session,
        admin,
        work.inbox_item.id,
        InboxApproveRequest(),
    )
    assert approved.status == InboxStatus.APPROVED
    assert approved.approved_memory_id


def test_agent_ingest_never_directly_approves_memory(session):
    backend = authenticate_api_key("backend-demo-key")
    assert backend

    result = ingest_memory(
        session,
        backend,
        IngestRequest(content="I prefer short answers.", auto_approve_public_low=True),
    )

    assert result.auto_approved is False
    assert result.memory is None
    assert result.inbox_item
    assert result.inbox_item.status == InboxStatus.PENDING_REVIEW


def test_context_compose_denies_without_grant_and_allows_with_grant(session):
    admin = authenticate_api_key("admin-demo-key")
    backend = authenticate_api_key("backend-demo-key")
    assert admin and backend

    no_grant = compose_context(
        session,
        backend,
        ContextComposeRequest(
            task="Which database should the memory-gateway project use?",
            project_id="memory-gateway",
            zones=[MemoryZone.PUBLIC_PROFILE, MemoryZone.WORK_CONTEXT],
            include_graph=False,
        ),
    )
    assert "pgvector" not in no_grant.prompt_context.lower()
    assert [zone.zone for zone in no_grant.denied_zones] == [MemoryZone.WORK_CONTEXT]

    grant = request_access_grant(
        session,
        backend,
            GrantRequest(
                task_id="ctx-test",
                purpose="Need project database preference.",
                allowed_zones=[MemoryZone.WORK_CONTEXT],
                project_id="memory-gateway",
            ),
    )
    approved = approve_access_grant(session, admin, grant.id)
    assert approved.token

    with_grant = compose_context(
        session,
        backend,
        ContextComposeRequest(
            task="Which database should the memory-gateway project use?",
            project_id="memory-gateway",
            zones=[MemoryZone.PUBLIC_PROFILE, MemoryZone.WORK_CONTEXT],
            grant_token=approved.token,
            include_graph=False,
        ),
    )
    assert "postgres" in with_grant.prompt_context.lower()
    assert "pgvector" in with_grant.prompt_context.lower()
    assert with_grant.denied_zones == []
    assert with_grant.source_cards


def test_payment_reference_context_never_returns_raw_card_number(session):
    admin = authenticate_api_key("admin-demo-key")
    backend = authenticate_api_key("backend-demo-key")
    assert admin and backend

    ingest = ingest_memory(
        session,
        admin,
        IngestRequest(
            content="For booking, payment card 4242 4242 4242 4242 requires confirmation.",
            project_id="memory-gateway",
        ),
    )
    assert ingest.inbox_item
    approved_item = approve_inbox_item(
        session,
        admin,
        ingest.inbox_item.id,
        InboxApproveRequest(),
    )
    assert approved_item.approved_memory_id

    grant = request_access_grant(
        session,
        backend,
            GrantRequest(
                task_id="payment-test",
                purpose="Booking flow needs payment confirmation rule.",
                allowed_zones=[MemoryZone.PAYMENT_REFERENCE],
                project_id="memory-gateway",
            ),
    )
    approved = approve_access_grant(session, admin, grant.id)
    assert approved.token

    context = compose_context(
        session,
        backend,
        ContextComposeRequest(
            task="Book travel and prepare payment confirmation.",
            project_id="memory-gateway",
            zones=[MemoryZone.PAYMENT_REFERENCE],
            grant_token=approved.token,
            include_graph=False,
        ),
    )

    assert "4242 4242 4242 4242" not in context.prompt_context
    assert "[REDACTED_CARD]" in context.prompt_context


def test_context_compose_includes_sql_fact_cards_without_neo4j(session):
    admin = authenticate_api_key("admin-demo-key")
    backend = authenticate_api_key("backend-demo-key")
    assert admin and backend

    ingest = ingest_memory(
        session,
        admin,
        IngestRequest(
            content="Project requirement: long-term memory storage must use Postgres and pgvector.",
            project_id="memory-gateway",
        ),
    )
    assert ingest.inbox_item
    approve_inbox_item(session, admin, ingest.inbox_item.id, InboxApproveRequest())

    grant = request_access_grant(
        session,
        backend,
            GrantRequest(
                task_id="facts-test",
                purpose="Need storage requirements.",
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
            task="Choose Postgres pgvector storage.",
            project_id="memory-gateway",
            zones=[MemoryZone.WORK_CONTEXT],
            grant_token=approved.token,
            include_graph=False,
        ),
    )

    assert any("Postgres" in card.title or "pgvector" in card.title for card in context.fact_cards)
    assert "Structured Facts" in context.prompt_context


def test_project_context_does_not_mix_between_projects(session):
    admin = authenticate_api_key("admin-demo-key")
    backend = authenticate_api_key("backend-demo-key")
    assert admin and backend

    alpha = ingest_memory(
        session,
        admin,
        IngestRequest(
            content="Project requirement: Alpha must use Postgres for storage.",
            project_id="alpha-project",
        ),
    )
    beta = ingest_memory(
        session,
        admin,
        IngestRequest(
            content="Project requirement: Beta must use SQLite for local prototypes.",
            project_id="beta-project",
        ),
    )
    assert alpha.inbox_item and beta.inbox_item
    approve_inbox_item(session, admin, alpha.inbox_item.id, InboxApproveRequest())
    approve_inbox_item(session, admin, beta.inbox_item.id, InboxApproveRequest())

    grant = request_access_grant(
        session,
        backend,
        GrantRequest(
            task_id="project-isolation",
            purpose="Need alpha project storage context.",
            allowed_zones=[MemoryZone.WORK_CONTEXT],
            project_id="alpha-project",
        ),
    )
    approved = approve_access_grant(session, admin, grant.id)
    assert approved.token

    context = compose_context(
        session,
        backend,
        ContextComposeRequest(
            task="Which storage should Alpha use?",
            project_id="alpha-project",
            zones=[MemoryZone.WORK_CONTEXT],
            grant_token=approved.token,
            include_graph=False,
        ),
    )

    assert "postgres" in context.prompt_context.lower()
    assert "sqlite" not in context.prompt_context.lower()

    wrong_project = compose_context(
        session,
        backend,
        ContextComposeRequest(
            task="Which storage should Beta use?",
            project_id="beta-project",
            zones=[MemoryZone.WORK_CONTEXT],
            grant_token=approved.token,
            include_graph=False,
        ),
    )
    assert "sqlite" not in wrong_project.prompt_context.lower()
    assert wrong_project.denied_zones[0].reason == "Grant is scoped to a different project."

    admin_grant = request_access_grant(
        session,
        admin,
        GrantRequest(
            task_id="admin-alpha-isolation",
            purpose="Verify admin project-scoped compose.",
            allowed_zones=[MemoryZone.WORK_CONTEXT],
            project_id="alpha-project",
        ),
    )
    admin_approved = approve_access_grant(session, admin, admin_grant.id)
    assert admin_approved.token

    admin_alpha = compose_context(
        session,
        admin,
        ContextComposeRequest(
            task="Which storage should Alpha use?",
            project_id="alpha-project",
            zones=[MemoryZone.WORK_CONTEXT],
            grant_token=admin_approved.token,
            include_graph=False,
        ),
    )
    assert "postgres" in admin_alpha.prompt_context.lower()
    assert "sqlite" not in admin_alpha.prompt_context.lower()


def test_inbox_update_supersedes_old_memory(session):
    admin = authenticate_api_key("admin-demo-key")
    backend = authenticate_api_key("backend-demo-key")
    assert admin and backend

    first = ingest_memory(
        session,
        admin,
        IngestRequest(
            content="I live 15 km from the office.",
            project_id=None,
            auto_approve_public_low=False,
        ),
    )
    assert first.inbox_item
    first_approved = approve_inbox_item(
        session,
        admin,
        first.inbox_item.id,
        InboxApproveRequest(memory_zone=MemoryZone.PERSONAL_CONTEXT),
    )
    old_memory_id = first_approved.approved_memory_id
    assert old_memory_id

    update = ingest_memory(
        session,
        admin,
        IngestRequest(
            content="I moved recently. I now live 3 km from the office.",
            project_id=None,
            auto_approve_public_low=False,
        ),
    )
    assert update.inbox_item
    assert update.inbox_item.proposal_kind == InboxProposalKind.UPDATE
    assert old_memory_id in update.inbox_item.conflict_memory_ids

    approved_update = approve_inbox_item(
        session,
        admin,
        update.inbox_item.id,
        InboxApproveRequest(memory_zone=MemoryZone.PERSONAL_CONTEXT),
    )
    new_memory_id = approved_update.approved_memory_id
    assert new_memory_id

    grant = request_access_grant(
        session,
        backend,
        GrantRequest(
            task_id="move-update",
            purpose="Need current commute distance.",
            allowed_zones=[MemoryZone.PERSONAL_CONTEXT],
        ),
    )
    approved = approve_access_grant(session, admin, grant.id)
    assert approved.token
    context = compose_context(
        session,
        backend,
        ContextComposeRequest(
            task="How far do I live from the office?",
            zones=[MemoryZone.PERSONAL_CONTEXT],
            grant_token=approved.token,
            include_graph=False,
        ),
    )

    assert "3 km" in context.prompt_context
    assert "15 km" not in context.prompt_context


def test_context_request_returns_pending_grant_for_private_zones(session):
    backend = authenticate_api_key("backend-demo-key")
    assert backend

    response = request_context(
        session,
        backend,
        ContextRequestRequest(
            task="Use project work memory to choose the storage stack.",
            task_id="request-context",
            project_id="memory-gateway",
            zones=[MemoryZone.PUBLIC_PROFILE, MemoryZone.WORK_CONTEXT],
        ),
    )

    assert response.status == "pending_grant"
    assert response.grant
    assert response.grant.project_id == "memory-gateway"
    assert response.denied_zones[0].zone == MemoryZone.WORK_CONTEXT
