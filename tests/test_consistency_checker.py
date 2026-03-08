# -*- coding: utf-8 -*-
import unittest

from novel_generator.consistency_checker import ConsistencyChecker


class TestConsistencyChecker(unittest.TestCase):
    def test_death_extraction_filters_fake_character_phrase(self):
        checker = ConsistencyChecker(".")
        text = "那个本该身亡的人缓缓站起。李青被杀。"
        facts = checker.extract_facts_from_content(text, chapter_num=1)
        chars = [x.get("character") for x in facts.get("deaths", [])]
        self.assertIn("李青", chars)
        self.assertNotIn("那个本该", chars)

    def test_same_chapter_death_should_not_trigger_resurrection(self):
        checker = ConsistencyChecker(".")
        checker._facts_db["deaths"] = {
            "李青": {"chapter": 1, "context": "李青身亡"}
        }
        conflicts = checker.check_consistency("李青倒在地上，众人悲恸。", chapter_num=1)
        resurrection = [c for c in conflicts if c.get("type") == "resurrection"]
        self.assertEqual(len(resurrection), 0)

    def test_dead_character_reference_should_not_trigger_resurrection(self):
        checker = ConsistencyChecker(".")
        checker._facts_db["deaths"] = {
            "赵四": {"chapter": 1, "context": "赵四身亡"}
        }
        text = "赵四虽已废去，但其党羽仍在外门活动。众人议论赵四被废消息。"
        conflicts = checker.check_consistency(text, chapter_num=2)
        resurrection = [c for c in conflicts if c.get("type") == "resurrection"]
        self.assertEqual(len(resurrection), 0)

    def test_dead_character_alive_action_should_trigger_resurrection(self):
        checker = ConsistencyChecker(".")
        checker._facts_db["deaths"] = {
            "赵四": {"chapter": 1, "context": "赵四身亡"}
        }
        text = "夜色里，赵四走进院门，冷笑着说道：你们都得死。"
        conflicts = checker.check_consistency(text, chapter_num=2)
        resurrection = [c for c in conflicts if c.get("type") == "resurrection"]
        self.assertEqual(len(resurrection), 1)

    def test_death_extraction_ignores_hypothetical_or_figurative_phrases(self):
        checker = ConsistencyChecker(".")
        text = (
            "他们的嘴唇都是青白色的，像是死了很久的人。"
            "再不吃点东西，我怕我就先饿死了。"
            "李青被杀。"
        )
        facts = checker.extract_facts_from_content(text, chapter_num=1)
        chars = [x.get("character") for x in facts.get("deaths", [])]
        self.assertIn("李青", chars)
        self.assertNotIn("像是", chars)
        self.assertNotIn("就先饿", chars)

    def test_death_extraction_ignores_if_clause_name_bleed(self):
        checker = ConsistencyChecker(".")
        text = (
            "如果周明德死了，周家一定会追查到底。"
            "夜色里，周明德冷笑着说道：我会亲手抓住你。"
        )
        facts = checker.extract_facts_from_content(text, chapter_num=31)
        chars = [x.get("character") for x in facts.get("deaths", [])]
        self.assertNotIn("果周明德", chars)
        self.assertNotIn("周明德", chars)

    def test_invalid_dead_name_should_not_trigger_resurrection(self):
        checker = ConsistencyChecker(".")
        checker._facts_db["deaths"] = {
            "像是": {"chapter": 9, "context": "像是死了很久的人"}
        }
        text = "那道黑影像是从墙上走来的一团墨。"
        conflicts = checker.check_consistency(text, chapter_num=10)
        resurrection = [c for c in conflicts if c.get("type") == "resurrection"]
        self.assertEqual(len(resurrection), 0)


if __name__ == "__main__":
    unittest.main()
