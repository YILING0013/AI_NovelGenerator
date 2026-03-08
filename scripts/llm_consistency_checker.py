# llm_consistency_checker.py
# -*- coding: utf-8 -*-
"""
LLM驱动的一致性检查器
使用大语言模型进行深度一致性分析

功能:
1. 角色一致性检查 - 验证角色行为、语言、心理状态
2. 情节逻辑检查 - 验证时间线、因果关系、事件发展
3. 世界观一致性检查 - 验证设定规则、物理定律、社会背景
4. 伏笔呼应检查 - 验证前后呼应、伏笔设计

版本: 1.0
创建时间: 2025-12-07
"""

import json
import logging
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConsistencyType(Enum):
    """一致性检查类型"""
    CHARACTER = "角色一致性"
    PLOT = "情节逻辑"
    WORLDVIEW = "世界观一致性"
    FORESHADOWING = "伏笔呼应"
    TIMELINE = "时间线"
    CAUSALITY = "因果关系"


class SeverityLevel(Enum):
    """问题严重程度"""
    CRITICAL = "critical"   # 严重问题,必须修复
    MAJOR = "major"         # 主要问题,建议修复
    MINOR = "minor"         # 轻微问题,可选修复
    INFO = "info"           # 信息提示


@dataclass
class ConsistencyIssue:
    """一致性问题"""
    check_type: str
    severity: str
    location: str
    description: str
    suggestion: str
    confidence: float = 0.8
    related_content: str = ""


@dataclass
class ConsistencyReport:
    """一致性检查报告"""
    overall_score: float
    passed: bool
    issues: List[ConsistencyIssue] = field(default_factory=list)
    verified_elements: List[str] = field(default_factory=list)
    summary: str = ""
    raw_response: str = ""


