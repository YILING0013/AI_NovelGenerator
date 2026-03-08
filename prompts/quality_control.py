# prompts/quality_control.py
# -*- coding: utf-8 -*-
"""
质量控制相关Prompt和配置
"""

# ============== 评分Prompt ==============
SCORING_PROMPT = """
请对以下章节内容进行质量评分（满分10分）：

章节内容：
{chapter_text}

评分维度：
1. 情节推进（2分）：是否有实质性剧情发展
2. 人物塑造（2分）：角色是否立体、对话是否自然
3. 文笔质量（2分）：语言是否流畅、描写是否生动
4. 悬念设置（2分）：是否有吸引读者继续阅读的钩子
5. 格式规范（2分）：是否符合格式要求、无污染

扣分项（每项-0.5至-2分）：
- 描写堆砌：过度使用形容词、修辞滥用
- 情节重复：与前文内容重复
- 章节第一句没有时间/空间/情感过渡词
- Markdown符号污染

请输出JSON格式：
{{
    "总分": X.X,
    "各维度得分": {{"情节推进": X, "人物塑造": X, "文笔质量": X, "悬念设置": X, "格式规范": X}},
    "问题描述": "简要描述发现的问题",
    "修改建议": "具体可操作的修改建议"
}}
"""

# ============== 改进计划Prompt ==============
IMPROVEMENT_PROMPT = """
根据以下问题反馈，生成具体的改进计划：

当前问题：
{problem_description}

修改建议：
{improvement_suggestions}

请输出详细的改进措施，包括：
1. 需要修改的具体位置
2. 具体的修改内容
3. 预期改进效果
"""

# ============== 质量阈值配置 ==============
QUALITY_CONFIG = {
    "DEFAULT_QUALITY_THRESHOLD": 8.5,
    "MAX_ITERATIONS": 5,
    "MIN_ACCEPTABLE_SCORE": 7.0,
    "WORD_COUNT_ADJUST_SCORE_TOLERANCE": 0.5,
}

# ============== 三层钩子系统 ==============
HOOK_SYSTEM = """
【三层钩子系统 - 强制验证】
本章必须包含以下三层钩子，缺一不可：

🔥 即时钩子（本章末尾100-200字内必须设置）
  - 类型：悬念式/反转式/暧昧打断式/危机降临式
  - 效果：读者必须产生「不点下一章会死」的冲动

⚡ 中期钩子（本章必须推进至少一条）
  - 可推进：复仇线/升级目标/女主关系/宗门斗争/身世探索

🌟 长期钩子（本章必须埋下/呼应/加深）
  - 核心伏笔：身世之谜/终极BOSS/世界真相/系统本质
"""

# ============== 节奏控制公式 ==============
PACING_FORMULA = """
【节奏控制公式】防止爽点疲劳
周期位置 = (章节号 - 1) % 7 + 1
├── 位置1-3：压制期 → 困境、挫折（禁止大爽点）
├── 位置4：爆发期 → 打脸、逆袭、升级（必须有大爽点）
├── 位置5：余韵期 → 情感沉淀、暧昧推进
├── 位置6-7：铺垫期 → 新线开启、关系深化
"""

def get_rhythm_position(chapter_num: int) -> dict:
    """根据章节号计算节奏位置"""
    position = (chapter_num - 1) % 7 + 1
    if position <= 3:
        return {"position": position, "phase": "压制期", "guideline": "困境、挫折（禁止大爽点）"}
    elif position == 4:
        return {"position": position, "phase": "爆发期", "guideline": "打脸、逆袭、升级（必须有大爽点）"}
    elif position == 5:
        return {"position": position, "phase": "余韵期", "guideline": "情感沉淀、暧昧推进"}
    else:
        return {"position": position, "phase": "铺垫期", "guideline": "新线开启、关系深化"}
