from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_gateway.db import MemoryRecord, SharePackRecord, utcnow
from memory_gateway.schemas import (
    DisplayOut,
    MemoryCardOut,
    SemanticCandidateOut,
    SharePackComposeRequest,
    SharePackComposeResponse,
    SharePackCreateRequest,
    SharePackCreateResponse,
    SharePackOut,
    SharePackPreviewRequest,
    SharePackPreviewResponse,
    SharePackScopeOut,
)
from memory_gateway.security import AgentIdentity
from memory_gateway.service import InvalidState, NotFound, PermissionDenied, as_utc_naive, now_for_db_compare
from memory_gateway.types import AuditAction, MemoryType, MemoryZone, ProposalStatus, Sensitivity, SharePackStatus, Visibility

from .audit import audit_event, new_id
from .context import _build_sections, _estimate_tokens, _fit_sections_to_budget
from .retrieval import _dedupe_ranked, _memory_card, rank_records_summary_first
from .semantic import ensure_memory_summary


DEFAULT_SHARE_ZONES = [MemoryZone.WORK_CONTEXT]
DEFAULT_SHARE_TYPES = [
    MemoryType.CONTEXT,
    MemoryType.RELATIONSHIP,
    MemoryType.PREFERENCE,
    MemoryType.PROCEDURE,
    MemoryType.LESSON,
    MemoryType.ANTI_PATTERN,
]
FORBIDDEN_SHARE_ZONES = {
    MemoryZone.PUBLIC_PROFILE,
    MemoryZone.PERSONAL_CONTEXT,
    MemoryZone.SENSITIVE_VAULT,
    MemoryZone.PAYMENT_REFERENCE,
}


@dataclass(frozen=True)
class ShareContextBuild:
    prompt_context: str
    source_cards: list[MemoryCardOut]
    matched_summaries: list[SemanticCandidateOut]
    scope: SharePackScopeOut
    excluded_summary: list[str]
    token_estimate: int
    candidate_count_after_policy: int


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _raw_share_token() -> str:
    return f"sp_{secrets.token_urlsafe(32)}"


def _normalize_zones(zones: list[MemoryZone] | None) -> list[MemoryZone]:
    requested = zones or DEFAULT_SHARE_ZONES
    allowed = [zone for zone in requested if zone == MemoryZone.WORK_CONTEXT]
    return list(dict.fromkeys(allowed)) or [MemoryZone.WORK_CONTEXT]


def _normalize_memory_types(memory_types: list[MemoryType] | None) -> list[MemoryType]:
    requested = memory_types or DEFAULT_SHARE_TYPES
    return list(dict.fromkeys(requested))


def _policy_summary() -> list[str]:
    return [
        "Only approved project-scoped work memories are included.",
        "Personal, sensitive, payment, private, deleted, pending, and superseded memories are excluded.",
        "The share token grants prompt-ready onboarding context only, not raw database access.",
    ]


def _scope(
    project_id: str,
    zones: list[MemoryZone],
    memory_types: list[MemoryType],
    tags: list[str] | None,
    excluded_memory_ids: list[str] | None,
) -> SharePackScopeOut:
    return SharePackScopeOut(
        project_id=project_id,
        allowed_zones=zones,
        allowed_memory_types=memory_types,
        allowed_tags=list(dict.fromkeys(tags or [])),
        excluded_memory_ids=list(dict.fromkeys(excluded_memory_ids or [])),
        policy_summary=_policy_summary(),
    )


def _share_pack_to_out(record: SharePackRecord, token: str | None = None) -> SharePackOut:
    status = SharePackStatus(record.status)
    now = now_for_db_compare()
    expires_at = as_utc_naive(record.expires_at)
    if status == SharePackStatus.ACTIVE and expires_at <= now:
        status = SharePackStatus.EXPIRED
    max_uses = int(record.max_uses or 0)
    use_count = int(record.use_count or 0)
    uses_remaining = max(max_uses - use_count, 0)
    zones = [MemoryZone(zone) for zone in (record.allowed_zones or [])]
    memory_types = [MemoryType(item) for item in (record.allowed_memory_types or [])]
    return SharePackOut(
        id=record.id,
        project_id=record.project_id,
        name=record.name,
        description=record.description or "",
        recipient_label=record.recipient_label or "",
        created_by_agent_id=record.created_by_agent_id,
        scope=_scope(
            record.project_id,
            zones,
            memory_types,
            record.allowed_tags or [],
            record.excluded_memory_ids or [],
        ),
        status=status,
        expires_at=record.expires_at,
        max_uses=max_uses,
        use_count=use_count,
        uses_remaining=uses_remaining,
        created_at=record.created_at,
        revoked_at=record.revoked_at,
        token=token,
        display=DisplayOut(
            title=record.name,
            subtitle=f"Project {record.project_id} share pack for {record.recipient_label or 'collaborator'}",
            badges=[status.value, f"{uses_remaining} uses left"],
            reasons=_policy_summary(),
            warnings=[] if status == SharePackStatus.ACTIVE else [f"Share pack is {status.value}."],
            primary_action="Copy token" if token else None,
        ),
    )


