#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
向量维度不匹配修复工具
解决 ChromaDB 期望4096维但收到768维的错误

使用方法:
1. 备份现有向量库
2. 运行此脚本自动修复
3. 重新启动应用
"""

import os
import shutil
import logging
import json
from pathlib import Path
import numpy as np
from typing import List, Dict, Any, Optional

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class VectorDimensionFixer:
    """向量维度修复器"""

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.vectorstore_dir = self.project_path / "vectorstore"
        self.config_file = self.project_path / "config.json"

        # 备份目录
        self.backup_dir = self.project_path / "vectorstore_backup"

        # 当前配置
        self.current_config = self._load_config()
        self.target_dimension = self._get_target_dimension()

    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"无法加载配置文件: {e}")
            return {}

    def _get_target_dimension(self) -> int:
        """获取目标向量维度"""
        embedding_configs = self.current_config.get("embedding_configs", {})
        last_embedding = self.current_config.get("last_embedding_interface_format", "OpenAI")

        if last_embedding in embedding_configs:
            model_name = embedding_configs[last_embedding].get("model_name", "")

            # 根据模型名称确定维度
            dimension_map = {
                # OpenAI 模型
                "text-embedding-ada-002": 1536,
                "text-embedding-3-small": 1536,
                "text-embedding-3-large": 3072,

                # Qwen 模型
                "Qwen/Qwen3-Embedding-8B": 4096,
                "Qwen/Qwen2-Embedding-7B": 1536,

                # BGE 模型
                "BAAI/bge-large-zh-v1.5": 1024,
                "BAAI/bge-base-zh-v1.5": 768,

                # 其他常见模型
                "sentence-transformers/all-MiniLM-L6-v2": 384,
                "sentence-transformers/paraphrase-MiniLM-L6-v2": 384,
                "intfloat/multilingual-e5-large": 1024,
            }

            for model_pattern, dimension in dimension_map.items():
                if model_pattern.lower() in model_name.lower():
                    logging.info(f"检测到模型 {model_name}，目标维度: {dimension}")
                    return dimension

        # 默认使用4096维（Qwen3-Embedding-8B）
        logging.warning(f"无法识别模型 {last_embedding}，使用默认维度4096")
        return 4096

    def backup_existing_vectorstore(self) -> bool:
        """备份现有向量库"""
        if not self.vectorstore_dir.exists():
            logging.info("向量库不存在，无需备份")
            return True

        try:
            # 删除现有备份
            if self.backup_dir.exists():
                shutil.rmtree(self.backup_dir)

            # 创建新备份
            shutil.copytree(self.vectorstore_dir, self.backup_dir)
            logging.info(f"向量库已备份到: {self.backup_dir}")
            return True

        except Exception as e:
            logging.error(f"备份向量库失败: {e}")
            return False

    def clear_existing_vectorstore(self) -> bool:
        """清空现有向量库"""
        try:
            if self.vectorstore_dir.exists():
                shutil.rmtree(self.vectorstore_dir)
                logging.info("已清空现有向量库")
            return True
        except Exception as e:
            logging.error(f"清空向量库失败: {e}")
            return False

    def fix_vectorstore_utils(self) -> bool:
        """修复 vectorstore_utils.py 中的维度问题"""
        vectorstore_file = self.project_path / "novel_generator" / "vectorstore_utils.py"

        if not vectorstore_file.exists():
            logging.error(f"找不到文件: {vectorstore_file}")
            return False

        try:
            # 读取原文件
            with open(vectorstore_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # 备份原文件
            backup_file = vectorstore_file.with_suffix('.py.backup')
            with open(backup_file, 'w', encoding='utf-8') as f:
                f.write(content)
            logging.info(f"已备份原文件到: {backup_file}")

            # 修复维度问题
            # 将硬编码的768维替换为动态检测的维度
            old_fallback_code = '''                    # 生成768维的随机向量（常见embedding维度）
                    import random
                    embeddings = [[random.uniform(-1, 1) for _ in range(768)] for _ in range(len(texts))]'''

            new_fallback_code = f'''                    # 生成{self.target_dimension}维的随机向量
                    import random
                    embeddings = [[random.uniform(-1, 1) for _ in range({self.target_dimension})] for _ in range(len(texts))]'''

            content = content.replace(old_fallback_code, new_fallback_code)

            # 修复查询嵌入的维度
            old_query_fallback = '''                    import random
                    res = [random.uniform(-1, 1) for _ in range(768)]'''

            new_query_fallback = f'''                    import random
                    res = [random.uniform(-1, 1) for _ in range({self.target_dimension})]'''

            content = content.replace(old_query_fallback, new_query_fallback)

            # 添加维度检测函数
            dimension_detector = f'''
def get_embedding_dimension(embedding_adapter):
    """动态检测embedding维度"""
    try:
        # 尝试嵌入一个简单的测试文本
        test_embedding = embedding_adapter.embed_query("test")
        if test_embedding:
            return len(test_embedding)
    except:
        pass

    # 如果无法检测，返回配置的维度
    return {self.target_dimension}

'''

            # 在文件开头添加维度检测函数（在import语句之后）
            insert_pos = content.find('def get_vectorstore_dir(filepath: str) -> str:')
            if insert_pos != -1:
                content = content[:insert_pos] + dimension_detector + content[insert_pos:]

            # 写入修复后的文件
            with open(vectorstore_file, 'w', encoding='utf-8') as f:
                f.write(content)

            logging.info(f"已修复向量维度问题，目标维度: {self.target_dimension}")
            return True

        except Exception as e:
            logging.error(f"修复 vectorstore_utils.py 失败: {e}")
            return False

    def create_dimension_validator(self) -> bool:
        """创建维度验证工具"""
        validator_file = self.project_path / "validate_embedding_dimension.py"

        try:
            validator_code = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
嵌入维度验证工具
验证当前配置的embedding模型生成的向量维度
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from embedding_adapters import create_embedding_adapter
import logging

def validate_embedding_dimension():
    """验证embedding维度"""
    try:
        # 读取配置
        import json
        with open("config.json", 'r', encoding='utf-8') as f:
            config = json.load(f)

        embedding_configs = config.get("embedding_configs", {{}})
        last_embedding = config.get("last_embedding_interface_format", "OpenAI")

        if last_embedding not in embedding_configs:
            print(f"❌ 找不到embedding配置: {{last_embedding}}")
            return False

        embed_config = embedding_configs[last_embedding]

        # 创建embedding适配器
        adapter = create_embedding_adapter(
            embed_config.get("interface_format", "OpenAI"),
            embed_config.get("api_key", ""),
            embed_config.get("base_url", ""),
            embed_config.get("model_name", "")
        )

        if not adapter:
            print("❌ 无法创建embedding适配器")
            return False

        # 测试嵌入维度
        test_text = "这是一个测试文本"
        embedding = adapter.embed_query(test_text)

        if embedding:
            dimension = len(embedding)
            print(f"✅ 当前embedding模型维度: {{dimension}}")

            if dimension == {self.target_dimension}:
                print("✅ 维度匹配预期")
                return True
            else:
                print(f"⚠️  维度不匹配，预期: {{self.target_dimension}}, 实际: {{dimension}}")
                return False
        else:
            print("❌ 无法生成embedding")
            return False

    except Exception as e:
        print(f"❌ 验证过程出错: {{e}}")
        return False

if __name__ == "__main__":
    print("🔍 验证embedding维度...")
    if validate_embedding_dimension():
        print("🎉 维度验证通过")
    else:
        print("❌ 维度验证失败")
'''

            with open(validator_file, 'w', encoding='utf-8') as f:
                f.write(validator_code)

            logging.info(f"已创建维度验证工具: {validator_file}")
            return True

        except Exception as e:
            logging.error(f"创建维度验证工具失败: {e}")
            return False

    def run_fix(self) -> bool:
        """运行完整的修复流程"""
        print("🔧 开始修复向量维度不匹配问题...")
        print(f"目标维度: {self.target_dimension}")
        print("=" * 60)

        # 1. 备份现有向量库
        if not self.backup_existing_vectorstore():
            print("❌ 备份失败，停止修复")
            return False
        print("✅ 步骤1: 备份现有向量库")

        # 2. 清空现有向量库
        if not self.clear_existing_vectorstore():
            print("❌ 清空向量库失败")
            return False
        print("✅ 步骤2: 清空现有向量库")

        # 3. 修复代码
        if not self.fix_vectorstore_utils():
            print("❌ 修复代码失败")
            return False
        print("✅ 步骤3: 修复vectorstore_utils.py")

        # 4. 创建验证工具
        if not self.create_dimension_validator():
            print("⚠️  创建验证工具失败，但修复继续")
        else:
            print("✅ 步骤4: 创建维度验证工具")

        print("=" * 60)
        print("🎉 向量维度修复完成！")
        print()
        print("📋 后续步骤:")
        print("1. 重新启动应用程序")
        print("2. 应用程序会自动重建向量库")
        print("3. 如果需要，可以运行以下命令验证维度:")
        print(f"   python validate_embedding_dimension.py")
        print()
        print("📁 备份位置:")
        print(f"   原向量库已备份到: {self.backup_dir}")
        print(f"   原代码已备份到: novel_generator/vectorstore_utils.py.backup")
        print()
        print("⚠️  注意事项:")
        print("- 首次启动可能需要较长时间重建向量库")
        print("- 如果仍有问题，请检查embedding模型配置")
        print("- 可以从备份恢复原始数据")

        return True

def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="修复向量维度不匹配问题")
    parser.add_argument(
        "--project-path",
        default=".",
        help="项目路径（默认为当前目录）"
    )

    args = parser.parse_args()

    # 创建修复器
    fixer = VectorDimensionFixer(args.project_path)

    # 运行修复
    try:
        success = fixer.run_fix()
        if success:
            print("\n🚀 修复成功！请重新启动应用程序。")
        else:
            print("\n❌ 修复失败，请检查错误信息。")
            return 1
    except KeyboardInterrupt:
        print("\n\n⏹️  修复被用户中断")
        return 1
    except Exception as e:
        print(f"\n❌ 修复过程出错: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    exit(main())