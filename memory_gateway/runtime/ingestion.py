from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

import re

from memory_gateway.db import CaptureEventRecord, MemoryInboxItemRecord, MemoryRecord, MemoryVersionRecord, utcnow
from memory_gateway.embedding import cosine_similarity, embed_text
from memory_gateway.graph import get_graph_client
from memory_gateway.policy import classify_sensitivity, max_sensitivity, zone_default_sensitivity
from memory_gateway.schemas import (
    DisplayOut,
    ExtractedFactOut,
    ExtractionPreviewRequest,
    ExtractionPreviewResponse,
    InboxApproveRequest,
    InboxItemOut,
    InboxMergeRequest,
    InboxRejectRequest,
    IngestRequest,
    IngestResponse,
    MemoryRelationshipSuggestionOut,
    ModelProcessingClassifyRequest,
)
from memory_gateway.security import AgentIdentity
from memory_gateway.service import (
    InvalidState,
    NotFound,
    PermissionDenied,
    _merge_model_capture_suggestion,
    _suggest_capture_by_rules,
    classify_capture_with_model,
    redact_sensitive_content,
)
from memory_gateway.types import (
    AuditAction,
    CaptureSource,
    ContentKind,
    InboxProposalKind,
    InboxStatus,
    MemoryType,
    MemoryZone,
    ProposalStatus,
    Sensitivity,
    Visibility,
)

from .audit import audit_event, new_id
from .facts import mark_facts_inactive_for_memory, upsert_facts_for_memory
from .facts import extract_fact_candidates
from .retrieval import memory_to_out
from .semantic import (
    apply_semantic_summary_to_inbox,
    apply_semantic_summary_to_memory,
    ensure_memory_summary,
    generate_memory_summary,
    judge_memory_relationship,
    needs_user_decision,
    record_decision_example,
    relationship_to_inbox_kind,
    retrieve_summary_candidates,
    similar_decision_examples,
)


UPDATE_CUES = {
    "moved",
    "now",
    "currently",
    "recently",
    "changed",
    "instead",
    "replace",
    "updated",
    "no longer",
    "现在",
    "最近",
    "搬家",
    "改为",
    "更新",
    "不再",
}


def _visibility_for_zone(zone: MemoryZone, project_id: str | None) -> Visibility:
    if zone == MemoryZone.PUBLIC_PROFILE:
        return Visibility.PUBLIC
    if project_id:
        return Visibility.PROJECT
    return Visibility.PRIVATE


def _normalize_project_for_zone(zone: MemoryZone, project_id: str | None) -> str | None:
    if zone == MemoryZone.PUBLIC_PROFILE:
        return None
    if zone == MemoryZone.WORK_CONTEXT and not project_id:
        raise InvalidState("work_context memories require a project_id")
    return project_id


def _display_for_inbox(item: MemoryInboxItemRecord) -> DisplayOut:
    proposal_kind = item.proposal_kind or InboxProposalKind.NEW.value
    reasons = [
        "Non-public or sensitive captures enter the inbox before becoming memory.",
        "Remote model output is advisory; hard policy decides the review requirement.",
    ]
    warnings = list(item.risk_warnings or [])
    type_label = "memory"
    if item.suggested_memory_type == MemoryType.RELATIONSHIP.value:
        type_label = "relationship memory"
        reasons.append(
            "This appears to describe a person or relationship. It is not public profile memory."
        )
        if item.suggested_zone == MemoryZone.PERSONAL_CONTEXT.value:
            reasons.append("Agents need a personal_context grant before using this relationship.")
        elif item.suggested_zone == MemoryZone.WORK_CONTEXT.value:
            reasons.append("Agents need a work_context grant for this project before using this relationship.")
    if proposal_kind == InboxProposalKind.DUPLICATE.value:
        reasons.append("This looks similar to an existing memory. Merge or reject if it adds no new value.")
    elif proposal_kind == InboxProposalKind.UPDATE.value:
        reasons.append("This appears to update an older memory. Approving will supersede the old memory.")
        warnings.append("Old memory will stop appearing in composed context after approval.")
    elif proposal_kind == InboxProposalKind.CONFLICT.value:
        reasons.append("This conflicts with an older memory. Review before approving both facts.")
        warnings.append("Keeping both may confuse future agent context.")
    title = f"Review {proposal_kind} {type_label}"
    if item.suggested_memory_type == MemoryType.RELATIONSHIP.value and proposal_kind == InboxProposalKind.NEW.value:
        title = "Review new relationship memory"
    return DisplayOut(
        title=title,
        subtitle=f"{item.suggested_zone} / {item.sensitivity} / {item.source}",
        badges=[
            proposal_kind,
            item.suggested_zone,
            item.sensitivity,
            item.suggested_memory_type,
            item.status,
        ],
        reasons=reasons,
        warnings=warnings,
        primary_action="Approve update, merge duplicate, reject, or save as separate memory",
        safe_preview=item.redacted_preview,
    )