def _enforce_share_admin(agent: AgentIdentity) -> None:
    if not (agent.is_admin or agent.can_write):
        raise PermissionDenied("only admin or writer agents can manage share packs")


def _candidate_records(
    session: Session,
    agent: AgentIdentity,
    *,
    project_id: str,
    zones: list[MemoryZone],
    memory_types: list[MemoryType],
    tags: list[str],
    excluded_memory_ids: list[str],
    require_project_access: bool,
) -> tuple[list[MemoryRecord], list[str]]:
    if any(zone in FORBIDDEN_SHARE_ZONES for zone in zones) or any(zone != MemoryZone.WORK_CONTEXT for zone in zones):
        zones = [MemoryZone.WORK_CONTEXT]
    excluded_summary = [
        "Personal, sensitive, payment, private, deleted, pending, and superseded memories are always excluded."
    ]
    if require_project_access and not agent.is_admin and "*" not in agent.allowed_projects and project_id not in agent.allowed_projects:
        raise PermissionDenied("agent cannot create share packs for this project")

    query = select(MemoryRecord).where(
        MemoryRecord.tenant_id == agent.tenant_id,
        MemoryRecord.project_id == project_id,
        MemoryRecord.deleted_at.is_(None),
        MemoryRecord.superseded_by_id.is_(None),
        MemoryRecord.status == ProposalStatus.APPROVED.value,
        MemoryRecord.visibility == Visibility.PROJECT.value,
        MemoryRecord.memory_zone.in_([zone.value for zone in zones]),
        MemoryRecord.memory_type.in_([item.value for item in memory_types]),
        MemoryRecord.sensitivity != Sensitivity.HIGH.value,
    )
    records = list(session.scalars(query))
    excluded_ids = set(excluded_memory_ids or [])
    if excluded_ids:
        records = [record for record in records if record.id not in excluded_ids]
        excluded_summary.append(f"{len(excluded_ids)} manually excluded memory id(s) were omitted.")
    if tags:
        tag_set = set(tags)
        records = [record for record in records if tag_set.intersection(set(record.tags or []))]
        excluded_summary.append("Tag filter applied; only memories with selected tags were included.")
    return records, excluded_summary


def _build_share_context(
    session: Session,
    agent: AgentIdentity,
    *,
    project_id: str,
    task: str,
    zones: list[MemoryZone],
    memory_types: list[MemoryType],
    tags: list[str],
    excluded_memory_ids: list[str],
    max_tokens: int,
    top_k: int,
    require_project_access: bool = True,
) -> ShareContextBuild:
    records, excluded_summary = _candidate_records(
        session,
        agent,
        project_id=project_id,
        zones=zones,
        memory_types=memory_types,
        tags=tags,
        excluded_memory_ids=excluded_memory_ids,
        require_project_access=require_project_access,
    )
    for record in records:
        ensure_memory_summary(session, agent, record)
    ranked = _dedupe_ranked(rank_records_summary_first(task, records))[:top_k]
    sections = _build_sections(ranked)
    prompt, kept_sections, token_estimate = _fit_sections_to_budget(task, sections, [], max_tokens)
    prompt = prompt.replace("# Permissioned Memory Context", f"# Shared Project Context: {project_id}", 1)
    prompt = prompt.replace(
        "- All included memories passed SQL ACL, zone, status, and grant checks before ranking.",
        "\n".join(
            [
                "- This context was generated from a Project Memory Share Pack.",
                "- Only approved project-scoped work memory is included.",
                "- Personal, sensitive, payment, private, deleted, and superseded memories are excluded.",
            ]
        ),
    )
    token_estimate = _estimate_tokens(prompt)
    kept_ids = {memory_id for section in kept_sections for memory_id in section.source_memory_ids}
    kept_ranked = [item for item in ranked if item.record.id in kept_ids]
    source_cards = [
        _memory_card(
            item.record,
            item.score,
            "Visible through a Project Memory Share Pack scope, not through personal or sensitive grants.",
        )
        for item in kept_ranked
    ]
    matched = [
        SemanticCandidateOut(
            memory_id=item.record.id,
            summary=item.record.semantic_summary or (item.record.content or "")[:260],
            content_preview=(item.record.content or "")[:260],
            zone=MemoryZone(item.record.memory_zone) if item.record.memory_zone else None,
            memory_type=MemoryType(item.record.memory_type),
            sensitivity=Sensitivity(item.record.sensitivity),
            score=round(item.score, 4),
            reason="Matched by share-pack summary-first retrieval.",
        )
        for item in kept_ranked
    ]
    return ShareContextBuild(
        prompt_context=prompt,
        source_cards=source_cards,
        matched_summaries=matched,
        scope=_scope(project_id, zones, memory_types, tags, excluded_memory_ids),
        excluded_summary=excluded_summary,
        token_estimate=token_estimate,
        candidate_count_after_policy=len(records),
    )


