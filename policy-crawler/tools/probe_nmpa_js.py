# -*- coding: utf-8 -*-
"""探针 v4：浏览器内读取 home-index.js，定位数据集列表页直达 URL。"""
import os
import sys

from playwright.sync_api import sync_playwright


OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "work",
)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
            locale="zh-CN",
        )
        page = ctx.new_page()
        page.goto("https://www.nmpa.gov.cn/datasearch/home-index.html", timeout=60000)
        page.wait_for_timeout(12000)
        js = page.evaluate("fetch('/datasearch/js/index/home-index.js?v=1').then(r=>r.text())")
        with open(os.path.join(OUT_DIR, "nmpa_home_index.js"), "w", encoding="utf-8") as f:
            f.write(js)
        print(js[:3000])
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