def _display_for_memory(memory: MemoryRecord) -> DisplayOut:
    reasons = ["Low-risk public profile memory was approved automatically."]
    if memory.memory_type == MemoryType.RELATIONSHIP.value:
        reasons = ["Relationship memory was saved after passing review and zone policy."]
    return DisplayOut(
        title="Memory saved",
        subtitle=f"{memory.memory_zone} / {memory.memory_type}",
        badges=[memory.memory_zone or "unzone", memory.sensitivity, memory.memory_type],
        reasons=reasons,
        warnings=[],
        primary_action="Available for context compose",
        safe_preview=memory.content[:1000],
    )


def inbox_item_to_out(item: MemoryInboxItemRecord, session: Session | None = None) -> InboxItemOut:
    relationship = _relationship_out(
        session=session,
        relationship={
            "proposal_kind": InboxProposalKind(item.proposal_kind or InboxProposalKind.NEW.value),
            "duplicate_memory_ids": item.duplicate_memory_ids or [],
            "conflict_memory_ids": item.conflict_memory_ids or [],
            "supersedes_memory_id": item.supersedes_memory_id,
        },
        content=item.redacted_preview,
        old_content=None,
    )
    return InboxItemOut(
        id=item.id,
        status=InboxStatus(item.status),
        project_id=item.project_id,
        content_kind=ContentKind(item.content_kind),
        source=CaptureSource(item.source),
        source_url=item.source_url,
        source_title=item.source_title,
        asset_path=item.asset_path,
        redacted_preview=item.redacted_preview,
        suggested_zone=MemoryZone(item.suggested_zone),
        suggested_memory_type=MemoryType(item.suggested_memory_type),
        sensitivity=Sensitivity(item.sensitivity),
        risk_warnings=item.risk_warnings or [],
        tags=item.tags or [],
        proposal_kind=InboxProposalKind(item.proposal_kind or InboxProposalKind.NEW.value),
        duplicate_memory_ids=item.duplicate_memory_ids or [],
        conflict_memory_ids=item.conflict_memory_ids or [],
        supersedes_memory_id=item.supersedes_memory_id,
        human_reason=relationship.human_reason,
        diff_summary=relationship.diff_summary,
        semantic_summary=item.semantic_summary or "",
        semantic_entities=item.semantic_entities or [],
        semantic_triggers=item.semantic_triggers or [],
        candidate_memory_ids=item.candidate_memory_ids or [],
        llm_relationship=item.llm_relationship,
        llm_confidence=float(item.llm_confidence or 0.0),
        llm_reason=item.llm_reason or "",
        needs_user_decision=bool(item.needs_user_decision),
        approved_memory_id=item.approved_memory_id,
        merged_into_memory_id=item.merged_into_memory_id,
        created_at=item.created_at,
        reviewed_at=item.reviewed_at,
        display=_display_for_inbox(item),
    )


def _duplicate_candidates(session: Session, agent: AgentIdentity, content: str) -> list[str]:
    analysis = _memory_relationship_candidates(
        session,
        agent,
        content,
        project_id=None,
        zone=None,
    )
    return analysis["duplicate_memory_ids"]


def _normalize_for_duplicate(content: str) -> str:
    lowered = content.lower().strip()
    lowered = re.sub(r"\s+", " ", lowered)
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", lowered)


def _has_update_cue(content: str) -> bool:
    lowered = content.lower()
    return any(cue in lowered for cue in UPDATE_CUES)


def _commute_distance_signature(content: str) -> tuple[str, str] | None:
    lowered = content.lower()
    if not any(
        marker in lowered
        for marker in ("office", "company", "work", "commute", "公司", "办公室", "上班", "通勤")
    ):
        return None
    if not any(
        marker in lowered
        for marker in ("live", "living", "reside", "moved", "distance", "住", "居住", "搬", "距离")
    ):
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:km|kilometer|kilometers|公里)", lowered)
    if not match:
        return None
    return ("personal:commute_distance_to_office", match.group(1))


