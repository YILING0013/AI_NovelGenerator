import json
import pathlib
import unittest

from config_manager import get_default_config, normalize_config, validate_choose_configs


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


class ConfigManagerTest(unittest.TestCase):
    def test_default_config_uses_current_model_presets(self):
        config = get_default_config()
        llm_configs = config["llm_configs"]

        self.assertIn("DeepSeek V4 Flash", llm_configs)
        self.assertEqual(llm_configs["DeepSeek V4 Flash"]["model_name"], "deepseek-v4-flash")
        self.assertIn("DeepSeek V4 Pro", llm_configs)
        self.assertEqual(llm_configs["Gemini 3.5 Flash"]["model_name"], "gemini-3.5-flash")
        self.assertEqual(llm_configs["OpenAI GPT 5.5"]["model_name"], "gpt-5.5")
        self.assertEqual(config["embedding_configs"]["OpenAI"]["model_name"], "text-embedding-3-small")
        self.assertEqual(config["embedding_configs"]["Gemini"]["model_name"], "gemini-embedding-2")

        stale_names = {"DeepSeek V3", "Gemini 2.0 Flash", "Gemini 2.5 Flash", "Gemini 2.5 Pro", "GPT 5"}
        self.assertTrue(stale_names.isdisjoint(llm_configs.keys()))
        self.assertEqual(validate_choose_configs(config), [])

    def test_normalize_config_migrates_legacy_task_choices(self):
        config = normalize_config({
            "llm_configs": {
                "DeepSeek V3": {"model_name": "deepseek-chat", "interface_format": "OpenAI"},
                "Gemini 2.5 Flash": {"model_name": "gemini-2.5-flash", "interface_format": "Gemini"},
                "GPT 5": {"model_name": "gpt-5", "interface_format": "OpenAI"},
            },
            "choose_configs": {
                "prompt_draft_llm": "DeepSeek V3",
                "chapter_outline_llm": "Gemini 2.5 Flash",
                "architecture_llm": "Gemini 2.0 Flash",
                "final_chapter_llm": "GPT 5",
                "consistency_review_llm": "DeepSeek V3",
            },
        })

        self.assertEqual(config["choose_configs"]["prompt_draft_llm"], "DeepSeek V4 Flash")
        self.assertEqual(config["choose_configs"]["chapter_outline_llm"], "Gemini 3.5 Flash")
        self.assertEqual(config["choose_configs"]["architecture_llm"], "Gemini 3.5 Flash")
        self.assertEqual(config["choose_configs"]["final_chapter_llm"], "OpenAI GPT 5.5")
        self.assertEqual(config["choose_configs"]["consistency_review_llm"], "DeepSeek V4 Flash")
        self.assertEqual(validate_choose_configs(config), [])

    def test_config_example_has_valid_task_references(self):
        example_path = REPO_ROOT / "config.example.json"
        config = json.loads(example_path.read_text(encoding="utf-8"))

        self.assertEqual(validate_choose_configs(config), [])
        self.assertEqual(config["llm_configs"]["Gemini 3.5 Flash"]["model_name"], "gemini-3.5-flash")
        self.assertNotIn("Gemini 2.0 Flash", json.dumps(config, ensure_ascii=False))
        self.assertNotIn("deepseek-chat", json.dumps(config, ensure_ascii=False))

    def test_embedding_ui_options_match_supported_adapters(self):
        config_tab_source = (REPO_ROOT / "ui" / "config_tab.py").read_text(encoding="utf-8")

        self.assertIn('emb_interface_options = ["OpenAI", "Azure OpenAI", "Gemini", "Ollama", "ML Studio", "SiliconFlow"]', config_tab_source)
        self.assertNotIn('emb_interface_options = ["DeepSeek"', config_tab_source)


if __name__ == "__main__":
    unittest.main()
