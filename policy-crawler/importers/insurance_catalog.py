# -*- coding: utf-8 -*-
"""国家医保药品目录导入器（版本化）。

流程：
    1. 从国家医保局通知公告列表页发现最新《国家基本医疗保险…药品目录》通知；
    2. 下载官方 PDF（全量目录 + 谈判药品支付标准）；
    3. 解析五大区块（西药 / 中成药 / 谈判西药 / 谈判中成药 / 竞价）；
    4. 写入 insurance_catalog（目录版本）+ insurance_catalog_entry（全量条目）；
    5. 与 drug_product 按「通用名 + 剂型」匹配，写入 drug_insurance_entry（品种医保状态）。

用法：
    python -m importers.insurance_catalog --auto --db policy_crawler.db
    python -m importers.insurance_catalog --pdf 目录.pdf --db policy_crawler.db --version "2025年"
"""
import argparse
import datetime
import json
import logging
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from drugstore import DrugStore, _norm  # noqa: E402
from models import InsuranceCatalog  # noqa: E402


log = logging.getLogger("policy-crawler.importers.catalog")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
NHSA_LIST_URL = "https://www.nhsa.gov.cn/col/col104/index.html"
NHSA_BASE = "https://www.nhsa.gov.cn"

# 名称归一化：剂型后缀（用于品种匹配时剥离）
FORM_SUFFIXES = (
    "片", "胶囊", "软胶囊", "注射液", "注射剂", "颗粒", "口服液", "口服溶液",
    "滴眼液", "栓剂", "气雾剂", "散剂", "丸", "丸剂", "糖浆", "干混悬剂",
    "喷雾剂", "凝胶剂", "乳膏剂", "软膏剂", "贴膏剂", "贴剂", "混悬剂",
    "溶液剂", "滴剂", "洗剂", "搽剂", "膜剂", "植入剂", "外用制剂",
)

SALT_PREFIXES = (
    "盐酸", "甲磺酸", "苯磺酸", "枸橼酸", "柠檬酸", "马来酸", "富马酸",
    "酒石酸", "琥珀酸", "磷酸", "醋酸", "硫酸", "氢溴酸", "硝酸", "乳酸",
    "依地酸", "双羟萘酸", "甲苯磺酸", "对甲苯磺酸", "乙磺酸",
)

ROMAN_NUMERALS = "ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅰⅱⅲⅳⅴⅵⅶⅷⅸⅹ"


# ---------- 发现与下载 ----------

def find_catalog_notice(list_html):
    """从 NHSA 通知公告列表页定位《国家基本医疗保险…药品目录》通知。"""
    for m in re.finditer(
        r'<a[^>]*href="(/art/\d{4}/\d+/\d+/art_\d+_\d+\.html)"[^>]*>(.*?)</a>',
        list_html,
        re.S,
    ):
        href, title = m.group(1), re.sub(r"\s+", " ", m.group(2)).strip()
        if "药品目录" in title and "商业健康保险" not in title:
            return title, NHSA_BASE + href
    return None, None


def find_catalog_attachment(detail_html):
    """从通知详情页提取主目录 PDF 下载链接（跳过商保创新药目录）。"""
    best = None
    for m in re.finditer(
        r'href="(/module/download/downfile\.jsp\?[^"]+)"[^>]*>([^<]+)</a>',
        detail_html,
    ):
        href, label = m.group(1), m.group(2).strip()
        if "药品目录" in label and "商业健康保险" not in label:
            best = label, NHSA_BASE + href
    return best


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def download_catalog_pdf(save_path, list_html=None, detail_html=None):
    """自动发现并下载最新目录 PDF，返回 (版本名, 本地路径)。"""
    list_html = list_html or _fetch(NHSA_LIST_URL).decode("utf-8", "replace")
    title, detail_url = find_catalog_notice(list_html)
    if not detail_url:
        raise RuntimeError("未在 NHSA 列表页找到药品目录通知")
    detail_html = detail_html or _fetch(detail_url).decode("utf-8", "replace")
    label, pdf_url = find_catalog_attachment(detail_html)
    if not pdf_url:
        raise RuntimeError("通知详情页未找到目录 PDF 附件")
    data = _fetch(pdf_url)
    with open(save_path, "wb") as f:
        f.write(data)
    version = re.sub(r"\s+", "", label)
    return version, save_path


# ---------- PDF 解析 ----------

