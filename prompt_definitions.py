# prompt_definitions.py
# -*- coding: utf-8 -*-
"""
集中存放所有提示词 (Prompt)，整合雪花写作法、角色弧光理论、悬念三要素模型等
并包含新增加的前三章摘要/下一章关键字提炼提示词，以及章节正文写作提示词。
"""

# =============== 生成草稿提示词当前章节摘要、知识库提炼 ===============
# 当前章节摘要生成提示词
summarize_recent_chapters_prompt = """\
作为一名专业的小说编辑和知识管理专家，正在基于已完成的前三章内容和本章信息生成当前章节的精准摘要。请严格遵循以下工作流程：
前三章内容：
{combined_text}

当前章节信息：
第{novel_number}章《{chapter_title}》：
├── 本章定位：{chapter_role}
├── 核心作用：{chapter_purpose}
├── 悬念密度：{suspense_level}
├── 伏笔操作：{foreshadowing}
├── 认知颠覆：{plot_twist_level}
└── 本章简述：{chapter_summary}

下一章信息：
第{next_chapter_number}章《{next_chapter_title}》：
├── 本章定位：{next_chapter_role}
├── 核心作用：{next_chapter_purpose}
├── 悬念密度：{next_chapter_suspense_level}
├── 伏笔操作：{next_chapter_foreshadowing}
├── 认知颠覆：{next_chapter_plot_twist_level}
└── 本章简述：{next_chapter_summary}

**上下文分析阶段**：
1. 回顾前三章核心内容：
   - 第一章核心要素：[章节标题]→[核心冲突/理论]→[关键人物/概念]
   - 第二章发展路径：[已建立的人物关系]→[技术/情节进展]→[遗留伏笔]
   - 第三章转折点：[新出现的变量]→[世界观扩展]→[待解决问题]
2. 提取延续性要素：
   - 必继承要素：列出前3章中必须延续的3个核心设定
   - 可调整要素：识别2个允许适度变化的辅助设定

**当前章节摘要生成规则**：
1. 内容架构：
   - 继承权重：70%内容需与前3章形成逻辑递进
   - 创新空间：30%内容可引入新要素，但需标注创新类型（如：技术突破/人物黑化）
2. 结构控制：
   - 采用"承继→发展→铺垫"三段式结构
   - 每段含1个前文呼应点+1个新进展
3. 预警机制：
   - 若检测到与前3章设定冲突，用[!]标记并说明
   - 对开放式发展路径，提供2种合理演化方向

现在请你基于目前故事的进展，完成以下两件事：
用最多800字，写一个简洁明了的「当前章节摘要」；

请按如下格式输出（不需要额外解释）：
当前章节摘要: <这里写当前章节摘要>
"""

# 知识库相关性检索提示词
knowledge_search_prompt = """\
请基于以下当前写作需求，生成合适的知识库检索关键词：

章节元数据：
- 准备创作：第{chapter_number}章
- 章节主题：{chapter_title}
- 核心人物：{characters_involved}
- 关键道具：{key_items}
- 场景位置：{scene_location}

写作目标：
- 本章定位：{chapter_role}
- 核心作用：{chapter_purpose}
- 伏笔操作：{foreshadowing}

当前摘要：
{short_summary}

- 用户指导：
{user_guidance}

- 核心人物(可能未指定)：{characters_involved}
- 关键道具(可能未指定)：{key_items}
- 空间坐标(可能未指定)：{scene_location}
- 时间压力(可能未指定)：{time_constraint}

生成规则：

1.关键词组合逻辑：
-类型1：[实体]+[属性]（如"量子计算机 故障日志"）
-类型2：[事件]+[后果]（如"实验室爆炸 辐射泄漏"）
-类型3：[地点]+[特征]（如"地下城 氧气循环系统"）

2.优先级：
-首选用户指导中明确提及的术语
-次选当前章节涉及的核心道具/地点
-最后补充可能关联的扩展概念

3.过滤机制：
-排除抽象程度高于"中级"的概念
-排除与前3章重复率超60%的词汇

请生成3-5组检索词，按优先级降序排列。
格式：每组用"·"连接2-3个关键词，每组占一行

示例：
科技公司·数据泄露
地下实验室·基因编辑·禁忌实验
"""

