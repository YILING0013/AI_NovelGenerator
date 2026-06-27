# config_manager.py
# -*- coding: utf-8 -*-
import json
import os
import logging
import tempfile
import threading
from copy import deepcopy

from llm_output_cleaning import remove_think_tags

IS_ENGLISH = False
_config_lock = threading.RLock()

DEFAULT_LLM_CONFIG_NAME = "DeepSeek V4 Flash"
DEFAULT_EMBEDDING_CONFIG_NAME = "OpenAI"

GENERATION_CONFIG_KEYS = (
    "prompt_draft_llm",
    "chapter_outline_llm",
    "architecture_llm",
    "final_chapter_llm",
    "consistency_review_llm",
)

LEGACY_LLM_CONFIG_NAME_MAP = {
    "DeepSeek V3": "DeepSeek V4 Flash",
    "Gemini 2.0 Flash": "Gemini 3.5 Flash",
    "Gemini 2.5 Flash": "Gemini 3.5 Flash",
    "Gemini 2.5 Pro": "Gemini 3.5 Flash",
    "GPT 5": "OpenAI GPT 5.5",
}

DEFAULT_CONFIG = {
    "last_llm_config_name": DEFAULT_LLM_CONFIG_NAME,
    "last_interface_format": "DeepSeek",
    "last_embedding_interface_format": DEFAULT_EMBEDDING_CONFIG_NAME,
    "llm_configs": {
        "DeepSeek V4 Flash": {
            "api_key": "",
            "base_url": "https://api.deepseek.com",
            "model_name": "deepseek-v4-flash",
            "temperature": 0.7,
            "max_tokens": 8192,
            "timeout": 600,
            "interface_format": "DeepSeek"
        },
        "DeepSeek V4 Pro": {
            "api_key": "",
            "base_url": "https://api.deepseek.com",
            "model_name": "deepseek-v4-pro",
            "temperature": 0.7,
            "max_tokens": 32768,
            "timeout": 600,
            "interface_format": "DeepSeek"
        },
        "Gemini 3.5 Flash": {
            "api_key": "",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "model_name": "gemini-3.5-flash",
            "temperature": 0.7,
            "max_tokens": 32768,
            "timeout": 600,
            "interface_format": "Gemini"
        },
        "Gemini 3.1 Pro Preview": {
            "api_key": "",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "model_name": "gemini-3.1-pro-preview",
            "temperature": 0.7,
            "max_tokens": 32768,
            "timeout": 600,
            "interface_format": "Gemini"
        },
        "OpenAI GPT 5.5": {
            "api_key": "",
            "base_url": "https://api.openai.com/v1",
            "model_name": "gpt-5.5",
            "temperature": 0.7,
            "max_tokens": 32768,
            "timeout": 600,
            "interface_format": "OpenAI"
        }
    },
    "embedding_configs": {
        "OpenAI": {
            "api_key": "",
            "base_url": "https://api.openai.com/v1",
            "model_name": "text-embedding-3-small",
            "retrieval_k": 4,
            "interface_format": "OpenAI"
        },
        "Gemini": {
            "api_key": "",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "model_name": "gemini-embedding-2",
            "retrieval_k": 4,
            "interface_format": "Gemini"
        }
    },
    "other_params": {
        "topic": "",
        "genre": "",
        "num_chapters": 0,
        "word_number": 0,
        "filepath": "",
        "chapter_num": "120",
        "user_guidance": "",
        "characters_involved": "",
        "key_items": "",
        "scene_location": "",
        "time_constraint": ""
    },
    "choose_configs": {
        "prompt_draft_llm": "DeepSeek V4 Flash",
        "chapter_outline_llm": "Gemini 3.5 Flash",
        "architecture_llm": "Gemini 3.5 Flash",
        "final_chapter_llm": "DeepSeek V4 Pro",
        "consistency_review_llm": "DeepSeek V4 Flash"
    },
    "proxy_setting": {
        "proxy_url": "127.0.0.1",
        "proxy_port": "",
        "enabled": False
    },
    "webdav_config": {
        "webdav_url": "",
        "webdav_username": "",
        "webdav_password": ""
    }
}


def get_default_config() -> dict:
    """返回新的默认配置副本，避免调用方意外修改全局模板。"""
    return deepcopy(DEFAULT_CONFIG)


def _merge_missing_values(target: dict, defaults: dict) -> dict:
    """只补缺失键，不覆盖用户已有值。"""
    for key, value in defaults.items():
        if key not in target:
            target[key] = deepcopy(value)
        elif isinstance(target[key], dict) and isinstance(value, dict):
            _merge_missing_values(target[key], value)
    return target


def _first_config_name(configs: dict) -> str:
    return next(iter(configs), DEFAULT_LLM_CONFIG_NAME)


