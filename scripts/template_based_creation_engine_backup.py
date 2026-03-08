# template_based_creation_engine.py
# -*- coding: utf-8 -*-
"""
模板化创作引擎 - 基于"五行混元决"理论的第五层优化
实现番茄平台经典模板库 + 意外事件随机引擎

核心功能：
1. 番茄平台经典模板库（退婚流、重生流、系统流等）
2. 意外事件随机引擎
3. 智能模板选择和组合
4. 情节自动推进和优化
"""

import random
import json
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TemplateType(Enum):
    """模板类型枚举"""
    REVENGE = "revenge"           # 复仇流
    REBIRTH = "rebirth"           # 重生流
    SYSTEM = "system"             # 系统流
    AUCTION = "auction"           # 拍卖会
    SECRET_REALM = "secret_realm" # 秘境探险
    TOURNAMENT = "tournament"     # 宗门大比
    UNDERCOVER = "undercover"     # 扮猪吃虎
    BREAKTHROUGH = "breakthrough" # 突破爽点

@dataclass
class SceneTemplate:
    """场景模板"""
    scene_id: str
    title: str
    description: str
    emotional_impact: float  # 情绪冲击力 0-1
    required_elements: List[str] = field(default_factory=list)
    optional_elements: List[str] = field(default_factory=list)
    word_count_range: Tuple[int, int] = (500, 1500)

@dataclass
class PlotTemplate:
    """剧情模板"""
    template_id: str
    name: str
    type: TemplateType
    scenes: List[SceneTemplate] = field(default_factory=list)
    shuangdian_points: List[int] = field(default_factory=list)  # 爽点所在场景索引
    total_word_count: Tuple[int, int] = (2000, 6000)
    tags: List[str] = field(default_factory=list)
    difficulty: str = "normal"  # easy, normal, hard

