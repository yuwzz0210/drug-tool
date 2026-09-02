# -*- coding: utf-8 -*-
"""Audit DB readiness for CDE package-insert collection (step 3).

Counts products/registrations, how many already carry an insert URL, and prints
sample targets with approval numbers so the collector can be validated against
the real CDE catalog search.
"""
import sqlite3
import sys

DB = sys.argv[1] if len(sys.argv) > 1 else "policy_crawler.db"


def main():
    db = sqlite3.connect(DB)
    rows = db.execute("""
        SELECT p.product_id, p.generic_name, p.dosage_form, p.specification,
               p.trade_name, p.package_insert_url, p.is_verified,
               r.approval_number, m.generic_name, m.molecule_id
        FROM drug_product p
        LEFT JOIN drug_registration r ON r.product_id = p.product_id
        LEFT JOIN drug_molecule m ON m.molecule_id = p.molecule_id
        ORDER BY p.product_id
    """).fetchall()
    print("TOTAL_PRODUCTS", len(rows))
    prod = {}
    for r in rows:
        prod.setdefault(r[0], r)
    print("DISTINCT_PRODUCTS", len(prod))
    has_pi = [p for p in prod.values() if (p[5] or "").strip()]
    print("WITH_PACKAGE_INSERT_URL", len(has_pi))
    with_approval = [p for p in prod.values() if (p[7] or "").strip()]
    print("WITH_APPROVAL_NUMBER", len(with_approval))
    no_pi_with_appr = [p for p in with_approval if not (p[5] or "").strip()]
    print("NO_PI_WITH_APPROVAL", len(no_pi_with_appr))
    print("\nSAMPLE_NO_PI (first 15):")
    for p in no_pi_with_appr[:15]:
        print(p[0], "|", p[1], "|", p[2], "|", p[3], "| appr:", p[7],
              "| holder:", p[4])
    # distinct approval numbers currently stored
    nums = db.execute(
        "SELECT COUNT(*), COUNT(DISTINCT approval_number) FROM drug_registration"
    ).fetchone()
    print("\nREGISTRATION_ROWS/UNIQUE", nums)
    db.close()


if __name__ == "__main__":
    main()
