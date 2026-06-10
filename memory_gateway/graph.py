from __future__ import annotations

import hashlib
import re
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from .config import get_settings
from .db import MemoryRecord
from .schemas import GraphCardOut
from .types import MemoryType, MemoryZone, Sensitivity


GRAPH_ENTITY_TYPES = {
    "person",
    "project",
    "organization",
    "tool",
    "requirement",
    "decision",
    "preference",
    "lesson",
    "sensitive_reference",
    "payment_reference",
}

GRAPH_RELATION_TYPES = {
    "REQUIRES",
    "PREFERS",
    "DECIDED",
    "AVOIDS",
    "USES",
    "RELATED_TO",
    "NEEDS_CONFIRMATION",
}

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
}


@dataclass(frozen=True)
class GraphHealth:
    available: bool
    enabled: bool
    reason: str | None = None


@dataclass(frozen=True)
class GraphCandidate:
    subject_name: str
    subject_type: str
    relation_type: str
    object_name: str
    object_type: str
    summary: str


@dataclass(frozen=True)
class GraphWriteResult:
    available: bool
    indexed_count: int = 0
    reason: str | None = None


@dataclass(frozen=True)
class GraphQueryResult:
    available: bool
    cards: list[GraphCardOut]
    reason: str | None = None


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def _entity_id(tenant_id: str, name: str, entity_type: str) -> str:
    return f"ent:{tenant_id}:{entity_type}:{_slug(name)}"


def _relation_id(
    tenant_id: str, subject_name: str, relation_type: str, object_name: str
) -> str:
    digest = hashlib.sha1(
        f"{tenant_id}|{subject_name}|{relation_type}|{object_name}".encode("utf-8")
    ).hexdigest()[:16]
    return f"rel:{tenant_id}:{digest}"


def _project_name(memory: MemoryRecord) -> str:
    return memory.project_id or "Personal memory"


def _relation_for_memory(memory: MemoryRecord, content: str) -> str:
    lowered = content.lower()
    if memory.memory_type == MemoryType.ANTI_PATTERN.value or any(
        term in lowered for term in ("avoid", "do not", "不要", "避免")
    ):
        return "AVOIDS"
    if any(term in lowered for term in ("decided", "decision", "决定")):
        return "DECIDED"
    if any(term in lowered for term in ("prefer", "preferred", "优先", "偏好")):
        return "PREFERS"
    if any(term in lowered for term in ("require", "must", "should", "需要", "要求")):
        return "REQUIRES"
    return "RELATED_TO"


def _requirement_object(content: str) -> str:
    sentence = re.split(r"[。\n.]", content.strip(), maxsplit=1)[0].strip()
    if not sentence:
        return "Captured requirement"
    return sentence[:120]


def extract_graph_candidates(memory: MemoryRecord) -> list[GraphCandidate]:
    content = memory.content or ""
    lowered = content.lower()
    subject = _project_name(memory)

    if memory.memory_zone == MemoryZone.PAYMENT_REFERENCE.value:
        return [
            GraphCandidate(
                subject,
                "project" if memory.project_id else "preference",
                "NEEDS_CONFIRMATION",
                "Payment confirmation",
                "payment_reference",
                "Payment-related tasks require explicit user confirmation.",
            )
        ]
    if memory.memory_zone == MemoryZone.SENSITIVE_VAULT.value:
        return [
            GraphCandidate(
                subject,
                "project" if memory.project_id else "preference",
                "NEEDS_CONFIRMATION",
                "Sensitive information reference",
                "sensitive_reference",
                "Sensitive information is stored as a reference and requires confirmation.",
            )
        ]

    relation = _relation_for_memory(memory, content)
    candidates: list[GraphCandidate] = []
    for keyword, label in TOOL_KEYWORDS.items():
        if keyword in lowered:
            candidates.append(
                GraphCandidate(
                    subject,
                    "project" if memory.project_id else "preference",
                    relation if relation != "RELATED_TO" else "USES",
                    label,
                    "tool",
                    f"{subject} {relation.lower().replace('_', ' ')} {label}.",
                )
            )

    if not candidates:
        object_type = "lesson" if memory.memory_type == MemoryType.LESSON.value else "requirement"
        if memory.memory_type == MemoryType.PREFERENCE.value:
            object_type = "preference"
        candidates.append(
            GraphCandidate(
                subject,
                "project" if memory.project_id else "preference",
                relation,
                _requirement_object(content),
                object_type,
                _requirement_object(content),
            )
        )
    return candidates


