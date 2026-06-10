from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import (
    AccessGrantRecord,
    AgentRecord,
    AuditEventRecord,
    CaptureEventRecord,
    FeedbackEventRecord,
    InteractionEventRecord,
    LearnedMemoryProposalRecord,
    MemoryRecord,
    MemoryVersionRecord,
    MemoryWriteProposalRecord,
    ModelProfileRecord,
    ProjectRecord,
    utcnow,
)
from .embedding import cosine_similarity, embed_text
from .graph import get_graph_client
from .policy import (
    ZONE_METADATA,
    can_read_memory,
    classify_sensitivity,
    policy_reason,
    requires_approval,
    max_sensitivity,
    zone_confirmation_level,
    zone_default_sensitivity,
    zone_default_ttl_minutes,
    zone_requires_grant,
)
from .schemas import (
    AuditOut,
    CaptureAnalyzeRequest,
    CaptureAnalyzeResponse,
    CaptureCommitRequest,
    CaptureCommitResponse,
    DisplayOut,
    FeedbackRequest,
    GraphExplainResponse,
    GraphHealthResponse,
    GraphRebuildResponse,
    GraphSearchRequest,
    GraphSearchResponse,
    GraphCardOut,
    GrantOut,
    GrantRequest,
    InteractionRequest,
    MemoryCardOut,
    MemoryOut,
    MemoryProposalRequest,
    ModelProcessingClassifyRequest,
    ModelProcessingLessonRequest,
    ModelProcessingResponse,
    ModelProcessingSummarizeRequest,
    ModelProfileCreateRequest,
    ModelProfileOut,
    ModelProfileTestRequest,
    ProposalOut,
    SearchRequest,
    SearchDisplayOut,
    VaultSearchRequest,
    ZoneOut,
)
from .security import AgentIdentity, demo_identities, hash_api_key
from .types import (
    AuditAction,
    CaptureSource,
    ContentKind,
    GrantStatus,
    MemoryType,
    MemoryZone,
    ModelProvider,
    ModelTask,
    ProposalStatus,
    Sensitivity,
    Visibility,
)


class PermissionDenied(Exception):
    pass


class NotFound(Exception):
    pass


class InvalidState(Exception):
    pass


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
TOKEN_RE = re.compile(r"(?i)\b(?:api[_ -]?key|token|secret|password)\s*[:=]\s*['\"]?[^,\s'\"]+")
CVV_RE = re.compile(r"(?i)\bcvv\s*[:=]?\s*\d{3,4}\b")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
ID_CARD_CN_RE = re.compile(r"\b\d{17}[\dXx]\b")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def as_utc_naive(value):
    if value.tzinfo is None:
        return value
    return value.replace(tzinfo=None)


def now_for_db_compare():
    return as_utc_naive(utcnow())


def audit(
    session: Session,
    agent: AgentIdentity,
    action: AuditAction,
    resource_type: str,
    resource_id: str | None = None,
    details: dict | None = None,
) -> str:
    audit_id = new_id("aud")
    session.add(
        AuditEventRecord(
            id=audit_id,
            tenant_id=agent.tenant_id,
            agent_id=agent.agent_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
        )
    )
    session.flush()
    return audit_id


def record_to_memory_out(record: MemoryRecord, score: float | None = None) -> MemoryOut:
    return MemoryOut(
        id=record.id,
        project_id=record.project_id,
        visibility=Visibility(record.visibility),
        memory_type=MemoryType(record.memory_type),
        memory_zone=MemoryZone(record.memory_zone) if record.memory_zone else None,
        content_kind=ContentKind(record.content_kind or ContentKind.TEXT.value),
        content=record.content,
        tags=record.tags or [],
        sensitivity=Sensitivity(record.sensitivity),
        source=record.source,
        source_url=record.source_url,
        source_title=record.source_title,
        asset_path=record.asset_path,
        redacted=bool(record.redacted),
        status=record.status,
        superseded_by_id=record.superseded_by_id,
        score=score,
        created_at=record.created_at,
    )


def proposal_to_out(
    record: MemoryWriteProposalRecord | LearnedMemoryProposalRecord,
) -> ProposalOut:
    confidence = getattr(record, "confidence", None)
    return ProposalOut(
        id=record.id,
        status=ProposalStatus(record.status),
        memory_type=MemoryType(record.memory_type),
        visibility=Visibility(record.visibility),
        sensitivity=Sensitivity(record.sensitivity),
        content=record.content,
        project_id=record.project_id,
        approved_memory_id=record.approved_memory_id,
        confidence=confidence,
    )


def model_profile_to_out(record: ModelProfileRecord) -> ModelProfileOut:
    return ModelProfileOut(
        id=record.id,
        name=record.name,
        provider=ModelProvider(record.provider),
        model=record.model,
        endpoint_url=record.endpoint_url,
        api_key_env=record.api_key_env,
        has_api_key=bool(record.api_key_secret or (record.api_key_env and os.getenv(record.api_key_env))),
        allowed_tasks=[ModelTask(task) for task in record.allowed_tasks or []],
        allowed_zones=[MemoryZone(zone) for zone in record.allowed_zones or []],
        local_only=bool(record.local_only),
        auto_apply_low_sensitivity=bool(record.auto_apply_low_sensitivity),
        is_active=bool(record.is_active),
        created_at=record.created_at,
    )


def seed_demo_data(session: Session) -> None:
    identities = demo_identities()
    for api_key, identity in identities.items():
        if not session.get(AgentRecord, identity.agent_id):
            session.add(
                AgentRecord(
                    agent_id=identity.agent_id,
                    tenant_id=identity.tenant_id,
                    api_key_hash=hash_api_key(api_key),
                    roles=[role.value for role in identity.roles],
                    allowed_projects=list(identity.allowed_projects),
                )
            )

    from .runtime.projects import ensure_seed_project

    ensure_seed_project(
        session,
        tenant_id="demo",
        project_id="memory-gateway",
        name="Memory Gateway",
        description="Default demo project for the memory firewall runtime.",
    )
    ensure_seed_project(
        session,
        tenant_id="demo",
        project_id="travel-planner",
        name="Travel Planner",
        description="Separate demo project used to prove project memory isolation.",
    )

    default_profiles = [
        ModelProfileRecord(
            id="rule-only-default",
            tenant_id="demo",
            name="Rule-only default",
            provider=ModelProvider.RULE_ONLY.value,
            model="rules",
            endpoint_url=None,
            api_key_env=None,
            allowed_tasks=[task.value for task in ModelTask],
            allowed_zones=[zone.value for zone in MemoryZone],
            local_only=True,
            auto_apply_low_sensitivity=True,
            is_active=True,
        ),
        ModelProfileRecord(
            id="ollama-local",
            tenant_id="demo",
            name="Ollama local",
            provider=ModelProvider.OLLAMA.value,
            model="llama3.1",
            endpoint_url="http://127.0.0.1:11434",
            api_key_env=None,
            allowed_tasks=[task.value for task in ModelTask],
            allowed_zones=[zone.value for zone in MemoryZone],
            local_only=True,
            auto_apply_low_sensitivity=True,
            is_active=False,
        ),
        ModelProfileRecord(
            id="openai-compatible-redacted-only",
            tenant_id="demo",
            name="OpenAI-compatible redacted only",
            provider=ModelProvider.OPENAI_COMPATIBLE.value,
            model="gpt-4o-mini",
            endpoint_url="https://api.openai.com",
            api_key_env="OPENAI_API_KEY",
            allowed_tasks=[task.value for task in ModelTask],
            allowed_zones=[
                MemoryZone.PUBLIC_PROFILE.value,
                MemoryZone.WORK_CONTEXT.value,
                MemoryZone.PERSONAL_CONTEXT.value,
            ],
            local_only=False,
            auto_apply_low_sensitivity=True,
            is_active=False,
        ),
    ]
    for profile in default_profiles:
        existing_profile = session.get(ModelProfileRecord, profile.id)
        if not existing_profile:
            session.add(profile)
        else:
            existing_profile.allowed_tasks = [task.value for task in ModelTask]
            if existing_profile.id == "rule-only-default":
                existing_profile.allowed_zones = [zone.value for zone in MemoryZone]

    seeds = [
        {
            "id": "mem_public_intro",
            "project_id": None,
            "visibility": Visibility.PUBLIC,
            "memory_type": MemoryType.CONTEXT,
            "memory_zone": MemoryZone.PUBLIC_PROFILE,
            "content": "Memory Gateway is an auditable long-term memory control plane for agents.",
            "tags": ["intro"],
            "source": "seed",
        },
        {
            "id": "mem_project_database",
            "project_id": "memory-gateway",
            "visibility": Visibility.PROJECT,
            "memory_type": MemoryType.PREFERENCE,
            "memory_zone": MemoryZone.WORK_CONTEXT,
            "content": (
                "For the memory-gateway project, prefer Postgres with pgvector for "
                "multi-user collaboration and vector retrieval."
            ),
            "tags": ["database", "pgvector"],
            "source": "seed",
        },
        {
            "id": "mem_project_review_procedure",
            "project_id": "memory-gateway",
            "visibility": Visibility.PROJECT,
            "memory_type": MemoryType.PROCEDURE,
            "memory_zone": MemoryZone.WORK_CONTEXT,
            "content": (
                "Before approving learned lessons, check source feedback, sensitivity, "
                "and whether the rule is project-scoped."
            ),
            "tags": ["approval", "procedure"],
            "source": "seed",
        },
        {
            "id": "mem_private_salary",
            "project_id": "memory-gateway",
            "visibility": Visibility.PRIVATE,
            "allowed_agent_ids": ["admin_agent"],
            "memory_type": MemoryType.CONTEXT,
            "memory_zone": MemoryZone.SENSITIVE_VAULT,
            "content": "Confidential salary discussion notes must never be exposed to non-admin agents.",
            "tags": ["private"],
            "source": "seed",
        },
    ]
    for item in seeds:
        if session.get(MemoryRecord, item["id"]):
            continue
        content = item["content"]
        sensitivity = classify_sensitivity(content)
        session.add(
            MemoryRecord(
                id=item["id"],
                tenant_id="demo",
                project_id=item.get("project_id"),
                visibility=item["visibility"].value,
                allowed_agent_ids=item.get("allowed_agent_ids", []),
                denied_agent_ids=[],
                memory_type=item["memory_type"].value,
                memory_zone=item["memory_zone"].value,
                content_kind=ContentKind.TEXT.value,
                capture_source=CaptureSource.CLIPBOARD.value,
                content=content,
                tags=item["tags"],
                sensitivity=sensitivity.value,
                source=item["source"],
                embedding=embed_text(content),
                status="approved",
                created_by_agent_id="seed",
            )
        )
    session.flush()
    try:
        from .runtime.facts import upsert_facts_for_memory
        from .runtime.semantic import apply_semantic_summary_to_memory, generate_memory_summary

        admin_identity = next(identity for identity in identities.values() if identity.is_admin)
        seed_records = session.scalars(
            select(MemoryRecord).where(MemoryRecord.tenant_id == admin_identity.tenant_id)
        ).all()
        for memory in seed_records:
            if not memory.semantic_summary:
                zone = MemoryZone(memory.memory_zone) if memory.memory_zone else MemoryZone.PUBLIC_PROFILE
                semantic = generate_memory_summary(
                    session,
                    admin_identity,
                    memory.content,
                    memory.project_id,
                    zone,
                )
                apply_semantic_summary_to_memory(memory, semantic)
            upsert_facts_for_memory(session, admin_identity, memory)
    except Exception:
        # Seeding must stay lightweight; fact extraction can be rebuilt later.
        pass


