# -*- coding: utf-8 -*-
"""医保目录导入器测试（真实官网 HTML 夹具 + 官方 PDF 切片夹具）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from drugstore import DrugStore  # noqa: E402
from importers import insurance_catalog as ic  # noqa: E402
from models import DrugProduct  # noqa: E402
from store import SqliteStore  # noqa: E402


FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def _try_import(name):
    try:
        __import__(name)
        return True
    except Exception:
        return False


def _read(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8", errors="replace") as f:
        return f.read()


class TestCatalogDiscovery(unittest.TestCase):
    def test_find_catalog_notice(self):
        title, url = ic.find_catalog_notice(_read("nhsa_catalog_list.html"))
        self.assertIn("药品目录", title)
        self.assertNotIn("商业健康保险", title)
        self.assertIn("art_104_18970.html", url)

    def test_find_catalog_attachment(self):
        result = ic.find_catalog_attachment(_read("nhsa_catalog_notice.html"))
        self.assertIsNotNone(result)
        label, url = result
        self.assertIn("药品目录", label)
        self.assertIn("downfile.jsp", url)


@unittest.skipUnless(_try_import("pdfplumber"), "pdfplumber 未安装")
class TestCatalogPdf(unittest.TestCase):
    def test_parse_catalog_sample(self):
        rows = ic.parse_catalog_pdf(os.path.join(FIXTURES, "nhsa_catalog_sample.pdf"))
        self.assertGreater(len(rows), 20)
        names = {r["name"] for r in rows}
        self.assertIn("兰索拉唑", names)          # 西药部分
        self.assertTrue(any("双黄连" in n for n in names))  # 中成药部分（多药名同行）
        self.assertIn("芦比前列酮软胶囊", names)   # 谈判药品部分
        sections = {r["section"] for r in rows}
        self.assertTrue({"西药", "中成药", "谈判"} <= sections)
        # 谈判药品应有支付标准与协议有效期
        negotiable = [r for r in rows if r["section"] == "谈判" and r["name"] == "芦比前列酮软胶囊"]
        self.assertTrue(negotiable)
        self.assertIn("元", negotiable[0]["pay_standard"])
        self.assertIn("2026年1月1日", negotiable[0]["valid_until"])

    def test_parse_valid_range(self):
        self.assertEqual(
            ic._parse_valid_range("2026年1月1日至2027年12月31日"),
            ("2026-01-01", "2027-12-31"),
        )
        self.assertEqual(ic._parse_valid_range("无"), ("", ""))


@unittest.skipUnless(_try_import("pdfplumber"), "pdfplumber 未安装")
class TestCatalogImport(unittest.TestCase):
    def setUp(self):
        self.store = SqliteStore(":memory:")
        self.drugs = DrugStore.from_store(self.store)
        for gn in ("兰索拉唑", "双黄连注射液", "司美格鲁肽"):
            self.drugs.upsert_product(DrugProduct(generic_name=gn))

    def test_import_catalog_matches_products(self):
        rows = ic.parse_catalog_pdf(os.path.join(FIXTURES, "nhsa_catalog_sample.pdf"))
        report = ic.import_catalog(self.drugs, rows, "国家医保药品目录（2025年）")
        self.assertEqual(report["catalog_id"], 1)
        self.assertEqual(report["parsed_entries"], len(rows))
        self.assertGreater(report["matched_products"], 0)
        # 兰索拉唑应命中并写入医保条目
        _, prows = self.drugs.fetch_products(keyword="兰索拉唑")
        self.assertEqual(len(prows), 1)
        detail = self.drugs.fetch_product_detail(prows[0]["product_id"])
        self.assertEqual(detail["insurance"][0]["category"], "乙类")
        # 全量条目已入库
        cnt = self.store._conn.execute(
            "SELECT COUNT(*) FROM insurance_catalog_entry").fetchone()[0]
        self.assertEqual(cnt, len(rows))
        # 报告含未匹配名单
        self.assertIn("unmatched_names", report)

    def test_name_matching_precision(self):
        self.drugs.upsert_product(DrugProduct(generic_name="二甲双胍"))
        self.drugs.upsert_product(DrugProduct(generic_name="阿美替尼"))
        self.drugs.upsert_product(DrugProduct(generic_name="艾美赛珠单抗"))
        lookup = ic.build_product_lookup(self.drugs)
        by_gn = {pid: keys for pid, keys in lookup}
        # 复方药不得命中单方品种
        self.assertEqual(ic._match_products(lookup, {"name": "西格列汀二甲双胍Ⅰ\n西格列汀二甲双胍Ⅱ"}), [])
        # 单方精确命中
        hits = ic._match_products(lookup, {"name": "二甲双胍"})
        self.assertEqual(len(hits), 1)
        # 盐基前缀归一：甲磺酸阿美替尼片 → 阿美替尼
        hits = ic._match_products(lookup, {"name": "甲磺酸阿美替尼片"})
        self.assertEqual(len(hits), 1)
        # 剂型后缀归一：艾美赛珠单抗注射液 → 艾美赛珠单抗
        hits = ic._match_products(lookup, {"name": "艾美赛珠单抗注射液"})
        self.assertEqual(len(hits), 1)

if __name__ == "__main__":
    unittest.main()
