#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量章节质量检查脚本
对wxhyj/Novel_directory.txt中的所有章节进行批量质量检查
"""

import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 导入必要模块
from chapter_directory_parser import parse_chapter_blueprint
from quality_checker import QualityChecker, QualityLevel

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('batch_quality_check.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class BatchQualityChecker:
    """
    批量质量检查器 - 供 UI 调用（增强版）
    """
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.novel_path = Path(filepath) / "Novel_directory.txt"
        self.checker = QualityChecker(filepath)  # 传入路径用于架构一致性检查
    
    def check_all_chapters(self) -> dict:
        """
        检查所有章节质量，返回详细报告
        """
        if not self.novel_path.exists():
            logger.warning(f"Novel_directory.txt not found at {self.novel_path}")
            return None
        
        try:
            chapters = load_novel_directory(str(self.novel_path))
            if not chapters:
                return None
            
            all_reports = []
            low_score_chapters = []
            chapter_details = []  # 详细信息
            
            for chapter in chapters:
                chapter_number = chapter['chapter_number']
                chapter_content = chapter['content']
                
                # 解析章节信息
                try:
                    from chapter_directory_parser import parse_chapter_blueprint
                    chapter_info = parse_chapter_blueprint(chapter_content)
                    chapter_info['chapter_number'] = chapter_number
                except Exception:
                    chapter_info = {
                        'chapter_number': chapter_number,
                        'chapter_title': f'第{chapter_number}章',
                    }
                
                # 质量检查
                try:
                    report = self.checker.check_chapter_quality(
                        chapter_content,
                        chapter_info,
                        blueprint_text=chapter_content
                    )
                    all_reports.append(report)
                    
                    # 收集详细信息
                    detail = {
                        'chapter_number': chapter_number,
                        'score': report.overall_score,
                        'quality_level': report.quality_level.value,
                        'issues': [i.description for i in report.issues],
                        'issue_summary': self.checker.get_issue_summary(report)
                    }
                    chapter_details.append(detail)
                    
                    if report.overall_score < 80:
                        low_score_chapters.append(chapter_number)
                        
                except Exception as e:
                    logger.warning(f"Chapter {chapter_number} quality check failed: {e}")
            
            if not all_reports:
                return None
            
            scores = [r.overall_score for r in all_reports]
            
            # 统计问题分布
            issue_stats = {}
            for report in all_reports:
                for issue in report.issues:
                    key = issue.description.split(':')[0]  # 取问题类型
                    issue_stats[key] = issue_stats.get(key, 0) + 1
            
            # === 章节衔接检查（新增） ===
            coherence_result = None
            try:
                from novel_generator.coherence_checker import CoherenceChecker
                coherence_checker = CoherenceChecker(self.filepath)
                
                # 准备章节数据
                chapter_data = []
                for ch in chapters:
                    content = ch.get('blueprint', ch.get('content', ''))
                    chapter_data.append({
                        'chapter_number': ch.get('chapter_number', 0),
                        'content': content
                    })
                
                if len(chapter_data) >= 2:
                    coherence_result = coherence_checker.check_all_chapters(chapter_data)
            except Exception as ce:
                logger.warning(f"Coherence check failed: {ce}")
            
            # === 架构解析摘要（新增） ===
            arch_summary = None
            try:
                if hasattr(self.checker, 'architecture_parser') and self.checker.architecture_parser:
                    arch_summary = self.checker.architecture_parser.get_parsing_summary()
            except Exception:
                pass
            
            return {
                'total_chapters': len(all_reports),
                'average_score': sum(scores) / len(scores),
                'low_score_chapters': low_score_chapters,
                'chapter_details': chapter_details,
                'issue_statistics': issue_stats,
                'quality_distribution': {
                    'excellent': len([r for r in all_reports if r.overall_score >= 90]),
                    'good': len([r for r in all_reports if 80 <= r.overall_score < 90]),
                    'fair': len([r for r in all_reports if 70 <= r.overall_score < 80]),
                    'poor': len([r for r in all_reports if r.overall_score < 70])
                },
                'coherence_check': coherence_result,
                'architecture_summary': arch_summary
            }
        except Exception as e:
            logger.error(f"Batch quality check failed: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_chapter_issues(self, chapter_number: int) -> list:
        """
        获取指定章节的详细问题列表
        """
        chapters = load_novel_directory(str(self.novel_path))
        for chapter in chapters:
            if chapter['chapter_number'] == chapter_number:
                chapter_info = {'chapter_number': chapter_number}
                report = self.checker.check_chapter_quality(
                    chapter['content'], chapter_info
                )
                return [i.description for i in report.issues]
        return []




def load_novel_directory(file_path: str) -> list:
    """
    加载小说章节目录
    """
    chapters = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 使用正则按 "第X章" 分割内容
        import re
        # 匹配 "第X章" 开头的行作为分割点
        chapter_pattern = r'^(第\d+章\s*[-—]?\s*.*?)(?=^第\d+章|\Z)'
        matches = re.findall(chapter_pattern, content, re.MULTILINE | re.DOTALL)
        
        for section in matches:
            section = section.strip()
            if not section:
                continue

            # 提取章节号
            match = re.search(r'第(\d+)章', section)
            if match:
                chapter_number = int(match.group(1))
                chapters.append({
                    'chapter_number': chapter_number,
                    'content': section
                })

        logger.info(f"成功加载 {len(chapters)} 个章节")
        return chapters

    except Exception as e:
        logger.error(f"加载章节目录失败: {e}")
        return []


def check_chapter_format_compliance(chapter_content: str) -> dict:
    """
    检查章节是否符合模块格式标准（使用关键词模糊匹配）
    """
    # 核心模块的关键词匹配规则（与quality_checker.py保持一致）
    required_module_patterns = {
        "基础元信息": ["基础元信息", "元信息", "章节定位"],
        "张力架构": ["张力架构", "张力设计", "冲突设计", "紧张感"],
        "情感轨迹": ["情感轨迹", "情感工程", "暧昧", "修罗场", "Romance"],
        "核心结构": ["核心结构", "结构矩阵", "情节精要", "情节蓝图"],
        "系统机制": ["系统机制", "系统整合", "数值变化", "权限变更"],
        "悬念体系": ["悬念体系", "伏笔", "信息差", "Foreshadowing"],
        "创作指南": ["创作执行", "创作指南", "质量检查", "Quality"],
        "衔接设计": ["衔接设计", "承上启下", "节奏控制"],
        "理性思维": ["理性思维", "Rationality", "程序员思维", "降维打击"],
    }

    missing_modules = []
    present_modules = []

    for module_name, keywords in required_module_patterns.items():
        # 只要内容中包含任一关键词，即视为该模块存在
        if any(kw in chapter_content for kw in keywords):
            present_modules.append(module_name)
        else:
            missing_modules.append(module_name)

    compliance_score = (len(present_modules) / len(required_module_patterns)) * 100

    return {
        'compliance_score': compliance_score,
        'present_modules': present_modules,
        'missing_modules': missing_modules,
        'is_compliant': len(missing_modules) == 0
    }


def main():
    """
    主函数
    """
    logger.info("开始批量章节质量检查")

    # 初始化质量检查器
    checker = QualityChecker()

    # 加载章节目录
    novel_path = Path("wxhyj/Novel_directory.txt")
    if not novel_path.exists():
        logger.error(f"找不到文件: {novel_path}")
        return

    chapters = load_novel_directory(str(novel_path))
    if not chapters:
        logger.error("没有找到有效的章节")
        return

    # 存储所有报告
    all_reports = []
    format_issues = []
    low_score_chapters = []

    # 逐个检查章节
    for chapter in chapters:
        chapter_number = chapter['chapter_number']
        chapter_content = chapter['content']

        logger.info(f"正在检查第 {chapter_number} 章")

        # 1. 检查格式规范性
        format_check = check_chapter_format_compliance(chapter_content)
        if not format_check['is_compliant']:
            format_issues.append({
                'chapter_number': chapter_number,
                'compliance_score': format_check['compliance_score'],
                'missing_modules': format_check['missing_modules']
            })

        # 2. 解析章节信息
        try:
            chapter_info = parse_chapter_blueprint(chapter_content)
            chapter_info['chapter_number'] = chapter_number
        except Exception as e:
            logger.warning(f"解析第 {chapter_number} 章信息失败: {e}")
            chapter_info = {
                'chapter_number': chapter_number,
                'chapter_title': f'第{chapter_number}章',
                'word_count_target': '2000字'
            }

        # 3. 执行质量检查
        try:
            report = checker.check_chapter_quality(
                chapter_content,
                chapter_info,
                blueprint_text=chapter_content
            )

            # 添加格式检查结果
            format_metric = {
                'category': 'format_compliance',
                'name': '九大模块规范性',
                'score': format_check['compliance_score'],
                'weight': 0.2,
                'description': '检查是否符合9大模块格式标准',
                'details': {
                    'present_modules': len(format_check['present_modules']),
                    'missing_modules': len(format_check['missing_modules']),
                    'module_list': format_check['missing_modules']
                }
            }

            # 重新计算整体分数
            all_metrics = report.metrics + [format_metric]
            report.overall_score = checker._calculate_overall_score(all_metrics)
            report.quality_level = checker._determine_quality_level(report.overall_score)

            all_reports.append(report)

            # 记录低分章节
            if report.overall_score < 80:
                low_score_chapters.append({
                    'chapter_number': chapter_number,
                    'chapter_title': report.chapter_title,
                    'score': report.overall_score,
                    'quality_level': report.quality_level.value,
                    'issues': len(report.issues)
                })

        except Exception as e:
            logger.error(f"检查第 {chapter_number} 章质量失败: {e}")

    # 生成批量报告
    logger.info("生成质量报告...")

    # 统计信息
    total_chapters = len(all_reports)
    scores = [r.overall_score for r in all_reports]
    average_score = sum(scores) / len(scores) if scores else 0

    quality_distribution = {
        'excellent': len([r for r in all_reports if r.overall_score >= 90]),
        'good': len([r for r in all_reports if 80 <= r.overall_score < 90]),
        'fair': len([r for r in all_reports if 70 <= r.overall_score < 80]),
        'poor': len([r for r in all_reports if 60 <= r.overall_score < 70]),
        'unacceptable': len([r for r in all_reports if r.overall_score < 60])
    }

    # 生成报告内容
    report_content = {
        'check_time': datetime.now().isoformat(),
        'summary': {
            'total_chapters': total_chapters,
            'average_score': round(average_score, 2),
            'quality_distribution': quality_distribution,
            'format_compliance_rate': round(((total_chapters - len(format_issues)) / total_chapters) * 100, 2)
        },
        'format_issues': format_issues,
        'low_score_chapters': low_score_chapters,
        'common_issues': analyze_common_issues(all_reports),
        'recommendations': generate_recommendations(format_issues, low_score_chapters)
    }

    # 保存报告
    report_path = "wxhyj/chapter_quality_report.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report_content, f, ensure_ascii=False, indent=2)

    # 生成Markdown报告
    generate_markdown_report(report_content, "wxhyj/chapter_quality_report.md")

    logger.info(f"质量检查完成！报告已保存到: {report_path}")

    # 打印关键信息
    print("\n" + "="*50)
    print("批量章节质量检查完成")
    print("="*50)
    print(f"总章节数: {total_chapters}")
    print(f"平均分数: {average_score:.2f}")
    print(f"格式符合率: {((total_chapters - len(format_issues)) / total_chapters) * 100:.2f}%")
    print(f"低分章节数(<80分): {len(low_score_chapters)}")
    print(f"格式不规范章节数: {len(format_issues)}")
    print("="*50)


def analyze_common_issues(reports) -> list:
    """
    分析常见问题
    """
    issue_count = {}

    for report in reports:
        for issue in report.issues:
            key = issue.description
            if key not in issue_count:
                issue_count[key] = {
                    'description': issue.description,
                    'category': issue.category.value,
                    'count': 0,
                    'chapters': []
                }
            issue_count[key]['count'] += 1
            issue_count[key]['chapters'].append(report.chapter_number)

    # 排序并返回前10个最常见的问题
    sorted_issues = sorted(issue_count.values(), key=lambda x: x['count'], reverse=True)
    return sorted_issues[:10]


def generate_recommendations(format_issues, low_score_chapters) -> list:
    """
    生成改进建议
    """
    recommendations = []

    # 格式问题建议
    if format_issues:
        missing_modules = {}
        for issue in format_issues:
            for module in issue['missing_modules']:
                if module not in missing_modules:
                    missing_modules[module] = 0
                missing_modules[module] += 1

        recommendations.append({
            'type': 'format',
            'priority': 'high',
            'description': f"发现 {len(format_issues)} 个章节格式不规范，建议补充缺失的模块",
            'details': missing_modules
        })

    # 低分章节建议
    if low_score_chapters:
        score_ranges = {
            '60-70': len([c for c in low_score_chapters if c['score'] < 70]),
            '70-80': len([c for c in low_score_chapters if 70 <= c['score'] < 80])
        }

        recommendations.append({
            'type': 'quality',
            'priority': 'high',
            'description': f"发现 {len(low_score_chapters)} 个章节评分低于80分，需要重点优化",
            'details': score_ranges
        })

    return recommendations


def generate_markdown_report(report_data, output_path):
    """
    生成Markdown格式的报告
    """
    md_content = f"""# 章节质量检查报告

