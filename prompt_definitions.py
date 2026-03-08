# prompt_definitions.py
# -*- coding: utf-8 -*-
"""
统一提示词定义（Phase-2 精简版）

设计目标：
1. 章节/摘要/雪花/角色状态等核心提示词统一来自 prompts/（单一真相源）。
2. 保留运行中仍在使用的“专用提示词”（蓝图批量生成、角色导入、风格增强）。
3. 保留历史兼容别名，避免脚本与旧调用崩溃。
"""

from __future__ import annotations

import prompts as _canonical_prompts
from collections.abc import Callable
from importlib import import_module
from typing import cast


# ============================================================================
# 语言纯度辅助（兼容）
# ============================================================================
def _resolve_language_purity() -> tuple[Callable[[str], str], bool]:
    try:
        module = import_module("language_purity_prompt")
        func = cast(Callable[[str], str], module.add_language_purity_constraints)
        if callable(func):
            return func, True
    except Exception:
        pass

    def fallback(prompt: str) -> str:
        return prompt + "\n\n🚨 语言要求：严格使用纯中文写作，禁止中英文混用（专有名词除外）。"

    return fallback, False


add_language_purity_constraints, LANGUAGE_PURITY_AVAILABLE = _resolve_language_purity()


# ============================================================================
# 来自 prompts/ 的核心运行时提示词与配置（单一真相源）
# ============================================================================
FORMAT_CONSTRAINTS = _canonical_prompts.FORMAT_CONSTRAINTS
WORD_COUNT_TEMPLATE = _canonical_prompts.WORD_COUNT_TEMPLATE
LANGUAGE_PURITY = _canonical_prompts.LANGUAGE_PURITY
ANTI_REPETITION = _canonical_prompts.ANTI_REPETITION
get_common_constraints = _canonical_prompts.get_common_constraints
get_chapter_constraints = _canonical_prompts.get_chapter_constraints

ENDING_STYLES = _canonical_prompts.ENDING_STYLES
BATTLE_STYLE_POOL = _canonical_prompts.BATTLE_STYLE_POOL
CULTIVATION_PROGRESS_MAP = _canonical_prompts.CULTIVATION_PROGRESS_MAP
get_cultivation_constraint = _canonical_prompts.get_cultivation_constraint
VILLAIN_DIALOGUE_STYLES = _canonical_prompts.VILLAIN_DIALOGUE_STYLES
VOLUME_MAPPING = _canonical_prompts.VOLUME_MAPPING
get_volume_info = _canonical_prompts.get_volume_info

first_chapter_draft_prompt = _canonical_prompts.first_chapter_draft_prompt
next_chapter_draft_prompt = _canonical_prompts.next_chapter_draft_prompt
summarize_recent_chapters_prompt = _canonical_prompts.summarize_recent_chapters_prompt
knowledge_search_prompt = _canonical_prompts.knowledge_search_prompt
knowledge_filter_prompt = _canonical_prompts.knowledge_filter_prompt
summary_prompt = _canonical_prompts.summary_prompt

core_seed_prompt = _canonical_prompts.core_seed_prompt
character_dynamics_prompt = _canonical_prompts.character_dynamics_prompt
world_building_prompt = _canonical_prompts.world_building_prompt
plot_architecture_prompt = _canonical_prompts.plot_architecture_prompt

create_character_state_prompt = _canonical_prompts.create_character_state_prompt
update_character_state_prompt = _canonical_prompts.update_character_state_prompt

SCORING_PROMPT = _canonical_prompts.SCORING_PROMPT
IMPROVEMENT_PROMPT = _canonical_prompts.IMPROVEMENT_PROMPT
QUALITY_CONFIG = _canonical_prompts.QUALITY_CONFIG
HOOK_SYSTEM = _canonical_prompts.HOOK_SYSTEM
PACING_FORMULA = _canonical_prompts.PACING_FORMULA
get_rhythm_position = _canonical_prompts.get_rhythm_position


# ============================================================================
# 章节风格增强模块（chapter.py / quality_loop_controller.py 运行依赖）
# ============================================================================
COT_INSTRUCTIONS = """
【结构化思考要求】
先明确本章目标（推进/反转/埋伏笔），再组织场景顺序。禁止无目标堆砌描写。
若存在多项约束，优先保证：既有设定一致性 > 本章核心冲突推进 > 伏笔回收/埋设 > 文采修饰。
至少安排1处“承接前文后果/未解问题”的推进点，避免章节像重开新局。
"""

