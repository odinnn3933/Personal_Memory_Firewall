from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from memory_gateway.graph import get_graph_client
from memory_gateway.schemas import (
    ContextComposeRequest,
    ContextComposeResponse,
    ContextRequestRequest,
    ContextRequestResponse,
    ContextRequestStatusResponse,
    ContextSectionOut,
    DeniedZoneOut,
    GrantRequest,
    SemanticCandidateOut,
)
from memory_gateway.security import AgentIdentity
from memory_gateway.policy import zone_requires_grant
from memory_gateway.service import (
    InvalidState,
    NotFound,
    PermissionDenied,
    as_utc_naive,
    get_access_grant,
    now_for_db_compare,
    request_access_grant,
)
from memory_gateway.db import AccessGrantRecord
from memory_gateway.types import AuditAction, GrantStatus, MemoryType, MemoryZone, Sensitivity

from .audit import audit_event
from .facts import readable_fact_cards
from .retrieval import RankedMemory, retrieve_for_context


SECTION_META = {
    "preferences": ("Preferences", {MemoryType.PREFERENCE.value}),
    "relationships": ("Relationships", {MemoryType.RELATIONSHIP.value}),
    "project_facts": ("Project Facts", {MemoryType.CONTEXT.value}),
    "procedures": ("Procedures", {MemoryType.PROCEDURE.value}),
    "lessons": ("Lessons", {MemoryType.LESSON.value}),
    "anti_patterns": ("Anti-Patterns", {MemoryType.ANTI_PATTERN.value}),
}


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _memory_line(item: RankedMemory) -> str:
    record = item.record
    return (
        f"- ({record.id}, {record.memory_zone}, {record.memory_type}, "
        f"score={item.score:.3f}) {record.content}"
    )


def _build_sections(items: list[RankedMemory]) -> list[ContextSectionOut]:
    grouped: dict[str, list[RankedMemory]] = defaultdict(list)
    for item in items:
        placed = False
        for key, (_, memory_types) in SECTION_META.items():
            if item.record.memory_type in memory_types:
                grouped[key].append(item)
                placed = True
                break
        if not placed:
            grouped["project_facts"].append(item)

    sections: list[ContextSectionOut] = []
    for key, (title, _) in SECTION_META.items():
        memories = grouped.get(key, [])
        if not memories:
            continue
        sections.append(
            ContextSectionOut(
                key=key,
                title=title,
                content="\n".join(_memory_line(item) for item in memories),
                source_memory_ids=[item.record.id for item in memories],
            )
        )
    return sections


def _fit_sections_to_budget(
    task: str,
    sections: list[ContextSectionOut],
    denied: list[DeniedZoneOut],
    max_tokens: int,
) -> tuple[str, list[ContextSectionOut], int]:
    kept: list[ContextSectionOut] = []
    lines = [
        "# Permissioned Memory Context",
        f"Task: {task.strip()}",
        "",
        "Use this context only for the current task. Do not reveal grant tokens or hidden memory.",
    ]
    for section in sections:
        tentative = lines + ["", f"## {section.title}", section.content]
        if _estimate_tokens("\n".join(tentative)) > max_tokens:
            continue
        lines = tentative
        kept.append(section)

    if denied:
        denied_lines = ["", "## Denied Or Missing Memory Zones"]
        denied_lines.extend(f"- {item.zone.value}: {item.reason}" for item in denied)
        tentative = lines + denied_lines
        if _estimate_tokens("\n".join(tentative)) <= max_tokens:
            lines = tentative

    lines.append("")
    lines.append("## Source Policy")
    lines.append("- All included memories passed SQL ACL, zone, status, and grant checks before ranking.")
    prompt = "\n".join(lines)
    return prompt, kept, _estimate_tokens(prompt)


