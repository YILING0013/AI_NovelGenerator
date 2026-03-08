# chapter_completeness_fixer.py
# -*- coding: utf-8 -*-
"""
章节完整性修复工具
专门用于修复Novel_directory.txt中缺失的章节
"""
import os
import re
import json
import time
from datetime import datetime
from blueprint_optimized import OptimizedChapterGenerator

def analyze_directory_issues(directory_file: str) -> dict:
    """
    深度分析目录文件的问题
    """
    print(f"🔍 深度分析目录文件：{directory_file}")

    if not os.path.exists(directory_file):
        return {"error": "文件不存在"}

    with open(directory_file, 'r', encoding='utf-8') as f:
        content = f.read().strip()

    if not content:
        return {"error": "文件为空"}

    # 解析章节
    chapters = []
    lines = content.split('\n')
    current_chapter = {}

    chapter_pattern = re.compile(r'^第\s*(\d+)\s*章\s*(?:-\s*(.*))?\s*$')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        chapter_match = chapter_pattern.match(line)
        if chapter_match:
            # 保存前一个章节
            if current_chapter:
                chapters.append(current_chapter)

            # 开始新章节
            chapter_num = int(chapter_match.group(1))
            chapter_title = chapter_match.group(2).strip() if chapter_match.group(2) else ""

            current_chapter = {
                "number": chapter_num,
                "title": chapter_title,
                "content_lines": [line],
                "has_details": False,
                "detail_count": 0
            }
        else:
            if current_chapter:
                current_chapter["content_lines"].append(line)
                # 计算详细内容行数
                if len(line) > 10 and not line.startswith('第'):
                    current_chapter["detail_count"] += 1
                    if current_chapter["detail_count"] >= 5:
                        current_chapter["has_details"] = True

    # 添加最后一个章节
    if current_chapter:
        chapters.append(current_chapter)

    # 分析问题
    if not chapters:
        return {"error": "未找到有效章节"}

    chapter_numbers = [ch["number"] for ch in chapters]
    max_chapter = max(chapter_numbers)
    min_chapter = min(chapter_numbers)

    # 分类章节
    complete_chapters = [ch for ch in chapters if ch["has_details"]]
    partial_chapters = [ch for ch in chapters if not ch["has_details"] and ch["detail_count"] > 0]
    title_only_chapters = [ch for ch in chapters if ch["detail_count"] == 0]

    # 找出缺失范围
    expected_chapters = set(range(min_chapter, max_chapter + 1))
    actual_chapters = set(chapter_numbers)
    missing_chapters = sorted(expected_chapters - actual_chapters)

    # 找出问题范围（需要重新生成的）
    problem_ranges = []
    if missing_chapters:
        start_range = missing_chapters[0]
        end_range = missing_chapters[0]

        for i in range(1, len(missing_chapters)):
            if missing_chapters[i] == missing_chapters[i-1] + 1:
                end_range = missing_chapters[i]
            else:
                problem_ranges.append((start_range, end_range))
                start_range = end_range = missing_chapters[i]

        problem_ranges.append((start_range, end_range))

    return {
        "total_chapters": len(chapters),
        "complete_chapters": len(complete_chapters),
        "partial_chapters": len(partial_chapters),
        "title_only_chapters": len(title_only_chapters),
        "chapter_range": f"{min_chapter}-{max_chapter}",
        "missing_chapters": missing_chapters,
        "problem_ranges": problem_ranges,
        "chapters_detail": chapters,
        "completeness_rate": f"{len(complete_chapters) / len(chapters) * 100:.1f}%"
    }

def create_fix_plan(analysis: dict) -> dict:
    """
    创建修复计划
    """
    if "error" in analysis:
        return {"error": analysis["error"]}

    plan = {
        "strategy": "分批修复",
        "phases": []
    }

    # 按优先级排序问题范围
    problem_ranges = analysis["problem_ranges"]

    # 策略1：优先修复早期章节（更重要）
    early_ranges = [r for r in problem_ranges if r[0] <= 100]
    late_ranges = [r for r in problem_ranges if r[0] > 100]

    # 策略2：小范围优先（成功率更高）
    small_ranges = [r for r in problem_ranges if r[1] - r[0] <= 20]
    large_ranges = [r for r in problem_ranges if r[1] - r[0] > 20]

    # 制定修复计划
    all_ranges = sorted(problem_ranges, key=lambda x: (x[0], x[1] - x[0]))

    for i, (start, end) in enumerate(all_ranges):
        phase = {
            "phase_id": i + 1,
            "range": (start, end),
            "chapter_count": end - start + 1,
            "priority": "high" if start <= 100 else "medium",
            "strategy": "complete_generation" if (end - start + 1) <= 30 else "chunked_generation"
        }
        plan["phases"].append(phase)

    return plan