def _storage_preference_signature(content: str, project_id: str | None) -> tuple[str, str] | None:
    lowered = content.lower()
    if not project_id:
        return None
    if not any(marker in lowered for marker in ("memory", "storage", "database", "vector", "记忆", "存储", "数据库", "向量")):
        return None
    tools = []
    for keyword in ("postgres", "pgvector", "sqlite", "neo4j", "mysql", "redis"):
        if keyword in lowered:
            tools.append(keyword)
    if not tools:
        return None
    return (f"project:{project_id}:storage_stack", "+".join(sorted(tools)))


def _fact_signature(content: str, project_id: str | None) -> tuple[str, str] | None:
    return _commute_distance_signature(content) or _storage_preference_signature(content, project_id)


def _candidate_records(
    session: Session,
    agent: AgentIdentity,
    *,
    project_id: str | None,
    zone: MemoryZone | None,
) -> list[MemoryRecord]:
    query = select(MemoryRecord).where(
        MemoryRecord.tenant_id == agent.tenant_id,
        MemoryRecord.deleted_at.is_(None),
        MemoryRecord.status == ProposalStatus.APPROVED.value,
    )
    if zone:
        query = query.where(MemoryRecord.memory_zone == zone.value)
    records = list(session.scalars(query))
    scoped: list[MemoryRecord] = []
    for record in records:
        if record.memory_zone == MemoryZone.PUBLIC_PROFILE.value:
            if zone == MemoryZone.PUBLIC_PROFILE:
                scoped.append(record)
            continue
        if record.project_id == project_id:
            scoped.append(record)
    return scoped


def _memory_relationship_candidates(
    session: Session,
    agent: AgentIdentity,
    content: str,
    *,
    project_id: str | None,
    zone: MemoryZone | None,
) -> dict[str, object]:
    query_embedding = embed_text(content)
    normalized = _normalize_for_duplicate(content)
    new_signature = _fact_signature(content, project_id)
    records = _candidate_records(session, agent, project_id=project_id, zone=zone)
    scored = []
    duplicate_ids: list[str] = []
    conflict_ids: list[str] = []
    supersedes_memory_id: str | None = None
    for record in records:
        if not record.content:
            continue
        score = cosine_similarity(query_embedding, record.embedding or [])
        scored.append((score, record.id))
        if normalized and normalized == _normalize_for_duplicate(record.content):
            duplicate_ids.append(record.id)
        elif score >= 0.9:
            duplicate_ids.append(record.id)
        old_signature = _fact_signature(record.content, record.project_id)
        if new_signature and old_signature and new_signature[0] == old_signature[0]:
            if new_signature[1] != old_signature[1]:
                conflict_ids.append(record.id)
                supersedes_memory_id = supersedes_memory_id or record.id
    scored.sort(reverse=True)
    for score, memory_id in scored:
        if score >= 0.82 and memory_id not in duplicate_ids and memory_id not in conflict_ids:
            duplicate_ids.append(memory_id)
        if len(duplicate_ids) >= 5:
            break
    if conflict_ids and _has_update_cue(content):
        proposal_kind = InboxProposalKind.UPDATE
    elif conflict_ids:
        proposal_kind = InboxProposalKind.CONFLICT
    elif duplicate_ids:
        proposal_kind = InboxProposalKind.DUPLICATE
    else:
        proposal_kind = InboxProposalKind.NEW
    return {
        "proposal_kind": proposal_kind,
        "duplicate_memory_ids": list(dict.fromkeys(duplicate_ids))[:5],
        "conflict_memory_ids": list(dict.fromkeys(conflict_ids))[:5],
        "supersedes_memory_id": supersedes_memory_id,
    }


def _relationship_out(
    session: Session | None,
    relationship: dict[str, object],
    content: str,
    old_content: str | None = None,
) -> MemoryRelationshipSuggestionOut:
    kind = relationship["proposal_kind"]
    assert isinstance(kind, InboxProposalKind)
    supersedes = relationship.get("supersedes_memory_id")
    resolved_old_content = old_content or ""
    if supersedes and session is not None:
        old = session.get(MemoryRecord, str(supersedes))
        resolved_old_content = old.content if old else ""
    if kind == InboxProposalKind.UPDATE:
        reason = "This looks like an update to an older memory."
    elif kind == InboxProposalKind.CONFLICT:
        reason = "This conflicts with an older memory and needs review."
    elif kind == InboxProposalKind.DUPLICATE:
        reason = "This is similar to an existing memory."
    else:
        reason = "This appears to be new memory."
    diff_summary = ""
    if resolved_old_content:
        diff_summary = f"Old: {resolved_old_content[:180]}\nNew: {content[:180]}"
    elif supersedes:
        diff_summary = f"Old memory: {supersedes}\nNew: {content[:180]}"
    return MemoryRelationshipSuggestionOut(
        proposal_kind=kind,
        duplicate_memory_ids=list(relationship.get("duplicate_memory_ids") or []),
        conflict_memory_ids=list(relationship.get("conflict_memory_ids") or []),
        supersedes_memory_id=str(supersedes) if supersedes else None,
        human_reason=reason,
        diff_summary=diff_summary,
    )