def compose_context(
    session: Session,
    agent: AgentIdentity,
    request: ContextComposeRequest,
) -> ContextComposeResponse:
    retrieval = retrieve_for_context(
        session,
        agent,
        query=request.task,
        project_id=request.project_id,
        zones=request.zones,
        grant_token=request.grant_token,
        memory_types=request.memory_types,
        top_k=request.top_k,
        strict_grant=False,
        retrieval_mode=request.retrieval_mode,
    )
    allowed_ids = {item.record.id for item in retrieval.ranked}
    fact_cards = readable_fact_cards(
        session,
        allowed_memory_ids=allowed_ids,
        query=request.task,
        top_k=min(request.top_k, 8),
    )

    graph_cards = []
    if request.include_graph and allowed_ids:
        result = get_graph_client().search(
            tenant_id=agent.tenant_id,
            query=request.task,
            allowed_memory_ids=list(allowed_ids),
            top_k=min(request.top_k, 8),
        )
        if result.available:
            graph_cards = result.cards

    sections = _build_sections(retrieval.ranked)
    if fact_cards:
        sections.append(
            ContextSectionOut(
                key="facts",
                title="Structured Facts",
                content="\n".join(
                    f"- ({card.id}, {card.relation_type}, confidence={card.confidence}) {card.subtitle}"
                    for card in fact_cards
                ),
                source_memory_ids=list(
                    dict.fromkeys(
                        source_id
                        for card in fact_cards
                        for source_id in card.source_memory_ids
                    )
                ),
            )
        )
    if graph_cards:
        sections.append(
            ContextSectionOut(
                key="graph_relations",
                title="Graph Relations",
                content="\n".join(
                    f"- ({card.id}, {card.relation_type}) {card.subtitle}"
                    for card in graph_cards
                ),
                source_memory_ids=list(
                    dict.fromkeys(
                        source_id
                        for card in graph_cards
                        for source_id in card.source_memory_ids
                    )
                ),
            )
        )

    denied = [
        DeniedZoneOut(zone=item.zone, reason=item.reason)
        for item in retrieval.denied_zones
    ]
    prompt, kept_sections, token_estimate = _fit_sections_to_budget(
        request.task, sections, denied, request.max_tokens
    )
    audit_id = audit_event(
        session,
        agent,
        AuditAction.CONTEXT_COMPOSE,
        "context",
        retrieval.grant_id,
        {
            "task": request.task,
            "project_id": request.project_id,
            "zones": [zone.value for zone in request.zones],
            "candidate_count_after_acl": retrieval.candidate_count_after_acl,
            "returned_memory_ids": [item.record.id for item in retrieval.ranked],
            "denied_zones": [item.zone.value for item in retrieval.denied_zones],
            "token_estimate": token_estimate,
            "retrieval_mode": request.retrieval_mode,
        },
    )
    matched_summaries = [
        SemanticCandidateOut(
            memory_id=item.record.id,
            summary=item.record.semantic_summary or (item.record.content or "")[:260],
            content_preview=(item.record.content or "")[:260],
            zone=MemoryZone(item.record.memory_zone) if item.record.memory_zone else None,
            memory_type=MemoryType(item.record.memory_type),
            sensitivity=Sensitivity(item.record.sensitivity),
            score=round(item.score, 4),
            reason="Matched by summary-first retrieval.",
        )
        for item in retrieval.ranked
    ]
    return ContextComposeResponse(
        prompt_context=prompt,
        sections=kept_sections,
        source_cards=retrieval.source_cards,
        matched_summaries=matched_summaries,
        fact_cards=fact_cards,
        graph_cards=graph_cards,
        denied_zones=denied,
        audit_id=audit_id,
        token_estimate=token_estimate,
        candidate_count_after_acl=retrieval.candidate_count_after_acl,
    )


def request_context(
    session: Session,
    agent: AgentIdentity,
    request: ContextRequestRequest,
) -> ContextRequestResponse:
    private_zones = [zone for zone in request.zones if zone_requires_grant(zone)]
    if request.grant_token or not private_zones:
        context = compose_context(
            session,
            agent,
            ContextComposeRequest(
                task=request.task,
                project_id=request.project_id,
                zones=request.zones,
                grant_token=request.grant_token,
                memory_types=request.memory_types,
                max_tokens=request.max_tokens,
                include_graph=request.include_graph,
                top_k=request.top_k,
                retrieval_mode=request.retrieval_mode,
                use_llm_rerank=request.use_llm_rerank,
            ),
        )
        audit_id = audit_event(
            session,
            agent,
            AuditAction.CONTEXT_REQUEST,
            "context",
            context.audit_id,
            {
                "status": "ready",
                "project_id": request.project_id,
                "zones": [zone.value for zone in request.zones],
            },
        )
        return ContextRequestResponse(
            status="ready",
            context=context,
            denied_zones=context.denied_zones,
            message="Context is ready for the agent prompt.",
            audit_id=audit_id,
        )

    grant = request_access_grant(
        session,
        agent,
        GrantRequest(
            task_id=request.task_id or f"context-{abs(hash(request.task))}",
            purpose=request.purpose or f"Need memory context for: {request.task[:240]}",
            allowed_zones=private_zones,
            project_id=request.project_id,
            ttl_minutes=request.ttl_minutes,
        ),
    )
    grant_record = session.get(AccessGrantRecord, grant.id)
    if grant_record:
        grant_record.context_request = {
            "task": request.task,
            "project_id": request.project_id,
            "zones": [zone.value for zone in request.zones],
            "memory_types": [item.value for item in request.memory_types or []],
            "max_tokens": request.max_tokens,
            "include_graph": request.include_graph,
            "top_k": request.top_k,
            "retrieval_mode": request.retrieval_mode,
            "use_llm_rerank": request.use_llm_rerank,
        }
        session.flush()
    audit_id = audit_event(
        session,
        agent,
        AuditAction.CONTEXT_REQUEST,
        "access_grant",
        grant.id,
        {
            "status": "pending_grant",
            "project_id": request.project_id,
            "zones": [zone.value for zone in request.zones],
        },
    )
    return ContextRequestResponse(
        status="pending_grant",
        grant=grant,
        denied_zones=[
            DeniedZoneOut(zone=zone, reason="User approval is required before this zone can be composed.")
            for zone in private_zones
        ],
        message="Grant approval is required. Ask the user to approve it in the desktop app, then call compose with the returned token.",
        audit_id=audit_id,
    )


