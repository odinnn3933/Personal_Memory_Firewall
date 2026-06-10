from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from memory_gateway.api.deps import CurrentAgent, DbSession
from memory_gateway.config import get_settings
from memory_gateway.db import FeedbackEventRecord, init_db
from memory_gateway.schemas import (
    AuditOut,
    CaptureAnalyzeRequest,
    CaptureAnalyzeResponse,
    CaptureCommitRequest,
    CaptureCommitResponse,
    ContextComposeRequest,
    ContextComposeResponse,
    ContextRequestRequest,
    ContextRequestResponse,
    ContextRequestStatusResponse,
    ExplainResponse,
    ExtractionPreviewRequest,
    ExtractionPreviewResponse,
    ExtractLessonsRequest,
    FeedbackOut,
    FeedbackRequest,
    GrantApprovalRequest,
    GraphExplainResponse,
    GraphHealthResponse,
    GraphRebuildResponse,
    GraphSearchRequest,
    GraphSearchResponse,
    GrantOut,
    GrantRequest,
    InboxApproveRequest,
    InboxItemOut,
    InboxMergeRequest,
    InboxRejectRequest,
    IngestRequest,
    IngestResponse,
    InteractionRequest,
    MemoryDetailResponse,
    MemoryListResponse,
    MemoryPatchRequest,
    MemoryProposalRequest,
    MemoryRestoreRequest,
    MemorySupersedeRequest,
    ModelProcessingClassifyRequest,
    ModelProcessingLessonRequest,
    ModelProcessingResponse,
    ModelProcessingSummarizeRequest,
    ModelProfileCreateRequest,
    ModelProfileOut,
    ModelProfileTestRequest,
    ProposalOut,
    ProjectCreateRequest,
    ProjectOut,
    SearchRequest,
    SearchResponse,
    DecisionExampleOut,
    SemanticJudgeRequest,
    SemanticJudgeResponse,
    SharePackComposeRequest,
    SharePackComposeResponse,
    SharePackCreateRequest,
    SharePackCreateResponse,
    SharePackOut,
    SharePackPreviewRequest,
    SharePackPreviewResponse,
    SemanticSummarizeRequest,
    SemanticSummaryOut,
    SummaryRebuildResponse,
    VaultSearchRequest,
    ZoneOut,
)
from memory_gateway.runtime.projects import create_project, list_projects
from memory_gateway.runtime.context import (
    compose_approved_context_request,
    compose_context,
    request_context,
)
from memory_gateway.runtime.ingestion import (
    approve_inbox_separate,
    approve_inbox_update,
    approve_inbox_item,
    ingest_memory,
    list_inbox_items,
    merge_inbox_item,
    preview_extraction,
    reject_inbox_item,
)
from memory_gateway.runtime.memories import (
    list_memories_for_editor,
    memory_detail,
    memory_timeline,
    patch_memory,
    restore_memory,
    supersede_memory,
)
from memory_gateway.runtime.semantic import (
    generate_memory_summary,
    judge_memory_relationship,
    list_decision_examples,
    rebuild_missing_summaries,
    retrieve_summary_candidates,
    similar_decision_examples,
)
from memory_gateway.runtime.share import (
    compose_share_pack,
    create_share_pack,
    list_share_packs,
    preview_share_pack,
    revoke_share_pack,
)
from memory_gateway.service import (
    InvalidState,
    NotFound,
    PermissionDenied,
    analyze_capture,
    approve_access_grant,
    approve_learning_proposal,
    approve_memory_write_proposal,
    activate_model_profile,
    commit_capture,
    create_model_profile,
    create_memory_proposal,
    delete_memory,
    explain_memory,
    extract_lessons,
    get_access_grant,
    graph_explain,
    graph_health,
    graph_rebuild,
    graph_search,
    classify_capture_with_model,
    extract_lesson_with_model,
    list_access_grants,
    list_model_profiles,
    list_recent_audit_events,
    list_zones,
    list_learning_proposals,
    record_interaction,
    request_access_grant,
    revoke_access_grant,
    search_memories,
    seed_demo_data,
    summarize_memory_with_model,
    submit_feedback,
    test_model_profile,
    vault_search,
)
from memory_gateway.types import GrantStatus, InboxStatus, MemoryType, MemoryZone, ProposalStatus, SharePackStatus


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Personal Memory Firewall for AI Agents",
    version="0.1.0",
    description="User-controlled, auditable memory firewall with BYOM processing.",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list(),
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _map_service_error(error: Exception) -> HTTPException:
    if isinstance(error, PermissionDenied):
        return HTTPException(status_code=403, detail=str(error))
    if isinstance(error, NotFound):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, InvalidState):
        return HTTPException(status_code=409, detail=str(error))
    return HTTPException(status_code=500, detail=str(error))


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/admin/seed")
def seed_demo(session: DbSession, agent: CurrentAgent) -> dict[str, str]:
    if not agent.is_admin:
        raise HTTPException(status_code=403, detail="only admin agents can seed")
    seed_demo_data(session)
    session.commit()
    return {"status": "seeded"}


