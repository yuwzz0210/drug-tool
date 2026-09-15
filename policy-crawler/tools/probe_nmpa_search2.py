# -*- coding: utf-8 -*-
"""探针 v5：直达 search-result 页，输入产品名称并抓取 dataCenter 请求格式。"""
import json
import os
import sys

from playwright.sync_api import sync_playwright


OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "work",
)
ITEM_ID = "ff80808183cad75001840881f848179f"  # 境内生产药品


def main():
    captured = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
            locale="zh-CN",
        )
        page = ctx.new_page()

        def on_response(resp):
            req = resp.request
            url = resp.url
            if "/datasearch/" in url and not any(
                k in url for k in (".css", ".js", ".jpg", ".png", ".woff", ".ttf", "config/")
            ):
                try:
                    post = req.post_data or ""
                    body = resp.text()[:1500]
                except Exception:
                    post, body = "", ""
                captured.append({
                    "status": resp.status,
                    "url": resp.url,
                    "method": req.method,
                    "post": post[:2000],
                    "body": body,
                })

        page.on("response", on_response)
        page.goto(
            "https://www.nmpa.gov.cn/datasearch/search-result.html?itemId=" + ITEM_ID,
            timeout=60000,
        )
        page.wait_for_timeout(12000)
        print("TITLE:", page.title())
        print("BODY:", page.evaluate("document.body.innerText.slice(0,260)").replace("\n", " "))
        inputs = page.evaluate("""
          Array.from(document.querySelectorAll('input')).map((el, i) => ({
            i: i, ph: el.placeholder, type: el.type, val: el.value, vis: !!el.offsetParent
          }))
        """)
        print("INPUTS:", json.dumps(inputs, ensure_ascii=False)[:800])
        buttons = page.evaluate("""
          Array.from(document.querySelectorAll('button')).map((el, i) => ({
            i: i, text: (el.innerText||'').trim().slice(0,20), vis: !!el.offsetParent
          }))
        """)
        print("BUTTONS:", json.dumps(buttons, ensure_ascii=False)[:600])
        # 填关键词输入框（placeholder 含「请输入」），回车查询
        try:
            box = page.locator("input[placeholder*='请输入']").first
            print("FILL placeholder:", box.get_attribute("placeholder")[:40])
            box.fill("阿托伐他汀")
            # 点击可见的图标按钮 + 派发回车
            try:
                page.locator("button:visible").first.click()
            except Exception:
                pass
            box.dispatch_event("keyup", {"key": "Enter", "keyCode": 13, "which": 13})
            box.press("Enter")
            page.wait_for_timeout(8000)
        except Exception as exc:
            print("查询失败:", exc)
        print("CAPTURED:", len(captured))
        for c in captured:
            print("===", c["status"], c["method"], c["url"][:120])
            print("POST:", c["post"][:900])
            print("BODY:", c["body"][:500].replace("\n", " "))
        with open(os.path.join(OUT_DIR, "nmpa_search_capture.json"), "w", encoding="utf-8") as f:
            json.dump(captured, f, ensure_ascii=False, indent=2)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