def _safe_relation_type(value: str) -> str:
    if value not in GRAPH_RELATION_TYPES:
        return "RELATED_TO"
    return value


def _risk_note(sensitivity: str, zone: str | None) -> str:
    if zone in {MemoryZone.SENSITIVE_VAULT.value, MemoryZone.PAYMENT_REFERENCE.value}:
        return "High-risk reference. Raw secrets are not returned."
    if sensitivity == Sensitivity.HIGH.value:
        return "High sensitivity. Access was allowed only after policy checks."
    if sensitivity == Sensitivity.MEDIUM.value:
        return "Project or personal context. Access depends on an active grant."
    return "Low-risk profile context."


def _graph_card_from_record(record: dict[str, Any]) -> GraphCardOut:
    source_ids = list(record.get("source_memory_ids") or [])
    zone = record.get("memory_zone")
    sensitivity = record.get("sensitivity") or Sensitivity.LOW.value
    relation = record.get("relation_type") or "RELATED_TO"
    subject = record.get("subject_name") or "Memory"
    obj = record.get("object_name") or "Related fact"
    summary = record.get("summary") or f"{subject} {relation.lower()} {obj}"
    return GraphCardOut(
        id=record.get("relation_id") or hashlib.sha1(summary.encode("utf-8")).hexdigest()[:16],
        title=f"{subject} -> {obj}",
        subtitle=summary,
        entity_type=record.get("object_type") or "requirement",
        relation_type=relation,
        zone=MemoryZone(zone) if zone else None,
        sensitivity=Sensitivity(sensitivity),
        source_count=len(source_ids),
        source_memory_ids=source_ids,
        why_visible="Visible because all source memories passed SQL ACL and grant checks.",
        risk_note=_risk_note(sensitivity, zone),
    )