def preview_extraction(
    session: Session,
    agent: AgentIdentity,
    request: ExtractionPreviewRequest,
) -> ExtractionPreviewResponse:
    if not agent.can_write:
        raise PermissionDenied("agent cannot preview extraction")
    rule_response = _suggest_capture_by_rules(
        request.content,
        request.content_kind,
        request.project_id,
    )
    redacted, warnings = redact_sensitive_content(request.content)
    zone = request.memory_zone or rule_response.suggested_zone
    memory_type = request.memory_type or rule_response.suggested_memory_type
    relationship = _memory_relationship_candidates(
        session,
        agent,
        redacted,
        project_id=request.project_id,
        zone=zone,
    )
    semantic = generate_memory_summary(
        session,
        agent,
        redacted,
        request.project_id,
        zone,
        request.model_profile_id,
    )
    candidates = retrieve_summary_candidates(
        session,
        agent,
        semantic,
        request.project_id,
        zone,
        top_k=8,
    )
    examples = similar_decision_examples(
        session,
        agent,
        semantic.summary,
        request.project_id,
        zone,
    )
    judgment = judge_memory_relationship(
        session,
        agent,
        semantic,
        candidates,
        examples,
        request.model_profile_id,
    )
    semantic_kind = relationship_to_inbox_kind(judgment.relationship, judgment.confidence)
    if semantic_kind != InboxProposalKind.NEW or judgment.relationship in {"separate", "uncertain"}:
        relationship = {
            "proposal_kind": semantic_kind,
            "duplicate_memory_ids": [judgment.candidate_memory_id] if judgment.relationship == "duplicate" and judgment.candidate_memory_id else [],
            "conflict_memory_ids": [judgment.candidate_memory_id] if judgment.relationship in {"update", "conflict", "uncertain"} and judgment.candidate_memory_id else [],
            "supersedes_memory_id": judgment.candidate_memory_id if judgment.relationship == "update" and judgment.candidate_memory_id else None,
        }
    temp = MemoryRecord(
        id="preview",
        tenant_id=agent.tenant_id,
        project_id=request.project_id,
        owner_user_id=None,
        visibility=_visibility_for_zone(zone, request.project_id).value,
        allowed_agent_ids=[],
        denied_agent_ids=[],
        memory_type=memory_type.value,
        memory_zone=zone.value,
        content_kind=request.content_kind.value,
        redacted=redacted != request.content,
        content=redacted,
        tags=list(rule_response.tags),
        sensitivity=max_sensitivity(rule_response.sensitivity, classify_sensitivity(redacted)).value,
        source="preview",
        embedding=[],
        status=ProposalStatus.PENDING.value,
    )
    facts = [
        ExtractedFactOut(
            subject=fact.subject,
            predicate=fact.predicate,
            object=fact.object,
            fact_type=fact.fact_type,
            project_id=request.project_id,
            zone=zone,
            confidence=fact.confidence,
        )
        for fact in extract_fact_candidates(temp)
    ]
    relationship_out = _relationship_out(session, relationship, redacted)
    display = DisplayOut(
        title=f"Extraction preview: {relationship_out.proposal_kind.value}",
        subtitle=f"{zone.value} / {memory_type.value} / {rule_response.sensitivity.value}",
        badges=[
            relationship_out.proposal_kind.value,
            zone.value,
            memory_type.value,
            rule_response.sensitivity.value,
        ],
        reasons=[
            relationship_out.human_reason,
            "Semantic summary is generated from redacted content before approval.",
            judgment.reason or "Relationship judgment used summary candidates.",
        ],
        warnings=list(dict.fromkeys((rule_response.risk_warnings or []) + warnings)),
        primary_action="Review before approving into memory",
        safe_preview=redacted,
    )
    audit_event(
        session,
        agent,
        AuditAction.EXTRACT,
        "extraction_preview",
        None,
        {
            "proposal_kind": relationship_out.proposal_kind.value,
            "project_id": request.project_id,
            "zone": zone.value,
        },
    )
    return ExtractionPreviewResponse(
        redacted_preview=redacted[:1000],
        suggested_zone=zone,
        suggested_memory_type=memory_type,
        sensitivity=rule_response.sensitivity,
        facts=facts,
        relationship=relationship_out,
        semantic=semantic,
        candidate_matches=candidates,
        llm_relationship=judgment,
        needs_user_decision=needs_user_decision(judgment.relationship, judgment.confidence),
        display=display,
    )


