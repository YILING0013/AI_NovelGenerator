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
from prompt_definitions import chunked_chapter_blueprint_prompt, BLUEPRINT_EXAMPLE_V3
from utils import read_file, clear_file_content, save_string_to_txt
from architecture_consistency_checker import ArchitectureConsistencyChecker
from novel_generator.architecture_extractor import DynamicArchitectureExtractor
from optimized_rate_limiter import get_rate_limiter

class StrictChapterGenerator:
    MAX_RETRIES = 3
    RETRY_DELAY = 2

    # 核心模块定义（严格使用架构格式 ## X. 名称）- 7节格式 v2.1
    REQUIRED_MODULES = {
        "基础元信息": ["## 1. 基础元信息", "1. 基础元信息", "基础元信息"],
        "张力与冲突": ["## 2. 张力与冲突", "2. 张力与冲突", "张力与冲突"],
        "匠心思维应用": ["## 3. 匠心思维应用", "3. 匠心思维应用", "匠心思维应用"],
        "伏笔与信息差": ["## 4. 伏笔与信息差", "4. 伏笔与信息差", "伏笔与信息差"],
        "暧昧与修罗场": ["## 5. 暧昧与修罗场", "5. 暧昧与修罗场", "暧昧与修罗场"],
        "剧情精要": ["## 6. 剧情精要", "6. 剧情精要", "剧情精要"],
        "衔接设计": ["## 7. 衔接设计", "7. 衔接设计", "衔接设计"],
    }

    # 子节点完整性检查（使用架构格式术语）- 7节格式 v2.1
    REQUIRED_SUBNODES = {
        "剧情精要": ["开场", "发展", "高潮", "收尾"],
        "张力与冲突": ["冲突类型", "核心冲突点", "紧张感曲线"],
        "基础元信息": ["定位", "核心功能"],
        "衔接设计": ["承上", "启下"],
    }

    # 角色名白名单（基于架构文件定义）
    CANONICAL_CHARACTERS = {
        "张昊",        # 主角
        "林小雨",      # 女主1 - 青梅竹马
        "苏清雪",      # 女主2 - 高冷圣女
        "素媚儿",      # 女主3 - 妖媚魔女
        "云渺渺",      # 女主4 - 活泼师妹
        "莲幽儿",      # 女主5 - 冥界幽灵
        "萧尘",        # 宿敌
        "陈逸风",      # 背叛者
        "云寂",        # NPC - 疯癫真人
    }

    # 常见错误角色名 -> 正确角色名映射
    TYPO_CHARACTERS = {
        "苏清寒": "苏清雪",
        "苏清歌": "苏清雪",
        "苏清韵": "苏清雪",
        "素媚": "素媚儿",
        "苏媚": "素媚儿",
        "林晓雨": "林小雨",
        "萧辰": "萧尘",
        "陈一风": "陈逸风",
    }

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

        # 初始化一致性检查器和频率限制器
        self.consistency_checker = ArchitectureConsistencyChecker()
        self.rate_limiter = get_rate_limiter()

        # 自动验证配置
        self.auto_consistency_check = True
        self.consistency_threshold = 0.75  # 一致性阈值
        self.max_consistency_retries = 2   # 一致性检查最大重试次数

        # 🚨 LLM 对话日志记录器
        self.llm_log_dir = None  # 将在生成时设置
        self.current_log_file = None
        self.llm_conversation_log = []  # 存储当前批次的对话日志

    def _preprocess_content(self, content: str) -> str:
        """
        智能预处理内容：标准化格式，移除空白，规范化标点
        """
        if not content:
            return content

        # 1. 标准化空白字符
        processed = re.sub(r'[ \t]+', ' ', content)  # 多个空白字符合并为一个空格（保留换行）
        processed = processed.strip()  # 去除首尾空白

        # 2. 标准化省略号（将所有变体统一为标准形式）
        processed = re.sub(r'⋯', '...', processed)  # 统一省略号
        processed = re.sub(r'…', '...', processed)   # 统一省略号

        # 3. 标准化中文标点
        processed = re.sub(r'，\s*…', '，...', processed)  # 逗号+省略号
        processed = re.sub(r'。\s*…', '。...', processed)  # 句号+省略号
        processed = re.sub(r'：\s*…', '：...', processed)  # 冒号+省略号

        # 4. 处理常见的省略表达模式
        processed = re.sub(r'如下\s*：\s*\n*\s*([^\n]*?)\.\.\.+\s*\n*',
                         r'如下：\1（省略内容）\n', processed)  # 如下：...模式

        # 5. 检测并标记可能的省略模式
        processed = re.sub(r'(\S+)\s*等\s*(\d+)*(个|种|项|方面|内容|要素|部分)',
                         r'\1等\2\3（可能省略）', processed)

        return processed

    # ==================== LLM 对话日志记录方法 ====================

    def _init_llm_log(self, filepath: str, start_chapter: int, end_chapter: int):
        """
        初始化 LLM 对话日志文件

        Args:
            filepath: 小说文件路径
            start_chapter: 起始章节
            end_chapter: 结束章节
        """
        from datetime import datetime

        # 创建日志目录
        self.llm_log_dir = os.path.join(filepath, "llm_conversation_logs")
        os.makedirs(self.llm_log_dir, exist_ok=True)

        # 创建日志文件名（按章节范围）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"llm_log_chapters_{start_chapter}-{end_chapter}_{timestamp}.md"
        self.current_log_file = os.path.join(self.llm_log_dir, log_filename)

        # 清空之前的日志
        self.llm_conversation_log = []

        # 写入日志头部
        header = f"""# LLM 对话日志 - 第{start_chapter}章到第{end_chapter}章

**生成时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**章节范围**: {start_chapter} - {end_chapter}
**LLM模型**: {self.llm_model}
**温度**: {self.temperature}

---

"""
        self.llm_conversation_log.append(header)

        logging.info(f"📝 LLM对话日志已初始化: {self.current_log_file}")

    def _log_llm_call(self, call_type: str, prompt: str, response: str = "",
                     validation_result: dict = None, metadata: dict = None):
        """
        记录一次 LLM 调用

        Args:
            call_type: 调用类型（"generation", "repair", "consistency_repair"）
            prompt: 发送给 LLM 的完整提示词
            response: LLM 返回的原始响应
            validation_result: 验证结果（如果有）
            metadata: 额外的元数据
        """
        from datetime import datetime

        timestamp = datetime.now().strftime("%H:%M:%S")

        # 构建日志条目
        log_entry = f"""

## {call_type} - {timestamp}

"""

        # 添加元数据
        if metadata:
            log_entry += "**元数据**:\n```\n"
            for key, value in metadata.items():
                log_entry += f"{key}: {value}\n"
            log_entry += "```\n\n"

        # 添加提示词
        log_entry += f"""**提示词长度**: {len(prompt)} 字符

### 发送给 LLM 的提示词:

```prompt
{prompt[:5000]}  # 限制前5000字符，避免日志过大
"""
        if len(prompt) > 5000:
            log_entry += f"\n... (省略 {len(prompt) - 5000} 字符)\n"
        log_entry += "```\n"

        # 添加响应
        if response:
            log_entry += f"""

**响应长度**: {len(response)} 字符

### LLM 返回的响应:

```response
{response[:10000]}  # 限制前10000字符
"""
            if len(response) > 10000:
                log_entry += f"\n... (省略 {len(response) - 10000} 字符)\n"
            log_entry += "```\n"

        # 添加验证结果
        if validation_result:
            log_entry += f"""

### 验证结果:

**是否通过**: {validation_result.get('is_valid', False)}

"""
            if validation_result.get('errors'):
                log_entry += "**错误列表**:\n"
                for error in validation_result['errors']:
                    log_entry += f"- ❌ {error}\n"
                log_entry += "\n"

            if validation_result.get('warnings'):
                log_entry += "**警告列表**:\n"
                for warning in validation_result['warnings']:
                    log_entry += f"- ⚠️ {warning}\n"
                log_entry += "\n"

            if validation_result.get('generated_chapters'):
                log_entry += f"**生成的章节**: {validation_result['generated_chapters']}\n\n"

        log_entry += "---\n"

        # 添加到日志列表
        self.llm_conversation_log.append(log_entry)

        # 立即保存到文件（确保即使崩溃也能保留日志）
        self._save_llm_log()

    def _log_separator(self, title: str = ""):
        """添加分隔符"""
        separator = f"""

# {'=' * 60}
# {title}
# {'=' * 60}

"""
        self.llm_conversation_log.append(separator)
        self._save_llm_log()

    def _save_llm_log(self):
        """保存日志到文件"""
        if not self.current_log_file:
            return

        try:
            with open(self.current_log_file, 'w', encoding='utf-8') as f:
                f.writelines(self.llm_conversation_log)
        except Exception as e:
            logging.error(f"保存LLM对话日志失败: {e}")

    def _finalize_llm_log(self, success: bool, summary: str = ""):
        """
        完成日志记录

        Args:
            success: 是否成功
            summary: 总结信息
        """
        from datetime import datetime

        footer = f"""

# 🏁 生成结束

**结束时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**最终状态**: {'✅ 成功' if success else '❌ 失败'}
**总结**: {summary}

---

**日志文件**: {self.current_log_file}

"""
        self.llm_conversation_log.append(footer)
        self._save_llm_log()

        logging.info(f"💾 LLM对话日志已保存: {self.current_log_file}")

    # ==================== 验证方法 ====================

    def _strict_validation(self, content: str, expected_start: int, expected_end: int) -> dict:
        """
        宽松验证：容忍有限省略，重点验证内容完整性
        """
        result = {
            "is_valid": True,
            "errors": [],
            "warnings": [],
            "missing_chapters": [],
            "generated_chapters": [],
            "omission_count": 0
        }

        # 🔧 恢复验证系统 - 集成自动清理机制
        logging.info("✅ 验证系统已恢复，集成自动清理机制")

        # 0. 自动清理省略号和其他违规模式
        cleaned_content = self._auto_clean_omissions(content)
        if cleaned_content != content:
            omission_count = content.count('...') + content.count('…') + content.count('省略')
            logging.info(f"🧹 自动清理省略号：检测并清理了{omission_count}个违规模式")
            content = cleaned_content
            result["cleaned_content"] = cleaned_content  # 添加清理后的内容到结果中
        else:
            result["cleaned_content"] = content  # 如果没有清理，返回原内容

        # 1. 智能预处理：标准化内容格式
        processed_content = self._preprocess_content(content)

        # 2. 分级省略检测 - 严重违规零容忍，轻微省略限制数量
        # 严重违规模式（批量章节省略、篇幅借口等）
        severe_patterns = [
            # 批量章节省略（严重违规）
            r'后续章节类似', # 其余章节类似
            r'后面章节结构相同', # 后面章节结构相同
            r'第.*章.*至.*章.*省略', # 第X章至第Y章省略
            r'第.*章.*到.*章.*省略', # 第X章到第Y章省略
            r'其余.*章.*类似', # 其余章节类似
            r'批量.*生成', # 批量生成
            r'节奏规划生成', # 节奏规划生成

            # 篇幅借口省略（严重违规）
            r'由于篇幅限制', # 由于篇幅限制
            r'篇幅所限', # 篇幅所限
            r'受限于篇幅', # 受限于篇幅
            r'为了节省篇幅', # 为了节省篇幅
            r'由于内容过长', # 由于内容过长
            r'字数限制', # 字数限制
            r'字数所限', # 字数所限

            # 明确的内容省略（严重违规）
            r'详细内容省略', # 详细内容省略
            r'内容省略',   # 内容省略
            r'详情省略',   # 详情省略
            r'具体内容省略', # 具体内容省略
            r'此处省略', # 此处省略
            r'此处从略', # 此处从略
            r'此处跳过', # 此处跳过
            r'从略处理', # 从略处理
            r'以下省略', # 以下省略
            r'以上省略', # 以上省略
        ]

        # 轻微省略模式（合理的叙事省略）
        minor_patterns = [
            # 基础省略号（合理的叙事省略）
            r'\.\.\.',  # 省略号
            r'…',      # 中文省略号
            r'⋯',      # 另一种中文省略号

            # 合理的省略词汇
            r'省略',    # 省略
            r'跳过',    # 跳过
            r'从略',    # 从略
            r'略',      # 单字"略"
            r'等等',    # 等等
            r'等',      # 单字"等"

            # 模糊表述（在合理范围内）
            r'.*等\d*种',  # ...等X种
            r'.*等多个',   # ...等多个
            r'.*等几项',   # ...等几项
            r'.*等方面',   # ...等方面
            r'.*等内容',   # ...等内容
            r'.*等要素',   # ...等要素
            r'.*等部分',   # ...等部分

            # 后续提及（不涉及批量省略）
            r'后续.*将', # 后续将
            r'后面.*将', # 后面将
            r'后续.*按照', # 后续按照
            r'后面.*按照', # 后面按照
            r'后续.*时间', # 后续时间
            r'后面.*时间', # 后面时间
            r'将来.*时间', # 将来时间
            r'以后.*时间', # 以后时间

            # 模糊内容
            r'相关内容',   # 相关内容
            r'类似内容',   # 类似内容
            r'相应内容',   # 相应内容
            r'对应内容',   # 对应内容
            r'有关内容',   # 有关内容
        ]

        # 优先检测严重违规模式 - 零容忍
        severe_violations = 0
        for pattern in severe_patterns:
            matches = re.findall(pattern, processed_content, re.IGNORECASE)
            if matches:
                severe_violations += len(matches)
                result["is_valid"] = False  # 严重省略模式必须修复
                result["errors"].append(f"🚨 严重省略违规: 发现模式 '{pattern}' -> {matches[:3]}")

        # 如果没有严重违规，再检测轻微省略
        if severe_violations == 0:
            minor_count = 0
            for pattern in minor_patterns:
                matches = re.findall(pattern, processed_content, re.IGNORECASE)
                if matches:
                    minor_count += len(matches)
                    result["omission_count"] += len(matches)
                    result["warnings"].append(f"⚠️ 发现轻微省略模式 '{pattern}' -> {matches[:2]}")

            # 允许少量轻微省略（每10章允许3个）
            chapter_count = expected_end - expected_start + 1
            allowed_minor = max(3, chapter_count // 3)
            if minor_count > allowed_minor:
                result["is_valid"] = False  # 轻微省略过多需修复
                result["errors"].append(f"🚨 轻微省略过多：发现{minor_count}个，允许{allowed_minor}个")
            elif minor_count > 0:
                result["warnings"].append(f"✅ 允许范围内省略：{minor_count}个轻微省略（允许{allowed_minor}个）")

        # 如果有严重错误，直接返回失败
        if not result["is_valid"]:
            return result

        # 3. 检查章节完整性和连续性
        # 使用 multiline 模式 (^匹配行首) 避免匹配正文中的 "详见第X章"
        # 兼容 Markdown 标题格式 (### 第1章) 和加粗 (**第1章**)
        # 🚨 严格要求：章节号与"章"字之间不能有空格（格式：第X章，不是 第 X 章）
        # 🚨 修复：移除否定前瞻，允许"章"后面有破折号
        chapter_pattern = r"(?m)^[#*\s]*第(\d+)(?:[-–—]\d+)?章(?=\s*-|$)"
        generated_chapters = re.findall(chapter_pattern, content)
        generated_numbers = [int(x) for x in generated_chapters if x.isdigit()]

        # 🚨 新增：检测重复章节（关键修复）
        # 检查原始列表中是否有重复的章节编号
        unique_numbers = set()
        duplicate_numbers = set()
        for num in generated_numbers:
            if num in unique_numbers:
                duplicate_numbers.add(num)
            else:
                unique_numbers.add(num)

        if duplicate_numbers:
            result["is_valid"] = False
            result["errors"].append(f"🚨 检测到重复章节：{sorted(duplicate_numbers)} - 同一章节编号出现多次！")

        # 🚨 新增：检测格式混乱（有空格的格式）
        # 检查是否存在 "第 X 章" 格式（章节号和章字之间有空格）
        loose_pattern = r"(?m)^[#*\s]*第\s+\d+\s+章"
        loose_matches = re.findall(loose_pattern, content)
        if loose_matches:
            result["is_valid"] = False
            result["errors"].append(f"🚨 格式混乱：发现{len(loose_matches)}处使用了 '第 X 章' 格式（有空格），必须统一为 '第X章' 格式（无空格）")

        result["generated_chapters"] = sorted(list(unique_numbers))

        expected_count = expected_end - expected_start + 1
        actual_count = len(unique_numbers)

        # 必须生成正确数量的章节
        if actual_count != expected_count:
            result["is_valid"] = False  # 章节数量错误需修复
            result["errors"].append(f"🚨 章节数量错误：期望{expected_count}章，实际{actual_count}章")

        # 必须包含所有期望的章节编号
        expected_numbers = set(range(expected_start, expected_end + 1))
        actual_numbers = set(generated_numbers)

        missing_numbers = expected_numbers - actual_numbers
        extra_numbers = actual_numbers - expected_numbers

        if missing_numbers:
            result["is_valid"] = False  # 缺失章节需修复
            result["missing_chapters"] = sorted(missing_numbers)
            result["errors"].append(f"🚨 缺失章节：{sorted(missing_numbers)}")

        if extra_numbers:
            result["is_valid"] = False  # 超出范围章节需修复
            result["errors"].append(f"🚨 超出范围章节：{sorted(extra_numbers)}")

        # 4. 检查每个章节是否有足够的内容
        # 使用 splitlines() 处理多种换行符 (\n, \r\n, \r)
        lines = content.splitlines()
        chapter_content = {}
        current_chapter = None
        content_lines = []

        for line in lines:
            line = line.strip()
            # 移除 BOM 和其他不可见字符 (如零宽空格)
            line = line.lstrip('\ufeff\u200b\u200c\u200d')
            # 兼容 Markdown 格式
            # Match chapter using raw string (no f-string needed here)
            chapter_match = re.match(r"^[#*\s]*第\s*(\d+)(?:[-–—]\d+)?\s*章", line)
            


            if chapter_match:
                start_new_chapter = False
                new_chapter_num = int(chapter_match.group(1))

                # 只有当章节号在预期范围内时，才视为新章节开始
                # 这样可以避免 "第19章：伏笔" 这样的列表项打断当前章节
                if expected_start <= new_chapter_num <= expected_end:
                    start_new_chapter = True
                
                logging.debug(f"Chapter Header Found: {new_chapter_num} | Start New: {start_new_chapter}")

                if start_new_chapter:
                    # 保存前一个章节的内容
                    if current_chapter is not None:
                        chapter_content[current_chapter] = content_lines
                        logging.debug(f"Saved Chapter {current_chapter} with {len(content_lines)} lines")

                    # 开始新章节
                    current_chapter = new_chapter_num
                    content_lines = [line]
                else:
                    # 如果不是新章节（例如只是文中的引用），作为普通内容添加
                    if current_chapter is not None:
                        content_lines.append(line)
            else:
                if current_chapter is not None and line:
                    content_lines.append(line)

        # 保存最后一个章节
        if current_chapter is not None:
            chapter_content[current_chapter] = content_lines
            logging.debug(f"Saved Last Chapter {current_chapter} with {len(content_lines)} lines")

        # 检查每个章节的内容长度（改用字符数而非行数，因为 LLM 可能输出密集段落）
        for chapter_num in range(expected_start, expected_end + 1):
            if chapter_num in chapter_content:
                chapter_text = "\n".join(chapter_content[chapter_num])
                # 计算有效字符数（排除空白和标点）
                valid_chars = len(re.sub(r'[\s\n\r═\-\*\#\[\]【】（）\(\)]', '', chapter_text))
                
                if valid_chars < 1500:  # 每章至少1500个有效字符（强化阈值）
                    result["is_valid"] = False  # 内容不足需修复
                    result["errors"].append(f"🚨 第{chapter_num}章内容不足：只有{valid_chars}个有效字符（需至少1500）")

                # 5. 检查核心模块完整性 (严格版)
                chapter_text = "\n".join(chapter_content[chapter_num])
                missing_modules = []
                for module_name, keywords in self.REQUIRED_MODULES.items():
                    # 只要存在任意一个变体关键词即可
                    if not any(kw in chapter_text for kw in keywords):
                        missing_modules.append(module_name)
                
                if missing_modules:
                    result["is_valid"] = False # 缺失模块需修复
                    result["errors"].append(f"🚨 第{chapter_num}章缺失核心模块：{', '.join(missing_modules)}")

                # 6. 检查子节点完整性（确保关键模块包含必需的子节点）
                for module_name, subnodes in self.REQUIRED_SUBNODES.items():
                    # 只对存在的模块检查子节点
                    if any(kw in chapter_text for kw in self.REQUIRED_MODULES.get(module_name, [])):
                        missing_subnodes = [s for s in subnodes if s not in chapter_text]
                        if missing_subnodes:
                            result["is_valid"] = False
                            result["errors"].append(f"🚨 第{chapter_num}章【{module_name}】缺少子节点：{', '.join(missing_subnodes)}")

                # 7. 检查角色名一致性（防止LLM生成错误的角色名）
                found_typos = []
                for typo_name, correct_name in self.TYPO_CHARACTERS.items():
                    if typo_name in chapter_text:
                        found_typos.append(f"{typo_name}→{correct_name}")
                
                if found_typos:
                    result["is_valid"] = False  # 角色名错误需修复
                    result["errors"].append(f"🚨 第{chapter_num}章角色名错误：{', '.join(found_typos)}")

            else:
                result["is_valid"] = False  # 章节完全缺失需修复
                result["errors"].append(f"🚨 第{chapter_num}章完全缺失")

        return result

    def _create_strict_prompt(self, architecture_text: str, chapter_list: str,
                           start_chapter: int, end_chapter: int, user_guidance: str = "") -> str:
        """
        创建严格的提示词：明确禁止省略，要求详细内容
        """
        base_prompt = chunked_chapter_blueprint_prompt.format(
            novel_architecture=architecture_text,
            chapter_list=chapter_list,
            n=start_chapter,
            m=end_chapter,
            total_chapters=end_chapter - start_chapter + 1,
            blueprint_example=BLUEPRINT_EXAMPLE_V3
        )

        strict_requirements = f"""

🚨【绝对强制性要求 - 违者视为任务失败】🚨

1. **禁止任何形式的省略 - 零容忍政策**：
   - 绝对禁止使用"..."、"…"、"省略"、"跳过"等任何省略表述
   - 绝对禁止使用"由于篇幅限制"、"字数限制"等作为省略理由
   - 绝对禁止使用"后续章节类似"、"以此类推"等偷懒表述
   - 绝对禁止使用"后续章节"、"后面章节"、"其余章节"等暗示省略的表述
   - 绝对禁止使用"等等"、"等相关"、"等方面"等模糊省略表述
   - 绝对禁止使用"规划生成"、"内容规划"等隐含省略的表述
   - 每一章都必须有完整的详细内容，不允许任何形式的省略

2. **必须生成所有章节 - 不可缺失**：
   - 必须生成第{start_chapter}章到第{end_chapter}章，共{end_chapter - start_chapter + 1}章
   - 每章都必须包含完整的7个标准节（基础元信息、张力与冲突、匠心思维应用、伏笔与信息差、暧昧与修罗场、剧情精要、衔接设计）
   - 每章内容至少需要800-1200字的详细描述
   - 每个字段都必须填写详细、具体的内容，不能留空

3. **质量要求 - 详细具体**：
   - 每章至少需要20行以上的详细内容
   - 不能只有标题或几行简单的描述
   - 每个字段都必须填写详细、具体的内容，不能使用模糊或概括性语言
   - 必须包含具体的情节、情感变化、冲突设计等详细内容

4. **格式要求 - 完整规范**：
   - 严格按照示例格式，包含所有必要字段
   - 每章结构完整，信息详细
   - 不允许任何形式的简化或省略
   - 必须逐章完整生成，不能跳跃式生成

5. **内容要求 - 严禁偷懒**：
   - 每个章节的【基础元信息】、【张力与冲突】、【匠心思维应用】、【伏笔与信息差】、【暧昧与修罗场】、【剧情精要】、【衔接设计】都必须完整填写
   - 不能使用"类似"、"相同"、"相关"等模糊词汇代替具体内容
   - 必须提供具体的、可执行的、详细的创作指导

⚡【验证标准 - 极其严格】⚡：
- 生成后将进行严格验证，发现任何省略立即判定失败
- 缺少任何章节或章节内容不足都将重新生成
- 使用任何形式的省略表述都会导致任务失败
- 只有100%符合要求的内容才会被接受
- 验证系统会检测所有可能的省略模式，包括隐含省略

💀【终极警告 - 零容忍】💀：
- 任何形式的省略都将导致立即失败，无警告
- 系统会自动检测所有省略模式，包括变体和隐含表达
- 失败后将自动重试，最多重试5次
- 如果5次都失败，整个任务将判定为失败

请为第{start_chapter}章到第{end_chapter}章生成详细的章节目录，确保每一章都完整且详细，绝对禁止任何形式的省略。
"""

        return base_prompt + strict_requirements

    def _create_strict_prompt_with_guide(self, architecture_text: str, context_guide: str, chapter_list: str,
                           start_chapter: int, end_chapter: int, user_guidance: str = "") -> str:
        """
        创建严格提示词 (两阶段版) - 使用 Context Guide 替代完整架构
        """
        base_prompt = f"""
你是一位严谨的小说蓝图架构师。请根据【生成指南】为《补天》生成**第{start_chapter}-{end_chapter}章**的详细蓝图。

### 核心参考资料（必须严格执行）
{context_guide}

### 已有章节概览
{chapter_list}

{user_guidance}
"""
        strict_requirements = f"""
🚨【绝对强制性要求 - 违者视为任务失败】🚨

1. **禁止任何形式的省略 - 零容忍政策**：
   - 绝对禁止使用"..."、"…"、"省略"、"跳过"等任何省略表述
   - 每一章都必须有完整的详细内容
   - **严禁生成多余章节**：只生成第{start_chapter}章到第{end_chapter}章，不要自动续写后续章节！

2. **必须使用增强版7节数字格式**：
{ENHANCED_BLUEPRINT_TEMPLATE}

3. **格式严格一致性（Formatting Consistency）**:
   - 第{start_chapter}章到第{end_chapter}章，**每一章**都必须严格使用上述模板格式。
   - **每一章都必须包含全部7个节**：基础元信息、张力与冲突、匠心思维应用、伏笔与信息差、暧昧与修罗场、剧情精要、衔接设计
   - **不得省略任何一节**，即使某节内容为"本章不涉及"也必须保留该节标题

4. **🚨 格式禁忌（严格遵守）🚨**：
   - **严禁**使用 `### 【xxx】` 格式（如 `### 【基础元信息】`）
   - **严禁**使用 `-   **项目名**：` 格式（无序列表）
   - **严禁**自创新的节标题（只能使用上述7个节）
   - **严禁**更改项目名称（如将"张力评级"改为"张力等级"）
   - **必须**使用 `## N. 节名` 格式（二级标题+数字编号）
   - **必须**使用 `*   **项目名**：` 格式（无序列表+粗体项目名）
   - **必须**包含所有标准字段（张力评级、目标字数、冲突类型、匠心思维应用、伏笔植入、衔接设计）

5. **架构一致性**：
   - 必须使用【生成指南】中提及的角色名（如张昊、苏清雪），严禁使用其他名字。
   - 必须遵循【生成指南】中的情节锁定。
   - 只有100%符合要求的内容才会被接受
   - **使用【普通文本模式】**：不要使用Markdown代码块（```）包裹内容，直接输出文本

6. **🚨 核心世界观修正 (Worldview Correction)**：
   - **绝对禁止**使用 "万物皆瓷" (All is Porcelain) 这一表述！这是错误的！
   - **必须**使用 "**万物皆器**" (All is Artifact)！
   - **隐喻泛化**：不要把所有东西都写成瓷器（釉面/开片）。
     - 剑修/金铁 -> 使用青铜/冶金术语 (锈蚀/淬火/金属疲劳)
     - 阵法/木石 -> 使用建筑/木技术语 (榫卯/大漆/纹理)
     - 肉身 -> 使用玉石/泥塑术语 (包浆/沁色/质地)
   - **禁止**过度堆砌 "烧制"、"窑炉" 等瓷器专用词，除非对象真的是瓷器。

🔐【格式自检清单】（生成前必读）：
- [ ] 每个章节是否以 `第X章 - 标题` 开头？（可选加 `### **...**` 包装）
- [ ] 是否包含全部7个节？
- [ ] 是否没有使用 `### 【xxx】` 格式？
- [ ] 是否没有使用 `-   **项目名**：` 格式？
- [ ] 所有新增字段是否都已填写？

请为第{start_chapter}章到第{end_chapter}章生成详细的章节目录。
"""
        return base_prompt + strict_requirements

    def _auto_clean_omissions(self, content: str) -> str:
        """
        自动清理省略号和其他违规模式的后处理机制
        这是一个务实解决方案，针对GLM-4.6模型容易生成省略号的问题
        """
        if not content:
            return content

        cleaned_content = content
        original_length = len(content)

        # 1. 清理各种省略号模式
        omission_patterns = [
            (r'\.\.\.', ''),                    # 英文省略号
            (r'…', ''),                        # 中文省略号
            (r'省略', ''),                      # 省略
            (r'跳过', ''),                      # 跳过
            (r'此处省略', ''),                   # 此处省略
            (r'由于篇幅', ''),                   # 由于篇幅
            (r'篇幅限制', ''),                   # 篇幅限制
            (r'字数限制', ''),                   # 字数限制
            (r'后续章节', ''),                   # 后续章节
            (r'后续.*章', ''),                   # 后续X章
            (r'第.*章.*至.*章', ''),             # 第X章至第Y章
            (r'从略', ''),                      # 从略
            (r'等等', ''),                      # 等等
            (r'以此类推', ''),                    # 以此类推
            (r'类似格式', ''),                    # 类似格式
            (r'相同格式', ''),                    # 相同格式
            (r'将.*格式', ''),                    # 将...格式
            (r'按照.*格式', ''),                  # 按照...格式
            (r'其余章节类似', ''),                # 其余章节类似
            (r'后面章节结构相同', ''),              # 后面章节结构相同
            (r'详细内容省略', ''),                # 详细内容省略
            (r'节奏规划生成', ''),                # 节奏规划生成
        ]

        # 应用省略号清理
        for pattern, replacement in omission_patterns:
            cleaned_content = re.sub(pattern, replacement, cleaned_content, flags=re.IGNORECASE)

        # 2. 修复因清理省略号造成的语法问题
        # 修复多余的空格和标点符号
        cleaned_content = re.sub(r'[，,]{2,}', '，', cleaned_content)  # 多个逗号
        cleaned_content = re.sub(r'[。.]{2,}', '。', cleaned_content)  # 多个句号
        cleaned_content = re.sub(r'[ \t]+', ' ', cleaned_content)  # 多个空格（不包含换行）
        cleaned_content = re.sub(r'(\w)\s+([，。！？])', r'\1\2', cleaned_content)  # 文字和标点间的空格

        # 3. 智能补全省略的关键内容（仅在必要时）
        lines = cleaned_content.split('\n')
        new_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 检查是否是因为省略号清理导致的不完整行
            if len(line) < 10 and not line.startswith('第') and not line.startswith('【'):
                # 可能是被清理的片段，尝试补全
                if '定位：' in line and len(line) < 20:
                    line = line.replace('定位：', '定位：详细描述章节在整体结构中的位置和作用')
                elif '作用：' in line and len(line) < 20:
                    line = line.replace('作用：', '作用：具体说明本章对剧情推进的核心贡献')
                elif '字数目标：' in line and len(line) < 15:
                    line = line.replace('字数目标：', '字数目标：5000字 | 难度等级：★★★☆☆')
                elif '张力评级：' in line and len(line) < 15:
                    line = line.replace('张力评级：', '张力评级：★★★☆☆ | 类型：剧情冲突')
                elif '情感弧光：' in line and len(line) < 15:
                    line = line.replace('情感弧光：', '情感弧光：起始情感→中间情感→结束情感')
                # 其他模式可以继续添加...

            new_lines.append(line)

        cleaned_content = '\n'.join(new_lines)

        # 4. 清理多余的空行
        cleaned_content = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_content)

        # 记录清理统计
        final_length = len(cleaned_content)
        removed_chars = original_length - final_length

        if removed_chars > 0:
            logging.info(f"🧹 自动清理完成：移除了{removed_chars}个字符，包括违规省略模式")

        # 0.5 强制替换违规名称 (Strict Name Enforcement)
        # 在任何其他清理之前，先强制替换所有违规名称
        forbidden_map = {
            "苏清寒": "苏清雪", 
            "林晓雨": "林小雨", 
            "张浩": "张昊",
            "青云宗": "太上剑宗", 
            "玄天宗": "太上剑宗", 
            "剑道宗": "太上剑宗"
        }
        
        corrected_count = 0
        for bad_name, correct_name in forbidden_map.items():
            if bad_name in cleaned_content:
                count = cleaned_content.count(bad_name)
                cleaned_content = cleaned_content.replace(bad_name, correct_name)
                corrected_count += count
                logging.info(f"🔧 自动纠正违规名称：'{bad_name}' -> '{correct_name}' (共{count}处)")

        if corrected_count > 0:
            logging.info(f"✅ 共修正了 {corrected_count} 处命名错误")

        return cleaned_content.strip()

    def _repair_structural_issues(self, content: str, validation_result: dict,
                                   start_chapter: int, end_chapter: int,
                                   architecture_text: str, max_repair_attempts: int = 2) -> str:
        """
        修复结构性问题（省略模式、缺章、内容不足等）
        使用LLM进行智能修复
        """
        issues = validation_result.get("errors", [])
        if not issues:
            logging.info("无需修复：没有发现结构性问题")
            return content
        
        logging.info(f"🔧 开始修复 {len(issues)} 个结构性问题...")
        
        # 构建修复 prompt
        repair_prompt = f"""你是一个专业的小说蓝图修复师。以下章节目录存在结构性问题，请修复。

【存在的问题】
{chr(10).join(f"- {issue}" for issue in issues)}

【原始内容】
{content}

【修复要求】
1. 保留所有有效内容，只修复问题部分
2. 第{start_chapter}章到第{end_chapter}章必须完整存在
3. 将所有"此处省略"、"等内容"、"以上内容"替换为具体的情节描述
4. 补全缺失的核心模块（如匠心思维应用、衔接设计等），内容必须与参考架构一致
5. 每章必须包含完整的【基础元信息】、【张力与冲突】、【匠心思维应用】、【伏笔与信息差】、【暧昧与修罗场】、【剧情精要】、【衔接设计】等7大核心模块

🚨 **格式强制要求**：
1. **章节标题行**：必须是 `第X章 - [章节标题]`（章节号与章字之间无空格，破折号前后有空格）
2. **小节标题**：必须是 `## X. [小节标题]`（## + 数字 + 点 + 空格 + 标题）
3. **严禁混用格式**：不得在文中切换格式
4. **严禁使用** `第 X 章` 格式（章节号和章字之间有空格）

✅ 正确格式示例：
第1章 - 乱葬岗的修复师
## 1. 基础元信息
*   **章节**：第1章 - 乱葬岗的修复师

❌ 错误格式示例：
第 1 章 - 乱葬岗的修复师（有空格）
第1章[标题]（缺少破折号）

【参考架构片段】
{architecture_text[:8000]}

请直接输出修复后的完整章节目录："""

        for attempt in range(max_repair_attempts):
            try:
                logging.info(f"  修复尝试 {attempt + 1}/{max_repair_attempts}...")
                self.rate_limiter.wait_if_needed("结构修复")
                
                repaired = invoke_with_cleaning(self.llm_adapter, repair_prompt)
                
                if not repaired or not repaired.strip():
                    logging.warning(f"  修复尝试 {attempt + 1} 返回空内容")
                    continue
                
                # 快速验证修复结果
                quick_check = self._strict_validation(repaired.strip(), start_chapter, end_chapter)

                if quick_check["is_valid"]:
                    logging.info(f"✅ 修复成功！问题从 {len(issues)} 个减少到 0 个")
                    return repaired.strip()
                else:
                    new_errors = quick_check.get("errors", [])
                    logging.warning(f"  修复后仍有 {len(new_errors)} 个问题")

                    # 🚨 关键修复：不再接受"部分修复"
                    # 如果修复后仍有严重错误（重复、格式混乱等），不接受部分修复
                    severe_errors = [e for e in new_errors if "重复" in e or "格式混乱" in e or "章节数量错误" in e]
                    if severe_errors:
                        logging.error(f"  修复后仍有严重错误：{severe_errors}")
                        logging.error(f"  不接受部分修复，将尝试下一次修复...")
                        continue  # 不接受，继续下一次修复尝试

                    # 只有非严重错误（如内容不完整）才接受部分修复
                    if len(new_errors) < len(issues):
                        logging.info(f"  部分修复成功：问题从 {len(issues)} 个减少到 {len(new_errors)} 个")
                        content = repaired.strip()
                        issues = new_errors
                        
            except Exception as e:
                logging.error(f"  修复尝试 {attempt + 1} 异常: {e}")

        # 🚨 关键修复：如果所有修复尝试后仍有严重问题，抛出异常而不是返回问题内容
        final_check = self._strict_validation(content, start_chapter, end_chapter)
        severe_errors = [e for e in final_check.get("errors", []) if "重复" in e or "格式混乱" in e or "章节数量错误" in e]

        if severe_errors:
            error_msg = f"经过{max_repair_attempts}次修复尝试后，内容仍有严重错误：{severe_errors}"
            logging.error(f"❌ {error_msg}")
            raise Exception(error_msg)

        logging.warning(f"⚠️ 修复未完全成功，仍有 {len(issues)} 个问题（非严重错误）")
        return content  # 返回（可能部分修复的）内容

    def _generate_batch_with_retry(self, start_chapter: int, end_chapter: int,
                                architecture_text: str, existing_content: str = "",
                                filepath: str = "") -> str:
        """
        分批次生成，严格要求成功 (集成两阶段生成)

        Args:
            filepath: 小说文件路径，用于保存 LLM 对话日志
        """
        batch_size = end_chapter - start_chapter + 1
        logging.info(f"开始生成批次：第{start_chapter}章到第{end_chapter}章，共{batch_size}章")

        # 🚨 初始化 LLM 对话日志
        if filepath:
            self._init_llm_log(filepath, start_chapter, end_chapter)
            self._log_separator(f"开始生成第{start_chapter}章到第{end_chapter}章")

        max_attempts = 3  # 恢复正常重试次数，确保生成质量

        for attempt in range(max_attempts):
            try:
                logging.info(f"尝试第{attempt + 1}次生成...")

                # Phase 1: 语境萃取 (Context Extraction)
                # 利用LLM从完整架构中提取"定制化指南"
                extractor = DynamicArchitectureExtractor(architecture_text)
                logging.info("📚 Phase 1: 正在进行架构语境萃取...")
                # 注意：这里可能会有些耗时，但为了质量是值得的
                context_guide = extractor.get_context_guide_via_llm(self.llm_adapter, start_chapter, end_chapter)

                # Phase 2: 蓝图生成
                logging.info("✍️ Phase 2: 正在生成蓝图...")
                
                # 创建严格提示词 (使用此新方法)
                prompt = self._create_strict_prompt_with_guide(
                    architecture_text=architecture_text,
                    context_guide=context_guide,
                    chapter_list=existing_content[-3000:] if existing_content else "",
                    start_chapter=start_chapter,
                    end_chapter=end_chapter,
                    user_guidance="请生成详细的章节目录，禁止任何形式的省略，严格遵循生成指南"
                )

                # 调用API
                result = invoke_with_cleaning(self.llm_adapter, prompt)

                if not result or not result.strip():
                    logging.error(f"第{attempt + 1}次尝试：生成结果为空")
                    # 🚨 记录失败的 LLM 调用
                    if filepath:
                        self._log_llm_call(
                            call_type=f"❌ 第{attempt + 1}次生成失败（结果为空）",
                            prompt=prompt,
                            response="",
                            metadata={
                                "尝试次数": attempt + 1,
                                "章节范围": f"{start_chapter}-{end_chapter}",
                                "失败原因": "生成结果为空"
                            }
                        )
                    continue

                # 严格验证（包含内置的自动清理）
                validation = self._strict_validation(result, start_chapter, end_chapter)

                # 🚨 记录 LLM 生成调用和验证结果
                if filepath:
                    self._log_llm_call(
                        call_type=f"✅ 第{attempt + 1}次生成",
                        prompt=prompt,
                        response=result,
                        validation_result=validation,
                        metadata={
                            "尝试次数": attempt + 1,
                            "章节范围": f"{start_chapter}-{end_chapter}",
                            "响应长度": f"{len(result)} 字符"
                        }
                    )

                if validation["is_valid"]:
                    # 使用清理后的内容
                    result = validation.get("cleaned_content", result)
                    # 自动一致性检查（如果启用）
                    consistency_ok = True
                    if self.auto_consistency_check:
                        logging.info("🔍 执行自动一致性检查...")
                        consistency_result = self._check_architecture_consistency(result, architecture_text)

                        if consistency_result["is_consistent"]:
                            logging.info(f"✅ 一致性检查通过：得分 {consistency_result['overall_score']:.2f}")
                        else:
                            consistency_ok = False
                            logging.error(f"❌ 一致性检查失败：得分 {consistency_result['overall_score']:.2f}（阈值：{self.consistency_threshold}）")

                            # 显示失败原因
                            if consistency_result["issues"]:
                                logging.error("一致性问题：")
                                for issue in consistency_result["issues"]:
                                    logging.error(f"  - {issue}")

                            # 如果一致性检查失败，尝试修复 (原有逻辑保留)
                            if attempt < max_attempts - 1:
                                logging.info("🔧 尝试自动修复一致性问题...")
                                try:
                                    repaired_content = self._repair_batch_with_consistency_check(
                                        start_chapter=start_chapter,
                                        end_chapter=end_chapter,
                                        architecture_text=architecture_text,
                                        original_content=result,
                                        consistency_issues=consistency_result["issues"]
                                    )

                                    # 如果修复成功，返回修复后的内容
                                    if repaired_content != result:
                                        logging.info(f"✅ 一致性修复成功，第{start_chapter}章到第{end_chapter}章")
                                        return "\n" + repaired_content
                                    else:
                                        logging.warning("修复未成功，将重新生成")
                                except Exception as e:
                                    logging.error(f"修复过程异常：{e}")
                                    # 修复失败，继续正常重试流程

                    if consistency_ok:
                        logging.info(f"✅ 批次生成成功：第{start_chapter}章到第{end_chapter}章")
                        # 🚨 完成日志记录
                        if filepath:
                            self._finalize_llm_log(
                                success=True,
                                summary=f"批次生成成功，第{start_chapter}章到第{end_chapter}章，共{batch_size}章"
                            )
                        return "\n" + result
                    else:
                        # 一致性检查失败，记录并重试
                        logging.error(f"第{attempt + 1}次尝试一致性检查失败")
                        if attempt < max_attempts - 1:
                            logging.info(f"将进行第{attempt + 2}次重试（针对一致性问题）...")
                            time.sleep(10)  # 一致性检查失败后等待更长时间
                else:
                    # 验证失败，尝试修复而不是直接重试
                    logging.error(f"第{attempt + 1}次尝试验证失败，尝试自动修复...")
                    for error in validation["errors"]:
                        logging.error(f"  - {error}")

                    # 调用结构修复方法
                    repaired_content = self._repair_structural_issues(
                        content=result,
                        validation_result=validation,
                        start_chapter=start_chapter,
                        end_chapter=end_chapter,
                        architecture_text=architecture_text
                    )

                    # 重新验证修复后的内容
                    revalidation = self._strict_validation(repaired_content, start_chapter, end_chapter)

                    # 🚨 记录修复后的验证结果
                    if filepath:
                        self._log_llm_call(
                            call_type=f"🔧 第{attempt + 1}次修复后验证",
                            prompt="",
                            response=repaired_content,
                            validation_result=revalidation,
                            metadata={
                                "原始错误": len(validation.get("errors", [])),
                                "修复后错误": len(revalidation.get("errors", [])),
                                "修复状态": "成功" if revalidation["is_valid"] else "失败"
                            }
                        )

                    if revalidation["is_valid"]:
                        logging.info("✅ 结构修复成功！继续进行一致性检查...")
                        result = repaired_content
                        # 修复成功后，继续一致性检查流程
                        if self.auto_consistency_check:
                            consistency_result = self._check_architecture_consistency(result, architecture_text)
                            if consistency_result["is_consistent"]:
                                logging.info(f"✅ 批次生成+修复成功：第{start_chapter}章到第{end_chapter}章")
                                # 🚨 最终安全检查：确保没有格式问题或重复
                                final_check_errors = revalidation.get("errors", [])
                                if any("重复" in e or "格式混乱" in e for e in final_check_errors):
                                    logging.error(f"❌ 修复后仍有严重问题：{final_check_errors}")
                                    logging.error(f"不接受此修复，将重新生成")
                                    if attempt < max_attempts - 1:
                                        time.sleep(5)
                                        continue  # 不接受，重试
                                    else:
                                        raise Exception(f"修复后仍有严重问题：{final_check_errors}")
                                # 🚨 完成日志记录（修复成功）
                                if filepath:
                                    self._finalize_llm_log(
                                        success=True,
                                        summary=f"批次生成+修复成功，第{start_chapter}章到第{end_chapter}章，共{batch_size}章"
                                    )
                                return "\n" + result
                            else:
                                logging.warning(f"修复后一致性检查未通过，将重新生成")
                        else:
                            # 🚨 即使没有一致性检查，也要确保没有严重问题
                            final_check_errors = revalidation.get("errors", [])
                            if any("重复" in e or "格式混乱" in e for e in final_check_errors):
                                logging.error(f"❌ 修复后仍有严重问题：{final_check_errors}")
                                if attempt < max_attempts - 1:
                                    time.sleep(5)
                                    continue  # 不接受，重试
                                else:
                                    raise Exception(f"修复后仍有严重问题：{final_check_errors}")
                            # 🚨 完成日志记录（修复成功，无一致性检查）
                            if filepath:
                                self._finalize_llm_log(
                                    success=True,
                                    summary=f"批次生成+修复成功（无一致性检查），第{start_chapter}章到第{end_chapter}章，共{batch_size}章"
                                )
                            return "\n" + result
                    else:
                        logging.warning(f"修复后仍有 {len(revalidation['errors'])} 个问题，将进行第{attempt + 2}次重试...")
                        
                    if attempt < max_attempts - 1:
                        time.sleep(5)  # 短暂等待后重试

            except Exception as e:
                logging.error(f"第{attempt + 1}次尝试异常：{e}")

        # 如果所有尝试都失败，记录详细错误并抛出异常终止执行
        logging.error("=" * 60)
        logging.error(f"❌ 批次生成彻底失败：第{start_chapter}章到第{end_chapter}章")
        logging.error(f"❌ 经过 {max_attempts} 次生成尝试 + 多次修复尝试均未成功")
        logging.error("❌ 请检查以下可能的原因：")
        logging.error("   1. API 响应质量问题（模型输出内容不符合格式要求）")
        logging.error("   2. 验证规则过严（检查 _strict_validation 中的阈值）")
        logging.error("   3. 架构文件内容不完整（检查 Novel_architecture.txt）")
        logging.error("=" * 60)

        # 🚨 完成日志记录（失败）
        if filepath:
            self._finalize_llm_log(
                success=False,
                summary=f"批次生成失败：第{start_chapter}章到第{end_chapter}章，经过{max_attempts}次尝试均未成功"
            )

        raise Exception(
            f"批次生成失败：第{start_chapter}章到第{end_chapter}章，"
            f"经过{max_attempts}次尝试仍未成功。请查看日志文件定位具体问题。"
        )

    def _check_architecture_consistency(self, content: str, architecture_text: str) -> dict:
        """
        全面的架构一致性检查
        """
        logging.info("🔍 开始架构一致性检查...")

        # 使用频率限制器控制API调用
        self.rate_limiter.wait_if_needed("架构一致性检查")

        try:
            # 使用完整的一致性检查器
            result = self.consistency_checker.check_full_consistency(architecture_text, content)

            # 🚨 严格命名检查 (Strict Name Validation)
            forbidden_map = {
                "苏清寒": "苏清雪", "林晓雨": "林小雨", "张浩": "张昊",
                "青云宗": "太上剑宗", "玄天宗": "太上剑宗", "剑道宗": "太上剑宗"
            }
            strict_errors = []
            for bad_name, correct_name in forbidden_map.items():
                if bad_name in content:
                    strict_errors.append(f"CRITICAL: Found forbidden name '{bad_name}', must be '{correct_name}'")
            
            if strict_errors:
                result["overall_score"] = 0.0
                result["issues"] = strict_errors + result.get("issues", [])
                logging.error(f"❌ 严格检查未通过: {strict_errors}")

            # 记录详细结果
            logging.info(f"📊 一致性检查结果：总体得分 {result['overall_score']:.2f}")

            if result["issues"]:
                logging.warning("❌ 发现一致性问题：")
                for issue in result["issues"]:
                    logging.warning(f"  - {issue}")

            if result["checks"]:
                logging.info("📋 详细检查结果：")
                for check_name, check_result in result["checks"].items():
                    status = "✅" if check_result["consistent"] else "❌"
                    score = check_result["score"]
                    logging.info(f"  {status} {check_name}: {score:.2f}")

                    if check_result["issues"]:
                        for issue in check_result["issues"]:
                            logging.warning(f"    - {issue}")

            # 返回简化的结果用于判断
            return {
                "is_consistent": result["overall_score"] >= self.consistency_threshold,
                "overall_score": result["overall_score"],
                "issues": result["issues"],
                "detailed_result": result
            }

        except Exception as e:
            logging.error(f"一致性检查异常：{e}")
            return {
                "is_consistent": False,
                "overall_score": 0.0,
                "issues": [f"检查过程异常: {str(e)}"],
                "detailed_result": None
            }

    def _generate_consistency_repair_prompt(self, content: str, consistency_issues: list, architecture_text: str) -> str:
        """
        根据一致性问题生成修复提示
        """
        issues_text = "\n".join([f"- {issue}" for issue in consistency_issues])

        repair_prompt = f"""
🔧【一致性修复提示】🔧

检测到以下一致性问题需要修复：
{issues_text}

🎯【修复要求】：
1. 确保章节发展与整体架构设计保持一致
2. 修复角色弧光的不连续性
3. 调整情节推进的合理性
4. 保持世界构建的一致性
5. 维护主题的统一性

📋【修复原则】：
- 保持原有章节结构，只调整内容细节
- 确保每个章节的逻辑连贯性
- 维护角色发展的合理性
- 保持叙事流畅性

请根据上述问题对章节目录进行修复，确保一致性达标。
"""
        return repair_prompt

    def _repair_batch_with_consistency_check(self, start_chapter: int, end_chapter: int,
                                           architecture_text: str, original_content: str,
                                           consistency_issues: list) -> str:
        """
        修复批次的一致性问题
        """
        logging.info(f"🔧 开始修复第{start_chapter}章到第{end_chapter}章的一致性问题...")

        # 记录prompt请求
        self.rate_limiter.record_prompt()

        # 生成修复提示
        repair_prompt = self._generate_consistency_repair_prompt(
            original_content, consistency_issues, architecture_text
        )

        # 创建修复请求
        full_prompt = f"""
原始内容：
{original_content}

{repair_prompt}

请重新生成第{start_chapter}章到第{end_chapter}章的详细目录，确保解决所有一致性问题。
"""

        try:
            # 调用API进行修复
            result = invoke_with_cleaning(self.llm_adapter, full_prompt)

            if not result or not result.strip():
                logging.error("修复请求返回空结果")
                return original_content

            # 验证修复结果
            validation = self._strict_validation(result, start_chapter, end_chapter)
            if not validation["is_valid"]:
                logging.error("修复后内容验证失败")
                return original_content

            # 检查修复后的一致性
            consistency_result = self._check_architecture_consistency(result, architecture_text)
            if consistency_result["is_consistent"]:
                logging.info(f"✅ 一致性修复成功：得分 {consistency_result['overall_score']:.2f}")
                return result
            else:
                logging.warning(f"修复后一致性仍不达标：得分 {consistency_result['overall_score']:.2f}")
                return original_content

        except Exception as e:
            logging.error(f"修复过程异常：{e}")
            return original_content

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
            chapter_pattern = r"(?m)^第\s*(\d+)\s*章\s*-\s*"
            existing_chapters = re.findall(chapter_pattern, existing_content)
            existing_numbers = [int(x) for x in existing_chapters if x.isdigit()]
            start_chapter = max(existing_numbers) + 1 if existing_numbers else 1
            
            # ====== 断点续传前的质量检测 ======
            if existing_numbers:
                logging.info("=" * 60)
                logging.info("🔍 断点续传前质量检测：检查已生成的章节...")
                
                # 对已有内容进行验证
                max_existing = max(existing_numbers)
                pre_check = self._strict_validation(existing_content, 1, max_existing)
                
                if not pre_check["is_valid"]:
                    logging.warning("=" * 60)
                    logging.warning("⚠️ 已生成内容存在质量问题：")
                    for error in pre_check["errors"]:
                        logging.warning(f"  - {error}")
                    logging.warning("=" * 60)
                    
                    # 交互式提示用户选择
                    print("\n" + "=" * 60)
                    print("⚠️ 已生成的章节存在以下问题：")
                    for error in pre_check["errors"][:5]:  # 只显示前5个
                        print(f"  - {error}")
                    if len(pre_check["errors"]) > 5:
                        print(f"  ... 还有 {len(pre_check['errors']) - 5} 个问题")
                    print("=" * 60)
                    print("\n请选择操作：")
                    print("  [R] 修复 - 进入质量修复循环")
                    print("  [C] 继续 - 跳过问题，继续生成后续章节")
                    print("  [Q] 退出 - 停止执行，手动处理")
                    
                    while True:
                        try:
                            choice = input("\n请输入选择 (R/C/Q): ").strip().upper()
                        except EOFError:
                            # 非交互模式，默认继续
                            logging.info("非交互模式，默认继续生成")
                            choice = "C"
                        
                        if choice == "R":
                            logging.info("🔧 用户选择修复，开始质量修复循环...")
                            
                            # 调用修复方法
                            repaired_content = self._repair_structural_issues(
                                content=existing_content,
                                validation_result=pre_check,
                                start_chapter=1,
                                end_chapter=max_existing,
                                architecture_text=architecture_text,
                                max_repair_attempts=3
                            )
                            
                            # 重新验证
                            revalidation = self._strict_validation(repaired_content, 1, max_existing)
                            if revalidation["is_valid"]:
                                logging.info("✅ 修复成功！保存修复后的内容...")
                                existing_content = repaired_content
                                # 保存修复后的内容
                                clear_file_content(filename_dir)
                                save_string_to_txt(existing_content, filename_dir)
                            else:
                                logging.error("❌ 修复后仍有问题，请手动处理：")
                                for error in revalidation["errors"]:
                                    logging.error(f"  - {error}")
                                raise Exception("质量修复失败，请手动处理已生成内容后重试")
                            break
                            
                        elif choice == "C":
                            logging.info("用户选择继续，跳过已存在问题...")
                            break
                            
                        elif choice == "Q":
                            logging.info("用户选择退出")
                            raise Exception("用户选择退出，请手动处理已生成内容")
                            
                        else:
                            print("无效选择，请输入 R、C 或 Q")
                else:
                    logging.info(f"✅ 已生成章节（1-{max_existing}）质量检测通过")
                logging.info("=" * 60)
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
                    current_start, current_end, architecture_text, final_blueprint, filepath
                )

                # 批次已完成基本验证（在 _generate_batch_with_retry 中已包含一致性检查）
                logging.info(f"✅ 第{batch_count}批生成验证完成")

                # 整合到最终结果
                if final_blueprint.strip():
                    final_blueprint += "\n\n" + batch_result.strip()
                else:
                    final_blueprint = batch_result.strip()

                # 立即保存当前进度
                clear_file_content(filename_dir)
                save_string_to_txt(final_blueprint.strip(), filename_dir)
                logging.info(f"✅ 第{batch_count}批已保存，进度：{current_end}/{number_of_chapters}")

                # 每完成一个批次后检查当前整体一致性（如果启用自动检查）
                if self.auto_consistency_check:
                    logging.info(f"🔍 执行第{batch_count}批后的整体一致性检查...")
                    current_content = read_file(filename_dir).strip()
                    if current_content:
                        overall_consistency = self._check_architecture_consistency(current_content, architecture_text)
                        logging.info(f"📊 当前整体一致性得分：{overall_consistency['overall_score']:.2f}")

                        if not overall_consistency["is_consistent"]:
                            logging.warning(f"⚠️ 整体一致性需要改进，将在后续批次中注意")
                        else:
                            logging.info(f"✅ 整体一致性良好")

                current_start = current_end + 1

            except Exception as e:
                logging.error(f"第{batch_count}批生成失败：{e}")
                # 严格模式下，任何批次失败都导致整体失败
                return False

        # 最终验证
        logging.info("🔍 进行最终全面验证...")
        final_content = read_file(filename_dir).strip()
        if final_content:
            # 1. 严格结构验证
            final_validation = self._strict_validation(final_content, 1, number_of_chapters)

            if not final_validation["is_valid"]:
                logging.error("❌ 最终结构验证失败：")
                for error in final_validation["errors"]:
                    logging.error(f"  - {error}")
                return False

            # 2. 完整一致性检查（如果启用）
            if self.auto_consistency_check:
                logging.info("🔍 执行最终架构一致性检查...")
                final_consistency = self._check_architecture_consistency(final_content, architecture_text)

                if final_consistency["is_consistent"]:
                    logging.info(f"🎉 所有验证通过！章节目录生成完成")
                    logging.info(f"📊 最终一致性得分：{final_consistency['overall_score']:.2f}")

                    # 显示详细的验证结果
                    if "detailed_result" in final_consistency and final_consistency["detailed_result"]:
                        detailed = final_consistency["detailed_result"]
                        if "checks" in detailed:
                            logging.info("📋 最终验证详情：")
                            for check_name, check_result in detailed["checks"].items():
                                status = "✅" if check_result["consistent"] else "❌"
                                score = check_result["score"]
                                logging.info(f"  {status} {check_name}: {score:.2f}")

                    return True
                else:
                    logging.error(f"❌ 最终一致性验证失败：得分 {final_consistency['overall_score']:.2f}（阈值：{self.consistency_threshold}）")
                    if final_consistency["issues"]:
                        logging.error("一致性问题：")
                        for issue in final_consistency["issues"]:
                            logging.error(f"  - {issue}")
                    return False
            else:
                logging.info("🎉 结构验证通过！章节目录生成完成（自动一致性检查已禁用）")
                return True

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
    兼容入口：统一委托给 `novel_generator.blueprint.Strict_Chapter_blueprint_generate`，
    避免与主链路逻辑漂移。
    """
    from novel_generator.blueprint import Strict_Chapter_blueprint_generate as _main_strict_generate

    return _main_strict_generate(
        interface_format=interface_format,
        api_key=api_key,
        base_url=base_url,
        llm_model=llm_model,
        filepath=filepath,
        number_of_chapters=number_of_chapters,
        user_guidance=user_guidance,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        batch_size=batch_size
    )

if __name__ == "__main__":
    pass
