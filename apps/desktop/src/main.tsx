import React, { useEffect, useMemo, useRef, useState } from "react";
import ReactDOM from "react-dom/client";
import {
  Bell,
  Check,
  Clipboard,
  FileText,
  Inbox,
  KeyRound,
  RefreshCw,
  Save,
  Search,
  Settings,
  Shield,
  X
} from "lucide-react";
import {
  ApiClient,
  AuditEvent,
  CaptureAnalysis,
  ContextComposeResponse,
  ContextRequestStatusResponse,
  Display,
  ExtractionPreview,
  FactCard,
  Grant,
  InboxItem,
  Memory,
  MemoryCard,
  MemoryType,
  MemoryDetail,
  MemoryZone,
  ModelProcessingResponse,
  ModelProfile,
  Project,
  SemanticCandidate,
  SharePack,
  SharePackComposeResponse,
  SharePackCreateResponse,
  SharePackPreviewResponse
} from "./api";
import "./styles.css";

async function readClipboardText(): Promise<string> {
  try {
    const mod = await import("@tauri-apps/plugin-clipboard-manager");
    return (await mod.readText()) || "";
  } catch {
    return await navigator.clipboard.readText();
  }
}

async function bringAppToFront(): Promise<void> {
  try {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    const win = getCurrentWindow();
    await win.show();
    await win.unminimize();
    await win.setFocus();
  } catch {
    window.focus();
  }
}

async function notifyGrantRequest(grant: Grant): Promise<void> {
  const title = "Memory access request";
  const body = `${grant.agent_id} requests ${asArray(grant.allowed_zones).map(zoneLabel).join(", ")} for ${grant.project_id || "global"}.`;
  try {
    if ("Notification" in window) {
      const permission = Notification.permission === "default"
        ? await Notification.requestPermission()
        : Notification.permission;
      if (permission === "granted") {
        new Notification(title, { body });
      }
    }
  } catch {
    // Notification support varies between browser preview and Tauri shells.
  }
}

function BadgeRow({ badges }: { badges: Array<string | null | undefined> }) {
  return (
    <div className="badge-row">
      {badges.filter(Boolean).map((badge) => (
        <span key={badge}>{badge}</span>
      ))}
    </div>
  );
}

function asArray<T>(value: T[] | null | undefined): T[] {
  return Array.isArray(value) ? value : [];
}

function asNumber(value: number | null | undefined): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function DisplayPanel({ display, fallback }: { display?: Display | null; fallback: string }) {
  if (!display) return <div className="empty">{fallback}</div>;
  const badges = asArray(display.badges);
  const reasons = asArray(display.reasons);
  const warnings = asArray(display.warnings);
  return (
    <div className="display-card">
      <div>
        <h3>{display.title}</h3>
        <p>{display.subtitle}</p>
      </div>
      <BadgeRow badges={badges} />
      {display.safe_preview && <div className="preview-box">{display.safe_preview}</div>}
      <div className="reason-list">
        {reasons.map((reason) => (
          <span key={reason}>{reason}</span>
        ))}
      </div>
      {warnings.map((warning) => (
        <p className="warning" key={warning}>{warning}</p>
      ))}
      {display.primary_action && <small>{display.primary_action}</small>}
    </div>
  );
}

function readableMemoryType(type?: MemoryType | string | null) {
  const labels: Record<string, string> = {
    context: "Context",
    preference: "Preference",
    relationship: "Relationship",
    procedure: "Procedure",
    lesson: "Lesson",
    anti_pattern: "Anti-pattern"
  };
  return type ? labels[String(type)] || String(type).replace(/_/g, " ") : "Memory";
}

function CaptureDecisionCards({
  analysis,
  preview
}: {
  analysis?: CaptureAnalysis | null;
  preview?: ExtractionPreview | null;
}) {
  if (!analysis && !preview) {
    return <div className="empty">Analyze or ingest selected content to see a human-readable decision card.</div>;
  }
  const summary = preview?.semantic?.summary || analysis?.redacted_preview || "No summary yet.";
  const zone = preview?.suggested_zone || analysis?.suggested_zone || null;
  const memoryType = preview?.suggested_memory_type || analysis?.suggested_memory_type || null;
  const sensitivity = preview?.sensitivity || analysis?.sensitivity || "low";
  const needsReview = Boolean(analysis?.should_require_confirmation || preview?.needs_user_decision || zone !== "public_profile");
  const warnings = asArray(analysis?.risk_warnings).concat(asArray(preview?.display?.warnings));
  return (
    <div className="decision-grid">
      <article className="decision-card">
        <span>Memory Summary</span>
        <strong>{readableMemoryType(memoryType)}</strong>
        <p>{summary}</p>
      </article>
      <article className="decision-card">
        <span>Suggested Save Location</span>
        <strong>{zoneLabel(zone)}</strong>
        <p>
          Save as {readableMemoryType(memoryType).toLowerCase()} memory with {sensitivity} sensitivity.
        </p>
      </article>
      <article className={`decision-card ${needsReview ? "review" : ""}`}>
        <span>Risk & Permission</span>
        <strong>{needsReview ? "Review required" : "Can auto-save"}</strong>
        <p>
          {zone === "public_profile"
            ? "Agents may use this without a grant if it stays low risk."
            : `Agents need a ${zone || "protected"} grant before using this memory.`}
        </p>
        {warnings.slice(0, 2).map((warning) => <small key={warning}>{warning}</small>)}
      </article>
    </div>
  );
}

function MemoryResultCard({ card }: { card: MemoryCard }) {
  return (
    <article className={`memory-row ${card.sensitivity}`}>
      <strong>{card.title}</strong>
      <p>{card.preview}</p>
      <small>{card.why_visible}</small>
      <BadgeRow badges={[card.zone, card.memory_type, card.sensitivity, card.score == null ? "score n/a" : `score ${card.score}`]} />
    </article>
  );
}

function FactResultCard({ card }: { card: FactCard }) {
  return (
    <article className={`graph-card ${card.sensitivity}`}>
      <strong>{card.title}</strong>
      <p>{card.subtitle}</p>
      <small>{card.why_visible}</small>
      <BadgeRow badges={[card.relation_type, card.fact_type, card.zone, card.sensitivity, `confidence ${card.confidence}`]} />
    </article>
  );
}

function SemanticCandidateCard({ candidate }: { candidate: SemanticCandidate }) {
  return (
    <article className={`memory-row ${candidate.sensitivity}`}>
      <div className="row-title">
        <strong>Matched summary</strong>
        <span>score {candidate.score}</span>
      </div>
      <p>{candidate.summary}</p>
      <small>{candidate.reason}</small>
      <BadgeRow badges={[candidate.zone, candidate.memory_type, candidate.sensitivity, candidate.memory_id]} />
    </article>
  );
}

function SharePackCard({
  pack,
  onRevoke
}: {
  pack: SharePack;
  onRevoke: (id: string) => void;
}) {
  return (
    <article className={`memory-row ${pack.status === "active" ? "low" : "medium"}`}>
      <div className="row-title">
        <strong>{pack.name}</strong>
        <span>{pack.status}</span>
      </div>
      <p>{pack.description || `Share pack for ${pack.recipient_label || "collaborator"}`}</p>
      <small>Expires {new Date(pack.expires_at).toLocaleString()} - {pack.uses_remaining} uses left</small>
      <BadgeRow badges={[
        pack.project_id,
        pack.recipient_label || "recipient not labeled",
        ...asArray(pack.scope?.allowed_memory_types).map(readableMemoryType)
      ]} />
      <div className="actions">
        <button onClick={() => onRevoke(pack.id)} disabled={pack.status !== "active"}><X size={16} />Revoke</button>
      </div>
    </article>
  );
}

