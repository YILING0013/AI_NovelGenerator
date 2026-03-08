#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate a high-fidelity 1500-chapter directory based on detailed Novel_architecture.txt specs.
"""

import os

OUTPUT_FILE = r"c:\Users\tcui\Documents\GitHub\AI_NovelGenerator\wxhyj\Novel_directory.txt"

def generate_directory():
    # Define rigid structure from architecture
    directory_map = {}
    
    # === Helper to fill ranges ===
    def fill_range(start, end, theme_prefix, beats=None):
        count = end - start + 1
        for i in range(count):
            ch_num = start + i
            if ch_num in directory_map: continue # Don't overwrite specific events
            
            if beats:
                # Cycle through narrative beats if provided
                beat = beats[i % len(beats)]
                title = f"{theme_prefix}: {beat}"
            else:
                title = f"{theme_prefix} (Sequence {i+1})"
            
            directory_map[ch_num] = title

    # ==========================================
    # 1. Define SPECIFIC EVENTS (Fixed Anchors)
    # ==========================================
    fixed_events = {
        # Vol 1
        1: "致命死局 (Fatal Crisis) - 乱葬岗觉醒",
        2: "洞悉本源 (Origin Insight) - 灵力破绽解析",
        3: "道心崩塌 (Dao Collapse) - 长老悖论反噬",
        40: "觉醒触发：外门大比初露锋芒",
        55: "源代码一瞥 (Truth Hint) - 系统花屏",
        60: "万魔古窟开启 - 多方势力汇聚",
        75: "熔岩之海：遭遇熔火蜥皇",
        80: "心魔考验：穿越前的记忆",
        85: "虚假胜利：融合魔血与苏清雪",
        90: "筑基成功：魔道血脉激活",
        100: "林小雨的确立：月下誓言",
        135: "监察者降临：世界的残酷真相",
        150: "第一卷终章：暂时的平静与逃亡",
        
        # Vol 2
        151: "宗门风云：革新派与保守派",
        200: "巫族线索：古老图腾的呼唤",
        250: "金丹雷劫：双脉融合的考验",
        300: "五脉融合度突破50% - 质变",
        350: "秘境夺宝高潮：上古遗迹开启",
        400: "宗门大比：五脉神通扬威",
        450: "第二卷终章：更大的世界版图",
        
        # Vol 3
        451: "身世线索浮现：天命调试的发现",
        500: "元婴大道：碎丹成婴的艰难",
        550: "锁定仇敌：当年灭门名单",
        551: "复仇序幕：断其财路",
        600: "复仇进阶：毁其名誉",
        625: "仇敌反扑：血誓契约与人质危机",
        635: "绝境反转：营救林小雨",
        650: "最终击杀：道心拷问 - 我与恶龙",
        700: "第四血脉：佛门觉醒 - 因果净化",
        750: "第三卷终章：化神之约",
        
        # Vol 4
        751: "儒家血脉初醒：浩然正气",
        800: "第一战役：破局之战 - 镇魔塔崩塌",
        900: "第二战役：背叛危机 - 陈逸风的抉择",
        980: "前奏：素媚的遗言",
        990: "温柔一晚：最后的宁静",
        995: "高危预警：因果波动爆发",
        1000: "第三战役：红颜献祭 - 素媚陨落",
        1031: "飞升试炼：天劫预兆降临",
        1036: "后事安排：势力交接",
        1041: "凡界最后一战：对抗天道化身",
        1046: "九九天劫：五女护法",
        1050: "第四卷终章：飞升仙界",
        
        # Vol 5
        1051: "初入仙界：降维打击开始",
        1080: "发现素媚残魂：系统深处的数据包",
        1200: "仙界根据地：建立新秩序",
        1250: "天外邪魔降临：位面战争爆发",
        1300: "五脉归一：混沌体大成",
        1350: "浩劫决战：为了生存",
        1400: "接管天道权限：成为执笔者",
        1490: "素媚复活：红莲重绽",
        1492: "萧尘的和解：守护凡界",
        1495: "五女圆满：各自的归宿",
        1498: "新世界的黎明：打破囚笼",
        1500: "全书完：永恒的日常"
    }
    
    directory_map.update(fixed_events)
    
    # ==========================================
    # 2. Fill Gaps with Thematic Narrative Beats
    # ==========================================
    
    # Vol 1 Sub 1 (4-39): Awakening Aftermath
    fill_range(4, 39, "觉醒余波", [
        "宗门震动与调查", 
        "暗流：森罗魔域的窥视", 
        "暗流：纯血盟的嗅探", 
        "素媚的踪迹初现", 
        "外门弟子的挑衅与打脸", 
        "修炼：混元血脉初体验", 
        "系统任务：收集残缺血脉", 
        "与林小雨的日常互动"
    ])
    
    # Vol 1 Sub 2 (41-54, 56-59, 61-90): Trial & Conflict
    fill_range(41, 54, "古窟前奏", ["准备物资", "五人组初遇", "进入万魔古窟外围", "遭遇低阶魔兽"])
    fill_range(56, 59, "古窟探险", ["深入魔窟地下", "遭遇古老机关", "魔气侵蚀与系统抵抗"])
    fill_range(61, 74, "混战爆发", ["各方势力乱战", "萧尘的剑道压制", "素媚的诡异手段", "保护师妹"])
    fill_range(76, 79, "绝境求生", ["被蜥皇追杀", "绝地反击的准备", "系统紧急推演"])
    fill_range(81, 84, "魔血融合", ["痛苦的融合过程", "血脉排斥反应", "生死一线"])
    fill_range(86, 89, "反杀时刻", ["魔威初显", "碾压追兵", "震惊全场"])
    
    # Vol 1 Sub 3 (91-134, 136-149): Rise & Crisis
    fill_range(91, 99, "名扬外门", ["回归宗门", "奖励清点", "各方拉拢"])
    fill_range(101, 134, "筑基历练", ["下山执行任务", "遭遇新的敌人", "系统升级功能测试", "与苏清雪的纠葛"])
    fill_range(136, 149, "逃亡之路", ["躲避监察者搜索", "隐藏身份", "寻找新的庇护所"])

    # Vol 2 Sub 1 (151-249): Sect Politics & Travel
    fill_range(152, 199, "宗门博弈", ["资源争夺战", "长老派系的刁难", "反击与立威", "拉拢新势力"])
    fill_range(201, 249, "五域游历", ["前往南疆/北荒", "感悟巫族自然之力", "收集五行灵物", "奇遇连连"])
    
    # Vol 2 Sub 2 (251-349): Secret Realm
    fill_range(251, 299, "秘境争锋", ["进入上古秘境", "破解上古阵法", "与其他天骄交手", "获得关键传承"])
    fill_range(301, 349, "血脉突破", ["巫族血脉深度开发", "双脉融合战术演练", "面对更强敌人的挑战"])
    
    # Vol 2 Sub 3 (351-449): Establishing Dominance
    fill_range(351, 399, "势力扩张", ["建立自己的小圈子", "培养亲信", "整顿宗门风气"])
    fill_range(401, 449, "名动一方", ["宗门排位战", "甚至挑战别派长老", "确立年轻一代领袖地位"])
    
    # Vol 3 Sub 1 (451-549): Truth Investigation
    fill_range(451, 499, "迷雾追踪", ["解读古籍线索", "寻访当年证人", "拼凑灭门真相", "发现惊人内幕"])
    fill_range(501, 549, "元婴之路", ["感悟天地法则", "冲击元婴瓶颈", "心魔再临与斩断"])
    
    # Vol 3 Sub 2 (551-649): Revenge Arc (Detailed Phases)
    fill_range(552, 599, "复仇：商业绞杀", ["切断敌方灵石矿脉", "破坏敌方丹药市场", "收买敌方附庸", "舆论攻势"])
    fill_range(601, 624, "复仇：名誉崩塌", ["揭露当年罪证", "让敌方众叛亲离", "公开审判大会", "步步紧逼"])
    fill_range(626, 634, "复仇：绝境危机", ["应对天道监察者", "寻找林小雨下落", "与时间的赛跑"])
    fill_range(636, 649, "复仇：终局之战", ["攻破敌方老巢", "直面幕后黑手", "一场没有胜利者的战斗"])
    
    # Vol 3 Sub 3 (651-749): Aftermath & New Goal
    fill_range(651, 699, "战后重建", ["抚平创伤", "重新思考人生目标", "与女主们的温情时光", "探索佛门因果"])
    fill_range(701, 749, "化神准备", ["感悟化神意境", "收集化神机缘", "为下一阶段布局"])
    
    # Vol 4 Sub 1 (751-899): Unification War Start
    fill_range(752, 799, "儒道觉醒", ["感悟浩然正气", "以理服人", "建立统一战线雏形"])
    fill_range(801, 899, "征战八荒", ["收服周边小宗门", "推行新秩序", "打破旧有阶级", "遭遇顽固势力抵抗"])
    
    # Vol 4 Sub 2 (901-979): Betrayal & Hardship
    fill_range(901, 979, "至暗时刻", ["陈逸风背叛的余波", "军队士气低落", "敌军趁势反扑", "艰难的防守反击", "重整旗鼓"])
    
    # Vol 4 Sub 3 (1001-1030): Final Push
    fill_range(1001, 1030, "哀兵必胜", ["素媚牺牲的激励", "全军复仇意志", "攻破最后防线", "天下归心"])
    
    # Vol 4 Sub 4 (1032-1049): Ascension Prep
    fill_range(1032, 1035, "飞升前奏", ["安排身后事", "与故人道别"])
    fill_range(1037, 1040, "最后部署", ["确立继承人", "留下传承法宝"])
    fill_range(1042, 1045, "挑战天道", ["验证自身实力", "为了尊严的一战"])
    fill_range(1047, 1049, "渡劫时刻", ["天雷洗礼", "肉身成圣"])
    
    # Vol 5 (1051-1500): Immortal World
    fill_range(1052, 1079, "仙界求生", ["适应高维法则", "躲避仙界土著追杀", "寻找立足点"])
    fill_range(1081, 1199, "黑客崛起", ["利用系统漏洞", "修改仙界规则", "建立黑客组织"])
    fill_range(1201, 1249, "风雨欲来", ["察觉邪魔踪迹", "仙界各大势力预警", "备战状态"])
    fill_range(1251, 1299, "位面战争", ["前线厮杀", "惨烈的拉锯战", "英雄的陨落"])
    fill_range(1301, 1349, "绝地反击", ["混沌体威力全开", "扭转战局", "深入敌后"])
    fill_range(1351, 1399, "最后的征途", ["清理残余势力", "追溯邪魔源头", "直面最终BOSS"])
    fill_range(1401, 1489, "重塑世界", ["修改天道底层代码", "修复世界BUG", "建立理想乡"])
    fill_range(1491, 1491, "余波：平静的一天", ["看云卷云舒"])
    fill_range(1493, 1494, "故地重游", ["回到最初的起点"])
    fill_range(1496, 1497, "婚礼", ["迟到的仪式"])
    fill_range(1499, 1499, "尾声", ["新的传说"])

    # Output Construction
    content = ["# 《开局废柴，我能看穿万法破绽》 1500章完整目录", 
               "生成说明：基于《小说架构》V2.0 严格推演", ""]
    
    # Sort and define sections
    sorted_chapters = sorted(directory_map.items())
    
    current_vol = 0
    vol_ranges = [
        (1, 150, "第一卷：魔血染青天"),
        (151, 450, "第二卷：巫骨踏山河"),
        (451, 750, "第三卷：道心斩红尘"),
        (751, 1050, "第四卷：儒令镇八荒"),
        (1051, 1500, "第五卷：我意即天意")
    ]

    for ch_num, title in sorted_chapters:
        # Check volume headers
        for v_start, v_end, v_title in vol_ranges:
            if ch_num == v_start:
                content.append(f"\n## {v_title} ({v_start}-{v_end}章)")
                content.append("-" * 40)
                break
        
        content.append(f"第{ch_num}章 {title}")
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(content))
    
    print(f"Detailed directory generated at: {OUTPUT_FILE}")

if __name__ == "__main__":
    generate_directory()