def preview_share_pack(
    session: Session,
    agent: AgentIdentity,
    request: SharePackPreviewRequest,
) -> SharePackPreviewResponse:
    _enforce_share_admin(agent)
    zones = _normalize_zones(request.allowed_zones)
    memory_types = _normalize_memory_types(request.allowed_memory_types)
    build = _build_share_context(
        session,
        agent,
        project_id=request.project_id,
        task=request.task,
        zones=zones,
        memory_types=memory_types,
        tags=request.allowed_tags,
        excluded_memory_ids=request.excluded_memory_ids,
        max_tokens=request.max_tokens,
        top_k=request.top_k,
        require_project_access=True,
    )
    audit_id = audit_event(
        session,
        agent,
        AuditAction.SHARE_PREVIEW,
        "share_pack",
        None,
        {
            "project_id": request.project_id,
            "zones": [zone.value for zone in zones],
            "memory_types": [item.value for item in memory_types],
            "candidate_count_after_policy": build.candidate_count_after_policy,
            "returned_memory_ids": [card.id for card in build.source_cards],
        },
    )
    return SharePackPreviewResponse(
        prompt_context=build.prompt_context,
        source_cards=build.source_cards,
        matched_summaries=build.matched_summaries,
        scope=build.scope,
        excluded_summary=build.excluded_summary,
        audit_id=audit_id,
        token_estimate=build.token_estimate,
        candidate_count_after_policy=build.candidate_count_after_policy,
        display=DisplayOut(
            title=f"Share preview for {request.project_id}",
            subtitle=f"{len(build.source_cards)} memory card(s) will be included.",
            badges=["preview", "work_context only"],
            reasons=build.scope.policy_summary,
            warnings=build.excluded_summary,
            primary_action="Create Share Pack",
            safe_preview=build.prompt_context[:500],
        ),
    )


def create_share_pack(
    session: Session,
    agent: AgentIdentity,
    request: SharePackCreateRequest,
) -> SharePackCreateResponse:
    _enforce_share_admin(agent)
    zones = _normalize_zones(request.allowed_zones)
    memory_types = _normalize_memory_types(request.allowed_memory_types)
    build = _build_share_context(
        session,
        agent,
        project_id=request.project_id,
        task=request.task,
        zones=zones,
        memory_types=memory_types,
        tags=request.allowed_tags,
        excluded_memory_ids=request.excluded_memory_ids,
        max_tokens=request.max_tokens,
        top_k=request.top_k,
        require_project_access=True,
    )
    token = _raw_share_token()
    record = SharePackRecord(
        id=new_id("sp"),
        tenant_id=agent.tenant_id,
        project_id=request.project_id,
        name=request.name,
        description=request.description,
        recipient_label=request.recipient_label,
        created_by_agent_id=agent.agent_id,
        allowed_zones=[zone.value for zone in zones],
        allowed_memory_types=[item.value for item in memory_types],
        allowed_tags=list(dict.fromkeys(request.allowed_tags)),
        excluded_memory_ids=list(dict.fromkeys(request.excluded_memory_ids)),
        token_hash=_hash_token(token),
        status=SharePackStatus.ACTIVE.value,
        expires_at=utcnow() + timedelta(days=request.ttl_days),
        max_uses=request.max_uses,
        use_count=0,
        created_at=utcnow(),
    )
    session.add(record)
    session.flush()
    audit_id = audit_event(
        session,
        agent,
        AuditAction.SHARE_CREATE,
        "share_pack",
        record.id,
        {
            "project_id": record.project_id,
            "zones": record.allowed_zones,
            "memory_types": record.allowed_memory_types,
            "max_uses": record.max_uses,
            "expires_at": record.expires_at.isoformat(),
            "initial_memory_ids": [card.id for card in build.source_cards],
        },
    )
    return SharePackCreateResponse(
        share_pack=_share_pack_to_out(record, token=token),
        prompt_context=build.prompt_context,
        source_cards=build.source_cards,
        matched_summaries=build.matched_summaries,
        audit_id=audit_id,
    )


