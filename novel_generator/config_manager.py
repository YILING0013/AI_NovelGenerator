# novel_generator/config_manager.py
# -*- coding: utf-8 -*-
"""
统一配置管理器 - 单例模式

本模块提供线程安全的单例配置管理器，统一管理所有LLM、Embedding和小说生成配置。
解决配置分散在多个文件、重复验证逻辑、无热重载等问题。

主要功能：
1. 单例模式确保全局唯一配置实例
2. 线程安全的配置读写
3. 配置验证和默认值管理
4. 配置文件热重载
5. 配置缓存和性能优化
6. 敏感信息保护

使用方式：
    from novel_generator.config_manager import ConfigManager

    # 获取单例实例
    config = ConfigManager()

    # 获取LLM配置
    llm_config = config.get_llm_config("智谱AI GLM-4.7")

    # 获取选定的架构生成LLM配置
    arch_config = config.get_architecture_llm_config()

作者: AI架构重构团队
创建日期: 2026-01-04
"""

import json
import os
import threading
import hashlib
import logging
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from dataclasses import dataclass, field


# ============================================
# 日志配置
# ============================================

logger = logging.getLogger(__name__)


# ============================================
# 数据类定义
# ============================================

@dataclass
class LLMConfig:
    """LLM配置数据类"""
    id: str = ""
    api_key: str = ""
    base_url: str = ""
    model_name: str = ""
    temperature: float = 0.7
    max_tokens: int = 8192
    timeout: int = 600
    interface_format: str = "OpenAI"
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'api_key': self.api_key,
            'base_url': self.base_url,
            'model_name': self.model_name,
            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
            'timeout': self.timeout,
            'interface_format': self.interface_format,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LLMConfig':
        """从字典创建"""
        return cls(
            id=data.get('id', ''),
            api_key=data.get('api_key', ''),
            base_url=data.get('base_url', ''),
            model_name=data.get('model_name', ''),
            temperature=data.get('temperature', 0.7),
            max_tokens=data.get('max_tokens', 8192),
            timeout=data.get('timeout', 600),
            interface_format=data.get('interface_format', 'OpenAI'),
            created_at=data.get('created_at', ''),
            updated_at=data.get('updated_at', '')
        )

    def validate(self) -> Tuple[bool, str]:
        """
        验证配置有效性

        Returns:
            (is_valid, error_message)
        """
        if not self.api_key:
            return False, "API Key不能为空"
        if not self.base_url:
            return False, "Base URL不能为空"
        if not self.model_name:
            return False, "模型名称不能为空"
        if self.temperature < 0 or self.temperature > 2:
            return False, f"Temperature必须在0-2之间，当前值: {self.temperature}"
        if self.max_tokens <= 0:
            return False, f"Max Tokens必须大于0，当前值: {self.max_tokens}"
        if self.timeout <= 0:
            return False, f"Timeout必须大于0，当前值: {self.timeout}"
        return True, ""


@dataclass
class EmbeddingConfig:
    """Embedding配置数据类"""
    api_key: str = ""
    base_url: str = ""
    model_name: str = ""
    retrieval_k: int = 4
    interface_format: str = "OpenAI"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'api_key': self.api_key,
            'base_url': self.base_url,
            'model_name': self.model_name,
            'retrieval_k': self.retrieval_k,
            'interface_format': self.interface_format
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EmbeddingConfig':
        """从字典创建"""
        return cls(
            api_key=data.get('api_key', ''),
            base_url=data.get('base_url', ''),
            model_name=data.get('model_name', ''),
            retrieval_k=data.get('retrieval_k', 4),
            interface_format=data.get('interface_format', 'OpenAI')
        )

    def validate(self) -> Tuple[bool, str]:
        """验证配置有效性"""
        if not self.api_key:
            return False, "API Key不能为空"
        if not self.base_url:
            return False, "Base URL不能为空"
        if not self.model_name:
            return False, "模型名称不能为空"
        if self.retrieval_k <= 0:
            return False, f"Retrieval K必须大于0，当前值: {self.retrieval_k}"
        return True, ""


