from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from memory_gateway.db import Base
from memory_gateway.schemas import (
    CaptureAnalyzeRequest,
    ModelProcessingClassifyRequest,
    ModelProfileCreateRequest,
)
from memory_gateway.security import authenticate_api_key
from memory_gateway.service import (
    activate_model_profile,
    analyze_capture,
    classify_capture_with_model,
    create_model_profile,
    list_model_profiles,
    seed_demo_data,
)
from memory_gateway.types import MemoryZone, ModelProvider, ModelTask


def main() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, future=True)
    admin = authenticate_api_key("admin-demo-key")
    assert admin

    with Session() as session:
        seed_demo_data(session)
        print("\n== default profiles ==")
        for profile in list_model_profiles(session, admin):
            print(f"- {profile.id} provider={profile.provider} active={profile.is_active}")

        custom = create_model_profile(
            session,
            admin,
            ModelProfileCreateRequest(
                id="demo-rule-public",
                name="Demo rule public",
                provider=ModelProvider.RULE_ONLY,
                model="rules",
                allowed_tasks=[ModelTask.CLASSIFY_CAPTURE],
                allowed_zones=[MemoryZone.PUBLIC_PROFILE],
                local_only=True,
                auto_apply_low_sensitivity=True,
            ),
        )
        activate_model_profile(session, admin, custom.id)
        print("\n== activated profile ==")
        print(custom.id)

        low = analyze_capture(
            session,
            admin,
            CaptureAnalyzeRequest(
                content="I prefer concise answers with bullet points.",
                model_profile_id=custom.id,
            ),
        )
        print("\n== low-risk capture analysis ==")
        print(low.model_dump())

        high = classify_capture_with_model(
            session,
            admin,
            ModelProcessingClassifyRequest(
                content="Payment card 4111 1111 1111 1111 CVV 123",
                model_profile_id="openai-compatible-redacted-only",
            ),
        )
        print("\n== high-risk remote profile is blocked or redacted ==")
        print(high.model_dump())


if __name__ == "__main__":
    main()

