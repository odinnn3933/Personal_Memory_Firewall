from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from memory_gateway.db import Base
from memory_gateway.runtime.context import compose_approved_context_request, compose_context, request_context
from memory_gateway.runtime.ingestion import (
    approve_inbox_item,
    approve_inbox_separate,
    approve_inbox_update,
    ingest_memory,
    reject_inbox_item,
)
from memory_gateway.runtime.memories import (
    list_memories_for_editor,
    memory_detail,
    restore_memory,
    supersede_memory,
)
from memory_gateway.runtime.semantic import list_decision_examples
from memory_gateway.schemas import (
    ContextComposeRequest,
    ContextRequestRequest,
    InboxApproveRequest,
    InboxRejectRequest,
    IngestRequest,
    MemoryRestoreRequest,
    MemorySupersedeRequest,
)
from memory_gateway.security import authenticate_api_key
from memory_gateway.service import approve_access_grant, delete_memory, seed_demo_data
from memory_gateway.types import MemoryZone


def step(title: str, fn: Callable[[], None]) -> None:
    print(f"\n== {title} ==")
    fn()
    print(f"PASS: {title}")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)

    admin = authenticate_api_key("admin-demo-key")
    backend = authenticate_api_key("backend-demo-key")
    require(admin is not None and backend is not None, "demo API keys are not configured")

    state: dict[str, str] = {}

    with SessionLocal() as session:
        seed_demo_data(session)

        def public_capture() -> None:
            result = ingest_memory(
                session,
                admin,
                IngestRequest(content="I prefer concise bullet-point answers."),
            )
            require(result.auto_approved, "low-risk public profile should auto-approve")
            require(result.memory is not None, "auto-approved ingest should return memory")
            state["public_memory"] = result.memory.id
            print(f"saved public memory: {result.memory.semantic_summary or result.memory.content}")

        def work_capture_and_approval() -> None:
            result = ingest_memory(
                session,
                admin,
                IngestRequest(
                    content=(
                        "Project requirement: the memory-gateway project must use Postgres "
                        "and pgvector for long-term memory retrieval."
                    ),
                    project_id="memory-gateway",
                    auto_approve_public_low=False,
                ),
            )
            require(result.inbox_item is not None, "work memory should enter inbox")
            approved = approve_inbox_item(
                session,
                admin,
                result.inbox_item.id,
                InboxApproveRequest(memory_zone=MemoryZone.WORK_CONTEXT, project_id="memory-gateway"),
            )
            require(approved.approved_memory_id is not None, "work inbox item should approve to memory")
            state["work_memory"] = approved.approved_memory_id
            print(f"approved work memory: {approved.approved_memory_id}")

        def work_context_requires_grant() -> None:
            result = compose_context(
                session,
                backend,
                ContextComposeRequest(
                    task="What storage should memory-gateway use?",
                    project_id="memory-gateway",
                    zones=[MemoryZone.WORK_CONTEXT],
                    include_graph=False,
                ),
            )
            require(result.source_cards == [], "work_context should not be returned without grant")
            require(result.denied_zones, "denied zone should explain missing grant")
            print(result.prompt_context)

        def approve_and_compose_work_context() -> None:
            pending = request_context(
                session,
                backend,
                ContextRequestRequest(
                    task="What storage should memory-gateway use?",
                    task_id="full-flow-demo-work",
                    purpose="Need project memory to answer architecture question.",
                    project_id="memory-gateway",
                    zones=[MemoryZone.WORK_CONTEXT],
                    include_graph=False,
                ),
            )
            require(pending.grant is not None, "context request should create a pending grant")
            before = compose_approved_context_request(session, backend, pending.grant.id)
            require(before.status == "pending_grant", "context should wait for user approval")
            approve_access_grant(session, admin, pending.grant.id)
            ready = compose_approved_context_request(session, backend, pending.grant.id)
            require(ready.context is not None, "approved grant should return prompt-ready context")
            require("Postgres" in ready.context.prompt_context, "composed context should include approved work memory")
            print(ready.context.prompt_context)

        def project_isolation() -> None:
            result = compose_context(
                session,
                backend,
                ContextComposeRequest(
                    task="What storage should travel-planner use?",
                    project_id="travel-planner",
                    zones=[MemoryZone.WORK_CONTEXT],
                    include_graph=False,
                ),
            )
            require(
                "memory-gateway project must use Postgres" not in result.prompt_context,
                "travel-planner must not receive memory-gateway project memory",
            )
            print("travel-planner did not receive memory-gateway work memory")

        def personal_update_flow() -> None:
            old = ingest_memory(
                session,
                admin,
                IngestRequest(content="I live 15 km from the office.", auto_approve_public_low=False),
            )
            require(old.inbox_item is not None, "old personal memory should enter inbox")
            approved_old = approve_inbox_separate(
                session,
                admin,
                old.inbox_item.id,
                InboxApproveRequest(memory_zone=MemoryZone.PERSONAL_CONTEXT),
            )
            require(approved_old.approved_memory_id is not None, "old personal memory should approve")

            new = ingest_memory(
                session,
                admin,
                IngestRequest(content="I moved recently. I now live 3 km from the office.", auto_approve_public_low=False),
            )
            require(new.inbox_item is not None, "new personal update should enter inbox")
            print(f"relationship: {new.inbox_item.llm_relationship}, reason: {new.inbox_item.llm_reason}")
            require(
                new.inbox_item.supersedes_memory_id == approved_old.approved_memory_id,
                "semantic pipeline should identify old commute memory as update target",
            )
            approved_new = approve_inbox_update(
                session,
                admin,
                new.inbox_item.id,
                InboxApproveRequest(
                    memory_zone=MemoryZone.PERSONAL_CONTEXT,
                    supersede_memory_id=approved_old.approved_memory_id,
                ),
            )
            require(approved_new.approved_memory_id is not None, "update should create replacement memory")
            old_detail = memory_detail(session, admin, approved_old.approved_memory_id)
            require(old_detail.memory.status == "superseded", "old commute memory should be superseded")
            state["personal_memory"] = approved_new.approved_memory_id

            pending = request_context(
                session,
                backend,
                ContextRequestRequest(
                    task="How far does the user currently live from the office?",
                    task_id="full-flow-demo-personal",
                    purpose="Need personal context for commute answer.",
                    zones=[MemoryZone.PERSONAL_CONTEXT],
                    include_graph=False,
                ),
            )
            require(pending.grant is not None, "personal context should require a grant")
            approve_access_grant(session, admin, pending.grant.id)
            ready = compose_approved_context_request(session, backend, pending.grant.id)
            require(ready.context is not None, "approved personal grant should compose context")
            require("3 km" in ready.context.prompt_context, "current commute memory should be returned")
            require("15 km" not in ready.context.prompt_context, "superseded commute memory should not be returned")
            print(ready.context.prompt_context)

        def reject_and_decision_examples() -> None:
            scratch = ingest_memory(
                session,
                admin,
                IngestRequest(content="Temporary scratch note that should not be remembered.", auto_approve_public_low=False),
            )
            require(scratch.inbox_item is not None, "scratch item should enter inbox")
            reject_inbox_item(
                session,
                admin,
                scratch.inbox_item.id,
                InboxRejectRequest(reason="Scratch note."),
            )
            decisions = list_decision_examples(session, admin)
            require(any(item.user_decision == "reject" for item in decisions), "reject decision example should be recorded")
            require(any(item.user_decision == "approve_update" for item in decisions), "update decision example should be recorded")
            print(f"decision examples recorded: {len(decisions)}")

        def memory_lifecycle() -> None:
            replacement = supersede_memory(
                session,
                admin,
                state["work_memory"],
                MemorySupersedeRequest(
                    content="Project requirement: use Postgres, pgvector, and audit logs for memory retrieval.",
                    reason="Full-flow lifecycle check.",
                ),
            )
            old = memory_detail(session, admin, state["work_memory"])
            require(old.memory.status == "superseded", "old work memory should be superseded")
            delete_memory(session, admin, replacement.memory.id)
            deleted = list_memories_for_editor(
                session,
                admin,
                project_id="memory-gateway",
                status="deleted",
                query="audit logs",
            )
            require(any(memory.id == replacement.memory.id for memory in deleted.memories), "deleted memory should appear in deleted filter")
            restored = restore_memory(
                session,
                admin,
                replacement.memory.id,
                MemoryRestoreRequest(reason="Full-flow restore check."),
            )
            require(restored.memory.status == "approved", "restored memory should be approved")
            print(f"restored replacement memory: {restored.memory.id}")

        step("public capture auto-approval", public_capture)
        step("work capture inbox approval", work_capture_and_approval)
        step("work context denied without grant", work_context_requires_grant)
        step("grant approval returns prompt-ready context", approve_and_compose_work_context)
        step("project memory isolation", project_isolation)
        step("semantic personal update replaces stale memory", personal_update_flow)
        step("rejected inbox item records learning example", reject_and_decision_examples)
        step("memory editor lifecycle supersede/delete/restore", memory_lifecycle)

        session.commit()

    print("\nFULL SYSTEM FLOW PASS")


if __name__ == "__main__":
    main()
