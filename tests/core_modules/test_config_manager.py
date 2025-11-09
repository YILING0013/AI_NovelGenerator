# -*- coding: utf-8 -*-
"""
配置管理器测试
"""
import pytest
import tempfile
import json
from pathlib import Path
from config_manager import ConfigManager

class TestConfigManager:
    """配置管理器测试类"""

    def test_config_load(self, mock_config, config_file):
        """测试配置加载"""
        manager = ConfigManager(config_file)
        assert manager.config == mock_config

    def test_config_save(self, mock_config, temp_dir):
        """测试配置保存"""
        config_path = temp_dir / "test_config.json"
        manager = ConfigManager(str(config_path))

        new_config = {"test_key": "test_value"}
        manager.update_config(new_config)
        manager.save_config()

        with open(config_path, 'r', encoding='utf-8') as f:
            saved_config = json.load(f)
        assert saved_config == new_config

    def test_hot_reload(self, config_file):
        """测试热重载功能"""
        manager = ConfigManager(config_file)
        original_config = manager.config.copy()

        # 修改文件
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump({"new_key": "new_value"}, f)

        # 热重载
        manager.reload_config()
        assert manager.config != original_config
        assert manager.config["new_key"] == "new_value"

    def test_config_validation(self, temp_dir):
        """测试配置验证"""
        invalid_config_path = temp_dir / "invalid.json"
        with open(invalid_config_path, 'w') as f:
            f.write("invalid json")

        with pytest.raises(json.JSONDecodeError):
            ConfigManager(str(invalid_config_path))
