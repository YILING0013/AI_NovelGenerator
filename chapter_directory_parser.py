# chapter_blueprint_parser.py
# -*- coding: utf-8 -*-
import os
import re
from typing import Any


CHAPTER_BLUEPRINT_SPLIT_DIRNAME = "chapter_blueprints"

# 兼容 markdown 标题、加粗和中英文分隔符
CHAPTER_HEADER_PATTERN = re.compile(
    r"(?m)^(?:#+\s*)?(?:\*\*)?\s*第\s*(\d+)\s*章(?:\s*[-–—:：]\s*[^\n]*)?\s*(?:\*\*)?\s*$"
)

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

    # 使用多种章节标题格式进行分块，支持不同时期的格式变化
    # 早期章节：### **第1章 - 标题**
    # 后期章节：第1章 - 标题
    # 🆕 无标题格式：第1章)
    # 🆕 支持"章节标题："字段格式：第X章 后面可以跟任意内容或换行
    chunk_pattern = r'\n(?=###\s*\*{0,2}\*第\s*\d+\s*章|第\s*\d+\s*章\s*[-):]|第\s*\d+\s*章\b)'
    chunks = re.split(chunk_pattern, blueprint_text.strip())

    # 移除开头的空块（如果有的话）
    if chunks and not chunks[0].strip():
        chunks = chunks[1:]
    results = []

    # 兼容多种章节标题格式
    # 例如：
    #   ### **第1章 - 紫极光下的预兆**
    #   第1章 - 紫极光下的预兆
    #   第1章 - [紫极光下的预兆]
    # 支持格式1: ### **第1章 - 标题**
    chapter_number_pattern1 = re.compile(r'^###\s*\*{0,2}\*?第\s*(\d+)\s*章\s*-\s*(.*?)\*{0,2}$')

    # 支持格式2: 第1章 - 标题 (后期章节格式)
    chapter_number_pattern2 = re.compile(r'^第\s*(\d+)\s*章\s*-\s*(.*?)$')

    # 🆕 支持格式3: 第1章) (无标题格式 - 兼容早期蓝图)
    chapter_number_pattern3 = re.compile(r'^第\s*(\d+)\s*章\s*\)?$')

    role_pattern     = re.compile(r'^本章定位：\s*\[?(.*?)\]?$')
    purpose_pattern  = re.compile(r'^核心作用：\s*\[?(.*?)\]?$')
    suspense_pattern = re.compile(r'^悬念密度：\s*\[?(.*?)\]?$')
    foreshadow_pattern = re.compile(r'^伏笔操作：\s*\[?(.*?)\]?$')
    twist_pattern       = re.compile(r'^认知颠覆：\s*\[?(.*?)\]?$')
    summary_pattern = re.compile(r'^本章简述：\s*\[?(.*?)\]?$')

    # 新增模式以匹配实际的Novel_directory.txt格式
    # 🆕 添加章节标题字段解析（用于解析"章节标题：xxx"格式）
    chapter_title_field_pattern = re.compile(r'^章节标题：\s*(.*)$')
    new_role_pattern = re.compile(r'^写作重点：\s*(.*)$')
    new_purpose_pattern = re.compile(r'^作用：\s*(.*)$')
    new_suspense_pattern = re.compile(r'^张力评级：\s*(.*)$')
    new_foreshadow_pattern = re.compile(r'^长期伏笔：\s*(.*)$')
    new_twist_pattern = re.compile(r'^递进式悬念：\s*(.*)$')
    # 兼容 Novel_directory 常见字段
    legacy_role_pattern = re.compile(r'^(?:定位|章节定位)：\s*(.*)$')
    legacy_purpose_pattern = re.compile(r'^(?:核心功能|核心作用)：\s*(.*)$')
    legacy_summary_pattern = re.compile(r'^(?:核心冲突点|本章简介)：\s*(.*)$')
    legacy_suspense_pattern = re.compile(r'^(?:紧张感曲线|悬念密度)：\s*(.*)$')
    characters_involved_pattern = re.compile(r'^出场角色：\s*(.*)$')
    key_items_pattern = re.compile(r'^(?:关键道具|关键物品)：\s*(.*)$')
    scene_location_pattern = re.compile(r'^(?:空间坐标|场景地点|地点)：\s*(.*)$')
    time_constraint_pattern = re.compile(r'^(?:时间压力|时间限制)：\s*(.*)$')

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
    shuangdian_position_pattern = re.compile(r'^爽点位置：\s*(.*)$')
    word_count_pattern = re.compile(r'^字数目标：\s*(.*)$')

    # ========== 新增：增强版章节蓝图6大模块 ==========
    # 【程序员思维应用】
    programmer_thinking_pattern = re.compile(r'^本章应用：\s*(.*)$')
    programmer_scene_pattern = re.compile(r'^应用场景：\s*(.*)$')
    programmer_quote_pattern = re.compile(r'^经典台词：\s*(.*)$')
    programmer_foreshadow_pattern = re.compile(r'^预埋暗示：\s*(.*)$')
    
    # 【伏笔植入清单】
    foreshadow_plant_pattern = re.compile(r'^本章植入伏笔：\s*(.*)$')
    foreshadow_reveal_pattern = re.compile(r'^本章回收伏笔：\s*(.*)$')
    
    # 【暧昧场景设计】
    romance_female_lead_pattern = re.compile(r'^本章涉及女主：\s*(.*)$')
    romance_type_pattern = re.compile(r'^暧昧类型：\s*(.*)$')
    romance_level_pattern = re.compile(r'^暧昧等级：\s*(.*)$')
    romance_technique_pattern = re.compile(r'^技法运用：\s*(.*)$')
    romance_dialogue_pattern = re.compile(r'^关键对话：\s*(.*)$')
    romance_atmosphere_pattern = re.compile(r'^氛围描写：\s*(.*)$')
    romance_progress_pattern = re.compile(r'^暧昧进度推进：\s*(.*)$')
    
    # 【爽点密度检查】
    shuangdian_count_pattern = re.compile(r'^本章爽点数量：\s*(.*)$')
    shuangdian_list_pattern = re.compile(r'^爽点列表：\s*(.*)$')
    
    # 【女主成长线推进】
    female_lead_growth_pattern = re.compile(r'^女主成长：\s*(.*)$')
    female_lead_arc_pattern = re.compile(r'^成长弧光：\s*(.*)$')
    
    # 【质量检查清单】
    quality_check_pattern = re.compile(r'^质量检查：\s*(.*)$')
    identity_consistency_pattern = re.compile(r'^身份一致性：\s*(.*)$')
    worldview_consistency_pattern = re.compile(r'^世界观一致性：\s*(.*)$')
    emotional_coherence_pattern = re.compile(r'^情感连贯性：\s*(.*)$')

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
        characters_involved = ""
        key_items = ""
        scene_location = ""
        time_constraint = ""

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
        shuangdian_position = ""
        word_count_target = ""
        
        # 新增：增强版6大模块变量
        programmer_thinking = ""       # 程序员思维应用
        programmer_scene = ""          # 应用场景
        programmer_quote = ""          # 经典台词
        programmer_foreshadow = ""     # 预埋暗示
        foreshadow_plant = ""          # 本章植入伏笔
        foreshadow_reveal = ""         # 本章回收伏笔
        romance_female_lead = ""       # 本章涉及女主
        romance_type = ""              # 暧昧类型
        romance_level = ""             # 暧昧等级
        romance_technique = ""         # 技法运用
        romance_dialogue = ""          # 关键对话
        romance_atmosphere = ""        # 氛围描写
        romance_progress = ""          # 暧昧进度推进
        shuangdian_count = ""          # 本章爽点数量
        shuangdian_list = ""           # 爽点列表
        female_lead_growth = ""        # 女主成长
        female_lead_arc = ""           # 成长弧光
        quality_check = ""             # 质量检查
        identity_consistency = ""      # 身份一致性
        worldview_consistency = ""     # 世界观一致性
        emotional_coherence = ""       # 情感连贯性


        # 先匹配第一行（或前几行），找到章号和标题
        # 尝试格式1匹配
        header_match = chapter_number_pattern1.match(lines[0].strip())
        if not header_match:
            # 尝试格式2匹配
            header_match = chapter_number_pattern2.match(lines[0].strip())
        if not header_match:
            # 🆕 尝试格式3匹配 (无标题格式: 第X章))
            header_match = chapter_number_pattern3.match(lines[0].strip())
        if not header_match:
            # 不符合任何已知格式，跳过
            continue

        chapter_number = int(header_match.group(1))
        # 🆕 处理无标题情况 (pattern3 没有捕获组2)
        try:
            lastindex = header_match.lastindex
            has_title_group = lastindex is not None and lastindex >= 2
            chapter_title = header_match.group(2).strip() if has_title_group else ""
        except IndexError:
            chapter_title = ""

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
            # 🆕 优先处理章节标题字段（章节标题：xxx）
            if not chapter_title:
                m_title = chapter_title_field_pattern.match(line_stripped)
                if m_title:
                    chapter_title = m_title.group(1).strip()
                    continue

            if not chapter_role:
                m_role = legacy_role_pattern.match(line_stripped)
                if m_role:
                    chapter_role = m_role.group(1).strip()
                    continue

            if not chapter_role:
                m_role = new_role_pattern.match(line_stripped)
                if m_role:
                    chapter_role = m_role.group(1).strip()
                    continue

            if not chapter_purpose:
                m_purpose = legacy_purpose_pattern.match(line_stripped)
                if m_purpose:
                    chapter_purpose = m_purpose.group(1).strip()
                    continue

            if not chapter_purpose:
                m_purpose = new_purpose_pattern.match(line_stripped)
                if m_purpose:
                    chapter_purpose = m_purpose.group(1).strip()
                    continue

            if not suspense_level:
                m_suspense = legacy_suspense_pattern.match(line_stripped)
                if m_suspense:
                    suspense_level = m_suspense.group(1).strip()
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

            if not chapter_summary:
                m_summary = legacy_summary_pattern.match(line_stripped)
                if m_summary:
                    chapter_summary = m_summary.group(1).strip()
                    continue

            if not characters_involved:
                m_characters = characters_involved_pattern.match(line_stripped)
                if m_characters:
                    characters_involved = m_characters.group(1).strip()
                    continue

            if not key_items:
                m_key_items = key_items_pattern.match(line_stripped)
                if m_key_items:
                    key_items = m_key_items.group(1).strip()
                    continue

            if not scene_location:
                m_scene_location = scene_location_pattern.match(line_stripped)
                if m_scene_location:
                    scene_location = m_scene_location.group(1).strip()
                    continue

            if not time_constraint:
                m_time_constraint = time_constraint_pattern.match(line_stripped)
                if m_time_constraint:
                    time_constraint = m_time_constraint.group(1).strip()
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

            m_shuangdian_position = shuangdian_position_pattern.match(line_stripped)
            if m_shuangdian_position:
                shuangdian_position = m_shuangdian_position.group(1).strip()
                continue

            m_word_count = word_count_pattern.match(line_stripped)
            if m_word_count:
                word_count_target = m_word_count.group(1).strip()
                continue

            # ========== 新增：解析增强版6大模块字段 ==========
            # 【程序员思维应用】
            m_programmer_thinking = programmer_thinking_pattern.match(line_stripped)
            if m_programmer_thinking:
                programmer_thinking = m_programmer_thinking.group(1).strip()
                continue
            
            m_programmer_scene = programmer_scene_pattern.match(line_stripped)
            if m_programmer_scene:
                programmer_scene = m_programmer_scene.group(1).strip()
                continue
            
            m_programmer_quote = programmer_quote_pattern.match(line_stripped)
            if m_programmer_quote:
                programmer_quote = m_programmer_quote.group(1).strip()
                continue
            
            m_programmer_foreshadow = programmer_foreshadow_pattern.match(line_stripped)
            if m_programmer_foreshadow:
                programmer_foreshadow = m_programmer_foreshadow.group(1).strip()
                continue
            
            # 【伏笔植入清单】
            m_foreshadow_plant = foreshadow_plant_pattern.match(line_stripped)
            if m_foreshadow_plant:
                foreshadow_plant = m_foreshadow_plant.group(1).strip()
                continue
            
            m_foreshadow_reveal = foreshadow_reveal_pattern.match(line_stripped)
            if m_foreshadow_reveal:
                foreshadow_reveal = m_foreshadow_reveal.group(1).strip()
                continue
            
            # 【暧昧场景设计】
            m_romance_female_lead = romance_female_lead_pattern.match(line_stripped)
            if m_romance_female_lead:
                romance_female_lead = m_romance_female_lead.group(1).strip()
                continue
            
            m_romance_type = romance_type_pattern.match(line_stripped)
            if m_romance_type:
                romance_type = m_romance_type.group(1).strip()
                continue
            
            m_romance_level = romance_level_pattern.match(line_stripped)
            if m_romance_level:
                romance_level = m_romance_level.group(1).strip()
                continue
            
            m_romance_technique = romance_technique_pattern.match(line_stripped)
            if m_romance_technique:
                romance_technique = m_romance_technique.group(1).strip()
                continue
            
            m_romance_dialogue = romance_dialogue_pattern.match(line_stripped)
            if m_romance_dialogue:
                romance_dialogue = m_romance_dialogue.group(1).strip()
                continue
            
            m_romance_atmosphere = romance_atmosphere_pattern.match(line_stripped)
            if m_romance_atmosphere:
                romance_atmosphere = m_romance_atmosphere.group(1).strip()
                continue
            
            m_romance_progress = romance_progress_pattern.match(line_stripped)
            if m_romance_progress:
                romance_progress = m_romance_progress.group(1).strip()
                continue
            
            # 【爽点密度检查】
            m_shuangdian_count = shuangdian_count_pattern.match(line_stripped)
            if m_shuangdian_count:
                shuangdian_count = m_shuangdian_count.group(1).strip()
                continue
            
            m_shuangdian_list = shuangdian_list_pattern.match(line_stripped)
            if m_shuangdian_list:
                shuangdian_list = m_shuangdian_list.group(1).strip()
                continue
            
            # 【女主成长线推进】
            m_female_lead_growth = female_lead_growth_pattern.match(line_stripped)
            if m_female_lead_growth:
                female_lead_growth = m_female_lead_growth.group(1).strip()
                continue
            
            m_female_lead_arc = female_lead_arc_pattern.match(line_stripped)
            if m_female_lead_arc:
                female_lead_arc = m_female_lead_arc.group(1).strip()
                continue
            
            # 【质量检查清单】
            m_quality_check = quality_check_pattern.match(line_stripped)
            if m_quality_check:
                quality_check = m_quality_check.group(1).strip()
                continue
            
            m_identity_consistency = identity_consistency_pattern.match(line_stripped)
            if m_identity_consistency:
                identity_consistency = m_identity_consistency.group(1).strip()
                continue
            
            m_worldview_consistency = worldview_consistency_pattern.match(line_stripped)
            if m_worldview_consistency:
                worldview_consistency = m_worldview_consistency.group(1).strip()
                continue
            
            m_emotional_coherence = emotional_coherence_pattern.match(line_stripped)
            if m_emotional_coherence:
                emotional_coherence = m_emotional_coherence.group(1).strip()
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
            "characters_involved": characters_involved,
            "key_items": key_items,
            "scene_location": scene_location,
            "time_constraint": time_constraint,
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
            "character_state_in_chapter": character_state_in_chapter,
            "worldview_progression": worldview_progression,
            "shuangdian_position": shuangdian_position,
            "word_count_target": word_count_target,
            # ========== 新增：增强版6大模块字段 ==========
            # 【程序员思维应用】
            "programmer_thinking": programmer_thinking,
            "programmer_scene": programmer_scene,
            "programmer_quote": programmer_quote,
            "programmer_foreshadow": programmer_foreshadow,
            # 【伏笔植入清单】
            "foreshadow_plant": foreshadow_plant,
            "foreshadow_reveal": foreshadow_reveal,
            # 【暧昧场景设计】
            "romance_female_lead": romance_female_lead,
            "romance_type": romance_type,
            "romance_level": romance_level,
            "romance_technique": romance_technique,
            "romance_dialogue": romance_dialogue,
            "romance_atmosphere": romance_atmosphere,
            "romance_progress": romance_progress,
            # 【爽点密度检查】
            "shuangdian_count": shuangdian_count,
            "shuangdian_list": shuangdian_list,
            # 【女主成长线推进】
            "female_lead_growth": female_lead_growth,
            "female_lead_arc": female_lead_arc,
            # 【质量检查清单】
            "quality_check": quality_check,
            "identity_consistency": identity_consistency,
            "worldview_consistency": worldview_consistency,
            "emotional_coherence": emotional_coherence
        })


    # 按照 chapter_number 排序后返回
    results.sort(key=lambda x: x["chapter_number"])
    return results


