from __future__ import annotations

from difflib import unified_diff

from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_gateway.db import (
    AuditEventRecord,
    MemoryFactRecord,
    MemoryRecord,
    MemoryVersionRecord,
    utcnow,
)
from memory_gateway.embedding import embed_text, tokenize
from memory_gateway.graph import get_graph_client
from memory_gateway.policy import classify_sensitivity, max_sensitivity, zone_default_sensitivity
from memory_gateway.schemas import (
    AuditOut,
    MemoryCardOut,
    MemoryDetailResponse,
    MemoryListResponse,
    MemoryOut,
    MemoryPatchRequest,
    MemoryRestoreRequest,
    MemorySupersedeRequest,
    MemoryVersionOut,
    SearchDisplayOut,
)
from memory_gateway.security import AgentIdentity
from memory_gateway.service import InvalidState, NotFound, PermissionDenied, redact_sensitive_content
from memory_gateway.types import (
    AuditAction,
    ContentKind,
    FactStatus,
    MemoryType,
    MemoryZone,
    ProposalStatus,
    Sensitivity,
    Visibility,
)

from .audit import audit_event, new_id
from .facts import fact_to_card, mark_facts_inactive_for_memory, upsert_facts_for_memory
from .retrieval import memory_to_out
from .semantic import apply_semantic_summary_to_memory, generate_memory_summary


def _normalize_project_for_zone(zone: MemoryZone | None, project_id: str | None) -> str | None:
    if zone == MemoryZone.PUBLIC_PROFILE:
        return None
    if zone == MemoryZone.WORK_CONTEXT and not project_id:
        raise InvalidState("work_context memories require a project_id")
    return project_id


def _visibility_for(zone: MemoryZone | None, project_id: str | None) -> Visibility:
    if zone == MemoryZone.PUBLIC_PROFILE:
        return Visibility.PUBLIC
    if project_id:
        return Visibility.PROJECT
    return Visibility.PRIVATE


def _diff(old: str, new: str) -> list[str]:
    return list(
        unified_diff(
            old.splitlines(),
            new.splitlines(),
            fromfile="before",
            tofile="after",
            lineterm="",
        )
    )[:80]


def _version_to_out(record: MemoryVersionRecord) -> MemoryVersionOut:
    return MemoryVersionOut(
        id=record.id,
        memory_id=record.memory_id,
        previous_memory_id=record.previous_memory_id,
        event=record.event,
        actor_agent_id=record.actor_agent_id,
        details=record.details or {},
        created_at=record.created_at,
    )


def _audit_to_out(record: AuditEventRecord) -> AuditOut:
    return AuditOut(
        id=record.id,
        agent_id=record.agent_id,
        action=record.action,
        resource_type=record.resource_type,
        resource_id=record.resource_id,
        details=record.details or {},
        created_at=record.created_at,
    )


def _memory_card(record: MemoryRecord) -> MemoryCardOut:
    zone = MemoryZone(record.memory_zone) if record.memory_zone else None
    status = "deleted" if record.deleted_at is not None else record.status
    return MemoryCardOut(
        id=record.id,
        title=f"{zone.value if zone else 'unzone'} / {record.memory_type}",
        subtitle=f"{status} / {record.source}",
        zone=zone,
        memory_type=MemoryType(record.memory_type),
        sensitivity=Sensitivity(record.sensitivity),
        source=record.source,
        why_visible="Visible in the memory editor for this tenant and selected scope.",
        preview=(record.content or "")[:260],
        score=None,
    )


def _memory_out(record: MemoryRecord) -> MemoryOut:
    output = memory_to_out(record)
    if record.deleted_at is not None:
        output.status = "deleted"
    return output


