"""
二次生成校验模块 (P2优化)

功能：
1. 生成后自动校验（去重、修为、风格）
2. 发现问题时生成针对性重写Prompt
3. 局部重写问题段落
4. 合并生成终稿
"""

import re
import logging
from typing import Dict, List, Tuple, Optional, Callable

# 导入依赖模块
try:
    from novel_generator.finalization import check_chapter_similarity
    DEDUP_AVAILABLE = True
except ImportError:
    DEDUP_AVAILABLE = False

try:
    from prompt_definitions import CULTIVATION_PROGRESS_MAP, BATTLE_STYLE_POOL
    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False
    CULTIVATION_PROGRESS_MAP = {}
    BATTLE_STYLE_POOL = []


class ChapterValidator:
    """章节内容校验器"""
    
    # 修为相关关键词
    REALM_KEYWORDS = {
        "后天初期": ["后天初期", "后天一层", "初入修炼"],
        "后天中期": ["后天中期", "后天二层", "后天三层"],
        "后天后期": ["后天后期", "后天四层", "后天五层"],
        "后天大圆满": ["后天大圆满", "后天巅峰", "后天圆满"],
        "先天一重": ["先天一重", "先天初期", "踏入先天"],
        "先天二重": ["先天二重", "先天中期"],
        "先天三重": ["先天三重", "先天后期"],
        "先天大圆满": ["先天大圆满", "先天巅峰"]
    }
    
    # 突破描写关键词
    BREAKTHROUGH_PATTERNS = [
        r"修为.*?突破",
        r"境界.*?提升",
        r"踏入.*?境",
        r"晋升.*?期",
        r"成功.*?进阶",
        r"实力.*?暴涨"
    ]
    
    def __init__(self, chapter_num: int, expected_realm: str = None):
        self.chapter_num = chapter_num
        self.expected_realm = expected_realm
        self.issues: List[Dict] = []
    
    def validate_realm_consistency(self, content: str) -> List[Dict]:
        """
        校验修为一致性
        
        Args:
            content: 章节内容
            
        Returns:
            问题列表
        """
        issues = []
        
        if not self.expected_realm:
            return issues
        
        # 检测实际描写的修为
        detected_realms = []
        for realm, keywords in self.REALM_KEYWORDS.items():
            for keyword in keywords:
                if keyword in content:
                    detected_realms.append(realm)
                    break
        
        # 检查是否有超出预期的修为描写
        expected_level = self._get_realm_level(self.expected_realm)
        for realm in detected_realms:
            realm_level = self._get_realm_level(realm)
            if realm_level > expected_level + 1:  # 允许一级缓冲
                # 找到具体位置
                for keyword in self.REALM_KEYWORDS.get(realm, []):
                    if keyword in content:
                        idx = content.find(keyword)
                        context = content[max(0, idx-50):idx+50]
                        issues.append({
                            "type": "realm_overflow",
                            "severity": "high",
                            "description": f"修为描写超标：出现'{realm}'，预期'{self.expected_realm}'",
                            "location": idx,
                            "context": context,
                            "suggestion": f"将'{realm}'替换为'{self.expected_realm}'或移除该描写"
                        })
                        break
        
        # 检测是否有不当的突破描写
        for pattern in self.BREAKTHROUGH_PATTERNS:
            matches = re.finditer(pattern, content)
            for match in matches:
                idx = match.start()
                context = content[max(0, idx-30):idx+50]
                issues.append({
                    "type": "unexpected_breakthrough",
                    "severity": "medium",
                    "description": f"检测到突破描写：'{match.group()}'",
                    "location": idx,
                    "context": context,
                    "suggestion": "如非突破章节，建议改为'感悟瓶颈'或'积累修为'"
                })
        
        return issues
    
    def validate_battle_style(self, content: str, expected_style: str = None) -> List[Dict]:
        """
        校验战斗风格
        
        Args:
            content: 章节内容
            expected_style: 预期的战斗风格
            
        Returns:
            问题列表
        """
        issues = []
        
        if not expected_style:
            return issues
        
        # 风格关键词映射
        style_keywords = {
            "正面硬刚": ["正面对决", "硬碰硬", "力量压制", "一拳", "轰出"],
            "以巧破力": ["巧妙避开", "侧身", "借力", "灵活", "闪避"],
            "团队协作": ["配合", "联手", "协同", "掩护", "支援"],
            "智谋取胜": ["计谋", "布局", "诱敌", "陷阱", "算计"],
            "绝地反击": ["濒死", "爆发", "逆转", "背水一战", "险胜"]
        }
        
        # 检测实际风格
        detected_styles = []
        for style, keywords in style_keywords.items():
            match_count = sum(1 for k in keywords if k in content)
            if match_count >= 2:
                detected_styles.append(style)
        
        # 检查是否与预期风格一致
        if expected_style not in detected_styles and detected_styles:
            issues.append({
                "type": "style_mismatch",
                "severity": "low",
                "description": f"战斗风格不符：预期'{expected_style}'，实际'{detected_styles}'",
                "suggestion": f"建议增加'{expected_style}'相关描写"
            })
        
        return issues
    
    def validate_all(self, content: str, prev_content: str = None, 
                     expected_style: str = None) -> Dict:
        """
        执行全面校验
        
        Args:
            content: 当前章节内容
            prev_content: 前一章内容（用于去重检测）
            expected_style: 预期战斗风格
            
        Returns:
            校验结果
        """
        all_issues = []
        
        # 1. 修为一致性校验
        realm_issues = self.validate_realm_consistency(content)
        all_issues.extend(realm_issues)
        
        # 2. 战斗风格校验
        style_issues = self.validate_battle_style(content, expected_style)
        all_issues.extend(style_issues)
        
        # 3. 去重校验
        if DEDUP_AVAILABLE and prev_content:
            try:
                is_similar, score, duplicates = check_chapter_similarity(
                    content, prev_content, threshold=0.15
                )
                if is_similar:
                    all_issues.append({
                        "type": "content_duplication",
                        "severity": "high",
                        "description": f"与前一章相似度过高: {score:.2%}",
                        "duplicates": duplicates[:3],
                        "suggestion": "需要重写重复段落"
                    })
            except Exception as e:
                logging.warning(f"[Validator] 去重检测失败: {e}")
        
        # 生成校验报告
        result = {
            "chapter": self.chapter_num,
            "passed": len([i for i in all_issues if i["severity"] == "high"]) == 0,
            "issues": all_issues,
            "summary": {
                "total_issues": len(all_issues),
                "high_severity": len([i for i in all_issues if i["severity"] == "high"]),
                "medium_severity": len([i for i in all_issues if i["severity"] == "medium"]),
                "low_severity": len([i for i in all_issues if i["severity"] == "low"])
            }
        }
        
        return result
    
    def _get_realm_level(self, realm: str) -> int:
        """获取境界等级数值"""
        realm_order = [
            "后天初期", "后天中期", "后天后期", "后天大圆满",
            "先天一重", "先天二重", "先天三重", "先天大圆满"
        ]
        for i, r in enumerate(realm_order):
            if r in realm or realm in r:
                return i
        return 0


