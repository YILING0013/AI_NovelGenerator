# config_manager.py
# -*- coding: utf-8 -*-
import json
import os
import threading
import logging
from typing import Any, Dict
from llm_adapters import create_llm_adapter, check_base_url
from embedding_adapters import create_embedding_adapter


logger = logging.getLogger(__name__)

_DEFAULT_QUALITY_POLICY: Dict[str, Any] = {
    "default_quality_threshold": 9.0,
    "max_iterations": 10,
    "min_word_count_before_expand": 3500,
    "target_word_count_after_expand": 4000,
    "word_count_adjust_score_tolerance": 0.5,
    "severe_threshold_offset": 2.0,
    "stagnation_threshold": 0.05,
    "stagnation_count_limit": 5,
    "parse_failure_streak_limit": 3,
    "enable_llm_consistency_check": True,
    "consistency_hard_gate": True,
    "enable_timeline_check": True,
    "timeline_hard_gate": True,
    "enable_compression": False,
    "force_critic_logging_each_iteration": False,
}

_QUALITY_POLICY_BOOL_FIELDS = {
    "enable_llm_consistency_check",
    "consistency_hard_gate",
    "enable_timeline_check",
    "timeline_hard_gate",
    "enable_compression",
    "force_critic_logging_each_iteration",
}

_OTHER_PARAMS_BOOL_FIELDS = {
    "force_critic_logging_each_iteration",
    "enable_llm_consistency_check",
    "consistency_hard_gate",
    "enable_timeline_check",
    "timeline_hard_gate",
    "stop_batch_on_hard_gate",
    "post_batch_runtime_audit_enabled",
    "architecture_context_ignore_budget",
    "enable_chapter_contract_guard",
    "chapter_contract_hard_gate",
    "enable_state_ledger_writeback",
    "state_ledger_hard_gate",
    "enable_next_opening_anchor_guard",
    "next_opening_anchor_hard_gate",
    "enable_output_integrity_guard",
    "output_integrity_hard_gate",
    "blueprint_full_auto_mode",
    "blueprint_auto_restart_on_arch_change",
    "blueprint_resume_auto_repair_existing",
    "blueprint_force_resume_skip_history_validation",
    "batch_partial_resume_allow_fallback",
    "batch_precheck_deep_scan",
    "batch_precheck_auto_continue_on_warning",
}

_ARCH_CONTEXT_BUDGET_FIELDS = {
    "architecture_context_budget_chapter_prompt": 18000,
    "architecture_context_budget_consistency": 22000,
    "architecture_context_budget_quality_loop": 16000,
}


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on", "enabled", "t"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", "disabled", "f", ""}:
            return False
    return default


def _normalize_quality_threshold(value: Any, default: float) -> float:
    threshold = _safe_float(value, default)
    if threshold <= 0:
        threshold = default
    return min(10.0, threshold)


def _normalize_architecture_context_budget(value: Any, default: int) -> int:
    parsed = _safe_int(value, default)
    if parsed <= 0:
        parsed = default
    return max(4000, min(120000, parsed))


def normalize_quality_policy(raw_policy: Any, fallback_threshold: Any = 9.0) -> Dict[str, Any]:
    """规范化 quality_policy，保证类型和边界稳定。"""
    policy = dict(_DEFAULT_QUALITY_POLICY)
    if isinstance(raw_policy, dict):
        policy.update(raw_policy)

    threshold_default = _normalize_quality_threshold(
        policy.get("default_quality_threshold", fallback_threshold),
        _normalize_quality_threshold(fallback_threshold, float(_DEFAULT_QUALITY_POLICY["default_quality_threshold"])),
    )
    policy["default_quality_threshold"] = threshold_default
    policy["max_iterations"] = max(1, min(50, _safe_int(policy.get("max_iterations"), int(_DEFAULT_QUALITY_POLICY["max_iterations"]))))
    min_word_count = _safe_int(
        policy.get("min_word_count_before_expand"),
        int(_DEFAULT_QUALITY_POLICY["min_word_count_before_expand"]),
    )
    if min_word_count <= 0:
        min_word_count = int(_DEFAULT_QUALITY_POLICY["min_word_count_before_expand"])
    policy["min_word_count_before_expand"] = max(100, min_word_count)

    target_word_count = _safe_int(
        policy.get("target_word_count_after_expand"),
        int(_DEFAULT_QUALITY_POLICY["target_word_count_after_expand"]),
    )
    if target_word_count <= 0:
        target_word_count = int(_DEFAULT_QUALITY_POLICY["target_word_count_after_expand"])
    policy["target_word_count_after_expand"] = max(100, target_word_count)
    if policy["target_word_count_after_expand"] < policy["min_word_count_before_expand"]:
        policy["target_word_count_after_expand"] = policy["min_word_count_before_expand"]
    policy["word_count_adjust_score_tolerance"] = max(
        0.0,
        _safe_float(
            policy.get("word_count_adjust_score_tolerance"),
            float(_DEFAULT_QUALITY_POLICY["word_count_adjust_score_tolerance"]),
        ),
    )
    policy["severe_threshold_offset"] = max(
        0.0,
        _safe_float(policy.get("severe_threshold_offset"), float(_DEFAULT_QUALITY_POLICY["severe_threshold_offset"])),
    )
    policy["stagnation_threshold"] = max(
        0.0,
        _safe_float(policy.get("stagnation_threshold"), float(_DEFAULT_QUALITY_POLICY["stagnation_threshold"])),
    )
    policy["stagnation_count_limit"] = max(
        1,
        _safe_int(policy.get("stagnation_count_limit"), int(_DEFAULT_QUALITY_POLICY["stagnation_count_limit"])),
    )
    policy["parse_failure_streak_limit"] = max(
        1,
        _safe_int(policy.get("parse_failure_streak_limit"), int(_DEFAULT_QUALITY_POLICY["parse_failure_streak_limit"])),
    )
    for bool_key in _QUALITY_POLICY_BOOL_FIELDS:
        policy[bool_key] = _safe_bool(policy.get(bool_key), bool(_DEFAULT_QUALITY_POLICY[bool_key]))
    return policy


