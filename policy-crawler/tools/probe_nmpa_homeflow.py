# -*- coding: utf-8 -*-
"""探针 v15：完整模拟用户流程：首页搜索 → 新窗口 search-result → 捕获带 sign 的列表请求。"""
import json
import os
import sys

from playwright.sync_api import sync_playwright


OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "work",
)


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
                    body = resp.text()[:1500]
                except Exception:
                    body = ""
                captured.append({"status": resp.status, "url": resp.url, "body": body})

        ctx.on("page", lambda pg: pg.on("response", on_response))
        page.on("response", on_response)
        page.goto("https://www.nmpa.gov.cn/datasearch/home-index.html", timeout=60000)
        page.wait_for_timeout(12000)
        page.evaluate("document.querySelectorAll('.introjs-overlay,.introjs-helperLayer,.introjs-tooltip,.introjs-arrow').forEach(e=>e.remove())")
        inputs = page.evaluate("""
          Array.from(document.querySelectorAll('input')).map((el, i) => ({
            i: i, ph: el.placeholder, type: el.type, vis: !!el.offsetParent
          }))
        """)
        print("INPUTS:", json.dumps(inputs, ensure_ascii=False)[:700])
        box = None
        for el in page.locator("input").all():
            ph = el.get_attribute("placeholder") or ""
            if el.is_visible() and "请选择" not in ph:
                box = el
                print("选用输入框:", ph[:50])
                break
        if box is None:
            print("未找到输入框")
            browser.close()
            return 1
        box.fill("阿托伐他汀")
        page.wait_for_timeout(2000)
        # 触发搜索：回车 + 点击可见按钮
        box.press("Enter")
        page.wait_for_timeout(3000)
        try:
            page.locator("button:visible").first.click()
        except Exception:
            pass
        page.wait_for_timeout(4000)
        print("页面数:", len(ctx.pages), [pg.url[:100] for pg in ctx.pages])
        # 等待新窗口
        result_page = None
        for pg in ctx.pages:
            if "search-result" in pg.url:
                result_page = pg
                break
        if result_page is None:
            print("未出现 search-result 窗口")
        else:
            result_page.wait_for_timeout(10000)
            print("结果页 URL:", result_page.url[:140])
            print("结果页 TEXT:", result_page.evaluate("document.body.innerText.slice(0,600)").replace("\n", " | "))
        print("CAPTURED:", len(captured))
        for c in captured:
            print(" ", c["status"], c["url"][:240])
            print("   BODY:", c["body"][:500].replace("\n", " "))
        with open(os.path.join(OUT_DIR, "nmpa_homeflow_capture.json"), "w", encoding="utf-8") as f:
            json.dump(captured, f, ensure_ascii=False, indent=2)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
