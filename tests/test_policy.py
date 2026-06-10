from __future__ import annotations

from memory_gateway.db import MemoryRecord
from memory_gateway.policy import can_read_memory, classify_sensitivity, requires_approval
from memory_gateway.security import authenticate_api_key
from memory_gateway.types import MemoryType, Sensitivity, Visibility


def test_permission_matrix(session):
    backend = authenticate_api_key("backend-demo-key")
    guest = authenticate_api_key("guest-demo-key")
    admin = authenticate_api_key("admin-demo-key")
    assert backend and guest and admin

    project_memory = session.get(MemoryRecord, "mem_project_database")
    private_memory = session.get(MemoryRecord, "mem_private_salary")
    public_memory = session.get(MemoryRecord, "mem_public_intro")

    assert can_read_memory(backend, public_memory, "memory-gateway")
    assert can_read_memory(guest, public_memory, "memory-gateway")
    assert can_read_memory(backend, project_memory, "memory-gateway")
    assert not can_read_memory(guest, project_memory, "memory-gateway")
    assert not can_read_memory(backend, private_memory, "memory-gateway")
    assert can_read_memory(admin, private_memory, "memory-gateway")


def test_denied_agent_overrides_adminless_allow(session):
    backend = authenticate_api_key("backend-demo-key")
    assert backend
    memory = session.get(MemoryRecord, "mem_project_database")
    memory.denied_agent_ids = ["backend_agent"]
    assert not can_read_memory(backend, memory, "memory-gateway")


def test_sensitivity_and_approval_rules():
    assert classify_sensitivity("contains API token secret").value == "high"
    assert requires_approval(MemoryType.LESSON, Visibility.PROJECT, Sensitivity.LOW)
    assert requires_approval(MemoryType.CONTEXT, Visibility.PRIVATE, Sensitivity.LOW)
    assert not requires_approval(MemoryType.CONTEXT, Visibility.PROJECT, Sensitivity.LOW)

