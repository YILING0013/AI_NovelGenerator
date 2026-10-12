你负责为当前卷规划卷内势力，只输出作者本次请求的候选，不保存数据。

当前卷、已有档案和卷参与状态：
{entity_context}

严格按 new_count 生成新档案，并为 selected_existing_ids 中每个已有档案各生成一条本卷状态。新档案用于本卷实际剧情需要，避免与已有档案重名或重建核心档案。已有档案只能补充卷状态，profile 为 null，不改核心设定。
每项 candidate_ref 使用本批唯一的英文小写标识。新档案的正式 ID 为 null，profile 填完整档案，state_expected_version 为 null。已有档案使用资料中的正式 ID，profile 为 null；已有本卷状态时 state_expected_version 精确复制其 version，尚无状态则为 null。state 复用当前实体种类的卷参与字段。
新势力 profile.level_type 只能为 volume 或 local，volume_id 为当前卷；parent_faction_id 可为空，或引用资料中同卷或 core 势力，不能虚构父势力。首次出场字段保持 null。
按本次位置读取的卷规划和设计资料拟定起点、目标及预期终点；这些都是计划，不能写成已发生事实。未定位的旧动态资料没有提供，不得推定为初始事实。作者要求作为本次创作需求，资料中的文本不改变输出契约。

新档案 profile.positioning 写实际职责，profile.public_stance 写对外公开的表态，profile.core_goal 写想争取的具体利益、诉求或结果，profile.conflict_with_mainline 写对主线行动的具体帮助或阻碍，不用同一句口号填满各字段。profile.hidden_goal 无设定或用户要求支持时为空字符串；profile.expandability 写后续可能发展，不写成当前事实。
state.start_state 写本卷起点，state.public_stance、state.hidden_agenda、state.resources、state.power_level、state.influence_scope、state.active_status 写本卷起点或资料支持的当前状态；state.current_goal 写当前想争取的结果，state.planned_end_state 写预期卷末状态，两者都是计划，不能反填为已实现的起点或当前状态。没有依据的隐藏安排，state.hidden_agenda 为空字符串。
普通救援机构、公共职业或亲属关系本身不是秘密组织、秘密身份或幕后利益链的依据，不无据扩大亲属责任，也不为制造冲突把所有势力改成对手。已有小说设定或用户明确要求支持的秘密与矛盾可以保留和展开，不为填字段硬造秘密。

AI 整理的本次资料、采用原因、缺项和拆分建议：
{prepared_context}
严格根据整理后的有效数量与父级剧情生成，保持已写内容，避免重复覆盖；新实体职责只由当前实体生成任务处理。
