# -*- coding: utf-8 -*-
"""
依赖管理优化脚本
"""
import subprocess
import sys
import json
from pathlib import Path
import warnings

def check_outdated_packages():
    """检查过时包"""
    try:
        result = subprocess.run([
            sys.executable, "-m", "pip", "list", "--outdated", "--format=json"
        ], capture_output=True, text=True)

        if result.returncode == 0:
            outdated = json.loads(result.stdout)
            return outdated
        return []
    except Exception:
        return []

def update_pkg_resources():
    """更新pkg_resources相关包"""
    updates = [
        "setuptools>=81.0.0",
        "pip>=24.0.0"
    ]

    for package in updates:
        try:
            subprocess.run([
                sys.executable, "-m", "pip", "install", "--upgrade", package
            ], check=True)
            print(f"✓ 已更新 {package}")
        except subprocess.CalledProcessError:
            print(f"✗ 更新 {package} 失败")

def create_requirements_lock():
    """创建requirements.lock文件"""
    try:
        result = subprocess.run([
            sys.executable, "-m", "pip", "freeze"
        ], capture_output=True, text=True)

        if result.returncode == 0:
            with open("requirements.lock", 'w') as f:
                f.write(result.stdout)
            print("✓ 已创建 requirements.lock")
    except Exception as e:
        print(f"✗ 创建 requirements.lock 失败: {e}")

if __name__ == "__main__":
    print("开始依赖管理优化...")

    # 检查过时包
    print("\n检查过时包...")
    outdated = check_outdated_packages()
    if outdated:
        print(f"发现 {len(outdated)} 个过时包")
        for package in outdated[:5]:  # 显示前5个
            print(f"  - {package['name']}: {package['version']} -> {package['latest_version']}")

    # 更新pkg_resources相关包
    print("\n更新pkg_resources相关包...")
    update_pkg_resources()

    # 创建锁定文件
    print("\n创建依赖锁定文件...")
    create_requirements_lock()

    print("\n依赖管理优化完成")
