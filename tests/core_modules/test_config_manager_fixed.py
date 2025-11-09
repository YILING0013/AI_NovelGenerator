# -*- coding: utf-8 -*-
"""
配置管理器测试 - 基于实际代码结构
"""
import pytest
import tempfile
import json
import os
from pathlib import Path
from config_manager import load_config, create_config

class TestConfigManager:
    """配置管理器测试类"""

    def test_load_config(self):
        """测试配置加载"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            test_config = {
                "test_key": "test_value",
                "llm_configs": {
                    "test_llm": {
                        "api_key": "test_key"
                    }
                }
            }
            json.dump(test_config, f)
            temp_file = f.name

        try:
            loaded_config = load_config(temp_file)
            assert loaded_config["test_key"] == "test_value"
            assert "llm_configs" in loaded_config
        finally:
            os.unlink(temp_file)

    def test_create_config(self, temp_dir):
        """测试配置创建"""
        config_path = temp_dir / "test_config.json"

        # 创建配置
        config = create_config(str(config_path))

        # 验证文件已创建
        assert config_path.exists()

        # 验证配置内容
        with open(config_path, 'r', encoding='utf-8') as f:
            created_config = json.load(f)

        assert "llm_configs" in created_config
        assert "DeepSeek V3" in created_config["llm_configs"]
        assert "GPT 5" in created_config["llm_configs"]

    def test_load_nonexistent_config(self, temp_dir):
        """测试加载不存在的配置文件"""
        config_path = temp_dir / "nonexistent.json"

        # 加载不存在的配置应该创建默认配置
        config = load_config(str(config_path))

        # 验证文件已创建
        assert config_path.exists()

        # 验证包含默认配置
        assert "llm_configs" in config

    def test_load_invalid_json(self, temp_dir):
        """测试加载无效JSON文件"""
        config_path = temp_dir / "invalid.json"

        # 写入无效JSON
        with open(config_path, 'w') as f:
            f.write("invalid json content")

        # 加载无效JSON应该返回空字典
        config = load_config(str(config_path))
        assert config == {}