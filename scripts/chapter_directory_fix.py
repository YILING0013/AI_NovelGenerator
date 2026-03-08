# chapter_directory_fix.py
# -*- coding: utf-8 -*-
"""
修复Novel_directory.txt中缺失的章节目录
"""
import os
import re
import logging
from datetime import datetime
from novel_generator.common import invoke_with_cleaning
from llm_adapters import create_llm_adapter
from prompt_definitions import chunked_chapter_blueprint_prompt, BLUEPRINT_EXAMPLE_V3
from utils import read_file, clear_file_content, save_string_to_txt

# 配置日志
logging.basicConfig(
    filename='chapter_fix.log',
    filemode='a',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def analyze_missing_chapters(directory_file: str) -> dict:
    """
    分析目录文件中缺失的章节
    """
    content = read_file(directory_file).strip()
    if not content:
        return {"existing_chapters": [], "missing_chapters": [], "empty_chapters": []}

    # 解析现有章节
    chapter_pattern = r'^第\s*(\d+)\s*章\s*(?:\[(.*)\]|\s*)\s*$'
    lines = content.split('\n')

    existing_chapters = []
    empty_chapters = []
    current_chapter = None
    chapter_content = {}

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 检查是否是章节标题
        chapter_match = re.match(chapter_pattern, line)
        if chapter_match:
            chapter_num = int(chapter_match.group(1))
            chapter_title = chapter_match.group(2) if chapter_match.group(2) else ""

            # 保存前一个章节的信息
            if current_chapter is not None:
                content_lines = [l for l in chapter_content[current_chapter] if l.strip() and not l.startswith('第')]
                if len(content_lines) <= 3:  # 内容太少，认为是空章节
                    empty_chapters.append(current_chapter)
                else:
                    existing_chapters.append(current_chapter)

            # 开始新章节
            current_chapter = chapter_num
            chapter_content[current_chapter] = [line]
        else:
            if current_chapter is not None:
                chapter_content[current_chapter].append(line)

    # 处理最后一个章节
    if current_chapter is not None:
        content_lines = [l for l in chapter_content[current_chapter] if l.strip() and not l.startswith('第')]
        if len(content_lines) <= 3:
            empty_chapters.append(current_chapter)
        else:
            existing_chapters.append(current_chapter)

    # 找出缺失的章节（假设应该是连续的）
    if existing_chapters + empty_chapters:
        max_chapter = max(existing_chapters + empty_chapters)
        expected_chapters = list(range(1, max_chapter + 1))
        missing_chapters = set(expected_chapters) - set(existing_chapters + empty_chapters)
    else:
        missing_chapters = []

    return {
        "existing_chapters": sorted(existing_chapters),
        "missing_chapters": sorted(list(missing_chapters)),
        "empty_chapters": sorted(empty_chapters),
        "chapter_content": chapter_content
    }

def generate_missing_chapters(
    interface_format: str,
    api_key: str,
    base_url: str,
    llm_model: str,
    filepath: str,
    missing_chapters: list,
    existing_content: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    timeout: int = 600
) -> str:
    """
    生成缺失章节的内容
    """
    arch_file = os.path.join(filepath, "Novel_architecture.txt")
    if not os.path.exists(arch_file):
        logging.error("Novel_architecture.txt not found")
        return ""

    architecture_text = read_file(arch_file).strip()
    if not architecture_text:
        logging.error("Novel_architecture.txt is empty")
        return ""

    llm_adapter = create_llm_adapter(
        interface_format=interface_format,
        base_url=base_url,
        model_name=llm_model,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout
    )

    # 分批生成缺失章节（每批最多10章）
    batch_size = 10
    generated_content = ""

    for i in range(0, len(missing_chapters), batch_size):
        batch_chapters = missing_chapters[i:i+batch_size]
        start_chapter = batch_chapters[0]
        end_chapter = batch_chapters[-1]

        logging.info(f"Generating missing chapters batch: {batch_chapters}")

        # 构建生成提示词
        chunk_prompt = chunked_chapter_blueprint_prompt.format(
            novel_architecture=architecture_text,
            chapter_list=existing_content[-2000:],  # 使用最近2000字符作为上下文
            n=start_chapter,
            m=end_chapter,
            total_chapters=end_chapter - start_chapter + 1,
            blueprint_example=BLUEPRINT_EXAMPLE_V3
        )

        # 添加额外的严格要求
        strict_prompt = chunk_prompt + f"""

🚨【紧急修复任务 - 缺失章节生成】🚨
检测到以下章节缺失或内容不完整：{batch_chapters}

🔥【严格要求】
1. 必须生成第{start_chapter}章到第{end_chapter}章的完整内容
2. 每章都需要包含详细的信息：
   - 写作重点、作用、张力评级
   - 情感弧光、关键转折点、情感记忆点
   - 冲突设计、人物弧光、限制条件
   - 开场设计、高潮安排、收尾策略
   - 主钩子、次钩子、长期伏笔
   - 风格要求、语言特色、关键场景
3. 绝对禁止使用省略号或"篇幅限制"等借口
4. 每章内容应在800-1200字左右
5. 确保与前后章节的逻辑连贯性

这是修复任务，关系到小说的完整性，请务必认真生成！
"""

        try:
            result = invoke_with_cleaning(llm_adapter, strict_prompt)
            if result and result.strip():
                generated_content += "\n\n" + result.strip()
                logging.info(f"Successfully generated batch {i//batch_size + 1}: chapters {batch_chapters}")
            else:
                logging.error(f"Empty result for batch {i//batch_size + 1}: chapters {batch_chapters}")
        except Exception as e:
            logging.error(f"Error generating batch {i//batch_size + 1}: {e}")

    return generated_content.strip()

def fix_chapter_directory(
    interface_format: str,
    api_key: str,
    base_url: str,
    llm_model: str,
    filepath: str
) -> bool:
    """
    修复章节目录的主函数
    """
    directory_file = os.path.join(filepath, "Novel_directory.txt")

    if not os.path.exists(directory_file):
        logging.error("Novel_directory.txt not found")
        return False

    logging.info("开始分析章节目录完整性...")

    # 分析现有章节
    analysis = analyze_missing_chapters(directory_file)
    existing_chapters = analysis["existing_chapters"]
    missing_chapters = analysis["missing_chapters"]
    empty_chapters = analysis["empty_chapters"]

    logging.info(f"分析结果：")
    logging.info(f"- 完整章节：{len(existing_chapters)} 章 ({existing_chapters[:10]}...)")
    logging.info(f"- 空章节：{len(empty_chapters)} 章 ({empty_chapters[:10]}...)")
    logging.info(f"- 缺失章节：{len(missing_chapters)} 章 ({missing_chapters[:10]}...)")

    if not missing_chapters and not empty_chapters:
        logging.info("✅ 章节目录完整，无需修复")
        return True

    # 读取现有内容
    existing_content = read_file(directory_file).strip()

    # 生成缺失章节
    all_missing = missing_chapters + empty_chapters
    if all_missing:
        logging.info(f"开始生成 {len(all_missing)} 个缺失/空章节的内容...")

        generated_content = generate_missing_chapters(
            interface_format=interface_format,
            api_key=api_key,
            base_url=base_url,
            llm_model=llm_model,
            filepath=filepath,
            missing_chapters=all_missing,
            existing_content=existing_content
        )

        if generated_content:
            # 合并内容
            new_content = existing_content + "\n\n" + generated_content
            new_content = re.sub(r'\n{3,}', '\n\n', new_content)  # 清理多余的空行

            # 保存修复后的文件
            backup_file = directory_file + f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            os.rename(directory_file, backup_file)
            logging.info(f"原文件已备份到：{backup_file}")

            clear_file_content(directory_file)
            save_string_to_txt(new_content.strip(), directory_file)

            logging.info(f"✅ 章节目录修复完成，共生成 {len(generated_content)} 字符内容")
            return True
        else:
            logging.error("❌ 生成缺失章节失败")
            return False
    else:
        logging.info("✅ 没有需要修复的章节")
        return True

if __name__ == "__main__":
    # 这里需要从配置文件读取设置
    # 示例用法：
    # fix_chapter_directory(
    #     interface_format="openai",
    #     api_key="your_api_key",
    #     base_url="https://api.openai.com/v1",
    #     llm_model="gpt-4",
    #     filepath="path/to/your/novel"
    # )
    pass
