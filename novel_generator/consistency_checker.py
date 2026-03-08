#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
跨章节一致性检查模块 (ConsistencyChecker)
检测跨章矛盾：角色复活、设定漂移等
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from datetime import datetime


class ConsistencyChecker:
    """跨章节一致性检查器"""
    
    FACTS_FILE = ".facts_db.json"
    NAME_PATTERN = r"[A-Za-z\u4e00-\u9fa5]{2,4}"
    
    # 事实类型
    FACT_DEATH = "death"          # 角色死亡
    FACT_LOCATION = "location"    # 角色位置
    FACT_REALM = "realm"          # 境界变化
    FACT_RELATIONSHIP = "relationship"  # 关系变化
    FACT_ITEM = "item"            # 物品获取/丢失
    INVALID_CHARACTER_TERMS = {
        "那个", "这个", "这些", "那些", "有人", "众人", "路人", "对方",
        "本该", "本应", "此人", "那人", "其人", "自己", "他们", "我们",
        "应该",
        "你们", "她们", "它们", "其中", "之后", "然后", "但是", "因为",
        "所以", "如果", "虽然", "然而", "并且", "于是", "已经", "仍然",
        "这个人", "那个人", "那个本该", "像是", "好像", "仿佛", "似乎",
    }
    INVALID_CHARACTER_PREFIXES = (
        "那个", "这个", "这些", "那些", "其中", "本该", "本应",
        "如果", "若是", "像是", "好像", "仿佛", "似乎",
        "并且", "并", "而且", "但是", "然而", "因为", "所以",
        "已经", "仍然", "正在", "至少", "还有", "就", "又",
    )
    INVALID_CHARACTER_SUFFIXES = (
        "这里", "那里", "这边", "那边", "里面", "外面",
        "里", "边", "中", "上", "下", "前", "后", "时",
        "了", "着", "过", "得", "会", "将",
    )
    INVALID_CHARACTER_CONTAINS = ("我", "你", "他", "她", "它", "们", "自己", "的")
    INVALID_CHARACTER_SUBSTRINGS = (
        "如果", "若是", "像是", "好像", "仿佛", "似乎",
        "这边", "那边", "这里", "那里", "那种", "这种", "随时", "就先",
        "已经", "仍然", "足够", "看了看", "在这里", "里那",
        "怎么还没", "本来就要", "三天前就", "一具冰冷", "死便", "就要死", "还没死",
    )
    DEATH_HYPOTHETICAL_HINTS = (
        "像是", "好像", "仿佛", "似乎", "如果", "若是", "会", "将会", "可能", "怕", "险些", "差点",
    )
    DEATH_HYPOTHETICAL_CLAUSE_MARKERS = ("如果", "若是", "假如", "要是")
    DEATH_TERMS = ("被杀", "死了", "殒落", "身亡", "倒地不起", "断气", "魂飞魄散", "灰飞烟灭")
    DEATH_NEGATION_HINTS = ("没死", "不死", "未死", "死不了", "不能死")
    DEAD_REFERENCE_MARKERS = (
        "已死", "已亡", "身亡", "暴毙", "死讯", "尸体", "遗体", "被废", "废了修为",
        "消息", "风声", "传闻", "党羽", "余党", "旧部", "狗腿子", "提到", "回忆", "曾经",
    )
    ALIVE_ACTION_MARKERS = (
        "走来", "走进", "走出", "出现", "现身", "站起", "起身", "开口", "说道", "冷笑",
        "大笑", "出手", "挥剑", "抬手", "攻击", "追杀", "喝道", "命令", "盯着", "看向",
    )
    
    def __init__(self, novel_path: str):
        self.novel_path = Path(novel_path)
        self.facts_file = self.novel_path / self.FACTS_FILE
        self._facts_db = self._load_facts()
        if self._sanitize_facts_db():
            self._save_facts()
    
    def _load_facts(self) -> Dict[str, Any]:
        """加载事实数据库"""
        if self.facts_file.exists():
            try:
                with open(self.facts_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logging.warning(f"[Consistency] 加载事实数据库失败: {e}")
        return {
            "deaths": {},           # {角色名: {chapter: N, context: "..."}}
            "locations": {},        # {角色名: {chapter: N, location: "..."}}
            "realms": {},           # {角色名: [{chapter: N, realm: "..."}]}
            "relationships": {},    # {角色对: [{chapter: N, relation: "..."}]}
            "items": {},            # {物品名: {owner: "...", chapter: N}}
            "updated_at": None
        }

    def _sanitize_facts_db(self) -> bool:
        """清理历史事实库中的异常角色名，避免旧误报持续污染。"""
        changed = False
        deaths = self._facts_db.get("deaths")
        if not isinstance(deaths, dict):
            self._facts_db["deaths"] = {}
            return True

        removed = []
        for name in list(deaths.keys()):
            info = deaths.get(name) if isinstance(deaths, dict) else None
            context = info.get("context", "") if isinstance(info, dict) else ""
            if not self._is_valid_character_name(name) or self._is_probably_hypothetical_death_record(name, context):
                removed.append(name)
                deaths.pop(name, None)
                changed = True

        if removed:
            logging.info(f"[Consistency] 清理无效死亡角色名: {', '.join(removed[:10])}")
        return changed
    
    def _save_facts(self):
        """保存事实数据库"""
        self._facts_db["updated_at"] = datetime.now().isoformat()
        try:
            with open(self.facts_file, 'w', encoding='utf-8') as f:
                json.dump(self._facts_db, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"[Consistency] 保存事实数据库失败: {e}")
    
    def extract_facts_from_content(self, content: str, chapter_num: int) -> Dict[str, List[Dict]]:
        """
        从章节内容中提取关键事实
        :param content: 章节内容
        :param chapter_num: 章节号
        :return: 提取的事实字典
        """
        facts = {
            "deaths": [],
            "realm_changes": [],
            "locations": [],
            "items": []
        }
        
        # 死亡事件检测
        name_pat = self.NAME_PATTERN
        death_patterns = [
            ("direct_death", rf'({name_pat})(被杀|死了|殒落|身亡|倒地不起|断气|魂飞魄散|灰飞烟灭)'),
            ("kill_action", rf'杀死了?({name_pat})'),
            ("corpse_ref", rf'({name_pat})(的尸体|的遗体)'),
        ]
        for mode, pattern in death_patterns:
            for match in re.finditer(pattern, content):
                char = (match.group(1) or "").strip()
                if not self._is_valid_character_name(char):
                    continue
                if mode == "direct_death":
                    death_word = (match.group(2) or "").strip()
                    if self._is_hypothetical_death_context(
                        content, match.start(1), match.end(2), death_word
                    ):
                        continue
                elif mode == "kill_action":
                    if self._is_hypothetical_death_context(
                        content, match.start(1), match.end(1), "被杀"
                    ):
                        continue
                facts["deaths"].append({
                    "character": char,
                    "chapter": chapter_num,
                    "context": self._get_context_by_index(content, match.start(1), match.end(1), 50)
                })
        
        # 境界变化检测
        realm_patterns = [
            rf'({name_pat})(?:突破到|晋级为|踏入|达到)(?:了)?([A-Za-z\u4e00-\u9fa5]{2,8}境)',
            rf'({name_pat})成功突破(?:到)?([A-Za-z\u4e00-\u9fa5]{2,8})',
        ]
        for pattern in realm_patterns:
            for match in re.finditer(pattern, content):
                if (match.lastindex or 0) >= 2:
                    char = (match.group(1) or "").strip()
                    if not self._is_valid_character_name(char):
                        continue
                    facts["realm_changes"].append({
                        "character": char,
                        "new_realm": match.group(2),
                        "chapter": chapter_num
                    })
        
        # 位置变化检测
        location_patterns = [
            rf'({name_pat})(?:来到|抵达|进入|离开)(?:了)?([A-Za-z\u4e00-\u9fa5]{2,10})',
        ]
        for pattern in location_patterns:
            for match in re.finditer(pattern, content):
                if (match.lastindex or 0) >= 2:
                    char = (match.group(1) or "").strip()
                    if not self._is_valid_character_name(char):
                        continue
                    facts["locations"].append({
                        "character": char,
                        "location": match.group(2),
                        "chapter": chapter_num
                    })
        
        return facts

    def _is_valid_character_name(self, name: str) -> bool:
        """过滤明显非角色名的短语，减少一致性误报。"""
        if not name:
            return False
        n = name.strip()
        if len(n) < 2 or len(n) > 4:
            return False
        # 含明显标点/引导词时直接过滤
        if re.search(r"[，。；：、【】（）()“”\"'《》—\-\d]", n):
            return False
        if n in self.INVALID_CHARACTER_TERMS:
            return False
        if any(token in n for token in self.INVALID_CHARACTER_SUBSTRINGS):
            return False
        if any(token in n for token in self.INVALID_CHARACTER_CONTAINS):
            return False
        # 代词或连接词前缀常被误提取为“角色名”
        if n.startswith(self.INVALID_CHARACTER_PREFIXES):
            return False
        if n.endswith(self.INVALID_CHARACTER_SUFFIXES):
            return False
        return True

    def _is_hypothetical_death_context(
        self,
        content: str,
        start_idx: int,
        end_idx: int,
        death_word: str,
    ) -> bool:
        """过滤“像是死了/会断气/如果死了”等非确定死亡语境。"""
        window = content[max(0, start_idx - 12): min(len(content), end_idx + 16)]
        cross_marker = content[max(0, start_idx - 1): min(len(content), start_idx + 1)]
        if cross_marker in self.DEATH_HYPOTHETICAL_CLAUSE_MARKERS:
            return True
        if any(marker in window for marker in self.DEATH_NEGATION_HINTS):
            return True
        if death_word:
            pos = window.find(death_word)
            if pos != -1:
                prefix = window[max(0, pos - 8):pos]
                if any(hint in prefix for hint in self.DEATH_HYPOTHETICAL_HINTS):
                    return True
        if death_word == "断气" and "死寂" in window:
            return True
        return False

    def _is_probably_hypothetical_death_record(self, name: str, context: str) -> bool:
        """判断历史死亡记录是否更像“假设/推测语句”导致的误提取。"""
        if not name or not context:
            return False
        idx = context.find(name)
        if idx == -1:
            return False

        cross_marker = context[max(0, idx - 1): min(len(context), idx + 1)]
        if cross_marker in self.DEATH_HYPOTHETICAL_CLAUSE_MARKERS:
            return True

        for death_word in self.DEATH_TERMS:
            hit = context.find(death_word, idx)
            if hit == -1:
                continue
            prefix = context[max(0, hit - 10):hit]
            if any(hint in prefix for hint in self.DEATH_HYPOTHETICAL_HINTS):
                return True
            break
        return False
    
    def _get_context(self, content: str, keyword: str, length: int = 50) -> str:
        """获取关键词周围的上下文"""
        idx = content.find(keyword)
        if idx == -1:
            return ""
        start = max(0, idx - length)
        end = min(len(content), idx + len(keyword) + length)
        return content[start:end]

    def _get_context_by_index(self, content: str, start_idx: int, end_idx: int, length: int = 50) -> str:
        """按索引获取上下文，避免同名词多次出现时取错位置。"""
        start = max(0, start_idx - length)
        end = min(len(content), end_idx + length)
        return content[start:end]
    
    def update_facts(self, content: str, chapter_num: int):
        """
        从新章节更新事实数据库
        :param content: 章节内容
        :param chapter_num: 章节号
        """
        extracted = self.extract_facts_from_content(content, chapter_num)
        
        # 更新死亡记录
        for death in extracted["deaths"]:
            char = death["character"]
            if char not in self._facts_db["deaths"]:
                self._facts_db["deaths"][char] = {
                    "chapter": chapter_num,
                    "context": death["context"]
                }
                logging.info(f"[Consistency] 记录死亡事件: {char} (第{chapter_num}章)")
        
        # 更新境界记录
        for realm in extracted["realm_changes"]:
            char = realm["character"]
            if char not in self._facts_db["realms"]:
                self._facts_db["realms"][char] = []
            self._facts_db["realms"][char].append({
                "chapter": chapter_num,
                "realm": realm["new_realm"]
            })
        
        # 更新位置记录
        for loc in extracted["locations"]:
            char = loc["character"]
            self._facts_db["locations"][char] = {
                "chapter": chapter_num,
                "location": loc["location"]
            }
        
        self._save_facts()
    
    def check_consistency(self, content: str, chapter_num: int) -> List[Dict[str, Any]]:
        """
        检查新章节与历史事实的一致性
        :param content: 章节内容
        :param chapter_num: 章节号
        :return: 矛盾列表
        """
        conflicts = []
        
        # 检查1：死者复活
        for dead_char, death_info in self._facts_db.get("deaths", {}).items():
            if not self._is_valid_character_name(dead_char):
                continue
            # 仅检查“已在更早章节死亡”的角色，避免同章内正常叙述被误判复活
            if int(death_info.get("chapter", 0) or 0) >= int(chapter_num):
                continue
            if dead_char in content and self._has_alive_evidence(content, dead_char):
                conflicts.append({
                    "type": "resurrection",
                    "character": dead_char,
                    "death_chapter": death_info["chapter"],
                    "current_chapter": chapter_num,
                    "message": f"角色'{dead_char}'在第{death_info['chapter']}章已死亡，但在第{chapter_num}章再次出现",
                    "severity": "high"
                })
        
        # 检查2：境界回退
        extracted = self.extract_facts_from_content(content, chapter_num)
        for realm_change in extracted["realm_changes"]:
            char = realm_change["character"]
            if char in self._facts_db.get("realms", {}):
                history = self._facts_db["realms"][char]
                if history:
                    last_realm = history[-1]["realm"]
                    new_realm = realm_change["new_realm"]
                    # 简单检查：如果新境界名称比旧境界短，可能是回退
                    # 实际应用中需要更精确的境界等级比较
                    if len(new_realm) < len(last_realm) and new_realm not in last_realm:
                        conflicts.append({
                            "type": "realm_regression",
                            "character": char,
                            "last_realm": last_realm,
                            "new_realm": new_realm,
                            "current_chapter": chapter_num,
                            "message": f"角色'{char}'境界可能回退: {last_realm} -> {new_realm}",
                            "severity": "medium"
                        })
        
        return conflicts

    def _has_alive_evidence(self, content: str, character: str) -> bool:
        """仅当上下文出现“存活行为证据”时，才判定为死者复活。"""
        if not content or not character or not self._is_valid_character_name(character):
            return False

        cursor = 0
        while True:
            idx = content.find(character, cursor)
            if idx == -1:
                break
            cursor = idx + len(character)
            window = content[max(0, idx - 28): min(len(content), idx + len(character) + 40)]

            # 明确是“提及死者/党羽/传闻/回忆”场景，不算复活
            if any(marker in window for marker in self.DEAD_REFERENCE_MARKERS):
                continue
            if any(marker in window for marker in ("不止", "不是", "并非")) and "赵四" in window:
                # 典型“赵四……不止赵四”属于推断背后势力，不是复活
                continue

            # 仅当出现明确“存活动作”再判定复活
            if any(marker in window for marker in self.ALIVE_ACTION_MARKERS):
                return True
        return False
    
    def generate_consistency_prompt(self, content: str, chapter_num: int) -> str:
        """
        生成一致性提示，用于注入到优化Prompt中
        :return: 一致性警告文本
        """
        conflicts = self.check_consistency(content, chapter_num)
        
        if not conflicts:
            return ""
        
        lines = ["\n╔══════════════════════════════════════════════════════════════╗"]
        lines.append("║ ⚠️ 【一致性警告】检测到以下跨章矛盾，请修正：              ║")
        lines.append("╠══════════════════════════════════════════════════════════════╣")
        
        for i, conflict in enumerate(conflicts[:5], 1):  # 最多显示5个
            lines.append(f"║ {i}. {conflict['message'][:55]}")
        
        lines.append("╚══════════════════════════════════════════════════════════════╝")
        
        return "\n".join(lines)
    
    def get_dead_characters(self) -> Set[str]:
        """获取所有已死亡角色"""
        return set(self._facts_db.get("deaths", {}).keys())
    
    def get_character_current_realm(self, character: str) -> Optional[str]:
        """获取角色当前境界"""
        realms = self._facts_db.get("realms", {}).get(character, [])
        if realms:
            return realms[-1]["realm"]
        return None


def get_consistency_checker(novel_path: str) -> ConsistencyChecker:
    """获取一致性检查器实例"""
    return ConsistencyChecker(novel_path)
