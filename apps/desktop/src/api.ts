export type MemoryZone =
  | "public_profile"
  | "work_context"
  | "personal_context"
  | "sensitive_vault"
  | "payment_reference";

export type MemoryType = "context" | "preference" | "relationship" | "procedure" | "lesson" | "anti_pattern";

export interface Display {
  title: string;
  subtitle: string;
  badges: string[];
  reasons: string[];
  warnings: string[];
  primary_action?: string | null;
  safe_preview?: string | null;
}

export interface MemoryCard {
  id: string;
  title: string;
  subtitle: string;
  zone?: MemoryZone | null;
  memory_type: MemoryType;
  sensitivity: "low" | "medium" | "high";
  source: string;
  why_visible: string;
  preview: string;
  score?: number | null;
}

export interface SearchDisplay {
  summary: string;
  cards: MemoryCard[];
}

export interface GraphCard {
  id: string;
  title: string;
  subtitle: string;
  entity_type: string;
  relation_type: string;
  zone?: MemoryZone | null;
  sensitivity: "low" | "medium" | "high";
  source_count: number;
  source_memory_ids: string[];
  why_visible: string;
  risk_note: string;
}

export interface CaptureAnalysis {
  rule_suggestion?: Record<string, unknown> | null;
  model_suggestion?: Record<string, unknown> | null;
  final_suggestion_source: string;
  sent_to_model: boolean;
  used_redacted_preview: boolean;
  suggested_zone: MemoryZone;
  suggested_memory_type: MemoryType;
  sensitivity: "low" | "medium" | "high";
  redacted_preview: string;
  risk_warnings: string[];
  tags: string[];
  should_require_confirmation: boolean;
  display?: Display | null;
}

export interface Grant {
  id: string;
  agent_id: string;
  task_id: string;
  project_id?: string | null;
  purpose: string;
  allowed_zones: MemoryZone[];
  status: "pending" | "approved" | "rejected" | "revoked" | "expired";
  confirmation_level: "low" | "normal" | "high";
  expires_at: string;
  created_at: string;
  token?: string | null;
}

