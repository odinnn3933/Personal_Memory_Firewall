# GitHub Release Checklist

Use this before pushing or sharing the repository.

## Required Verification

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\test_full_flow.ps1
```

Expected:

```text
54 passed
FULL SYSTEM FLOW PASS
RELATIONSHIP MEMORY DEMO PASS
AGENT REQUEST FLOW DEMO PASS
PROJECT SHARE DEMO PASS
FULL FLOW CHECK PASS
```

## Files Not To Commit

Confirm these stay untracked:

```text
memory_gateway.db
.env
.pytest_cache/
__pycache__/
apps/desktop/node_modules/
apps/desktop/dist/
apps/desktop/src-tauri/target/
apps/desktop/vite-preview.*.log
```

The repository `.gitignore` should already cover these. Do not force-add them.

## README Expectations

The README should make these points clear in the first screen:

- This is a permissioned memory runtime, not just vector search.
- Agents request context through grants.
- Protected memories are user-approved.
- Relationship and personal memories require the right zone grant.
- Project Share Packs provide revocable, expiring, work-context-only onboarding.
- This is a research MVP, not production security.

## Demo Story To Show

Best 60-second flow:

```text
1. Seed demo data.
2. Run project_share_demo.
3. Show guest/no-grant denied from work_context.
4. Create Share Pack.
5. Guest uses share token to get project onboarding context.
6. Show personal/payment content excluded.
7. Revoke Share Pack and show token no longer works.
```

Best relationship-memory flow:

```text
1. Capture "Alice is my close friend..."
2. System classifies it as personal_context / relationship.
3. Approve it from Inbox.
4. Agent asks "Who is Alice?"
5. Without personal_context grant, context denies the zone.
6. Approve grant.
7. Agent receives prompt context with ## Relationships and FRIEND_OF fact.
```

Best terminal commands:

```powershell
python examples\project_share_demo.py
python examples\relationship_memory_demo.py
python examples\agent_request_flow_demo.py
```

## Honest Limitations

Keep these visible:

- Demo API keys are local only.
- The desktop app is a prototype.
- Share Packs are token-based MVP sharing, not a real account/invite system.
- Relationship extraction is rule-based fallback unless a BYOM profile is configured.
- Neo4j is optional enhancement, not a required source of permission truth.
- The system does not store raw secrets or payment credentials.

## Suggested GitHub Description

```text
Personal Memory Firewall: permissioned context runtime and revocable project memory sharing for AI agents.
```

## Suggested Topics

```text
ai-agents
memory
mcp
fastapi
tauri
personal-ai
context-engineering
agent-memory
privacy
knowledge-graph
```
