#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证embedding维度"""

import sys
import os
sys.path.append('.')

from embedding_adapters import create_embedding_adapter
import json

try:
    with open("config.json", 'r', encoding='utf-8') as f:
        config = json.load(f)

    embed_config = config["embedding_configs"]["SiliconFlow"]
    # 只传递适配器需要的参数
    adapter_params = {
        "api_key": embed_config.get("api_key", ""),
        "base_url": embed_config.get("base_url", ""),
        "model_name": embed_config.get("model_name", "")
    }
    adapter = create_embedding_adapter("SiliconFlow", **adapter_params)

    if adapter:
        test_embedding = adapter.embed_query("测试")
        if test_embedding:
            dimension = len(test_embedding)
            print(f"✅ Embedding维度: {dimension}")
            if dimension == 4096:
                print("🎉 维度正确！")
            else:
                print(f"⚠️  维度不是4096，而是{dimension}")
        else:
            print("❌ 无法生成embedding")
    else:
        print("❌ 无法创建adapter")

except Exception as e:
    print(f"❌ 验证失败: {e}")
