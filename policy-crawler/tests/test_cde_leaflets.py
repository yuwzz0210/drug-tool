# -*- coding: utf-8 -*-
"""CDE 说明书解析与入库测试（步骤3）。"""
import json
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.cde_leaflets import (  # noqa: E402
    classify_route,
    classify_storage,
    extract_leaflet_date,
)
from collectors.cde_postmarket import (  # noqa: E402
    company_matches,
    company_token_set,
    decide_acceptance,
    name_matches,
)
from models import DRUG_SCHEMA  # noqa: E402
from tools.import_cde_leaflets import import_one, leaflet_payload  # noqa: E402


class TestLeafletRules(unittest.TestCase):
    def test_storage_cold(self):
        self.assertEqual(classify_storage("遮光，密封，在2~8℃保存"), "冷藏(2~8℃)")
        self.assertEqual(classify_storage("于2-8℃避光保存"), "冷藏(2~8℃)")
        self.assertEqual(classify_storage("置冷处保存"), "冷藏(2~8℃)")

    def test_storage_frozen(self):
        self.assertEqual(classify_storage("-20℃以下冷冻保存"), "冷冻")
        self.assertEqual(classify_storage("零下18℃避光保存"), "冷冻")

    def test_storage_shade(self):
        self.assertEqual(classify_storage("遮光，密封，在阴凉处（不超过20℃）保存"),
                         "阴凉(≤20℃)")
        self.assertEqual(classify_storage("密闭保存"), "常温")

    def test_route(self):
        self.assertEqual(classify_route("口服"), "口服")
        self.assertEqual(classify_route("静脉滴注"), "注射")
        self.assertEqual(classify_route("皮下注射"), "注射")
        self.assertEqual(classify_route("吸入给药"), "吸入")
        self.assertEqual(classify_route("外用"), "外用")
        self.assertEqual(classify_route(""), "")

    def test_leaflet_date(self):
        text = ("核准日期：2021年06月08日\n修订日期：2023年01月20日\n"
                "【适应症】用于……")
        self.assertEqual(extract_leaflet_date(text), "2023-01-20")
        text2 = "核准日期：2021-06-08 修订日期：2023-1-2"
        self.assertEqual(extract_leaflet_date(text2), "2023-01-02")
        self.assertEqual(extract_leaflet_date("无日期"), "")


