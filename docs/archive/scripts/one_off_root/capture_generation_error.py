"""
捕获生成过程中的详细错误信息
"""
import logging
import sys
import os

# 设置日志到文件和控制台
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('capture_error.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

def main():
    logger.info("=" * 80)
    logger.info("开始捕获生成错误信息")
    logger.info("=" * 80)

    # 检查配置
    try:
        import json
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)

        last_interface = config.get('last_interface_format')
        logger.info(f"当前使用的LLM: {last_interface}")

        llm_config = config.get('llm_configs', {}).get(last_interface, {})
        logger.info(f"API Base URL: {llm_config.get('base_url')}")
        logger.info(f"Model: {llm_config.get('model_name')}")
        logger.info(f"Temperature: {llm_config.get('temperature')}")

    except Exception as e:
        logger.error(f"读取配置失败: {e}")
        return 1

    # 尝试初始化生成器
    try:
        from novel_generator.blueprint import StrictChapterGenerator

        logger.info("开始初始化生成器...")

        generator = StrictChapterGenerator(
            interface_format=llm_config.get('interface_format'),
            api_key=llm_config.get('api_key'),
            base_url=llm_config.get('base_url'),
            llm_model=llm_config.get('model_name'),
            temperature=llm_config.get('temperature', 0.7),
            max_tokens=llm_config.get('max_tokens', 60000),
            timeout=llm_config.get('timeout', 1800)
        )

        logger.info("✅ 生成器初始化成功")

    except Exception as e:
        logger.error(f"❌ 生成器初始化失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1

    # 测试单次生成
    try:
        logger.info("\n" + "=" * 80)
        logger.info("开始测试单次生成（第1章）")
        logger.info("=" * 80)

        # 读取架构文件
        arch_path = "wxhyj/Novel_architecture.txt"
        if not os.path.exists(arch_path):
            logger.error(f"架构文件不存在: {arch_path}")
            return 1

        with open(arch_path, 'r', encoding='utf-8') as f:
            architecture_text = f.read()

        logger.info(f"✅ 架构文件已读取，长度: {len(architecture_text)} 字符")

        # 尝试生成
        logger.info("开始调用LLM...")
        result = generator.generate_complete_directory_strict(
            architecture_text=architecture_text,
            start_chapter=1,
            end_chapter=1,  # 只生成第1章
            filepath="wxhyj"
        )

        logger.info("✅ 生成成功")
        logger.info(f"结果长度: {len(result)} 字符")
        logger.info(f"结果预览:\n{result[:500]}...")

    except Exception as e:
        logger.error(f"❌ 生成失败: {e}")
        logger.error(f"错误类型: {type(e).__name__}")
        import traceback
        logger.error(traceback.format_exc())

        # 尝试获取更多信息
        if hasattr(e, '__cause__') and e.__cause__:
            logger.error(f"根本原因: {e.__cause__}")

        return 1

    logger.info("\n" + "=" * 80)
    logger.info("测试完成")
    logger.info("=" * 80)

    return 0

if __name__ == "__main__":
    sys.exit(main())
