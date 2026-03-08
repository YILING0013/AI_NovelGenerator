from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from novel_generator.batch_quality_check import BatchQualityChecker


def _build_chapter(chapter_num: int) -> str:
    return "\n".join(
        [
            f"第{chapter_num}章 - 测试章节{chapter_num}",
            "## 1. 基础元信息",
            "章节序号：测试",
            "## 2. 张力与冲突",
            "核心冲突点：测试",
            "## 3. 匠心思维应用",
            "应用场景：测试",
            "## 4. 伏笔与信息差",
            "本章植入伏笔：测试",
            "## 5. 暧昧与修罗场",
            "涉及的女性角色互动：本章不涉及女性角色互动",
            "## 6. 剧情精要",
            "开场：测试",
            "## 7. 衔接设计",
            "承上：测试",
        ]
    )


def test_batch_quality_checker_returns_runtime_report(monkeypatch, temp_dir):
    project = Path(temp_dir)
    (project / "Novel_directory.txt").write_text(
        "\n\n".join([_build_chapter(1), _build_chapter(2)]),
        encoding="utf-8",
    )

    def fake_check(self, content, chapter_info, blueprint_text=None):
        chapter_number = int(chapter_info.get("chapter_number", 0))
        score = 78.0 if chapter_number == 2 else 88.0
        issues = [SimpleNamespace(description="格式缺失: 张力评级", severity="medium")] if chapter_number == 2 else []
        return SimpleNamespace(
            overall_score=score,
            quality_level=SimpleNamespace(value="Good"),
            issues=issues,
            metrics=[
                {"name": "子分-结构合规", "score": 92.0 if chapter_number == 1 else 86.0, "weight": 0.0},
                {"name": "子分-叙事语义", "score": 84.0 if chapter_number == 1 else 76.0, "weight": 0.0},
            ],
        )

    monkeypatch.setattr("quality_checker.QualityChecker.check_chapter_quality", fake_check)
    monkeypatch.setattr(
        "quality_checker.QualityChecker.get_issue_summary",
        lambda self, report: "有问题" if report.issues else "无明显问题",
    )
    monkeypatch.setattr(
        "novel_generator.coherence_checker.CoherenceChecker.check_all_chapters",
        lambda self, chapters: {
            "total_chapters": len(chapters),
            "total_issues": 1,
            "coherence_score": 95.0,
            "issues": [
                {
                    "issue_type": "location_jump",
                    "description": "测试跳转",
                    "severity": "medium",
                    "chapter_pair": (1, 2),
                }
            ],
            "issue_breakdown": {"location_jump": 1},
        },
    )

    checker = BatchQualityChecker(str(project))
    report = checker.check_all_chapters()

    assert report is not None
    assert report["total_chapters"] == 2
    assert report["low_score_chapters"] == [2]
    assert report["quality_distribution"]["good"] == 1
    assert report["quality_distribution"]["fair"] == 1
    assert report["issue_statistics"]["格式缺失"] == 1
    assert report["coherence_check"]["total_issues"] == 1
    assert isinstance(report["coherence_check"]["issues"][0], dict)
    assert report["average_structure_score"] == 89.0
    assert report["average_semantic_score"] == 80.0
    details_by_chapter = {item["chapter_number"]: item for item in report["chapter_details"]}
    assert details_by_chapter[1]["structure_score"] == 92.0
    assert details_by_chapter[2]["semantic_score"] == 76.0


def test_batch_quality_checker_returns_none_when_directory_missing(temp_dir):
    checker = BatchQualityChecker(str(temp_dir))
    assert checker.check_all_chapters() is None