def _create_memory_from_inbox(
    session: Session,
    agent: AgentIdentity,
    item: MemoryInboxItemRecord,
    *,
    zone: MemoryZone,
    memory_type: MemoryType,
    project_id: str | None,
    tags: list[str],
    source: str,
) -> MemoryRecord:
    project_id = _normalize_project_for_zone(zone, project_id)
    sensitivity = max_sensitivity(
        Sensitivity(item.sensitivity),
        zone_default_sensitivity(zone),
        classify_sensitivity(item.redacted_preview),
    )
    memory = MemoryRecord(
        id=new_id("mem"),
        tenant_id=item.tenant_id,
        project_id=project_id,
        owner_user_id=None,
        visibility=_visibility_for_zone(zone, project_id).value,
        allowed_agent_ids=[],
        denied_agent_ids=[],
        memory_type=memory_type.value,
        memory_zone=zone.value,
        content_kind=item.content_kind,
        capture_source=item.source,
        source_url=item.source_url,
        source_title=item.source_title,
        asset_path=item.asset_path,
        redacted=item.redacted_preview != item.raw_preview[:1000],
        content=item.redacted_preview,
        tags=tags,
        sensitivity=sensitivity.value,
        source=source,
        embedding=embed_text(item.redacted_preview),
        status=ProposalStatus.APPROVED.value,
        created_by_agent_id=agent.agent_id,
    )
    memory.semantic_summary = item.semantic_summary or item.redacted_preview[:260]
    memory.semantic_entities = item.semantic_entities or []
    memory.semantic_triggers = item.semantic_triggers or []
    memory.semantic_facts = item.semantic_facts or []
    memory.summary_embedding = embed_text(memory.semantic_summary)
    memory.summary_confidence = float(item.llm_confidence or 0.0)
    memory.summary_updated_at = utcnow()
    session.add(memory)
    session.flush()
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
    return memory


def _supersede_memory(
    session: Session,
    agent: AgentIdentity,
    old_memory_id: str,
    new_memory: MemoryRecord,
) -> None:
    old_memory = session.get(MemoryRecord, old_memory_id)
    if not old_memory or old_memory.tenant_id != agent.tenant_id:
        raise NotFound("memory to supersede not found")
    if old_memory.status != ProposalStatus.APPROVED.value:
        raise InvalidState(f"memory to supersede is {old_memory.status}, not approved")
    if old_memory.project_id != new_memory.project_id:
        raise InvalidState("cannot supersede memory across project boundaries")
    old_memory.status = ProposalStatus.SUPERSEDED.value
    old_memory.superseded_by_id = new_memory.id
    session.add(
        MemoryVersionRecord(
            id=new_id("ver"),
            tenant_id=new_memory.tenant_id,
            memory_id=new_memory.id,
            previous_memory_id=old_memory.id,
            event="supersedes",
            actor_agent_id=agent.agent_id,
        )
    )
    mark_facts_inactive_for_memory(session, agent, old_memory.id)
    graph_result = get_graph_client().mark_memory_inactive(old_memory.id)
    audit_event(
        session,
        agent,
        AuditAction.MEMORY_SUPERSEDE,
        "memory",
        new_memory.id,
        {
            "previous_memory_id": old_memory.id,
            "graph_available": graph_result.available,
            "reason": graph_result.reason,
        },
    )