# 知识库内容过滤提示词
knowledge_filter_prompt = """\
对知识库内容进行三级过滤：

待过滤内容：
{retrieved_texts}

当前叙事需求：
{chapter_info}

过滤流程：

冲突检测：

删除与已有摘要重复度＞40%的内容

标记存在世界观矛盾的内容（使用▲前缀）

价值评估：

关键价值点（❗标记）：
· 提供新的角色关系可能性
· 包含可转化的隐喻素材
· 存在至少2个可延伸的细节锚点

次级价值点（·标记）：
· 补充环境细节
· 提供技术/流程描述

结构重组：

按"情节燃料/人物维度/世界碎片/叙事技法"分类

为每个分类添加适用场景提示（如"可用于XX类型伏笔"）

输出格式：
[分类名称]→[适用场景]
❗/· [内容片段] （▲冲突提示）
...

示例：
[情节燃料]→可用于时间压力类悬念
❗ 地下氧气系统剩余23%储量（可制造生存危机）
▲ 与第三章提到的"永久生态循环系统"存在设定冲突
"""

# =============== 1. 核心种子设定（雪花第1层）===================
core_seed_prompt = """\
作为专业作家，请用"雪花写作法"第一步构建故事核心：
主题：{topic}
类型：{genre}
篇幅：约{number_of_chapters}章（每章{word_number}字）

请用单句公式概括故事本质，例如：
"当[主角]遭遇[核心事件]，必须[关键行动]，否则[灾难后果]；与此同时，[隐藏的更大危机]正在发酵。"

要求：
1. 必须包含显性冲突与潜在危机
2. 体现人物核心驱动力
3. 暗示世界观关键矛盾
4. 使用25-100字精准表达

仅返回故事核心文本，不要解释任何内容。
"""

# =============== 2. 角色动力学设定（角色弧光模型）===================
character_dynamics_prompt = """\
基于以下元素：
- 内容指导：{user_guidance}
- 核心种子：{core_seed}

请设计3-6个具有动态变化潜力的核心角色，每个角色需包含：
特征：
- 背景、外貌、性别、年龄、职业等
- 暗藏的秘密或潜在弱点(可与世界观或其他角色有关)

核心驱动力三角：
- 表面追求（物质目标）
- 深层渴望（情感需求）
- 灵魂需求（哲学层面）

角色弧线设计：
初始状态 → 触发事件 → 认知失调 → 蜕变节点 → 最终状态

关系冲突网：
- 与其他角色的关系或对立点
- 与至少两个其他角色的价值观冲突
- 一个合作纽带
- 一个隐藏的背叛可能性

要求：
仅给出最终文本，不要解释任何内容。
"""

# =============== 3. 世界构建矩阵（三维度交织法）===================
world_building_prompt = """\
基于以下元素：
- 内容指导：{user_guidance}
- 核心冲突："{core_seed}"

为服务上述内容，请构建三维交织的世界观：

1. 物理维度：
- 空间结构（地理×社会阶层分布图）
- 时间轴（关键历史事件年表）
- 法则体系（物理/魔法/社会规则的漏洞点）

2. 社会维度：
- 权力结构断层线（可引发冲突的阶层/种族/组织矛盾）
- 文化禁忌（可被打破的禁忌及其后果）
- 经济命脉（资源争夺焦点）

3. 隐喻维度：
- 贯穿全书的视觉符号系统（如反复出现的意象）
- 氣候/环境变化映射的心理状态
- 建筑风格暗示的文明困境

要求：
每个维度至少包含3个可与角色决策产生互动的动态元素。
仅给出最终文本，不要解释任何内容。
"""

# =============== 4. 情节架构（三幕式悬念）===================
plot_architecture_prompt = """\
基于以下元素：
- 内容指导：{user_guidance}
- 核心种子：{core_seed}
- 角色体系：{character_dynamics}
- 世界观：{world_building}

要求按以下结构设计：
第一幕（触发） 
- 日常状态中的异常征兆（3处铺垫）
- 引出故事：展示主线、暗线、副线的开端
- 关键事件：打破平衡的催化剂（需改变至少3个角色的关系）
- 错误抉择：主角的认知局限导致的错误反应

第二幕（对抗）
- 剧情升级：主线+副线的交叉点
- 双重压力：外部障碍升级+内部挫折
- 虚假胜利：看似解决实则深化危机的转折点
- 灵魂黑夜：世界观认知颠覆时刻

第三幕（解决）
- 代价显现：解决危机必须牺牲的核心价值
- 嵌套转折：至少包含三层认知颠覆（表面解→新危机→终极抉择）
- 余波：留下2个开放式悬念因子

每个阶段需包含3个关键转折点及其对应的伏笔回收方案。
仅给出最终文本，不要解释任何内容。
"""

