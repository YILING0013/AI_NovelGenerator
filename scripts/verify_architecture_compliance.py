
import argparse
import os
import re
import sys
from pathlib import Path
from typing import List, Dict, Set

# Script to verify that Novel_directory.txt matches the requirements in Novel_architecture.txt

def read_file(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            with open(path, 'r', encoding='gbk') as f:
                return f.read()
        except:
            return ""
    except FileNotFoundError:
        return ""

def parse_directory(content):
    chapters = {}
    lines = content.split('\n')
    current_chapter = None
    current_content = []
    
    chapter_pattern = r"^第\s*(\d+)\s*章"
    
    for line in lines:
        match = re.search(chapter_pattern, line.strip())
        if match:
            if current_chapter:
                chapters[current_chapter] = "\n".join(current_content)
            current_chapter = int(match.group(1))
            current_content = [line]
        elif current_chapter:
            current_content.append(line)
            
    if current_chapter:
        chapters[current_chapter] = "\n".join(current_content)
        
    return chapters

def check_compliance(novel_dir):
    report = []
    architecture_path = os.path.join(novel_dir, "wxhyj", "Novel_architecture.txt")
    directory_path = os.path.join(novel_dir, "wxhyj", "Novel_directory.txt")
    
    # 1. 基础文件检查
    if not os.path.exists(architecture_path):
        return ["❌ Architecture file missing!"]
    if not os.path.exists(directory_path):
        return ["❌ Directory file missing!"]
        
    arch_content = read_file(architecture_path)
    dir_content = read_file(directory_path)
    
    chapters = parse_directory(dir_content)
    if not chapters:
        return ["❌ No chapters found in Novel_directory.txt"]
    
    chapter_nums = sorted(chapters.keys())
    total_chapters = len(chapter_nums)
    last_chapter = chapter_nums[-1]
    
    report.append(f"📊 **基础统计**")
    report.append(f"- 识别到的章节数: {total_chapters}")
    report.append(f"- 最后一章编号: {last_chapter}")
    
    # 2. 连续性检查
    missing = []
    for i in range(1, last_chapter + 1):
        if i not in chapters:
            missing.append(i)
            
    if missing:
        report.append(f"❌ **章节缺失警告**: 发现 {len(missing)} 个缺失章节")
        report.append(f"  - 缺失列表 (前10个): {missing[:10]}...")
    else:
        report.append(f"✅ **连续性检查**: 所有章节编号连续 (1-{last_chapter})")
        
    # 3. 模板完整性检查 (Section 12 Compliance)
    required_fields = [
        "【基础元信息】", 
        "【张力架构设计】", 
        "【情感轨迹工程】", 
        "【核心结构矩阵】",
        "【情节精要蓝图】",
        "【系统机制整合】",
        "【多层次悬念体系】",
        "【创作执行指南】",
        "【系统性衔接设计】",
        "【程序员思维应用】",
        "【伏笔植入清单】",
        "【暧昧场景设计】",
        "【爽点密度检查】",
        "【女主成长线推进】"
    ]
    
    report.append(f"\n📝 **模板完整性检查 (Section 12)**")
    sample_size = min(5, total_chapters)
    # Check first few, middle few, last few
    check_indices = sorted(list(set([1, total_chapters // 2, last_chapter])))
    
    for idx in check_indices:
        if idx in chapters:
            content = chapters[idx]
            missing_fields = [field for field in required_fields if field not in content]
            if missing_fields:
                report.append(f"❌ 第{idx}章 缺少字段: {missing_fields}")
            else:
                report.append(f"✅ 第{idx}章 包含所有14个核心模块")
                
    # 4. 关键剧情点检查 (Key Reversals and Bonds)
    # Based on architecture file content
    report.append(f"\n🔑 **关键剧情点一致性检查**")
    
    key_points = [
        # (Chapter Num, Keywords, Description)
        (280, ["陈逸风", "背叛"], "反转1：盟友的背叛"),
        (305, ["魔心莲", "献祭", "死"], "反转2：红颜的献祭"),
        (318, ["世界的伪装", "9527", "囚笼"], "反转3：世界的伪装"),
    ]
    
    for chap_num, keywords, desc in key_points:
        if chap_num in chapters:
            content = chapters[chap_num]
            found = any(k in content for k in keywords)
            status = "✅" if found else "❌"
            report.append(f"{status} 第{chap_num}章 [{desc}]: {'已检测到关键词' if found else '未检测到关键词 (需人工核查)'}")
        else:
            report.append(f"❌ 第{chap_num}章 [{desc}]: 章节尚未生成")

    return report

def parse_args() -> argparse.Namespace:
    default_project_root = Path(__file__).resolve().parent.parent

    parser = argparse.ArgumentParser(description="验证 Novel_directory.txt 与 Novel_architecture.txt 的一致性")
    parser.add_argument(
        "--project-root",
        default=str(default_project_root),
        help="项目根目录（默认：脚本上级目录）",
    )
    parser.add_argument(
        "--report-path",
        default="",
        help="报告输出路径（默认：<project-root>/architecture_compliance_report.md）",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    report_path = Path(args.report_path).resolve() if args.report_path else project_root / "architecture_compliance_report.md"

    print("正在执行架构一致性验证...\n")
    report_lines = check_compliance(str(project_root))
    print("\n".join(report_lines))

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# 架构合规性验证报告\n\n")
        f.write("\n\n".join(report_lines))

    print(f"\n报告已保存至: {report_path}")
