from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .types import (
    CaptureSource,
    ContentKind,
    FactStatus,
    GrantStatus,
    InboxProposalKind,
    InboxStatus,
    MemoryType,
    MemoryZone,
    ModelProvider,
    ModelTask,
    ProposalStatus,
    Sensitivity,
    SharePackStatus,
    Visibility,
)


class ProjectCreateRequest(BaseModel):
    id: str
    name: str
    description: str = ""


class ProjectOut(BaseModel):
    id: str
    name: str
    description: str
    status: str
    created_at: datetime
    updated_at: datetime


class MemoryOut(BaseModel):
    id: str
    project_id: str | None
    visibility: Visibility
    memory_type: MemoryType
    memory_zone: MemoryZone | None = None
    content_kind: ContentKind = ContentKind.TEXT
    content: str
    tags: list[str]
    sensitivity: Sensitivity
    source: str
    source_url: str | None = None
    source_title: str | None = None
    asset_path: str | None = None
    redacted: bool = False
    status: str = "approved"
    superseded_by_id: str | None = None
    semantic_summary: str = ""
    semantic_entities: list[str] = Field(default_factory=list)
    semantic_triggers: list[str] = Field(default_factory=list)
    semantic_facts: list[dict[str, Any]] = Field(default_factory=list)
    summary_confidence: float = 0.0
    score: float | None = None
    created_at: datetime


class DisplayOut(BaseModel):
    title: str
    subtitle: str = ""
    badges: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    primary_action: str | None = None
    safe_preview: str | None = None


class MemoryCardOut(BaseModel):
    id: str
    title: str
    subtitle: str
    zone: MemoryZone | None = None
    memory_type: MemoryType
    sensitivity: Sensitivity
    source: str
    why_visible: str
    preview: str
    score: float | None = None


class SearchDisplayOut(BaseModel):
    summary: str
    cards: list[MemoryCardOut] = Field(default_factory=list)


class GraphCardOut(BaseModel):
    id: str
    title: str
    subtitle: str
    entity_type: str
    relation_type: str
    zone: MemoryZone | None = None
    sensitivity: Sensitivity
    source_count: int
    source_memory_ids: list[str]
    why_visible: str
    risk_note: str = ""


class SearchRequest(BaseModel):
    query: str
    project_id: str | None = None
    memory_types: list[MemoryType] | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class SearchResponse(BaseModel):
    memories: list[MemoryOut]
    candidate_count_after_acl: int
    audit_id: str
    display: SearchDisplayOut | None = None


class ZoneOut(BaseModel):
    zone: MemoryZone
    label: str
    description: str
    default_sensitivity: Sensitivity
    requires_grant: bool
    default_ttl_minutes: int
    confirmation_level: str


class CaptureAnalyzeRequest(BaseModel):
    content: str = ""
    content_kind: ContentKind = ContentKind.TEXT
    capture_source: CaptureSource = CaptureSource.CLIPBOARD
    project_id: str | None = None
    source_url: str | None = None
    source_title: str | None = None
    asset_path: str | None = None
    model_profile_id: str | None = None


class CaptureAnalyzeResponse(BaseModel):
    rule_suggestion: dict[str, Any] | None = None
    model_suggestion: dict[str, Any] | None = None
    final_suggestion_source: str = "rule"
    sent_to_model: bool = False
    used_redacted_preview: bool = False
    suggested_zone: MemoryZone
    suggested_memory_type: MemoryType
    sensitivity: Sensitivity
    redacted_preview: str
    risk_warnings: list[str]
    tags: list[str]
    should_require_confirmation: bool
    display: DisplayOut | None = None


class CaptureCommitRequest(BaseModel):
    content: str
    content_kind: ContentKind = ContentKind.TEXT
    capture_source: CaptureSource = CaptureSource.CLIPBOARD
    memory_zone: MemoryZone
    memory_type: MemoryType
    project_id: str | None = None
    source_url: str | None = None
    source_title: str | None = None
    asset_path: str | None = None
    tags: list[str] = Field(default_factory=list)
    approve_now: bool = True


class CaptureCommitResponse(BaseModel):
    capture_id: str
    memory: MemoryOut | None = None
    proposal: ProposalOut | None = None
    audit_id: str


