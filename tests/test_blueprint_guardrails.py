import json
import re
from pathlib import Path
from types import SimpleNamespace

from novel_generator.architecture_compliance import ArchitectureComplianceChecker
from novel_generator.blueprint import StrictChapterGenerator


def _build_chapter(
    chapter_num: int,
    missing_section: int | None = None,
    protagonist: str = "秦昭野",
    female_line: str = "本章不涉及女性角色互动",
) -> str:
    sections = [
        (1, "基础元信息", "* **章节序号**：第{n}章\n* **出场角色**：{protagonist}"),
        (2, "张力与冲突", "* **核心冲突点**：测试冲突"),
        (3, "匠心思维应用", "* **应用场景**：测试场景"),
        (4, "伏笔与信息差", "* **本章植入伏笔**：测试伏笔"),
        (5, "暧昧与修罗场", "* **涉及的女性角色互动**：{female_line}"),
        (6, "剧情精要", "* **开场**：测试开场"),
        (7, "衔接设计", "* **承上**：测试承上"),
    ]
    lines = [f"第{chapter_num}章 - 测试章节{chapter_num}"]
    for sec_num, sec_name, body_tpl in sections:
        if missing_section == sec_num:
            continue
        lines.append(f"## {sec_num}. {sec_name}")
        lines.append(
            body_tpl.format(
                n=chapter_num,
                protagonist=protagonist,
                female_line=female_line,
            )
        )
    return "\n".join(lines)


def _build_architecture_with_entities(protagonist: str = "秦昭野") -> str:
    return "\n".join(
        [
            "## 5. 角色系统",
            f"主角实名：{protagonist}",
            "1. 沈绛霜（王朝线）",
            "2. 宁照雪（宗门线）",
            "3. 姬夜罗（魔门线）",
            "## 15. 卷1-卷4详细情节点（80点，可直接拆章）",
            "### 15.1 卷1《边荒断命》情节点（1-20）",
            "1. 1-3章：古碑爆裂，主角前世身死。",
            "2. 4-6章：主角重生于边荒废脉少年。",
        ]
    )


def _build_progression_chapter(
    chapter_num: int,
    core_function: str,
    opening: str,
    climax: str,
    ending: str,
) -> str:
    return "\n".join(
        [
            f"第{chapter_num}章 - 推进测试{chapter_num}",
            "## 1. 基础元信息",
            f"* **章节序号**：第{chapter_num}章",
            "* **章节标题**：推进测试",
            f"* **核心功能**：{core_function}",
            "* **出场角色**：秦昭野",
            "## 2. 张力与冲突",
            "* **核心冲突点**：高压求生与情报争夺",
            "## 3. 匠心思维应用",
            "* **应用场景**：矿牢环境策略使用",
            "## 4. 伏笔与信息差",
            "* **本章植入伏笔**：后续行动线索",
            "* **本章回收伏笔**：前章铺垫回收",
            "## 5. 暧昧与修罗场",
            "* **涉及的女性角色互动**：本章不涉及女性角色互动",
            "## 6. 剧情精要",
            f"* **开场**：{opening}",
            "* **发展**：主角在高压环境中执行细化策略",
            f"* **高潮**：{climax}",
            f"* **收尾**：{ending}",
            "## 7. 衔接设计",
            "* **承上**：承接上一章线索",
            "* **转场**：从矿牢内部转入新冲突",
            "* **启下**：抛出下一章执行目标",
        ]
    )


def _build_metadata_style_chapter_without_section1_header(chapter_num: int = 1) -> str:
    return "\n".join(
        [
            f"第{chapter_num}章",
            "章节标题：寒门惊梦，残卷初鸣",
            "定位：第1卷 边荒求生 - 子幕1 绝境重启",
            "核心功能：确立重生节点与废脉困境",
            "目标字数：5000字",
            "出场角色：秦昭野",
            "",
            "## 2. 张力与冲突",
            "冲突类型：生存",
            "## 3. 匠心思维应用",
            "应用场景：废脉求生",
            "## 4. 伏笔与信息差",
            "本章植入伏笔：古碑裂纹",
            "## 5. 暧昧与修罗场",
            "涉及的女性角色互动：本章不涉及女性角色互动",
            "## 6. 剧情精要",
            "开场：重生惊醒",
            "## 7. 衔接设计",
            "承上：开篇",
        ]
    )


def _create_generator(monkeypatch, **kwargs) -> StrictChapterGenerator:
    monkeypatch.setattr(
        "novel_generator.blueprint.create_llm_adapter",
        lambda **kwargs: object(),
    )
    return StrictChapterGenerator(
        interface_format="test",
        api_key="test",
        base_url="http://test.local",
        llm_model="test-model",
        timeout=1,
        **kwargs,
    )


def test_architecture_compliance_checker_fails_on_missing_fields(temp_dir):
    project = Path(temp_dir)
    (project / "Novel_architecture.txt").write_text("架构内容", encoding="utf-8")
    (project / "config").mkdir(exist_ok=True)
    (project / "config" / "foreshadowing_rules.json").write_text(
        json.dumps({"major_reversals": {}}, ensure_ascii=False),
        encoding="utf-8",
    )
    content = "\n\n".join(
        [
            _build_chapter(1),
            _build_chapter(2, missing_section=5),
        ]
    )
    (project / "Novel_directory.txt").write_text(content, encoding="utf-8")

    checker = ArchitectureComplianceChecker(str(project))
    result = checker.check_compliance_result()

    assert result["passed"] is False
    assert any("第2章缺少必要字段" in reason for reason in result["hard_fail_reasons"])


def test_sync_single_split_directory_file_writes_chapter_file(monkeypatch, temp_dir):
    project = Path(temp_dir)
    generator = _create_generator(monkeypatch)

    generator._sync_single_split_directory_file(
        str(project),
        12,
        "第12章 - 单章同步测试\n## 1. 基础元信息\n* **章节序号**：第12章",
    )

    chapter_path = project / "chapter_blueprints" / "chapter_12.txt"
    assert chapter_path.exists()
    content = chapter_path.read_text(encoding="utf-8")
    assert "第12章 - 单章同步测试" in content


def test_force_resolve_duplicate_titles_locally_renames_later_chapters(monkeypatch):
    generator = _create_generator(monkeypatch)
    content = "\n\n".join(
        [
            _build_chapter(1).replace("测试章节1", "强权即真理"),
            _build_chapter(2).replace("测试章节2", "强权即真理"),
            _build_chapter(3).replace("测试章节3", "势逆而转"),
        ]
    )

    deduped, renamed_count = generator._force_resolve_duplicate_titles_locally(content)
    assert renamed_count == 1
    assert "第2章 - 强权即真理·第2章" in deduped

    validation = generator._strict_validation(deduped, 1, 3)
    assert validation["is_valid"] is True


def test_try_local_duplicate_title_fallback_passes_when_only_duplicates(monkeypatch, temp_dir):
    project = Path(temp_dir)
    generator = _create_generator(monkeypatch)
    content = "\n\n".join(
        [
            _build_chapter(1).replace("测试章节1", "秩序的祭品"),
            _build_chapter(2).replace("测试章节2", "秩序的祭品"),
        ]
    )
    directory_file = project / "Novel_directory.txt"
    directory_file.write_text(content, encoding="utf-8")

    fixed_content, report, passed = generator._try_local_duplicate_title_fallback(
        filepath=str(project),
        filename_dir=str(directory_file),
        content=content,
        expected_end=2,
        report={"success": False, "last_errors": []},
    )

    assert passed is True
    assert report["success"] is True
    assert "第2章 - 秩序的祭品·第2章" in fixed_content


