# -*- coding: utf-8 -*-
"""导出站点快照 data/drugs.json（分页取全量品种，含注册/医保/适应症/机制）。

用法（policy-crawler 目录下）：
    python tools/export_drugs_snapshot.py --db policy_crawler.db --out ../data/drugs.json
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from drug_queries import drug_detail  # noqa: E402
from drugstore import DrugStore  # noqa: E402


def export_snapshot(db_path, out_path):
    drugs = DrugStore.from_path(db_path)
    out = []
    page = 1
    while True:
        total, rows = drugs.fetch_products(page=page, size=100)
        for r in rows:
            d = drug_detail(drugs, r["product_id"])
            out.append({
                "product_id": d["product_id"],
                "generic_name": d["generic_name"],
                "trade_name": d["trade_name"],
                "dosage_form": d["dosage_form"],
                "specification": d["specification"],
                "manufacturer": d["manufacturer_norm"],
                "atc_code": d["atc_code"],
                "drug_type": d["drug_type"],
                "is_verified": bool(d["is_verified"]),
                "indications": [i["indication_text"] for i in d["indications"]],
                "mechanisms": [m["mechanism_text"] for m in d["mechanisms"]],
                "ingredients": d["ingredients"],
                "registrations": [
                    {"approval_number": x["approval_number"], "status": x["status"],
                     "registration_date": x["registration_date"], "holder": x.get("holder", "")}
                    for x in d["registrations"]
                ],
                "insurance": d["insurance"],
                "extra_data": json.loads(d["extra_data"] or "{}"),
                "updated_at": d["updated_at"],
            })
        if page * 100 >= total:
            break
        page += 1
    drugs.close()
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return len(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description="导出 data/drugs.json 站点快照")
    parser.add_argument("--db", default="policy_crawler.db")
    parser.add_argument("--out", default=os.path.join(ROOT, "repo", "data", "drugs.json"))
    args = parser.parse_args(argv)
    n = export_snapshot(args.db, args.out)
    print("drugs.json 已导出:", n, "条 →", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
