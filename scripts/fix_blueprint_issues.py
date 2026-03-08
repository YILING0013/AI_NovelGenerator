# -*- coding: utf-8 -*-
"""
蓝图问题综合修复工具
修复深度扫描发现的所有问题
"""

import os
import re
import sys
import shutil
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from novel_generator.core.blueprint import get_blueprint


class BlueprintFixer:
    """蓝图问题修复器"""
    
    def __init__(self, project_path: str):
        self.project_path = project_path
        self.blueprint_path = os.path.join(project_path, "wxhyj", "Novel_directory.txt")
        self.fixes_applied = {
            "placeholders": 0,
            "structure": 0,
            "duplicates": 0,
        }
    
    def backup(self):
        """备份蓝图文件"""
        backup_path = self.blueprint_path + ".bak2"
        if not os.path.exists(backup_path):
            shutil.copy2(self.blueprint_path, backup_path)
            print(f"✅ 已备份至: {backup_path}")
        else:
            print(f"⚠️ 备份已存在: {backup_path}")
    
    def fix_all(self):
        """修复所有问题"""
        print("=" * 60)
        print("蓝图问题综合修复")
        print("=" * 60)
        
        self.backup()
        
        with open(self.blueprint_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_len = len(content)
        
        # 1. 修复占位符
        content = self._fix_placeholders(content)
        
        # 2. 修复结构问题（通常需要手动处理，这里只标记）
        # self._identify_structure_issues()
        
        # 3. 修复重复问题（标记而非删除，避免误删）
        # self._identify_duplicates()
        
        # 写回文件
        with open(self.blueprint_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"\n📊 修复统计:")
        print(f"  占位符修复: {self.fixes_applied['placeholders']}处")
        print(f"  文件大小变化: {len(content) - original_len:+d} 字节")
        print("=" * 60)
    
    def _fix_placeholders(self, content: str) -> str:
        """
        修复占位符问题
        
        策略：
        1. `伏笔#X` -> `伏笔#AUTO_xxx` (自动编号)
        2. `第X章` -> 保留（这通常是正确的引用格式）
        """
        print("\n📌 修复占位符...")
        
        # 统计修复前的数量
        before_count = len(re.findall(r'伏笔#X', content))
        
        # 为每个 #X 生成唯一编号
        counter = [1]  # 使用列表以便在闭包中修改
        
        def replace_placeholder(match):
            # 获取上下文以生成有意义的编号
            result = f"伏笔#AUTO_{counter[0]:03d}"
            counter[0] += 1
            return result
        
        # 替换 伏笔#X
        content = re.sub(r'伏笔#X', replace_placeholder, content)
        
        # 替换 [伏笔#X]
        def replace_bracket_placeholder(match):
            result = f"[伏笔#AUTO_{counter[0]:03d}]"
            counter[0] += 1
            return result
        
        content = re.sub(r'\[伏笔#X\]', replace_bracket_placeholder, content)
        
        after_count = len(re.findall(r'伏笔#X', content))
        fixed = before_count - after_count
        
        self.fixes_applied['placeholders'] = counter[0] - 1
        print(f"  ✅ 替换了 {self.fixes_applied['placeholders']} 处占位符")
        
        return content
    
    def identify_structure_issues(self):
        """识别结构问题（仅报告，不自动修复）"""
        print("\n📌 检查结构问题...")
        
        bp = get_blueprint(self.project_path)
        
        required_modules = [
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
            "【女主成长线推进】",
            "【质量检查清单】",
        ]
        
        issues = []
        for chapter_num in bp.iter_chapters():
            content = bp.get_chapter_content(chapter_num)
            missing = []
            for module in required_modules:
                if module not in content and f"**{module}**" not in content:
                    missing.append(module)
            if missing:
                issues.append((chapter_num, missing))
        
        if issues:
            print(f"  ⚠️ 发现 {len(issues)} 章结构不完整:")
            for ch, missing in issues[:5]:
                print(f"    第{ch}章: 缺少 {', '.join(missing[:3])}...")
        else:
            print("  ✅ 所有章节结构完整")
        
        return issues
    
    def identify_duplicates(self):
        """识别重复问题（仅报告，不自动修复）"""
        print("\n📌 检查重复问题...")
        
        bp = get_blueprint(self.project_path)
        chapters = list(bp.iter_chapters())
        
        duplicates = []
        for i in range(len(chapters) - 1):
            ch1, ch2 = chapters[i], chapters[i + 1]
            content1 = bp.get_chapter_content(ch1)
            content2 = bp.get_chapter_content(ch2)
            
            # 提取关键对话
            dialogs1 = set(re.findall(r'关键对话[：:]\s*(.+?)(?=\n|$)', content1))
            dialogs2 = set(re.findall(r'关键对话[：:]\s*(.+?)(?=\n|$)', content2))
            
            if dialogs1 and dialogs2:
                overlap = dialogs1 & dialogs2
                if overlap:
                    duplicates.append((ch1, ch2, list(overlap)[0][:50]))
        
        if duplicates:
            print(f"  ⚠️ 发现 {len(duplicates)} 对重复:")
            for ch1, ch2, sample in duplicates[:5]:
                print(f"    第{ch1}章 ↔ 第{ch2}章: \"{sample}...\"")
        else:
            print("  ✅ 未发现内容重复")
        
        return duplicates


def main():
    project_path = r"c:\Users\tcui\Documents\GitHub\AI_NovelGenerator"
    
    fixer = BlueprintFixer(project_path)
    
    # 先识别问题
    print("\n" + "=" * 60)
    print("问题识别阶段")
    print("=" * 60)
    fixer.identify_structure_issues()
    fixer.identify_duplicates()
    
    # 执行修复
    print("\n" + "=" * 60)
    print("自动修复阶段")
    print("=" * 60)
    fixer.fix_all()


if __name__ == "__main__":
    main()