def list_share_packs(
    session: Session,
    agent: AgentIdentity,
    status: SharePackStatus | None = None,
) -> list[SharePackOut]:
    _enforce_share_admin(agent)
    query = select(SharePackRecord).where(SharePackRecord.tenant_id == agent.tenant_id)
    if status:
        query = query.where(SharePackRecord.status == status.value)
    records = list(session.scalars(query.order_by(SharePackRecord.created_at.desc())))
    now = now_for_db_compare()
    for record in records:
        if record.status == SharePackStatus.ACTIVE.value and as_utc_naive(record.expires_at) <= now:
            record.status = SharePackStatus.EXPIRED.value
    session.flush()
    return [_share_pack_to_out(record) for record in records]


def compose_share_pack(
    session: Session,
    agent: AgentIdentity,
    share_pack_id: str,
    request: SharePackComposeRequest,
) -> SharePackComposeResponse:
    record = session.get(SharePackRecord, share_pack_id)
    if not record or record.tenant_id != agent.tenant_id:
        raise NotFound("share pack not found")
    if _hash_token(request.share_token) != record.token_hash:
        raise PermissionDenied("invalid share token")
    if record.status == SharePackStatus.ACTIVE.value and as_utc_naive(record.expires_at) <= now_for_db_compare():
        record.status = SharePackStatus.EXPIRED.value
        session.flush()
    if record.status != SharePackStatus.ACTIVE.value:
        raise InvalidState(f"share pack is {record.status}")
    if int(record.use_count or 0) >= int(record.max_uses or 0):
        raise InvalidState("share pack max uses exhausted")
    zones = _normalize_zones([MemoryZone(zone) for zone in (record.allowed_zones or [])])
    memory_types = _normalize_memory_types([MemoryType(item) for item in (record.allowed_memory_types or [])])
    build = _build_share_context(
        session,
        agent,
        project_id=record.project_id,
        task=request.task,
        zones=zones,
        memory_types=memory_types,
        tags=record.allowed_tags or [],
        excluded_memory_ids=record.excluded_memory_ids or [],
        max_tokens=request.max_tokens,
        top_k=request.top_k,
        require_project_access=False,
    )
    record.use_count = int(record.use_count or 0) + 1
    session.flush()
    audit_id = audit_event(
        session,
        agent,
        AuditAction.SHARE_COMPOSE,
        "share_pack",
        record.id,
        {
            "project_id": record.project_id,
            "task": request.task,
            "use_count": record.use_count,
            "returned_memory_ids": [card.id for card in build.source_cards],
            "token_estimate": build.token_estimate,
        },
    )
    return SharePackComposeResponse(
        share_pack=_share_pack_to_out(record),
        prompt_context=build.prompt_context,
        source_cards=build.source_cards,
        matched_summaries=build.matched_summaries,
        scope=build.scope,
        audit_id=audit_id,
        token_estimate=build.token_estimate,
        display=DisplayOut(
            title=f"Shared context for {record.project_id}",
            subtitle=f"{len(build.source_cards)} approved project memory card(s) included.",
            badges=["share_pack", f"{record.max_uses - record.use_count} uses left"],
            reasons=build.scope.policy_summary,
            warnings=build.excluded_summary,
            safe_preview=build.prompt_context[:500],
        ),
    )


def revoke_share_pack(
    session: Session,
    agent: AgentIdentity,
    share_pack_id: str,
) -> SharePackOut:
    _enforce_share_admin(agent)
    record = session.get(SharePackRecord, share_pack_id)
    if not record or record.tenant_id != agent.tenant_id:
        raise NotFound("share pack not found")
    if record.status != SharePackStatus.REVOKED.value:
        record.status = SharePackStatus.REVOKED.value
        record.revoked_at = utcnow()
        session.flush()
    audit_event(
        session,
        agent,
        AuditAction.SHARE_REVOKE,
        "share_pack",
        record.id,
        {"project_id": record.project_id, "use_count": record.use_count},
    )
    return _share_pack_to_out(record)
