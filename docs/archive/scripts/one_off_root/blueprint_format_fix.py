# blueprint_format_fix.py
# -*- coding: utf-8 -*-
"""
蓝图生成格式修复脚本
彻底解决格式混乱、重复问题
"""

import os
import shutil
from datetime import datetime

def fix_prompt_definitions():
    """修复 prompt_definitions.py 中的格式问题"""

    print("=" * 60)
    print("修复 prompt_definitions.py")
    print("=" * 60)

    file_path = "prompt_definitions.py"
    backup_path = f"{file_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # 1. 备份原始文件
    print(f"1. 备份原始文件到: {backup_path}")
    shutil.copy2(file_path, backup_path)

    # 2. 读取文件
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 3. 应用修复

    # 修复 1: 替换旧的 ENHANCED_BLUEPRINT_TEMPLATE
    new_template_v3 = """
# ============================================================
# V3.0 统一的蓝图格式模板（唯一版本）
# ============================================================

BLUEPRINT_FORMAT_V3 = \"\"\"\\
第{chapter_number}章 - [章节标题]

## 1. 基础元信息
章节序号：第{chapter_number}章
章节标题：[章节标题]
定位：第[X]卷 [卷名] - 子幕[X] [子幕名]
核心功能：[一句话概括本章作用]
字数目标：[3000-5000] 字
出场角色：[列出本章角色]

## 2. 张力与冲突
冲突类型：[生存/权力/情感/理念]
核心冲突点：[具体冲突事件]
紧张感曲线：
  1. 铺垫：[起始状态]
  2. 爬升：[事件升级]
  3. 爆发：[高潮点]
  4. 回落/悬念：[收尾]

## 3. 匠心思维应用
应用场景：[本章哪里用了理性思维]
思维模式：[断代鉴定/金缮修复/揭裱重装/做旧全色/应力分析]
视觉化描述：
  错误写法：[通用描述]
  正确写法：[具体视觉奇观]
经典台词：[代表性台词]

## 4. 伏笔与信息差
本章植入伏笔：
  [伏笔内容] -> [预计在第X章揭示]
本章回收伏笔：
  [伏笔内容] <- [埋藏于第X章]
信息差控制：
  主角知道：[例如]
  敌人/路人以为：[例如]
  爽点来源：[利用信息差制造的打脸或反转]

## 5. 暧昧与修罗场
涉及女主：[姓名/不涉及]
场景类型：[心动/试探/推拉/爆发/修罗场/不涉及]
技法运用：[感官描写/环境烘托/心理独白/侧面描写]
高光细节：[具体描写一段最撩人的细节]

## 6. 剧情精要
开场：[前500字内容]
发展：
  [节点1]
  [节点2]
高潮：[本章最高能的场面]
收尾：[结尾留下的悬念]

## 7. 衔接设计
承上：[承接前文的关键情节或伏笔]
转场：[本章的转场方式]
启下：[为后续章节埋下伏笔或设置悬念]
\"\"\"
"""

    # 查找并替换 ENHANCED_BLUEPRINT_TEMPLATE
    old_enhanced = 'ENHANCED_BLUEPRINT_TEMPLATE = """'
    if old_enhanced in content:
        print("2. 找到 ENHANCED_BLUEPRINT_TEMPLATE，替换为 V3.0")
        # 找到结束位置
        end_marker = '"""'
        start_idx = content.find(old_enhanced)
        end_idx = content.find(end_marker, start_idx + len(old_enhanced))
        if end_idx == -1:
            print("   警告：找不到结束标记，跳过替换")
        else:
            content = content[:start_idx] + new_template_v3 + content[end_idx + len(end_marker):]
    else:
        print("2. 警告：未找到 ENHANCED_BLUEPRINT_TEMPLATE")

    # 修复 2: 替换旧的 BLUEPRINT_FEW_SHOT_EXAMPLE
    new_example_v3 = """
BLUEPRINT_EXAMPLE_V3 = \"\"\"\\
第1章 - 绝境处刑与金缮初现

## 1. 基础元信息
章节序号：第1章
章节标题：绝境处刑与金缮初现
定位：第1卷 凡胎重铸 - 子幕1 乱葬岗觉醒
核心功能：确立主角废柴开局的绝望感，引出灵魂穿越与天书觉醒
字数目标：4500 字
出场角色：张昊（主角）、赵刚（反派龙套）

## 2. 张力与冲突
冲突类型：生存
核心冲突点：主角被虐杀濒死 vs 天书觉醒反杀
紧张感曲线：
  1. 铺垫：被踩在泥里，遭受辱骂
  2. 爬升：骨骼碎裂，意识模糊
  3. 爆发：死亡临界，系统激活
  4. 回落/悬念：反杀成功，但明天如何面对宗门

## 3. 匠心思维应用
应用场景：赵刚挥刀斩首的瞬间，时间在主角眼中变慢
思维模式：本源透视 - 将武学解析为能量纹路
视觉化描述：
  错误写法：他看穿了破绽
  正确写法：在他眼中，赵刚那威猛的一击，全是冗余的线条。他只需要在那根最脆弱的连接点上轻轻一按
经典台词：你的灵力结构，太吵了

## 4. 伏笔与信息差
本章植入伏笔：
  玉佩碎裂 -> 在后续章节揭示其为上古阵法密钥
  能量吸收 -> 暗示混元补天录可兼容特殊能量
本章回收伏笔：
  无（开篇第一章）
信息差控制：
  主角知道：自己已经觉醒天书
  敌人/路人以为：主角是垂死挣扎的废物
  爽点来源：从被踩在泥里到一指废掉敌人手臂

## 5. 暧昧与修罗场
涉及女主：不涉及
场景类型：不涉及
技法运用：不涉及
高光细节：不涉及

## 6. 剧情精要
开场：雨夜，荒郊。泥水混合着血水。主角像死狗一样被踩在泥里
发展：
  节点1：虐杀升级，骨骼碎裂
  节点2：临界死亡，世界突然寂静
  节点3：系统激活，视觉奇观
高潮：主角一指点在红线断点，赵刚手臂炸成血雾
收尾：远处传来巡逻队的脚步声，悬念：明天怎么面对宗门的雷霆之怒

## 7. 衔接设计
承上：开篇章节，无前文承接
转场：从反杀现场到回到宗门的转场
启下：为第2章宗门审问埋下伏笔，赵刚之死引发的质疑
\"\"\"
"""

    old_example = 'BLUEPRINT_FEW_SHOT_EXAMPLE = """'
    if old_example in content:
        print("3. 找到 BLUEPRINT_FEW_SHOT_EXAMPLE，替换为 V3.0")
        start_idx = content.find(old_example)
        end_idx = content.find(end_marker, start_idx + len(old_example))
        if end_idx == -1:
            print("   警告：找不到结束标记，跳过替换")
        else:
            content = content[:start_idx] + new_example_v3 + content[end_idx + len(end_marker):]
    else:
        print("3. 警告：未找到 BLUEPRINT_FEW_SHOT_EXAMPLE")

    # 4. 写入修复后的文件
    print(f"4. 写入修复后的文件")
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print("✅ prompt_definitions.py 修复完成")
    return True


