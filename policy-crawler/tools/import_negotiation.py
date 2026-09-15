# -*- coding: utf-8 -*-
"""国谈/竞价结果导入：insurance_catalog_entry（谈判/竞价）→ negotiation_result。

数据来源：已入库的国家医保药品目录（catalog 2 = 2025 年）中
section='谈判' 与 section='竞价' 的条目，字段含通用名/剂型/支付标准/
协议期（valid_until）/甲乙类。**只映射既有官方字段，不引入外部猜测。**

关联规则：
- molecule_id：用 normalize.molecule_key 归一后与 drug_molecule.generic_name 比对，
  仅当唯一命中时写入；
- product_id：仅当条目名归一后与某个 drug_product.generic_name 完全相同
  且该名称只对应一个品种时写入，否则留空（避免误挂）。

幂等：以 catalog_entry_id 为唯一键 upsert。

用法：
    python tools/import_negotiation.py --db policy_crawler.db
    python tools/import_negotiation.py --db policy_crawler.db --report logs/negotiation_report.json
"""
import argparse
import json
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from normalize import molecule_key, norm_roman, to_half_width  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


SECTION_CATEGORY = {"谈判": "谈判", "竞价": "竞价"}


def _name_key(name):
    """完整药名归一（保留剂型，用于与品种名精确比对）。"""
    return norm_roman(to_half_width(name or "")).strip()


def _batch_year(version_name, valid_until):
    """从目录版本名或协议期推断国谈批次年份。"""
    for text in (version_name or "", valid_until or ""):
        m = re.search(r"(20\d{2})\s*年", text)
        if m:
            return m.group(1)
    return ""


def _build_molecule_index(db):
    """molecule_key -> [molecule_id, ...]（key 命中多个分子时不写关联）。"""
    index = {}
    for mid, name in db.execute(
            "SELECT molecule_id, generic_name FROM drug_molecule"):
        key = molecule_key(name)
        if key:
            index.setdefault(key, []).append(mid)
    return index


def _build_product_index(db):
    """完整通用名归一 -> [product_id, ...]。"""
    index = {}
    for pid, name in db.execute(
            "SELECT product_id, generic_name FROM drug_product"):
        key = _name_key(name)
        if key:
            index.setdefault(key, []).append(pid)
    return index


def import_rows(db, report_path=None):
    mol_index = _build_molecule_index(db)
    prod_index = _build_product_index(db)
    rows = db.execute("""
        SELECT e.entry_id, e.catalog_id, e.section, e.category, e.name,
               e.dosage_form, e.pay_standard, e.payment_scope, e.valid_until,
               c.version_name, c.source_url
          FROM insurance_catalog_entry e
          JOIN insurance_catalog c ON c.catalog_id = e.catalog_id
         WHERE e.section IN ('谈判', '竞价')
         ORDER BY e.entry_id
    """).fetchall()

    stats = {"entries": 0, "molecule_linked": 0, "product_linked": 0,
             "unmatched": 0, "skipped_no_name": 0}
    unmatched = []
    for (entry_id, catalog_id, section, category, name, dosage_form,
         pay_standard, payment_scope, valid_until, version_name,
         source_url) in rows:
        name = (name or "").strip()
        if not name:
            stats["skipped_no_name"] += 1
            continue
        stats["entries"] += 1
        mol_key = molecule_key(name)
        mol_hits = mol_index.get(mol_key, [])
        molecule_id = mol_hits[0] if len(mol_hits) == 1 else None
        prod_hits = prod_index.get(_name_key(name), [])
        product_id = prod_hits[0] if len(prod_hits) == 1 else None
        if molecule_id:
            stats["molecule_linked"] += 1
        if product_id:
            stats["product_linked"] += 1
        if not molecule_id:
            stats["unmatched"] += 1
            if len(unmatched) < 100:
                unmatched.append({"entry_id": entry_id, "name": name,
                                  "section": section})

        notes = "医保目录条目映射(catalog_entry_id=%s)" % entry_id
        if payment_scope:
            notes += "；支付范围=" + payment_scope[:200]
        db.execute("""
            INSERT INTO negotiation_result
                (molecule_id, product_id, catalog_id, catalog_entry_id,
                 batch_year, drug_name, dosage_form, category, pay_standard,
                 agreement_period, source_url, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(catalog_entry_id) DO UPDATE SET
                molecule_id=excluded.molecule_id,
                product_id=excluded.product_id,
                catalog_id=excluded.catalog_id,
                batch_year=excluded.batch_year,
                drug_name=excluded.drug_name,
                dosage_form=excluded.dosage_form,
                category=excluded.category,
                pay_standard=excluded.pay_standard,
                agreement_period=excluded.agreement_period,
                source_url=excluded.source_url,
                notes=excluded.notes
        """, (molecule_id, product_id, catalog_id, entry_id,
              _batch_year(version_name, valid_until), name,
              (dosage_form or "").strip(),
              SECTION_CATEGORY.get(section, section),
              (pay_standard or "").strip(),
              (valid_until or "").strip(),
              (source_url or "").strip(), notes))
    db.commit()

    stats["stored"] = db.execute(
        "SELECT COUNT(*) FROM negotiation_result").fetchone()[0]
    if report_path:
        os.makedirs(os.path.dirname(os.path.abspath(report_path)),
                    exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump({"stats": stats, "unmatched_sample": unmatched}, fh,
                      ensure_ascii=False, indent=2)
    return stats


def main(argv=None):
    ap = argparse.ArgumentParser(description="国谈/竞价结果导入")
    ap.add_argument("--db", default="policy_crawler.db")
    ap.add_argument("--report", default="")
    args = ap.parse_args(argv)
    db = sqlite3.connect(args.db)
    try:
        stats = import_rows(db, args.report or None)
    finally:
        db.close()
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print("IMPORT_NEGOTIATION_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
