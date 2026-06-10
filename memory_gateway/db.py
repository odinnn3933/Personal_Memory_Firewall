from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentRecord(Base):
    __tablename__ = "agents"

    agent_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    api_key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    roles: Mapped[list[str]] = mapped_column(JSON, default=list)
    allowed_projects: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProjectRecord(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MemoryRecord(Base):
    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    visibility: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    allowed_agent_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    denied_agent_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    memory_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    memory_zone: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    content_kind: Mapped[str] = mapped_column(String(40), default="text")
    capture_source: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    asset_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    redacted: Mapped[bool] = mapped_column(default=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    sensitivity: Mapped[str] = mapped_column(String(40), nullable=False)
    source: Mapped[str] = mapped_column(String(120), default="seed")
    embedding: Mapped[list[float]] = mapped_column(JSON, default=list)
    semantic_summary: Mapped[str] = mapped_column(Text, default="")
    semantic_entities: Mapped[list[str]] = mapped_column(JSON, default=list)
    semantic_triggers: Mapped[list[str]] = mapped_column(JSON, default=list)
    semantic_facts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    summary_embedding: Mapped[list[float]] = mapped_column(JSON, default=list)
    summary_model_profile_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    summary_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="approved", index=True)
    superseded_by_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_agent_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MemoryWriteProposalRecord(Base):
    __tablename__ = "memory_write_proposals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    proposed_by_agent_id: Mapped[str] = mapped_column(String(120), nullable=False)
    memory_type: Mapped[str] = mapped_column(String(40), nullable=False)
    memory_zone: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    content_kind: Mapped[str] = mapped_column(String(40), default="text")
    capture_source: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    asset_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    redacted: Mapped[bool] = mapped_column(default=False)
    visibility: Mapped[str] = mapped_column(String(40), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    sensitivity: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_agent_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approved_memory_id: Mapped[str | None] = mapped_column(
        ForeignKey("memories.id"), nullable=True
    )


class InteractionEventRecord(Base):
    __tablename__ = "interaction_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    task_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(120), nullable=False)
    task_input: Mapped[str] = mapped_column(Text, nullable=False)
    agent_output: Mapped[str] = mapped_column(Text, default="")
    tool_summary: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[str] = mapped_column(String(80), default="unknown")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FeedbackEventRecord(Base):
    __tablename__ = "feedback_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    task_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(120), nullable=False)
    rating: Mapped[int] = mapped_column(nullable=False)
    correction: Mapped[str] = mapped_column(Text, nullable=False)
    expected_behavior: Mapped[str] = mapped_column(Text, default="")
    error_type: Mapped[str] = mapped_column(String(120), default="unknown")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    proposals: Mapped[list["LearnedMemoryProposalRecord"]] = relationship(
        back_populates="feedback"
    )


class LearnedMemoryProposalRecord(Base):
    __tablename__ = "learned_memory_proposals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    feedback_id: Mapped[str] = mapped_column(ForeignKey("feedback_events.id"), nullable=False)
    proposed_by_agent_id: Mapped[str] = mapped_column(String(120), nullable=False)
    memory_type: Mapped[str] = mapped_column(String(40), nullable=False)
    memory_zone: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    visibility: Mapped[str] = mapped_column(String(40), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    sensitivity: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.7)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_agent_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approved_memory_id: Mapped[str | None] = mapped_column(
        ForeignKey("memories.id"), nullable=True
    )

    feedback: Mapped[FeedbackEventRecord] = relationship(back_populates="proposals")


class MemoryVersionRecord(Base):
    __tablename__ = "memory_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    memory_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    previous_memory_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event: Mapped[str] = mapped_column(String(80), nullable=False)
    actor_agent_id: Mapped[str] = mapped_column(String(120), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEventRecord(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CaptureEventRecord(Base):
    __tablename__ = "capture_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    content_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    capture_source: Mapped[str] = mapped_column(String(80), nullable=False)
    raw_preview: Mapped[str] = mapped_column(Text, default="")
    redacted_preview: Mapped[str] = mapped_column(Text, default="")
    suggested_zone: Mapped[str] = mapped_column(String(80), nullable=False)
    suggested_memory_type: Mapped[str] = mapped_column(String(40), nullable=False)
    sensitivity: Mapped[str] = mapped_column(String(40), nullable=False)
    risk_warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    asset_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    committed_memory_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MemoryInboxItemRecord(Base):
    __tablename__ = "memory_inbox_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    content_kind: Mapped[str] = mapped_column(String(40), nullable=False, default="text")
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="api", index=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    asset_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    raw_preview: Mapped[str] = mapped_column(Text, default="")
    redacted_preview: Mapped[str] = mapped_column(Text, default="")
    suggested_zone: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    suggested_memory_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    sensitivity: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    risk_warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    rule_suggestion: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    model_suggestion: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    proposal_kind: Mapped[str] = mapped_column(String(40), default="new", index=True)
    duplicate_memory_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    conflict_memory_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    supersedes_memory_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    semantic_summary: Mapped[str] = mapped_column(Text, default="")
    semantic_entities: Mapped[list[str]] = mapped_column(JSON, default=list)
    semantic_triggers: Mapped[list[str]] = mapped_column(JSON, default=list)
    semantic_facts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    candidate_memory_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    llm_relationship: Mapped[str | None] = mapped_column(String(40), nullable=True)
    llm_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    llm_reason: Mapped[str] = mapped_column(Text, default="")
    needs_user_decision: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(40), default="pending_review", index=True)
    approved_memory_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    merged_into_memory_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_agent_id: Mapped[str | None] = mapped_column(String(120), nullable=True)


class MemoryFactRecord(Base):
    __tablename__ = "memory_facts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    subject: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    predicate: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    object: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    fact_type: Mapped[str] = mapped_column(String(80), nullable=False, default="requirement")
    summary: Mapped[str] = mapped_column(Text, default="")
    memory_zone: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    visibility: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    sensitivity: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_memory_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.7)
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MemoryDecisionExampleRecord(Base):
    __tablename__ = "memory_decision_examples"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    zone: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    new_memory_summary: Mapped[str] = mapped_column(Text, default="")
    candidate_memory_summary: Mapped[str] = mapped_column(Text, default="")
    llm_relationship: Mapped[str] = mapped_column(String(40), default="uncertain")
    llm_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    user_decision: Mapped[str] = mapped_column(String(80), nullable=False)
    superseded_memory_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    final_memory_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AccessGrantRecord(Base):
    __tablename__ = "access_grants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    agent_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    allowed_zones: Mapped[list[str]] = mapped_column(JSON, default=list)
    context_request: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    confirmation_level: Mapped[str] = mapped_column(String(40), default="normal")
    token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    token_revealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_agent_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SharePackRecord(Base):
    __tablename__ = "share_packs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    recipient_label: Mapped[str] = mapped_column(String(200), default="")
    created_by_agent_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    allowed_zones: Mapped[list[str]] = mapped_column(JSON, default=list)
    allowed_memory_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    allowed_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    excluded_memory_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_uses: Mapped[int] = mapped_column(default=20)
    use_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ModelProfileRecord(Base):
    __tablename__ = "model_profiles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    model: Mapped[str] = mapped_column(String(160), default="")
    endpoint_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    api_key_env: Mapped[str | None] = mapped_column(String(120), nullable=True)
    api_key_secret: Mapped[str | None] = mapped_column(String(500), nullable=True)
    allowed_tasks: Mapped[list[str]] = mapped_column(JSON, default=list)
    allowed_zones: Mapped[list[str]] = mapped_column(JSON, default=list)
    local_only: Mapped[bool] = mapped_column(default=False)
    auto_apply_low_sensitivity: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def run_dev_migrations() -> None:
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    if "memories" not in table_names:
        return
    memory_additions = {
        "memory_zone": "VARCHAR(80)",
        "content_kind": "VARCHAR(40) DEFAULT 'text'",
        "capture_source": "VARCHAR(80)",
        "source_url": "VARCHAR(500)",
        "source_title": "VARCHAR(500)",
        "asset_path": "VARCHAR(1000)",
        "redacted": "BOOLEAN DEFAULT 0",
        "superseded_by_id": "VARCHAR(64)",
        "semantic_summary": "TEXT DEFAULT ''",
        "semantic_entities": "JSON DEFAULT '[]'",
        "semantic_triggers": "JSON DEFAULT '[]'",
        "semantic_facts": "JSON DEFAULT '[]'",
        "summary_embedding": "JSON DEFAULT '[]'",
        "summary_model_profile_id": "VARCHAR(64)",
        "summary_confidence": "FLOAT DEFAULT 0",
        "summary_updated_at": "DATETIME",
    }
    with engine.begin() as connection:
        columns = {column["name"] for column in inspector.get_columns("memories")}
        for name, ddl_type in memory_additions.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE memories ADD COLUMN {name} {ddl_type}"))
        if "memory_write_proposals" in table_names:
            columns = {
                column["name"] for column in inspector.get_columns("memory_write_proposals")
            }
            for name, ddl_type in memory_additions.items():
                if name not in columns:
                    connection.execute(
                        text(f"ALTER TABLE memory_write_proposals ADD COLUMN {name} {ddl_type}")
                    )
        if "learned_memory_proposals" in table_names:
            columns = {
                column["name"] for column in inspector.get_columns("learned_memory_proposals")
            }
            if "memory_zone" not in columns:
                connection.execute(
                    text("ALTER TABLE learned_memory_proposals ADD COLUMN memory_zone VARCHAR(80)")
                )
        if "model_profiles" in table_names:
            columns = {
                column["name"] for column in inspector.get_columns("model_profiles")
            }
            if "api_key_secret" not in columns:
                connection.execute(
                    text("ALTER TABLE model_profiles ADD COLUMN api_key_secret VARCHAR(500)")
                )
        if "memory_inbox_items" in table_names:
            columns = {
                column["name"] for column in inspector.get_columns("memory_inbox_items")
            }
            inbox_additions = {
                "proposal_kind": "VARCHAR(40) DEFAULT 'new'",
                "conflict_memory_ids": "JSON DEFAULT '[]'",
                "supersedes_memory_id": "VARCHAR(64)",
                "semantic_summary": "TEXT DEFAULT ''",
                "semantic_entities": "JSON DEFAULT '[]'",
                "semantic_triggers": "JSON DEFAULT '[]'",
                "semantic_facts": "JSON DEFAULT '[]'",
                "candidate_memory_ids": "JSON DEFAULT '[]'",
                "llm_relationship": "VARCHAR(40)",
                "llm_confidence": "FLOAT DEFAULT 0",
                "llm_reason": "TEXT DEFAULT ''",
                "needs_user_decision": "BOOLEAN DEFAULT 0",
            }
            for name, ddl_type in inbox_additions.items():
                if name not in columns:
                    connection.execute(
                        text(f"ALTER TABLE memory_inbox_items ADD COLUMN {name} {ddl_type}")
                    )
        if "access_grants" in table_names:
            columns = {
                column["name"] for column in inspector.get_columns("access_grants")
            }
            if "project_id" not in columns:
                connection.execute(
                    text("ALTER TABLE access_grants ADD COLUMN project_id VARCHAR(120)")
                )
            if "context_request" not in columns:
                connection.execute(
                    text("ALTER TABLE access_grants ADD COLUMN context_request JSON DEFAULT '{}'")
                )
        if "memory_versions" in table_names:
            columns = {
                column["name"] for column in inspector.get_columns("memory_versions")
            }
            if "details" not in columns:
                connection.execute(
                    text("ALTER TABLE memory_versions ADD COLUMN details JSON DEFAULT '{}'")
                )
        if "share_packs" not in table_names:
            connection.execute(
                text(
                    """
                    CREATE TABLE share_packs (
                        id VARCHAR(64) NOT NULL PRIMARY KEY,
                        tenant_id VARCHAR(120) NOT NULL,
                        project_id VARCHAR(120) NOT NULL,
                        name VARCHAR(200) NOT NULL,
                        description TEXT DEFAULT '',
                        recipient_label VARCHAR(200) DEFAULT '',
                        created_by_agent_id VARCHAR(120) NOT NULL,
                        allowed_zones JSON DEFAULT '[]',
                        allowed_memory_types JSON DEFAULT '[]',
                        allowed_tags JSON DEFAULT '[]',
                        excluded_memory_ids JSON DEFAULT '[]',
                        token_hash VARCHAR(128) NOT NULL,
                        status VARCHAR(40) DEFAULT 'active',
                        expires_at DATETIME NOT NULL,
                        max_uses INTEGER DEFAULT 20,
                        use_count INTEGER DEFAULT 0,
                        created_at DATETIME,
                        revoked_at DATETIME
                    )
                    """
                )
            )
            connection.execute(text("CREATE INDEX ix_share_packs_tenant_id ON share_packs (tenant_id)"))
            connection.execute(text("CREATE INDEX ix_share_packs_project_id ON share_packs (project_id)"))
            connection.execute(text("CREATE INDEX ix_share_packs_status ON share_packs (status)"))
            connection.execute(text("CREATE INDEX ix_share_packs_token_hash ON share_packs (token_hash)"))


def make_engine(database_url: str | None = None):
    url = database_url or get_settings().database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, future=True)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    run_dev_migrations()


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
