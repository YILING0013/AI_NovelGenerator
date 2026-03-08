#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

class QualityLevel(Enum):
    EXCELLENT = "Excellent"   # 90-100
    GOOD = "Good"             # 80-89
    FAIR = "Fair"             # 70-79
    POOR = "Poor"             # 60-69
    UNACCEPTABLE = "Unacceptable" # <60

@dataclass
class QualityIssue:
    description: str
    category: QualityLevel
    severity: str = "medium"

@dataclass
class QualityReport:
    chapter_number: int
    chapter_title: str
    overall_score: float
    quality_level: QualityLevel
    metrics: List[Dict[str, Any]]
    issues: List[QualityIssue] = field(default_factory=list)

class QualityChecker:
    """
    章节质量检查器 - 增强版
    """
    
    # 核心模块关键词（与 Step2 七节模板对齐）
    # 说明：每个模块命中任一关键词即视为覆盖，避免旧模板关键词导致误判低分。
    REQUIRED_MODULE_PATTERNS = {
        "基础元信息": ["## 1. 基础元信息", "基础元信息", "章节序号", "字数目标", "出场角色"],
        "张力与冲突": ["## 2. 张力与冲突", "张力与冲突", "冲突类型", "核心冲突点", "紧张感曲线"],
        "匠心思维应用": ["## 3. 匠心思维应用", "匠心思维应用", "应用场景", "思维模式", "视觉化描述", "经典台词"],
        "伏笔与信息差": ["## 4. 伏笔与信息差", "伏笔与信息差", "本章植入伏笔", "本章回收伏笔", "信息差控制"],
        "暧昧与修罗场": ["## 5. 暧昧与修罗场", "暧昧与修罗场", "涉及的女性角色互动", "本章不涉及女性角色互动"],
        "剧情精要": ["## 6. 剧情精要", "剧情精要", "开场", "发展", "高潮", "收尾"],
        "衔接设计": ["## 7. 衔接设计", "衔接设计", "承上", "转场", "启下"],
    }
    
    # 可选增强模块（命中用于加分，不命中不应严重拉低）
    OPTIONAL_MODULE_PATTERNS = {
        "系统机制线索": ["系统机制变化", "命轨", "天书", "权限", "代价", "规则"],
        "知识库锚点": ["知识库引用", "世界观锚点", "世界观", "王朝", "宗门", "秘境"],
        "技法运用": ["技法运用", "视觉化描述", "经典台词", "镜头语言", "错误写法", "正确写法"],
    }
    
    # 🆕 双轨叙事检查：外轨禁用的技术术语（程序员隐喻）
    EXTERNAL_TRACK_BLACKLIST = [
        "蓝屏", "Debug", "SQL注入", "DDoS", "缓冲区溢出", "堆栈溢出", "死循环",
        "防火墙", "病毒", "木马", "后门", "内存溢出", "多线程", "并发", "算法",
        "CPU", "GPU", "IO", "API", "SDK", "数据库", "服务器", "客户端",
        "编译", "解析", "加密", "解密", "二进制", "十六进制", "哈希值",
        "逻辑死锁", "逻辑漏洞", "代码", "源码", "脚本", "Bug", "Patch",
    ]
    
    # 🆕 黄金三章配置（前3章需要更高的钩子密度）
    GOLDEN_THREE_CHAPTERS = [1, 2, 3]
    GOLDEN_THREE_HOOK_KEYWORDS = [
        "悬念", "钩子", "反转", "冲突", "危机", "命悬一线", "生死", "秘密",
        "震撼", "惊人", "意外", "绝境", "逆转", "爽点", "爆发",
    ]
    
    def __init__(self, filepath: str = None):
        """
        初始化质量检查器
        
        Args:
            filepath: 项目路径，用于加载架构文件进行一致性检查
        """
        self.filepath = filepath
        self.architecture_parser = None
        self.architecture_data = None
        
        if filepath:
            try:
                from novel_generator.architecture_parser import ArchitectureParser
                self.architecture_parser = ArchitectureParser(filepath)
                self.architecture_data = self.architecture_parser.parse()
            except Exception as e:
                import logging
                logging.warning(f"Failed to load architecture: {e}")

    def check_chapter_quality(self, content: str, chapter_info: Dict[str, Any], blueprint_text: Optional[str] = None) -> QualityReport:
        """
        检查章节质量，返回详细报告
        """
        metrics = []
        issues = []
        
        # 1. 字数检查 (权重 20%)
        word_count = len(content)
        target_min = 2000
        target_max = 8000
        
        if word_count < target_min:
            score_length = max(0, 100 - (target_min - word_count) / 20)
            issues.append(QualityIssue(
                f"蓝图字数不足: {word_count}字 (建议≥{target_min}字)",
                QualityLevel.FAIR, "high"
            ))
        elif word_count > target_max:
            score_length = max(70, 100 - (word_count - target_max) / 50)
            issues.append(QualityIssue(
                f"蓝图字数过多: {word_count}字 (建议≤{target_max}字)",
                QualityLevel.GOOD, "low"
            ))
        else:
            score_length = 100

        metrics.append({
            'name': '字数达标率',
            'score': score_length,
            'weight': 0.2,
            'description': f'当前字数: {word_count}'
        })

        # 2. 核心模块完整性 (权重 40%) - 使用关键词模糊匹配
        found_required = []
        missing_required = []
        for module_name, keywords in self.REQUIRED_MODULE_PATTERNS.items():
            # 只要内容中包含任一关键词，即视为该模块存在
            if any(kw in content for kw in keywords):
                found_required.append(module_name)
            else:
                missing_required.append(module_name)
        
        total_required = len(self.REQUIRED_MODULE_PATTERNS)
        required_ratio = len(found_required) / total_required
        score_required = required_ratio * 100
        
        if missing_required:
            issues.append(QualityIssue(
                f"缺失核心模块({len(missing_required)}个): {', '.join(missing_required[:3])}{'...' if len(missing_required) > 3 else ''}",
                QualityLevel.POOR, "critical"
            ))
        
        metrics.append({
            'name': '核心模块完整性',
            'score': score_required,
            'weight': 0.4,
            'description': f'找到 {len(found_required)}/{total_required} 个核心模块'
        })

        # 3. 可选模块检查 (权重 12%)
        found_optional = []
        missing_optional = []
        for module_name, keywords in self.OPTIONAL_MODULE_PATTERNS.items():
            if any(kw in content for kw in keywords):
                found_optional.append(module_name)
            else:
                missing_optional.append(module_name)
        
        total_optional = len(self.OPTIONAL_MODULE_PATTERNS)
        score_optional = (len(found_optional) / total_optional) * 100 if total_optional > 0 else 100
        
        if missing_optional:
            issues.append(QualityIssue(
                f"缺失增强模块: {', '.join(missing_optional)}",
                QualityLevel.FAIR, "medium"
            ))
        
        metrics.append({
            'name': '增强模块',
            'score': score_optional,
            'weight': 0.12,
            'description': f'找到 {len(found_optional)}/{total_optional} 个增强模块'
        })

        # 4. 格式规范性 (权重 15%)
        has_all_required_sections = all(
            re.search(rf"(?m)^\s*##\s*{sec_num}\.\s*{re.escape(sec_name)}\s*$", content) is not None
            for sec_num, sec_name in [
                (1, "基础元信息"),
                (2, "张力与冲突"),
                (3, "匠心思维应用"),
                (4, "伏笔与信息差"),
                (5, "暧昧与修罗场"),
                (6, "剧情精要"),
                (7, "衔接设计"),
            ]
        )
        format_checks = {
            '章节标题': bool(re.search(r"(?m)^\s*第\s*\d+\s*章(?:\s*[-–—:：].+)?$", content)),
            '字数目标': bool(
                re.search(
                    r"字数目标[：:]\s*(?:\d{3,5}\s*[-~—–至到]\s*\d{3,5}\s*字|\d{3,5}\s*字)",
                    content,
                )
            ),
            '7节结构': has_all_required_sections,
        }
        format_score = sum(format_checks.values()) / len(format_checks) * 100

        # 张力评级为建议项：命中给加分，不命中只给轻提醒（不记为格式缺失）
        has_tension_rating = bool(
            re.search(
                r"(?:张力评级[：:].+|[★☆]{1,5}|[A-S]级)",
                content,
            )
        )
        if has_tension_rating:
            format_score = min(100, format_score + 8)
        else:
            issues.append(QualityIssue(
                "建议补充: 张力评级（如 S/A/B/C 或 ★1-★5）",
                QualityLevel.GOOD, "low"
            ))
        
        failed_formats = [k for k, v in format_checks.items() if not v]
        if failed_formats:
            issues.append(QualityIssue(
                f"格式缺失: {', '.join(failed_formats)}",
                QualityLevel.FAIR, "medium"
            ))

        # 定位占位符检测（第X卷/子幕X/待定）
        location_match = re.search(r"定位[：:]\s*(.+)", content)
        location_text = location_match.group(1).strip() if location_match else ""
        location_placeholder_tokens = []
        location_checks = [
            ("第X卷", r"第\s*[XxＸｘ]\s*卷"),
            ("子幕X", r"子幕\s*[XxＸｘ]"),
            ("卷名待定", r"卷名\s*待定"),
            ("待定", r"(?:\[|\(|（)?\s*待定\s*(?:\]|\)|）)?"),
        ]
        for token, pattern in location_checks:
            if re.search(pattern, location_text, flags=re.IGNORECASE):
                location_placeholder_tokens.append(token)
        if location_placeholder_tokens:
            issues.append(QualityIssue(
                "定位字段疑似占位符: " + "、".join(location_placeholder_tokens),
                QualityLevel.POOR,
                "high",
            ))
            format_score = max(0.0, format_score - 25.0)
        
        metrics.append({
            'name': '格式规范性',
            'score': format_score,
            'weight': 0.15,
            'description': f'通过 {sum(format_checks.values())}/{len(format_checks)} 项格式检查'
        })

        # 5. 内容丰富度 (权重 10%)
        richness_indicators = {
            '情感关键词': len(re.findall(r"情感|情绪|心理|内心|暧昧|修罗场", content)),
            '冲突关键词': len(re.findall(r"冲突|对抗|矛盾|张力|危机|反杀|博弈", content)),
            '推进关键词': len(re.findall(r"伏笔|铺垫|暗示|线索|开场|发展|高潮|收尾|承上|转场|启下", content)),
        }
        total_richness = sum(richness_indicators.values())
        richness_score = min(100, total_richness * 6)
        
        if richness_score < 50:
            issues.append(QualityIssue(
                f"内容深度不足: 关键词密度偏低({total_richness}个)",
                QualityLevel.FAIR, "low"
            ))
        
        metrics.append({
            'name': '内容丰富度',
            'score': richness_score,
            'weight': 0.05,  # 降低权重
            'description': f'关键词密度: {total_richness}'
        })

        # 6. 架构一致性检查 (权重 15%)
        arch_score = 100
        if self.architecture_parser and self.architecture_data:
            chapter_number = chapter_info.get('chapter_number', 0)
            arch_result = self.architecture_parser.validate_chapter_against_architecture(
                chapter_number, content
            )
            arch_score = arch_result.get('score', 100)
            arch_issues = arch_result.get('issues', [])
            
            for issue_desc in arch_issues[:3]:  # 最多报告3个架构问题
                issues.append(QualityIssue(
                    f"架构偏离: {issue_desc}",
                    QualityLevel.POOR, "high"
                ))
            
            metrics.append({
                'name': '架构一致性',
                'score': arch_score,
                'weight': 0.15,
                'description': f'与架构匹配度: {arch_score:.0f}%'
            })
        else:
            # 无架构文件时跳过此维度
            metrics.append({
                'name': '架构一致性',
                'score': 100,
                'weight': 0.0,  # 无权重
                'description': '未加载架构文件'
            })

        # 🆕 7. 双轨叙事检查 (权重 8%) - 检测外轨叙事中的技术隐喻
        external_track_violations = []
        for term in self.EXTERNAL_TRACK_BLACKLIST:
            if term.lower() in content.lower():
                # 检查是否出现在蓝图的"外轨"描述中（排除"内轨"、"系统界面"、"内心独白"等上下文）
                # 简化处理：直接检测是否在"视觉化描述"、"开场"、"发展"等外轨区域
                external_track_violations.append(term)
        
        dual_track_score = max(0, 100 - len(external_track_violations) * 8)
        if external_track_violations:
            severity = "high" if len(external_track_violations) >= 5 else "medium"
            issues.append(QualityIssue(
                f"双轨叙事违规: 外轨发现技术术语 [{', '.join(external_track_violations[:5])}]",
                QualityLevel.POOR, severity
            ))
        
        metrics.append({
            'name': '双轨叙事合规',
            'score': dual_track_score,
            'weight': 0.08,
            'description': f'发现 {len(external_track_violations)} 个外轨违规术语'
        })

        # 🆕 8. 黄金三章增强检查 (权重 5%，仅前3章生效)
        chapter_number = chapter_info.get('chapter_number', 0)
        if chapter_number in self.GOLDEN_THREE_CHAPTERS:
            hook_count = sum(1 for kw in self.GOLDEN_THREE_HOOK_KEYWORDS if kw in content)
            golden_score = min(100, hook_count * 12)  # 每个钩子关键词12分
            
            if hook_count < 5:
                issues.append(QualityIssue(
                    f"黄金三章钩子不足: 仅找到 {hook_count} 个钩子关键词 (建议≥5)",
                    QualityLevel.FAIR, "medium"
                ))
            
            metrics.append({
                'name': '黄金三章钩子密度',
                'score': golden_score,
                'weight': 0.05,
                'description': f'第{chapter_number}章钩子关键词: {hook_count}个'
            })
        else:
            # 非黄金三章，跳过此维度
            metrics.append({
                'name': '黄金三章钩子密度',
                'score': 100,
                'weight': 0.0,
                'description': f'非黄金三章(第{chapter_number}章)'
            })

        # 9. 子分：结构合规 / 叙事语义（仅展示，不参与总分）
        structure_metric_names = [
            '字数达标率',
            '核心模块完整性',
            '格式规范性',
        ]
        semantic_metric_names = [
            '增强模块',
            '内容丰富度',
            '架构一致性',
            '双轨叙事合规',
            '黄金三章钩子密度',
        ]
        structure_score = self._calculate_metric_group_score(metrics, structure_metric_names)
        semantic_score = self._calculate_metric_group_score(metrics, semantic_metric_names)
        metrics.append({
            'name': '子分-结构合规',
            'score': structure_score,
            'weight': 0.0,
            'description': '由字数达标率/核心模块完整性/格式规范性加权得到'
        })
        metrics.append({
            'name': '子分-叙事语义',
            'score': semantic_score,
            'weight': 0.0,
            'description': '由增强模块/内容丰富度/架构一致性/双轨叙事/黄金三章加权得到'
        })

        # 计算总分
        overall_score = self._calculate_overall_score(metrics)
        overall_score = self._apply_issue_based_score_caps(overall_score, issues)
        quality_level = self._determine_quality_level(overall_score)

        return QualityReport(
            chapter_number=chapter_info.get('chapter_number', 0),
            chapter_title=chapter_info.get('chapter_title', 'Unknown'),
            overall_score=overall_score,
            quality_level=quality_level,
            metrics=metrics,
            issues=issues
        )

    def get_issue_summary(self, report: QualityReport) -> str:
        """
        生成问题摘要字符串
        """
        if not report.issues:
            return "无明显问题"
        
        critical = [i for i in report.issues if i.severity == "critical"]
        high = [i for i in report.issues if i.severity == "high"]
        
        summary_parts = []
        if critical:
            summary_parts.append(f"严重问题({len(critical)})")
        if high:
            summary_parts.append(f"重要问题({len(high)})")
        
        return "; ".join(summary_parts) if summary_parts else f"轻微问题({len(report.issues)})"

    def _calculate_metric_group_score(self, metrics: List[Dict[str, Any]], metric_names: List[str]) -> float:
        """
        计算指定指标组的加权得分。
        - 仅统计 name 在 metric_names 中的指标；
        - weight<=0 的指标忽略；
        - 若无有效指标，返回 0。
        """
        target_names = {str(name) for name in metric_names}
        total_score = 0.0
        total_weight = 0.0
        for metric in metrics:
            name = str(metric.get('name', ''))
            if name not in target_names:
                continue
            weight = float(metric.get('weight', 0.0) or 0.0)
            if weight <= 0:
                continue
            score = float(metric.get('score', 0.0) or 0.0)
            total_score += score * weight
            total_weight += weight

        if total_weight <= 0:
            return 0.0
        return total_score / total_weight

    def _apply_issue_based_score_caps(self, raw_score: float, issues: List[QualityIssue]) -> float:
        """
        问题驱动的分数上限：
        - 关键结构占位问题不能拿高分；
        - 双轨叙事违规不能维持“接近满分”的假高分；
        - 严重级问题限制总分区间。
        """
        score = float(raw_score)
        caps = [100.0]

        issue_descriptions = [str(issue.description) for issue in issues]
        severities = [str(issue.severity).lower() for issue in issues]

        if any("定位字段疑似占位符" in desc or "定位含占位符" in desc for desc in issue_descriptions):
            caps.append(82.0)

        if any("双轨叙事违规" in desc for desc in issue_descriptions):
            caps.append(88.0)

        if any(sev == "critical" for sev in severities):
            caps.append(79.0)
        elif any(sev == "high" for sev in severities):
            caps.append(89.0)

        return min(score, min(caps))

    def _calculate_overall_score(self, metrics: List[Dict[str, Any]]) -> float:
        total_score = 0
        total_weight = 0
        for m in metrics:
            total_score += m['score'] * m.get('weight', 1.0)
            total_weight += m.get('weight', 1.0)
        
        if total_weight == 0:
            return 0
        return total_score / total_weight

    def _determine_quality_level(self, score: float) -> QualityLevel:
        if score >= 90: return QualityLevel.EXCELLENT
        if score >= 80: return QualityLevel.GOOD
        if score >= 70: return QualityLevel.FAIR
        if score >= 60: return QualityLevel.POOR
        return QualityLevel.UNACCEPTABLE

