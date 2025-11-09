# input_validation.py
# -*- coding: utf-8 -*-
"""
输入验证和清理模块
防止注入攻击、路径遍历等安全风险
"""

import re
import os
import html
import json
import hashlib
from typing import Any, Dict, List, Optional, Union
from pathlib import Path
import logging


class InputValidator:
    """
    输入验证器
    提供各种输入验证和清理功能
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # 危险字符模式
        self.dangerous_patterns = {
            'path_traversal': r'\.\.[\\/]',
            'script_injection': r'<script[^>]*>.*?</script>',
            'sql_injection': r'(\b(union|select|insert|update|delete|drop|create|alter)\b|\b(or|and)\s+\d+\s*=\s*\d+)',
            'command_injection': r'[;&|`$()]',
            'xss': r'javascript:|vbscript:|onload=|onerror=|onclick=',
            'file_injection': r'\.(exe|bat|cmd|sh|ps1|vbs|js|jar|app|deb|rpm)$',
        }

        # 允许的文件扩展名
        self.allowed_extensions = {
            'text': ['.txt', '.md', '.rst'],
            'config': ['.json', '.yaml', '.yml', '.ini', '.conf', '.cfg'],
            'code': ['.py', '.js', '.ts', '.html', '.css'],
            'document': ['.doc', '.docx', '.pdf', '.rtf'],
        }

        # 最大文件大小 (字节)
        self.max_file_sizes = {
            'text': 10 * 1024 * 1024,      # 10MB
            'config': 1024 * 1024,         # 1MB
            'code': 5 * 1024 * 1024,       # 5MB
            'document': 50 * 1024 * 1024,  # 50MB
        }

    def validate_file_path(self, file_path: str, allow_relative: bool = False) -> bool:
        """
        验证文件路径安全性
        防止路径遍历攻击
        """
        if not isinstance(file_path, str) or not file_path.strip():
            raise ValueError("文件路径不能为空")

        file_path = file_path.strip()

        # 检查路径遍历
        if re.search(self.dangerous_patterns['path_traversal'], file_path):
            raise ValueError(f"检测到路径遍历攻击: {file_path}")

        # 检查危险字符
        dangerous_chars = ['<', '>', ':', '"', '|', '?', '*']
        if any(char in file_path for char in dangerous_chars):
            raise ValueError(f"文件路径包含危险字符: {file_path}")

        # 规范化路径
        try:
            normalized_path = os.path.normpath(file_path)

            # 检查是否为绝对路径
            if os.path.isabs(normalized_path) and not allow_relative:
                # 限制绝对路径只能在特定目录下
                allowed_dirs = [
                    os.path.expanduser("~"),
                    os.getcwd(),
                    os.path.join(os.path.expanduser("~"), "Documents"),
                ]

                abs_path = os.path.abspath(normalized_path)
                if not any(abs_path.startswith(allowed_dir) for allowed_dir in allowed_dirs):
                    raise ValueError(f"不允许访问目录: {abs_path}")

            # 检查文件扩展名
            file_ext = Path(normalized_path).suffix.lower()
            allowed_exts = []
            for ext_list in self.allowed_extensions.values():
                allowed_exts.extend(ext_list)

            if file_ext and file_ext not in allowed_exts:
                raise ValueError(f"不允许的文件类型: {file_ext}")

            return True

        except (OSError, ValueError) as e:
            raise ValueError(f"无效文件路径: {e}")

    def validate_text_input(self, text: str, max_length: int = 10000, allow_html: bool = False) -> str:
        """
        验证文本输入
        防止XSS和注入攻击
        """
        if not isinstance(text, str):
            raise ValueError("输入必须是字符串")

        if len(text) > max_length:
            raise ValueError(f"文本长度超过限制: {len(text)} > {max_length}")

        # 移除或转义HTML标签
        if not allow_html:
            # 检查脚本注入
            if re.search(self.dangerous_patterns['script_injection'], text, re.IGNORECASE):
                raise ValueError("检测到脚本注入")

            # 检查XSS模式
            if re.search(self.dangerous_patterns['xss'], text, re.IGNORECASE):
                raise ValueError("检测到XSS攻击模式")

            # HTML转义
            text = html.escape(text)

        return text.strip()

    def validate_json_input(self, json_str: str, schema: Optional[Dict] = None) -> Dict:
        """
        验证JSON输入
        防止JSON注入和结构化攻击
        """
        try:
            # 解析JSON
            data = json.loads(json_str)

            # 验证JSON结构
            if schema:
                self._validate_json_schema(data, schema)

            # 递归验证所有字符串字段
            self._validate_json_strings(data)

            return data

        except json.JSONDecodeError as e:
            raise ValueError(f"无效JSON格式: {e}")

    def _validate_json_schema(self, data: Dict, schema: Dict):
        """验证JSON结构"""
        # 简单的schema验证
        required_fields = schema.get('required', [])
        for field in required_fields:
            if field not in data:
                raise ValueError(f"缺少必需字段: {field}")

        # 验证字段类型
        field_types = schema.get('types', {})
        for field, expected_type in field_types.items():
            if field in data and not isinstance(data[field], expected_type):
                raise ValueError(f"字段类型错误: {field} 应为 {expected_type.__name__}")

    def _validate_json_strings(self, data: Any):
        """递归验证JSON中的字符串"""
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, str):
                    # 检查危险模式
                    for pattern_name, pattern in self.dangerous_patterns.items():
                        if re.search(pattern, value, re.IGNORECASE):
                            raise ValueError(f"在字段 {key} 中检测到 {pattern_name}")
                elif isinstance(value, (dict, list)):
                    self._validate_json_strings(value)
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, (dict, list, str)):
                    self._validate_json_strings(item)

    def validate_file_content(self, file_path: str, content: bytes, max_size: Optional[int] = None) -> bool:
        """
        验证文件内容
        检查文件大小、类型和恶意内容
        """
        # 检查文件大小
        if max_size and len(content) > max_size:
            raise ValueError(f"文件过大: {len(content)} > {max_size}")

        # 根据文件扩展名检查
        file_ext = Path(file_path).suffix.lower()

        # 检查文本文件
        if file_ext in self.allowed_extensions['text'] + self.allowed_extensions['config'] + self.allowed_extensions['code']:
            try:
                # 尝试解码为UTF-8
                text_content = content.decode('utf-8')

                # 检查危险模式
                for pattern_name, pattern in self.dangerous_patterns.items():
                    if re.search(pattern, text_content, re.IGNORECASE):
                        self.logger.warning(f"在文件 {file_path} 中检测到 {pattern_name}")
                        # 对于配置文件，这可能是正常的，只记录警告

            except UnicodeDecodeError:
                raise ValueError("文件编码无效，应为UTF-8")

        return True

    def sanitize_filename(self, filename: str) -> str:
        """
        清理文件名
        移除危险字符和保留字
        """
        if not isinstance(filename, str):
            raise ValueError("文件名必须是字符串")

        # 移除危险字符
        dangerous_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*', '\0']
        sanitized = filename
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, '_')

        # 移除Windows保留字
        reserved_names = [
            'CON', 'PRN', 'AUX', 'NUL',
            'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
            'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
        ]

        name_part = sanitized.split('.')[0].upper()
        if name_part in reserved_names:
            sanitized = f"_{sanitized}"

        # 限制长度
        if len(sanitized) > 255:
            name, ext = os.path.splitext(sanitized)
            sanitized = name[:255-len(ext)] + ext

        return sanitized.strip()

    def validate_api_parameters(self, params: Dict[str, Any], required_params: List[str] = None) -> Dict[str, Any]:
        """
        验证API参数
        防止API注入攻击
        """
        validated_params = {}

        if required_params:
            for param in required_params:
                if param not in params:
                    raise ValueError(f"缺少必需参数: {param}")

        for key, value in params.items():
            # 参数名验证
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', key):
                raise ValueError(f"无效参数名: {key}")

            # 参数值验证
            if isinstance(value, str):
                # 检查命令注入
                if re.search(self.dangerous_patterns['command_injection'], value):
                    raise ValueError(f"参数 {key} 包含危险字符")

                # 检查SQL注入
                if re.search(self.dangerous_patterns['sql_injection'], value, re.IGNORECASE):
                    raise ValueError(f"参数 {key} 检测到SQL注入模式")

                validated_params[key] = value.strip()
            elif isinstance(value, (int, float, bool)):
                validated_params[key] = value
            elif isinstance(value, list):
                # 验证列表中的每个元素
                validated_list = []
                for item in value:
                    if isinstance(item, str):
                        if not self.validate_text_input(item, max_length=1000):
                            raise ValueError(f"列表参数 {key} 包含无效项")
                        validated_list.append(item)
                    else:
                        validated_list.append(item)
                validated_params[key] = validated_list
            else:
                validated_params[key] = value

        return validated_params

    def create_safe_file_path(self, base_dir: str, relative_path: str) -> str:
        """
        创建安全的文件路径
        确保路径在允许的基础目录内
        """
        # 验证基础目录
        if not os.path.exists(base_dir) or not os.path.isdir(base_dir):
            raise ValueError(f"基础目录不存在: {base_dir}")

        # 清理相对路径
        safe_relative = self.sanitize_filename(relative_path)
        safe_relative = safe_relative.replace('..', '').replace('\\', '/')

        # 构建完整路径
        full_path = os.path.join(base_dir, safe_relative)

        # 规范化并验证
        normalized_path = os.path.normpath(full_path)
        abs_base = os.path.abspath(base_dir)
        abs_path = os.path.abspath(normalized_path)

        # 确保最终路径在基础目录内
        if not abs_path.startswith(abs_base):
            raise ValueError(f"路径超出允许范围: {abs_path}")

        return abs_path

    def generate_content_hash(self, content: Union[str, bytes]) -> str:
        """生成内容哈希，用于完整性验证"""
        if isinstance(content, str):
            content = content.encode('utf-8')

        return hashlib.sha256(content).hexdigest()


# 全局输入验证器实例
input_validator = InputValidator()


def validate_file_path(file_path: str, allow_relative: bool = False) -> bool:
    """验证文件路径"""
    return input_validator.validate_file_path(file_path, allow_relative)


def validate_text_input(text: str, max_length: int = 10000, allow_html: bool = False) -> str:
    """验证文本输入"""
    return input_validator.validate_text_input(text, max_length, allow_html)


def sanitize_filename(filename: str) -> str:
    """清理文件名"""
    return input_validator.sanitize_filename(filename)


def validate_api_parameters(params: Dict[str, Any], required_params: List[str] = None) -> Dict[str, Any]:
    """验证API参数"""
    return input_validator.validate_api_parameters(params, required_params)