# =============== 5. 章节目录生成（悬念节奏曲线）===================
chapter_blueprint_prompt = """\
基于以下元素：
- 内容指导：{user_guidance}
- 小说架构：
{novel_architecture}

设计{number_of_chapters}章的节奏分布：
1. 章节集群划分：
- 每3-5章构成一个悬念单元，包含完整的小高潮
- 单元之间设置"认知过山车"（连续2章紧张→1章缓冲）
- 关键转折章需预留多视角铺垫

2. 每章需明确：
- 章节定位（角色/事件/主题等）
- 核心悬念类型（信息差/道德困境/时间压力等）
- 情感基调迁移（如从怀疑→恐惧→决绝）
- 伏笔操作（埋设/强化/回收）
- 认知颠覆强度（1-5级）

输出格式示例：
第n章 - [标题]
本章定位：[角色/事件/主题/...]
核心作用：[推进/转折/揭示/...]
悬念密度：[紧凑/渐进/爆发/...]
伏笔操作：埋设(A线索)→强化(B矛盾)...
认知颠覆：★☆☆☆☆
本章简述：[一句话概括]

第n+1章 - [标题]
本章定位：[角色/事件/主题/...]
核心作用：[推进/转折/揭示/...]
悬念密度：[紧凑/渐进/爆发/...]
伏笔操作：埋设(A线索)→强化(B矛盾)...
认知颠覆：★☆☆☆☆
本章简述：[一句话概括]

要求：
- 使用精炼语言描述，每章字数控制在100字以内。
- 合理安排节奏，确保整体悬念曲线的连贯性。
- 在生成{number_of_chapters}章前不要出现结局章节。

仅给出最终文本，不要解释任何内容。
"""

chunked_chapter_blueprint_prompt = """\
基于以下元素：
- 内容指导：{user_guidance}
- 小说架构：
{novel_architecture}

需要生成总共{number_of_chapters}章的节奏分布，

当前已有章节目录（若为空则说明是初始生成）：\n
{chapter_list}

现在请设计第{n}章到第{m}的节奏分布：
1. 章节集群划分：
- 每3-5章构成一个悬念单元，包含完整的小高潮
- 单元之间设置"认知过山车"（连续2章紧张→1章缓冲）
- 关键转折章需预留多视角铺垫

2. 每章需明确：
- 章节定位（角色/事件/主题等）
- 核心悬念类型（信息差/道德困境/时间压力等）
- 情感基调迁移（如从怀疑→恐惧→决绝）
- 伏笔操作（埋设/强化/回收）
- 认知颠覆强度（1-5级）

输出格式示例：
第n章 - [标题]
本章定位：[角色/事件/主题/...]
核心作用：[推进/转折/揭示/...]
悬念密度：[紧凑/渐进/爆发/...]
伏笔操作：埋设(A线索)→强化(B矛盾)...
认知颠覆：★☆☆☆☆
本章简述：[一句话概括]

第n+1章 - [标题]
本章定位：[角色/事件/主题/...]
核心作用：[推进/转折/揭示/...]
悬念密度：[紧凑/渐进/爆发/...]
伏笔操作：埋设(A线索)→强化(B矛盾)...
认知颠覆：★☆☆☆☆
本章简述：[一句话概括]

要求：
- 使用精炼语言描述，每章字数控制在100字以内。
- 合理安排节奏，确保整体悬念曲线的连贯性。
- 在生成{number_of_chapters}章前不要出现结局章节。

仅给出最终文本，不要解释任何内容。
"""

# =============== 6. 前文摘要更新 ===================
summary_prompt = """\
以下是新完成的章节文本：
{chapter_text}

这是当前的前文摘要（可为空）：
{global_summary}

请根据本章新增内容，更新前文摘要。
要求：
- 保留既有重要信息，同时融入新剧情要点
- 以简洁、连贯的语言描述全书进展
- 客观描绘，不展开联想或解释
- 总字数控制在2000字以内

仅返回前文摘要文本，不要解释任何内容。
"""