def _extract_chapter_blocks(blueprint_text: str) -> list[dict[str, Any]]:
    text = str(blueprint_text or "").strip()
    if not text:
        return []

    matches = list(CHAPTER_HEADER_PATTERN.finditer(text))
    blocks: list[dict[str, Any]] = []
    for idx, match in enumerate(matches):
        chapter_number = int(match.group(1))
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        chapter_text = text[start:end].strip()
        if not chapter_text:
            continue
        blocks.append({
            "chapter_number": chapter_number,
            "content": chapter_text,
        })
    return sorted(blocks, key=lambda item: int(item["chapter_number"]))


def get_chapter_blueprint_dir(filepath: str) -> str:
    return os.path.join(str(filepath or "").strip(), CHAPTER_BLUEPRINT_SPLIT_DIRNAME)


def get_chapter_blueprint_file(filepath: str, chapter_number: int) -> str:
    return os.path.join(get_chapter_blueprint_dir(filepath), f"chapter_{int(chapter_number)}.txt")


def split_blueprint_to_chapter_files(
    filepath: str,
    blueprint_text: str,
    *,
    remove_stale: bool = False,
) -> dict[str, Any]:
    """
    将单文件目录拆分为 `chapter_blueprints/chapter_X.txt`。
    """
    output_dir = get_chapter_blueprint_dir(filepath)
    os.makedirs(output_dir, exist_ok=True)

    blocks = _extract_chapter_blocks(blueprint_text)
    written_files: list[str] = []
    written_numbers: set[int] = set()
    for block in blocks:
        chapter_number = int(block["chapter_number"])
        chapter_path = get_chapter_blueprint_file(filepath, chapter_number)
        with open(chapter_path, "w", encoding="utf-8") as f:
            f.write(str(block["content"]).strip() + "\n")
        written_files.append(chapter_path)
        written_numbers.add(chapter_number)

    removed_files: list[str] = []
    if remove_stale:
        for fname in os.listdir(output_dir):
            if not (fname.startswith("chapter_") and fname.endswith(".txt")):
                continue
            num_part = fname[len("chapter_") : -len(".txt")]
            if not num_part.isdigit():
                continue
            chapter_number = int(num_part)
            if chapter_number in written_numbers:
                continue
            stale_path = os.path.join(output_dir, fname)
            try:
                os.remove(stale_path)
                removed_files.append(stale_path)
            except OSError:
                continue

    return {
        "chapter_count": len(written_files),
        "output_dir": output_dir,
        "written_files": written_files,
        "removed_files": removed_files,
    }


