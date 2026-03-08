# fix_progressive_generator.py
# -*- coding: utf-8 -*-
"""
修复 progressive_blueprint_generator.py 中的节定义错误
"""

def fix_progressive_generator():
    filepath = 'novel_generator/progressive_blueprint_generator.py'

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 修复1: 第77-83行的 required_modules
    old_modules_1 = '''        self.required_modules = {
            "## 1. 基础元信息",
            "## 2. 张力与冲突",
            "## 3. 匠心思维应用",
            "## 4. 伏笔与信息差",
            "## 6. 剧情精要",
            "## 7. 质量检查清单",
        }'''

    new_modules_1 = '''        self.required_modules = {
            "## 1. 基础元信息",
            "## 2. 张力与冲突",
            "## 3. 匠心思维应用",
            "## 4. 伏笔与信息差",
            "## 5. 暧昧与修罗场",
            "## 6. 剧情精要",
            "## 7. 衔接设计",
        }'''

    if old_modules_1 in content:
        content = content.replace(old_modules_1, new_modules_1)
        print("✅ 修复了第77-83行的 required_modules（添加了第5节，修正了第7节）")
    else:
        print("⚠️ 未找到第77-83行的 required_modules（可能已经修复）")

    # 修复2: 第860行的 required_modules
    old_modules_2 = 'required_modules = ["基础元信息", "张力与冲突", "匠心思维应用", "伏笔与信息差", "剧情精要", "质量检查清单"]'
    new_modules_2 = 'required_modules = ["基础元信息", "张力与冲突", "匠心思维应用", "伏笔与信息差", "暧昧与修罗场", "剧情精要", "衔接设计"]'

    if old_modules_2 in content:
        content = content.replace(old_modules_2, new_modules_2)
        print("✅ 修复了第860行的 required_modules（添加了第5节，修正了第7节）")
    else:
        print("⚠️ 未找到第860行的 required_modules（可能已经修复）")

    # 保存
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print("\n✅ progressive_blueprint_generator.py 修复完成")
    return True


if __name__ == "__main__":
    fix_progressive_generator()
