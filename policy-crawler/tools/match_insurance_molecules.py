# -*- coding: utf-8 -*-
"""分子层医保目录匹配：目录条目 → 品种分子(molecule) → 全组产品继承医保状态。

用法（policy-crawler 目录下）：
    python tools/match_insurance_molecules.py --db policy_crawler.db

原理：
1. 目录条目名与分子规范名都经 normalize.molecule_key（去剂型/盐基/标识/归一化）；
2. 相等即匹配（目录条目可能含多药名，逐段匹配）；
3. 命中后把目录条目写入该分子下全部产品的 drug_insurance_entry。
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from drugstore import DrugStore  # noqa: E402
from importers.insurance_catalog import _parse_valid_range  # noqa: E402
from normalize import molecule_key  # noqa: E402


def catalog_name_keys(name):
    """目录条目名可能含多个药名（换行分隔），逐段生成分子键集合。"""
    keys = set()
    for part in (name or "").splitlines():
        k = molecule_key(part)
        if len(k) >= 2:
            keys.add(k)
    return keys


def find_matches(catalog_entries, molecules):
    """目录条目 → 分子 匹配。返回 {catalog_entry_id: [molecule_id, ...]}。"""
    mol_keys = {}
    for m in molecules:
        k = molecule_key(m["generic_name"])
        if len(k) >= 2:
            mol_keys.setdefault(k, []).append(m["molecule_id"])
    matches = {}
    for e in catalog_entries:
        hits = []
        for k in catalog_name_keys(e["name"]):
            for mid in mol_keys.get(k, []):
                if mid not in hits:
                    hits.append(mid)
        if hits:
            matches[e["entry_id"]] = hits
    return matches


def run(db_path, catalog_id=None):
    drugs = DrugStore.from_path(db_path)
    if catalog_id is None:
        row = drugs._conn.execute(
            "SELECT catalog_id FROM insurance_catalog ORDER BY catalog_id DESC LIMIT 1",
        ).fetchone()
        catalog_id = row["catalog_id"] if row else 0
    entries = [dict(r) for r in drugs._conn.execute(
        "SELECT * FROM insurance_catalog_entry WHERE catalog_id=?", (catalog_id,)).fetchall()]
    molecules = [dict(r) for r in drugs._conn.execute(
        "SELECT molecule_id, generic_name FROM drug_molecule").fetchall()]
    products = [dict(r) for r in drugs._conn.execute(
        "SELECT product_id, molecule_id FROM drug_product").fetchall()]

    matches = find_matches(entries, molecules)
    # 分子 → 命中目录条目
    by_mol = {}
    for eid, mids in matches.items():
        e = next((x for x in entries if x["entry_id"] == eid), None)
        if not e:
            continue
        for mid in mids:
            by_mol.setdefault(mid, []).append(e)

    # 覆盖：目录条目匹配到的分子下所有产品
    drugs.reset_catalog_matches(catalog_id)
    prod_by_mol = {}
    for p in products:
        if p.get("molecule_id"):
            prod_by_mol.setdefault(p["molecule_id"], []).append(p["product_id"])
    covered_products = set()
    covered_molecules = 0
    for mid, entry_list in by_mol.items():
        pids = prod_by_mol.get(mid, [])
        if not pids:
            continue
        covered_molecules += 1
        for pid in pids:
            entry_payloads = []
            for e in entry_list:
                effective, expire = _parse_valid_range(e.get("valid_until", ""))
                entry_payloads.append({
                    "category": e.get("category", ""),
                    "insurance_code": e.get("code", ""),
                    "payment_scope": e.get("payment_scope", ""),
                    "price": e.get("pay_standard", ""),
                    "effective_date": effective,
                    "expire_date": expire,
                })
            drugs.set_product_catalog_entries(pid, catalog_id, entry_payloads)
            covered_products.add(pid)

    matched_mol_names = {m["generic_name"] for m in molecules if m["molecule_id"] in by_mol}
    all_mol_names = {m["generic_name"] for m in molecules}
    drugs.close()
    return {
        "catalog_id": catalog_id,
        "catalog_entries_total": len(entries),
        "catalog_entries_matched": len(matches),
        "molecules_total": len(molecules),
        "molecules_covered": covered_molecules,
        "products_covered": len(covered_products),
        "unmatched_molecules": sorted(all_mol_names - matched_mol_names),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="分子层医保目录匹配")
    parser.add_argument("--db", default="policy_crawler.db")
    parser.add_argument("--catalog-id", type=int, default=None)
    args = parser.parse_args(argv)
    report = run(args.db, args.catalog_id)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
