# -*- coding: utf-8 -*-
"""procurement_result 表与第12批导入的幂等/回挂测试。"""
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import DRUG_SCHEMA  # noqa: E402
from tools.import_procurement_pdf import insert_procurement_result  # noqa: E402


class TestProcurementResult(unittest.TestCase):
    def _db(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db = sqlite3.connect(tmp.name)
        db.executescript(DRUG_SCHEMA)
        self._tmp = tmp.name
        return db

    def test_idempotent_and_backlink(self):
        db = self._db()
        row = {"batch": "GY-YD2026-1", "batch_seq": "1",
               "variety_name": "巴瑞替尼口服常释剂型", "generic_name": "巴瑞替尼片",
               "dosage_form": "片剂", "spec_pack": "2mg*28片/盒",
               "packaging": "铝塑", "supplier": "甲公司", "price": None,
               "price_unit": "", "source": "第12批供应清单(官方PDF)"}
        insert_procurement_result(db, row)
        row2 = dict(row, packaging="瓶装")
        insert_procurement_result(db, row2)
        rows = db.execute("SELECT packaging, product_id "
                          "FROM procurement_result").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "瓶装")   # idempotent update
        self.assertIsNone(rows[0][1])          # not linked yet
        # later registration build -> backlink by product_id
        insert_procurement_result(db, row2, product_id=7)
        self.assertEqual(db.execute(
            "SELECT product_id FROM procurement_result").fetchone()[0], 7)
        db.close()
        os.unlink(self._tmp)


if __name__ == "__main__":
    unittest.main()