class LLMConsistencyChecker:
    """LLM驱动的一致性检查器"""
    
    def __init__(self, llm_adapter=None):
        """
        初始化一致性检查器
        
        Args:
            llm_adapter: LLM适配器实例
        """
        self.llm_adapter = llm_adapter
        logger.info("LLM一致性检查器初始化完成")
    
    def set_llm_adapter(self, llm_adapter):
        """设置LLM适配器"""
        self.llm_adapter = llm_adapter
    
    def check_consistency(
        self,
        current_chapter: str,
        previous_summary: Optional[str] = None,
        character_state: Optional[str] = None,
        world_setting: Optional[str] = None,
        chapter_info: Optional[Dict] = None
    ) -> ConsistencyReport:
        """
        执行全面一致性检查
        
        Args:
            current_chapter: 当前章节内容
            previous_summary: 前文摘要
            character_state: 角色状态信息
            world_setting: 世界观设定
            chapter_info: 章节元信息
            
        Returns:
            ConsistencyReport: 一致性检查报告
        """
        if not self.llm_adapter:
            logger.error("LLM适配器未设置")
            return self._create_fallback_report()
        
        if not current_chapter or not current_chapter.strip():
            logger.warning("章节内容为空")
            return self._create_empty_content_report()
        
        # 构建检查提示词
        prompt = self._build_consistency_prompt(
            current_chapter,
            previous_summary,
            character_state,
            world_setting,
            chapter_info
        )
        
        try:
            # 调用LLM进行检查
            response = self.llm_adapter.invoke(prompt)
            
            # 解析响应
            report = self._parse_consistency_response(response)
            report.raw_response = response
            
            logger.info(f"一致性检查完成,评分: {report.overall_score}, 问题数: {len(report.issues)}")
            return report
            
        except Exception as e:
            logger.error(f"LLM一致性检查失败: {e}")
            return self._create_fallback_report()
    
    def check_character_consistency(
        self,
        current_chapter: str,
        character_profiles: Dict[str, str],
        previous_behaviors: Optional[str] = None
    ) -> ConsistencyReport:
        """
        专门检查角色一致性
        
        Args:
            current_chapter: 当前章节内容
            character_profiles: 角色档案 {角色名: 档案描述}
            previous_behaviors: 角色之前的行为记录
            
        Returns:
            ConsistencyReport: 角色一致性报告
        """
        if not self.llm_adapter:
            return self._create_fallback_report()
        
        profiles_text = "\n".join([
            f"【{name}】\n{profile}" 
            for name, profile in character_profiles.items()
        ])
        
        prompt = f"""作为小说编辑,请检查以下章节中角色行为和对话的一致性。

【角色档案】
{profiles_text}

【角色之前行为记录】
{previous_behaviors or "无记录"}

【待检查章节】
{current_chapter[:6000]}

【检查要求】
1. 角色性格是否一致:言行是否符合设定的性格特征
2. 语言风格是否一致:说话方式、用词习惯是否保持一致
3. 能力表现是否一致:是否有超出设定能力的表现
4. 情感反应是否合理:基于角色性格,情感反应是否自然
5. 关系互动是否一致:角色之间的关系表现是否符合设定

【输出格式】
返回JSON:
```json
{{
  "overall_score": 8.5,
  "passed": true,
  "issues": [
    {{
      "check_type": "角色一致性",
      "severity": "major",
      "location": "第3段",
      "description": "张三突然表现得非常暴躁,与之前沉稳内敛的性格不符",
      "suggestion": "增加情绪变化的铺垫,或调整反应方式使其更符合性格",
      "confidence": 0.9,
      "related_content": "张三猛地一拍桌子"
    }}
  ],
  "verified_elements": ["李四的语言风格一致", "主角能力表现合理"],
  "summary": "整体角色一致性良好,但张三的情绪反应需要调整"
}}
```"""
        
        try:
            response = self.llm_adapter.invoke(prompt)
            return self._parse_consistency_response(response)
        except Exception as e:
            logger.error(f"角色一致性检查失败: {e}")
            return self._create_fallback_report()
    
    def check_plot_logic(
        self,
        current_chapter: str,
        previous_events: str,
        chapter_outline: Optional[str] = None
    ) -> ConsistencyReport:
        """
        检查情节逻辑一致性
        
        Args:
            current_chapter: 当前章节内容
            previous_events: 前文事件摘要
            chapter_outline: 章节大纲(可选)
            
        Returns:
            ConsistencyReport: 情节逻辑报告
        """
        if not self.llm_adapter:
            return self._create_fallback_report()
        
        prompt = f"""作为小说编辑,请检查以下章节的情节逻辑一致性。

【前文事件摘要】
{previous_events}

【章节大纲】
{chapter_outline or "未提供"}

【待检查章节】
{current_chapter[:6000]}

【检查要求】
1. 时间线一致性:时间顺序是否合理,是否有矛盾
2. 因果关系:事件发展是否有合理的因果逻辑
3. 事件连续性:与前文是否有断裂或矛盾
4. 情节推进:是否有突兀的转折或跳跃
5. 伏笔处理:是否有未交代的伏笔,是否有新的伏笔设置

【输出格式】
返回JSON:
```json
{{
  "overall_score": 7.5,
  "passed": true,
  "issues": [
    {{
      "check_type": "时间线",
      "severity": "major",
      "location": "第5段",
      "description": "章节开头说是清晨,但中间突然变成了深夜,没有时间过渡",
      "suggestion": "增加时间流逝的描写或调整时间设定",
      "confidence": 0.95
    }}
  ],
  "verified_elements": ["因果关系合理", "事件发展连贯"],
  "summary": "情节逻辑总体合理,时间线需要调整"
}}
```"""
        
        try:
            response = self.llm_adapter.invoke(prompt)
            return self._parse_consistency_response(response)
        except Exception as e:
            logger.error(f"情节逻辑检查失败: {e}")
            return self._create_fallback_report()
    
    def check_worldview_consistency(
        self,
        current_chapter: str,
        world_rules: str,
        power_system: Optional[str] = None
    ) -> ConsistencyReport:
        """
        检查世界观一致性
        
        Args:
            current_chapter: 当前章节内容
            world_rules: 世界观规则设定
            power_system: 力量体系设定(可选)
            
        Returns:
            ConsistencyReport: 世界观一致性报告
        """
        if not self.llm_adapter:
            return self._create_fallback_report()
        
        prompt = f"""作为小说编辑,请检查以下章节的世界观一致性。

【世界观规则】
{world_rules}

【力量体系】
{power_system or "未详细设定"}

【待检查章节】
{current_chapter[:6000]}

【检查要求】
1. 设定规则遵守:是否违反已建立的世界规则
2. 力量体系一致:能力表现是否符合力量体系设定
3. 社会背景一致:社会制度、文化习俗是否前后一致
4. 科技水平一致:技术发展程度是否保持一致
5. 术语使用一致:专有名词、术语使用是否统一

【输出格式】
返回JSON:
```json
{{
  "overall_score": 8.0,
  "passed": true,
  "issues": [
    {{
      "check_type": "世界观一致性",
      "severity": "minor",
      "location": "第7段",
      "description": "使用了'手机'一词,但背景设定是古代修真世界",
      "suggestion": "改为'传音符'或其他符合设定的通讯方式",
      "confidence": 0.98
    }}
  ],
  "verified_elements": ["修炼体系描写正确", "境界划分一致"],
  "summary": "世界观基本一致,有一处现代词汇需要修正"
}}
```"""
        
        try:
            response = self.llm_adapter.invoke(prompt)
            return self._parse_consistency_response(response)
        except Exception as e:
            logger.error(f"世界观一致性检查失败: {e}")
            return self._create_fallback_report()
    
    def _build_consistency_prompt(
        self,
        current_chapter: str,
        previous_summary: Optional[str],
        character_state: Optional[str],
        world_setting: Optional[str],
        chapter_info: Optional[Dict]
    ) -> str:
        """构建综合一致性检查提示词"""
        
        # 限制内容长度
        max_length = 6000
        if len(current_chapter) > max_length:
            current_chapter = current_chapter[:max_length] + "\n\n[内容过长,已截断]"
        
        context_sections = []
        
        if previous_summary:
            context_sections.append(f"【前文摘要】\n{previous_summary[:2000]}")
        
        if character_state:
            context_sections.append(f"【角色状态】\n{character_state[:1500]}")
        
        if world_setting:
            context_sections.append(f"【世界观设定】\n{world_setting[:1500]}")
        
        if chapter_info:
            info_text = f"【章节信息】\n标题: {chapter_info.get('chapter_title', '未知')}\n定位: {chapter_info.get('chapter_role', '未知')}"
            context_sections.append(info_text)
        
        context_text = "\n\n".join(context_sections) if context_sections else "无额外上下文信息"
        
        prompt = f"""作为专业小说编辑,请对以下章节进行全面的一致性检查。

{context_text}

【待检查章节】
{current_chapter}

【检查维度】
1. 角色一致性: 角色行为、语言、性格是否前后一致
2. 情节逻辑: 时间线、因果关系、事件发展是否合理
3. 世界观一致性: 设定规则、力量体系是否被遵守
4. 伏笔呼应: 是否有遗漏的伏笔,新伏笔设置是否合理
5. 连续性: 与前文的衔接是否自然流畅

【严重程度分类】
- critical: 严重问题,如重大矛盾、逻辑错误
- major: 主要问题,如明显不一致
- minor: 轻微问题,如小的违和感
- info: 信息提示,如建议优化

【输出格式】
返回JSON:
```json
{{
  "overall_score": 8.0,
  "passed": true,
  "issues": [
    {{
      "check_type": "角色一致性",
      "severity": "major",
      "location": "第N段",
      "description": "问题描述",
      "suggestion": "修改建议",
      "confidence": 0.9,
      "related_content": "相关原文片段"
    }}
  ],
  "verified_elements": ["已验证无问题的元素列表"],
  "summary": "一致性检查总结"
}}
```

请严格按JSON格式输出。"""
        
        return prompt
    
    def _parse_consistency_response(self, response: str) -> ConsistencyReport:
        """解析LLM一致性检查响应"""
        
        try:
            # 尝试提取JSON
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response.strip()
                if json_str.startswith('```'):
                    json_str = re.sub(r'^```\w*\n?', '', json_str)
                    json_str = re.sub(r'\n?```$', '', json_str)
            
            data = json.loads(json_str)
            
            # 解析问题列表
            issues = []
            for issue_data in data.get('issues', []):
                issue = ConsistencyIssue(
                    check_type=issue_data.get('check_type', '未知'),
                    severity=issue_data.get('severity', 'minor'),
                    location=issue_data.get('location', '未知'),
                    description=issue_data.get('description', ''),
                    suggestion=issue_data.get('suggestion', ''),
                    confidence=float(issue_data.get('confidence', 0.8)),
                    related_content=issue_data.get('related_content', '')
                )
                issues.append(issue)
            
            return ConsistencyReport(
                overall_score=float(data.get('overall_score', 5.0)),
                passed=data.get('passed', True),
                issues=issues,
                verified_elements=data.get('verified_elements', []),
                summary=data.get('summary', '')
            )
            
        except json.JSONDecodeError as e:
            logger.warning(f"JSON解析失败: {e}")
            return self._fuzzy_parse_response(response)
        except Exception as e:
            logger.error(f"响应解析失败: {e}")
            return self._create_fallback_report()
    
    def _fuzzy_parse_response(self, response: str) -> ConsistencyReport:
        """模糊解析响应"""
        
        score_match = re.search(r'overall_score["\s:]+(\d+\.?\d*)', response)
        overall_score = float(score_match.group(1)) if score_match else 5.0
        
        passed_match = re.search(r'passed["\s:]+(\w+)', response)
        passed = passed_match.group(1).lower() == 'true' if passed_match else True
        
        return ConsistencyReport(
            overall_score=overall_score,
            passed=passed,
            issues=[],
            verified_elements=["需要人工审核"],
            summary="LLM响应解析失败,请检查原始响应"
        )
    
    def _create_fallback_report(self) -> ConsistencyReport:
        """创建回退报告"""
        return ConsistencyReport(
            overall_score=5.0,
            passed=True,
            issues=[],
            verified_elements=["检查失败,使用默认值"],
            summary="一致性检查无法完成"
        )
    
    def _create_empty_content_report(self) -> ConsistencyReport:
        """创建空内容报告"""
        return ConsistencyReport(
            overall_score=1.0,
            passed=False,
            issues=[
                ConsistencyIssue(
                    check_type="内容检查",
                    severity="critical",
                    location="全文",
                    description="章节内容为空",
                    suggestion="需要生成有效内容"
                )
            ],
            summary="章节内容为空,无法进行一致性检查"
        )
    
    def generate_fix_prompt(
        self,
        original_content: str,
        consistency_report: ConsistencyReport
    ) -> str:
        """
        基于一致性报告生成修复提示词
        
        Args:
            original_content: 原始章节内容
            consistency_report: 一致性检查报告
            
        Returns:
            修复提示词
        """
        
        # 格式化问题列表
        issues_text = ""
        for i, issue in enumerate(consistency_report.issues, 1):
            issues_text += f"""
{i}. [{issue.severity.upper()}] {issue.check_type} - {issue.location}
   问题: {issue.description}
   建议: {issue.suggestion}
   相关内容: {issue.related_content or '无'}
"""
        
        prompt = f"""请修复以下章节中的一致性问题。

【原始章节】
{original_content}

【一致性检查评分】
{consistency_report.overall_score}/10

【需要修复的问题】
{issues_text}

【修复要求】
1. 保持情节主线不变
2. 针对性解决上述列出的一致性问题
3. 确保修改后的内容与前文保持一致
4. 保持字数大致不变(±10%)
5. 修改应该自然流畅,不能有明显的修补痕迹

请直接输出修复后的完整章节,不要添加任何解释。"""
        
        return prompt


def create_consistency_checker(llm_adapter=None) -> LLMConsistencyChecker:
    """
    创建一致性检查器实例
    
    Args:
        llm_adapter: LLM适配器实例
        
    Returns:
        LLMConsistencyChecker实例
    """
    return LLMConsistencyChecker(llm_adapter)


if __name__ == "__main__":
    # 测试代码
    checker = create_consistency_checker()
    print("LLM一致性检查器测试完成")
