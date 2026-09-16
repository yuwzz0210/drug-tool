# -*- coding: utf-8 -*-
"""用真实浏览器探测药监局「上市药品目录集」入口与字段（只读）。

用法：python tools/probe_nmpa_catalog_browser.py
输出：logs/nmpa_catalog_probe.json
"""
import io
import json
import re
import sys

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

HOME = "https://www.nmpa.gov.cn/datasearch/home-index.html"


def main():
    from playwright.sync_api import sync_playwright
    out = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            locale="zh-CN",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Safari/537.36"))
        page = ctx.new_page()
        page.goto(HOME, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(6000)
        out["title"] = page.title()
        out["url"] = page.url
        body = page.inner_text("body")
        out["text_head"] = re.sub(r"\s+", " ", body)[:600]
        links = page.eval_on_selector_all(
            "a", "els => els.map(e => [ (e.innerText||'').trim(), e.href ])")
        hits = [{"text": t[:40], "href": h} for t, h in links
                if t and any(k in t for k in ("目录集", "药品", "数据查询"))]
        out["links"] = hits[:25]
        print("title:", out["title"], "| url:", out["url"])
        print("text:", out["text_head"][:260])
        for h in hits[:15]:
            print("  -", h["text"], "->", h["href"][:95])
        ctx.close()
        browser.close()
    with open("logs/nmpa_catalog_probe.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print("NMPA_CATALOG_PROBE_DONE")


if __name__ == "__main__":
    main()
