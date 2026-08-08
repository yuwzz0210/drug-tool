# -*- coding: utf-8 -*-
"""把「网址导航」JSON 转换为爬虫区域数据源注册表 regional_sources.json。

用法：
    python -m tools.build_regional_sources "网址导航_其他标签链接.json" [输出路径]

生成的条目默认 enabled=False（parser 需逐站用真实列表页校验后再开启）。
"""
import argparse
import json
import sys


CATEGORY_PARSER = {"医保局": "nhsa", "药监局": "nmpa", "卫健委": "nhc"}

AREA_CODES = {
    "国家": "cn", "北京市": "bj", "天津市": "tj", "河北省": "heb", "山西省": "sx",
    "内蒙古自治区": "nmg", "辽宁省": "ln", "吉林省": "jl", "黑龙江省": "hlj",
    "上海市": "sh", "江苏省": "js", "浙江省": "zj", "安徽省": "ah", "福建省": "fj",
    "江西省": "jx", "山东省": "sd", "河南省": "ha", "湖北省": "hb", "湖南省": "hn",
    "广东省": "gd", "广西壮族自治区": "gx", "海南省": "hi", "重庆市": "cq",
    "四川省": "sc", "贵州省": "gz", "云南省": "yn", "西藏自治区": "xz",
    "陕西省": "sn", "甘肃省": "gs", "青海省": "qh", "宁夏回族自治区": "nx",
    "新疆维吾尔自治区": "xj", "新疆生产建设兵团": "xjbt",
}


def _area_code(area):
    area = (area or "").strip()
    return AREA_CODES.get(area, area[:2].lower() or "xx")


def build_regional_sources(nav, categories=("医保局", "药监局", "卫健委")):
    """导航 dict → {source_id: source配置}；portal 去重，默认 enabled=False。"""
    out = {}
    for cat in categories:
        parser = CATEGORY_PARSER[cat]
        seen = set()
        for item in nav.get(cat, []):
            raw = (item.get("portal_url") or "").rstrip("/")
            if not raw or raw in seen:
                continue
            seen.add(raw)
            portal = raw + "/"
            area = item.get("area", "")
            sid = "{}_{}".format(parser, _area_code(area))
            if sid in out:
                sid = "{}_{}".format(sid, len([k for k in out if k.startswith(sid + "_")]) + 1)
            out[sid] = {
                "name": item.get("name", ""),
                "area": area,
                "base": portal,
                "portal_url": portal,
                "parser": parser,
                "list_url": "",
                "keep_paths": [],
                "enabled": False,
            }
    return out


def write_regional_sources(sources, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sources, f, ensure_ascii=False, indent=2)


def main(argv=None):
    ap = argparse.ArgumentParser(description="导航 JSON → regional_sources.json")
    ap.add_argument("nav_file", help="网址导航 JSON 路径")
    ap.add_argument("output", nargs="?", default="regional_sources.json")
    args = ap.parse_args(argv)
    with open(args.nav_file, encoding="utf-8-sig") as f:
        nav = json.load(f)
    sources = build_regional_sources(nav)
    write_regional_sources(sources, args.output)
    print("生成 {} 个区域数据源 -> {}".format(len(sources), args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