def ingest_memory(session: Session, agent: AgentIdentity, request: IngestRequest) -> IngestResponse:
    if not agent.can_write:
        raise PermissionDenied("agent cannot ingest memories")

    rule_response = _suggest_capture_by_rules(
        request.content, request.content_kind, request.project_id
    )
    final_response = rule_response
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
        final_response = _merge_model_capture_suggestion(rule_response, model_response.suggestion)
        final_response.model_suggestion = model_response.suggestion
        final_response.sent_to_model = model_response.sent_to_model
        final_response.used_redacted_preview = True
        final_response.final_suggestion_source = (
            "model" if model_response.suggestion.get("applied") is True else "rule"
        )

    redacted, warnings = redact_sensitive_content(request.content)
    risk_warnings = list(dict.fromkeys((final_response.risk_warnings or []) + warnings))
    source = request.source
    relationship = _memory_relationship_candidates(
        session,
        agent,
        redacted,
        project_id=request.project_id,
        zone=final_response.suggested_zone,
    )
    semantic = generate_memory_summary(
        session,
        agent,
        redacted,
        request.project_id,
        final_response.suggested_zone,
        request.model_profile_id,
    )
    candidates = retrieve_summary_candidates(
        session,
        agent,
        semantic,
        request.project_id,
        final_response.suggested_zone,
        top_k=8,
    )
    examples = similar_decision_examples(
        session,
        agent,
        semantic.summary,
        request.project_id,
        final_response.suggested_zone,
    )
    judgment = judge_memory_relationship(
        session,
        agent,
        semantic,
        candidates,
        examples,
        request.model_profile_id,
    )
    semantic_kind = relationship_to_inbox_kind(judgment.relationship, judgment.confidence)
    if semantic_kind != InboxProposalKind.NEW or judgment.relationship in {"separate", "uncertain"}:
        candidate_id = judgment.candidate_memory_id
        relationship = {
            "proposal_kind": semantic_kind,
            "duplicate_memory_ids": [candidate_id] if judgment.relationship == "duplicate" and candidate_id else [],
            "conflict_memory_ids": [candidate_id] if judgment.relationship in {"update", "conflict", "uncertain"} and candidate_id else [],
            "supersedes_memory_id": candidate_id if judgment.relationship == "update" and candidate_id else None,
        }
    should_auto_approve = (
        agent.is_admin
        and request.auto_approve_public_low
        and final_response.suggested_zone == MemoryZone.PUBLIC_PROFILE
        and final_response.sensitivity == Sensitivity.LOW
        and relationship["proposal_kind"] == InboxProposalKind.NEW
        and not needs_user_decision(judgment.relationship, judgment.confidence)
        and judgment.relationship in {"separate"}
    )

    capture = CaptureEventRecord(
        id=new_id("cap"),
        tenant_id=agent.tenant_id,
        agent_id=agent.agent_id,
        project_id=request.project_id,
        content_kind=request.content_kind.value,
        capture_source=source.value,
        raw_preview=request.content[:500],
        redacted_preview=redacted[:500],
        suggested_zone=final_response.suggested_zone.value,
        suggested_memory_type=final_response.suggested_memory_type.value,
        sensitivity=final_response.sensitivity.value,
        risk_warnings=risk_warnings,
        source_url=request.source_url,
        source_title=request.source_title,
        asset_path=request.asset_path,
    )
    session.add(capture)
    session.flush()

    if should_auto_approve:
        item = MemoryInboxItemRecord(
            id=new_id("inb"),
            tenant_id=agent.tenant_id,
            agent_id=agent.agent_id,
            project_id=request.project_id,
            content_kind=request.content_kind.value,
            source=source.value,
            source_url=request.source_url,
            source_title=request.source_title,
            asset_path=request.asset_path,
            raw_preview=request.content[:1000],
            redacted_preview=redacted[:1000],
            suggested_zone=final_response.suggested_zone.value,
            suggested_memory_type=final_response.suggested_memory_type.value,
            sensitivity=final_response.sensitivity.value,
            risk_warnings=risk_warnings,
            tags=final_response.tags,
            rule_suggestion=final_response.rule_suggestion or {},
            model_suggestion=final_response.model_suggestion,
            proposal_kind=relationship["proposal_kind"].value,
            duplicate_memory_ids=relationship["duplicate_memory_ids"],
            conflict_memory_ids=relationship["conflict_memory_ids"],
            supersedes_memory_id=relationship["supersedes_memory_id"],
            semantic_summary=semantic.summary,
            semantic_entities=semantic.entities,
            semantic_triggers=semantic.triggers,
            semantic_facts=semantic.facts,
            candidate_memory_ids=[candidate.memory_id for candidate in candidates],
            llm_relationship=judgment.relationship,
            llm_confidence=judgment.confidence,
            llm_reason=judgment.reason,
            needs_user_decision=needs_user_decision(judgment.relationship, judgment.confidence),
            status=InboxStatus.APPROVED.value,
            reviewed_at=utcnow(),
            reviewed_by_agent_id=agent.agent_id,
        )
        session.add(item)
        session.flush()
        memory = _create_memory_from_inbox(
            session,
            agent,
            item,
            zone=final_response.suggested_zone,
            memory_type=final_response.suggested_memory_type,
            project_id=request.project_id,
            tags=final_response.tags,
            source=f"ingest:{item.id}",
        )
        item.approved_memory_id = memory.id
        capture.committed_memory_id = memory.id
        audit_id = audit_event(
            session,
            agent,
            AuditAction.INGEST,
            "memory",
            memory.id,
            {"source": source.value, "auto_approved": True},
        )
        return IngestResponse(
            auto_approved=True,
            memory=memory_to_out(memory),
            audit_id=audit_id,
            display=_display_for_memory(memory),
        )

    item = MemoryInboxItemRecord(
        id=new_id("inb"),
        tenant_id=agent.tenant_id,
        agent_id=agent.agent_id,
        project_id=request.project_id,
        content_kind=request.content_kind.value,
        source=source.value,
        source_url=request.source_url,
        source_title=request.source_title,
        asset_path=request.asset_path,
        raw_preview=request.content[:1000],
        redacted_preview=redacted[:1000],
        suggested_zone=final_response.suggested_zone.value,
        suggested_memory_type=final_response.suggested_memory_type.value,
        sensitivity=final_response.sensitivity.value,
        risk_warnings=risk_warnings,
        tags=final_response.tags,
        rule_suggestion=final_response.rule_suggestion or {},
        model_suggestion=final_response.model_suggestion,
        proposal_kind=relationship["proposal_kind"].value,
        duplicate_memory_ids=relationship["duplicate_memory_ids"],
        conflict_memory_ids=relationship["conflict_memory_ids"],
        supersedes_memory_id=relationship["supersedes_memory_id"],
        semantic_summary=semantic.summary,
        semantic_entities=semantic.entities,
        semantic_triggers=semantic.triggers,
        semantic_facts=semantic.facts,
        candidate_memory_ids=[candidate.memory_id for candidate in candidates],
        llm_relationship=judgment.relationship,
        llm_confidence=judgment.confidence,
        llm_reason=judgment.reason,
        needs_user_decision=needs_user_decision(judgment.relationship, judgment.confidence),
        status=InboxStatus.PENDING_REVIEW.value,
    )
    session.add(item)
    session.flush()
    audit_id = audit_event(
        session,
        agent,
        AuditAction.INGEST,
        "memory_inbox_item",
        item.id,
        {"source": source.value, "auto_approved": False},
    )
    return IngestResponse(
        auto_approved=False,
        inbox_item=inbox_item_to_out(item, session),
        audit_id=audit_id,
        display=_display_for_inbox(item),
    )


