# -*- coding: utf-8 -*-
import unittest
from pathlib import Path

from novel_generator.consistency_review import (
    build_ledger_backed_review_inputs,
    has_obvious_conflict,
    extract_conflict_items,
)
from novel_generator.generation_state_facade import GenerationStateFacade


class TestHasObviousConflict(unittest.TestCase):
    def test_no_conflict_with_suggestions(self):
        text = "结论：未发现明显冲突。建议继续加强情感张力与细节描写。"
        self.assertFalse(has_obvious_conflict(text))

    def test_no_conflict_short_form(self):
        self.assertFalse(has_obvious_conflict("无明显冲突"))

    def test_tentative_risk_should_not_block(self):
        text = "未发现硬性冲突，但存在潜在节奏不一致风险，建议后续关注。"
        self.assertFalse(has_obvious_conflict(text))

    def test_explicit_conflict_should_block(self):
        text = "发现明显冲突：主角上一章失忆，本章却完整回忆过去，存在前后不一致。"
        self.assertTrue(has_obvious_conflict(text))

    def test_problem_list_should_block(self):
        text = "问题1：角色设定矛盾，人物动机前后不一致。原因：... 建议修复：..."
        self.assertTrue(has_obvious_conflict(text))

    def test_extract_conflict_items(self):
        text = "无明显冲突。\n问题1：设定冲突，时间线不一致。\n建议：修复锚点。"
        items = extract_conflict_items(text, limit=2)
        self.assertTrue(items)
        self.assertIn("问题1", items[0])

    def test_policy_suggestion_without_evidence_should_not_block(self):
        text = (
            "### 1. 改命/代价系统的概念映射不一致\n"
            "建议：在136.2中补充条款，统一口径。"
        )
        self.assertFalse(has_obvious_conflict(text))
        self.assertEqual(extract_conflict_items(text, limit=3), [])

    def test_conflict_with_evidence_should_block(self):
        text = (
            "问题1：借契与债务系统冲突。\n"
            "证据：本章写“借契不计息”，后文又写“日息一厘，复利计算”。"
        )
        self.assertTrue(has_obvious_conflict(text))
        items = extract_conflict_items(text, limit=3)
        self.assertTrue(items)

    def test_extract_conflict_items_keep_enough_context(self):
        text = (
            "问题1：术语冲突。证据：本章连续使用“系统、精神力、灵气”等通用词，"
            "与设定中“三轨九术、天书残页、灵机/炁”口径不一致，导致世界观语言纯度下降。"
        )
        items = extract_conflict_items(text, limit=1)
        self.assertTrue(items)
        self.assertIn("术语冲突", items[0])
        self.assertIn("三轨九术", items[0])


class TestLedgerBackedReviewInputs(unittest.TestCase):
    def test_build_inputs_enriches_summary_state_and_plot_arcs(self):
        tmp_path = Path(self._testMethodName)
        if tmp_path.exists():
            for child in sorted(tmp_path.glob("**/*"), reverse=True):
                if child.is_file():
                    child.unlink()
                elif child.is_dir():
                    child.rmdir()
            tmp_path.rmdir()
        tmp_path.mkdir()
        try:
            facade = GenerationStateFacade(str(tmp_path), chapters_per_volume=2)
            facade.commit_chapter_state(
                chapter_number=1,
                chapter_text="第一章正文",
                global_summary_text="全书摘要：主角已踏上复仇路。",
                character_state_text="主角状态：轻伤但可战。",
                chapter_summary="主角离开故乡，立下誓言。",
            )
            (tmp_path / "plot_arcs.txt").write_text("主线推进：追查仇敌。", encoding="utf-8")
            (tmp_path / "hook_registry.json").write_text(
                '[{"hook_text": "青铜门背后的真相", "status": "open"}]',
                encoding="utf-8",
            )
            (tmp_path / ".narrative_threads.json").write_text(
                '[{"name": "复仇主线"}]',
                encoding="utf-8",
            )

            character_state_text, global_summary_text, plot_arcs_text = build_ledger_backed_review_inputs(
                filepath=str(tmp_path),
                chapter_number=2,
            )

            self.assertIn("角色状态账本", character_state_text)
            self.assertIn("主角状态：轻伤但可战", character_state_text)
            self.assertIn("卷级记忆", global_summary_text)
            self.assertIn("主角离开故乡，立下誓言", global_summary_text)
            self.assertIn("现有剧情要点", plot_arcs_text)
            self.assertIn("复仇主线", plot_arcs_text)
            self.assertIn("青铜门背后的真相", plot_arcs_text)
        finally:
            for child in sorted(tmp_path.glob("**/*"), reverse=True):
                if child.is_file():
                    child.unlink()
                elif child.is_dir():
                    child.rmdir()
            tmp_path.rmdir()


if __name__ == "__main__":
    unittest.main()
