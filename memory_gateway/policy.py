from __future__ import annotations

from .db import MemoryRecord
from .security import AgentIdentity
from .types import MemoryType, MemoryZone, Sensitivity, Visibility

SENSITIVE_KEYWORDS = {
    "password",
    "password:",
    "token",
    "token=",
    "secret",
    "api key",
    "salary",
    "medical",
    "credential",
    "private key",
    "card number",
    "cvv",
    "ssn",
    "passport",
    "\u5bc6\u7801",
    "\u85aa\u8d44",
    "\u533b\u7597",
    "\u5bc6\u94a5",
    "\u94f6\u884c\u5361",
    "\u8eab\u4efd\u8bc1",
}

MEDIUM_SENSITIVITY_KEYWORDS = {
    "private",
    "internal",
    "confidential",
    "\u9690\u79c1",
}

ZONE_METADATA = {
    MemoryZone.PUBLIC_PROFILE: {
        "label": "Public Profile",
        "description": "Low-risk preferences agents may use without a grant.",
        "default_sensitivity": Sensitivity.LOW,
        "requires_grant": False,
        "default_ttl_minutes": 60,
        "confirmation_level": "low",
    },
    MemoryZone.WORK_CONTEXT: {
        "label": "Work Context",
        "description": "Project requirements, team decisions, and work-specific context.",
        "default_sensitivity": Sensitivity.MEDIUM,
        "requires_grant": True,
        "default_ttl_minutes": 15,
        "confirmation_level": "normal",
    },
    MemoryZone.PERSONAL_CONTEXT: {
        "label": "Personal Context",
        "description": "Personal preferences such as travel, schedule, and lifestyle context.",
        "default_sensitivity": Sensitivity.MEDIUM,
        "requires_grant": True,
        "default_ttl_minutes": 15,
        "confirmation_level": "normal",
    },
    MemoryZone.SENSITIVE_VAULT: {
        "label": "Sensitive Vault",
        "description": "High-risk references and red-line rules, never raw secrets.",
        "default_sensitivity": Sensitivity.HIGH,
        "requires_grant": True,
        "default_ttl_minutes": 5,
        "confirmation_level": "high",
    },
    MemoryZone.PAYMENT_REFERENCE: {
        "label": "Payment Reference",
        "description": "Payment-related references requiring explicit confirmation.",
        "default_sensitivity": Sensitivity.HIGH,
        "requires_grant": True,
        "default_ttl_minutes": 5,
        "confirmation_level": "high",
    },
}


def classify_sensitivity(content: str) -> Sensitivity:
    lowered = content.lower()
    if any(keyword in lowered for keyword in SENSITIVE_KEYWORDS):
        return Sensitivity.HIGH
    if any(keyword in lowered for keyword in MEDIUM_SENSITIVITY_KEYWORDS):
        return Sensitivity.MEDIUM
    return Sensitivity.LOW


def zone_requires_grant(zone: MemoryZone | None) -> bool:
    if zone is None:
        return False
    return bool(ZONE_METADATA[zone]["requires_grant"])


def zone_default_ttl_minutes(zone: MemoryZone) -> int:
    return int(ZONE_METADATA[zone]["default_ttl_minutes"])


def zone_default_sensitivity(zone: MemoryZone) -> Sensitivity:
    return ZONE_METADATA[zone]["default_sensitivity"]


def max_sensitivity(*values: Sensitivity) -> Sensitivity:
    order = {
        Sensitivity.LOW: 0,
        Sensitivity.MEDIUM: 1,
        Sensitivity.HIGH: 2,
    }
    return max(values, key=lambda value: order[value])


def zone_confirmation_level(zones: list[MemoryZone]) -> str:
    levels = [str(ZONE_METADATA[zone]["confirmation_level"]) for zone in zones]
    if "high" in levels:
        return "high"
    if "normal" in levels:
        return "normal"
    return "low"


def requires_approval(
    memory_type: MemoryType,
    visibility: Visibility,
    sensitivity: Sensitivity,
) -> bool:
    return (
        memory_type in {MemoryType.LESSON, MemoryType.ANTI_PATTERN}
        or visibility == Visibility.PRIVATE
        or sensitivity != Sensitivity.LOW
    )


def can_read_memory(agent: AgentIdentity, memory: MemoryRecord, project_id: str | None) -> bool:
    if memory.deleted_at is not None or memory.status != "approved":
        return False
    if memory.tenant_id != agent.tenant_id:
        return False
    if agent.agent_id in (memory.denied_agent_ids or []):
        return False
    if agent.is_admin:
        return True
    if memory.allowed_agent_ids and agent.agent_id not in memory.allowed_agent_ids:
        return False
    if memory.visibility == Visibility.PUBLIC:
        return True
    if memory.visibility == Visibility.PROJECT:
        return (
            memory.project_id == project_id
            and project_id is not None
            and ("*" in agent.allowed_projects or project_id in agent.allowed_projects)
        )
    if memory.visibility == Visibility.PRIVATE:
        return agent.agent_id in (memory.allowed_agent_ids or [])
    return False


def policy_reason(agent: AgentIdentity, memory: MemoryRecord, project_id: str | None) -> str:
    if agent.agent_id in (memory.denied_agent_ids or []):
        return "denied_agent_ids overrides all allow rules"
    if agent.is_admin:
        return "admin role can read approved, non-deleted memories in the tenant"
    if memory.visibility == Visibility.PUBLIC:
        return "public memory is readable by tenant readers"
    if memory.visibility == Visibility.PROJECT:
        return f"agent has access to project {project_id!r}"
    if memory.visibility == Visibility.PRIVATE:
        return "agent is explicitly listed in allowed_agent_ids"
    return "no matching allow rule"