def _read_text_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def load_chapter_info(
    filepath: str,
    target_chapter_number: int,
    *,
    blueprint_text_fallback: str = "",
) -> dict[str, Any]:
    """
    优先从 `chapter_blueprints/chapter_X.txt` 读取章节目录信息；
    若拆分文件不存在，再回退到 `Novel_directory.txt` 并自动拆分缓存。
    """
    chapter_number = int(target_chapter_number)
    chapter_file = get_chapter_blueprint_file(filepath, chapter_number)
    chapter_text = _read_text_file(chapter_file).strip()

    if not chapter_text:
        source_text = str(blueprint_text_fallback or "").strip()
        if not source_text:
            directory_file = os.path.join(str(filepath or "").strip(), "Novel_directory.txt")
            source_text = _read_text_file(directory_file).strip()
        if source_text:
            try:
                split_blueprint_to_chapter_files(filepath, source_text, remove_stale=False)
            except OSError:
                pass
            chapter_text = _read_text_file(chapter_file).strip()
            if not chapter_text:
                return get_chapter_info_from_blueprint(source_text, chapter_number)
        else:
            return get_chapter_info_from_blueprint("", chapter_number)

    chapter_info = get_chapter_info_from_blueprint(chapter_text, chapter_number)
    if not isinstance(chapter_info, dict):
        return get_chapter_info_from_blueprint("", chapter_number)

    next_chapter_file = get_chapter_blueprint_file(filepath, chapter_number + 1)
    next_text = _read_text_file(next_chapter_file).strip()
    if next_text:
        next_info = get_chapter_info_from_blueprint(next_text, chapter_number + 1)
        if isinstance(next_info, dict):
            next_summary = next_info.get("chapter_summary") or next_info.get("chapter_purpose") or ""
            chapter_info["next_chapter_summary"] = str(next_summary or "")
    return chapter_info


