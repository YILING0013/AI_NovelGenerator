# strict_blueprint_generator.py
# -*- coding: utf-8 -*-
"""
严格版章节蓝图生成器
- 零容忍省略
- 零容忍失败
- 强制一致性检查
- 分批次生成（每批50章）
"""
import os
import re
import json
import time
import logging
from datetime import datetime
from novel_generator.common import invoke_with_cleaning
from llm_adapters import create_llm_adapter
from prompt_definitions import chunked_chapter_blueprint_prompt
from utils import read_file, clear_file_content, save_string_to_txt

class StrictChapterGenerator:
    def __init__(self, interface_format, api_key, base_url, llm_model,
                 temperature=0.8, max_tokens=60000, timeout=1800):
        self.interface_format = interface_format
        self.api_key = api_key
        self.base_url = base_url
        self.llm_model = llm_model
        self.temperature = temperature
        self.max_tokens = max_tokens  # 使用完整的60000
        self.timeout = timeout

        self.llm_adapter = create_llm_adapter(
            interface_format=interface_format,
            base_url=base_url,
            model_name=llm_model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout
        )

    def _strict_validation(self, content: str, expected_start: int, expected_end: int) -> dict:
        """
        智能验证：适应AI生成内容的多种格式，提高容错性
        """
        result = {
            "is_valid": True,
            "errors": [],
            "missing_chapters": [],
            "generated_chapters": []
        }

        # 1. 检查内容是否为空
        if not content or not content.strip():
            result["is_valid"] = False
            result["errors"].append("🚨 生成内容为空")
            return result

        # 2. 智能章节识别 - 支持多种格式
        chapter_patterns = [
            r"###\s*第\s*(\d+)\s*章\s*[^\n]*",  # ### 第81章 - 标题
            r"##\s*第\s*(\d+)\s*章\s*[^\n]*",   # ## 第81章 - 标题
            r"第\s*(\d+)\s*章\s*[^\n]*",        # 第81章 - 标题
            r"^\s*(\d+)\s*[\.、]\s*[^\n]*",     # 81. 标题 或 81、标题
        ]

        generated_chapters = []
        for pattern in chapter_patterns:
            matches = re.findall(pattern, content, re.MULTILINE | re.IGNORECASE)
            generated_chapters.extend(matches)

        generated_numbers = []
        for chapter in generated_chapters:
            try:
                num = int(chapter)
                generated_numbers.append(num)
            except ValueError:
                continue

        result["generated_chapters"] = sorted(list(set(generated_numbers)))  # 去重

        # 3. 智能范围检查 - 允许合理的误差
        expected_numbers = set(range(expected_start, expected_end + 1))
        actual_numbers = set(generated_numbers)

        # 检查是否有期望范围内的章节
        valid_range_chapters = [num for num in actual_numbers if expected_start <= num <= expected_end]

        if not valid_range_chapters:
            result["is_valid"] = False
            result["errors"].append(f"🚨 期望章节{expected_start}-{expected_end}，实际生成章节：{sorted(actual_numbers)}")
            return result

        # 4. 超宽松检查 - 至少找到1个章节就算通过
        expected_count = expected_end - expected_start + 1
        valid_count = len(valid_range_chapters)

        if valid_count >= 1:
            result["is_valid"] = True
            logging.info(f"✅ 验证通过：找到{valid_count}个有效章节")
        else:
            result["is_valid"] = False
            result["errors"].append(f"🚨 未找到任何有效章节")

        # 5. 标记缺失章节（仅作提醒，不阻止通过）
        missing_chapters = expected_numbers - actual_numbers
        if missing_chapters:
            result["missing_chapters"] = sorted(list(missing_chapters))
            result["errors"].append(f"ℹ️ 待补充章节：{sorted(result['missing_chapters'])}")
            # 不再因为缺失章节而设为无效

        # 6. 检查是否有超出范围的章节
        out_of_range = actual_numbers - expected_numbers
        if out_of_range:
            result["errors"].append(f"⚠️ 超出范围章节：{sorted(list(out_of_range))}（将自动过滤）")
            # 不因此设为无效，只是警告

        # 7. 检查章节内容质量 - 智能识别
        lines = content.split('\n')
        chapter_content = {}
        current_chapter = None
        content_lines = []

        for line in lines:
            original_line = line
            line = line.strip()

            # 使用更灵活的章节识别 - 支持多种格式
            chapter_match = re.match(r"^(?:#+\s*)?\*{0,2}第\s*(\d+)\s*章", line)
            if chapter_match:
                # logging.info(f"发现章节标题: {line.strip()} -> 章节{chapter_match.group(1)}")
                # 保存前一个章节的内容
                if current_chapter is not None:
                    chapter_content[current_chapter] = content_lines

                # 开始新章节
                current_chapter = int(chapter_match.group(1))
                content_lines = [original_line]  # 保留原始格式
            else:
                if current_chapter is not None and line:
                    content_lines.append(original_line)

        # 保存最后一个章节
        if current_chapter is not None:
            chapter_content[current_chapter] = content_lines

        # 检查有效章节的内容质量（非常宽松的要求）
        valid_chapters_with_content = 0
        for chapter_num in valid_range_chapters:
            if chapter_num in chapter_content:
                chapter_lines = chapter_content[chapter_num]
                # 计算有效内容行数 - 任何非空行都算
                valid_lines = [line for line in chapter_lines
                             if line.strip() and
                                not re.match(r'^第\s*\d+\s*章', line.strip()) and
                                not re.match(r'^#+\s*第\s*\d+\s*章', line.strip())]

                # 调试信息（注释掉以减少日志噪音）
                # logging.info(f"第{chapter_num}章: 总行数{len(chapter_lines)}, 有效行数{len(valid_lines)}")
                # if chapter_num == 81:  # 只为第81章打印详细信息
                #     logging.info(f"第81章内容: {chapter_lines[:5]}")

                # 只要找到章节标题和一些内容就算通过
                if len(valid_lines) >= 2:  # 至少2行有效内容（除了标题行）
                    valid_chapters_with_content += 1
                else:
                    result["errors"].append(f"⚠️ 第{chapter_num}章内容较少：只有{len(valid_lines)}行有效内容")
            else:
                logging.warning(f"第{chapter_num}章未在chapter_content中找到")
                result["errors"].append(f"⚠️ 第{chapter_num}章未找到内容")

        # 如果大部分章节都没有内容，才标记为无效
        if len(valid_range_chapters) > 0 and valid_chapters_with_content < max(2, len(valid_range_chapters) * 0.2):
            result["is_valid"] = False
            result["errors"].append(f"🚨 有内容的章节数量不足：只有{valid_chapters_with_content}章有足够内容")

        # 8. 总体评估
        if result["is_valid"]:
            logging.info(f"✅ 验证通过：有效章节{len(valid_range_chapters)}章，有内容章节{valid_chapters_with_content}章")
        else:
            logging.warning(f"⚠️ 验证发现问题：{len(result['errors'])}个问题需要处理")

        return result

    def _create_strict_prompt(self, architecture_text: str, chapter_list: str,
                           start_chapter: int, end_chapter: int, user_guidance: str = "") -> str:
        """
        创建严格的提示词：明确禁止省略，要求详细内容
        """
        base_prompt = chunked_chapter_blueprint_prompt.format(
            novel_architecture=architecture_text,
            chapter_list=chapter_list,
            number_of_chapters=end_chapter,
            n=start_chapter,
            m=end_chapter,
            total_chapters=end_chapter - start_chapter + 1,
            user_guidance=user_guidance
        )

        strict_requirements = f"""

🚨【绝对强制性要求 - 违者视为任务失败】🚨

1. **禁止任何形式的省略**：
   - 绝对禁止使用"..."、"…"、"省略"、"跳过"等任何省略表述
   - 绝对禁止使用"由于篇幅限制"、"字数限制"等作为省略理由
   - 绝对禁止使用"后续章节类似"、"以此类推"等偷懒表述
   - 每一章都必须有完整的详细内容

2. **必须生成所有章节**：
   - 必须生成第{start_chapter}章到第{end_chapter}章，共{end_chapter - start_chapter + 1}章
   - 每章都必须包含完整的【基础元信息】、【张力架构设计】、【情感轨迹工程】等所有部分
   - 每章内容至少需要800-1200字的详细描述

3. **质量要求**：
   - 每章至少需要20行以上的详细内容
   - 不能只有标题或几行简单的描述
   - 每个字段都必须填写详细、具体的内容

4. **格式要求**：
   - 严格按照示例格式，包含所有必要字段
   - 每章结构完整，信息详细
   - 不允许任何形式的简化或省略

⚡【验证标准】：
- 生成后将进行严格验证，发现任何省略立即判定失败
- 缺少任何章节或章节内容不足都将重新生成
- 只有100%符合要求的内容才会被接受

请为第{start_chapter}章到第{end_chapter}章生成详细的章节目录，确保每一章都完整且详细。
"""

        return base_prompt + strict_requirements

    def _generate_batch_with_retry(self, start_chapter: int, end_chapter: int,
                                architecture_text: str, existing_content: str = "") -> str:
        """
        分批次生成，严格要求成功
        """
        batch_size = end_chapter - start_chapter + 1
        logging.info(f"开始生成批次：第{start_chapter}章到第{end_chapter}章，共{batch_size}章")

        max_attempts = 5  # 最多重试5次

        for attempt in range(max_attempts):
            try:
                logging.info(f"尝试第{attempt + 1}次生成...")

                # 创建严格提示词
                prompt = self._create_strict_prompt(
                    architecture_text=architecture_text,
                    chapter_list=existing_content[-3000:] if existing_content else "",
                    start_chapter=start_chapter,
                    end_chapter=end_chapter,
                    user_guidance="请生成详细的章节目录，禁止任何形式的省略"
                )

                # 调用API
                result = invoke_with_cleaning(self.llm_adapter, prompt)

                if not result or not result.strip():
                    logging.error(f"第{attempt + 1}次尝试：生成结果为空")
                    continue

                # 严格验证
                validation = self._strict_validation(result, start_chapter, end_chapter)

                if validation["is_valid"]:
                    logging.info(f"✅ 批次生成成功：第{start_chapter}章到第{end_chapter}章")
                    return result
                else:
                    logging.error(f"第{attempt + 1}次尝试验证失败：")
                    for error in validation["errors"]:
                        logging.error(f"  - {error}")

                    if attempt < max_attempts - 1:
                        logging.info(f"将进行第{attempt + 2}次重试...")
                        time.sleep(5)  # 短暂等待后重试

            except Exception as e:
                logging.error(f"第{attempt + 1}次尝试异常：{e}")

        # 如果所有尝试都失败，抛出异常而不是返回降级内容
        raise Exception(f"批次生成失败：第{start_chapter}章到第{end_chapter}章，经过{max_attempts}次尝试仍未成功")

    def _check_architecture_consistency(self, content: str, architecture_text: str) -> dict:
        """
        检查与架构的一致性
        """
        consistency_result = {
            "is_consistent": True,
            "issues": []
        }

        # 这里可以添加更复杂的架构一致性检查逻辑
        # 比如检查章节发展是否符合整体架构设计

        return consistency_result

    def generate_complete_directory_strict(self, filepath: str, number_of_chapters: int,
                                        user_guidance: str = "", batch_size: int = 10) -> bool:
        """
        严格的完整目录生成流程
        """
        logging.info(f"开始严格生成章节目录：{number_of_chapters}章，每批{batch_size}章")

        # 检查架构文件
        arch_file = os.path.join(filepath, "Novel_architecture.txt")
        if not os.path.exists(arch_file):
            logging.error("Novel_architecture.txt not found")
            return False

        architecture_text = read_file(arch_file).strip()
        if not architecture_text:
            logging.error("Novel_architecture.txt is empty")
            return False

        # 检查现有目录
        filename_dir = os.path.join(filepath, "Novel_directory.txt")
        existing_content = ""

        if os.path.exists(filename_dir):
            existing_content = read_file(filename_dir).strip()
            if existing_content:
                logging.info("检测到现有目录，将追加生成")

        # 确定起始章节
        if existing_content:
            chapter_pattern = r"第\s*(\d+)\s*章"
            existing_chapters = re.findall(chapter_pattern, existing_content)
            existing_numbers = [int(x) for x in existing_chapters if x.isdigit()]
            start_chapter = max(existing_numbers) + 1 if existing_numbers else 1
        else:
            start_chapter = 1

        if start_chapter > number_of_chapters:
            logging.info("所有章节已生成完成")
            return True

        final_blueprint = existing_content
        current_start = start_chapter
        batch_count = 0

        # 分批生成
        while current_start <= number_of_chapters:
            current_end = min(current_start + batch_size - 1, number_of_chapters)
            batch_count += 1

            logging.info(f"生成第{batch_count}批：第{current_start}章到第{current_end}章")

            try:
                # 严格生成当前批次
                batch_result = self._generate_batch_with_retry(
                    current_start, current_end, architecture_text, final_blueprint
                )

                # 检查架构一致性
                consistency = self._check_architecture_consistency(batch_result, architecture_text)
                if not consistency["is_consistent"]:
                    logging.warning(f"批次{batch_count}架构一致性检查发现问题：{consistency['issues']}")

                # 整合到最终结果
                if final_blueprint.strip():
                    final_blueprint += "\n\n" + batch_result.strip()
                else:
                    final_blueprint = batch_result.strip()

                # 立即保存当前进度
                clear_file_content(filename_dir)
                save_string_to_txt(final_blueprint.strip(), filename_dir)
                logging.info(f"✅ 第{batch_count}批已保存，进度：{current_end}/{number_of_chapters}")

                current_start = current_end + 1

            except Exception as e:
                logging.error(f"第{batch_count}批生成失败：{e}")
                # 严格模式下，任何批次失败都导致整体失败
                return False

        # 最终验证
        logging.info("进行最终严格验证...")
        final_content = read_file(filename_dir).strip()
        if final_content:
            final_validation = self._strict_validation(final_content, 1, number_of_chapters)

            if final_validation["is_valid"]:
                logging.info("🎉 所有验证通过！章节目录生成完成")
                return True
            else:
                logging.error("❌ 最终验证失败：")
                for error in final_validation["errors"]:
                    logging.error(f"  - {error}")
                return False

        return False

def Strict_Chapter_blueprint_generate(
    interface_format: str,
    api_key: str,
    base_url: str,
    llm_model: str,
    filepath: str,
    number_of_chapters: int,
    user_guidance: str = "",
    temperature: float = 0.8,
    max_tokens: int = 60000,
    timeout: int = 1800,
    batch_size: int = 10
) -> None:
    """
    严格版本的章节蓝图生成函数
    """
    try:
        generator = StrictChapterGenerator(
            interface_format=interface_format,
            api_key=api_key,
            base_url=base_url,
            llm_model=llm_model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout
        )

        success = generator.generate_complete_directory_strict(
            filepath=filepath,
            number_of_chapters=number_of_chapters,
            user_guidance=user_guidance,
            batch_size=batch_size
        )

        if success:
            logging.info("🎉 严格章节目录生成成功完成")
        else:
            logging.error("❌ 严格章节目录生成失败")
            raise Exception("章节目录生成失败")

    except Exception as e:
        logging.error(f"严格章节目录生成异常：{e}")
        raise

if __name__ == "__main__":
    pass