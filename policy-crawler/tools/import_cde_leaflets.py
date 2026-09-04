# -*- coding: utf-8 -*-
"""把 CDE 说明书采集结果（JSONL + PDF）回写主库（步骤3 入库层）。

写入内容（均为官方公开说明书/目录集元数据，记录来源便于复核）:
    drug_leaflet   : 一批准文号一条解析记录（PDF 全文 + 关键节 + 冷链/途径）
    drug_product   : package_insert_url / source_url
    drug_indication: 【适应症】
    drug_mechanism : 【药理毒理】
    drug_molecule  : route / cold_chain / mechanism_summary（仅空值回填）

用法:
    python tools/import_cde_leaflets.py --db policy_crawler.db \
        --results ../logs/cde_full.jsonl --dry-run
    python tools/import_cde_leaflets.py --db policy_crawler.db \
        --results ../logs/cde_full.jsonl
"""
import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from collectors.cde_leaflets import (  # noqa: E402
    DETAIL_URL,
    DOWNLOAD_URL,
    classify_route,
    classify_storage,
    extract_leaflet_date,
    parse_leaflet_sections,
)
from models import DRUG_SCHEMA  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

log = logging.getLogger("policy-crawler.tools.import_cde_leaflets")

SECTION_KEYS = (
    "适应症", "用法用量", "不良反应", "禁忌", "注意事项",
    "孕妇及哺乳期妇女用药", "儿童用药", "老年用药", "药物相互作用",
    "药物过量", "药理毒理", "药代动力学", "贮藏", "有效期", "执行标准",
    "生产企业",
)


def leaflet_payload(rec, parsed):
    """Build the normalized payload for one CDE catalog record."""
    detail = rec.get("detail") or {}
    row = (rec.get("rows") or [{}])[0]
    sections = parsed.get("sections") or {}
    rid = (rec.get("catalog_rid") or row.get("idCode") or detail.get("idCode")
           or (row.get("href") or "").rsplit("/", 1)[-1]
           or rec.get("acceptcode") or "")
    pdf_url = (rec.get("pdf_url")
               or DOWNLOAD_URL.format(rec.get("file_id") or ""))
    source_url = (rec.get("source_url") or DETAIL_URL.format(rid))
    return {
        "approval_number": rec.get("approval_number") or rec.get("pzwh", ""),
        "product_id": rec.get("product_id"),
        "catalog_rid": rid,
        "pdf_url": pdf_url,
        "source_url": source_url,
        "filename": rec.get("filename", ""),
        "route": classify_route(detail.get("gytj") or ""),
        "storage": sections.get("贮藏", ""),
        "cold_chain": classify_storage(sections.get("贮藏", "")),
        "usage_dosage": sections.get("用法用量", ""),
        "indications": sections.get("适应症", ""),
        "leaflet_date": extract_leaflet_date(parsed.get("text", "")),
        "sections_json": json.dumps(
            {k: sections.get(k, "") for k in SECTION_KEYS
             if sections.get(k)}, ensure_ascii=False),
        "raw_text": parsed.get("text", ""),
        "generic_name": rec.get("generic_name", ""),
        "specification": rec.get("specification", ""),
    }