class Neo4jGraphClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._driver: Any | None = None
        self._reason: str | None = None
        if not self.settings.graph_enabled:
            self._reason = "graph is disabled"
            return
        try:
            from neo4j import GraphDatabase

            self._driver = GraphDatabase.driver(
                self.settings.neo4j_uri,
                auth=(self.settings.neo4j_user, self.settings.neo4j_password),
                connection_timeout=1.5,
                connection_acquisition_timeout=1.5,
            )
        except Exception as error:  # pragma: no cover - depends on optional runtime
            self._driver = None
            self._reason = str(error)

    def health(self) -> GraphHealth:
        if not self.settings.graph_enabled:
            return GraphHealth(False, False, "graph is disabled")
        if not self._driver:
            return GraphHealth(False, True, self._reason or "neo4j driver unavailable")
        reachable, reason = self._socket_reachable()
        if not reachable:
            return GraphHealth(False, True, reason)
        try:
            with self._driver.session(database=self.settings.neo4j_database) as session:
                session.run("RETURN 1 AS ok").single()
            return GraphHealth(True, True)
        except Exception as error:  # pragma: no cover - depends on optional runtime
            return GraphHealth(False, True, str(error))

    def _socket_reachable(self) -> tuple[bool, str | None]:
        parsed = urlparse(self.settings.neo4j_uri)
        host = parsed.hostname
        port = parsed.port or 7687
        if not host:
            return False, "neo4j uri has no host"
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True, None
        except OSError as error:
            return (
                False,
                (
                    f"Neo4j is not reachable at {host}:{port}. "
                    "Start Docker Desktop and run `docker compose up neo4j`, "
                    "or use `docker compose up --build` for the full stack."
                ),
            )

    def upsert_memory(self, memory: MemoryRecord) -> GraphWriteResult:
        health = self.health()
        if not health.available or not self._driver:
            return GraphWriteResult(False, 0, health.reason)
        candidates = extract_graph_candidates(memory)
        try:
            with self._driver.session(database=self.settings.neo4j_database) as session:
                for candidate in candidates:
                    relation_type = _safe_relation_type(candidate.relation_type)
                    subject_id = _entity_id(
                        memory.tenant_id, candidate.subject_name, candidate.subject_type
                    )
                    object_id = _entity_id(memory.tenant_id, candidate.object_name, candidate.object_type)
                    relation_id = _relation_id(
                        memory.tenant_id,
                        candidate.subject_name,
                        relation_type,
                        candidate.object_name,
                    )
                    query = f"""
                    MERGE (s:MemoryEntity {{id: $subject_id}})
                    SET s.name = $subject_name,
                        s.entity_type = $subject_type,
                        s.tenant_id = $tenant_id,
                        s.project_id = $project_id,
                        s.status = 'active',
                        s.source_memory_ids =
                          CASE WHEN $memory_id IN coalesce(s.source_memory_ids, [])
                          THEN coalesce(s.source_memory_ids, [])
                          ELSE coalesce(s.source_memory_ids, []) + [$memory_id] END
                    MERGE (o:MemoryEntity {{id: $object_id}})
                    SET o.name = $object_name,
                        o.entity_type = $object_type,
                        o.tenant_id = $tenant_id,
                        o.project_id = $project_id,
                        o.status = 'active',
                        o.source_memory_ids =
                          CASE WHEN $memory_id IN coalesce(o.source_memory_ids, [])
                          THEN coalesce(o.source_memory_ids, [])
                          ELSE coalesce(o.source_memory_ids, []) + [$memory_id] END
                    MERGE (s)-[r:{relation_type} {{relation_id: $relation_id}}]->(o)
                    SET r.tenant_id = $tenant_id,
                        r.project_id = $project_id,
                        r.memory_zone = $memory_zone,
                        r.visibility = $visibility,
                        r.sensitivity = $sensitivity,
                        r.summary = $summary,
                        r.status = 'active',
                        r.source_memory_ids =
                          CASE WHEN $memory_id IN coalesce(r.source_memory_ids, [])
                          THEN coalesce(r.source_memory_ids, [])
                          ELSE coalesce(r.source_memory_ids, []) + [$memory_id] END
                    """
                    session.run(
                        query,
                        subject_id=subject_id,
                        subject_name=candidate.subject_name,
                        subject_type=candidate.subject_type,
                        object_id=object_id,
                        object_name=candidate.object_name,
                        object_type=candidate.object_type,
                        relation_id=relation_id,
                        tenant_id=memory.tenant_id,
                        project_id=memory.project_id,
                        memory_id=memory.id,
                        memory_zone=memory.memory_zone,
                        visibility=memory.visibility,
                        sensitivity=memory.sensitivity,
                        summary=candidate.summary,
                    )
            return GraphWriteResult(True, len(candidates))
        except Exception as error:  # pragma: no cover - depends on optional runtime
            return GraphWriteResult(False, 0, str(error))

    def mark_memory_inactive(self, memory_id: str) -> GraphWriteResult:
        health = self.health()
        if not health.available or not self._driver:
            return GraphWriteResult(False, 0, health.reason)
        try:
            with self._driver.session(database=self.settings.neo4j_database) as session:
                session.run(
                    """
                    MATCH ()-[r]->()
                    WHERE $memory_id IN coalesce(r.source_memory_ids, [])
                    SET r.source_memory_ids = [id IN r.source_memory_ids WHERE id <> $memory_id]
                    """
                    ,
                    memory_id=memory_id,
                )
                session.run(
                    """
                    MATCH (n:MemoryEntity)
                    WHERE $memory_id IN coalesce(n.source_memory_ids, [])
                    SET n.source_memory_ids = [id IN n.source_memory_ids WHERE id <> $memory_id]
                    """
                    ,
                    memory_id=memory_id,
                )
                session.run("MATCH ()-[r]->() WHERE size(coalesce(r.source_memory_ids, [])) = 0 SET r.status = 'inactive'")
                session.run("MATCH (n:MemoryEntity) WHERE size(coalesce(n.source_memory_ids, [])) = 0 SET n.status = 'inactive'")
            return GraphWriteResult(True, 1)
        except Exception as error:  # pragma: no cover - depends on optional runtime
            return GraphWriteResult(False, 0, str(error))

    def mark_tenant_inactive(self, tenant_id: str) -> GraphWriteResult:
        health = self.health()
        if not health.available or not self._driver:
            return GraphWriteResult(False, 0, health.reason)
        try:
            with self._driver.session(database=self.settings.neo4j_database) as session:
                session.run(
                    "MATCH ()-[r]->() WHERE r.tenant_id = $tenant_id SET r.status = 'inactive'",
                    tenant_id=tenant_id,
                )
                session.run(
                    "MATCH (n:MemoryEntity) WHERE n.tenant_id = $tenant_id SET n.status = 'inactive'",
                    tenant_id=tenant_id,
                )
            return GraphWriteResult(True, 1)
        except Exception as error:  # pragma: no cover - depends on optional runtime
            return GraphWriteResult(False, 0, str(error))

    def search(
        self,
        tenant_id: str,
        query: str,
        allowed_memory_ids: list[str],
        top_k: int,
    ) -> GraphQueryResult:
        health = self.health()
        if not health.available or not self._driver:
            return GraphQueryResult(False, [], health.reason)
        if not allowed_memory_ids:
            return GraphQueryResult(True, [])
        lowered_query = query.lower().strip()
        try:
            with self._driver.session(database=self.settings.neo4j_database) as session:
                records = session.run(
                    """
                    MATCH (s:MemoryEntity)-[r]->(o:MemoryEntity)
                    WHERE r.tenant_id = $tenant_id
                      AND r.status = 'active'
                      AND all(id IN coalesce(r.source_memory_ids, []) WHERE id IN $allowed_memory_ids)
                      AND (
                        $query = ''
                        OR toLower(coalesce(s.name, '')) CONTAINS $query
                        OR toLower(coalesce(o.name, '')) CONTAINS $query
                        OR toLower(coalesce(r.summary, '')) CONTAINS $query
                      )
                    RETURN r.relation_id AS relation_id,
                           type(r) AS relation_type,
                           s.name AS subject_name,
                           s.entity_type AS subject_type,
                           o.name AS object_name,
                           o.entity_type AS object_type,
                           r.summary AS summary,
                           r.memory_zone AS memory_zone,
                           r.sensitivity AS sensitivity,
                           r.source_memory_ids AS source_memory_ids
                    LIMIT $top_k
                    """,
                    tenant_id=tenant_id,
                    query=lowered_query,
                    allowed_memory_ids=allowed_memory_ids,
                    top_k=top_k,
                )
                cards = [_graph_card_from_record(dict(record)) for record in records]
            return GraphQueryResult(True, cards)
        except Exception as error:  # pragma: no cover - depends on optional runtime
            return GraphQueryResult(False, [], str(error))

    def explain_entity(
        self,
        tenant_id: str,
        entity_id: str,
        allowed_memory_ids: list[str],
        top_k: int = 10,
    ) -> GraphQueryResult:
        health = self.health()
        if not health.available or not self._driver:
            return GraphQueryResult(False, [], health.reason)
        try:
            with self._driver.session(database=self.settings.neo4j_database) as session:
                records = session.run(
                    """
                    MATCH (s:MemoryEntity)-[r]-(o:MemoryEntity)
                    WHERE r.tenant_id = $tenant_id
                      AND (s.id = $entity_id OR o.id = $entity_id)
                      AND r.status = 'active'
                      AND all(id IN coalesce(r.source_memory_ids, []) WHERE id IN $allowed_memory_ids)
                    RETURN r.relation_id AS relation_id,
                           type(r) AS relation_type,
                           s.name AS subject_name,
                           s.entity_type AS subject_type,
                           o.name AS object_name,
                           o.entity_type AS object_type,
                           r.summary AS summary,
                           r.memory_zone AS memory_zone,
                           r.sensitivity AS sensitivity,
                           r.source_memory_ids AS source_memory_ids
                    LIMIT $top_k
                    """,
                    tenant_id=tenant_id,
                    entity_id=entity_id,
                    allowed_memory_ids=allowed_memory_ids,
                    top_k=top_k,
                )
                cards = [_graph_card_from_record(dict(record)) for record in records]
            return GraphQueryResult(True, cards)
        except Exception as error:  # pragma: no cover - depends on optional runtime
            return GraphQueryResult(False, [], str(error))


def get_graph_client() -> Neo4jGraphClient:
    return Neo4jGraphClient()