def fix_missing_chapters(
    directory_file: str,
    interface_format: str,
    api_key: str,
    base_url: str,
    llm_model: str,
    temperature: float = 0.7,
    max_tokens: int = 20000,
    timeout: int = 1200
) -> bool:
    """
    修复缺失章节的主函数
    """
    print("🚀 开始修复章节完整性...")

    # 1. 深度分析问题
    analysis = analyze_directory_issues(directory_file)
    if "error" in analysis:
        print(f"❌ 分析失败：{analysis['error']}")
        return False

    print(f"📊 分析结果：")
    print(f"   总章节数：{analysis['total_chapters']}")
    print(f"   完整章节：{analysis['complete_chapters']}")
    print(f"   部分章节：{analysis['partial_chapters']}")
    print(f"   仅标题章节：{analysis['title_only_chapters']}")
    print(f"   完整率：{analysis['completeness_rate']}")
    print(f"   缺失章节：{len(analysis['missing_chapters'])}")
    print(f"   问题范围：{len(analysis['problem_ranges'])}")

    if not analysis['missing_chapters'] and analysis['title_only_chapters'] == 0:
        print("✅ 目录完整，无需修复")
        return True

    # 2. 制定修复计划
    fix_plan = create_fix_plan(analysis)
    if "error" in fix_plan:
        print(f"❌ 制定修复计划失败：{fix_plan['error']}")
        return False

    print(f"📋 修复计划：{fix_plan['strategy']}")
    print(f"   修复阶段数：{len(fix_plan['phases'])}")

    # 3. 执行修复
    filepath = os.path.dirname(directory_file)
    success = True

    # 创建优化生成器
    generator = OptimizedChapterGenerator(
        interface_format=interface_format,
        api_key=api_key,
        base_url=base_url,
        llm_model=llm_model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout
    )

    # 备份原文件
    backup_file = directory_file + f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    os.rename(directory_file, backup_file)
    print(f"📁 原文件已备份到：{backup_file}")

    try:
        # 读取架构文件
        arch_file = os.path.join(filepath, "Novel_architecture.txt")
        if not os.path.exists(arch_file):
            print("❌ Novel_architecture.txt 不存在")
            return False

        architecture_text = read_file(arch_file).strip()

        # 读取现有目录
        existing_content = read_file(backup_file).strip()

        # 按阶段修复
        for phase in fix_plan["phases"]:
            start_chapter, end_chapter = phase["range"]
            print(f"\n🔄 执行阶段{phase['phase_id']}：修复章节 [{start_chapter}..{end_chapter}]")

            # 生成缺失章节
            try:
                missing_content = generator.generate_chunk_with_fallback(
                    start_chapter, end_chapter, architecture_text, existing_content
                )

                if missing_content:
                    # 整合到现有内容中
                    existing_content = integrate_new_chapters(existing_content, missing_content)
                    print(f"✅ 阶段{phase['phase_id']}完成")
                else:
                    print(f"❌ 阶段{phase['phase_id']}失败")
                    success = False

            except Exception as e:
                print(f"❌ 阶段{phase['phase_id']}异常：{e}")
                success = False

        # 保存修复后的文件
        clear_file_content(directory_file)
        save_string_to_txt(existing_content.strip(), directory_file)

        # 4. 最终验证
        print("\n🔍 最终验证...")
        final_analysis = analyze_directory_issues(directory_file)
        if "error" not in final_analysis:
            print(f"📊 修复后状态：")
            print(f"   完整率：{final_analysis['completeness_rate']}")
            print(f"   缺失章节：{len(final_analysis['missing_chapters'])}")

            if len(final_analysis['missing_chapters']) == 0:
                print("🎉 修复完成！所有章节已补全")
            else:
                print(f"⚠️ 部分修复完成，仍有{len(final_analysis['missing_chapters'])}章缺失")

        return success

    except Exception as e:
        print(f"❌ 修复过程异常：{e}")
        # 恢复备份
        if os.path.exists(backup_file):
            os.rename(backup_file, directory_file)
        return False

def integrate_new_chapters(existing_content: str, new_content: str) -> str:
    """
    将新生成的章节整合到现有内容中
    """
    # 简单的字符串拼接（可以根据需要优化为更智能的整合）
    if existing_content.strip():
        return existing_content.strip() + "\n\n" + new_content.strip()
    else:
        return new_content.strip()

def read_file(file_path: str) -> str:
    """安全读取文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"读取文件失败 {file_path}: {e}")
        return ""

def clear_file_content(file_path: str) -> bool:
    """清空文件内容"""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("")
        return True
    except Exception as e:
        print(f"清空文件失败 {file_path}: {e}")
        return False

def save_string_to_txt(content: str, file_path: str) -> bool:
    """保存内容到文件"""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"保存文件失败 {file_path}: {e}")
        return False

if __name__ == "__main__":
    import sys as _sys
    
    if len(_sys.argv) > 1:
        directory_file = _sys.argv[1]
    else:
        print("Usage: python chapter_completeness_fixer.py <Novel_directory.txt>")
        _sys.exit(1)

    print("🔧 章节完整性修复工具")
    print("=" * 50)

    # 1. 分析当前状态
    analysis = analyze_directory_issues(directory_file)

    if "error" not in analysis:
        print("\n📊 当前状态分析：")
        print(json.dumps(analysis, indent=2, ensure_ascii=False))

        # 2. 创建修复计划
        plan = create_fix_plan(analysis)
        if "error" not in plan:
            print("\n📋 修复计划：")
            print(json.dumps(plan, indent=2, ensure_ascii=False))

    # 实际修复需要配置信息
    print("\n⚠️ 要执行修复，请调用 fix_missing_chapters() 函数")
    print("需要提供：API配置、模型信息等")