def _display(memories: list[MemoryOut], query: str | None) -> SearchDisplayOut:
    cards = []
    by_id: dict[str, MemoryOut] = {memory.id: memory for memory in memories}
    # The display card type expects source/preview fields not carried by MemoryOut directly.
    # Keep it lightweight by rebuilding from MemoryOut.
    for memory in memories:
        zone = memory.memory_zone
        cards.append(
            MemoryCardOut(
                id=memory.id,
                title=f"{zone.value if zone else 'unzone'} / {memory.memory_type.value}",
                subtitle=f"{memory.status} / {memory.source}",
                zone=zone,
                memory_type=memory.memory_type,
                sensitivity=memory.sensitivity,
                source=memory.source,
                why_visible="Visible in memory editor after tenant and scope filtering.",
                preview=memory.content[:260],
                score=memory.score,
            )
        )
    summary = f"{len(by_id)} memories"
    if query:
        summary += f" matching {query!r}"
    return SearchDisplayOut(summary=summary, cards=cards)


def _require_admin(agent: AgentIdentity, action: str) -> None:
    if not agent.is_admin:
        raise PermissionDenied(f"only admin agents can {action}")


def _get_memory(session: Session, agent: AgentIdentity, memory_id: str) -> MemoryRecord:
    record = session.get(MemoryRecord, memory_id)
    if not record or record.tenant_id != agent.tenant_id:
        raise NotFound("memory not found")
    return record


def _record_version(
    session: Session,
    agent: AgentIdentity,
    memory: MemoryRecord,
    *,
    event: str,
    previous_memory_id: str | None = None,
    details: dict | None = None,
) -> None:
    session.add(
        MemoryVersionRecord(
            id=new_id("ver"),
            tenant_id=memory.tenant_id,
            memory_id=memory.id,
            previous_memory_id=previous_memory_id,
            event=event,
            actor_agent_id=agent.agent_id,
            details=details or {},
        )
    )


def _reindex_memory(session: Session, agent: AgentIdentity, memory: MemoryRecord) -> None:
    mark_facts_inactive_for_memory(session, agent, memory.id)
    memory.embedding = embed_text(memory.content or "")
    zone = MemoryZone(memory.memory_zone) if memory.memory_zone else MemoryZone.PUBLIC_PROFILE
    semantic = generate_memory_summary(session, agent, memory.content or "", memory.project_id, zone)
    apply_semantic_summary_to_memory(memory, semantic)
    upsert_facts_for_memory(session, agent, memory)
    graph_result = get_graph_client().upsert_memory(memory)
    audit_event(
        session,
        agent,
        AuditAction.GRAPH_EXTRACT,
        "memory",
        memory.id,
        {
            "graph_available": graph_result.available,
            "indexed_count": graph_result.indexed_count,
            "reason": graph_result.reason,
        },
    )


def list_memories_for_editor(
    session: Session,
    agent: AgentIdentity,
    *,
    project_id: str | None = None,
    zone: MemoryZone | None = None,
    memory_type: MemoryType | None = None,
    status: str | None = None,
    query: str | None = None,
    limit: int = 100,
) -> MemoryListResponse:
    _require_admin(agent, "list memories")
    stmt = select(MemoryRecord).where(MemoryRecord.tenant_id == agent.tenant_id)
    if project_id is not None:
        stmt = stmt.where(MemoryRecord.project_id == project_id)
    if zone is not None:
        stmt = stmt.where(MemoryRecord.memory_zone == zone.value)
    if memory_type is not None:
        stmt = stmt.where(MemoryRecord.memory_type == memory_type.value)
    if status == "deleted":
        stmt = stmt.where(MemoryRecord.deleted_at.is_not(None))
    elif status is not None:
        stmt = stmt.where(MemoryRecord.status == status)
        stmt = stmt.where(MemoryRecord.deleted_at.is_(None))
    else:
        stmt = stmt.where(MemoryRecord.deleted_at.is_(None))
    records = list(session.scalars(stmt))
    if query:
        terms = set(tokenize(query))
        records = [
            record
            for record in records
            if terms & set(tokenize(" ".join([record.content or "", " ".join(record.tags or [])])))
        ]
    records.sort(key=lambda record: record.created_at, reverse=True)
    memories = [_memory_out(record) for record in records[:limit]]
    audit_event(
        session,
        agent,
        AuditAction.SEARCH,
        "memory_editor",
        None,
        {"project_id": project_id, "zone": zone.value if zone else None, "status": status},
    )
    return MemoryListResponse(memories=memories, display=_display(memories, query))


