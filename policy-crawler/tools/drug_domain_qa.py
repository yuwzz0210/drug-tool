# -*- coding: utf-8 -*-
"""Drug-domain coverage matrix: how complete each layer is, where the gaps are.

Usage:
    python tools/drug_domain_qa.py --db policy_crawler.db
"""
import argparse
import sqlite3
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="policy_crawler.db")
    args = ap.parse_args()
    db = sqlite3.connect(args.db)
    q = db.execute

    def c(sql):
        return q(sql).fetchone()[0]

    print("=== 药品域分层体检 ===")
    print("molecule         : %d" % c("SELECT COUNT(*) FROM drug_molecule"))
    print("product          : %d" % c("SELECT COUNT(*) FROM drug_product"))
    print("registration     : %d (products 有文号: %d / 无文号: %d)"
          % (c("SELECT COUNT(*) FROM drug_registration"),
             c("SELECT COUNT(DISTINCT product_id) FROM drug_registration"),
             c("SELECT COUNT(*) FROM drug_product p WHERE NOT EXISTS"
               " (SELECT 1 FROM drug_registration r WHERE r.product_id=p.product_id)")))
    print("leaflet products : %d / %d" % (
        c("SELECT COUNT(*) FROM drug_product WHERE length(package_insert_url)>0"),
        c("SELECT COUNT(*) FROM drug_product")))
    print("indication rows  : %d (products 有适应症: %d)" % (
        c("SELECT COUNT(*) FROM drug_indication"),
        c("SELECT COUNT(DISTINCT product_id) FROM drug_indication")))
    print("mechanism rows   : %d (products 有机制: %d)" % (
        c("SELECT COUNT(*) FROM drug_mechanism"),
        c("SELECT COUNT(DISTINCT product_id) FROM drug_mechanism")))
    print("ingredient rows  : %d" % c("SELECT COUNT(*) FROM drug_ingredient"))
    print("insurance links  : %d (products 已关联: %d)" % (
        c("SELECT COUNT(*) FROM drug_insurance_entry"),
        c("SELECT COUNT(DISTINCT product_id) FROM drug_insurance_entry")))
    print("price rows       : %d" % c("SELECT COUNT(*) FROM price_history"))
    print("market rows      : %d" % c("SELECT COUNT(*) FROM drug_market"))

    print("\n--- molecule 关键字段填充 ---")
    for col in ("route", "cold_chain", "mechanism_summary",
                "extra_indications", "atc_code"):
        n = c("SELECT COUNT(*) FROM drug_molecule "
              "WHERE length(%s)>0" % col)
        print("%-20s %d / %d" % (col, n,
              c("SELECT COUNT(*) FROM drug_molecule")))

    print("\n--- product 关键字段填充 ---")
    for col in ("dosage_form", "specification", "manufacturer_norm",
                "trade_name", "package_insert_url"):
        n = c("SELECT COUNT(*) FROM drug_product WHERE length(%s)>0" % col)
        print("%-22s %d / %d" % (col, n,
              c("SELECT COUNT(*) FROM drug_product")))

    print("\n--- 说明书层 sections 覆盖(基于 leaflet) ---")
    have = c("""SELECT COUNT(*) FROM drug_leaflet
                WHERE length(indications)>0""")
    print("indications text in leaflet: %d / %d"
          % (have, c("SELECT COUNT(*) FROM drug_leaflet")))
    have2 = c("""SELECT COUNT(*) FROM drug_leaflet
                 WHERE length(usage_dosage)>0""")
    print("usage_dosage text in leaflet: %d / %d"
          % (have2, c("SELECT COUNT(*) FROM drug_leaflet")))
    db.close()


if __name__ == "__main__":
    main()
