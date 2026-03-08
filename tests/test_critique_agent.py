# -*- coding: utf-8 -*-
import unittest

from novel_generator.critique_agent import PoisonousReaderAgent


class _MockAdapter:
    def __init__(self, response):
        self._response = response

    def invoke(self, _prompt):
        return self._response


class TestCritiqueAgent(unittest.TestCase):
    def test_parse_json_from_markdown_block(self):
        agent = PoisonousReaderAgent(llm_config={})
        text = """```json
{"rating":"Pass","score":8.2,"toxic_comment":"ok","improvement_demand":"none"}
```"""
        parsed = agent._parse_json(text)
        self.assertIsInstance(parsed, dict)
        self.assertEqual(parsed.get("rating"), "Pass")

    def test_parse_failure_returns_non_blocking_result(self):
        agent = PoisonousReaderAgent(llm_config={})
        agent.llm_adapter = _MockAdapter("这不是json")
        result = agent.critique_chapter("test content")
        self.assertTrue(result.get("parse_failed"))
        self.assertEqual(result.get("rating"), "Pass")
        self.assertGreaterEqual(float(result.get("score", 0)), 7.5)

    def test_normalize_result_clamps_score_and_rating(self):
        agent = PoisonousReaderAgent(llm_config={})
        normalized = agent._normalize_result({"rating": "maybe", "score": 999})
        self.assertEqual(normalized["rating"], "Pass")
        self.assertEqual(normalized["score"], 10.0)


if __name__ == "__main__":
    unittest.main()
