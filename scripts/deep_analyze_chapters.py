# -*- coding: utf-8 -*-
"""深度分析10章质量"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chapter_quality_analyzer import ChapterQualityAnalyzer

novel_path = r"c:\Users\tcui\Documents\GitHub\AI_NovelGenerator\wxhyj"
chapters_dir = os.path.join(novel_path, "chapters")

analyzer = ChapterQualityAnalyzer(novel_path)
print("=" * 70)
print(f"深度质量分析报告 (阈值: 9分, 检测题材: {analyzer.genre})")
print("=" * 70)

# 分析每章
# 分析每章 (1-50章)
results = []
for i in range(1, 51):
    chapter_file = os.path.join(chapters_dir, f"chapter_{i}.txt")
    if not os.path.exists(chapter_file):
        print(f"⚠️ 第{i}章文件不存在，跳过")
        continue

    with open(chapter_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    scores = analyzer.analyze_content(content)
    overall = float(scores.get("综合评分", 0))
    genre_score = scores.get("题材综合分", 10)
    
    results.append({
        "chapter": i,
        "overall": overall,
        "genre_score": genre_score,
        "scores": scores
    })

# 输出结果到文件
report_file = "analysis_report_50.txt"
with open(report_file, "w", encoding="utf-8") as f:
    f.write("=" * 70 + "\n")
    f.write(f"深度质量分析报告 (阈值: 9分, 检测题材: {analyzer.genre})\n")
    f.write("=" * 70 + "\n")

    for r in results:
        ch = r["chapter"]
        overall = r["overall"]
        genre = r["genre_score"]
        scores = r["scores"]
        
        # 判断是否需要重写
        if overall < 7:
            status = "❌ 需全章重写"
        elif overall < 9:
            status = "⚠️ 需局部优化"
        else:
            status = "✅ 质量达标"
        
        f.write(f"\n第{ch}章 | 综合: {overall:.1f} | 题材: {genre:.1f} | {status}\n")
        f.write(f"  剧情连贯: {scores.get('剧情连贯性', 0):.1f} | 角色: {scores.get('角色一致性', 0):.1f} | 写作: {scores.get('写作质量', 0):.1f}\n")
        f.write(f"  情感张力: {scores.get('情感张力', 0):.1f} | 系统机制: {scores.get('系统机制', 0):.1f} | 字数: {scores.get('字数', 0)}\n")
        
        # 题材维度
        if "题材维度" in scores:
            dims = scores["题材维度"]
            dim_str = " | ".join([f"{d['name']}: {d['score']:.1f}" for d in dims.values()])
            f.write(f"  题材维度: {dim_str}\n")
        
        # 改进建议
        hints = scores.get("题材改进建议", [])
        if hints:
            for h in hints:
                f.write(f"  💡 {h}\n")

    f.write("\n" + "=" * 70 + "\n")
    f.write("汇总统计\n")
    f.write("=" * 70 + "\n")
    if results:
        avg = sum(r["overall"] for r in results) / len(results)
        need_rewrite = [r for r in results if r["overall"] < 7]
        need_optimize = [r for r in results if 7 <= r["overall"] < 9]
        passed = [r for r in results if r["overall"] >= 9]
        f.write(f"平均分: {avg:.2f}\n")
        f.write(f"需全章重写: {len(need_rewrite)}章 {[r['chapter'] for r in need_rewrite]}\n")
        f.write(f"需局部优化: {len(need_optimize)}章 {[r['chapter'] for r in need_optimize]}\n")
        f.write(f"质量达标: {len(passed)}章 {[r['chapter'] for r in passed]}\n")

print(f"分析完成，报告已保存至 {report_file}")
