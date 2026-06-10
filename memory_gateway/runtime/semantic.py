from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_gateway.db import (
    MemoryDecisionExampleRecord,
    MemoryInboxItemRecord,
    MemoryRecord,
    ModelProfileRecord,
    utcnow,
)
from memory_gateway.embedding import cosine_similarity, embed_text, tokenize
from memory_gateway.policy import classify_sensitivity
from memory_gateway.schemas import (
    DecisionExampleOut,
    SemanticCandidateOut,
    SemanticRelationshipOut,
    SemanticSummaryOut,
)
from memory_gateway.security import AgentIdentity
from memory_gateway.types import (
    AuditAction,
    InboxProposalKind,
    MemoryType,
    MemoryZone,
    ModelProvider,
    ModelTask,
    ProposalStatus,
    Sensitivity,
)

from .audit import audit_event, new_id


RELATIONSHIP_TO_KIND = {
    "duplicate": InboxProposalKind.DUPLICATE,
    "update": InboxProposalKind.UPDATE,
    "conflict": InboxProposalKind.CONFLICT,
    "separate": InboxProposalKind.NEW,
    "uncertain": InboxProposalKind.CONFLICT,
}


@dataclass(frozen=True)
class CandidateScore:
    record: MemoryRecord
    score: float
    reason: str