def _build_colmap(header):
    colmap = {}
    for idx, cell in enumerate(header or []):
        text = (cell or "").replace("\n", "")
        if "编号" in text:
            colmap["code"] = idx
        elif "药品名称" in text:
            colmap["name"] = idx
        elif "剂型" in text:
            colmap["form"] = idx
        elif "医保支付标准" in text:
            colmap["pay"] = idx
        elif "备注" in text:
            colmap["note"] = idx
        elif "有效期" in text:
            colmap["valid"] = idx
    return colmap


def _detect_section(header):
    head = "".join((c or "") for c in (header or []))
    if "序号" in head and "药品名称" in head and "编号" not in head and "分类代码" not in head:
        return "index"  # 目录索引页（序号|药品名称 双栏）或中药饮片页
    if "饮片名称" in head:
        return "index"
    if "医保支付标准" in head:
        if "协议有效期" in head:
            return "谈判"
        return "竞价"
    if "剂型" in head:
        return "西药"
    return "中成药"


def _cell(row, colmap, key):
    idx = colmap.get(key)
    if idx is None or idx >= len(row):
        return ""
    return _norm(row[idx])


def _category_from_code(cell):
    text = _norm(cell)
    if "甲" in text:
        return "甲类"
    if "乙" in text:
        return "乙类"
    return ""


def _row_category(row, colmap):
    """目录表格存在两种布局：编号单元格含「乙 ★(18)」，或「乙」「★(18)」分列。"""
    code_idx = colmap.get("code")
    name_idx = colmap.get("name")
    candidates = {
        code_idx,
        (code_idx or 1) - 1,
        (name_idx or 2) - 1,
        (name_idx or 2) - 2,
    }
    for i in candidates:
        if i is not None and 0 <= i < len(row):
            cat = _category_from_code(row[i])
            if cat:
                return cat
    return ""


def _code_from_cell(cell):
    m = re.search(r"\d+", _norm(cell))
    return m.group(0) if m else ""


def _parse_valid_range(text):
    """把「2026年1月1日至2027年12月31日」拆成 (生效日, 失效日)。"""
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日?\s*至\s*(\d{4})年(\d{1,2})月(\d{1,2})日?", text or "")
    if not m:
        return "", ""
    y1, mo1, d1, y2, mo2, d2 = m.groups()
    return ("%s-%02d-%02d" % (y1, int(mo1), int(d1)),
            "%s-%02d-%02d" % (y2, int(mo2), int(d2)))


def parse_catalog_pdf(pdf_path):
    """解析官方目录 PDF，返回标准化条目列表。"""
    import pdfplumber

    rows = []
    current_section = None
    current_colmap = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                if not table:
                    continue
                header = table[0]
                head_text = "".join((c or "") for c in header)
                if any(k in head_text for k in ("药品名称", "饮片名称", "序号")):
                    # 本表首行为表头：切换区块与列映射
                    section = _detect_section(header)
                    if section == "index":
                        current_section = "index"
                        current_colmap = {}
                        continue
                    current_section = section
                    current_colmap = _build_colmap(header)
                    start = 1
                else:
                    # 续页：沿用上一区块的列映射，首行即数据
                    start = 0
                if current_section == "index" or "name" not in current_colmap:
                    continue
                for row in table[start:]:
                    name = _cell(row, current_colmap, "name")
                    if not name:
                        continue
                    category = _row_category(row, current_colmap)
                    if not category:
                        continue
                    code_cell = _cell(row, current_colmap, "code")
                    if not code_cell and (current_colmap.get("code") or 1) - 1 < len(row):
                        code_cell = _norm(row[(current_colmap.get("code") or 1) - 1])
                    rows.append({
                        "section": current_section,
                        "category": category,
                        "code": _code_from_cell(code_cell),
                        "name": name,
                        "dosage_form": _cell(row, current_colmap, "form"),
                        "pay_standard": _cell(row, current_colmap, "pay"),
                        "payment_scope": _cell(row, current_colmap, "note"),
                        "valid_until": _cell(row, current_colmap, "valid"),
                    })
    return rows


# ---------- 品种匹配 ----------

def _norm_name(name):
    return _norm(name).lower().replace(" ", "")


