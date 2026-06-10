from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from memory_gateway.db import MemoryRecord
from memory_gateway.embedding import cosine_similarity, embed_text, tokenize
from memory_gateway.schemas import MemoryCardOut, MemoryOut
from memory_gateway.security import AgentIdentity
from memory_gateway.types import ContentKind, MemoryType, MemoryZone, Sensitivity, Visibility

from .access import DeniedZone, readable_memories_for_zones
from .semantic import ensure_memory_summary


@dataclass(frozen=True)
class RankedMemory:
    record: MemoryRecord
    score: float
    vector_score: float
    keyword_score: float
    recency_score: float
    importance_score: float


@dataclass(frozen=True)
class RetrievalResult:
    grant_id: str | None
    ranked: list[RankedMemory]
    memories: list[MemoryOut]
    source_cards: list[MemoryCardOut]
    denied_zones: list[DeniedZone]
    candidate_count_after_acl: int


def memory_to_out(record: MemoryRecord, score: float | None = None) -> MemoryOut:
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
        semantic_summary=record.semantic_summary or "",
        semantic_entities=record.semantic_entities or [],
        semantic_triggers=record.semantic_triggers or [],
        semantic_facts=record.semantic_facts or [],
        summary_confidence=float(record.summary_confidence or 0.0),
        score=score,
        created_at=record.created_at,
    )


def _keyword_score(query: str, content: str, tags: list[str]) -> float:
    query_tokens = set(tokenize(query))
    if not query_tokens:
        return 0.0
    content_tokens = set(tokenize(content + " " + " ".join(tags or [])))
    if not content_tokens:
        return 0.0
    overlap = len(query_tokens & content_tokens)
    return overlap / max(len(query_tokens), 1)


def _recency_score(created_at: datetime | None) -> float:
    if not created_at:
        return 0.0
    now = datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    days = max((now - created_at).days, 0)
    if days <= 1:
        return 1.0
    if days <= 7:
        return 0.7
    if days <= 30:
        return 0.4
    return 0.1


def _importance_score(record: MemoryRecord) -> float:
    score = 0.0
    if record.memory_type in {MemoryType.LESSON.value, MemoryType.ANTI_PATTERN.value}:
        score += 0.28
    if record.memory_type == MemoryType.PROCEDURE.value:
        score += 0.18
    if record.memory_zone == MemoryZone.WORK_CONTEXT.value:
        score += 0.08
    tags = set(record.tags or [])
    if {"important", "policy", "decision", "requirement", "approval"} & tags:
        score += 0.16
    return min(score, 0.5)


def _memory_card(record: MemoryRecord, score: float, why_visible: str) -> MemoryCardOut:
    zone = MemoryZone(record.memory_zone) if record.memory_zone else None
    memory_type = MemoryType(record.memory_type)
    title_map = {
        MemoryType.RELATIONSHIP: "Relationship Memory",
        MemoryType.PREFERENCE: "Preference Memory",
        MemoryType.PROCEDURE: "Procedure Memory",
        MemoryType.LESSON: "Lesson Memory",
        MemoryType.ANTI_PATTERN: "Anti-Pattern Memory",
        MemoryType.CONTEXT: "Context Memory",
    }
    return MemoryCardOut(
        id=record.id,
        title=title_map.get(memory_type, "Memory"),
        subtitle=f"{zone.value if zone else 'unzone'} / {record.source}",
        zone=zone,
        memory_type=memory_type,
        sensitivity=Sensitivity(record.sensitivity),
        source=record.source,
        why_visible=why_visible,
        preview=(record.content or "")[:260],
        score=round(score, 4),
    )


def rank_records(query: str, records: list[MemoryRecord]) -> list[RankedMemory]:
    query_embedding = embed_text(query)
    ranked: list[RankedMemory] = []
    for record in records:
        vector = cosine_similarity(query_embedding, record.embedding or [])
        keyword = _keyword_score(query, record.content or "", record.tags or [])
        recency = _recency_score(record.created_at)
        importance = _importance_score(record)
        score = (
            max(vector, 0) * 0.42
            + keyword * 0.34
            + recency * 0.08
            + importance * 0.16
        )
        ranked.append(
            RankedMemory(
                record=record,
                score=score,
                vector_score=vector,
                keyword_score=keyword,
                recency_score=recency,
                importance_score=importance,
            )
        )
    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked


def _semantic_overlap(query: str, values: list[str]) -> float:
    query_tokens = set(tokenize(query))
    value_tokens = {token for item in values for token in tokenize(item)}
    if not query_tokens or not value_tokens:
        return 0.0
    return len(query_tokens & value_tokens) / max(len(query_tokens), 1)


def rank_records_summary_first(query: str, records: list[MemoryRecord]) -> list[RankedMemory]:
    query_embedding = embed_text(query)
    ranked: list[RankedMemory] = []
    for record in records:
        summary = record.semantic_summary or (record.content or "")[:300]
        summary_embedding = record.summary_embedding or embed_text(summary)
        vector = cosine_similarity(query_embedding, summary_embedding)
        keyword = _keyword_score(query, summary, list(record.tags or []))
        trigger = _semantic_overlap(query, record.semantic_triggers or [])
        entity = _semantic_overlap(query, record.semantic_entities or [])
        recency = _recency_score(record.created_at)
        importance = _importance_score(record)
        score = (
            trigger * 0.30
            + entity * 0.25
            + keyword * 0.20
            + max(vector, 0) * 0.15
            + (recency * 0.04 + importance * 0.06)
        )
        ranked.append(
            RankedMemory(
                record=record,
                score=score,
                vector_score=vector,
                keyword_score=keyword,
                recency_score=recency,
                importance_score=importance,
            )
        )
    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked


def _dedupe_ranked(items: list[RankedMemory]) -> list[RankedMemory]:
    seen: set[str] = set()
    deduped: list[RankedMemory] = []
    for item in items:
        key = " ".join(tokenize(item.record.content or ""))[:400]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def retrieve_for_context(
    session,
    agent: AgentIdentity,
    *,
    query: str,
    project_id: str | None,
    zones: list[MemoryZone],
    grant_token: str | None,
    memory_types: list[MemoryType] | None,
    top_k: int,
    strict_grant: bool = False,
    retrieval_mode: str = "summary_first",
) -> RetrievalResult:
    grant, allowed_records, denied = readable_memories_for_zones(
        session,
        agent,
        project_id,
        zones,
        grant_token,
        memory_types,
        strict_grant=strict_grant,
    )
    if retrieval_mode == "summary_first":
        for record in allowed_records:
            ensure_memory_summary(session, agent, record)
        ranked = _dedupe_ranked(rank_records_summary_first(query, allowed_records))[:top_k]
    else:
        ranked = _dedupe_ranked(rank_records(query, allowed_records))[:top_k]
    memories = [memory_to_out(item.record, round(item.score, 4)) for item in ranked]
    cards = [
        _memory_card(
            item.record,
            item.score,
            "Visible after SQL ACL, zone, status, and active grant checks.",
        )
        for item in ranked
    ]
    return RetrievalResult(
        grant_id=grant.id if grant else None,
        ranked=ranked,
        memories=memories,
        source_cards=cards,
        denied_zones=denied,
        candidate_count_after_acl=len(allowed_records),
    )