@dataclass(frozen=True)
class SearchResult:
    memories: list[MemoryOut]
    candidate_count_after_acl: int
    audit_id: str
    display: SearchDisplayOut


def _zone_label(zone: MemoryZone | None) -> str:
    if not zone:
        return "Unzoned"
    return str(ZONE_METADATA[zone]["label"])


def _capture_display(response: CaptureAnalyzeResponse) -> DisplayOut:
    zone = response.suggested_zone
    action = "Save directly" if not response.should_require_confirmation else "Review before saving"
    reasons = [
        f"Suggested zone: {_zone_label(zone)}",
        f"Memory type: {response.suggested_memory_type.value}",
        f"Classifier source: {response.final_suggestion_source}",
    ]
    if response.sent_to_model:
        reasons.append("A redacted preview was sent to the selected model profile.")
    else:
        reasons.append("No remote model call was used for this capture.")
    return DisplayOut(
        title=f"Save as {_zone_label(zone)}",
        subtitle=f"{response.sensitivity.value.capitalize()} sensitivity {response.suggested_memory_type.value}",
        badges=[zone.value, response.sensitivity.value, response.suggested_memory_type.value],
        reasons=reasons,
        warnings=response.risk_warnings,
        primary_action=action,
        safe_preview=response.redacted_preview,
    )


def _memory_card(memory: MemoryOut, why_visible: str) -> MemoryCardOut:
    preview = memory.content[:240]
    return MemoryCardOut(
        id=memory.id,
        title=f"{_zone_label(memory.memory_zone)} / {memory.memory_type.value}",
        subtitle=memory.source,
        zone=memory.memory_zone,
        memory_type=memory.memory_type,
        sensitivity=memory.sensitivity,
        source=memory.source,
        why_visible=why_visible,
        preview=preview,
        score=memory.score,
    )


def _search_display(memories: list[MemoryOut], query: str, reason: str) -> SearchDisplayOut:
    if not memories:
        return SearchDisplayOut(summary=f"No readable memories matched {query!r}.", cards=[])
    return SearchDisplayOut(
        summary=f"Found {len(memories)} readable memories for {query!r}.",
        cards=[_memory_card(memory, reason) for memory in memories],
    )


def _model_display(response: ModelProcessingResponse) -> DisplayOut:
    warnings = list(response.risk_warnings)
    if response.fallback_used:
        warnings.append("Model processing failed and rules were used instead.")
    reasons = [
        f"Provider: {response.provider.value}",
        f"Task: {response.task.value}",
        "Only a redacted preview was available to model processing.",
    ]
    if response.sent_to_model:
        reasons.append("The selected model profile was called.")
    else:
        reasons.append("No remote model call was made.")
    return DisplayOut(
        title="Model processing result",
        subtitle="Remote model used" if response.sent_to_model else "Rule-only or policy-blocked",
        badges=[response.provider.value, response.task.value],
        reasons=reasons,
        warnings=warnings,
        primary_action="Use suggestion" if not response.fallback_used else "Review fallback",
        safe_preview=response.redacted_preview,
    )


def search_memories(session: Session, agent: AgentIdentity, request: SearchRequest) -> SearchResult:
    query = select(MemoryRecord).where(
        MemoryRecord.tenant_id == agent.tenant_id,
        MemoryRecord.deleted_at.is_(None),
        MemoryRecord.status == ProposalStatus.APPROVED.value,
    )
    if request.memory_types:
        query = query.where(MemoryRecord.memory_type.in_([item.value for item in request.memory_types]))

    records = list(session.scalars(query))
    scoped_records = []
    for record in records:
        if record.memory_zone == MemoryZone.PUBLIC_PROFILE.value:
            scoped_records.append(record)
        elif record.project_id == request.project_id:
            scoped_records.append(record)
    allowed = [
        record for record in scoped_records if can_read_memory(agent, record, request.project_id)
    ]
    query_embedding = embed_text(request.query)
    scored = [
        (record, cosine_similarity(query_embedding, record.embedding or [])) for record in allowed
    ]
    scored.sort(key=lambda item: item[1], reverse=True)
    memories = [
        record_to_memory_out(record, score=round(score, 4))
        for record, score in scored[: request.top_k]
    ]
    audit_id = audit(
        session,
        agent,
        AuditAction.SEARCH,
        "memory",
        details={
            "query": request.query,
            "project_id": request.project_id,
            "candidate_count_after_acl": len(allowed),
            "returned_ids": [memory.id for memory in memories],
        },
    )
    return SearchResult(
        memories=memories,
        candidate_count_after_acl=len(allowed),
        audit_id=audit_id,
        display=_search_display(memories, request.query, "Visible after SQL ACL filtering."),
    )


def create_memory_proposal(
    session: Session, agent: AgentIdentity, request: MemoryProposalRequest
) -> ProposalOut:
    if not agent.can_write:
        raise PermissionDenied("agent cannot propose memories")
    sensitivity = classify_sensitivity(request.content)
    status = ProposalStatus.PENDING.value
    proposal = MemoryWriteProposalRecord(
        id=new_id("mwp"),
        tenant_id=agent.tenant_id,
        project_id=request.project_id,
        proposed_by_agent_id=agent.agent_id,
        memory_type=request.memory_type.value,
        memory_zone=request.memory_zone.value if request.memory_zone else None,
        content_kind=ContentKind.TEXT.value,
        visibility=request.visibility.value,
        content=request.content,
        tags=request.tags,
        sensitivity=sensitivity.value,
        status=status,
    )
    session.add(proposal)
    session.flush()
    audit(
        session,
        agent,
        AuditAction.WRITE_PROPOSAL,
        "memory_write_proposal",
        proposal.id,
        {"requires_approval": requires_approval(request.memory_type, request.visibility, sensitivity)},
    )
    return proposal_to_out(proposal)


def record_interaction(
    session: Session, agent: AgentIdentity, request: InteractionRequest
) -> str:
    event_id = new_id("int")
    session.add(
        InteractionEventRecord(
            id=event_id,
            tenant_id=agent.tenant_id,
            project_id=request.project_id,
            task_id=request.task_id,
            agent_id=agent.agent_id,
            task_input=request.task_input,
            agent_output=request.agent_output,
            tool_summary=request.tool_summary,
            result=request.result,
        )
    )
    session.flush()
    return event_id


def submit_feedback(
    session: Session, agent: AgentIdentity, request: FeedbackRequest
) -> FeedbackEventRecord:
    event = FeedbackEventRecord(
        id=new_id("fb"),
        tenant_id=agent.tenant_id,
        project_id=request.project_id,
        task_id=request.task_id,
        agent_id=agent.agent_id,
        rating=request.rating,
        correction=request.correction,
        expected_behavior=request.expected_behavior,
        error_type=request.error_type,
    )
    session.add(event)
    session.flush()
    audit(
        session,
        agent,
        AuditAction.FEEDBACK,
        "feedback",
        event.id,
        {
            "task_id": request.task_id,
            "rating": request.rating,
            "error_type": request.error_type,
        },
    )
    return event