## 检查概览

- **检查时间**: {report_data['check_time'][:10]}
- **总章节数**: {report_data['summary']['total_chapters']}
- **平均分数**: {report_data['summary']['average_score']}
- **格式符合率**: {report_data['summary']['format_compliance_rate']}%

## 质量分布

| 质量等级 | 章节数 | 占比 |
|---------|--------|------|
| 优秀 (90-100分) | {report_data['summary']['quality_distribution']['excellent']} | {report_data['summary']['quality_distribution']['excellent']/report_data['summary']['total_chapters']*100:.1f}% |
| 良好 (80-89分) | {report_data['summary']['quality_distribution']['good']} | {report_data['summary']['quality_distribution']['good']/report_data['summary']['total_chapters']*100:.1f}% |
| 一般 (70-79分) | {report_data['summary']['quality_distribution']['fair']} | {report_data['summary']['quality_distribution']['fair']/report_data['summary']['total_chapters']*100:.1f}% |
| 较差 (60-69分) | {report_data['summary']['quality_distribution']['poor']} | {report_data['summary']['quality_distribution']['poor']/report_data['summary']['total_chapters']*100:.1f}% |
| 不可接受 (<60分) | {report_data['summary']['quality_distribution']['unacceptable']} | {report_data['summary']['quality_distribution']['unacceptable']/report_data['summary']['total_chapters']*100:.1f}% |

