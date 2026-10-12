import importlib.util
import pathlib
import sys
import unittest
from unittest import mock


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TEXT_UTILS_PATH = REPO_ROOT / "novel_generator" / "text_utils.py"


def load_text_utils_module():
    spec = importlib.util.spec_from_file_location("text_utils_under_test", TEXT_UTILS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TextUtilsTest(unittest.TestCase):
    def test_fallback_splits_chinese_sentences_without_spaces(self):
        text_utils = load_text_utils_module()

        sentences = text_utils.fallback_sentence_split("第一句。第二句！第三句？")

        self.assertEqual(sentences, ["第一句。", "第二句！", "第三句？"])

    def test_split_sentences_falls_back_when_nltk_is_unavailable(self):
        text_utils = load_text_utils_module()

        with mock.patch.dict(sys.modules, {"nltk": None}):
            sentences = text_utils.split_sentences("One sentence. Another sentence.")

        self.assertEqual(sentences, ["One sentence.", "Another sentence."])


if __name__ == "__main__":
    unittest.main()
