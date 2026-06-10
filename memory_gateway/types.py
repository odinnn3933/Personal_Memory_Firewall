from enum import StrEnum


class AgentRole(StrEnum):
    ADMIN = "admin"
    WRITER = "writer"
    READER = "reader"


class MemoryType(StrEnum):
    CONTEXT = "context"
    PREFERENCE = "preference"
    RELATIONSHIP = "relationship"
    PROCEDURE = "procedure"
    LESSON = "lesson"
    ANTI_PATTERN = "anti_pattern"


class MemoryZone(StrEnum):
    PUBLIC_PROFILE = "public_profile"
    WORK_CONTEXT = "work_context"
    PERSONAL_CONTEXT = "personal_context"
    SENSITIVE_VAULT = "sensitive_vault"
    PAYMENT_REFERENCE = "payment_reference"


class ContentKind(StrEnum):
    TEXT = "text"
    IMAGE = "image"


class CaptureSource(StrEnum):
    CLIPBOARD = "clipboard"
    MANUAL = "manual"
    API = "api"
    FILE_TEXT = "file_text"
    AGENT_FEEDBACK = "agent_feedback"


class ModelProvider(StrEnum):
    RULE_ONLY = "rule_only"
    OPENAI_COMPATIBLE = "openai_compatible"
    OLLAMA = "ollama"


class ModelTask(StrEnum):
    CLASSIFY_CAPTURE = "classify_capture"
    SUMMARIZE_MEMORY = "summarize_memory"
    EXTRACT_LESSON = "extract_lesson"
    EXTRACT_FACTS = "extract_facts"
    EMBED_MEMORY = "embed_memory"


class Visibility(StrEnum):
    PUBLIC = "public"
    PROJECT = "project"
    PRIVATE = "private"


class Sensitivity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class GrantStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVOKED = "revoked"
    EXPIRED = "expired"


class SharePackStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class InboxStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    MERGED = "merged"


class InboxProposalKind(StrEnum):
    NEW = "new"
    DUPLICATE = "duplicate"
    UPDATE = "update"
    CONFLICT = "conflict"


class FactStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUPERSEDED = "superseded"


class AuditAction(StrEnum):
    SEARCH = "search"
    WRITE_PROPOSAL = "write_proposal"
    FEEDBACK = "feedback"
    EXTRACT = "extract"
    APPROVE = "approve"
    DELETE = "delete"
    EXPLAIN = "explain"
    CAPTURE_ANALYZE = "capture_analyze"
    CAPTURE_COMMIT = "capture_commit"
    GRANT_REQUEST = "grant_request"
    GRANT_APPROVE = "grant_approve"
    GRANT_REJECT = "grant_reject"
    GRANT_REVOKE = "grant_revoke"
    VAULT_SEARCH = "vault_search"
    MODEL_PROFILE_CREATE = "model_profile_create"
    MODEL_PROFILE_ACTIVATE = "model_profile_activate"
    MODEL_PROCESS = "model_process"
    GRAPH_EXTRACT = "graph_extract"
    GRAPH_SEARCH = "graph_search"
    GRAPH_REBUILD = "graph_rebuild"
    GRAPH_EXPLAIN = "graph_explain"
    INGEST = "ingest"
    INBOX_APPROVE = "inbox_approve"
    INBOX_REJECT = "inbox_reject"
    INBOX_MERGE = "inbox_merge"
    CONTEXT_COMPOSE = "context_compose"
    CONTEXT_REQUEST = "context_request"
    FACT_EXTRACT = "fact_extract"
    PROJECT_CREATE = "project_create"
    MEMORY_SUPERSEDE = "memory_supersede"
    SHARE_PREVIEW = "share_preview"
    SHARE_CREATE = "share_create"
    SHARE_COMPOSE = "share_compose"
    SHARE_REVOKE = "share_revoke"
