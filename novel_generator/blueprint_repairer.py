#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
蓝图自动修复器
自动识别并修复低分章节蓝图
"""

import os
import re
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

from llm_adapters import create_llm_adapter

logger = logging.getLogger(__name__)


class BlueprintRepairer:
    """
    蓝图自动修复器
    """
    
    def __init__(self, interface_format: str, api_key: str, base_url: str,
                 llm_model: str, filepath: str,
                 temperature: float = 0.7, max_tokens: int = 8000, timeout: int = 600):
        self.interface_format = interface_format
        self.api_key = api_key
        self.base_url = base_url
        self.llm_model = llm_model
        self.filepath = filepath
        self.temperature = temperature
        self.max_tokens = max_tokens
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
        
        # 加载架构文件
        arch_path = Path(filepath) / "Novel_architecture.txt"
        if arch_path.exists():
            with open(arch_path, 'r', encoding='utf-8') as f:
                self.architecture_text = f.read()
        else:
            self.architecture_text = ""
            logger.warning("未找到架构文件")
    
    def _create_repair_prompt(self, chapter_number: int, original_content: str,
                               quality_issues: List[str] = None) -> str:
        """
        创建修复提示词（增强版 - 针对实际扣分项优化）
        """
        # 分类问题
        format_issues = []
        content_issues = []
        coherence_issues = []
        
        if quality_issues:
            for issue in quality_issues:
                issue_lower = issue.lower()
                if any(kw in issue for kw in ["缺失", "模块", "格式"]):
                    format_issues.append(issue)
                elif any(kw in issue for kw in ["衔接", "地点跳跃", "角色消失", "冲突未延续"]):
                    coherence_issues.append(issue)
                else:
                    content_issues.append(issue)
        
        # 构建问题描述
        issues_text = ""
        if format_issues:
            issues_text += "### 格式问题（需补充缺失模块）\n"
            issues_text += "\n".join([f"  - {i}" for i in format_issues]) + "\n\n"
        if coherence_issues:
            issues_text += "### 衔接问题（需加强章节过渡）\n"
            issues_text += "\n".join([f"  - {i}" for i in coherence_issues]) + "\n\n"
        if content_issues:
            issues_text += "### 内容问题（需提升内容质量）\n"
            issues_text += "\n".join([f"  - {i}" for i in content_issues]) + "\n\n"
        
        if not issues_text:
            issues_text = "  - 整体质量评分偏低，需要全面提升\n"
        
        prompt = f"""你是一位专业的网文大纲策划师。请根据以下信息，**优化**第{chapter_number}章的蓝图内容质量。

## 当前章节蓝图（需要优化）

{original_content}

## 发现的质量问题

{issues_text}

## 🎯 评分标准（你必须满足这些才能提高分数）

### 1. 格式规范性检查（占15%）- 必须全部满足：
- **张力评级**：必须包含星级评级，格式如 `★★★☆☆` 或 `A级/B级/S级`
- **字数目标**：必须明确写出 `目标字数：XXXX字` 或 `预计XXXX字`

### 2. 增强模块检查（占15%）- 至少包含其一：
- **知识库引用**：在内容中提及"知识库"、"背景设定"或"世界观"相关内容
- **技法运用**：在内容中提及"感官描写"、"环境烘托"或"技法运用"相关内容

### 3. 核心模块（占40%）- 确保保留：
### 3. 核心模块（占40%）- 确保保留：
基础元信息、张力与冲突、匠心思维应用、伏笔与信息差、暧昧与修罗场、剧情精要、衔接设计

## 修复要求

**【格式保持规则 - 最高优先级】**
你必须**完全保留**原蓝图的格式结构及模块命名方式（## X. 模块名）。

**【必须添加的内容】**
1. 在`## 1. 基础元信息`或开头处添加：`张力评级：★★★☆☆`（根据本章内容调整星数）
2. 在`## 1. 基础元信息`或开头处添加：`目标字数：5000字`（根据实际调整）
3. 在任意模块中自然融入"知识库"或"技法运用"相关内容

**【参考小说架构】**
{self.architecture_text[:2000] if len(self.architecture_text) > 2000 else self.architecture_text}

## 输出要求

