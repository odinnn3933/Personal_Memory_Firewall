from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from memory_gateway.db import SessionLocal
from memory_gateway.security import AgentIdentity, authenticate_api_key


def get_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_current_agent(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> AgentIdentity:
    agent = authenticate_api_key(x_api_key)
    if not agent:
        raise HTTPException(status_code=401, detail="invalid or missing X-API-Key")
    return agent


DbSession = Annotated[Session, Depends(get_db)]
CurrentAgent = Annotated[AgentIdentity, Depends(get_current_agent)]

