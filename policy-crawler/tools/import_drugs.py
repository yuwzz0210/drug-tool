# -*- coding: utf-8 -*-
"""把前端导出的「药品数据库.json」（localStorage drug_db_v2）导入药品域主库。

用法（policy-crawler 目录下）：
    python tools/import_drugs.py --db policy_crawler.db --json ../药品数据库.json

设计：
- 品种按「通用名+剂型+规格+生产企业」组合去重（upsert）；
- 批准文号拆到注册层（一品种多文号）；
- 适应症/作用机制拆分入库；
- 医保状态粗映射（甲类/乙类/谈判药），精确版本化在 P2 由医保目录导入器补齐；
- 原始字段全部保留到 extra_data（JSON），迁移期不丢数据。
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from drugstore import DrugStore, _norm  # noqa: E402
from models import DrugInsuranceEntry, DrugProduct, DrugRegistration, InsuranceCatalog  # noqa: E402


MAPPED_KEYS = {
    "gn", "bn", "form", "spec", "mfr", "appr", "adate",
    "ind", "ind2", "mech", "mech_plain", "ins", "paystd",
    "price", "pprice",
}

_SPLIT_RE = re.compile(r"[\s;；,，、/]+")


def split_text(value):
    """按常见分隔符拆分适应症等文本。"""
    if not value:
        return []
    out = []
    for part in _SPLIT_RE.split(str(value)):
        part = _norm(part)
        if part and part not in out:
            out.append(part)
    return out


def guess_category(ins):
    """根据前端 ins 字段粗映射医保类别。"""
    text = _norm(ins)
    if not text:
        return ""
    if "谈判" in text:
        return "谈判药"
    if "甲" in text and "乙" not in text:
        return "甲类"
    if "乙" in text:
        return "乙类"
    if text.lower() in ("是", "y", "yes", "1", "医保"):
        return "医保"
    if text.lower() in ("否", "n", "no", "0", "非医保", "自费"):
        return "非医保"
    return text


def map_record(item):
    """把前端一条药品记录映射为结构化数据。"""
    raw = {k: v for k, v in item.items() if k not in MAPPED_KEYS and v not in (None, "")}
    product = DrugProduct(
        generic_name=item.get("gn", ""),
        dosage_form=item.get("form", ""),
        specification=item.get("spec", ""),
        manufacturer_norm=item.get("mfr", ""),
        trade_name=item.get("bn", ""),
        is_otc=False,
        extra_data=json.dumps(raw, ensure_ascii=False),
    )
    registrations = [
        DrugRegistration(product_id=0, approval_number=num, registration_date=item.get("adate", ""))
        for num in split_text(item.get("appr"))
    ]
    indications = split_text(item.get("ind")) + split_text(item.get("ind2"))
    mechanisms = []
    for m in split_text(item.get("mech") or item.get("mech_plain")):
        if m and m not in mechanisms:
            mechanisms.append(m)
    price = item.get("price")
    if price in (None, ""):
        price = item.get("pprice")
    insurance = {
        "category": guess_category(item.get("ins")),
        "payment_scope": item.get("paystd", ""),
        "price": price if price not in (None, "") else "",
    }
    return product, registrations, indications, mechanisms, insurance


def import_file(db_path, json_path, catalog_version=""):
    with open(json_path, encoding="utf-8") as f:
        records = json.load(f)
    if not isinstance(records, list):
        raise ValueError("JSON 顶层必须是数组（药品记录列表）")
    store = DrugStore.from_path(db_path)
    catalog_id = 0
    if catalog_version:
        catalog_id = store.upsert_catalog(InsuranceCatalog(version_name=catalog_version))
    report = {
        "total_records": len(records),
        "products": 0,
        "registrations": 0,
        "indications": 0,
        "mechanisms": 0,
        "insurance_entries": 0,
        "skipped": 0,
    }
    for item in records:
        if not isinstance(item, dict) or not item.get("gn"):
            report["skipped"] += 1
            continue
        product, registrations, indications, mechanisms, insurance = map_record(item)
        pid = store.upsert_product(product)
        report["products"] += 1
        for reg in registrations:
            reg.product_id = pid
            store.upsert_registration(reg)
            report["registrations"] += 1
        store.replace_indications(pid, indications)
        report["indications"] += len(indications)
        store.replace_mechanisms(pid, mechanisms)
        report["mechanisms"] += len(mechanisms)
        store.replace_insurance_entries(pid, [insurance], catalog_id=catalog_id)
        report["insurance_entries"] += 1
    store.close()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="导入前端导出的药品数据库 JSON")
    parser.add_argument("--db", default="policy_crawler.db")
    parser.add_argument("--json", required=True, help="前端「导出JSON」生成的文件路径")
    parser.add_argument("--catalog", default="", help="医保目录版本名（如 2025版国家医保目录）")
    args = parser.parse_args(argv)
    report = import_file(args.db, args.json, args.catalog)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
