# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
CONSISTENCY_CHECKER_PATH = REPO_ROOT / "consistency_checker.py"


def load_consistency_checker(response):
    class FakeAdapter:
        def invoke(self, prompt):
            return response

    fake_llm_adapters = types.ModuleType("llm_adapters")
    fake_llm_adapters.create_llm_adapter = lambda **kwargs: FakeAdapter()

    log_records = []
    fake_common = types.ModuleType("novel_generator.common")
    fake_common.log_llm_io = lambda label, content: log_records.append((label, content))

    fake_package = types.ModuleType("novel_generator")
    fake_package.__path__ = []

    spec = importlib.util.spec_from_file_location("consistency_checker_under_test", CONSISTENCY_CHECKER_PATH)
    module = importlib.util.module_from_spec(spec)

    with mock.patch.dict(
        sys.modules,
        {
            "llm_adapters": fake_llm_adapters,
            "novel_generator": fake_package,
            "novel_generator.common": fake_common,
        },
    ):
        spec.loader.exec_module(module)

    return module, log_records


class ConsistencyCheckerTest(unittest.TestCase):
    def test_check_consistency_cleans_think_tags_from_direct_llm_response(self):
        module, log_records = load_consistency_checker("<think>secret reasoning</think>无明显冲突")

        result = module.check_consistency(
            novel_setting="设定",
            character_state="角色",
            global_summary="摘要",
            chapter_text="章节",
            api_key="key",
            base_url="https://example.com",
            model_name="model",
        )

        self.assertEqual(result, "无明显冲突")
        self.assertNotIn("<think>", result)
        self.assertNotIn("</think>", result)
        self.assertNotIn("secret reasoning", result)
        self.assertIn(("ConsistencyChecker Response", "无明显冲突"), log_records)


if __name__ == "__main__":
    unittest.main()
