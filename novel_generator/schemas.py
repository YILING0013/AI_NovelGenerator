# -*- coding: utf-8 -*-
"""
Schema模型定义 - 使用Pydantic进行数据验证

该模块定义了小说生成系统中的所有数据结构Schema，确保：
1. 数据类型安全
2. 格式一致性
3. 数据完整性
"""
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Dict, Literal
from enum import Enum


class ConflictType(str, Enum):
    """冲突类型枚举"""
    SURVIVAL = "生存"
    POWER = "权力"
    EMOTION = "情感"
    PHILOSOPHY = "理念"


class SuspenseLevel(str, Enum):
    """悬念等级枚举"""
    SSS = "SSS级"
    SS = "SS级"
    S = "S级"
    A = "A级"
    B = "B级"
    C = "C级"


class ProgrammerThinkingMode(str, Enum):
    """匠心思维模式枚举"""
    ORIGIN_PERSPECTIVE = "本源透视"
    QIN_REMOVAL = "去沁"
    KINTSUGI = "金缮"
    STRUCTURE_DECONSTRUCTION = "结构解构"
    VALUE_REASSESSMENT = "价值重估"


class RomanceType(str, Enum):
    """暧昧类型枚举"""
    PURE_PROTECTION = "纯粹守护"
    UNCONDITIONAL_TRUST = "无悔付出"
    SHY_FLIRTATION = "羞涩试探"
    JEALOUSY_POSSESSIVENESS = "占有欲"
    FORCED_PROXIMITY = "强制近距离"
    DANGER_SITUATION = "危机中的温情"


class BasicMetaInfo(BaseModel):
    """基础元信息Schema"""
    chapter_number: int = Field(..., gt=0, description="章节序号，必须大于0")
    chapter_title: str = Field(..., min_length=1, description="章节标题，不能为空")
    location: str = Field(..., description="章节定位，如：第1卷 序幕 - 子幕1 危机初现")
    core_function: str = Field(..., min_length=1, description="核心功能，一句话概括本章作用")
    target_word_count: int = Field(..., gt=0, le=10000, description="目标字数，1-10000字")
    characters_involved: List[str] = Field(default_factory=list, description="出场角色列表")

    @field_validator('chapter_number')
    @classmethod
    def validate_chapter_number(cls, v):
        if v <= 0:
            raise ValueError("章节序号必须大于0")
        return v


class TensionAndConflict(BaseModel):
    """张力与冲突Schema"""
    conflict_type: ConflictType = Field(..., description="冲突类型")
    core_conflict: str = Field(..., min_length=1, description="核心冲突点")
    tension_curve: str = Field(..., min_length=1, description="紧张感曲线，格式：铺垫→爬升→爆发→回落/悬念")

    @field_validator('tension_curve')
    @classmethod
    def validate_tension_curve(cls, v):
        required_phases = ["铺垫", "爬升", "爆发", "回落/悬念"]
        for phase in required_phases:
            if phase not in v and "回落" not in v:
                raise ValueError(f"紧张感曲线必须包含所有四个阶段: {required_phases}")
        return v


class ProgrammerThinking(BaseModel):
    """匠心思维应用Schema"""
    thinking_mode: ProgrammerThinkingMode = Field(..., description="思维模式")
    application_scene: str = Field(..., min_length=1, description="应用场景")
    visual_description: str = Field(..., min_length=1, description="视觉化描述")
    classic_quote: Optional[str] = Field(None, description="经典台词")


class ForeshadowingInfo(BaseModel):
    """伏笔与信息差Schema"""
    plant_foreshadowings: List[str] = Field(default_factory=list, description="本章植入伏笔列表")
    reveal_foreshadowings: List[str] = Field(default_factory=list, description="本章回收伏笔列表")
    information_gap: Optional[str] = Field(None, description="信息差控制，描述主角知道vs敌人以为的对比")


class RomanceScene(BaseModel):
    """暧昧与修罗场Schema"""
    female_lead_involved: str = Field(..., description="涉及的女性角色互动描述")
    interaction_type: Optional[RomanceType] = Field(None, description="暧昧类型")
    interaction_level: Optional[str] = Field(None, description="暧昧等级")
    technique_used: Optional[str] = Field(None, description="技法运用")
    key_dialogue: Optional[str] = Field(None, description="关键对话")
    atmosphere: Optional[str] = Field(None, description="氛围描写")

    @model_validator(mode='after')
    def validate_no_interaction(self):
        """如果没有女性角色互动，必须明确说明"""
        if "不涉及女性角色互动" in self.female_lead_involved:
            return self
        if not self.interaction_type:
            raise ValueError("涉及女性角色互动时，必须指定暧昧类型")
        return self


class PlotEssential(BaseModel):
    """剧情精要Schema"""
    opening: str = Field(..., min_length=1, description="开场场景")
    development: str = Field(..., min_length=1, description="发展节点")
    climax: str = Field(..., min_length=1, description="高潮事件")
    ending: str = Field(..., min_length=1, description="收尾状态/悬念")


class ConnectionDesign(BaseModel):
    """衔接设计Schema"""
    connect_previous: str = Field(..., min_length=1, description="承上：承接前文")
    transition: Optional[str] = Field(None, description="转场：转场方式")
    setup_next: str = Field(..., min_length=1, description="启下：为后续埋下伏笔")


