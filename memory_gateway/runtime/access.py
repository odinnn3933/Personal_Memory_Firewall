from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from memory_gateway.db import AccessGrantRecord, MemoryRecord
from memory_gateway.policy import can_read_memory, zone_requires_grant
from memory_gateway.security import AgentIdentity
from memory_gateway.service import PermissionDenied
from memory_gateway.types import GrantStatus, MemoryZone, ProposalStatus


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DeniedZone:
    zone: MemoryZone
    reason: str


@dataclass(frozen=True)
class ZoneAccess:
    grant: AccessGrantRecord | None
    allowed_zones: list[MemoryZone]
    denied_zones: list[DeniedZone]


def _grant_is_expired(grant: AccessGrantRecord) -> bool:
    from memory_gateway.service import as_utc_naive, now_for_db_compare

    return as_utc_naive(grant.expires_at) <= now_for_db_compare()


def resolve_zone_access(
    session: Session,
    agent: AgentIdentity,
    zones: list[MemoryZone],
    grant_token: str | None,
    project_id: str | None = None,
    *,
    strict: bool = False,
) -> ZoneAccess:
    public_zones = [zone for zone in zones if not zone_requires_grant(zone)]
    private_zones = [zone for zone in zones if zone_requires_grant(zone)]
    if not private_zones:
        return ZoneAccess(None, list(dict.fromkeys(public_zones)), [])

    denied = [
        DeniedZone(zone, "Grant token is required for this memory zone.")
        for zone in private_zones
    ]
    if not grant_token:
        if strict:
            raise PermissionDenied("grant token is required for requested memory zones")
        return ZoneAccess(None, public_zones, denied)

    grant = session.scalars(
        select(AccessGrantRecord).where(
            AccessGrantRecord.tenant_id == agent.tenant_id,
            AccessGrantRecord.agent_id == agent.agent_id,
            AccessGrantRecord.token_hash == token_hash(grant_token),
        )
    ).first()
    if not grant:
        if strict:
            raise PermissionDenied("invalid grant token")
        return ZoneAccess(None, public_zones, [
            DeniedZone(zone, "The supplied grant token is invalid for this agent.")
            for zone in private_zones
        ])
    if grant.status != GrantStatus.APPROVED.value:
        if strict:
            raise PermissionDenied(f"grant is {grant.status}")
        return ZoneAccess(grant, public_zones, [
            DeniedZone(zone, f"Grant is {grant.status}.")
            for zone in private_zones
        ])
    if grant.project_id != project_id:
        if strict:
            raise PermissionDenied("grant is scoped to a different project")
        return ZoneAccess(grant, public_zones, [
            DeniedZone(zone, "Grant is scoped to a different project.")
            for zone in private_zones
        ])
    if _grant_is_expired(grant):
        grant.status = GrantStatus.EXPIRED.value
        session.flush()
        if strict:
            raise PermissionDenied("grant has expired")
        return ZoneAccess(grant, public_zones, [
            DeniedZone(zone, "Grant has expired.")
            for zone in private_zones
        ])

    grant_zones = {MemoryZone(zone) for zone in grant.allowed_zones}
    allowed_private = [zone for zone in private_zones if zone in grant_zones]
    denied_private = [
        DeniedZone(zone, "Grant does not include this memory zone.")
        for zone in private_zones
        if zone not in grant_zones
    ]
    if strict and denied_private:
        missing = [item.zone.value for item in denied_private]
        raise PermissionDenied(f"grant does not allow zones: {missing}")
    return ZoneAccess(grant, list(dict.fromkeys(public_zones + allowed_private)), denied_private)


def readable_memories_for_zones(
    session: Session,
    agent: AgentIdentity,
    project_id: str | None,
    zones: list[MemoryZone],
    grant_token: str | None,
    memory_types: list | None = None,
    *,
    strict_grant: bool = False,
) -> tuple[AccessGrantRecord | None, list[MemoryRecord], list[DeniedZone]]:
    access = resolve_zone_access(
        session, agent, zones, grant_token, project_id, strict=strict_grant
    )
    if not access.allowed_zones:
        return access.grant, [], access.denied_zones
    query = select(MemoryRecord).where(
        MemoryRecord.tenant_id == agent.tenant_id,
        MemoryRecord.deleted_at.is_(None),
        MemoryRecord.status == ProposalStatus.APPROVED.value,
        MemoryRecord.memory_zone.in_([zone.value for zone in access.allowed_zones]),
    )
    if memory_types:
        query = query.where(MemoryRecord.memory_type.in_([item.value for item in memory_types]))
    records = list(session.scalars(query))
    allowed = []
    grant_zones = set(access.allowed_zones) if access.grant else set()
    for record in records:
        if record.memory_zone != MemoryZone.PUBLIC_PROFILE.value and record.project_id != project_id:
            continue
        if can_read_memory(agent, record, project_id):
            allowed.append(record)
            continue
        if (
            access.grant
            and record.visibility == "private"
            and record.memory_zone
            and MemoryZone(record.memory_zone) in grant_zones
            and record.project_id == project_id
        ):
            allowed.append(record)
    return access.grant, allowed, access.denied_zones