function MemoryEditorCard({
  memory,
  onOpen
}: {
  memory: Memory;
  onOpen: (memory: Memory) => void;
}) {
  return (
    <article className={`memory-row ${memory.sensitivity}`}>
      <div className="row-title">
        <strong>{zoneLabel(memory.memory_zone)} / {memory.memory_type}</strong>
        <span>{memory.status || "approved"}</span>
      </div>
      <p>{memory.content}</p>
      <BadgeRow badges={[
        memory.project_id || "global",
        memory.sensitivity,
        ...(memory.tags || []),
        memory.superseded_by_id ? `superseded by ${memory.superseded_by_id}` : null
      ]} />
      <div className="actions">
        <button onClick={() => onOpen(memory)}><FileText size={16} />Details</button>
      </div>
    </article>
  );
}

function InboxCard({
  item,
  onApprove,
  onApproveUpdate,
  onApproveSeparate,
  onReject
}: {
  item: InboxItem;
  onApprove: (item: InboxItem) => void;
  onApproveUpdate: (item: InboxItem) => void;
  onApproveSeparate: (item: InboxItem) => void;
  onReject: (item: InboxItem) => void;
}) {
  const needsRelationshipDecision = item.proposal_kind === "update" || item.proposal_kind === "conflict";
  const tags = asArray(item.tags);
  const duplicateIds = asArray(item.duplicate_memory_ids);
  const conflictIds = asArray(item.conflict_memory_ids);
  const riskWarnings = asArray(item.risk_warnings);
  const semanticEntities = asArray(item.semantic_entities);
  const semanticTriggers = asArray(item.semantic_triggers);
  const displayReasons = asArray(item.display?.reasons);
  const confidence = asNumber(item.llm_confidence);
  const isRelationship = item.suggested_memory_type === "relationship";
  return (
    <article className={`memory-row ${item.sensitivity}`}>
      <div className="row-title">
        <strong>{zoneLabel(item.suggested_zone)} / {readableMemoryType(item.suggested_memory_type)}</strong>
        <span>{item.status}</span>
      </div>
      <p>{item.redacted_preview}</p>
      <small>{item.source}{item.source_title ? ` - ${item.source_title}` : ""}</small>
      <BadgeRow badges={[
        item.proposal_kind,
        item.sensitivity,
        ...tags,
        duplicateIds.length ? `${duplicateIds.length} duplicates` : null,
        conflictIds.length ? `${conflictIds.length} conflicts` : null,
        item.supersedes_memory_id ? "will supersede old memory" : null
      ]} />
      {riskWarnings.map((warning) => (
        <p className="warning" key={warning}>{warning}</p>
      ))}
      {item.human_reason && <small>{item.human_reason}</small>}
      {isRelationship && (
        <div className="notice inline-notice">
          This relationship stays protected. Agents need a {item.suggested_zone} grant before it can appear in context.
        </div>
      )}
      {item.semantic_summary && (
        <div className="display-card semantic-card">
          <div>
            <h3>Semantic Summary</h3>
            <p>{item.semantic_summary}</p>
          </div>
          <BadgeRow badges={[
            item.llm_relationship || "relationship n/a",
            `confidence ${confidence.toFixed(2)}`,
            item.needs_user_decision ? "needs decision" : "ready"
          ]} />
          {item.llm_reason && <small>{item.llm_reason}</small>}
          <div className="reason-list">
            {semanticEntities.slice(0, 6).map((entity) => <span key={entity}>{entity}</span>)}
            {semanticTriggers.slice(0, 6).map((trigger) => <span key={trigger}>trigger: {trigger}</span>)}
          </div>
        </div>
      )}
      {item.diff_summary && <div className="preview-box diff-preview">{item.diff_summary}</div>}
      {displayReasons.map((reason) => (
        <small key={reason}>{reason}</small>
      ))}
      <div className="actions">
        {needsRelationshipDecision ? (
          <>
            <button onClick={() => onApproveUpdate(item)} disabled={!item.supersedes_memory_id}>
              <Check size={16} />Approve Update
            </button>
            <button onClick={() => onApproveSeparate(item)}><FileText size={16} />Save Separate</button>
          </>
        ) : (
          <button onClick={() => onApprove(item)}><Check size={16} />Approve</button>
        )}
        <button onClick={() => onReject(item)}><X size={16} />Reject</button>
      </div>
    </article>
  );
}

function GrantApprovalDialog({
  grant,
  onApprove,
  onReject,
  onDismiss
}: {
  grant: Grant;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  onDismiss: () => void;
}) {
  const allowedZones = asArray(grant.allowed_zones);
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Memory access request">
      <section className={`grant-modal ${grant.confirmation_level}`}>
        <div className="modal-title">
          <KeyRound size={22} />
          <div>
            <h2>Memory Access Request</h2>
            <p>{grant.agent_id} wants short-lived memory access.</p>
          </div>
          <button className="icon-button" onClick={onDismiss} aria-label="Dismiss"><X size={16} /></button>
        </div>
        <div className="grant-summary">
          <div>
            <span>Project</span>
            <strong>{grant.project_id || "global"}</strong>
          </div>
          <div>
            <span>Zones</span>
            <strong>{allowedZones.map(zoneLabel).join(", ")}</strong>
          </div>
          <div>
            <span>Risk</span>
            <strong>{grant.confirmation_level}</strong>
          </div>
          <div>
            <span>Expires</span>
            <strong>{new Date(grant.expires_at).toLocaleTimeString()}</strong>
          </div>
        </div>
        <div className="preview-box">{grant.purpose}</div>
        <div className="reason-list">
          <span>Approve only if the task purpose matches the requested zones.</span>
          <span>The token is short-lived and scoped to this agent, task, zones, and project.</span>
        </div>
        <div className="modal-actions">
          <button onClick={() => onReject(grant.id)}><X size={16} />Deny</button>
          <button className="primary-action" onClick={() => onApprove(grant.id)}><Check size={16} />Approve and Compose</button>
        </div>
      </section>
    </div>
  );
}

const ALL_ZONES: MemoryZone[] = [
  "public_profile",
  "work_context",
  "personal_context",
  "sensitive_vault",
  "payment_reference"
];

const CAPTURE_SAMPLES = [
  {
    id: "project",
    label: "Project requirement",
    text: "Project requirement: long-term memory storage must use Postgres and pgvector. Agents may only read work context after a short-lived grant."
  },
  {
    id: "friend",
    label: "Friend relationship",
    text: "Alice is my close friend. We usually play basketball together on weekends."
  },
  {
    id: "commute",
    label: "Commute update",
    text: "I moved recently. I now live 3 km from the office."
  },
  {
    id: "payment",
    label: "Payment reference",
    text: "For travel booking, payment must always require my explicit confirmation. Never store raw card number or CVV."
  }
];

const ZONE_META: Record<MemoryZone, { label: string; description: string; risk: string }> = {
  public_profile: {
    label: "Public Profile",
    description: "Low-risk style and format preferences.",
    risk: "No grant"
  },
  work_context: {
    label: "Work Context",
    description: "Project facts, team decisions, requirements.",
    risk: "Grant required"
  },
  personal_context: {
    label: "Personal Context",
    description: "Travel, schedule, lifestyle preferences.",
    risk: "Grant required"
  },
  sensitive_vault: {
    label: "Sensitive Vault",
    description: "Redacted references and red-line rules.",
    risk: "High confirmation"
  },
  payment_reference: {
    label: "Payment Reference",
    description: "Payment confirmation rules, never raw card data.",
    risk: "High confirmation"
  }
};

function zoneLabel(zone?: MemoryZone | string | null) {
  if (!zone) return "Unzoned";
  return ZONE_META[zone as MemoryZone]?.label || String(zone).replace(/_/g, " ");
}

type ErrorBoundaryProps = {
  children: React.ReactNode;
};