class TestLeafletImport(unittest.TestCase):
    def _db(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db = sqlite3.connect(tmp.name)
        db.executescript(DRUG_SCHEMA)
        db.execute(
            """INSERT INTO drug_molecule
               (molecule_id, generic_name) VALUES (1, '来那度胺')""")
        db.execute(
            """INSERT INTO drug_product
               (product_id, molecule_id, generic_name, dosage_form,
                specification, manufacturer_norm)
               VALUES (10, 1, '来那度胺胶囊', '胶囊剂', '25mg', '正大天晴')""")
        db.execute(
            """INSERT INTO drug_registration
               (registration_id, product_id, approval_number, status, holder)
               VALUES (100, 10, '国药准字H20193006', '有效', '正大天晴')""")
        db.commit()
        self._tmp = tmp.name
        return db

    def _payload(self):
        rec = {
            "pzwh": "国药准字H20193006",
            "status": "ok",
            "filename": "国药准字H20193006_来那度胺胶囊.pdf",
            "file_id": "5c6568a6c6deb335fcfeb9a79e790e93",
            "detail": {"gytj": "口服", "ypmc": "来那度胺胶囊"},
            "rows": [{"idCode": "e2a35d2a49b67797ad991d9f167d3109"}],
        }
        parsed = {
            "ok": True,
            "text": ("核准日期：2019年09月01日 修订日期：2021年05月06日\n"
                     "【适应症】用于治疗多发性骨髓瘤。\n"
                     "【用法用量】口服，每日25mg。\n"
                     "【贮藏】密封，在2~8℃避光保存。\n"
                     "【药理毒理】本品为免疫调节剂。"),
            "sections": {
                "适应症": "用于治疗多发性骨髓瘤。",
                "用法用量": "口服，每日25mg。",
                "贮藏": "密封，在2~8℃避光保存。",
                "药理毒理": "本品为免疫调节剂。",
            },
        }
        return leaflet_payload(rec, parsed)

    def test_import_and_idempotency(self):
        db = self._db()
        p1 = self._payload()
        eff1 = import_one(db, p1)
        db.commit()
        self.assertIn("leaflet", eff1["effects"])
        self.assertIn("indication", eff1["effects"])
        self.assertIn("mechanism", eff1["effects"])
        self.assertIn("molecule-fill", eff1["effects"])

        row = db.execute(
            "SELECT approval_number, cold_chain, route, indications "
            "FROM drug_leaflet").fetchone()
        self.assertEqual(row[0], "国药准字H20193006")
        self.assertEqual(row[1], "冷藏(2~8℃)")
        self.assertEqual(row[2], "口服")
        self.assertTrue(row[3].startswith("用于治疗"))

        prod = db.execute(
            "SELECT package_insert_url FROM drug_product WHERE product_id=10"
        ).fetchone()
        self.assertTrue(prod[0].startswith("https://www.cde.org.cn/hymlj/download/sms/"))

        mol = db.execute(
            "SELECT route, cold_chain FROM drug_molecule WHERE molecule_id=1"
        ).fetchone()
        self.assertEqual(mol, ("口服", "冷藏(2~8℃)"))

        # second import must not duplicate indication/mechanism
        eff2 = import_one(db, p1)
        db.commit()
        self.assertNotIn("indication", eff2["effects"])
        self.assertNotIn("mechanism", eff2["effects"])
        self.assertEqual(db.execute(
            "SELECT COUNT(*) FROM drug_indication WHERE product_id=10"
        ).fetchone()[0], 1)
        self.assertEqual(db.execute(
            "SELECT COUNT(*) FROM drug_mechanism WHERE product_id=10"
        ).fetchone()[0], 1)
        db.close()
        os.unlink(self._tmp)

    def test_unlinked_approval(self):
        db = self._db()
        p = self._payload()
        p["approval_number"] = "国药准字H99999999"
        eff = import_one(db, p)
        self.assertIn("unlinked:no-registration", eff["effects"])
        db.close()
        os.unlink(self._tmp)

    def test_sections_json_content(self):
        p = self._payload()
        secs = json.loads(p["sections_json"])
        self.assertEqual(secs["适应症"], "用于治疗多发性骨髓瘤。")
        self.assertEqual(secs["药理毒理"], "本品为免疫调节剂。")
        self.assertEqual(p["leaflet_date"], "2021-05-06")


class TestPostmarketMatch(unittest.TestCase):
    def test_name_match(self):
        self.assertTrue(name_matches("贝福替尼", "甲磺酸贝福替尼胶囊"))
        self.assertTrue(name_matches("二甲双胍", "盐酸二甲双胍片"))
        self.assertTrue(name_matches("阿法替尼", "马来酸阿法替尼片"))
        self.assertFalse(name_matches("阿法替尼", "吉非替尼片"))

    def test_company_match(self):
        self.assertTrue(company_matches(
            "贝达药业股份有限公司;贝达药业股份有限公司", "贝达药业"))
        self.assertFalse(company_matches("阿斯利康", "齐鲁制药"))

    def test_decide(self):
        recs = [
            {"acceptid": "CXHS2300015", "drgnamecn": "甲磺酸贝福替尼胶囊",
             "companys": "贝达药业股份有限公司", "createddate": "2023-01-20",
             "acceptidCODE": "aaa"},
            {"acceptid": "CXHS2100008", "drgnamecn": "甲磺酸贝福替尼胶囊",
             "companys": "贝达药业股份有限公司", "createddate": "2021-03-04",
             "acceptidCODE": "bbb"},
        ]
        prod = {"name": "贝福替尼", "holder": "贝达药业", "manufacturer": ""}
        picks, how = decide_acceptance(prod, recs)
        self.assertEqual(how, "unique")
        self.assertEqual(len(picks), 2)

        # same company expressed with repeated ; segments stays unique
        recs2 = [
            {"acceptid": "A1", "drgnamecn": "甲磺酸贝福替尼胶囊",
             "companys": "贝达药业股份有限公司", "createddate": "2021-01-01"},
            {"acceptid": "A2", "drgnamecn": "甲磺酸贝福替尼胶囊",
             "companys": "贝达药业股份有限公司;贝达药业股份有限公司",
             "createddate": "2023-01-01"},
        ]
        _, how2 = decide_acceptance(
            {"name": "贝福替尼", "holder": "贝达药业", "manufacturer": ""},
            recs2)
        self.assertEqual(how2, "unique")
        self.assertEqual(
            company_token_set("贝达药业股份有限公司;贝达药业股份有限公司"),
            company_token_set("贝达药业股份有限公司"))

        prod2 = {"name": "贝福替尼", "holder": "", "manufacturer": ""}
        _, how3 = decide_acceptance(prod2, [recs[0]])
        self.assertEqual(how3, "unique")

        other = {"acceptid": "CXHS2300016", "drgnamecn": "甲磺酸贝福替尼胶囊",
                 "companys": "其他药业", "createddate": "2023-02-01",
                 "acceptidCODE": "ccc"}
        picks3, how4 = decide_acceptance(
            {"name": "贝福替尼", "holder": "贝达药业", "manufacturer": ""},
            [recs[0], other])
        self.assertEqual(how4, "company_match")
        self.assertEqual([r["acceptid"] for r in picks3], ["CXHS2300015"])


class TestLeafletImportByProductId(unittest.TestCase):
    def _db(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db = sqlite3.connect(tmp.name)
        db.executescript(DRUG_SCHEMA)
        db.execute(
            "INSERT INTO drug_molecule (molecule_id, generic_name) "
            "VALUES (1, '甲磺酸贝福替尼')")
        db.execute(
            """INSERT INTO drug_product
               (product_id, molecule_id, generic_name, dosage_form,
                specification, manufacturer_norm)
               VALUES (10, 1, '甲磺酸贝福替尼胶囊', '胶囊剂', '25mg', '贝达药业')""")
        db.execute(
            """INSERT INTO drug_registration
               (registration_id, product_id, approval_number, status, holder)
               VALUES (100, 10, '国药准字H20230015', '有效', '贝达药业')""")
        db.commit()
        self._tmp = tmp.name
        return db

    def test_import_via_product_id(self):
        db = self._db()
        payload = {
            "approval_number": "国药准字H20230015",
            "product_id": 10,
            "catalog_rid": "CXHS2300015",
            "pdf_url": "https://www.cde.org.cn/main/xxgk/PostMarketDownload"
                       "?attidCODE=x&tableid=CXHS2300015",
            "source_url": "https://www.cde.org.cn/main/xxgk/postmarketpage"
                          "?acceptidCODE=CXHS2300015",
            "filename": "说明书.pdf",
            "route": "",
            "storage": "密封保存",
            "cold_chain": "常温",
            "usage_dosage": "每日一次",
            "indications": "适用于 EGFR 突变的 NSCLC。",
            "leaflet_date": "2023-06-01",
            "sections_json": json.dumps(
                {"药理毒理": "本品为 EGFR-TKI。"}, ensure_ascii=False),
            "raw_text": "【适应症】适用于 EGFR 突变的 NSCLC。",
        }
        eff = import_one(db, payload)
        db.commit()
        self.assertIn("leaflet", eff["effects"])
        row = db.execute(
            "SELECT catalog_rid, pdf_url FROM drug_leaflet").fetchone()
        self.assertEqual(row[0], "CXHS2300015")
        self.assertIn("PostMarketDownload", row[1])
        db.close()
        os.unlink(self._tmp)


if __name__ == "__main__":
    unittest.main()
