# -*- coding: utf-8 -*-
"""
女主成长线验证工具 - 检查蓝图中女主关键章节是否正确标记
根据Novel_architecture.txt中的设计验证Novel_directory.txt
"""

import re
import os
from typing import Dict, List, Tuple

# 女主成长线关键章节
# NOTE: 已移除硬编码，现在从 story_rules.json 动态加载
# 如果配置为空，脚本将跳过验证

def load_female_milestones(filepath: str) -> dict:
    """从 story_rules.json 加载女主里程碑配置"""
    import json
    
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                               "config", "story_rules.json")
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            milestones_raw = config.get("female_lead_milestones", {})
            if milestones_raw:
                # 按女主分组
                result = {}
                for chapter, info in milestones_raw.items():
                    lead = info.get("lead", "未知")
                    milestone = info.get("milestone", "")
                    
                    if lead not in result:
                        result[lead] = {
                            "description": f"{lead}的成长线",
                            "milestones": [],
                            "keywords": [lead]
                        }
                    result[lead]["milestones"].append((int(chapter), milestone))
                
                # 排序里程碑
                for lead in result:
                    result[lead]["milestones"].sort(key=lambda x: x[0])
                
                return result
        except Exception as e:
            print(f"⚠️ 加载 story_rules.json 失败: {e}")
    
    return {}


# 兼容旧代码
FEMALE_LEAD_MILESTONES = {}


def load_blueprint(filepath: str) -> str:
    """加载蓝图文件"""
    blueprint_path = os.path.join(filepath, "Novel_directory.txt")
    if not os.path.exists(blueprint_path):
        return ""
    with open(blueprint_path, 'r', encoding='utf-8') as f:
        return f.read()


def extract_chapter_content(blueprint: str, chapter_num: int) -> str:
    """提取指定章节的蓝图内容"""
    # 匹配章节标题开始到下一章节开始
    pattern = rf'###\s*\*\*第{chapter_num}章.*?(?=###\s*\*\*第\d+章|$)'
    match = re.search(pattern, blueprint, re.DOTALL)
    if match:
        return match.group(0)
    return ""


def check_milestone_in_chapter(chapter_content: str, keywords: List[str], milestone_desc: str) -> Dict:
    """检查章节内容中是否包含里程碑相关内容"""
    result = {
        "found": False,
        "keyword_matches": [],
        "relevance_score": 0
    }
    
    if not chapter_content:
        return result
    
    # 检查关键词匹配
    for keyword in keywords:
        if keyword in chapter_content:
            result["keyword_matches"].append(keyword)
    
    # 计算相关性分数
    result["relevance_score"] = len(result["keyword_matches"]) / len(keywords) * 100
    result["found"] = result["relevance_score"] >= 20  # 至少20%关键词匹配
    
    # 检查里程碑描述中的关键词
    milestone_keywords = milestone_desc.split("，")[0].split("、")
    for kw in milestone_keywords:
        if len(kw) >= 2 and kw in chapter_content:
            result["relevance_score"] += 10
    
    return result


def verify_female_lead_growth(filepath: str) -> Dict:
    """验证女主成长线"""
    blueprint = load_blueprint(filepath)
    if not blueprint:
        return {"error": "蓝图文件不存在或为空"}
    
    # 动态加载里程碑配置
    milestones = load_female_milestones(filepath)
    if not milestones:
        return {"info": "story_rules.json 中未配置女主里程碑规则，跳过检查", "total_milestones": 0}
    
    results = {
        "total_milestones": 0,
        "verified_milestones": 0,
        "missing_milestones": [],
        "weak_milestones": [],
        "details": {}
    }
    
    for female_lead, info in milestones.items():
        lead_result = {
            "description": info["description"],
            "milestones_total": len(info["milestones"]),
            "milestones_found": 0,
            "milestones_weak": 0,
            "milestone_details": []
        }
        
        for chapter_num, milestone_desc in info["milestones"]:
            results["total_milestones"] += 1
            chapter_content = extract_chapter_content(blueprint, chapter_num)
            
            check_result = check_milestone_in_chapter(
                chapter_content, 
                info["keywords"], 
                milestone_desc
            )
            
            milestone_info = {
                "chapter": chapter_num,
                "description": milestone_desc,
                "found": check_result["found"],
                "relevance_score": check_result["relevance_score"],
                "matched_keywords": check_result["keyword_matches"]
            }
            
            if check_result["found"]:
                if check_result["relevance_score"] >= 50:
                    results["verified_milestones"] += 1
                    lead_result["milestones_found"] += 1
                    milestone_info["status"] = "✅ 正常"
                else:
                    lead_result["milestones_weak"] += 1
                    milestone_info["status"] = "⚠️ 较弱"
                    results["weak_milestones"].append(f"{female_lead} 第{chapter_num}章: {milestone_desc}")
            else:
                milestone_info["status"] = "❌ 缺失"
                results["missing_milestones"].append(f"{female_lead} 第{chapter_num}章: {milestone_desc}")
            
            lead_result["milestone_details"].append(milestone_info)
        
        results["details"][female_lead] = lead_result
    
    return results


def print_verification_report(results: Dict, novel_name: str = "小说"):
    """打印验证报告"""
    if "error" in results:
        print(f"错误: {results['error']}")
        return
    
    print("=" * 60)
    print(f"《{novel_name}》女主成长线验证报告")
    print("=" * 60)
    
    total = results["total_milestones"]
    verified = results["verified_milestones"]
    percentage = verified / total * 100 if total > 0 else 0
    
    print(f"\n📊 总体统计:")
    print(f"  - 总里程碑数: {total}")
    print(f"  - 已验证: {verified} ({percentage:.1f}%)")
    print(f"  - 较弱: {len(results['weak_milestones'])}")
    print(f"  - 缺失: {len(results['missing_milestones'])}")
    
    for female_lead, detail in results["details"].items():
        print(f"\n👧 {female_lead} - {detail['description']}")
        print(f"   找到: {detail['milestones_found']}/{detail['milestones_total']}")
        
        for m in detail["milestone_details"]:
            status = m["status"]
            print(f"   {status} 第{m['chapter']}章: {m['description'][:30]}...")
            if m["matched_keywords"]:
                print(f"       匹配关键词: {', '.join(m['matched_keywords'])}")
    
    if results["missing_milestones"]:
        print(f"\n⚠️ 需要关注的缺失里程碑:")
        for m in results["missing_milestones"][:5]:
            print(f"   - {m}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    import sys as _sys
    
    if len(_sys.argv) > 1:
        filepath = _sys.argv[1]
    else:
        print("Usage: python verify_female_lead_growth.py <novel_folder>")
        _sys.exit(1)
    
    results = verify_female_lead_growth(filepath)
    novel_name = os.path.basename(filepath)
    print_verification_report(results, novel_name)
