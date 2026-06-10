# Personal Memory Firewall

**A permissioned context runtime for AI agents.**

Personal Memory Firewall lets agents ask for scoped, auditable, prompt-ready memory context instead of reading a user's whole memory store. It is built around a simple rule: memory should be useful to agents, but the user decides what can be captured, approved, shared, revoked, and composed into a prompt.

> Status: research MVP / internship portfolio project. This repository uses local demo keys and is not production security.

## Why It Is Different

Most agent memory demos focus on recall. This project focuses on control:

- **Permissioned retrieval:** non-public memory zones require short-lived grants.
- **Project isolation:** work memories are scoped by `project_id`.
- **Prompt-ready context:** agents receive Markdown context packages with source policy, not raw database rows.
- **Share Packs:** users can share revocable, expiring project onboarding context with collaborators or agents without exposing personal/sensitive memory.
- **Governed updates:** stale memories can be superseded, deleted, restored, and audited.
- **Human review:** protected captures enter an inbox before becoming retrievable.

## Core Demo

The strongest demo is the **Project Memory Share Pack**:

```text
approved project work memories
-> preview share scope
-> create expiring/revocable share token
-> collaborator/agent receives prompt-ready onboarding context
-> personal/sensitive/payment/private memories stay excluded
```

Run it:

```powershell
python examples\project_share_demo.py
```

Expected story:

- A guest agent cannot directly read `work_context`.
- Admin creates a Share Pack for `memory-gateway`.
- Guest uses the share token to get project onboarding context.
- Personal friend memory and payment references do not appear.
- Revoking the Share Pack blocks future use.

## Full Verification

```powershell
powershell -ExecutionPolicy Bypass -File scripts\test_full_flow.ps1
```

Current expected result:

```text
54 passed
FULL SYSTEM FLOW PASS
RELATIONSHIP MEMORY DEMO PASS
AGENT REQUEST FLOW DEMO PASS
PROJECT SHARE DEMO PASS
FULL FLOW CHECK PASS
```

## Quickstart

Requirements:

- Python 3.11+
- Node.js 18+
- Rust only if you want to run the Tauri desktop shell

Install and run the API:

```powershell
python -m pip install -e ".[dev]"
python -m memory_gateway.cli seed
python -m memory_gateway.cli api --port 8010
```

Open the API docs:

```text
http://127.0.0.1:8010/docs
```

Demo API keys:

```text
admin-demo-key
backend-demo-key
guest-demo-key
```

## Desktop App

The desktop prototype lives in `apps/desktop`.

React preview:

```powershell
cd apps\desktop
npm install
npm run dev
```

Tauri shell:

```powershell
npm run tauri dev
```

The desktop app expects the backend at:

```text
http://127.0.0.1:8010
```

Main tabs:

- `Capture`: paste or read selected clipboard text.
- `Inbox`: approve/reject/merge/update protected memories.
- `Memories`: edit, supersede, delete, restore, and inspect timeline.
- `Grants`: approve short-lived agent access requests.
- `Compose`: simulate agent context composition.
- `Share`: create and revoke Project Memory Share Packs.
- `Audit`: inspect recent actions.
- `Settings`: configure API keys, project, and BYOM model profiles.

## Architecture

```text
Desktop / REST / MCP / Python SDK / Skill Pack
        |
        v
FastAPI permissioned context runtime
        |
        +-- ingestion + redaction + inbox
        +-- access grants + ACL-first retrieval
        +-- project share packs
        +-- summary-first ranking + SQL facts
        +-- context composer
        +-- audit trail
        +-- optional Neo4j graph enhancement
```

See [docs/architecture.md](docs/architecture.md) for more detail.

## Memory Zones

- `public_profile`: low-risk preferences agents may use without a grant.
- `work_context`: project and team context; grant required and project-scoped.
- `personal_context`: life context, habits, relationships; grant required.
- `sensitive_vault`: high-risk references and red-line rules; grant required.
- `payment_reference`: payment-related references; grant required; raw card/CVV/token data is redacted.

First-version safety rule: do not store real card numbers, CVV, passwords, API keys, tokens, or national IDs in clear text.

## Share Packs

Share Packs are for collaborator onboarding, not general personal memory sharing.

MVP defaults:

- zone: `work_context`
- TTL: 7 days
- max uses: 20
- token storage: raw token returned once, hash stored in the database
- excluded: `personal_context`, `sensitive_vault`, `payment_reference`, private, deleted, pending, superseded, and cross-project memories

REST endpoints:

- `POST /v1/share-packs/preview`
- `POST /v1/share-packs`
- `GET /v1/share-packs`
- `POST /v1/share-packs/{id}/compose`
- `POST /v1/share-packs/{id}/revoke`

MCP tools:

- `memory_preview_share_pack`
- `memory_create_share_pack`
- `memory_compose_share_pack`
- `memory_list_share_packs`
- `memory_revoke_share_pack`

## Agent Workflow

Normal task context:

```text
memory_request_context
-> pending_grant when protected zones are needed
-> user approves in desktop/API
-> memory_get_context_request or memory_compose_approved_context
-> prompt_context
```

Collaborator onboarding:

```text
memory_compose_share_pack
-> prompt-ready project context
```

The MCP server is named:

```text
personal-memory-firewall
```

Skill pack:

```text
integrations/skills/personal-memory-firewall
```

## Other Demos

```powershell
python examples\full_system_flow_demo.py
python examples\relationship_memory_demo.py
python examples\agent_request_flow_demo.py
python examples\semantic_update_demo.py
python examples\summary_first_context_demo.py
```

These show:

- work context denied without grant
- grant approval and agent continuation
- relationship memory in `personal_context`
- project isolation
- stale memory supersede/update
- prompt-ready context with source cards

## BYOM Model Profiles

Default profiles:

- `rule-only-default`: offline deterministic fallback.
- `ollama-local`: local Ollama endpoint.
- `openai-compatible-redacted-only`: OpenAI-compatible endpoint using redacted previews.

Model output is advisory. Hard policy still wins:

- Redaction runs first.
- Remote profiles receive redacted previews only.
- Sensitive/payment content is not sent to remote models by default.
- Models cannot approve grants or downgrade sensitivity.
- Non-public memories still require review and grants.

## Docker

```powershell
docker compose up --build
```

The compose stack includes Postgres and Neo4j. Local demos default to SQLite and degrade gracefully when Neo4j is unavailable.

## What This Is Not

- Not production authentication.
- Not a hosted multi-user product.
- Not a complete personal knowledge graph.
- Not a password manager or payment vault.
- Not model weight training.

For production, this would still need real auth, encryption at rest, secret management, tenant isolation hardening, account management, and security review.

## Compared With Existing Memory Systems

| Direction | Typical focus | This project focus |
| --- | --- | --- |
| Mem0-style memory | self-improving memory recall | permissioned ingestion and governed context |
| Zep-style graph context | temporal graph context | SQL-authoritative ACL with optional graph enhancement |
| Letta-style memory | agent memory layers | user-controlled context packages for external agents |
| Vector-store demos | semantic search | review, update, grants, audit, and Share Packs |
