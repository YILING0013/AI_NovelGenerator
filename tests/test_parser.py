import unittest
from chapter_directory_parser import parse_chapter_blueprint

class TestChapterParser(unittest.TestCase):
    def test_parse_standard_format(self):
        text = """
Chapter 1 - The Beginning
Chapter Position: Intro
Core Purpose: Introduce protagonist
Suspense Density: Normal
Foreshadowing: The old pendant
Plot Twist Level: 1/5
Chapter Summary: The hero leaves home.
"""
        results = parse_chapter_blueprint(text)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["chapter_number"], 1)
        self.assertEqual(results[0]["chapter_title"], "The Beginning")
        self.assertEqual(results[0]["chapter_role"], "Intro")

    def test_parse_variation_format(self):
        text = """
Chapter 2 - The Discovery
Chapter Position: Middle
Core Purpose: Plot thickening
Suspense Density: High
Foreshadowing: The mysterious letter
Plot Twist Level: 3/5
Chapter Summary: They found the secret passage.
"""
        results = parse_chapter_blueprint(text)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["chapter_number"], 2)
        self.assertEqual(results[0]["chapter_title"], "The Discovery")
        self.assertEqual(results[0]["chapter_role"], "Middle")

if __name__ == "__main__":
    unittest.main()