SUBTEXT_GUIDE = """
【潜台词要求】
关键对话需体现“表层说辞 + 深层意图”，通过停顿、动作、回避回答等方式体现博弈。
"""

LITERARY_STYLE_GUIDE = """
【文风要求】
叙述要清晰、节奏有起伏；动作场景偏短句，情绪与氛围场景可适度放缓。
"""

CULTURAL_DEPTH_GUIDE = """
【世界观语言纯度】
外轨（旁白/人物对白）优先使用仙侠语汇，避免现代技术词直接破坏沉浸感。
"""

TWO_TRACK_NARRATIVE_RULE = """
【双轨叙事】
内轨：主角内心与系统界面，可保留理性分析语气。
外轨：人物对话与场景叙述，保持世界观内语言，并延续前文已成立的因果、关系与代价，不得无解释重置。
"""


# ============================================================================
# 蓝图模板（7节标准）
# ============================================================================
BLUEPRINT_FORMAT_V3 = """\
第{chapter_number}章 - [章节标题]

## 1. 基础元信息
章节序号：第{chapter_number}章
章节标题：[章节标题]
定位：[卷/子幕定位]
核心功能：[一句话概括]
字数目标：[3000-5000字]
出场角色：[角色列表]

## 2. 张力与冲突
冲突类型：[生存/利益/理念/情感]
核心冲突点：[具体事件]
紧张感曲线：铺垫 -> 爬升 -> 爆发 -> 回落

## 3. 匠心思维应用
应用场景：[本章应用点]
思维模式：[分析方式]
视觉化描述：[关键画面]
经典台词：[代表性台词]

## 4. 伏笔与信息差
本章植入伏笔：[内容 -> 预计回收]
本章回收伏笔：[如无填“无”]
信息差控制：[主角知道 / 他人误判 / 爽点来源]

## 5. 暧昧与修罗场
涉及女主：[姓名/本章不涉及]
场景类型：[心动/试探/推拉/爆发/修罗场/不涉及]
技法运用：[感官描写/环境烘托/心理独白]
高光细节：[具体细节]

## 6. 剧情精要
开场：[前500字]
发展：[节点1, 节点2]
高潮：[本章最高能场面]
收尾：[结尾悬念]

## 7. 衔接设计
承上：[承接前文]
转场：[转场方式]
启下：[为后续埋钩子]
"""

BLUEPRINT_EXAMPLE_V3 = """\
第1章 - 风雪夜的转折点

## 1. 基础元信息
章节序号：第1章
章节标题：风雪夜的转折点
定位：第1卷 序幕 - 子幕1 危机初现
核心功能：建立主角困境并触发第一次反转
字数目标：4500字
出场角色：主角、对手、目击者

## 2. 张力与冲突
冲突类型：生存
核心冲突点：主角被压制后寻找唯一破局点
紧张感曲线：铺垫 -> 爬升 -> 爆发 -> 回落

## 3. 匠心思维应用
应用场景：临界时刻完成高压判断
思维模式：结构洞察与最小代价破局
视觉化描述：从被动挨打切换到精准反制
经典台词：你最强的地方，正是你最脆的地方

## 4. 伏笔与信息差
本章植入伏笔：异常反馈 -> 后续揭示隐藏机制
本章回收伏笔：无
信息差控制：主角掌握新线索，敌人误判其无力反击

## 5. 暧昧与修罗场
涉及女主：本章不涉及
场景类型：不涉及
技法运用：不涉及
高光细节：不涉及

## 6. 剧情精要
开场：恶劣环境下主角陷入失控边缘
发展：冲突升级，关键线索出现
高潮：主角完成一次有效逆转
收尾：外部压力即将介入

## 7. 衔接设计
承上：开篇章节，无前文承接
转场：从冲突现场切换至后续追查
启下：为下一章后果发酵埋下伏笔
"""

# 历史兼容别名
BLUEPRINT_FEW_SHOT_EXAMPLE = BLUEPRINT_EXAMPLE_V3
ENHANCED_BLUEPRINT_TEMPLATE = BLUEPRINT_FORMAT_V3


