# -*- coding: utf-8 -*-
"""NMPA 药品注册信息采集器。

NMPA 数据查询（https://www.nmpa.gov.cn/datasearch/home-index.html）背后是 JSON 接口，
但整站带 JS 反爬挑战（412/202），普通 HTTP 客户端会被拦截。本模块：
1. 优先直接请求官方接口（fetch_registrations）；
2. 被拦截时抛出 JSChallengeError，并支持读取浏览器 DevTools 保存的真实响应
   （--json 文件）继续导入，选择器以真实响应收敛。

用法：
    python -m collectors.nmpa_drugs --keyword 阿托伐他汀 --db policy_crawler.db
    python -m collectors.nmpa_drugs --json nmpa-response.json --db policy_crawler.db
"""
import argparse
import json
import logging
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from drugstore import DrugStore, _norm  # noqa: E402
from models import DrugProduct, DrugRegistration  # noqa: E402


log = logging.getLogger("policy-crawler.collectors.nmpa")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
DATASEARCH_URL = "https://www.nmpa.gov.cn/datasearch/dataCenter"

FIELD_ALIASES = {
    "generic": ["通用名", "通用名称", "产品名称", "药品名称", "名称", "药品通用名"],
    "trade": ["商品名", "商品名称"],
    "approval": ["批准文号", "注册证号", "药品批准文号", "批准文号/注册证号"],
    "form": ["剂型", "产品剂型", "药品剂型"],
    "spec": ["规格", "药品规格", "产品规格"],
    "manufacturer": ["生产单位", "生产企业", "生产厂家", "上市许可持有人", "持证商", "企业名称"],
    "date": ["批准日期", "发证日期", "批准时间"],
    "type": ["药品类型", "产品类别", "类别", "产品类型"],
    "otc": ["是否OTC", "OTC", "是否非处方药"],
}


class JSChallengeError(RuntimeError):
    """目标站触发 JS 反爬（412/202），需要浏览器环境或浏览器保存的响应。"""


def _first(record, keys):
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return _norm(value)
    return ""


def parse_registrations(payload):
    """把 NMPA 数据查询响应归一化为注册记录列表（防御式字段映射）。"""
    data = payload
    if isinstance(data, dict):
        data = data.get("data", data)
    if isinstance(data, dict) and isinstance(data.get("list"), list):
        data = data["list"]
    if isinstance(data, dict) and isinstance(data.get("rows"), list):
        data = data["rows"]
    if not isinstance(data, list):
        raise ValueError("无法识别的响应结构：顶层应为数组或 {data:{list:[...]}}")
    records = []
    for item in data:
        if not isinstance(item, dict):
            continue
        generic = _first(item, FIELD_ALIASES["generic"])
        if not generic:
            continue
        records.append({
            "generic_name": generic,
            "trade_name": _first(item, FIELD_ALIASES["trade"]),
            "approval_number": _first(item, FIELD_ALIASES["approval"]),
            "dosage_form": _first(item, FIELD_ALIASES["form"]),
            "specification": _first(item, FIELD_ALIASES["spec"]),
            "manufacturer": _first(item, FIELD_ALIASES["manufacturer"]),
            "approval_date": _first(item, FIELD_ALIASES["date"]),
            "drug_type": _first(item, FIELD_ALIASES["type"]),
            "is_otc": _first(item, FIELD_ALIASES["otc"]).lower() in ("是", "y", "yes", "1", "otc"),
        })
    return records


def fetch_registrations(keyword="", page=1, page_size=20):
    """尝试直接请求 NMPA 数据查询接口；被反爬拦截时抛 JSChallengeError。"""
    body = json.dumps({
        "page": page,
        "pageSize": page_size,
        "conditions": [{"field": "type", "value": "1"}] if not keyword else [],
        "keyword": keyword,
    }).encode("utf-8")
    req = urllib.request.Request(
        DATASEARCH_URL,
        data=body,
        headers={"User-Agent": UA, "Content-Type": "application/json",
                 "Referer": "https://www.nmpa.gov.cn/datasearch/home-index.html",
                 "Accept": "application/json, text/javascript, */*; q=0.01",
                 "X-Requested-With": "XMLHttpRequest"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code in (412, 202, 403):
            raise JSChallengeError(
                "NMPA 数据查询触发 JS 反爬（HTTP %s）。请在浏览器打开 "
                "https://www.nmpa.gov.cn/datasearch/home-index.html，DevTools→Network 搜索 "
                "药品名称后保存 dataCenter 响应 JSON，再用 --json 导入。" % exc.code)
        raise
    return json.loads(raw)


def import_registrations(drugs, records):
    """把注册记录写入品种主库（组合键去重 + 批准文号独立）。"""
    report = {"records": len(records), "products": 0, "registrations": 0}
    for r in records:
        product = DrugProduct(
            generic_name=r["generic_name"],
            dosage_form=r["dosage_form"],
            specification=r["specification"],
            manufacturer_norm=r["manufacturer"],
            trade_name=r["trade_name"],
            drug_type=r["drug_type"],
            is_otc=r["is_otc"],
            source_url=DATASEARCH_URL,
        )
        pid = drugs.upsert_product(product)
        report["products"] += 1
        if r["approval_number"]:
            drugs.upsert_registration(DrugRegistration(
                product_id=pid,
                approval_number=r["approval_number"],
                registration_date=r["approval_date"],
                source_url=DATASEARCH_URL,
            ))
            report["registrations"] += 1
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="NMPA 药品注册采集器")
    parser.add_argument("--keyword", default="", help="查询关键词（通用名/商品名）")
    parser.add_argument("--json", default="", help="浏览器保存的 dataCenter 响应 JSON 路径")
    parser.add_argument("--db", default="policy_crawler.db")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=20)
    args = parser.parse_args(argv)

    if args.json:
        with open(args.json, encoding="utf-8") as f:
            payload = json.load(f)
        records = parse_registrations(payload)
    else:
        payload = fetch_registrations(args.keyword, args.page, args.page_size)
        records = parse_registrations(payload)
    print("解析到注册记录:", len(records))
    for r in records[:5]:
        print(" ", r["generic_name"], r["dosage_form"], r["specification"],
              r["manufacturer"], r["approval_number"])
    if records:
        drugs = DrugStore.from_path(args.db)
        report = import_registrations(drugs, records)
        drugs.close()
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