## 格式问题章节

共发现 {len(report_data['format_issues'])} 个章节存在格式问题：

"""

    # 列出格式问题章节
    for issue in report_data['format_issues'][:10]:  # 只显示前10个
        md_content += f"### 第{issue['chapter_number']}章 (格式符合度: {issue['compliance_score']:.1f}%)\n\n"
        md_content += f"缺失模块:\n"
        for module in issue['missing_modules']:
            md_content += f"- {module}\n"
        md_content += "\n"

    # 低分章节
    md_content += f"\n## 低分章节 (评分<80分)\n\n"
    md_content += f"共发现 {len(report_data['low_score_chapters'])} 个低分章节：\n\n"

    for chapter in report_data['low_score_chapters'][:10]:  # 只显示前10个
        md_content += f"- **第{chapter['chapter_number']}章 - {chapter['chapter_title']}**: {chapter['score']:.1f}分 ({chapter['quality_level']})\n"

    # 常见问题
    md_content += f"\n## 常见问题分析\n\n"

    for i, issue in enumerate(report_data['common_issues'][:5], 1):
        md_content += f"{i}. **{issue['description']}** (出现 {issue['count']} 次)\n"
        md_content += f"   - 类别: {issue['category']}\n"
        md_content += f"   - 涉及章节: {', '.join(map(str, issue['chapters'][:5]))}{'...' if len(issue['chapters']) > 5 else ''}\n\n"

    # 改进建议
    md_content += "## 改进建议\n\n"

    for rec in report_data['recommendations']:
        md_content += f"### {rec['priority'].upper()} - {rec['type'].title()}问题\n\n"
        md_content += f"{rec['description']}\n\n"

        if rec.get('details'):
            md_content += "**详情:**\n"
            for key, value in rec['details'].items():
                md_content += f"- {key}: {value}\n"
            md_content += "\n"

    # 保存Markdown报告
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(md_content)


if __name__ == "__main__":
    main()