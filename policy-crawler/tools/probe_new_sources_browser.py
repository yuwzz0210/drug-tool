# -*- coding: utf-8 -*-
"""用真实浏览器探测：上市药品目录集官方入口 + 湖南招采网登录页结构。

只读探测，不登录、不提交表单。
用法：python tools/probe_new_sources_browser.py
"""
import io
import json
import sys
import time

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

SEARCH = ("https://cn.bing.com/search?q="
          "%E4%B8%8A%E5%B8%82%E8%8D%AF%E5%93%81%E7%9B%AE%E5%BD%95%E9%9B%86%20"
          "%E5%9B%BD%E5%AE%B6%E8%8D%AF%E7%9B%91%E5%B1%80")
HUNAN = "https://tps.ybj.hunan.gov.cn/tps-local/"


def main():
    from playwright.sync_api import sync_playwright
    out = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale="zh-CN")
        page = ctx.new_page()
        page.goto(SEARCH, timeout=45000, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        results = page.eval_on_selector_all(
            "#b_results li.b_algo",
            """els => els.slice(0,6).map(e => {
                 const a = e.querySelector('h2 a');
                 return {title: a ? a.innerText : '',
                         url: a ? a.href : '',
                         snippet: (e.innerText||'').slice(0,120)};
               })""")
        out["bing"] = results
        print("=== 搜索「上市药品目录集」前 6 条")
        for r in results:
            print(" -", r["title"][:46], "|", r["url"][:80])

        time.sleep(4)
        page.goto(HUNAN, timeout=45000, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        out["hunan_title"] = page.title()
        out["hunan_url"] = page.url
        inputs = page.eval_on_selector_all(
            "input", "els => els.slice(0,8).map(e => [e.type, e.id, e.placeholder])")
        buttons = page.eval_on_selector_all(
            "button, a.btn", "els => els.slice(0,8).map(e => (e.innerText||'').trim())")
        text = page.inner_text("body")[:400].replace("\n", " ")
        out["hunan_inputs"] = inputs
        out["hunan_buttons"] = buttons
        out["hunan_text"] = text
        print("=== 湖南招采网")
        print(" title:", out["hunan_title"], "| url:", out["hunan_url"])
        print(" inputs:", inputs)
        print(" buttons:", buttons)
        print(" text:", text[:220])
        ctx.close()
        browser.close()
    with open("logs/new_sources_probe.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print("PROBE_BROWSER_DONE")


if __name__ == "__main__":
    main()