def memory_timeline(
    session: Session,
    agent: AgentIdentity,
    memory_id: str,
) -> list[MemoryVersionOut]:
    memory = _get_memory(session, agent, memory_id)
    versions = list(
        session.scalars(
            select(MemoryVersionRecord).where(
                MemoryVersionRecord.tenant_id == agent.tenant_id,
                MemoryVersionRecord.memory_id == memory.id,
            )
        )
    )
    if memory.superseded_by_id:
        versions.extend(
            list(
                session.scalars(
                    select(MemoryVersionRecord).where(
                        MemoryVersionRecord.tenant_id == agent.tenant_id,
                        MemoryVersionRecord.previous_memory_id == memory.id,
                    )
                )
            )
        )
    versions.sort(key=lambda record: record.created_at)
    return [_version_to_out(record) for record in versions]


def memory_detail(
    session: Session,
    agent: AgentIdentity,
    memory_id: str,
) -> MemoryDetailResponse:
    _require_admin(agent, "view memory details")
    memory = _get_memory(session, agent, memory_id)
    facts = list(
        session.scalars(
            select(MemoryFactRecord).where(
                MemoryFactRecord.source_memory_ids.contains([memory.id])
            )
        )
    )
    audits = list(
        session.scalars(
            select(AuditEventRecord)
            .where(
                AuditEventRecord.tenant_id == agent.tenant_id,
                AuditEventRecord.resource_id == memory.id,
            )
            .order_by(AuditEventRecord.created_at.desc())
        )
    )[:20]
    return MemoryDetailResponse(
        memory=_memory_out(memory),
        facts=[
            fact_to_card(fact, "Visible in memory editor for source inspection.")
            for fact in facts
            if fact.status == FactStatus.ACTIVE.value
        ],
        timeline=memory_timeline(session, agent, memory_id),
        audit=[_audit_to_out(record) for record in audits],
    )


def patch_memory(
    session: Session,
    agent: AgentIdentity,
    memory_id: str,
    request: MemoryPatchRequest,
) -> MemoryDetailResponse:
    _require_admin(agent, "edit memories")
    memory = _get_memory(session, agent, memory_id)
    old = {
        "content": memory.content,
        "tags": list(memory.tags or []),
        "memory_type": memory.memory_type,
        "memory_zone": memory.memory_zone,
        "project_id": memory.project_id,
        "status": memory.status,
    }
    zone = request.memory_zone or (MemoryZone(memory.memory_zone) if memory.memory_zone else None)
    project_id = request.project_id if request.project_id is not None else memory.project_id
    project_id = _normalize_project_for_zone(zone, project_id)
    if request.content is not None:
        redacted, _ = redact_sensitive_content(request.content)
        memory.content = redacted
        memory.redacted = redacted != request.content
        memory.sensitivity = max_sensitivity(
            classify_sensitivity(redacted),
            zone_default_sensitivity(zone) if zone else Sensitivity.LOW,
        ).value
    if request.tags is not None:
        memory.tags = request.tags
    if request.memory_type is not None:
        memory.memory_type = request.memory_type.value
    if zone is not None:
        memory.memory_zone = zone.value
    memory.project_id = project_id
    memory.visibility = _visibility_for(zone, project_id).value
    _record_version(
        session,
        agent,
        memory,
        event="edited",
        details={
            "before": old,
            "after": {
                "content": memory.content,
                "tags": memory.tags,
                "memory_type": memory.memory_type,
                "memory_zone": memory.memory_zone,
                "project_id": memory.project_id,
                "status": memory.status,
            },
            "diff": _diff(old["content"], memory.content),
            "reason": request.reason,
        },
    )
    _reindex_memory(session, agent, memory)
    session.flush()
    audit_event(session, agent, AuditAction.APPROVE, "memory", memory.id, {"event": "edited"})
    return memory_detail(session, agent, memory.id)