class TomatoTemplateLibrary:
    """番茄平台模板库 - 基于"五行混元决"理论"""

    def __init__(self):
        self.templates: Dict[str, PlotTemplate] = {}
        self.surprise_events: List[Dict[str, Any]] = []
        self.character_archetypes: Dict[str, Dict] = {}
        self._initialize_library()

    def _initialize_library(self):
        """初始化模板库"""
        logger.info("🎭 初始化番茄平台经典模板库...")
        self._create_classic_templates()
        self._create_surprise_events()
        self._create_character_archetypes()
        logger.info(f"✅ 模板库初始化完成：{len(self.templates)}个模板，{len(self.surprise_events)}个意外事件")

    def _create_classic_templates(self):
        """创建经典模板"""

        # 1. 退婚流模板
        divorce_template = PlotTemplate(
            template_id="divorce_flow_001",
            name="经典退婚流",
            type=TemplateType.REVENGE,
            scenes=[
                SceneTemplate("scene_1", "天才陨落", "曾经的天才主角实力尽失，被世人嘲笑",
                            emotional_impact=0.2, required_elements=["退婚原因", "众人嘲讽"]),
                SceneTemplate("scene_2", "当众退婚", "未婚妻当众提出退婚，羞辱主角至极",
                            emotional_impact=0.1, required_elements=["退婚台词", "主角愤怒"]),
                SceneTemplate("scene_3", "神秘奇遇", "绝境中激活老爷爷/系统，获得传承",
                            emotional_impact=0.6, required_elements=["奇遇触发", "金手指激活"]),
                SceneTemplate("scene_4", "实力恢复", "迅速恢复实力，甚至超越从前",
                            emotional_impact=0.7, required_elements=["实力提升", "功法修炼"]),
                SceneTemplate("scene_5", "初次打脸", "在关键时刻展示实力，震惊所有人",
                            emotional_impact=0.9, required_elements=["打脸场面", "众人震惊"]),
            ],
            shuangdian_points=[2, 3, 4],  # 奇遇、恢复、打脸
            tags=["退婚", "复仇", "老爷爷", "打脸", "逆袭"],
            difficulty="normal"
        )

        # 2. 重生流模板
        rebirth_template = PlotTemplate(
            template_id="rebirth_flow_001",
            name="仙尊重生",
            type=TemplateType.REBIRTH,
            scenes=[
                SceneTemplate("scene_1", "含恨而终", "前世巅峰时期遭背叛，含恨而死",
                            emotional_impact=0.3, required_elements=["死亡原因", "仇敌信息"]),
                SceneTemplate("scene_2", "意外重生", "重回少年时代，获得改变命运的机会",
                            emotional_impact=0.5, required_elements=["重生时机", "身体状态"]),
                SceneTemplate("scene_3", "先知优势", "利用前世经验，提前获得机缘",
                            emotional_impact=0.6, required_elements=["预言能力", "机缘获取"]),
                SceneTemplate("scene_4", "弥补遗憾", "拯救前世重要的人，弥补心中遗憾",
                            emotional_impact=0.7, required_elements=["遗憾弥补", "情感释放"]),
                SceneTemplate("scene_5", "复仇开始", "对前世仇敌展开复仇，实力碾压",
                            emotional_impact=0.9, required_elements=["复仇场面", "实力碾压"]),
            ],
            shuangdian_points=[1, 2, 3, 4],
            tags=["重生", "复仇", "先知", "弥补遗憾", "碾压"],
            difficulty="normal"
        )

        # 3. 系统流模板
        system_template = PlotTemplate(
            template_id="system_flow_001",
            name="神级系统",
            type=TemplateType.SYSTEM,
            scenes=[
                SceneTemplate("scene_1", "系统激活", "意外获得神秘系统，开启成神之路",
                            emotional_impact=0.6, required_elements=["系统激活", "新手礼包"]),
                SceneTemplate("scene_2", "任务发布", "系统发布第一个任务，完成获得奖励",
                            emotional_impact=0.5, required_elements=["任务内容", "奖励机制"]),
                SceneTemplate("scene_3", "能力提升", "通过系统快速提升实力，超越常人",
                            emotional_impact=0.7, required_elements=["升级过程", "能力展示"]),
                SceneTemplate("scene_4", "打脸众人", "利用系统能力打脸质疑者，震惊四座",
                            emotional_impact=0.8, required_elements=["打脸情节", "众人反应"]),
                SceneTemplate("scene_5", "系统升级", "系统完成重要升级，解锁更强大功能",
                            emotional_impact=0.9, required_elements=["系统升级", "新功能解锁"]),
            ],
            shuangdian_points=[0, 2, 3, 4],
            tags=["系统", "任务", "升级", "打脸", "神级"],
            difficulty="easy"
        )

        # 4. 拍卖会模板
        auction_template = PlotTemplate(
            template_id="auction_001",
            name="拍卖会打脸",
            type=TemplateType.AUCTION,
            scenes=[
                SceneTemplate("scene_1", "拍卖会邀请", "收到高级拍卖会邀请，进入富人圈子",
                            emotional_impact=0.4, required_elements=["拍卖会", "身份验证"]),
                SceneTemplate("scene_2", "富人嘲讽", "富人圈质疑主角身份，出言嘲讽",
                            emotional_impact=0.3, required_elements=["质疑嘲讽", "看不起"]),
                SceneTemplate("scene_3", "压轴宝物", "拿出令人震惊的压箱底宝物",
                            emotional_impact=0.7, required_elements=["神秘宝物", "众人惊讶"]),
                SceneTemplate("scene_4", "激烈竞拍", "与富二代展开激烈竞价，震惊全场",
                            emotional_impact=0.8, required_elements=["竞价过程", "天价出价"]),
                SceneTemplate("scene_5", "最终打脸", "成功拍得宝物，身份揭露，众人跪舔",
                            emotional_impact=0.95, required_elements=["身份揭露", "众人跪舔"]),
            ],
            shuangdian_points=[2, 3, 4],
            tags=["拍卖会", "打脸", "富人", "竞拍", "身份"],
            difficulty="normal"
        )

        # 5. 秘境探险模板
        secret_realm_template = PlotTemplate(
            template_id="secret_realm_001",
            name="秘境探险传承",
            type=TemplateType.SECRET_REALM,
            scenes=[
                SceneTemplate("scene_1", "秘境发现", "意外发现古代秘境入口",
                            emotional_impact=0.5, required_elements=["秘境入口", "发现过程"]),
                SceneTemplate("scene_2", "凶险闯关", "在秘境中遭遇各种危险和机关",
                            emotional_impact=0.6, required_elements=["危险机关", "智斗过程"]),
                SceneTemplate("scene_3", "上古传承", "获得上古大能的传承和宝物",
                            emotional_impact=0.8, required_elements=["传承获得", "实力提升"]),
                SceneTemplate("scene_4", "守护神兽", "收服或战胜守护神兽，获得认可",
                            emotional_impact=0.85, required_elements=["神兽战斗", "收服过程"]),
                SceneTemplate("scene_5", "满载而归", "带着传承和宝物离开秘境，实力大增",
                            emotional_impact=0.9, required_elements=["实力飞跃", "众人震惊"]),
            ],
            shuangdian_points=[2, 3, 4],
            tags=["秘境", "探险", "传承", "神兽", "宝物"],
            difficulty="hard"
        )

        # 6. 宗门大比模板
        tournament_template = PlotTemplate(
            template_id="tournament_001",
            name="宗门大比一鸣惊人",
            type=TemplateType.TOURNAMENT,
            scenes=[
                SceneTemplate("scene_1", "大比开幕", "宗门年度大比开始，各路天才云集",
                            emotional_impact=0.4, required_elements=["大比开始", "天才云集"]),
                SceneTemplate("scene_2", "被众人轻视", "主角被认为是弱者，遭人嘲笑和质疑",
                            emotional_impact=0.3, required_elements=["被轻视", "质疑嘲笑"]),
                SceneTemplate("scene_3", "初赛惊艳", "在初赛中意外展现实力，震惊众人",
                            emotional_impact=0.7, required_elements=["初赛惊艳", "实力展现"]),
                SceneTemplate("scene_4", "决赛巅峰对决", "与最强对手展开激烈对决",
                            emotional_impact=0.85, required_elements=["巅峰对决", "激烈战斗"]),
                SceneTemplate("scene_5", "一战成名", "最终夺冠，成为宗门新星，获得重要资源",
                            emotional_impact=0.95, required_elements=["一战成名", "获得资源"]),
            ],
            shuangdian_points=[2, 3, 4],
            tags=["宗门大比", "一鸣惊人", "天才", "夺冠", "成名"],
            difficulty="normal"
        )

        # 7. 扮猪吃虎模板
        undercover_template = PlotTemplate(
            template_id="undercover_001",
            name="扮猪吃虎震惊全场",
            type=TemplateType.UNDERCOVER,
            scenes=[
                SceneTemplate("scene_1", "隐藏实力", "主角刻意隐藏真实实力，装作普通",
                            emotional_impact=0.3, required_elements=["隐藏实力", "伪装普通"]),
                SceneTemplate("scene_2", "遭遇挑衅", "被敌人或对手挑衅和羞辱",
                            emotional_impact=0.2, required_elements=["遭遇挑衅", "被人羞辱"]),
                SceneTemplate("scene_3", "众人保护", "朋友或长辈为维护主角而挺身而出",
                            emotional_impact=0.5, required_elements=["朋友维护", "长辈保护"]),
                SceneTemplate("scene_4", "突然爆发", "在关键时刻突然爆发真实实力",
                            emotional_impact=0.9, required_elements=["突然爆发", "实力碾压"]),
                SceneTemplate("scene_5", "真相揭露", "身份和实力揭露，震惊所有人，反派跪地求饶",
                            emotional_impact=0.95, required_elements=["真相揭露", "众人震惊"]),
            ],
            shuangdian_points=[3, 4],
            tags=["扮猪吃虎", "隐藏实力", "突然爆发", "真相揭露", "打脸"],
            difficulty="normal"
        )

        # 8. 突破升级模板
        breakthrough_template = PlotTemplate(
            template_id="breakthrough_001",
            name="生死关头大突破",
            type=TemplateType.BREAKTHROUGH,
            scenes=[
                SceneTemplate("scene_1", "遭遇瓶颈", "主角在修炼中遇到难以突破的瓶颈",
                            emotional_impact=0.4, required_elements=["修炼瓶颈", "难以突破"]),
                SceneTemplate("scene_2", "生死危机", "面临生死关头或巨大压力",
                            emotional_impact=0.2, required_elements=["生死危机", "巨大压力"]),
                SceneTemplate("scene_3", "顿悟时刻", "在绝境中获得顿悟，理解新的道理",
                            emotional_impact=0.7, required_elements=["顿悟时刻", "理解新理"]),
                SceneTemplate("scene_4", "实力暴涨", "实力突然大幅提升，连破多个境界",
                            emotional_impact=0.9, required_elements=["实力暴涨", "连破境界"]),
                SceneTemplate("scene_5", "威震四方", "新的实力威震四方，敌人闻风丧胆",
                            emotional_impact=0.85, required_elements=["威震四方", "敌人胆寒"]),
            ],
            shuangdian_points=[3, 4],
            tags=["突破", "升级", "顿悟", "实力暴涨", "威震四方"],
            difficulty="hard"
        )

        # 9. 美女救英雄模板
        beauty_rescue_template = PlotTemplate(
            template_id="beauty_rescue_001",
            name="美女救英雄反被救",
            type=TemplateType.BREAKTHROUGH,
            scenes=[
                SceneTemplate("scene_1", "美女遇险", "女主角或重要女性角色遇到危险",
                            emotional_impact=0.5, required_elements=["美女遇险", "危急情况"]),
                SceneTemplate("scene_2", "主角救援", "主角冒险前去救援，陷入困境",
                            emotional_impact=0.6, required_elements=["主角救援", "陷入困境"]),
                SceneTemplate("scene_3", "实力爆发", "在救援过程中爆发隐藏实力",
                            emotional_impact=0.8, required_elements=["实力爆发", "隐藏力量"]),
                SceneTemplate("scene_4", "反败为胜", "不仅救了美女，还反杀了敌人",
                            emotional_impact=0.9, required_elements=["反败为胜", "反杀敌人"]),
                SceneTemplate("scene_5", "情感升温", "美女对主角产生好感，关系升温",
                            emotional_impact=0.7, required_elements=["情感升温", "关系发展"]),
            ],
            shuangdian_points=[3, 4],
            tags=["美女救英雄", "情感", "实力爆发", "反杀", "感情线"],
            difficulty="normal"
        )

        # 10. 师父传承模板
        master_inheritance_template = PlotTemplate(
            template_id="master_inheritance_001",
            name="师父临终托传承",
            type=TemplateType.BREAKTHROUGH,
            scenes=[
                SceneTemplate("scene_1", "师父重伤", "师父或恩师遭遇重伤，命在旦夕",
                            emotional_impact=0.3, required_elements=["师父重伤", "命在旦夕"]),
                SceneTemplate("scene_2", "临终托付", "师父临终前将重要传承或责任托付给主角",
                            emotional_impact=0.6, required_elements=["临终托付", "传承责任"]),
                SceneTemplate("scene_3", "发誓复仇", "主角发誓要为师父报仇或完成遗愿",
                            emotional_impact=0.7, required_elements=["发誓复仇", "完成遗愿"]),
                SceneTemplate("scene_4", "继承遗志", "继承师父的遗志和力量，实力大增",
                            emotional_impact=0.85, required_elements=["继承遗志", "实力大增"]),
                SceneTemplate("scene_5", "复仇开始", "开始为师父复仇，展现实力震慑敌人",
                            emotional_impact=0.9, required_elements=["复仇开始", "实力震慑"]),
            ],
            shuangdian_points=[2, 4, 5],
            tags=["师父传承", "临终托付", "复仇", "继承遗志", "实力提升"],
            difficulty="normal"
        )

        # 11. 神秘组织模板
        mysterious_org_template = PlotTemplate(
            template_id="mysterious_org_001",
            name="神秘组织招揽",
            type=TemplateType.BREAKTHROUGH,
            scenes=[
                SceneTemplate("scene_1", "神秘邀请", "收到神秘组织的邀请或关注",
                            emotional_impact=0.5, required_elements=["神秘邀请", "组织关注"]),
                SceneTemplate("scene_2", "考验测试", "经历神秘组织的各种考验和测试",
                            emotional_impact=0.6, required_elements=["组织考验", "艰难测试"]),
                SceneTemplate("scene_3", "展露天赋", "在考验中展露惊人的天赋和潜力",
                            emotional_impact=0.8, required_elements=["展露天赋", "惊人潜力"]),
                SceneTemplate("scene_4", "获得认可", "获得组织高层的认可和赏识",
                            emotional_impact=0.85, required_elements=["获得认可", "高层赏识"]),
                SceneTemplate("scene_5", "加入组织", "成功加入神秘组织，获得强大资源和地位",
                            emotional_impact=0.9, required_elements=["加入组织", "获得地位"]),
            ],
            shuangdian_points=[3, 4, 5],
            tags=["神秘组织", "招揽", "考验", "天赋", "地位提升"],
            difficulty="hard"
        )

        # 12. 兄弟反目模板
        brother_betrayal_template = PlotTemplate(
            template_id="brother_betrayal_001",
            name="兄弟反目成仇",
            type=TemplateType.REVENGE,
            scenes=[
                SceneTemplate("scene_1", "兄弟情深", "与结拜兄弟感情深厚，互相信任",
                            emotional_impact=0.6, required_elements=["兄弟情深", "互相信任"]),
                SceneTemplate("scene_2", "利益冲突", "因为巨大利益产生冲突和分歧",
                            emotional_impact=0.4, required_elements=["利益冲突", "产生分歧"]),
                SceneTemplate("scene_3", "背叛背叛", "兄弟背叛主角，投靠敌人",
                            emotional_impact=0.2, required_elements=["兄弟背叛", "投靠敌人"]),
                SceneTemplate("scene_4", "心碎觉醒", "主角心碎之后觉醒新的力量或决心",
                            emotional_impact=0.7, required_elements=["心碎觉醒", "新的决心"]),
                SceneTemplate("scene_5", "复仇对决", "与反目兄弟展开最终对决，清算恩怨",
                            emotional_impact=0.9, required_elements=["复仇对决", "清算恩怨"]),
            ],
            shuangdian_points=[4, 5],
            tags=["兄弟反目", "背叛", "复仇", "对决", "恩怨清算"],
            difficulty="hard"
        )

        self.templates = {
            "divorce_flow": divorce_template,
            "rebirth_flow": rebirth_template,
            "system_flow": system_template,
            "auction": auction_template,
            "secret_realm": secret_realm_template,
            "tournament": tournament_template,
            "undercover": undercover_template,
            "breakthrough": breakthrough_template,
            "beauty_rescue": beauty_rescue_template,
            "master_inheritance": master_inheritance_template,
            "mysterious_org": mysterious_org_template,
            "brother_betrayal": brother_betrayal_template
        }

    def _create_surprise_events(self):
        """创建意外事件库 - 大幅扩展版本"""
        self.surprise_events = [
            # 原有事件
            {
                "id": "event_001",
                "name": "神秘老者突然出现",
                "type": "helper",
                "impact": 0.7,
                "trigger_conditions": ["绝境", "战斗", "突破关键"],
                "description": "在关键时刻，神秘老者突然出现，提供帮助或指引"
            },
            {
                "id": "event_002",
                "name": "上古阵法被意外激活",
                "type": "power_up",
                "impact": 0.8,
                "trigger_conditions": ["危机时刻", "特殊地点", "血迹激活"],
                "description": "意外激活沉睡的上古阵法，获得强大力量"
            },
            {
                "id": "event_003",
                "name": "主角宝物与敌人产生共鸣",
                "type": "plot_twist",
                "impact": 0.6,
                "trigger_conditions": ["战斗", "宝物接触", "敌人身世"],
                "description": "主角的宝物与敌人的宝物产生神秘共鸣，揭露隐藏秘密"
            },
            {
                "id": "event_004",
                "name": "盟友突然背叛",
                "type": "betrayal",
                "impact": -0.4,
                "trigger_conditions": ["关键时刻", "利益冲突", "敌人威胁"],
                "description": "最信任的盟友突然背叛主角，陷入绝境"
            },
            {
                "id": "event_005",
                "name": "隐藏血脉觉醒",
                "type": "power_up",
                "impact": 0.9,
                "trigger_conditions": ["生死关头", "血腥场面", "情绪激动"],
                "description": "在生死关头觉醒隐藏的上古血脉，实力暴增"
            },
            {
                "id": "event_006",
                "name": "得到神秘传承",
                "type": "power_up",
                "impact": 0.85,
                "trigger_conditions": ["奇遇", "传承考验", "资质认可"],
                "description": "通过考验获得古代强者的完整传承"
            },
            {
                "id": "event_007",
                "name": "天劫降临",
                "type": "crisis",
                "impact": -0.3,
                "trigger_conditions": ["突破", "实力提升", "外界关注"],
                "description": "实力提升引来天劫，面临生死考验"
            },
            {
                "id": "event_008",
                "name": "故人之后出现",
                "type": "helper",
                "impact": 0.5,
                "trigger_conditions": ["危机", "特定地点", "身份信物"],
                "description": "前世故人的后代出现，提供帮助或信息"
            },

            # 新增事件 - 情感类
            {
                "id": "event_009",
                "name": "失散亲人意外重逢",
                "type": "emotional",
                "impact": 0.6,
                "trigger_conditions": ["特定地点", "身份识别", "情感触发"],
                "description": "与失散多年的亲人意外重逢，获得情感支持和重要信息"
            },
            {
                "id": "event_010",
                "name": "暗恋对象身份揭露",
                "type": "plot_twist",
                "impact": 0.7,
                "trigger_conditions": ["情感冲突", "身份调查", "意外发现"],
                "description": "发现暗恋对象有着惊人的身份背景，改变故事走向"
            },
            {
                "id": "event_011",
                "name": "前世记忆觉醒",
                "type": "power_up",
                "impact": 0.8,
                "trigger_conditions": ["强烈刺激", "相似场景", "情感波动"],
                "description": "强烈刺激下觉醒前世记忆，获得宝贵经验和技能"
            },

            # 新增事件 - 势力类
            {
                "id": "event_012",
                "name": "神秘组织关注",
                "type": "plot_twist",
                "impact": 0.5,
                "trigger_conditions": ["实力展露", "特殊事件", "外界注意"],
                "description": "主角的表现引起神秘组织的关注，收到邀请或威胁"
            },
            {
                "id": "event_013",
                "name": "旧部下寻来",
                "type": "helper",
                "impact": 0.6,
                "trigger_conditions": ["身份揭露", "势力扩张", "消息传播"],
                "description": "前世或过去的部下寻来，带来忠诚追随者和资源"
            },
            {
                "id": "event_014",
                "name": "敌对势力内斗",
                "type": "opportunity",
                "impact": 0.7,
                "trigger_conditions": ["敌人内部", "利益分配", "权力争夺"],
                "description": "敌对势力发生内斗，为主角创造了可乘之机"
            },
            {
                "id": "event_015",
                "name": "中立势力倒戈",
                "type": "helper",
                "impact": 0.6,
                "trigger_conditions": ["实力对比", "利益诱惑", "道义选择"],
                "description": "原本中立的关键势力决定支持主角一方"
            },

            # 新增事件 - 宝物类
            {
                "id": "event_016",
                "name": "神器认主",
                "type": "power_up",
                "impact": 0.9,
                "trigger_conditions": ["血脉匹配", "实力达到", "时机成熟"],
                "description": "传说中的神器主动选择主角作为新主人"
            },
            {
                "id": "event_017",
                "name": "宝物融合进化",
                "type": "power_up",
                "impact": 0.8,
                "trigger_conditions": ["特殊材料", "能量注入", "时机契合"],
                "description": "主角的宝物与其他宝物融合，进化为更强的形态"
            },
            {
                "id": "event_018",
                "name": "空间戒指发现",
                "type": "opportunity",
                "impact": 0.5,
                "trigger_conditions": ["意外获得", "身份验证", "权限解锁"],
                "description": "意外获得前人留下的空间戒指，里面藏有重要资源"
            },

            # 新增事件 - 环境类
            {
                "id": "event_019",
                "name": "秘境空间开启",
                "type": "opportunity",
                "impact": 0.7,
                "trigger_conditions": ["天时地利", "星象异变", "能量汇聚"],
                "description": "百年一遇的秘境空间意外开启，里面机缘无数"
            },
            {
                "id": "event_020",
                "name": "时空裂缝出现",
                "type": "crisis",
                "impact": -0.3,
                "trigger_conditions": ["能量暴动", "空间不稳", "实验失败"],
                "description": "时空裂缝突然出现，威胁周围一切，但也可能通往未知"
            },
            {
                "id": "event_021",
                "name": "灵气潮汐爆发",
                "type": "opportunity",
                "impact": 0.6,
                "trigger_conditions": ["天象变化", "环境异变", "能量波动"],
                "description": "罕见的灵气潮汐爆发，大幅提升修炼效率"
            },

            # 新增事件 - 修行类
            {
                "id": "event_022",
                "name": "顿悟突破",
                "type": "power_up",
                "impact": 0.8,
                "trigger_conditions": ["心境契合", "外力刺激", "机缘巧合"],
                "description": "在特定心境下突然顿悟，实力大幅突破"
            },
            {
                "id": "event_023",
                "name": "功法缺陷暴露",
                "type": "crisis",
                "impact": -0.4,
                "trigger_conditions": ["实战检验", "层次提升", "对比发现"],
                "description": "当前功法在关键时刻暴露致命缺陷，需要寻找新的解决方法"
            },
            {
                "id": "event_024",
                "name": "丹药炉鼎异变",
                "type": "opportunity",
                "impact": 0.6,
                "trigger_conditions": ["炼丹过程", "材料特殊", "能量反应"],
                "description": "炼制丹药时炉鼎发生异变，产生意想不到的效果"
            },

            # 新增事件 - 身份类
            {
                "id": "event_025",
                "name": "真实身份揭露",
                "type": "plot_twist",
                "impact": 0.7,
                "trigger_conditions": ["证据出现", "记忆恢复", "他人指认"],
                "description": "主角的真实身份被揭露，可能是名人后代或重要人物"
            },
            {
                "id": "event_026",
                "name": "被误认他人",
                "type": "plot_twist",
                "impact": 0.5,
                "trigger_conditions": ["相貌相似", "身份混淆", "特殊场合"],
                "description": "主角被误认为是某个重要人物，带来意想不到的机遇和危险"
            },
            {
                "id": "event_027",
                "name": "血脉诅咒发作",
                "type": "crisis",
                "impact": -0.5,
                "trigger_conditions": ["血脉激活", "月圆之夜", "情绪波动"],
                "description": "家族血脉中的古老诅咒突然发作，带来生命危险"
            },

            # 新增事件 - 奇遇类
            {
                "id": "event_028",
                "name": "仙人指路",
                "type": "helper",
                "impact": 0.8,
                "trigger_conditions": ["绝境求索", "心诚则灵", "机缘成熟"],
                "description": "在绝境中诚心祈求，得到路过的仙人指点迷津"
            },
            {
                "id": "event_029",
                "name": "宠物进化",
                "type": "power_up",
                "impact": 0.6,
                "trigger_conditions": ["战斗激励", "特殊宝物", "环境刺激"],
                "description": "主角的宠物或伙伴在关键时刻进化，获得新能力"
            },
            {
                "id": "event_030",
                "name": "预言应验",
                "type": "plot_twist",
                "impact": 0.7,
                "trigger_conditions": ["时间节点", "条件满足", "命运安排"],
                "description": "古老的预言开始在主角身上应验，揭示更大的命运"
            }
        ]

    def _create_character_archetypes(self):
        """创建角色原型"""
        self.character_archetypes = {
            "protagonist": {
                "traits": ["坚毅", "聪明", "重情重义", "杀伐果断"],
                "growth_arc": "从弱小到强大",
                "core_motivation": "保护亲友，追求极致"
            },
            "mentor": {
                "traits": ["智慧", "神秘", "强大", "指导"],
                "role": "引导者和保护者"
            },
            "rival": {
                "traits": ["傲慢", "嫉妒", "实力强", "有背景"],
                "role": "前期反派，后期可能转化"
            },
            "ally": {
                "traits": ["忠诚", "各有特长", "讲义气"],
                "role": "伙伴和助力"
            },
            "love_interest": {
                "traits": ["美丽", "有实力", "有个性", "支持主角"],
                "role": "情感支撑和战力"
            }
        }

