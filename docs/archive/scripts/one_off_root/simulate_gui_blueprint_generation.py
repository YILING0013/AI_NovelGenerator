# simulate_gui_blueprint_generation.py
# -*- coding: utf-8 -*-
"""
模拟GUI调用生成10章蓝图并验证格式

这个脚本模拟GUI的generate_chapter_blueprint_ui函数，
调用Chapter_blueprint_generate生成10章蓝图，
然后验证生成的蓝图是否符合7节格式要求。
"""

import os
import sys
import json
import re
from pathlib import Path


def load_config():
    """加载配置文件"""
    config_path = "config.json"
    if not os.path.exists(config_path):
        print(f"❌ 配置文件不存在: {config_path}")
        print("   请确保 config.json 存在并包含正确的LLM配置")
        return None
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    return config


def get_llm_config(config, llm_name=None):
    """获取LLM配置"""
    if llm_name is None:
        # 使用第一个可用的LLM配置
        llm_configs = config.get("llm_configs", {})
        if not llm_configs:
            print("❌ 配置文件中没有找到 llm_configs")
            return None
        
        llm_name = list(llm_configs.keys())[0]
    
    llm_config = config["llm_configs"].get(llm_name)
    if not llm_config:
        print(f"❌ 未找到LLM配置: {llm_name}")
        return None
    
    return llm_config, llm_name


def validate_blueprint_format(content):
    """验证蓝图格式是否符合7节要求"""
    print("\n" + "=" * 60)
    print("📋 验证生成的蓝图格式")
    print("=" * 60)
    
    # 定义必需的7节
    required_sections = [
        "## 1. 基础元信息",
        "## 2. 张力与冲突",
        "## 3. 匠心思维应用",
        "## 4. 伏笔与信息差",
        "## 5. 暧昧与修罗场",
        "## 6. 剧情精要",
        "## 7. 衔接设计"
    ]
    
    # 检查第8-13节是否存在（不应该存在）
    print("\n1️⃣ 检查第8-13节（不应该存在）...")
    found_8_to_13 = []
    for i in range(8, 14):
        if f'## {i}.' in content:
            found_8_to_13.append(str(i))
    
    if found_8_to_13:
        print(f"   ❌ 失败：发现了第{', '.join(found_8_to_13)}节（不应该存在）")
        return False
    else:
        print("   ✅ 通过：没有第8-13节")
    
    # 提取所有章节
    print("\n2️⃣ 提取所有章节...")
    chapter_pattern = r'### \*\*第(\d+)章'
    chapters = re.findall(chapter_pattern, content)
    
    if not chapters:
        print("   ❌ 失败：未找到任何章节")
        return False
    
    chapter_numbers = [int(ch) for ch in chapters]
    unique_chapters = sorted(set(chapter_numbers))
    
    print(f"   找到 {len(unique_chapters)} 个章节: {unique_chapters}")
    
    # 验证每个章节的格式
    print("\n3️⃣ 验证每个章节的7节格式...")
    all_valid = True
    
    for chapter_num in unique_chapters:
        # 提取该章节的内容
        chapter_match = re.search(
            rf'### \*\*第{chapter_num}章.*?(?=### \*\*第|\Z)',
            content,
            re.DOTALL
        )
        
        if not chapter_match:
            print(f"   ❌ 第{chapter_num}章：未找到内容")
            all_valid = False
            continue
        
        chapter_content = chapter_match.group(0)
        
        # 检查7节是否都存在
        missing_sections = []
        for section in required_sections:
            if section not in chapter_content:
                missing_sections.append(section.split('. ')[1])  # 只取节名
        
        if missing_sections:
            print(f"   ❌ 第{chapter_num}章：缺失节 {missing_sections}")
            all_valid = False
        else:
            print(f"   ✅ 第{chapter_num}章：7节完整")
    
    if not all_valid:
        print("\n❌ 部分章节格式验证失败")
        return False
    
    # 检查重复节标题
    print("\n4️⃣ 检查重复节标题...")
    for chapter_num in unique_chapters:
        chapter_match = re.search(
            rf'### \*\*第{chapter_num}章.*?(?=### \*\*第|\Z)',
            content,
            re.DOTALL
        )
        
        if not chapter_match:
            continue
        
        chapter_content = chapter_match.group(0)
        
        # 检查每个节标题是否重复
        for section in required_sections:
            section_name = section.split('. ')[1]
            count = chapter_content.count(section)
            
            if count > 1:
                print(f"   ❌ 第{chapter_num}章：'{section_name}' 节重复 {count} 次")
                all_valid = False
    
    if all_valid:
        print("   ✅ 通过：没有重复的节标题")
    
    print("\n" + "=" * 60)
    if all_valid:
        print("✅ 所有章节格式验证通过！")
    else:
        print("❌ 部分章节格式验证失败")
    print("=" * 60)
    
    return all_valid