class IngestRequest(BaseModel):
    content: str
    content_kind: ContentKind = ContentKind.TEXT
    source: CaptureSource = CaptureSource.API
    project_id: str | None = None
    source_url: str | None = None
    source_title: str | None = None
    asset_path: str | None = None
    model_profile_id: str | None = None
    auto_approve_public_low: bool = True


class InboxItemOut(BaseModel):
    id: str
    status: InboxStatus
    project_id: str | None = None
    content_kind: ContentKind
    source: CaptureSource
    source_url: str | None = None
    source_title: str | None = None
    asset_path: str | None = None
    redacted_preview: str
    suggested_zone: MemoryZone
    suggested_memory_type: MemoryType
    sensitivity: Sensitivity
    risk_warnings: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    proposal_kind: InboxProposalKind = InboxProposalKind.NEW
    duplicate_memory_ids: list[str] = Field(default_factory=list)
    conflict_memory_ids: list[str] = Field(default_factory=list)
    supersedes_memory_id: str | None = None
    human_reason: str = ""
    diff_summary: str = ""
    semantic_summary: str = ""
    semantic_entities: list[str] = Field(default_factory=list)
    semantic_triggers: list[str] = Field(default_factory=list)
    candidate_memory_ids: list[str] = Field(default_factory=list)
    llm_relationship: str | None = None
    llm_confidence: float = 0.0
    llm_reason: str = ""
    needs_user_decision: bool = False
    approved_memory_id: str | None = None
    merged_into_memory_id: str | None = None
    created_at: datetime
    reviewed_at: datetime | None = None
    display: DisplayOut | None = None


class IngestResponse(BaseModel):
    auto_approved: bool
    memory: MemoryOut | None = None
    inbox_item: InboxItemOut | None = None
    audit_id: str
    display: DisplayOut | None = None


class ExtractedFactOut(BaseModel):
    subject: str
    predicate: str
    object: str
    fact_type: str
    project_id: str | None = None
    zone: MemoryZone | None = None
    confidence: float
    valid_from: datetime | None = None
    valid_to: datetime | None = None


class MemoryRelationshipSuggestionOut(BaseModel):
    proposal_kind: InboxProposalKind
    duplicate_memory_ids: list[str] = Field(default_factory=list)
    conflict_memory_ids: list[str] = Field(default_factory=list)
    supersedes_memory_id: str | None = None
    human_reason: str = ""
    diff_summary: str = ""


class SemanticFactOut(BaseModel):
    subject: str
    predicate: str
    object: str


class SemanticSummaryOut(BaseModel):
    summary: str
    entities: list[str] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)
    facts: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = 0.0
    sent_to_model: bool = False
    used_redacted_preview: bool = True
    model_profile_id: str | None = None
    fallback_used: bool = False
    risk_warnings: list[str] = Field(default_factory=list)


class SemanticCandidateOut(BaseModel):
    memory_id: str
    summary: str
    content_preview: str
    zone: MemoryZone | None = None
    memory_type: MemoryType
    sensitivity: Sensitivity
    score: float
    reason: str


class SemanticRelationshipOut(BaseModel):
    relationship: str = "uncertain"
    confidence: float = 0.0
    candidate_memory_id: str | None = None
    reason: str = ""
    recommended_action: str = "ask_user"
    sent_to_model: bool = False
    fallback_used: bool = False


class ExtractionPreviewRequest(BaseModel):
    content: str
    content_kind: ContentKind = ContentKind.TEXT
    project_id: str | None = None
    memory_zone: MemoryZone | None = None
    memory_type: MemoryType | None = None
    model_profile_id: str | None = None


class ExtractionPreviewResponse(BaseModel):
    redacted_preview: str
    suggested_zone: MemoryZone
    suggested_memory_type: MemoryType
    sensitivity: Sensitivity
    facts: list[ExtractedFactOut] = Field(default_factory=list)
    relationship: MemoryRelationshipSuggestionOut
    semantic: SemanticSummaryOut | None = None
    candidate_matches: list[SemanticCandidateOut] = Field(default_factory=list)
    llm_relationship: SemanticRelationshipOut | None = None
    needs_user_decision: bool = False
    display: DisplayOut


class InboxApproveRequest(BaseModel):
    memory_zone: MemoryZone | None = None
    memory_type: MemoryType | None = None
    project_id: str | None = None
    tags: list[str] | None = None
    supersede_memory_id: str | None = None
    note: str = ""


class InboxRejectRequest(BaseModel):
    reason: str = ""


