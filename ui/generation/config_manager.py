"""
Configuration Manager
配置管理器类

负责管理LLM配置、参数设置和配置验证等功能。
这是所有其他组件的基础，因为它们都需要依赖配置信息。

主要功能:
- 获取草稿生成配置
- 获取定稿生成配置
- 配置有效性验证
- 配置缓存和热重载
"""

from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class ConfigurationManager:
    """配置管理器类 - 统一管理所有LLM配置"""

    def __init__(self, ui_instance):
        """
        初始化配置管理器

        Args:
            ui_instance: GUI实例，用于获取配置变量
        """
        self.ui = ui_instance
        self._config_cache = {}  # 配置缓存
        self._last_config_hash = None  # 上次配置哈希，用于检测变更

        logger.info("ConfigurationManager 初始化完成")

    def get_draft_config(self) -> Dict[str, Any]:
        """
        获取草稿生成配置

        Returns:
            Dict[str, Any]: 草稿生成配置字典
            - interface_format: LLM接口格式
            - api_key: API密钥
            - base_url: 基础URL
            - model_name: 模型名称
            - temperature: 温度参数
            - max_tokens: 最大token数
            - timeout: 超时时间

        Raises:
            ValueError: 当配置无效时
        """
        config_key = 'draft'

        # 检查缓存
        if self._is_cache_valid(config_key):
            return self._config_cache[config_key]

        try:
            # 从UI获取配置
            llm_name = self.ui.prompt_draft_llm_var.get()
            if not llm_name:
                raise ValueError("草稿LLM配置未选择")

            llm_config = self.ui.loaded_config["llm_configs"][llm_name]
            if not llm_config:
                raise ValueError(f"草稿LLM配置 '{llm_name}' 不存在")

            # 构建标准配置
            config = {
                'interface_format': llm_config.get("interface_format", ""),
                'api_key': llm_config.get("api_key", ""),
                'base_url': llm_config.get("base_url", ""),
                'model_name': llm_config.get("model_name", ""),
                'temperature': llm_config.get("temperature", 0.7),
                'max_tokens': llm_config.get("max_tokens", 60000),
                'timeout': llm_config.get("timeout", 600)
            }

            # 验证配置有效性
            self._validate_llm_config(config, "草稿")

            # 缓存配置
            self._config_cache[config_key] = config
            logger.info(f"成功获取草稿配置: {llm_name}")

            return config

        except Exception as e:
            logger.error(f"获取草稿配置失败: {e}")
            raise ValueError(f"草稿配置无效: {e}")

    def get_final_config(self) -> Dict[str, Any]:
        """
        获取定稿生成配置

        Returns:
            Dict[str, Any]: 定稿生成配置字典

        Raises:
            ValueError: 当配置无效时
        """
        config_key = 'final'

        # 检查缓存
        if self._is_cache_valid(config_key):
            return self._config_cache[config_key]

        try:
            # 从UI获取配置
            llm_name = self.ui.final_chapter_llm_var.get()
            if not llm_name:
                raise ValueError("定稿LLM配置未选择")

            llm_config = self.ui.loaded_config["llm_configs"][llm_name]
            if not llm_config:
                raise ValueError(f"定稿LLM配置 '{llm_name}' 不存在")

            # 构建标准配置
            config = {
                'interface_format': llm_config.get("interface_format", ""),
                'api_key': llm_config.get("api_key", ""),
                'base_url': llm_config.get("base_url", ""),
                'model_name': llm_config.get("model_name", ""),
                'temperature': llm_config.get("temperature", 0.7),
                'max_tokens': llm_config.get("max_tokens", 60000),
                'timeout': llm_config.get("timeout", 600)
            }

            # 验证配置有效性
            self._validate_llm_config(config, "定稿")

            # 缓存配置
            self._config_cache[config_key] = config
            logger.info(f"成功获取定稿配置: {llm_name}")

            return config

        except Exception as e:
            logger.error(f"获取定稿配置失败: {e}")
            raise ValueError(f"定稿配置无效: {e}")

    def get_embedding_config(self) -> Dict[str, Any]:
        """
        获取Embedding配置

        Returns:
            Dict[str, Any]: Embedding配置字典
        """
        config_key = 'embedding'

        # 检查缓存
        if self._is_cache_valid(config_key):
            return self._config_cache[config_key]

        try:
            # 从UI获取配置
            embedding_name = self.ui.embedding_llm_var.get()
            if not embedding_name:
                raise ValueError("Embedding配置未选择")

            embedding_config = self.ui.loaded_config["embedding_configs"][embedding_name]
            if not embedding_config:
                raise ValueError(f"Embedding配置 '{embedding_name}' 不存在")

            # 构建标准配置
            config = {
                'interface_format': embedding_config.get("interface_format", ""),
                'api_key': embedding_config.get("api_key", ""),
                'base_url': embedding_config.get("base_url", ""),
                'model_name': embedding_config.get("model_name", ""),
                'timeout': embedding_config.get("timeout", 120)
            }

            # 验证配置有效性
            self._validate_llm_config(config, "Embedding")

            # 缓存配置
            self._config_cache[config_key] = config
            logger.info(f"成功获取Embedding配置: {embedding_name}")

            return config

        except Exception as e:
            logger.error(f"获取Embedding配置失败: {e}")
            raise ValueError(f"Embedding配置无效: {e}")

    def get_novel_parameters(self) -> Dict[str, Any]:
        """
        获取小说生成参数

        Returns:
            Dict[str, Any]: 小说参数字典
        """
        try:
            # 基础参数
            params = {
                'filepath': self.ui.filepath_var.get().strip(),
                'user_guidance': self.ui.user_guide_text.get("0.0", "end").strip(),
                'characters_involved': self.ui.characters_involved_var.get().strip(),
                'key_items': self.ui.key_items_var.get().strip(),
                'scene_location': self.ui.scene_location_var.get().strip(),
                'time_constraint': self.ui.time_constraint_var.get().strip()
            }

            # 高级参数
            advanced_params = self.ui.loaded_config.get("other_params", {})
            params.update({
                'language_purity_enabled': advanced_params.get('language_purity_enabled', True),
                'auto_correct_mixed_language': advanced_params.get('auto_correct_mixed_language', True),
                'preserve_proper_nouns': advanced_params.get('preserve_proper_nouns', True),
                'strict_language_mode': advanced_params.get('strict_language_mode', False)
            })

            # 验证必要参数
            if not params['filepath']:
                raise ValueError("文件路径不能为空")

            return params

        except Exception as e:
            logger.error(f"获取小说参数失败: {e}")
            raise ValueError(f"小说参数无效: {e}")

    def _validate_llm_config(self, config: Dict[str, Any], config_type: str) -> None:
        """
        验证LLM配置的有效性

        Args:
            config: LLM配置字典
            config_type: 配置类型（用于错误信息）

        Raises:
            ValueError: 当配置无效时
        """
        required_fields = ['interface_format', 'api_key', 'base_url', 'model_name']

        for field in required_fields:
            if not config.get(field):
                raise ValueError(f"{config_type}配置缺少必要字段: {field}")

        # 数值范围验证
        if config['temperature'] < 0 or config['temperature'] > 2:
            raise ValueError(f"{config_type}配置中temperature必须在0-2之间")

        if config['max_tokens'] <= 0:
            raise ValueError(f"{config_type}配置中max_tokens必须大于0")

        if config['timeout'] <= 0:
            raise ValueError(f"{config_type}配置中timeout必须大于0")

    def _is_cache_valid(self, config_key: str) -> bool:
        """
        检查缓存是否有效

        Args:
            config_key: 配置键

        Returns:
            bool: 缓存是否有效
        """
        # 如果没有缓存，返回False
        if config_key not in self._config_cache:
            return False

        # 这里可以添加更复杂的缓存逻辑，比如基于配置文件修改时间
        # 为了简化，暂时认为缓存总是有效，除非手动清除
        return True

    def invalidate_cache(self) -> None:
        """清除所有配置缓存"""
        self._config_cache.clear()
        self._last_config_hash = None
        logger.info("配置缓存已清除")

    def refresh_configs(self) -> None:
        """刷新所有配置"""
        self.invalidate_cache()
        # 通过访问配置来重新加载
        try:
            self.get_draft_config()
            self.get_final_config()
            logger.info("配置刷新完成")
        except Exception as e:
            logger.error(f"配置刷新失败: {e}")

    def get_config_summary(self) -> Dict[str, Any]:
        """
        获取配置摘要（不包含敏感信息）

        Returns:
            Dict[str, Any]: 配置摘要
        """
        try:
            draft_config = self.get_draft_config()
            final_config = self.get_final_config()

            return {
                'draft_llm': {
                    'model_name': draft_config['model_name'],
                    'interface_format': draft_config['interface_format'],
                    'temperature': draft_config['temperature'],
                    'max_tokens': draft_config['max_tokens']
                },
                'final_llm': {
                    'model_name': final_config['model_name'],
                    'interface_format': final_config['interface_format'],
                    'temperature': final_config['temperature'],
                    'max_tokens': final_config['max_tokens']
                },
                'novel_file': self.get_novel_parameters()['filepath']
            }
        except Exception as e:
            logger.error(f"获取配置摘要失败: {e}")
            return {'error': str(e)}