# =============== 7. 角色状态更新 ===================
create_character_state_prompt = """\
依据当前角色动力学设定：{character_dynamics}

请生成一个角色状态文档，内容格式：
例：
张三：
├──物品:
│  ├──青衫：一件破损的青色长袍，带有暗红色的污渍
│  └──寒铁长剑：一柄断裂的铁剑，剑身上刻有古老的符文
├──能力
│  ├──技能1：强大的精神感知能力：能够察觉到周围人的心中活动
│  └──技能2：无形攻击：能够释放一种无法被视觉捕捉的精神攻击
├──状态
│  ├──身体状态: 身材挺拔，穿着华丽的铠甲，面色冷峻
│  └──心理状态: 目前的心态比较平静，但内心隐藏着对柳溪镇未来掌控的野心和不安
├──主要角色间关系网
│  ├──李四：张三从小就与她有关联，对她的成长一直保持关注
│  └──王二：两人之间有着复杂的过去，最近因一场冲突而让对方感到威胁
├──触发或加深的事件
│  ├──村庄内突然出现不明符号：这个不明符号似乎在暗示柳溪镇即将发生重大事件
│  └──李四被刺穿皮肤：这次事件让两人意识到对方的强大实力，促使他们迅速离开队伍

角色名：
├──物品:
│  ├──某物(道具)：描述
│  └──XX长剑(武器)：描述
│   ...
├──能力
│  ├──技能1：描述
│  └──技能2：描述
│   ...
├──状态
│  ├──身体状态：
│  └──心理状态：描述
│    
├──主要角色间关系网
│  ├──李四：描述
│  └──王二：描述
│   ...
├──触发或加深的事件
│  ├──事件1：描述
│  └──事件2：描述
    ...

新出场角色：
- (此处填写未来任何新增角色或临时出场人物的基本信息)

要求：
仅返回编写好的角色状态文本，不要解释任何内容。
"""

update_character_state_prompt = """\
以下是新完成的章节文本：
{chapter_text}

这是当前的角色状态文档：
{old_state}

请更新主要角色状态，内容格式：
例：
张三：
├──物品:
│  ├──青衫：一件破损的青色长袍，带有暗红色的污渍
│  └──寒铁长剑：一柄断裂的铁剑，剑身上刻有古老的符文
├──能力
│  ├──技能1：强大的精神感知能力：能够察觉到周围人的心中活动
│  └──技能2：无形攻击：能够释放一种无法被视觉捕捉的精神攻击
├──状态
│  ├──身体状态: 身材挺拔，穿着华丽的铠甲，面色冷峻
│  └──心理状态: 目前的心态比较平静，但内心隐藏着对柳溪镇未来掌控的野心和不安
├──主要角色间关系网
│  ├──李四：张三从小就与她有关联，对她的成长一直保持关注
│  └──王二：两人之间有着复杂的过去，最近因一场冲突而让对方感到威胁
├──触发或加深的事件
│  ├──村庄内突然出现不明符号：这个不明符号似乎在暗示柳溪镇即将发生重大事件
│  └──李四被刺穿皮肤：这次事件让两人意识到对方的强大实力，促使他们迅速离开队伍

角色名：
├──物品:
│  ├──某物(道具)：描述
│  └──XX长剑(武器)：描述
│   ...
├──能力
│  ├──技能1：描述
│  └──技能2：描述
│   ...
├──状态
│  ├──身体状态：
│  └──心理状态：描述
│    
├──主要角色间关系网
│  ├──李四：描述
│  └──王二：描述
│   ...
├──触发或加深的事件
│  ├──事件1：描述
│  └──事件2：描述
    ...

......

新出场角色：
- 任何新增角色或临时出场人物的基本信息，简要描述即可，不要展开，淡出视线的角色可删除。

要求：
- 请直接在已有文档基础上进行增删
- 不改变原有结构，语言尽量简洁、有条理

仅返回更新后的角色状态文本，不要解释任何内容。
"""

# =============== 8. 章节正文写作 ===================

# 8.1 第一章草稿提示
first_chapter_draft_prompt = """\
即将创作：第 {novel_number} 章《{chapter_title}》
本章定位：{chapter_role}
核心作用：{chapter_purpose}
悬念密度：{suspense_level}
伏笔操作：{foreshadowing}
认知颠覆：{plot_twist_level}
本章简述：{chapter_summary}

可用元素：
- 核心人物(可能未指定)：{characters_involved}
- 关键道具(可能未指定)：{key_items}
- 空间坐标(可能未指定)：{scene_location}
- 时间压力(可能未指定)：{time_constraint}

参考文档：
- 小说设定：
{novel_setting}

完成第 {novel_number} 章的正文，字数要求{word_number}字，至少设计下方2个或以上具有动态张力的场景：
1. 对话场景：
   - 潜台词冲突（表面谈论A，实际博弈B）
   - 权力关系变化（通过非对称对话长度体现）

2. 动作场景：
   - 环境交互细节（至少3个感官描写）
   - 节奏控制（短句加速+比喻减速）
   - 动作揭示人物隐藏特质

3. 心理场景：
   - 认知失调的具体表现（行为矛盾）
   - 隐喻系统的运用（连接世界观符号）
   - 决策前的价值天平描写

4. 环境场景：
   - 空间透视变化（宏观→微观→异常焦点）
   - 非常规感官组合（如"听见阳光的重量"）
   - 动态环境反映心理（环境与人物心理对应）

格式要求：
- 仅返回章节正文文本；
- 不使用分章节小标题；
- 不要使用markdown格式。

额外指导(可能未指定)：{user_guidance}
"""