export interface AuditEvent {
  id: string;
  agent_id: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

export interface Memory {
  id: string;
  project_id?: string | null;
  visibility?: "public" | "project" | "private";
  memory_zone?: MemoryZone | null;
  memory_type: MemoryType;
  content_kind?: "text" | "image";
  content: string;
  tags?: string[];
  sensitivity: "low" | "medium" | "high";
  source?: string;
  status?: string;
  superseded_by_id?: string | null;
  semantic_summary?: string;
  semantic_entities?: string[];
  semantic_triggers?: string[];
  semantic_facts?: Array<Record<string, unknown>>;
  summary_confidence?: number;
  created_at?: string;
  score?: number | null;
}

export interface SearchResponse {
  memories: Memory[];
  candidate_count_after_acl: number;
  audit_id: string;
  display?: SearchDisplay | null;
}

export interface InboxItem {
  id: string;
  status: "pending_review" | "approved" | "rejected" | "merged";
  project_id?: string | null;
  content_kind: "text" | "image";
  source: "clipboard" | "manual" | "api" | "file_text" | "agent_feedback";
  source_url?: string | null;
  source_title?: string | null;
  asset_path?: string | null;
  redacted_preview: string;
  suggested_zone: MemoryZone;
  suggested_memory_type: MemoryType;
  sensitivity: "low" | "medium" | "high";
  risk_warnings: string[];
  tags: string[];
  proposal_kind: "new" | "duplicate" | "update" | "conflict";
  duplicate_memory_ids: string[];
  conflict_memory_ids: string[];
  supersedes_memory_id?: string | null;
  human_reason: string;
  diff_summary: string;
  semantic_summary: string;
  semantic_entities: string[];
  semantic_triggers: string[];
  candidate_memory_ids: string[];
  llm_relationship?: string | null;
  llm_confidence: number;
  llm_reason: string;
  needs_user_decision: boolean;
  approved_memory_id?: string | null;
  merged_into_memory_id?: string | null;
  created_at: string;
  reviewed_at?: string | null;
  display?: Display | null;
}

export interface IngestResponse {
  auto_approved: boolean;
  memory?: Memory | null;
  inbox_item?: InboxItem | null;
  audit_id: string;
  display?: Display | null;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface FactCard {
  id: string;
  title: string;
  subtitle: string;
  fact_type: string;
  relation_type: string;
  zone?: MemoryZone | null;
  sensitivity: "low" | "medium" | "high";
  source_count: number;
  source_memory_ids: string[];
  why_visible: string;
  confidence: number;
}

export interface ContextSection {
  key: string;
  title: string;
  content: string;
  source_memory_ids: string[];
}

export interface DeniedZone {
  zone: MemoryZone;
  reason: string;
}

export interface ContextComposeResponse {
  prompt_context: string;
  sections: ContextSection[];
  source_cards: MemoryCard[];
  matched_summaries: SemanticCandidate[];
  fact_cards: FactCard[];
  graph_cards: GraphCard[];
  denied_zones: DeniedZone[];
  audit_id: string;
  token_estimate: number;
  candidate_count_after_acl: number;
}

export interface ContextRequestStatusResponse {
  status: string;
  context?: ContextComposeResponse | null;
  grant?: Grant | null;
  message: string;
  audit_id?: string;
}

export interface SharePackScope {
  project_id: string;
  allowed_zones: MemoryZone[];
  allowed_memory_types: MemoryType[];
  allowed_tags: string[];
  excluded_memory_ids: string[];
  policy_summary: string[];
}

export interface SharePack {
  id: string;
  project_id: string;
  name: string;
  description: string;
  recipient_label: string;
  created_by_agent_id: string;
  scope: SharePackScope;
  status: "active" | "revoked" | "expired";
  expires_at: string;
  max_uses: number;
  use_count: number;
  uses_remaining: number;
  created_at: string;
  revoked_at?: string | null;
  token?: string | null;
  display?: Display | null;
}

export interface SharePackPreviewResponse {
  prompt_context: string;
  source_cards: MemoryCard[];
  matched_summaries: SemanticCandidate[];
  scope: SharePackScope;
  excluded_summary: string[];
  audit_id: string;
  token_estimate: number;
  candidate_count_after_policy: number;
  display: Display;
}

export interface SharePackCreateResponse {
  share_pack: SharePack;
  prompt_context: string;
  source_cards: MemoryCard[];
  matched_summaries: SemanticCandidate[];
  audit_id: string;
}

export interface SharePackComposeResponse {
  share_pack: SharePack;
  prompt_context: string;
  source_cards: MemoryCard[];
  matched_summaries: SemanticCandidate[];
  scope: SharePackScope;
  audit_id: string;
  token_estimate: number;
  display: Display;
}

export interface MemoryVersion {
  id: string;
  memory_id: string;
  previous_memory_id?: string | null;
  event: string;
  actor_agent_id: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface MemoryDetail {
  memory: Memory;
  facts: FactCard[];
  timeline: MemoryVersion[];
  audit: AuditEvent[];
}

export interface MemoryListResponse {
  memories: Memory[];
  display?: SearchDisplay | null;
}

export interface ExtractionPreview {
  redacted_preview: string;
  suggested_zone: MemoryZone;
  suggested_memory_type: MemoryType;
  sensitivity: "low" | "medium" | "high";
  facts: Array<{
    subject: string;
    predicate: string;
    object: string;
    fact_type: string;
    project_id?: string | null;
    zone?: MemoryZone | null;
    confidence: number;
  }>;
  relationship: {
    proposal_kind: "new" | "duplicate" | "update" | "conflict";
    duplicate_memory_ids: string[];
    conflict_memory_ids: string[];
    supersedes_memory_id?: string | null;
    human_reason: string;
    diff_summary: string;
  };
  semantic?: SemanticSummary | null;
  candidate_matches: SemanticCandidate[];
  llm_relationship?: SemanticRelationship | null;
  needs_user_decision: boolean;
  display: Display;
}

export interface SemanticSummary {
  summary: string;
  entities: string[];
  triggers: string[];
  facts: Array<Record<string, unknown>>;
  confidence: number;
  sent_to_model: boolean;
  used_redacted_preview: boolean;
  model_profile_id?: string | null;
  fallback_used: boolean;
  risk_warnings: string[];
}

export interface SemanticCandidate {
  memory_id: string;
  summary: string;
  content_preview: string;
  zone?: MemoryZone | null;
  memory_type: MemoryType;
  sensitivity: "low" | "medium" | "high";
  score: number;
  reason: string;
}

export interface SemanticRelationship {
  relationship: string;
  confidence: number;
  candidate_memory_id?: string | null;
  reason: string;
  recommended_action: string;
  sent_to_model: boolean;
  fallback_used: boolean;
}

export interface GraphHealth {
  graph_available: boolean;
  enabled: boolean;
  provider: string;
  reason?: string | null;
}

export interface GraphSearchResponse {
  graph_available: boolean;
  summary: string;
  cards: GraphCard[];
  audit_id: string;
  reason?: string | null;
}

export interface ModelProfile {
  id: string;
  name: string;
  provider: "rule_only" | "openai_compatible" | "ollama";
  model: string;
  endpoint_url?: string | null;
  api_key_env?: string | null;
  has_api_key: boolean;
  allowed_tasks: string[];
  allowed_zones: MemoryZone[];
  local_only: boolean;
  auto_apply_low_sensitivity: boolean;
  is_active: boolean;
  created_at: string;
}

export interface ModelProfileCreateInput {
  id?: string | null;
  name: string;
  provider: "rule_only" | "openai_compatible" | "ollama";
  model: string;
  endpoint_url?: string | null;
  api_key?: string | null;
  api_key_env?: string | null;
  allowed_tasks?: string[];
  allowed_zones?: MemoryZone[];
  local_only?: boolean;
  auto_apply_low_sensitivity?: boolean;
  is_active?: boolean;
}

export interface ModelProcessingResponse {
  profile_id: string;
  provider: "rule_only" | "openai_compatible" | "ollama";
  task: "classify_capture" | "summarize_memory" | "extract_lesson";
  sent_to_model: boolean;
  used_redacted_preview: boolean;
  redacted_preview: string;
  suggestion: Record<string, unknown>;
  fallback_used: boolean;
  risk_warnings: string[];
  display?: Display | null;
}

const DEFAULT_BASE_URL = "http://127.0.0.1:8010";
const DEFAULT_API_KEY = "admin-demo-key";
const DEFAULT_AGENT_API_KEY = "backend-demo-key";

export class ApiClient {
  constructor(
    public baseUrl = localStorage.getItem("pmf.baseUrl") || DEFAULT_BASE_URL,
    public apiKey = localStorage.getItem("pmf.apiKey") || DEFAULT_API_KEY,
    public agentApiKey = localStorage.getItem("pmf.agentApiKey") || DEFAULT_AGENT_API_KEY,
    public projectId = localStorage.getItem("pmf.projectId") || "memory-gateway"
  ) {}

