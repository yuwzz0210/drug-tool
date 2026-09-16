# -*- coding: utf-8 -*-
"""品种库覆盖缺口审计：算清"还差多少品种、哪条路补得最快"。

只读工具，不改数据库。对比三类来源：
1) 本库现状：drug_product / drug_registration（批准文号身份牌）
2) 官方目录名：insurance_catalog_entry 的通用名（医保目录，已有 6,900+ 条）
3) 省级挂网价文件：如湖南《药品价格信息公布表》（含批准文号/编码/规格/厂家）

输出：每条来源能带来的新增批准文号数、可覆盖率，以及缺口样本。

用法：
    python tools/audit_coverage_gap.py --db policy_crawler.db \
        --hunan-xlsx logs/regional/hunan_2026q2_price.xlsx \
        --report logs/coverage_gap.json
"""
import argparse
import collections
import io
import json
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if os.path.join(ROOT, "tools") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "tools"))

import xlsx_lite  # noqa: E402
from normalize import molecule_key, norm_roman, to_half_width  # noqa: E402

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass


def norm_approval(text):
    if not text:
        return ""
    return re.sub(r"[\s\u3000]+", "",
                  norm_roman(to_half_width(str(text)))).upper()


def hunan_rows(path):
    """返回 (批准文号, 产品名称, 剂型, 规格, 厂家, 药品统一编码) 列表。"""
    rows = xlsx_lite.read_rows(path, 0)
    header_at = None
    for idx, row in enumerate(rows[:30]):
        if row and row[0].strip() == "序号" and any("批准文号" in c for c in row):
            header_at = idx
            break
    if header_at is None:
        raise SystemExit("未找到湖南表表头")
    out = []
    for row in rows[header_at + 1:]:
        if len(row) < 10 or not any(c.strip() for c in row):
            continue
        out.append((norm_approval(row[9]), row[1].strip(), row[5].strip(),
                    row[6].strip(), row[8].strip(), row[3].strip()))
    return out


def audit(db_path, hunan_xlsx=None):
    db = sqlite3.connect(db_path)
    report = {}

    regs = {norm_approval(r[0]) for r in db.execute(
        "SELECT approval_number FROM drug_registration "
        "WHERE approval_number IS NOT NULL AND approval_number<>''")}
    mol_keys = set()
    for (name,) in db.execute("SELECT generic_name FROM drug_molecule"):
        key = molecule_key(name)
        if key:
            mol_keys.add(key)
    report["library"] = {
        "products": db.execute("SELECT COUNT(*) FROM drug_product").fetchone()[0],
        "registrations": len(regs),
        "molecules": len(mol_keys),
    }

    # 医保目录：药名清单（有名字，无批准文号）
    catalog_names = [r[0] for r in db.execute(
        "SELECT DISTINCT name FROM insurance_catalog_entry WHERE name<>''")]
    cat_keys = {molecule_key(n) for n in catalog_names}
    cat_keys.discard("")
    report["catalog"] = {
        "entries": db.execute(
            "SELECT COUNT(*) FROM insurance_catalog_entry").fetchone()[0],
        "unique_names": len(set(catalog_names)),
        "names_covered_by_library": len(cat_keys & mol_keys),
        "names_missing": len(cat_keys - mol_keys),
    }

    if hunan_xlsx and os.path.exists(hunan_xlsx):
        rows = hunan_rows(hunan_xlsx)
        approvals = collections.OrderedDict()
        codes = set()
        names = set()
        for approval, name, form, spec, mfr, code in rows:
            if approval and approval not in approvals:
                approvals[approval] = (name, form, spec, mfr)
            if code:
                codes.add(code)
            if name:
                names.add(molecule_key(name))
        names.discard("")
        new_approvals = [a for a in approvals if a not in regs]
        report["hunan_table"] = {
            "rows": len(rows),
            "unique_approvals": len(approvals),
            "unique_drug_codes": len(codes),
            "unique_names": len(names),
            "approvals_already_in_library": len(approvals) - len(new_approvals),
            "new_approvals_available": len(new_approvals),
            "new_registration_ratio": round(
                len(approvals) / max(1, len(regs)), 2),
            "catalog_names_covered_after_import": len(cat_keys & names),
        }
        report["hunan_new_sample"] = [
            {"approval_number": a, "name": approvals[a][0],
             "spec": approvals[a][2], "manufacturer": approvals[a][3]}
            for a in new_approvals[:10]]

    gaps = sorted(cat_keys - mol_keys)
    report["catalog_missing_sample"] = gaps[:30]
    db.close()
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description="品种库覆盖缺口审计")
    ap.add_argument("--db", default="policy_crawler.db")
    ap.add_argument("--hunan-xlsx", default="")
    ap.add_argument("--report", default="logs/coverage_gap.json")
    args = ap.parse_args(argv)
    report = audit(args.db, args.hunan_xlsx or None)
    if args.report:
        os.makedirs(os.path.dirname(os.path.abspath(args.report)),
                    exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("COVERAGE_AUDIT_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
