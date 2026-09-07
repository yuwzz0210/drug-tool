# -*- coding: utf-8 -*-
"""全量注册库抓取程序的严格性与防乱套测试。"""
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.registry_full import (  # noqa: E402
    insert_registry_record,
    map_numbered_row,
    normalize_payload_row,
    validate_registry_record,
)
from models import DRUG_SCHEMA  # noqa: E402


class TestStrictValidation(unittest.TestCase):
    def test_accept_official_row(self):
        rec = {"approval_number": "国药准字H20230015",
               "generic_name": "甲磺酸贝福替尼胶囊", "dosage_form": "胶囊剂",
               "specification": "25mg", "manufacturer": "贝达药业"}
        ok, why = validate_registry_record(rec)
        self.assertTrue(ok, why)

    def test_reject_missing_or_malformed(self):
        self.assertFalse(validate_registry_record(
            {"approval_number": "", "generic_name": "x"})[0])
        self.assertFalse(validate_registry_record(
            {"approval_number": "随便编的号", "generic_name": "x"})[0])
        self.assertFalse(validate_registry_record(
            {"approval_number": "国药准字H20230015", "generic_name": ""})[0])
        # 缺身份牌第2层字段 -> 拒绝，不许半截入库
        self.assertFalse(validate_registry_record(
            {"approval_number": "国药准字H20230015",
             "generic_name": "甲磺酸贝福替尼胶囊"})[0])

    def test_normalize_chinese_row(self):
        rec = normalize_payload_row({
            "药品名称": "盐酸二甲双胍片", "批准文号": "国药准字H20230015",
            "剂型": "片剂", "规格": "0.5g", "生产企业": "某药厂"})
        self.assertEqual(rec["approval_number"], "国药准字H20230015")
        self.assertEqual(rec["dosage_form"], "片剂")

    def test_map_numbered_row(self):
        mapping = {1: "approval", 2: "generic", 3: "form", 4: "spec",
                   5: "manufacturer"}
        rec = map_numbered_row(
            {"f0": "1", "f1": "国药准字H20230015", "f2": "贝福替尼胶囊",
             "f3": "胶囊剂", "f4": "25mg", "f5": "贝达药业"}, mapping)
        self.assertEqual(rec["approval_number"], "国药准字H20230015")
        self.assertEqual(rec["manufacturer"], "贝达药业")


class TestInsertRules(unittest.TestCase):
    def _db(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db = sqlite3.connect(tmp.name)
        db.executescript(DRUG_SCHEMA)
        self._tmp = tmp.name
        return db

    def test_insert_and_conflict_skip(self):
        db = self._db()
        audit = []
        rec = {"approval_number": "国药准字H20230015",
               "generic_name": "贝福替尼胶囊", "dosage_form": "胶囊剂",
               "specification": "25mg", "manufacturer": "贝达药业"}
        self.assertEqual(insert_registry_record(db, rec, "test", audit),
                         "insert")
        self.assertEqual(db.execute(
            "SELECT COUNT(*) FROM drug_product").fetchone()[0], 1)
        # same approval but different identity -> conflict, no overwrite
        rec2 = dict(rec, generic_name="别家贝福替尼", manufacturer="别家")
        self.assertEqual(insert_registry_record(db, rec2, "test", audit),
                         "conflict_skip")
        self.assertEqual(db.execute(
            "SELECT COUNT(*) FROM drug_product").fetchone()[0], 1)
        # same identity again -> update ok, still one product
        self.assertEqual(insert_registry_record(db, rec, "test", audit),
                         "insert")
        self.assertEqual(db.execute(
            "SELECT COUNT(*) FROM drug_product").fetchone()[0], 1)
        db.close()
        os.unlink(self._tmp)

    def test_reject_row_not_inserted(self):
        db = self._db()
        audit = []
        bad = {"approval_number": "编造", "generic_name": "x"}
        self.assertTrue(insert_registry_record(db, bad, "test", audit)
                        .startswith("reject"))
        self.assertEqual(db.execute(
            "SELECT COUNT(*) FROM drug_product").fetchone()[0], 0)
        db.close()
        os.unlink(self._tmp)


if __name__ == "__main__":
    unittest.main()