def _strip_form(name):
    for suffix in FORM_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _strip_salt(name):
    """剥离常见盐基前缀（甲磺酸/盐酸…），如 甲磺酸阿美替尼 → 阿美替尼。"""
    for prefix in SALT_PREFIXES:
        if name.startswith(prefix) and len(name) > len(prefix) + 1:
            return name[len(prefix):]
    return name


def _name_keys(name):
    """生成名称的规范化匹配键集合（剂型/括号/盐基/罗马数字归一）。"""
    n = _norm_name(name)
    while n and n[-1] in ROMAN_NUMERALS:
        n = n[:-1]
    keys = set()
    for variant in (n, _strip_form(n)):
        if not variant:
            continue
        keys.add(variant)
        base = re.split(r"[（(]", variant)[0]
        if len(base) >= 2:
            keys.add(base)
        stripped = _strip_salt(variant)
        if len(stripped) >= 2:
            keys.add(stripped)
    return {k for k in keys if len(k) >= 2}


def _row_name_keys(name):
    """一行可能含多个药品名（换行分隔），合并所有匹配键。"""
    keys = set()
    for part in re.split(r"[\n\r]+", name or ""):
        keys |= _name_keys(part)
    return keys


def _match_products(products, row):
    """返回匹配到的 product_id 列表（可多个，如同一通用名多企业）。"""
    hit_ids = []
    row_keys = _row_name_keys(row.get("name", ""))
    if not row_keys:
        return hit_ids
    for pid, gn_keys in products:
        if row_keys & gn_keys and pid not in hit_ids:
            hit_ids.append(pid)
    return hit_ids


def build_product_lookup(drugs):
    """从库中加载全部品种并生成匹配键。"""
    _, rows = drugs.fetch_products(page=1, size=100000)
    lookup = []
    for r in rows:
        lookup.append((r["product_id"], _name_keys(r["generic_name"])))
    return lookup


# ---------- 导入 ----------

def import_catalog(drugs, rows, version_name, publish_date=""):
    """写入目录版本 + 全量条目 + 品种匹配结果。返回报告。"""
    catalog_id = drugs.upsert_catalog(InsuranceCatalog(
        version_name=version_name,
        publish_date=publish_date,
        source_url=NHSA_LIST_URL,
    ))
    drugs.replace_catalog_entries(catalog_id, rows)
    drugs.reset_catalog_matches(catalog_id)
    lookup = build_product_lookup(drugs)
    matched = {}
    unmatched = []
    for row in rows:
        ids = _match_products(lookup, row)
        if not ids:
            unmatched.append(row["name"])
            continue
        effective, expire = _parse_valid_range(row.get("valid_until", ""))
        entry = {
            "category": row["category"],
            "payment_scope": row.get("payment_scope", ""),
            "price": row.get("pay_standard", ""),
            "effective_date": effective,
            "expire_date": expire,
            "insurance_code": row.get("code", ""),
        }
        for pid in ids:
            matched.setdefault(pid, []).append(entry)
    for pid, entries in matched.items():
        drugs.set_product_catalog_entries(pid, catalog_id, entries)
    return {
        "catalog": version_name,
        "catalog_id": catalog_id,
        "parsed_entries": len(rows),
        "matched_products": len(matched),
        "matched_entries": sum(len(v) for v in matched.values()),
        "unmatched_names": len(set(unmatched)),
        "unmatched_samples": sorted(set(unmatched))[:20],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="国家医保药品目录导入器")
    parser.add_argument("--db", default="policy_crawler.db")
    parser.add_argument("--pdf", default="", help="本地目录 PDF 路径")
    parser.add_argument("--version", default="", help="目录版本名（缺省从 PDF 文件名推断）")
    parser.add_argument("--publish-date", default="")
    parser.add_argument("--auto", action="store_true", help="自动从 NHSA 官网发现并下载最新目录")
    args = parser.parse_args(argv)

    if args.auto and not args.pdf:
        args.pdf = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "work", "nhsa-catalog-latest.pdf")
        version, args.pdf = download_catalog_pdf(args.pdf)
        if not args.version:
            args.version = version
    if not args.pdf or not os.path.exists(args.pdf):
        parser.error("请提供 --pdf 路径或使用 --auto 自动下载")
    version = args.version or os.path.splitext(os.path.basename(args.pdf))[0]

    rows = parse_catalog_pdf(args.pdf)
    drugs = DrugStore.from_path(args.db)
    report = import_catalog(drugs, rows, version, args.publish_date)
    drugs.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
