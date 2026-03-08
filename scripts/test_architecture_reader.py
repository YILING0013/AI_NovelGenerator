# -*- coding: utf-8 -*-
"""
测试 ArchitectureReader 的功能
验证是否能正确从 Novel_architecture.txt 中提取"程序员思维"、"暧昧技法"等章节
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from novel_generator.architecture_reader import ArchitectureReader

def test_reader():
    # 模拟架构文件内容
    mock_content = """#=== 0) 小说设定 ===
主题：五行混元诀
...

#=== 5) 程序员思维→奇幻能力转化体系 ===

## 核心理念：代码即法则

将编程概念映射为修仙体系，打造独一无二的战斗逻辑：

### 能力转化对照表
| 编程概念 | 奇幻转化 |
|---------|---------|
| Debug | 法则感知 |
...

#=== 11) 暧昧香艳场景设计原则 ===

## 核心理念：极致撩拨，点到为止

在平台监管底线内，将暧昧情愫写到极致...

## 场景尺度控制表
...
"""
    
    # 1. 初始化Reader
    reader = ArchitectureReader(mock_content)
    
    # 2. 测试 get_section
    print("-" * 50)
    print("测试 get_section('程序员思维')...")
    prog_section = reader.get_section("程序员思维")
    if prog_section and "代码即法则" in prog_section:
        print("✅ 程序员思维章节提取成功")
        # print(prog_section[:100] + "...")
    else:
        print("❌ 程序员思维章节提取失败")
        
    # 3. 测试 get_dynamic_guidelines
    print("-" * 50)
    print("测试 get_dynamic_guidelines()...")
    guidelines = reader.get_dynamic_guidelines()
    
    if "程序员思维" in guidelines and "暧昧香艳" in guidelines:
        print("✅ 动态指导原则提取成功")
        print("包含关键词: 程序员思维, 暧昧香艳")
    else:
        print("❌ 动态指导原则提取失败")
        print(f"提取结果: {guidelines[:100]}...")

    # 4. 测试以文件路径加载（集成测试）
    print("-" * 50)
    print("集成测试: 读取实际 Novel_architecture.txt...")
    real_arch_path = r"c:\Users\tcui\Documents\GitHub\AI_NovelGenerator\wxhyj\Novel_architecture.txt"
    if os.path.exists(real_arch_path):
        with open(real_arch_path, 'r', encoding='utf-8') as f:
            content = f.read()
        real_reader = ArchitectureReader(content)
        real_guidelines = real_reader.get_dynamic_guidelines()
        
        print(f"提取到的指导原则长度: {len(real_guidelines)} 字符")
        if "程序员思维" in real_guidelines:
            print("✅ 从实际文件中检测到 [程序员思维]")
        else:
            print("⚠️ 未从实际文件中检测到 [程序员思维]")
            
        if "暧昧" in real_guidelines:
            print("✅ 从实际文件中检测到 [暧昧]")
        else:
            print("⚠️ 未从实际文件中检测到 [暧昧]")
    else:
        print("⚠️ 实际文件不存在，跳过集成测试")

if __name__ == "__main__":
    test_reader()
