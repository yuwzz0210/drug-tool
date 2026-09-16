# -*- coding: utf-8 -*-
"""导出站点快照 data/drugs.json（v1：直接消费 drug_profile 视图）。

视图负责“最新值”口径；数组类字段（适应症/机制/文号/医保/集采/政策）在导出时
按 product_id 聚合组装。保留旧字段（indications/mechanisms/insurance/registrations
/package_insert_url…）以兼容现有前端。

用法（policy-crawler 目录下）：
    python tools/export_drugs_snapshot.py --db policy_crawler.db --out ../../repo/data/drugs.json
"""
import argparse
import json
import os
import sqlite3
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _rows_by(db, sql, key=0):
    out = {}
    for r in db.execute(sql):
        out.setdefault(r[key], []).append(r)
    return out


def is_focus(rec):
    """网站快照收录口径（保持站点轻量）：

    收录有「准入类」事实的品种——医保 / 国谈 / 集采 / 双通道 / 政策关联，
    或带适应症说明书（可读的一药一页）。
    仅有一条省级挂网价的普通品种不进快照（这类在库里已有 2.4 万条，
    属于"库内资产"，需要时再按需查询，避免站点 JSON 膨胀）。
    """
    return bool(rec.get("insurance_details") or rec.get("vbp_events")
                or rec.get("negotiation") or rec.get("dual_channel")
                or rec.get("policy_links")
                or rec.get("indications") or rec.get("usage_dosage"))


def focus_rank(rec):
    """截断时的优先级：国谈/医保/集采/双通道/政策 逐级下降。"""
    return (
        1 if rec.get("negotiation") else 0,
        1 if rec.get("insurance_details") else 0,
        1 if rec.get("vbp_events") else 0,
        1 if rec.get("dual_channel") else 0,
        1 if rec.get("policy_links") else 0,
        1 if rec.get("indications") else 0,
    )