@dataclass
class NovelParams:
    """小说生成参数"""
    topic: str = ""
    genre: str = ""
    num_chapters: int = 50
    word_number: int = 3000
    filepath: str = ""
    chapter_num: str = "1"
    user_guidance: str = ""
    characters_involved: str = ""
    key_items: str = ""
    scene_location: str = ""
    time_constraint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'topic': self.topic,
            'genre': self.genre,
            'num_chapters': self.num_chapters,
            'word_number': self.word_number,
            'filepath': self.filepath,
            'chapter_num': self.chapter_num,
            'user_guidance': self.user_guidance,
            'characters_involved': self.characters_involved,
            'key_items': self.key_items,
            'scene_location': self.scene_location,
            'time_constraint': self.time_constraint
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NovelParams':
        """从字典创建"""
        return cls(
            topic=data.get('topic', ''),
            genre=data.get('genre', ''),
            num_chapters=data.get('num_chapters', 50),
            word_number=data.get('word_number', 3000),
            filepath=data.get('filepath', ''),
            chapter_num=data.get('chapter_num', '1'),
            user_guidance=data.get('user_guidance', ''),
            characters_involved=data.get('characters_involved', ''),
            key_items=data.get('key_items', ''),
            scene_location=data.get('scene_location', ''),
            time_constraint=data.get('time_constraint', '')
        )

    def validate(self) -> Tuple[bool, str]:
        """验证参数有效性"""
        if not self.filepath:
            return False, "文件路径不能为空"
        if self.num_chapters <= 0:
            return False, f"章节数量必须大于0，当前值: {self.num_chapters}"
        if self.word_number <= 0:
            return False, f"字数目标必须大于0，当前值: {self.word_number}"
        return True, ""


# ============================================
# 单例配置管理器
# ============================================