def test_inject_required_keywords_into_chapter_appends_anchor_line(monkeypatch):
    generator = _create_generator(monkeypatch)
    chapter = _build_chapter(881).replace("测试章节881", "灰烬里的名字")

    patched, count = generator._inject_required_keywords_into_chapter(
        chapter,
        ["179. 881-885章：卷末关节重锤", "真本传遍十三城"],
    )

    assert count >= 1
    assert "架构锚点补全" in patched
    assert "卷末关节重锤" in patched or "真本传遍十三城" in patched


def test_patch_consistency_keyword_gaps_targets_specific_chapter(monkeypatch):
    generator = _create_generator(monkeypatch)
    content = "\n\n".join(
        [
            _build_chapter(880).replace("测试章节880", "前章"),
            _build_chapter(881).replace("测试章节881", "当前章"),
        ]
    )
    issues = [
        {
            "chapter": "第881章",
            "required_keywords": ["卷末关节重锤", "真本传遍十三城"],
        }
    ]

    patched, injected_total = generator._patch_consistency_keyword_gaps(content, issues)
    assert injected_total >= 1
    chap_881 = generator._extract_single_chapter(patched, 881)
    chap_880 = generator._extract_single_chapter(patched, 880)
    assert "架构锚点补全" in chap_881
    assert "架构锚点补全" not in chap_880


def test_run_directory_quality_gate_uses_builtin_fallback(monkeypatch, temp_dir):
    project = Path(temp_dir)
    directory_file = project / "Novel_directory.txt"
    directory_file.write_text(_build_chapter(1), encoding="utf-8")
    (project / "Novel_architecture.txt").write_text(_build_architecture_with_entities(), encoding="utf-8")

    generator = _create_generator(monkeypatch)
    monkeypatch.setattr(generator, "_resolve_directory_validator_paths", lambda _: ("", ""))

    passed, report = generator._run_directory_quality_gate(str(project), str(directory_file))
    assert passed is True
    assert report["passed"] is True
    assert report["summary"]["total_chapters"] == 1


def test_run_directory_quality_gate_does_not_flag_inline_ellipsis_as_placeholder(monkeypatch, temp_dir):
    project = Path(temp_dir)
    directory_file = project / "Novel_directory.txt"
    directory_file.write_text(
        _build_chapter(1).replace(
            "* **核心冲突点**：测试冲突",
            "* **核心冲突点**：敌人逼近...主角仍保持冷静。",
        ),
        encoding="utf-8",
    )
    (project / "Novel_architecture.txt").write_text(_build_architecture_with_entities(), encoding="utf-8")

    generator = _create_generator(monkeypatch)
    monkeypatch.setattr(generator, "_resolve_directory_validator_paths", lambda _: ("", ""))

    passed, report = generator._run_directory_quality_gate(str(project), str(directory_file))
    assert passed is True
    assert report["summary"]["placeholder_count"] == 0


def test_run_directory_quality_gate_allows_multiline_female_interaction_with_arch_name(monkeypatch, temp_dir):
    project = Path(temp_dir)
    directory_file = project / "Novel_directory.txt"
    directory_file.write_text(
        _build_chapter(1).replace(
            "* **涉及的女性角色互动**：本章不涉及女性角色互动",
            "涉及的女性角色互动：\n* 姬夜罗（魔门线）",
        ),
        encoding="utf-8",
    )
    (project / "Novel_architecture.txt").write_text(_build_architecture_with_entities(), encoding="utf-8")

    generator = _create_generator(monkeypatch)
    monkeypatch.setattr(generator, "_resolve_directory_validator_paths", lambda _: ("", ""))

    passed, report = generator._run_directory_quality_gate(str(project), str(directory_file))
    assert passed is True
    assert "检测到女性互动描述，但未命中架构女主实名" not in report.get("hard_fail_reasons", [])


def test_run_directory_quality_gate_blocks_entity_drift(monkeypatch, temp_dir):
    project = Path(temp_dir)
    directory_file = project / "Novel_directory.txt"
    directory_file.write_text(
        _build_chapter(
            1,
            protagonist="林夜",
            female_line="与苏沐雪在城门夜雨中对峙",
        ),
        encoding="utf-8",
    )
    (project / "Novel_architecture.txt").write_text(_build_architecture_with_entities(), encoding="utf-8")

    generator = _create_generator(monkeypatch)
    monkeypatch.setattr(generator, "_resolve_directory_validator_paths", lambda _: ("", ""))

    passed, report = generator._run_directory_quality_gate(str(project), str(directory_file))
    assert passed is False
    reasons = report.get("hard_fail_reasons", [])
    assert any("主角实名" in reason for reason in reasons)
    assert any("女性互动" in reason for reason in reasons)