# ============================================================================
# 蓝图批量生成提示词（strict_blueprint_generator 等依赖）
# 必填字段：novel_architecture/chapter_list/n/m/total_chapters/blueprint_example
# ============================================================================
chunked_chapter_blueprint_prompt = """\
请为小说生成第{n}章到第{m}章的详细章节目录。

任务范围：
- 起始章节：第{n}章
- 结束章节：第{m}章
- 共{total_chapters}章（严格按顺序生成，不多不少）

小说设定：
{novel_architecture}

已有章节（用于衔接）：
{chapter_list}

参考范例（仅学习结构深度，严禁抄袭剧情）：
{blueprint_example}

硬性规则：
1. 只生成第{n}章到第{m}章，禁止超范围章节。
2. 每章必须完整包含7个节（按模板顺序，不可省略）。
3. 标题格式必须为：第X章 - [标题]（章节号与“章”之间无空格）。
4. 每章内容必须具体可执行，禁止“略”“省略”“后续类似”。
5. 若本章不涉及女主互动，第5节必须明确写“本章不涉及”。
6. “启下”应使用“下一章/后续章节”表述，避免写具体章节号。
7. 建议补充语义锚点：张力评级、世界观锚点/知识库引用、系统机制变化（若无可写“无新增机制”）。
8. 每章必须体现“承接上一阶段的后果”与“推向后续的执行点”，禁止像重开新剧情一样另起炉灶。
9. 已经解决的冲突不要重复包装成新核心冲突；若冲突升级，必须写清升级原因与新增代价。

输出时请严格遵循 ENHANCED_BLUEPRINT_TEMPLATE 定义的7节数字格式。
"""


