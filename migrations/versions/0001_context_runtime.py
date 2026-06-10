from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_context_runtime"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=120), primary_key=True),
        sa.Column("tenant_id", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_projects_tenant_id", "projects", ["tenant_id"])
    op.create_index("ix_projects_status", "projects", ["status"])

    op.add_column("memories", sa.Column("superseded_by_id", sa.String(length=64), nullable=True))
    op.add_column("memories", sa.Column("semantic_summary", sa.Text(), nullable=False, server_default=""))
    op.add_column("memories", sa.Column("semantic_entities", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("memories", sa.Column("semantic_triggers", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("memories", sa.Column("semantic_facts", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("memories", sa.Column("summary_embedding", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("memories", sa.Column("summary_model_profile_id", sa.String(length=64), nullable=True))
    op.add_column("memories", sa.Column("summary_confidence", sa.Float(), nullable=False, server_default="0"))
    op.add_column("memories", sa.Column("summary_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("access_grants", sa.Column("project_id", sa.String(length=120), nullable=True))
    op.add_column("access_grants", sa.Column("context_request", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("memory_versions", sa.Column("details", sa.JSON(), nullable=False, server_default="{}"))
    op.create_index("ix_access_grants_project_id", "access_grants", ["project_id"])

    op.create_table(
        "memory_inbox_items",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=120), nullable=False),
        sa.Column("agent_id", sa.String(length=120), nullable=False),
        sa.Column("project_id", sa.String(length=120), nullable=True),
        sa.Column("content_kind", sa.String(length=40), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("source_title", sa.String(length=500), nullable=True),
        sa.Column("asset_path", sa.String(length=1000), nullable=True),
        sa.Column("raw_preview", sa.Text(), nullable=False, server_default=""),
        sa.Column("redacted_preview", sa.Text(), nullable=False, server_default=""),
        sa.Column("suggested_zone", sa.String(length=80), nullable=False),
        sa.Column("suggested_memory_type", sa.String(length=40), nullable=False),
        sa.Column("sensitivity", sa.String(length=40), nullable=False),
        sa.Column("risk_warnings", sa.JSON(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("rule_suggestion", sa.JSON(), nullable=False),
        sa.Column("model_suggestion", sa.JSON(), nullable=True),
        sa.Column("proposal_kind", sa.String(length=40), nullable=False, server_default="new"),
        sa.Column("duplicate_memory_ids", sa.JSON(), nullable=False),
        sa.Column("conflict_memory_ids", sa.JSON(), nullable=False),
        sa.Column("supersedes_memory_id", sa.String(length=64), nullable=True),
        sa.Column("semantic_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("semantic_entities", sa.JSON(), nullable=False),
        sa.Column("semantic_triggers", sa.JSON(), nullable=False),
        sa.Column("semantic_facts", sa.JSON(), nullable=False),
        sa.Column("candidate_memory_ids", sa.JSON(), nullable=False),
        sa.Column("llm_relationship", sa.String(length=40), nullable=True),
        sa.Column("llm_confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("llm_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("needs_user_decision", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("approved_memory_id", sa.String(length=64), nullable=True),
        sa.Column("merged_into_memory_id", sa.String(length=64), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_agent_id", sa.String(length=120), nullable=True),
    )
    op.create_index("ix_memory_inbox_items_tenant_id", "memory_inbox_items", ["tenant_id"])
    op.create_index("ix_memory_inbox_items_status", "memory_inbox_items", ["status"])
    op.create_index("ix_memory_inbox_items_proposal_kind", "memory_inbox_items", ["proposal_kind"])

    op.create_table(
        "memory_facts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=120), nullable=False),
        sa.Column("project_id", sa.String(length=120), nullable=True),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("predicate", sa.String(length=80), nullable=False),
        sa.Column("object", sa.String(length=500), nullable=False),
        sa.Column("fact_type", sa.String(length=80), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("memory_zone", sa.String(length=80), nullable=True),
        sa.Column("visibility", sa.String(length=40), nullable=False),
        sa.Column("sensitivity", sa.String(length=40), nullable=False),
        sa.Column("source_memory_ids", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_memory_facts_tenant_id", "memory_facts", ["tenant_id"])
    op.create_index("ix_memory_facts_status", "memory_facts", ["status"])

    op.create_table(
        "memory_decision_examples",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=120), nullable=False),
        sa.Column("project_id", sa.String(length=120), nullable=True),
        sa.Column("zone", sa.String(length=80), nullable=True),
        sa.Column("new_memory_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("candidate_memory_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("llm_relationship", sa.String(length=40), nullable=False, server_default="uncertain"),
        sa.Column("llm_confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("user_decision", sa.String(length=80), nullable=False),
        sa.Column("superseded_memory_id", sa.String(length=64), nullable=True),
        sa.Column("final_memory_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_memory_decision_examples_tenant_id", "memory_decision_examples", ["tenant_id"])
    op.create_index("ix_memory_decision_examples_project_id", "memory_decision_examples", ["project_id"])
    op.create_index("ix_memory_decision_examples_zone", "memory_decision_examples", ["zone"])

    op.create_table(
        "share_packs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=120), nullable=False),
        sa.Column("project_id", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("recipient_label", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("created_by_agent_id", sa.String(length=120), nullable=False),
        sa.Column("allowed_zones", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("allowed_memory_types", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("allowed_tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("excluded_memory_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_share_packs_tenant_id", "share_packs", ["tenant_id"])
    op.create_index("ix_share_packs_project_id", "share_packs", ["project_id"])
    op.create_index("ix_share_packs_status", "share_packs", ["status"])
    op.create_index("ix_share_packs_token_hash", "share_packs", ["token_hash"])


def downgrade() -> None:
    op.drop_index("ix_share_packs_token_hash", table_name="share_packs")
    op.drop_index("ix_share_packs_status", table_name="share_packs")
    op.drop_index("ix_share_packs_project_id", table_name="share_packs")
    op.drop_index("ix_share_packs_tenant_id", table_name="share_packs")
    op.drop_table("share_packs")
    op.drop_table("memory_decision_examples")
    op.drop_table("memory_facts")
    op.drop_table("memory_inbox_items")
    op.drop_index("ix_access_grants_project_id", table_name="access_grants")
    op.drop_column("memory_versions", "details")
    op.drop_column("access_grants", "context_request")
    op.drop_column("access_grants", "project_id")
    op.drop_column("memories", "summary_updated_at")
    op.drop_column("memories", "summary_confidence")
    op.drop_column("memories", "summary_model_profile_id")
    op.drop_column("memories", "summary_embedding")
    op.drop_column("memories", "semantic_facts")
    op.drop_column("memories", "semantic_triggers")
    op.drop_column("memories", "semantic_entities")
    op.drop_column("memories", "semantic_summary")
    op.drop_column("memories", "superseded_by_id")
    op.drop_table("projects")
