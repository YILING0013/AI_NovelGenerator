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
from prompt_definitions import (
    chunked_chapter_blueprint_prompt,  # 已弃用，保留兼容性
    BLUEPRINT_EXAMPLE_V3  # Few-Shot示例
)
from utils import read_file, clear_file_content, save_string_to_txt
from novel_generator.architecture_extractor import DynamicArchitectureExtractor

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

        # 🚨 LLM 对话日志记录器
        self.llm_log_dir = None  # 将在生成时设置
        self.current_log_file = None
        self.llm_conversation_log = []  # 存储当前批次的对话日志

        self.llm_adapter = create_llm_adapter(
            interface_format=interface_format,
            base_url=base_url,
            model_name=llm_model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout
        )

    def _init_llm_log(self, filepath: str, start_chapter: int, end_chapter: int):
        """初始化 LLM 对话日志文件"""
        from datetime import datetime

        try:
            # 创建日志目录
            self.llm_log_dir = os.path.join(filepath, "llm_conversation_logs")
            os.makedirs(self.llm_log_dir, exist_ok=True)

            # 创建日志文件名（按章节范围）
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_filename = f"llm_log_chapters_{start_chapter}-{end_chapter}_{timestamp}.md"
            self.current_log_file = os.path.join(self.llm_log_dir, log_filename)

            # 初始化日志内容
            self.llm_conversation_log = []

            # 写入日志头部
            header = f"""# LLM 对话日志 - 第{start_chapter}章到第{end_chapter}章

**生成时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**章节范围**: 第{start_chapter}章 - 第{end_chapter}章
**LLM模型**: {self.llm_model}
**温度参数**: {self.temperature}

---

"""
            with open(self.current_log_file, 'w', encoding='utf-8') as f:
                f.write(header)

            logging.info(f"🚨 LLM对话日志已初始化: {self.current_log_file}")
        except Exception as e:
            logging.error(f"❌ 初始化LLM对话日志失败: {e}")
            self.current_log_file = None
            self.llm_log_dir = None

    def _log_llm_call(self, call_type: str, prompt: str, response: str,
                     validation_result: dict = None, metadata: dict = None):
        """记录单次LLM调用"""
        from datetime import datetime

        # 🚨 检查日志文件是否已初始化
        if not self.current_log_file:
            return

        timestamp = datetime.now().strftime("%H:%M:%S")

        log_entry = f"""## {call_type} - {timestamp}

### 📝 Prompt (提示词)
```
{prompt[:3000]}{"..." if len(prompt) > 3000 else ""}
```

### 🤖 Response (LLM响应)
```
{response[:5000]}{"..." if len(response) > 5000 else ""}
```

### 📊 元数据
"""

        # 添加元数据
        if metadata:
            for key, value in metadata.items():
                log_entry += f"- **{key}**: {value}\n"

        # 添加验证结果
        if validation_result:
            log_entry += f"\n### ✅ 验证结果\n"
            log_entry += f"- **是否通过**: {'✅ 是' if validation_result.get('is_valid') else '❌ 否'}\n"

            if validation_result.get('generated_chapters'):
                log_entry += f"- **生成的章节**: {validation_result['generated_chapters']}\n"

            if validation_result.get('errors'):
                log_entry += f"- **错误信息**:\n"
                for error in validation_result['errors']:
                    log_entry += f"  - {error}\n"

        log_entry += "\n---\n\n"

        # 追加到内存日志
        self.llm_conversation_log.append(log_entry)

        # 立即写入文件
        try:
            with open(self.current_log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)
            logging.info(f"📝 已记录LLM调用: {call_type}")
        except Exception as e:
            logging.error(f"❌ 写入LLM调用日志失败: {e}")

    def _log_separator(self, title: str):
        """记录分隔符"""
        from datetime import datetime

        # 🚨 检查日志文件是否已初始化
        if not self.current_log_file:
            return

        separator = f"""
# {title} - {datetime.now().strftime("%H:%M:%S")}

---

"""
        try:
            with open(self.current_log_file, 'a', encoding='utf-8') as f:
                f.write(separator)
        except Exception as e:
            logging.error(f"❌ 写入分隔符失败: {e}")

    def _save_llm_log(self):
        """保存当前批次日志到文件"""
        if not self.current_log_file:
            return

        # 追加所有日志到文件
        with open(self.current_log_file, 'a', encoding='utf-8') as f:
            f.write("\n".join(self.llm_conversation_log))

    def _finalize_llm_log(self, success: bool, error_message: str = ""):
        """完成日志文件，添加最终状态"""
        from datetime import datetime

        # 🚨 检查日志文件是否存在，避免因初始化失败导致文件不存在
        if not self.current_log_file or not os.path.exists(self.current_log_file):
            logging.warning(f"⚠️ 日志文件不存在，跳过完成日志写入: {self.current_log_file}")
            return

        status = "✅ 成功" if success else "❌ 失败"
        footer = f"""
# 🏁 生成完成 - {datetime.now().strftime("%H:%M:%S")}

**最终状态**: {status}
"""

        if error_message:
            footer += f"**错误信息**: {error_message}\n"

        footer += f"""
**日志条目数**: {len(self.llm_conversation_log)}
**结束时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

---

*本日志由 AI 小说生成工具自动生成*
"""

        try:
            with open(self.current_log_file, 'a', encoding='utf-8') as f:
                f.write(footer)
            logging.info(f"🚨 LLM对话日志已完成: {self.current_log_file} (状态: {status})")
        except Exception as e:
            logging.error(f"❌ 写入日志文件失败: {e}")

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

        # 2. 智能章节识别 - 区分"章节标题"和"内容引用"
        # 🚨 关键修复：只检测行首的章节标题，忽略内容中的引用
        # 匹配行首的章节标题：支持"第X章 - 标题"或"第X章\n"格式
        chapter_title_pattern = r"(?:^|\n)第\s*(\d+)\s*章(?:\s*[-–—]\s*[^\n]*|\n)"
        chapter_titles = re.findall(chapter_title_pattern, content, re.MULTILINE)
        generated_numbers = [int(ch) for ch in chapter_titles if ch.isdigit()]

        # 🆕 章节结构完整性检查
        # 检测是否有"章节中断"或"内容混叠"的情况
        # 例如：第1章内容还没结束就出现第2章的标题
        lines = content.split('\n')
        chapter_sections = {}  # 章节号 -> [起始行, 结束行, 内容长度]
        current_chapter = None
        chapter_start_line = 0

        # 🔍 首先检测章节混叠（章节标题出现在其他章节的内容中）
        # 🚨 修复：只检测真正的独立章节标题行，忽略合法的上下文引用（如"启下"中的提及）
        content_mixed_chapters = []

        # 需要跳过的上下文：在以下节中，"第X章"的引用是合法的
        allowed_sections = {
            '衔接设计', '伏笔埋设', '启下', '伏笔', '回顾', '总结', '设计', '埋设'
        }

        current_section = None

        for i, line in enumerate(lines):
            stripped_line = line.strip()

            # 检测当前在哪个节
            if re.match(r'^##?\s*\d+\.\s*([一-龥]+)', stripped_line):
                section_title_match = re.match(r'^##?\s*\d+\.\s*([一-龥]+)', stripped_line)
                if section_title_match:
                    current_section = section_title_match.group(1)
                continue

            # 如果当前在允许引用"第X章"的节中，跳过检测
            if current_section and any(allowed in current_section for allowed in allowed_sections):
                continue

            # 如果是空行或格式标记（如**章节**: 第X章），跳过
            if not stripped_line or re.match(r'^\*\*[一-龥]+\*\*[:：]', stripped_line):
                continue

            # 检测章节标题（只检测行首的独立章节标题）
            if re.match(r'^第\s*\d+\s*章', stripped_line):
                chapter_match = re.search(r'第\s*(\d+)\s*章', stripped_line)
                if chapter_match:
                    detected_chapter = int(chapter_match.group(1))
                    # 只有当章节号超出预期范围时才标记为混叠
                    if detected_chapter > expected_end or detected_chapter < expected_start:
                        content_mixed_chapters.append({
                            'line_num': i + 1,
                            'content': stripped_line[:80],
                            'detected_chapter': detected_chapter
                        })
        if content_mixed_chapters:
            for mixed in content_mixed_chapters:
                error_msg = f"🚨 章节内容混叠：第{mixed['detected_chapter']}章的标题出现在第{mixed['line_num']}行（章节内容中）：{mixed['content']}..."
                result["errors"].append(error_msg)
                result["is_valid"] = False
            logging.warning(f"检测到章节内容混叠：{len(content_mixed_chapters)}处")

        # 如果检测到混叠，直接返回失败
        if not result["is_valid"]:
            return result

        for i, line in enumerate(lines):
            # 🆕 改进的章节标题检测：支持行首和非行首
            # 匹配"第X章"或"章节序号：第X章"等格式
            chapter_patterns = [
                r'^第\s*(\d+)\s*章',                      # 行首：第X章
                r'章节[序号标题]*[:：]\s*第\s*(\d+)\s*章',  # "章节序号：第X章"
                r'\*\*章节\*\*[:：]\s*第\s*(\d+)\s*章',    # "**章节**: 第X章"
            ]

            chapter_num = None
            for pattern in chapter_patterns:
                match = re.search(pattern, line)
                if match:
                    chapter_num = int(match.group(1))
                    break

            if chapter_num is not None:

                # 如果之前有章节在处理，记录其结束位置
                if current_chapter is not None:
                    if current_chapter in chapter_sections:
                        chapter_sections[current_chapter][1] = i - 1
                        chapter_sections[current_chapter][2] = i - chapter_start_line

                # 开始新章节
                current_chapter = chapter_num
                chapter_start_line = i
                if chapter_num not in chapter_sections:
                    chapter_sections[chapter_num] = [i, i, 0]  # [起始, 结束, 长度]

        # 记录最后一个章节
        if current_chapter is not None and current_chapter in chapter_sections:
            chapter_sections[current_chapter][1] = len(lines) - 1
            chapter_sections[current_chapter][2] = len(lines) - chapter_start_line

        # 检查章节完整性
        incomplete_chapters = []
        expected_numbers = set(range(expected_start, expected_end + 1))
        for chapter_num in expected_numbers:
            if chapter_num in chapter_sections:
                start_line, end_line, content_length = chapter_sections[chapter_num]
                # 检查内容长度：如果小于15行，认为章节不完整（允许简洁格式）
                if content_length < 15:
                    incomplete_chapters.append(f"第{chapter_num}章（仅{content_length}行，不完整）")

        if incomplete_chapters:
            result["is_valid"] = False
            result["errors"].append(f"🚨 章节结构不完整：{'; '.join(incomplete_chapters)}")

        # 🆕 节标题重复检测
        # 检测每个章节内是否有重复的节标题（如"## 1. 基础元信息"出现多次）
        section_header_pattern = r'^##\s+\d+\.\s+[\u4e00-\u9fa5]+'
        repeated_sections = []

        for chapter_num in expected_numbers:
            # 提取该章节的内容范围
            if chapter_num in chapter_sections:
                start_line = chapter_sections[chapter_num][0]
                # 找到该章节的结束行（下一个章节开始前，或文件结束）
                if chapter_num < expected_end and (chapter_num + 1) in chapter_sections:
                    end_line = chapter_sections[chapter_num + 1][0]
                else:
                    end_line = len(lines)

                chapter_lines = lines[start_line:end_line]

                # 统计节标题出现次数
                section_counts = {}
                for line in chapter_lines:
                    match = re.match(section_header_pattern, line)
                    if match:
                        section_title = match.group(0)
                        section_counts[section_title] = section_counts.get(section_title, 0) + 1

                # 检查是否有节标题重复
                for section_title, count in section_counts.items():
                    if count > 1:
                        repeated_sections.append(f"第{chapter_num}章中'{section_title}'重复了{count}次")

        if repeated_sections:
            result["is_valid"] = False
            result["errors"].append(f"🚨 节标题重复检测：{'; '.join(repeated_sections)}")

        # 🆕 节完整性检测
        # 检查每个章节是否包含所有必需的节
        required_sections = ["基础元信息", "张力与冲突", "匠心思维应用", "伏笔与信息差",
                           "暧昧与修罗场", "剧情精要", "衔接设计"]
        missing_sections = []

        for chapter_num in expected_numbers:
            if chapter_num in chapter_sections:
                start_line = chapter_sections[chapter_num][0]
                if chapter_num < expected_end and (chapter_num + 1) in chapter_sections:
                    end_line = chapter_sections[chapter_num + 1][0]
                else:
                    end_line = len(lines)

                chapter_lines = lines[start_line:end_line]
                chapter_text = '\n'.join(chapter_lines)

                # 检查每个必需的节是否存在
                chapter_missing = []
                for required_section in required_sections:
                    if required_section not in chapter_text:
                        chapter_missing.append(required_section)

                if chapter_missing:
                    missing_sections.append(f"第{chapter_num}章缺失: {', '.join(chapter_missing)}")

        if missing_sections:
            result["is_valid"] = False
            result["errors"].append(f"🚨 节完整性检测：{'; '.join(missing_sections)}")

        # 🆕 智能重复检测
        # 规则：如果同一章节号出现超过2次，才认为是错误
        # 1次：正常
        # 2次：可能是内容引用（如"第1章的伏笔"），可接受
        # 3次及以上：肯定是LLM重复生成，拒绝
        unique_numbers = list(set(generated_numbers))
        duplicate_numbers = []
        for num in unique_numbers:
            count = generated_numbers.count(num)
            if count > 2:
                duplicate_numbers.append(num)

        if duplicate_numbers:
            result["is_valid"] = False
            result["errors"].append(f"🚨 检测到过度重复：{sorted(duplicate_numbers)}（每章出现{[generated_numbers.count(n) for n in duplicate_numbers]}次，超过2次上限）")

        # 🆕 格式混乱检测 - 检测 `第 X 章` 格式（有空格）
        loose_pattern = r"(?m)^[#*\s]*第\s+\d+\s+章"
        loose_matches = re.findall(loose_pattern, content)
        if loose_matches:
            result["is_valid"] = False
            result["errors"].append(f"🚨 检测到格式混乱：发现{len(loose_matches)}个章节使用了 `第 X 章` 格式（有空格），应为 `第X章` 格式（无空格）")

        result["generated_chapters"] = sorted(unique_numbers)

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
        # 🚨 但如果之前已经检测到重复或格式混乱，则不能通过
        expected_count = expected_end - expected_start + 1
        valid_count = len(valid_range_chapters)

        if valid_count >= 1 and result["is_valid"]:
            # 只有在之前没有错误的情况下才设置通过
            result["is_valid"] = True
            logging.info(f"✅ 验证通过：找到{valid_count}个有效章节")
        elif valid_count >= 1 and not result["is_valid"]:
            # 有章节但之前有错误（重复/格式混乱），保持失败状态
            logging.warning(f"⚠️ 找到{valid_count}个有效章节，但因存在重复或格式混乱，验证失败")
        else:
            result["is_valid"] = False
            result["errors"].append(f"🚨 未找到任何有效章节")

        # 5. 标记缺失章节（仅作提醒，不阻止通过）
        missing_chapters = expected_numbers - actual_numbers
        if missing_chapters:
            result["missing_chapters"] = sorted(list(missing_chapters))
            result["errors"].append(f"🚨 必须包含所有章节！缺失：{sorted(result['missing_chapters'])}")
            result["is_valid"] = False  # 恢复严格模式：缺失章节即失败

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
        # 阈值计算：至少需要1章，或者期望章节数的20%（以较大者为准）
        threshold = max(1, len(valid_range_chapters) * 0.2)
        if len(valid_range_chapters) > 0 and valid_chapters_with_content < threshold:
            result["is_valid"] = False
            result["errors"].append(f"🚨 有内容的章节数量不足：只有{valid_chapters_with_content}章有足够内容（需要至少{threshold:.0f}章）")

        # 8. 总体评估
        if result["is_valid"]:
            logging.info(f"✅ 验证通过：有效章节{len(valid_range_chapters)}章，有内容章节{valid_chapters_with_content}章")
        else:
            logging.warning(f"⚠️ 验证发现问题：{len(result['errors'])}个问题需要处理")

        return result

    def _extract_chapter_titles_only(self, existing_content: str, max_chapters: int = 10) -> str:
        """
        从已有内容中仅提取章节标题，避免展示旧格式导致LLM模仿错误格式

        Args:
            existing_content: 已有的章节目录内容
            max_chapters: 最多提取多少章的标题

        Returns:
            格式化的章节标题列表字符串
        """
        if not existing_content:
            return ""

        import re

        # 匹配多种章节标题格式
        patterns = [
            r'^(第\d+章[：\s\-——]+.+?)(?:\n|$)',  # 第1章：标题 或 第1章 - 标题
            r'^第(\d+)章[：\s\-——]*(.+?)(?:\n|$)',  # 第1章标题
            r'^【(.+?)】.*?章节.*?[:：](.+?)(?:\n|$)',  # 【基础元信息】章节标题：xxx
        ]

        titles = []
        seen_chapters = set()

        for line in existing_content.split('\n'):
            line = line.strip()
            if not line:
                continue

            # 尝试匹配章节标题
            for pattern in patterns:
                match = re.match(pattern, line)
                if match:
                    # 提取章节号和标题
                    if '第' in line and '章' in line:
                        # 直接使用匹配到的完整标题行
                        title = line
                        # 提取章节号用于去重
                        chapter_match = re.search(r'第(\d+)章', title)
                        if chapter_match:
                            chapter_num = chapter_match.group(1)
                            if chapter_num not in seen_chapters:
                                seen_chapters.add(chapter_num)
                                titles.append(title)
                    break

            if len(titles) >= max_chapters:
                break

        if titles:
            # 返回简洁的标题列表
            result = "以下是已生成章节的标题列表（仅用于了解剧情连贯性）：\n"
            result += "\n".join(titles)
            return result
        else:
            # 如果无法提取标题，返回空字符串
            return ""


    def _auto_fix_missing_sections(self, content: str, validation_result: dict) -> tuple[str, bool]:
        """
        自动修复缺失的节，支持修复多个连续缺失的节

        增强版：可以修复如"第2章缺失: 暧昧与修罗场, 剧情精要, 衔接设计"这种情况
        """
        import re

        errors = validation_result.get("errors", [])
        section_errors = [e for e in errors if "节完整性检测" in e or "缺失:" in e]

        if not section_errors:
            return content, False

        logging.info("🔧 尝试自动修复缺失的节（增强版）...")

        # 定义所有可能的节模板
        section_templates = {
            5: ("暧昧与修罗场", """## 5. 暧昧与修罗场
*   **涉及的女性角色互动**：本章不涉及女性角色互动
*   **说明**：本章未涉及女性角色互动，保留此节以满足格式要求"""),
            6: ("剧情精要", """## 6. 剧情精要
*   **开场**：[开场场景]
*   **发展**：[剧情发展节点]
*   **高潮**：[高潮事件]
*   **收尾**：[结尾状态/悬念]"""),
            7: ("衔接设计", """## 7. 衔接设计
*   **承上**：[承接前文]
*   **转场**：[转场方式]
*   **启下**：[为后续埋下伏笔]""")
        }

        lines = content.split('\n')
        fixed_lines = []
        i = 0
        fixes_made = 0

        # 解析需要修复的章节和缺失的节
        chapters_to_fix = {}  # {章节号: 缺失的节列表}
        for error in section_errors:
            match = re.search(r'第(\d+)章缺失:\s*(.+)', error)
            if match:
                chapter_num = int(match.group(1))
                missing_sections = match.group(2).strip()
                # 解析缺失的节
                missing_list = [s.strip() for s in missing_sections.split(',')]
                chapters_to_fix[chapter_num] = missing_list

        if not chapters_to_fix:
            return content, False

        logging.info(f"📋 需要修复的章节: {list(chapters_to_fix.keys())}")
        for ch, secs in chapters_to_fix.items():
            logging.info(f"  第{ch}章缺失节: {secs}")

        current_chapter = None
        last_section = None
        in_chapter = False

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # 检测章节标题
            chapter_match = re.match(r'^#{1,3}\s*\*{0,2}\s*第(\d+)章', stripped) or \
                           re.match(r'^\*{0,2}第(\d+)章', stripped)

            if chapter_match:
                current_chapter = int(chapter_match.group(1))
                last_section = None
                in_chapter = True
                fixed_lines.append(line)
                i += 1
                continue

            # 检测节标题
            section_match = re.match(r'^##\s*(\d+)\.\s*(.+)', stripped)
            if section_match and in_chapter and current_chapter in chapters_to_fix:
                section_num = int(section_match.group(1))
                section_name = section_match.group(2).strip()

                # 检查是否需要插入缺失的节
                if section_num > 1:
                    missing_sections = chapters_to_fix[current_chapter]
                    for missing_num in range(last_section + 1, section_num):
                        if missing_num in section_templates:
                            missing_name, missing_template = section_templates[missing_num]
                            if any(missing_name in s for s in missing_sections):
                                logging.info(f"  🔧 在第{current_chapter}章第{last_section}节后插入第{missing_num}节（{missing_name}）")
                                fixed_lines.append("")
                                for template_line in missing_template.split('\n'):
                                    fixed_lines.append(template_line)
                                fixed_lines.append("")
                                fixes_made += 1

                last_section = section_num

            fixed_lines.append(line)
            i += 1

        if fixes_made > 0:
            fixed_content = '\n'.join(fixed_lines)
            logging.info(f"✅ 自动修复完成，共修复了 {fixes_made} 个节")
            return fixed_content, True
        else:
            logging.warning("⚠️ 无法自动修复")
            return content, False


    def _create_strict_prompt_with_guide(self, architecture_text: str, context_guide: str, chapter_list: str,
                           start_chapter: int, end_chapter: int, user_guidance: str = "") -> str:
        """
        创建严格提示词 (两阶段版) - 使用 Context Guide 替代完整架构
        """
        
        # 构建强化版Prompt
        # 1. 基础信息
        prompt_header = f"""
你是一位严谨的小说蓝图架构师。请根据【生成指南】为《补天》生成**第{start_chapter}-{end_chapter}章**的详细蓝图。

### 核心参考资料（必须严格执行）
{context_guide}

### 已有章节概览
{chapter_list}

⚠️ **重要警告**：以上"已有章节概览"仅用于了解剧情连贯性，**严禁模仿其格式**！你必须严格按照下方的标准格式（7个节）生成，不能省略任何节。

{user_guidance}
"""

        # 2. Few-Shot示例（展示正确的格式）
        few_shot_example = f"""

📚 **参考范例**（学习其格式和深度，但严禁抄袭剧情）：

{BLUEPRINT_EXAMPLE_V3}

⚠️ **重要警告**：上述范例仅用于学习格式。你现在的任务是生成 **第{start_chapter}章到第{end_chapter}章** 的内容，必须根据【生成指南】和【已有章节】继续推进剧情，**绝对禁止**复制范例中的剧情！

"""

        # 3. 模板与格式约束
        strict_requirements = f"""
🚨【绝对强制性要求】🚨

1. **章节格式规范**：

每个章节必须遵循以下结构（按顺序，**每个节标题只能出现一次，所有7个节都必须存在**）：

   ### **第X章 - [章节标题]**

   ## 1. 基础元信息
   *   **章节序号**：第X章
   *   **章节标题**：[章节标题]
   *   **定位**：第[X]卷 [卷名] - 子幕[X] [子幕名]
   *   **核心功能**：[一句话概括本章作用]
   *   **字数目标**：[3000-5000] 字
   *   **出场角色**：[列出角色]

   ## 2. 张力与冲突
   *   **冲突类型**：[生存/权力/情感/理念等]
   *   **核心冲突点**：[具体冲突内容]
   *   **紧张感曲线**：[铺垫→爬升→爆发→回落/悬念]

   ## 3. 匠心思维应用
   *   **应用场景**：[具体场景]
   *   **思维模式**：[本源透视/去沁/金缮等]
   *   **视觉化描述**：[错误写法 vs 正确写法]
   *   **经典台词**：[代表性台词]

   ## 4. 伏笔与信息差
   *   **本章植入伏笔**：[列出伏笔]
   *   **本章回收伏笔**：[如有]
   *   **信息差控制**：[主角知道 vs 敌人以为]

   ## 5. 暧昧与修罗场
   *   **涉及的女性角色互动**：[描述女性角色互动，如林小雨、苏清雪等]
   *   **🚨 重要**：即使本章不涉及任何女性角色，也**必须保留此节**，并填写"本章不涉及女性角色互动"
   *   **格式要求**：
       - 如果涉及：详细描述互动内容
       - 如果不涉及：必须写"本章不涉及女性角色互动"（不能省略整个节）

   ## 6. 剧情精要
   *   **开场**：[开场场景]
   *   **发展**：[节点1、节点2、节点3...]
   *   **高潮**：[高潮事件]
   *   **收尾**：[结尾状态/悬念]

   ## 7. 衔接设计
   *   **承上**：[承接前文]
   *   **转场**：[转场方式]
   *   **启下**：[为后续埋下伏笔]

   🚨 **格式禁忌**：
   - **严禁重复任何节标题**："## 1. 基础元信息"、"## 2. 张力与冲突"等在每章中只能出现一次
   - **严禁省略任何节**：所有7个节都必须有内容，包括"暧昧与修罗场"
   - **特别强调**："暧昧与修罗场"节即使不涉及女性角色，也必须保留并填写"本章不涉及女性角色互动"
   - **严禁**在"基础元信息"中重复写"第X章 - 标题"
   - **严禁**在正文中引用具体章节号（如"第1章"、"第50章"）
   - 只在章节开头写一次标题，后续用"本章"代替
   - 引用其他章节时，用"后续章节"、"前文"代替

2. **完整性铁律**：
   - 禁止任何省略（如"..."或"略"）。
   - 每章至少800字详细描述。
   - **每个节都必须有内容，不能省略**
   - **严禁只写3个节就结束，必须写满7个节**

3. **架构一致性**：
   - 必须使用【生成指南】中提及的角色名（如张昊、苏清雪），严禁使用其他名字。
   - 必须遵循【生成指南】中的情节锁定。

4. **批次要求**：
   - 本次生成第{start_chapter}章到第{end_chapter}章（共{end_chapter - start_chapter + 1}章）
   - **严格按顺序生成**，不得跳跃或重复
   - **每章必须完整独立**，不得出现"第1章内容中混入第2章开头"的情况
   - **每章的7个节都必须完整，不能偷工减料省略后面的节**

请开始生成第{start_chapter}章到第{end_chapter}章：
"""
        return prompt_header + few_shot_example + strict_requirements

    # 保留旧方法以兼容（如果不使用两阶段）
    def _create_strict_prompt(self, architecture_text: str, chapter_list: str,
                           start_chapter: int, end_chapter: int, user_guidance: str = "") -> str:
         # 此方法已废弃，逻辑转移到 _create_strict_prompt_with_guide
         pass

    def _generate_batch_with_retry(self, start_chapter: int, end_chapter: int,
                                architecture_text: str, existing_content: str = "",
                                filepath: str = "") -> str:
        """
        分批次生成，严格要求成功

        Args:
            filepath: 小说文件路径，用于生成LLM对话日志
        """
        batch_size = end_chapter - start_chapter + 1
        logging.info(f"开始生成批次：第{start_chapter}章到第{end_chapter}章，共{batch_size}章")

        # 🚨 初始化 LLM 对话日志
        if filepath:
            self._init_llm_log(filepath, start_chapter, end_chapter)
            self._log_separator(f"开始生成第{start_chapter}章到第{end_chapter}章")

        last_error_msg = ""
        max_attempts = 5  # 最多重试5次

        for attempt in range(max_attempts):
            try:
                logging.info(f"尝试第{attempt + 1}次生成...")

                # 动态调整指导语，加入上一次的失败反馈
                target_chapters = ", ".join([f"第{i}章" for i in range(start_chapter, end_chapter + 1)])
                current_guidance = f"🎯 你的任务是生成：【{target_chapters}】。\n请生成详细的章节目录，禁止任何形式的省略。"
                
                if last_error_msg:
                    current_guidance += f"\n\n❌ 上一次尝试失败原因：\n{last_error_msg}\n👉 请针对性修正上述问题，确保不再犯同样的错误！"

                # Phase 1: 语境萃取 (Context Extraction)
                # 利用LLM从完整架构中提取"定制化指南"
                extractor = DynamicArchitectureExtractor(architecture_text)
                logging.info("📚 Phase 1: 正在进行架构语境萃取...")
                context_guide = extractor.get_context_guide_via_llm(self.llm_adapter, start_chapter, end_chapter)

                # 将萃取出的guide整合进prompt
                # 注意：这里不再需要手动截断architecture_text，因为guide已经是精华了
                # 但为了保险，我们还是传入Architecture的核心部分（Section 0-1），+ guide
                
                chapter_list_text = (
                    self._extract_chapter_titles_only(existing_content[-5000:]) if existing_content else ""
                )
                phase2_prompt = self._create_strict_prompt_with_guide(
                     architecture_text=architecture_text, # 依然传入，但主要依赖guide
                     context_guide=context_guide,
                     chapter_list=chapter_list_text,
                     start_chapter=start_chapter,
                     end_chapter=end_chapter,
                     user_guidance=current_guidance
                )
                
                # Phase 2: 蓝图生成
                logging.info("✍️ Phase 2: 正在生成蓝图...")
                result = invoke_with_cleaning(self.llm_adapter, phase2_prompt)


                # DEBUG: 记录完整Prompt用于分析
                full_prompt_debug_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'FULL_PROMPT_DEBUG.txt')
                with open(full_prompt_debug_file, 'w', encoding='utf-8') as f:
                    f.write("===== PHASE2 PROMPT DEBUG =====\n")
                    f.write(f"Start: {start_chapter}, End: {end_chapter}\n")
                    f.write("\n===== CONTEXT GUIDE =====\n")
                    f.write(str(context_guide)[:5000] + "...\n")
                    f.write("\n===== CHAPTER LIST =====\n")
                    f.write(str(chapter_list_text)[:2000] + "...\n")
                    f.write("\n===== FULL PHASE2 PROMPT =====\n")
                    f.write(phase2_prompt)
                    f.write("\n===== END PROMPT =====\n")
                logging.info(f'📝 完整Prompt已保存到: {full_prompt_debug_file}')
                

                if not result or not result.strip():
                    logging.error(f"第{attempt + 1}次尝试：生成结果为空")
                    # 🆕 保存空结果诊断
                    empty_debug_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                                                    f"blueprint_EMPTY_{start_chapter}_{end_chapter}_{attempt+1}.txt")
                    with open(empty_debug_file, 'w', encoding='utf-8') as f:
                        f.write(f"LLM 返回空结果\nresult type: {type(result)}\nresult repr: {repr(result)}")
                    logging.info(f"  📝 空结果诊断已保存: {empty_debug_file}")
                    continue

                # 严格验证
                validation = self._strict_validation(result, start_chapter, end_chapter)

                # 🆕 Schema 验证 (使用 Pydantic 模型)
                try:
                    from .schema_validator import BlueprintValidator

                    # 创建验证器实例（如果需要角色白名单，可以传入）
                    validator = BlueprintValidator()

                    # 验证蓝图格式
                    schema_validation = validator.validate_blueprint_format(result, start_chapter, end_chapter)

                    if not schema_validation["is_valid"]:
                        logging.warning(f"⚠️ Schema 验证发现问题: {', '.join(schema_validation['errors'])}")
                        # 合并到现有验证结果中
                        validation["is_valid"] = False
                        validation["errors"].extend(schema_validation["errors"])
                    else:
                        logging.info("✅ Schema 验证通过")
                except Exception as schema_e:
                    logging.warning(f"⚠️ Schema 验证异常: {schema_e}（不影响继续使用传统验证）")

                # 🆕 尝试自动修复缺失的节
                if not validation["is_valid"]:
                    result, was_fixed = self._auto_fix_missing_sections(result, validation)
                    if was_fixed:
                        # 重新验证修复后的内容
                        validation = self._strict_validation(result, start_chapter, end_chapter)
                        logging.info(f"🔧 自动修复后重新验证...")

                if validation["is_valid"]:
                    logging.info(f"✅ 批次生成成功：第{start_chapter}章到第{end_chapter}章")

                    # 🚨 记录 LLM 生成调用和验证结果
                    if filepath:
                        self._log_llm_call(
                            call_type=f"✅ 第{attempt + 1}次生成（成功）",
                            prompt=phase2_prompt,
                            response=result,
                            validation_result=validation,
                            metadata={
                                "尝试次数": attempt + 1,
                                "章节范围": f"{start_chapter}-{end_chapter}",
                                "响应长度": f"{len(result)} 字符",
                                "生成章节数": len(validation.get("generated_chapters", []))
                            }
                        )
                        # 完成日志并返回
                        self._finalize_llm_log(success=True)

                    return result
                else:
                    logging.error(f"第{attempt + 1}次尝试验证失败：")
                    # 关键调试：打印失败的内容，以便分析
                    logging.warning(f"\n======== 失败的生成内容 START ========\n{result[:500]}...\n======== 失败的生成内容 END ========\n")

                    # 🚨 记录失败的LLM调用
                    if filepath:
                        self._log_llm_call(
                            call_type=f"❌ 第{attempt + 1}次生成（验证失败）",
                            prompt=phase2_prompt,
                            response=result,
                            validation_result=validation,
                            metadata={
                                "尝试次数": attempt + 1,
                                "章节范围": f"{start_chapter}-{end_chapter}",
                                "响应长度": f"{len(result)} 字符",
                                "错误数量": len(validation.get("errors", []))
                            }
                        )

                    # 🆕 保存失败内容到文件，便于诊断
                    debug_file = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                              f"blueprint_debug_attempt_{start_chapter}_{end_chapter}_{attempt+1}.txt")
                    try:
                        with open(debug_file, 'w', encoding='utf-8') as f:
                            f.write(f"=== 验证结果 ===\n{validation}\n\n=== 生成内容 ===\n{result}")
                        logging.info(f"  📝 失败内容已保存: {debug_file}")
                    except Exception as save_err:
                        logging.warning(f"  无法保存调试文件: {save_err}")

                    error_list = []
                    for error in validation["errors"]:
                        logging.error(f"  - {error}")
                        error_list.append(error)

                    last_error_msg = "\n".join(error_list)

                    if attempt < max_attempts - 1:
                        logging.info(f"将进行第{attempt + 2}次重试...")
                        time.sleep(5)  # 短暂等待后重试

            except Exception as e:
                error_str = str(e)
                logging.error(f"第{attempt + 1}次尝试异常：{error_str}")
                
                # 🆕 保存异常诊断
                import traceback
                exc_debug_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                                              f"blueprint_EXCEPTION_{start_chapter}_{end_chapter}_{attempt+1}.txt")
                try:
                    with open(exc_debug_file, 'w', encoding='utf-8') as f:
                        f.write(f"异常类型: {type(e).__name__}\n异常信息: {error_str}\n\n完整堆栈:\n{traceback.format_exc()}")
                    logging.info(f"  📝 异常诊断已保存: {exc_debug_file}")
                except:
                    pass
                
                # 特别处理 API 资源耗尽 (Quota Exceeded)
                if "RESOURCE_EXHAUSTED" in error_str or "429" in error_str:
                    wait_time = 60
                    logging.warning(f"⚠️ 检测到 API 配额耗尽 (Resource Exhausted)，将强制冷却 {wait_time} 秒...")
                    time.sleep(wait_time)
                else:
                    # 其他错误短暂等待
                    time.sleep(5)

        # 如果所有尝试都失败，抛出异常而不是返回降级内容
        # 🚨 完成日志（失败状态）
        if filepath:
            self._finalize_llm_log(success=False, error_message=f"经过{max_attempts}次尝试仍未成功")

        raise Exception(f"批次生成失败：第{start_chapter}章到第{end_chapter}章，经过{max_attempts}次尝试仍未成功")

    def _check_architecture_consistency(self, content: str, architecture_text: str) -> dict:
        """
        检查与架构的一致性 - 启用版本
        检查蓝图是否包含架构中要求的关键场景/角色/事件
        """
        issues = []
        
        # 定义关键章节的必需元素（从架构中提取）
        key_elements = {
            "第1章": {
                "keywords": ["乱葬岗", "赵四", "流金", "金瞳", "反杀", "丹田"],
                "description": "致命死局 - 乱葬岗虐杀与穿越激活"
            },
            "第2章": {
                "keywords": ["瓷器", "应力", "碎裂", "洞悉", "本源"],
                "description": "洞悉本源 - 看穿招式如劣质瓷器"
            },
            "第3章": {
                "keywords": ["广场", "长老", "道心", "反噬", "林小雨"],
                "description": "道心崩塌 - 拖尸打脸与长老反噬"
            }
        }
        
        for chapter_key, requirements in key_elements.items():
            # 检查该章节是否在生成内容中
            if chapter_key in content:
                # 提取该章节附近2000字的内容
                start_idx = content.index(chapter_key)
                end_idx = min(start_idx + 2500, len(content))
                chapter_content = content[start_idx:end_idx]
                
                # 检查关键词匹配
                missing = [kw for kw in requirements["keywords"] if kw not in chapter_content]
                match_rate = 1 - (len(missing) / len(requirements["keywords"]))
                
                if missing:
                    issues.append({
                        "chapter": chapter_key,
                        "description": requirements["description"],
                        "missing_keywords": missing,
                        "match_rate": match_rate,
                        "severity": "major" if len(missing) > 2 else "minor"
                    })
                    logging.warning(f"架构一致性检查: {chapter_key} 缺失关键词: {missing}")
        
        # 🆕 动态角色名称验证 (白名单机制)
        extractor = DynamicArchitectureExtractor(architecture_text)
        valid_characters = extractor.get_character_list()
        
        # 常见错误映射（如果不在白名单中，且出现在内容中，则报错）
        # 这里保留一个最小的核心检查，但主要的逻辑是：
        # 检测到的名字如果看起来像人名（2-3字），且不在valid_characters里，且在forbidden_names里，则报错
        
        # 仍然保留核心混淆检查，因为LLM可能生造不在架构里的名字
        forbidden_names = {
            "苏清寒": "苏清雪", 
            "林晓雨": "林小雨",
            "张浩": "张昊",
            "萧辰": "萧尘",
            "云淼淼": "云渺渺",
            "连幽儿": "莲幽儿",
            "苏媚": "素媚"
        }
        
        for wrong_name, correct_name in forbidden_names.items():
            if wrong_name in content:
                issues.append({
                    "type": "角色名称错误",
                    "wrong_name": wrong_name,
                    "correct_name": correct_name,
                    "severity": "critical"
                })
        
        # 🆕 动态宗门验证
        valid_sects = extractor.get_sect_list()
        # 检查是否使用了错误的宗门名
        wrong_sects = ["青云宗", "玄天宗", "剑道宗"]
        for ws in wrong_sects:
             if ws in content and "太上剑宗" not in content[:500]: # 简单启发式
                  issues.append({
                    "type": "宗门名称错误",
                    "wrong_name": ws,
                    "correct_name": "太上剑宗",
                    "severity": "critical"
                })
        
        
        # 计算总体合规分数
        total_checks = len([k for k in key_elements.keys() if k in content])
        critical_violations = len([i for i in issues if i.get("severity") == "critical"])
        major_violations = len([i for i in issues if i.get("severity") == "major"])
        minor_violations = len([i for i in issues if i.get("severity") == "minor"])
        
        compliance_score = 1.0
        if total_checks > 0:
            compliance_score = 1.0 - (critical_violations * 0.5 + major_violations * 0.3 + minor_violations * 0.1)
        
        # 有critical错误则不通过
        is_consistent = critical_violations == 0 and major_violations == 0
        
        if issues:
            logging.info(f"架构一致性检查: 发现 {len(issues)} 个问题 (合规分: {compliance_score:.2f})")
        else:
            logging.info("架构一致性检查: 通过 ✓")
        
        return {
            "is_consistent": is_consistent,
            "compliance_score": max(0, compliance_score),
            "issues": issues,
            "total_violations": len(issues),
            "critical_violations": critical_violations,
            "major_violations": major_violations,
            "minor_violations": minor_violations
        }

    def _extract_chapter_number_from_content(self, content: str) -> int:
        """从内容中提取章节编号"""
        import re

        # 尝试多种章节编号格式
        patterns = [
            r"第\s*(\d+)\s*章",
            r"chapter\s*(\d+)",
            r"(\d+)\s*、",
            r"【\s*第?\s*(\d+)\s*章\s*】"
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except (ValueError, IndexError):
                    continue

        return 1  # 默认返回第1章

    def _batch_quality_optimize(self, filepath: str, full_content: str, 
                                 start_chapter: int, end_chapter: int) -> str:
        """
        批次质量优化：检查并修复当前批次的低分章节
        
        Args:
            filepath: 项目路径
            full_content: 当前完整的蓝图内容
            start_chapter: 批次起始章节
            end_chapter: 批次结束章节
            
        Returns:
            优化后的完整蓝图内容
        """
        from quality_checker import QualityChecker
        from novel_generator.blueprint_repairer import BlueprintRepairer
        
        checker = QualityChecker(filepath)
        low_score_chapters = []
        
        # 1. 检查当前批次的每个章节
        for chapter_num in range(start_chapter, end_chapter + 1):
            chapter_content = self._extract_single_chapter(full_content, chapter_num)
            if not chapter_content:
                logging.warning(f"未能提取第{chapter_num}章内容，跳过质量检查")
                continue
            
            report = checker.check_chapter_quality(
                chapter_content, 
                {"chapter_number": chapter_num}
            )
            
            if report.overall_score < 80:
                low_score_chapters.append({
                    'chapter_number': chapter_num,
                    'content': chapter_content,
                    'score': report.overall_score,
                    'issues': [issue.description for issue in report.issues]
                })
                logging.info(f"  第{chapter_num}章: {report.overall_score:.1f}分 (需优化)")
            else:
                logging.info(f"  第{chapter_num}章: {report.overall_score:.1f}分 ✓")
        
        # 2. 如果有低分章节，自动修复
        if low_score_chapters:
            logging.info(f"🔧 发现 {len(low_score_chapters)} 个低分章节，开始自动修复...")
            
            repairer = BlueprintRepairer(
                interface_format=self.interface_format,
                api_key=self.api_key,
                base_url=self.base_url,
                llm_model=self.llm_model,
                filepath=filepath,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout
            )
            
            for chapter_info in low_score_chapters:
                chapter_num = chapter_info['chapter_number']
                original_content = chapter_info['content']
                issues = chapter_info['issues']
                
                logging.info(f"  修复第{chapter_num}章 (原分: {chapter_info['score']:.1f})...")
                
                repaired = repairer.repair_single_chapter(
                    chapter_num, original_content, issues, max_retries=2
                )
                
                if repaired:
                    # 验证修复后的质量
                    new_report = checker.check_chapter_quality(
                        repaired, {"chapter_number": chapter_num}
                    )
                    improvement = new_report.overall_score - chapter_info['score']
                    logging.info(f"  第{chapter_num}章修复完成: {chapter_info['score']:.1f} → {new_report.overall_score:.1f} ({improvement:+.1f})")
                    
                    # 替换原内容
                    full_content = self._replace_chapter_content(
                        full_content, chapter_num, repaired
                    )
                else:
                    logging.warning(f"  第{chapter_num}章修复失败，保留原内容")
        else:
            logging.info("✅ 当前批次所有章节质量达标")
        
        return full_content

    def _extract_single_chapter(self, content: str, chapter_num: int) -> str:
        """从完整内容中提取单个章节"""
        pattern = rf'((?:###?\s*\*?\*?)?\s*第\s*{chapter_num}\s*章[^\n]*\n[\s\S]*?)(?=(?:###?\s*\*?\*?)?\s*第\s*\d+\s*章|\Z)'
        match = re.search(pattern, content, re.MULTILINE)
        return match.group(1).strip() if match else ""

    def _replace_chapter_content(self, full_content: str, chapter_num: int, new_content: str) -> str:
        """替换指定章节的内容"""
        pattern = rf'((?:###?\s*\*?\*?)?\s*第\s*{chapter_num}\s*章[^\n]*\n[\s\S]*?)(?=(?:###?\s*\*?\*?)?\s*第\s*\d+\s*章|\Z)'
        # 确保新内容末尾有换行
        new_content = new_content.strip() + "\n\n"
        return re.sub(pattern, new_content, full_content, count=1, flags=re.MULTILINE)

    def _format_cleanup(self, filepath: str) -> bool:
        """
        🆕 格式整理：清理重复内容、修复格式混乱、去除空白章节
        """
        logging.info("=" * 60)
        logging.info("🧹 开始格式整理...")
        
        filename_dir = os.path.join(filepath, "Novel_directory.txt")
        content = read_file(filename_dir)
        if not content:
            logging.warning("格式整理：文件为空")
            return False
        
        original_length = len(content)
        
        # 1. 提取所有章节并去重
        # 🆕 改进的正则：只匹配行首的章节标题，避免匹配内容中的引用
        # 使用多行模式，^匹配行首
        chapter_pattern = r'(?:^|\n)(第\s*(\d+)\s*章[^\n]*?\n(?:[\s\S]*?))(?=\n第\s*\d+\s*章[^\n]*?\n|\Z)'
        matches = list(re.finditer(chapter_pattern, content, re.MULTILINE))
        
        chapters_dict = {}  # chapter_num -> content (保留最后一个版本)
        for match in matches:
            chapter_num = int(match.group(2))
            chapter_content = match.group(1).strip()
            # 只保留内容较长的版本（可能是完整版）
            if chapter_num not in chapters_dict or len(chapter_content) > len(chapters_dict[chapter_num]):
                chapters_dict[chapter_num] = chapter_content
        
        # 2. 按章节号排序重组
        sorted_chapters = sorted(chapters_dict.keys())
        cleaned_content = "\n\n".join([chapters_dict[num] for num in sorted_chapters])
        
        # 3. 清理多余空行
        cleaned_content = re.sub(r'\n{4,}', '\n\n\n', cleaned_content)
        
        # 保存清理后的内容
        clear_file_content(filename_dir)
        save_string_to_txt(cleaned_content.strip(), filename_dir)
        
        new_length = len(cleaned_content)
        removed = original_length - new_length
        
        logging.info(f"  - 去重后章节数: {len(sorted_chapters)}")
        logging.info(f"  - 原始大小: {original_length:,} 字符")
        logging.info(f"  - 清理后大小: {new_length:,} 字符")
        logging.info(f"  - 清理冗余: {removed:,} 字符 ({removed/original_length*100:.1f}%)")
        logging.info("✅ 格式整理完成")
        
        return True

    def _full_quality_repair_loop(self, filepath: str, max_rounds: int = 3, 
                                   target_score: float = 80.0) -> dict:
        """
        🆕 全自动质量修复循环：检查所有章节，自动修复低分章节，直到达标或达到最大轮次
        
        Args:
            filepath: 项目路径
            max_rounds: 最大修复轮次
            target_score: 目标平均分
            
        Returns:
            修复报告
        """
        from quality_checker import QualityChecker
        from novel_generator.blueprint_repairer import BlueprintRepairer
        
        logging.info("=" * 60)
        logging.info("🔄 开始全自动质量修复循环...")
        logging.info(f"  - 最大轮次: {max_rounds}")
        logging.info(f"  - 目标平均分: {target_score}")
        
        filename_dir = os.path.join(filepath, "Novel_directory.txt")
        checker = QualityChecker(filepath)
        
        repair_stats = {
            "rounds_completed": 0,
            "total_repaired": 0,
            "initial_avg_score": 0,
            "final_avg_score": 0,
            "chapters_improved": []
        }
        
        for round_num in range(1, max_rounds + 1):
            logging.info("-" * 50)
            logging.info(f"📊 第 {round_num}/{max_rounds} 轮质量检查...")
            
            # 重新读取内容
            content = read_file(filename_dir)
            if not content:
                break
            
            # 提取所有章节
            chapter_pattern = r'(第\s*(\d+)\s*章\s*[-–—][^\n]*\n[\s\S]*?)(?=第\s*\d+\s*章\s*[-–—]|\Z)'
            matches = list(re.finditer(chapter_pattern, content))
            
            all_scores = []
            low_score_chapters = []
            
            for match in matches:
                chapter_num = int(match.group(2))
                chapter_content = match.group(1).strip()
                
                try:
                    report = checker.check_chapter_quality(
                        chapter_content, {"chapter_number": chapter_num}
                    )
                    all_scores.append(report.overall_score)
                    
                    if report.overall_score < target_score:
                        low_score_chapters.append({
                            'chapter_number': chapter_num,
                            'content': chapter_content,
                            'score': report.overall_score,
                            'issues': [i.description for i in report.issues]
                        })
                except Exception as e:
                    logging.warning(f"  检查第{chapter_num}章失败: {e}")
            
            avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
            
            if round_num == 1:
                repair_stats["initial_avg_score"] = avg_score
            
            logging.info(f"  - 检查章节数: {len(matches)}")
            logging.info(f"  - 当前平均分: {avg_score:.1f}")
            logging.info(f"  - 低分章节数: {len(low_score_chapters)}")
            
            # 如果没有低分章节，退出循环
            if not low_score_chapters:
                logging.info(f"✅ 所有章节质量达标，退出修复循环")
                repair_stats["rounds_completed"] = round_num
                repair_stats["final_avg_score"] = avg_score
                break
            
            # 🆕 修复所有低分章节（不再限制50章）
            chapters_to_repair = low_score_chapters  # 修复所有低分章节
            logging.info(f"🔧 本轮修复 {len(chapters_to_repair)} 章...")
            
            repairer = BlueprintRepairer(
                interface_format=self.interface_format,
                api_key=self.api_key,
                base_url=self.base_url,
                llm_model=self.llm_model,
                filepath=filepath,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout
            )
            
            repaired_count = 0
            for chapter_info in chapters_to_repair:
                chapter_num = chapter_info['chapter_number']
                
                try:
                    repaired = repairer.repair_single_chapter(
                        chapter_num, 
                        chapter_info['content'], 
                        chapter_info['issues'],
                        max_retries=2
                    )
                    
                    if repaired:
                        # 验证修复后分数
                        new_report = checker.check_chapter_quality(
                            repaired, {"chapter_number": chapter_num}
                        )
                        
                        if new_report.overall_score > chapter_info['score']:
                            # 替换内容
                            content = self._replace_chapter_content(content, chapter_num, repaired)
                            repaired_count += 1
                            repair_stats["chapters_improved"].append({
                                "chapter": chapter_num,
                                "before": chapter_info['score'],
                                "after": new_report.overall_score
                            })
                            logging.info(f"    第{chapter_num}章: {chapter_info['score']:.1f} → {new_report.overall_score:.1f} ✓")
                        else:
                            logging.info(f"    第{chapter_num}章: 修复无改善，保留原内容")
                except Exception as e:
                    logging.warning(f"    第{chapter_num}章修复失败: {e}")
            
            # 保存本轮修复结果
            clear_file_content(filename_dir)
            save_string_to_txt(content.strip(), filename_dir)
            
            repair_stats["total_repaired"] += repaired_count
            repair_stats["rounds_completed"] = round_num
            logging.info(f"  本轮修复完成: {repaired_count} 章")
            
            # 短暂等待避免 API 限流
            time.sleep(5)
        
        # 最终统计
        final_content = read_file(filename_dir)
        final_matches = list(re.finditer(chapter_pattern, final_content))
        final_scores = []
        for match in final_matches:
            chapter_num = int(match.group(2))
            chapter_content = match.group(1).strip()
            try:
                report = checker.check_chapter_quality(chapter_content, {"chapter_number": chapter_num})
                final_scores.append(report.overall_score)
            except:
                pass
        
        repair_stats["final_avg_score"] = sum(final_scores) / len(final_scores) if final_scores else 0
        
        logging.info("=" * 60)
        logging.info("🎯 全自动修复循环完成！")
        logging.info(f"  - 完成轮次: {repair_stats['rounds_completed']}/{max_rounds}")
        logging.info(f"  - 总修复章节: {repair_stats['total_repaired']}")
        logging.info(f"  - 初始平均分: {repair_stats['initial_avg_score']:.1f}")
        logging.info(f"  - 最终平均分: {repair_stats['final_avg_score']:.1f}")
        logging.info(f"  - 分数提升: {repair_stats['final_avg_score'] - repair_stats['initial_avg_score']:+.1f}")
        
        return repair_stats

    def generate_complete_directory_strict(self, filepath: str, number_of_chapters: int,
                                        user_guidance: str = "", batch_size: int = 1,
                                        auto_optimize: bool = True) -> bool:
        """
        严格的完整目录生成流程
        """
        import math
        from datetime import datetime
        
        total_batches = math.ceil(number_of_chapters / batch_size)
        logging.info("=" * 60)
        logging.info(f"📚 蓝图生成任务启动")
        logging.info(f"   总章节数: {number_of_chapters} | 每批: {batch_size}章 | 预计批次: {total_batches}")
        logging.info(f"   自动优化: {'开启' if auto_optimize else '关闭'}")
        logging.info("=" * 60)

        # 检查架构文件
        arch_file = os.path.join(filepath, "Novel_architecture.txt")
        if not os.path.exists(arch_file):
            logging.error("❌ Novel_architecture.txt not found")
            return False

        architecture_text = read_file(arch_file).strip()
        if not architecture_text:
            logging.error("❌ Novel_architecture.txt is empty")
            return False

        # 检查现有目录
        filename_dir = os.path.join(filepath, "Novel_directory.txt")
        existing_content = ""

        if os.path.exists(filename_dir):
            existing_content = read_file(filename_dir).strip()
            if existing_content:
                logging.info("📂 检测到现有目录，将追加生成")

        # 确定起始章节
        if existing_content:
            chapter_pattern = r"第\s*(\d+)\s*章"
            existing_chapters = re.findall(chapter_pattern, existing_content)
            existing_numbers = [int(x) for x in existing_chapters if x.isdigit()]
            start_chapter = max(existing_numbers) + 1 if existing_numbers else 1
            logging.info(f"📍 断点续传: 从第{start_chapter}章继续")
        else:
            start_chapter = 1

        if start_chapter > number_of_chapters:
            logging.info("✅ 所有章节已生成完成")
            return True

        final_blueprint = existing_content
        current_start = start_chapter
        batch_count = 0
        start_time = datetime.now()

        # 分批生成
        while current_start <= number_of_chapters:
            current_end = min(current_start + batch_size - 1, number_of_chapters)
            batch_count += 1
            
            # 计算进度
            progress = current_end / number_of_chapters * 100
            remaining_batches = math.ceil((number_of_chapters - current_end) / batch_size)
            
            logging.info("-" * 50)
            logging.info(f"📝 批次 {batch_count}/{total_batches} | 第{current_start}-{current_end}章")
            logging.info(f"   进度: {progress:.1f}% | 剩余批次: {remaining_batches}")

            try:
                # 严格生成当前批次
                batch_result = self._generate_batch_with_retry(
                    current_start, current_end, architecture_text, final_blueprint, filepath
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

                # 🆕 立即执行去重，防止累积重复
                try:
                    self._format_cleanup(filepath)
                    # 重新读取去重后的内容
                    final_blueprint = read_file(filename_dir).strip()
                    logging.info(f"🧹 第{batch_count}批已去重")
                except Exception as cleanup_e:
                    logging.warning(f"⚠️ 批次去重异常（不影响继续生成）: {cleanup_e}")

                # === 分卷优化：每批次生成后自动质量检查和修复 ===
                if auto_optimize:
                    try:
                        logging.info(f"🔍 正在检查第{current_start}章到第{current_end}章的质量...")
                        final_blueprint = self._batch_quality_optimize(
                            filepath, final_blueprint, current_start, current_end
                        )
                        # 重新保存优化后的内容
                        clear_file_content(filename_dir)
                        save_string_to_txt(final_blueprint.strip(), filename_dir)
                    except Exception as opt_e:
                        logging.warning(f"⚠️ 批次优化异常（不影响继续生成）: {opt_e}")

                current_start = current_end + 1

            except Exception as e:
                logging.error(f"❌ 批次 {batch_count} 生成失败：{e}")
                # 严格模式下，任何批次失败都导致整体失败 (抛出异常以传递详细信息)
                raise Exception(f"第{batch_count}批次生成失败: {str(e)}")

        # 最终验证
        end_time = datetime.now()
        elapsed = end_time - start_time
        elapsed_minutes = elapsed.total_seconds() / 60
        
        logging.info("=" * 60)
        logging.info("🔎 进行最终验证...")
        final_content = read_file(filename_dir).strip()
        if final_content:
            final_validation = self._strict_validation(final_content, 1, number_of_chapters)

            if final_validation["is_valid"]:
                logging.info("=" * 60)
                logging.info("🎉 蓝图生成任务完成！")
                logging.info(f"   生成章节: 第1章 - 第{number_of_chapters}章")
                logging.info(f"   总批次数: {batch_count}")
                logging.info(f"   总耗时: {elapsed_minutes:.1f} 分钟")
                logging.info("=" * 60)
                
                # 🆕 Step 1: 格式整理（去重、排序、清理空行）
                try:
                    self._format_cleanup(filepath)
                except Exception as cleanup_e:
                    logging.warning(f"⚠️ 格式整理异常: {cleanup_e}")
                
                # 🆕 Step 2: 全自动质量修复循环
                if auto_optimize:
                    try:
                        repair_stats = self._full_quality_repair_loop(
                            filepath, 
                            max_rounds=3, 
                            target_score=80.0
                        )
                        logging.info(f"📊 修复统计: 初始{repair_stats['initial_avg_score']:.1f}分 → 最终{repair_stats['final_avg_score']:.1f}分")
                    except Exception as repair_e:
                        logging.warning(f"⚠️ 自动修复循环异常: {repair_e}")
                
                # 🆕 Step 3: 自动执行架构合规性检查
                try:
                    from novel_generator.architecture_compliance import ArchitectureComplianceChecker
                    logging.info("🔍 正在生成架构合规性报告...")
                    
                    # Detect corpus name
                    novel_corpus_name = "wxhyj" # default fallback
                    try:
                        for item in os.listdir(filepath):
                            if os.path.isdir(os.path.join(filepath, item)):
                                if os.path.exists(os.path.join(filepath, item, "Novel_architecture.txt")):
                                    novel_corpus_name = item
                                    break
                    except Exception as detect_e:
                        logging.warning(f"⚠️ 语料库名称检测失败，使用默认值: {detect_e}")

                    checker = ArchitectureComplianceChecker(filepath, novel_corpus_name=novel_corpus_name)
                    report_path = checker.generate_report_file()
                    logging.info(f"✅ 架构合规性报告已生成: {report_path}")
                except Exception as e:
                    logging.error(f"❌ 自动架构合规性检查失败: {e}")
                
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
    batch_size: int = 1,
    auto_optimize: bool = True
) -> None:
    """
    严格版本的章节蓝图生成函数
    
    Args:
        auto_optimize: 是否在每批次生成后自动进行质量检查和修复（默认True）
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
            batch_size=batch_size,
            auto_optimize=auto_optimize
        )

        if success:
            logging.info("🎉 严格章节目录生成成功完成")
        else:
            logging.error("❌ 严格章节目录生成失败 (未知原因，请检查日志)")
            raise Exception("章节目录生成失败：验证未通过或未知错误")

    except Exception as e:
        error_msg = f"严格章节目录生成异常：{str(e)}"
        logging.error(error_msg)
        # 重新抛出包含详细信息的异常
        raise Exception(error_msg) from e

if __name__ == "__main__":
    pass
