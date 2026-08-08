import unittest

from sanitize import clean_html_text, scrub_pii, extract_doc_number


class TestSanitize(unittest.TestCase):
    def test_clean_html_text_keeps_paragraph_text(self):
        html = "<div class='content'><p>第一段内容。</p><p>第二段内容。</p></div>"
        text = clean_html_text(html)
        self.assertIn("第一段内容。", text)
        self.assertIn("第二段内容。", text)

    def test_clean_html_text_strips_tags(self):
        html = "<p>带<b>加粗</b>与<a href='x'>链接</a>的正文</p>"
        text = clean_html_text(html)
        self.assertNotIn("<b>", text)
        self.assertIn("加粗", text)

    def test_scrub_pii_removes_id_card(self):
        text = "身份证号：110101199001011234 已登记"
        out = scrub_pii(text)
        self.assertNotIn("110101199001011234", out)
        self.assertIn("已脱敏", out)

    def test_scrub_pii_removes_mobile(self):
        text = "联系电话 13812345678 请查收"
        out = scrub_pii(text)
        self.assertNotIn("13812345678", out)

    def test_scrub_pii_does_not_touch_landline(self):
        text = "电话 010-12345678"
        out = scrub_pii(text)
        self.assertIn("010-12345678", out)

    def test_extract_doc_number(self):
        text = "现发布《指导原则》。国药监药管〔2026〕18号，自发布之日起施行。"
        self.assertEqual(extract_doc_number(text), "国药监药管〔2026〕18号")


if __name__ == "__main__":
    unittest.main()