def test_resume_is_blocked_when_architecture_hash_changed(monkeypatch, temp_dir):
    import pytest

    project = Path(temp_dir)
    (project / "Novel_architecture.txt").write_text("新架构内容", encoding="utf-8")
    (project / "Novel_directory.txt").write_text(_build_chapter(1), encoding="utf-8")
    (project / ".blueprint_state.json").write_text(
        json.dumps(
            {
                "architecture_hash": "outdated-hash",
                "target_chapters": 5,
                "last_generated_chapter": 1,
                "completed": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    generator = _create_generator(monkeypatch)
    with pytest.raises(RuntimeError) as exc_info:
        generator.generate_complete_directory_strict(
            filepath=str(project),
            number_of_chapters=5,
            batch_size=1,
            auto_optimize=False,
        )
    assert "架构文件已变更" in str(exc_info.value)


def test_collect_postcheck_issue_map_merges_gate_and_low_score(monkeypatch):
    generator = _create_generator(monkeypatch)

    def fake_check_chapter_quality(self, content, chapter_info):
        chapter_num = int(chapter_info.get("chapter_number", 0))
        if chapter_num == 2:
            return SimpleNamespace(
                overall_score=62.0,
                issues=[SimpleNamespace(description="衔接跳跃"), SimpleNamespace(description="信息差不足")],
            )
        return SimpleNamespace(overall_score=88.0, issues=[])

    monkeypatch.setattr("quality_checker.QualityChecker.check_chapter_quality", fake_check_chapter_quality)

    full_content = "\n\n".join([_build_chapter(1), _build_chapter(2)])
    gate_report = {"hard_fail_reasons": ["第2章缺失节：5. 暧昧与修罗场"]}
    issue_map, score_map = generator._collect_postcheck_issue_map(
        full_content=full_content,
        target_score=80.0,
        gate_report=gate_report,
        compliance_result={},
    )

    assert 2 in issue_map
    assert any("低于目标" in item for item in issue_map[2])
    assert any("缺失节" in item for item in issue_map[2])
    assert score_map[2] == 62.0


def test_normalize_missing_sections_promotes_metadata_section1(monkeypatch):
    generator = _create_generator(monkeypatch)
    raw_content = _build_metadata_style_chapter_without_section1_header(1)

    normalized, fixes = generator._normalize_missing_sections(raw_content, 1, 1)

    assert fixes >= 1
    assert normalized.count("## 1. 基础元信息") == 1
    assert "章节标题：寒门惊梦，残卷初鸣" in normalized
    assert "[待完善]" not in normalized
    assert generator._strict_validation(normalized, 1, 1)["is_valid"] is True


def test_format_cleanup_content_promotes_metadata_section1_without_placeholder_template(monkeypatch):
    generator = _create_generator(monkeypatch)
    raw_content = _build_metadata_style_chapter_without_section1_header(1)

    cleaned, _ = generator._format_cleanup_content(raw_content)

    assert cleaned.count("## 1. 基础元信息") == 1
    assert "章节标题：寒门惊梦，残卷初鸣" in cleaned
    assert "[待补充]" not in cleaned


def test_format_cleanup_content_renumbers_shifted_required_sections_by_name(monkeypatch):
    generator = _create_generator(monkeypatch)
    raw_content = "\n".join(
        [
            "第1章 - 偏移节号测试",
            "## 1. 基础元信息",
            "章节序号：第1章",
            "章节标题：偏移节号测试",
            "定位：第1卷 测试卷 - 子幕1",
            "核心功能：测试节号修正",
            "目标字数：4500字",
            "出场角色：秦昭野",
            "## 2. 张力与冲突",
            "核心冲突点：测试冲突",
            "## 3. 核心结构",
            "结构说明：这是非强制模块",
            "## 4. 匠心思维应用",
            "应用场景：错位编号",
            "## 7. 伏笔与信息差",
            "本章植入伏笔：错位编号",
            "## 8. 暧昧与修罗场",
            "涉及的女性角色互动：本章不涉及女性角色互动",
            "## 11. 剧情精要",
            "开场：错位编号",
            "## 12. 衔接设计",
            "承上：错位编号",
        ]
    )

    cleaned, _ = generator._format_cleanup_content(raw_content)

    assert "## 3. 匠心思维应用" in cleaned
    assert "## 4. 伏笔与信息差" in cleaned
    assert "## 5. 暧昧与修罗场" in cleaned
    assert "## 6. 剧情精要" in cleaned
    assert "## 7. 衔接设计" in cleaned
    assert "[待补充]" not in cleaned


def test_format_cleanup_content_dedupes_duplicate_chapter_blocks(monkeypatch):
    generator = _create_generator(monkeypatch)
    long_block = _build_chapter(1) + "\n## 8. 创作指南\n长版本标记：保留"
    short_block = "\n".join(
        [
            "第1章 - 重复短版本",
            "## 1. 基础元信息",
            "章节序号：第1章",
            "短版本标记：删除",
            "## 2. 张力与冲突",
            "核心冲突点：短版本",
        ]
    )
    raw_content = f"{long_block}\n\n{short_block}"

    cleaned, stats = generator._format_cleanup_content(raw_content)
    chapter_headers = re.findall(
        r"(?m)^(?:#+\s*)?(?:\*\*)?\s*第\s*(\d+)\s*章(?:\s*[-–—:：]\s*[^\n*]+)?\s*(?:\*\*)?\s*$",
        cleaned,
    )

    assert chapter_headers == ["1"]
    assert stats["chapter_count"] == 1
    has_long_marker = "长版本标记：保留" in cleaned
    has_short_marker = "短版本标记：删除" in cleaned
    assert has_long_marker != has_short_marker


def test_extract_single_chapter_ignores_in_body_chapter_mentions(monkeypatch):
    generator = _create_generator(monkeypatch)
    chapter_one = _build_chapter(1).replace(
        "* **核心冲突点**：测试冲突",
        "* **核心冲突点**：当前危机与第2章后续布局呼应",
    )
    full_content = "\n\n".join([chapter_one, _build_chapter(2)])

    extracted = generator._extract_single_chapter(full_content, 1)

    assert "第2章后续布局呼应" in extracted
    assert "## 7. 衔接设计" in extracted
    assert "第2章 - 测试章节2" not in extracted


def test_replace_chapter_content_ignores_in_body_chapter_mentions(monkeypatch):
    generator = _create_generator(monkeypatch)
    chapter_one = _build_chapter(1).replace(
        "* **核心冲突点**：测试冲突",
        "* **核心冲突点**：当前危机与第2章后续布局呼应",
    )
    full_content = "\n\n".join([chapter_one, _build_chapter(2)])
    repaired_chapter_one = _build_chapter(1).replace("测试章节1", "修复后章节1").replace(
        "* **核心冲突点**：测试冲突",
        "* **核心冲突点**：修复方案与第2章后续布局联动",
    )

    updated = generator._replace_chapter_content(full_content, 1, repaired_chapter_one)
    extracted = generator._extract_single_chapter(updated, 1)

    assert updated.count("第1章 - 修复后章节1") == 1
    assert updated.count("第2章 - 测试章节2") == 1
    assert "修复方案与第2章后续布局联动" in extracted
    assert "第2章 - 测试章节2" not in extracted
    assert generator._strict_validation(updated, 1, 2)["is_valid"] is True


def test_format_cleanup_content_dedupes_duplicate_required_sections(monkeypatch):
    generator = _create_generator(monkeypatch)
    duplicated_tail = "\n".join(
        [
            "## 5. 暧昧与修罗场",
            "* **涉及的女性角色互动**：重复片段",
            "## 6. 剧情精要",
            "* **开场**：重复开场",
            "## 7. 衔接设计",
            "* **承上**：重复承上",
        ]
    )
    raw_content = _build_chapter(1) + "\n\n" + duplicated_tail

    cleaned, stats = generator._format_cleanup_content(raw_content)

    assert cleaned.count("## 5. 暧昧与修罗场") == 1
    assert cleaned.count("## 6. 剧情精要") == 1
    assert cleaned.count("## 7. 衔接设计") == 1
    assert stats["duplicate_section_fixes"] >= 1
    assert generator._strict_validation(cleaned, 1, 1)["is_valid"] is True


def test_collect_postcheck_issue_map_maps_global_placeholder_reason_to_chapter(monkeypatch):
    generator = _create_generator(monkeypatch)

    monkeypatch.setattr(
        "quality_checker.QualityChecker.check_chapter_quality",
        lambda self, content, chapter_info: SimpleNamespace(overall_score=92.0, issues=[]),
    )

    chapter_one = _build_metadata_style_chapter_without_section1_header(1).replace(
        "章节标题：寒门惊梦，残卷初鸣",
        "章节标题：[待补充]",
    )
    full_content = "\n\n".join([chapter_one, _build_chapter(2)])
    issue_map, score_map = generator._collect_postcheck_issue_map(
        full_content=full_content,
        target_score=80.0,
        gate_report={"hard_fail_reasons": ["检测到占位/省略痕迹 1 处"]},
        compliance_result={},
    )

    assert 1 in issue_map
    assert 2 not in issue_map
    assert any("检测到占位/省略痕迹" in item for item in issue_map[1])
    assert score_map[1] == 92.0


def test_collect_postcheck_issue_map_uses_all_chapters_when_placeholder_source_is_unknown(monkeypatch):
    generator = _create_generator(monkeypatch)

    monkeypatch.setattr(
        "quality_checker.QualityChecker.check_chapter_quality",
        lambda self, content, chapter_info: SimpleNamespace(overall_score=92.0, issues=[]),
    )

    full_content = "\n\n".join([_build_chapter(1), _build_chapter(2)])
    issue_map, _ = generator._collect_postcheck_issue_map(
        full_content=full_content,
        target_score=80.0,
        gate_report={"hard_fail_reasons": ["检测到占位/省略痕迹 1 处"]},
        compliance_result={},
    )

    assert sorted(issue_map.keys()) == [1, 2]
    assert all(any("检测到占位/省略痕迹" in item for item in items) for items in issue_map.values())


def test_targeted_postcheck_repair_extracts_single_chapter_from_llm_response(monkeypatch, temp_dir):
    generator = _create_generator(monkeypatch)
    project = Path(temp_dir)

    monkeypatch.setattr(
        "quality_checker.QualityChecker.check_chapter_quality",
        lambda self, content, chapter_info: SimpleNamespace(
            overall_score=60.0 if int(chapter_info.get("chapter_number", 0)) == 1 else 92.0,
            issues=[SimpleNamespace(description="低分待修复")],
        ),
    )

    class _FakeRepairer:
        def __init__(self, **kwargs):
            _ = kwargs

        def repair_single_chapter(self, chapter_number, original_content, quality_issues=None, max_retries=2):
            _ = original_content
            _ = quality_issues
            _ = max_retries
            repaired_target = _build_chapter(chapter_number).replace(
                f"测试章节{chapter_number}",
                f"修复后章节{chapter_number}",
            )
            leaked_extra = _build_chapter(chapter_number + 1).replace(
                f"测试章节{chapter_number + 1}",
                "污染章节",
            )
            return f"{repaired_target}\n\n{leaked_extra}"

    monkeypatch.setattr("novel_generator.blueprint_repairer.BlueprintRepairer", _FakeRepairer)

    full_content = "\n\n".join([_build_chapter(1), _build_chapter(2)])
    repaired_content, report = generator._run_targeted_repair_after_postcheck(
        filepath=str(project),
        full_content=full_content,
        target_score=80.0,
        gate_report={},
        compliance_result={},
    )

    assert report["repaired"] == [1]
    assert report["failed"] == []
    assert "第1章 - 修复后章节1" in repaired_content
    assert "污染章节" not in repaired_content
    assert repaired_content.count("第2章 - 测试章节2") == 1
    assert generator._strict_validation(repaired_content, 1, 2)["is_valid"] is True


def test_architecture_consistency_fails_when_chapter_mapping_unavailable(monkeypatch):
    generator = _create_generator(monkeypatch)
    content = _build_chapter(1)
    architecture_text = "## 5. 角色系统\n主角实名：秦昭野\n"

    result = generator._check_architecture_consistency(content, architecture_text)
    assert result["is_consistent"] is False
    assert result["critical_violations"] >= 1
    assert any("章节映射" in issue.get("description", "") for issue in result.get("issues", []))


def test_task_card_guidance_is_injected_from_project_csv(monkeypatch, temp_dir):
    project = Path(temp_dir)
    task_card = project / "逆命天书_逐章任务卡_v2.4.csv"
    task_card.write_text(
        "\n".join(
            [
                "chapter,volume,phase,window_15,card_id,realm_stage,realm_substage,combo_2p1s,conflict_hint,trope_ban,core_goal,conflict_type,payoff_type,cost_type,pov,quality_flag,notes",
                "1,1,1,001-015,V01-C01,引炁,初段,图腾术+星历术+符契术,战斗>资源>叙事,天降神力一章无敌,古碑爆裂立悬念,,,,,todo,",
                "2,1,1,001-015,V01-C01,引炁,初段,图腾术+星历术+符契术,战斗>资源>叙事,天降神力一章无敌,重生矿牢高压开局,,,,,todo,",
            ]
        ),
        encoding="utf-8",
    )

    generator = _create_generator(monkeypatch)
    guidance = generator._build_task_card_guidance(str(project), 1, 2)

    assert "章节任务卡（硬约束" in guidance
    assert "第1章" in guidance
    assert "核心目标：古碑爆裂立悬念" in guidance
    assert "九境：引炁/初段" in guidance
    assert "术法组合：图腾术+星历术+符契术" in guidance
    assert "冲突优先：战斗>资源>叙事" in guidance
    assert "禁用桥段：天降神力一章无敌" in guidance


def test_extract_architecture_entities_filters_non_character_noise(monkeypatch):
    generator = _create_generator(monkeypatch)
    architecture_text = "\n".join(
        [
            "主角实名：秦昭野",
            "1. 源海（天书源头与命运缝线）",
            "2. 宁照雪（宗门线）",
            "3. 姬夜罗（魔门线）",
            "4. 对外协作（协作线）",
        ]
    )

    protagonist, female_leads = generator._extract_architecture_entities(architecture_text)
    assert protagonist == "秦昭野"
    assert "宁照雪" in female_leads
    assert "姬夜罗" in female_leads
    assert "源海" not in female_leads
    assert "对外协作" not in female_leads


def test_extract_novel_title_prefers_explicit_metadata(monkeypatch):
    generator = _create_generator(monkeypatch)
    architecture_text = "\n".join(
        [
            "## 1. 20本参考池",
            "1. 《诡秘之主》",
            "2. 《奥术神座》",
            "小说名：逆命天书",
        ]
    )

    title = generator._extract_novel_title_from_architecture(architecture_text)
    assert title == "逆命天书"


def test_extract_novel_title_ignores_reference_pool_entries(monkeypatch):
    generator = _create_generator(monkeypatch)
    architecture_text = "\n".join(
        [
            "## 1. 20本参考池",
            "1. 《诡秘之主》",
            "2. 《奥术神座》",
            "## 6. 四十卷展开",
            "卷1《边荒断命》",
        ]
    )

    title = generator._extract_novel_title_from_architecture(architecture_text)
    assert title == "本书"


def test_extract_novel_title_falls_back_to_project_folder_name(monkeypatch):
    generator = _create_generator(monkeypatch)
    architecture_text = "\n".join(
        [
            "## 1. 20本参考池",
            "1. 《诡秘之主》",
            "2. 《奥术神座》",
        ]
    )

    title = generator._extract_novel_title_from_architecture(
        architecture_text,
        project_path="/tmp/逆命天书",
    )
    assert title == "逆命天书"


def test_architecture_consistency_ignores_function_reward_tail_noise(monkeypatch):
    generator = _create_generator(monkeypatch)
    content = _build_chapter(1).replace("测试开场", "古碑爆裂后，秦昭野前世陨落")
    architecture_text = "\n".join(
        [
            "## 15. 卷1-卷4详细情节点（80点，可直接拆章）",
            "### 15.1 卷1《边荒断命》情节点（1-20）",
            "1. 1-3章：古碑爆裂，主角前世身死。功能：立悬念。回报/代价：读者立即入局，主角失去旧世界身份。",
        ]
    )

    result = generator._check_architecture_consistency(content, architecture_text)

    assert result["is_consistent"] is True
    chapter_issues = [
        issue
        for issue in result.get("issues", [])
        if issue.get("chapter") == "第1章"
    ]
    assert chapter_issues == []


def test_architecture_consistency_allows_window_template_mapping(monkeypatch):
    generator = _create_generator(monkeypatch)
    architecture_text = "\n".join(
        [
            "## 11. 开篇执行模板（前120章）",
            "### 11.1 1-30章（生死钩）",
            "- 重生困局 -> 天书初鸣 -> 第一场反杀 -> 血脉苗头 -> 姬夜罗敌对登场 -> 边荒小决战。",
            "- 目标：读者确认主角有脑够狠且有代价。",
            "## 94. 全书40卷章节配额基线",
            "| 卷次 | 章节范围 | 目标字数 | 阶段 |",
            "| 卷1 | 1-100 | 70万-80万 | 第一阶段 |",
        ]
    )
    content = _build_chapter(1).replace(
        "测试开场",
        "主角重生于边荒乱葬岗，天书初鸣后完成第一场反杀并确认血脉异样。",
    )

    result = generator._check_architecture_consistency(content, architecture_text)

    assert result["is_consistent"] is True
    assert result["major_violations"] == 0


def test_architecture_consistency_blocks_duplicate_progression_in_same_arch_range(monkeypatch):
    generator = _create_generator(monkeypatch)
    architecture_text = "\n".join(
        [
            "## 15. 卷1-卷4详细情节点（80点，可直接拆章）",
            "### 15.1 卷1《矿牢反杀》情节点（1-20）",
            "1. 11-14章：主角借矿牢地形反杀监工队，确立首个爽点，并被地方豪强盯上。",
        ]
    )
    content = "\n\n".join(
        [
            _build_progression_chapter(
                11,
                "主角借矿牢地形反杀监工队并被地方豪强盯上",
                "主角借矿牢地形反杀监工队，诱导监工深入狭窄矿道",
                "主角借矿牢地形反杀监工队，完成首个爽点并夺取腰牌",
                "主角借矿牢地形反杀监工队后确认被地方豪强盯上",
            ),
            _build_progression_chapter(
                12,
                "主角借矿牢地形反杀监工队并被地方豪强盯上",
                "主角借矿牢地形反杀监工队，继续使用同一塌方矿道",
                "主角借矿牢地形反杀监工队，完成首个爽点并夺取腰牌",
                "主角借矿牢地形反杀监工队后确认被地方豪强盯上",
            ),
            _build_progression_chapter(
                13,
                "主角借矿牢地形反杀监工队并被地方豪强盯上",
                "主角借矿牢地形反杀监工队，反复触发相同矿道陷阱",
                "主角借矿牢地形反杀监工队，完成首个爽点并夺取腰牌",
                "主角借矿牢地形反杀监工队后确认被地方豪强盯上",
            ),
        ]
    )

    result = generator._check_architecture_consistency(content, architecture_text)

    assert result["is_consistent"] is False
    duplicate_chapters = {issue.get("chapter") for issue in result.get("issues", []) if "重复" in issue.get("description", "")}
    assert "第12章" in duplicate_chapters
    assert "第13章" in duplicate_chapters
    assert any(
        ("事件推进重复度过高" in issue.get("description", ""))
        or ("核心功能高度重复" in issue.get("description", ""))
        for issue in result.get("issues", [])
    )


def test_architecture_consistency_allows_distinct_progression_in_same_arch_range(monkeypatch):
    generator = _create_generator(monkeypatch)
    architecture_text = "\n".join(
        [
            "## 15. 卷1-卷4详细情节点（80点，可直接拆章）",
            "### 15.1 卷1《封禁真相》情节点（1-20）",
            "1. 15-18章：主角确认血脉封禁符真相并推进解封布局。",
        ]
    )
    content = "\n\n".join(
        [
            _build_progression_chapter(
                15,
                "主角确认血脉封禁符来源并建立证据链",
                "主角通过天书内视发现脊椎处封禁符纹路",
                "主角比对伤痕与符纹，确认并非天生废脉",
                "主角记录封禁符特征，准备追查施术者",
            ),
            _build_progression_chapter(
                16,
                "主角围绕血脉封禁符真相推进解封布局，并破解监工记录简锁定豪强徽记",
                "主角拆解记录简暗码并定位豪强转运路线，同时校验血脉封禁符真相",
                "主角结合缴获腰牌推进解封布局，锁定幕后豪强管家身份",
                "主角制定伪装计划并延伸解封布局，准备接触药库线人",
            ),
            _build_progression_chapter(
                17,
                "主角围绕血脉封禁符真相完善解封布局，并推演潜入药库路径",
                "主角利用天书推演解封步骤与灵材配比，进一步核实血脉封禁符真相",
                "主角在药库外围布置撤离路线并校准解封布局的执行窗口",
                "主角锁定潜入窗口，解封布局进入执行倒计时",
            ),
        ]
    )

    result = generator._check_architecture_consistency(content, architecture_text)

    assert result["is_consistent"] is True
    assert all(
        "事件推进重复度过高" not in issue.get("description", "")
        for issue in result.get("issues", [])
    )


def test_architecture_consistency_allows_wxhyj_boundary_overlap_without_false_positive(monkeypatch):
    generator = _create_generator(monkeypatch)
    architecture_text = "\n".join(
        [
            "## 15. 卷1-卷4详细情节点（80点，可直接拆章）",
            "### 15.1 卷1《封禁疑云》情节点（1-20）",
            "1. 15-18章：主角发现血脉封禁符，确认疑似人为废脉真相，并围绕解封与追查幕后黑手持续推进。",
        ]
    )
    content = "\n\n".join(
        [
            _build_progression_chapter(
                15,
                "主角利用天书残页洞察自身病灶，发现血脉封禁符，确立疑似人为废脉真相，并记录封禁纹路证据链",
                "秦昭野战后搜身时触发天书显影，脊椎异常纹路首次显现",
                "主角发现血脉封禁符并比对记录简，确认疑似人为废脉真相",
                "主角整理封禁纹路证据链，准备追查幕后黑手",
            ),
            _build_progression_chapter(
                16,
                "主角在确认疑似人为废脉真相后，围绕解封与追查幕后黑手持续推进，拆解监工记录简暗码并锁定药库内线身份",
                "主角围绕解封与追查幕后黑手持续推进，先拆解记录简朱砂标记并排查豪强转运时间差",
                "主角将疑似人为废脉真相与豪强转运链对照，锁定药库内线与替班节奏",
                "主角完成接触窗口规划，转入潜入执行倒计时",
            ),
            _build_progression_chapter(
                17,
                "主角通过家族徽记与封禁纹路复核，发现血脉封禁符关联势力，进一步确认疑似人为废脉真相并推演潜入药库路径",
                "主角复盘封禁纹路并校验家族徽记来源，开始推演潜入药库方案",
                "主角发现血脉封禁符与豪强印记存在对应关系，再次确认疑似人为废脉真相",
                "主角锁定潜入窗口与撤离路径，解封布局进入执行阶段",
            ),
        ]
    )

    result = generator._check_architecture_consistency(content, architecture_text)

    assert result["is_consistent"] is True
    assert all(
        not (
            issue.get("chapter") == "第17章"
            and "事件推进重复度过高" in issue.get("description", "")
        )
        for issue in result.get("issues", [])
    )


def test_architecture_consistency_detects_lookback_duplicate_progression(monkeypatch):
    generator = _create_generator(monkeypatch)
    architecture_text = "\n".join(
        [
            "## 15. 卷1-卷4详细情节点（80点，可直接拆章）",
            "### 15.1 卷2《账册风暴》情节点（21-40）",
            "1. 31-34章：主角围绕军械账册追查豪强贪墨证据。",
        ]
    )
    content = "\n\n".join(
        [
            _build_progression_chapter(
                31,
                "主角潜入城防库房夺取军械账册，并锁定豪强贪墨证据",
                "主角夜探库房，避开巡防耳目",
                "主角夺取账册并抄录豪强账目漏洞",
                "主角确认账册真伪，准备转移证据",
            ),
            _build_progression_chapter(
                32,
                "主角伪装伤兵混入医馆，建立撤离接应点并转移账册",
                "主角以伤兵身份进入医馆并接触药童",
                "主角利用医馆暗道转移账册抄本",
                "主角搭建撤离节点，等待下一步接头",
            ),
            _build_progression_chapter(
                33,
                "主角再次潜入城防库房夺取军械账册，并确认豪强贪墨证据",
                "主角趁交接混乱回到库房内室",
                "主角夺取账册正本并比对豪强资金流向",
                "主角确认贪墨证据后决定公开切口",
            ),
        ]
    )

    result = generator._check_architecture_consistency(content, architecture_text)

    assert result["is_consistent"] is False
    assert any(
        issue.get("chapter") == "第33章"
        and (
            "事件推进重复度过高" in issue.get("description", "")
            or "核心功能高度重复" in issue.get("description", "")
        )
        for issue in result.get("issues", [])
    )


def test_range_progression_uniqueness_allows_two_anchor_overlap_without_high_coverage(monkeypatch):
    generator = _create_generator(monkeypatch)
    samples = {
        "15-18章：封禁真相推进": [
            {
                "chapter_num": 15,
                "core_function": "",
                "focus_text": "发现血脉封禁符，确认疑似人为废脉真相，记录封禁纹路证据链",
                "tokens": [],
            },
            {
                "chapter_num": 16,
                "core_function": "",
                "focus_text": "拆解豪强转运记录，锁定药库内线身份，建立接触窗口",
                "tokens": [],
            },
            {
                "chapter_num": 17,
                "core_function": "",
                "focus_text": "发现血脉封禁符，确认疑似人为废脉真相，推演潜入药库路径",
                "tokens": [],
            },
        ]
    }

    issues = generator._check_range_progression_uniqueness(samples)

    assert all(
        not (
            issue.get("chapter") == "第17章"
            and "事件推进重复度过高" in issue.get("description", "")
        )
        for issue in issues
    )


def test_range_progression_uniqueness_blocks_two_anchor_full_coverage(monkeypatch):
    generator = _create_generator(monkeypatch)
    samples = {
        "41-44章：账册追查": [
            {
                "chapter_num": 41,
                "core_function": "",
                "focus_text": "伪造军令骗开库门，转移军械账册",
                "tokens": [],
            },
            {
                "chapter_num": 42,
                "core_function": "",
                "focus_text": "伪装账房学徒潜入外院，建立撤离暗道",
                "tokens": [],
            },
            {
                "chapter_num": 43,
                "core_function": "",
                "focus_text": "伪造军令骗开库门，并在混乱中转移军械账册",
                "tokens": [],
            },
        ]
    }

    issues = generator._check_range_progression_uniqueness(samples)

    assert any(
        issue.get("chapter") == "第43章"
        and "事件推进重复度过高" in issue.get("description", "")
        and float(issue.get("clause_overlap_ratio", 0.0)) >= 0.9
        for issue in issues
    )


def test_architecture_consistency_allows_single_anchor_overlap(monkeypatch):
    generator = _create_generator(monkeypatch)
    architecture_text = "\n".join(
        [
            "## 15. 卷1-卷4详细情节点（80点，可直接拆章）",
            "### 15.1 卷2《药库渗透》情节点（21-40）",
            "1. 21-23章：主角借黑市线人切入药库线，持续推进潜入准备。",
        ]
    )
    content = "\n\n".join(
        [
            _build_progression_chapter(
                21,
                "主角锁定黑市线人身份并确认药库密道入口",
                "主角追踪黑市流言，锁定线人轮值轨迹",
                "主角在旧仓巷口确认药库密道方位",
                "主角记录入口细节，准备后续接触",
            ),
            _build_progression_chapter(
                22,
                "主角围绕黑市线人身份展开渗透，并伪造通行文牒接近药库库房",
                "主角与线人接头并交换伪造文牒样本",
                "主角借夜市掩护靠近药库外库门",
                "主角完成踩点并回收伪造痕迹",
            ),
            _build_progression_chapter(
                23,
                "主角围绕黑市线人身份完成交易切入，并引爆库房外部警戒冲突",
                "主角利用交易切口吸引外围守卫调岗",
                "主角引爆假警讯制造库房外圈混乱",
                "主角在混乱中锁定正式潜入窗口",
            ),
        ]
    )

    result = generator._check_architecture_consistency(content, architecture_text)

    assert result["is_consistent"] is True
    assert all(
        "事件推进重复度过高" not in issue.get("description", "")
        for issue in result.get("issues", [])
    )


def test_generate_complete_directory_strict_fast_path_for_unchanged_completed_state(monkeypatch, temp_dir):
    project = Path(temp_dir)
    architecture_text = _build_architecture_with_entities()
    directory_text = _build_chapter(1)
    (project / "Novel_architecture.txt").write_text(architecture_text, encoding="utf-8")
    (project / "Novel_directory.txt").write_text(directory_text, encoding="utf-8")

    generator = _create_generator(monkeypatch)
    state = {
        "architecture_hash": generator._hash_text(architecture_text),
        "target_chapters": 1,
        "last_generated_chapter": 1,
        "completed": True,
        "completed_target_chapters": 1,
        "completed_content_hash": generator._hash_text(directory_text),
    }
    (project / ".blueprint_state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    def _unexpected_gate_call(*args, **kwargs):
        raise RuntimeError("gate should not run in fast path")

    monkeypatch.setattr(generator, "_run_directory_quality_gate", _unexpected_gate_call)

    ok = generator.generate_complete_directory_strict(
        filepath=str(project),
        number_of_chapters=1,
        batch_size=1,
        auto_optimize=True,
    )
    assert ok is True


def test_generate_complete_directory_strict_auto_repairs_existing_then_resumes(monkeypatch, temp_dir):
    project = Path(temp_dir)
    architecture_text = _build_architecture_with_entities()
    chapter1 = _build_chapter(1).replace("测试章节1", "强权即真理").replace(
        "* **章节序号**：第1章",
        "* **章节序号**：第1章\n* **定位**：第X卷",
    )
    chapter2 = _build_chapter(2).replace("测试章节2", "强权即真理").replace(
        "* **章节序号**：第2章",
        "* **章节序号**：第2章\n* **定位**：第X卷",
    )
    existing_invalid = "\n\n".join([chapter1, chapter2])

    (project / "Novel_architecture.txt").write_text(architecture_text, encoding="utf-8")
    (project / "Novel_directory.txt").write_text(existing_invalid, encoding="utf-8")

    generator = _create_generator(monkeypatch)
    repaired_existing = "\n\n".join(
        [
            _build_chapter(1).replace("测试章节1", "边荒复生"),
            _build_chapter(2).replace("测试章节2", "寒门立誓"),
        ]
    )

    calls = {"auto_repair": 0, "batch": 0}

    def _fake_auto_repair(filepath, filename_dir, existing_content, expected_end, max_rounds=2):
        calls["auto_repair"] += 1
        assert expected_end == 2
        return repaired_existing, {
            "success": True,
            "repaired_total": 2,
            "rounds_attempted": 1,
            "blocking_errors": [],
        }

    def _fake_generate_batch(*args, **kwargs):
        calls["batch"] += 1
        assert args[0] == 3
        assert args[1] == 3
        return _build_chapter(3).replace("测试章节3", "血契初鸣")

    class _DummyComplianceChecker:
        def __init__(self, *args, **kwargs):
            pass

        def generate_report_file(self):
            return str(project / "mock_report.json")

        def check_compliance_result(self):
            return {"passed": True, "hard_fail_reasons": []}

    monkeypatch.setattr(generator, "_auto_repair_existing_for_resume", _fake_auto_repair)
    monkeypatch.setattr(generator, "_generate_batch_with_retry", _fake_generate_batch)
    monkeypatch.setattr(generator, "_sync_split_directory_files", lambda *args, **kwargs: None)
    monkeypatch.setattr(generator, "_format_cleanup", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        generator,
        "_run_directory_quality_gate",
        lambda *args, **kwargs: (True, {"summary": {}, "hard_fail_reasons": [], "rewrite_hints": []}),
    )
    monkeypatch.setattr(
        "novel_generator.architecture_compliance.ArchitectureComplianceChecker",
        _DummyComplianceChecker,
    )

    ok = generator.generate_complete_directory_strict(
        filepath=str(project),
        number_of_chapters=3,
        batch_size=1,
        auto_optimize=False,
    )

    assert ok is True
    assert calls["auto_repair"] == 1
    assert calls["batch"] == 1
    final_text = (project / "Novel_directory.txt").read_text(encoding="utf-8")
    assert "第3章 - 血契初鸣" in final_text


def test_generate_complete_directory_strict_blocks_resume_on_unfixable_structure_errors(monkeypatch, temp_dir):
    project = Path(temp_dir)
    architecture_text = _build_architecture_with_entities()
    existing_invalid = "\n\n".join([_build_chapter(1), _build_chapter(3)])

    (project / "Novel_architecture.txt").write_text(architecture_text, encoding="utf-8")
    (project / "Novel_directory.txt").write_text(existing_invalid, encoding="utf-8")

    generator = _create_generator(monkeypatch)
    monkeypatch.setattr(
        generator,
        "_auto_repair_existing_for_resume",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not auto repair")),
    )
    monkeypatch.setattr(
        generator,
        "_generate_batch_with_retry",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not start generation")),
    )

    ok = generator.generate_complete_directory_strict(
        filepath=str(project),
        number_of_chapters=5,
        batch_size=1,
        auto_optimize=False,
    )
    assert ok is False


def test_generate_complete_directory_strict_recovers_progress_from_split_directory(monkeypatch, temp_dir):
    project = Path(temp_dir)
    architecture_text = _build_architecture_with_entities()

    # 主目录只剩到43章（例如历史异常中断导致）
    truncated_main = "\n\n".join(_build_chapter(i) for i in range(1, 44))
    (project / "Novel_architecture.txt").write_text(architecture_text, encoding="utf-8")
    (project / "Novel_directory.txt").write_text(truncated_main, encoding="utf-8")

    # 拆分目录实际已完整到100章
    split_dir = project / "chapter_blueprints"
    split_dir.mkdir(parents=True, exist_ok=True)
    for chapter_num in range(1, 101):
        (split_dir / f"chapter_{chapter_num}.txt").write_text(
            _build_chapter(chapter_num),
            encoding="utf-8",
        )

    generator = _create_generator(monkeypatch)
    calls = {"batch": 0}

    def _fake_generate_batch(*args, **kwargs):
        calls["batch"] += 1
        assert args[0] == 101
        assert args[1] == 101
        return _build_chapter(101).replace("测试章节101", "续写校验章")

    class _DummyComplianceChecker:
        def __init__(self, *args, **kwargs):
            pass

        def generate_report_file(self):
            return str(project / "mock_report.json")

        def check_compliance_result(self):
            return {"passed": True, "hard_fail_reasons": []}

    monkeypatch.setattr(generator, "_generate_batch_with_retry", _fake_generate_batch)
    monkeypatch.setattr(
        generator,
        "_auto_repair_existing_for_resume",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not auto repair")),
    )
    monkeypatch.setattr(generator, "_sync_split_directory_files", lambda *args, **kwargs: None)
    monkeypatch.setattr(generator, "_format_cleanup", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        generator,
        "_run_directory_quality_gate",
        lambda *args, **kwargs: (True, {"summary": {}, "hard_fail_reasons": [], "rewrite_hints": []}),
    )
    monkeypatch.setattr(
        "novel_generator.architecture_compliance.ArchitectureComplianceChecker",
        _DummyComplianceChecker,
    )

    ok = generator.generate_complete_directory_strict(
        filepath=str(project),
        number_of_chapters=101,
        batch_size=1,
        auto_optimize=False,
    )

    assert ok is True
    assert calls["batch"] == 1
    final_text = (project / "Novel_directory.txt").read_text(encoding="utf-8")
    assert "第101章 - 续写校验章" in final_text


def test_generate_complete_directory_strict_blocks_resume_when_auto_repair_disabled(monkeypatch, temp_dir):
    project = Path(temp_dir)
    architecture_text = _build_architecture_with_entities()
    chapter1 = _build_chapter(1).replace("测试章节1", "强权即真理").replace(
        "* **章节序号**：第1章",
        "* **章节序号**：第1章\n* **定位**：第X卷",
    )
    chapter2 = _build_chapter(2).replace("测试章节2", "强权即真理").replace(
        "* **章节序号**：第2章",
        "* **章节序号**：第2章\n* **定位**：第X卷",
    )
    existing_invalid = "\n\n".join([chapter1, chapter2])

    (project / "Novel_architecture.txt").write_text(architecture_text, encoding="utf-8")
    (project / "Novel_directory.txt").write_text(existing_invalid, encoding="utf-8")

    generator = _create_generator(monkeypatch, enable_resume_auto_repair_existing=False)
    monkeypatch.setattr(
        generator,
        "_auto_repair_existing_for_resume",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not auto repair")),
    )
    monkeypatch.setattr(
        generator,
        "_generate_batch_with_retry",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not start generation")),
    )

    ok = generator.generate_complete_directory_strict(
        filepath=str(project),
        number_of_chapters=3,
        batch_size=1,
        auto_optimize=False,
    )
    assert ok is False


def test_generate_complete_directory_strict_force_resume_skips_history_validation(monkeypatch, temp_dir):
    project = Path(temp_dir)
    architecture_text = _build_architecture_with_entities()
    chapter1 = _build_chapter(1).replace("测试章节1", "强权即真理").replace(
        "* **章节序号**：第1章",
        "* **章节序号**：第1章\n* **定位**：第X卷",
    )
    chapter2 = _build_chapter(2).replace("测试章节2", "强权即真理").replace(
        "* **章节序号**：第2章",
        "* **章节序号**：第2章\n* **定位**：第X卷",
    )
    existing_invalid = "\n\n".join([chapter1, chapter2])

    (project / "Novel_architecture.txt").write_text(architecture_text, encoding="utf-8")
    (project / "Novel_directory.txt").write_text(existing_invalid, encoding="utf-8")

    generator = _create_generator(
        monkeypatch,
        enable_resume_auto_repair_existing=False,
        enable_force_resume_skip_history_validation=True,
    )
    monkeypatch.setattr(
        generator,
        "_auto_repair_existing_for_resume",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not auto repair")),
    )

    calls = {"batch": 0}

    def _fake_generate_batch(*args, **kwargs):
        calls["batch"] += 1
        assert args[0] == 3
        assert args[1] == 3
        return _build_chapter(3).replace("测试章节3", "强制续传章")

    monkeypatch.setattr(generator, "_generate_batch_with_retry", _fake_generate_batch)
    monkeypatch.setattr(
        generator,
        "_run_directory_quality_gate",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("force-resume mode should skip release gate")),
    )

    ok = generator.generate_complete_directory_strict(
        filepath=str(project),
        number_of_chapters=3,
        batch_size=1,
        auto_optimize=False,
    )
    assert ok is True
    assert calls["batch"] == 1
    final_text = (project / "Novel_directory.txt").read_text(encoding="utf-8")
    assert "第3章 - 强制续传章" in final_text


def test_generate_batch_with_retry_reuses_context_guide_across_retries(monkeypatch):
    generator = _create_generator(monkeypatch)
    architecture_text = _build_architecture_with_entities()

    phase1_calls = {"count": 0}
    generation_calls = {"count": 0}

    monkeypatch.setattr("novel_generator.blueprint.time.sleep", lambda *_: None)
    monkeypatch.setattr(generator, "_create_strict_prompt_with_guide", lambda **kwargs: "prompt")
    monkeypatch.setattr(generator, "_context_guide_is_usable", lambda guide: True)
    monkeypatch.setattr(generator, "_normalize_missing_sections", lambda content, *_: (content, 0))
    monkeypatch.setattr(
        generator,
        "_check_architecture_consistency",
        lambda content, architecture: {"is_consistent": True},
    )

    validation_queue = [
        {"is_valid": False, "errors": ["first attempt failed"], "generated_chapters": []},
        {"is_valid": True, "errors": [], "generated_chapters": [1]},
    ]

    def _fake_strict_validation(*args, **kwargs):
        if validation_queue:
            return validation_queue.pop(0)
        return {"is_valid": True, "errors": [], "generated_chapters": [1]}

    def _fake_phase1(*args, **kwargs):
        phase1_calls["count"] += 1
        return "context-guide"

    def _fake_generation(*args, **kwargs):
        generation_calls["count"] += 1
        if generation_calls["count"] == 1:
            return "第1章 - 重试版本1"
        return _build_chapter(1).replace("测试章节1", "重试版本2")

    monkeypatch.setattr(generator, "_strict_validation", _fake_strict_validation)
    monkeypatch.setattr(generator, "_run_with_heartbeat", _fake_phase1)
    monkeypatch.setattr(generator, "_invoke_with_heartbeat", _fake_generation)

    result = generator._generate_batch_with_retry(
        start_chapter=1,
        end_chapter=1,
        architecture_text=architecture_text,
        existing_content="",
        filepath="",
    )

    assert phase1_calls["count"] == 1
    assert generation_calls["count"] == 2
    assert "重试版本2" in result


def test_generate_batch_with_retry_records_retry_telemetry(monkeypatch):
    generator = _create_generator(monkeypatch)
    architecture_text = _build_architecture_with_entities()

    monkeypatch.setattr("novel_generator.blueprint.time.sleep", lambda *_: None)
    monkeypatch.setattr(generator, "_create_strict_prompt_with_guide", lambda **kwargs: "prompt")
    monkeypatch.setattr(generator, "_context_guide_is_usable", lambda guide: True)
    monkeypatch.setattr(generator, "_normalize_missing_sections", lambda content, *_: (content, 0))
    monkeypatch.setattr(
        generator,
        "_check_architecture_consistency",
        lambda content, architecture: {"is_consistent": True},
    )

    validation_queue = [
        {"is_valid": False, "errors": ["first attempt failed"], "generated_chapters": []},
        {"is_valid": True, "errors": [], "generated_chapters": [1]},
    ]

    responses = [
        "第1章 - 首次失败样例",
        _build_chapter(1).replace("测试章节1", "第二次成功"),
    ]

    monkeypatch.setattr(generator, "_strict_validation", lambda *args, **kwargs: validation_queue.pop(0))
    monkeypatch.setattr(generator, "_run_with_heartbeat", lambda *args, **kwargs: "context-guide")
    monkeypatch.setattr(generator, "_invoke_with_heartbeat", lambda *args, **kwargs: responses.pop(0))
    monkeypatch.setattr(
        "novel_generator.schema_validator.SchemaValidator.validate_blueprint_format",
        lambda self, *args, **kwargs: {"is_valid": True, "errors": []},
    )

    result = generator._generate_batch_with_retry(
        start_chapter=1,
        end_chapter=1,
        architecture_text=architecture_text,
        existing_content="",
        filepath="",
    )

    telemetry = generator._latest_batch_telemetry
    assert telemetry.get("status") == "success"
    assert telemetry.get("success_attempt") == 2
    assert telemetry.get("attempt_count") == 2
    assert telemetry.get("retry_reasons") == ["validation_failed"]
    attempts = telemetry.get("attempts", [])
    assert len(attempts) == 2
    assert attempts[0].get("retry_reason") == "validation_failed"
    assert attempts[1].get("context_guide_reused") is True
    assert "第二次成功" in result


def test_append_run_batch_telemetry_keeps_recent_history(monkeypatch):
    generator = _create_generator(monkeypatch)
    run_state = {}

    for idx in range(35):
        generator._append_run_batch_telemetry(
            run_state,
            {
                "chapter_range": f"{idx}-{idx}",
                "status": "success",
                "attempt_count": 1,
                "success_attempt": 1,
                "total_seconds": 0.25,
                "retry_reasons": [],
            },
            max_history=30,
        )

    history = run_state.get("batch_telemetry_history", [])
    assert len(history) == 30
    assert history[0].get("chapter_range") == "5-5"
    assert run_state.get("last_batch_telemetry", {}).get("chapter_range") == "34-34"


def test_append_run_batch_telemetry_records_coverage_summary(monkeypatch):
    generator = _create_generator(monkeypatch)
    run_state = {}

    generator._append_run_batch_telemetry(
        run_state,
        {
            "chapter_range": "181-181",
            "status": "success",
            "attempt_count": 1,
            "success_attempt": 1,
            "total_seconds": 0.25,
            "retry_reasons": [],
            "attempts": [
                {
                    "attempt": 1,
                    "status": "success",
                    "coverage_source": "patched_from_full",
                    "missing_chapters_preflight": [181],
                }
            ],
        },
        max_history=30,
    )

    summary = run_state.get("last_batch_telemetry", {})
    assert summary.get("coverage_source") == "patched_from_full"
    assert summary.get("missing_chapters_preflight_count") == 1


def test_generate_batch_with_retry_recovers_mapping_gap_from_full_architecture(monkeypatch):
    generator = _create_generator(monkeypatch)

    runtime_architecture = "\n".join(
        [
            "## 0. 项目总纲",
            "3. 大循环（120-180章），地图升级、规则升级、敌我结构重排。",
            "43. 201-205章：司空烈，强者资格高于程序",
        ]
    )
    full_architecture = "\n".join(
        [
            runtime_architecture,
            "39. 181-185章：主角携幸存者北上学宫。功能：阶段切图。回报/代价：新增保护负担。",
        ]
    )

    monkeypatch.setattr("novel_generator.blueprint.time.sleep", lambda *_: None)
    captured_prompt_architecture = {"text": ""}

    def _fake_prompt_builder(**kwargs):
        captured_prompt_architecture["text"] = str(kwargs.get("architecture_text", ""))
        return "prompt"

    monkeypatch.setattr(generator, "_create_strict_prompt_with_guide", _fake_prompt_builder)
    monkeypatch.setattr(generator, "_context_guide_is_usable", lambda _guide: True)
    monkeypatch.setattr(generator, "_run_with_heartbeat", lambda *args, **kwargs: "context-guide")
    monkeypatch.setattr(generator, "_invoke_with_heartbeat", lambda *args, **kwargs: _build_chapter(181))

    seen = {"called": False}

    def _fake_consistency(content: str, architecture_text: str):
        seen["called"] = True
        assert "第181章：" in architecture_text
        return {"is_consistent": True, "issues": []}

    monkeypatch.setattr(generator, "_check_architecture_consistency", _fake_consistency)

    result = generator._generate_batch_with_retry(
        start_chapter=181,
        end_chapter=181,
        architecture_text=runtime_architecture,
        existing_content="",
        filepath="",
        full_architecture_text=full_architecture,
    )

    assert seen["called"] is True
    assert "第181章" in result
    assert "第181章：" not in captured_prompt_architecture["text"]
    telemetry = generator._latest_batch_telemetry
    assert telemetry.get("status") == "success"
    assert telemetry.get("attempts", [])[0].get("coverage_source") == "patched_from_full"
    assert telemetry.get("attempts", [])[0].get("missing_chapters_preflight") == [181]
    coverage_resolved = telemetry.get("attempts", [])[0].get("coverage_resolved", {})
    assert coverage_resolved.get("is_fully_covered") is True
    assert coverage_resolved.get("missing_count") == 0


def test_generate_batch_with_retry_fails_fast_on_unresolved_mapping_gap(monkeypatch):
    generator = _create_generator(monkeypatch)

    runtime_architecture = "\n".join(
        [
            "## 0. 项目总纲",
            "3. 大循环（120-180章），地图升级、规则升级、敌我结构重排。",
            "43. 201-205章：司空烈，强者资格高于程序",
        ]
    )

    def _should_not_call(*_args, **_kwargs):
        raise AssertionError("LLM path should not be called when mapping gap is unresolved")

    monkeypatch.setattr(generator, "_run_with_heartbeat", _should_not_call)
    monkeypatch.setattr(generator, "_invoke_with_heartbeat", _should_not_call)

    import pytest
    from novel_generator.blueprint import ArchitectureMappingGapError

    with pytest.raises(ArchitectureMappingGapError):
        generator._generate_batch_with_retry(
            start_chapter=181,
            end_chapter=181,
            architecture_text=runtime_architecture,
            existing_content="",
            filepath="",
            full_architecture_text="",
        )

    telemetry = generator._latest_batch_telemetry
    assert telemetry.get("status") == "failed"
    assert telemetry.get("attempt_count") == 1
    assert "mapping_gap" in (telemetry.get("retry_reasons") or [])
