# -*- coding: utf-8 -*-
"""回填完成后输出 CDE 说明书覆盖报告。

按文号前缀(H/J/S/Z)、是否命中目录集、是否有说明书 PDF 分桶，并把
"查无记录"清单导出，供下一通道（CDE 上市药品信息/受理号）补漏。

用法:
    python tools/audit_cde_coverage.py --results logs/cde_full.jsonl \
        --db policy_crawler.db
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


def prefix_of(pzwh):
    m = re.search(r"[HJSZ](?=\d)", pzwh or "")
    return m.group(0) if m else "?"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", required=True)
    ap.add_argument("--db", default="policy_crawler.db")
    ap.add_argument("--out", default="logs/cde_coverage_report.txt")
    args = ap.parse_args()

    db = sqlite3.connect(args.db)
    info = {}
    for r in db.execute("""
            SELECT r.approval_number, p.product_id, p.generic_name,
                   p.dosage_form, p.specification, m.generic_name
            FROM drug_registration r
            JOIN drug_product p ON p.product_id = r.product_id
            LEFT JOIN drug_molecule m ON m.molecule_id = p.molecule_id"""):
        info[r[0]] = {"product_id": r[1], "generic_name": r[2] or "",
                      "dosage_form": r[3] or "", "specification": r[4] or "",
                      "molecule": r[5] or ""}
    db.close()

    statuses = {}
    ok_list, nf_list, nl_list = [], [], []
    with open(args.results, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            pz = rec.get("pzwh")
            st = rec.get("status")
            statuses[st] = statuses.get(st, 0) + 1
            item = {"pzwh": pz, "prefix": prefix_of(pz), "info": info.get(pz)}
            (ok_list if st == "ok" else nf_list if st == "not_found"
             else nl_list if st == "no_leaflet" else []).append(item)

    by_status_prefix = {}
    for bucket, lst in (("ok", ok_list), ("not_found", nf_list),
                        ("no_leaflet", nl_list)):
        for it in lst:
            key = (bucket, it["prefix"])
            by_status_prefix[key] = by_status_prefix.get(key, 0) + 1

    lines = []
    lines.append("=== CDE 说明书覆盖报告 ===")
    lines.append("总处理: %d | ok=%d | no_leaflet=%d | not_found=%d" % (
        sum(statuses.values()), len(ok_list), len(nl_list), len(nf_list)))
    lines.append("按文号前缀/状态:")
    for prefix in ("H", "J", "S", "Z", "?"):
        row = "  %s: ok=%d no_leaflet=%d not_found=%d" % (
            prefix, by_status_prefix.get(("ok", prefix), 0),
            by_status_prefix.get(("no_leaflet", prefix), 0),
            by_status_prefix.get(("not_found", prefix), 0))
        lines.append(row)
    if ok_list:
        lines.append("\n已获取说明书 PDF(%d):" % len(ok_list))
        for it in ok_list[:80]:
            inf = it["info"] or {}
            lines.append("  %s | %s | %s %s" % (
                it["pzwh"], inf.get("molecule") or inf.get("generic_name"),
                inf.get("dosage_form"), inf.get("specification")))
    if nf_list:
        lines.append("\n目录集无记录-待补通道(%d):" % len(nf_list))
        for it in nf_list[:100]:
            inf = it["info"] or {}
            lines.append("  %s | %s | %s %s" % (
                it["pzwh"], inf.get("molecule") or inf.get("generic_name"),
                inf.get("dosage_form"), inf.get("specification")))
    report = "\n".join(lines)
    print(report)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(report)
    print("\nSAVED", args.out)


if __name__ == "__main__":
    main()
