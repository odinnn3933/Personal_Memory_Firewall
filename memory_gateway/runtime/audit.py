from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from memory_gateway.db import AuditEventRecord
from memory_gateway.security import AgentIdentity
from memory_gateway.types import AuditAction


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def audit_event(
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
            action=action.value,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
        )
    )
    session.flush()
    return audit_id
