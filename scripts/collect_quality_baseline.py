#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""采集小说章节质量基线报告（用于回归对比）。"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from chapter_quality_analyzer import ChapterQualityAnalyzer

try:
    from novel_generator.critique_agent import PoisonousReaderAgent
    CRITIC_AVAILABLE = True
except Exception:
    CRITIC_AVAILABLE = False


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _chapter_sort_key(path: Path) -> Tuple[int, str]:
    match = re.search(r"chapter_(\d+)\.txt$", path.name)
    if match:
        return int(match.group(1)), path.name
    return 10**9, path.name


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _pick_llm_config(config: Dict[str, Any], llm_name: Optional[str]) -> Tuple[str, Dict[str, Any]]:
    llm_configs = config.get("llm_configs", {})
    if not llm_configs:
        raise ValueError("config.json 中不存在 llm_configs。")

    chosen_name = llm_name
    if not chosen_name:
        chosen_name = config.get("choose_configs", {}).get("quality_loop_llm")
    if not chosen_name or chosen_name not in llm_configs:
        chosen_name = next(iter(llm_configs.keys()))
    return chosen_name, llm_configs[chosen_name]


def _build_llm_runtime_config(raw_cfg: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "api_key": raw_cfg.get("api_key", ""),
        "base_url": raw_cfg.get("base_url", ""),
        "model_name": raw_cfg.get("model_name", ""),
        "temperature": raw_cfg.get("temperature", 0.7),
        "max_tokens": raw_cfg.get("max_tokens", 8192),
        "timeout": raw_cfg.get("timeout", 600),
        "interface_format": raw_cfg.get("interface_format", "OpenAI"),
    }


def collect_baseline(
    novel_path: Path,
    llm_config: Dict[str, Any],
    threshold: float,
    sample_size: int,
    enable_critic: bool,
) -> Dict[str, Any]:
    chapters_dir = novel_path / "chapters"
    if not chapters_dir.exists():
        raise FileNotFoundError(f"章节目录不存在: {chapters_dir}")

    chapter_files = sorted(chapters_dir.glob("chapter_*.txt"), key=_chapter_sort_key)
    if not chapter_files:
        raise FileNotFoundError(f"未找到章节文件: {chapters_dir}/chapter_*.txt")
    if sample_size > 0:
        chapter_files = chapter_files[:sample_size]

    analyzer = ChapterQualityAnalyzer(str(novel_path), llm_config=llm_config)
    critic = PoisonousReaderAgent(llm_config) if (enable_critic and CRITIC_AVAILABLE) else None

    chapter_rows: List[Dict[str, Any]] = []
    raw_scores: List[float] = []
    final_scores: List[float] = []
    critic_scores: List[float] = []
    failed_reasons: Dict[str, int] = {}

    for chapter_file in chapter_files:
        with chapter_file.open("r", encoding="utf-8") as f:
            content = f.read()

        chapter_match = re.search(r"chapter_(\d+)\.txt$", chapter_file.name)
        chapter_num = int(chapter_match.group(1)) if chapter_match else 0

        scores = analyzer.analyze_content(content, chapter_num=chapter_num)
        raw_score = _safe_float(scores.get("综合评分"), 0.0)
        final_score = raw_score
        critic_score: Optional[float] = None
        reasons: List[str] = []

        if raw_score < threshold:
            reasons.append("score_below_threshold")

        if critic:
            result = critic.critique_chapter(content)
            critic_score = _safe_float(result.get("score"), 0.0)
            rating = str(result.get("rating", "")).lower()
            if rating == "reject" or critic_score < 7.5:
                reasons.append("critic_reject")
                final_score = min(final_score, 6.0)

        if not reasons:
            reasons = ["pass"]

        for reason in reasons:
            failed_reasons[reason] = failed_reasons.get(reason, 0) + 1

        row = {
            "chapter": chapter_num,
            "file": str(chapter_file),
            "word_count": len(content),
            "raw_score": raw_score,
            "critic_score": critic_score,
            "final_score": final_score,
            "reasons": reasons,
            "dimensions": {
                "剧情连贯性": scores.get("剧情连贯性"),
                "角色一致性": scores.get("角色一致性"),
                "写作质量": scores.get("写作质量"),
                "情感张力": scores.get("情感张力"),
                "系统机制": scores.get("系统机制"),
            },
        }
        chapter_rows.append(row)
        raw_scores.append(raw_score)
        final_scores.append(final_score)
        if critic_score is not None:
            critic_scores.append(critic_score)

    def _avg(values: List[float]) -> float:
        return round(statistics.fmean(values), 3) if values else 0.0

    summary = {
        "chapter_count": len(chapter_rows),
        "threshold": threshold,
        "average_raw_score": _avg(raw_scores),
        "average_critic_score": _avg(critic_scores) if critic_scores else None,
        "average_final_score": _avg(final_scores),
        "below_threshold_count": sum(1 for s in final_scores if s < threshold),
        "pass_count": sum(1 for s in final_scores if s >= threshold),
        "reason_counts": dict(sorted(failed_reasons.items(), key=lambda x: x[1], reverse=True)),
    }

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "novel_path": str(novel_path),
        "summary": summary,
        "chapters": chapter_rows,
    }