def normalize_config_data(config_data: Any) -> Dict[str, Any]:
    """规范化配置中的关键运行参数，避免字符串布尔/越界值导致质量门控失效。"""
    if not isinstance(config_data, dict):
        return {}

    normalized = dict(config_data)
    other_params = normalized.get("other_params", None)
    if "other_params" in normalized and isinstance(other_params, dict):
        normalized_other_params = dict(other_params)
        for bool_key in _OTHER_PARAMS_BOOL_FIELDS:
            if bool_key in normalized_other_params:
                normalized_other_params[bool_key] = _safe_bool(normalized_other_params.get(bool_key))
        if "quality_threshold" in normalized_other_params:
            normalized_other_params["quality_threshold"] = _normalize_quality_threshold(
                normalized_other_params.get("quality_threshold"),
                9.0,
            )
        if "post_batch_runtime_audit_sample_size" in normalized_other_params:
            sample_size = _safe_int(normalized_other_params.get("post_batch_runtime_audit_sample_size"), 20)
            normalized_other_params["post_batch_runtime_audit_sample_size"] = max(0, sample_size)
        for budget_key, default_budget in _ARCH_CONTEXT_BUDGET_FIELDS.items():
            if budget_key in normalized_other_params:
                normalized_other_params[budget_key] = _normalize_architecture_context_budget(
                    normalized_other_params.get(budget_key),
                    default_budget,
                )
        normalized["other_params"] = normalized_other_params

    llm_configs = normalized.get("llm_configs", None)
    if "llm_configs" in normalized and isinstance(llm_configs, dict):
        fallback_threshold = 9.0
        other_params_obj = normalized.get("other_params", {})
        if isinstance(other_params_obj, dict):
            fallback_threshold = _normalize_quality_threshold(other_params_obj.get("quality_threshold"), 9.0)
        normalized_llm_configs: Dict[str, Any] = {}
        for name, cfg in llm_configs.items():
            if not isinstance(cfg, dict):
                normalized_llm_configs[name] = cfg
                continue
            cfg_copy = dict(cfg)
            if "quality_policy" in cfg_copy:
                per_model_threshold = _normalize_quality_threshold(
                    cfg_copy.get("quality_threshold", fallback_threshold),
                    fallback_threshold,
                )
                cfg_copy["quality_policy"] = normalize_quality_policy(
                    cfg_copy.get("quality_policy"),
                    fallback_threshold=per_model_threshold,
                )
            normalized_llm_configs[name] = cfg_copy
        normalized["llm_configs"] = normalized_llm_configs

    return normalized


def load_config(config_file: str) -> Dict[str, Any]:
    """从指定的 config_file 加载配置，若不存在则创建一个默认配置文件。"""

    # PenBo 修改代码，增加配置文件不存在则创建一个默认配置文件
    if not os.path.exists(config_file):
        create_config(config_file)

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
        return normalize_config_data(loaded)
    except (json.JSONDecodeError, OSError) as error:
            logger.warning(f"加载配置失败，返回空配置: {error}")
            return {}


