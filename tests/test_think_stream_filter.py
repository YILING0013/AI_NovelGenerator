"""流式思考块过滤与非流式清洗必须对同一段模型输出给出一致正文。

同一段文本可能经两个公开入口返回：普通生成走
``BaseLLMClient._sanitize_text_content``，流式生成走 ``_ThinkStreamFilter``。
两者对未配对标签的处理不一致时，流式入口会丢掉标签之后的真实正文。
"""

import unittest

from backend.llm.base_client import BaseLLMClient, _ThinkStreamFilter


def _streamed(chunks: list[str], *, preserve_json_strings: bool = False) -> str:
    """按给定分片喂给流式过滤器，返回完整正文。"""
    stream_filter = _ThinkStreamFilter(preserve_json_strings=preserve_json_strings)
    return "".join(stream_filter.feed(chunk) for chunk in chunks) + stream_filter.finish()


class ThinkStreamFilterContractTest(unittest.TestCase):
    """流式正文必须等于同一段文本的非流式清洗结果。"""

    def test_closed_think_block_is_removed(self):
        """成对标签内的思考内容不进入正文，其余文字原样保留。"""
        raw = "雾从港口漫进街道。<think attribute=\"1\">先核对时间线。</think>林舟打开了来信。"
        expected = BaseLLMClient._sanitize_text_content(raw)
        self.assertEqual(expected, "雾从港口漫进街道。林舟打开了来信。")
        for chunks in ([raw], [raw[i:i + 1] for i in range(len(raw))]):
            with self.subTest(chunk_size=len(chunks)):
                self.assertEqual(_streamed(chunks), expected)

    def test_unpaired_close_tag_keeps_following_text(self):
        """只有结束标签时（开始标签已在提示词中），其后正文不能丢失。

        非流式清洗只删除这个标签；流式过滤曾把它当作待补全的标签一直留在缓冲里，
        收尾时整段丢弃，导致生成结果只剩标签之前的文字。
        """
        raw = "（推理片段）先确认时间线。</think>林舟把信纸压在台灯下，看清了落款。"
        expected = BaseLLMClient._sanitize_text_content(raw)
        self.assertEqual(expected, "（推理片段）先确认时间线。林舟把信纸压在台灯下，看清了落款。")
        for chunks in (
            [raw],
            [raw[i:i + 1] for i in range(len(raw))],
            ["（推理片段）先确认时间线。", "</think>", "林舟把信纸压在台灯下，看清了落款。"],
        ):
            with self.subTest(chunk_size=len(chunks)):
                self.assertEqual(_streamed(chunks), expected)

    def test_leading_close_tag_keeps_the_whole_body(self):
        """结束标签在最前面时，整章正文都必须保留。"""
        raw = "</think>林舟把信纸压在台灯下，看清了落款。"
        expected = BaseLLMClient._sanitize_text_content(raw)
        self.assertEqual(expected, "林舟把信纸压在台灯下，看清了落款。")
        self.assertEqual(_streamed([raw]), expected)
        self.assertEqual(_streamed([raw[i:i + 1] for i in range(len(raw))]), expected)

    def test_json_mode_keeps_tag_text_inside_string_values(self):
        """JSON 输出里字符串中的标签是字段内容，两个入口都不能删除。"""
        raw = '{"note": "不要输出  thinking 标记", "body": "正文"}'
        expected = BaseLLMClient._sanitize_text_content(raw, preserve_json_strings=True)
        self.assertEqual(expected, raw)
        self.assertEqual(_streamed([raw], preserve_json_strings=True), expected)


if __name__ == "__main__":
    unittest.main()
