# prompts/constants.py
# -*- coding: utf-8 -*-
"""
常量配置模块 - 修为体系、战斗风格、反派风格等
"""

# ============== 结尾风格 ==============
ENDING_STYLES = [
    "悬念式结尾：在章节末尾抛出一个新的谜团、危机或未解之谜，引发读者强烈的好奇心。",
    "总结式结尾：对本章发生的事件进行简短的内心独白或情感升华，展现主角的成长或感悟。",
    "场景式结尾：以一个富有画面感、意境深远的场景描写作为结束，烘托氛围，留下余韵。",
    "对话式结尾：以一段意味深长的对话或一句掷地有声的台词结束，戛然而止，更有力度。",
    "反转式结尾：在最后时刻揭示一个意想不到的事实或反转，颠覆读者的预期。"
]

# ============== 战斗风格策略池 ==============
BATTLE_STYLE_POOL = [
    {
        "name": "正面硬刚",
        "description": "以力破巧，展现绝对实力碾压。特点：一招制敌、力量对比鲜明、观察者震惊反应。",
        "keywords": ["碾压", "秒杀", "一拳", "力量差距"],
        "writing_guide": "重点描写力量爆发瞬间、敌人的震惊表情、旁观者的哗然反应"
    },
    {
        "name": "以巧破力",
        "description": "利用敌人弱点，四两拨千斤。特点：观察→分析→精准打击、智取而非力取。",
        "keywords": ["弱点", "破绽", "巧妙", "精准"],
        "writing_guide": "重点描写主角的观察分析过程、找到破绽的顿悟瞬间、精准一击的描写"
    },
    {
        "name": "团队协作",
        "description": "多人配合作战，各展所长。特点：角色分工、配合默契、互相掩护。",
        "keywords": ["配合", "掩护", "分工", "协同"],
        "writing_guide": "重点描写队员之间的默契配合、各自能力的展现、团队羁绊的体现"
    },
    {
        "name": "环境利用",
        "description": "利用地形、天气等环境因素制胜。特点：环境描写丰富、战术灵活。",
        "keywords": ["地形", "陷阱", "环境", "借势"],
        "writing_guide": "重点描写环境细节、主角如何观察并利用环境、出其不意的战术效果"
    },
    {
        "name": "心理博弈",
        "description": "攻心为上，以气势、言语、计谋瓦解对手。特点：对话交锋、心理描写丰富。",
        "keywords": ["威慑", "试探", "心理", "气势"],
        "writing_guide": "重点描写双方的心理活动、言语交锋、气势对碰、心理防线的崩溃"
    }
]

# ============== 修为进度管理 ==============
# 根据400章规划，匹配5卷分卷结构
CULTIVATION_PROGRESS_MAP = {
    # 第一卷：系统觉醒篇 (1-80章) - 练气到筑基
    (1, 20): ("练气初期", "练气后期"),
    (21, 50): ("练气后期", "筑基初期"),
    (51, 80): ("筑基初期", "筑基中期"),
    
    # 第二卷：宗门争霸篇 (81-160章) - 筑基到金丹
    (81, 120): ("筑基中期", "筑基后期"),
    (121, 160): ("筑基圆满", "金丹初期"),
    
    # 第三卷：复仇之路篇 (161-240章) - 金丹到元婴
    (161, 200): ("金丹初期", "金丹中期"),
    (201, 240): ("金丹后期", "元婴初期"),
    
    # 第四卷：统一天下篇 (241-320章) - 元婴到化神
    (241, 280): ("元婴初期", "元婴中期"),
    (281, 320): ("元婴后期", "化神初期"),
    
    # 第五卷：飞升成仙篇 (321-400章) - 化神到渡劫飞升
    (321, 360): ("化神初期", "化神后期"),
    (361, 388): ("化神圆满", "渡劫期"),
    (389, 400): ("渡劫期", "飞升成仙"),
}

