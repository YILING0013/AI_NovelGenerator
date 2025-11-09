# chapter_blueprint_parser.py
# -*- coding: utf-8 -*-
import re

def parse_chapter_blueprint(blueprint_text: str):
    """
    解析整份章节蓝图文本，返回一个列表，每个元素是一个 dict：
    {
      "chapter_number": int,
      "chapter_title": str,
      "chapter_role": str,       # 本章定位
      "chapter_purpose": str,    # 核心作用
      "suspense_level": str,     # 悬念密度
      "foreshadowing": str,      # 伏笔操作
      "plot_twist_level": str,   # 认知颠覆
      "chapter_summary": str     # 本章简述
    }
    """

    # 使用Markdown标题进行分块，更准确地识别章节边界
    # 这样能确保每个块只包含一个章节的内容
    chunks = re.split(r'\n(?=###\s*\*{0,2}\*第\s*\d+\s*章)', blueprint_text.strip())

    # 移除开头的空块（如果有的话）
    if chunks and not chunks[0].strip():
        chunks = chunks[1:]
    results = []

    # 兼容多种章节标题格式
    # 例如：
    #   ### **第1章 - 紫极光下的预兆**
    #   第1章 - 紫极光下的预兆
    #   第1章 - [紫极光下的预兆]
    chapter_number_pattern = re.compile(r'^###\s*\*{0,2}\*第\s*(\d+)\s*章\s*-\s*(.*?)$')

    role_pattern     = re.compile(r'^本章定位：\s*\[?(.*)\]?$')
    purpose_pattern  = re.compile(r'^核心作用：\s*\[?(.*)\]?$')
    suspense_pattern = re.compile(r'^悬念密度：\s*\[?(.*)\]?$')
    foreshadow_pattern = re.compile(r'^伏笔操作：\s*\[?(.*)\]?$')
    twist_pattern       = re.compile(r'^认知颠覆：\s*\[?(.*)\]?$')
    summary_pattern = re.compile(r'^本章简述：\s*\[?(.*)\]?$')

    # 新增模式以匹配实际的Novel_directory.txt格式
    new_role_pattern = re.compile(r'^写作重点：\s*(.*)$')
    new_purpose_pattern = re.compile(r'^作用：\s*(.*)$')
    new_suspense_pattern = re.compile(r'^张力评级：\s*(.*)$')
    new_foreshadow_pattern = re.compile(r'^长期伏笔：\s*(.*)$')
    new_twist_pattern = re.compile(r'^递进式悬念：\s*(.*)$')

    # 扩展字段模式以捕获更多章节信息
    emotional_arc_pattern = re.compile(r'^情感弧光：\s*(.*)$')
    emotional_intensity_pattern = re.compile(r'^情感强度：\s*(.*)$')
    turning_point_pattern = re.compile(r'^关键转折点：\s*(.*)$')
    emotional_memory_pattern = re.compile(r'^情感记忆点：\s*(.*)$')
    conflict_design_pattern = re.compile(r'^冲突设计：\s*(.*)$')
    character_arc_pattern = re.compile(r'^人物弧光：\s*(.*)$')
    limitations_pattern = re.compile(r'^限制条件：\s*(.*)$')
    opening_design_pattern = re.compile(r'^开场设计：\s*(.*)$')
    climax_arrangement_pattern = re.compile(r'^高潮安排：\s*(.*)$')
    ending_strategy_pattern = re.compile(r'^收尾策略：\s*(.*)$')
    pacing_control_pattern = re.compile(r'^节奏控制：\s*(.*)$')
    main_hook_pattern = re.compile(r'^主钩子：\s*(.*)$')
    secondary_hook_pattern = re.compile(r'^次钩子：\s*(.*)$')
    style_requirements_pattern = re.compile(r'^风格要求：\s*(.*)$')
    language_features_pattern = re.compile(r'^语言特色：\s*(.*)$')
    avoidance_pattern = re.compile(r'^避免事项：\s*(.*)$')
    key_scene_pattern = re.compile(r'^关键场景：\s*(.*)$')
    foreshadowing_management_pattern = re.compile(r'^伏笔管理：\s*(.*)$')
    character_state_pattern = re.compile(r'^角色状态：\s*(.*)$')
    worldview_progression_pattern = re.compile(r'^世界观推进：\s*(.*)$')

    for chunk in chunks:
        lines = chunk.strip().splitlines()
        if not lines:
            continue

        chapter_number   = None
        chapter_title    = ""
        chapter_role     = ""
        chapter_purpose  = ""
        suspense_level   = ""
        foreshadowing    = ""
        plot_twist_level = ""
        chapter_summary  = ""

        # 扩展字段变量
        emotional_arc = ""
        emotional_intensity = ""
        turning_point = ""
        emotional_memory = ""
        conflict_design = ""
        character_arc_in_chapter = ""
        limitations = ""
        opening_design = ""
        climax_arrangement = ""
        ending_strategy = ""
        pacing_control = ""
        main_hook = ""
        secondary_hook = ""
        style_requirements = ""
        language_features = ""
        avoidance_items = ""
        key_scene = ""
        foreshadowing_management = ""
        character_state_in_chapter = ""
        worldview_progression = ""

        # 先匹配第一行（或前几行），找到章号和标题
        header_match = chapter_number_pattern.match(lines[0].strip())
        if not header_match:
            # 不符合“第X章 - 标题”的格式，跳过
            continue

        chapter_number = int(header_match.group(1))
        chapter_title  = header_match.group(2).strip()

        # 从后面的行匹配其他字段
        for line in lines[1:]:
            line_stripped = line.strip()
            if not line_stripped:
                continue

            m_role = role_pattern.match(line_stripped)
            if m_role:
                chapter_role = m_role.group(1).strip()
                continue

            m_purpose = purpose_pattern.match(line_stripped)
            if m_purpose:
                chapter_purpose = m_purpose.group(1).strip()
                continue

            m_suspense = suspense_pattern.match(line_stripped)
            if m_suspense:
                suspense_level = m_suspense.group(1).strip()
                continue

            m_foreshadow = foreshadow_pattern.match(line_stripped)
            if m_foreshadow:
                foreshadowing = m_foreshadow.group(1).strip()
                continue

            m_twist = twist_pattern.match(line_stripped)
            if m_twist:
                plot_twist_level = m_twist.group(1).strip()
                continue

            m_summary = summary_pattern.match(line_stripped)
            if m_summary:
                chapter_summary = m_summary.group(1).strip()
                continue

            # 尝试匹配新的格式字段
            if not chapter_role:
                m_role = new_role_pattern.match(line_stripped)
                if m_role:
                    chapter_role = m_role.group(1).strip()
                    continue

            if not chapter_purpose:
                m_purpose = new_purpose_pattern.match(line_stripped)
                if m_purpose:
                    chapter_purpose = m_purpose.group(1).strip()
                    continue

            if not suspense_level:
                m_suspense = new_suspense_pattern.match(line_stripped)
                if m_suspense:
                    suspense_level = m_suspense.group(1).strip()
                    continue

            if not foreshadowing:
                m_foreshadow = new_foreshadow_pattern.match(line_stripped)
                if m_foreshadow:
                    foreshadowing = m_foreshadow.group(1).strip()
                    continue

            if not plot_twist_level:
                m_twist = new_twist_pattern.match(line_stripped)
                if m_twist:
                    plot_twist_level = m_twist.group(1).strip()
                    continue

            # 如果关键张力点存在但没有章节简述，使用关键张力点作为简述
            if not chapter_summary and line_stripped.startswith("关键张力点："):
                chapter_summary = line_stripped.replace("关键张力点：", "").strip()

            # 解析扩展字段
            m_emotional_arc = emotional_arc_pattern.match(line_stripped)
            if m_emotional_arc:
                emotional_arc = m_emotional_arc.group(1).strip()
                continue

            m_emotional_intensity = emotional_intensity_pattern.match(line_stripped)
            if m_emotional_intensity:
                emotional_intensity = m_emotional_intensity.group(1).strip()
                continue

            m_turning_point = turning_point_pattern.match(line_stripped)
            if m_turning_point:
                turning_point = m_turning_point.group(1).strip()
                continue

            m_emotional_memory = emotional_memory_pattern.match(line_stripped)
            if m_emotional_memory:
                emotional_memory = m_emotional_memory.group(1).strip()
                continue

            m_conflict_design = conflict_design_pattern.match(line_stripped)
            if m_conflict_design:
                conflict_design = m_conflict_design.group(1).strip()
                continue

            m_character_arc = character_arc_pattern.match(line_stripped)
            if m_character_arc:
                character_arc_in_chapter = m_character_arc.group(1).strip()
                continue

            m_limitations = limitations_pattern.match(line_stripped)
            if m_limitations:
                limitations = m_limitations.group(1).strip()
                continue

            m_opening_design = opening_design_pattern.match(line_stripped)
            if m_opening_design:
                opening_design = m_opening_design.group(1).strip()
                continue

            m_climax_arrangement = climax_arrangement_pattern.match(line_stripped)
            if m_climax_arrangement:
                climax_arrangement = m_climax_arrangement.group(1).strip()
                continue

            m_ending_strategy = ending_strategy_pattern.match(line_stripped)
            if m_ending_strategy:
                ending_strategy = m_ending_strategy.group(1).strip()
                continue

            m_pacing_control = pacing_control_pattern.match(line_stripped)
            if m_pacing_control:
                pacing_control = m_pacing_control.group(1).strip()
                continue

            m_main_hook = main_hook_pattern.match(line_stripped)
            if m_main_hook:
                main_hook = m_main_hook.group(1).strip()
                continue

            m_secondary_hook = secondary_hook_pattern.match(line_stripped)
            if m_secondary_hook:
                secondary_hook = m_secondary_hook.group(1).strip()
                continue

            m_style_requirements = style_requirements_pattern.match(line_stripped)
            if m_style_requirements:
                style_requirements = m_style_requirements.group(1).strip()
                continue

            m_language_features = language_features_pattern.match(line_stripped)
            if m_language_features:
                language_features = m_language_features.group(1).strip()
                continue

            m_avoidance = avoidance_pattern.match(line_stripped)
            if m_avoidance:
                avoidance_items = m_avoidance.group(1).strip()
                continue

            m_key_scene = key_scene_pattern.match(line_stripped)
            if m_key_scene:
                key_scene = m_key_scene.group(1).strip()
                continue

            m_foreshadowing_management = foreshadowing_management_pattern.match(line_stripped)
            if m_foreshadowing_management:
                foreshadowing_management = m_foreshadowing_management.group(1).strip()
                continue

            m_character_state = character_state_pattern.match(line_stripped)
            if m_character_state:
                character_state_in_chapter = m_character_state.group(1).strip()
                continue

            m_worldview_progression = worldview_progression_pattern.match(line_stripped)
            if m_worldview_progression:
                worldview_progression = m_worldview_progression.group(1).strip()
                continue

        results.append({
            "chapter_number": chapter_number,
            "chapter_title": chapter_title,
            "chapter_role": chapter_role,
            "chapter_purpose": chapter_purpose,
            "suspense_level": suspense_level,
            "foreshadowing": foreshadowing,
            "plot_twist_level": plot_twist_level,
            "chapter_summary": chapter_summary,
            # 扩展字段
            "emotional_arc": emotional_arc,
            "emotional_intensity": emotional_intensity,
            "turning_point": turning_point,
            "emotional_memory": emotional_memory,
            "conflict_design": conflict_design,
            "character_arc_in_chapter": character_arc_in_chapter,
            "limitations": limitations,
            "opening_design": opening_design,
            "climax_arrangement": climax_arrangement,
            "ending_strategy": ending_strategy,
            "pacing_control": pacing_control,
            "main_hook": main_hook,
            "secondary_hook": secondary_hook,
            "style_requirements": style_requirements,
            "language_features": language_features,
            "avoidance_items": avoidance_items,
            "key_scene": key_scene,
            "foreshadowing_management": foreshadowing_management,
            "character_state_in_chapter": character_state_in_chapter,
            "worldview_progression": worldview_progression
        })

    # 按照 chapter_number 排序后返回
    results.sort(key=lambda x: x["chapter_number"])
    return results