class ConfigManager:
    """
    统一配置管理器 - 线程安全单例模式

    该类管理所有配置的加载、验证、缓存和热重载。
    使用双重检查锁定模式实现线程安全的单例。

    Attributes:
        _config_file: 配置文件路径
        _config: 当前配置字典
        _config_hash: 配置文件哈希值（用于检测变更）
        _cache: 配置对象缓存
        _lock: 线程锁
    """

    # 类变量，用于单例实现
    _instance: Optional['ConfigManager'] = None
    _lock = threading.Lock()

    def __new__(cls, config_file: Optional[str] = None) -> 'ConfigManager':
        """
        单例实现 - 双重检查锁定

        Args:
            config_file: 配置文件路径（仅首次创建时有效）

        Returns:
            ConfigManager单例实例
        """
        if cls._instance is None:
            with cls._lock:
                # 双重检查
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialize(config_file)
                    cls._instance = instance
                    logger.info("ConfigManager单例已创建")
        return cls._instance

    def _initialize(self, config_file: Optional[str]) -> None:
        """
        初始化实例（仅在首次创建时调用）

        Args:
            config_file: 配置文件路径
        """
        # 确定配置文件路径
        if config_file is None:
            config_file = self._find_config_file()

        self._config_file = config_file
        self._config: Dict[str, Any] = {}
        self._config_hash: str = ""
        self._cache: Dict[str, Any] = {}
        self._config_lock = threading.RLock()

        # 加载配置
        self._load_config()

        logger.info(f"ConfigManager初始化完成，配置文件: {self._config_file}")

    @staticmethod
    def _find_config_file() -> str:
        """
        查找配置文件

        按优先级查找：
        1. 当前目录的 config.json
        2. 用户主目录的 .ai_novel_generator/config.json
        3. 创建默认配置文件

        Returns:
            配置文件路径
        """
        # 1. 当前目录
        current_dir = Path.cwd()
        config_path = current_dir / "config.json"
        if config_path.exists():
            return str(config_path)

        # 2. 项目根目录（通过main.py判断）
        script_dir = Path(__file__).parent.parent
        config_path = script_dir / "config.json"
        if config_path.exists():
            return str(config_path)

        # 3. 创建默认配置
        return str(config_path)

    def _load_config(self, force: bool = False) -> None:
        """
        加载配置文件

        Args:
            force: 是否强制重新加载
        """
        with self._config_lock:
            # 检查文件是否存在
            if not os.path.exists(self._config_file):
                logger.warning(f"配置文件不存在: {self._config_file}，创建默认配置")
                self._create_default_config()
                return

            # 计算文件哈希
            try:
                with open(self._config_file, 'rb') as f:
                    file_hash = hashlib.md5(f.read()).hexdigest()
            except Exception as e:
                logger.error(f"计算配置文件哈希失败: {e}")
                file_hash = ""

            # 检查是否需要重新加载
            if not force and self._config_hash == file_hash:
                return  # 配置未变更

            # 加载配置
            try:
                with open(self._config_file, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
                self._config_hash = file_hash
                self._cache.clear()  # 清除缓存
                logger.info(f"配置已加载: {self._config_file}")
            except json.JSONDecodeError as e:
                logger.error(f"配置文件JSON解析失败: {e}")
                self._config = {}
            except Exception as e:
                logger.error(f"加载配置文件失败: {e}")
                self._config = {}

    def _create_default_config(self) -> None:
        """创建默认配置文件"""
        default_config = {
            "last_interface_format": "OpenAI",
            "last_embedding_interface_format": "OpenAI",
            "llm_configs": {
                "DeepSeek V3": {
                    "id": "",
                    "api_key": "",
                    "base_url": "https://api.deepseek.com/v1",
                    "model_name": "deepseek-chat",
                    "temperature": 0.7,
                    "max_tokens": 8192,
                    "timeout": 600,
                    "interface_format": "OpenAI",
                    "created_at": "",
                    "updated_at": ""
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
                "architecture_llm": "DeepSeek V3",
                "final_chapter_llm": "DeepSeek V3",
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
                "webdav_password": ""
            }
        }

        try:
            with open(self._config_file, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, indent=4)
            self._config = default_config
            logger.info(f"默认配置已创建: {self._config_file}")
        except Exception as e:
            logger.error(f"创建默认配置失败: {e}")
            self._config = {}

    # ============================================
    # 公共API - LLM配置
    # ============================================

    def reload(self) -> None:
        """强制重新加载配置文件"""
        self._load_config(force=True)
        logger.info("配置已强制重新加载")

    def get_all_llm_names(self) -> List[str]:
        """
        获取所有LLM配置名称

        Returns:
            LLM配置名称列表
        """
        self._load_config()  # 检查配置是否变更
        return list(self._config.get("llm_configs", {}).keys())

    def get_llm_config(self, llm_name: str, use_cache: bool = True) -> Optional[LLMConfig]:
        """
        获取指定LLM的配置

        Args:
            llm_name: LLM配置名称
            use_cache: 是否使用缓存

        Returns:
            LLMConfig对象，配置不存在时返回None
        """
        cache_key = f"llm_{llm_name}"

        # 检查缓存
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        with self._config_lock:
            llm_configs = self._config.get("llm_configs", {})
            if llm_name not in llm_configs:
                logger.warning(f"LLM配置不存在: {llm_name}")
                return None

            config_data = llm_configs[llm_name]
            config = LLMConfig.from_dict(config_data)

            # 验证配置
            is_valid, error_msg = config.validate()
            if not is_valid:
                logger.warning(f"LLM配置验证失败 ({llm_name}): {error_msg}")

            # 缓存配置
            if use_cache:
                self._cache[cache_key] = config

            return config

    def get_architecture_llm_config(self) -> Optional[LLMConfig]:
        """获取架构生成LLM配置"""
        llm_name = self._config.get("choose_configs", {}).get("architecture_llm")
        if not llm_name:
            logger.warning("未配置架构生成LLM")
            return None
        return self.get_llm_config(llm_name)

    def get_outline_llm_config(self) -> Optional[LLMConfig]:
        """获取章节大纲LLM配置"""
        llm_name = self._config.get("choose_configs", {}).get("chapter_outline_llm")
        if not llm_name:
            logger.warning("未配置章节大纲LLM")
            return None
        return self.get_llm_config(llm_name)

    def get_draft_llm_config(self) -> Optional[LLMConfig]:
        """获取草稿生成LLM配置"""
        llm_name = self._config.get("choose_configs", {}).get("prompt_draft_llm")
        if not llm_name:
            logger.warning("未配置草稿生成LLM")
            return None
        return self.get_llm_config(llm_name)

    def get_final_llm_config(self) -> Optional[LLMConfig]:
        """获取定稿生成LLM配置"""
        llm_name = self._config.get("choose_configs", {}).get("final_chapter_llm")
        if not llm_name:
            logger.warning("未配置定稿生成LLM")
            return None
        return self.get_llm_config(llm_name)

    def get_consistency_llm_config(self) -> Optional[LLMConfig]:
        """获取一致性检查LLM配置"""
        llm_name = self._config.get("choose_configs", {}).get("consistency_review_llm")
        if not llm_name:
            logger.warning("未配置一致性检查LLM")
            return None
        return self.get_llm_config(llm_name)

    def get_quality_loop_llm_config(self) -> Optional[LLMConfig]:
        """获取质量循环LLM配置"""
        llm_name = self._config.get("choose_configs", {}).get("quality_loop_llm")
        if not llm_name:
            logger.warning("未配置质量循环LLM")
            return None
        return self.get_llm_config(llm_name)

    def get_critique_llm_config(self) -> Optional[LLMConfig]:
        """获取评论LLM配置"""
        llm_name = self._config.get("choose_configs", {}).get("critique_llm")
        if not llm_name:
            logger.warning("未配置评论LLM")
            return None
        return self.get_llm_config(llm_name)

    # ============================================
    # 公共API - Embedding配置
    # ============================================

    def get_all_embedding_names(self) -> List[str]:
        """获取所有Embedding配置名称"""
        self._load_config()
        return list(self._config.get("embedding_configs", {}).keys())

    def get_embedding_config(self, embedding_name: str, use_cache: bool = True) -> Optional[EmbeddingConfig]:
        """
        获取指定Embedding的配置

        Args:
            embedding_name: Embedding配置名称
            use_cache: 是否使用缓存

        Returns:
            EmbeddingConfig对象，配置不存在时返回None
        """
        cache_key = f"embedding_{embedding_name}"

        # 检查缓存
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        with self._config_lock:
            embedding_configs = self._config.get("embedding_configs", {})
            if embedding_name not in embedding_configs:
                logger.warning(f"Embedding配置不存在: {embedding_name}")
                return None

            config_data = embedding_configs[embedding_name]
            config = EmbeddingConfig.from_dict(config_data)

            # 验证配置
            is_valid, error_msg = config.validate()
            if not is_valid:
                logger.warning(f"Embedding配置验证失败 ({embedding_name}): {error_msg}")

            # 缓存配置
            if use_cache:
                self._cache[cache_key] = config

            return config

    def get_default_embedding_config(self) -> Optional[EmbeddingConfig]:
        """获取默认Embedding配置"""
        last_name = self._config.get("last_embedding_interface_format", "OpenAI")
        return self.get_embedding_config(last_name)

    # ============================================
    # 公共API - 小说参数
    # ============================================

    def get_novel_params(self, use_cache: bool = True) -> NovelParams:
        """
        获取小说生成参数

        Args:
            use_cache: 是否使用缓存

        Returns:
            NovelParams对象
        """
        cache_key = "novel_params"

        # 检查缓存
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        with self._config_lock:
            other_params = self._config.get("other_params", {})
            params = NovelParams.from_dict(other_params)

            # 缓存
            if use_cache:
                self._cache[cache_key] = params

            return params

    def update_novel_param(self, key: str, value: Any) -> bool:
        """
        更新单个小说参数

        Args:
            key: 参数键
            value: 参数值

        Returns:
            是否更新成功
        """
        with self._config_lock:
            if "other_params" not in self._config:
                self._config["other_params"] = {}

            self._config["other_params"][key] = value
            self._cache.pop("novel_params", None)  # 清除缓存

            return self._save_config()

    # ============================================
    # 公共API - 代理配置
    # ============================================

    def get_proxy_config(self) -> Dict[str, Any]:
        """
        获取代理配置

        Returns:
            代理配置字典
        """
        return self._config.get("proxy_setting", {
            "proxy_url": "127.0.0.1",
            "proxy_port": "",
            "enabled": False
        })

    def is_proxy_enabled(self) -> bool:
        """检查是否启用代理"""
        proxy_config = self.get_proxy_config()
        return proxy_config.get("enabled", False)

    # ============================================
    # 公共API - WebDAV配置
    # ============================================

    def get_webdav_config(self) -> Dict[str, Any]:
        """获取WebDAV配置"""
        return self._config.get("webdav_config", {
            "webdav_url": "",
            "webdav_username": "",
            "webdav_password": ""
        })

    # ============================================
    # 公共API - 配置持久化
    # ============================================

    def _save_config(self) -> bool:
        """
        保存配置到文件

        Returns:
            是否保存成功
        """
        try:
            with open(self._config_file, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, ensure_ascii=False, indent=4)
            logger.info("配置已保存")
            return True
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            return False

    def save_llm_config(self, llm_name: str, config: LLMConfig) -> bool:
        """
        保存LLM配置

        Args:
            llm_name: LLM配置名称
            config: LLMConfig对象

        Returns:
            是否保存成功
        """
        with self._config_lock:
            if "llm_configs" not in self._config:
                self._config["llm_configs"] = {}

            self._config["llm_configs"][llm_name] = config.to_dict()
            self._cache.pop(f"llm_{llm_name}", None)  # 清除缓存

            return self._save_config()

    def save_embedding_config(self, embedding_name: str, config: EmbeddingConfig) -> bool:
        """保存Embedding配置"""
        with self._config_lock:
            if "embedding_configs" not in self._config:
                self._config["embedding_configs"] = {}

            self._config["embedding_configs"][embedding_name] = config.to_dict()
            self._cache.pop(f"embedding_{embedding_name}", None)

            return self._save_config()

    # ============================================
    # 公共API - 配置摘要
    # ============================================

    def get_config_summary(self) -> Dict[str, Any]:
        """
        获取配置摘要（不包含敏感信息）

        Returns:
            配置摘要字典
        """
        summary = {
            "config_file": self._config_file,
            "llm_configs": [],
            "embedding_configs": [],
            "novel_params": {},
            "choose_configs": self._config.get("choose_configs", {}),
            "proxy_enabled": self.is_proxy_enabled()
        }

        # LLM配置摘要（不包含API Key）
        for name in self.get_all_llm_names():
            config = self.get_llm_config(name, use_cache=False)
            if config:
                summary["llm_configs"].append({
                    "name": name,
                    "model_name": config.model_name,
                    "interface_format": config.interface_format,
                    "temperature": config.temperature,
                    "max_tokens": config.max_tokens
                })

        # Embedding配置摘要
        for name in self.get_all_embedding_names():
            config = self.get_embedding_config(name, use_cache=False)
            if config:
                summary["embedding_configs"].append({
                    "name": name,
                    "model_name": config.model_name,
                    "interface_format": config.interface_format,
                    "retrieval_k": config.retrieval_k
                })

        # 小说参数摘要
        params = self.get_novel_params(use_cache=False)
        summary["novel_params"] = {
            "topic": params.topic[:50] + "..." if len(params.topic) > 50 else params.topic,
            "genre": params.genre,
            "num_chapters": params.num_chapters,
            "word_number": params.word_number,
            "filepath": params.filepath
        }

        return summary

    def invalidate_cache(self) -> None:
        """清除所有缓存"""
        self._cache.clear()
        logger.info("配置缓存已清除")


# ============================================
# 便捷函数
# ============================================

def get_config_manager() -> ConfigManager:
    """
    获取ConfigManager单例实例

    Returns:
        ConfigManager单例
    """
    return ConfigManager()


# ============================================
# 测试代码
# ============================================

if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 测试单例
    config1 = ConfigManager()
    config2 = ConfigManager()
    print(f"单例测试: {config1 is config2}")  # 应该输出 True

    # 获取配置摘要
    summary = config1.get_config_summary()
    print(f"\n配置摘要:")
    print(f"LLM配置数量: {len(summary['llm_configs'])}")
    print(f"Embedding配置数量: {len(summary['embedding_configs'])}")
    print(f"选定的架构LLM: {summary['choose_configs'].get('architecture_llm')}")

    # 获取LLM配置
    arch_config = config1.get_architecture_llm_config()
    if arch_config:
        print(f"\n架构LLM配置:")
        print(f"  模型: {arch_config.model_name}")
        print(f"  Base URL: {arch_config.base_url}")
        print(f"  Temperature: {arch_config.temperature}")

    # 获取小说参数
    params = config1.get_novel_params()
    print(f"\n小说参数:")
    print(f"  主题: {params.topic[:50]}...")
    print(f"  章节数: {params.num_chapters}")
    print(f"  字数目标: {params.word_number}")