def _lesson_content(feedback: FeedbackEventRecord) -> tuple[MemoryType, str, list[str], float]:
    correction = feedback.correction.strip()
    expected = feedback.expected_behavior.strip()
    error_type = feedback.error_type.lower()
    if any(term in error_type for term in ("do_not", "avoid", "anti", "bad")):
        memory_type = MemoryType.ANTI_PATTERN
        prefix = "Avoid repeating this mistake:"
        tags = ["feedback", "anti_pattern", feedback.error_type]
    else:
        memory_type = MemoryType.LESSON
        prefix = "When handling similar tasks, remember:"
        tags = ["feedback", "lesson", feedback.error_type]
    body = correction
    if expected:
        body = f"{correction} Expected behavior: {expected}"
    content = f"{prefix} {body}"
    confidence = 0.85 if feedback.rating <= 2 else 0.65
    return memory_type, content, tags, confidence


def extract_lessons(
    session: Session, agent: AgentIdentity, feedback_id: str
) -> list[ProposalOut]:
    feedback = session.get(FeedbackEventRecord, feedback_id)
    if not feedback or feedback.tenant_id != agent.tenant_id:
        raise NotFound("feedback not found")
    if feedback.agent_id != agent.agent_id and not agent.is_admin:
        raise PermissionDenied("agent can only extract lessons from its own feedback")

    existing = session.scalars(
        select(LearnedMemoryProposalRecord).where(
            LearnedMemoryProposalRecord.feedback_id == feedback_id,
            LearnedMemoryProposalRecord.status != ProposalStatus.REJECTED.value,
        )
    ).all()
    if existing:
        return [proposal_to_out(item) for item in existing]

    memory_type, content, tags, confidence = _lesson_content(feedback)
    sensitivity = classify_sensitivity(content)
    proposal = LearnedMemoryProposalRecord(
        id=new_id("lmp"),
        tenant_id=feedback.tenant_id,
        project_id=feedback.project_id,
        feedback_id=feedback.id,
        proposed_by_agent_id=agent.agent_id,
        memory_type=memory_type.value,
        memory_zone=MemoryZone.WORK_CONTEXT.value if feedback.project_id else MemoryZone.PUBLIC_PROFILE.value,
        visibility=Visibility.PROJECT.value if feedback.project_id else Visibility.PUBLIC.value,
        content=content,
        tags=tags,
        sensitivity=sensitivity.value,
        confidence=confidence,
        status=ProposalStatus.PENDING.value,
    )
    session.add(proposal)
    session.flush()
    audit(
        session,
        agent,
        AuditAction.EXTRACT,
        "learned_memory_proposal",
        proposal.id,
        {"feedback_id": feedback_id, "confidence": confidence},
    )
    return [proposal_to_out(proposal)]


def list_learning_proposals(
    session: Session,
    agent: AgentIdentity,
    status: ProposalStatus = ProposalStatus.PENDING,
) -> list[ProposalOut]:
    if not agent.is_admin:
        raise PermissionDenied("only admin agents can list learning proposals")
    records = session.scalars(
        select(LearnedMemoryProposalRecord).where(
            LearnedMemoryProposalRecord.tenant_id == agent.tenant_id,
            LearnedMemoryProposalRecord.status == status.value,
        )
    ).all()
    return [proposal_to_out(record) for record in records]


def approve_learning_proposal(
    session: Session, agent: AgentIdentity, proposal_id: str
) -> ProposalOut:
    if not agent.is_admin:
        raise PermissionDenied("only admin agents can approve learned memories")
    proposal = session.get(LearnedMemoryProposalRecord, proposal_id)
    if not proposal or proposal.tenant_id != agent.tenant_id:
        raise NotFound("learning proposal not found")
    if proposal.status != ProposalStatus.PENDING.value:
        raise InvalidState(f"proposal is {proposal.status}, not pending")

    memory_id = new_id("mem")
    memory = MemoryRecord(
        id=memory_id,
        tenant_id=proposal.tenant_id,
        project_id=proposal.project_id,
        visibility=proposal.visibility,
        allowed_agent_ids=[],
        denied_agent_ids=[],
        memory_type=proposal.memory_type,
        memory_zone=proposal.memory_zone,
        content=proposal.content,
        tags=proposal.tags,
        sensitivity=proposal.sensitivity,
        source=f"feedback:{proposal.feedback_id}",
        embedding=embed_text(proposal.content),
        status=ProposalStatus.APPROVED.value,
        created_by_agent_id=proposal.proposed_by_agent_id,
    )
    proposal.status = ProposalStatus.APPROVED.value
    proposal.approved_at = utcnow()
    proposal.approved_by_agent_id = agent.agent_id
    proposal.approved_memory_id = memory_id
    session.add(memory)
    session.add(
        MemoryVersionRecord(
            id=new_id("ver"),
            tenant_id=proposal.tenant_id,
            memory_id=memory_id,
            previous_memory_id=None,
            event="created_from_feedback",
            actor_agent_id=agent.agent_id,
        )
    )
    session.flush()
    audit(
        session,
        agent,
        AuditAction.APPROVE,
        "learned_memory_proposal",
        proposal.id,
        {"approved_memory_id": memory_id},
    )
    _index_graph_memory(session, agent, memory)
    from .runtime.facts import upsert_facts_for_memory

    upsert_facts_for_memory(session, agent, memory)
    return proposal_to_out(proposal)


def approve_memory_write_proposal(
    session: Session, agent: AgentIdentity, proposal_id: str
) -> ProposalOut:
    if not agent.is_admin:
        raise PermissionDenied("only admin agents can approve memory proposals")
    proposal = session.get(MemoryWriteProposalRecord, proposal_id)
    if not proposal or proposal.tenant_id != agent.tenant_id:
        raise NotFound("memory proposal not found")
    if proposal.status != ProposalStatus.PENDING.value:
        raise InvalidState(f"proposal is {proposal.status}, not pending")
    memory_id = new_id("mem")
    memory = MemoryRecord(
        id=memory_id,
        tenant_id=proposal.tenant_id,
        project_id=proposal.project_id,
        visibility=proposal.visibility,
        allowed_agent_ids=[],
        denied_agent_ids=[],
        memory_type=proposal.memory_type,
        memory_zone=proposal.memory_zone,
        content_kind=proposal.content_kind,
        capture_source=proposal.capture_source,
        source_url=proposal.source_url,
        source_title=proposal.source_title,
        asset_path=proposal.asset_path,
        redacted=bool(proposal.redacted),
        content=proposal.content,
        tags=proposal.tags,
        sensitivity=proposal.sensitivity,
        source=f"proposal:{proposal.id}",
        embedding=embed_text(proposal.content),
        status=ProposalStatus.APPROVED.value,
        created_by_agent_id=proposal.proposed_by_agent_id,
    )
    proposal.status = ProposalStatus.APPROVED.value
    proposal.approved_at = utcnow()
    proposal.approved_by_agent_id = agent.agent_id
    proposal.approved_memory_id = memory_id
    session.add(memory)
    session.flush()
    audit(session, agent, AuditAction.APPROVE, "memory_write_proposal", proposal.id)
    _index_graph_memory(session, agent, memory)
    from .runtime.facts import upsert_facts_for_memory

    upsert_facts_for_memory(session, agent, memory)
    return proposal_to_out(proposal)


def delete_memory(session: Session, agent: AgentIdentity, memory_id: str) -> None:
    if not agent.is_admin:
        raise PermissionDenied("only admin agents can delete memories")
    memory = session.get(MemoryRecord, memory_id)
    if not memory or memory.tenant_id != agent.tenant_id:
        raise NotFound("memory not found")
    memory.deleted_at = utcnow()
    session.add(
        MemoryVersionRecord(
            id=new_id("ver"),
            tenant_id=memory.tenant_id,
            memory_id=memory.id,
            previous_memory_id=None,
            event="deleted",
            actor_agent_id=agent.agent_id,
        )
    )
    session.flush()
    audit(session, agent, AuditAction.DELETE, "memory", memory_id)
    _mark_graph_memory_inactive(session, agent, memory_id)
    from .runtime.facts import mark_facts_inactive_for_memory

    mark_facts_inactive_for_memory(session, agent, memory_id)


def explain_memory(
    session: Session, agent: AgentIdentity, memory_id: str, project_id: str | None = None
) -> tuple[bool, str, dict, str]:
    memory = session.get(MemoryRecord, memory_id)
    if not memory or memory.tenant_id != agent.tenant_id:
        raise NotFound("memory not found")
    allowed = can_read_memory(agent, memory, project_id)
    reason = policy_reason(agent, memory, project_id)
    details = {
        "visibility": memory.visibility,
        "memory_type": memory.memory_type,
        "project_id": memory.project_id,
        "requested_project_id": project_id,
        "allowed_agent_ids": memory.allowed_agent_ids,
        "denied_agent_ids": memory.denied_agent_ids,
        "status": memory.status,
        "deleted": memory.deleted_at is not None,
    }
    audit_id = audit(session, agent, AuditAction.EXPLAIN, "memory", memory_id, details)
    return allowed, reason, details, audit_id


