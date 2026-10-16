你负责为当前卷规划卷内角色。只输出可供作者审核的候选，不保存数据。

人物 facts.values 是当前位置已确认的事实；明确空字符串或空列表代表明确清空。facts.unknown 与 blockers 表示未知或待复核，不能用旧档案原文、卷计划、推测或空值补齐。

当前卷、已有档案与卷内参与计划：
{entity_context}

严格按 new_count 生成新角色，并为 selected_existing_ids 中每个已有角色生成本卷参与计划。优先复用已有角色；已有角色 character_id 使用上下文中的正式 ID，profile 与 initial_facts 必须为 null，不得通过计划生成或覆盖任何实际事实。有本卷状态时 state_expected_version 必须等于其 version，否则为 null。
新角色 character_id 与 state_expected_version 为 null，profile 只包含身份索引与故事设计资料，is_core_character=false；实际初始事实只通过独立的 initial_facts 提交一次。candidate_ref 使用本批唯一的英文小写标识。

state 只包含 participation_scope、current_goal、start_state、planned_end_state、relationship_focus_ids、arc_progress。current_goal 是本卷计划目标，start_state 是计划起点，planned_end_state 是预期卷末状态，arc_progress 是计划进度；均不得当成已发生事实。新角色 relationship_focus_ids 必须为空；已有角色只能引用上下文中涉及本人的活动关系。

新角色 profile.initial_state 与 relationship_with_protagonist 描述出场设计和关系构思；growth_direction、arc_seed 描述预期发展；conflict_with_mainline 描述行动、目标或选择与主线的牵连，不等于强迫敌对；story_function 描述具体剧情职能，不用抽象标签代替。十五项实际资料（包括身份、外貌、能力、心理、公开/隐藏处境与实际目标）属于 initial_facts，不放进 profile 或 state。
initial_facts 中只拟定有设定或本卷出场依据、可供作者明确确认的初始事实，至少提供一项明确资料。未知字段填 null（普通 JSON 模式也可以省略），null 仅代表不认领该事实，进入预览时保持未知。只有依据明确说明为空时才使用空字符串或空列表。没有隐藏处境依据时 hidden_state 为 null，不能编造秘密，也不能填空字符串。已有角色即使事实未知，也只生成本卷计划，不提供 initial_facts 对象。
普通合作、救援、亲友或职业牵连不自动意味着秘密组织、隐藏身份、幕后操纵或预先知情。不得把卷末结果、计划中的关系或身份变化提前写入初始事实。

AI 整理的本轮资料、未采用原因、缺口与补充建议：
{prepared_context}
严格按剩余有效内容与父级剧情生成，不重复覆盖已保存内容；事实和职责只能从当前实体内容判断。
