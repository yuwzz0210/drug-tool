# -*- coding: utf-8 -*-
"""离线构建政策库：用已保存的真实官网列表页/详情页跑生产解析器，建库并输出校验报告。

用途：
    1. 在无外网环境下验证 NMPA/NHSA/NHC 解析器对真实页面的解析质量；
    2. 把已保存的真实数据落成 SQLite 政策库 + data/policies.json（联网后由真实爬取补充正文）。

用法（policy-crawler 目录下）：
    python tools/build_offline_db.py
    python tools/build_offline_db.py --db policy_crawler.db --json data/policies.json
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import SOURCES  # noqa: E402
from main import save_to_json  # noqa: E402
from models import Policy  # noqa: E402
from parsers import PARSERS  # noqa: E402
from store import SqliteStore  # noqa: E402


DEFAULT_WORK_ROOT = os.path.join(os.path.dirname(ROOT), "work")


def _read(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _match_detail(items, detail):
    """详情页与列表条目匹配：仅当标题一致时才挂接详情正文，避免错配。"""
    d_title = (detail.get("title") or "").strip()
    if not d_title:
        return None
    for item in items:
        t = (item.get("title") or "").strip()
        if d_title and (d_title in t or t in d_title):
            return item
    return None


def build(source_keys, db_path, json_path, work_root=None):
    work_root = work_root or DEFAULT_WORK_ROOT
    store = SqliteStore(db_path)
    report = []
    all_policies = []
    for key in source_keys:
        src = SOURCES[key]
        parser = PARSERS[src["parser"]]
        base = src["base"]
        keep = src.get("keep_paths") or []
        list_html = _read(os.path.join(work_root, key + "-real", "list.html"))
        detail_html = _read(os.path.join(work_root, key + "-real", "detail.html"))
        if list_html is None:
            report.append({"source": key, "error": "缺少列表页 work/{}-real/list.html".format(key)})
            continue
        items = parser.parse_list(list_html, base, keep_paths=keep)
        detail = parser.parse_detail(detail_html, url=items[0]["url"] if items else "") if detail_html else {}
        matched = _match_detail(items, detail) if detail else None
        authority = detail.get("issuing_authority") or src["name"]
        policies = []
        for item in items:
            is_matched = matched is not None and item["url"] == matched["url"]
            policies.append(Policy(
                title=item["title"],
                source_url=item["url"],
                publish_date=item.get("date", ""),
                doc_number=detail.get("doc_number", "") if is_matched else "",
                issuing_authority=authority,
                content=detail.get("content", "") if is_matched else "",
                attachment_links=json.dumps(detail.get("attachments", []), ensure_ascii=False) if is_matched else "[]",
            ))
        all_policies.extend(policies)
        report.append({
            "source": key,
            "list_items": len(items),
            "detail_title": detail.get("title", ""),
            "detail_date": detail.get("publish_date", ""),
            "detail_doc_number": detail.get("doc_number", ""),
            "detail_authority": authority,
            "detail_content_len": len(detail.get("content", "")),
            "attachments": len(detail.get("attachments", [])),
            "matched_item": matched["title"] if matched else None,
        })
    store.upsert_many(all_policies) if hasattr(store, "upsert_many") else _upsert_loop(store, all_policies)
    if json_path:
        save_to_json(all_policies, json_path)
    store.close() if hasattr(store, "close") else None
    return report, all_policies


def _upsert_loop(store, policies):
    for p in policies:
        store.upsert_policy(p)


def main(argv=None):
    parser = argparse.ArgumentParser(description="离线构建政策库（真实已存页面）")
    parser.add_argument("--db", default="policy_crawler.db")
    parser.add_argument("--json", default="data/policies.json")
    parser.add_argument("--sources", default="nmpa,nhsa,nhc")
    parser.add_argument("--work", default=None, help="真实页面目录，默认自动探测")
    args = parser.parse_args(argv)
    report, policies = build(args.sources.split(","), args.db, args.json, args.work)
    for r in report:
        print(r)
    print("入库政策总数:", len(policies))
    return 0


if __name__ == "__main__":
    sys.exit(main())