def _json_from_text(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        value = json.loads(match.group(0))
    return value if isinstance(value, dict) else {}


def _openai_chat_completions_url(endpoint_url: str | None) -> str:
    base = (endpoint_url or "https://api.openai.com").rstrip("/")
    if base.endswith("/v1/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _call_chat_json(
    profile: ModelProfileRecord,
    *,
    system: str,
    user: str,
) -> dict[str, Any]:
    if profile.provider == ModelProvider.OPENAI_COMPATIBLE.value:
        api_key = (profile.api_key_secret or "").strip() or os.getenv(profile.api_key_env or "")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        response = httpx.post(
            _openai_chat_completions_url(profile.endpoint_url),
            headers=headers,
            json={
                "model": profile.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            timeout=20,
        )
        response.raise_for_status()
        return _json_from_text(response.json()["choices"][0]["message"]["content"])
    if profile.provider == ModelProvider.OLLAMA.value:
        base = (profile.endpoint_url or "http://127.0.0.1:11434").rstrip("/")
        response = httpx.post(
            f"{base}/api/chat",
            json={
                "model": profile.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "format": "json",
            },
            timeout=20,
        )
        response.raise_for_status()
        return _json_from_text(response.json()["message"]["content"])
    return {}


def _fallback_summary(
    content: str,
    *,
    project_id: str | None,
    zone: MemoryZone,
) -> dict[str, Any]:
    normalized = re.sub(r"\s+", " ", content.strip())
    summary = normalized[:260] or "Empty memory capture"
    tokens = tokenize(summary)
    stop = {
        "the",
        "and",
        "for",
        "with",
        "this",
        "that",
        "from",
        "现在",
        "最近",
        "项目",
    }
    entities = []
    for token in tokens:
        if len(token) >= 3 and token not in stop and token not in entities:
            entities.append(token)
        if len(entities) >= 8:
            break
    triggers = entities[:6]
    if project_id and project_id not in entities:
        entities.insert(0, project_id)
    relationship_match = re.search(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b[^.\n]{0,80}\b(friend|colleague|coworker|client|customer|mentor|family|partner)\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if not relationship_match:
        relationship_match = re.search(
            r"([\u4e00-\u9fff]{1,8})\s*(?:是|为|為).{0,8}(?:我的)?(朋友|同事|客户|客戶|导师|導師|家人|伴侣|伴侶)",
            normalized,
        )
    if relationship_match:
        person = relationship_match.group(1).strip()
        relation_word = relationship_match.group(2).lower()
        predicate = "KNOWS"
        if relation_word in {"friend", "朋友"}:
            predicate = "FRIEND_OF"
        elif relation_word in {"colleague", "coworker", "同事"}:
            predicate = "COLLEAGUE_OF"
        elif relation_word in {"client", "customer", "客户", "客戶"}:
            predicate = "CLIENT_OF"
        elif relation_word in {"mentor", "导师", "導師"}:
            predicate = "MENTOR_OF"
        elif relation_word in {"family", "partner", "家人", "伴侣", "伴侶"}:
            predicate = "FAMILY_OF"
        if person not in entities:
            entities.insert(0, person)
        if "relationship" not in triggers:
            triggers.insert(0, "relationship")
        return {
            "summary": summary,
            "entities": entities,
            "triggers": triggers,
            "facts": [
                {
                    "subject": "user",
                    "predicate": predicate,
                    "object": person,
                }
            ],
            "confidence": 0.68,
        }
    return {
        "summary": summary,
        "entities": entities,
        "triggers": triggers,
        "facts": [
            {
                "subject": project_id or ("user" if zone != MemoryZone.WORK_CONTEXT else "project"),
                "predicate": "related_to",
                "object": summary[:120],
            }
        ],
        "confidence": 0.55,
    }


def _normalize_summary_payload(payload: dict[str, Any]) -> dict[str, Any]:
    facts = payload.get("facts") or payload.get("semantic_facts") or []
    normalized_facts: list[dict[str, Any]] = []
    if isinstance(facts, list):
        for fact in facts[:8]:
            if not isinstance(fact, dict):
                continue
            subject = str(fact.get("subject") or "").strip()
            predicate = str(fact.get("predicate") or "").strip()
            obj = str(fact.get("object") or "").strip()
            if subject and predicate and obj:
                normalized_facts.append(
                    {"subject": subject[:160], "predicate": predicate[:120], "object": obj[:240]}
                )
    return {
        "summary": str(payload.get("summary") or payload.get("semantic_summary") or "")[:1000],
        "entities": [str(item)[:120] for item in (payload.get("entities") or []) if str(item).strip()][:20],
        "triggers": [str(item)[:120] for item in (payload.get("triggers") or []) if str(item).strip()][:20],
        "facts": normalized_facts,
        "confidence": max(0.0, min(float(payload.get("confidence") or 0.0), 1.0)),
    }


def generate_memory_summary(
    session: Session,
    agent: AgentIdentity,
    content: str,
    project_id: str | None,
    zone: MemoryZone,
    model_profile_id: str | None = None,
) -> SemanticSummaryOut:
    from memory_gateway.service import get_model_profile, redact_sensitive_content

    redacted, warnings = redact_sensitive_content(content)
    profile = get_model_profile(session, agent, model_profile_id)
    sent_to_model = False
    fallback_used = False
    payload: dict[str, Any]
    blocked_remote = (
        profile.provider == ModelProvider.OPENAI_COMPATIBLE.value
        and (zone in {MemoryZone.SENSITIVE_VAULT, MemoryZone.PAYMENT_REFERENCE} or classify_sensitivity(redacted) == Sensitivity.HIGH)
    )
    if (
        profile.provider != ModelProvider.RULE_ONLY.value
        and ModelTask.SUMMARIZE_MEMORY.value in (profile.allowed_tasks or [])
        and not blocked_remote
    ):
        try:
            sent_to_model = True
            payload = _call_chat_json(
                profile,
                system=(
                    "Return strict JSON only. You generate semantic memory summaries. "
                    "Never include raw passwords, tokens, card numbers, CVV, or credentials. "
                    "Keys: summary, entities, triggers, facts, confidence. "
                    "facts items use subject, predicate, object."
                ),
                user=(
                    f"Project id: {project_id or 'global'}\n"
                    f"Memory zone: {zone.value}\n"
                    "Summarize this redacted memory for later retrieval and conflict comparison:\n\n"
                    f"{redacted}"
                ),
            )
        except Exception as error:
            fallback_used = True
            payload = _fallback_summary(redacted, project_id=project_id, zone=zone)
            payload["model_error"] = str(error)
    else:
        fallback_used = profile.provider != ModelProvider.RULE_ONLY.value
        payload = _fallback_summary(redacted, project_id=project_id, zone=zone)
        if blocked_remote:
            warnings.append("Remote semantic summarization was blocked for sensitive/payment content.")

    normalized = _normalize_summary_payload(payload)
    if not normalized["summary"]:
        fallback_used = True
        normalized = _fallback_summary(redacted, project_id=project_id, zone=zone)
    audit_event(
        session,
        agent,
        AuditAction.MODEL_PROCESS,
        "semantic_summary",
        profile.id,
        {
            "sent_to_model": sent_to_model,
            "fallback_used": fallback_used,
            "used_redacted_preview": True,
            "zone": zone.value,
        },
    )
    return SemanticSummaryOut(
        summary=normalized["summary"],
        entities=normalized["entities"],
        triggers=normalized["triggers"],
        facts=normalized["facts"],
        confidence=float(normalized["confidence"] or 0.0),
        sent_to_model=sent_to_model,
        used_redacted_preview=True,
        model_profile_id=profile.id,
        fallback_used=fallback_used,
        risk_warnings=warnings,
    )


def apply_semantic_summary_to_memory(
    memory: MemoryRecord,
    semantic: SemanticSummaryOut,
) -> None:
    memory.semantic_summary = semantic.summary
    memory.semantic_entities = semantic.entities
    memory.semantic_triggers = semantic.triggers
    memory.semantic_facts = semantic.facts
    memory.summary_embedding = embed_text(semantic.summary)
    memory.summary_model_profile_id = semantic.model_profile_id
    memory.summary_confidence = semantic.confidence
    memory.summary_updated_at = utcnow()


def apply_semantic_summary_to_inbox(
    item: MemoryInboxItemRecord,
    semantic: SemanticSummaryOut,
) -> None:
    item.semantic_summary = semantic.summary
    item.semantic_entities = semantic.entities
    item.semantic_triggers = semantic.triggers


def ensure_memory_summary(
    session: Session,
    agent: AgentIdentity,
    memory: MemoryRecord,
    model_profile_id: str | None = None,
) -> SemanticSummaryOut:
    if memory.semantic_summary:
        return SemanticSummaryOut(
            summary=memory.semantic_summary,
            entities=memory.semantic_entities or [],
            triggers=memory.semantic_triggers or [],
            facts=memory.semantic_facts or [],
            confidence=float(memory.summary_confidence or 0.0),
            sent_to_model=False,
            model_profile_id=memory.summary_model_profile_id,
        )
    semantic = generate_memory_summary(
        session,
        agent,
        memory.content or "",
        memory.project_id,
        MemoryZone(memory.memory_zone) if memory.memory_zone else MemoryZone.PUBLIC_PROFILE,
        model_profile_id,
    )
    apply_semantic_summary_to_memory(memory, semantic)
    session.flush()
    return semantic


def _overlap_score(left: list[str], right: list[str]) -> float:
    left_tokens = {token for item in left for token in tokenize(item)}
    right_tokens = {token for item in right for token in tokenize(item)}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(len(left_tokens), 1)


def _summary_text(record: MemoryRecord) -> str:
    return record.semantic_summary or (record.content or "")[:300]


def retrieve_summary_candidates(
    session: Session,
    agent: AgentIdentity,
    summary: SemanticSummaryOut,
    project_id: str | None,
    zone: MemoryZone,
    top_k: int = 8,
) -> list[SemanticCandidateOut]:
    query = select(MemoryRecord).where(
        MemoryRecord.tenant_id == agent.tenant_id,
        MemoryRecord.deleted_at.is_(None),
        MemoryRecord.status == ProposalStatus.APPROVED.value,
        MemoryRecord.memory_zone == zone.value,
    )
    records = list(session.scalars(query))
    query_embedding = embed_text(summary.summary)
    scored: list[CandidateScore] = []
    for record in records:
        if record.memory_zone != MemoryZone.PUBLIC_PROFILE.value and record.project_id != project_id:
            continue
        record_summary = _summary_text(record)
        summary_embedding = record.summary_embedding or embed_text(record_summary)
        trigger = _overlap_score(summary.triggers, record.semantic_triggers or [])
        entity = _overlap_score(summary.entities, record.semantic_entities or [])
        keyword = _overlap_score([summary.summary], [record_summary, record.content or ""])
        vector = max(cosine_similarity(query_embedding, summary_embedding), 0.0)
        score = trigger * 0.3 + entity * 0.25 + keyword * 0.2 + vector * 0.15
        if score <= 0:
            continue
        scored.append(
            CandidateScore(
                record=record,
                score=score,
                reason=(
                    f"trigger={trigger:.2f}, entity={entity:.2f}, "
                    f"keyword={keyword:.2f}, vector={vector:.2f}"
                ),
            )
        )
    scored.sort(key=lambda item: item.score, reverse=True)
    candidates: list[SemanticCandidateOut] = []
    for item in scored[:top_k]:
        record = item.record
        candidates.append(
            SemanticCandidateOut(
                memory_id=record.id,
                summary=_summary_text(record),
                content_preview=(record.content or "")[:260],
                zone=MemoryZone(record.memory_zone) if record.memory_zone else None,
                memory_type=MemoryType(record.memory_type),
                sensitivity=Sensitivity(record.sensitivity),
                score=round(item.score, 4),
                reason=item.reason,
            )
        )
    return candidates


def decision_example_to_out(record: MemoryDecisionExampleRecord) -> DecisionExampleOut:
    return DecisionExampleOut(
        id=record.id,
        project_id=record.project_id,
        zone=MemoryZone(record.zone) if record.zone else None,
        new_memory_summary=record.new_memory_summary,
        candidate_memory_summary=record.candidate_memory_summary,
        llm_relationship=record.llm_relationship,
        llm_confidence=float(record.llm_confidence or 0.0),
        user_decision=record.user_decision,
        superseded_memory_id=record.superseded_memory_id,
        final_memory_id=record.final_memory_id,
        created_at=record.created_at,
    )


def similar_decision_examples(
    session: Session,
    agent: AgentIdentity,
    summary: str,
    project_id: str | None,
    zone: MemoryZone,
    limit: int = 3,
) -> list[DecisionExampleOut]:
    records = list(
        session.scalars(
            select(MemoryDecisionExampleRecord).where(
                MemoryDecisionExampleRecord.tenant_id == agent.tenant_id,
                MemoryDecisionExampleRecord.project_id == project_id,
                MemoryDecisionExampleRecord.zone == zone.value,
            )
        )
    )
    query_embedding = embed_text(summary)
    scored = [
        (
            cosine_similarity(query_embedding, embed_text(record.new_memory_summary or "")),
            record,
        )
        for record in records
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    return [decision_example_to_out(record) for score, record in scored[:limit] if score > 0.05]


def _fallback_relationship(
    summary: SemanticSummaryOut,
    candidates: list[SemanticCandidateOut],
) -> SemanticRelationshipOut:
    if not candidates:
        return SemanticRelationshipOut(
            relationship="separate",
            confidence=0.45,
            reason="No similar semantic summaries were found.",
            recommended_action="save_separate",
            fallback_used=True,
        )
    best = candidates[0]
    update_cues = ("now", "recently", "moved", "changed", "no longer", "instead", "现在", "最近", "搬家", "改成", "不再")
    duplicate = best.score >= 0.92
    update = best.score >= 0.18 and any(cue in summary.summary.lower() for cue in update_cues)
    if duplicate:
        relationship = "duplicate"
        action = "merge"
        confidence = min(0.82, best.score)
    elif update:
        relationship = "update"
        action = "approve_update"
        confidence = max(0.8, min(0.9, best.score + 0.55))
    elif best.score >= 0.28:
        relationship = "uncertain"
        action = "ask_user"
        confidence = 0.62
    else:
        relationship = "separate"
        action = "save_separate"
        confidence = 0.5
    return SemanticRelationshipOut(
        relationship=relationship,
        confidence=confidence,
        candidate_memory_id=best.memory_id,
        reason=f"Fallback semantic comparison selected the closest summary: {best.summary[:180]}",
        recommended_action=action,
        fallback_used=True,
    )


def judge_memory_relationship(
    session: Session,
    agent: AgentIdentity,
    new_summary: SemanticSummaryOut,
    candidates: list[SemanticCandidateOut],
    decision_examples: list[DecisionExampleOut],
    model_profile_id: str | None = None,
) -> SemanticRelationshipOut:
    from memory_gateway.service import get_model_profile

    if not candidates:
        return _fallback_relationship(new_summary, candidates)
    profile = get_model_profile(session, agent, model_profile_id)
    if profile.provider == ModelProvider.RULE_ONLY.value:
        return _fallback_relationship(new_summary, candidates)
    try:
        payload = _call_chat_json(
            profile,
            system=(
                "Return strict JSON only. Decide whether a new memory is duplicate, update, "
                "conflict, separate, or uncertain compared with candidate memories. "
                "Never decide permissions or approvals. Keys: relationship, confidence, "
                "candidate_memory_id, reason, recommended_action."
            ),
            user=json.dumps(
                {
                    "new_memory": {
                        "summary": new_summary.summary,
                        "entities": new_summary.entities,
                        "triggers": new_summary.triggers,
                        "facts": new_summary.facts,
                    },
                    "candidate_memories": [
                        {
                            "memory_id": candidate.memory_id,
                            "summary": candidate.summary,
                            "preview": candidate.content_preview,
                            "score": candidate.score,
                        }
                        for candidate in candidates[:5]
                    ],
                    "previous_user_decisions": [
                        {
                            "new_memory_summary": example.new_memory_summary,
                            "candidate_memory_summary": example.candidate_memory_summary,
                            "llm_relationship": example.llm_relationship,
                            "user_decision": example.user_decision,
                        }
                        for example in decision_examples[:3]
                    ],
                },
                ensure_ascii=False,
            ),
        )
        relationship = str(payload.get("relationship") or "uncertain").lower()
        if relationship not in RELATIONSHIP_TO_KIND:
            relationship = "uncertain"
        candidate_id = str(payload.get("candidate_memory_id") or "") or candidates[0].memory_id
        confidence = max(0.0, min(float(payload.get("confidence") or 0.0), 1.0))
        if 0.55 <= confidence < 0.8 and relationship in {"update", "conflict"}:
            relationship = "uncertain"
        return SemanticRelationshipOut(
            relationship=relationship,
            confidence=confidence,
            candidate_memory_id=candidate_id,
            reason=str(payload.get("reason") or "")[:1000],
            recommended_action=str(payload.get("recommended_action") or "ask_user"),
            sent_to_model=True,
            fallback_used=False,
        )
    except Exception as error:
        result = _fallback_relationship(new_summary, candidates)
        result.reason = f"{result.reason} Model judge failed: {error}"
        return result


def relationship_to_inbox_kind(relationship: str, confidence: float) -> InboxProposalKind:
    if confidence < 0.55:
        return InboxProposalKind.NEW
    return RELATIONSHIP_TO_KIND.get(relationship, InboxProposalKind.CONFLICT)


def needs_user_decision(relationship: str, confidence: float) -> bool:
    return relationship in {"update", "conflict", "uncertain"} or 0.55 <= confidence < 0.8


def record_decision_example(
    session: Session,
    agent: AgentIdentity,
    *,
    item: MemoryInboxItemRecord,
    user_decision: str,
    final_memory_id: str | None = None,
    superseded_memory_id: str | None = None,
) -> None:
    candidate_summary = ""
    candidate_id = superseded_memory_id or item.supersedes_memory_id or ((item.candidate_memory_ids or [None])[0])
    if candidate_id:
        candidate = session.get(MemoryRecord, candidate_id)
        if candidate:
            candidate_summary = candidate.semantic_summary or candidate.content[:300]
    session.add(
        MemoryDecisionExampleRecord(
            id=new_id("dec"),
            tenant_id=agent.tenant_id,
            project_id=item.project_id,
            zone=item.suggested_zone,
            new_memory_summary=item.semantic_summary or item.redacted_preview[:300],
            candidate_memory_summary=candidate_summary,
            llm_relationship=item.llm_relationship or "uncertain",
            llm_confidence=float(item.llm_confidence or 0.0),
            user_decision=user_decision,
            superseded_memory_id=superseded_memory_id,
            final_memory_id=final_memory_id,
        )
    )
    session.flush()


def list_decision_examples(
    session: Session,
    agent: AgentIdentity,
    *,
    project_id: str | None = None,
    zone: MemoryZone | None = None,
    limit: int = 50,
) -> list[DecisionExampleOut]:
    query = select(MemoryDecisionExampleRecord).where(
        MemoryDecisionExampleRecord.tenant_id == agent.tenant_id
    )
    if project_id is not None:
        query = query.where(MemoryDecisionExampleRecord.project_id == project_id)
    if zone is not None:
        query = query.where(MemoryDecisionExampleRecord.zone == zone.value)
    records = list(session.scalars(query.order_by(MemoryDecisionExampleRecord.created_at.desc()).limit(limit)))
    return [decision_example_to_out(record) for record in records]


def rebuild_missing_summaries(
    session: Session,
    agent: AgentIdentity,
    *,
    model_profile_id: str | None = None,
    limit: int = 500,
) -> tuple[int, int, str]:
    records = list(
        session.scalars(
            select(MemoryRecord)
            .where(
                MemoryRecord.tenant_id == agent.tenant_id,
                MemoryRecord.deleted_at.is_(None),
                MemoryRecord.status == ProposalStatus.APPROVED.value,
            )
            .limit(limit)
        )
    )
    rebuilt = 0
    failed = 0
    for memory in records:
        try:
            semantic = generate_memory_summary(
                session,
                agent,
                memory.content or "",
                memory.project_id,
                MemoryZone(memory.memory_zone) if memory.memory_zone else MemoryZone.PUBLIC_PROFILE,
                model_profile_id,
            )
            apply_semantic_summary_to_memory(memory, semantic)
            rebuilt += 1
        except Exception:
            failed += 1
    session.flush()
    audit_id = audit_event(
        session,
        agent,
        AuditAction.MODEL_PROCESS,
        "semantic_summary_rebuild",
        None,
        {"rebuilt_count": rebuilt, "failed_count": failed},
    )
    return rebuilt, failed, audit_id
