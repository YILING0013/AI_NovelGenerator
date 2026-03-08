# -*- coding: utf-8 -*-
"""
反转伏笔植入检查工具
验证架构中定义的重大反转是否在蓝图中正确植入伏笔
"""

import re
import os
from typing import Dict, List

# 架构中定义的重大反转及其伏笔
# NOTE: 已移除硬编码，现在从 story_rules.json 动态加载
# 如果配置为空，脚本将跳过验证

def load_major_reversals(filepath: str) -> dict:
    """从 story_rules.json 加载重大反转配置"""
    import json
    
    # 尝试从项目配置加载
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                               "config", "story_rules.json")
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            reversals_raw = config.get("major_reversal_chapters", {})
            # 将简单格式转换为完整格式
            if reversals_raw:
                result = {}
                for chapter, description in reversals_raw.items():
                    result[description] = {
                        "reveal_chapter": int(chapter),
                        "description": description,
                        "required_foreshadowing": [],  # 需要在配置中定义
                        "keywords": description[:10].split() if description else []
                    }
                return result
        except Exception as e:
            print(f"⚠️ 加载 story_rules.json 失败: {e}")
    
    return {}


# 兼容旧代码的全局变量
MAJOR_REVERSALS = {}



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


def check_foreshadowing(blueprint: str, reversal_name: str, reversal_info: Dict) -> Dict:
    """检查某个反转的伏笔是否正确植入"""
    result = {
        "reversal_name": reversal_name,
        "reveal_chapter": reversal_info["reveal_chapter"],
        "description": reversal_info["description"],
        "foreshadowing_status": [],
        "overall_score": 0,
        "keywords_found": []
    }
    
    total_foreshadowing = len(reversal_info["required_foreshadowing"])
    found_count = 0
    
    for foreshadow in reversal_info["required_foreshadowing"]:
        chapter_num = foreshadow["chapter"]
        required_content = foreshadow["content"]
        
        chapter_content = extract_chapter_content(blueprint, chapter_num)
        
        # 检查关键词匹配
        keywords_matched = []
        for keyword in reversal_info["keywords"]:
            if keyword in chapter_content:
                keywords_matched.append(keyword)
        
        # 检查伏笔描述是否存在
        has_foreshadow = len(keywords_matched) >= 2 or "伏笔" in chapter_content
        
        status = {
            "chapter": chapter_num,
            "required": required_content,
            "found": has_foreshadow,
            "keywords_matched": keywords_matched,
            "status": "✅ 已植入" if has_foreshadow else "❌ 缺失"
        }
        
        if has_foreshadow:
            found_count += 1
            result["keywords_found"].extend(keywords_matched)
        
        result["foreshadowing_status"].append(status)
    
    result["overall_score"] = found_count / total_foreshadowing * 100 if total_foreshadowing > 0 else 0
    result["keywords_found"] = list(set(result["keywords_found"]))
    
    return result


def verify_all_reversals(filepath: str) -> Dict:
    """验证所有反转伏笔"""
    blueprint = load_blueprint(filepath)
    if not blueprint:
        return {"error": "蓝图文件不存在或为空"}
    
    # 动态加载反转配置
    reversals = load_major_reversals(filepath)
    if not reversals:
        return {"info": "story_rules.json 中未配置反转伏笔规则，跳过检查", "total_reversals": 0}
    
    results = {
        "total_reversals": len(reversals),
        "fully_foreshadowed": 0,
        "partially_foreshadowed": 0,
        "missing_foreshadowing": 0,
        "details": {}
    }
    
    for reversal_name, reversal_info in reversals.items():
        result = check_foreshadowing(blueprint, reversal_name, reversal_info)
        results["details"][reversal_name] = result
        
        if result["overall_score"] >= 80:
            results["fully_foreshadowed"] += 1
        elif result["overall_score"] >= 40:
            results["partially_foreshadowed"] += 1
        else:
            results["missing_foreshadowing"] += 1
    
    return results


def print_reversal_report(results: Dict, novel_name: str = "小说"):
    """打印反转伏笔报告"""
    if "error" in results:
        print(f"错误: {results['error']}")
        return
    
    print("=" * 60)
    print(f"《{novel_name}》反转伏笔植入检查报告")
    print("=" * 60)
    
    total = results["total_reversals"]
    fully = results["fully_foreshadowed"]
    partially = results["partially_foreshadowed"]
    missing = results["missing_foreshadowing"]
    
    print(f"\n📊 总体统计:")
    print(f"  - 重大反转数: {total}")
    print(f"  - 伏笔完整: {fully} ({fully/total*100:.1f}%)")
    print(f"  - 伏笔部分: {partially} ({partially/total*100:.1f}%)")
    print(f"  - 伏笔缺失: {missing} ({missing/total*100:.1f}%)")
    
    print(f"\n📋 各反转详情:")
    for reversal_name, detail in results["details"].items():
        score = detail["overall_score"]
        status = "✅" if score >= 80 else "⚠️" if score >= 40 else "❌"
        print(f"\n  {status} 【{reversal_name}】 (第{detail['reveal_chapter']}章揭示)")
        print(f"     {detail['description'][:40]}...")
        print(f"     伏笔完成度: {score:.1f}%")
        
        for fs in detail["foreshadowing_status"]:
            print(f"       - 第{fs['chapter']}章: {fs['status']}")
            if fs["keywords_matched"]:
                print(f"         关键词: {', '.join(fs['keywords_matched'])}")
    
    # 需要补充的伏笔
    missing_list = []
    for reversal_name, detail in results["details"].items():
        for fs in detail["foreshadowing_status"]:
            if not fs["found"]:
                missing_list.append(f"第{fs['chapter']}章: {fs['required']} ({reversal_name})")
    
    if missing_list:
        print(f"\n⚠️ 需要补充的伏笔:")
        for m in missing_list[:10]:
            print(f"  - {m}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    import sys as _sys
    
    if len(_sys.argv) > 1:
        filepath = _sys.argv[1]
    else:
        print("Usage: python check_reversal_foreshadowing.py <novel_folder>")
        _sys.exit(1)
    
    results = verify_all_reversals(filepath)
    novel_name = os.path.basename(filepath)
    print_reversal_report(results, novel_name)
