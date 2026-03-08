#!/usr/bin/env python
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from quality_checker import QualityChecker

logger = logging.getLogger(__name__)

CHAPTER_HEADER_PATTERN = re.compile(
    r"(?m)^(?:#+\s*)?(?:\*\*)?\s*第\s*(\d+)\s*章(?:\s*[-–—:：]\s*([^\n*]+))?\s*(?:\*\*)?\s*$"
)
LOW_SCORE_THRESHOLD = 80.0


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="gbk")
        except UnicodeDecodeError:
            return ""
    except OSError:
        return ""


def _extract_chapter_blocks(content: str) -> list[dict[str, Any]]:
    headers = list(CHAPTER_HEADER_PATTERN.finditer(content))
    blocks: list[dict[str, Any]] = []

    for idx, match in enumerate(headers):
        chapter_number = int(match.group(1))
        chapter_title = (match.group(2) or "").strip() or f"第{chapter_number}章"
        start = match.start()
        end = headers[idx + 1].start() if idx + 1 < len(headers) else len(content)
        chapter_content = content[start:end].strip()
        if not chapter_content:
            continue
        blocks.append(
            {
                "chapter_number": chapter_number,
                "chapter_title": chapter_title,
                "content": chapter_content,
            }
        )

    blocks.sort(key=lambda item: int(item["chapter_number"]))
    return blocks


def _issue_bucket(description: str) -> str:
    normalized = str(description or "").strip()
    if not normalized:
        return "未知问题"
    if "：" in normalized:
        return normalized.split("：", 1)[0].strip() or "未知问题"
    if ":" in normalized:
        return normalized.split(":", 1)[0].strip() or "未知问题"
    return normalized[:24]


def _normalize_coherence_issue(issue: Any) -> dict[str, Any]:
    if isinstance(issue, dict):
        chapter_pair = issue.get("chapter_pair", (0, 0))
        if isinstance(chapter_pair, list):
            chapter_pair = tuple(chapter_pair)
        return {
            "issue_type": str(issue.get("issue_type", "unknown")),
            "description": str(issue.get("description", "")),
            "severity": str(issue.get("severity", "medium")),
            "chapter_pair": chapter_pair,
        }

    chapter_pair = getattr(issue, "chapter_pair", (0, 0))
    if isinstance(chapter_pair, list):
        chapter_pair = tuple(chapter_pair)
    return {
        "issue_type": str(getattr(issue, "issue_type", "unknown")),
        "description": str(getattr(issue, "description", "")),
        "severity": str(getattr(issue, "severity", "medium")),
        "chapter_pair": chapter_pair,
    }


def _extract_metric_score(metrics: Any, metric_name: str) -> float | None:
    if not isinstance(metrics, list):
        return None
    for item in metrics:
        if not isinstance(item, dict):
            continue
        if str(item.get("name", "")).strip() != metric_name:
            continue
        try:
            return float(item.get("score"))
        except (TypeError, ValueError):
            return None
    return None


