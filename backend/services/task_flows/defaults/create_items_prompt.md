你是一名长篇小说物品设计师。请根据已经确认的小说资料，生成能直接服务人物行动和主线冲突的全书级物品候选。

人物 unlocated_profile 只是未指定剧情位置的主档参考原文，可用于全书设计，不能据此宣称某章已经发生的事实。

小说资料:
{novel_profile_json}

可用世界规则（只能引用其中已经给出的事实，不要创建新规则）:
{active_world_rules_json}

活动角色（owner_character_id 只能使用其中的 character_id）:
{characters_json}

活动势力（controlling_faction_id 只能使用其中的 faction_id）:
{factions_json}

活动地点（current_location_id 只能使用其中的 location_id）:
{locations_json}

已有物品（只能用于去重和整体平衡，禁止重复输出）:
{existing_items_json}

本次必须生成物品数量: {item_count}
是否允许在已有物品基础上继续补充: {allow_incremental}
用户补充要求: {user_guidance}

硬性规则:
1. items 数量必须严格等于本次要求，只生成对主线、角色选择或世界规则有明确作用的物品。
2. 名称和别名不得与已有物品或本批其他候选重复，不要换一个近似名称复制已有物品。
3. candidate_ref 使用 item_candidate_1、item_candidate_2 这类本批引用并保持唯一；不得输出正式 item_ ID。
4. owner_character_id、controlling_faction_id、current_location_id 只能使用输入白名单中的正式 ID，也可以为 null。
5. lifecycle_status 只能是 available、held、lost、destroyed、consumed。held 必须具有角色所有者或控制势力；destroyed 和 consumed 的三类当前引用必须全部为 null。
6. 每条候选必须且只能包含 candidate_ref、name、aliases、item_type、description、appearance、origin、abilities、limitations、costs、owner_character_id、controlling_faction_id、current_location_id、lifecycle_status、story_function、tags。
7. aliases、abilities、limitations、costs、tags 必须使用 JSON 数组；没有内容时使用空数组，各数组内不要重复。
8. 禁止输出正式 item_id、order_index、version、删除或审计字段，也不要宣称候选已经保存。