class ContentRewriter:
    """内容重写器"""
    
    def __init__(self, llm_invoke_func: Callable = None):
        """
        初始化重写器
        
        Args:
            llm_invoke_func: LLM调用函数，接收prompt返回生成内容
        """
        self.llm_invoke = llm_invoke_func
    
    def generate_rewrite_prompt(self, issue: Dict, original_content: str) -> str:
        """
        根据问题生成重写Prompt
        
        Args:
            issue: 问题描述
            original_content: 原始内容
            
        Returns:
            重写Prompt
        """
        issue_type = issue.get("type", "unknown")
        context = issue.get("context", "")
        suggestion = issue.get("suggestion", "")
        
        if issue_type == "realm_overflow":
            return f"""请重写以下段落，将其中的修为描写调整为符合要求的级别。

原始段落：
{context}

问题：{issue.get("description", "")}
要求：{suggestion}

只输出重写后的段落，不要加任何解释："""

        elif issue_type == "unexpected_breakthrough":
            return f"""请重写以下段落，将其中的"突破成功"描写改为"感悟瓶颈/积累中"。

原始段落：
{context}

要求：保持情节张力，但将结果改为"尚未突破，仍在积累"。

只输出重写后的段落："""

        elif issue_type == "content_duplication":
            duplicates = issue.get("duplicates", [])
            return f"""以下内容与前一章重复，请完全重写，确保表达方式完全不同。

重复段落：
{chr(10).join(duplicates[:2])}

要求：
1. 保持原有情节信息
2. 使用完全不同的措辞和描写角度
3. 可以适当精简或扩展

只输出重写后的内容："""

        elif issue_type == "style_mismatch":
            expected_style = issue.get("description", "").split("预期'")[1].split("'")[0] if "预期'" in issue.get("description", "") else ""
            return f"""请为以下战斗场景增加"{expected_style}"风格的描写。

原始内容：
{original_content[:500]}...

要求：在保持原有情节的基础上，增加符合"{expected_style}"风格的战斗描写元素。

只输出修改后的战斗段落："""

        return f"请根据以下建议重写内容：{suggestion}"
    
    def rewrite_segment(self, issue: Dict, original_content: str) -> Optional[str]:
        """
        重写问题段落
        
        Args:
            issue: 问题描述
            original_content: 原始内容
            
        Returns:
            重写后的内容，失败返回None
        """
        if not self.llm_invoke:
            logging.warning("[Rewriter] LLM调用函数未配置，无法执行重写")
            return None
        
        prompt = self.generate_rewrite_prompt(issue, original_content)
        
        try:
            rewritten = self.llm_invoke(prompt)
            return rewritten.strip() if rewritten else None
        except Exception as e:
            logging.error(f"[Rewriter] 重写失败: {e}")
            return None


