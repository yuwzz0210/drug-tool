# -*- coding: utf-8 -*-
"""NMPA 药品注册采集器测试（解析 + 导入，不联网）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.nmpa_drugs import import_registrations, parse_registrations  # noqa: E402
from collectors.nmpa_browser import parse_captured  # noqa: E402
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


class TestParseCaptured(unittest.TestCase):
    def test_parse_list_and_detail_dedup(self):
        captured = [
            {"kind": "list", "url": "x/search", "body": {"code": 200, "data": {"total": 1, "list": [
                {"f0": "国药准字H20200001", "f1": "阿托伐他汀钙片",
                 "f2": "天地恒一制药股份有限公司", "f3": "86900000000001", "f4": "dk1"},
            ]}}},
            {"kind": "detail", "url": "x/queryDetail", "body": {"code": 200, "data": {
                "isMark": False,
                "detail": {
                    "f0": "国药准字H20200001", "f1": "阿托伐他汀钙片", "f3": "立普妥",
                    "f4": "片剂", "f5": "20mg", "f6": "某上市许可持有人",
                    "f8": "天地恒一制药股份有限公司", "f9": "2020-01-01", "f11": "化学药品",
                },
            }}},
        ]
        records = parse_captured(captured)
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertEqual(r["generic_name"], "阿托伐他汀钙片")
        self.assertEqual(r["dosage_form"], "片剂")
        self.assertEqual(r["specification"], "20mg")
        self.assertEqual(r["manufacturer"], "天地恒一制药股份有限公司")
        self.assertEqual(r["approval_date"], "2020-01-01")

    def test_parse_detail_wrapped_in_data_detail(self):
        """queryDetail 真实结构：{code, data:{isMark, detail:{f0..f15}}}。"""
        captured = [
            {"kind": "list", "url": "x/search", "body": {"code": 200, "data": {"list": [
                {"f0": "国药准字H20200001", "f1": "阿托伐他汀钙片", "f2": "某企业",
                 "f3": "86900000000001", "f4": "dk1"},
            ]}}},
            {"kind": "detail", "url": "x/queryDetail", "body": {"code": 200, "data": {
                "isMark": False,
                "detail": {"f0": "国药准字H20200001", "f1": "阿托伐他汀钙片",
                           "f4": "片剂", "f5": "20mg", "f6": "某持有人",
                           "f8": "某企业", "f9": "2020-01-01", "f11": "化学药品"},
            }}},
        ]
        records = parse_captured(captured)
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertEqual(r["dosage_form"], "片剂")
        self.assertEqual(r["specification"], "20mg")
        self.assertEqual(r["holder"], "某持有人")

    def test_skip_bad_records(self):
        captured = [
            {"kind": "list", "url": "x/search", "body": {"code": 200, "data": {"list": [
                {"f0": "", "f1": "无名"},
                {"f0": "国药准字H20200002", "f1": "阿莫西林"},
            ]}}},
        ]
        records = parse_captured(captured)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["approval_number"], "国药准字H20200002")


if __name__ == "__main__":
    unittest.main()