def list_zones() -> list[ZoneOut]:
    return [
        ZoneOut(
            zone=zone,
            label=str(metadata["label"]),
            description=str(metadata["description"]),
            default_sensitivity=metadata["default_sensitivity"],
            requires_grant=bool(metadata["requires_grant"]),
            default_ttl_minutes=int(metadata["default_ttl_minutes"]),
            confirmation_level=str(metadata["confirmation_level"]),
        )
        for zone, metadata in ZONE_METADATA.items()
    ]


def _suggest_capture_by_rules(
    content: str,
    content_kind: ContentKind,
    project_id: str | None = None,
) -> CaptureAnalyzeResponse:
    redacted, warnings = redact_sensitive_content(content)
    lowered = content.lower()
    sensitivity = classify_sensitivity(content)
    tags: list[str] = []

    if content_kind == ContentKind.IMAGE:
        suggested_zone = MemoryZone.PERSONAL_CONTEXT
        suggested_type = MemoryType.CONTEXT
        tags.append("image")
        warnings.append("Image contents are stored as a local asset reference in v1.")
    elif any(
        term in lowered
        for term in (
            "colleague",
            "coworker",
            "co-worker",
            "team member",
            "teammate",
            "client",
            "customer",
            "同事",
            "客户",
            "客戶",
            "团队成员",
            "團隊成員",
        )
    ):
        suggested_zone = MemoryZone.WORK_CONTEXT
        suggested_type = MemoryType.RELATIONSHIP
        tags.extend(["relationship", "work"])
        sensitivity = max_sensitivity(sensitivity, Sensitivity.MEDIUM)
    elif any(
        term in lowered
        for term in (
            "friend",
            "buddy",
            "best friend",
            "family",
            "parent",
            "partner",
            "mentor",
            "roommate",
            "朋友",
            "好友",
            "家人",
            "父母",
            "伴侣",
            "伴侶",
            "导师",
            "導師",
            "室友",
        )
    ):
        suggested_zone = MemoryZone.PERSONAL_CONTEXT
        suggested_type = MemoryType.RELATIONSHIP
        tags.extend(["relationship", "personal"])
        sensitivity = max_sensitivity(sensitivity, Sensitivity.MEDIUM)
    elif any(term in lowered for term in ("payment", "card", "visa", "mastercard", "cvv", "支付宝", "微信支付")):
        suggested_zone = MemoryZone.PAYMENT_REFERENCE
        suggested_type = MemoryType.PROCEDURE
        tags.extend(["payment", "confirmation_required"])
        sensitivity = Sensitivity.HIGH
        warnings.append("Payment data is stored only as a confirmation reference, not raw credentials.")
    elif sensitivity == Sensitivity.HIGH:
        suggested_zone = MemoryZone.SENSITIVE_VAULT
        suggested_type = MemoryType.CONTEXT
        tags.append("sensitive")
    elif any(
        term in lowered
        for term in (
            "project",
            "meeting",
            "roadmap",
            "backend",
            "frontend",
            "api",
            "team",
            "客户",
            "项目",
            "会议",
            "接口",
        )
    ):
        suggested_zone = MemoryZone.WORK_CONTEXT
        suggested_type = MemoryType.CONTEXT
        tags.append("work")
        sensitivity = max_sensitivity(sensitivity, Sensitivity.MEDIUM)
    elif any(
        term in lowered
        for term in (
            "travel",
            "flight",
            "hotel",
            "calendar",
            "family",
            "trip",
            "commute",
            "office",
            "live",
            "living",
            "moved",
            "航班",
            "酒店",
            "旅行",
            "通勤",
            "办公室",
            "公司",
            "居住",
            "搬家",
        )
    ):
        suggested_zone = MemoryZone.PERSONAL_CONTEXT
        suggested_type = MemoryType.PREFERENCE
        tags.append("personal")
        sensitivity = max_sensitivity(sensitivity, Sensitivity.MEDIUM)
    else:
        suggested_zone = MemoryZone.PUBLIC_PROFILE
        suggested_type = MemoryType.PREFERENCE
        tags.append("profile")

    should_require_confirmation = zone_requires_grant(suggested_zone) or sensitivity != Sensitivity.LOW
    return CaptureAnalyzeResponse(
        rule_suggestion={
            "suggested_zone": suggested_zone.value,
            "suggested_memory_type": suggested_type.value,
            "sensitivity": sensitivity.value,
            "tags": tags,
        },
        suggested_zone=suggested_zone,
        suggested_memory_type=suggested_type,
        sensitivity=sensitivity,
        redacted_preview=redacted[:1000],
        risk_warnings=warnings,
        tags=tags,
        should_require_confirmation=should_require_confirmation,
    )


