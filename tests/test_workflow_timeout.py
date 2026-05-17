from __future__ import annotations

from backend.llm.config import LLMConfig, LLMProviderConfig
from backend.services.llm import llm_service as llm_service_module
from backend.services.llm import workflow_service


def _enabled_provider() -> LLMProviderConfig:
    return LLMProviderConfig(
        type="gemini",
        base_url="",
        api_key="test-key",
        default_model="test-model",
        enabled=True,
        timeout_seconds=60,
    )


def test_resolve_timeout_for_step_reads_positive_step_override(monkeypatch):
    config = {
        "workflows": {
            "create_novel_by_ai": {
                "steps": {
                    "expand_idea_to_full_novel_story": {
                        "provider": "gemini_chat",
                        "timeout_seconds": "180",
                    }
                }
            }
        }
    }

    monkeypatch.setattr(workflow_service, "get_config_value", lambda key, default=None: config)

    assert workflow_service.resolve_timeout_for_step(
        "create_novel_by_ai",
        "expand_idea_to_full_novel_story",
    ) == 180


def test_get_llm_service_for_step_passes_timeout_override(monkeypatch):
    config = {
        "workflows": {
            "create_novel_by_ai": {
                "default_provider": "gemini_chat",
                "steps": {
                    "expand_idea_to_full_novel_story": {
                        "provider": "gemini_chat",
                        "timeout_seconds": 240,
                    }
                },
            }
        }
    }
    llm_config = LLMConfig(
        default_provider="gemini_chat",
        providers={"gemini_chat": _enabled_provider()},
    )
    captured: dict[str, object] = {}

    class FakeLLMService:
        def __init__(self, provider_name: str | None = None, timeout_seconds: int | None = None) -> None:
            captured["provider_name"] = provider_name
            captured["timeout_seconds"] = timeout_seconds

    monkeypatch.setattr(workflow_service, "get_config_value", lambda key, default=None: config)
    monkeypatch.setattr(workflow_service, "get_llm_config", lambda: llm_config)
    monkeypatch.setattr(workflow_service, "LLMService", FakeLLMService)

    workflow_service.get_llm_service_for_step(
        "create_novel_by_ai",
        "expand_idea_to_full_novel_story",
    )

    assert captured == {"provider_name": "gemini_chat", "timeout_seconds": 240}


def test_core_factions_step_can_use_independent_provider(monkeypatch):
    config = {
        "workflows": {
            "create_factions_by_ai": {
                "default_provider": "default_chat",
                "steps": {
                    "create_core_factions": {
                        "provider": "faction_chat",
                        "timeout_seconds": 360,
                    }
                },
            }
        }
    }
    llm_config = LLMConfig(
        default_provider="default_chat",
        providers={
            "default_chat": _enabled_provider(),
            "faction_chat": _enabled_provider(),
        },
    )

    monkeypatch.setattr(workflow_service, "get_config_value", lambda key, default=None: config)
    monkeypatch.setattr(workflow_service, "get_llm_config", lambda: llm_config)

    assert workflow_service.resolve_provider_for_step(
        "create_factions_by_ai",
        "create_core_factions",
    ) == "faction_chat"
    assert workflow_service.resolve_timeout_for_step(
        "create_factions_by_ai",
        "create_core_factions",
    ) == 360


def test_provider_resolution_is_scoped_by_workflow_name(monkeypatch):
    config = {
        "workflows": {
            "create_novel_by_ai": {
                "default_provider": "novel_chat",
                "steps": {"core_seed": {"provider": "novel_chat", "timeout_seconds": None}},
            },
            "custom_outline_flow": {
                "default_provider": "outline_chat",
                "steps": {"outline": {"provider": "outline_chat", "timeout_seconds": 120}},
            },
        }
    }
    llm_config = LLMConfig(
        default_provider="novel_chat",
        providers={
            "novel_chat": _enabled_provider(),
            "outline_chat": _enabled_provider(),
        },
    )

    monkeypatch.setattr(workflow_service, "get_config_value", lambda key, default=None: config)
    monkeypatch.setattr(workflow_service, "get_llm_config", lambda: llm_config)

    assert workflow_service.resolve_provider_for_step("create_novel_by_ai", "core_seed") == "novel_chat"
    assert workflow_service.resolve_provider_for_step("custom_outline_flow", "outline") == "outline_chat"
    assert workflow_service.resolve_timeout_for_step("custom_outline_flow", "outline") == 120


def test_llm_service_forwards_timeout_override_to_client_factory(monkeypatch):
    captured: dict[str, object] = {}

    class FakeClient:
        pass

    def fake_create_llm_client(provider_name: str | None = None, *, timeout_seconds: int | None = None):
        captured["provider_name"] = provider_name
        captured["timeout_seconds"] = timeout_seconds
        return FakeClient()

    monkeypatch.setattr(llm_service_module, "create_llm_client", fake_create_llm_client)

    llm_service_module.LLMService(provider_name="gemini_chat", timeout_seconds=300)

    assert captured == {"provider_name": "gemini_chat", "timeout_seconds": 300}
