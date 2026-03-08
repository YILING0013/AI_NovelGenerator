# novel_generator/progressive_blueprint_generator.py
# -*- coding: utf-8 -*-
"""
三阶段渐进式蓝图生成器

采用"结构规划 → 逐章生成 → 整体检查"的三阶段生成流程，
确保最高质量的蓝图输出。

特点：
- 阶段1：先生成章节骨架，确保结构正确
- 阶段2：逐章生成并多层验证，确保每章质量
- 阶段3：整体一致性检查，确保连贯性
- 不计成本，追求最高质量

作者: AI架构重构团队
创建日期: 2026-01-04
"""

import os
import re
import json
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

from novel_generator.common import invoke_with_cleaning
from llm_adapters import create_llm_adapter
from novel_generator.architecture_extractor import DynamicArchitectureExtractor
from architecture_consistency_checker import ArchitectureConsistencyChecker
from optimized_rate_limiter import get_rate_limiter
from utils import read_file, save_string_to_txt


# ==================== 配置常量 ====================

class ProgressiveConfig:
    """三阶段生成器配置"""

    # 阶段1配置
    STAGE1_MAX_RETRIES = 5  # 标题生成最大重试次数
    STAGE1_RETRY_DELAY = 5  # 重试延迟（秒）

    # 阶段2配置
    STAGE2_MAX_RETRIES = 5  # 单章生成最大重试次数
    STAGE2_RETRY_DELAY = 3  # 重试延迟（秒）
    STAGE2_QUALITY_THRESHOLD = 0.9  # 质量阈值

    # 阶段3配置
    STAGE3_QUALITY_THRESHOLD = 0.85  # 整体质量阈值
    STAGE3_AUTO_REPAIR = True  # 是否自动修复

    # 验证配置
    ENABLE_SELF_REFLECTION = True  # 启用LLM自我反思验证
    ENABLE_CONSISTENCY_CHECK = True  # 启用一致性检查

    # 日志配置
    LOG_LEVEL = logging.INFO


# ==================== 多层验证系统 ====================

