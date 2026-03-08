# analyze_chapters_201_205.py
# -*- coding: utf-8 -*-
"""
使用LLM一致性检查器分析第201-205章
"""

import json
import sys
import os

# 确保可以导入项目模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from llm_adapters import create_llm_adapter
from llm_consistency_checker import create_consistency_checker
from llm_quality_evaluator import create_quality_evaluator

def load_config():
    """加载配置"""
    with open('config.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def load_chapter(chapter_num):
    """加载章节内容"""
    filepath = f"wxhyj/chapters/chapter_{chapter_num}.txt"
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    return None

def main():
    print("=" * 60)
    print("第201-205章 深度一致性分析")
    print("=" * 60)
    
    # 加载配置
    config = load_config()
    
    # 使用智谱AI GLM-4.6作为分析LLM
    llm_config = config['llm_configs']['智谱AI GLM-4.6']
    
    print(f"\n使用模型: {llm_config['model_name']}")
    print(f"接口格式: {llm_config['interface_format']}")
    
    # 创建LLM适配器
    llm_adapter = create_llm_adapter(
        interface_format=llm_config['interface_format'],
        base_url=llm_config['base_url'],
        model_name=llm_config['model_name'],
        api_key=llm_config['api_key'],
        temperature=0.3,  # 分析使用低温度
        max_tokens=8192,
        timeout=llm_config['timeout']
    )
    
    # 创建一致性检查器和质量评估器
    consistency_checker = create_consistency_checker(llm_adapter)
    quality_evaluator = create_quality_evaluator(llm_adapter)
    
    # 加载章节
    chapters = {}
    for i in range(201, 206):
        content = load_chapter(i)
        if content:
            chapters[i] = content
            print(f"✓ 已加载第{i}章 ({len(content)}字)")
    
    # 构建前文摘要
    previous_summary = """
    前情提要(第200章及之前):
    - 张昊与同伴们进入上古战争堡垒"审判天舟"
    - 遭遇强大的"神谕者"和"清理程序"攻击
    - 在生死关头,张昊觉醒了更强的力量,击退敌人
    - 但危机并未解除,天舟深处有更强大的存在苏醒
    """
    
    # 角色状态
    character_state = """
    主要角色状态:
    - 张昊: 混沌之主,刚完成"意志归一",体力透支严重
    - 苏清雪: 太上冰心传人,本源消耗巨大
    - 魔心莲: 魔道修士,与苏清雪形成对比,同样虚弱
    - 萧尘: 返祖者领袖,受伤严重
    - 张天衡: 张家前代家主(张昊大伯),被认为已死
    - 张啸天: 张昊父亲,失踪多年
    """
    
    all_reports = {}
    
    # 逐章分析
    for chap_num, content in chapters.items():
        print(f"\n{'='*50}")
        print(f"分析第{chap_num}章")
        print('='*50)
        
        # 质量评估
        print("\n[1] 运行LLM质量评估...")
        quality_report = quality_evaluator.evaluate_chapter(
            chapter_content=content,
            chapter_info={'chapter_title': f'第{chap_num}章', 'word_number': len(content)},
            context=previous_summary
        )
        
        print(f"   综合评分: {quality_report.overall_score}/10")
        print(f"   维度评分:")
        for dim, score in quality_report.dimension_scores.items():
            print(f"     - {dim}: {score}")
        
        if quality_report.strengths:
            print(f"   优点:")
            for s in quality_report.strengths[:3]:
                print(f"     ✓ {s}")
        
        if quality_report.weaknesses:
            print(f"   问题:")
            for w in quality_report.weaknesses[:3]:
                print(f"     ✗ {w}")
        
        # 一致性检查
        print("\n[2] 运行LLM一致性检查...")
        consistency_report = consistency_checker.check_consistency(
            current_chapter=content,
            previous_summary=previous_summary,
            character_state=character_state,
            chapter_info={'chapter_title': f'第{chap_num}章'}
        )
        
        print(f"   一致性评分: {consistency_report.overall_score}/10")
        print(f"   通过检查: {'是' if consistency_report.passed else '否'}")
        
        if consistency_report.issues:
            print(f"   发现问题 ({len(consistency_report.issues)}个):")
            for issue in consistency_report.issues[:3]:
                print(f"     [{issue.severity}] {issue.check_type}: {issue.description[:50]}...")
        
        if consistency_report.verified_elements:
            print(f"   已验证元素:")
            for elem in consistency_report.verified_elements[:3]:
                print(f"     ✓ {elem}")
        
        # 存储报告
        all_reports[chap_num] = {
            'quality': {
                'overall_score': quality_report.overall_score,
                'dimension_scores': quality_report.dimension_scores,
                'strengths': quality_report.strengths,
                'weaknesses': quality_report.weaknesses,
                'issues_count': len(quality_report.specific_issues)
            },
            'consistency': {
                'overall_score': consistency_report.overall_score,
                'passed': consistency_report.passed,
                'issues': [{'type': i.check_type, 'desc': i.description, 'severity': i.severity} 
                          for i in consistency_report.issues],
                'verified': consistency_report.verified_elements
            }
        }
        
        # 更新前文摘要(用于下一章分析)
        previous_summary = f"第{chap_num}章摘要: {content[:500]}..."
    
    # 输出总结报告
    print("\n" + "=" * 60)
    print("综合分析报告")
    print("=" * 60)
    
    total_quality = sum(r['quality']['overall_score'] for r in all_reports.values()) / len(all_reports)
    total_consistency = sum(r['consistency']['overall_score'] for r in all_reports.values()) / len(all_reports)
    
    print(f"\n平均质量评分: {total_quality:.1f}/10")
    print(f"平均一致性评分: {total_consistency:.1f}/10")
    
    print("\n各章评分:")
    print("-" * 40)
    print(f"{'章节':<8} {'质量':<10} {'一致性':<10} {'通过':<8}")
    print("-" * 40)
    for chap_num, report in all_reports.items():
        passed = '✓' if report['consistency']['passed'] else '✗'
        print(f"第{chap_num}章   {report['quality']['overall_score']:<10.1f} {report['consistency']['overall_score']:<10.1f} {passed:<8}")
    
    # 保存报告
    report_path = "wxhyj/chapter_analysis_201_205.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(all_reports, f, ensure_ascii=False, indent=2)
    print(f"\n详细报告已保存至: {report_path}")
    
    print("\n分析完成!")

if __name__ == "__main__":
    main()
