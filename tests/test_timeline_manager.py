# -*- coding: utf-8 -*-
import tempfile
import unittest

from novel_generator.timeline_manager import TimelineManager


class TestTimelineManager(unittest.TestCase):
    def test_chapter1_should_not_use_stale_current_day(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = TimelineManager(tmpdir)
            mgr.state = {
                "current_day": 30,
                "chapters": {"1": {"day": 1, "source": "explicit"}},
            }
            conflicts = mgr.check_timeline_consistency("第1天 清晨。", chapter_num=1)
            self.assertEqual([], [c for c in conflicts if c.get("type") == "timeline_regression"])

    def test_chapter2_should_compare_with_previous_chapters_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = TimelineManager(tmpdir)
            mgr.state = {
                "current_day": 30,
                "chapters": {"1": {"day": 5, "source": "explicit"}},
            }
            conflicts = mgr.check_timeline_consistency("D+1 夜。", chapter_num=2)
            regressions = [c for c in conflicts if c.get("type") == "timeline_regression"]
            self.assertTrue(regressions)

    def test_relative_markers_should_not_trigger_intra_chapter_regression(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = TimelineManager(tmpdir)
            mgr.state = {
                "current_day": 7,
                "chapters": {"1": {"day": 7, "source": "explicit"}},
            }
            chapter_text = (
                "命轨：七日后午时三刻。"
                "画面一：三天后，刀疤脸醉酒。"
                "画面二：五日后，看守收到家书。"
            )
            conflicts = mgr.check_timeline_consistency(chapter_text, chapter_num=2)
            intra_regressions = [
                c for c in conflicts if c.get("type") == "intra_chapter_timeline_regression"
            ]
            self.assertEqual([], intra_regressions)

    def test_absolute_markers_should_still_trigger_intra_chapter_regression(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = TimelineManager(tmpdir)
            mgr.state = {
                "current_day": 7,
                "chapters": {"1": {"day": 7, "source": "explicit"}},
            }
            conflicts = mgr.check_timeline_consistency("D+7 深夜。D+3 清晨。", chapter_num=2)
            intra_regressions = [
                c for c in conflicts if c.get("type") == "intra_chapter_timeline_regression"
            ]
            self.assertTrue(intra_regressions)


if __name__ == "__main__":
    unittest.main()
