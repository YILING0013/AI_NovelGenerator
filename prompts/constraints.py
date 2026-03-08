# prompts/constraints.py
# -*- coding: utf-8 -*-
"""
公共约束模块 - 只定义一次，所有prompt引用
"""

# ============== 格式约束 ==============
FORMAT_CONSTRAINTS = """
【格式硬性规定】⚠️ 违反以下任一条视为生成失败：
1. 仅返回章节正文文本，不要任何额外说明
2. 禁止使用任何Markdown符号：**、##、#、*、```等
3. 章节标题格式必须为：第X章 标题名（无任何符号装饰）
4. 不使用分章节小标题
"""

# ============== 字数约束模板 ==============
WORD_COUNT_TEMPLATE = """
【字数硬性要求】
- 本章字数必须达到{word_number}字以上（硬性下限）
- 低于此字数视为未完成，需继续补充内容直至达标
- 写完所有情节后若字数不足，应扩展细节描写、对话或心理活动
"""

# ============== 语言纯度约束 ==============
LANGUAGE_PURITY = """
【语言规范】
1. 严格使用纯中文写作：所有内容必须使用中文表达，禁止中英文混用
2. 专有名词除外：品牌名、人名、地名等专有名词可保持原文
3. 零容忍省略：绝对禁止使用任何形式的省略表达

❌ 禁止：
- "他 suddenly 站了起来" → ✅ "他突然站了起来"
- "由于篇幅限制，此处省略..." → ✅ 完整写出

🔄 常见替换：
suddenly→突然 | quickly→迅速 | slowly→缓缓 | carefully→仔细
"""

# ============== 反重复约束 ==============
ANTI_REPETITION = """
【反重复约束】
绝对禁止重复以下内容：
1. 系统签到奖励的完整描述（如"恭喜宿主获得..."的完整列表）
2. 属性面板/状态面板的完整展示（可简短提及数值变化，禁止全文复述）
3. 内心宣言式独白（如"废柴已死，我要改写命运"类的觉醒宣言）
4. 功法/丹药效果的详细说明（首次出现时可详述，后续仅用效果词概括）
5. 相同场景的重复描写

正确做法：新章节直接推进剧情，引用前文用一句话概括即可。
"""

# ============== 组合函数 ==============
def get_common_constraints(word_number: int = 3500) -> str:
    """获取组合后的公共约束"""
    return (
        FORMAT_CONSTRAINTS + 
        WORD_COUNT_TEMPLATE.format(word_number=word_number) + 
        LANGUAGE_PURITY
    )

def get_chapter_constraints(word_number: int = 3500, include_anti_repetition: bool = False) -> str:
    """获取章节生成约束"""
    constraints = get_common_constraints(word_number)
    if include_anti_repetition:
        constraints += ANTI_REPETITION
    return constraints