def fix_blueprint_py():
    """修复 novel_generator/blueprint.py 中的 Prompt 构建逻辑"""

    print("\n" + "=" * 60)
    print("修复 novel_generator/blueprint.py")
    print("=" * 60)

    file_path = "novel_generator/blueprint.py"
    backup_path = f"{file_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # 1. 备份
    print(f"1. 备份原始文件到: {backup_path}")
    shutil.copy2(file_path, backup_path)

    # 2. 读取文件
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 3. 应用修复
    modifications = []

    # 修复 1: 更新导入，使用新的 V3.0 格式
    old_import = 'from prompt_definitions import chunked_chapter_blueprint_prompt, BLUEPRINT_FEW_SHOT_EXAMPLE, ENHANCED_BLUEPRINT_TEMPLATE'
    new_import = 'from prompt_definitions import chunked_chapter_blueprint_prompt  # 已弃用，保留兼容性'

    if old_import in content:
        print("2. 更新导入语句")
        content = content.replace(old_import, new_import)
        modifications.append("导入语句已更新")

    # 修复 2: 简化 strict_requirements，消除重复警告
    # 这里我们只标记修改位置，实际修改需要更精确的定位
    print("3. 标记 strict_requirements 需要简化的位置")

    # 查找 strict_requirements 函数的开始
    strict_req_marker = 'strict_requirements = f"""'
    if strict_req_marker in content:
        print("   找到 strict_requirements，需要手动简化")
        modifications.append("strict_requirements 需要简化（消除重复警告）")

    # 4. 写入修复后的文件
    print(f"4. 写入修复后的文件")
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print("✅ novel_generator/blueprint.py 部分修复完成")
    print("⚠️ 注意：strict_requirements 需要手动进一步简化")

    return modifications


def main():
    """主函数"""

    print("\n")
    print("🚀 蓝图生成格式修复工具")
    print("=" * 60)
    print("开始执行修复...")
    print("")

    try:
        # 修复 prompt_definitions.py
        fix_prompt_definitions()

        # 修复 blueprint.py（部分修复）
        modifications = fix_blueprint_py()

        print("\n" + "=" * 60)
        print("修复完成总结")
        print("=" * 60)
        print("✅ prompt_definitions.py - 已修复")
        print("⚠️  novel_generator/blueprint.py - 部分修复（需手动完成）")
        print("")
        print("下一步操作：")
        print("1. 查看备份文件：prompt_definitions.py.backup_*")
        print("2. 检查修改是否符合预期")
        print("3. 手动完成 blueprint.py 中的剩余修复")
        print("4. 运行测试生成，验证格式一致性")

    except Exception as e:
        print(f"\n❌ 修复失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
