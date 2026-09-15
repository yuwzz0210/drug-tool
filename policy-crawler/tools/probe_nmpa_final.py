# -*- coding: utf-8 -*-
"""探针 v12：挂钩页面请求层 + 点击真正的查询按钮，抓取带 sign 的列表请求。"""
import json
import os
import sys

from playwright.sync_api import sync_playwright


OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "work",
)
ITEM_ID = "ff80808183cad75001840881f848179f"


def main():
    captured = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
            locale="zh-CN",
            viewport={"width": 1440, "height": 960},
        )
        page = ctx.new_page()

        def on_response(resp):
            if "/datasearch/data/nmpadata/" in resp.url:
                try:
                    body = resp.text()[:1200]
                except Exception:
                    body = ""
                captured.append({"status": resp.status, "url": resp.url, "body": body})

        page.on("response", on_response)
        page.goto("https://www.nmpa.gov.cn/datasearch/search-result.html?itemId=" + ITEM_ID, timeout=60000)
        page.wait_for_timeout(12000)
        page.evaluate("document.querySelectorAll('.introjs-overlay,.introjs-helperLayer,.introjs-tooltip,.introjs-arrow').forEach(e=>e.remove())")
        # 挂钩请求层
        page.evaluate("""
          window.__reqLog = [];
          const oFetch = window.fetch.bind(window);
          window.fetch = (...args) => {
            window.__reqLog.push({kind: 'fetch', url: String(args[0]), init: args[1] ? JSON.stringify(args[1]) : ''});
            return oFetch(...args);
          };
        """)
        box = page.locator("input[placeholder*='请输入']").first
        box.click()
        box.fill("阿托伐他汀")
        page.wait_for_timeout(2000)
        # 点真正的查询按钮
        clicked = False
        for sel in ("button[data-step='5']", "button.el-button--primary", ".el-input__suffix button, .el-input-group__append button"):
            loc = page.locator(sel)
            if loc.count() and loc.first.is_visible():
                loc.first.click()
                clicked = True
                print("点击按钮:", sel)
                break
        if not clicked:
            # 兜底：点最后一个可见按钮
            vis = page.locator("button:visible")
            print("可见按钮数:", vis.count())
            vis.last.click()
            print("点击最后一个可见按钮")
        page.wait_for_timeout(10000)
        reqlog = page.evaluate("window.__reqLog || []")
        print("REQLOG:", json.dumps(reqlog, ensure_ascii=False)[:1200])
        print("CAPTURED:", len(captured))
        for c in captured:
            print(" ", c["status"], c["url"][:240])
            print("   BODY:", c["body"][:500].replace("\n", " "))
        with open(os.path.join(OUT_DIR, "nmpa_sign_capture.json"), "w", encoding="utf-8") as f:
            json.dump({"reqlog": reqlog, "responses": captured}, f, ensure_ascii=False, indent=2)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
