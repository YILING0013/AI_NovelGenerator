# -*- coding: utf-8 -*-
"""
多线程叙事平衡追踪器 (Narrative Thread Tracker)
追踪多条叙事线的推进平衡性。
"""

import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class NarrativeThreadTracker:
    """叙事线程追踪器"""
    
    THREADS_FILE = ".narrative_threads.json"
    
    DEFAULT_THREADS = {
        "修炼线": {"keywords": ["修炼", "突破", "境界", "功法", "丹药", "闭关", "灵气"], "color": "🔵"},
        "情感线": {"keywords": ["思念", "暧昧", "温柔", "深情", "心疼", "喜欢", "爱慕"], "color": "💗"},
        "权谋线": {"keywords": ["阴谋", "势力", "争斗", "背叛", "联盟", "利益", "权力"], "color": "⚫"},
        "探索线": {"keywords": ["秘境", "遗迹", "宝物", "机缘", "探索", "发现", "古迹"], "color": "🟢"},
        "战斗线": {"keywords": ["战斗", "对决", "交手", "厮杀", "切磋", "比武", "围攻"], "color": "🔴"},
        "身世线": {"keywords": ["身世", "血脉", "传承", "父母", "家族", "秘密", "来历"], "color": "🟣"},
    }
    
    DORMANT_THRESHOLD = 10

    def __init__(self, novel_path: str):
        self.novel_path = Path(novel_path)
        self.threads_file = self.novel_path / self.THREADS_FILE
        self._data = self._load_data()

    def _load_data(self) -> Dict[str, Any]:
        if self.threads_file.exists():
            try:
                with open(self.threads_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"threads": {}, "chapter_log": {}}

    def _save_data(self):
        try:
            with open(self.threads_file, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存叙事线程数据失败: {e}")

    def analyze_chapter(self, content: str, chapter_num: int) -> Dict[str, float]:
        thread_scores = {}
        for thread_name, config in self.DEFAULT_THREADS.items():
            count = sum(content.count(kw) for kw in config["keywords"])
            thread_scores[thread_name] = min(count / 10, 1.0)
        return thread_scores

    def update_threads(self, content: str, chapter_num: int):
        scores = self.analyze_chapter(content, chapter_num)
        self._data["chapter_log"][str(chapter_num)] = scores
        for thread_name, score in scores.items():
            if score > 0.2:
                if thread_name not in self._data["threads"]:
                    self._data["threads"][thread_name] = {
                        "first_active": chapter_num, "last_active": chapter_num, "active_count": 0}
                self._data["threads"][thread_name]["last_active"] = chapter_num
                self._data["threads"][thread_name]["active_count"] += 1
        self._save_data()

    def get_dormant_threads(self, current_chapter: int) -> List[Dict[str, Any]]:
        dormant = []
        for name, data in self._data.get("threads", {}).items():
            gap = current_chapter - data.get("last_active", 0)
            if gap >= self.DORMANT_THRESHOLD:
                dormant.append({"name": name, "last_active": data["last_active"],
                                "dormant_chapters": gap,
                                "color": self.DEFAULT_THREADS.get(name, {}).get("color", "⚪")})
        return sorted(dormant, key=lambda x: x["dormant_chapters"], reverse=True)

    def generate_balance_prompt(self, current_chapter: int) -> str:
        dormant = self.get_dormant_threads(current_chapter)
        if not dormant:
            return ""
        lines = ["\n【🧵 叙事线程提醒】以下叙事线已较久未推进："]
        for item in dormant[:3]:
            lines.append(f"  {item['color']} {item['name']}: "
                         f"最后活跃于第{item['last_active']}章 (已{item['dormant_chapters']}章未提及)")
        lines.append("  建议在近期章节中适当推进上述线程，保持叙事平衡。")
        return "\n".join(lines)