def get_chapter_info_from_blueprint(blueprint_text: str, target_chapter_number: int):
    """
    在已经加载好的章节蓝图文本中，找到对应章号的结构化信息，返回一个 dict。
    若找不到则返回一个默认的结构。
    """
    all_chapters = parse_chapter_blueprint(blueprint_text)
    for i, ch in enumerate(all_chapters):
        if ch["chapter_number"] == target_chapter_number:
            # Found the chapter, now try to get next chapter's summary
            next_chapter_summary = ""
            if i + 1 < len(all_chapters):
                next_chapter_summary = all_chapters[i+1].get("chapter_summary", "")
            
            ch["next_chapter_summary"] = next_chapter_summary
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
        "characters_involved": "",
        "key_items": "",
        "scene_location": "",
        "time_constraint": "",
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
        "worldview_progression": "",
        "shuangdian_position": "",
        "word_count_target": "",
        "next_chapter_summary": "",
        # ========== 新增：增强版6大模块默认值 ==========
        # 【程序员思维应用】
        "programmer_thinking": "",
        "programmer_scene": "",
        "programmer_quote": "",
        "programmer_foreshadow": "",
        # 【伏笔植入清单】
        "foreshadow_plant": "",
        "foreshadow_reveal": "",
        # 【暧昧场景设计】
        "romance_female_lead": "",
        "romance_type": "",
        "romance_level": "",
        "romance_technique": "",
        "romance_dialogue": "",
        "romance_atmosphere": "",
        "romance_progress": "",
        # 【爽点密度检查】
        "shuangdian_count": "",
        "shuangdian_list": "",
        # 【女主成长线推进】
        "female_lead_growth": "",
        "female_lead_arc": "",
        # 【质量检查清单】
        "quality_check": "",
        "identity_consistency": "",
        "worldview_consistency": "",
        "emotional_coherence": ""
    }


