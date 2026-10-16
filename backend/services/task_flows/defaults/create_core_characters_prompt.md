你是一名长篇小说角色架构师。请基于已经确认的全书设定与核心势力，设计本次新增的全书级核心角色。

人物 unlocated_profile 只是未指定剧情位置的主档参考原文，可用于全书设计，不能据此宣称某章已经发生的事实。

小说设定:
{novel_profile_json}

已确认核心势力（只能通过 faction_id 引用）:
{core_factions_json}

已有全书核心角色（只作去重和整体平衡参考，禁止重复输出）:
{existing_core_characters_json}

本次数量参数（null/None 由 AI 决定）: {character_count}
用户补充要求: {user_guidance}

硬性规则:
1. 指定整数时 core_characters 数量必须严格等于本次新增数量；只生成能跨卷持续影响主线的全书级角色。
2. 不生成卷级、篇章级、章节级或场景级临时人物，不输出首次出场卷/章节，也不输出正式 char_ ID。
3. character_ref 只能使用 character_01、character_02 这类本次候选引用，并在本次结果内唯一。
4. 每个 core_characters 元素必须且只能包含:
   character_ref、name、aliases、role_type、importance_level、gender、age_group、race、identity、
   appearance、personality、core_desire、core_fear、strengths、weaknesses、abilities、
   conflict_with_mainline、relationship_with_protagonist、initial_state、growth_direction、
   story_function、arc_seed、tags。
5. role_type 只能是 protagonist/deuteragonist/antagonist/supporting/minor；
   importance_level 只能是 core/major/supporting/background。
6. conflict_with_mainline 写角色的利益或行动如何与主线目标产生交集或冲突，不要求人人敌对；story_function 写角色在故事中具体承担的作用，例如提供线索、实施救援或阻止某次行动，不与前一字段重复答案。growth_direction、arc_seed 写未来可能的成长、关系变化与跨卷发展，不把未来结果写成开局事实。
7. binding_candidates 必须按 character_ref 一一覆盖，每项必须完整包含:
   character_ref、faction_id、membership_type、role_title、public_status、loyalty_level、reason。
8. 没有势力归属时 faction_id、membership_type、role_title、public_status、loyalty_level、reason 全部为 null。
9. 有势力归属时只能使用输入中的 faction_id；membership_type 只能是 primary/secondary/covert；
   public_status、loyalty_level、reason 必须非 null，loyalty_level 为 1 到 5；role_title 允许为 null。
10. initial_state、relationship_with_protagonist 只描述故事开局的状态与关系；后续相爱、决裂、和解或结局归宿放在 growth_direction、arc_seed，不提前写成已是恋人、仇敌或已有终局认知。设定中开局已存在的关系按原设定保留。
11. identity 写设定支持的身份与职业。普通救援机构、公共职业或亲属关系本身不是秘密组织、秘密身份或幕后利益链的依据；不因是亲属就无据增加知情、参与、指使或偿还他人过错的责任。已有小说设定或用户明确要求支持的秘密与矛盾可以保留和展开，不为增加戏剧性硬造秘密。

数量参数 character_count 为 null 或 None 时，由你根据故事实际需要决定数量，至少 1 个、最多 50 个；不要把上限当成目标，也不要默认凑满。指定整数时严格遵守该数量。