type ErrorBoundaryState = {
  error: Error | null;
};

class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <main className="crash-shell">
          <section className="panel crash-panel">
            <div className="panel-title">
              <h2>Something went wrong in the desktop UI</h2>
              <button onClick={() => this.setState({ error: null })}><RefreshCw size={16} />Recover</button>
            </div>
            <p>{this.state.error.message}</p>
            <small>The backend process is still safe. This screen caught a render error instead of crashing the whole app.</small>
          </section>
        </main>
      );
    }
    return this.props.children;
  }
}

function App() {
  const client = useMemo(() => new ApiClient(), []);
  const [tab, setTab] = useState<"inbox" | "capture" | "memories" | "grants" | "compose" | "share" | "audit" | "settings">("capture");
  const [baseUrl, setBaseUrl] = useState(client.baseUrl);
  const [apiKey, setApiKey] = useState(client.apiKey);
  const [agentApiKey, setAgentApiKey] = useState(client.agentApiKey);
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectId, setActiveProjectId] = useState(client.projectId);
  const [newProjectId, setNewProjectId] = useState("");
  const [newProjectName, setNewProjectName] = useState("");
  const [clipboardText, setClipboardText] = useState("");
  const [analysis, setAnalysis] = useState<CaptureAnalysis | null>(null);
  const [ingestDisplay, setIngestDisplay] = useState<Display | null>(null);
  const [inbox, setInbox] = useState<InboxItem[]>([]);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [memoryStatusFilter, setMemoryStatusFilter] = useState("approved");
  const [memoryQuery, setMemoryQuery] = useState("");
  const [selectedMemory, setSelectedMemory] = useState<MemoryDetail | null>(null);
  const [memoryEditContent, setMemoryEditContent] = useState("");
  const [memorySupersedeContent, setMemorySupersedeContent] = useState("");
  const [extractionPreview, setExtractionPreview] = useState<ExtractionPreview | null>(null);
  const [grants, setGrants] = useState<Grant[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [profiles, setProfiles] = useState<ModelProfile[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(localStorage.getItem("pmf.modelProfileId"));
  const [approvedGrantToken, setApprovedGrantToken] = useState<string | null>(null);
  const [composeTask, setComposeTask] = useState("We need to choose long-term memory storage for the memory-gateway project.");
  const [composeZones, setComposeZones] = useState<MemoryZone[]>(["public_profile", "work_context"]);
  const [composeResult, setComposeResult] = useState<ContextComposeResponse | null>(null);
  const [sharePacks, setSharePacks] = useState<SharePack[]>([]);
  const [shareName, setShareName] = useState("Project onboarding share");
  const [shareDescription, setShareDescription] = useState("Scoped project context for a collaborator or agent.");
  const [shareRecipient, setShareRecipient] = useState("new collaborator");
  const [shareTask, setShareTask] = useState("Onboard me to this project.");
  const [shareTypes, setShareTypes] = useState<MemoryType[]>(["context", "relationship", "preference", "procedure", "lesson", "anti_pattern"]);
  const [shareTtlDays, setShareTtlDays] = useState(7);
  const [shareMaxUses, setShareMaxUses] = useState(20);
  const [sharePreview, setSharePreview] = useState<SharePackPreviewResponse | null>(null);
  const [createdShare, setCreatedShare] = useState<SharePackCreateResponse | null>(null);
  const [shareCompose, setShareCompose] = useState<SharePackComposeResponse | null>(null);
  const [shareTokenInput, setShareTokenInput] = useState("");
  const [sharePackIdInput, setSharePackIdInput] = useState("");
  const [pendingGrantAlert, setPendingGrantAlert] = useState<Grant | null>(null);
  const [grantContextPreview, setGrantContextPreview] = useState<ContextRequestStatusResponse | null>(null);
  const [seenPendingGrantIds, setSeenPendingGrantIds] = useState<Set<string>>(new Set());
  const seenPendingGrantIdsRef = useRef<Set<string>>(new Set());
  const [profileName, setProfileName] = useState("My model profile");
  const [profileProvider, setProfileProvider] = useState<ModelProfile["provider"]>("openai_compatible");
  const [profileBaseUrl, setProfileBaseUrl] = useState("https://api.openai.com");
  const [profileModel, setProfileModel] = useState("");
  const [profileApiKey, setProfileApiKey] = useState("");
  const [profileLocalOnly, setProfileLocalOnly] = useState(false);
  const [profileAutoApply, setProfileAutoApply] = useState(true);
  const [profileTestResult, setProfileTestResult] = useState<ModelProcessingResponse | null>(null);
  const [connectionOk, setConnectionOk] = useState<boolean | null>(null);
  const [status, setStatus] = useState("Ready");

  async function configureShortcuts() {
    try {
      const { register } = await import("@tauri-apps/plugin-global-shortcut");
      await register("CommandOrControl+Shift+M", async () => {
        setTab("capture");
        await loadClipboard();
      });
    } catch {
      // Browser preview keeps the same UI without global shortcut support.
    }
  }

  async function checkConnection() {
    try {
      await client.health();
      setConnectionOk(true);
      setStatus("Backend connected");
    } catch (error) {
      setConnectionOk(false);
      setStatus(error instanceof Error ? error.message : "Backend unavailable");
    }
  }

  async function seedBackend() {
    try {
      await client.seed();
      await Promise.all([loadProjects(), loadInbox(), loadProfiles(), loadSharePacks(), loadAudit()]);
      setStatus("Demo data seeded");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Seed failed");
    }
  }

  async function loadClipboard() {
    try {
      const text = await readClipboardText();
      setClipboardText(text);
      if (text.trim()) {
        setAnalysis(await client.analyzeCapture(text, selectedProfileId));
        setIngestDisplay(null);
        setStatus("Clipboard analyzed");
      } else {
        setAnalysis(null);
        setStatus("Clipboard is empty");
      }
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Failed to read clipboard");
    }
  }

  async function analyzeTypedText() {
    if (!clipboardText.trim()) {
      setStatus("Enter text before analysis");
      return;
    }
    try {
      setAnalysis(await client.analyzeCapture(clipboardText, selectedProfileId));
      setExtractionPreview(await client.extractionPreview(clipboardText));
      setIngestDisplay(null);
      setStatus("Analysis ready");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Analysis failed");
    }
  }

  async function ingestTypedText() {
    if (!clipboardText.trim()) {
      setStatus("Enter text before ingest");
      return;
    }
    try {
      const result = await client.ingest(clipboardText, selectedProfileId);
      setIngestDisplay(result.display || null);
      await Promise.all([loadInbox(), loadAudit()]);
      setStatus(result.auto_approved ? "Saved as approved memory" : "Sent to inbox review");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Ingest failed");
    }
  }

  async function loadInbox() {
    try {
      setInbox(asArray(await client.listInbox()));
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to load inbox";
      setStatus(message.includes("404") ? "Backend is running old code. Restart FastAPI on port 8010." : message);
    }
  }

  async function loadMemories(status = memoryStatusFilter, query = memoryQuery) {
    try {
      const result = await client.listMemories(status, query);
      const loaded = asArray(result.memories);
      setMemories(loaded);
      setStatus(`Loaded ${loaded.length} memories`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Failed to load memories");
    }
  }

  async function openMemory(memory: Memory) {
    try {
      const detail = await client.getMemory(memory.id);
      setSelectedMemory(detail);
      setMemoryEditContent(detail.memory.content);
      setMemorySupersedeContent("");
      setStatus("Memory detail loaded");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Failed to load memory");
    }
  }

  async function saveMemoryEdit() {
    if (!selectedMemory) return;
    try {
      const detail = await client.patchMemory(selectedMemory.memory.id, {
        content: memoryEditContent,
        reason: "Edited from desktop memory editor"
      });
      setSelectedMemory(detail);
      await loadMemories();
      setStatus("Memory edited");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Edit failed");
    }
  }

  async function supersedeSelectedMemory() {
    if (!selectedMemory || !memorySupersedeContent.trim()) return;
    try {
      const detail = await client.supersedeMemory(selectedMemory.memory.id, memorySupersedeContent);
      setSelectedMemory(detail);
      setMemorySupersedeContent("");
      await loadMemories();
      setStatus("Memory superseded");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Supersede failed");
    }
  }

  async function restoreSelectedMemory() {
    if (!selectedMemory) return;
    try {
      const detail = await client.restoreMemory(selectedMemory.memory.id);
      setSelectedMemory(detail);
      await loadMemories();
      setStatus("Memory restored");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Restore failed");
    }
  }

  async function deleteSelectedMemory() {
    if (!selectedMemory) return;
    try {
      await client.deleteMemory(selectedMemory.memory.id);
      const detail = await client.getMemory(selectedMemory.memory.id);
      setSelectedMemory(detail);
      await loadMemories(memoryStatusFilter, memoryQuery);
      setStatus("Memory deleted. It can still be restored from the deleted filter.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Delete failed");
    }
  }

  async function loadProjects() {
    try {
      const result = asArray(await client.listProjects());
      setProjects(result);
      if (result.length && !result.some((project) => project.id === activeProjectId)) {
        selectProject(result[0].id);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to load projects";
      setStatus(message.includes("404") ? "Backend is running old code. Restart FastAPI on port 8010." : message);
    }
  }

  function selectProject(projectId: string) {
    client.setProject(projectId);
    setActiveProjectId(projectId);
    setApprovedGrantToken(null);
    setComposeResult(null);
    setStatus(`Project set to ${projectId}`);
  }

  async function createProject() {
    const id = newProjectId.trim();
    const name = newProjectName.trim() || id;
    if (!id) {
      setStatus("Project id is required");
      return;
    }
    try {
      const project = await client.createProject(id, name);
      await loadProjects();
      selectProject(project.id);
      setNewProjectId("");
      setNewProjectName("");
      setStatus("Project created");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Project creation failed");
    }
  }

  async function approveInboxItem(item: InboxItem) {
    try {
      await client.approveInbox(item.id, item.suggested_zone, item.suggested_memory_type);
      await Promise.all([loadInbox(), loadMemories(), loadAudit()]);
      setStatus("Inbox item approved");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Approve failed");
    }
  }

  async function approveInboxUpdateItem(item: InboxItem) {
    if (!item.supersedes_memory_id) {
      setStatus("This update has no target memory to supersede");
      return;
    }
    try {
      await client.approveInboxUpdate(
        item.id,
        item.supersedes_memory_id,
        item.suggested_zone,
        item.suggested_memory_type
      );
      await Promise.all([loadInbox(), loadMemories(), loadAudit()]);
      setStatus("Update approved. Old memory was superseded.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Approve update failed");
    }
  }

  async function approveInboxSeparateItem(item: InboxItem) {
    try {
      await client.approveInboxSeparate(item.id, item.suggested_zone, item.suggested_memory_type);
      await Promise.all([loadInbox(), loadMemories(), loadAudit()]);
      setStatus("Saved as a separate memory");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Save separate failed");
    }
  }

  async function rejectInboxItem(item: InboxItem) {
    try {
      await client.rejectInbox(item.id);
      await Promise.all([loadInbox(), loadAudit()]);
      setStatus("Inbox item rejected");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Reject failed");
    }
  }

  async function loadGrants() {
    try {
      const pending = asArray(await client.getPendingGrants());
      setGrants(pending);
      const next = pending.find((grant) => !seenPendingGrantIdsRef.current.has(grant.id));
      if (next) {
        const updated = new Set([...seenPendingGrantIdsRef.current, next.id]);
        seenPendingGrantIdsRef.current = updated;
        setSeenPendingGrantIds(updated);
        setPendingGrantAlert(next);
        setTab("grants");
        setStatus(`New memory access request from ${next.agent_id}`);
        await bringAppToFront();
        await notifyGrantRequest(next);
      }
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Failed to load grants");
    }
  }

  async function loadSharePacks() {
    try {
      setSharePacks(asArray(await client.listSharePacks()));
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to load share packs";
      setStatus(message.includes("404") ? "Backend is running old code. Restart FastAPI on port 8010." : message);
    }
  }

  function toggleShareType(type: MemoryType) {
    setShareTypes((current) =>
      current.includes(type)
        ? current.filter((item) => item !== type)
        : [...current, type]
    );
  }

  async function previewSharePack() {
    try {
      const result = await client.previewSharePack(
        shareName,
        shareDescription,
        shareRecipient,
        shareTask,
        shareTypes
      );
      setSharePreview(result);
      setShareCompose(null);
      setStatus(`Share preview ready with ${asArray(result.source_cards).length} sources`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Share preview failed");
    }
  }

  async function createSharePack() {
    try {
      const result = await client.createSharePack(
        shareName,
        shareDescription,
        shareRecipient,
        shareTask,
        shareTypes,
        shareTtlDays,
        shareMaxUses
      );
      setCreatedShare(result);
      setSharePreview(null);
      setShareCompose(null);
      setSharePackIdInput(result.share_pack.id);
      setShareTokenInput(result.share_pack.token || "");
      await Promise.all([loadSharePacks(), loadAudit()]);
      setStatus("Share Pack created. Token is shown once.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Share Pack creation failed");
    }
  }

  async function composeSharePackPreview() {
    const id = sharePackIdInput.trim() || createdShare?.share_pack.id;
    const token = shareTokenInput.trim() || createdShare?.share_pack.token || "";
    if (!id || !token) {
      setStatus("Share pack id and token are required");
      return;
    }
    try {
      const result = await client.composeSharePack(id, token, shareTask);
      setShareCompose(result);
      await Promise.all([loadSharePacks(), loadAudit()]);
      setStatus(`Shared context composed with ${asArray(result.source_cards).length} sources`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Share Pack compose failed");
    }
  }

  async function revokeSharePack(id: string) {
    try {
      await client.revokeSharePack(id);
      await Promise.all([loadSharePacks(), loadAudit()]);
      setStatus("Share Pack revoked");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Share Pack revoke failed");
    }
  }

  async function requestGrant() {
    const privateZones = composeZones.filter((zone) => zone !== "public_profile");
    if (!privateZones.length) {
      setStatus("Selected zones do not need a grant");
      return;
    }
    try {
      await client.requestGrant(`compose-${Date.now()}`, `Compose context for: ${composeTask}`, privateZones);
      await loadGrants();
      setTab("grants");
      setStatus("Grant requested");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Grant request failed");
    }
  }

  async function requestContextFlow() {
    try {
      const result = await client.requestContext(composeTask, composeZones, approvedGrantToken);
      if (result.status === "ready" && result.context) {
        setComposeResult(result.context);
        setTab("compose");
        setStatus(`Context composed with ${asArray(result.context.source_cards).length} sources`);
        return;
      }
      if (result.grant) {
        await loadGrants();
        setTab("grants");
        setStatus(result.message || "Grant requested");
        return;
      }
      setStatus(result.message || "Context request finished");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Context request failed");
    }
  }

  async function approveGrant(id: string) {
    try {
      const approved = await client.approveGrant(id);
      if (approved.token) setApprovedGrantToken(approved.token);
      setPendingGrantAlert((current) => current?.id === id ? null : current);
      try {
        const context = await client.composeApprovedContext(id);
        setGrantContextPreview(context);
        if (context.context) setComposeResult(context.context);
      } catch {
        setGrantContextPreview(null);
      }
      await Promise.all([loadGrants(), loadAudit()]);
      setStatus("Grant approved and context composed");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Approve failed");
    }
  }

  async function revokeGrant(id: string) {
    try {
      await client.revokeGrant(id);
      setPendingGrantAlert((current) => current?.id === id ? null : current);
      await Promise.all([loadGrants(), loadAudit()]);
      setStatus("Grant revoked");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Revoke failed");
    }
  }

  async function composeContext() {
    try {
      const result = await client.composeContext(composeTask, composeZones, approvedGrantToken);
      setComposeResult(result);
      setTab("compose");
      setStatus(`Context composed with ${asArray(result.source_cards).length} sources`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Compose failed");
    }
  }

  async function loadAudit() {
    try {
      setAudit(asArray(await client.getAudit()));
    } catch {
      // Audit is secondary in the desktop flow.
    }
  }

  async function loadProfiles() {
    try {
      const result = asArray(await client.getModelProfiles());
      setProfiles(result);
      const active = result.find((profile) => profile.is_active);
      if (!selectedProfileId && active) {
        setSelectedProfileId(active.id);
      }
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Failed to load profiles");
    }
  }

  async function createProfile() {
    try {
      const allowedZones = profileLocalOnly
        ? ALL_ZONES
        : ["public_profile", "work_context", "personal_context"] as MemoryZone[];
      const profile = await client.createModelProfile({
        name: profileName,
        provider: profileProvider,
        model: profileProvider === "rule_only" ? "rules" : profileModel,
        endpoint_url: profileProvider === "rule_only" ? null : profileBaseUrl,
        api_key: profileApiKey || null,
        allowed_tasks: ["classify_capture", "summarize_memory", "extract_lesson", "extract_facts", "embed_memory"],
        allowed_zones: allowedZones,
        local_only: profileProvider === "ollama" || profileProvider === "rule_only" || profileLocalOnly,
        auto_apply_low_sensitivity: profileAutoApply,
        is_active: true
      });
      setSelectedProfileId(profile.id);
      localStorage.setItem("pmf.modelProfileId", profile.id);
      setProfileApiKey("");
      await loadProfiles();
      setStatus("Model profile saved and activated");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Profile save failed");
    }
  }

  async function activateProfile(id: string) {
    try {
      await client.activateModelProfile(id);
      setSelectedProfileId(id);
      localStorage.setItem("pmf.modelProfileId", id);
      await loadProfiles();
      setStatus("Profile activated");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Activation failed");
    }
  }

  async function testProfile(id: string) {
    try {
      setProfileTestResult(await client.testModelProfile(id, clipboardText || "I prefer concise technical context."));
      setStatus("Model profile tested");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Model test failed");
    }
  }

  function saveConfig() {
    client.setConfig(baseUrl, apiKey, agentApiKey);
    setStatus("Config saved");
  }

  function toggleZone(zone: MemoryZone) {
    setComposeZones((current) =>
      current.includes(zone)
        ? current.filter((item) => item !== zone)
        : [...current, zone]
    );
  }

  function useSampleCapture(sampleId = "project") {
    const sample = CAPTURE_SAMPLES.find((item) => item.id === sampleId) || CAPTURE_SAMPLES[0];
    setClipboardText(sample.text);
    setAnalysis(null);
    setExtractionPreview(null);
    setIngestDisplay(null);
    setTab("capture");
    setStatus(`${sample.label} sample loaded`);
  }

  function prepareComposeDemo() {
    setComposeTask("Choose the database and vector retrieval approach for the memory-gateway project.");
    setComposeZones(["public_profile", "work_context"]);
    setTab("compose");
    setStatus("Compose demo prepared. Request a grant or compose with public memory only.");
  }

  function prepareShareDemo() {
    setShareName("Memory Gateway onboarding pack");
    setShareDescription("Share approved project work context with a collaborator.");
    setShareRecipient("new teammate");
    setShareTask("What should I know before contributing to memory-gateway?");
    setShareTypes(["context", "relationship", "preference", "procedure", "lesson", "anti_pattern"]);
    setTab("share");
    setStatus("Share demo prepared. Preview before creating the token.");
  }

  useEffect(() => {
    configureShortcuts();
    checkConnection();
    loadProfiles();
    loadProjects();
    loadInbox();
    loadMemories();
    loadGrants();
    loadSharePacks();
    loadAudit();
    const timer = window.setInterval(() => {
      loadInbox();
      loadGrants();
    }, 5000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <main>
      <header className="topbar">
        <div className="brand">
          <Shield size={24} />
          <div>
            <h1>Personal Memory Firewall</h1>
            <p>Permissioned ingestion and prompt-ready context for agents</p>
          </div>
        </div>
        <div className="top-actions">
          <span className={`status-pill ${connectionOk ? "ok" : connectionOk === false ? "bad" : ""}`}>
            {connectionOk === null ? "Checking" : connectionOk ? "Backend online" : "Backend offline"}
          </span>
          <select value={activeProjectId} onChange={(event) => selectProject(event.target.value)} aria-label="Current project">
            {projects.map((project) => (
              <option value={project.id} key={project.id}>{project.name}</option>
            ))}
            {!projects.length && <option value={activeProjectId}>{activeProjectId}</option>}
          </select>
          <button onClick={() => useSampleCapture()}><Clipboard size={16} />Sample</button>
          <button onClick={prepareComposeDemo}><FileText size={16} />Compose</button>
          <button onClick={prepareShareDemo}><KeyRound size={16} />Share</button>
          <button onClick={() => setTab("settings")}><Settings size={16} />Settings</button>
        </div>
      </header>

      <nav className="tabs">
        <button className={tab === "inbox" ? "active" : ""} onClick={() => setTab("inbox")}><Inbox size={16} />Inbox</button>
        <button className={tab === "capture" ? "active" : ""} onClick={() => setTab("capture")}><Clipboard size={16} />Capture</button>
        <button className={tab === "memories" ? "active" : ""} onClick={() => setTab("memories")}><FileText size={16} />Memories</button>
        <button className={tab === "grants" ? "active" : ""} onClick={() => setTab("grants")}><KeyRound size={16} />Grants</button>
        <button className={tab === "compose" ? "active" : ""} onClick={() => setTab("compose")}><FileText size={16} />Compose</button>
        <button className={tab === "share" ? "active" : ""} onClick={() => setTab("share")}><KeyRound size={16} />Share</button>
        <button className={tab === "audit" ? "active" : ""} onClick={() => setTab("audit")}><Bell size={16} />Audit</button>
        <button className={tab === "settings" ? "active" : ""} onClick={() => setTab("settings")}><Settings size={16} />Settings</button>
      </nav>

      <section className="pane">
        {pendingGrantAlert && (
          <GrantApprovalDialog
            grant={pendingGrantAlert}
            onApprove={approveGrant}
            onReject={revokeGrant}
            onDismiss={() => setPendingGrantAlert(null)}
          />
        )}

        <div className="notice">
          {connectionOk === null ? "Checking backend" : connectionOk ? "Backend connected" : "Backend unavailable"} - {status}
        </div>
        <div className="notice inline-notice">
          Current project: {activeProjectId}. Work memories and grants are isolated to this project.
        </div>

        <div className="workflow">
          <article className={tab === "capture" ? "active" : ""} onClick={() => setTab("capture")}>
            <strong>1. Capture</strong>
            <span>Paste or copy text, then analyze and ingest it.</span>
          </article>
          <article className={tab === "inbox" ? "active" : ""} onClick={() => setTab("inbox")}>
            <strong>2. Review</strong>
            <span>Approve protected memories before agents can use them.</span>
          </article>
          <article className={tab === "grants" ? "active" : ""} onClick={() => setTab("grants")}>
            <strong>3. Grant</strong>
            <span>Open only the zones needed for a short time.</span>
          </article>
          <article className={tab === "compose" ? "active" : ""} onClick={() => setTab("compose")}>
            <strong>4. Compose</strong>
            <span>Return prompt-ready context with sources.</span>
          </article>
          <article className={tab === "share" ? "active" : ""} onClick={() => setTab("share")}>
            <strong>5. Share</strong>
            <span>Create revocable project onboarding packs.</span>
          </article>
        </div>

        {tab === "inbox" && (
          <div className="panel">
            <div className="panel-title">
              <h2>Review Inbox</h2>
              <div className="actions">
                <button onClick={seedBackend}><RefreshCw size={16} />Seed</button>
                <button onClick={loadInbox}><RefreshCw size={16} />Refresh</button>
              </div>
            </div>
            <div className="list">
              {inbox.map((item) => (
                <InboxCard
                  key={item.id}
                  item={item}
                  onApprove={approveInboxItem}
                  onApproveUpdate={approveInboxUpdateItem}
                  onApproveSeparate={approveInboxSeparateItem}
                  onReject={rejectInboxItem}
                />
              ))}
              {inbox.length === 0 && (
                <div className="empty-state">
                  <Inbox size={34} />
                  <strong>No pending reviews</strong>
                  <span>Ingest work or personal context first. Protected memories will appear here for approval.</span>
                  <button onClick={() => setTab("capture")}><Clipboard size={16} />Capture memory</button>
                </div>
              )}
            </div>
          </div>
        )}

        {tab === "capture" && (
          <div className="two-col">
            <section className="panel">
              <div className="panel-title">
                <h2>Capture</h2>
                <div className="actions">
                  <select onChange={(event) => useSampleCapture(event.target.value)} defaultValue="" aria-label="Capture sample">
                    <option value="" disabled>Sample</option>
                    {CAPTURE_SAMPLES.map((sample) => (
                      <option value={sample.id} key={sample.id}>{sample.label}</option>
                    ))}
                  </select>
                  <button onClick={loadClipboard}><Clipboard size={16} />Clipboard</button>
                  <button onClick={analyzeTypedText}><Search size={16} />Analyze</button>
                  <button onClick={ingestTypedText}><Save size={16} />Ingest</button>
                </div>
              </div>
              <textarea
                value={clipboardText}
                onChange={(event) => setClipboardText(event.target.value)}
                placeholder="Paste a project note, preference, meeting conclusion, or rule here. Example: Project requirement: use Postgres + pgvector for long-term memory storage."
              />
            </section>
            <section className="panel">
              <div className="panel-title"><h2>Classification</h2></div>
              <div className="analysis">
                <CaptureDecisionCards analysis={analysis} preview={extractionPreview} />
                <DisplayPanel display={ingestDisplay || analysis?.display || extractionPreview?.display} fallback="No backend decision yet." />
                {extractionPreview && (
                  <div className="display-card extraction-card">
                    <div>
                      <h3>Facts & Update Check</h3>
                      <p>{extractionPreview.relationship.human_reason}</p>
                    </div>
                    <BadgeRow badges={[
                      extractionPreview.relationship.proposal_kind,
                      readableMemoryType(extractionPreview.suggested_memory_type),
                      zoneLabel(extractionPreview.suggested_zone),
                      extractionPreview.sensitivity
                    ]} />
                    {extractionPreview.relationship.diff_summary && (
                      <div className="preview-box">{extractionPreview.relationship.diff_summary}</div>
                    )}
                    <div className="reason-list">
                      {asArray(extractionPreview.facts).map((fact) => (
                        <span key={`${fact.subject}-${fact.predicate}-${fact.object}`}>
                          {fact.subject} {fact.predicate} {fact.object}
                        </span>
                      ))}
                    </div>
                    {asArray(extractionPreview.candidate_matches).length > 0 && (
                      <div className="list flat-list">
                        {asArray(extractionPreview.candidate_matches).slice(0, 3).map((candidate) => (
                          <SemanticCandidateCard key={candidate.memory_id} candidate={candidate} />
                        ))}
                      </div>
                    )}
                  </div>
                )}
                {!analysis && !ingestDisplay && (
                  <div className="quick-actions">
                    <button onClick={() => useSampleCapture("friend")}><Clipboard size={16} />Friend sample</button>
                    <button onClick={() => useSampleCapture("project")}><Clipboard size={16} />Project sample</button>
                    <button onClick={loadClipboard}><Clipboard size={16} />Read clipboard</button>
                  </div>
                )}
              </div>
            </section>
          </div>
        )}

        {tab === "memories" && (
          <div className="two-col">
            <section className="panel">
              <div className="panel-title">
                <h2>Memory Editor</h2>
                <div className="actions">
                  <select value={memoryStatusFilter} onChange={(event) => setMemoryStatusFilter(event.target.value)} aria-label="Memory status">
                    <option value="approved">approved</option>
                    <option value="superseded">superseded</option>
                    <option value="deleted">deleted</option>
                    <option value="pending">pending</option>
                  </select>
                  <button onClick={() => loadMemories()}><RefreshCw size={16} />Refresh</button>
                </div>
              </div>
              <div className="form-grid">
                <label>
                  <span>Search</span>
                  <input value={memoryQuery} onChange={(event) => setMemoryQuery(event.target.value)} placeholder="keyword or tag" />
                </label>
                <button onClick={() => loadMemories()}><Search size={16} />Search Memories</button>
              </div>
              <div className="list">
                {memories.map((memory) => (
                  <MemoryEditorCard key={memory.id} memory={memory} onOpen={openMemory} />
                ))}
                {memories.length === 0 && <div className="empty">No memories match this filter.</div>}
              </div>
            </section>
            <section className="panel">
              <div className="panel-title">
                <h2>Memory Detail</h2>
                {selectedMemory && <small>{selectedMemory.memory.id}</small>}
              </div>
              {selectedMemory ? (
                <div className="analysis">
                  <BadgeRow badges={[
                    selectedMemory.memory.status || "approved",
                    selectedMemory.memory.memory_zone,
                    selectedMemory.memory.memory_type,
                    selectedMemory.memory.sensitivity
                  ]} />
                  <label className="form-grid">
                    <span>Edit content</span>
                    <textarea className="compact-textarea" value={memoryEditContent} onChange={(event) => setMemoryEditContent(event.target.value)} />
                  </label>
                  <div className="actions">
                    <button onClick={saveMemoryEdit}><Save size={16} />Save Edit</button>
                    <button onClick={restoreSelectedMemory}><RefreshCw size={16} />Restore</button>
                    <button onClick={deleteSelectedMemory}><X size={16} />Delete</button>
                  </div>
                  <label className="form-grid">
                    <span>Supersede with new content</span>
                    <textarea className="compact-textarea" value={memorySupersedeContent} onChange={(event) => setMemorySupersedeContent(event.target.value)} />
                  </label>
                  <button onClick={supersedeSelectedMemory}><X size={16} />Supersede Old Memory</button>
                  <h2>Facts</h2>
                  {selectedMemory.memory.semantic_summary && (
                    <>
                      <h2>Semantic Summary</h2>
                      <div className="display-card semantic-card">
                        <p>{selectedMemory.memory.semantic_summary}</p>
                        <BadgeRow badges={[
                          ...asArray(selectedMemory.memory.semantic_entities).slice(0, 8),
                          ...asArray(selectedMemory.memory.semantic_triggers).slice(0, 8).map((trigger) => `trigger: ${trigger}`)
                        ]} />
                      </div>
                    </>
                  )}
                  <div className="list flat-list">
                    {asArray(selectedMemory.facts).map((fact) => <FactResultCard key={fact.id} card={fact} />)}
                    {asArray(selectedMemory.facts).length === 0 && <div className="empty">No active facts.</div>}
                  </div>
                  <h2>Timeline</h2>
                  <div className="audit">
                    {asArray(selectedMemory.timeline).map((event) => (
                      <article key={event.id}>
                        <span>{new Date(event.created_at).toLocaleTimeString()}</span>
                        <strong>{event.event}</strong>
                        <small>{event.actor_agent_id}</small>
                      </article>
                    ))}
                    {asArray(selectedMemory.timeline).length === 0 && <div className="empty">No version events yet.</div>}
                  </div>
                </div>
              ) : (
                <div className="empty-state">
                  <FileText size={34} />
                  <strong>Select a memory</strong>
                  <span>Inspect facts, edit content, supersede stale memories, or restore old entries.</span>
                </div>
              )}
            </section>
          </div>
        )}

        {tab === "grants" && (
          <div className="panel">
            <div className="panel-title">
              <h2>Short-Lived Grants</h2>
              <button onClick={loadGrants}><RefreshCw size={16} />Refresh</button>
            </div>
            <div className="list">
              {approvedGrantToken && (
                <article className="grant normal">
                  <div>
                    <strong>Approved grant token held for this session</strong>
                    <p>Use Compose to retrieve protected zones.</p>
                  </div>
                </article>
              )}
              {grantContextPreview?.context && (
                <article className="memory-row low">
                  <strong>Approved context preview</strong>
                  <p>{grantContextPreview.message}</p>
                  <div className="prompt-box">{grantContextPreview.context.prompt_context}</div>
                  <button onClick={() => setTab("compose")}><FileText size={16} />Open in Compose</button>
                </article>
              )}
              {grants.map((grant) => (
                <article className={`grant ${grant.confirmation_level}`} key={grant.id}>
                  <div>
                    <strong>{grant.agent_id}</strong>
                    <p>{grant.purpose}</p>
                    <small>{grant.project_id || "global"} - {asArray(grant.allowed_zones).map(zoneLabel).join(", ")} - expires {new Date(grant.expires_at).toLocaleTimeString()}</small>
                  </div>
                  <div className="actions">
                    <button onClick={() => approveGrant(grant.id)}><Check size={16} />Approve and Compose</button>
                    <button onClick={() => revokeGrant(grant.id)}><X size={16} />Reject</button>
                  </div>
                </article>
              ))}
              {grants.length === 0 && <div className="empty">No pending grant requests.</div>}
            </div>
          </div>
        )}

        {tab === "compose" && (
          <div className="two-col">
            <section className="panel">
              <div className="panel-title">
                <h2>Agent Context Request</h2>
                <div className="actions">
                  <button onClick={requestContextFlow}><KeyRound size={16} />Request Context</button>
                  <button onClick={requestGrant}><KeyRound size={16} />Grant Only</button>
                  <button onClick={composeContext}><FileText size={16} />Compose</button>
                </div>
              </div>
              <div className="form-grid">
                <label>
                  <span>Task</span>
                  <textarea className="compact-textarea" value={composeTask} onChange={(event) => setComposeTask(event.target.value)} />
                </label>
                <div className="zone-grid">
                  {ALL_ZONES.map((zone) => (
                    <label className={`zone-option ${composeZones.includes(zone) ? "selected" : ""}`} key={zone}>
                      <input type="checkbox" checked={composeZones.includes(zone)} onChange={() => toggleZone(zone)} />
                      <span>
                        <strong>{ZONE_META[zone].label}</strong>
                        <small>{ZONE_META[zone].description}</small>
                      </span>
                      <em>{ZONE_META[zone].risk}</em>
                    </label>
                  ))}
                </div>
              </div>
            </section>
            <section className="panel">
              <div className="panel-title">
                <h2>Prompt Context</h2>
                {composeResult && <small>{composeResult.token_estimate} estimated tokens</small>}
              </div>
              {composeResult ? (
                <div className="analysis">
                  <div className="prompt-box">{composeResult.prompt_context}</div>
                  {asArray(composeResult.denied_zones).length > 0 && (
                    <div className="notice inline-notice">
                      {asArray(composeResult.denied_zones).map((zone) => `${zoneLabel(zone.zone)}: ${zone.reason}`).join(" - ")}
                    </div>
                  )}
                  <h2>Sources</h2>
                  <div className="list flat-list">
                    {asArray(composeResult.matched_summaries).map((candidate) => (
                      <SemanticCandidateCard key={candidate.memory_id} candidate={candidate} />
                    ))}
                    {asArray(composeResult.source_cards).map((card) => <MemoryResultCard key={card.id} card={card} />)}
                    {asArray(composeResult.fact_cards).map((card) => <FactResultCard key={card.id} card={card} />)}
                    {asArray(composeResult.source_cards).length === 0 && asArray(composeResult.fact_cards).length === 0 && (
                      <div className="empty-state">
                        <FileText size={34} />
                        <strong>No readable sources included</strong>
                        <span>Try Public Profile only, or request a grant for Work Context.</span>
                        <button onClick={requestContextFlow}><KeyRound size={16} />Request context</button>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="empty-state">
                  <FileText size={34} />
                  <strong>No context composed yet</strong>
                  <span>Choose zones, request a grant if needed, then compose the context package agents will receive.</span>
                  <button onClick={composeContext}><FileText size={16} />Compose now</button>
                </div>
              )}
            </section>
          </div>
        )}

        {tab === "share" && (
          <div className="two-col">
            <section className="panel">
              <div className="panel-title">
                <h2>Project Share Pack</h2>
                <div className="actions">
                  <button onClick={previewSharePack}><Search size={16} />Preview</button>
                  <button onClick={createSharePack}><Save size={16} />Create</button>
                  <button onClick={loadSharePacks}><RefreshCw size={16} />Refresh</button>
                </div>
              </div>
              <div className="form-grid">
                <label><span>Name</span><input value={shareName} onChange={(event) => setShareName(event.target.value)} /></label>
                <label><span>Description</span><input value={shareDescription} onChange={(event) => setShareDescription(event.target.value)} /></label>
                <label><span>Recipient</span><input value={shareRecipient} onChange={(event) => setShareRecipient(event.target.value)} /></label>
                <label>
                  <span>Onboarding task</span>
                  <textarea className="compact-textarea" value={shareTask} onChange={(event) => setShareTask(event.target.value)} />
                </label>
                <div className="decision-grid">
                  <article className="decision-card">
                    <span>Share Scope</span>
                    <strong>Work Context only</strong>
                    <p>Personal, sensitive, payment, private, deleted, and superseded memory is excluded by backend policy.</p>
                  </article>
                  <article className="decision-card">
                    <span>Token Policy</span>
                    <strong>Expiring and revocable</strong>
                    <p>The token is returned once, stored only as a hash, and can be revoked at any time.</p>
                  </article>
                </div>
                <div className="zone-grid">
                  {(["context", "relationship", "preference", "procedure", "lesson", "anti_pattern"] as MemoryType[]).map((type) => (
                    <label className={`zone-option ${shareTypes.includes(type) ? "selected" : ""}`} key={type}>
                      <input type="checkbox" checked={shareTypes.includes(type)} onChange={() => toggleShareType(type)} />
                      <span>
                        <strong>{readableMemoryType(type)}</strong>
                        <small>Allowed in project onboarding context</small>
                      </span>
                      <em>{shareTypes.includes(type) ? "included" : "excluded"}</em>
                    </label>
                  ))}
                </div>
                <div className="connection settings-connection compact-connection">
                  <label><span>TTL days</span><input type="number" min={1} max={90} value={shareTtlDays} onChange={(event) => setShareTtlDays(Number(event.target.value) || 7)} /></label>
                  <label><span>Max uses</span><input type="number" min={1} max={500} value={shareMaxUses} onChange={(event) => setShareMaxUses(Number(event.target.value) || 20)} /></label>
                </div>
              </div>
              {createdShare?.share_pack.token && (
                <div className="analysis">
                  <div className="display-card token-card">
                    <div>
                      <h3>Token returned once</h3>
                      <p>Give this token to the collaborator or agent together with the Share Pack id.</p>
                    </div>
                    <div className="preview-box">{createdShare.share_pack.token}</div>
                    <BadgeRow badges={[createdShare.share_pack.id, `${createdShare.share_pack.uses_remaining} uses left`]} />
                  </div>
                </div>
              )}
              <div className="list">
                {sharePacks.map((pack) => (
                  <SharePackCard key={pack.id} pack={pack} onRevoke={revokeSharePack} />
                ))}
                {sharePacks.length === 0 && <div className="empty">No Share Packs yet. Preview and create one for the current project.</div>}
              </div>
            </section>
            <section className="panel">
              <div className="panel-title">
                <h2>Preview & Recipient Compose</h2>
                <button onClick={composeSharePackPreview}><FileText size={16} />Use Token</button>
              </div>
              <div className="form-grid">
                <label><span>Share Pack id</span><input value={sharePackIdInput} onChange={(event) => setSharePackIdInput(event.target.value)} placeholder="sp_..." /></label>
                <label><span>Share token</span><input value={shareTokenInput} onChange={(event) => setShareTokenInput(event.target.value)} placeholder="sp_token returned once" /></label>
              </div>
              <div className="analysis">
                {sharePreview && (
                  <div className="display-card">
                    <div>
                      <h3>{sharePreview.display.title}</h3>
                      <p>{sharePreview.display.subtitle}</p>
                    </div>
                    <BadgeRow badges={["preview", `${sharePreview.token_estimate} tokens`, `${sharePreview.candidate_count_after_policy} candidates`]} />
                    <div className="prompt-box">{sharePreview.prompt_context}</div>
                    {asArray(sharePreview.excluded_summary).map((warning) => <p className="warning" key={warning}>{warning}</p>)}
                  </div>
                )}
                {shareCompose && (
                  <div className="display-card">
                    <div>
                      <h3>{shareCompose.display.title}</h3>
                      <p>{shareCompose.display.subtitle}</p>
                    </div>
                    <BadgeRow badges={[shareCompose.share_pack.status, `${shareCompose.share_pack.uses_remaining} uses left`, `${shareCompose.token_estimate} tokens`]} />
                    <div className="prompt-box">{shareCompose.prompt_context}</div>
                  </div>
                )}
                <h2>Included Sources</h2>
                <div className="list flat-list">
                  {asArray(shareCompose?.matched_summaries || sharePreview?.matched_summaries).map((candidate) => (
                    <SemanticCandidateCard key={candidate.memory_id} candidate={candidate} />
                  ))}
                  {asArray(shareCompose?.source_cards || sharePreview?.source_cards).map((card) => (
                    <MemoryResultCard key={card.id} card={card} />
                  ))}
                  {!sharePreview && !shareCompose && (
                    <div className="empty-state">
                      <KeyRound size={34} />
                      <strong>No share preview yet</strong>
                      <span>Preview the onboarding pack before creating a token, then test recipient compose here.</span>
                      <button onClick={previewSharePack}><Search size={16} />Preview Share Pack</button>
                    </div>
                  )}
                </div>
              </div>
            </section>
          </div>
        )}

        {tab === "audit" && (
          <div className="panel">
            <div className="panel-title">
              <h2>Audit Trail</h2>
              <button onClick={loadAudit}><RefreshCw size={16} />Refresh</button>
            </div>
            <div className="audit">
              {audit.map((event) => (
                <article key={event.id}>
                  <span>{new Date(event.created_at).toLocaleTimeString()}</span>
                  <strong>{event.action}</strong>
                  <small>{event.resource_type} {event.resource_id || ""}</small>
                </article>
              ))}
              {audit.length === 0 && <div className="empty">No audit events yet.</div>}
            </div>
          </div>
        )}

        {tab === "settings" && (
          <div className="dashboard">
            <section className="panel hero-panel">
              <div className="panel-title"><h2>Connection</h2></div>
              <div className="connection settings-connection">
                <input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} aria-label="Backend URL" />
                <input value={apiKey} onChange={(event) => setApiKey(event.target.value)} aria-label="User API key" />
                <input value={agentApiKey} onChange={(event) => setAgentApiKey(event.target.value)} aria-label="Agent API key" />
                <button onClick={saveConfig}><Settings size={16} />Save</button>
              </div>
            </section>
            <section className="panel hero-panel">
              <div className="panel-title">
                <h2>Projects</h2>
                <button onClick={loadProjects}><RefreshCw size={16} />Refresh</button>
              </div>
              <div className="connection settings-connection">
                <select value={activeProjectId} onChange={(event) => selectProject(event.target.value)} aria-label="Active project">
                  {projects.map((project) => (
                    <option value={project.id} key={project.id}>{project.name}</option>
                  ))}
                  {!projects.length && <option value={activeProjectId}>{activeProjectId}</option>}
                </select>
                <input value={newProjectId} onChange={(event) => setNewProjectId(event.target.value)} placeholder="project-id" />
                <input value={newProjectName} onChange={(event) => setNewProjectName(event.target.value)} placeholder="Project name" />
                <button onClick={createProject}><Save size={16} />Create</button>
              </div>
            </section>
            <div className="two-col">
              <section className="panel">
              <div className="panel-title"><h2>Model Profile</h2></div>
              <div className="form-grid">
                <label><span>Name</span><input value={profileName} onChange={(event) => setProfileName(event.target.value)} /></label>
                <label>
                  <span>Provider</span>
                  <select value={profileProvider} onChange={(event) => setProfileProvider(event.target.value as ModelProfile["provider"])}>
                    <option value="openai_compatible">OpenAI-compatible</option>
                    <option value="ollama">Ollama local</option>
                    <option value="rule_only">Rule-only</option>
                  </select>
                </label>
                <label><span>Base URL</span><input value={profileBaseUrl} onChange={(event) => setProfileBaseUrl(event.target.value)} /></label>
                <label><span>Model</span><input value={profileModel} onChange={(event) => setProfileModel(event.target.value)} /></label>
                <label><span>API Key</span><input type="password" value={profileApiKey} onChange={(event) => setProfileApiKey(event.target.value)} /></label>
                <label className="checkbox-row"><input type="checkbox" checked={profileLocalOnly} onChange={(event) => setProfileLocalOnly(event.target.checked)} /><span>Local only</span></label>
                <label className="checkbox-row"><input type="checkbox" checked={profileAutoApply} onChange={(event) => setProfileAutoApply(event.target.checked)} /><span>Auto-apply low-risk public suggestions</span></label>
                <button onClick={createProfile}><Save size={16} />Save Profile</button>
              </div>
              </section>
              <section className="panel">
              <div className="panel-title">
                <h2>Profiles</h2>
                <button onClick={loadProfiles}><RefreshCw size={16} />Refresh</button>
              </div>
              <div className="list">
                {profiles.map((profile) => (
                  <article className={`grant ${profile.local_only ? "normal" : "high"}`} key={profile.id}>
                    <div>
                      <strong>{profile.name}</strong>
                      <p>{profile.provider} - {profile.model}</p>
                      <small>{profile.is_active ? "active" : "inactive"} - key {profile.has_api_key ? "configured" : "not stored"}</small>
                    </div>
                    <div className="actions">
                      <button onClick={() => activateProfile(profile.id)} disabled={profile.id === selectedProfileId}><Check size={16} />Use</button>
                      <button onClick={() => testProfile(profile.id)}><Search size={16} />Test</button>
                    </div>
                  </article>
                ))}
              </div>
              <div className="test-result">
                <DisplayPanel display={profileTestResult?.display} fallback="Test a profile to see whether model processing was called and whether redacted preview was used." />
              </div>
              </section>
            </div>
          </div>
        )}
      </section>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>
);