def _compose_request_from_grant(grant: AccessGrantRecord, grant_token: str | None) -> ContextComposeRequest:
    payload = grant.context_request or {}
    zones = payload.get("zones") or grant.allowed_zones or [MemoryZone.PUBLIC_PROFILE.value]
    memory_types = payload.get("memory_types") or None
    return ContextComposeRequest(
        task=payload.get("task") or grant.purpose,
        project_id=payload.get("project_id", grant.project_id),
        zones=[MemoryZone(zone) for zone in zones],
        grant_token=grant_token,
        memory_types=[MemoryType(item) for item in memory_types] if memory_types else None,
        max_tokens=int(payload.get("max_tokens") or 1200),
        include_graph=bool(payload.get("include_graph", True)),
        top_k=int(payload.get("top_k") or 8),
        retrieval_mode=str(payload.get("retrieval_mode") or "summary_first"),
        use_llm_rerank=bool(payload.get("use_llm_rerank", True)),
    )


def compose_approved_context_request(
    session: Session,
    agent: AgentIdentity,
    grant_id: str,
) -> ContextRequestStatusResponse:
    grant = session.get(AccessGrantRecord, grant_id)
    if not grant or grant.tenant_id != agent.tenant_id:
        raise NotFound("context request not found")
    if grant.agent_id != agent.agent_id and not agent.is_admin:
        raise PermissionDenied("agent cannot read this context request")
    if grant.status == GrantStatus.APPROVED.value and as_utc_naive(grant.expires_at) <= now_for_db_compare():
        grant.status = GrantStatus.EXPIRED.value
        session.flush()
    if grant.status != GrantStatus.APPROVED.value:
        audit_id = audit_event(
            session,
            agent,
            AuditAction.CONTEXT_REQUEST,
            "access_grant",
            grant.id,
            {"status": grant.status},
        )
        return ContextRequestStatusResponse(
            status=grant.status if grant.status != GrantStatus.PENDING.value else "pending_grant",
            grant=get_access_grant(session, agent, grant.id),
            message=f"Context request is {grant.status}.",
            audit_id=audit_id,
        )
    if not grant.token_hash:
        raise InvalidState("approved grant has no token hash")

    # Internal continuation: the agent does not receive the raw token here.
    # ACL is satisfied because the approved grant belongs to this agent/project/zones.
    context = compose_context_without_token(session, agent, grant)
    audit_id = audit_event(
        session,
        agent,
        AuditAction.CONTEXT_REQUEST,
        "access_grant",
        grant.id,
        {"status": "ready", "continued_without_token": True},
    )
    return ContextRequestStatusResponse(
        status="ready",
        context=context,
        grant=get_access_grant(session, agent, grant.id),
        message="Context is ready for the agent prompt.",
        audit_id=audit_id,
    )