class InboxMergeRequest(BaseModel):
    target_memory_id: str
    note: str = ""


class SemanticSummarizeRequest(BaseModel):
    content: str
    project_id: str | None = None
    memory_zone: MemoryZone = MemoryZone.PUBLIC_PROFILE
    model_profile_id: str | None = None


class SemanticJudgeRequest(BaseModel):
    content: str
    project_id: str | None = None
    memory_zone: MemoryZone = MemoryZone.PUBLIC_PROFILE
    model_profile_id: str | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class SemanticJudgeResponse(BaseModel):
    semantic: SemanticSummaryOut
    candidates: list[SemanticCandidateOut] = Field(default_factory=list)
    judgment: SemanticRelationshipOut


class SummaryRebuildResponse(BaseModel):
    rebuilt_count: int
    failed_count: int = 0
    audit_id: str


class DecisionExampleOut(BaseModel):
    id: str
    project_id: str | None = None
    zone: MemoryZone | None = None
    new_memory_summary: str
    candidate_memory_summary: str
    llm_relationship: str
    llm_confidence: float
    user_decision: str
    superseded_memory_id: str | None = None
    final_memory_id: str | None = None
    created_at: datetime


class MemoryProposalRequest(BaseModel):
    content: str
    project_id: str | None = None
    memory_type: MemoryType = MemoryType.CONTEXT
    memory_zone: MemoryZone | None = None
    visibility: Visibility = Visibility.PROJECT
    tags: list[str] = Field(default_factory=list)


class ProposalOut(BaseModel):
    id: str
    status: ProposalStatus
    memory_type: MemoryType
    visibility: Visibility
    sensitivity: Sensitivity
    content: str
    project_id: str | None
    approved_memory_id: str | None = None
    confidence: float | None = None


class InteractionRequest(BaseModel):
    task_id: str
    task_input: str
    agent_output: str = ""
    tool_summary: str = ""
    result: str = "unknown"
    project_id: str | None = None


class FeedbackRequest(BaseModel):
    task_id: str
    rating: int = Field(ge=1, le=5)
    correction: str
    expected_behavior: str = ""
    error_type: str = "unknown"
    project_id: str | None = None


class FeedbackOut(BaseModel):
    id: str
    task_id: str
    rating: int
    correction: str
    expected_behavior: str
    error_type: str
    project_id: str | None


class ExtractLessonsRequest(BaseModel):
    feedback_id: str


class ExplainResponse(BaseModel):
    memory_id: str
    allowed: bool
    reason: str
    details: dict[str, Any]
    audit_id: str


class GrantRequest(BaseModel):
    task_id: str
    purpose: str
    allowed_zones: list[MemoryZone]
    project_id: str | None = None
    ttl_minutes: int | None = Field(default=None, ge=1, le=60)


class GrantOut(BaseModel):
    id: str
    agent_id: str
    task_id: str
    project_id: str | None = None
    purpose: str
    allowed_zones: list[MemoryZone]
    status: GrantStatus
    confirmation_level: str
    expires_at: datetime
    created_at: datetime
    token: str | None = None


class GrantApprovalRequest(BaseModel):
    ttl_minutes: int | None = Field(default=None, ge=1, le=60)


class VaultSearchRequest(BaseModel):
    query: str
    project_id: str | None = None
    zones: list[MemoryZone]
    grant_token: str | None = None
    memory_types: list[MemoryType] | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class ContextComposeRequest(BaseModel):
    task: str
    project_id: str | None = None
    zones: list[MemoryZone] = Field(default_factory=lambda: [MemoryZone.PUBLIC_PROFILE])
    grant_token: str | None = None
    memory_types: list[MemoryType] | None = None
    max_tokens: int = Field(default=1200, ge=200, le=8000)
    include_graph: bool = True
    top_k: int = Field(default=8, ge=1, le=30)
    retrieval_mode: str = "summary_first"
    use_llm_rerank: bool = True


class ContextSectionOut(BaseModel):
    key: str
    title: str
    content: str
    source_memory_ids: list[str] = Field(default_factory=list)


class DeniedZoneOut(BaseModel):
    zone: MemoryZone
    reason: str


class FactCardOut(BaseModel):
    id: str
    title: str
    subtitle: str
    fact_type: str
    relation_type: str
    zone: MemoryZone | None = None
    sensitivity: Sensitivity
    source_count: int
    source_memory_ids: list[str]
    why_visible: str
    confidence: float


