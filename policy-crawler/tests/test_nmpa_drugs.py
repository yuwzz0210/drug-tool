# -*- coding: utf-8 -*-
"""NMPA 药品注册采集器测试（解析 + 导入，不联网）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.nmpa_drugs import import_registrations, parse_registrations  # noqa: E402
from drugstore import DrugStore  # noqa: E402
from store import SqliteStore  # noqa: E402


class TestParseRegistrations(unittest.TestCase):
    def test_parse_data_list_shape(self):
        payload = {"data": {"list": [
            {"通用名": "阿托伐他汀钙片", "商品名": "立普妥", "批准文号": "国药准字J20180000",
             "剂型": "片剂", "规格": "20mg", "生产单位": "辉瑞制药",
             "批准日期": "2018-05-01", "药品类型": "化学药品"},
            {"通用名称": "盐酸二甲双胍片", "生产企业": "施贵宝", "注册证号": "国药准字H20190000"},
        ]}}
        records = parse_registrations(payload)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["generic_name"], "阿托伐他汀钙片")
        self.assertEqual(records[0]["trade_name"], "立普妥")
        self.assertEqual(records[0]["approval_number"], "国药准字J20180000")
        self.assertEqual(records[0]["manufacturer"], "辉瑞制药")
        self.assertEqual(records[1]["approval_number"], "国药准字H20190000")

    def test_parse_plain_list_and_skip_invalid(self):
        records = parse_registrations([
            {"产品名称": "奥希替尼", "批准文号": "国药准字J20170000"},
            {"not_a_record": True},
        ])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["generic_name"], "奥希替尼")

    def test_parse_bad_structure(self):
        with self.assertRaises(ValueError):
            parse_registrations({"foo": "bar"})


class TestImportRegistrations(unittest.TestCase):
    def setUp(self):
        self.store = SqliteStore(":memory:")
        self.drugs = DrugStore.from_store(self.store)

    def test_import_and_dedup(self):
        records = [
            {"generic_name": "阿托伐他汀钙片", "dosage_form": "片剂", "specification": "20mg",
             "manufacturer": "辉瑞制药", "trade_name": "立普妥",
             "approval_number": "国药准字J20180000", "approval_date": "2018-05-01",
             "drug_type": "化学药品", "is_otc": False},
        ]
        r1 = import_registrations(self.drugs, records)
        r2 = import_registrations(self.drugs, records)
        self.assertEqual(r1["products"], 1)
        self.assertEqual(r2["products"], 1)  # 同品种不重复
        self.assertEqual(r2["registrations"], 1)
        total, rows = self.drugs.fetch_products(keyword="阿托伐他汀")
        self.assertEqual(total, 1)
        detail = self.drugs.fetch_product_detail(rows[0]["product_id"])
        self.assertEqual(detail["registrations"][0]["approval_number"], "国药准字J20180000")


if __name__ == "__main__":
    unittest.main()
