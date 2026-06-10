from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_gateway.db import MemoryFactRecord, MemoryRecord, utcnow
from memory_gateway.embedding import tokenize
from memory_gateway.policy import max_sensitivity
from memory_gateway.schemas import FactCardOut
from memory_gateway.security import AgentIdentity
from memory_gateway.types import AuditAction, FactStatus, MemoryType, MemoryZone, Sensitivity, Visibility

from .audit import audit_event, new_id


TOOL_KEYWORDS = {
    "postgres": "Postgres",
    "pgvector": "pgvector",
    "sqlite": "SQLite",
    "neo4j": "Neo4j",
    "fastapi": "FastAPI",
    "sqlalchemy": "SQLAlchemy",
    "docker": "Docker",
    "tauri": "Tauri",
    "react": "React",
    "langgraph": "LangGraph",
    "crewai": "CrewAI",
    "ollama": "Ollama",
    "openai": "OpenAI-compatible model",
    "claude": "Claude",
    "codex": "Codex",
}

RELATIONSHIP_PATTERNS = [
    (r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b\s+(?:is|as)\s+(?:my\s+)?(?:close\s+)?(?:best\s+)?friend\b", "FRIEND_OF"),
    (r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b[^.\n]{0,80}\b(?:is|as)\s+(?:my\s+)?(?:best\s+)?friend\b", "FRIEND_OF"),
    (r"\b(?:my\s+)?(?:best\s+)?friend\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b", "FRIEND_OF"),
    (r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b[^.\n]{0,80}\b(?:colleague|coworker|co-worker|teammate|team member)\b", "COLLEAGUE_OF"),
    (r"\b(?:colleague|coworker|co-worker|teammate|team member)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b", "COLLEAGUE_OF"),
    (r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b[^.\n]{0,80}\b(?:client|customer)\b", "CLIENT_OF"),
    (r"\b(?:client|customer)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b", "CLIENT_OF"),
    (r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b[^.\n]{0,80}\b(?:mentor)\b", "MENTOR_OF"),
    (r"\b(?:mentor)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b", "MENTOR_OF"),
    (r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b[^.\n]{0,80}\b(?:family|parent|partner|roommate)\b", "FAMILY_OF"),
    (r"([\u4e00-\u9fff]{1,8})\s*(?:是|为|為).{0,8}(?:我的)?(?:朋友|好友)", "FRIEND_OF"),
    (r"(?:朋友|好友)\s*([\u4e00-\u9fff]{1,8})", "FRIEND_OF"),
    (r"([\u4e00-\u9fff]{1,8})\s*(?:是|为|為).{0,8}(?:我的)?(?:同事|团队成员|團隊成員)", "COLLEAGUE_OF"),
    (r"(?:同事|团队成员|團隊成員)\s*([\u4e00-\u9fff]{1,8})", "COLLEAGUE_OF"),
    (r"([\u4e00-\u9fff]{1,8})\s*(?:是|为|為).{0,8}(?:我的)?(?:客户|客戶)", "CLIENT_OF"),
    (r"(?:客户|客戶)\s*([\u4e00-\u9fff]{1,8})", "CLIENT_OF"),
    (r"([\u4e00-\u9fff]{1,8})\s*(?:是|为|為).{0,8}(?:我的)?(?:导师|導師)", "MENTOR_OF"),
    (r"(?:导师|導師)\s*([\u4e00-\u9fff]{1,8})", "MENTOR_OF"),
    (r"([\u4e00-\u9fff]{1,8})\s*(?:是|为|為).{0,8}(?:我的)?(?:家人|父母|伴侣|伴侶|室友)", "FAMILY_OF"),
]


ZONE_ORDER = {
    None: 0,
    MemoryZone.PUBLIC_PROFILE.value: 1,
    MemoryZone.WORK_CONTEXT.value: 2,
    MemoryZone.PERSONAL_CONTEXT.value: 2,
    MemoryZone.SENSITIVE_VAULT.value: 3,
    MemoryZone.PAYMENT_REFERENCE.value: 4,
}

VISIBILITY_ORDER = {
    Visibility.PUBLIC.value: 1,
    Visibility.PROJECT.value: 2,
    Visibility.PRIVATE.value: 3,
}

SENSITIVITY_ORDER = {
    Sensitivity.LOW.value: 1,
    Sensitivity.MEDIUM.value: 2,
    Sensitivity.HIGH.value: 3,
}


@dataclass(frozen=True)
class FactCandidate:
    subject: str
    predicate: str
    object: str
    fact_type: str
    summary: str
    confidence: float = 0.72


def _first_sentence(content: str) -> str:
    sentence = re.split(r"[\n。.!?]", content.strip(), maxsplit=1)[0].strip()
    return sentence[:180] or "Captured fact"


def _subject(memory: MemoryRecord) -> str:
    if memory.project_id:
        return memory.project_id
    if memory.memory_zone == MemoryZone.PUBLIC_PROFILE.value:
        return "Public profile"
    return "Personal memory"


def _predicate(memory: MemoryRecord, content: str) -> str:
    lowered = content.lower()
    if memory.memory_type == MemoryType.ANTI_PATTERN.value or any(
        term in lowered for term in ("avoid", "do not", "never", "不要", "避免")
    ):
        return "AVOIDS"
    if any(term in lowered for term in ("decided", "decision", "决定")):
        return "DECIDED"
    if memory.memory_type == MemoryType.PREFERENCE.value or any(
        term in lowered for term in ("prefer", "preferred", "优先", "偏好")
    ):
        return "PREFERS"
    if any(term in lowered for term in ("require", "requires", "must", "should", "需要", "要求")):
        return "REQUIRES"
    if memory.memory_type == MemoryType.PROCEDURE.value:
        return "USES"
    return "RELATED_TO"


def _fact_type(memory: MemoryRecord) -> str:
    mapping = {
        MemoryType.LESSON.value: "lesson",
        MemoryType.ANTI_PATTERN.value: "anti_pattern",
        MemoryType.PREFERENCE.value: "preference",
        MemoryType.PROCEDURE.value: "procedure",
        MemoryType.CONTEXT.value: "requirement",
        MemoryType.RELATIONSHIP.value: "relationship",
    }
    return mapping.get(memory.memory_type, "requirement")


def _clean_person_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip(" ,.;:，。；：")).strip()


def _relationship_candidates(memory: MemoryRecord) -> list[FactCandidate]:
    content = memory.content or ""
    candidates: list[FactCandidate] = []
    for pattern, predicate in RELATIONSHIP_PATTERNS:
        for match in re.finditer(pattern, content, flags=re.IGNORECASE):
            name = _clean_person_name(match.group(1))
            if not name or name.lower() in {"my", "friend", "colleague", "client", "customer"}:
                continue
            candidates.append(
                FactCandidate(
                    subject="user",
                    predicate=predicate,
                    object=name,
                    fact_type="relationship",
                    summary=f"User has relationship {predicate.lower().replace('_', ' ')} {name}.",
                    confidence=0.84,
                )
            )
    if candidates:
        deduped: dict[tuple[str, str], FactCandidate] = {}
        for candidate in candidates:
            deduped[(candidate.predicate, candidate.object.lower())] = candidate
        return list(deduped.values())

    name_match = re.search(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b", content)
    if not name_match:
        name_match = re.search(r"([\u4e00-\u9fff]{2,8})", content)
    if name_match:
        name = _clean_person_name(name_match.group(1))
        return [
            FactCandidate(
                subject="user",
                predicate="KNOWS",
                object=name,
                fact_type="relationship",
                summary=f"User knows {name}.",
                confidence=0.62,
            )
        ]
    return []


def extract_fact_candidates(memory: MemoryRecord) -> list[FactCandidate]:
    content = memory.content or ""
    subject = _subject(memory)
    if memory.memory_type == MemoryType.RELATIONSHIP.value:
        candidates = _relationship_candidates(memory)
        if candidates:
            return candidates
    if memory.memory_zone == MemoryZone.PAYMENT_REFERENCE.value:
        return [
            FactCandidate(
                subject=subject,
                predicate="NEEDS_CONFIRMATION",
                object="Payment confirmation",
                fact_type="payment_reference",
                summary="Payment-related actions require explicit user confirmation.",
                confidence=0.9,
            )
        ]
    if memory.memory_zone == MemoryZone.SENSITIVE_VAULT.value:
        return [
            FactCandidate(
                subject=subject,
                predicate="NEEDS_CONFIRMATION",
                object="Sensitive information reference",
                fact_type="sensitive_reference",
                summary="Sensitive information is available only as a redacted reference.",
                confidence=0.88,
            )
        ]

    lowered = content.lower()
    predicate = _predicate(memory, content)
    candidates: list[FactCandidate] = []
    for keyword, label in TOOL_KEYWORDS.items():
        if keyword in lowered:
            relation = predicate if predicate != "RELATED_TO" else "USES"
            candidates.append(
                FactCandidate(
                    subject=subject,
                    predicate=relation,
                    object=label,
                    fact_type="tool",
                    summary=f"{subject} {relation.lower().replace('_', ' ')} {label}.",
                    confidence=0.78,
                )
            )
    if candidates:
        return candidates

    obj = _first_sentence(content)
    return [
        FactCandidate(
            subject=subject,
            predicate=predicate,
            object=obj,
            fact_type=_fact_type(memory),
            summary=obj,
            confidence=0.7,
        )
    ]


def _fact_key(memory: MemoryRecord, candidate: FactCandidate) -> str:
    digest = hashlib.sha1(
        (
            f"{memory.tenant_id}|{memory.project_id}|"
            f"{candidate.subject}|{candidate.predicate}|{candidate.object}"
        ).encode("utf-8")
    ).hexdigest()[:20]
    return f"fact_{digest}"


def _stricter_zone(left: str | None, right: str | None) -> str | None:
    return left if ZONE_ORDER.get(left, 0) >= ZONE_ORDER.get(right, 0) else right


def _stricter_visibility(left: str, right: str) -> str:
    return left if VISIBILITY_ORDER.get(left, 0) >= VISIBILITY_ORDER.get(right, 0) else right


def _stricter_sensitivity(left: str, right: str) -> str:
    return left if SENSITIVITY_ORDER.get(left, 0) >= SENSITIVITY_ORDER.get(right, 0) else right


def upsert_facts_for_memory(
    session: Session,
    agent: AgentIdentity,
    memory: MemoryRecord,
) -> list[MemoryFactRecord]:
    candidates = extract_fact_candidates(memory)
    records: list[MemoryFactRecord] = []
    for candidate in candidates:
        fact_id = _fact_key(memory, candidate)
        record = session.get(MemoryFactRecord, fact_id)
        if record:
            sources = list(dict.fromkeys((record.source_memory_ids or []) + [memory.id]))
            record.source_memory_ids = sources
            record.memory_zone = _stricter_zone(record.memory_zone, memory.memory_zone)
            record.visibility = _stricter_visibility(record.visibility, memory.visibility)
            record.sensitivity = _stricter_sensitivity(record.sensitivity, memory.sensitivity)
            record.confidence = max(record.confidence or 0.0, candidate.confidence)
            record.status = FactStatus.ACTIVE.value
            record.updated_at = utcnow()
        else:
            record = MemoryFactRecord(
                id=fact_id,
                tenant_id=memory.tenant_id,
                project_id=memory.project_id,
                subject=candidate.subject,
                predicate=candidate.predicate,
                object=candidate.object,
                fact_type=candidate.fact_type,
                summary=candidate.summary,
                memory_zone=memory.memory_zone,
                visibility=memory.visibility,
                sensitivity=memory.sensitivity,
                source_memory_ids=[memory.id],
                confidence=candidate.confidence,
                status=FactStatus.ACTIVE.value,
                valid_from=memory.created_at if isinstance(memory.created_at, datetime) else utcnow(),
            )
            session.add(record)
        records.append(record)
    session.flush()
    audit_event(
        session,
        agent,
        AuditAction.FACT_EXTRACT,
        "memory",
        memory.id,
        {"fact_ids": [record.id for record in records]},
    )
    return records


def mark_facts_inactive_for_memory(
    session: Session,
    agent: AgentIdentity,
    memory_id: str,
) -> None:
    facts = session.scalars(
        select(MemoryFactRecord).where(
            MemoryFactRecord.source_memory_ids.contains([memory_id])
        )
    ).all()
    changed: list[str] = []
    for fact in facts:
        fact.source_memory_ids = [item for item in fact.source_memory_ids if item != memory_id]
        if not fact.source_memory_ids:
            fact.status = FactStatus.INACTIVE.value
            fact.valid_to = utcnow()
        fact.updated_at = utcnow()
        changed.append(fact.id)
    if changed:
        session.flush()
        audit_event(
            session,
            agent,
            AuditAction.FACT_EXTRACT,
            "memory",
            memory_id,
            {"inactive_or_updated_fact_ids": changed},
        )


def fact_to_card(fact: MemoryFactRecord, why_visible: str) -> FactCardOut:
    zone = MemoryZone(fact.memory_zone) if fact.memory_zone else None
    return FactCardOut(
        id=fact.id,
        title=f"{fact.subject} -> {fact.object}",
        subtitle=fact.summary or f"{fact.subject} {fact.predicate} {fact.object}",
        fact_type=fact.fact_type,
        relation_type=fact.predicate,
        zone=zone,
        sensitivity=Sensitivity(fact.sensitivity),
        source_count=len(fact.source_memory_ids or []),
        source_memory_ids=fact.source_memory_ids or [],
        why_visible=why_visible,
        confidence=round(float(fact.confidence or 0), 3),
    )


def readable_fact_cards(
    session: Session,
    allowed_memory_ids: set[str],
    query: str,
    top_k: int,
) -> list[FactCardOut]:
    if not allowed_memory_ids:
        return []
    facts = session.scalars(
        select(MemoryFactRecord).where(MemoryFactRecord.status == FactStatus.ACTIVE.value)
    ).all()
    query_tokens = set(tokenize(query))
    scored: list[tuple[float, MemoryFactRecord]] = []
    for fact in facts:
        sources = set(fact.source_memory_ids or [])
        if not sources or not sources.issubset(allowed_memory_ids):
            continue
        haystack = f"{fact.subject} {fact.predicate} {fact.object} {fact.summary}"
        tokens = set(tokenize(haystack))
        overlap = len(query_tokens & tokens)
        score = overlap * 0.25 + float(fact.confidence or 0.0)
        scored.append((score, fact))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        fact_to_card(
            fact,
            "Visible because every source memory passed SQL ACL and grant checks.",
        )
        for _, fact in scored[:top_k]
    ]
