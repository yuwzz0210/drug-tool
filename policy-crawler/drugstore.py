# -*- coding: utf-8 -*-
"""药品/器械域存储：品种主库的增删改查（SQLite 实现，Schema 见 models.DRUG_SCHEMA）。

设计要点：
- 品种层 drug_product 以「通用名+剂型+规格+生产企业」组合去重；
- 注册层 drug_registration 以批准文号唯一（一品种多文号）；
- 适应症/机制/成分/医保条目按品种替换式写入（保留历史留待 P2 版本化增强）。
"""
import json
import sqlite3

from models import DRUG_SCHEMA, DrugProduct, DrugRegistration


def _norm(text):
    """清洗：去首尾空白、全角空格转半角、压缩连续空白。"""
    if text is None:
        return ""
    text = str(text).strip()
    text = text.replace("\u3000", " ")
    return " ".join(text.split())


def product_key(product):
    return (_norm(product.generic_name), _norm(product.dosage_form),
            _norm(product.specification), _norm(product.manufacturer_norm))


class DrugStore:
    """共享 SqliteStore 连接的药品域数据访问层（同一 .db 文件）。"""

    def __init__(self, conn):
        self._conn = conn
        self._conn.executescript(DRUG_SCHEMA)
        self._conn.commit()

    @classmethod
    def from_path(cls, db_path=":memory:"):
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return cls(conn)

    @classmethod
    def from_store(cls, store):
        conn = getattr(store, "_conn", None)
        if conn is None:
            raise ValueError("store 不支持共享连接，请使用 DrugStore.from_path")
        return cls(conn)

    def close(self):
        self._conn.close()

    # ---------- 品种层 ----------

    def upsert_product(self, product):
        key = product_key(product)
        row = self._conn.execute(
            """SELECT product_id FROM drug_product
               WHERE generic_name=? AND dosage_form=? AND specification=? AND manufacturer_norm=?""",
            key,
        ).fetchone()
        extra = product.extra_data or "{}"
        if row:
            pid = row["product_id"]
            self._conn.execute(
                """UPDATE drug_product SET trade_name=?, atc_code=?, drug_type=?,
                   is_otc=?, package_insert_url=?, source_url=?, is_verified=?,
                   extra_data=?, updated_at=datetime('now','localtime')
                   WHERE product_id=?""",
                (_norm(product.trade_name), _norm(product.atc_code), _norm(product.drug_type),
                 int(bool(product.is_otc)), _norm(product.package_insert_url),
                 _norm(product.source_url), int(bool(product.is_verified)),
                 extra, pid),
            )
        else:
            cur = self._conn.execute(
                """INSERT INTO drug_product
                   (generic_name, dosage_form, specification, manufacturer_norm,
                    trade_name, atc_code, drug_type, is_otc, package_insert_url,
                    source_url, is_verified, extra_data)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (key[0], key[1], key[2], key[3], _norm(product.trade_name),
                 _norm(product.atc_code), _norm(product.drug_type), int(bool(product.is_otc)),
                 _norm(product.package_insert_url), _norm(product.source_url),
                 int(bool(product.is_verified)), extra),
            )
            pid = cur.lastrowid
        self._conn.commit()
        return pid

    # ---------- 注册层 ----------

    def upsert_registration(self, reg):
        num = _norm(reg.approval_number)
        if not num:
            return None
        row = self._conn.execute(
            "SELECT registration_id FROM drug_registration WHERE approval_number=?",
            (num,),
        ).fetchone()
        if row:
            self._conn.execute(
                """UPDATE drug_registration SET product_id=?, registration_date=?,
                   expire_date=?, status=?, holder=?, source_url=? WHERE registration_id=?""",
                (reg.product_id, _norm(reg.registration_date), _norm(reg.expire_date),
                 _norm(reg.status) or "有效", _norm(reg.holder), _norm(reg.source_url),
                 row["registration_id"]),
            )
        else:
            self._conn.execute(
                """INSERT INTO drug_registration
                   (product_id, approval_number, registration_date, expire_date,
                    status, holder, source_url)
                   VALUES (?,?,?,?,?,?,?)""",
                (reg.product_id, num, _norm(reg.registration_date), _norm(reg.expire_date),
                 _norm(reg.status) or "有效", _norm(reg.holder), _norm(reg.source_url)),
            )
        self._conn.commit()

    # ---------- 子表：适应症 / 机制 / 成分 / 医保 ----------

    def replace_indications(self, product_id, texts):
        self._conn.execute("DELETE FROM drug_indication WHERE product_id=?", (product_id,))
        seen = set()
        for text in texts:
            t = _norm(text)
            if not t or t in seen:
                continue
            seen.add(t)
            self._conn.execute(
                "INSERT INTO drug_indication (product_id, indication_text) VALUES (?,?)",
                (product_id, t),
            )
        self._conn.commit()

    def replace_mechanisms(self, product_id, texts):
        self._conn.execute("DELETE FROM drug_mechanism WHERE product_id=?", (product_id,))
        seen = set()
        for text in texts:
            t = _norm(text)
            if not t or t in seen:
                continue
            seen.add(t)
            self._conn.execute(
                "INSERT INTO drug_mechanism (product_id, mechanism_text) VALUES (?,?)",
                (product_id, t),
            )
        self._conn.commit()

    def replace_ingredients(self, product_id, items):
        self._conn.execute("DELETE FROM drug_ingredient WHERE product_id=?", (product_id,))
        for item in items:
            name = _norm(item.get("name"))
            if not name:
                continue
            self._conn.execute(
                "INSERT INTO drug_ingredient (product_id, ingredient_name, strength, unit) VALUES (?,?,?,?)",
                (product_id, name, _norm(item.get("strength")), _norm(item.get("unit"))),
            )
        self._conn.commit()

    def upsert_catalog(self, catalog):
        version = _norm(catalog.version_name)
        row = self._conn.execute(
            "SELECT catalog_id FROM insurance_catalog WHERE version_name=?", (version,),
        ).fetchone()
        if row:
            cid = row["catalog_id"]
            self._conn.execute(
                "UPDATE insurance_catalog SET publish_date=?, source_url=?, notes=? WHERE catalog_id=?",
                (_norm(catalog.publish_date), _norm(catalog.source_url),
                 _norm(catalog.notes), cid),
            )
        else:
            cur = self._conn.execute(
                "INSERT INTO insurance_catalog (version_name, publish_date, source_url, notes) VALUES (?,?,?,?)",
                (version, _norm(catalog.publish_date), _norm(catalog.source_url),
                 _norm(catalog.notes)),
            )
            cid = cur.lastrowid
        self._conn.commit()
        return cid

    def replace_insurance_entries(self, product_id, entries, catalog_id=0):
        """替换某品种的全部医保条目；每条可指定 category/编码/支付范围/价格等。"""
        self._conn.execute("DELETE FROM drug_insurance_entry WHERE product_id=?", (product_id,))
        for e in entries:
            self._conn.execute(
                """INSERT INTO drug_insurance_entry
                   (product_id, catalog_id, category, insurance_code, payment_scope,
                    price, effective_date, expire_date, is_current)
                   VALUES (?,?,?,?,?,?,?,?,1)""",
                (product_id, catalog_id or e.get("catalog_id", 0),
                 _norm(e.get("category")), _norm(e.get("insurance_code")),
                 _norm(e.get("payment_scope")), _norm(e.get("price")),
                 _norm(e.get("effective_date")), _norm(e.get("expire_date"))),
            )
        self._conn.commit()

    # ---------- 器械域 ----------

    def upsert_device(self, device):
        num = _norm(device.registration_number)
        if not num:
            raise ValueError("器械注册证号不能为空")
        row = self._conn.execute(
            "SELECT device_id FROM device_product WHERE registration_number=?", (num,),
        ).fetchone()
        extra = device.extra_data or "{}"
        if row:
            did = row["device_id"]
            self._conn.execute(
                """UPDATE device_product SET product_name=?, management_category=?,
                   intended_use=?, structural_composition=?, manufacturer=?,
                   approval_date=?, source_url=?, is_verified=?, extra_data=?,
                   updated_at=datetime('now','localtime') WHERE device_id=?""",
                (_norm(device.product_name), _norm(device.management_category),
                 _norm(device.intended_use), _norm(device.structural_composition),
                 _norm(device.manufacturer), _norm(device.approval_date),
                 _norm(device.source_url), int(bool(device.is_verified)), extra, did),
            )
        else:
            cur = self._conn.execute(
                """INSERT INTO device_product
                   (registration_number, product_name, management_category, intended_use,
                    structural_composition, manufacturer, approval_date, source_url,
                    is_verified, extra_data)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (num, _norm(device.product_name), _norm(device.management_category),
                 _norm(device.intended_use), _norm(device.structural_composition),
                 _norm(device.manufacturer), _norm(device.approval_date),
                 _norm(device.source_url), int(bool(device.is_verified)), extra),
            )
            did = cur.lastrowid
        self._conn.commit()
        return did

    # ---------- 政策关联 ----------

    def link_policy_drug(self, policy_id, product_id, relation_type="相关", confidence=0.0,
                         is_manual_confirmed=False):
        self._conn.execute(
            """INSERT OR IGNORE INTO policy_drug_relation
               (policy_id, product_id, relation_type, confidence, is_manual_confirmed)
               VALUES (?,?,?,?,?)""",
            (policy_id, product_id, _norm(relation_type) or "相关",
             float(confidence or 0), int(bool(is_manual_confirmed))),
        )
        self._conn.commit()

    def link_policy_device(self, policy_id, device_id, relation_type="相关", confidence=0.0,
                           is_manual_confirmed=False):
        self._conn.execute(
            """INSERT OR IGNORE INTO policy_device_relation
               (policy_id, device_id, relation_type, confidence, is_manual_confirmed)
               VALUES (?,?,?,?,?)""",
            (policy_id, device_id, _norm(relation_type) or "相关",
             float(confidence or 0), int(bool(is_manual_confirmed))),
        )
        self._conn.commit()

    def add_change(self, entity_type, entity_id, change_type="", change_date="",
                   description="", source_url=""):
        self._conn.execute(
            """INSERT INTO drug_change_history
               (entity_type, entity_id, change_type, change_date, description, source_url)
               VALUES (?,?,?,?,?,?)""",
            (entity_type, entity_id, _norm(change_type), _norm(change_date),
             _norm(description), _norm(source_url)),
        )
        self._conn.commit()

    # ---------- 供查询层使用的原始读取 ----------

    def fetch_products(self, keyword="", page=1, size=20):
        where = ""
        params = []
        if keyword:
            where = """WHERE generic_name LIKE ? OR trade_name LIKE ?
                       OR manufacturer_norm LIKE ? OR atc_code LIKE ?
                       OR extra_data LIKE ?
                       OR product_id IN (
                           SELECT product_id FROM drug_indication
                           WHERE indication_text LIKE ?)"""
            like = "%{}%".format(_norm(keyword))
            params = [like, like, like, like, like, like]
        total = self._conn.execute(
            "SELECT COUNT(*) AS n FROM drug_product " + where, params,
        ).fetchone()["n"]
        page = max(1, page)
        size = max(1, min(100, size))
        rows = self._conn.execute(
            "SELECT * FROM drug_product " + where +
            " ORDER BY updated_at DESC, product_id DESC LIMIT ? OFFSET ?",
            params + [size, (page - 1) * size],
        ).fetchall()
        return total, [dict(r) for r in rows]

    def fetch_product_detail(self, product_id):
        row = self._conn.execute(
            "SELECT * FROM drug_product WHERE product_id=?", (product_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            **dict(row),
            "registrations": [dict(r) for r in self._conn.execute(
                "SELECT * FROM drug_registration WHERE product_id=? ORDER BY registration_date DESC",
                (product_id,),
            ).fetchall()],
            "indications": [dict(r) for r in self._conn.execute(
                "SELECT indication_text FROM drug_indication WHERE product_id=? ORDER BY indication_id",
                (product_id,),
            ).fetchall()],
            "mechanisms": [dict(r) for r in self._conn.execute(
                "SELECT mechanism_text FROM drug_mechanism WHERE product_id=? ORDER BY mechanism_id",
                (product_id,),
            ).fetchall()],
            "ingredients": [dict(r) for r in self._conn.execute(
                "SELECT ingredient_name, strength, unit FROM drug_ingredient WHERE product_id=?",
                (product_id,),
            ).fetchall()],
            "insurance": [dict(r) for r in self._conn.execute(
                """SELECT e.category, e.insurance_code, e.payment_scope, e.price,
                          e.effective_date, e.expire_date, e.is_current, c.version_name AS catalog
                   FROM drug_insurance_entry e
                   LEFT JOIN insurance_catalog c ON c.catalog_id=e.catalog_id
                   WHERE e.product_id=? ORDER BY e.is_current DESC, e.entry_id DESC""",
                (product_id,),
            ).fetchall()],
        }

    def fetch_devices(self, keyword="", page=1, size=20):
        where = ""
        params = []
        if keyword:
            where = "WHERE product_name LIKE ? OR registration_number LIKE ? OR manufacturer LIKE ?"
            like = "%{}%".format(_norm(keyword))
            params = [like, like, like]
        total = self._conn.execute(
            "SELECT COUNT(*) AS n FROM device_product " + where, params,
        ).fetchone()["n"]
        page = max(1, page)
        size = max(1, min(100, size))
        rows = self._conn.execute(
            "SELECT * FROM device_product " + where +
            " ORDER BY updated_at DESC, device_id DESC LIMIT ? OFFSET ?",
            params + [size, (page - 1) * size],
        ).fetchall()
        return total, [dict(r) for r in rows]

    def stats(self):
        return {
            "drugs_total": self._conn.execute("SELECT COUNT(*) AS n FROM drug_product").fetchone()["n"],
            "drugs_verified": self._conn.execute(
                "SELECT COUNT(*) AS n FROM drug_product WHERE is_verified=1").fetchone()["n"],
            "registrations": self._conn.execute(
                "SELECT COUNT(*) AS n FROM drug_registration").fetchone()["n"],
            "insurance_entries": self._conn.execute(
                "SELECT COUNT(*) AS n FROM drug_insurance_entry").fetchone()["n"],
            "devices_total": self._conn.execute("SELECT COUNT(*) AS n FROM device_product").fetchone()["n"],
        }