@app.post("/v1/interactions")
def create_interaction(
    request: InteractionRequest, session: DbSession, agent: CurrentAgent
) -> dict[str, str]:
    event_id = record_interaction(session, agent, request)
    session.commit()
    return {"id": event_id}


@app.post("/v1/memories/search", response_model=SearchResponse)
def search(request: SearchRequest, session: DbSession, agent: CurrentAgent) -> SearchResponse:
    result = search_memories(session, agent, request)
    session.commit()
    return SearchResponse(
        memories=result.memories,
        candidate_count_after_acl=result.candidate_count_after_acl,
        audit_id=result.audit_id,
        display=result.display,
    )


@app.get("/v1/zones", response_model=list[ZoneOut])
def zones() -> list[ZoneOut]:
    return list_zones()


@app.get("/v1/projects", response_model=list[ProjectOut])
def projects(session: DbSession, agent: CurrentAgent) -> list[ProjectOut]:
    try:
        return list_projects(session, agent)
    except Exception as error:
        raise _map_service_error(error) from error


@app.post("/v1/projects", response_model=ProjectOut)
def project_create(
    request: ProjectCreateRequest,
    session: DbSession,
    agent: CurrentAgent,
) -> ProjectOut:
    try:
        response = create_project(session, agent, request)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/ingest", response_model=IngestResponse)
def ingest(request: IngestRequest, session: DbSession, agent: CurrentAgent) -> IngestResponse:
    try:
        response = ingest_memory(session, agent, request)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/extraction/preview", response_model=ExtractionPreviewResponse)
def extraction_preview(
    request: ExtractionPreviewRequest,
    session: DbSession,
    agent: CurrentAgent,
) -> ExtractionPreviewResponse:
    try:
        response = preview_extraction(session, agent, request)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/semantic/summarize", response_model=SemanticSummaryOut)
