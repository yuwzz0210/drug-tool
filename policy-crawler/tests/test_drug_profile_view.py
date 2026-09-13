# -*- coding: utf-8 -*-
"""drug_profile v1 视图的取数口径测试（最新值/派生/聚合计数）。"""
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import DRUG_SCHEMA, SQLITE_SCHEMA  # noqa: E402


class TestDrugProfileView(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self._tmp = tmp.name
        self.db = sqlite3.connect(self._tmp)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SQLITE_SCHEMA)
        self.db.executescript(DRUG_SCHEMA)
        db = self.db
        db.execute("INSERT INTO drug_molecule (molecule_id, generic_name) "
                   "VALUES (1, '贝福替尼'), (2, '阿法替尼')")
        db.execute("""INSERT INTO drug_product
            (product_id, molecule_id, generic_name, dosage_form,
             specification, manufacturer_norm)
            VALUES (1,1,'贝福替尼胶囊','胶囊剂','25mg','甲厂'),
                   (2,1,'贝福替尼胶囊','胶囊剂','50mg','乙厂'),
                   (3,2,'阿法替尼片','片剂','40mg','丙厂')""")
        db.execute("""INSERT INTO drug_registration
            (registration_id, product_id, approval_number, status, holder,
             registration_date)
            VALUES (1,1,'国药准字H20230015','有效','甲厂','2023-01-01'),
                   (2,2,'国药准字H20230016','有效','乙厂','2023-02-01'),
                   (3,3,'国药准字J20170029','有效','丙厂','2017-02-01')""")
        db.execute("""INSERT INTO drug_indication (product_id, indication_text)
            VALUES (1,'适应症A'),(1,'适应症B')""")
        db.execute("""INSERT INTO drug_leaflet
            (product_id, approval_number, catalog_rid, pdf_url, usage_dosage,
             updated_at)
            VALUES (1,'国药准字H20230015','r1','http://x/1.pdf','旧用法',
                    '2024-01-01 00:00:00'),
                   (1,'国药准字H20230015','r2','http://x/1.pdf','新用法',
                    '2025-01-01 00:00:00')""")
        db.execute("""INSERT INTO price_history
            (product_id, price_type, price, region, effective_date)
            VALUES (1,'挂网',10,'湖南','2025-01-01'),
                   (1,'挂网',8,'湖南','2025-06-01')""")
        db.execute("""INSERT INTO procurement_result
            (batch, batch_seq, generic_name, spec_pack, supplier, product_id)
            VALUES ('GY-YD2026-1','1','贝福替尼胶囊','25mg','甲厂',1),
                   ('GY-YD2025-2','2','贝福替尼胶囊','25mg','甲厂',1)""")
        db.execute("""INSERT INTO policies (id, title, source_url)
            VALUES (1,'关于贝福替尼的政策','http://p/1')""")
        db.execute("""INSERT INTO policy_drug_relation
            (policy_id, product_id, relation_type) VALUES (1,1,'相关')""")
        db.execute("""INSERT INTO insurance_catalog (catalog_id, version_name)
            VALUES (1,'2025版')""")
        db.execute("""INSERT INTO drug_insurance_entry
            (product_id, catalog_id, region, category, insurance_code)
            VALUES (1,1,'国家','乙类','XA01')""")
        db.commit()

    def tearDown(self):
        self.db.close()
        os.unlink(self._tmp)

    def _row(self, approval):
        return self.db.execute(
            "SELECT * FROM drug_profile WHERE approval_number=?",
            (approval,)).fetchone()

    def test_latest_and_derived_fields(self):
        r = self._row("国药准字H20230015")
        self.assertEqual(r["usage_dosage"], "新用法")           # latest leaflet
        self.assertEqual(r["latest_listed_price"], 8)             # latest price
        self.assertEqual(r["vbp_event_count"], 2)                 # 两个批次
        self.assertEqual(r["policy_count"], 1)
        self.assertEqual(r["insurance_category"], "乙类")
        self.assertEqual(r["indication_count"], 2)
        self.assertEqual(r["followers_count"], 2)                 # 甲乙两厂
        self.assertEqual(r["is_exclusive"], 0)                    # not exclusive
        self.assertEqual(r["origin_type"], "国产")

    def test_import_origin_and_exclusive(self):
        r = self._row("国药准字J20170029")
        self.assertEqual(r["origin_type"], "进口")
        self.assertEqual(r["followers_count"], 1)
        self.assertEqual(r["is_exclusive"], 1)


if __name__ == "__main__":
    unittest.main()