def validate_and_fix_chapter(
    content: str,
    chapter_num: int,
    prev_content: str = None,
    expected_realm: str = None,
    expected_style: str = None,
    llm_invoke_func: Callable = None,
    auto_fix: bool = False
) -> Dict:
    """
    校验并修复章节内容
    
    Args:
        content: 章节内容
        chapter_num: 章节号
        prev_content: 前一章内容
        expected_realm: 预期修为
        expected_style: 预期战斗风格
        llm_invoke_func: LLM调用函数（用于自动修复）
        auto_fix: 是否自动修复
        
    Returns:
        包含校验结果和修复后内容的字典
    """
    # 创建校验器
    validator = ChapterValidator(chapter_num, expected_realm)
    
    # 执行校验
    validation_result = validator.validate_all(content, prev_content, expected_style)
    
    result = {
        "original_content": content,
        "validation": validation_result,
        "fixed_content": content,
        "fixes_applied": []
    }
    
    # 如果启用自动修复且有问题
    if auto_fix and not validation_result["passed"] and llm_invoke_func:
        rewriter = ContentRewriter(llm_invoke_func)
        fixed_content = content
        
        for issue in validation_result["issues"]:
            if issue["severity"] == "high":
                rewritten = rewriter.rewrite_segment(issue, fixed_content)
                if rewritten:
                    # 尝试替换问题段落
                    context = issue.get("context", "")
                    if context and context in fixed_content:
                        fixed_content = fixed_content.replace(context, rewritten)
                        result["fixes_applied"].append({
                            "issue_type": issue["type"],
                            "original": context,
                            "fixed": rewritten
                        })
        
        result["fixed_content"] = fixed_content
    
    return result


# 导出
__all__ = [
    'ChapterValidator',
    'ContentRewriter',
    'validate_and_fix_chapter'
]
