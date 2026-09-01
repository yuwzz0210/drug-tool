# -*- coding: utf-8 -*-
"""价格时序 + 市场层测试。"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

from drugstore import DrugStore  # noqa: E402
from import_price_market import import_file  # noqa: E402
from models import DrugMarket, DrugMolecule, DrugProduct, DrugRegistration, PriceRecord  # noqa: E402
from store import SqliteStore  # noqa: E402


class TestPriceMarket(unittest.TestCase):
    def setUp(self):
        self.store = SqliteStore(":memory:")
        self.drugs = DrugStore.from_store(self.store)
        pid = self.drugs.upsert_product(DrugProduct(generic_name="奥希替尼片", dosage_form="片剂",
                                                    specification="80mg", manufacturer_norm="阿斯利康"))
        self.drugs.upsert_registration(DrugRegistration(product_id=pid, approval_number="国药准字J20170000"))
        self.pid = pid

    def test_molecule_columns_exist(self):
        cols = [r[1] for r in self.drugs._conn.execute("PRAGMA table_info(drug_molecule)").fetchall()]
        for col in ("guideline_level", "route", "cold_chain", "patent_expiry",
                    "iteration_chain", "generation", "extra_indications", "reviewed_at"):
            self.assertIn(col, cols)

    def test_price_upsert_idempotent(self):
        rec = PriceRecord(product_id=self.pid, price=5580.0, price_type="集采中选",
                          effective_date="2026-09-01", source_url="https://x", reviewed_by="张三")
        self.drugs.upsert_price(rec)
        self.drugs.upsert_price(rec)
        rows = self.drugs.get_price_history(self.pid)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["price"], 5580.0)

    def test_market_upsert(self):
        mid = self.drugs.upsert_molecule(DrugMolecule(generic_name="奥希替尼"))
        rec = DrugMarket(molecule_id=mid, region="全国", sales_year=2026,
                         patient_count=100000, diagnosis_rate=0.5,
                         prescription_penetration=0.3, confidence="中")
        self.drugs.upsert_market(rec)
        rec2 = DrugMarket(molecule_id=mid, region="全国", sales_year=2026,
                          patient_count=120000, diagnosis_rate=0.6,
                          prescription_penetration=0.35, confidence="高")
        self.drugs.upsert_market(rec2)
        rows = self.drugs.fetch_market(mid)
        self.assertEqual(len(rows), 1)  # 同分子/区域/年份 → 覆盖更新
        self.assertEqual(rows[0]["patient_count"], 120000)

    def test_import_file(self):
        payload = {
            "prices": [
                {"approval_number": "国药准字J20170000", "price": 5580,
                 "price_type": "集采中选", "effective_date": "2026-09-01"},
                {"approval_number": "不存在", "price": 1},
            ],
            "markets": [
                {"generic_name": "奥希替尼片", "region": "湖南", "sales_year": 2026,
                 "patient_count": 20000, "diagnosis_rate": 0.4,
                 "prescription_penetration": 0.5, "confidence": "中"},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            dbpath = os.path.join(tmp, "t.db")
            pre = DrugStore.from_path(dbpath)
            pid = pre.upsert_product(DrugProduct(generic_name="奥希替尼片", dosage_form="片剂",
                                                 specification="80mg", manufacturer_norm="阿斯利康"))
            pre.upsert_registration(DrugRegistration(product_id=pid, approval_number="国药准字J20170000"))
            pre.close()
            jp = os.path.join(tmp, "in.json")
            with open(jp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            report = import_file(dbpath, jp)
        self.assertEqual(report["prices"], 1)
        self.assertEqual(report["prices_skipped"], 1)
        self.assertEqual(report["markets"], 1)


if __name__ == "__main__":
    unittest.main()
