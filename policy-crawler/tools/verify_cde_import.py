# -*- coding: utf-8 -*-
"""Verify CDE leaflet import landed correctly in the DB (step 3 QA)."""
import sqlite3
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DB = sys.argv[1] if len(sys.argv) > 1 else "policy_crawler.db"


def main():
    db = sqlite3.connect(DB)
    q = db.execute
    print("drug_leaflet", q(
        "SELECT COUNT(*) FROM drug_leaflet").fetchone()[0])
    print("leaflet_with_pdf_url", q(
        "SELECT COUNT(*) FROM drug_leaflet WHERE pdf_url!=''").fetchone()[0])
    print("products_with_insert_url", q(
        "SELECT COUNT(*) FROM drug_product WHERE package_insert_url!=''"
    ).fetchone()[0])
    print("indication_rows_CDE", q(
        "SELECT COUNT(*) FROM drug_indication "
        "WHERE approval_status='说明书(CDE)'").fetchone()[0])
    print("mechanism_rows_CDE", q(
        "SELECT COUNT(*) FROM drug_mechanism WHERE mechanism_text!=''"
    ).fetchone()[0])
    print("molecule_route_filled", q(
        "SELECT COUNT(*) FROM drug_molecule WHERE route!=''").fetchone()[0])
    print("molecule_cold_chain_filled", q(
        "SELECT COUNT(*) FROM drug_molecule WHERE cold_chain!=''").fetchone()[0])
    rows = q("""
        SELECT l.approval_number, m.generic_name, l.route, l.cold_chain,
               l.leaflet_date, p.package_insert_url
        FROM drug_leaflet l
        JOIN drug_product p ON p.product_id=l.product_id
        JOIN drug_molecule m ON m.molecule_id=p.molecule_id
        ORDER BY l.leaflet_id LIMIT 5""").fetchall()
    print("\nSAMPLES:")
    for r in rows:
        print(" | ".join(str(x or "") for x in r))
    db.close()


if __name__ == "__main__":
    main()
