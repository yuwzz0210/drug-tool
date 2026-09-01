# -*- coding: utf-8 -*-
"""价格时序 + 市场层录入工具（人工随用随录 / 集采结果导入共用）。

JSON 格式：
{
  "prices": [
    {"approval_number": "国药准字H20200001", "price": 12.5,
     "price_type": "挂网", "effective_date": "2026-09-01",
     "source_url": "https://...", "reviewed_by": "张三"}
  ],
  "markets": [
    {"generic_name": "奥希替尼", "region": "全国", "sales_year": 2026,
     "patient_count": 100000, "diagnosis_rate": 0.5,
     "prescription_penetration": 0.3, "annual_sales": "60亿",
     "formula": "患者池×确诊率×渗透率", "confidence": "中",
     "source": "流行病学文献估算", "estimated_date": "2026-09-01"}
  ]
}

用法：python tools/import_price_market.py --db policy_crawler.db --json 录入.json
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from drugstore import DrugStore  # noqa: E402
from models import DrugMarket, DrugMolecule, PriceRecord  # noqa: E402
from normalize import molecule_key  # noqa: E402


def import_file(db_path, json_path):
    with open(json_path, encoding="utf-8") as f:
        payload = json.load(f)
    drugs = DrugStore.from_path(db_path)
    report = {"prices": 0, "prices_skipped": 0, "markets": 0, "markets_skipped": 0}

    # 价格：按批准文号解析 product_id
    for p in payload.get("prices", []):
        num = (p.get("approval_number") or "").strip()
        if not num:
            report["prices_skipped"] += 1
            continue
        row = drugs._conn.execute(
            "SELECT product_id FROM drug_registration WHERE approval_number=?",
            (num,),
        ).fetchone()
        if row is None:
            report["prices_skipped"] += 1
            continue
        drugs.upsert_price(PriceRecord(
            product_id=row["product_id"],
            price=float(p["price"]),
            price_type=p.get("price_type", "挂网"),
            unit=p.get("unit", ""),
            effective_date=p.get("effective_date", ""),
            expire_date=p.get("expire_date", ""),
            source_url=p.get("source_url", ""),
            reviewed_at=p.get("reviewed_at", ""),
            reviewed_by=p.get("reviewed_by", ""),
            notes=p.get("notes", ""),
        ))
        report["prices"] += 1

    # 市场：按规范通用名解析 molecule_id
    for m in payload.get("markets", []):
        key = molecule_key(m.get("generic_name", ""))
        if not key:
            report["markets_skipped"] += 1
            continue
        mid = drugs.upsert_molecule(DrugMolecule(generic_name=key))
        drugs.upsert_market(DrugMarket(
            molecule_id=mid,
            region=m.get("region", "全国"),
            sales_year=int(m.get("sales_year") or 0),
            patient_count=float(m.get("patient_count") or 0),
            diagnosis_rate=float(m.get("diagnosis_rate") or 0),
            prescription_penetration=float(m.get("prescription_penetration") or 0),
            annual_sales=m.get("annual_sales", ""),
            formula=m.get("formula", ""),
            confidence=m.get("confidence", "中"),
            source=m.get("source", ""),
            estimated_date=m.get("estimated_date", ""),
            reviewed_at=m.get("reviewed_at", ""),
        ))
        report["markets"] += 1
    drugs.close()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="价格/市场层录入")
    parser.add_argument("--db", default="policy_crawler.db")
    parser.add_argument("--json", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(import_file(args.db, args.json), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