# PenBo 增加了创建默认配置文件函数
def create_config(config_file: str) -> Dict[str, Any]:
    """创建一个创建默认配置文件。"""
    config = {
    "last_interface_format": "OpenAI",
    "last_embedding_interface_format": "OpenAI",
    "llm_configs": {
        "DeepSeek V3": {
            "api_key": "",
            "base_url": "https://api.deepseek.com/v1",
            "model_name": "deepseek-chat",
            "temperature": 0.7,
            "max_tokens": 8192,
            "timeout": 600,
            "interface_format": "OpenAI",
            "quality_policy": {
                "default_quality_threshold": 9.0,
                "max_iterations": 10,
                "min_word_count_before_expand": 3500,
                "target_word_count_after_expand": 4000,
                "word_count_adjust_score_tolerance": 0.5,
                "severe_threshold_offset": 2.0,
                "stagnation_threshold": 0.05,
                "stagnation_count_limit": 5,
                "parse_failure_streak_limit": 3,
                "force_critic_logging_each_iteration": False
            }
        },
        "GPT 5": {
            "api_key": "",
            "base_url": "https://api.openai.com/v1",
            "model_name": "gpt-5",
            "temperature": 0.7,
            "max_tokens": 32768,
            "timeout": 600,
            "interface_format": "OpenAI",
            "quality_policy": {
                "default_quality_threshold": 9.0,
                "max_iterations": 10,
                "min_word_count_before_expand": 3500,
                "target_word_count_after_expand": 4000,
                "word_count_adjust_score_tolerance": 0.5,
                "severe_threshold_offset": 2.0,
                "stagnation_threshold": 0.05,
                "stagnation_count_limit": 5,
                "parse_failure_streak_limit": 3,
                "force_critic_logging_each_iteration": False
            }
        },
        "Gemini 2.5 Pro": {
            "api_key": "",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "model_name": "gemini-2.5-pro",
            "temperature": 0.7,
            "max_tokens": 32768,
            "timeout": 600,
            "interface_format": "OpenAI",
            "quality_policy": {
                "default_quality_threshold": 9.0,
                "max_iterations": 10,
                "min_word_count_before_expand": 3500,
                "target_word_count_after_expand": 4000,
                "word_count_adjust_score_tolerance": 0.5,
                "severe_threshold_offset": 2.0,
                "stagnation_threshold": 0.05,
                "stagnation_count_limit": 5,
                "parse_failure_streak_limit": 3,
                "force_critic_logging_each_iteration": False
            }
        }
    },
    "embedding_configs": {
        "OpenAI": {
            "api_key": "",
            "base_url": "https://api.openai.com/v1",
            "model_name": "text-embedding-ada-002",
            "retrieval_k": 4,
            "interface_format": "OpenAI"
        }
    },
    "other_params": {
        "topic": "",
        "genre": "",
        "num_chapters": 50,
        "word_number": 3000,
        "blueprint_batch_size": 5,
        "blueprint_target_score": 80.0,
        "blueprint_optimize_per_batch": False,
        "blueprint_stage_timeout": 1800,
        "blueprint_heartbeat_interval": 30,
        "blueprint_enable_critic": False,
        "blueprint_critic_threshold": 7.5,
        "blueprint_critic_trigger_margin": 8.0,
        "blueprint_full_auto_mode": True,
        "blueprint_auto_restart_on_arch_change": True,
        "blueprint_resume_auto_repair_existing": True,
        "blueprint_force_resume_skip_history_validation": False,
        "batch_partial_resume_allow_fallback": True,
        "batch_precheck_deep_scan": True,
        "batch_precheck_auto_continue_on_warning": True,
        "enable_iterative_generation": True,
        "max_iterations": 10,
        "quality_threshold": 9.0,
        "force_critic_logging_each_iteration": False,
        "enable_llm_consistency_check": True,
        "consistency_hard_gate": True,
        "enable_timeline_check": True,
        "timeline_hard_gate": True,
        "stop_batch_on_hard_gate": True,
        "post_batch_runtime_audit_enabled": False,
        "post_batch_runtime_audit_sample_size": 20,
        "architecture_context_ignore_budget": True,
        "enable_chapter_contract_guard": True,
        "chapter_contract_hard_gate": True,
        "enable_state_ledger_writeback": True,
        "state_ledger_hard_gate": True,
        "enable_next_opening_anchor_guard": True,
        "next_opening_anchor_hard_gate": True,
        "enable_output_integrity_guard": True,
        "output_integrity_hard_gate": True,
        "architecture_context_budget_chapter_prompt": 18000,
        "architecture_context_budget_consistency": 22000,
        "architecture_context_budget_quality_loop": 16000,
        "filepath": "",
        "chapter_num": "1",
        "user_guidance": "",
        "characters_involved": "",
        "key_items": "",
        "scene_location": "",
        "time_constraint": ""
    },
    "choose_configs": {
        "prompt_draft_llm": "DeepSeek V3",
        "chapter_outline_llm": "DeepSeek V3",
        "architecture_llm": "Gemini 2.5 Pro",
        "final_chapter_llm": "GPT 5",
        "consistency_review_llm": "DeepSeek V3"
    },
    "proxy_setting": {
        "proxy_url": "127.0.0.1",
        "proxy_port": "",
        "enabled": False
    },
    "webdav_config": {
        "webdav_url": "",
        "webdav_username": "",
        "webdav_password": "",
        "webdav_target_dir": "AI_Novel_Generator"
    }
}
    normalized_config = normalize_config_data(config)
    save_config(normalized_config, config_file)
    return normalized_config