def list_inbox_items(
    session: Session,
    agent: AgentIdentity,
    status: InboxStatus = InboxStatus.PENDING_REVIEW,
) -> list[InboxItemOut]:
    if not agent.is_admin:
        raise PermissionDenied("only admin agents can list inbox items")
    records = session.scalars(
        select(MemoryInboxItemRecord).where(
            MemoryInboxItemRecord.tenant_id == agent.tenant_id,
            MemoryInboxItemRecord.status == status.value,
        )
    ).all()
    return [inbox_item_to_out(record, session) for record in records]


def approve_inbox_item(
    session: Session,
    agent: AgentIdentity,
    inbox_id: str,
    request: InboxApproveRequest,
) -> InboxItemOut:
    if not agent.is_admin:
        raise PermissionDenied("only admin agents can approve inbox items")
    item = session.get(MemoryInboxItemRecord, inbox_id)
    if not item or item.tenant_id != agent.tenant_id:
        raise NotFound("inbox item not found")
    if item.status != InboxStatus.PENDING_REVIEW.value:
        raise InvalidState(f"inbox item is {item.status}, not pending_review")

    zone = request.memory_zone or MemoryZone(item.suggested_zone)
    memory_type = request.memory_type or MemoryType(item.suggested_memory_type)
    project_id = request.project_id if request.project_id is not None else item.project_id
    tags = request.tags if request.tags is not None else list(item.tags or [])
    item.suggested_zone = zone.value
    item.suggested_memory_type = memory_type.value
    item.project_id = project_id
    item.tags = tags
    memory = _create_memory_from_inbox(
        session,
        agent,
        item,
        zone=zone,
        memory_type=memory_type,
        project_id=project_id,
        tags=tags,
        source=f"inbox:{item.id}",
    )
    supersede_memory_id = (
        request.supersede_memory_id
        or item.supersedes_memory_id
        or ((item.conflict_memory_ids or [None])[0] if item.proposal_kind == InboxProposalKind.UPDATE.value else None)
    )
    if supersede_memory_id:
        _supersede_memory(session, agent, supersede_memory_id, memory)
        record_decision_example(
            session,
            agent,
            item=item,
            user_decision="approve_update",
            final_memory_id=memory.id,
            superseded_memory_id=supersede_memory_id,
        )
    elif item.proposal_kind == InboxProposalKind.DUPLICATE.value:
        record_decision_example(
            session,
            agent,
            item=item,
            user_decision="approve_duplicate_as_new",
            final_memory_id=memory.id,
        )
    else:
        record_decision_example(
            session,
            agent,
            item=item,
            user_decision="approve_separate",
            final_memory_id=memory.id,
        )
    item.status = InboxStatus.APPROVED.value
    item.approved_memory_id = memory.id
    item.supersedes_memory_id = supersede_memory_id
    item.review_note = request.note
    item.reviewed_at = utcnow()
    item.reviewed_by_agent_id = agent.agent_id
    session.add(
        MemoryVersionRecord(
            id=new_id("ver"),
            tenant_id=memory.tenant_id,
            memory_id=memory.id,
            previous_memory_id=None,
            event="created_from_inbox",
            actor_agent_id=agent.agent_id,
        )
    )
    session.flush()
    audit_event(
        session,
        agent,
        AuditAction.INBOX_APPROVE,
        "memory_inbox_item",
        item.id,
        {"approved_memory_id": memory.id},
    )
    return inbox_item_to_out(item, session)