def compose_context_without_token(
    session: Session,
    agent: AgentIdentity,
    grant: AccessGrantRecord,
) -> ContextComposeResponse:
    request = _compose_request_from_grant(grant, grant_token=None)
    from .retrieval import rank_records, rank_records_summary_first, _memory_card, _dedupe_ranked
    from .semantic import ensure_memory_summary

    zones = request.zones
    memory_types = request.memory_types
    query = request.task
    # Reuse the same ranking/composer pieces, but supply allowed records from the approved grant directly.
    allowed_zones = [MemoryZone(zone) for zone in grant.allowed_zones]
    if any(zone not in allowed_zones and zone_requires_grant(zone) for zone in zones):
        raise PermissionDenied("approved grant does not cover requested zones")
    from memory_gateway.db import MemoryRecord
    from memory_gateway.types import ProposalStatus
    from sqlalchemy import select
    records_query = select(MemoryRecord).where(
        MemoryRecord.tenant_id == agent.tenant_id,
        MemoryRecord.deleted_at.is_(None),
        MemoryRecord.status == ProposalStatus.APPROVED.value,
        MemoryRecord.memory_zone.in_([zone.value for zone in zones]),
    )
    if memory_types:
        records_query = records_query.where(MemoryRecord.memory_type.in_([item.value for item in memory_types]))
    records = list(session.scalars(records_query))
    allowed = []
    for record in records:
        if record.memory_zone != MemoryZone.PUBLIC_PROFILE.value and record.project_id != request.project_id:
            continue
        if record.memory_zone == MemoryZone.PUBLIC_PROFILE.value or MemoryZone(record.memory_zone) in allowed_zones:
            allowed.append(record)
    if request.retrieval_mode == "summary_first":
        for record in allowed:
            ensure_memory_summary(session, agent, record)
        ranked = _dedupe_ranked(rank_records_summary_first(query, allowed))[: request.top_k]
    else:
        ranked = _dedupe_ranked(rank_records(query, allowed))[: request.top_k]
    # Build a normal response from ranked items without requiring token revalidation.
    allowed_ids = {item.record.id for item in ranked}
    fact_cards = readable_fact_cards(
        session,
        allowed_memory_ids=allowed_ids,
        query=request.task,
        top_k=min(request.top_k, 8),
    )
    graph_cards = []
    if request.include_graph and allowed_ids:
        result = get_graph_client().search(
            tenant_id=agent.tenant_id,
            query=request.task,
            allowed_memory_ids=list(allowed_ids),
            top_k=min(request.top_k, 8),
        )
        if result.available:
            graph_cards = result.cards
    sections = _build_sections(ranked)
    if fact_cards:
        sections.append(
            ContextSectionOut(
                key="facts",
                title="Structured Facts",
                content="\n".join(
                    f"- ({card.id}, {card.relation_type}, confidence={card.confidence}) {card.subtitle}"
                    for card in fact_cards
                ),
                source_memory_ids=list(
                    dict.fromkeys(source_id for card in fact_cards for source_id in card.source_memory_ids)
                ),
            )
        )
    if graph_cards:
        sections.append(
            ContextSectionOut(
                key="graph_relations",
                title="Graph Relations",
                content="\n".join(f"- ({card.id}, {card.relation_type}) {card.subtitle}" for card in graph_cards),
                source_memory_ids=list(
                    dict.fromkeys(source_id for card in graph_cards for source_id in card.source_memory_ids)
                ),
            )
        )
    prompt, kept_sections, token_estimate = _fit_sections_to_budget(
        request.task, sections, [], request.max_tokens
    )
    audit_id = audit_event(
        session,
        agent,
        AuditAction.CONTEXT_COMPOSE,
        "context",
        grant.id,
        {
            "task": request.task,
            "project_id": request.project_id,
            "zones": [zone.value for zone in request.zones],
            "candidate_count_after_acl": len(allowed),
            "returned_memory_ids": [item.record.id for item in ranked],
            "continued_without_token": True,
            "retrieval_mode": request.retrieval_mode,
        },
    )
    matched_summaries = [
        SemanticCandidateOut(
            memory_id=item.record.id,
            summary=item.record.semantic_summary or (item.record.content or "")[:260],
            content_preview=(item.record.content or "")[:260],
            zone=MemoryZone(item.record.memory_zone) if item.record.memory_zone else None,
            memory_type=MemoryType(item.record.memory_type),
            sensitivity=Sensitivity(item.record.sensitivity),
            score=round(item.score, 4),
            reason="Matched by summary-first retrieval.",
        )
        for item in ranked
    ]
    return ContextComposeResponse(
        prompt_context=prompt,
        sections=kept_sections,
        source_cards=[
            _memory_card(
                item.record,
                item.score,
                "Visible after approved context request grant checks.",
            )
            for item in ranked
        ],
        matched_summaries=matched_summaries,
        fact_cards=fact_cards,
        graph_cards=graph_cards,
        denied_zones=[],
        audit_id=audit_id,
        token_estimate=token_estimate,
        candidate_count_after_acl=len(allowed),
    )