def import_one(db, payload, dry_run=False, now=None):
    """Upsert one leaflet payload; returns dict of per-layer effects."""
    now = now or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out = {"approval_number": payload["approval_number"], "effects": []}
    pzwh = payload["approval_number"]
    if not pzwh or not payload["catalog_rid"]:
        out["effects"].append("skip:missing-key")
        return out

    if payload.get("product_id"):
        prod = db.execute(
            "SELECT product_id, molecule_id FROM drug_product "
            "WHERE product_id=?", (payload["product_id"],)).fetchone()
    else:
        prod = db.execute(
            """SELECT p.product_id, p.molecule_id
               FROM drug_registration r
               JOIN drug_product p ON p.product_id = r.product_id
               WHERE r.approval_number = ?""", (pzwh,)).fetchone()
    if not prod:
        out["effects"].append("unlinked:no-registration")
        return out
    product_id, molecule_id = prod

    def run(sql, params):
        if not dry_run:
            db.execute(sql, params)
        return sql

    run("""
        INSERT INTO drug_leaflet (
            product_id, approval_number, catalog_rid, pdf_url, source_url,
            filename, route, storage, cold_chain, usage_dosage, indications,
            leaflet_date, sections_json, raw_text, fetched_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(approval_number, catalog_rid) DO UPDATE SET
            pdf_url=excluded.pdf_url, source_url=excluded.source_url,
            filename=excluded.filename, route=excluded.route,
            storage=excluded.storage, cold_chain=excluded.cold_chain,
            usage_dosage=excluded.usage_dosage,
            indications=excluded.indications,
            leaflet_date=excluded.leaflet_date,
            sections_json=excluded.sections_json,
            raw_text=excluded.raw_text, updated_at=excluded.updated_at
        """, (product_id, pzwh, payload["catalog_rid"], payload["pdf_url"],
              payload["source_url"], payload["filename"], payload["route"],
              payload["storage"], payload["cold_chain"],
              payload["usage_dosage"], payload["indications"],
              payload["leaflet_date"], payload["sections_json"],
              payload["raw_text"], now, now))
    out["effects"].append("leaflet")

    run("""UPDATE drug_product
           SET package_insert_url=?, source_url=?, updated_at=?
           WHERE product_id=?""",
        (payload["pdf_url"], payload["source_url"], now, product_id))
    out["effects"].append("product-url")

    if payload["indications"].strip():
        dup = db.execute(
            """SELECT 1 FROM drug_indication
               WHERE product_id=? AND TRIM(indication_text)=TRIM(?)""",
            (product_id, payload["indications"])).fetchone()
        if not dup:
            run("""INSERT INTO drug_indication
                   (product_id, indication_text, indication_norm,
                    approval_status, effective_date, is_current)
                   VALUES (?,?,?, '说明书(CDE)', ?, 1)""",
                (product_id, payload["indications"],
                 payload["indications"][:500],
                 payload.get("leaflet_date") or ""))
            out["effects"].append("indication")

    mech = (json.loads(payload["sections_json"] or "{}") or {})
    mech_text = mech.get("药理毒理") or ""
    if mech_text.strip():
        dup = db.execute(
            """SELECT 1 FROM drug_mechanism
               WHERE product_id=? AND TRIM(mechanism_text)=TRIM(?)""",
            (product_id, mech_text)).fetchone()
        if not dup:
            run("""INSERT INTO drug_mechanism
                   (product_id, target_name, mechanism_text, is_current)
                   VALUES (?,?,?,1)""",
                (product_id, "", mech_text))
            out["effects"].append("mechanism")

    if molecule_id:
        mol = db.execute(
            "SELECT route, cold_chain, mechanism_summary FROM drug_molecule "
            "WHERE molecule_id=?", (molecule_id,)).fetchone()
        sets, params = [], []
        if mol:
            if payload["route"] and not (mol[0] or "").strip():
                sets.append("route=?")
                params.append(payload["route"])
            if payload["cold_chain"] and not (mol[1] or "").strip():
                sets.append("cold_chain=?")
                params.append(payload["cold_chain"])
            if mech_text and not (mol[2] or "").strip():
                sets.append("mechanism_summary=?")
                params.append(mech_text[:300])
        if sets:
            sets.append("reviewed_at=?")
            params.append(now)
            params.append(molecule_id)
            run("UPDATE drug_molecule SET %s WHERE molecule_id=?"
                % ", ".join(sets), params)
            out["effects"].append("molecule-fill")

    return out


def import_results(results_path, db_path, dry_run=False, limit=None):
    """Read collector JSONL and write all 'ok' records into the DB."""
    db = sqlite3.connect(db_path)
    db.execute("PRAGMA foreign_keys=ON")
    if not dry_run:
        db.executescript(DRUG_SCHEMA)
    stats = {"ok_records": 0, "imported": 0, "unlinked": 0,
             "missing_pdf": 0, "needs_ocr": 0, "errors": 0}
    unlinked = []
    with open(results_path, "r", encoding="utf-8") as fh:
        lines = [l for l in fh if l.strip()]
    if limit:
        lines = lines[:limit]
    for line in lines:
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("status") != "ok":
            continue
        stats["ok_records"] += 1
        dest = rec.get("dest") or ""
        parsed = None
        if dest and os.path.exists(dest):
            parsed = parse_leaflet_sections(dest)
        if parsed is None or not parsed.get("ok"):
            stats["missing_pdf"] += 1
            log.warning("pdf missing/unparsed for %s (%s)",
                        rec.get("pzwh"), dest)
            continue
        if not (parsed.get("text") or "").strip():
            stats["needs_ocr"] += 1
            log.warning("pdf has no extractable text (needs OCR): %s",
                        rec.get("pzwh"))
            continue
        try:
            payload = leaflet_payload(rec, parsed)
            eff = import_one(db, payload, dry_run=dry_run)
            if not dry_run:
                db.commit()
            if "unlinked:no-registration" in eff["effects"]:
                stats["unlinked"] += 1
                unlinked.append(rec.get("pzwh"))
            elif "leaflet" in eff["effects"]:
                stats["imported"] += 1
            log.info("%s -> %s", rec.get("pzwh"),
                     ",".join(eff["effects"]))
        except Exception as exc:
            stats["errors"] += 1
            log.exception("import failed for %s", rec.get("pzwh"))
    db.close()
    return stats, unlinked


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="policy_crawler.db")
    ap.add_argument("--results", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    stats, unlinked = import_results(args.results, args.db,
                                     dry_run=args.dry_run, limit=args.limit)
    print("STATS", json.dumps(stats, ensure_ascii=False))
    if unlinked:
        print("UNLINKED_COUNT", len(unlinked))
        print("UNLINKED", json.dumps(unlinked[:30], ensure_ascii=False))


if __name__ == "__main__":
    main()