def supersede_memory(
    session: Session,
    agent: AgentIdentity,
    memory_id: str,
    request: MemorySupersedeRequest,
) -> MemoryDetailResponse:
    _require_admin(agent, "supersede memories")
    old = _get_memory(session, agent, memory_id)
    if old.status != ProposalStatus.APPROVED.value:
        raise InvalidState(f"memory is {old.status}, not approved")
    if request.new_memory_id:
        new = _get_memory(session, agent, request.new_memory_id)
        if new.project_id != old.project_id:
            raise InvalidState("cannot supersede memory across project boundaries")
    else:
        if not request.content:
            raise InvalidState("content or new_memory_id is required")
        redacted, _ = redact_sensitive_content(request.content)
        zone = request.memory_zone or (MemoryZone(old.memory_zone) if old.memory_zone else MemoryZone.PUBLIC_PROFILE)
        project_id = _normalize_project_for_zone(
            zone,
            request.project_id if request.project_id is not None else old.project_id,
        )
        sensitivity = max_sensitivity(
            classify_sensitivity(redacted),
            zone_default_sensitivity(zone),
        )
        new = MemoryRecord(
            id=new_id("mem"),
            tenant_id=old.tenant_id,
            project_id=project_id,
            owner_user_id=old.owner_user_id,
            visibility=_visibility_for(zone, project_id).value,
            allowed_agent_ids=list(old.allowed_agent_ids or []),
            denied_agent_ids=list(old.denied_agent_ids or []),
            memory_type=(request.memory_type or MemoryType(old.memory_type)).value,
            memory_zone=zone.value,
            content_kind=old.content_kind or ContentKind.TEXT.value,
            capture_source=old.capture_source,
            source_url=old.source_url,
            source_title=old.source_title,
            asset_path=old.asset_path,
            redacted=redacted != request.content,
            content=redacted,
            tags=request.tags if request.tags is not None else list(old.tags or []),
            sensitivity=sensitivity.value,
            source=f"supersede:{old.id}",
            embedding=embed_text(redacted),
            status=ProposalStatus.APPROVED.value,
            created_by_agent_id=agent.agent_id,
        )
        semantic = generate_memory_summary(session, agent, redacted, project_id, zone)
        apply_semantic_summary_to_memory(new, semantic)
        session.add(new)
        session.flush()
    old.status = ProposalStatus.SUPERSEDED.value
    old.superseded_by_id = new.id
    mark_facts_inactive_for_memory(session, agent, old.id)
    _reindex_memory(session, agent, new)
    _record_version(
        session,
        agent,
        new,
        event="supersedes",
        previous_memory_id=old.id,
        details={
            "previous_content": old.content,
            "new_content": new.content,
            "diff": _diff(old.content, new.content),
            "reason": request.reason,
        },
    )
    _record_version(
        session,
        agent,
        old,
        event="superseded",
        previous_memory_id=None,
        details={"superseded_by_id": new.id, "reason": request.reason},
    )
    session.flush()
    audit_event(
        session,
        agent,
        AuditAction.MEMORY_SUPERSEDE,
        "memory",
        new.id,
        {"previous_memory_id": old.id},
    )
    return memory_detail(session, agent, new.id)


def restore_memory(
    session: Session,
    agent: AgentIdentity,
    memory_id: str,
    request: MemoryRestoreRequest,
) -> MemoryDetailResponse:
    _require_admin(agent, "restore memories")
    memory = _get_memory(session, agent, memory_id)
    if memory.status == ProposalStatus.APPROVED.value and memory.deleted_at is None:
        raise InvalidState("memory is already approved")
    memory.status = ProposalStatus.APPROVED.value
    memory.deleted_at = None
    memory.superseded_by_id = None
    _reindex_memory(session, agent, memory)
    _record_version(
        session,
        agent,
        memory,
        event="restored",
        details={"reason": request.reason},
    )
    session.flush()
    audit_event(session, agent, AuditAction.APPROVE, "memory", memory.id, {"event": "restored"})
    return memory_detail(session, agent, memory.id)