class ContextComposeResponse(BaseModel):
    prompt_context: str
    sections: list[ContextSectionOut]
    source_cards: list[MemoryCardOut]
    matched_summaries: list[SemanticCandidateOut] = Field(default_factory=list)
    fact_cards: list[FactCardOut] = Field(default_factory=list)
    graph_cards: list[GraphCardOut] = Field(default_factory=list)
    denied_zones: list[DeniedZoneOut] = Field(default_factory=list)
    audit_id: str
    token_estimate: int
    candidate_count_after_acl: int


class ContextRequestRequest(BaseModel):
    task: str
    task_id: str | None = None
    purpose: str | None = None
    project_id: str | None = None
    zones: list[MemoryZone] = Field(default_factory=lambda: [MemoryZone.PUBLIC_PROFILE])
    grant_token: str | None = None
    memory_types: list[MemoryType] | None = None
    max_tokens: int = Field(default=1200, ge=200, le=8000)
    include_graph: bool = True
    top_k: int = Field(default=8, ge=1, le=30)
    ttl_minutes: int | None = Field(default=None, ge=1, le=60)
    retrieval_mode: str = "summary_first"
    use_llm_rerank: bool = True


class ContextRequestResponse(BaseModel):
    status: str
    context: ContextComposeResponse | None = None
    grant: GrantOut | None = None
    denied_zones: list[DeniedZoneOut] = Field(default_factory=list)
    message: str
    audit_id: str


class ContextRequestStatusResponse(BaseModel):
    status: str
    context: ContextComposeResponse | None = None
    grant: GrantOut | None = None
    message: str
    audit_id: str


class SharePackScopeOut(BaseModel):
    project_id: str
    allowed_zones: list[MemoryZone]
    allowed_memory_types: list[MemoryType]
    allowed_tags: list[str] = Field(default_factory=list)
    excluded_memory_ids: list[str] = Field(default_factory=list)
    policy_summary: list[str] = Field(default_factory=list)


class SharePackOut(BaseModel):
    id: str
    project_id: str
    name: str
    description: str = ""
    recipient_label: str = ""
    created_by_agent_id: str
    scope: SharePackScopeOut
    status: SharePackStatus
    expires_at: datetime
    max_uses: int
    use_count: int
    uses_remaining: int
    created_at: datetime
    revoked_at: datetime | None = None
    token: str | None = None
    display: DisplayOut | None = None


class SharePackPreviewRequest(BaseModel):
    project_id: str
    name: str = "Project onboarding share"
    description: str = ""
    recipient_label: str = ""
    task: str = "Onboard me to this project."
    allowed_zones: list[MemoryZone] = Field(default_factory=lambda: [MemoryZone.WORK_CONTEXT])
    allowed_memory_types: list[MemoryType] = Field(
        default_factory=lambda: [
            MemoryType.CONTEXT,
            MemoryType.RELATIONSHIP,
            MemoryType.PREFERENCE,
            MemoryType.PROCEDURE,
            MemoryType.LESSON,
            MemoryType.ANTI_PATTERN,
        ]
    )
    allowed_tags: list[str] = Field(default_factory=list)
    excluded_memory_ids: list[str] = Field(default_factory=list)
    max_tokens: int = Field(default=1600, ge=400, le=8000)
    top_k: int = Field(default=12, ge=1, le=40)


class SharePackPreviewResponse(BaseModel):
    prompt_context: str
    source_cards: list[MemoryCardOut]
    matched_summaries: list[SemanticCandidateOut] = Field(default_factory=list)
    scope: SharePackScopeOut
    excluded_summary: list[str] = Field(default_factory=list)
    audit_id: str
    token_estimate: int
    candidate_count_after_policy: int
    display: DisplayOut


class SharePackCreateRequest(SharePackPreviewRequest):
    ttl_days: int = Field(default=7, ge=1, le=90)
    max_uses: int = Field(default=20, ge=1, le=500)


class SharePackCreateResponse(BaseModel):
    share_pack: SharePackOut
    prompt_context: str
    source_cards: list[MemoryCardOut]
    matched_summaries: list[SemanticCandidateOut] = Field(default_factory=list)
    audit_id: str


class SharePackComposeRequest(BaseModel):
    share_token: str
    task: str = "Onboard me to this project."
    max_tokens: int = Field(default=1600, ge=400, le=8000)
    top_k: int = Field(default=12, ge=1, le=40)


