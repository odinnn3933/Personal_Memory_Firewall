---
name: personal-memory-firewall
description: Use when an agent needs to retrieve, request, save, classify, or learn from user-controlled memories through the Personal Memory Firewall MCP server. This skill applies to Codex, Claude Code, and other coding agents working with memory zones, short-lived grants, BYOM memory processing, feedback learning, or privacy-preserving context retrieval.
---

# Personal Memory Firewall

Use the MCP tools as the only memory interface. Do not access the database, local files, or raw vault data directly.

## Retrieval Workflow

1. Identify the task purpose and the minimum memory zones needed.
2. Use `memory_list_zones` if the zone policy is unclear.
3. Call `memory_request_context` with the task, project id, and minimum zones.
4. If it returns `status=ready`, use the returned `prompt_context`.
5. If it returns `status=pending_grant`, wait for the user to approve the grant in the desktop app.
6. After approval, call `memory_get_context_request` or `memory_compose_approved_context` with the grant id.
7. Use lower-level `memory_request_grant` only when you need to create a grant without composing context yet.
8. Use `memory_vault_search` only when exact source memories are needed for debugging.
9. After mistakes or preference updates, call `memory_context_feedback`.

## Project Share Pack Workflow

Use Share Packs only for collaborator or agent onboarding to a project. A Share Pack returns prompt-ready project context without exposing the raw memory database.

1. For normal task work, keep using `memory_request_context`.
2. For onboarding a collaborator, use `memory_compose_share_pack` with the provided share pack id and share token.
3. Treat the share token as a secret; never store it as memory or include it in generated files.
4. Do not use Share Packs to request `personal_context`, `sensitive_vault`, or `payment_reference`.
5. If a Share Pack is revoked, expired, or exhausted, ask the user to create a new one.

## Zone Policy

- `public_profile`: general low-risk preferences; no grant required.
- `work_context`: project and team context; request only for work tasks.
- `work_context` requests must include the current `project_id`; do not mix memories across projects.
- `personal_context`: personal preferences; request only for personal tasks.
- `sensitive_vault`: high-risk references; request only when explicitly necessary.
- `payment_reference`: payment-related references; request only for booking or payment tasks and treat as high confirmation.

## Model Processing

Use model tools only for suggestions. Models cannot approve grants, downgrade sensitive data, or override hard policy.

- Use `memory_classify_with_model` for capture classification suggestions.
- Treat `model_suggestion` as advisory.
- Trust `final_suggestion_source`, `sent_to_model`, and `used_redacted_preview` for safety reporting.
- Never send raw card numbers, passwords, API keys, tokens, or grant tokens as memory content.

## Graph Memory

- Use `memory_graph_health` to check whether graph retrieval is available.
- Prefer `memory_compose_context`; it may include SQL facts and graph cards when available.
- Use `memory_graph_search` only for graph-specific debugging.
- Treat graph cards as derived context; source memory permissions remain authoritative.
- If graph retrieval is unavailable, continue with `memory_vault_search`.

## Ingestion Workflow

- Use `memory_ingest` for selected text, API-submitted content, or agent feedback summaries.
- Use `memory_extraction_preview` when the user wants to inspect facts, duplicates, conflicts, or update suggestions before saving.
- Non-public captures enter the review inbox and are not searchable until the user/admin approves them.
- Inbox items may be marked as `duplicate`, `update`, or `conflict`; do not assume new content should become a new memory.
- Use `memory_list_inbox` and `memory_approve_inbox` only from a user/admin approval context.

## Prohibited Behavior

- Do not claim access to a memory zone before a grant is approved.
- Do not invent or reuse expired grant tokens.
- Do not invent, persist, or reuse revoked Share Pack tokens.
- Do not store grant tokens, passwords, card numbers, CVV, API keys, or raw payment details.
- Do not use model output to bypass user confirmation.
- Do not request broader zones than the task needs.

For exact tool names and arguments, read `references/tool-contract.md`.