def semantic_summarize(
    request: SemanticSummarizeRequest,
    session: DbSession,
    agent: CurrentAgent,
) -> SemanticSummaryOut:
    try:
        response = generate_memory_summary(
            session,
            agent,
            request.content,
            request.project_id,
            request.memory_zone,
            request.model_profile_id,
        )
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/semantic/judge", response_model=SemanticJudgeResponse)
def semantic_judge(
    request: SemanticJudgeRequest,
    session: DbSession,
    agent: CurrentAgent,
) -> SemanticJudgeResponse:
    try:
        semantic = generate_memory_summary(
            session,
            agent,
            request.content,
            request.project_id,
            request.memory_zone,
            request.model_profile_id,
        )
        candidates = retrieve_summary_candidates(
            session,
            agent,
            semantic,
            request.project_id,
            request.memory_zone,
            request.top_k,
        )
        examples = similar_decision_examples(
            session,
            agent,
            semantic.summary,
            request.project_id,
            request.memory_zone,
        )
        judgment = judge_memory_relationship(
            session,
            agent,
            semantic,
            candidates,
            examples,
            request.model_profile_id,
        )
        session.commit()
        return SemanticJudgeResponse(semantic=semantic, candidates=candidates, judgment=judgment)
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/summaries/rebuild", response_model=SummaryRebuildResponse)
def summaries_rebuild(
    session: DbSession,
    agent: CurrentAgent,
    model_profile_id: str | None = None,
) -> SummaryRebuildResponse:
    try:
        rebuilt, failed, audit_id = rebuild_missing_summaries(
            session,
            agent,
            model_profile_id=model_profile_id,
        )
        session.commit()
        return SummaryRebuildResponse(rebuilt_count=rebuilt, failed_count=failed, audit_id=audit_id)
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.get("/v1/decision-examples", response_model=list[DecisionExampleOut])
def decision_examples(
    session: DbSession,
    agent: CurrentAgent,
    project_id: str | None = None,
    zone: MemoryZone | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[DecisionExampleOut]:
    try:
        return list_decision_examples(session, agent, project_id=project_id, zone=zone, limit=limit)
    except Exception as error:
        raise _map_service_error(error) from error


@app.get("/v1/inbox", response_model=list[InboxItemOut])
def inbox_items(
    session: DbSession,
    agent: CurrentAgent,
    status: InboxStatus = Query(default=InboxStatus.PENDING_REVIEW),
) -> list[InboxItemOut]:
    try:
        return list_inbox_items(session, agent, status)
    except Exception as error:
        raise _map_service_error(error) from error


@app.post("/v1/inbox/{inbox_id}/approve", response_model=InboxItemOut)
def inbox_approve(
    inbox_id: str,
    request: InboxApproveRequest,
    session: DbSession,
    agent: CurrentAgent,
) -> InboxItemOut:
    try:
        response = approve_inbox_item(session, agent, inbox_id, request)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/inbox/{inbox_id}/approve-update", response_model=InboxItemOut)
def inbox_approve_update(
    inbox_id: str,
    request: InboxApproveRequest,
    session: DbSession,
    agent: CurrentAgent,
) -> InboxItemOut:
    try:
        response = approve_inbox_update(session, agent, inbox_id, request)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/inbox/{inbox_id}/approve-separate", response_model=InboxItemOut)
def inbox_approve_separate(
    inbox_id: str,
    request: InboxApproveRequest,
    session: DbSession,
    agent: CurrentAgent,
) -> InboxItemOut:
    try:
        response = approve_inbox_separate(session, agent, inbox_id, request)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/inbox/{inbox_id}/reject", response_model=InboxItemOut)
def inbox_reject(
    inbox_id: str,
    request: InboxRejectRequest,
    session: DbSession,
    agent: CurrentAgent,
) -> InboxItemOut:
    try:
        response = reject_inbox_item(session, agent, inbox_id, request)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/inbox/{inbox_id}/merge", response_model=InboxItemOut)
def inbox_merge(
    inbox_id: str,
    request: InboxMergeRequest,
    session: DbSession,
    agent: CurrentAgent,
) -> InboxItemOut:
    try:
        response = merge_inbox_item(session, agent, inbox_id, request)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/context/compose", response_model=ContextComposeResponse)
def context_compose(
    request: ContextComposeRequest,
    session: DbSession,
    agent: CurrentAgent,
) -> ContextComposeResponse:
    try:
        response = compose_context(session, agent, request)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/context/request", response_model=ContextRequestResponse)
def context_request(
    request: ContextRequestRequest,
    session: DbSession,
    agent: CurrentAgent,
) -> ContextRequestResponse:
    try:
        response = request_context(session, agent, request)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.get("/v1/context/requests/{grant_id}", response_model=ContextRequestStatusResponse)
def context_request_status(
    grant_id: str,
    session: DbSession,
    agent: CurrentAgent,
) -> ContextRequestStatusResponse:
    try:
        response = compose_approved_context_request(session, agent, grant_id)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/context/requests/{grant_id}/compose", response_model=ContextRequestStatusResponse)
def context_request_compose(
    grant_id: str,
    session: DbSession,
    agent: CurrentAgent,
) -> ContextRequestStatusResponse:
    try:
        response = compose_approved_context_request(session, agent, grant_id)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/share-packs/preview", response_model=SharePackPreviewResponse)
def share_pack_preview(
    request: SharePackPreviewRequest,
    session: DbSession,
    agent: CurrentAgent,
) -> SharePackPreviewResponse:
    try:
        response = preview_share_pack(session, agent, request)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/share-packs", response_model=SharePackCreateResponse)
def share_pack_create(
    request: SharePackCreateRequest,
    session: DbSession,
    agent: CurrentAgent,
) -> SharePackCreateResponse:
    try:
        response = create_share_pack(session, agent, request)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.get("/v1/share-packs", response_model=list[SharePackOut])
def share_pack_list(
    session: DbSession,
    agent: CurrentAgent,
    status: SharePackStatus | None = Query(default=None),
) -> list[SharePackOut]:
    try:
        response = list_share_packs(session, agent, status)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/share-packs/{share_pack_id}/compose", response_model=SharePackComposeResponse)
def share_pack_compose(
    share_pack_id: str,
    request: SharePackComposeRequest,
    session: DbSession,
    agent: CurrentAgent,
) -> SharePackComposeResponse:
    try:
        response = compose_share_pack(session, agent, share_pack_id, request)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/share-packs/{share_pack_id}/revoke", response_model=SharePackOut)
def share_pack_revoke(
    share_pack_id: str,
    session: DbSession,
    agent: CurrentAgent,
) -> SharePackOut:
    try:
        response = revoke_share_pack(session, agent, share_pack_id)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/captures/analyze", response_model=CaptureAnalyzeResponse)
def capture_analyze(
    request: CaptureAnalyzeRequest, session: DbSession, agent: CurrentAgent
) -> CaptureAnalyzeResponse:
    response = analyze_capture(session, agent, request)
    session.commit()
    return response


@app.post("/v1/captures/commit", response_model=CaptureCommitResponse)
def capture_commit(
    request: CaptureCommitRequest, session: DbSession, agent: CurrentAgent
) -> CaptureCommitResponse:
    try:
        response = commit_capture(session, agent, request)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/vault/search", response_model=SearchResponse)
def search_vault(
    request: VaultSearchRequest, session: DbSession, agent: CurrentAgent
) -> SearchResponse:
    try:
        result = vault_search(session, agent, request)
        session.commit()
        return SearchResponse(
            memories=result.memories,
            candidate_count_after_acl=result.candidate_count_after_acl,
            audit_id=result.audit_id,
            display=result.display,
        )
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.get("/v1/graph/health", response_model=GraphHealthResponse)
def graph_status() -> GraphHealthResponse:
    return graph_health()


@app.post("/v1/graph/search", response_model=GraphSearchResponse)
def search_graph(
    request: GraphSearchRequest, session: DbSession, agent: CurrentAgent
) -> GraphSearchResponse:
    try:
        response = graph_search(session, agent, request)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.get("/v1/graph/entities/{entity_id}/explain", response_model=GraphExplainResponse)
def explain_graph_entity(
    entity_id: str,
    session: DbSession,
    agent: CurrentAgent,
    project_id: str | None = None,
    grant_token: str | None = None,
    zones: list[MemoryZone] = Query(default=[MemoryZone.PUBLIC_PROFILE]),
) -> GraphExplainResponse:
    try:
        response = graph_explain(session, agent, entity_id, project_id, zones, grant_token)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/graph/rebuild", response_model=GraphRebuildResponse)
def rebuild_graph(session: DbSession, agent: CurrentAgent) -> GraphRebuildResponse:
    try:
        response = graph_rebuild(session, agent)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/memories/proposals", response_model=ProposalOut)
def create_proposal(
    request: MemoryProposalRequest, session: DbSession, agent: CurrentAgent
) -> ProposalOut:
    try:
        proposal = create_memory_proposal(session, agent, request)
        session.commit()
        return proposal
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.get("/v1/memories", response_model=MemoryListResponse)
def list_memories(
    session: DbSession,
    agent: CurrentAgent,
    project_id: str | None = None,
    zone: MemoryZone | None = None,
    memory_type: str | None = None,
    status: str | None = None,
    query: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> MemoryListResponse:
    try:
        response = list_memories_for_editor(
            session,
            agent,
            project_id=project_id,
            zone=zone,
            memory_type=MemoryType(memory_type) if memory_type else None,
            status=status,
            query=query,
            limit=limit,
        )
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.get("/v1/memories/{memory_id}", response_model=MemoryDetailResponse)
def memory_get(memory_id: str, session: DbSession, agent: CurrentAgent) -> MemoryDetailResponse:
    try:
        response = memory_detail(session, agent, memory_id)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.patch("/v1/memories/{memory_id}", response_model=MemoryDetailResponse)
def memory_patch(
    memory_id: str,
    request: MemoryPatchRequest,
    session: DbSession,
    agent: CurrentAgent,
) -> MemoryDetailResponse:
    try:
        response = patch_memory(session, agent, memory_id, request)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/memories/{memory_id}/supersede", response_model=MemoryDetailResponse)
def memory_supersede(
    memory_id: str,
    request: MemorySupersedeRequest,
    session: DbSession,
    agent: CurrentAgent,
) -> MemoryDetailResponse:
    try:
        response = supersede_memory(session, agent, memory_id, request)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/memories/{memory_id}/restore", response_model=MemoryDetailResponse)
def memory_restore(
    memory_id: str,
    request: MemoryRestoreRequest,
    session: DbSession,
    agent: CurrentAgent,
) -> MemoryDetailResponse:
    try:
        response = restore_memory(session, agent, memory_id, request)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.get("/v1/memories/{memory_id}/timeline")
def memory_get_timeline(memory_id: str, session: DbSession, agent: CurrentAgent):
    try:
        response = memory_timeline(session, agent, memory_id)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/memories/proposals/{proposal_id}/approve", response_model=ProposalOut)
def approve_memory_proposal(
    proposal_id: str, session: DbSession, agent: CurrentAgent
) -> ProposalOut:
    try:
        proposal = approve_memory_write_proposal(session, agent, proposal_id)
        session.commit()
        return proposal
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/grants/request", response_model=GrantOut)
def grant_request(
    request: GrantRequest, session: DbSession, agent: CurrentAgent
) -> GrantOut:
    try:
        response = request_access_grant(session, agent, request)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.get("/v1/grants", response_model=list[GrantOut])
def grants(
    session: DbSession,
    agent: CurrentAgent,
    status: GrantStatus | None = Query(default=GrantStatus.PENDING),
) -> list[GrantOut]:
    try:
        return list_access_grants(session, agent, status)
    except Exception as error:
        raise _map_service_error(error) from error


@app.get("/v1/grants/{grant_id}", response_model=GrantOut)
def grant_detail(grant_id: str, session: DbSession, agent: CurrentAgent) -> GrantOut:
    try:
        response = get_access_grant(session, agent, grant_id)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/grants/{grant_id}/approve", response_model=GrantOut)
def grant_approve(
    grant_id: str,
    request: GrantApprovalRequest,
    session: DbSession,
    agent: CurrentAgent,
) -> GrantOut:
    try:
        response = approve_access_grant(session, agent, grant_id, request.ttl_minutes)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/grants/{grant_id}/revoke", response_model=GrantOut)
def grant_revoke(grant_id: str, session: DbSession, agent: CurrentAgent) -> GrantOut:
    try:
        response = revoke_access_grant(session, agent, grant_id)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.get("/v1/audit", response_model=list[AuditOut])
def audit_events(
    session: DbSession,
    agent: CurrentAgent,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[AuditOut]:
    try:
        return list_recent_audit_events(session, agent, limit)
    except Exception as error:
        raise _map_service_error(error) from error


@app.get("/v1/model-profiles", response_model=list[ModelProfileOut])
def model_profiles(session: DbSession, agent: CurrentAgent) -> list[ModelProfileOut]:
    return list_model_profiles(session, agent)


@app.post("/v1/model-profiles", response_model=ModelProfileOut)
def model_profile_create(
    request: ModelProfileCreateRequest, session: DbSession, agent: CurrentAgent
) -> ModelProfileOut:
    try:
        response = create_model_profile(session, agent, request)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/model-profiles/{profile_id}/activate", response_model=ModelProfileOut)
def model_profile_activate(profile_id: str, session: DbSession, agent: CurrentAgent) -> ModelProfileOut:
    try:
        response = activate_model_profile(session, agent, profile_id)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/model-profiles/{profile_id}/test", response_model=ModelProcessingResponse)
def model_profile_test(
    profile_id: str,
    request: ModelProfileTestRequest,
    session: DbSession,
    agent: CurrentAgent,
) -> ModelProcessingResponse:
    try:
        response = test_model_profile(session, agent, profile_id, request)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/model-processing/classify", response_model=ModelProcessingResponse)
def model_processing_classify(
    request: ModelProcessingClassifyRequest,
    session: DbSession,
    agent: CurrentAgent,
) -> ModelProcessingResponse:
    try:
        response = classify_capture_with_model(session, agent, request)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/model-processing/summarize", response_model=ModelProcessingResponse)
def model_processing_summarize(
    request: ModelProcessingSummarizeRequest,
    session: DbSession,
    agent: CurrentAgent,
) -> ModelProcessingResponse:
    try:
        response = summarize_memory_with_model(session, agent, request)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/model-processing/extract-lesson", response_model=ModelProcessingResponse)
def model_processing_lesson(
    request: ModelProcessingLessonRequest,
    session: DbSession,
    agent: CurrentAgent,
) -> ModelProcessingResponse:
    try:
        response = extract_lesson_with_model(session, agent, request)
        session.commit()
        return response
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/feedback", response_model=FeedbackOut)
def feedback(request: FeedbackRequest, session: DbSession, agent: CurrentAgent) -> FeedbackOut:
    event = submit_feedback(session, agent, request)
    session.commit()
    return FeedbackOut(
        id=event.id,
        task_id=event.task_id,
        rating=event.rating,
        correction=event.correction,
        expected_behavior=event.expected_behavior,
        error_type=event.error_type,
        project_id=event.project_id,
    )


@app.post("/v1/learning/extract", response_model=list[ProposalOut])
def learning_extract(
    request: ExtractLessonsRequest, session: DbSession, agent: CurrentAgent
) -> list[ProposalOut]:
    try:
        proposals = extract_lessons(session, agent, request.feedback_id)
        session.commit()
        return proposals
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.get("/v1/learning/proposals", response_model=list[ProposalOut])
def learning_proposals(
    session: DbSession,
    agent: CurrentAgent,
    status: ProposalStatus = Query(default=ProposalStatus.PENDING),
) -> list[ProposalOut]:
    try:
        return list_learning_proposals(session, agent, status)
    except Exception as error:
        raise _map_service_error(error) from error


@app.post("/v1/learning/proposals/{proposal_id}/approve", response_model=ProposalOut)
def approve_lesson(
    proposal_id: str, session: DbSession, agent: CurrentAgent
) -> ProposalOut:
    try:
        proposal = approve_learning_proposal(session, agent, proposal_id)
        session.commit()
        return proposal
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.post("/v1/memories/{memory_id}/delete")
def remove_memory(memory_id: str, session: DbSession, agent: CurrentAgent) -> dict[str, str]:
    try:
        delete_memory(session, agent, memory_id)
        session.commit()
        return {"status": "deleted"}
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


@app.get("/v1/memories/{memory_id}/explain", response_model=ExplainResponse)
def explain(
    memory_id: str,
    session: DbSession,
    agent: CurrentAgent,
    project_id: str | None = None,
) -> ExplainResponse:
    try:
        allowed, reason, details, audit_id = explain_memory(session, agent, memory_id, project_id)
        session.commit()
        return ExplainResponse(
            memory_id=memory_id,
            allowed=allowed,
            reason=reason,
            details=details,
            audit_id=audit_id,
        )
    except Exception as error:
        session.rollback()
        raise _map_service_error(error) from error


if __name__ == "__main__":
    uvicorn.run("memory_gateway.api.main:app", host="0.0.0.0", port=8000, reload=False)