def export_snapshot(db_path, out_path, mode="focus", max_rows=8000):
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    view_rows = db.execute("SELECT * FROM drug_profile ORDER BY product_id"
                           ).fetchall()

    indications = _rows_by(
        db, "SELECT product_id, indication_text FROM drug_indication")
    mechanisms = _rows_by(
        db, "SELECT product_id, mechanism_text FROM drug_mechanism")
    ingredients = _rows_by(
        db, "SELECT product_id, ingredient_name, strength, unit "
            "FROM drug_ingredient")
    regs = _rows_by(
        db, "SELECT product_id, approval_number, status, registration_date, "
            "holder, source_url FROM drug_registration")
    leaflet_by_approval = {}
    for r in db.execute("SELECT approval_number, pdf_url, source_url, "
                        "leaflet_date FROM drug_leaflet"):
        if r["approval_number"]:
            leaflet_by_approval[r["approval_number"]] = dict(r)
    insurance = _rows_by(db, """
        SELECT e.product_id, e.region, e.category, e.insurance_code,
               e.payment_scope, e.reimbursement_ratio, e.supplement_status,
               e.price, e.effective_date, e.is_current, c.version_name
        FROM drug_insurance_entry e
        LEFT JOIN insurance_catalog c ON c.catalog_id=e.catalog_id""")
    vbp = _rows_by(db, """
        SELECT product_id, batch, batch_seq, variety_name, spec_pack,
               supplier, price, price_unit, source
        FROM procurement_result WHERE product_id IS NOT NULL""")
    policies = _rows_by(db, """
        SELECT r.product_id, p.id, p.title, p.publish_date, p.source_url,
               p.issuing_authority
        FROM policy_drug_relation r JOIN policies p ON p.id=r.policy_id""")
    extra = {r[0]: r[1] for r in db.execute(
        "SELECT product_id, extra_data FROM drug_product")}
    # Wave-1 新增：按品种（molecule）维度聚合的国谈与双通道，
    # 供前端在「一药一页」里展示谈判/双通道/挂网价信息。
    negotiation = _rows_by(db, """
        SELECT molecule_id, drug_name, category, pay_standard,
               agreement_period, batch_year, source_url
        FROM negotiation_result WHERE molecule_id IS NOT NULL""")
    dual_channel = _rows_by(db, """
        SELECT molecule_id, region, drug_name, dosage_form, specification,
               status, effective_date, batch, source_url
        FROM dual_channel WHERE molecule_id IS NOT NULL""")
    prices = _rows_by(db, """
        SELECT product_id, price_type, price, unit, region, batch,
               effective_date, source_url, notes
        FROM price_history""")

    out = []
    _skipped = []
    for v in view_rows:
        pid = v["product_id"]
        reg_list = []
        for r in regs.get(pid, []):
            leaf = leaflet_by_approval.get(r["approval_number"], {})
            reg_list.append({
                "approval_number": r["approval_number"],
                "status": r["status"], "registration_date": r["registration_date"],
                "holder": r["holder"],
                "leaflet_pdf_url": leaf.get("pdf_url", ""),
                "leaflet_date": leaf.get("leaflet_date", ""),
            })
        rec = dict(v)
        rec.update({
            "is_verified": False,
            "indications": [r["indication_text"] for r in indications.get(pid, [])],
            "mechanisms": [r["mechanism_text"] for r in mechanisms.get(pid, [])],
            "ingredients": [
                {"name": r["ingredient_name"], "strength": r["strength"],
                 "unit": r["unit"]} for r in ingredients.get(pid, [])],
            "registrations": reg_list,
            "insurance": [
                {"region": r["region"], "category": r["category"],
                 "insurance_code": r["insurance_code"],
                 "payment_scope": r["payment_scope"],
                 "reimbursement_ratio": r["reimbursement_ratio"],
                 "supplement_status": r["supplement_status"],
                 "price": r["price"], "effective_date": r["effective_date"],
                 "is_current": r["is_current"],
                 "catalog_version": r["version_name"]}
                for r in insurance.get(pid, [])],
            "vbp_events": [
                {"batch": r["batch"], "seq": r["batch_seq"],
                 "variety_name": r["variety_name"], "spec_pack": r["spec_pack"],
                 "supplier": r["supplier"], "price": r["price"],
                 "price_unit": r["price_unit"], "source": r["source"]}
                for r in vbp.get(pid, [])],
            "policy_links": [
                {"id": r["id"], "title": r["title"],
                 "publish_date": r["publish_date"],
                 "source_url": r["source_url"],
                 "issuing_authority": r["issuing_authority"]}
                for r in policies.get(pid, [])],
            "negotiation": [
                {"drug_name": r["drug_name"], "category": r["category"],
                 "pay_standard": r["pay_standard"],
                 "agreement_period": r["agreement_period"],
                 "batch_year": r["batch_year"],
                 "source_url": r["source_url"]}
                for r in negotiation.get(v["molecule_id"], [])],
            "dual_channel": [
                {"region": r["region"], "drug_name": r["drug_name"],
                 "dosage_form": r["dosage_form"],
                 "specification": r["specification"],
                 "status": r["status"],
                 "effective_date": r["effective_date"],
                 "batch": r["batch"], "source_url": r["source_url"]}
                for r in dual_channel.get(v["molecule_id"], [])],
            "prices": [
                {"price_type": r["price_type"], "price": r["price"],
                 "unit": r["unit"], "region": r["region"],
                 "batch": r["batch"],
                 "effective_date": r["effective_date"],
                 "source_url": r["source_url"], "notes": r["notes"]}
                for r in prices.get(pid, [])],
            "package_insert_url": v["leaflet_url"] or "",
            "leaflet_source_url": v["source_url"] or "",
            "extra_data": json.loads(extra.get(pid) or "{}"),
        })
        if mode == "full" or is_focus(rec):
            out.append(rec)
        else:
            _skipped.append(pid)
    if max_rows and len(out) > max_rows:
        out.sort(key=focus_rank, reverse=True)
        out = out[:max_rows]
    db.close()
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return len(out), len(_skipped)


def main(argv=None):
    parser = argparse.ArgumentParser(description="导出 data/drugs.json 站点快照")
    parser.add_argument("--db", default="policy_crawler.db")
    parser.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "repo", "data", "drugs.json"))
    parser.add_argument("--mode", choices=("focus", "full"), default="focus",
                        help="focus=仅导出有政策/价格/医保/集采关联的品种（默认）")
    parser.add_argument("--max-rows", type=int, default=8000,
                        help="快照行数上限，0 表示不限制")
    args = parser.parse_args(argv)
    n, skipped = export_snapshot(args.db, args.out, mode=args.mode,
                                 max_rows=args.max_rows)
    print("drugs.json 已导出:", n, "条 →", args.out,
          "| 过滤掉（无关联品种）:", skipped)
    print("文件大小: %.1f MB" % (os.path.getsize(args.out) / 1048576.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
