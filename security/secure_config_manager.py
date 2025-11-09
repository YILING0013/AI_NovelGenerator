# secure_config_manager.py
# -*- coding: utf-8 -*-
"""
安全配置管理模块
解决API密钥明文存储、配置文件验证等安全问题
"""

import json
import os
import keyring
import hashlib
import base64
from typing import Dict, Optional, Any
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class SecureConfigManager:
    """
    安全配置管理器
    - 使用系统keyring存储敏感信息
    - 配置文件完整性验证
    - 输入验证和清理
    """

    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.app_name = "ai_novel_generator"
        self._init_encryption()

    def _init_encryption(self):
        """初始化加密组件"""
        # 使用用户机器信息作为盐值
        machine_info = os.environ.get('COMPUTERNAME', 'default') + os.environ.get('USERNAME', 'default')
        salt = hashlib.sha256(machine_info.encode()).digest()

        # 从keyring获取或生成主密钥
        master_key = keyring.get_password(self.app_name, "master_key")
        if not master_key:
            master_key = base64.urlsafe_b64encode(os.urandom(32)).decode()
            keyring.set_password(self.app_name, "master_key", master_key)

        # 派生加密密钥
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(base64.urlsafe_b64decode(master_key)))
        self.cipher = Fernet(key)

    def encrypt_sensitive_data(self, data: str) -> str:
        """加密敏感数据"""
        return self.cipher.encrypt(data.encode()).decode()

    def decrypt_sensitive_data(self, encrypted_data: str) -> str:
        """解密敏感数据"""
        return self.cipher.decrypt(encrypted_data.encode()).decode()

    def validate_file_path(self, file_path: str) -> bool:
        """
        验证文件路径安全性
        防止路径遍历攻击
        """
        if not isinstance(file_path, str):
            return False

        # 基本路径安全检查
        dangerous_patterns = [
            "..",           # 父目录遍历
            "~",            # 用户目录
            "/etc/",        # 系统配置目录
            "/sys/",        # 系统目录
            "/proc/",       # 进程目录
            "C:\\Windows",  # Windows系统目录
            "C:\\System32", # Windows系统目录
        ]

        file_path_lower = file_path.lower()
        for pattern in dangerous_patterns:
            if pattern in file_path_lower:
                raise ValueError(f"危险路径模式: {pattern}")

        # 检查文件扩展名
        allowed_extensions = ['.txt', '.json', '.md', '.py']
        if not any(file_path.lower().endswith(ext) for ext in allowed_extensions):
            raise ValueError("不支持的文件类型")

        # 规范化路径
        try:
            normalized_path = os.path.normpath(file_path)
            abs_path = os.path.abspath(normalized_path)

            # 确保路径在允许的范围内
            current_dir = os.path.abspath(os.getcwd())
            if not abs_path.startswith(current_dir) and not abs_path.startswith(os.path.expanduser("~")):
                raise ValueError("路径超出允许范围")

        except (OSError, ValueError) as e:
            raise ValueError(f"无效路径: {e}")

        return True

    def load_config(self) -> dict:
        """加载配置文件并验证完整性"""
        if not os.path.exists(self.config_file):
            return self._create_secure_config()

        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            # 验证配置文件完整性
            if not self._validate_config_structure(config_data):
                raise ValueError("配置文件结构无效")

            # 解密敏感信息
            config_data = self._decrypt_sensitive_fields(config_data)

            return config_data

        except (json.JSONDecodeError, FileNotFoundError, ValueError) as e:
            print(f"配置文件加载失败: {e}")
            return self._create_secure_config()

    def save_config(self, config_data: dict) -> bool:
        """安全保存配置文件"""
        try:
            # 加密敏感字段
            encrypted_config = self._encrypt_sensitive_fields(config_data)

            # 验证配置结构
            if not self._validate_config_structure(encrypted_config):
                raise ValueError("配置结构无效")

            # 创建备份
            self._backup_config()

            # 原子性写入
            temp_file = f"{self.config_file}.tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(encrypted_config, f, indent=2, ensure_ascii=False)

            # 原子性替换
            if os.name == 'nt':  # Windows
                if os.path.exists(self.config_file):
                    os.remove(self.config_file)
            os.rename(temp_file, self.config_file)

            return True

        except Exception as e:
            print(f"配置保存失败: {e}")
            return False

    def _encrypt_sensitive_fields(self, config: dict) -> dict:
        """加密配置中的敏感字段"""
        encrypted_config = config.copy()

        # 加密API密钥
        if "llm_configs" in encrypted_config:
            for service, service_config in encrypted_config["llm_configs"].items():
                if "api_key" in service_config and service_config["api_key"]:
                    encrypted_key = self.encrypt_sensitive_data(service_config["api_key"])
                    service_config["api_key"] = f"encrypted:{encrypted_key}"
                    # 保存到keyring
                    keyring.set_password(self.app_name, f"llm_{service}", service_config["api_key"])

        if "embedding_configs" in encrypted_config:
            for service, service_config in encrypted_config["embedding_configs"].items():
                if "api_key" in service_config and service_config["api_key"]:
                    encrypted_key = self.encrypt_sensitive_data(service_config["api_key"])
                    service_config["api_key"] = f"encrypted:{encrypted_key}"
                    keyring.set_password(self.app_name, f"embed_{service}", service_config["api_key"])

        # 加密WebDAV密码
        if "webdav_config" in encrypted_config:
            webdav_config = encrypted_config["webdav_config"]
            if "webdav_password" in webdav_config and webdav_config["webdav_password"]:
                encrypted_password = self.encrypt_sensitive_data(webdav_config["webdav_password"])
                webdav_config["webdav_password"] = f"encrypted:{encrypted_password}"
                keyring.set_password(self.app_name, "webdav_password", webdav_config["webdav_password"])

        return encrypted_config

    def _decrypt_sensitive_fields(self, config: dict) -> dict:
        """解密配置中的敏感字段"""
        decrypted_config = config.copy()

        # 解密API密钥
        if "llm_configs" in decrypted_config:
            for service, service_config in decrypted_config["llm_configs"].items():
                if "api_key" in service_config:
                    encrypted_key = keyring.get_password(self.app_name, f"llm_{service}")
                    if encrypted_key:
                        service_config["api_key"] = encrypted_key
                    elif isinstance(service_config["api_key"], str) and service_config["api_key"].startswith("encrypted:"):
                        try:
                            encrypted_data = service_config["api_key"][10:]  # 移除 "encrypted:" 前缀
                            service_config["api_key"] = self.decrypt_sensitive_data(encrypted_data)
                        except Exception:
                            service_config["api_key"] = ""

        if "embedding_configs" in decrypted_config:
            for service, service_config in decrypted_config["embedding_configs"].items():
                if "api_key" in service_config:
                    encrypted_key = keyring.get_password(self.app_name, f"embed_{service}")
                    if encrypted_key:
                        service_config["api_key"] = encrypted_key
                    elif isinstance(service_config["api_key"], str) and service_config["api_key"].startswith("encrypted:"):
                        try:
                            encrypted_data = service_config["api_key"][10:]
                            service_config["api_key"] = self.decrypt_sensitive_data(encrypted_data)
                        except Exception:
                            service_config["api_key"] = ""

        # 解密WebDAV密码
        if "webdav_config" in decrypted_config:
            webdav_config = decrypted_config["webdav_config"]
            if "webdav_password" in webdav_config:
                encrypted_password = keyring.get_password(self.app_name, "webdav_password")
                if encrypted_password:
                    webdav_config["webdav_password"] = encrypted_password
                elif isinstance(webdav_config["webdav_password"], str) and webdav_config["webdav_password"].startswith("encrypted:"):
                    try:
                        encrypted_data = webdav_config["webdav_password"][10:]
                        webdav_config["webdav_password"] = self.decrypt_sensitive_data(encrypted_data)
                    except Exception:
                        webdav_config["webdav_password"] = ""

        return decrypted_config

    def _validate_config_structure(self, config: dict) -> bool:
        """验证配置文件结构完整性"""
        required_sections = [
            "llm_configs",
            "other_params",
            "choose_configs"
        ]

        for section in required_sections:
            if section not in config:
                return False

        # 验证LLM配置结构
        if not isinstance(config["llm_configs"], dict):
            return False

        for service, service_config in config["llm_configs"].items():
            required_fields = ["api_key", "base_url", "model_name", "interface_format"]
            for field in required_fields:
                if field not in service_config:
                    return False

        return True

    def _create_secure_config(self) -> dict:
        """创建安全的默认配置"""
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
                    "interface_format": "OpenAI"
                },
                "GPT 5": {
                    "api_key": "",
                    "base_url": "https://api.openai.com/v1",
                    "model_name": "gpt-5",
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
                    "model_name": "text-embedding-ada-002",
                    "retrieval_k": 4,
                    "interface_format": "OpenAI"
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
                "time_constraint": "",
                "language_purity_enabled": True,
                "auto_correct_mixed_language": True,
                "preserve_proper_nouns": True,
                "strict_language_mode": False
            },
            "choose_configs": {
                "prompt_draft_llm": "DeepSeek V3",
                "chapter_outline_llm": "DeepSeek V3",
                "architecture_llm": "GPT 5",
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
                "webdav_password": ""
            }
        }

        self.save_config(config)
        return config

    def _backup_config(self):
        """创建配置文件备份"""
        if os.path.exists(self.config_file):
            import shutil
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = f"{self.config_file}.backup_{timestamp}"
            shutil.copy2(self.config_file, backup_file)

    def secure_get_api_key(self, service_type: str, service_name: str) -> str:
        """安全获取API密钥"""
        key_name = f"{service_type}_{service_name}"
        return keyring.get_password(self.app_name, key_name) or ""

    def secure_set_api_key(self, service_type: str, service_name: str, api_key: str) -> bool:
        """安全设置API密钥"""
        try:
            key_name = f"{service_type}_{service_name}"
            if api_key.strip():
                keyring.set_password(self.app_name, key_name, api_key.strip())
            else:
                # 如果为空，删除存储的密钥
                try:
                    keyring.delete_password(self.app_name, key_name)
                except keyring.errors.PasswordDeleteError:
                    pass
            return True
        except Exception as e:
            print(f"API密钥保存失败: {e}")
            return False

    def migrate_existing_config(self, old_config_file: str) -> bool:
        """迁移现有不安全配置到安全配置"""
        try:
            if not os.path.exists(old_config_file):
                return False

            with open(old_config_file, 'r', encoding='utf-8') as f:
                old_config = json.load(f)

            # 迁移并加密现有API密钥
            self.save_config(old_config)

            # 备份旧配置文件
            backup_file = f"{old_config_file}.migrated_backup"
            import shutil
            shutil.move(old_config_file, backup_file)

            return True

        except Exception as e:
            print(f"配置迁移失败: {e}")
            return False


# 全局安全配置管理器实例
secure_config_manager = SecureConfigManager()


def load_secure_config(config_file: str = "config.json") -> dict:
    """加载安全配置"""
    manager = SecureConfigManager(config_file)
    return manager.load_config()


def save_secure_config(config_data: dict, config_file: str = "config.json") -> bool:
    """保存安全配置"""
    manager = SecureConfigManager(config_file)
    return manager.save_config(config_data)