def normalize_config(config_data: dict) -> dict:
    """补齐配置结构，并把已知过期任务选择迁移到当前默认预设。"""
    if not isinstance(config_data, dict):
        config_data = {}

    defaults = get_default_config()

    for section_name in ("llm_configs", "embedding_configs"):
        if not isinstance(config_data.get(section_name), dict):
            config_data[section_name] = {}
        _merge_missing_values(config_data[section_name], defaults[section_name])

    for section_name in ("other_params", "proxy_setting", "webdav_config"):
        if not isinstance(config_data.get(section_name), dict):
            config_data[section_name] = {}
        _merge_missing_values(config_data[section_name], defaults[section_name])

    llm_configs = config_data["llm_configs"]
    last_llm_config_name = config_data.get("last_llm_config_name")
    if last_llm_config_name in LEGACY_LLM_CONFIG_NAME_MAP:
        last_llm_config_name = LEGACY_LLM_CONFIG_NAME_MAP[last_llm_config_name]
    if last_llm_config_name not in llm_configs:
        legacy_last = config_data.get("last_interface_format")
        if legacy_last in llm_configs:
            last_llm_config_name = legacy_last
        elif DEFAULT_LLM_CONFIG_NAME in llm_configs:
            last_llm_config_name = DEFAULT_LLM_CONFIG_NAME
        else:
            last_llm_config_name = _first_config_name(llm_configs)
    config_data["last_llm_config_name"] = last_llm_config_name
    config_data["last_interface_format"] = llm_configs.get(last_llm_config_name, {}).get("interface_format", "OpenAI")

    embedding_configs = config_data["embedding_configs"]
    last_embedding = config_data.get("last_embedding_interface_format")
    if last_embedding not in embedding_configs:
        last_embedding = DEFAULT_EMBEDDING_CONFIG_NAME if DEFAULT_EMBEDDING_CONFIG_NAME in embedding_configs else _first_config_name(embedding_configs)
    config_data["last_embedding_interface_format"] = last_embedding

    if not isinstance(config_data.get("choose_configs"), dict):
        config_data["choose_configs"] = {}
    choose_configs = config_data["choose_configs"]
    for key in GENERATION_CONFIG_KEYS:
        selected_name = choose_configs.get(key)
        selected_name = LEGACY_LLM_CONFIG_NAME_MAP.get(selected_name, selected_name)
        if selected_name not in llm_configs:
            selected_name = defaults["choose_configs"].get(key, last_llm_config_name)
        if selected_name not in llm_configs:
            selected_name = last_llm_config_name
        choose_configs[key] = selected_name

    return config_data


def validate_choose_configs(config_data: dict) -> list[str]:
    """返回任务模型选择中指向不存在配置的错误列表。"""
    errors = []
    llm_configs = config_data.get("llm_configs", {})
    choose_configs = config_data.get("choose_configs", {})
    for key in GENERATION_CONFIG_KEYS:
        selected_name = choose_configs.get(key)
        if selected_name not in llm_configs:
            errors.append(f"{key} 指向不存在的 LLM 配置: {selected_name}")
    return errors


def load_config(config_file: str) -> dict:
    """从指定的 config_file 加载配置，若不存在则创建一个默认配置文件。"""

    # PenBo 修改代码，增加配置文件不存在则创建一个默认配置文件
    if not os.path.exists(config_file):
        create_config(config_file)

    try:
        with _config_lock:
            with open(config_file, 'r', encoding='utf-8') as f:
                return normalize_config(json.load(f))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logging.error(f"配置文件格式错误: {e}")
        return {}
    except (IOError, OSError) as e:
        logging.error(f"无法读取配置文件: {e}")
        return {}


# PenBo 增加了创建默认配置文件函数
def create_config(config_file: str) -> dict:
    """创建一个创建默认配置文件。"""
    config = get_default_config()
    save_config(config, config_file)
    return config



def save_config(config_data: dict, config_file: str) -> bool:
    """将 config_data 保存到 config_file 中（原子写入），返回 True/False 表示是否成功。"""
    try:
        with _config_lock:
            dir_name = os.path.dirname(os.path.abspath(config_file))
            fd, temp_path = tempfile.mkstemp(suffix='.json', dir=dir_name)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(config_data, f, ensure_ascii=False, indent=4)
                os.replace(temp_path, config_file)
            except Exception:
                os.unlink(temp_path)
                raise
        return True
    except (IOError, OSError) as e:
        logging.error(f"无法保存配置文件: {e}")
        return False

def test_llm_config(interface_format, api_key, base_url, model_name, temperature, max_tokens, timeout, log_func, handle_exception_func):
    """测试当前的LLM配置是否可用"""
    def task():
        try:
            log_func("开始测试LLM配置...")
            from llm_adapters import create_llm_adapter

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
            response = llm_adapter.invoke(test_prompt)
            if response:
                response = remove_think_tags(response).strip()
            if response:
                log_func("✅ LLM配置测试成功！")
                log_func(f"测试回复: {response}")
            else:
                log_func("❌ LLM配置测试失败：未获取到响应")
        except Exception as e:
            log_func(f"❌ LLM配置测试出错: {str(e)}")
            handle_exception_func("测试LLM配置时出错")

    threading.Thread(target=task, daemon=True).start()

def test_embedding_config(api_key, base_url, interface_format, model_name, log_func, handle_exception_func):
    """测试当前的Embedding配置是否可用"""
    def task():
        try:
            log_func("开始测试Embedding配置...")
            from embedding_adapters import create_embedding_adapter

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
        except Exception as e:
            log_func(f"❌ Embedding配置测试出错: {str(e)}")
            handle_exception_func("测试Embedding配置时出错")

    threading.Thread(target=task, daemon=True).start()