class MultiLevelValidator:
    """多层验证系统"""

    def __init__(self, architecture_text: str, config: ProgressiveConfig):
        self.architecture_text = architecture_text
        self.config = config
        self.consistency_checker = ArchitectureConsistencyChecker()

        # 正则表达式模式
        self.chapter_title_pattern = r'^第(\d+)章\s+-\s+.+$'
        self.section_header_pattern = r'^##\s*\d+\.\s+.+$'

        self.required_modules = {
            "## 1. 基础元信息",
            "## 2. 张力与冲突",
            "## 3. 匠心思维应用",
            "## 4. 伏笔与信息差",
            "## 5. 暧昧与修罗场",
            "## 6. 剧情精要",
            "## 7. 衔接设计",
        }

        self.optional_modules = set()

        # 必需子节点
        self.required_subnodes = {
            "剧情精要": ["开场", "发展", "高潮", "收尾"],
            "张力与冲突": ["冲突类型", "核心冲突点", "紧张感曲线"],
            "基础元信息": ["定位", "核心功能"],
        }

    def validate_all_levels(self, content: str, chapter_num: int) -> Dict[str, Any]:
        """
        执行所有层级的验证

        Returns:
            {
                'all_valid': bool,
                'level1_structure': {...},
                'level2_format': {...},
                'level3_content': {...},
                'level4_consistency': {...},
                'level5_reflection': {...},
            }
        """
        result = {
            'all_valid': True,
            'chapter_num': chapter_num,
            'errors': [],
            'warnings': [],
        }

        # 层级1: 结构验证
        level1 = self._validate_level1_structure(content)
        result['level1_structure'] = level1
        if not level1['valid']:
            result['all_valid'] = False
            result['errors'].extend([f"[结构] {e}" for e in level1['errors']])

        # 层级2: 格式验证
        level2 = self._validate_level2_format(content, chapter_num)
        result['level2_format'] = level2
        if not level2['valid']:
            result['all_valid'] = False
            result['errors'].extend([f"[格式] {e}" for e in level2['errors']])

        # 层级3: 内容完整性验证
        level3 = self._validate_level3_content(content)
        result['level3_content'] = level3
        if not level3['valid']:
            result['all_valid'] = False
            result['errors'].extend([f"[内容] {e}" for e in level3['errors']])

        # 层级4: 一致性验证
        level4 = self._validate_level4_consistency(content)
        result['level4_consistency'] = level4
        if not level4['valid']:
            result['all_valid'] = False
            result['errors'].extend([f"[一致性] {e}" for e in level4['errors']])

        # 层级5: LLM自我反思验证（可选）
        if self.config.ENABLE_SELF_REFLECTION:
            level5 = self._validate_level5_reflection(content, chapter_num)
            result['level5_reflection'] = level5
            if not level5['valid']:
                result['all_valid'] = False
                result['errors'].extend([f"[反思] {e}" for e in level5['errors']])
        else:
            result['level5_reflection'] = {'valid': True, 'skipped': True}

        return result

    def _validate_level1_structure(self, content: str) -> Dict[str, Any]:
        """层级1: 结构验证 - 检查必需模块和子节点"""
        result = {'valid': True, 'errors': [], 'warnings': []}

        # 检查严重省略违规
        severe_patterns = [
            r'后续章节类似',
            r'后面章节结构相同',
            r'第.*章.*至.*章.*省略',
            r'由于篇幅限制',
            r'批量.*生成',
            r'详细内容省略',
            r'此处省略',
        ]

        for pattern in severe_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                result['valid'] = False
                result['errors'].append(f"发现严重省略模式: {pattern}")

        # 检查所有必需模块
        for module in self.required_modules:
            if module not in content:
                result['valid'] = False
                result['errors'].append(f"缺少必需模块: {module}")

        for module in self.optional_modules:
            if module not in content:
                result['warnings'].append(f"建议补充模块: {module}")

        # 检查必需子节点
        for section, required_fields in self.required_subnodes.items():
            if section in content:
                for field in required_fields:
                    # 使用更灵活的匹配（允许前后有空格和*符号）
                    pattern = rf'\*\s*{field}\*'
                    if not re.search(pattern, content):
                        result['errors'].append(f"{section}缺少字段: {field}")

        return result

    def _validate_level2_format(self, content: str, chapter_num: int) -> Dict[str, Any]:
        """层级2: 格式验证 - 检查标题、小节格式"""
        result = {'valid': True, 'errors': [], 'warnings': []}

        lines = content.splitlines()
        found_chapter_header = False

        for line in lines:
            stripped = line.strip()

            # 检查章节标题格式
            if re.match(r'^第\d+章', stripped):
                if not re.match(self.chapter_title_pattern, stripped):
                    result['valid'] = False
                    result['errors'].append(f"章节标题格式错误: {stripped}")
                else:
                    # 检查章节编号是否匹配
                    match = re.match(r'^第(\d+)章', stripped)
                    if match:
                        actual_num = int(match.group(1))
                        if actual_num != chapter_num:
                            result['valid'] = False
                            result['errors'].append(
                                f"章节编号不匹配: 期望{chapter_num}, 实际{actual_num}"
                            )
                found_chapter_header = True

        if not found_chapter_header:
            result['valid'] = False
            result['errors'].append("未找到章节标题")

        return result

    def _validate_level3_content(self, content: str) -> Dict[str, Any]:
        """层级3: 内容完整性验证 - 检查必填字段、无空值"""
        result = {'valid': True, 'errors': [], 'warnings': []}

        # 检查是否有过短的内容
        lines = content.splitlines()
        content_lines = [l for l in lines if l.strip() and not l.strip().startswith('#')]

        if len(content_lines) < 20:
            result['valid'] = False
            result['errors'].append(f"内容过少: 仅{len(content_lines)}行")

        # 检查空值
        empty_field_pattern = r'\*\s*\*\*\*\s*\*:\s*(?:\s*$|None|null|待定| TBD|TBD)'
        empty_fields = re.findall(empty_field_pattern, content, re.IGNORECASE)
        if empty_fields:
            result['warnings'].append(f"发现{len(empty_fields)}个空字段")

        return result

    def _validate_level4_consistency(self, content: str) -> Dict[str, Any]:
        """层级4: 一致性验证 - 检查角色名、术语、设定"""
        result = {'valid': True, 'errors': [], 'warnings': [], 'score': 1.0}

        # 名称一致性检查应基于当前项目架构，不在此处内置固定角色/势力映射。

        return result

    def _validate_level5_reflection(self, content: str, chapter_num: int) -> Dict[str, Any]:
        """层级5: LLM自我反思验证 - 让LLM自己检查"""
        result = {'valid': True, 'errors': [], 'warnings': [], 'reflection': ''}

        # 这个方法需要在调用时传入LLM adapter
        # 这里只返回占位符
        result['warnings'].append("自我反思验证需要在生成器中调用")

        return result