class SurpriseEventEngine:
    """意外事件随机引擎"""

    def __init__(self, template_library: TomatoTemplateLibrary):
        self.template_library = template_library
        self.event_history: List[str] = []
        self.event_weights: Dict[str, float] = {}
        self._initialize_event_weights()

    def _initialize_event_weights(self):
        """初始化事件权重"""
        for event in self.template_library.surprise_events:
            self.event_weights[event["id"]] = 1.0

    def select_surprise_event(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """根据上下文选择合适的意外事件"""

        # 获取当前情绪值和情节阶段
        current_emotion = context.get("emotion_value", 0.5)
        plot_stage = context.get("plot_stage", "early")
        recent_events = context.get("recent_events", [])

        # 筛选符合条件的事件
        suitable_events = []
        for event in self.template_library.surprise_events:
            # 避免重复使用相近的事件
            if event["id"] in self.event_history[-5:]:  # 最近5个事件不重复
                continue

            # 根据情绪状态选择事件类型
            if current_emotion < 0.3 and event["type"] in ["helper", "power_up"]:
                # 情绪低落时，增加帮助和提升事件权重
                suitable_events.append((event, 2.0))
            elif current_emotion > 0.7 and event["type"] in ["crisis", "betrayal"]:
                # 情绪高涨时，可以增加危机事件
                suitable_events.append((event, 1.5))
            else:
                suitable_events.append((event, 1.0))

        if not suitable_events:
            return None

        # 根据权重随机选择事件
        events, weights = zip(*suitable_events)
        total_weight = sum(weights)
        probabilities = [w / total_weight for w in weights]

        selected_event = np.random.choice(events, p=probabilities)
        self.event_history.append(selected_event["id"])

        logger.info(f"🎲 意外事件触发：{selected_event['name']} (类型: {selected_event['type']})")
        return selected_event

class TemplateBasedCreationEngine:
    """模板化创作引擎主类"""

    def __init__(self):
        self.template_library = TomatoTemplateLibrary()
        self.surprise_engine = SurpriseEventEngine(self.template_library)
        self.current_template: Optional[PlotTemplate] = None
        self.current_scene_index = 0
        self.creation_history: List[Dict] = []

        logger.info("🚀 模板化创作引擎初始化完成")

    def select_template(self, novel_style: str = "mixed", difficulty: str = "normal") -> PlotTemplate:
        """选择合适的模板"""

        available_templates = []
        for template in self.template_library.templates.values():
            if template.difficulty == difficulty or difficulty == "mixed":
                available_templates.append(template)

        if not available_templates:
            # 默认选择系统流模板
            return self.template_library.templates["system_flow"]

        # 根据风格偏好选择模板
        if novel_style == "revenge":
            revenge_templates = [t for t in available_templates if t.type == TemplateType.REVENGE]
            if revenge_templates:
                return random.choice(revenge_templates)
        elif novel_style == "rebirth":
            rebirth_templates = [t for t in available_templates if t.type == TemplateType.REBIRTH]
            if rebirth_templates:
                return random.choice(rebirth_templates)

        # 随机选择
        selected_template = random.choice(available_templates)
        logger.info(f"📋 选择模板：{selected_template.name} ({selected_template.type.value})")
        return selected_template

    def generate_scene_content(self, scene: SceneTemplate, context: Dict[str, Any]) -> Dict[str, Any]:
        """生成场景内容"""

        # 检查是否需要插入意外事件
        surprise_event = None
        if random.random() < 0.3:  # 30%概率触发意外事件
            surprise_event = self.surprise_engine.select_surprise_event(context)

        # 构建场景内容框架
        scene_content = {
            "scene_id": scene.scene_id,
            "title": scene.title,
            "description": scene.description,
            "emotional_impact": scene.emotional_impact,
            "required_elements": scene.required_elements,
            "optional_elements": scene.optional_elements,
            "surprise_event": surprise_event,
            "word_count_target": random.randint(*scene.word_count_range),
            "generation_prompt": self._build_scene_prompt(scene, context, surprise_event)
        }

        return scene_content

    def _build_scene_prompt(self, scene: SceneTemplate, context: Dict[str, Any],
                          surprise_event: Optional[Dict] = None) -> str:
        """构建场景生成提示词"""

        prompt_parts = [
            f"场景标题：{scene.title}",
            f"场景描述：{scene.description}",
            f"情绪冲击力：{scene.emotional_impact:.1f}/1.0",
            "",
            "必需元素："
        ]

        for element in scene.required_elements:
            prompt_parts.append(f"- {element}")

        if scene.optional_elements:
            prompt_parts.append("\n可选元素：")
            for element in scene.optional_elements:
                prompt_parts.append(f"- {element}")

        if surprise_event:
            prompt_parts.extend([
                "",
                f"意外事件：{surprise_event['name']}",
                f"事件描述：{surprise_event['description']}",
                f"事件影响：{surprise_event['impact']:.1f}"
            ])

        prompt_parts.extend([
            "",
            "写作要求：",
            "- 突出情绪冲击，让读者产生强烈共鸣",
            "- 节奏紧凑，避免冗长铺垫",
            "- 重点刻画人物反应和心理变化",
            "- 为下一个场景做好铺垫"
        ])

        return "\n".join(prompt_parts)

    def generate_plot_outline(self, template: PlotTemplate, customization: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """生成剧情大纲"""

        self.current_template = template
        outline = []

        for i, scene in enumerate(template.scenes):
            context = {
                "scene_index": i,
                "total_scenes": len(template.scenes),
                "template_type": template.type.value,
                "emotion_value": customization.get("emotion_value", 0.5) if customization else 0.5,
                "plot_stage": customization.get("plot_stage", "early") if customization else "early",
                "recent_events": [s.get("surprise_event", {}).get("name") for s in outline]
            }

            scene_content = self.generate_scene_content(scene, context)
            outline.append(scene_content)

            # 记录创作历史
            self.creation_history.append({
                "template_id": template.template_id,
                "scene_id": scene.scene_id,
                "timestamp": len(self.creation_history),
                "had_surprise_event": surprise_event is not None
            })

        logger.info(f"📝 生成剧情大纲完成：{len(outline)}个场景")
        return outline

    def get_optimization_suggestions(self, current_outline: List[Dict]) -> List[str]:
        """获取优化建议"""

        suggestions = []

        # 检查爽点密度
        shuangdian_count = len([scene for scene in current_outline
                              if scene.get("surprise_event") or
                              scene.get("emotional_impact", 0) > 0.7])

        if shuangdian_count < len(current_outline) * 0.3:
            suggestions.append("爽点密度偏低，建议增加更多高潮情节")

        # 检查情绪曲线
        emotion_values = [scene.get("emotional_impact", 0.5) for scene in current_outline]
        if len(emotion_values) > 3:
            if all(emotion_values[i] <= emotion_values[i+1] for i in range(len(emotion_values)-1)):
                suggestions.append("情绪曲线过于平缓，建议增加起伏变化")

        # 检查意外事件分布
        surprise_count = len([scene for scene in current_outline if scene.get("surprise_event")])
        if surprise_count < len(current_outline) * 0.2:
            suggestions.append("意外事件较少，建议增加更多转折元素")

        return suggestions

def create_template_based_creation_engine() -> TemplateBasedCreationEngine:
    """创建模板化创作引擎实例"""
    return TemplateBasedCreationEngine()

# 测试代码
if __name__ == "__main__":
    print("🚀 测试模板化创作引擎...")

    engine = create_template_based_creation_engine()

    # 测试模板选择
    template = engine.select_template("revenge", "normal")
    print(f"✅ 模板选择成功：{template.name}")

    # 测试剧情大纲生成
    outline = engine.generate_plot_outline(template)
    print(f"✅ 剧情大纲生成成功：{len(outline)}个场景")

    # 测试优化建议
    suggestions = engine.get_optimization_suggestions(outline)
    print(f"✅ 优化建议：{len(suggestions)}条")
    for suggestion in suggestions:
        print(f"   - {suggestion}")

    print("🎉 模板化创作引擎测试完成！")