# ============================================================================
# Step2 运行时主链路提示词（novel_generator/blueprint.py 依赖）
# 必填字段：start_chapter/end_chapter/chapter_count/context_guide/chapter_list/
#           user_guidance/blueprint_example
# ============================================================================
STEP2_GUIDED_STRICT_BLUEPRINT_PROMPT = """\
你是一位严谨的小说蓝图架构师。请根据【生成指南】为《{novel_title}》生成**第{start_chapter}-{end_chapter}章**的详细蓝图。

### 核心参考资料（必须严格执行）
{context_guide}

### 已有章节概览
{chapter_list}

⚠️ **重要警告**：以上“已有章节概览”仅用于了解剧情连贯性，**严禁模仿其格式**！你必须严格按照下方的标准格式（7个节）生成，不能省略任何节。

{user_guidance}

📚 **参考范例**（学习其格式和深度，但严禁抄袭剧情）：

{blueprint_example}

⚠️ **重要警告**：上述范例仅用于学习格式。你现在的任务是生成 **第{start_chapter}章到第{end_chapter}章** 的内容，必须根据【生成指南】和【已有章节】继续推进剧情，**绝对禁止**复制范例中的剧情！

🚨【绝对强制性要求】🚨

1. **章节格式规范**：

每个章节必须遵循以下结构（按顺序，**每个节标题只能出现一次，所有7个节都必须存在**）：

   第X章 - [章节标题]

   ## 1. 基础元信息
   *   **章节序号**：第X章
   *   **章节标题**：[章节标题]
   *   **定位**：第N卷 [卷名] - 子幕N [子幕名]
   *   **核心功能**：[一句话概括本章作用]
   *   **字数目标**：[3000-5000] 字
   *   **出场角色**：[列出角色]

   ## 2. 张力与冲突
   *   **冲突类型**：[生存/权力/情感/理念等]
   *   **核心冲突点**：[具体冲突内容]
   *   **紧张感曲线**：[铺垫→爬升→爆发→回落/悬念]
   *   **张力评级**：[S/A/B/C 或 ★1-★5]

   ## 3. 匠心思维应用
   *   **应用场景**：[具体场景]
   *   **思维模式**：[本章核心思维模式]
   *   **视觉化描述**：[错误写法 vs 正确写法]
   *   **技法运用**：[镜头/动作/信息差/节奏等]
   *   **经典台词**：[代表性台词]

   ## 4. 伏笔与信息差
   *   **本章植入伏笔**：[列出伏笔]
   *   **本章回收伏笔**：[如有]
   *   **信息差控制**：[主角知道 vs 敌人以为]
   *   **世界观锚点/知识库引用**：[本章关联设定]

   ## 5. 暧昧与修罗场
   *   **涉及的女性角色互动**：[描述女性角色互动，如女主A、女主B等]
   *   **🚨 重要**：即使本章不涉及任何女性角色，也**必须保留此节**，并填写"本章不涉及女性角色互动"
   *   **格式要求**：
       - 如果涉及：详细描述互动内容
       - 如果不涉及：必须写"本章不涉及女性角色互动"（不能省略整个节）

   ## 6. 剧情精要
   *   **开场**：[开场场景]
   *   **发展**：[节点1、节点2、节点3...]
   *   **高潮**：[高潮事件]
   *   **收尾**：[结尾状态/悬念]
   *   **系统机制变化**：[若无则写“无新增机制”]

   ## 7. 衔接设计
   *   **承上**：[承接前文]
   *   **转场**：[转场方式]
   *   **启下**：[为后续埋下伏笔]
   *   **执行要点**：[下一章必须兑现的1-2项]

   🚨 **格式禁忌**：
   - **严禁重复任何节标题**："## 1. 基础元信息"、"## 2. 张力与冲突"等在每章中只能出现一次
   - **严禁省略任何节**：所有7个节都必须有内容，包括"暧昧与修罗场"
   - **特别强调**："暧昧与修罗场"节即使不涉及女性角色，也必须保留并填写"本章不涉及女性角色互动"
   - **严禁**在"基础元信息"中重复写"第X章 - 标题"
   - **严禁定位占位词**：不得出现“第X卷/子幕X/卷名待定/TODO/TBD”
   - **标题去重**：新章节标题必须避免与最近章节重复
   - **严禁**在正文中引用具体章节号（如"第1章"、"第50章"）
   - 只在章节开头写一次标题，后续用"本章"代替
   - 引用其他章节时，用"后续章节"、"前文"代替

2. **完整性铁律**：
   - 禁止任何省略（如"..."或"略"）。
   - 每章至少800字详细描述。
   - **每个节都必须有内容，不能省略**
   - **严禁只写3个节就结束，必须写满7个节**

3. **架构一致性**：
   - 必须使用【生成指南】中提及的角色名，严禁改名或混淆同音字。
   - 必须遵循【生成指南】中的情节锁定。

4. **批次要求**：
   - 本次生成第{start_chapter}章到第{end_chapter}章（共{chapter_count}章）
   - **严格按顺序生成**，不得跳跃或重复
   - **每章必须完整独立**，不得出现"第1章内容中混入第2章开头"的情况
   - **每章的7个节都必须完整，不能偷工减料省略后面的节**

5. **连续性铁律**：
   - 每章至少兑现1项前文遗留问题、承诺、代价或误会；若暂不兑现，必须在“启下/执行要点”中说明其继续发酵方式。
   - 已经成立的人物关系、资源归属、能力限制、伤势代价不得无解释重置。
   - 已经解决的冲突不得重复作为同形态核心冲突回炉，除非明确写出升级机制。
   - 新设定必须服务当前冲突，并在“世界观锚点/系统机制变化/执行要点”中留下后续回收接口。

请开始生成第{start_chapter}章到第{end_chapter}章：
"""


# ============================================================================
# UI 角色导入提示词（ui/role_library.py 依赖）
# ============================================================================
Character_Import_Prompt = """\
根据输入文本提取角色信息，并严格按如下结构输出：

角色名：
├──物品:
│  ├──道具名: 描述
│  └──武器名: 描述
├──能力:
│  ├──技能名: 描述
│  └──技能名: 描述
├──状态:
│  ├──身体状态: 描述
│  └──心理状态: 描述
├──主要角色间关系网:
│  ├──角色A: 关系说明
│  └──角色B: 关系说明
├──触发或加深的事件:
│  ├──事件A: 描述与影响
│  └──事件B: 描述与影响

要求：
1. 角色名不得篡改。
2. 条目使用“名称: 描述”格式。
3. 仅输出结构化结果，不要额外解释。

待分析内容：
{content}
"""


