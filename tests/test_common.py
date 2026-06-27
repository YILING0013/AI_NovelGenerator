# -*- coding: utf-8 -*-
import importlib.util
import io
from pathlib import Path
import unittest
from contextlib import redirect_stdout

COMMON_PATH = Path(__file__).resolve().parents[1] / "novel_generator" / "common.py"
SPEC = importlib.util.spec_from_file_location("common_under_test", COMMON_PATH)
common = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(common)

invoke_with_cleaning = common.invoke_with_cleaning
remove_think_tags = common.remove_think_tags


class FakeLLMAdapter:
    def __init__(self, response):
        self.response = response

    def invoke(self, prompt):
        return self.response


class CommonCleaningTest(unittest.TestCase):
    def test_remove_think_tags_strips_reasoning_blocks(self):
        text = "prefix<think>internal reasoning</think>body"

        self.assertEqual("prefixbody", remove_think_tags(text))

    def test_remove_think_tags_strips_multiline_and_multiple_blocks(self):
        text = "A<think>line 1\nline 2</think>B<think>another</think>C"

        self.assertEqual("ABC", remove_think_tags(text))

    def test_invoke_with_cleaning_removes_think_tags_from_llm_output(self):
        adapter = FakeLLMAdapter(
            "```<think>internal reasoning should be hidden</think>\nChapter text```"
        )

        with redirect_stdout(io.StringIO()):
            result = invoke_with_cleaning(adapter, "write chapter")

        self.assertEqual("Chapter text", result)


if __name__ == "__main__":
    unittest.main()
