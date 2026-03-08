# run_progressive_generation.py
# -*- coding: utf-8 -*-
"""
三阶段渐进式蓝图生成器 - 独立运行脚本

使用方法：
    python run_progressive_generation.py --filepath wxhyj --chapters 20

配置：
    在 config.json 中设置 blueprint_generation.mode = "progressive"
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from novel_generator.progressive_blueprint_generator import (
    ProgressiveBlueprintGenerator,
    ProgressiveConfig
)
from utils import read_file


def setup_logging():
    """设置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('progressive_generation.log', encoding='utf-8')
        ]
    )


def load_config(filepath: str) -> dict:
    """加载配置文件"""
    config_path = os.path.join(filepath, "config.json")

    # 如果指定目录没有配置，使用项目根目录的配置
    if not os.path.exists(config_path):
        config_path = "config.json"

    if not os.path.exists(config_path):
        raise Exception(f"config.json not found at {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    return config


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='三阶段渐进式蓝图生成器')
    parser.add_argument('--filepath', type=str, default='wxhyj',
                       help='小说文件路径（默认: wxhyj）')
    parser.add_argument('--chapters', type=int, default=20,
                       help='生成章节数（默认: 20）')
    parser.add_argument('--llm', type=str, default=None,
                       help='使用的LLM名称（从config.json选择）')
    parser.add_argument('--temperature', type=float, default=None,
                       help='温度参数（0.0-1.0）')
    parser.add_argument('--max-tokens', type=int, default=None,
                       help='最大token数')

    args = parser.parse_args()

    # 设置日志
    setup_logging()

    logging.info("=" * 60)
    logging.info("🚀 三阶段渐进式蓝图生成器")
    logging.info("=" * 60)

    try:
        # 加载配置
        config = load_config(args.filepath)

        # 检查蓝图生成模式
        bp_config = config.get('blueprint_generation', {})
        mode = bp_config.get('mode', 'batch')

        if mode != 'progressive':
            logging.warning(f"⚠️ 当前模式是 '{mode}'，不是 'progressive'")
            logging.warning("请在 config.json 中设置 blueprint_generation.mode = 'progressive'")
            response = input("是否继续使用 progressive 模式？(y/n): ")
            if response.lower() != 'y':
                logging.info("已取消")
                return

        # 获取LLM配置
        llm_name = args.llm or config.get('choose_configs', {}).get('architecture_llm')
        if not llm_name:
            raise Exception("未指定LLM，请使用 --llm 参数或在 config.json 中设置")

        llm_config = config['llm_configs'].get(llm_name)
        if not llm_config:
            raise Exception(f"LLM配置未找到: {llm_name}")

        # 创建ProgressiveConfig
        progressive_config = ProgressiveConfig()
        if 'progressive_config' in bp_config:
            for key, value in bp_config['progressive_config'].items():
                if hasattr(progressive_config, key.upper()):
                    setattr(progressive_config, key.upper(), value)

        # 创建生成器
        logging.info(f"使用LLM: {llm_name}")
        logging.info(f"生成章节数: {args.chapters}")
        logging.info(f"输出路径: {args.filepath}")

        generator = ProgressiveBlueprintGenerator(
            interface_format=llm_config['interface_format'],
            api_key=llm_config['api_key'],
            base_url=llm_config['base_url'],
            llm_model=llm_config['model_name'],
            temperature=args.temperature or llm_config.get('temperature', 0.8),
            max_tokens=args.max_tokens or llm_config.get('max_tokens', 8000),
            timeout=llm_config.get('timeout', 300),
            config=progressive_config
        )

        # 执行生成
        result = generator.generate_progressive(
            filepath=args.filepath,
            number_of_chapters=args.chapters
        )

        # 输出结果
        logging.info("\n" + "=" * 60)
        if result['success']:
            logging.info("🎉 生成成功！")
            logging.info(f"📊 一致性得分: {result.get('consistency_score', 0):.2f}")
            logging.info(f"📊 质量得分: {result.get('quality_score', 0):.2f}")
            logging.info(f"⏱️ 总耗时: {result.get('total_duration', 'N/A')}")
            logging.info(f"📄 生成日志: {result.get('log_file', 'N/A')}")
            logging.info(f"📁 输出文件: {os.path.join(args.filepath, 'Novel_directory.txt')}")
        else:
            logging.error("❌ 生成失败")
            if 'error' in result:
                logging.error(f"错误: {result['error']}")
        logging.info("=" * 60)

    except KeyboardInterrupt:
        logging.info("\n⚠️ 用户中断")
    except Exception as e:
        logging.error(f"❌ 发生错误: {e}")
        import traceback
        logging.error(traceback.format_exc())


if __name__ == "__main__":
    main()
