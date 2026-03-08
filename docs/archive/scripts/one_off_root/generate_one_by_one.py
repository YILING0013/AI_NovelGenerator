"""
每次只生成1章，避免被截断
"""
import logging
import sys
import json
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

def generate_one_chapter():
    """每次只生成1章"""

    # 读取配置
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)

    # 使用智谱AI
    llm_config = config.get('llm_configs', {}).get('智谱AI GLM-4.7', {})

    logger.info("=" * 80)
    logger.info("使用智谱AI - 每次生成1章")
    logger.info("=" * 80)

    # 初始化生成器
    from novel_generator.blueprint import StrictChapterGenerator

    generator = StrictChapterGenerator(
        interface_format=llm_config.get('interface_format'),
        api_key=llm_config.get('api_key'),
        base_url=llm_config.get('base_url'),
        llm_model=llm_config.get('model_name'),
        temperature=llm_config.get('temperature', 0.7),
        max_tokens=llm_config.get('max_tokens', 60000),
        timeout=llm_config.get('timeout', 1800)
    )

    # 检查架构文件
    arch_path = "wxhyj/Novel_architecture.txt"
    if not os.path.exists(arch_path):
        logger.error(f"❌ 架构文件不存在: {arch_path}")
        return False

    logger.info(f"✅ 架构文件: {os.path.getsize(arch_path)} 字节")

    # 逐章生成
    for chapter_num in range(1, 6):  # 生成第1-5章
        logger.info("\n" + "=" * 80)
        logger.info(f"开始生成第{chapter_num}章...")
        logger.info("=" * 80)

        try:
            from novel_generator.blueprint import Strict_Chapter_blueprint_generate

            success = Strict_Chapter_blueprint_generate(
                interface_format=llm_config.get('interface_format'),
                api_key=llm_config.get('api_key'),
                base_url=llm_config.get('base_url'),
                llm_model=llm_config.get('model_name'),
                filepath="wxhyj",
                number_of_chapters=chapter_num,  # 每次只生成到当前章
                batch_size=1,  # 批次大小设为1
                temperature=llm_config.get('temperature', 0.7),
                max_tokens=llm_config.get('max_tokens', 60000),
                timeout=llm_config.get('timeout', 1800)
            )

            if success:
                logger.info(f"✅ 第{chapter_num}章生成成功")

                # 验证结果
                result_path = "wxhyj/Novel_directory.txt"
                if os.path.exists(result_path):
                    with open(result_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # 检查第chapter_num章是否包含所有7个节
                    # 支持多种章节标题格式
                    chapter_pattern = rf'(?:### \*\*)?第{chapter_num}章[^\n]*?(?=(?:### \*\*)?第{chapter_num+1}章|$)'
                    chapter_match = re.search(chapter_pattern, content, re.DOTALL)

                    if chapter_match:
                        chapter_text = chapter_match.group(0)
                        # 检查是否有7个编号的节（1-7）
                        section_headers = re.findall(r'^(\d+)\.\s+', chapter_text, re.MULTILINE)
                        section_numbers = sorted(set(int(num) for num in section_headers))

                        if len(section_numbers) >= 7:
                            logger.info(f"✅ 第{chapter_num}章包含所有7个节")
                        else:
                            logger.warning(f"⚠️ 第{chapter_num}章节数量不足: 找到{len(section_numbers)}个节，需要7个")
            else:
                logger.error(f"❌ 第{chapter_num}章生成失败")
                break

        except Exception as e:
            logger.error(f"❌ 第{chapter_num}章生成异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            break

    logger.info("\n" + "=" * 80)
    logger.info("生成完成")
    logger.info("=" * 80)

    return True

if __name__ == "__main__":
    import re
    success = generate_one_chapter()
    sys.exit(0 if success else 1)