class SharePackComposeResponse(BaseModel):
    share_pack: SharePackOut
    prompt_context: str
    source_cards: list[MemoryCardOut]
    matched_summaries: list[SemanticCandidateOut] = Field(default_factory=list)
    scope: SharePackScopeOut
    audit_id: str
    token_estimate: int
    display: DisplayOut


class GraphHealthResponse(BaseModel):
    graph_available: bool
    enabled: bool
    provider: str = "neo4j"
    reason: str | None = None


class GraphSearchRequest(BaseModel):
    query: str
    project_id: str | None = None
    zones: list[MemoryZone]
    grant_token: str | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class GraphSearchResponse(BaseModel):
    graph_available: bool
    summary: str
    cards: list[GraphCardOut] = Field(default_factory=list)
    audit_id: str
    reason: str | None = None


class GraphExplainResponse(BaseModel):
    graph_available: bool
    entity_id: str
    allowed: bool
    reason: str
    cards: list[GraphCardOut] = Field(default_factory=list)
    audit_id: str


class GraphRebuildResponse(BaseModel):
    graph_available: bool
    indexed_memories: int = 0
    audit_id: str
    reason: str | None = None


class AuditOut(BaseModel):
    id: str
    agent_id: str
    action: str
    resource_type: str
    resource_id: str | None
    details: dict[str, Any]
    created_at: datetime


class MemoryVersionOut(BaseModel):
    id: str
    memory_id: str
    previous_memory_id: str | None = None
    event: str
    actor_agent_id: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class MemoryListResponse(BaseModel):
    memories: list[MemoryOut]
    display: SearchDisplayOut | None = None


class MemoryDetailResponse(BaseModel):
    memory: MemoryOut
    facts: list[FactCardOut] = Field(default_factory=list)
    timeline: list[MemoryVersionOut] = Field(default_factory=list)
    audit: list[AuditOut] = Field(default_factory=list)


class MemoryPatchRequest(BaseModel):
    content: str | None = None
    tags: list[str] | None = None
    memory_type: MemoryType | None = None
    memory_zone: MemoryZone | None = None
    project_id: str | None = None
    reason: str = ""


class MemorySupersedeRequest(BaseModel):
    content: str | None = None
    new_memory_id: str | None = None
    memory_type: MemoryType | None = None
    memory_zone: MemoryZone | None = None
    project_id: str | None = None
    tags: list[str] | None = None
    reason: str = ""


class MemoryRestoreRequest(BaseModel):
    reason: str = ""


class ModelProfileCreateRequest(BaseModel):
    id: str | None = None
    name: str
    provider: ModelProvider
    model: str = ""
    endpoint_url: str | None = None
    api_key_env: str | None = None
    api_key: str | None = Field(default=None, repr=False)
    allowed_tasks: list[ModelTask] = Field(default_factory=list)
    allowed_zones: list[MemoryZone] = Field(default_factory=list)
    local_only: bool = False
    auto_apply_low_sensitivity: bool = False
    is_active: bool = False


class ModelProfileOut(BaseModel):
    id: str
    name: str
    provider: ModelProvider
    model: str
    endpoint_url: str | None
    api_key_env: str | None
    has_api_key: bool
    allowed_tasks: list[ModelTask]
    allowed_zones: list[MemoryZone]
    local_only: bool
    auto_apply_low_sensitivity: bool
    is_active: bool
    created_at: datetime


class ModelProfileTestRequest(BaseModel):
    content: str = "I prefer concise answers."
    task: ModelTask = ModelTask.CLASSIFY_CAPTURE


class ModelProcessingClassifyRequest(BaseModel):
    content: str
    project_id: str | None = None
    model_profile_id: str | None = None


class ModelProcessingSummarizeRequest(BaseModel):
    content: str
    model_profile_id: str | None = None


class ModelProcessingLessonRequest(BaseModel):
    feedback: str
    expected_behavior: str = ""
    model_profile_id: str | None = None


class ModelProcessingResponse(BaseModel):
    profile_id: str
    provider: ModelProvider
    task: ModelTask
    sent_to_model: bool
    used_redacted_preview: bool
    redacted_preview: str
    suggestion: dict[str, Any]
    fallback_used: bool = False
    risk_warnings: list[str] = Field(default_factory=list)
    display: DisplayOut | None = None
