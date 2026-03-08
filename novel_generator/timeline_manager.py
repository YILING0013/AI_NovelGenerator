# -*- coding: utf-8 -*-
"""
时间线账本管理器（硬约束基础层）
用于记录每章时间锚点，并检测“日期倒退”等时序冲突。
"""

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple


class TimelineManager:
    STATE_FILE = "timeline_state.json"

    def __init__(self, novel_path: str):
        self.novel_path = novel_path
        self.state_path = os.path.join(novel_path, self.STATE_FILE)
        self.state = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    loaded.setdefault("current_day", 0)
                    loaded.setdefault("chapters", {})
                    return loaded
            except (OSError, json.JSONDecodeError):
                pass
        return {"current_day": 0, "chapters": {}}

    def _save_state(self) -> None:
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _cn_to_int(cn: str) -> Optional[int]:
        mapping = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
        if not cn:
            return None
        if cn.isdigit():
            try:
                return int(cn)
            except ValueError:
                return None
        if cn == "十":
            return 10
        if "十" in cn:
            parts = cn.split("十")
            left = mapping.get(parts[0], 1) if parts[0] else 1
            right = mapping.get(parts[1], 0) if len(parts) > 1 and parts[1] else 0
            return left * 10 + right
        if len(cn) == 1 and cn in mapping:
            return mapping[cn]
        return None

    @classmethod
    def _extract_day_markers(cls, text: str) -> List[Tuple[int, int, str, str]]:
        markers: List[Tuple[int, int, str, str]] = []
        patterns = [
            ("absolute", r"D\+?(\d{1,4})(?:天|日)?"),
            ("relative", r"第(\d{1,4}|[零一二两三四五六七八九十]{1,3})(?:天|日)"),
            ("relative", r"(\d{1,3}|[零一二两三四五六七八九十]{1,3})天后"),
            ("relative", r"(\d{1,3}|[零一二两三四五六七八九十]{1,3})日后"),
            ("relative", r"(半月|月余|一周后|两周后|三周后)"),
        ]
        keyword_to_days = {"半月": 15, "月余": 30, "一周后": 7, "两周后": 14, "三周后": 21}
        for marker_type, pattern in patterns:
            for match in re.finditer(pattern, text):
                token = match.group(1)
                if token in keyword_to_days:
                    day = keyword_to_days[token]
                else:
                    day = cls._cn_to_int(token)
                if day is None:
                    continue
                markers.append((match.start(), int(day), match.group(0), marker_type))
        markers.sort(key=lambda x: x[0])
        return markers

    @staticmethod
    def _extract_explicit_day(text: str) -> Optional[int]:
        markers = TimelineManager._extract_day_markers(text)
        for _, day, _, marker_type in markers:
            if marker_type == "absolute":
                return day
        return None

    @staticmethod
    def _extract_relative_offset(text: str) -> Optional[int]:
        if any(k in text for k in ["翌日", "次日", "第二天"]):
            return 1
        if any(k in text for k in ["当天", "当日", "当晚", "片刻后"]):
            return 0

        match = re.search(r"(\d{1,3})天后", text)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
        if "半月" in text:
            return 15
        if "月余" in text:
            return 30
        if "一周后" in text:
            return 7
        if "两周后" in text:
            return 14
        return None

    def infer_day(self, chapter_text: str) -> Tuple[Optional[int], str]:
        """
        推断本章故事日。
        返回: (day, source) source in {"explicit", "relative", "unknown"}.
        """
        explicit = self._extract_explicit_day(chapter_text)
        if explicit is not None:
            return explicit, "explicit"

        rel = self._extract_relative_offset(chapter_text)
        if rel is not None:
            prev = int(self.state.get("current_day", 0))
            return max(0, prev + rel), "relative"

        return None, "unknown"

    def get_timeline_snapshot(self) -> str:
        current_day = int(self.state.get("current_day", 0))
        chapter_count = len(self.state.get("chapters", {}))
        return (
            "【Timeline Ledger (STRICT)】\n"
            f"- Current Story Day: D+{current_day}\n"
            f"- Tracked Chapters: {chapter_count}\n"
            "- Rule: 不允许时间倒退；若需跳跃必须明确写出“X天后/次日”等锚点。"
        )

    def _get_previous_day_baseline(self, chapter_num: int) -> int:
        """返回当前章节应对比的“前置章节日程基线”。"""
        if chapter_num <= 1:
            return 0
        chapters = self.state.get("chapters", {}) or {}
        prev_days = []
        for ch_key, meta in chapters.items():
            try:
                ch = int(ch_key)
            except ValueError:
                continue
            if ch >= chapter_num:
                continue
            if isinstance(meta, dict):
                day_val = meta.get("day")
                if isinstance(day_val, int):
                    prev_days.append(day_val)
        if prev_days:
            return max(prev_days)
        return 0

    def check_timeline_consistency(self, chapter_text: str, chapter_num: int) -> List[Dict[str, Any]]:
        conflicts: List[Dict[str, Any]] = []
        prev_day = self._get_previous_day_baseline(chapter_num)
        inferred_day, source = self.infer_day(chapter_text)
        markers = self._extract_day_markers(chapter_text)
        absolute_markers = [m for m in markers if m[3] == "absolute"]

        if len(absolute_markers) >= 2:
            last_day = absolute_markers[0][1]
            for _, day, raw, _ in absolute_markers[1:]:
                if day < last_day:
                    conflicts.append(
                        {
                            "type": "intra_chapter_timeline_regression",
                            "severity": "high",
                            "chapter": chapter_num,
                            "message": f"章内时间线倒退：出现“{raw}”使时间从 D+{last_day} 回退到 D+{day}",
                            "source": "intra_chapter",
                        }
                    )
                    break
                last_day = day

        if inferred_day is None:
            return conflicts

        if inferred_day < prev_day:
            conflicts.append(
                {
                    "type": "timeline_regression",
                    "severity": "high",
                    "chapter": chapter_num,
                    "previous_day": prev_day,
                    "current_day": inferred_day,
                    "message": f"时间线倒退：上一章已到 D+{prev_day}，本章出现 D+{inferred_day}",
                    "source": source,
                }
            )
        return conflicts

    def update_timeline(self, chapter_text: str, chapter_num: int) -> None:
        inferred_day, source = self.infer_day(chapter_text)
        current_day = int(self.state.get("current_day", 0))
        markers = self._extract_day_markers(chapter_text)
        max_marker_day = max([m[1] for m in markers if m[3] == "absolute"], default=None)
        if inferred_day is not None:
            current_day = max(current_day, inferred_day)
        if max_marker_day is not None:
            current_day = max(current_day, max_marker_day)

        self.state["current_day"] = current_day
        self.state.setdefault("chapters", {})
        self.state["chapters"][str(chapter_num)] = {
            "day": inferred_day if inferred_day is not None else (max_marker_day if max_marker_day is not None else current_day),
            "source": source,
        }
        self._save_state()