def _render_markdown(report: Dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# 质量基线报告",
        "",
        f"- 生成时间: `{report['generated_at']}`",
        f"- 小说目录: `{report['novel_path']}`",
        f"- 采样章节数: `{summary['chapter_count']}`",
        f"- 质量阈值: `{summary['threshold']}`",
        f"- 平均 Raw: `{summary['average_raw_score']}`",
        f"- 平均 Critic: `{summary['average_critic_score']}`",
        f"- 平均 Final: `{summary['average_final_score']}`",
        f"- 达标章节: `{summary['pass_count']}`",
        f"- 未达标章节: `{summary['below_threshold_count']}`",
        "",
        "## 触发原因统计",
        "",
    ]
    reason_counts = summary.get("reason_counts", {})
    if reason_counts:
        for reason, count in reason_counts.items():
            lines.append(f"- `{reason}`: {count}")
    else:
        lines.append("- 无")

    lines.extend([
        "",
        "## 各章分数",
        "",
        "| 章 | Raw | Critic | Final | Reasons |",
        "|---:|---:|---:|---:|---|",
    ])
    for row in report["chapters"]:
        critic = "-" if row["critic_score"] is None else f"{row['critic_score']:.2f}"
        lines.append(
            f"| {row['chapter']} | {row['raw_score']:.2f} | {critic} | {row['final_score']:.2f} | {', '.join(row['reasons'])} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="采集章节质量基线")
    parser.add_argument("--novel-path", required=True, help="小说目录（包含 chapters/）")
    parser.add_argument("--config", default="config.json", help="主配置文件路径")
    parser.add_argument("--llm-name", default="", help="使用的 LLM 配置名称（默认 quality_loop_llm）")
    parser.add_argument("--threshold", type=float, default=9.0, help="达标阈值")
    parser.add_argument("--sample-size", type=int, default=0, help="仅采样前 N 章，0 表示全部")
    parser.add_argument("--enable-critic", action="store_true", help="启用 Critic 评分")
    parser.add_argument("--output-dir", default="", help="输出目录（默认 <novel_path>/reports）")
    args = parser.parse_args()

    novel_path = Path(args.novel_path).expanduser().resolve()
    config_path = Path(args.config).expanduser().resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    config = _load_json(config_path)
    llm_name, llm_raw_config = _pick_llm_config(config, args.llm_name or None)
    llm_runtime_config = _build_llm_runtime_config(llm_raw_config)

    report = collect_baseline(
        novel_path=novel_path,
        llm_config=llm_runtime_config,
        threshold=args.threshold,
        sample_size=args.sample_size,
        enable_critic=args.enable_critic,
    )
    report["llm_name"] = llm_name

    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else (novel_path / "reports")
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"quality_baseline_{timestamp}.json"
    md_path = output_dir / f"quality_baseline_{timestamp}.md"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with md_path.open("w", encoding="utf-8") as f:
        f.write(_render_markdown(report))

    print(f"[OK] LLM配置: {llm_name}")
    print(f"[OK] JSON报告: {json_path}")
    print(f"[OK] Markdown报告: {md_path}")
    print(f"[OK] 平均Final: {report['summary']['average_final_score']}")


if __name__ == "__main__":
    main()