def get_chapter_info_from_blueprint(blueprint_text: str, target_chapter_number: int):
    """
    在已经加载好的章节蓝图文本中，找到对应章号的结构化信息，返回一个 dict。
    若找不到则返回一个默认的结构。
    """
    all_chapters = parse_chapter_blueprint(blueprint_text)
    for ch in all_chapters:
        if ch["chapter_number"] == target_chapter_number:
            return ch
    # 默认返回
    return {
        "chapter_number": target_chapter_number,
        "chapter_title": f"第{target_chapter_number}章",
        "chapter_role": "",
        "chapter_purpose": "",
        "suspense_level": "",
        "foreshadowing": "",
        "plot_twist_level": "",
        "chapter_summary": "",
        # 扩展字段默认值
        "emotional_arc": "",
        "emotional_intensity": "",
        "turning_point": "",
        "emotional_memory": "",
        "conflict_design": "",
        "character_arc_in_chapter": "",
        "limitations": "",
        "opening_design": "",
        "climax_arrangement": "",
        "ending_strategy": "",
        "pacing_control": "",
        "main_hook": "",
        "secondary_hook": "",
        "style_requirements": "",
        "language_features": "",
        "avoidance_items": "",
        "key_scene": "",
        "foreshadowing_management": "",
        "character_state_in_chapter": "",
        "worldview_progression": ""
    }
