import os
import unittest
from utils import read_file, save_string_to_txt, clear_file_content, append_text_to_file

class TestUtils(unittest.TestCase):
    def setUp(self):
        self.test_file = "test_file.txt"

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

    def test_save_and_read(self):
        content = "Hello, NovelForge!"
        save_string_to_txt(content, self.test_file)
        read_content = read_file(self.test_file)
        self.assertEqual(content, read_content)

    def test_read_nonexistent(self):
        self.assertEqual(read_file("nonexistent.txt"), "")

    def test_clear_file(self):
        save_string_to_txt("Content", self.test_file)
        clear_file_content(self.test_file)
        self.assertEqual(read_file(self.test_file), "")

    def test_append_text(self):
        save_string_to_txt("Line 1", self.test_file)
        append_text_to_file("Line 2", self.test_file)
        content = read_file(self.test_file)
        self.assertIn("Line 1", content)
        self.assertIn("Line 2", content)

if __name__ == "__main__":
    unittest.main()
