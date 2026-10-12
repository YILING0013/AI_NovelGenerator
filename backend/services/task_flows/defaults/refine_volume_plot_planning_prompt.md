根据刚生成的卷剧情，完善当前卷的现有规划。只输出 planning、coverage_notes 和 source_conflicts，不重复输出 plot。

当前目标是卷，planning 只使用卷字段：premise、major_conflict、key_turning_points、start_state、end_state、target_chapter_count、target_word_count。只完善故事前提、主要冲突和关键转折，原有 start_state、end_state 和预算必须原样保留。不要输出篇章字段 goal、key_beats、continuity_notes 或实体 ID 数组。已有下级时这些规划文字只是建议，服务端只保存剧情。

coverage_notes 简要指出剧情如何覆盖本卷关键转折并承接下一卷；发现原卷规划与新剧情的真实冲突时明确指出，不声称已经自动解决。

source_conflicts 报告本次实际收到的已写正文与已保存旧规划之间的疑似冲突，最多 12 项。每项包含 message、saved_text、old_plan；两侧都填写 resource_type、id、field、quote。quote 必须是对应字段中非空、逐字连续的原句（最多 2000 字），message 最多 1000 字。saved_text 只引用 chapter 的 excerpt 或 content；old_plan 引用已保存小说、卷、篇章、场景或章节的 plot、planning 下的具体字段或 summary 等原文，数组字段用从 0 开始的路径，如 planning.key_beats.0。

只能引用 writing_context 实际带来的原文和 prepared_context.previous_text 中服务端实际读取的片段。当前目标旧 plot 已从 writing_context 去掉，不能补造；prepared_context 的 boundaries、coverage 等整理意见和刚生成的 plot、planning 都不是保存来源。不得把“新候选与旧规划不同”冒充“两份保存来源冲突”。不确定的真实疑点可报告并交作者核对，不宣称已经解决，不替作者确定永久来源优先级。未发现可报告项目时输出 []；没完成报告时输出 null，不能把 null 描述成没有冲突。当前只看到最近早章的末尾片段及本次另外读到的早章片段，不声称检查了当前卷全部已写正文。

原卷规划与边界：
{writing_context}

卷剧情：
{plot}

本次整理资料：
{prepared_context}
