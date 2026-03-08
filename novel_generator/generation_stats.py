# -*- coding: utf-8 -*-
"""
生成质量稳定性监控 (Generation Stats Monitor)
追踪跨章节的质量趋势、检测异常波动。
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from statistics import mean, stdev

logger = logging.getLogger(__name__)


class GenerationStatsMonitor:
    """生成质量统计监控器"""
    
    STATS_FILE = ".generation_stats.json"
    
    def __init__(self, novel_path: str):
        self.novel_path = Path(novel_path)
        self.stats_file = self.novel_path / self.STATS_FILE
        self._stats = self._load_stats()

    def _load_stats(self) -> Dict[str, Any]:
        if self.stats_file.exists():
            try:
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"chapters": {}, "dimension_trends": {}}

    def _save_stats(self):
        try:
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump(self._stats, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存统计数据失败: {e}")

    def record_chapter_stats(self, chapter_num: int, scores: Dict[str, Any],
                              iterations: int, status: str):
        """记录章节的生成统计"""
        entry = {
            "scores": {k: v for k, v in scores.items()
                       if isinstance(v, (int, float))},
            "overall": float(scores.get('综合评分', 0)),
            "iterations": iterations,
            "status": status,
        }
        self._stats["chapters"][str(chapter_num)] = entry
        
        # 更新维度趋势
        for dim, val in entry["scores"].items():
            if dim not in self._stats["dimension_trends"]:
                self._stats["dimension_trends"][dim] = []
            self._stats["dimension_trends"][dim].append({
                "chapter": chapter_num, "score": val})
            # 最多保留50章数据
            self._stats["dimension_trends"][dim] = \
                self._stats["dimension_trends"][dim][-50:]
        
        self._save_stats()

    def detect_anomalies(self, chapter_num: int) -> List[str]:
        """检测质量异常"""
        warnings = []
        entry = self._stats["chapters"].get(str(chapter_num))
        if not entry:
            return warnings
        
        current_overall = entry.get("overall", 0)
        
        # 收集最近10章的overall分数
        recent = []
        for ch_str, ch_data in sorted(self._stats["chapters"].items(),
                                        key=lambda x: int(x[0])):
            ch = int(ch_str)
            if ch < chapter_num and chapter_num - ch <= 10:
                recent.append(ch_data.get("overall", 0))
        
        if len(recent) >= 3:
            avg = mean(recent)
            sd = stdev(recent) if len(recent) > 1 else 0
            # 检测急剧下降
            if current_overall < avg - 2 * max(sd, 0.3):
                warnings.append(
                    f"⚠️ 第{chapter_num}章评分({current_overall:.1f})显著低于"
                    f"近10章均值({avg:.1f}±{sd:.1f})，存在质量退化风险"
                )
            # 检测迭代次数异常
            current_iters = entry.get("iterations", 0)
            avg_iters = mean([self._stats["chapters"][str(c)].get("iterations", 0)
                              for c in range(max(1, chapter_num - 10), chapter_num)
                              if str(c) in self._stats["chapters"]] or [0])
            if current_iters > avg_iters * 2 and current_iters > 3:
                warnings.append(
                    f"⚠️ 第{chapter_num}章迭代{current_iters}次(均值{avg_iters:.0f})，"
                    f"生成效率可能下降"
                )
        
        return warnings

    def get_trend_summary(self) -> Dict[str, Any]:
        """获取趋势摘要"""
        summary = {}
        for dim, points in self._stats.get("dimension_trends", {}).items():
            if len(points) >= 3:
                scores = [p["score"] for p in points[-10:]]
                summary[dim] = {
                    "avg": round(mean(scores), 2),
                    "trend": "up" if scores[-1] > mean(scores[:-1]) else "down",
                    "min": round(min(scores), 2),
                    "max": round(max(scores), 2),
                }
        return summary