class ChapterDirectoryParser:
    def __init__(self):
        self._field_map = {
            "章节标题": "chapter_title",
            "字数目标": "word_count_target",
            "核心冲突": "core_conflict",
            "时间地点": "time_location",
            "本章简介": "chapter_summary",
            "情感弧光": "emotional_arc",
            "钩子设计": "hook_design",
            "伏笔线索": "foreshadowing",
            "冲突设计": "conflict_design",
        }

    def parse(self, content: str):
        result = {
            "chapter_title": "",
            "word_count_target": None,
            "core_conflict": "",
            "time_location": "",
            "chapter_summary": "",
            "emotional_arc": "",
            "hook_design": "",
            "foreshadowing": "",
            "conflict_design": "",
        }

        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or "：" not in line:
                continue
            key, value = line.split("：", 1)
            key = key.strip()
            value = value.strip()
            field_name = self._field_map.get(key)
            if not field_name:
                continue
            if field_name == "word_count_target":
                digits = "".join(ch for ch in value if ch.isdigit())
                result[field_name] = int(digits) if digits else None
            else:
                result[field_name] = value

        if not result["chapter_title"]:
            match = re.search(r"^第[\d一二三四五六七八九十百千]+章[：:](.+)$", content, re.MULTILINE)
            if match:
                result["chapter_title"] = match.group(1).strip()

        return result

    def parse_multiple(self, content: str):
        chunks = re.split(r"(?=^第[\d一二三四五六七八九十百千]+章[：:].*$)", content.strip(), flags=re.MULTILINE)
        parsed = []
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
            parsed.append(self.parse(chunk))
        return parsed
