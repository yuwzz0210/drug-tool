import contextlib
import io
import json
import os
import tempfile
import unittest

from main import main, save_to_json
from models import Policy


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class TestMainFileMode(unittest.TestCase):
    def test_crawl_file_mode_parses_local_list(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main([
                "crawl", "--source", "nmpa", "--file",
                os.path.join(FIXTURES, "nmpa_list.html"),
            ])
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn("药品经营质量管理规范现场检查指导原则", text)
        self.assertIn("药品追溯体系建设", text)


class TestSaveToJson(unittest.TestCase):
    """JSON 输出：规格字段、增量合并去重、稳定 id、倒序排列。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "policies.json")

    def test_write_schema_fields(self):
        save_to_json([
            Policy(title="关于药品追溯体系建设的通知", source_url="https://a/1.html",
                   publish_date="2026-08-01", content="x" * 300,
                   issuing_authority="国家药品监督管理局"),
        ], self.path)
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data), 1)
        r = data[0]
        self.assertEqual(r["title"], "关于药品追溯体系建设的通知")
        self.assertEqual(r["url"], "https://a/1.html")
        self.assertEqual(r["publish_date"], "2026-08-01")
        self.assertEqual(len(r["content_preview"]), 200)
        self.assertEqual(r["source_site"], "国家药品监督管理局")
        self.assertTrue(r["id"])
        self.assertTrue(r["created_at"])

    def test_incremental_merge_by_url_keeps_id(self):
        save_to_json([
            Policy(title="旧标题", source_url="https://a/1.html",
                   publish_date="2026-08-01", content="旧内容", issuing_authority="A局"),
        ], self.path)
        with open(self.path, encoding="utf-8") as f:
            old_id = json.load(f)[0]["id"]
        save_to_json([
            Policy(title="新标题", source_url="https://a/1.html",
                   publish_date="2026-08-02", content="新内容", issuing_authority="A局"),
            Policy(title="新增政策", source_url="https://a/2.html",
                   publish_date="2026-08-03", content="新条目", issuing_authority="B局"),
        ], self.path)
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data), 2)
        by_url = {r["url"]: r for r in data}
        self.assertEqual(by_url["https://a/1.html"]["title"], "新标题")
        self.assertEqual(by_url["https://a/1.html"]["id"], old_id)
        self.assertNotEqual(by_url["https://a/2.html"]["id"], old_id)
        self.assertEqual([r["url"] for r in data], ["https://a/2.html", "https://a/1.html"])

    def test_corrupt_existing_file_is_replaced(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("不是JSON")
        save_to_json([
            Policy(title="有效数据", source_url="https://a/3.html", content="c"),
        ], self.path)
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data), 1)

    def test_cli_output_writes_json_in_demo_mode(self):
        code = main([
            "crawl", "--source", "nmpa", "--demo",
            "--output", self.path,
        ])
        self.assertEqual(code, 0)
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertGreaterEqual(len(data), 1)
        self.assertIn("url", data[0])


if __name__ == "__main__":
    unittest.main()
