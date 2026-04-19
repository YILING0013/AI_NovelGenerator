import unittest
from llm_adapters import check_base_url, create_llm_adapter, GenericOpenAIAdapter

class TestLLMAdapters(unittest.TestCase):
    def test_check_base_url(self):
        # Case 1: Already has /v1
        self.assertEqual(check_base_url("https://api.openai.com/v1"), "https://api.openai.com/v1")
        # Case 2: Missing /v1
        self.assertEqual(check_base_url("https://api.openai.com"), "https://api.openai.com/v1")
        # Case 3: Ends with #
        self.assertEqual(check_base_url("https://api.openai.com/custom#"), "https://api.openai.com/custom")
        # Case 4: Other version
        self.assertEqual(check_base_url("https://api.openai.com/v2"), "https://api.openai.com/v2")

    def test_create_llm_adapter_openai(self):
        adapter = create_llm_adapter(
            interface_format="OpenAI",
            base_url="https://api.openai.com/v1",
            model_name="gpt-4",
            api_key="sk-test",
            temperature=0.7,
            max_tokens=1000,
            timeout=60
        )
        self.assertIsInstance(adapter, GenericOpenAIAdapter)

if __name__ == "__main__":
    unittest.main()
