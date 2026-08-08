import os
import tempfile
import unittest

from models import Policy
from pipeline import Pipeline
from store import SqliteStore


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "crawler.db")
        self.store = SqliteStore(self.db_path)
        self.pipeline = Pipeline(self.store)

    def make_policy(self, url, title="测试政策", content="正文"):
        return Policy(
            title=title,
            source_url=url,
            content=content,
            issuing_authority="测试机构",
            publish_date="2026-08-08",
        )

    def test_insert_new_policies(self):
        result = self.pipeline.process([
            self.make_policy("https://x.gov.cn/a.html"),
            self.make_policy("https://x.gov.cn/b.html"),
        ])
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["new_added"], 2)

    def test_duplicate_url_skipped(self):
        self.pipeline.process([self.make_policy("https://x.gov.cn/a.html")])
        result = self.pipeline.process([self.make_policy("https://x.gov.cn/a.html", content="更新后正文")])
        self.assertEqual(result["new_added"], 0)
        stored = self.store.get_by_url("https://x.gov.cn/a.html")
        self.assertIn("更新后正文", stored["content"])

    def test_pii_scrubbed_before_store(self):
        self.pipeline.process([
            self.make_policy("https://x.gov.cn/a.html", content="身份证号：110101199001011234，手机：13812345678")
        ])
        stored = self.store.get_by_url("https://x.gov.cn/a.html")
        self.assertNotIn("110101199001011234", stored["content"])
        self.assertNotIn("13812345678", stored["content"])

    def test_crawler_log_recorded(self):
        self.pipeline.process([self.make_policy("https://x.gov.cn/a.html")])
        logs = self.store.list_logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["new_added"], 1)
        self.assertEqual(logs[0]["total_fetched"], 1)

    def test_enrich_pdf_attachment(self):
        item = Policy(
            title="带附件政策",
            source_url="https://x.gov.cn/a.html",
            content="简短正文",
            attachment_links='[{"url":"https://x.gov.cn/a.pdf","file":"C:/tmp/a.pdf"}]',
        )
        self.pipeline.enrich_content(
            item,
            pdf_extractor=PDFStub("PDF提取内容"),
        )
        self.assertIn("PDF提取内容", item.content)

    def test_enrich_ocr_when_still_short(self):
        item = Policy(
            title="图片政策",
            source_url="https://x.gov.cn/b.html",
            content="短",
            images='[{"file":"C:/tmp/a.png"}]',
        )
        self.pipeline.enrich_content(item, ocr_extractor=OCRStub("OCR识别文本"))
        self.assertIn("OCR识别文本", item.content)

    def test_no_enrich_when_content_long(self):
        item = Policy(
            title="长文政策",
            source_url="https://x.gov.cn/c.html",
            content="长" * 200,
            attachment_links='[{"url":"https://x.gov.cn/a.pdf","file":"C:/tmp/a.pdf"}]',
        )
        self.pipeline.enrich_content(item, pdf_extractor=PDFStub("PDF提取内容"))
        self.assertNotIn("PDF提取内容", item.content)

    def test_validity_status_auto_updated_on_ingest(self):
        item = Policy(
            title="关于废止药品追溯管理办法的通知",
            source_url="https://x.gov.cn/d.html",
            content="废止",
            publish_date="2026-01-01",
        )
        self.pipeline.process([item])
        stored = self.store.get_by_url("https://x.gov.cn/d.html")
        self.assertEqual(stored["validity_status"], "废止")


class PDFStub:
    def __init__(self, text):
        self.text = text

    def extract(self, src):
        return self.text


class OCRStub:
    def __init__(self, text):
        self.text = text

    def extract(self, src):
        return self.text


if __name__ == "__main__":
    unittest.main()
