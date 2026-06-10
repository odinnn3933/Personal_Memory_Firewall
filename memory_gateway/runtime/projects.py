from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_gateway.db import ProjectRecord, utcnow
from memory_gateway.schemas import ProjectCreateRequest, ProjectOut
from memory_gateway.security import AgentIdentity
from memory_gateway.service import InvalidState, NotFound, PermissionDenied
from memory_gateway.types import AuditAction

from .audit import audit_event


def project_to_out(record: ProjectRecord) -> ProjectOut:
    return ProjectOut(
        id=record.id,
        name=record.name,
        description=record.description or "",
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def agent_can_access_project(agent: AgentIdentity, project_id: str | None) -> bool:
    if not project_id:
        return True
    return agent.is_admin or "*" in agent.allowed_projects or project_id in agent.allowed_projects


def list_projects(session: Session, agent: AgentIdentity) -> list[ProjectOut]:
    query = select(ProjectRecord).where(
        ProjectRecord.tenant_id == agent.tenant_id,
        ProjectRecord.status == "active",
    )
    records = list(session.scalars(query))
    if not agent.is_admin and "*" not in agent.allowed_projects:
        allowed = set(agent.allowed_projects)
        records = [record for record in records if record.id in allowed]
    records.sort(key=lambda record: record.name.lower())
    return [project_to_out(record) for record in records]


def create_project(
    session: Session,
    agent: AgentIdentity,
    request: ProjectCreateRequest,
) -> ProjectOut:
    if not agent.is_admin:
        raise PermissionDenied("only admin agents can create projects")
    project_id = request.id.strip()
    if not project_id:
        raise InvalidState("project id is required")
    existing = session.get(ProjectRecord, project_id)
    if existing and existing.tenant_id == agent.tenant_id:
        raise InvalidState("project already exists")
    if existing and existing.tenant_id != agent.tenant_id:
        raise NotFound("project id is not available")
    record = ProjectRecord(
        id=project_id,
        tenant_id=agent.tenant_id,
        name=request.name.strip() or project_id,
        description=request.description,
        status="active",
    )
    session.add(record)
    session.flush()
    audit_event(
        session,
        agent,
        AuditAction.PROJECT_CREATE,
        "project",
        record.id,
        {"name": record.name},
    )
    return project_to_out(record)


def ensure_seed_project(
    session: Session,
    *,
    tenant_id: str,
    project_id: str,
    name: str,
    description: str = "",
) -> None:
    existing = session.get(ProjectRecord, project_id)
    if existing:
        return
    session.add(
        ProjectRecord(
            id=project_id,
            tenant_id=tenant_id,
            name=name,
            description=description,
            status="active",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
    )