class ChapterBlueprint(BaseModel):
    """章节蓝图完整Schema - 7节标准格式"""
    # 基础信息
    basic_info: BasicMetaInfo = Field(..., description="基础元信息")

    # 核心模块
    tension_conflict: TensionAndConflict = Field(..., description="张力与冲突")
    programmer_thinking: ProgrammerThinking = Field(..., description="匠心思维应用")
    foreshadowing_info: ForeshadowingInfo = Field(..., description="伏笔与信息差")
    romance_scene: RomanceScene = Field(..., description="暧昧与修罗场")
    plot_essential: PlotEssential = Field(..., description="剧情精要")
    connection_design: ConnectionDesign = Field(..., description="衔接设计")

    # 扩展字段（可选）
    emotional_arc: Optional[str] = Field(None, description="情感弧光")
    emotional_intensity: Optional[str] = Field(None, description="情感强度")
    turning_point: Optional[str] = Field(None, description="关键转折点")
    emotional_memory: Optional[str] = Field(None, description="情感记忆点")
    conflict_design: Optional[str] = Field(None, description="冲突设计")
    character_arc_in_chapter: Optional[str] = Field(None, description="人物弧光")
    limitations: Optional[str] = Field(None, description="限制条件")
    opening_design: Optional[str] = Field(None, description="开场设计")
    climax_arrangement: Optional[str] = Field(None, description="高潮安排")
    ending_strategy: Optional[str] = Field(None, description="收尾策略")
    pacing_control: Optional[str] = Field(None, description="节奏控制")
    main_hook: Optional[str] = Field(None, description="主钩子")
    secondary_hook: Optional[str] = Field(None, description="次钩子")
    style_requirements: Optional[str] = Field(None, description="风格要求")
    language_features: Optional[str] = Field(None, description="语言特色")
    avoidance_items: Optional[str] = Field(None, description="避免事项")
    key_scene: Optional[str] = Field(None, description="关键场景")
    foreshadowing_management: Optional[str] = Field(None, description="伏笔管理")
    character_state_in_chapter: Optional[str] = Field(None, description="角色状态")
    worldview_progression: Optional[str] = Field(None, description="世界观推进")
    shuangdian_position: Optional[str] = Field(None, description="爽点位置")

    @model_validator(mode='after')
    def validate_completeness(self):
        """验证所有必需字段都存在"""
        # 确保暧昧与修罗场字段即使不涉及也要说明
        if "不涉及女性角色互动" not in self.romance_scene.female_lead_involved:
            if not self.romance_scene.interaction_type:
                raise ValueError("涉及女性角色互动时，必须指定暧昧类型")
        return self


class ChapterDirectoryEntry(BaseModel):
    """章节目录条目Schema"""
    chapter_number: int = Field(..., gt=0, description="章节序号")
    chapter_title: str = Field(..., min_length=1, description="章节标题")
    chapter_role: str = Field(..., description="本章定位")
    chapter_purpose: str = Field(..., min_length=1, description="核心作用")
    suspense_level: Optional[SuspenseLevel] = Field(None, description="悬念密度")
    foreshadowing: Optional[str] = Field(None, description="伏笔操作")
    plot_twist_level: Optional[str] = Field(None, description="认知颠覆")
    chapter_summary: str = Field(..., min_length=1, description="本章简述")
    target_word_count: Optional[int] = Field(None, description="字数目标")

    # 扩展字段
    emotional_arc: Optional[str] = None
    emotional_intensity: Optional[str] = None
    turning_point: Optional[str] = None
    emotional_memory: Optional[str] = None
    conflict_design: Optional[str] = None
    character_arc_in_chapter: Optional[str] = None
    limitations: Optional[str] = None
    opening_design: Optional[str] = None
    climax_arrangement: Optional[str] = None
    ending_strategy: Optional[str] = None
    pacing_control: Optional[str] = None
    main_hook: Optional[str] = None
    secondary_hook: Optional[str] = None
    style_requirements: Optional[str] = None
    language_features: Optional[str] = None
    avoidance_items: Optional[str] = None
    key_scene: Optional[str] = None
    foreshadowing_management: Optional[str] = None
    character_state_in_chapter: Optional[str] = None
    worldview_progression: Optional[str] = None
    shuangdian_position: Optional[str] = None
    word_count_target: Optional[str] = None

    # 程序员思维应用
    programmer_thinking: Optional[str] = None
    programmer_scene: Optional[str] = None
    programmer_quote: Optional[str] = None
    programmer_foreshadow: Optional[str] = None

    # 伏笔植入清单
    foreshadow_plant: Optional[str] = None
    foreshadow_reveal: Optional[str] = None

    # 暧昧场景设计
    romance_female_lead: Optional[str] = None
    romance_type: Optional[str] = None
    romance_level: Optional[str] = None
    romance_technique: Optional[str] = None
    romance_dialogue: Optional[str] = None
    romance_atmosphere: Optional[str] = None
    romance_progress: Optional[str] = None

    # 爽点密度检查
    shuangdian_count: Optional[str] = None
    shuangdian_list: Optional[str] = None

    # 女主成长线推进
    female_lead_growth: Optional[str] = None
    female_lead_arc: Optional[str] = None

    # 质量检查清单
    quality_check: Optional[str] = None
    identity_consistency: Optional[str] = None
    worldview_consistency: Optional[str] = None
    emotional_coherence: Optional[str] = None


class ValidationReport(BaseModel):
    """验证报告Schema"""
    is_valid: bool = Field(..., description="是否通过验证")
    errors: List[str] = Field(default_factory=list, description="错误列表")
    warnings: List[str] = Field(default_factory=list, description="警告列表")
    suggestions: List[str] = Field(default_factory=list, description="改进建议")

    def add_error(self, message: str):
        """添加错误"""
        self.errors.append(message)
        self.is_valid = False

    def add_warning(self, message: str):
        """添加警告"""
        self.warnings.append(message)

    def add_suggestion(self, message: str):
        """添加建议"""
        self.suggestions.append(message)

    @property
    def has_issues(self) -> bool:
        """是否有问题"""
        return len(self.errors) > 0 or len(self.warnings) > 0