def save_config(config_data: Dict[str, Any], config_file: str) -> bool:
    """将 config_data 保存到 config_file 中，返回 True/False 表示是否成功。"""
    normalized_config = normalize_config_data(config_data)
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(normalized_config, f, ensure_ascii=False, indent=4)
        return True
    except (OSError, TypeError, ValueError) as error:
        logger.error(f"保存配置失败: {error}")
        return False


class ConfigManager:
    def __init__(self, config_file: str):
        self.config_file = config_file
        self.config = self._load_config_strict()

    def _load_config_strict(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_file):
            return create_config(self.config_file)
        with open(self.config_file, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
        return normalize_config_data(loaded)

    def reload_config(self) -> None:
        self.config = self._load_config_strict()

    def update_config(self, config_data: Dict[str, Any]) -> None:
        self.config = normalize_config_data(dict(config_data))

    def save_config(self) -> bool:
        return save_config(self.config, self.config_file)

def test_llm_config(interface_format, api_key, base_url, model_name, temperature, max_tokens, timeout, log_func, handle_exception_func):
    """测试当前的LLM配置是否可用"""
    def task():
        try:
            log_func("开始测试LLM配置...")
            log_func(f"接口格式: {interface_format}")
            log_func(f"Base URL: {base_url}")
            try:
                normalized_base_url = check_base_url(str(base_url))
            except (TypeError, ValueError) as url_error:
                log_func(f"Base URL 规范化失败，使用原始值: {url_error}")
                normalized_base_url = str(base_url)
            if normalized_base_url != str(base_url):
                log_func(f"Base URL(规范化后): {normalized_base_url}")
            log_func(f"模型名称: {model_name}")
            log_func(f"API Key: {'已配置' if api_key else '未配置'}")

            llm_adapter = create_llm_adapter(
                interface_format=interface_format,
                base_url=base_url,
                model_name=model_name,
                api_key=api_key,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout
            )

            test_prompt = "Please reply 'OK'"
            log_func(f"发送测试提示: {test_prompt}")

            response = llm_adapter.invoke(test_prompt)
            if response and response.strip():
                log_func("✅ LLM配置测试成功！")
                log_func(f"测试回复: {response}")
            else:
                log_func("❌ LLM配置测试失败：未获取到响应")
                log_func("💡 可能的原因:")
                log_func("  1. API Key无效或已过期")
                log_func("  2. 网络连接问题")
                log_func("  3. 模型名称不正确")
                log_func("  4. Base URL不正确")
                log_func("  5. 请求超时")
                log_func("请检查app.log文件获取详细错误信息")
        except (RuntimeError, ValueError, TypeError, ConnectionError, OSError) as e:
            log_func(f"❌ LLM配置测试出错: {str(e)}")
            error_text = str(e).lower()
            if "cloudflare" in error_text or "you have been blocked" in error_text:
                log_func("⚠️ 检测到 Cloudflare/WAF 拦截。")
                log_func("💡 额外检查项:")
                log_func("  1. 确认 Base URL 为 https://<gateway>/v1")
                log_func("  2. 在网关侧放行当前出口IP，或关闭Bot挑战")
                log_func("  3. 核对网关是否支持 OpenAI Responses API")
            log_func("💡 请检查:")
            log_func("  1. API Key格式是否正确")
            log_func("  2. 网络连接是否正常")
            log_func("  3. 模型服务是否可用")
            handle_exception_func("测试LLM配置时出错")

    threading.Thread(target=task, daemon=True).start()

def test_embedding_config(api_key, base_url, interface_format, model_name, log_func, handle_exception_func):
    """测试当前的Embedding配置是否可用"""
    def task():
        try:
            log_func("开始测试Embedding配置...")
            embedding_adapter = create_embedding_adapter(
                interface_format=interface_format,
                api_key=api_key,
                base_url=base_url,
                model_name=model_name
            )

            test_text = "测试文本"
            embeddings = embedding_adapter.embed_query(test_text)
            if embeddings and len(embeddings) > 0:
                log_func("✅ Embedding配置测试成功！")
                log_func(f"生成的向量维度: {len(embeddings)}")
            else:
                log_func("❌ Embedding配置测试失败：未获取到向量")
        except (RuntimeError, ValueError, TypeError, ConnectionError, OSError) as e:
            log_func(f"❌ Embedding配置测试出错: {str(e)}")
            handle_exception_func("测试Embedding配置时出错")

    threading.Thread(target=task, daemon=True).start()
