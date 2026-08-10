import unittest

from text_processing import pre_process_text, split_text_into_chunks


DEFAULT_OPTIONS = {
    "remove_markdown": True,
    "remove_emoji": True,
    "no_urls": True,
    "no_line_breaks": True,
    "custom_keywords": "",
}


class TextProcessingTests(unittest.TestCase):
    def test_markdown_cleanup_preserves_medical_numbers_and_parentheses(self):
        source = """整体血糖控制良好（目标范围内占比80.7%），波动幅度（变异系数29.9%）。

**需要注意的问题（按优先级）**

**偏低/极低时段合计占18.5%**（极低<3.0 mmol/L占1.8%，偏低3.0-3.9 mmol/L占16.7%），最低值触及2.6 mmol/L。
**单次峰值偏高**：最高值达12.0 mmol/L。
标准差1.67 mmol/L。"""

        result = pre_process_text(source, DEFAULT_OPTIONS)

        for expected in ("80.7%", "29.9%", "18.5%", "3.0", "1.8%", "3.0-3.9", "16.7%", "2.6", "12.0", "1.67"):
            self.assertIn(expected, result)
        self.assertIn("（目标范围内占比80.7%）", result)
        self.assertNotIn("**", result)
        self.assertIn("\n\n需要注意的问题（按优先级）\n\n", result)

    def test_ordered_list_markers_are_only_removed_at_line_start(self):
        source = "1. 第一项为80.7%。\n2) 第二项为1.67 mmol/L。\n浓度29.9%。"

        result = pre_process_text(source, DEFAULT_OPTIONS)

        self.assertEqual(result, "第一项为80.7%。\n\n第二项为1.67 mmol/L。\n\n浓度29.9%。")

    def test_html_entities_and_block_structure_become_plain_text(self):
        source = "<p>目标值 &lt; 7 &amp; 状态良好。</p><p>第二段<br>继续。</p><script>不要朗读</script>"

        result = pre_process_text(source, DEFAULT_OPTIONS)

        self.assertEqual(result, "目标值 < 7 & 状态良好。\n\n第二段继续。")

    def test_urls_emoji_and_empty_brackets_are_removed_without_losing_punctuation(self):
        source = "说明😀：访问（https://example.com/a?q=1），然后继续。✅"

        result = pre_process_text(source, DEFAULT_OPTIONS)

        self.assertEqual(result, "说明：访问，然后继续。")

    def test_soft_wraps_merge_but_sentence_lines_remain_paragraphs(self):
        source = "第一段第一行\n仍是第一段。\n第二段已经结束。\n第三段。\n\n第四段\n继续。"

        result = pre_process_text(source, DEFAULT_OPTIONS)

        self.assertEqual(
            result,
            "第一段第一行仍是第一段。\n\n第二段已经结束。\n\n第三段。\n\n第四段继续。",
        )

    def test_line_boundaries_remain_when_soft_wrap_merge_is_disabled(self):
        options = {**DEFAULT_OPTIONS, "no_line_breaks": False}

        result = pre_process_text("第一行\n第二行", options)

        self.assertEqual(result, "第一行\n\n第二行")

    def test_chunking_respects_paragraphs_and_decimal_points(self):
        text = "目标范围内占比80.7%，结果稳定。\n\n变异系数29.9%，标准差1.67 mmol/L。"

        chunks = split_text_into_chunks(text, max_chunk_len=100)

        self.assertEqual(
            chunks,
            ["目标范围内占比80.7%，结果稳定。\n\n变异系数29.9%，标准差1.67 mmol/L。"],
        )

    def test_chunking_enforces_maximum_length_for_unbroken_text(self):
        chunks = split_text_into_chunks("一" * 25, max_chunk_len=10)

        self.assertEqual([len(chunk) for chunk in chunks], [10, 10, 5])

    def test_chunking_keeps_spaces_between_english_sentences(self):
        chunks = split_text_into_chunks(
            "First sentence. Second sentence. Third sentence.",
            max_chunk_len=100,
        )

        self.assertEqual(
            chunks,
            ["First sentence. Second sentence. Third sentence."],
        )

    def test_oversized_english_prefers_word_boundaries(self):
        chunks = split_text_into_chunks(
            "alpha beta gamma delta epsilon zeta eta theta",
            max_chunk_len=18,
        )

        self.assertTrue(all(len(chunk) <= 18 for chunk in chunks))
        self.assertEqual(" ".join(chunks), "alpha beta gamma delta epsilon zeta eta theta")

    def test_forced_hard_split_does_not_break_numeric_expression(self):
        source = "一" * 8 + "80.7%" + "二" * 12

        chunks = split_text_into_chunks(source, max_chunk_len=10)

        self.assertEqual("".join(chunks), source)
        self.assertTrue(any("80.7%" in chunk for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
