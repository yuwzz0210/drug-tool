# -*- coding: utf-8 -*-
"""第12批国家集采（GY-YD2026-1）PDF 导入工具。

输入（官方附件）：
  中选结果表：品种序号/品种名称/中选企业
  供应清单：品种序号/品种名称/药品通用名/剂型/规格包装/包装方式/中选企业
两文件均不含价格 -> 不写 price_history（严禁臆造价格）。

入库规则（身份牌优先）：
  - 仅把供应清单行挂到库内“身份一致”的已有品种上（通用名+剂型+厂家匹配，
    规格再核）；挂不上的一律进审计清单，等 NMPA 文号回填后再关联，不新建
    无身份牌的品种行。
  - 结果表（无通用名/规格）只做统计与审计，不直接挂品种。

用法：
    python tools/import_procurement_pdf.py --db policy_crawler.db --dry-run
    python tools/import_procurement_pdf.py --db policy_crawler.db
"""
import argparse
import json
import os
import re
import sqlite3
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import pdfplumber

RESULT_PDF = (r"C:\Users\YUWZZ\Desktop\html_pages"
              r"\第12批国家组织药品集中带量采购中选结果表（GY-YD2026-1）"
              r"_202608061786007462909.pdf")
SUPPLY_PDF = (r"C:\Users\YUWZZ\Desktop\html_pages"
              r"\第12批国家组织药品集中带量采购中选品种供应清单"
              r"（GY-YD2026-1）_202608061786007479657.pdf")
BATCH = "GY-YD2026-1"


def read_table_rows(path, header_kw):
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for t in page.extract_tables() or []:
                for row in t:
                    cells = [(c or "").replace("\n", "").strip() for c in row]
                    if not any(cells):
                        continue
                    if header_kw and cells[0] == header_kw[0]:
                        continue  # repeated header row
                    if len(cells) >= 3 and cells[0].isdigit():
                        rows.append(cells)
    return rows


def main_company(text):
    """中选企业主名：取括号外主体，去‘受托生产’后缀描述。"""
    t = (text or "").split("（")[0].split("(")[0].strip()
    return t


def load_products(db):
    return db.execute("""
        SELECT product_id, generic_name, dosage_form, specification,
               manufacturer_norm
        FROM drug_product
    """).fetchall()


def find_product(products, generic, dosage, spec_pack, company):
    """身份键匹配：通用名+剂型+厂家；规格兜底不强配。"""
    comp = main_company(company)
    strength = re.split(r"[*×Xx]", spec_pack or "")[0].strip()
    cand = []
    for p in products:
        if p[1] == generic and (p[2] or "") == (dosage or ""):
            mfg = p[4] or ""
            if comp and (comp in mfg or mfg in comp):
                score = 2 if (p[3] and strength and strength in p[3]) else 1
                cand.append((score, p))
    if not cand:
        return None
    cand.sort(key=lambda x: -x[0])
    best = cand[0]
    return best[1] if best[0] >= 1 else None


def insert_procurement_result(db, row, product_id=None):
    """Idempotent insert of one supply-list row (product_id may be NULL)."""
    db.execute(
        """INSERT INTO procurement_result
           (batch, batch_seq, variety_name, generic_name, dosage_form,
            spec_pack, packaging, supplier, product_id, price, price_unit,
            source, source_url, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now','localtime'))
           ON CONFLICT(batch, batch_seq, generic_name, spec_pack, supplier)
           DO UPDATE SET
             variety_name=excluded.variety_name,
             dosage_form=excluded.dosage_form,
             packaging=excluded.packaging,
             product_id=excluded.product_id,
             price=excluded.price,
             price_unit=excluded.price_unit,
             source=excluded.source,
             source_url=excluded.source_url,
             updated_at=excluded.updated_at""",
        (row["batch"], row["batch_seq"], row["variety_name"],
         row["generic_name"], row["dosage_form"], row["spec_pack"],
         row["packaging"], row["supplier"], product_id, row.get("price"),
         row.get("price_unit", ""), row.get("source", ""),
         row.get("source_url", "")))
    db.commit()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="policy_crawler.db")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--audit", default="logs/procurement_gy2026_1.jsonl")
    args = ap.parse_args()
    result_rows = read_table_rows(RESULT_PDF, ["品种序号"])
    supply_rows = read_table_rows(SUPPLY_PDF, ["品种序号"])
    print("result_rows", len(result_rows), "supply_rows", len(supply_rows))

    db = sqlite3.connect(args.db)
    products = load_products(db)
    audit = []
    linked = 0
    for r in supply_rows:
        if len(r) < 7:
            audit.append({"action": "skip_malformed", "row": r})
            continue
        seq, variety, generic, dosage, spec_pack, pack_way, company = r[:7]
        prod = find_product(products, generic, dosage, spec_pack, company)
        payload = {
            "batch": BATCH, "batch_seq": seq, "variety_name": variety,
            "generic_name": generic, "dosage_form": dosage,
            "spec_pack": spec_pack, "packaging": pack_way,
            "supplier": company, "price": None, "price_unit": "",
            "source": "第12批供应清单(官方PDF)"}
        if not args.dry_run:
            insert_procurement_result(db, payload,
                                      prod[0] if prod else None)
        if prod:
            linked += 1
            audit.append({"action": "linked", "product_id": prod[0],
                          "generic": generic, "spec_pack": spec_pack})
        else:
            audit.append({"action": "stored_unlinked",
                          "generic": generic, "spec_pack": spec_pack,
                          "company": company, "seq": seq})

    # result-table stats only (no dosage/spec -> not linked)
    seqs = {r[0] for r in result_rows if r[0].isdigit()}
    companies = {main_company(r[2]) for r in result_rows if len(r) >= 3}
    stats = {"supply_rows": len(supply_rows), "linked": linked,
             "stored_unlinked":
                 sum(1 for a in audit if a["action"] == "stored_unlinked"),
             "result_varieties": len(seqs),
             "result_companies": len(companies)}
    print("STATS", json.dumps(stats, ensure_ascii=False))
    if args.dry_run:
        print("unlinked samples:")
        n = 0
        for a in audit:
            if a["action"] == "stored_unlinked":
                print(" ", a)
                n += 1
                if n >= 8:
                    break
    if args.audit:
        with open(args.audit, "w", encoding="utf-8") as fh:
            for a in audit:
                fh.write(json.dumps(a, ensure_ascii=False) + "\n")
        print("AUDIT", args.audit)
    db.close()


if __name__ == "__main__":
    main()
