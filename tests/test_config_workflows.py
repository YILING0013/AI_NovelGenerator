from backend.config import config as config_module
from backend.llm.openai_client import _build_openai_sdk_base_url


def test_normalize_config_tree_adds_fixed_faction_workflow() -> None:
    """旧版流程配置缺少阵营流程时，加载配置会补齐固定流程与固定步骤。"""
    normalized = config_module._normalize_config_tree(
        {
            "llm": {
                "default_provider": "default_chat",
                "providers": {},
                "workflows": {
                    "create_novel_by_ai": {
                        "default_provider": "novel_chat",
                        "steps": {
                            "novel_meta": {
                                "provider": "novel_chat",
                                "timeout_seconds": "180",
                            }
                        },
                    }
                },
            }
        }
    )

    workflow = normalized["llm"]["workflows"]["create_novel_by_ai"]
    assert "core_factions" not in workflow["steps"]
    assert workflow["steps"]["novel_meta"] == {"provider": "novel_chat", "timeout_seconds": 180}

    faction_workflow = normalized["llm"]["workflows"]["create_factions_by_ai"]
    assert faction_workflow["default_provider"] == "default_chat"
    assert faction_workflow["steps"]["create_core_factions"] == {"provider": "", "timeout_seconds": None}


def test_normalize_config_tree_drops_manual_workflows() -> None:
    """手动写入的流程不进入运行时配置，设置页只展示程序内置流程。"""
    normalized = config_module._normalize_config_tree(
        {
            "llm": {
                "default_provider": "default_chat",
                "providers": {},
                "workflows": {
                    "custom_outline_flow": {
                        "steps": {
                            "outline": {
                                "provider": "outline_chat",
                                "timeout_seconds": "90",
                            }
                        },
                    }
                },
            }
        }
    )

    assert set(normalized["llm"]["workflows"]) == {
        "create_novel_by_ai",
        "create_factions_by_ai",
    }
    assert "custom_outline_flow" not in normalized["llm"]["workflows"]


def test_normalize_openai_base_url_keeps_service_root() -> None:
    """OpenAI 兼容 Provider 保存时只保留服务根地址。"""
    assert (
        config_module._normalize_provider_base_url("openai", "https://api.openai.com/v1")
        == "https://api.openai.com"
    )
    assert (
        config_module._normalize_provider_base_url("openai", "https://proxy.test/openai/v1/chat/completions")
        == "https://proxy.test/openai"
    )
    assert (
        config_module._normalize_provider_base_url("openai", "https://proxy.test/api/models")
        == "https://proxy.test/api"
    )


def test_openai_sdk_base_url_appends_runtime_version_only_once() -> None:
    """OpenAI SDK 调用地址在运行时补 /v1，兼容旧配置不重复追加。"""
    assert _build_openai_sdk_base_url("") is None
    assert _build_openai_sdk_base_url("https://api.openai.com") == "https://api.openai.com/v1"
    assert _build_openai_sdk_base_url("https://api.openai.com/v1") == "https://api.openai.com/v1"
    assert (
        _build_openai_sdk_base_url("https://proxy.test/openai/v1/chat/completions")
        == "https://proxy.test/openai/v1"
    )
    assert _build_openai_sdk_base_url("https://proxy.test/openai") == "https://proxy.test/openai/v1"