class BatchQualityChecker:
    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        self.directory_path = self.filepath / "Novel_directory.txt"
        self.checker = QualityChecker(str(self.filepath))

    def _load_chapters(self) -> list[dict[str, Any]]:
        if not self.directory_path.exists():
            logger.warning("Novel_directory.txt not found at %s", self.directory_path)
            return []

        content = _read_text(self.directory_path)
        if not content.strip():
            return []
        return _extract_chapter_blocks(content)

    def _get_architecture_summary(self) -> dict[str, Any] | None:
        parser = getattr(self.checker, "architecture_parser", None)
        if parser is None:
            return None
        summary_func = getattr(parser, "get_parsing_summary", None)
        if not callable(summary_func):
            return None
        try:
            summary = summary_func()
            if isinstance(summary, dict):
                return summary
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Architecture summary collection failed: %s", exc)
        return None

    def _run_coherence_check(self, chapters: list[dict[str, Any]]) -> dict[str, Any] | None:
        if len(chapters) < 2:
            return None
        try:
            from novel_generator.coherence_checker import CoherenceChecker

            checker = CoherenceChecker(str(self.filepath))
            payload = [
                {
                    "chapter_number": item["chapter_number"],
                    "content": item["content"],
                }
                for item in chapters
            ]
            coherence = checker.check_all_chapters(payload)
            if not isinstance(coherence, dict):
                return None
            issues = coherence.get("issues", [])
            coherence["issues"] = [_normalize_coherence_issue(issue) for issue in issues][:50]
            return coherence
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Coherence check failed: %s", exc)
            return None

    def check_all_chapters(self) -> dict[str, Any] | None:
        chapters = self._load_chapters()
        if not chapters:
            return None

        all_scores: list[float] = []
        structure_scores: list[float] = []
        semantic_scores: list[float] = []
        chapter_details: list[dict[str, Any]] = []
        low_score_chapters: list[int] = []
        issue_statistics: dict[str, int] = {}

        for chapter in chapters:
            chapter_number = int(chapter["chapter_number"])
            chapter_info = {
                "chapter_number": chapter_number,
                "chapter_title": str(chapter["chapter_title"]),
            }

            try:
                report = self.checker.check_chapter_quality(
                    chapter["content"],
                    chapter_info,
                    blueprint_text=chapter["content"],
                )
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Chapter %s quality check failed: %s", chapter_number, exc)
                continue

            score = float(report.overall_score)
            all_scores.append(score)
            structure_score = _extract_metric_score(getattr(report, "metrics", None), "子分-结构合规")
            semantic_score = _extract_metric_score(getattr(report, "metrics", None), "子分-叙事语义")
            if structure_score is not None:
                structure_scores.append(structure_score)
            if semantic_score is not None:
                semantic_scores.append(semantic_score)

            issue_descriptions = [str(issue.description) for issue in report.issues]
            for description in issue_descriptions:
                bucket = _issue_bucket(description)
                issue_statistics[bucket] = issue_statistics.get(bucket, 0) + 1

            chapter_details.append(
                {
                    "chapter_number": chapter_number,
                    "score": score,
                    "structure_score": structure_score,
                    "semantic_score": semantic_score,
                    "quality_level": str(getattr(report.quality_level, "value", report.quality_level)),
                    "issues": issue_descriptions,
                    "issue_summary": self.checker.get_issue_summary(report),
                }
            )

            if score < LOW_SCORE_THRESHOLD:
                low_score_chapters.append(chapter_number)

        if not all_scores:
            return None

        total = len(all_scores)
        quality_distribution = {
            "excellent": sum(1 for value in all_scores if value >= 90),
            "good": sum(1 for value in all_scores if 80 <= value < 90),
            "fair": sum(1 for value in all_scores if 70 <= value < 80),
            "poor": sum(1 for value in all_scores if value < 70),
        }

        return {
            "total_chapters": total,
            "average_score": sum(all_scores) / total,
            "average_structure_score": (sum(structure_scores) / len(structure_scores)) if structure_scores else None,
            "average_semantic_score": (sum(semantic_scores) / len(semantic_scores)) if semantic_scores else None,
            "low_score_chapters": low_score_chapters,
            "chapter_details": chapter_details,
            "issue_statistics": issue_statistics,
            "quality_distribution": quality_distribution,
            "coherence_check": self._run_coherence_check(chapters),
            "architecture_summary": self._get_architecture_summary(),
        }

    def get_chapter_issues(self, chapter_number: int) -> list[str]:
        chapters = self._load_chapters()
        target = next((item for item in chapters if int(item["chapter_number"]) == chapter_number), None)
        if target is None:
            return []

        chapter_info = {
            "chapter_number": chapter_number,
            "chapter_title": str(target["chapter_title"]),
        }
        try:
            report = self.checker.check_chapter_quality(
                target["content"],
                chapter_info,
                blueprint_text=target["content"],
            )
        except (OSError, json.JSONDecodeError):
            return []
        return [str(issue.description) for issue in report.issues]
