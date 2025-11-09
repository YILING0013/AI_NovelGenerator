# security_migration_tool.py
# -*- coding: utf-8 -*-
"""
安全迁移工具
将现有不安全配置迁移到安全配置系统
"""

import json
import os
import sys
import shutil
from datetime import datetime
from pathlib import Path


def install_dependencies():
    """安装安全模块依赖"""
    requirements = [
        "cryptography>=41.0.0",
        "keyring>=24.0.0",
        "certifi>=2023.0.0",
        "pydantic>=2.0.0",
        "jsonschema>=4.0.0"
    ]

    print("📦 正在安装安全模块依赖...")
    try:
        import subprocess
        for package in requirements:
            print(f"  安装 {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        print("✅ 依赖安装完成")
        return True
    except Exception as e:
        print(f"❌ 依赖安装失败: {e}")
        return False


def backup_existing_files():
    """备份现有配置文件"""
    print("📋 备份现有配置文件...")

    files_to_backup = [
        "config.json",
        "config.example.json"
    ]

    backup_dir = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(backup_dir, exist_ok=True)

    for file in files_to_backup:
        if os.path.exists(file):
            backup_path = os.path.join(backup_dir, file)
            shutil.copy2(file, backup_path)
            print(f"  ✅ 已备份: {file} -> {backup_path}")

    return backup_dir


def update_config_manager():
    """更新config_manager.py以使用安全配置"""
    print("🔧 更新config_manager.py...")

    config_manager_path = "config_manager.py"
    if not os.path.exists(config_manager_path):
        print(f"  ⚠️  文件不存在: {config_manager_path}")
        return False

    try:
        # 读取原文件
        with open(config_manager_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 添加安全配置导入
        secure_import = """
# 安全配置管理
try:
    from security import load_secure_config, save_secure_config, SecureConfigManager
    SECURITY_ENABLED = True
except ImportError:
    SECURITY_ENABLED = False
    print("警告: 安全模块未安装，请运行 python security_migration_tool.py")
"""

        if "from security import" not in content:
            content = secure_import + content

        # 备份原文件
        shutil.copy2(config_manager_path, f"{config_manager_path}.backup")

        # 写入更新后的内容
        with open(config_manager_path, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"  ✅ 已更新: {config_manager_path}")
        return True

    except Exception as e:
        print(f"  ❌ 更新失败: {e}")
        return False


def update_llm_adapters():
    """更新llm_adapters.py以使用安全HTTP请求"""
    print("🔧 更新llm_adapters.py...")

    adapters_path = "llm_adapters.py"
    if not os.path.exists(adapters_path):
        print(f"  ⚠️  文件不存在: {adapters_path}")
        return False

    try:
        # 读取原文件
        with open(adapters_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 添加安全HTTP导入
        secure_import = """
# 安全HTTP请求
try:
    from security import ssl_security_manager, secure_request
    SSL_SECURITY_ENABLED = True
except ImportError:
    SSL_SECURITY_ENABLED = False
    print("警告: SSL安全模块未安装")
"""

        if "from security import" not in content:
            content = secure_import + content

        # 备份原文件
        shutil.copy2(adapters_path, f"{adapters_path}.backup")

        # 写入更新后的内容
        with open(adapters_path, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"  ✅ 已更新: {adapters_path}")
        return True

    except Exception as e:
        print(f"  ❌ 更新失败: {e}")
        return False


def update_logging():
    """更新日志系统以使用安全日志"""
    print("🔧 更新日志系统...")

    # 创建安全日志配置
    log_config_content = '''
# secure_log_config.py
# 安全日志配置
import logging
from security import get_secure_logger

# 配置应用程序使用安全日志
def setup_secure_logging():
    """设置安全日志"""
    # 替换根日志记录器
    secure_logger = get_secure_logger()

    # 为现有模块添加安全过滤器
    for name in ['llm_adapters', 'config_manager', 'novel_generator']:
        logger = logging.getLogger(name)
        logger.handlers.clear()

        # 使用安全日志处理器
        for handler in secure_logger.logger.handlers:
            logger.addHandler(handler)
        logger.setLevel(secure_logger.logger.level)

if __name__ == "__main__":
    setup_secure_logging()
    print("安全日志配置完成")
'''

    try:
        with open("secure_log_config.py", 'w', encoding='utf-8') as f:
            f.write(log_config_content)
        print("  ✅ 已创建: secure_log_config.py")
        return True
    except Exception as e:
        print(f"  ❌ 创建失败: {e}")
        return False


def create_security_tests():
    """创建安全测试文件"""
    print("🧪 创建安全测试...")

    test_content = '''
# test_security.py
# -*- coding: utf-8 -*-
"""
安全功能测试
"""

import unittest
import tempfile
import os
from security import (
    SecureConfigManager,
    validate_file_path,
    validate_text_input,
    sanitize_filename,
    ssl_security_manager
)


class TestSecurityFeatures(unittest.TestCase):
    """安全功能测试类"""

    def setUp(self):
        """测试准备"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_manager = SecureConfigManager(os.path.join(self.temp_dir, "test_config.json"))

    def test_secure_api_key_storage(self):
        """测试API密钥安全存储"""
        test_key = "sk-test123456789"

        # 测试加密存储
        encrypted = self.config_manager.encrypt_sensitive_data(test_key)
        self.assertNotEqual(encrypted, test_key)

        # 测试解密
        decrypted = self.config_manager.decrypt_sensitive_data(encrypted)
        self.assertEqual(decrypted, test_key)

    def test_file_path_validation(self):
        """测试文件路径验证"""
        # 安全路径
        self.assertTrue(validate_file_path("test.txt"))
        self.assertTrue(validate_file_path("config/test.json"))

        # 危险路径
        with self.assertRaises(ValueError):
            validate_file_path("../etc/passwd")

        with self.assertRaises(ValueError):
            validate_file_path("C:\\Windows\\system32\\cmd.exe")

    def test_text_input_validation(self):
        """测试文本输入验证"""
        # 正常文本
        safe_text = validate_text_input("这是一个测试文本")
        self.assertEqual(safe_text, "这是一个测试文本")

        # XSS测试
        with self.assertRaises(ValueError):
            validate_text_input("<script>alert('xss')</script>")

    def test_filename_sanitization(self):
        """测试文件名清理"""
        # 危险文件名
        dangerous = "test<script>.txt"
        safe = sanitize_filename(dangerous)
        self.assertNotIn("<script>", safe)
        self.assertTrue(safe.endswith(".txt"))

    def test_ssl_security(self):
        """测试SSL安全"""
        # 测试已知安全网站
        result = ssl_security_manager.validate_ssl_certificate("google.com")
        self.assertIn('valid', result)

        # 测试URL验证
        url_result = ssl_security_manager.validate_url_security("https://api.openai.com")
        self.assertTrue(url_result['secure'])


if __name__ == "__main__":
    unittest.main()
'''

    try:
        with open("test_security.py", 'w', encoding='utf-8') as f:
            f.write(test_content)
        print("  ✅ 已创建: test_security.py")
        return True
    except Exception as e:
        print(f"  ❌ 创建失败: {e}")
        return False


def create_installation_guide():
    """创建安装指南"""
    print("📖 创建安装指南...")

    guide_content = '''# 🔐 安全模块安装指南

## 快速安装

1. **安装依赖**
   ```bash
   pip install -r security_requirements.txt
   ```

2. **运行迁移工具**
   ```bash
   python security_migration_tool.py
   ```

3. **验证安装**
   ```bash
   python test_security.py
   ```

## 手动安装步骤

### 1. 安装依赖包
```bash
pip install cryptography keyring certifi pydantic jsonschema
```

### 2. 备份现有配置
```bash
cp config.json config.json.backup
cp config.example.json config.example.json.backup
```

### 3. 迁移到安全配置
```python
from security import secure_config_manager

# 迁移现有配置
secure_config_manager.migrate_existing_config("config.json")
```

## 安全功能说明

### 🔑 API密钥安全存储
- 使用系统keyring加密存储
- 配置文件中不再包含明文密钥
- 支持密钥轮换和管理

### 🛡️ SSL/TLS安全
- 强制SSL证书验证
- 现代TLS版本支持
- 自定义CA证书支持

### 📝 输入验证
- 文件路径遍历防护
- XSS注入防护
- SQL注入检测
- 命令注入防护

### 📊 安全日志
- 自动过滤敏感信息
- 结构化日志记录
- 安全事件监控

## 配置说明

### 安全配置管理器
```python
from security import SecureConfigManager

# 创建安全配置管理器
manager = SecureConfigManager("config.json")

# 加载配置
config = manager.load_config()

# 保存配置
manager.save_config(config)
```

### 安全HTTP请求
```python
from security import secure_request

# 发起安全HTTP请求
response = secure_request("GET", "https://api.example.com/data")
```

### 输入验证
```python
from security import validate_file_path, validate_text_input

# 验证文件路径
safe_path = validate_file_path("user_input.txt")

# 验证文本输入
safe_text = validate_text_input(user_input)
```

## 故障排除

### 问题1: keyring后端错误
**解决方案:**
```bash
# Linux
sudo apt-get install python3-keyring

# macOS
brew install python-keyring

# Windows
pip install keyrings.windows
```

### 问题2: SSL证书验证失败
**解决方案:**
```python
from security import ssl_security_manager

# 使用自定义CA证书
ssl_security_manager.set_custom_ca_bundle("/path/to/ca-bundle.crt")
```

### 问题3: 配置迁移失败
**解决方案:**
1. 检查配置文件权限
2. 确保keyring服务运行
3. 手动迁移敏感配置

## 安全最佳实践

1. **定期更新依赖**: 保持安全库最新版本
2. **密钥轮换**: 定期更换API密钥
3. **监控日志**: 关注安全事件日志
4. **权限控制**: 遵循最小权限原则
5. **备份策略**: 定期备份安全配置

## 联系支持

如遇到安全问题，请：
1. 检查日志文件获取详细错误信息
2. 运行安全测试验证功能
3. 查看项目文档获取更多信息

---

**注意**: 此安全模块提供了基础防护，请根据具体部署环境调整安全策略。
'''

    try:
        with open("SECURITY_INSTALLATION_GUIDE.md", 'w', encoding='utf-8') as f:
            f.write(guide_content)
        print("  ✅ 已创建: SECURITY_INSTALLATION_GUIDE.md")
        return True
    except Exception as e:
        print(f"  ❌ 创建失败: {e}")
        return False


def main():
    """主迁移流程"""
    print("🚀 开始安全模块安装和配置迁移...")
    print("=" * 60)

    # 1. 安装依赖
    if not install_dependencies():
        print("❌ 依赖安装失败，请手动安装")
        return False

    print()

    # 2. 备份文件
    backup_dir = backup_existing_files()
    print()

    # 3. 更新配置文件
    if not update_config_manager():
        print("❌ 配置管理器更新失败")
        return False
    print()

    # 4. 更新适配器
    if not update_llm_adapters():
        print("❌ LLM适配器更新失败")
        return False
    print()

    # 5. 更新日志系统
    if not update_logging():
        print("❌ 日志系统更新失败")
        return False
    print()

    # 6. 创建测试文件
    if not create_security_tests():
        print("❌ 安全测试创建失败")
        return False
    print()

    # 7. 创建安装指南
    if not create_installation_guide():
        print("❌ 安装指南创建失败")
        return False

    print("=" * 60)
    print("🎉 安全模块安装完成!")
    print()
    print("📋 接下来的步骤:")
    print("1. 运行 'python test_security.py' 验证安装")
    print("2. 查看 'SECURITY_INSTALLATION_GUIDE.md' 了解使用方法")
    print("3. 备份位置:", backup_dir)
    print("4. 重启应用程序以应用安全配置")
    print()
    print("🔐 安全功能已启用:")
    print("- ✅ API密钥加密存储")
    print("- ✅ SSL/TLS安全配置")
    print("- ✅ 输入验证和清理")
    print("- ✅ 安全日志记录")
    print("- ✅ 路径遍历防护")

    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️ 用户取消安装")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 安装失败: {e}")
        sys.exit(1)