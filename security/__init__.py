# security/__init__.py
# -*- coding: utf-8 -*-
"""
安全模块
提供全面的安全防护功能，包括：
- API密钥安全存储
- SSL/TLS安全配置
- 输入验证和清理
- 安全日志管理
"""

from .secure_config_manager import SecureConfigManager, secure_config_manager
from .secure_logging import SecureLogger, secure_logger, get_secure_logger
from .ssl_security_manager import SSLSecurityManager, ssl_security_manager
from .input_validation import InputValidator, input_validator

# 导出主要接口
__all__ = [
    # 安全配置管理
    'SecureConfigManager',
    'secure_config_manager',
    'load_secure_config',
    'save_secure_config',

    # 安全日志
    'SecureLogger',
    'secure_logger',
    'get_secure_logger',

    # SSL安全
    'SSLSecurityManager',
    'ssl_security_manager',
    'secure_http_session',
    'secure_request',
    'validate_ssl_certificate',

    # 输入验证
    'InputValidator',
    'input_validator',
    'validate_file_path',
    'validate_text_input',
    'sanitize_filename',
    'validate_api_parameters',
]

# 便捷导入函数
from .secure_config_manager import load_secure_config, save_secure_config
from .ssl_security_manager import secure_http_session, secure_request, validate_ssl_certificate
from .input_validation import validate_file_path, validate_text_input, sanitize_filename, validate_api_parameters