  setConfig(baseUrl: string, apiKey: string, agentApiKey: string) {
    this.baseUrl = baseUrl;
    this.apiKey = apiKey;
    this.agentApiKey = agentApiKey;
    localStorage.setItem("pmf.baseUrl", baseUrl);
    localStorage.setItem("pmf.apiKey", apiKey);
    localStorage.setItem("pmf.agentApiKey", agentApiKey);
  }

  setProject(projectId: string) {
    this.projectId = projectId;
    localStorage.setItem("pmf.projectId", projectId);
  }

  health() {
    return this.request<{ status: string }>("/healthz");
  }

  seed() {
    return this.request<{ status: string }>("/v1/admin/seed", {
      method: "POST"
    });
  }

  listProjects() {
    return this.request<Project[]>("/v1/projects");
  }

  createProject(id: string, name: string, description = "") {
    return this.request<Project>("/v1/projects", {
      method: "POST",
      body: JSON.stringify({ id, name, description })
    });
  }

  async request<T>(path: string, init: RequestInit = {}, apiKey = this.apiKey): Promise<T> {
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, {
        ...init,
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": apiKey,
          ...(init.headers || {})
        }
      });
    } catch (error) {
      const detail = error instanceof Error ? error.message : "network request failed";
      throw new Error(`Cannot reach backend at ${this.baseUrl}. Check that the API is running and allowed by CORS. ${detail}`);
    }
    if (!response.ok) {
      const body = await response.text();
      throw new Error(`${response.status} ${response.statusText}: ${body}`);
    }
    return response.json() as Promise<T>;
  }

