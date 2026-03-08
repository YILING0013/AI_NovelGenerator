"""
修复后的调试脚本 - 正确读取配置
"""
import logging
import sys
import os
import json

logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

def main():
    logger.info("=" * 80)
    logger.info("调试生成问题")
    logger.info("=" * 80)

    # 读取配置
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)

    last_interface = config.get('last_interface_format')
    logger.info(f"当前LLM: {last_interface}")

    # 获取LLM配置列表
    llm_configs = config.get('llm_configs', {})
    logger.info(f"可用的LLM配置: {list(llm_configs.keys())}")

    # 查找匹配的配置
    llm_config = None
    for key, value in llm_configs.items():
        if last_interface in key or key in last_interface:
            llm_config = value
            logger.info(f"找到匹配配置: {key}")
            break

    if not llm_config:
        logger.error(f"未找到配置，使用第一个可用配置")
        first_key = list(llm_configs.keys())[0]
        llm_config = llm_configs[first_key]
        logger.info(f"使用: {first_key}")

    # 提取参数
    interface_format = llm_config.get('interface_format', 'openai')
    api_key = llm_config.get('api_key')
    base_url = llm_config.get('base_url')
    model_name = llm_config.get('model_name')
    temperature = llm_config.get('temperature', 0.7)
    max_tokens = llm_config.get('max_tokens', 60000)
    timeout = llm_config.get('timeout', 1800)

    logger.info(f"Interface: {interface_format}")
    logger.info(f"Base URL: {base_url}")
    logger.info(f"Model: {model_name}")
    logger.info(f"Temperature: {temperature}")

    # 检查必要参数
    if not api_key:
        logger.error("API Key为空！")
        return 1

    # 初始化生成器
    from novel_generator.blueprint import StrictChapterGenerator

    try:
        generator = StrictChapterGenerator(
            interface_format=interface_format,
            api_key=api_key,
            base_url=base_url,
            llm_model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout
        )
        logger.info("✅ 生成器初始化成功")
    except Exception as e:
        logger.error(f"❌ 初始化失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1

    # 读取架构
    arch_path = "wxhyj/Novel_architecture.txt"
    if not os.path.exists(arch_path):
        logger.error(f"架构文件不存在: {arch_path}")
        return 1

    with open(arch_path, 'r', encoding='utf-8') as f:
        architecture_text = f.read()

    logger.info(f"架构文件: {len(architecture_text)} 字符")

    # 测试生成
    try:
        logger.info("\n" + "=" * 80)
        logger.info("开始生成第1-5章...")
        logger.info("=" * 80)

        # 使用正确的函数
        from novel_generator.blueprint import Strict_Chapter_blueprint_generate

        success = Strict_Chapter_blueprint_generate(
            interface_format=interface_format,
            api_key=api_key,
            base_url=base_url,
            llm_model=model_name,
            filepath="wxhyj",
            number_of_chapters=5,
            user_guidance="",
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout
        )

        if success:
            logger.info("\n✅ 生成成功!")

            # 读取生成的结果
            result_path = "wxhyj/Novel_directory.txt"
            if os.path.exists(result_path):
                with open(result_path, 'r', encoding='utf-8') as f:
                    result = f.read()
                logger.info(f"结果长度: {len(result)} 字符")

                # 显示前1000字符
                logger.info("\n结果预览:")
                logger.info("-" * 80)
                logger.info(result[:1000])
                logger.info("-" * 80)
            else:
                logger.warning("⚠️ 结果文件不存在")
        else:
            logger.error("❌ 生成失败")

    except Exception as e:
        logger.error(f"\n❌ 生成失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1

    logger.info("\n" + "=" * 80)
    logger.info("测试完成")
    logger.info("=" * 80)

    return 0

if __name__ == "__main__":
    sys.exit(main())
