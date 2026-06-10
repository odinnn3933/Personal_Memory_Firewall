from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from memory_gateway.db import Base
from memory_gateway.schemas import GrantRequest, VaultSearchRequest
from memory_gateway.security import authenticate_api_key
from memory_gateway.service import (
    PermissionDenied,
    approve_access_grant,
    benchmark_forbidden_leak_rate,
    request_access_grant,
    seed_demo_data,
    utcnow,
    vault_search,
)
from memory_gateway.db import AccessGrantRecord
from memory_gateway.types import MemoryZone


def main() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, future=True)
    guest = authenticate_api_key("guest-demo-key")
    backend = authenticate_api_key("backend-demo-key")
    assert guest and backend
    with Session() as session:
        seed_demo_data(session)
        result = benchmark_forbidden_leak_rate(session, guest, backend)
        grant = request_access_grant(
            session,
            backend,
            GrantRequest(
                task_id="bench-expired",
                purpose="Measure expired grant behavior.",
                allowed_zones=[MemoryZone.WORK_CONTEXT],
                project_id="memory-gateway",
            ),
        )
        approved = approve_access_grant(session, authenticate_api_key("admin-demo-key"), grant.id)
        record = session.get(AccessGrantRecord, grant.id)
        record.expires_at = utcnow().replace(year=2000)
        expired_grant_access = 0
        try:
            vault_search(
                session,
                backend,
                VaultSearchRequest(
                    query="database",
                    project_id="memory-gateway",
                    zones=[MemoryZone.WORK_CONTEXT],
                    grant_token=approved.token,
                ),
            )
            expired_grant_access = 1
        except PermissionDenied:
            expired_grant_access = 0
        result["expired_grant_access"] = expired_grant_access
        print(result)


if __name__ == "__main__":
    main()
