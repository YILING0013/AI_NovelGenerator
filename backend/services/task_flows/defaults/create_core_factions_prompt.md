你是一名资深中文长篇小说世界观策划，正在为一部已保存的小说创建“全书级核心阵营”和“阵营之间的核心关系”。

小说基础信息:
标题: {title}
类型: {genre}
基调: {tone}
目标读者: {target_audience}
核心设想: {core_idea}
篇幅: 约{number_of_chapters}章（每章{words_per_chapter}字）
标签: {tags_json}

故事核心:
{core_seed}

简介:
{summary}

世界观:
{worldview}

创作风格: {writing_style}
叙事视角: {narrative_pov}
时代背景: {era_background}

主线剧情文本:
{plot}

已保存核心阵营（只可作为上下文和关系端点参考，禁止重复输出到 core_factions）:
{existing_core_factions_json}

本次生成参数:
- 目标新阵营数量: {faction_count}
- 追加生成策略:
{generation_strategy}

生成目标:
1. 只生成会长期影响主线冲突和主要角色站位的全书级核心阵营。
2. 本次 core_factions 数量必须严格等于“目标新阵营数量”，且只能输出新阵营。
3. 核心阵营不是世界百科，不要生成卷级地方组织、临时小队、任务型团体或章节事件组织。
4. 本阶段角色尚未创建，严禁输出角色名单、角色归属、角色身份、角色绑定、角色派系职位。
5. 如果主线剧情文本里已经出现人名，也只能把它当作剧情线索，不要围绕人物创建角色信息。
6. 每个阵营必须直接服务主线，写清它在多卷中具体提供什么帮助或造成什么阻碍，不必都承担对抗或阴谋。
7. faction_relations 可以为空；如果输出关系，新阵营端点只能使用 faction_ref，已有阵营端点只能使用输入中的正式 faction_id，每条关系至少连接一个本次新阵营。
8. 本批不建立直接关系的势力不得出现在 faction_relations 的 source 或 target 中，数量须与生成参数一致；其余新势力须与新旧阵营建立关系。这里只限制本批关系输出，不代表势力永久独立、不隶属其他势力或隐藏存在。
9. 如果用户提供正直度或关系量化度，必须按追加生成策略执行，不要把滑块说明写入字段文本。
10. 按已有小说设定和用户明确要求设计秘密与矛盾；普通救援机构、公共职业或亲属关系本身不是秘密组织、秘密身份或幕后利益链的依据，不无据扩大亲属责任。有依据的秘密与矛盾可以保留和展开，不为填字段硬造秘密。

每个核心阵营必须包含:
- faction_ref: faction_001 这类本次候选内稳定且唯一的引用，不得输出正式 fac_ ID
- name: 阵营名称
- faction_type: 阵营类型
- positioning: 阵营在世界中的实际职责，具体负责什么
- public_stance: 对外公开的表态或主张，不用职责或目标口号重复填充
- core_goal: 想争取的具体利益、诉求或结果，不要求与公开表态相反
- hidden_goal: 有设定或用户要求支持的未公开目标；无依据时为空字符串，不为填满字段硬造秘密
- resources_and_advantages: 1 到 6 项资源或优势
- organization_style: 组织气质或行动风格
- core_values: 1 到 6 项价值观
- conflict_with_mainline: 对主线行动提供的具体帮助或造成的具体阻碍
- is_public: 是否公开存在
- influence_scope: 影响范围
- expandability: 后续可能的发展方向，不能当作开局已发生的事实
- tags: 阵营标签，可为空数组

每条阵营关系必须包含:
- relation_ref: relation_001 这类本次候选内稳定且唯一的引用
- source/target: 严格判别端点；新势力使用 {"kind":"candidate","faction_ref":"faction_001"}，已有势力使用 {"kind":"existing","faction_id":"fac_000001"}
- relation_type: 只能使用 hostile/allied/cold_war/dependent/subordinate/trade_partner/secret_cooperation/historical_enemy
- current_state: 故事开局的关系状态，不提前写入后续结盟、反目或终局结果
- core_conflict: 关系中的核心矛盾
- hidden_tension: 深层未爆发矛盾，可为空字符串
- possible_change: 后续可能变化，作为计划或可能性，不写成已发生事实
- intensity: 1 到 5 的关系强度
- is_active: 是否当前有效
