# Tool Contract

The Personal Memory Firewall MCP server is named `personal-memory-firewall`.

## Discovery

- `memory_list_zones(api_key?, base_url?)`
  - Returns memory zones, risk level, grant requirements, and default TTL.

- `memory_list_projects(api_key?, base_url?)`
  - Returns projects visible to the current agent.
  - Use this to pick the current project before requesting `work_context`.

## Retrieval

- `memory_request_context(task, zones, grant_token?, project_id?, task_id?, purpose?, memory_types?, max_tokens?, include_graph?, top_k?, ttl_minutes?, api_key?, base_url?)`
  - Preferred agent entry point.
  - Returns prompt-ready context immediately when only public zones are needed or a valid grant token is supplied.
  - Returns a pending grant request when protected zones require user approval.

- `memory_compose_context(task, zones, grant_token?, project_id?, memory_types?, max_tokens?, include_graph?, top_k?, api_key?, base_url?)`
  - Direct compose tool for public-only tasks or when a valid grant token is already available.
  - Returns `prompt_context`, grouped sections, source cards, structured fact cards, optional graph cards, denied zones, and audit id.
  - Normal agents should start with `memory_request_context` so protected zones trigger the desktop approval flow.

- `memory_get_context_request(grant_id, api_key?, base_url?)`
  - Poll a pending context request.
  - Returns `status=ready` and `prompt_context` after desktop approval.

- `memory_compose_approved_context(grant_id, api_key?, base_url?)`
  - Compose prompt-ready context from an approved request without exposing the raw grant token to the agent.

## Project Share Packs

- `memory_preview_share_pack(project_id?, name?, recipient_label?, task?, allowed_memory_types?, max_tokens?, top_k?, api_key?, base_url?)`
  - Preview the project onboarding context before creating a share token.
  - Share Packs are limited to approved project-scoped `work_context`.

- `memory_create_share_pack(project_id?, name?, recipient_label?, task?, allowed_memory_types?, ttl_days?, max_uses?, api_key?, base_url?)`
  - Create a revocable and expiring project onboarding token.
  - The raw token is returned once; store it outside memory.

- `memory_compose_share_pack(share_pack_id, share_token, task?, max_tokens?, top_k?, api_key?, base_url?)`
  - Recipient/collaborator path. Returns prompt-ready project context from the Share Pack scope.
  - Does not grant access to personal, sensitive, payment, private, deleted, or superseded memories.

- `memory_list_share_packs(status?, api_key?, base_url?)`
  - User/admin review of active, revoked, or expired Share Packs.

- `memory_revoke_share_pack(share_pack_id, api_key?, base_url?)`
  - Revoke a Share Pack so the token can no longer compose context.

- `memory_graph_health(api_key?, base_url?)`
  - Checks whether the Neo4j graph layer is available.

- `memory_graph_search(query, zones, grant_token?, project_id?, top_k?, api_key?, base_url?)`
  - Returns human-readable, permission-filtered graph cards.
  - Use the same grant rules as `memory_vault_search`.
  - If unavailable, fall back to `memory_vault_search`.

- `memory_vault_search(query, zones, grant_token?, project_id?, memory_types?, top_k?, api_key?, base_url?)`
  - Use for zone-scoped retrieval.
  - `public_profile` can be searched without a grant token.
  - All other zones require a valid token.

- `memory_search(query, project_id?, memory_types?, top_k?, api_key?, base_url?)`
  - Legacy broad memory search. Prefer `memory_vault_search` for new workflows.

## Grants

- `memory_request_grant(task_id, purpose, allowed_zones, project_id?, ttl_minutes?, api_key?, base_url?)`
  - Request the minimum zones needed.
  - `work_context` grants are scoped to `project_id`; tokens must not be reused across projects.
  - The desktop app shows the request to the user.

- `memory_get_grant(grant_id, api_key?, base_url?)`
  - Check grant status.

- `memory_approve_grant(grant_id, ttl_minutes?, api_key?, base_url?)`
  - Admin/user-side approval tool.

## Capture And Model Suggestions

- `memory_ingest(content, project_id?, source?, content_kind?, auto_approve_public_low?, api_key?, base_url?)`
  - Submit selected/API/file/feedback content to the permissioned ingestion pipeline.
  - Low-risk public profile content may auto-approve for user/admin keys.
  - Non-public or agent-submitted content goes to inbox review.

- `memory_extraction_preview(content, project_id?, content_kind?, memory_zone?, memory_type?, api_key?, base_url?)`
  - Preview redaction, semantic summary, candidate matches, duplicate/conflict/update detection, and a human-readable reason.

- `memory_semantic_summarize(content, project_id?, memory_zone?, model_profile_id?, api_key?, base_url?)`
  - Generate a redacted semantic summary, entities, triggers, and semantic facts.
  - Use for debugging; normal agents should prefer `memory_request_context`.

- `memory_semantic_judge(content, project_id?, memory_zone?, model_profile_id?, top_k?, api_key?, base_url?)`
  - Compare a new memory against existing semantic summaries and judge duplicate/update/conflict/separate/uncertain.
  - Model output is advisory and must not bypass inbox approval.

- `memory_rebuild_summaries(model_profile_id?, api_key?, base_url?)`
  - Rebuild semantic summaries for approved memories.

- `memory_list_decision_examples(project_id?, zone?, limit?, api_key?, base_url?)`
  - List user decisions used as few-shot examples for later semantic judgment.

- `memory_list_memories(project_id?, zone?, memory_type?, status?, query?, limit?, api_key?, base_url?)`
  - User/admin memory editor list view.

- `memory_get_memory(memory_id, api_key?, base_url?)`
  - User/admin memory detail view with facts, timeline, and audit summary.

- `memory_list_inbox(status?, api_key?, base_url?)`
  - List review items. User/admin context only.

- `memory_approve_inbox(inbox_id, memory_zone?, memory_type?, project_id?, api_key?, base_url?)`
  - Promote an inbox item into approved memory.

- `memory_analyze_capture(content, content_kind?, project_id?, api_key?, base_url?)`
  - Rule and model-assisted capture classification.

- `memory_commit_capture(content, memory_zone, memory_type?, project_id?, api_key?, base_url?)`
  - Save user-confirmed memory.

- `memory_list_model_profiles(api_key?, base_url?)`
  - List BYOM profiles.

- `memory_classify_with_model(content, project_id?, model_profile_id?, api_key?, base_url?)`
  - Run BYOM classification with redaction and policy guards.

## Feedback Learning

- `memory_context_feedback(task_id, rating, correction, error_type?, expected_behavior?, project_id?, api_key?, base_url?)`
- `memory_submit_feedback(task_id, rating, correction, error_type?, expected_behavior?, project_id?, api_key?, base_url?)`
- `memory_extract_lessons(feedback_id, api_key?, base_url?)`
- `memory_approve_lesson(proposal_id, api_key?, base_url?)`

## Hard Rules

- Never store or transmit grant tokens as memories.
- Never store Share Pack tokens as memories.
- Never send raw secrets or payment details to a remote model.
- Never use model suggestions to downgrade sensitive content.
- A grant is task-scoped and time-limited.
- A grant is project-scoped when `project_id` is set.
- A Share Pack is project-scoped, expiring, revocable, and work-context only.
- Treat inbox `update` approvals as replacements; old superseded memories should not be used.
