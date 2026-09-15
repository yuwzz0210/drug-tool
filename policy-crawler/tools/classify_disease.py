# -*- coding: utf-8 -*-
"""病种/治疗领域分类：按说明书与目录适应症文本，为 drug_molecule 打标。

数据来源（全部为库内既有官方文本，不外链、不推测）：
- drug_leaflet.indications（说明书适应症原文，置信度=高）
- drug_indication.indication_text（目录/结构化适应症短句，置信度=中）
- drug_molecule.extra_indications（补充适应症，置信度=中）
- 仅命中治疗领域关键词时置信度=低

规则见 disease_rules.py（RULES_VERSION 记录版本）。
人工校准保护：classification_source 以「人工」开头的分子默认跳过，
除非显式 --overwrite-manual。

用法：
    python tools/classify_disease.py --db policy_crawler.db
    python tools/classify_disease.py --db policy_crawler.db --dry-run
"""
import argparse
import io
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from disease_rules import (  # noqa: E402
    RULES_VERSION,
    classify,
    classify_by_name,
    is_clean_text,
    is_indication_section,
)
from normalize import molecule_key  # noqa: E402

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass


LEAFLET_SQL = """
    SELECT DISTINCT l.indications FROM drug_leaflet l
      JOIN drug_product p ON p.product_id = l.product_id
     WHERE p.molecule_id = ? AND l.indications IS NOT NULL
       AND TRIM(l.indications) <> ''
"""

INDICATION_SQL = """
    SELECT DISTINCT di.indication_text FROM drug_indication di
      JOIN drug_product p ON p.product_id = di.product_id
     WHERE p.molecule_id = ? AND di.indication_text IS NOT NULL
       AND TRIM(di.indication_text) <> ''
"""


def _texts(db, sql, molecule_id):
    return [r[0] for r in db.execute(sql, (molecule_id,)) if r[0]]


def classify_molecule(db, molecule_id, generic_name="", extra_indications=""):
    """返回该分子的分类结果（含来源文本级别）。

    顺序：说明书适应症（高）→ 目录适应症短句（中）→ 补充适应症（中）
    → 说明书/目录领域级兜底（低）→ 药名词干推定（低）。
    说明书段落先经 is_indication_section 校验，抽错段落的 PDF 自动跳过。
    """
    leaflet_texts = [t for t in _texts(db, LEAFLET_SQL, molecule_id)
                     if is_indication_section(t)]
    indication_texts = [t for t in _texts(db, INDICATION_SQL, molecule_id)
                        if is_clean_text(t)]

    for label, texts, official in (
            ("leaflet", leaflet_texts, True),
            ("indication", indication_texts, False),
            ("extra_indications", [extra_indications] if extra_indications
             else [], False)):
        if not texts:
            continue
        result = classify(" ".join(texts), official=official)
        if result["disease"]:
            result["source_level"] = label
            return result

    # 领域级兜底（低置信度）
    fallback = classify(" ".join(leaflet_texts + indication_texts +
                                 ([extra_indications] if extra_indications
                                  else [])), official=False)
    if fallback["area"]:
        fallback["source_level"] = "fallback"
        return fallback

    # 药名词干推定（低置信度，来源标记 inn_stem）
    by_name = classify_by_name(generic_name)
    by_name["source_level"] = "inn_stem" if by_name["area"] else "none"
    return by_name


def run(db_path, dry_run=False, overwrite_manual=False, report_path=None):
    db = sqlite3.connect(db_path)
    rows = db.execute(
        "SELECT molecule_id, generic_name, COALESCE(extra_indications,''), "
        "COALESCE(classification_source,'') FROM drug_molecule "
        "ORDER BY molecule_id").fetchall()

    stats = {"molecules": len(rows), "classified": 0, "area_only": 0,
             "unclassified": 0, "skipped_manual": 0, "updated": 0,
             "inherited": 0, "by_area": {}, "by_confidence": {},
             "by_source": {}}
    unclassified = []
    results = {}
    for molecule_id, name, extra, current_source in rows:
        if current_source.startswith("人工") and not overwrite_manual:
            stats["skipped_manual"] += 1
            continue
        result = classify_molecule(db, molecule_id, name, extra)
        results[molecule_id] = (name, result)

    # 通过：同词干分子（如「注射用曲妥珠单抗」/「曲妥珠单抗」、「吡格列酮二甲双胍
    # 片(15mg/850mg)」/「吡格列酮二甲双胍」）继承已确证分类，避免同名分子重复行缺标。
    EVIDENCE_LEVELS = ("leaflet", "indication", "extra_indications")
    key_index = {}
    for molecule_id, (name, result) in results.items():
        if result["disease"] and result.get("source_level") in EVIDENCE_LEVELS:
            key = molecule_key(name)
            if key:
                key_index.setdefault(key, result)

    for molecule_id, (name, result) in sorted(results.items()):
        weak = result.get("source_level") not in EVIDENCE_LEVELS
        if weak:
            key = molecule_key(name)
            inherited = key_index.get(key) if key else None
            if inherited and inherited["disease"]:
                origin = inherited.get("inherited_from") or ""
                result = dict(inherited)
                result.update({"inherited_from": origin or "同词干已确证分子",
                               "source_level": "inherit"})
                stats["inherited"] += 1
        if not result["area"]:
            stats["unclassified"] += 1
            if len(unclassified) < 200:
                unclassified.append({"molecule_id": molecule_id,
                                     "generic_name": name})
            if not dry_run:
                # 规则引擎判定为「无法分类」时清空旧值，避免残留过期分类
                db.execute("""
                    UPDATE drug_molecule
                       SET therapeutic_area='', disease='', sub_disease='',
                           classification_source='', classification_confidence=''
                     WHERE molecule_id=?""", (molecule_id,))
            continue
        stats["classified"] += 1
        if not result["disease"]:
            stats["area_only"] += 1
        stats["by_area"][result["area"]] = \
            stats["by_area"].get(result["area"], 0) + 1
        conf = result["confidence"] or "低"
        stats["by_confidence"][conf] = stats["by_confidence"].get(conf, 0) + 1
        level = result.get("source_level", "")
        stats["by_source"][level] = stats["by_source"].get(level, 0) + 1

        source = result["version"]
        if len(result["hits"]) > 1:
            source += "；命中病种=" + "|".join(result["hits"][:6])
        source += "；来源=" + level
        if result.get("inherited_from"):
            source += "；继承自=" + result["inherited_from"]
        if not dry_run:
            db.execute("""
                UPDATE drug_molecule
                   SET therapeutic_area=?, disease=?, sub_disease=?,
                       classification_source=?, classification_confidence=?,
                       updated_at=datetime('now','localtime')
                 WHERE molecule_id=?""",
                       (result["area"], result["disease"],
                        result["sub_disease"], source,
                        result["confidence"] or "低", molecule_id))
            stats["updated"] += 1
    if not dry_run:
        db.commit()
    if report_path:
        os.makedirs(os.path.dirname(os.path.abspath(report_path)),
                    exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump({"stats": stats, "unclassified_sample": unclassified,
                       "rules_version": RULES_VERSION}, fh,
                      ensure_ascii=False, indent=2)
    db.close()
    return stats


def main(argv=None):
    ap = argparse.ArgumentParser(description="病种/领域分类")
    ap.add_argument("--db", default="policy_crawler.db")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--overwrite-manual", action="store_true")
    ap.add_argument("--report", default="")
    args = ap.parse_args(argv)
    stats = run(args.db, dry_run=args.dry_run,
                overwrite_manual=args.overwrite_manual,
                report_path=args.report or None)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print("CLASSIFY_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
