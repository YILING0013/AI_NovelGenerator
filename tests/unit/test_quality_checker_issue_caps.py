from __future__ import annotations

from quality_checker import QualityChecker


def _build_blueprint(location: str, extra_text: str = "") -> str:
    return "\n".join(
        [
            "第8章 - 测试章节",
            "## 1. 基础元信息",
            "章节序号：第8章",
            "章节标题：测试章节",
            f"定位：{location}",
            "核心功能：推进主线",
            "字数目标：4500字",
            "出场角色：主角、女主",
            "## 2. 张力与冲突",
            "冲突类型：生存",
            "核心冲突点：围剿反击",
            "紧张感曲线：铺垫→爬升→爆发→回落",
            "张力评级：S",
            "## 3. 匠心思维应用",
            "应用场景：审讯反制",
            "思维模式：结构洞察",
            "视觉化描述：错误写法 vs 正确写法",
            "技法运用：镜头切换",
            "经典台词：我只信证据",
            "## 4. 伏笔与信息差",
            "本章植入伏笔：密令断句",
            "本章回收伏笔：旧案残页",
            "信息差控制：主角已锁定内鬼，敌人仍在误判",
            "世界观锚点/知识库引用：天书残页、命轨",
            "## 5. 暧昧与修罗场",
            "涉及的女性角色互动：本章不涉及女性角色互动",
            "## 6. 剧情精要",
            "开场：压抑潜伏",
            "发展：线索拼接",
            "高潮：身份反转",
            "收尾：导向下一章",
            "## 7. 衔接设计",
            "承上：承接上章围剿",
            "转场：从密室到街巷",
            "启下：锁定暗线头目",
            extra_text,
        ]
    )


def test_quality_checker_caps_score_when_location_has_placeholders() -> None:
    checker = QualityChecker()
    report = checker.check_chapter_quality(
        _build_blueprint("第X卷 [卷名待定] - 子幕X [待定]"),
        {"chapter_number": 8, "chapter_title": "测试章节"},
    )

    issue_texts = [issue.description for issue in report.issues]
    assert any("定位字段疑似占位符" in text for text in issue_texts)
    assert report.overall_score <= 82.0


def test_quality_checker_caps_score_when_dual_track_violated() -> None:
    checker = QualityChecker()
    report = checker.check_chapter_quality(
        _build_blueprint("第2卷 试炼卷 - 子幕3 暗线推进", extra_text="旁白出现 Bug 与解析词汇"),
        {"chapter_number": 8, "chapter_title": "测试章节"},
    )

    issue_texts = [issue.description for issue in report.issues]
    assert any("双轨叙事违规" in text for text in issue_texts)
    assert report.overall_score <= 88.0
