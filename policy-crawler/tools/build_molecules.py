# -*- coding: utf-8 -*-
"""品种聚合：把「厂家 × 通用名+剂型」的 drug_product 按清洗后的规范通用名聚合到 drug_molecule。

用法（policy-crawler 目录下）：
    python tools/build_molecules.py --db policy_crawler.db

幂等：重复运行按 molecule.generic_name 唯一键 upsert，不产生重复。
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from drugstore import DrugStore  # noqa: E402
from models import DrugMolecule  # noqa: E402
from normalize import molecule_key  # noqa: E402


def build(db_path):
    drugs = DrugStore.from_path(db_path)
    groups = {}
    page = 1
    while True:
        total, rows = drugs.fetch_products(page=page, size=100)
        for r in rows:
            key = molecule_key(r["generic_name"])
            groups.setdefault(key, []).append(r["product_id"])
        if page * 100 >= total:
            break
        page += 1
    molecule_ids = {}
    for key, pids in groups.items():
        mid = drugs.upsert_molecule(DrugMolecule(generic_name=key))
        molecule_ids[key] = mid
        for pid in pids:
            drugs.set_product_molecule(pid, mid)
    drugs.close()
    sizes = sorted((len(v) for v in groups.values()), reverse=True)
    return {
        "products": total,
        "molecules": len(groups),
        "max_per_molecule": sizes[0] if sizes else 0,
        "avg_per_molecule": round(sum(sizes) / len(sizes), 1) if sizes else 0,
        "molecule_ids": molecule_ids,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="品种聚合层构建")
    parser.add_argument("--db", default="policy_crawler.db")
    args = parser.parse_args(argv)
    report = build(args.db)
    print(json.dumps({k: v for k, v in report.items() if k != "molecule_ids"},
                     ensure_ascii=False, indent=2))
    print("示例:", list(report["molecule_ids"].keys())[:12])
    return 0


if __name__ == "__main__":
    sys.exit(main())