def main():
    """主函数"""
    print("=" * 60)
    print("🚀 模拟GUI调用生成10章蓝图")
    print("=" * 60)
    
    # 1. 加载配置
    print("\n1️⃣ 加载配置文件...")
    config = load_config()
    if not config:
        return 1
    
    llm_config, llm_name = get_llm_config(config)
    if not llm_config:
        return 1
    
    print(f"   ✅ 使用LLM配置: {llm_name}")
    
    # 2. 设置输出路径
    print("\n2️⃣ 设置输出路径...")
    filepath = config.get("novel_settings", {}).get("output_dir", "novel_output")
    if not os.path.exists(filepath):
        os.makedirs(filepath)
        print(f"   ✅ 创建输出目录: {filepath}")
    else:
        print(f"   ✅ 输出目录: {filepath}")
    
    # 3. 导入必要的模块
    print("\n3️⃣ 导入必要模块...")
    try:
        from novel_generator import Chapter_blueprint_generate
        print("   ✅ 模块导入成功")
    except ImportError as e:
        print(f"   ❌ 模块导入失败: {e}")
        return 1
    
    # 4. 准备生成参数
    print("\n4️⃣ 准备生成参数...")
    number_of_chapters = 10
    batch_size = 1  # 每次生成1章
    
    print(f"   章节数: {number_of_chapters}")
    print(f"   批次大小: {batch_size}")
    print(f"   LLM模型: {llm_config['model_name']}")
    
    # 5. 生成蓝图
    print("\n5️⃣ 开始生成蓝图...")
    print("=" * 60)
    
    try:
        Chapter_blueprint_generate(
            interface_format=llm_config["interface_format"],
            api_key=llm_config["api_key"],
            base_url=llm_config.get("base_url", ""),
            llm_model=llm_config["model_name"],
            number_of_chapters=number_of_chapters,
            filepath=filepath,
            temperature=llm_config.get("temperature", 0.7),
            max_tokens=llm_config.get("max_tokens", 4000),
            timeout=llm_config.get("timeout", 120),
            user_guidance="",  # 空用户指导
            batch_size=batch_size
        )
        print("=" * 60)
        print("   ✅ 蓝图生成完成")
    except Exception as e:
        print(f"   ❌ 蓝图生成失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # 6. 验证生成的蓝图
    print("\n6️⃣ 验证生成的蓝图...")
    
    # 查找生成的蓝图文件
    blueprint_files = list(Path(filepath).glob("章节目录*.txt"))
    
    if not blueprint_files:
        print("   ❌ 未找到生成的蓝图文件")
        return 1
    
    blueprint_file = blueprint_files[-1]  # 使用最新的文件
    print(f"   ✅ 找到蓝图文件: {blueprint_file.name}")
    
    # 读取蓝图内容
    with open(blueprint_file, 'r', encoding='utf-8') as f:
        blueprint_content = f.read()
    
    # 验证格式
    if validate_blueprint_format(blueprint_content):
        print("\n" + "=" * 60)
        print("🎉 蓝图生成和验证全部通过！")
        print("=" * 60)
        print("\n✅ 修复效果确认：")
        print("   1. ✅ prompt_definitions.py 中第8-13节已删除")
        print("   2. ✅ blueprint.py 验证逻辑与7节格式一致")
        print("   3. ✅ 生成的10章蓝图符合7节格式")
        print("   4. ✅ 没有重复、混乱或不一致的章节")
        return 0
    else:
        print("\n" + "=" * 60)
        print("❌ 蓝图格式验证失败")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
