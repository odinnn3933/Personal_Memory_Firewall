from __future__ import annotations

import httpx

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


def test_default_model_profiles_seeded(session):
    admin = authenticate_api_key("admin-demo-key")
    assert admin
    profiles = list_model_profiles(session, admin)
    ids = {profile.id for profile in profiles}
    assert {"rule-only-default", "ollama-local", "openai-compatible-redacted-only"} <= ids
    assert next(profile for profile in profiles if profile.id == "rule-only-default").is_active


def test_model_profile_create_and_activate(session):
    admin = authenticate_api_key("admin-demo-key")
    assert admin
    created = create_model_profile(
        session,
        admin,
        ModelProfileCreateRequest(
            id="test-rule",
            name="Test Rule",
            provider=ModelProvider.RULE_ONLY,
            model="rules",
            allowed_tasks=[ModelTask.CLASSIFY_CAPTURE],
            allowed_zones=[MemoryZone.PUBLIC_PROFILE],
            local_only=True,
            auto_apply_low_sensitivity=True,
        ),
    )
    activated = activate_model_profile(session, admin, created.id)
    profiles = list_model_profiles(session, admin)
    assert activated.is_active
    assert [profile.id for profile in profiles if profile.is_active] == ["test-rule"]


def test_direct_api_key_is_used_but_not_exposed(monkeypatch, session):
    admin = authenticate_api_key("admin-demo-key")
    assert admin
    created = create_model_profile(
        session,
        admin,
        ModelProfileCreateRequest(
            id="direct-key-profile",
            name="Direct Key Profile",
            provider=ModelProvider.OPENAI_COMPATIBLE,
            model="gpt-test",
            endpoint_url="http://model.test/v1",
            api_key="sk-direct-test",
            allowed_tasks=[ModelTask.CLASSIFY_CAPTURE],
            allowed_zones=[MemoryZone.PUBLIC_PROFILE],
        ),
    )
    assert created.has_api_key
    assert "api_key" not in created.model_dump()

    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"suggested_zone":"public_profile","suggested_memory_type":"preference","tags":["profile"],"confidence":0.9}'
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    result = classify_capture_with_model(
        session,
        admin,
        ModelProcessingClassifyRequest(
            content="I prefer concise answers.",
            model_profile_id=created.id,
        ),
    )
    assert result.sent_to_model
    assert calls[0]["url"] == "http://model.test/v1/chat/completions"
    assert calls[0]["headers"]["Authorization"] == "Bearer sk-direct-test"
    assert calls[0]["json"]["model"] == "gpt-test"


def test_rule_only_profile_does_not_call_external_api(session):
    admin = authenticate_api_key("admin-demo-key")
    assert admin
    result = classify_capture_with_model(
        session,
        admin,
        ModelProcessingClassifyRequest(
            content="I prefer concise answers.",
            model_profile_id="rule-only-default",
        ),
    )
    assert not result.sent_to_model
    assert result.provider == ModelProvider.RULE_ONLY


def test_remote_profile_receives_redacted_preview(monkeypatch, session):
    admin = authenticate_api_key("admin-demo-key")
    assert admin
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append(json["messages"][1]["content"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"suggested_zone":"public_profile","suggested_memory_type":"preference","tags":["profile"],"confidence":0.9}'
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    result = classify_capture_with_model(
        session,
        admin,
        ModelProcessingClassifyRequest(
            content="I prefer concise answers. token=abc123",
            model_profile_id="openai-compatible-redacted-only",
        ),
    )
    assert not result.sent_to_model
    assert not calls
    assert "blocked_by_policy" in result.suggestion

    result = classify_capture_with_model(
        session,
        admin,
        ModelProcessingClassifyRequest(
            content="I prefer concise answers.",
            model_profile_id="openai-compatible-redacted-only",
        ),
    )
    assert result.sent_to_model
    assert "abc123" not in calls[-1]
    assert result.used_redacted_preview


def test_hard_policy_blocks_public_downgrade_for_payment(monkeypatch, session):
    admin = authenticate_api_key("admin-demo-key")
    assert admin
    called = False

    def fake_post(*args, **kwargs):
        nonlocal called
        called = True
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"suggested_zone":"public_profile","suggested_memory_type":"preference","tags":["unsafe"],"confidence":0.9}'
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    result = analyze_capture(
        session,
        admin,
        CaptureAnalyzeRequest(
            content="Visa card 4111 1111 1111 1111 CVV 123",
            model_profile_id="openai-compatible-redacted-only",
        ),
    )
    assert not called
    assert result.suggested_zone == MemoryZone.PAYMENT_REFERENCE
    assert result.sensitivity.value == "high"
    assert result.final_suggestion_source == "rule"


def test_model_failure_falls_back_to_rules(monkeypatch, session):
    admin = authenticate_api_key("admin-demo-key")
    assert admin

    def fake_post(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "post", fake_post)
    result = classify_capture_with_model(
        session,
        admin,
        ModelProcessingClassifyRequest(
            content="I prefer concise answers.",
            model_profile_id="openai-compatible-redacted-only",
        ),
    )
    assert result.fallback_used
    assert result.suggestion["model_error"] == "offline"
