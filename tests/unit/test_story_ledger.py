from __future__ import annotations

import json
from pathlib import Path

from novel_generator.story_ledger import StoryLedger


def test_story_ledger_bootstraps_from_legacy_views(tmp_path: Path):
    (tmp_path / "global_summary.txt").write_text("全局摘要A", encoding="utf-8")
    (tmp_path / "character_state.txt").write_text("角色状态A", encoding="utf-8")
    (tmp_path / "world_state.json").write_text(
        json.dumps({"world_flags": {"暴雨夜": True}}, ensure_ascii=False),
        encoding="utf-8",
    )

    ledger = StoryLedger(str(tmp_path))
    ledger.ensure_initialized()

    manifest = json.loads((tmp_path / "story_ledger" / "manifest.json").read_text(encoding="utf-8"))
    views = ledger.load_legacy_views()

    assert manifest["schema_version"] == 1
    assert views["global_summary_text"] == "全局摘要A"
    assert views["character_state_text"] == "角色状态A"
    assert views["world_state"] == {"world_flags": {"暴雨夜": True}}


def test_story_ledger_records_chapter_updates_and_builds_volume_summary(tmp_path: Path):
    ledger = StoryLedger(str(tmp_path), chapters_per_volume=2)
    ledger.ensure_initialized()

    ledger.record_chapter_update(
        chapter_number=1,
        chapter_text="第一章正文",
        global_summary_text="全局摘要1",
        character_state_text="角色状态1",
        chapter_summary="第一章摘要",
    )
    ledger.record_chapter_update(
        chapter_number=2,
        chapter_text="第二章正文",
        global_summary_text="全局摘要2",
        character_state_text="角色状态2",
        chapter_summary="第二章摘要",
    )

    snapshot = ledger.build_context_snapshot(current_chapter_num=2)
    chapter_record = json.loads(
        (tmp_path / "story_ledger" / "chapters" / "chapter_000002.json").read_text(encoding="utf-8")
    )

    assert "第一章摘要" in snapshot["volume_summary_text"]
    assert "第二章摘要" in snapshot["volume_summary_text"]
    assert chapter_record["chapter_summary"] == "第二章摘要"
    assert (tmp_path / "global_summary.txt").read_text(encoding="utf-8") == "全局摘要2"
    assert (tmp_path / "character_state.txt").read_text(encoding="utf-8") == "角色状态2"