def get_cultivation_constraint(chapter_num: int) -> dict:
    """根据章节号返回修为约束"""
    for (start, end), (current, max_realm) in CULTIVATION_PROGRESS_MAP.items():
        if start <= chapter_num <= end:
            return {
                "current_realm": current,
                "max_realm": max_realm,
                "constraint_text": f"【修为锁定】主角当前境界应在【{current}】附近，本章最多可突破至【{max_realm}】，禁止跳级！"
            }
    return {"current_realm": "自由", "max_realm": "自由", "constraint_text": ""}

# ============== 反派对话风格 ==============
VILLAIN_DIALOGUE_STYLES = {
    "阴阳怪气": {
        "description": "语带讽刺，表面客气实则尖酸",
        "example_patterns": ["哟，这不是...吗？", "真是令人...意外啊"],
        "prompt_guide": "反派说话时语带嘲讽，表面客气实则尖酸刻薄"
    },
    "粗犷直接": {
        "description": "直来直去，语言粗犷，充满暴力威胁",
        "example_patterns": ["给我滚！", "找死！"],
        "prompt_guide": "反派说话直来直去，语言粗犷有力"
    },
    "心机深沉": {
        "description": "话中有话，城府极深",
        "example_patterns": ["不知...是否有兴趣？", "我倒有一个提议..."],
        "prompt_guide": "反派说话话中有话，城府极深"
    },
    "狂傲自大": {
        "description": "目中无人，极度自信",
        "example_patterns": ["区区蝼蚁...", "你也配？"],
        "prompt_guide": "反派说话目中无人，极度自信傲慢"
    }
}

# ============== 分卷结构映射 ==============
# 根据Novel_architecture.txt定义，用于生成时动态校正
VOLUME_MAPPING = {
    (1, 80): {
        "volume": "第一卷",
        "name": "系统觉醒篇",
        "subacts": {
            (1, 27): "子幕1：觉醒触发",
            (28, 67): "子幕2：初试锋芒",
            (68, 80): "子幕3：声名鹊起"
        }
    },
    (81, 160): {
        "volume": "第二卷",
        "name": "宗门争霸篇",
        "subacts": {
            (81, 107): "子幕1：暗流涌动",
            (108, 147): "子幕2：群雄逐鹿",
            (148, 160): "子幕3：霸业初成"
        }
    },
    (161, 240): {
        "volume": "第三卷",
        "name": "复仇之路篇",
        "subacts": {
            (161, 187): "子幕1：真相初现",
            (188, 227): "子幕2：血海深仇",
            (228, 240): "子幕3：尘埃落定"
        }
    },
    (241, 320): {
        "volume": "第四卷",
        "name": "统一天下篇",
        "subacts": {
            (241, 267): "子幕1：势力雏形",
            (268, 307): "子幕2：纵横捭阖",
            (308, 320): "子幕3：天下归心"
        }
    },
    (321, 400): {
        "volume": "第五卷",
        "name": "飞升成仙篇",
        "subacts": {
            (321, 347): "子幕1：天劫将至",
            (348, 387): "子幕2：灭世浩劫",
            (388, 400): "子幕3：飞升仙界"
        }
    }
}

def get_volume_info(chapter_num: int) -> dict:
    """
    根据章节号获取正确的分卷信息
    
    Args:
        chapter_num: 章节号 (1-400)
        
    Returns:
        包含 volume, name, subact, position_text 的字典
    """
    for (start, end), info in VOLUME_MAPPING.items():
        if start <= chapter_num <= end:
            # 获取子幕信息
            subact = "未知子幕"
            for (sub_start, sub_end), subact_name in info["subacts"].items():
                if sub_start <= chapter_num <= sub_end:
                    subact = subact_name
                    break
            
            return {
                "volume": info["volume"],
                "name": info["name"],
                "subact": subact,
                "full_position": f"{info['volume']}：{info['name']} - {subact}",
                "position_text": f"【分卷定位】当前第{chapter_num}章属于{info['volume']}·{info['name']}的{subact}阶段"
            }
    
    # 超出400章的情况
    return {
        "volume": "第五卷+",
        "name": "续章",
        "subact": "扩展内容",
        "full_position": "第五卷+：续章 - 扩展内容",
        "position_text": f"【分卷定位】第{chapter_num}章已超出原定400章规划"
    }
