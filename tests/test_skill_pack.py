from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "integrations" / "skills" / "personal-memory-firewall" / "SKILL.md"
CONTRACT = SKILL.parent / "references" / "tool-contract.md"
MCP = ROOT / "memory_gateway" / "mcp" / "server.py"


def test_skill_frontmatter_and_contract_exist():
    content = SKILL.read_text(encoding="utf-8")
    assert content.startswith("---\n")
    assert "name: personal-memory-firewall" in content
    assert "description:" in content
    assert CONTRACT.exists()


def test_skill_does_not_instruct_direct_database_access():
    content = SKILL.read_text(encoding="utf-8").lower()
    assert "do not access the database" in content
    assert "memory_vault_search" in content
    assert "memory_request_grant" in content


def test_tool_contract_matches_mcp_tool_names():
    contract = CONTRACT.read_text(encoding="utf-8")
    mcp = MCP.read_text(encoding="utf-8")
    required_tools = [
        "memory_list_zones",
        "memory_list_projects",
        "memory_ingest",
        "memory_list_inbox",
        "memory_approve_inbox",
        "memory_compose_context",
        "memory_request_context",
        "memory_get_context_request",
        "memory_compose_approved_context",
        "memory_context_feedback",
        "memory_request_grant",
        "memory_get_grant",
        "memory_vault_search",
        "memory_graph_health",
        "memory_graph_search",
        "memory_list_model_profiles",
        "memory_classify_with_model",
        "memory_extraction_preview",
        "memory_semantic_summarize",
        "memory_semantic_judge",
        "memory_rebuild_summaries",
        "memory_list_decision_examples",
        "memory_list_memories",
        "memory_get_memory",
    ]
    for tool in required_tools:
        assert tool in contract
        assert f"def {tool}" in mcp
