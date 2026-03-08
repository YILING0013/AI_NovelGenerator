#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
架构解析器（全面版）
从 Novel_architecture.txt 中提取所有12节内容用于一致性检查
"""

import re
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field

from utils import resolve_architecture_file

logger = logging.getLogger(__name__)


@dataclass
class CharacterInfo:
    """角色信息"""
    name: str
    role: str = ""
    bloodline: str = ""
    first_appear_chapter: int = 0
    description: str = ""
    relationships: Dict[str, str] = field(default_factory=dict)


@dataclass
class PlotArc:
    """剧情弧"""
    name: str
    volume: int
    start_chapter: int
    end_chapter: int
    key_events: List[str] = field(default_factory=list)
    participating_characters: List[str] = field(default_factory=list)


@dataclass
class Skill:
    """技能/法宝"""
    name: str
    category: str = ""  # 法宝/绝技/被动/形态
    description: str = ""
    effects: List[str] = field(default_factory=list)


@dataclass
class WorldRegion:
    """世界区域"""
    name: str
    bloodline_affinity: str = ""
    buff: str = ""
    debuff: str = ""
    features: List[str] = field(default_factory=list)
    factions: List[str] = field(default_factory=list)


@dataclass
class ArchitectureData:
    """架构数据汇总（全12节）"""
    # === 第0节：小说设定 ===
    title: str = ""
    genre: str = ""
    total_chapters: int = 0
    target_words: str = ""
    core_elements: List[str] = field(default_factory=list)
    
    # === 第1节：核心种子 ===
    core_seed: str = ""
    
    # === 第2节：主角战力体系 ===
    protagonist_weapons: List[Skill] = field(default_factory=list)
    protagonist_skills: List[Skill] = field(default_factory=list)
    protagonist_modes: List[Skill] = field(default_factory=list)
    awakening_timeline: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # === 第3节：角色总表 ===
    characters: Dict[str, CharacterInfo] = field(default_factory=dict)
    
    # === 第4节：世界观 ===
    world_regions: Dict[str, WorldRegion] = field(default_factory=dict)
    time_history: List[str] = field(default_factory=list)
    cultivation_realms: List[str] = field(default_factory=list)
    
    # === 第5节：情节架构 ===
    plot_arcs: List[PlotArc] = field(default_factory=list)
    chapter_events: Dict[int, List[str]] = field(default_factory=dict)
    
    # === 第6节：五脉百科 ===
    bloodlines: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    factions_by_bloodline: Dict[str, List[str]] = field(default_factory=dict)
    
    # === 第7节：上古阴谋 ===
    mysteries: List[Dict[str, str]] = field(default_factory=list)
    foreshadowing_pairs: List[Dict[str, Any]] = field(default_factory=list)
    
    # === 第8节：禁忌美学 ===
    romance_guidelines: Dict[str, str] = field(default_factory=dict)
    
    # === 第9节：蓝图模板 ===
    blueprint_template: str = ""
    required_modules: List[str] = field(default_factory=list)
    
    # === 第10节：知识库策略 ===
    knowledge_strategy: Dict[str, str] = field(default_factory=dict)
    
    # === 第11节：仙界势力 ===
    celestial_factions: List[Dict[str, str]] = field(default_factory=list)
    
    # 解析状态
    sections_parsed: List[int] = field(default_factory=list)


class ArchitectureParser:
    """架构文件解析器（全12节）"""
    
    # 12节标题
    SECTION_TITLES = {
        0: "小说设定",
        1: "核心种子",
        2: "主角战力体系",
        3: "角色总表",
        4: "世界观",
        5: "情节架构",
        6: "五脉百科",
        7: "上古阴谋",
        8: "禁忌美学",
        9: "蓝图模板",
        10: "知识库策略",
        11: "仙界势力"
    }
    
    # NOTE: Character constants are now extracted dynamically in parse()
    # Fallback values if architecture file format changes
    DEFAULT_PROTAGONIST = "主角"
    DEFAULT_ANTAGONIST = "反派"
    
    # 五脉 (These are world-building constants, not novel-specific)
    FIVE_BLOODLINES = ["道脉", "巫脉", "魔脉", "释脉", "儒脉"]
    
    # 境界 (Generic cultivation system)
    CULTIVATION_REALMS = [
        "炼气", "筑基", "金丹", "元婴", "化神", "炼虚", "合体", "大乘", "渡劫"
    ]
    
    # 世界区域 (Can be overridden by architecture)
    DEFAULT_WORLD_REGIONS = ["中土神州", "北荒巫域", "南疆魔渊", "西漠佛国", "东海儒岛", 
                     "浮云天宫", "幽冥界", "妖界"]
    
    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        self.arch_path = Path(resolve_architecture_file(str(self.filepath), prefer_active=False))
        self.raw_content = ""
        self.sections: Dict[int, str] = {}
        self.data = ArchitectureData()
        
        # Dynamic character extraction (will be populated in parse())
        self.protagonist = self.DEFAULT_PROTAGONIST
        self.female_leads: List[str] = []
        self.antagonist = self.DEFAULT_ANTAGONIST
        self.world_regions: List[str] = self.DEFAULT_WORLD_REGIONS.copy()
    
    def parse(self) -> ArchitectureData:
        """解析架构文件（所有12节）"""
        if not self.arch_path.exists():
            logger.warning(f"Architecture file not found: {self.arch_path}")
            return self.data
        
        try:
            with open(self.arch_path, 'r', encoding='utf-8') as f:
                self.raw_content = f.read()
            
            # 分割各节内容
            self._split_sections()
            
            # 依次解析12节
            self._parse_section_0_settings()
            self._parse_section_1_core_seed()
            self._parse_section_2_power_system()
            self._parse_section_3_characters()
            self._parse_section_4_world()
            self._parse_section_5_plot()
            self._parse_section_6_factions()
            self._parse_section_7_mysteries()
            self._parse_section_8_romance()
            self._parse_section_9_template()
            self._parse_section_10_knowledge()
            self._parse_section_11_celestial()
            
            logger.info(f"Parsed {len(self.data.sections_parsed)}/12 sections")
            
        except Exception as e:
            logger.error(f"Failed to parse architecture: {e}")
            import traceback
            traceback.print_exc()
        
        return self.data
    
    def _split_sections(self):
        """分割12节内容"""
        self.sections = {}

        header_matches: list[tuple[int, int, int]] = []

        legacy_pattern = re.compile(r"(?m)^#===\s*(\d+)\)\s*([^=\n]+?)\s*===\s*$")
        for match in legacy_pattern.finditer(self.raw_content):
            header_matches.append((match.start(), match.end(), int(match.group(1))))

        markdown_pattern = re.compile(r"(?m)^##\s*(\d+)\.\s*([^\n]+?)\s*$")
        for match in markdown_pattern.finditer(self.raw_content):
            header_matches.append((match.start(), match.end(), int(match.group(1))))

        if not header_matches:
            return

        header_matches.sort(key=lambda item: item[0])
        for idx, (_, header_end, section_num) in enumerate(header_matches):
            section_start = header_end
            section_end = (
                header_matches[idx + 1][0]
                if idx + 1 < len(header_matches)
                else len(self.raw_content)
            )
            if section_num not in self.sections:
                self.sections[section_num] = self.raw_content[section_start:section_end]
    
    def _parse_section_0_settings(self):
        """第0节：小说设定"""
        if 0 not in self.sections:
            return
        content = self.sections[0]
        
        # 标题 (Robutst regex for markdown: **Title:**)
        title_match = re.search(r"(?:小说名称|核心书名)[^《]*《([^》]+)》", content)
        if title_match:
            self.data.title = title_match.group(1)
        
        # 类型
        genre_match = re.search(r"类型[：:]\s*([^\n]+)", content)

        if genre_match:
            self.data.genre = genre_match.group(1).strip()
        
        # 目标字数
        words_match = re.search(r"目标字数[：:]\s*([^\n]+)", content)
        if words_match:
            self.data.target_words = words_match.group(1).strip()
        
        # 章节数 (从目标字数估算或查找)
        chapter_match = re.search(r"约(\d+)-(\d+)章", content)
        if chapter_match:
            self.data.total_chapters = int(chapter_match.group(2))
        elif "1000-1200万字" in self.data.target_words:
            self.data.total_chapters = 3000 # 估算
        
        # 核心要素
        elements = re.findall(r"[-*]\s*(.+?)(?=\n[*-]|\Z)", content[:2000])
        self.data.core_elements = [e.strip() for e in elements[:10]]
        
        # 女主提取
        female_line_match = re.search(r'女主[^-\n]*[-–—]\s*(.+)', content)
        if female_line_match:
            female_line = female_line_match.group(1)
            paren_names = re.findall(r'[（(]([^）)]+)[）)]', female_line)
            if paren_names:
                self.female_leads = [n.strip() for n in paren_names if n.strip()]
                logger.info(f"Extracted female leads from section 0: {self.female_leads}")
        
        self.data.sections_parsed.append(0)

    
    def _parse_section_1_core_seed(self):
        """第1节：核心种子"""
        if 1 not in self.sections:
            return
        self.data.core_seed = self.sections[1][:1000]
        self.data.sections_parsed.append(1)
    
    def _parse_section_2_power_system(self):
        """第2节：主角战力体系"""
        if 2 not in self.sections:
            return
        content = self.sections[2]
        
        # 法宝
        weapon_match = re.search(r"【([^】]+)】.*?形态[：:]\s*([^\n]+)", content)
        if weapon_match:
            self.data.protagonist_weapons.append(Skill(
                name=weapon_match.group(1),
                category="法宝",
                description=weapon_match.group(2)
            ))
        
        # 核心绝技
        skill_pattern = r"【([^】]+)】[^效果]*效果[：:]\s*([^\n]+)"
        for match in re.finditer(skill_pattern, content):
            self.data.protagonist_skills.append(Skill(
                name=match.group(1),
                category="绝技",
                description=match.group(2)[:200]
            ))
        
        # 形态切换
        mode_pattern = r"【([^】]+模式)】[^定位]*定位[：:]\s*\*\*([^*]+)\*\*"
        for match in re.finditer(mode_pattern, content):
            self.data.protagonist_modes.append(Skill(
                name=match.group(1),
                category="形态",
                description=match.group(2)
            ))
        
        # 觉醒时间线
        awaken_pattern = r"\|\s*\*\*(\w{2})\*\*\s*\|[^|]+\|\s*\*\*([^*]+)\*\*\s*\|\s*第(\d+)章"
        for match in re.finditer(awaken_pattern, content):
            self.data.awakening_timeline[match.group(1)] = {
                "bind_character": match.group(2),
                "chapter": int(match.group(3))
            }
        
        self.data.sections_parsed.append(2)
    
    def _parse_section_3_characters(self):
        """第3节：角色总表 - 动态提取角色"""
        if 3 not in self.sections:
            return
        content = self.sections[3]
        
        # Dynamic extraction: Protagonist
        protagonist_patterns = [
            r'主角[：:]\s*([^\s（(]+)',
            r'角色一[：:]\s*([^\s（(]+)',
            r'姓名[：:]\s*\*\*([^*]+)\*\*',
        ]
        for pattern in protagonist_patterns:
            match = re.search(pattern, content)
            if match:
                self.protagonist = match.group(1).strip()
                break
        
        # Add protagonist to characters
        self.data.characters[self.protagonist] = CharacterInfo(
            name=self.protagonist,
            role="主角",
            bloodline="五脉同修",
            first_appear_chapter=1,
            description="核心主角"
        )
        
        # Dynamic extraction: Female Leads
        female_lead_patterns = [
            r'女主[一二三四五0-9]*[：:]\s*([^\s（(]+)',
            r'女角色[一二三四五0-9]*[：:]\s*([^\s（(]+)',
            r'\*\*女主[一二三四五]*\*\*[：:]\s*([^\s（(]+)',
        ]
        extracted_females = []
        for pattern in female_lead_patterns:
            matches = re.findall(pattern, content)
            extracted_females.extend([m.strip() for m in matches])
        
        # Only overwrite if we found new leads (preserve section 0 extraction)
        if extracted_females:
            self.female_leads = list(dict.fromkeys(extracted_females))[:5]
        
        for name in self.female_leads:
            self.data.characters[name] = CharacterInfo(
                name=name,
                role="女主",
                first_appear_chapter=1
            )
        
        # Dynamic extraction: Antagonist
        antagonist_patterns = [
            r'反派[：:]\s*([^\s（(]+)',
            r'宿敌[：:]\s*([^\s（(]+)',
            r'天命之子[：:]\s*([^\s（(]+)',
        ]
        for pattern in antagonist_patterns:
            match = re.search(pattern, content)
            if match:
                self.antagonist = match.group(1).strip()
                self.data.characters[self.antagonist] = CharacterInfo(
                    name=self.antagonist,
                    role="反派",
                    first_appear_chapter=1
                )
                break
        
        # From text extract more character events
        chapter_event_pattern = r"第(\d+)章[^】]*】[^：:]*[：:]?\s*([^\n]+)"
        for match in re.finditer(chapter_event_pattern, content):
            chapter = int(match.group(1))
            event = match.group(2).strip()
            if chapter not in self.data.chapter_events:
                self.data.chapter_events[chapter] = []
            self.data.chapter_events[chapter].append(event)
        
        self.data.sections_parsed.append(3)
    
    def _parse_section_4_world(self):
        """第4节：世界观"""
        if 4 not in self.sections:
            return
        content = self.sections[4]
        
        # 解析世界区域
        for region in self.world_regions:
            region_pattern = rf"{region}[^法则]*(?:\[法则环境\]|法则环境)[：:]\s*\*\*([^*]+)\*\*"
            match = re.search(region_pattern, content)
            if match:
                self.data.world_regions[region] = WorldRegion(
                    name=region,
                    features=[match.group(1)]
                )
        
        # 境界体系
        self.data.cultivation_realms = self.CULTIVATION_REALMS.copy()
        
        # 历史时间线
        history_pattern = r"\*\*(上古|近古|现世)[^*]*\*\*[：:]\s*([^\n]+)"
        for match in re.finditer(history_pattern, content):
            self.data.time_history.append(f"{match.group(1)}: {match.group(2)}")
        
        self.data.sections_parsed.append(4)

    def _parse_section_5_plot(self):
        """第5节：情节架构"""
        if 5 not in self.sections:
            return
        content = self.sections[5]
        
        # 卷结构 (Updated for 3000 chapters / 7 Volumes)
        # Note: Match the header keywords in Novel_architecture.txt
        volume_patterns = [
            (1, "生存篇", 1, 200),
            (2, "游历篇", 200, 500),
            (3, "揭秘篇", 500, 800),  # Or 学院篇/揭秘篇 depending on exact text
            (4, "冥界篇", 800, 1450),       # Updated name & range
            (5, "统一战争篇", 1450, 1900), # Updated name & range
            (6, "远征篇", 1900, 2350),      # New Volume
            (7, "飞升与终焉", 2350, 3000)   # New Volume
        ]
        
        for vol, name, start, end in volume_patterns:
            # Flexible matching: "第4卷", "第四卷", "冥界篇"
            # Convert arabic to chinese numeral for regex
            cn_numerals = {1:"一", 2:"二", 3:"三", 4:"四", 5:"五", 6:"六", 7:"七"}
            cn_vol = cn_numerals.get(vol, str(vol))
            
            # Regex: (第4卷|第四卷|Vol.4|冥界篇)
            vol_pattern = rf"第(?:{vol}|{cn_vol})卷|Vol\.?{vol}|{re.escape(name)}"
            events = []
            if re.search(vol_pattern, content):
                # Extract bullet points or key events roughly
                # Look for lines starting with "- [ ]" or similar in that section
                # FIX: Stop at next Volume header (## ), NOT subheaders (###)
                section_regex = rf"({vol_pattern})[^\n]*\n(.*?)(?=\n##\s|\Z)"
                section_match = re.search(section_regex, content, re.DOTALL)
                if section_match:
                    raw_text = section_match.group(2)
                    # Extract items like "【Event Name】" - often in checklist or text
                    event_matches = re.findall(r"【([^】]+)】", raw_text)
                    events = event_matches[:10]
            
            self.data.plot_arcs.append(PlotArc(
                name=name,
                volume=vol,
                start_chapter=start,
                end_chapter=end,
                key_events=events
            ))
        
        # 关键章节事件
        chapter_pattern = r"第(\d+)章[^】\n]*】?[：:]?\s*([^\n【]+)"
        for match in re.finditer(chapter_pattern, content):
            ch = int(match.group(1))
            event = match.group(2).strip()[:100]
            if ch not in self.data.chapter_events:
                self.data.chapter_events[ch] = []
            if event and event not in self.data.chapter_events[ch]:
                self.data.chapter_events[ch].append(event)
        
        self.data.sections_parsed.append(5)
    
    def _parse_section_6_factions(self):
        """第6节：五脉百科"""
        if 6 not in self.sections:
            return
        content = self.sections[6]
        
        for bl in self.FIVE_BLOODLINES:
            bl_pattern = rf"{bl}[^#]*?(?=道脉|巫脉|魔脉|释脉|儒脉|#===|$)"
            match = re.search(bl_pattern, content, re.DOTALL)
            if match:
                bl_content = match.group(0)[:2000]
                
                # 提取势力
                faction_pattern = r"\*\*([^*]+宗|[^*]+殿|[^*]+阁|[^*]+门|[^*]+盟)\*\*"
                factions = re.findall(faction_pattern, bl_content)
                
                self.data.bloodlines[bl] = {
                    "raw_excerpt": bl_content[:500],
                    "factions": factions[:5]
                }
                self.data.factions_by_bloodline[bl] = factions[:5]
        
        self.data.sections_parsed.append(6)
    
    def _parse_section_7_mysteries(self):
        """第7节：上古阴谋"""
        if 7 not in self.sections:
            return
        content = self.sections[7]
        
        # 三大谜团
        mystery_pattern = r"###\s*谜团[一二三][：:]\s*([^\n]+)"
        for match in re.finditer(mystery_pattern, content):
            self.data.mysteries.append({
                "title": match.group(1),
                "revealed_volume": "待定"
            })
        
        # 伏笔/payoff
        foreshadow_pattern = r"伏笔[：:]?\s*([^\n]+).*?回收[：:]?\s*([^\n]+)"
        for match in re.finditer(foreshadow_pattern, content, re.DOTALL):
            self.data.foreshadowing_pairs.append({
                "setup": match.group(1)[:100],
                "payoff": match.group(2)[:100]
            })
        
        self.data.sections_parsed.append(7)
    
    def _parse_section_8_romance(self):
        """第8节：禁忌美学"""
        if 8 not in self.sections:
            return
        content = self.sections[8]
        
        self.data.romance_guidelines = {
            "raw_excerpt": content[:1000],
            "parsed": True
        }
        
        self.data.sections_parsed.append(8)
    
    def _parse_section_9_template(self):
        """第9节：蓝图模板"""
        if 9 not in self.sections:
            return
        content = self.sections[9]
        
        self.data.blueprint_template = content[:3000]
        
        # 提取必需模块
        module_pattern = r"【([^】]+)】"
        modules = re.findall(module_pattern, content)
        self.data.required_modules = list(set(modules))[:15]
        
        self.data.sections_parsed.append(9)
    
    def _parse_section_10_knowledge(self):
        """第10节：知识库策略"""
        if 10 not in self.sections:
            return
        content = self.sections[10]
        
        self.data.knowledge_strategy = {
            "raw_excerpt": content[:500],
            "parsed": True
        }
        
        self.data.sections_parsed.append(10)
    
    def _parse_section_11_celestial(self):
        """第11节：仙界势力"""
        if 11 not in self.sections:
            return
        content = self.sections[11]
        
        # 提取仙界势力
        faction_pattern = r"\*\*([^*]+)\*\*[^-]*[-:：]\s*([^\n]+)"
        for match in re.finditer(faction_pattern, content):
            self.data.celestial_factions.append({
                "name": match.group(1),
                "description": match.group(2)[:100]
            })
        
        self.data.sections_parsed.append(11)
    
    # === 验证方法 ===
    
    def get_character_for_chapter(self, chapter_number: int) -> List[str]:
        """获取应在指定章节出现的角色"""
        return [name for name, info in self.data.characters.items()
                if info.first_appear_chapter <= chapter_number]
    
    def get_plot_arc_for_chapter(self, chapter_number: int) -> Optional[PlotArc]:
        """获取指定章节所属剧情弧"""
        for arc in self.data.plot_arcs:
            if arc.start_chapter <= chapter_number <= arc.end_chapter:
                return arc
        return None
    
    def get_expected_bloodline_stage(self, chapter_number: int) -> Dict[str, str]:
        """获取指定章节的血脉激活状态"""
        stages = {}
        for bl, info in self.data.awakening_timeline.items():
            if chapter_number >= info.get("chapter", 9999):
                stages[bl] = "已激活"
        
        # 默认道脉激活
        if chapter_number >= 1:
            stages["道脉"] = "初始激活"
        
        return stages
    
    def validate_chapter_against_architecture(self, chapter_number: int,
                                               chapter_content: str) -> Dict[str, Any]:
        """验证章节与架构的一致性（全面检查）"""
        issues = []
        score = 100
        checks_passed = []
        
        # 1. 角色出场检查
        for name, info in self.data.characters.items():
            if name in chapter_content:
                if info.first_appear_chapter > chapter_number:
                    issues.append(f"角色'{name}'提前出场（预期>{info.first_appear_chapter}章）")
                    score -= 8
                else:
                    checks_passed.append(f"角色'{name}'出场合理")
        
        # 2. 主角检查
        if self.protagonist not in chapter_content and chapter_number <= 1000:
            issues.append(f"主角'{self.protagonist}'未在蓝图中提及")
            score -= 5
        
        # 3. 剧情弧检查
        current_arc = self.get_plot_arc_for_chapter(chapter_number)
        if current_arc:
            for arc in self.data.plot_arcs:
                if arc.volume > current_arc.volume:
                    for event in arc.key_events:
                        if event and event in chapter_content:
                            issues.append(f"过早提及'{event}'（属于{arc.name}）")
                            score -= 5
        
        # 4. 血脉激活检查
        expected_bl = self.get_expected_bloodline_stage(chapter_number)
        for bl in self.FIVE_BLOODLINES:
            if f"{bl}激活" in chapter_content or f"{bl}觉醒" in chapter_content:
                if bl not in expected_bl:
                    issues.append(f"{bl}过早激活")
                    score -= 8
        
        # 5. 世界区域检查
        region_chapter_map = {
            "北荒巫域": 200, "南疆魔渊": 200, 
            "西漠佛国": 500, "东海儒岛": 800
        }
        for region, min_ch in region_chapter_map.items():
            if region in chapter_content and chapter_number < min_ch:
                issues.append(f"过早进入'{region}'（预期>{min_ch}章）")
                score -= 5
        
        # 6. 技能/法宝检查
        for skill in self.data.protagonist_skills:
            if skill.name in chapter_content:
                checks_passed.append(f"技能'{skill.name}'使用")
        
        return {
            "score": max(0, score),
            "issues": issues,
            "checks_passed": len(checks_passed),
            "expected_arc": current_arc.name if current_arc else "未知",
            "expected_bloodlines": expected_bl,
            "sections_available": len(self.data.sections_parsed)
        }
    
    def get_parsing_summary(self) -> Dict[str, Any]:
        """获取解析摘要"""
        return {
            "title": self.data.title,
            "total_chapters": self.data.total_chapters,
            "sections_parsed": self.data.sections_parsed,
            "characters_count": len(self.data.characters),
            "plot_arcs_count": len(self.data.plot_arcs),
            "skills_count": len(self.data.protagonist_skills),
            "regions_count": len(self.data.world_regions),
            "mysteries_count": len(self.data.mysteries),
            "template_modules": len(self.data.required_modules)
        }


def load_architecture(filepath: str) -> ArchitectureData:
    """便捷函数：加载并解析架构"""
    parser = ArchitectureParser(filepath)
    return parser.parse()