# 8.2 后续章节草稿提示
next_chapter_draft_prompt = """\
参考文档：
└── 前文摘要：
    {global_summary}

└── 前章结尾段：
    {previous_chapter_excerpt}

└── 用户指导：
    {user_guidance}

└── 角色状态：
    {character_state}

└── 当前章节摘要：
    {short_summary}

当前章节信息：
第{novel_number}章《{chapter_title}》：
├── 章节定位：{chapter_role}
├── 核心作用：{chapter_purpose}
├── 悬念密度：{suspense_level}
├── 伏笔设计：{foreshadowing}
├── 转折程度：{plot_twist_level}
├── 章节简述：{chapter_summary}
├── 字数要求：{word_number}字
├── 核心人物：{characters_involved}
├── 关键道具：{key_items}
├── 场景地点：{scene_location}
└── 时间压力：{time_constraint}

下一章节目录
第{next_chapter_number}章《{next_chapter_title}》：
├── 章节定位：{next_chapter_role}
├── 核心作用：{next_chapter_purpose}
├── 悬念密度：{next_chapter_suspense_level}
├── 伏笔设计：{next_chapter_foreshadowing}
├── 转折程度：{next_chapter_plot_twist_level}
└── 章节简述：{next_chapter_summary}

知识库参考：（按优先级应用）
{filtered_context}

🎯 知识库应用规则：
1. 内容分级：
   - 写作技法类（优先）：
     ▸ 场景构建模板
     ▸ 对话写作技巧
     ▸ 悬念营造手法
   - 设定资料类（选择性）：
     ▸ 独特世界观元素
     ▸ 未使用过的技术细节
   - 禁忌项类（必须规避）：
     ▸ 已在前文出现过的特定情节
     ▸ 重复的人物关系发展

2. 使用限制：
   ● 禁止直接复制已有章节的情节模式
   ● 历史章节内容仅允许：
     → 参照叙事节奏（不超过20%相似度）
     → 延续必要的人物反应模式（需改编30%以上）
   ● 第三方写作知识优先用于：
     → 增强场景表现力（占知识应用的60%以上）
     → 创新悬念设计（至少1处新技巧）

3. 冲突检测：
   ⚠️ 若检测到与历史章节重复：
     - 相似度>40%：必须重构叙事角度
     - 相似度20-40%：替换至少3个关键要素
     - 相似度<20%：允许保留核心概念但改变表现形式

依据前面所有设定，开始完成第 {novel_number} 章的正文，字数要求{word_number}字，
内容生成严格遵循：
-用户指导
-当前章节摘要
-当前章节信息
-无逻辑漏洞,
确保章节内容与前文摘要、前章结尾段衔接流畅、下一章目录保证上下文完整性，

格式要求：
- 仅返回章节正文文本；
- 不使用分章节小标题；
- 不要使用markdown格式。
"""

Character_Import_Prompt = """\
根据以下文本内容，分析出所有角色及其属性信息，严格按照以下格式要求：

<<角色状态格式要求>>
1. 必须包含以下五个分类（按顺序）：
   ● 物品 ● 能力 ● 状态 ● 主要角色间关系网 ● 触发或加深的事件
2. 每个属性条目必须用【名称: 描述】格式
   例：├──青衫: 一件破损的青色长袍，带有暗红色的污渍
3. 状态必须包含：
   ● 身体状态: [当前身体状况]
   ● 心理状态: [当前心理状况]
4. 关系网格式：
   ● [角色名称]: [关系类型，如"竞争对手"/"盟友"]
5. 触发事件格式：
   ● [事件名称]: [简要描述及影响]

<<示例>>
李员外:
├──物品:
│  ├──青衫: 一件破损的青色长袍，带有暗红色污渍
│  └──寒铁长剑: 剑身有裂痕，刻有「青云」符文
├──能力:
│  ├──精神感知: 能感知半径30米内的生命体
│  └──剑气压制: 通过目光释放精神威压
├──状态:
│  ├──身体状态: 右臂有未愈合的刀伤
│  └──心理状态: 对苏明远的实力感到忌惮
├──主要角色间关系网:
│  ├──苏明远: 竞争对手，十年前的同僚
│  └──林婉儿: 暗中培养的继承人
├──触发或加深的事件:
│  ├──兵器库遇袭: 丢失三把传家宝剑，影响战力
│  └──匿名威胁信: 信纸带有檀香味，暗示内部泄密
│

请严格按上述格式分析以下内容：
<<待分析小说文本开始>>
{content}
<<待分析小说文本结束>>
"""
