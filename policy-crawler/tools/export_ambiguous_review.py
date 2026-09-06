# -*- coding: utf-8 -*-
"""Export a human review sheet for postmarket ambiguous records.

Groups by normalized drug name so one repeated product row does not flood the
list; for each group lists our DB products (names/approvals/holder/trade) and
every CDE acceptance candidate observed (acceptid/company/date).

Usage:
    python tools/export_ambiguous_review.py --results logs/cde_pm_full.jsonl \
        --db policy_crawler.db --out logs/cde_pm_ambiguous_review.txt
"""
import argparse
import collections
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from normalize import norm_roman, to_half_width  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def name_key(name):
    return norm_roman(to_half_width(name or "")).strip() or (name or "")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", required=True)
    ap.add_argument("--db", default="policy_crawler.db")
    ap.add_argument("--out", default="logs/cde_pm_ambiguous_review.txt")
    args = ap.parse_args()

    recs = []
    with open(args.results, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("status") == "ambiguous":
                recs.append(r)

    db = sqlite3.connect(args.db)
    prod_rows = db.execute("""
        SELECT p.product_id, p.generic_name, p.dosage_form, p.specification,
               p.trade_name, p.manufacturer_norm
        FROM drug_product p
        WHERE (p.package_insert_url IS NULL OR p.package_insert_url = '')
        ORDER BY p.product_id
    """).fetchall()
    regs = {}
    for r in db.execute("""
            SELECT p.product_id, r.approval_number, r.holder
            FROM drug_product p
            LEFT JOIN drug_registration r ON r.product_id = p.product_id"""):
        regs.setdefault(r[0], []).append((r[1] or "", r[2] or ""))
    db.close()

    by_key = collections.defaultdict(list)
    for rec in recs:
        by_key[name_key(rec.get("name"))].append(rec)

    lines = []
    lines.append("=== CDE channel-2 ambiguous review list (deduped by name) ===")
    lines.append("unique drug names: %d | result rows: %d"
                 % (len(by_key), len(recs)))
    for key in sorted(by_key):
        group = by_key[key]
        lines.append("\n# %s  (rows=%d)" % (key, len(group)))
        # our DB products matching the key
        for pr in prod_rows:
            if name_key(pr[1]) == key:
                codes = ", ".join(a for a, _ in regs.get(pr[0], []))
                holder = "; ".join(h for _, h in regs.get(pr[0], []) if h)
                lines.append("  OUR product_id=%s | %s %s | 文号: %s"
                             " | 商品名: %s | 厂家: %s"
                             % (pr[0], pr[1], pr[2], codes,
                                pr[4] or "", holder or pr[5] or ""))
        cand = collections.OrderedDict()
        for rec in group:
            for a in (rec.get("accepts") or [])[:20]:
                cid = a.get("acceptid") or ""
                if cid not in cand:
                    cand[cid] = a
        lines.append("  CDE candidates:")
        for a in cand.values():
            lines.append("    %s | %s | %s | %s"
                         % (a.get("acceptid"), a.get("drgnamecn"),
                            a.get("companys"), a.get("createddate")))
    report = "\n".join(lines)
    print(report[:3500])
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(report)
    print("\nSAVED", args.out)


if __name__ == "__main__":
    main()