def approve_inbox_update(
    session: Session,
    agent: AgentIdentity,
    inbox_id: str,
    request: InboxApproveRequest,
) -> InboxItemOut:
    item = session.get(MemoryInboxItemRecord, inbox_id)
    if not item or item.tenant_id != agent.tenant_id:
        raise NotFound("inbox item not found")
    supersede_id = request.supersede_memory_id or item.supersedes_memory_id
    if not supersede_id:
        raise InvalidState("approve-update requires supersede_memory_id")
    request = request.model_copy(update={"supersede_memory_id": supersede_id})
    return approve_inbox_item(session, agent, inbox_id, request)


def approve_inbox_separate(
    session: Session,
    agent: AgentIdentity,
    inbox_id: str,
    request: InboxApproveRequest,
) -> InboxItemOut:
    item = session.get(MemoryInboxItemRecord, inbox_id)
    if not item or item.tenant_id != agent.tenant_id:
        raise NotFound("inbox item not found")
    item.supersedes_memory_id = None
    item.conflict_memory_ids = []
    item.proposal_kind = InboxProposalKind.NEW.value
    item.needs_user_decision = False
    request = request.model_copy(update={"supersede_memory_id": None})
    return approve_inbox_item(session, agent, inbox_id, request)


def reject_inbox_item(
    session: Session,
    agent: AgentIdentity,
    inbox_id: str,
    request: InboxRejectRequest,
) -> InboxItemOut:
    if not agent.is_admin:
        raise PermissionDenied("only admin agents can reject inbox items")
    item = session.get(MemoryInboxItemRecord, inbox_id)
    if not item or item.tenant_id != agent.tenant_id:
        raise NotFound("inbox item not found")
    if item.status != InboxStatus.PENDING_REVIEW.value:
        raise InvalidState(f"inbox item is {item.status}, not pending_review")
    item.status = InboxStatus.REJECTED.value
    item.review_note = request.reason
    item.reviewed_at = utcnow()
    item.reviewed_by_agent_id = agent.agent_id
    session.flush()
    record_decision_example(
        session,
        agent,
        item=item,
        user_decision="reject",
    )
    audit_event(
        session,
        agent,
        AuditAction.INBOX_REJECT,
        "memory_inbox_item",
        item.id,
        {"reason": request.reason},
    )
    return inbox_item_to_out(item, session)


def merge_inbox_item(
    session: Session,
    agent: AgentIdentity,
    inbox_id: str,
    request: InboxMergeRequest,
) -> InboxItemOut:
    if not agent.is_admin:
        raise PermissionDenied("only admin agents can merge inbox items")
    item = session.get(MemoryInboxItemRecord, inbox_id)
    target = session.get(MemoryRecord, request.target_memory_id)
    if not item or item.tenant_id != agent.tenant_id:
        raise NotFound("inbox item not found")
    if not target or target.tenant_id != agent.tenant_id:
        raise NotFound("target memory not found")
    if item.status != InboxStatus.PENDING_REVIEW.value:
        raise InvalidState(f"inbox item is {item.status}, not pending_review")
    target.tags = list(dict.fromkeys((target.tags or []) + (item.tags or [])))
    target.embedding = embed_text(target.content)
    item.status = InboxStatus.MERGED.value
    item.merged_into_memory_id = target.id
    item.review_note = request.note
    item.reviewed_at = utcnow()
    item.reviewed_by_agent_id = agent.agent_id
    session.flush()
    record_decision_example(
        session,
        agent,
        item=item,
        user_decision="merge",
        final_memory_id=target.id,
    )
    audit_event(
        session,
        agent,
        AuditAction.INBOX_MERGE,
        "memory_inbox_item",
        item.id,
        {"target_memory_id": target.id},
    )
    return inbox_item_to_out(item, session)
