#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
警告过滤器 - 消除pkg_resources弃用警告
"""

import warnings
import sys

def filter_warnings():
    """
    过滤弃用警告
    """
    # 过滤pkg_resources弃用警告
    warnings.filterwarnings(
        "ignore",
        category=UserWarning,
        message="pkg_resources is deprecated as an API",
        module="jieba._compat"
    )

    # 也可以过滤所有UserWarning（如果确定安全的话）
    # warnings.filterwarnings("ignore", category=UserWarning)

    print("✅ 已启用pkg_resources弃用警告过滤器")

def main():
    """
    应用警告过滤器
    """
    filter_warnings()

    # 测试导入
    try:
        import jieba
        print("✅ jieba导入成功，警告已过滤")
    except Exception as e:
        print(f"❌ jieba导入失败: {e}")

if __name__ == "__main__":
    main()