from __future__ import annotations

from quality_checker import QualityChecker


def _build_step2_blueprint(include_tension_rating: bool = False) -> str:
    section2_extra = "张力评级：A\n" if include_tension_rating else ""
    return "\n".join(
        [
            "第1章 - 测试章节",
            "## 1. 基础元信息",
            "章节序号：第1章",
            "章节标题：测试章节",
            "定位：第1卷 测试卷 - 子幕1 测试幕",
            "核心功能：推进主线",
            "字数目标：4500 字",
            "出场角色：测试角色A、测试角色B",
            "## 2. 张力与冲突",
            "冲突类型：生存危机",
            "核心冲突点：主角资源不足且被追击",
            "紧张感曲线：铺垫→爬升→爆发→回落",
            section2_extra.rstrip(),
            "## 3. 匠心思维应用",
            "应用场景：反追踪",
            "思维模式：结构洞察",
            "视觉化描述：错误写法 vs 正确写法",
            "经典台词：测试台词",
            "## 4. 伏笔与信息差",
            "本章植入伏笔：古碑裂痕",
            "本章回收伏笔：无",
            "信息差控制：主角知道真相，敌人误判",
            "## 5. 暧昧与修罗场",
            "涉及的女性角色互动：本章不涉及女性角色互动",
            "## 6. 剧情精要",
            "开场：主角醒来",
            "发展：追兵逼近",
            "高潮：反制成功",
            "收尾：留下新悬念",
            "系统机制变化：无新增机制",
            "## 7. 衔接设计",
            "承上：衔接前章危机",
            "转场：从室内转到荒野",
            "启下：下一章引入新敌人",
            "执行要点：兑现古碑裂痕的异常变化",
        ]
    )


def test_quality_checker_accepts_step2_seven_section_structure() -> None:
    checker = QualityChecker()
    report = checker.check_chapter_quality(
        _build_step2_blueprint(include_tension_rating=False),
        {"chapter_number": 1, "chapter_title": "测试章节"},
    )
    issue_texts = [issue.description for issue in report.issues]
    metric_map = {item.get("name"): item.get("score") for item in report.metrics if isinstance(item, dict)}

    assert all("缺失核心模块" not in text for text in issue_texts)
    assert all("格式缺失: 张力评级" not in text for text in issue_texts)
    assert any("建议补充: 张力评级" in text for text in issue_texts)
    assert "子分-结构合规" in metric_map
    assert "子分-叙事语义" in metric_map
    assert float(metric_map["子分-结构合规"]) >= 75


def test_quality_checker_tension_rating_is_bonus_not_hard_fail() -> None:
    checker = QualityChecker()
    base_report = checker.check_chapter_quality(
        _build_step2_blueprint(include_tension_rating=False),
        {"chapter_number": 4, "chapter_title": "测试章节"},
    )
    bonus_report = checker.check_chapter_quality(
        _build_step2_blueprint(include_tension_rating=True),
        {"chapter_number": 4, "chapter_title": "测试章节"},
    )

    base_issues = [issue.description for issue in base_report.issues]
    bonus_issues = [issue.description for issue in bonus_report.issues]

    assert any("建议补充: 张力评级" in text for text in base_issues)
    assert all("建议补充: 张力评级" not in text for text in bonus_issues)
    assert bonus_report.overall_score >= base_report.overall_score
