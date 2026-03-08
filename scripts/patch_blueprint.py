# -*- coding: utf-8 -*-
"""
蓝图内容自动补丁工具 (v4.0 - 清洁版)

使用 re.finditer 替代 re.split，逻辑更直白：
1. 找到所有章节标题的位置
2. 用位置切片获取每章内容
3. 追加补丁后重组
"""
import os
import re
import shutil

class BlueprintPatcher:
    def __init__(self, base_path):
        self.base_path = base_path
        self.blueprint_path = os.path.join(base_path, "wxhyj", "Novel_directory.txt")
        self.supplements = {
            "foreshadowing": r"C:\Users\tcui\.gemini\antigravity\brain\44192352-5549-4c32-bb88-78450efbc220\reversal_foreshadowing_supplements.md",
            "romance": r"C:\Users\tcui\.gemini\antigravity\brain\44192352-5549-4c32-bb88-78450efbc220\romance_gap_supplements.md"
        }
        self.patches = {}  # {chapter_num: [patch_texts]}

    def parse_supplements(self):
        """解析补充建议文件"""
        print("正在解析补充建议...", flush=True)
        
        # 伏笔建议
        if os.path.exists(self.supplements["foreshadowing"]):
            with open(self.supplements["foreshadowing"], 'r', encoding='utf-8') as f:
                content = f.read()
                for section in re.split(r'## 伏笔\d+：', content)[1:]:
                    m = re.search(r'第(\d+)章', section)
                    if not m:
                        continue
                    chapter_num = int(m.group(1))
                    text_m = re.search(r'\*\*建议文本\*\*：\s*\n((?:>.*\n?)+)', section, re.MULTILINE)
                    if text_m:
                        raw = text_m.group(1).replace('>', '').strip()
                        self._add_patch(chapter_num, f"\n\n【智能增强：伏笔植入】\n{raw}\n")
        
        # 暧昧建议
        if os.path.exists(self.supplements["romance"]):
            with open(self.supplements["romance"], 'r', encoding='utf-8') as f:
                content = f.read()
                for section in re.split(r'## 区间\d+：', content)[1:]:
                    loc_m = re.search(r'\*\*建议补充位置\*\*：(.*?)$', section, re.MULTILINE)
                    if not loc_m:
                        continue
                    nums = re.findall(r'\d+', loc_m.group(1))
                    if not nums:
                        continue
                    chapter_num = int(nums[0])
                    text_m = re.search(r'\*\*场景草稿\*\*：\s*\n((?:>.*\n?)+)', section, re.MULTILINE)
                    if text_m:
                        raw = text_m.group(1).replace('>', '').strip()
                        self._add_patch(chapter_num, f"\n\n【智能增强：暧昧场景】\n{raw}\n")

        print(f"DEBUG: 已加载补丁章节: {sorted(self.patches.keys())}", flush=True)

    def _add_patch(self, chapter_num, text):
        if chapter_num not in self.patches:
            self.patches[chapter_num] = []
        self.patches[chapter_num].append(text)

    def apply_patches(self):
        """
        应用补丁 - 使用 finditer 的直白逻辑：
        1. 找到所有章节标题的起始位置
        2. 每章内容 = 从当前标题到下一个标题之间的文本
        3. 如果该章需要补丁，追加到内容末尾
        """
        if not self.patches:
            print("没有需要应用的补丁", flush=True)
            return

        print(f"正在读取蓝图: {self.blueprint_path}", flush=True)
        with open(self.blueprint_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 备份（只备份一次）
        backup_path = self.blueprint_path + ".bak"
        if not os.path.exists(backup_path):
            shutil.copy2(self.blueprint_path, backup_path)
            print(f"已备份蓝图至: {backup_path}", flush=True)

        # 找到所有章节标题的位置
        header_pattern = re.compile(r'^[\s#*]*第(\d+)章[^\n]*', re.MULTILINE)
        matches = list(header_pattern.finditer(content))
        
        if not matches:
            print("❌ 未找到任何章节标题", flush=True)
            return

        print(f"DEBUG: 找到 {len(matches)} 个章节", flush=True)

        # 重建内容
        new_parts = []
        
        # 序言部分（第一个章节之前的内容）
        new_parts.append(content[:matches[0].start()])
        
        patches_applied = 0
        
        for i, m in enumerate(matches):
            chapter_num = int(m.group(1))
            
            # 本章内容 = 从当前标题开始，到下一个标题之前（或文件末尾）
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            chapter_content = content[start:end]
            
            # 如果需要打补丁
            if chapter_num in self.patches:
                for patch in self.patches[chapter_num]:
                    # 防止重复
                    if "智能增强" in chapter_content and patch[:20] in chapter_content:
                        print(f"  - 第{chapter_num}章: 跳过重复补丁", flush=True)
                    else:
                        # 在章节末尾（下一章之前）追加补丁
                        chapter_content = chapter_content.rstrip() + patch
                        patches_applied += 1
                        print(f"  - 第{chapter_num}章: 已应用补丁", flush=True)
            
            new_parts.append(chapter_content)

        # 写回文件
        with open(self.blueprint_path, 'w', encoding='utf-8') as f:
            f.write(''.join(new_parts))

        print(f"✅ 蓝图更新完成！共应用 {patches_applied} 处补丁。", flush=True)


if __name__ == "__main__":
    patcher = BlueprintPatcher(r"c:\Users\tcui\Documents\GitHub\AI_NovelGenerator")
    patcher.parse_supplements()
    patcher.apply_patches()
