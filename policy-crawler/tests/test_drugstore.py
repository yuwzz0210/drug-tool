# -*- coding: utf-8 -*-
"""药品域存储与导入测试。"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

from drug_queries import drug_detail, drug_stats, list_drugs  # noqa: E402
from drugstore import DrugStore  # noqa: E402
from import_drugs import guess_category, import_file, map_record  # noqa: E402
from models import DrugProduct, DrugRegistration  # noqa: E402
from store import SqliteStore  # noqa: E402


class TestDrugStore(unittest.TestCase):
    def setUp(self):
        self.store = SqliteStore(":memory:")
        self.drugs = DrugStore.from_store(self.store)

    def test_upsert_product_dedup_by_business_key(self):
        p1 = DrugProduct(generic_name="阿托伐他汀钙片", dosage_form="片剂",
                         specification="20mg", manufacturer_norm="辉瑞制药")
        pid1 = self.drugs.upsert_product(p1)
        pid2 = self.drugs.upsert_product(DrugProduct(
            generic_name="阿托伐他汀钙片", dosage_form="片剂",
            specification="20mg", manufacturer_norm="辉瑞制药",
            trade_name="立普妥", is_verified=True))
        self.assertEqual(pid1, pid2)
        # 同一通用名不同厂家 → 新品种
        pid3 = self.drugs.upsert_product(DrugProduct(
            generic_name="阿托伐他汀钙片", dosage_form="片剂",
            specification="20mg", manufacturer_norm="齐鲁制药"))
        self.assertNotEqual(pid1, pid3)

    def test_registration_multiple_per_product(self):
        pid = self.drugs.upsert_product(DrugProduct(generic_name="二甲双胍"))
        self.drugs.upsert_registration(DrugRegistration(product_id=pid, approval_number="国药准字H20110000"))
        self.drugs.upsert_registration(DrugRegistration(product_id=pid, approval_number="国药准字H20110001"))
        detail = drug_detail(self.drugs, pid)
        self.assertEqual(len(detail["registrations"]), 2)

    def test_replace_indications_and_mechanisms(self):
        pid = self.drugs.upsert_product(DrugProduct(generic_name="奥希替尼"))
        self.drugs.replace_indications(pid, ["非小细胞肺癌", "EGFR突变阳性"])
        self.drugs.replace_mechanisms(pid, ["EGFR-TKI，不可逆抑制EGFR激酶活性"])
        self.drugs.replace_insurance_entries(pid, [{"category": "谈判药", "price": "5580"}])
        detail = drug_detail(self.drugs, pid)
        self.assertEqual([i["indication_text"] for i in detail["indications"]],
                         ["非小细胞肺癌", "EGFR突变阳性"])
        self.assertEqual(detail["insurance"][0]["category"], "谈判药")
        self.assertEqual(detail["insurance"][0]["price"], "5580")

    def test_guess_category(self):
        self.assertEqual(guess_category("谈判药品"), "谈判药")
        self.assertEqual(guess_category("甲类"), "甲类")
        self.assertEqual(guess_category("乙类"), "乙类")
        self.assertEqual(guess_category("否"), "非医保")
        self.assertEqual(guess_category(""), "")

    def test_import_file_end_to_end(self):
        records = [
            {
                "gn": "注射用曲妥珠单抗", "bn": "赫赛汀", "form": "注射剂",
                "spec": "440mg/瓶", "mfr": "上海罗氏制药",
                "appr": "国药准字S20120000/国药准字S20120001",
                "adate": "2020-05-01", "ind": "HER2阳性乳腺癌；HER2阳性胃癌",
                "mech": "HER2靶向单克隆抗体",
                "ins": "谈判药品", "paystd": "限HER2阳性",
                "price": 5500, "year": 2020, "gen": "第一代",
                "area": "肿瘤", "disease": "乳腺癌",
            },
            {"gn": "阿莫西林胶囊", "form": "胶囊剂", "spec": "0.25g",
             "mfr": "石药集团", "ins": "甲类", "price": 12.5},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            jpath = os.path.join(tmp, "药品数据库.json")
            with open(jpath, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False)
            dbpath = os.path.join(tmp, "test.db")
            report = import_file(dbpath, jpath, catalog_version="2025版国家医保目录")
            self.assertEqual(report["total_records"], 2)
            self.assertEqual(report["products"], 2)
            self.assertEqual(report["registrations"], 2)
            self.assertEqual(report["indications"], 2)  # 乳腺癌 + 胃癌
            self.assertEqual(report["mechanisms"], 1)
            self.assertEqual(report["insurance_entries"], 2)

            store = DrugStore.from_path(dbpath)
            total, rows = store.fetch_products()
            self.assertEqual(total, 2)
            by_name = {r["generic_name"]: r for r in rows}
            self.assertEqual(by_name["注射用曲妥珠单抗"]["trade_name"], "赫赛汀")
            detail = drug_detail(store, by_name["注射用曲妥珠单抗"]["product_id"])
            self.assertEqual(len(detail["indications"]), 2)
            self.assertEqual(len(detail["registrations"]), 2)
            self.assertEqual(detail["insurance"][0]["category"], "谈判药")
            extra = json.loads(detail["extra_data"])
            self.assertEqual(extra["disease"], "乳腺癌")
            stats = drug_stats(store)
            self.assertEqual(stats["drugs_total"], 2)
            self.assertEqual(stats["insurance_entries"], 2)
            store.close()

    def test_list_drugs_search(self):
        self.drugs.upsert_product(DrugProduct(generic_name="恩曲替尼", trade_name="罗圣全"))
        self.drugs.upsert_product(DrugProduct(generic_name="拉罗替尼"))
        result = list_drugs(self.drugs, keyword="恩曲")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["generic_name"], "恩曲替尼")


if __name__ == "__main__":
    unittest.main()
