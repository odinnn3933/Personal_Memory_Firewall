from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .config import get_settings
from .types import AgentRole


@dataclass(frozen=True)
class AgentIdentity:
    agent_id: str
    tenant_id: str
    roles: tuple[AgentRole, ...]
    allowed_projects: tuple[str, ...]

    @property
    def is_admin(self) -> bool:
        return AgentRole.ADMIN in self.roles

    @property
    def can_write(self) -> bool:
        return self.is_admin or AgentRole.WRITER in self.roles


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def demo_identities() -> dict[str, AgentIdentity]:
    settings = get_settings()
    return {
        settings.admin_key: AgentIdentity(
            agent_id="admin_agent",
            tenant_id="demo",
            roles=(AgentRole.ADMIN, AgentRole.WRITER, AgentRole.READER),
            allowed_projects=("memory-gateway",),
        ),
        settings.backend_key: AgentIdentity(
            agent_id="backend_agent",
            tenant_id="demo",
            roles=(AgentRole.WRITER, AgentRole.READER),
            allowed_projects=("*",),
        ),
        settings.guest_key: AgentIdentity(
            agent_id="guest_agent",
            tenant_id="demo",
            roles=(AgentRole.READER,),
            allowed_projects=(),
        ),
    }


def authenticate_api_key(api_key: str | None) -> AgentIdentity | None:
    if not api_key:
        return None
    return demo_identities().get(api_key)