  analyzeCapture(content: string, modelProfileId?: string | null) {
    return this.request<CaptureAnalysis>("/v1/captures/analyze", {
      method: "POST",
      body: JSON.stringify({
        content,
        content_kind: "text",
        capture_source: "clipboard",
        project_id: this.projectId,
        model_profile_id: modelProfileId || null
      })
    });
  }

  ingest(content: string, modelProfileId?: string | null) {
    return this.request<IngestResponse>("/v1/ingest", {
      method: "POST",
      body: JSON.stringify({
        content,
        content_kind: "text",
        source: "clipboard",
        project_id: this.projectId,
        model_profile_id: modelProfileId || null,
        auto_approve_public_low: true
      })
    });
  }

  listInbox(status = "pending_review") {
    return this.request<InboxItem[]>(`/v1/inbox?status=${encodeURIComponent(status)}`);
  }

  approveInbox(id: string, zone?: MemoryZone, memoryType?: MemoryType) {
    return this.request<InboxItem>(`/v1/inbox/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({
        memory_zone: zone || null,
        memory_type: memoryType || null,
        project_id: this.projectId,
        tags: null,
        note: "Approved from desktop inbox"
      })
    });
  }

  approveInboxUpdate(id: string, supersedeMemoryId: string, zone?: MemoryZone, memoryType?: MemoryType) {
    return this.request<InboxItem>(`/v1/inbox/${id}/approve-update`, {
      method: "POST",
      body: JSON.stringify({
        memory_zone: zone || null,
        memory_type: memoryType || null,
        project_id: this.projectId,
        supersede_memory_id: supersedeMemoryId,
        tags: null,
        note: "Approved as update from desktop inbox"
      })
    });
  }

  approveInboxSeparate(id: string, zone?: MemoryZone, memoryType?: MemoryType) {
    return this.request<InboxItem>(`/v1/inbox/${id}/approve-separate`, {
      method: "POST",
      body: JSON.stringify({
        memory_zone: zone || null,
        memory_type: memoryType || null,
        project_id: this.projectId,
        tags: null,
        note: "Saved as separate memory from desktop inbox"
      })
    });
  }

  rejectInbox(id: string, reason = "Rejected from desktop inbox") {
    return this.request<InboxItem>(`/v1/inbox/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason })
    });
  }

  commitCapture(content: string, analysis: CaptureAnalysis) {
    return this.request<{ capture_id: string; memory?: unknown; proposal?: unknown }>("/v1/captures/commit", {
      method: "POST",
      body: JSON.stringify({
        content,
        content_kind: "text",
        capture_source: "clipboard",
        memory_zone: analysis.suggested_zone,
        memory_type: analysis.suggested_memory_type,
        project_id: this.projectId,
        tags: analysis.tags,
        approve_now: true
      })
    });
  }

  getPendingGrants() {
    return this.request<Grant[]>("/v1/grants?status=pending");
  }

  requestGrant(
    taskId = `desktop-demo-${Date.now()}`,
    purpose = "Desktop demo needs work_context to show permissioned memory retrieval.",
    allowedZones: MemoryZone[] = ["work_context"]
  ) {
    return this.request<Grant>("/v1/grants/request", {
      method: "POST",
      body: JSON.stringify({
        task_id: taskId,
        purpose,
        allowed_zones: allowedZones,
        project_id: this.projectId,
        ttl_minutes: 15
      })
    }, this.agentApiKey);
  }

  approveGrant(id: string) {
    return this.request<Grant>(`/v1/grants/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ ttl_minutes: null })
    });
  }

  revokeGrant(id: string) {
    return this.request<Grant>(`/v1/grants/${id}/revoke`, {
      method: "POST"
    });
  }

  vaultSearch(query: string, zones: MemoryZone[], grantToken?: string | null) {
    return this.request<SearchResponse>("/v1/vault/search", {
      method: "POST",
      body: JSON.stringify({
        query,
        project_id: this.projectId,
        zones,
        grant_token: grantToken || null,
        top_k: 5
      })
    }, this.agentApiKey);
  }

  graphHealth() {
    return this.request<GraphHealth>("/v1/graph/health");
  }

  graphSearch(query: string, zones: MemoryZone[], grantToken?: string | null) {
    return this.request<GraphSearchResponse>("/v1/graph/search", {
      method: "POST",
      body: JSON.stringify({
        query,
        project_id: this.projectId,
        zones,
        grant_token: grantToken || null,
        top_k: 6
      })
    }, this.agentApiKey);
  }

  graphRebuild() {
    return this.request<{ graph_available: boolean; indexed_memories: number; audit_id: string; reason?: string | null }>("/v1/graph/rebuild", {
      method: "POST"
    });
  }

  composeContext(task: string, zones: MemoryZone[], grantToken?: string | null, maxTokens = 1200) {
    return this.request<ContextComposeResponse>("/v1/context/compose", {
      method: "POST",
      body: JSON.stringify({
        task,
        project_id: this.projectId,
        zones,
        grant_token: grantToken || null,
        memory_types: null,
        max_tokens: maxTokens,
        include_graph: true,
        top_k: 8,
        retrieval_mode: "summary_first",
        use_llm_rerank: true
      })
    }, this.agentApiKey);
  }

  requestContext(task: string, zones: MemoryZone[], grantToken?: string | null, maxTokens = 1200) {
    return this.request<ContextRequestStatusResponse>("/v1/context/request", {
      method: "POST",
      body: JSON.stringify({
        task,
        task_id: `desktop-context-${Date.now()}`,
        purpose: `Compose context for: ${task}`,
        project_id: this.projectId,
        zones,
        grant_token: grantToken || null,
        memory_types: null,
        max_tokens: maxTokens,
        include_graph: true,
        top_k: 8,
        retrieval_mode: "summary_first",
        use_llm_rerank: true
      })
    }, this.agentApiKey);
  }

  getContextRequest(grantId: string) {
    return this.request<ContextRequestStatusResponse>(`/v1/context/requests/${grantId}`, {}, this.agentApiKey);
  }

  composeApprovedContext(grantId: string) {
    return this.request<ContextRequestStatusResponse>(`/v1/context/requests/${grantId}/compose`, {
      method: "POST"
    }, this.agentApiKey);
  }

  previewSharePack(
    name: string,
    description: string,
    recipientLabel: string,
    task: string,
    allowedMemoryTypes: MemoryType[],
    maxTokens = 1600,
    topK = 12
  ) {
    return this.request<SharePackPreviewResponse>("/v1/share-packs/preview", {
      method: "POST",
      body: JSON.stringify({
        project_id: this.projectId,
        name,
        description,
        recipient_label: recipientLabel,
        task,
        allowed_zones: ["work_context"],
        allowed_memory_types: allowedMemoryTypes,
        allowed_tags: [],
        excluded_memory_ids: [],
        max_tokens: maxTokens,
        top_k: topK
      })
    });
  }

  createSharePack(
    name: string,
    description: string,
    recipientLabel: string,
    task: string,
    allowedMemoryTypes: MemoryType[],
    ttlDays: number,
    maxUses: number,
    maxTokens = 1600,
    topK = 12
  ) {
    return this.request<SharePackCreateResponse>("/v1/share-packs", {
      method: "POST",
      body: JSON.stringify({
        project_id: this.projectId,
        name,
        description,
        recipient_label: recipientLabel,
        task,
        allowed_zones: ["work_context"],
        allowed_memory_types: allowedMemoryTypes,
        allowed_tags: [],
        excluded_memory_ids: [],
        max_tokens: maxTokens,
        top_k: topK,
        ttl_days: ttlDays,
        max_uses: maxUses
      })
    });
  }

  listSharePacks(status?: string | null) {
    const params = status ? `?status=${encodeURIComponent(status)}` : "";
    return this.request<SharePack[]>(`/v1/share-packs${params}`);
  }

  composeSharePack(sharePackId: string, shareToken: string, task: string, maxTokens = 1600, topK = 12) {
    return this.request<SharePackComposeResponse>(`/v1/share-packs/${sharePackId}/compose`, {
      method: "POST",
      body: JSON.stringify({
        share_token: shareToken,
        task,
        max_tokens: maxTokens,
        top_k: topK
      })
    }, this.agentApiKey);
  }

  revokeSharePack(sharePackId: string) {
    return this.request<SharePack>(`/v1/share-packs/${sharePackId}/revoke`, {
      method: "POST"
    });
  }

  listMemories(status = "approved", query = "") {
    const params = new URLSearchParams({
      project_id: this.projectId,
      status,
      limit: "100"
    });
    if (query.trim()) params.set("query", query.trim());
    return this.request<MemoryListResponse>(`/v1/memories?${params.toString()}`);
  }

  getMemory(id: string) {
    return this.request<MemoryDetail>(`/v1/memories/${id}`);
  }

  patchMemory(id: string, payload: Partial<Pick<Memory, "content" | "tags" | "memory_type" | "memory_zone" | "project_id">> & { reason?: string }) {
    return this.request<MemoryDetail>(`/v1/memories/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    });
  }

  supersedeMemory(id: string, content: string, reason = "Superseded from desktop memory editor") {
    return this.request<MemoryDetail>(`/v1/memories/${id}/supersede`, {
      method: "POST",
      body: JSON.stringify({ content, reason })
    });
  }

  restoreMemory(id: string) {
    return this.request<MemoryDetail>(`/v1/memories/${id}/restore`, {
      method: "POST",
      body: JSON.stringify({ reason: "Restored from desktop memory editor" })
    });
  }

  deleteMemory(id: string) {
    return this.request<{ status: string }>(`/v1/memories/${id}/delete`, {
      method: "POST"
    });
  }

  extractionPreview(content: string) {
    return this.request<ExtractionPreview>("/v1/extraction/preview", {
      method: "POST",
      body: JSON.stringify({
        content,
        content_kind: "text",
        project_id: this.projectId
      })
    });
  }

  getAudit() {
    return this.request<AuditEvent[]>("/v1/audit?limit=30");
  }

  getModelProfiles() {
    return this.request<ModelProfile[]>("/v1/model-profiles");
  }

  createModelProfile(input: ModelProfileCreateInput) {
    return this.request<ModelProfile>("/v1/model-profiles", {
      method: "POST",
      body: JSON.stringify(input)
    });
  }

  activateModelProfile(id: string) {
    return this.request<ModelProfile>(`/v1/model-profiles/${id}/activate`, {
      method: "POST"
    });
  }

  testModelProfile(id: string, content = "I prefer concise answers.") {
    return this.request<ModelProcessingResponse>(`/v1/model-profiles/${id}/test`, {
      method: "POST",
      body: JSON.stringify({
        content,
        task: "classify_capture"
      })
    });
  }
}
