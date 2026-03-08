# -*- coding: utf-8 -*-
"""
暧昧场景密度检查工具
检查蓝图中是否每10章至少有1个暧昧场景
暗昧场景密度检查工具
检查蓝图中是否每10章至少有1个暗昧场景
"""

import re
import os
from typing import Dict, List, Tuple

# 暗昧场景关键词 (NOTE: 女主关键词会动态加载)
ROMANCE_KEYWORDS = {
    "高张力": ["心动", "脸红", "耳根", "暗昧", "暗昧等级", "暗昧类型", "好感度"],
    "身体接触": ["疗伤", "触碰", "指尖", "气息", "拥抱", "牵手", "靠近", "依偁"],
    "情感表达": ["表白", "告白", "喜欢", "爱慕", "心意", "守护", "保护"],
    "氛围描写": ["月下", "夜色", "烛光", "温暖", "温柔", "心跳", "脸颈发烫"],
    "修罗场": ["嫉妒", "争风吃醋", "修罗场", "四人", "争夺"]
}

# NOTE: 推荐的暗昧分布已移除硬编码，现在会从架构文件动态读取


def load_blueprint(filepath: str) -> str:
    """加载蓝图文件"""
    blueprint_path = os.path.join(filepath, "Novel_directory.txt")
    if not os.path.exists(blueprint_path):
        return ""
    with open(blueprint_path, 'r', encoding='utf-8') as f:
        return f.read()


def extract_chapter_content(blueprint: str, chapter_num: int) -> str:
    """提取指定章节的蓝图内容"""
    pattern = rf'###\s*\*\*第{chapter_num}章.*?(?=###\s*\*\*第\d+章|$)'
    match = re.search(pattern, blueprint, re.DOTALL)
    if match:
        return match.group(0)
    return ""


def _load_female_leads(filepath: str):
    """动态加载女主列表"""
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from novel_generator.architecture_parser import ArchitectureParser
        parser = ArchitectureParser(filepath)
        parser.parse()
        if parser.female_leads:
            return parser.female_leads
    except Exception:
        pass
    return []  # Empty fallback


def check_romance_in_chapter(chapter_content: str, female_leads: list = None) -> Dict:
    """检查章节中的暗昧场景"""
    result = {
        "has_romance": False,
        "romance_score": 0,
        "matched_categories": [],
        "matched_keywords": [],
        "female_leads_mentioned": []
    }
    
    if not chapter_content:
        return result
    
    if female_leads is None:
        female_leads = []
    
    # 检查各类关键词
    for category, keywords in ROMANCE_KEYWORDS.items():
        category_matches = []
        for keyword in keywords:
            if keyword in chapter_content:
                category_matches.append(keyword)
                result["matched_keywords"].append(keyword)
        
        if category_matches:
            result["matched_categories"].append(category)
            result["romance_score"] += len(category_matches)
    
    # 检查女主出场
    for lead in female_leads:
        if lead in chapter_content:
            result["female_leads_mentioned"].append(lead)
    
    # 判断是否有暗昧场景
    result["has_romance"] = result["romance_score"] >= 3 and len(result["female_leads_mentioned"]) > 0
    
    return result


def analyze_romance_density(filepath: str, max_chapter: int = 400, female_leads: list = None) -> Dict:
    """分析暗昧场景密度"""
    blueprint = load_blueprint(filepath)
    if not blueprint:
        return {"error": "蓝图文件不存在或为空"}
    
    results = {
        "total_chapters": 0,
        "chapters_with_romance": 0,
        "density_per_10_chapters": [],
        "gaps": [],  # 超过10章没有暗昧的区间
        "chapter_details": {}
    }

    if female_leads is None:
        female_leads = []
    
    # 逐10章区间分析
    for start in range(1, max_chapter + 1, 10):
        end = min(start + 9, max_chapter)
        range_romance_count = 0
        range_details = []
        
        for chapter_num in range(start, end + 1):
            chapter_content = extract_chapter_content(blueprint, chapter_num)
            if not chapter_content:
                continue
            
            results["total_chapters"] += 1
            romance_result = check_romance_in_chapter(chapter_content, female_leads)
            
            if romance_result["has_romance"]:
                range_romance_count += 1
                results["chapters_with_romance"] += 1
            
            results["chapter_details"][chapter_num] = romance_result
            range_details.append({
                "chapter": chapter_num,
                "has_romance": romance_result["has_romance"],
                "score": romance_result["romance_score"]
            })
        
        results["density_per_10_chapters"].append({
            "range": f"{start}-{end}",
            "romance_count": range_romance_count,
            "status": "✅ 达标" if range_romance_count >= 1 else "❌ 不达标"
        })
        
        if range_romance_count == 0:
            results["gaps"].append(f"{start}-{end}")
    
    return results


def print_romance_report(results: Dict, novel_name: str = "小说"):
    """打印暗昧场景报告"""
    if "error" in results:
        print(f"错误: {results['error']}")
        return
    
    print("=" * 60)
    print(f"《{novel_name}》暗昧场景密度检查报告")
    print("=" * 60)
    
    total = results["total_chapters"]
    with_romance = results["chapters_with_romance"]
    density = with_romance / total * 100 if total > 0 else 0
    
    print(f"\n📊 总体统计:")
    print(f"  - 已分析章节数: {total}")
    print(f"  - 包含暧昧场景: {with_romance} ({density:.1f}%)")
    print(f"  - 目标: 每10章至少1个暧昧场景")
    
    # 统计达标情况
    compliant = sum(1 for d in results["density_per_10_chapters"] if d["romance_count"] >= 1)
    total_ranges = len(results["density_per_10_chapters"])
    compliance_rate = compliant / total_ranges * 100 if total_ranges > 0 else 0
    
    print(f"\n📈 密度达标情况:")
    print(f"  - 达标区间: {compliant}/{total_ranges} ({compliance_rate:.1f}%)")
    
    print(f"\n📋 各区间详情 (前20个):")
    for i, d in enumerate(results["density_per_10_chapters"][:20]):
        print(f"  {d['range']}: {d['status']} (暧昧章节: {d['romance_count']})")
    
    if results["gaps"]:
        print(f"\n⚠️ 暧昧空白区间 (需要补充):")
        for gap in results["gaps"][:10]:
            print(f"  - 第{gap}章")
    
    # 推荐补充
    print(f"\n💡 补充建议:")
    for (start, end), rec in list(RECOMMENDED_ROMANCE_CHAPTERS.items())[:5]:
        print(f"  第{start}-{end}章: 建议添加{rec['lead']}的{rec['type']}场景")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    import sys as _sys
    
    if len(_sys.argv) > 1:
        filepath = _sys.argv[1]
    else:
        print("Usage: python check_romance_density.py <novel_folder>")
        _sys.exit(1)
    
    results = analyze_romance_density(filepath, max_chapter=120)
    # 尝试获取小说名称
    novel_name = os.path.basename(filepath)
    print_romance_report(results, novel_name)