def redact_sensitive_content(content: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    redacted = content
    replacements = [
        (CARD_RE, "[REDACTED_CARD]", "Payment card-like number was redacted."),
        (TOKEN_RE, "[REDACTED_SECRET]", "Secret/token/password-like value was redacted."),
        (CVV_RE, "[REDACTED_CVV]", "CVV-like value was redacted."),
        (SSN_RE, "[REDACTED_SSN]", "SSN-like value was redacted."),
        (ID_CARD_CN_RE, "[REDACTED_ID]", "National ID-like value was redacted."),
    ]
    for pattern, placeholder, warning in replacements:
        redacted, count = pattern.subn(placeholder, redacted)
        if count:
            warnings.append(warning)
    return redacted, warnings


def list_model_profiles(session: Session, agent: AgentIdentity) -> list[ModelProfileOut]:
    records = session.scalars(
        select(ModelProfileRecord).where(ModelProfileRecord.tenant_id == agent.tenant_id)
    ).all()
    return [model_profile_to_out(record) for record in records]


def create_model_profile(
    session: Session, agent: AgentIdentity, request: ModelProfileCreateRequest
) -> ModelProfileOut:
    if not agent.is_admin:
        raise PermissionDenied("only admin agents can create model profiles")
    profile_id = request.id or new_id("mp")
    if session.get(ModelProfileRecord, profile_id):
        raise InvalidState("model profile id already exists")
    record = ModelProfileRecord(
        id=profile_id,
        tenant_id=agent.tenant_id,
        name=request.name,
        provider=request.provider.value,
        model=request.model,
        endpoint_url=request.endpoint_url,
        api_key_env=request.api_key_env,
        api_key_secret=(request.api_key or "").strip() or None,
        allowed_tasks=[task.value for task in request.allowed_tasks] or [task.value for task in ModelTask],
        allowed_zones=[zone.value for zone in request.allowed_zones] or [zone.value for zone in MemoryZone],
        local_only=request.local_only,
        auto_apply_low_sensitivity=request.auto_apply_low_sensitivity,
        is_active=False,
    )
    session.add(record)
    session.flush()
    if request.is_active:
        activate_model_profile(session, agent, profile_id)
    audit(session, agent, AuditAction.MODEL_PROFILE_CREATE, "model_profile", profile_id)
    return model_profile_to_out(record)


def activate_model_profile(session: Session, agent: AgentIdentity, profile_id: str) -> ModelProfileOut:
    if not agent.is_admin:
        raise PermissionDenied("only admin agents can activate model profiles")
    record = session.get(ModelProfileRecord, profile_id)
    if not record or record.tenant_id != agent.tenant_id:
        raise NotFound("model profile not found")
    existing = session.scalars(
        select(ModelProfileRecord).where(ModelProfileRecord.tenant_id == agent.tenant_id)
    ).all()
    for profile in existing:
        profile.is_active = profile.id == profile_id
    session.flush()
    audit(session, agent, AuditAction.MODEL_PROFILE_ACTIVATE, "model_profile", profile_id)
    return model_profile_to_out(record)


def get_model_profile(
    session: Session,
    agent: AgentIdentity,
    profile_id: str | None = None,
) -> ModelProfileRecord:
    query = select(ModelProfileRecord).where(ModelProfileRecord.tenant_id == agent.tenant_id)
    if profile_id:
        profile = session.get(ModelProfileRecord, profile_id)
    else:
        profile = session.scalars(query.where(ModelProfileRecord.is_active.is_(True))).first()
    if not profile or profile.tenant_id != agent.tenant_id:
        fallback = session.get(ModelProfileRecord, "rule-only-default")
        if fallback and fallback.tenant_id == agent.tenant_id:
            return fallback
        raise NotFound("model profile not found")
    return profile


def _profile_allows(profile: ModelProfileRecord, task: ModelTask, zone: MemoryZone) -> bool:
    return task.value in (profile.allowed_tasks or []) and zone.value in (profile.allowed_zones or [])


def _remote_model_allowed(profile: ModelProfileRecord, rule_response: CaptureAnalyzeResponse) -> bool:
    if profile.provider == ModelProvider.RULE_ONLY.value:
        return False
    if profile.provider == ModelProvider.OLLAMA.value:
        return True
    if rule_response.suggested_zone in {MemoryZone.SENSITIVE_VAULT, MemoryZone.PAYMENT_REFERENCE}:
        return False
    if rule_response.sensitivity == Sensitivity.HIGH:
        return False
    return True


def _json_from_text(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _model_prompt(task: ModelTask, content: str) -> list[dict[str, str]]:
    system = (
        "Return strict JSON only. You are a memory processing assistant. "
        "Never request credentials or grant permissions. "
        "Allowed zones: public_profile, work_context, personal_context, sensitive_vault, payment_reference. "
        "Allowed memory types: context, preference, procedure, lesson, anti_pattern."
    )
    if task == ModelTask.CLASSIFY_CAPTURE:
        user = (
            "Classify this redacted capture. Return keys: suggested_zone, "
            "suggested_memory_type, tags, summary, confidence.\n\n"
            f"Capture:\n{content}"
        )
    elif task == ModelTask.SUMMARIZE_MEMORY:
        user = f"Summarize this redacted memory in one concise sentence as JSON with key summary:\n{content}"
    elif task == ModelTask.EXTRACT_LESSON:
        user = (
            "Extract one lesson as JSON with keys memory_type, content, tags, confidence.\n"
            f"Feedback:\n{content}"
        )
    elif task == ModelTask.EXTRACT_FACTS:
        user = (
            "Extract memory facts as strict JSON with key facts. Each fact should have "
            "subject, predicate, object, fact_type, summary, confidence.\n\n"
            f"Memory:\n{content}"
        )
    else:
        user = (
            "Return a JSON embedding instruction with keys provider, model, and text_length. "
            "Do not include raw secrets.\n\n"
            f"Memory:\n{content}"
        )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _openai_chat_completions_url(endpoint_url: str | None) -> str:
    base = (endpoint_url or "https://api.openai.com").rstrip("/")
    if base.endswith("/v1/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _call_openai_compatible(profile: ModelProfileRecord, task: ModelTask, content: str) -> dict:
    api_key = (profile.api_key_secret or "").strip()
    if not api_key:
        api_key = os.getenv(profile.api_key_env or "")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    response = httpx.post(
        _openai_chat_completions_url(profile.endpoint_url),
        headers=headers,
        json={
            "model": profile.model,
            "messages": _model_prompt(task, content),
            "temperature": 0,
            "response_format": {"type": "json_object"},
        },
        timeout=20,
    )
    response.raise_for_status()
    return _json_from_text(response.json()["choices"][0]["message"]["content"])


def _call_ollama(profile: ModelProfileRecord, task: ModelTask, content: str) -> dict:
    base = (profile.endpoint_url or "http://127.0.0.1:11434").rstrip("/")
    messages = _model_prompt(task, content)
    response = httpx.post(
        f"{base}/api/chat",
        json={
            "model": profile.model,
            "messages": messages,
            "stream": False,
            "format": "json",
        },
        timeout=20,
    )
    response.raise_for_status()
    return _json_from_text(response.json()["message"]["content"])


def _call_model_profile(profile: ModelProfileRecord, task: ModelTask, content: str) -> dict:
    if profile.provider == ModelProvider.OPENAI_COMPATIBLE.value:
        return _call_openai_compatible(profile, task, content)
    if profile.provider == ModelProvider.OLLAMA.value:
        return _call_ollama(profile, task, content)
    return {}


def _merge_model_capture_suggestion(
    rule_response: CaptureAnalyzeResponse,
    suggestion: dict,
) -> CaptureAnalyzeResponse:
    protected = rule_response.sensitivity != Sensitivity.LOW or rule_response.suggested_zone != MemoryZone.PUBLIC_PROFILE
    zone = rule_response.suggested_zone
    memory_type = rule_response.suggested_memory_type
    tags = list(rule_response.tags)
    source = "rule"
    if not protected and suggestion.get("suggested_zone"):
        try:
            candidate_zone = MemoryZone(str(suggestion["suggested_zone"]))
            candidate_type = MemoryType(str(suggestion.get("suggested_memory_type", memory_type.value)))
            if candidate_zone == MemoryZone.PUBLIC_PROFILE:
                zone = candidate_zone
                memory_type = candidate_type
                tags = [str(item) for item in suggestion.get("tags", tags)]
                suggestion["applied"] = True
                suggestion.pop("blocked_by_policy", None)
                source = "model"
            else:
                suggestion["applied"] = False
                suggestion["blocked_by_policy"] = "model may only auto-apply low-risk public_profile suggestions"
        except ValueError:
            suggestion["applied"] = False
            suggestion["blocked_by_policy"] = "invalid model suggestion"
    else:
        suggestion["applied"] = False
        if protected:
            suggestion["blocked_by_policy"] = "non-public or non-low sensitivity suggestions require user confirmation"
    return CaptureAnalyzeResponse(
        rule_suggestion=rule_response.rule_suggestion,
        model_suggestion=suggestion,
        final_suggestion_source=source,
        sent_to_model=False,
        used_redacted_preview=True,
        suggested_zone=zone,
        suggested_memory_type=memory_type,
        sensitivity=rule_response.sensitivity,
        redacted_preview=rule_response.redacted_preview,
        risk_warnings=rule_response.risk_warnings,
        tags=tags,
        should_require_confirmation=zone_requires_grant(zone) or rule_response.sensitivity != Sensitivity.LOW,
    )


def classify_capture_with_model(
    session: Session,
    agent: AgentIdentity,
    request: ModelProcessingClassifyRequest,
    rule_response: CaptureAnalyzeResponse | None = None,
) -> ModelProcessingResponse:
    profile = get_model_profile(session, agent, request.model_profile_id)
    rule_response = rule_response or _suggest_capture_by_rules(request.content, ContentKind.TEXT, request.project_id)
    redacted, warnings = redact_sensitive_content(request.content)
    sent_to_model = False
    fallback_used = False
    suggestion: dict = dict(rule_response.rule_suggestion or {})
    suggestion["applied"] = False
    if _profile_allows(profile, ModelTask.CLASSIFY_CAPTURE, rule_response.suggested_zone) and _remote_model_allowed(profile, rule_response):
        try:
            if profile.provider != ModelProvider.RULE_ONLY.value:
                sent_to_model = True
                suggestion = _call_model_profile(profile, ModelTask.CLASSIFY_CAPTURE, redacted)
            else:
                suggestion["provider"] = "rule_only"
        except Exception as error:
            fallback_used = True
            suggestion = dict(rule_response.rule_suggestion or {})
            suggestion["model_error"] = str(error)
    else:
        if profile.provider != ModelProvider.RULE_ONLY.value:
            suggestion["blocked_by_policy"] = "profile is not allowed for this task or zone"
    audit(
        session,
        agent,
        AuditAction.MODEL_PROCESS,
        "model_profile",
        profile.id,
        {
            "task": ModelTask.CLASSIFY_CAPTURE.value,
            "sent_to_model": sent_to_model,
            "used_redacted_preview": True,
            "fallback_used": fallback_used,
            "rule_zone": rule_response.suggested_zone.value,
        },
    )
    response = ModelProcessingResponse(
        profile_id=profile.id,
        provider=ModelProvider(profile.provider),
        task=ModelTask.CLASSIFY_CAPTURE,
        sent_to_model=sent_to_model,
        used_redacted_preview=True,
        redacted_preview=redacted[:1000],
        suggestion=suggestion,
        fallback_used=fallback_used,
        risk_warnings=warnings,
    )
    response.display = _model_display(response)
    return response


def summarize_memory_with_model(
    session: Session,
    agent: AgentIdentity,
    request: ModelProcessingSummarizeRequest,
) -> ModelProcessingResponse:
    profile = get_model_profile(session, agent, request.model_profile_id)
    redacted, warnings = redact_sensitive_content(request.content)
    sent_to_model = False
    fallback_used = False
    suggestion = {"summary": redacted[:240]}
    if profile.provider != ModelProvider.RULE_ONLY.value and ModelTask.SUMMARIZE_MEMORY.value in (profile.allowed_tasks or []):
        try:
            sent_to_model = True
            suggestion = _call_model_profile(profile, ModelTask.SUMMARIZE_MEMORY, redacted)
        except Exception as error:
            fallback_used = True
            suggestion["model_error"] = str(error)
    audit(session, agent, AuditAction.MODEL_PROCESS, "model_profile", profile.id, {"task": ModelTask.SUMMARIZE_MEMORY.value, "sent_to_model": sent_to_model})
    response = ModelProcessingResponse(
        profile_id=profile.id,
        provider=ModelProvider(profile.provider),
        task=ModelTask.SUMMARIZE_MEMORY,
        sent_to_model=sent_to_model,
        used_redacted_preview=True,
        redacted_preview=redacted[:1000],
        suggestion=suggestion,
        fallback_used=fallback_used,
        risk_warnings=warnings,
    )
    response.display = _model_display(response)
    return response


def extract_lesson_with_model(
    session: Session,
    agent: AgentIdentity,
    request: ModelProcessingLessonRequest,
) -> ModelProcessingResponse:
    profile = get_model_profile(session, agent, request.model_profile_id)
    content = f"{request.feedback}\nExpected behavior: {request.expected_behavior}"
    redacted, warnings = redact_sensitive_content(content)
    sent_to_model = False
    fallback_used = False
    suggestion = {
        "memory_type": MemoryType.LESSON.value,
        "content": f"When handling similar tasks, remember: {redacted}",
        "tags": ["feedback", "lesson"],
        "confidence": 0.65,
    }
    if profile.provider != ModelProvider.RULE_ONLY.value and ModelTask.EXTRACT_LESSON.value in (profile.allowed_tasks or []):
        try:
            sent_to_model = True
            suggestion = _call_model_profile(profile, ModelTask.EXTRACT_LESSON, redacted)
        except Exception as error:
            fallback_used = True
            suggestion["model_error"] = str(error)
    audit(session, agent, AuditAction.MODEL_PROCESS, "model_profile", profile.id, {"task": ModelTask.EXTRACT_LESSON.value, "sent_to_model": sent_to_model})
    response = ModelProcessingResponse(
        profile_id=profile.id,
        provider=ModelProvider(profile.provider),
        task=ModelTask.EXTRACT_LESSON,
        sent_to_model=sent_to_model,
        used_redacted_preview=True,
        redacted_preview=redacted[:1000],
        suggestion=suggestion,
        fallback_used=fallback_used,
        risk_warnings=warnings,
    )
    response.display = _model_display(response)
    return response


def test_model_profile(
    session: Session,
    agent: AgentIdentity,
    profile_id: str,
    request: ModelProfileTestRequest,
) -> ModelProcessingResponse:
    if request.task == ModelTask.SUMMARIZE_MEMORY:
        return summarize_memory_with_model(
            session,
            agent,
            ModelProcessingSummarizeRequest(content=request.content, model_profile_id=profile_id),
        )
    if request.task == ModelTask.EXTRACT_LESSON:
        return extract_lesson_with_model(
            session,
            agent,
            ModelProcessingLessonRequest(feedback=request.content, model_profile_id=profile_id),
        )
    if request.task in {ModelTask.EXTRACT_FACTS, ModelTask.EMBED_MEMORY}:
        profile = get_model_profile(session, agent, profile_id)
        redacted, warnings = redact_sensitive_content(request.content)
        suggestion = (
            {"facts": [{"summary": redacted[:180], "confidence": 0.6}]}
            if request.task == ModelTask.EXTRACT_FACTS
            else {"embedding_provider": "deterministic", "text_length": len(redacted)}
        )
        response = ModelProcessingResponse(
            profile_id=profile.id,
            provider=ModelProvider(profile.provider),
            task=request.task,
            sent_to_model=False,
            used_redacted_preview=True,
            redacted_preview=redacted[:1000],
            suggestion=suggestion,
            fallback_used=profile.provider != ModelProvider.RULE_ONLY.value,
            risk_warnings=warnings,
        )
        response.display = _model_display(response)
        return response
    return classify_capture_with_model(
        session,
        agent,
        ModelProcessingClassifyRequest(content=request.content, model_profile_id=profile_id),
    )


def analyze_capture(
    session: Session, agent: AgentIdentity, request: CaptureAnalyzeRequest
) -> CaptureAnalyzeResponse:
    rule_response = _suggest_capture_by_rules(
        request.content,
        request.content_kind,
        request.project_id,
    )
    final_response = rule_response
    model_response: ModelProcessingResponse | None = None
    if request.model_profile_id:
        model_response = classify_capture_with_model(
            session,
            agent,
            ModelProcessingClassifyRequest(
                content=request.content,
                project_id=request.project_id,
                model_profile_id=request.model_profile_id,
            ),
            rule_response=rule_response,
        )
        suggestion = model_response.suggestion
        final_response = _merge_model_capture_suggestion(rule_response, suggestion)
        final_response.model_suggestion = suggestion
        final_response.sent_to_model = model_response.sent_to_model
        final_response.used_redacted_preview = model_response.used_redacted_preview
        final_response.final_suggestion_source = (
            "model"
            if suggestion.get("applied") is True
            else "rule"
        )

    capture = CaptureEventRecord(
        id=new_id("cap"),
        tenant_id=agent.tenant_id,
        agent_id=agent.agent_id,
        project_id=request.project_id,
        content_kind=request.content_kind.value,
        capture_source=request.capture_source.value,
        raw_preview=request.content[:500],
        redacted_preview=final_response.redacted_preview[:500],
        suggested_zone=final_response.suggested_zone.value,
        suggested_memory_type=final_response.suggested_memory_type.value,
        sensitivity=final_response.sensitivity.value,
        risk_warnings=final_response.risk_warnings,
        source_url=request.source_url,
        source_title=request.source_title,
        asset_path=request.asset_path,
    )
    session.add(capture)
    session.flush()
    audit(
        session,
        agent,
        AuditAction.CAPTURE_ANALYZE,
        "capture",
        capture.id,
        {
            "suggested_zone": final_response.suggested_zone.value,
            "sensitivity": final_response.sensitivity.value,
            "redacted": final_response.redacted_preview != request.content[:1000],
            "model_profile_id": request.model_profile_id,
            "sent_to_model": model_response.sent_to_model if model_response else False,
        },
    )
    final_response.display = _capture_display(final_response)
    return final_response


def commit_capture(
    session: Session, agent: AgentIdentity, request: CaptureCommitRequest
) -> CaptureCommitResponse:
    if not agent.can_write:
        raise PermissionDenied("agent cannot commit captures")
    project_id = None if request.memory_zone == MemoryZone.PUBLIC_PROFILE else request.project_id
    if request.memory_zone == MemoryZone.WORK_CONTEXT and not project_id:
        raise InvalidState("work_context memories require a project_id")
    redacted, warnings = redact_sensitive_content(request.content)
    sensitivity = max_sensitivity(
        classify_sensitivity(request.content),
        zone_default_sensitivity(request.memory_zone),
    )
    content_to_store = redacted
    visibility = (
        Visibility.PUBLIC
        if request.memory_zone == MemoryZone.PUBLIC_PROFILE
        else Visibility.PROJECT
        if project_id
        else Visibility.PRIVATE
    )
    capture_id = new_id("cap")
    capture = CaptureEventRecord(
        id=capture_id,
        tenant_id=agent.tenant_id,
        agent_id=agent.agent_id,
        project_id=project_id,
        content_kind=request.content_kind.value,
        capture_source=request.capture_source.value,
        raw_preview=request.content[:500],
        redacted_preview=content_to_store[:500],
        suggested_zone=request.memory_zone.value,
        suggested_memory_type=request.memory_type.value,
        sensitivity=sensitivity.value,
        risk_warnings=warnings,
        source_url=request.source_url,
        source_title=request.source_title,
        asset_path=request.asset_path,
    )
    session.add(capture)

    should_propose = requires_approval(request.memory_type, visibility, sensitivity) and not agent.is_admin
    if should_propose or not request.approve_now:
        proposal = MemoryWriteProposalRecord(
            id=new_id("mwp"),
            tenant_id=agent.tenant_id,
            project_id=project_id,
            proposed_by_agent_id=agent.agent_id,
            memory_type=request.memory_type.value,
            memory_zone=request.memory_zone.value,
            content_kind=request.content_kind.value,
            capture_source=request.capture_source.value,
            source_url=request.source_url,
            source_title=request.source_title,
            asset_path=request.asset_path,
            redacted=content_to_store != request.content,
            visibility=visibility.value,
            content=content_to_store,
            tags=request.tags,
            sensitivity=sensitivity.value,
            status=ProposalStatus.PENDING.value,
        )
        session.add(proposal)
        session.flush()
        audit_id = audit(
            session,
            agent,
            AuditAction.CAPTURE_COMMIT,
            "memory_write_proposal",
            proposal.id,
            {"capture_id": capture_id, "zone": request.memory_zone.value, "redacted": bool(warnings)},
        )
        return CaptureCommitResponse(
            capture_id=capture_id,
            proposal=proposal_to_out(proposal),
            audit_id=audit_id,
        )

    memory = MemoryRecord(
        id=new_id("mem"),
        tenant_id=agent.tenant_id,
        project_id=project_id,
        owner_user_id=None,
        visibility=visibility.value,
        allowed_agent_ids=[],
        denied_agent_ids=[],
        memory_type=request.memory_type.value,
        memory_zone=request.memory_zone.value,
        content_kind=request.content_kind.value,
        capture_source=request.capture_source.value,
        source_url=request.source_url,
        source_title=request.source_title,
        asset_path=request.asset_path,
        redacted=content_to_store != request.content,
        content=content_to_store,
        tags=request.tags,
        sensitivity=sensitivity.value,
        source=f"capture:{capture_id}",
        embedding=embed_text(content_to_store),
        status=ProposalStatus.APPROVED.value,
        created_by_agent_id=agent.agent_id,
    )
    session.add(memory)
    session.flush()
    capture.committed_memory_id = memory.id
    audit_id = audit(
        session,
        agent,
        AuditAction.CAPTURE_COMMIT,
        "memory",
        memory.id,
        {"capture_id": capture_id, "zone": request.memory_zone.value, "redacted": bool(warnings)},
    )
    _index_graph_memory(session, agent, memory)
    from .runtime.facts import upsert_facts_for_memory

    upsert_facts_for_memory(session, agent, memory)
    return CaptureCommitResponse(
        capture_id=capture_id,
        memory=record_to_memory_out(memory),
        audit_id=audit_id,
    )


def grant_to_out(record: AccessGrantRecord, token: str | None = None) -> GrantOut:
    return GrantOut(
        id=record.id,
        agent_id=record.agent_id,
        task_id=record.task_id,
        project_id=record.project_id,
        purpose=record.purpose,
        allowed_zones=[MemoryZone(zone) for zone in record.allowed_zones],
        status=GrantStatus(record.status),
        confirmation_level=record.confirmation_level,
        expires_at=record.expires_at,
        created_at=record.created_at,
        token=token,
    )


def request_access_grant(
    session: Session, agent: AgentIdentity, request: GrantRequest
) -> GrantOut:
    if not request.allowed_zones:
        raise InvalidState("at least one memory zone is required")
    if MemoryZone.WORK_CONTEXT in request.allowed_zones and not request.project_id:
        raise InvalidState("work_context grants require a project_id")
    min_default_ttl = min(zone_default_ttl_minutes(zone) for zone in request.allowed_zones)
    ttl_minutes = request.ttl_minutes or min_default_ttl
    if any(zone == MemoryZone.PAYMENT_REFERENCE for zone in request.allowed_zones):
        ttl_minutes = min(ttl_minutes, 5)
    expires_at = utcnow() + timedelta(minutes=ttl_minutes)
    grant = AccessGrantRecord(
        id=new_id("gr"),
        tenant_id=agent.tenant_id,
        project_id=request.project_id,
        agent_id=agent.agent_id,
        task_id=request.task_id,
        purpose=request.purpose,
        allowed_zones=[zone.value for zone in request.allowed_zones],
        status=GrantStatus.PENDING.value,
        confirmation_level=zone_confirmation_level(request.allowed_zones),
        expires_at=expires_at,
    )
    session.add(grant)
    session.flush()
    audit(
        session,
        agent,
        AuditAction.GRANT_REQUEST,
        "access_grant",
        grant.id,
        {
            "allowed_zones": grant.allowed_zones,
            "purpose": request.purpose,
            "project_id": request.project_id,
        },
    )
    return grant_to_out(grant)


def get_access_grant(session: Session, agent: AgentIdentity, grant_id: str) -> GrantOut:
    grant = session.get(AccessGrantRecord, grant_id)
    if not grant or grant.tenant_id != agent.tenant_id:
        raise NotFound("grant not found")
    if grant.agent_id != agent.agent_id and not agent.is_admin:
        raise PermissionDenied("agent cannot read this grant")
    if grant.status == GrantStatus.APPROVED.value and as_utc_naive(grant.expires_at) <= now_for_db_compare():
        grant.status = GrantStatus.EXPIRED.value
        session.flush()
    return grant_to_out(grant)


def list_access_grants(
    session: Session,
    agent: AgentIdentity,
    status: GrantStatus | None = GrantStatus.PENDING,
) -> list[GrantOut]:
    if not agent.is_admin:
        raise PermissionDenied("only admin agents can list access grants")
    query = select(AccessGrantRecord).where(AccessGrantRecord.tenant_id == agent.tenant_id)
    if status:
        query = query.where(AccessGrantRecord.status == status.value)
    return [grant_to_out(record) for record in session.scalars(query).all()]


def approve_access_grant(
    session: Session,
    agent: AgentIdentity,
    grant_id: str,
    ttl_minutes: int | None = None,
) -> GrantOut:
    if not agent.is_admin:
        raise PermissionDenied("only admin agents can approve grants")
    grant = session.get(AccessGrantRecord, grant_id)
    if not grant or grant.tenant_id != agent.tenant_id:
        raise NotFound("grant not found")
    if grant.status != GrantStatus.PENDING.value:
        raise InvalidState(f"grant is {grant.status}, not pending")
    zones = [MemoryZone(zone) for zone in grant.allowed_zones]
    min_default_ttl = min(zone_default_ttl_minutes(zone) for zone in zones)
    effective_ttl = ttl_minutes or min_default_ttl
    if any(zone == MemoryZone.PAYMENT_REFERENCE for zone in zones):
        effective_ttl = min(effective_ttl, 5)
    raw_token = secrets.token_urlsafe(32)
    grant.status = GrantStatus.APPROVED.value
    grant.token_hash = token_hash(raw_token)
    grant.token_revealed_at = utcnow()
    grant.expires_at = utcnow() + timedelta(minutes=effective_ttl)
    grant.approved_at = utcnow()
    grant.approved_by_agent_id = agent.agent_id
    session.flush()
    audit(
        session,
        agent,
        AuditAction.GRANT_APPROVE,
        "access_grant",
        grant.id,
        {"allowed_zones": grant.allowed_zones, "ttl_minutes": effective_ttl},
    )
    return grant_to_out(grant, token=raw_token)


def revoke_access_grant(session: Session, agent: AgentIdentity, grant_id: str) -> GrantOut:
    if not agent.is_admin:
        raise PermissionDenied("only admin agents can revoke grants")
    grant = session.get(AccessGrantRecord, grant_id)
    if not grant or grant.tenant_id != agent.tenant_id:
        raise NotFound("grant not found")
    grant.status = GrantStatus.REVOKED.value
    grant.revoked_at = utcnow()
    session.flush()
    audit(session, agent, AuditAction.GRANT_REVOKE, "access_grant", grant.id)
    return grant_to_out(grant)


def _validate_vault_grant(
    session: Session,
    agent: AgentIdentity,
    zones: list[MemoryZone],
    grant_token: str | None,
    project_id: str | None,
) -> AccessGrantRecord | None:
    requested_private_zones = [zone for zone in zones if zone_requires_grant(zone)]
    if not requested_private_zones:
        return None
    if not grant_token:
        raise PermissionDenied("grant token is required for requested memory zones")
    hashed = token_hash(grant_token)
    grant = session.scalars(
        select(AccessGrantRecord).where(
            AccessGrantRecord.tenant_id == agent.tenant_id,
            AccessGrantRecord.agent_id == agent.agent_id,
            AccessGrantRecord.token_hash == hashed,
        )
    ).first()
    if not grant:
        raise PermissionDenied("invalid grant token")
    if grant.status != GrantStatus.APPROVED.value:
        raise PermissionDenied(f"grant is {grant.status}")
    if grant.project_id != project_id:
        raise PermissionDenied("grant is scoped to a different project")
    if as_utc_naive(grant.expires_at) <= now_for_db_compare():
        grant.status = GrantStatus.EXPIRED.value
        session.flush()
        raise PermissionDenied("grant has expired")
    allowed = {MemoryZone(zone) for zone in grant.allowed_zones}
    missing = [zone.value for zone in requested_private_zones if zone not in allowed]
    if missing:
        raise PermissionDenied(f"grant does not allow zones: {missing}")
    return grant


def _readable_memory_records_for_zones(
    session: Session,
    agent: AgentIdentity,
    project_id: str | None,
    zones: list[MemoryZone],
    grant_token: str | None,
) -> tuple[AccessGrantRecord | None, list[MemoryRecord]]:
    grant = _validate_vault_grant(session, agent, zones, grant_token, project_id)
    query = select(MemoryRecord).where(
        MemoryRecord.tenant_id == agent.tenant_id,
        MemoryRecord.deleted_at.is_(None),
        MemoryRecord.status == ProposalStatus.APPROVED.value,
        MemoryRecord.memory_zone.in_([zone.value for zone in zones]),
    )
    records = list(session.scalars(query))
    allowed = []
    grant_zones = {MemoryZone(zone) for zone in grant.allowed_zones} if grant else set()
    for record in records:
        if record.memory_zone != MemoryZone.PUBLIC_PROFILE.value and record.project_id != project_id:
            continue
        if can_read_memory(agent, record, project_id):
            allowed.append(record)
            continue
        if (
            grant
            and record.visibility == Visibility.PRIVATE.value
            and record.memory_zone
            and MemoryZone(record.memory_zone) in grant_zones
            and record.project_id == project_id
        ):
            allowed.append(record)
    return grant, allowed


def _strictest_zone(records: list[MemoryRecord]) -> MemoryZone | None:
    if not records:
        return None
    order = {
        MemoryZone.PUBLIC_PROFILE.value: 0,
        MemoryZone.WORK_CONTEXT.value: 1,
        MemoryZone.PERSONAL_CONTEXT.value: 1,
        MemoryZone.SENSITIVE_VAULT.value: 2,
        MemoryZone.PAYMENT_REFERENCE.value: 3,
    }
    selected = max(records, key=lambda record: order.get(record.memory_zone or "", -1))
    return MemoryZone(selected.memory_zone) if selected.memory_zone else None


def _strictest_sensitivity(records: list[MemoryRecord]) -> Sensitivity:
    if not records:
        return Sensitivity.LOW
    return max_sensitivity(*(Sensitivity(record.sensitivity) for record in records))


def _enrich_graph_cards(
    cards: list[GraphCardOut],
    readable_records: list[MemoryRecord],
) -> list[GraphCardOut]:
    by_id = {record.id: record for record in readable_records}
    enriched: list[GraphCardOut] = []
    for card in cards:
        sources = [by_id[source_id] for source_id in card.source_memory_ids if source_id in by_id]
        if len(sources) != len(card.source_memory_ids):
            continue
        zone = _strictest_zone(sources)
        sensitivity = _strictest_sensitivity(sources)
        risk_note = card.risk_note
        if zone == MemoryZone.PAYMENT_REFERENCE:
            risk_note = "Payment reference only. Raw payment data is never returned."
        elif zone == MemoryZone.SENSITIVE_VAULT:
            risk_note = "Sensitive reference only. Raw secrets are never returned."
        enriched.append(
            card.model_copy(
                update={
                    "zone": zone,
                    "sensitivity": sensitivity,
                    "source_count": len(sources),
                    "why_visible": (
                        "Visible because every source memory passed SQL ACL and active grant checks."
                    ),
                    "risk_note": risk_note,
                }
            )
        )
    return enriched


def graph_health() -> GraphHealthResponse:
    health = get_graph_client().health()
    return GraphHealthResponse(
        graph_available=health.available,
        enabled=health.enabled,
        reason=health.reason,
    )


def _index_graph_memory(session: Session, agent: AgentIdentity, memory: MemoryRecord) -> None:
    result = get_graph_client().upsert_memory(memory)
    audit(
        session,
        agent,
        AuditAction.GRAPH_EXTRACT,
        "memory",
        memory.id,
        {
            "graph_available": result.available,
            "indexed_count": result.indexed_count,
            "reason": result.reason,
        },
    )


def _mark_graph_memory_inactive(session: Session, agent: AgentIdentity, memory_id: str) -> None:
    result = get_graph_client().mark_memory_inactive(memory_id)
    audit(
        session,
        agent,
        AuditAction.GRAPH_EXTRACT,
        "memory",
        memory_id,
        {
            "graph_available": result.available,
            "indexed_count": result.indexed_count,
            "reason": result.reason,
            "status": "inactive",
        },
    )


def graph_search(
    session: Session,
    agent: AgentIdentity,
    request: GraphSearchRequest,
) -> GraphSearchResponse:
    grant, allowed = _readable_memory_records_for_zones(
        session, agent, request.project_id, request.zones, request.grant_token
    )
    allowed_ids = [record.id for record in allowed]
    result = get_graph_client().search(
        tenant_id=agent.tenant_id,
        query=request.query,
        allowed_memory_ids=allowed_ids,
        top_k=request.top_k,
    )
    cards = _enrich_graph_cards(result.cards, allowed) if result.available else []
    if not result.available:
        summary = "Graph is unavailable. Regular memory search can still run."
    elif not cards:
        summary = f"No readable graph facts matched {request.query!r}."
    else:
        summary = f"Found {len(cards)} permissioned graph facts for {request.query!r}."
    audit_id = audit(
        session,
        agent,
        AuditAction.GRAPH_SEARCH,
        "graph",
        grant.id if grant else None,
        {
            "query": request.query,
            "project_id": request.project_id,
            "zones": [zone.value for zone in request.zones],
            "graph_available": result.available,
            "reason": result.reason,
            "candidate_count_after_acl": len(allowed),
            "returned_ids": [card.id for card in cards],
        },
    )
    return GraphSearchResponse(
        graph_available=result.available,
        summary=summary,
        cards=cards,
        audit_id=audit_id,
        reason=result.reason,
    )


def graph_explain(
    session: Session,
    agent: AgentIdentity,
    entity_id: str,
    project_id: str | None,
    zones: list[MemoryZone],
    grant_token: str | None,
) -> GraphExplainResponse:
    _, allowed = _readable_memory_records_for_zones(
        session, agent, project_id, zones, grant_token
    )
    result = get_graph_client().explain_entity(
        tenant_id=agent.tenant_id,
        entity_id=entity_id,
        allowed_memory_ids=[record.id for record in allowed],
    )
    cards = _enrich_graph_cards(result.cards, allowed) if result.available else []
    allowed_result = bool(result.available and cards)
    audit_id = audit(
        session,
        agent,
        AuditAction.GRAPH_EXPLAIN,
        "graph_entity",
        entity_id,
        {
            "project_id": project_id,
            "zones": [zone.value for zone in zones],
            "graph_available": result.available,
            "allowed": allowed_result,
            "reason": result.reason,
        },
    )
    reason = (
        "Entity relations are visible after SQL ACL and grant checks."
        if allowed_result
        else result.reason or "No readable relations are attached to this entity."
    )
    return GraphExplainResponse(
        graph_available=result.available,
        entity_id=entity_id,
        allowed=allowed_result,
        reason=reason,
        cards=cards,
        audit_id=audit_id,
    )


def graph_rebuild(session: Session, agent: AgentIdentity) -> GraphRebuildResponse:
    if not agent.is_admin:
        raise PermissionDenied("only admin agents can rebuild graph memory")
    client = get_graph_client()
    inactive = client.mark_tenant_inactive(agent.tenant_id)
    if not inactive.available:
        audit_id = audit(
            session,
            agent,
            AuditAction.GRAPH_REBUILD,
            "graph",
            details={"graph_available": False, "reason": inactive.reason},
        )
        return GraphRebuildResponse(
            graph_available=False,
            indexed_memories=0,
            audit_id=audit_id,
            reason=inactive.reason,
        )
    records = session.scalars(
        select(MemoryRecord).where(
            MemoryRecord.tenant_id == agent.tenant_id,
            MemoryRecord.deleted_at.is_(None),
            MemoryRecord.status == ProposalStatus.APPROVED.value,
        )
    ).all()
    indexed = 0
    reason: str | None = None
    for memory in records:
        result = client.upsert_memory(memory)
        if result.available:
            indexed += 1
        else:
            reason = result.reason
            break
    audit_id = audit(
        session,
        agent,
        AuditAction.GRAPH_REBUILD,
        "graph",
        details={
            "graph_available": reason is None,
            "indexed_memories": indexed,
            "reason": reason,
        },
    )
    return GraphRebuildResponse(
        graph_available=reason is None,
        indexed_memories=indexed,
        audit_id=audit_id,
        reason=reason,
    )


def vault_search(
    session: Session, agent: AgentIdentity, request: VaultSearchRequest
) -> SearchResult:
    from .runtime.retrieval import retrieve_for_context

    result = retrieve_for_context(
        session,
        agent,
        query=request.query,
        project_id=request.project_id,
        zones=request.zones,
        grant_token=request.grant_token,
        memory_types=request.memory_types,
        top_k=request.top_k,
        strict_grant=True,
    )
    audit_id = audit(
        session,
        agent,
        AuditAction.VAULT_SEARCH,
        "memory",
        result.grant_id,
        {
            "query": request.query,
            "project_id": request.project_id,
            "zones": [zone.value for zone in request.zones],
            "candidate_count_after_acl": result.candidate_count_after_acl,
            "returned_ids": [memory.id for memory in result.memories],
        },
    )
    return SearchResult(
        memories=result.memories,
        candidate_count_after_acl=result.candidate_count_after_acl,
        audit_id=audit_id,
        display=SearchDisplayOut(
            summary=(
                f"Found {len(result.memories)} readable memories for {request.query!r}."
                if result.memories
                else f"No readable memories matched {request.query!r}."
            ),
            cards=result.source_cards,
        ),
    )


def list_recent_audit_events(
    session: Session,
    agent: AgentIdentity,
    limit: int = 50,
) -> list[AuditOut]:
    if not agent.is_admin:
        raise PermissionDenied("only admin agents can list audit events")
    records = session.scalars(
        select(AuditEventRecord)
        .where(AuditEventRecord.tenant_id == agent.tenant_id)
        .order_by(AuditEventRecord.created_at.desc())
        .limit(limit)
    ).all()
    return [
        AuditOut(
            id=record.id,
            agent_id=record.agent_id,
            action=record.action,
            resource_type=record.resource_type,
            resource_id=record.resource_id,
            details=record.details or {},
            created_at=record.created_at,
        )
        for record in records
    ]


def benchmark_forbidden_leak_rate(
    session: Session,
    guest: AgentIdentity,
    backend: AgentIdentity,
    query: str = "database vector memory salary confidential",
) -> dict:
    start = time.perf_counter()
    guest_result = search_memories(
        session,
        guest,
        SearchRequest(query=query, project_id="memory-gateway", top_k=10),
    )
    backend_result = search_memories(
        session,
        backend,
        SearchRequest(query=query, project_id="memory-gateway", top_k=10),
    )
    forbidden_ids = {"mem_project_database", "mem_private_salary"}
    leaks = [memory.id for memory in guest_result.memories if memory.id in forbidden_ids]
    elapsed_ms = (time.perf_counter() - start) * 1000
    return {
        "forbidden_leak_rate": 0 if not leaks else len(leaks) / len(forbidden_ids),
        "guest_returned_ids": [memory.id for memory in guest_result.memories],
        "backend_returned_ids": [memory.id for memory in backend_result.memories],
        "leaks": leaks,
        "elapsed_ms": round(elapsed_ms, 2),
    }
