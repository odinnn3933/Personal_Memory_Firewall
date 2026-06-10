from __future__ import annotations

from memory_gateway.schemas import SearchRequest
from memory_gateway.security import authenticate_api_key
from memory_gateway.service import benchmark_forbidden_leak_rate, search_memories
from memory_gateway.types import MemoryType


def test_acl_filter_happens_before_ranking(session):
    guest = authenticate_api_key("guest-demo-key")
    backend = authenticate_api_key("backend-demo-key")
    assert guest and backend

    request = SearchRequest(
        query="Postgres pgvector database vector retrieval",
        project_id="memory-gateway",
        memory_types=[MemoryType.PREFERENCE],
        top_k=5,
    )
    guest_result = search_memories(session, guest, request)
    backend_result = search_memories(session, backend, request)

    assert guest_result.candidate_count_after_acl == 0
    assert backend_result.candidate_count_after_acl == 1
    assert backend_result.memories[0].id == "mem_project_database"


def test_forbidden_leak_rate_zero(session):
    guest = authenticate_api_key("guest-demo-key")
    backend = authenticate_api_key("backend-demo-key")
    assert guest and backend
    result = benchmark_forbidden_leak_rate(session, guest, backend)
    assert result["forbidden_leak_rate"] == 0
    assert result["leaks"] == []

