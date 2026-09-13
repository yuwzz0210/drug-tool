# -*- coding: utf-8 -*-
"""医保维度扩展（地区/编码唯一键）测试。"""
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import DRUG_SCHEMA  # noqa: E402


class TestInsuranceDimensions(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self._tmp = tmp.name
        self.db = sqlite3.connect(self._tmp)
        self.db.executescript(DRUG_SCHEMA)
        self.db.execute(
            "INSERT INTO insurance_catalog (version_name) VALUES ('2025版')")
        self.db.execute(
            """INSERT INTO drug_product (product_id, generic_name,
               manufacturer_norm) VALUES (1, '贝福替尼胶囊', '贝达药业')""")
        self.db.commit()

    def tearDown(self):
        self.db.close()
        os.unlink(self._tmp)

    def test_region_versions_and_unique_code(self):
        ins = """INSERT INTO drug_insurance_entry
                 (product_id, catalog_id, region, insurance_code, category,
                  reimbursement_ratio, supplement_status)
                 VALUES (?,?,?,?,?,?,?)"""
        self.db.execute(ins, (1, 1, "国家", "XA01", "乙类", "", ""))
        # same catalog/product but a province row is allowed
        self.db.execute(ins, (1, 1, "湖南", "XA01", "乙类", "自付10%", "省级增补"))
        self.db.commit()
        rows = self.db.execute(
            "SELECT region, reimbursement_ratio, supplement_status "
            "FROM drug_insurance_entry ORDER BY region").fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], ("国家", "", ""))
        self.assertEqual(rows[1], ("湖南", "自付10%", "省级增补"))
        # 同一编码可对应多个目录条目（如同一药物不同剂型），不设唯一约束；
        # 幂等由导入器的“先删后插”保证
        self.db.execute(ins, (1, 1, "国家", "XA01", "乙类", "", ""))
        self.db.commit()
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM drug_insurance_entry").fetchone()[0], 3)

    def test_catalog_defaults(self):
        v, t = self.db.execute(
            "SELECT region, catalog_type FROM insurance_catalog "
            "WHERE catalog_id=1").fetchone()
        self.assertEqual(v, "国家")
        self.assertEqual(t, "国家医保药品目录")


if __name__ == "__main__":
    unittest.main()
