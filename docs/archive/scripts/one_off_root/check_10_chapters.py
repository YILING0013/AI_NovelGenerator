
import sys
import os
from pathlib import Path
import json

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from quality_checker import QualityChecker
from chapter_directory_parser import parse_chapter_blueprint

def check_specific_chapters():
    checker = QualityChecker("wxhyj")
    
    chapter_dir = Path("wxhyj/chapters")
    
    with open("wxhyj/check_10_report.txt", "w", encoding='utf-8') as f:
        f.write(f"{'Chapter':<8} | {'Score':<6} | {'Level':<10} | {'Issues'}\n")
        f.write("-" * 80 + "\n")

        for i in range(1, 11):
            filename = f"chapter_{i}.txt"
            filepath = chapter_dir / filename
            
            if not filepath.exists():
                f.write(f"Chapter {i} not found at {filepath}\n")
                continue
                
            try:
                with open(filepath, 'r', encoding='utf-8') as chapter_file:
                    content = chapter_file.read()
                    
                # Parse info
                try:
                    chapter_info = parse_chapter_blueprint(content)
                    chapter_info['chapter_number'] = i
                except:
                    chapter_info = {'chapter_number': i, 'chapter_title': f'Chapter {i}'}
                    
                # Check
                report = checker.check_chapter_quality(content, chapter_info, blueprint_text=content)
                
                # Format check
                required_module_patterns = {
                    "基础元信息": ["基础元信息", "元信息", "章节定位"],
                    "张力架构": ["张力架构", "张力设计", "冲突设计", "紧张感"],
                    "情感轨迹": ["情感轨迹", "情感工程", "暧昧", "修罗场", "Romance"],
                    "核心结构": ["核心结构", "结构矩阵", "情节精要"],
                    "系统机制": ["系统机制", "系统整合", "数值变化"],
                    "悬念体系": ["悬念体系", "伏笔", "信息差", "Foreshadowing"],
                    "创作指南": ["创作执行", "创作指南", "质量检查", "Quality"],
                    "衔接设计": ["衔接设计", "承上启下", "节奏控制"],
                    "理性思维": ["理性思维", "Rationality", "程序员思维"]
                }
                
                present_modules = []
                missing_modules = []
                for module_name, keywords in required_module_patterns.items():
                    if any(kw in content for kw in keywords):
                        present_modules.append(module_name)
                    else:
                        missing_modules.append(module_name)
                
                compliance_score = (len(present_modules) / len(required_module_patterns)) * 100
                
                # Adjust score
                format_metric = {
                    'name': '九大模块规范性',
                    'score': compliance_score,
                    'weight': 0.2
                }
                report.metrics.append(format_metric)
                
                total_score = 0
                total_weight = 0
                for m in report.metrics:
                    w = m.get('weight', 0.1)
                    s = m.get('score', 0)
                    total_score += s * w
                    total_weight += w
                
                final_score = total_score / total_weight if total_weight > 0 else 0
                
                issue_desc = [x.description for x in report.issues]
                if missing_modules:
                    issue_desc.append(f"Missing: {', '.join(missing_modules)}")
                
                f.write(f"{i:<8} | {final_score:<6.2f} | {report.quality_level.value:<10} | {len(report.issues)} issues\n")
                if missing_modules:
                    f.write(f"  Format Compliance: {compliance_score:.1f}% (Missing: {', '.join(missing_modules)})\n")
                
            except Exception as e:
                f.write(f"Error checking chapter {i}: {e}\n")

if __name__ == "__main__":
    check_specific_chapters()