1. 直接输出优化后的完整章节蓝图
2. 格式必须以 "第{chapter_number}章 - " 开头
3. **必须保持与原蓝图相同的格式结构和模块命名**
4. **必须包含张力评级（★格式）和字数目标**
5. 不要输出任何解释或额外内容
"""
        return prompt
    
    def repair_single_chapter(self, chapter_number: int, original_content: str,
                              quality_issues: List[str] = None,
                              max_retries: int = 3) -> Optional[str]:
        """
        修复单个章节蓝图
        
        Returns:
            修复后的内容，如果失败返回 None
        """
        prompt = self._create_repair_prompt(chapter_number, original_content, quality_issues)
        
        for attempt in range(max_retries):
            try:
                logger.info(f"修复第{chapter_number}章 (尝试 {attempt + 1}/{max_retries})")
                
                response = self.llm_adapter.invoke(prompt)
                
                if response and len(response.strip()) > 500:
                    # 基本验证：检查是否包含章节标题
                    if f"第{chapter_number}章" in response:
                        logger.info(f"第{chapter_number}章修复成功")
                        return response.strip()
                    else:
                        logger.warning(f"第{chapter_number}章修复结果格式不正确，重试...")
                else:
                    logger.warning(f"第{chapter_number}章修复结果过短，重试...")
                
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"第{chapter_number}章修复失败: {e}")
                if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                    logger.info("API 限速，等待 60 秒...")
                    time.sleep(60)
                else:
                    time.sleep(5)
        
        return None
    
    def repair_batch(self, chapters_to_repair: List[Dict[str, Any]],
                     progress_callback: Callable[[int, int, str], None] = None,
                     max_chapters: int = 200) -> Dict[str, Any]:
        """
        批量修复低分章节（增强版 - 带无效修复重试）
        
        Args:
            chapters_to_repair: 需要修复的章节列表，每项包含 chapter_number, content, issues
            progress_callback: 进度回调函数 (current, total, message)
            max_chapters: 单次最多修复章节数（默认200）
            
        Returns:
            修复结果报告（含修复前后评分对比）
        """
        from quality_checker import QualityChecker
        quality_checker = QualityChecker()
        
        # 限制修复数量
        to_repair = chapters_to_repair[:max_chapters]
        total = len(to_repair)
        
        results = {
            'total': total,
            'success': 0,
            'failed': 0,
            'no_improvement': 0,  # 新增：无提升计数
            'repaired_chapters': [],
            'failed_chapters': [],
            'score_improvements': [],
            'average_improvement': 0
        }
        
        MAX_RETRY_FOR_NO_IMPROVEMENT = 2  # 无效修复最多重试2次
        
        for idx, chapter_info in enumerate(to_repair):
            chapter_number = chapter_info['chapter_number']
            original_content = chapter_info['content']
            issues = chapter_info.get('issues', [])
            
            # 记录修复前评分
            pre_report = quality_checker.check_chapter_quality(
                original_content, {'chapter_number': chapter_number}
            )
            pre_score = pre_report.overall_score
            
            if progress_callback:
                progress_callback(idx + 1, total, f"正在修复第{chapter_number}章 (原分: {pre_score:.1f})...")
            
            best_repaired = None
            best_score = pre_score
            best_improvement = 0
            
            # 尝试修复，如果无提升则重试
            for attempt in range(MAX_RETRY_FOR_NO_IMPROVEMENT + 1):
                repaired = self.repair_single_chapter(chapter_number, original_content, issues)
                
                if not repaired:
                    break  # 修复失败，退出重试
                
                # 评估修复后质量
                post_report = quality_checker.check_chapter_quality(
                    repaired, {'chapter_number': chapter_number}
                )
                post_score = post_report.overall_score
                improvement = post_score - pre_score
                
                # 如果有提升，保留最佳结果
                if post_score > best_score:
                    best_repaired = repaired
                    best_score = post_score
                    best_improvement = improvement
                
                # 如果提升超过3分，认为修复有效，不再重试
                if improvement >= 3:
                    if progress_callback:
                        progress_callback(idx + 1, total, f"第{chapter_number}章修复成功: {pre_score:.1f} → {post_score:.1f} (✅{improvement:+.1f})")
                    break
                elif attempt < MAX_RETRY_FOR_NO_IMPROVEMENT:
                    if progress_callback:
                        progress_callback(idx + 1, total, f"第{chapter_number}章提升不足 ({improvement:+.1f})，重试 {attempt + 2}/{MAX_RETRY_FOR_NO_IMPROVEMENT + 1}...")
                    time.sleep(2)  # 重试前等待
            
            # 处理结果
            if best_repaired and best_improvement > 0:
                # 有提升，使用最佳结果
                if progress_callback and best_improvement < 3:
                    progress_callback(idx + 1, total, f"第{chapter_number}章修复完成: {pre_score:.1f} → {best_score:.1f} (⬆️{best_improvement:+.1f})")
                
                results['success'] += 1
                results['repaired_chapters'].append({
                    'chapter_number': chapter_number,
                    'new_content': best_repaired,
                    'pre_score': pre_score,
                    'post_score': best_score,
                    'improvement': best_improvement
                })
                results['score_improvements'].append(best_improvement)
            elif best_repaired:
                # 修复成功但无提升，仍保存（可能修复了格式问题）
                if progress_callback:
                    progress_callback(idx + 1, total, f"第{chapter_number}章无明显提升: {pre_score:.1f} → {best_score:.1f} (➖保留原内容)")
                results['no_improvement'] += 1
                # 不保存无提升的修复，保留原内容
            else:
                if progress_callback:
                    progress_callback(idx + 1, total, f"第{chapter_number}章修复失败 ❌")
                results['failed'] += 1
                results['failed_chapters'].append(chapter_number)
            
            # 避免API限速
            time.sleep(1)
        
        # 计算平均提升
        if results['score_improvements']:
            results['average_improvement'] = sum(results['score_improvements']) / len(results['score_improvements'])
        
        # 生成详细报告
        self._generate_repair_report(results)
        
        return results
    
    def _generate_repair_report(self, results: Dict[str, Any]):
        """
        生成修复报告 Markdown 文件
        """
        from datetime import datetime
        
        report_path = Path(self.filepath) / "blueprint_repair_report.md"
        
        report_lines = [
            "# 蓝图修复报告",
            f"",
            f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"",
            "## 修复概览",
            f"",
            f"| 指标 | 数值 |",
            f"|------|------|",
            f"| 总修复数 | {results['total']} |",
            f"| 成功数 | {results['success']} |",
            f"| 失败数 | {results['failed']} |",
            f"| 平均提升 | {results['average_improvement']:.2f} 分 |",
            f"",
        ]
        
        if results['repaired_chapters']:
            report_lines.extend([
                "## 修复详情",
                f"",
                "| 章节 | 修复前 | 修复后 | 提升 |",
                "|------|--------|--------|------|",
            ])
            for ch in results['repaired_chapters']:
                status = "✅" if ch['improvement'] > 0 else ("➖" if ch['improvement'] == 0 else "⚠️")
                report_lines.append(
                    f"| 第{ch['chapter_number']}章 | {ch['pre_score']:.1f} | {ch['post_score']:.1f} | {status} {ch['improvement']:+.1f} |"
                )
            report_lines.append("")
        
        if results['failed_chapters']:
            report_lines.extend([
                "## 修复失败章节",
                f"",
                f"以下章节修复失败，需人工处理：",
                f"",
                ", ".join([f"第{n}章" for n in results['failed_chapters']]),
                ""
            ])
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(report_lines))
        
        logger.info(f"修复报告已保存至: {report_path}")
    
    def save_repaired_chapters(self, repaired_chapters: List[Dict[str, Any]]) -> bool:
        """
        将修复后的章节保存回目录文件（带去重预处理）
        """
        directory_path = Path(self.filepath) / "Novel_directory.txt"
        
        if not directory_path.exists():
            logger.error("目录文件不存在")
            return False
        
        try:
            with open(directory_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # === 去重预处理：确保每个章节号只有一个版本 ===
            chapter_pattern = r'^(第\d+章\s*[-—]?\s*.*?)(?=^第\d+章|\Z)'
            matches = re.findall(chapter_pattern, content, re.MULTILINE | re.DOTALL)
            
            # 使用字典保留每个章节号的最后一个版本
            from collections import OrderedDict
            chapters_dict = OrderedDict()
            for section in matches:
                section = section.strip()
                if not section:
                    continue
                match = re.search(r'第(\d+)章', section)
                if match:
                    chapter_number = int(match.group(1))
                    chapters_dict[chapter_number] = section
            
            original_count = len(matches)
            unique_count = len(chapters_dict)
            if original_count != unique_count:
                logger.info(f"去重预处理: {original_count} -> {unique_count} 章节")
            
            # 逐个替换修复后的章节（直接更新字典）
            for chapter in repaired_chapters:
                chapter_number = chapter['chapter_number']
                new_content = chapter['new_content']
                
                if chapter_number in chapters_dict:
                    chapters_dict[chapter_number] = new_content.strip()
                    logger.info(f"第{chapter_number}章已更新")
                else:
                    # 如果章节不存在，添加到末尾
                    chapters_dict[chapter_number] = new_content.strip()
                    logger.info(f"第{chapter_number}章已添加")
            
            # 按章节号排序并重建内容
            sorted_chapters = sorted(chapters_dict.items(), key=lambda x: x[0])
            final_content = "\n\n".join([ch[1] for ch in sorted_chapters])
            
            # 保存更新后的文件
            with open(directory_path, 'w', encoding='utf-8') as f:
                f.write(final_content)
            
            logger.info(f"已保存 {len(repaired_chapters)} 个修复后的章节（总章节数: {len(chapters_dict)}）")
            return True
            
        except Exception as e:
            logger.error(f"保存修复结果失败: {e}")
            return False


def repair_low_score_blueprints(
    interface_format: str,
    api_key: str,
    base_url: str,
    llm_model: str,
    filepath: str,
    low_score_chapters: List[int],
    chapter_issues: Dict[int, List[str]] = None,  # 新增：具体问题映射
    progress_callback: Callable[[int, int, str], None] = None,
    max_chapters: int = 50
) -> Dict[str, Any]:
    """
    修复低分蓝图的便捷函数（增强版 - 支持传递具体问题）
    
    Args:
        chapter_issues: 章节号 -> 问题列表的映射，如 {1: ["缺失模块", "衔接问题"]}
    """
    from batch_quality_check import load_novel_directory
    
    # 加载目录
    directory_path = Path(filepath) / "Novel_directory.txt"
    chapters = load_novel_directory(str(directory_path))
    
    # 如果没有传入问题映射，尝试从质量报告中读取
    if chapter_issues is None:
        chapter_issues = {}
        report_path = Path(filepath) / "chapter_quality_report.json"
        if report_path.exists():
            try:
                import json
                with open(report_path, 'r', encoding='utf-8') as f:
                    report = json.load(f)
                # 从 format_issues 和 low_score_chapters 中提取问题
                for item in report.get("format_issues", []):
                    ch_num = item.get("chapter_number")
                    missing = item.get("missing_modules", [])
                    if ch_num and missing:
                        if ch_num not in chapter_issues:
                            chapter_issues[ch_num] = []
                        chapter_issues[ch_num].extend([f"缺失模块: {m}" for m in missing])
                for item in report.get("low_score_chapters", []):
                    ch_num = item.get("chapter_number")
                    issues = item.get("issues", [])
                    if ch_num and issues:
                        if ch_num not in chapter_issues:
                            chapter_issues[ch_num] = []
                        chapter_issues[ch_num].extend(issues)
            except Exception as e:
                logger.warning(f"读取质量报告失败: {e}")
    
    # 筛选需要修复的章节
    chapters_to_repair = []
    for chapter in chapters:
        ch_num = chapter['chapter_number']
        if ch_num in low_score_chapters:
            chapters_to_repair.append({
                'chapter_number': ch_num,
                'content': chapter['content'],
                'issues': chapter_issues.get(ch_num, [])  # 传递具体问题
            })
    
    if not chapters_to_repair:
        return {'total': 0, 'success': 0, 'failed': 0}
    
    # 创建修复器并执行
    repairer = BlueprintRepairer(
        interface_format=interface_format,
        api_key=api_key,
        base_url=base_url,
        llm_model=llm_model,
        filepath=filepath
    )
    
    results = repairer.repair_batch(chapters_to_repair, progress_callback, max_chapters)
    
    # 保存修复结果
    if results['repaired_chapters']:
        repairer.save_repaired_chapters(results['repaired_chapters'])
    
    return results