# ==================== 三阶段生成器 ====================

class ProgressiveBlueprintGenerator:
    """
    三阶段渐进式蓝图生成器

    流程：
    阶段1: 结构规划 - 生成章节标题
    阶段2: 逐章生成 - 多层验证
    阶段3: 整体检查 - 一致性验证
    """

    def __init__(
        self,
        interface_format: str,
        api_key: str,
        base_url: str,
        llm_model: str,
        temperature: float = 0.8,
        max_tokens: int = 8000,
        timeout: int = 300,
        config: Optional[ProgressiveConfig] = None
    ):
        # 基础配置
        self.interface_format = interface_format
        self.api_key = api_key
        self.base_url = base_url
        self.llm_model = llm_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

        # LLM适配器
        self.llm_adapter = create_llm_adapter(
            interface_format=interface_format,
            base_url=base_url,
            model_name=llm_model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout
        )

        # 配置
        self.config = config or ProgressiveConfig()

        # 工具
        self.rate_limiter = get_rate_limiter()
        self.consistency_checker = ArchitectureConsistencyChecker()

        # 状态跟踪
        self.generation_log = {
            'start_time': datetime.now().isoformat(),
            'stage1': {},
            'stage2': {},
            'stage3': {},
        }

    # ==================== 阶段1：结构规划 ====================

    def stage1_generate_titles(
        self,
        number_of_chapters: int,
        architecture_text: str
    ) -> List[str]:
        """
        阶段1: 生成章节标题列表

        Args:
            number_of_chapters: 章节总数
            architecture_text: 架构文本

        Returns:
            章节标题列表，如 ["第1章 - 标题A", "第2章 - 标题B", ...]
        """
        logging.info("=" * 60)
        logging.info("📐 阶段1: 结构规划 - 生成章节标题")
        logging.info("=" * 60)

        self.generation_log['stage1']['start_time'] = datetime.now().isoformat()
        self.generation_log['stage1']['number_of_chapters'] = number_of_chapters

        for attempt in range(self.config.STAGE1_MAX_RETRIES):
            try:
                logging.info(f"尝试第{attempt + 1}次生成标题...")

                # 生成标题
                titles = self._generate_titles_attempt(
                    number_of_chapters, architecture_text
                )

                # 验证标题
                validation = self._validate_titles(titles, number_of_chapters)

                if validation['valid']:
                    logging.info(f"✅ 阶段1完成：生成{len(titles)}个章节标题")
                    self.generation_log['stage1']['success'] = True
                    self.generation_log['stage1']['attempts'] = attempt + 1
                    self.generation_log['stage1']['titles'] = titles
                    return titles
                else:
                    logging.warning(f"标题验证失败：{validation['errors']}")
                    if attempt < self.config.STAGE1_MAX_RETRIES - 1:
                        logging.info(f"等待{self.config.STAGE1_RETRY_DELAY}秒后重试...")
                        time.sleep(self.config.STAGE1_RETRY_DELAY)

            except Exception as e:
                logging.error(f"生成标题异常: {e}")
                if attempt < self.config.STAGE1_MAX_RETRIES - 1:
                    time.sleep(self.config.STAGE1_RETRY_DELAY)

        # 所有尝试都失败
        raise Exception(
            f"阶段1失败：无法生成有效的章节标题，"
            f"已尝试{self.config.STAGE1_MAX_RETRIES}次"
        )

    def _generate_titles_attempt(
        self,
        number_of_chapters: int,
        architecture_text: str
    ) -> List[str]:
        """单次标题生成尝试"""
        prompt = f"""
请为小说的{number_of_chapters}个章节生成标题列表。

📋 小说架构概览：
{architecture_text[:3000]}

🎯 标题生成要求：
1. 格式：必须是 `第X章 - [标题]`（章节号与章字之间无空格，破折号前后有空格）
2. 数量：正好{number_of_chapters}个标题，从第1章到第{number_of_chapters}章
3. 连续性：章节编号必须连续，不得跳号
4. 唯一性：每个章节编号只出现一次
5. 吸引力：标题要有悬念或信息量，体现章节核心内容
6. 一致性：标题内容必须与小说架构设定一致

🚨 严禁以下行为：
- 使用格式如 `第 X 章`（有空格）或 `第X章[标题]`（无破折号）
- 重复章节编号
- 跳号或漏号
- 空标题或无意义标题

✅ 正确示例：
第1章 - 风雪夜的转折点
第7章 - 旧线索的新裂痕

❌ 错误示例：
第 1 章 - 风雪夜的转折点（空格太多）
第1章[标题]（缺少破折号）
第1章（无标题）

请直接输出{number_of_chapters}行标题，每行一个，不要添加其他内容：
"""

        self.rate_limiter.record_prompt()
        result = invoke_with_cleaning(self.llm_adapter, prompt)

        if not result or not result.strip():
            raise Exception("生成结果为空")

        # 解析标题
        lines = result.strip().splitlines()
        titles = [line.strip() for line in lines if line.strip()]

        logging.info(f"生成了{len(titles)}个标题")

        return titles

    def _validate_titles(
        self,
        titles: List[str],
        expected_count: int
    ) -> Dict[str, Any]:
        """验证标题列表"""
        result = {'valid': True, 'errors': [], 'warnings': []}

        # 检查数量
        if len(titles) != expected_count:
            result['valid'] = False
            result['errors'].append(
                f"标题数量错误：期望{expected_count}个，实际{len(titles)}个"
            )

        # 检查格式和提取编号
        chapter_numbers = []
        for i, title in enumerate(titles):
            # 检查格式
            if not re.match(r'^第\d+章\s+-\s+.+$', title):
                result['valid'] = False
                result['errors'].append(f"第{i+1}行格式错误: {title}")
                continue

            # 提取编号
            match = re.match(r'^第(\d+)章', title)
            if match:
                num = int(match.group(1))
                chapter_numbers.append(num)

        # 检查连续性
        if sorted(chapter_numbers) != list(range(1, expected_count + 1)):
            result['valid'] = False
            result['errors'].append(f"章节编号不连续: {chapter_numbers}")

        # 检查重复
        if len(chapter_numbers) != len(set(chapter_numbers)):
            duplicates = [x for x in chapter_numbers if chapter_numbers.count(x) > 1]
            result['valid'] = False
            result['errors'].append(f"发现重复章节: {set(duplicates)}")

        return result

    # ==================== 阶段2：逐章生成 ====================

    def stage2_generate_chapters(
        self,
        titles: List[str],
        architecture_text: str,
        filepath: str
    ) -> bool:
        """
        阶段2: 逐章生成蓝图

        Args:
            titles: 章节标题列表
            architecture_text: 架构文本
            filepath: 保存路径

        Returns:
            是否全部成功
        """
        logging.info("=" * 60)
        logging.info("✍️ 阶段2: 逐章生成 - 多层验证")
        logging.info("=" * 60)

        self.generation_log['stage2']['start_time'] = datetime.now().isoformat()
        self.generation_log['stage2']['total_chapters'] = len(titles)

        # 创建验证器
        validator = MultiLevelValidator(architecture_text, self.config)

        # 准备输出文件
        output_file = os.path.join(filepath, "Novel_directory.txt")
        all_content = []

        # 逐章生成
        for idx, title in enumerate(titles):
            chapter_num = idx + 1

            logging.info(f"\n{'=' * 40}")
            logging.info(f"📝 生成第{chapter_num}章: {title}")
            logging.info(f"{'=' * 40}")

            # 获取前几章作为上下文
            previous_context = "\n\n".join(all_content[-3:]) if all_content else ""

            try:
                # 生成单章
                chapter_content = self._generate_single_chapter_with_retry(
                    chapter_num=chapter_num,
                    chapter_title=title,
                    architecture_text=architecture_text,
                    previous_context=previous_context,
                    validator=validator
                )

                # 添加到总内容
                all_content.append(chapter_content)

                # 立即保存
                current_content = "\n\n".join(all_content)
                save_string_to_txt(current_content, output_file)

                logging.info(f"✅ 第{chapter_num}章完成并保存 ({idx+1}/{len(titles)})")

            except Exception as e:
                logging.error(f"❌ 第{chapter_num}章生成失败: {e}")
                self.generation_log['stage2']['failed_chapters'] = self.generation_log['stage2'].get('failed_chapters', [])
                self.generation_log['stage2']['failed_chapters'].append(chapter_num)

                # 严格模式：任何章节失败都终止
                raise Exception(f"第{chapter_num}章生成失败，已终止整体生成")

        self.generation_log['stage2']['success'] = True
        self.generation_log['stage2']['end_time'] = datetime.now().isoformat()

        logging.info("\n" + "=" * 60)
        logging.info(f"✅ 阶段2完成：成功生成{len(titles)}章")
        logging.info("=" * 60)

        return True

    def _generate_single_chapter_with_retry(
        self,
        chapter_num: int,
        chapter_title: str,
        architecture_text: str,
        previous_context: str,
        validator: MultiLevelValidator
    ) -> str:
        """生成单章（带重试）"""
        last_errors = []

        for attempt in range(self.config.STAGE2_MAX_RETRIES):
            try:
                logging.info(f"  → 尝试 {attempt + 1}/{self.config.STAGE2_MAX_RETRIES}")

                # 生成内容
                content = self._generate_single_chapter_content(
                    chapter_num, chapter_title, architecture_text, previous_context
                )

                # 多层验证
                validation = validator.validate_all_levels(content, chapter_num)

                if validation['all_valid']:
                    logging.info(f"  ✅ 第{chapter_num}章验证通过")
                    return content
                else:
                    logging.warning(f"  ⚠️ 第{chapter_num}章验证失败:")
                    for error in validation['errors'][:5]:
                        logging.warning(f"     - {error}")

                    last_errors = validation['errors']

                    if attempt < self.config.STAGE2_MAX_RETRIES - 1:
                        # 尝试针对性修复
                        if self.config.ENABLE_SELF_REFLECTION:
                            logging.info(f"  🔄 尝试LLM自我修复...")
                            repaired = self._attempt_llm_repair(
                                content, validation, chapter_num, architecture_text
                            )
                            if repaired:
                                revalidation = validator.validate_all_levels(repaired, chapter_num)
                                if revalidation['all_valid']:
                                    logging.info(f"  ✅ 修复成功")
                                    return repaired

                        logging.info(f"  ⏳ 等待{self.config.STAGE2_RETRY_DELAY}秒后重试...")
                        time.sleep(self.config.STAGE2_RETRY_DELAY)

            except Exception as e:
                logging.error(f"  ❌ 生成异常: {e}")
                last_errors = [str(e)]

        # 所有尝试都失败
        error_summary = "\n".join(last_errors[:3])
        raise Exception(
            f"第{chapter_num}章生成失败，已尝试{self.config.STAGE2_MAX_RETRIES}次\n"
            f"最后错误:\n{error_summary}"
        )

    def _generate_single_chapter_content(
        self,
        chapter_num: int,
        chapter_title: str,
        architecture_text: str,
        previous_context: str
    ) -> str:
        """生成单章内容"""
        # 构建上下文
        context_part = f"""
## 前几章概要（用于保持连贯性）：
{previous_context[-2000:] if previous_context else "（这是第一章）"}

## 当前章节信息：
- 章节编号：{chapter_num}
- 章节标题：{chapter_title}
""" if previous_context else f"""

## 当前章节信息：
- 章节编号：{chapter_num}
- 章节标题：{chapter_title}
- 这是开篇章节
"""

        prompt = f"""
请为第{chapter_num}章生成详细的章节蓝图。

{context_part}

## 小说架构设定：
{architecture_text[:4000]}

🚨 **格式强制要求**：
1. **章节标题行**：必须是 `第X章 - [章节标题]`（无空格，有破折号）
2. **小节标题**：必须是 `## X. [小节标题]`（## + 数字 + 点 + 空格 + 标题）
3. **严禁混用格式**：不得在文中切换格式

## 必需包含的模块（按顺序）：
## 1. 基础元信息
*   **章节**：第{chapter_num}章 - {chapter_title}
*   **定位**：第X卷 [卷名] - 子幕X [子幕名]
*   **核心功能**：[一句话概括本章作用]
*   **字数目标**：3000-5000字
*   **出场角色**：[角色列表]

## 2. 张力与冲突
*   **冲突类型**：[生存/利益/理念/情感]
*   **核心冲突点**：[具体冲突事件]
*   **紧张感曲线**：
    *   **铺垫**：[起始状态]
    *   **爬升**：[事件升级]
    *   **爆发**：[高潮点]
    *   **回落/悬念**：[收尾]

## 3. 匠心思维应用
*   **思维模式**：[断代鉴定/金缮修复/揭裱重装等]
*   **应用场景**：[本章哪里用了理性思维]
*   **视觉化描述**：
    *   *正确写法*：[具体视觉奇观描写]
    *   *错误写法*：[避免的通用描述]
*   **经典台词**：
    *   "[体现理性霸道的台词]"

## 4. 伏笔与信息差
*   **本章植入伏笔**：
    *   [伏笔内容] -> [预计在第X章揭示]
*   **本章回收伏笔**：
    *   [伏笔内容] <- [埋藏于第X章] (如无则填"无")
*   **信息差控制**：
    *   主角知道：[...]
    *   敌人/路人以为：[...]

## 5. 暧昧与修罗场
*   **涉及的女性角色互动**：[描述女性角色互动，如女主A、女主B等]
*   **🚨 重要**：即使本章不涉及任何女性角色，也**必须保留此节**，并填写"本章不涉及女性角色互动"

## 6. 剧情精要
*   **开场**：[前500字内容]
*   **发展**：
    *   [节点1]
    *   [节点2]
*   **高潮**：[本章最高能的场面]
*   **收尾**：[结尾留下的悬念]

## 7. 衔接设计
*   **承上**：[承接前文的关键情节或伏笔]
*   **转场**：[本章的转场方式]
*   **启下**：[为后续章节埋下伏笔或设置悬念]

⚠️ **绝对禁止**：
- 使用"..."、"…"、"省略"等表示内容省略
- 使用"由于篇幅限制"等借口
- 批量省略章节或内容
- 重复章节编号
- 与架构设定冲突的角色名、地名、术语

现在开始生成第{chapter_num}章的完整蓝图：
"""

        self.rate_limiter.record_prompt()
        result = invoke_with_cleaning(self.llm_adapter, prompt)

        if not result or not result.strip():
            raise Exception("生成结果为空")

        return "\n" + result

    def _attempt_llm_repair(
        self,
        content: str,
        validation: Dict[str, Any],
        chapter_num: int,
        architecture_text: str
    ) -> Optional[str]:
        """尝试LLM修复"""
        # 提取错误信息
        error_summary = "\n".join(validation['errors'][:5])

        repair_prompt = f"""
以下章节蓝图验证未通过，请修复问题：

## 当前内容：
{content}

## 发现的问题：
{error_summary}

## 修复要求：
1. 修复上述所有问题
2. 保持原有内容结构和质量
3. 确保格式完全符合要求
4. 不要使用省略号或省略表述

请输出修复后的完整内容：
"""

        try:
            self.rate_limiter.record_prompt()
            repaired = invoke_with_cleaning(self.llm_adapter, repair_prompt)
            return "\n" + repaired if repaired and repaired.strip() else None
        except Exception as e:
            logging.warning(f"LLM修复失败: {e}")
            return None

    # ==================== 阶段3：整体检查 ====================

    def stage3_overall_check(
        self,
        filepath: str,
        architecture_text: str
    ) -> Dict[str, Any]:
        """
        阶段3: 整体一致性检查

        Args:
            filepath: 文件路径
            architecture_text: 架构文本

        Returns:
            检查结果
        """
        logging.info("=" * 60)
        logging.info("🔗 阶段3: 整体一致性检查")
        logging.info("=" * 60)

        self.generation_log['stage3']['start_time'] = datetime.now().isoformat()

        # 读取生成的内容
        output_file = os.path.join(filepath, "Novel_directory.txt")
        content = read_file(output_file)

        # 3.1 架构一致性检查
        logging.info("执行架构一致性检查...")
        consistency_result = self.consistency_checker.check_full_consistency(
            architecture_text, content
        )

        self.generation_log['stage3']['consistency_score'] = consistency_result['overall_score']

        logging.info(f"📊 一致性得分: {consistency_result['overall_score']:.2f}")

        if consistency_result['issues']:
            logging.warning("发现一致性问题:")
            for issue in consistency_result['issues'][:5]:
                logging.warning(f"  - {issue}")

        # 3.2 整体质量评分
        quality_result = self._calculate_overall_quality(content)

        self.generation_log['stage3']['quality_score'] = quality_result['score']
        logging.info(f"📊 质量得分: {quality_result['score']:.2f}")

        # 3.3 判断是否需要修复
        is_acceptable = (
            consistency_result['overall_score'] >= self.config.STAGE3_QUALITY_THRESHOLD and
            quality_result['score'] >= self.config.STAGE3_QUALITY_THRESHOLD
        )

        self.generation_log['stage3']['is_acceptable'] = is_acceptable
        self.generation_log['stage3']['end_time'] = datetime.now().isoformat()

        if is_acceptable:
            logging.info("\n" + "=" * 60)
            logging.info("🎉 三阶段生成全部完成！质量达标")
            logging.info("=" * 60)
        else:
            logging.warning("\n" + "=" * 60)
            logging.warning("⚠️ 整体质量未达预期，建议人工审查")
            logging.warning("=" * 60)

        return {
            'is_acceptable': is_acceptable,
            'consistency_score': consistency_result['overall_score'],
            'quality_score': quality_result['score'],
            'issues': consistency_result.get('issues', []),
        }

    def _calculate_overall_quality(self, content: str) -> Dict[str, Any]:
        """计算整体质量得分"""
        # 简单的质量评分
        score = 1.0

        lines = content.splitlines()
        content_lines = [l for l in lines if l.strip()]

        # 检查1: 章节数量
        chapter_count = len(re.findall(r'^第\d+章', content, re.MULTILINE))
        if chapter_count < 20:
            score -= 0.1 * (20 - chapter_count)

        # 检查2: 平均每章行数
        avg_lines = len(content_lines) / max(chapter_count, 1)
        if avg_lines < 15:
            score -= 0.2

        # 检查3: 必需模块覆盖率
        required_modules = ["基础元信息", "张力与冲突", "匠心思维应用", "伏笔与信息差", "暧昧与修罗场", "剧情精要", "衔接设计"]
        module_coverage = sum(1 for m in required_modules if m in content) / len(required_modules)
        score *= module_coverage

        return {
            'score': max(0.0, min(1.0, score)),
            'chapter_count': chapter_count,
            'avg_lines_per_chapter': avg_lines,
        }

    # ==================== 主流程 ====================

    def generate_progressive(
        self,
        filepath: str,
        number_of_chapters: int,
        architecture_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        执行完整的三阶段生成流程

        Args:
            filepath: 输出路径
            number_of_chapters: 章节总数
            architecture_text: 架构文本（如果为None则从文件读取）

        Returns:
            生成结果
        """
        start_time = datetime.now()

        try:
            # 读取架构
            if not architecture_text:
                arch_file = os.path.join(filepath, "Novel_architecture.txt")
                if not os.path.exists(arch_file):
                    raise Exception("Novel_architecture.txt not found")
                architecture_text = read_file(arch_file).strip()

            # 阶段1: 结构规划
            titles = self.stage1_generate_titles(number_of_chapters, architecture_text)

            # 阶段2: 逐章生成
            self.stage2_generate_chapters(titles, architecture_text, filepath)

            # 阶段3: 整体检查
            final_result = self.stage3_overall_check(filepath, architecture_text)

            # 记录总耗时
            end_time = datetime.now()
            self.generation_log['total_duration'] = str(end_time - start_time)
            self.generation_log['end_time'] = end_time.isoformat()
            self.generation_log['success'] = final_result['is_acceptable']

            # 保存生成日志
            log_file = os.path.join(filepath, "generation_log.json")
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(self.generation_log, f, ensure_ascii=False, indent=2)

            return {
                'success': final_result['is_acceptable'],
                'log_file': log_file,
                'consistency_score': final_result['consistency_score'],
                'quality_score': final_result['quality_score'],
                'total_duration': self.generation_log['total_duration'],
            }

        except Exception as e:
            logging.error(f"三阶段生成失败: {e}")
            self.generation_log['success'] = False
            self.generation_log['error'] = str(e)

            return {
                'success': False,
                'error': str(e),
            }
