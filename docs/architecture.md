# Architecture

Personal Memory Firewall is a permissioned context runtime for AI agents. Its core job is not to store every possible memory. Its job is to decide what an agent is allowed to know for one task, then compose that allowed memory into a prompt-ready context package.

## Main Components

```text
Desktop / REST / MCP / Python SDK / Skill Pack
        |
        v
FastAPI Runtime
        |
        +-- Ingestion
        +-- Access Grants
        +-- Retrieval
        +-- Context Composer
        +-- Project Share Packs
        +-- Learning / Updates
        +-- Audit
        |
        v
SQLite or Postgres data model
        |
        +-- memories
        +-- memory_inbox_items
        +-- memory_facts
        +-- memory_versions
        +-- access_grants
        +-- share_packs
        +-- audit_events
        +-- model_profiles
```

Neo4j is optional. SQL facts and SQL ACL checks remain authoritative when graph retrieval is unavailable.

## Memory Zones

The system separates memory by use and risk:

- `public_profile`: low-risk preferences readable without a grant.
- `work_context`: project-scoped work facts, procedures, decisions, and relationships.
- `personal_context`: personal life context, habits, relationships, and preferences.
- `sensitive_vault`: redacted high-risk references and red-line rules.
- `payment_reference`: payment confirmation rules and references, never raw card/CVV data.

Only `public_profile` is grant-free. Every other zone requires an active grant for agent retrieval.

## Memory Types

Current memory types:

- `context`
- `preference`
- `relationship`
- `procedure`
- `lesson`
- `anti_pattern`

`relationship` is intentionally a type, not a zone. A friend relationship belongs in `personal_context`; a colleague or client relationship belongs in `work_context`.

## Ingestion Flow

```text
raw selected text
-> deterministic redaction
-> rule/model classification suggestion
-> semantic summary and triggers
-> duplicate/update/conflict candidate check
-> Memory Inbox unless low-risk public profile
-> approval creates memory + facts + version event
```

Models can suggest summaries and classifications, but they cannot approve grants, bypass inbox review, downgrade sensitivity, or override zone policy.

## Relationship Memory

Example:

```text
Alice is my close friend. We usually play basketball together.
```

Stored as:

```text
memory_zone = personal_context
memory_type = relationship
fact_type = relationship
predicate = FRIEND_OF
object = Alice
```

The fact inherits the source memory's zone, sensitivity, visibility, and source IDs. It is returned only if all source memories pass SQL ACL and grant checks.

## Agent Request Flow

Agents should not call low-level search by default. The preferred path is:

```text
agent calls memory_request_context(task, zones, project_id)
-> backend returns context immediately for public-only requests
-> backend creates pending grant for protected zones
-> user/admin approves in desktop or API
-> agent polls memory_get_context_request(grant_id)
-> backend returns prompt_context
```

This lets agents continue after approval without copying raw grant tokens into memory or prompts.

## Project Share Packs

Share Packs are for collaborator or agent onboarding, not normal task retrieval.

```text
user/admin previews approved project work memory
-> creates Share Pack token
-> recipient calls compose with share_pack_id + share_token
-> backend recomputes prompt-ready context from the current allowed project memories
```

The share token is an authorization source only for that Share Pack scope. It does not grant project membership and cannot open personal, sensitive, payment, private, deleted, pending, or superseded memories.

Share Pack tokens are:

- hash-only in the database
- returned once on creation
- expiring
- max-use limited
- revocable
- audited on preview, create, compose, and revoke

## ACL-First Retrieval

Retrieval is deliberately ordered:

```text
tenant/project/status/zone/grant SQL filtering
-> candidate ranking
-> source cards and fact cards
-> prompt-ready context
```

Ranking never runs over forbidden memories. Denied zones are returned as explanations, not as hidden content.

## Context Composer

The composer returns:

- `prompt_context`: Markdown ready to place in an agent prompt.
- `sections`: grouped context such as Preferences, Relationships, Project Facts, Procedures, Lessons, Anti-Patterns, Structured Facts.
- `source_cards`: human-readable memory sources.
- `fact_cards`: structured SQL facts.
- `denied_zones`: zones skipped because grant or permission was missing.
- `audit_id`: traceability for the compose event.

## Update And Versioning

When new memory updates old memory:

```text
new capture
-> semantic candidate match
-> update proposal in inbox
-> user approves update
-> old memory status = superseded
-> old facts become inactive
-> new memory becomes approved
-> memory_versions records the change
```

This prevents stale memory from appearing in future context.

## Desktop Prototype

The Tauri/React app provides:

- Capture
- Inbox
- Memories
- Grants
- Compose
- Audit
- Settings

It intentionally hides raw JSON and model payloads in the main UI. Debugging belongs in API docs, tests, and logs.

## Security Boundary

The MVP demonstrates security architecture, not production security:

- Demo API keys are static.
- SQLite mode is for local development.
- No real user accounts or cloud sync.
- Do not store raw passwords, tokens, private keys, CVV, full card numbers, or national IDs.
- A real deployment needs proper authentication, encryption at rest, secret management, and tenant isolation hardening.