# ============================================================================
# 质量注入模块（保留兼容）
# ============================================================================
three_layer_hook_system = """
【三层钩子系统】
即时钩子：章节末尾制造下一章驱动力。
中期钩子：至少推进一条阶段主线。
长期钩子：埋设或呼应世界观级伏笔。
"""

rhythm_breathing_control = """
【节奏呼吸控制】
压制期与爆发期交替，避免连续高压或连续平铺。
"""

rhythm_position_precision = """
【节奏定位校准】
结合章节号判断本章应处于铺垫/爆发/回落哪一段。
"""

perspective_switching_guide = """
【视角切换】
关键情绪节点可切换到观察者视角放大冲击，但需保持清晰。
"""

prose_density_control = """
【行文密度】
高张力段落强调动作动词；解释段落控制篇幅，避免信息墙。
"""

female_lead_ecological_niche = """
【女性角色生态位】
女性角色需有主动决策与剧情作用，避免纯工具人。
"""

female_lead_behavior_norms = """
【行为约束】
避免单一“惊呼/担心/被救”模板化反应。
"""

word_count_enforcement = """
【字数执行】
达到最低字数要求，优先扩展冲突推进与有效细节。
"""

correct_writing_examples = """
【正向示例】
用具体动作和结果写推进，不用空泛评价代替事件。
"""

supporting_character_interaction = """
【配角参与】
关键段落必须有配角参与或反馈，避免主角长段独角戏。
"""

shuangpoint_writing_guide = """
【爽点写法】
通过铺垫-反转-反馈形成闭环，而非突兀“开挂”。
"""

top_tier_quality_checklist = """
【质量检查清单】
- 剧情是否推进
- 人物是否一致
- 伏笔是否管理
- 格式是否合规
"""

quality_control_injection = """
{three_layer_hook_system}
{rhythm_breathing_control}
{rhythm_position_precision}
{perspective_switching_guide}
{prose_density_control}
{female_lead_ecological_niche}
{female_lead_behavior_norms}
{word_count_enforcement}
{correct_writing_examples}
{supporting_character_interaction}
{shuangpoint_writing_guide}
{top_tier_quality_checklist}
"""


__all__ = [
    # prompts 源
    "FORMAT_CONSTRAINTS", "WORD_COUNT_TEMPLATE", "LANGUAGE_PURITY", "ANTI_REPETITION",
    "get_common_constraints", "get_chapter_constraints",
    "ENDING_STYLES", "BATTLE_STYLE_POOL", "CULTIVATION_PROGRESS_MAP",
    "get_cultivation_constraint", "VILLAIN_DIALOGUE_STYLES", "VOLUME_MAPPING", "get_volume_info",
    "first_chapter_draft_prompt", "next_chapter_draft_prompt",
    "summarize_recent_chapters_prompt", "knowledge_search_prompt", "knowledge_filter_prompt", "summary_prompt",
    "core_seed_prompt", "character_dynamics_prompt", "world_building_prompt", "plot_architecture_prompt",
    "create_character_state_prompt", "update_character_state_prompt",
    "SCORING_PROMPT", "IMPROVEMENT_PROMPT", "QUALITY_CONFIG", "HOOK_SYSTEM", "PACING_FORMULA",
    "get_rhythm_position",
    # 本文件专用
    "COT_INSTRUCTIONS", "SUBTEXT_GUIDE", "LITERARY_STYLE_GUIDE", "CULTURAL_DEPTH_GUIDE",
    "TWO_TRACK_NARRATIVE_RULE",
    "BLUEPRINT_FORMAT_V3", "BLUEPRINT_EXAMPLE_V3", "BLUEPRINT_FEW_SHOT_EXAMPLE",
    "ENHANCED_BLUEPRINT_TEMPLATE", "chunked_chapter_blueprint_prompt",
    "STEP2_GUIDED_STRICT_BLUEPRINT_PROMPT",
    "Character_Import_Prompt",
    "three_layer_hook_system", "rhythm_breathing_control", "rhythm_position_precision",
    "perspective_switching_guide", "prose_density_control", "female_lead_ecological_niche",
    "female_lead_behavior_norms", "word_count_enforcement", "correct_writing_examples",
    "supporting_character_interaction", "shuangpoint_writing_guide",
    "top_tier_quality_checklist", "quality_control_injection",
    "add_language_purity_constraints", "LANGUAGE_PURITY_AVAILABLE",
]
