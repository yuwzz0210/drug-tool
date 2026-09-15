# -*- coding: utf-8 -*-
"""探针 v3：在浏览器里点击「境内生产药品」→ 输入产品名称 → 抓取 dataCenter 请求格式。"""
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
        )
        page = ctx.new_page()

        def on_response(resp):
            if "dataCenter" in resp.url or "datasearch" in resp.url.lower():
                req = resp.request
                try:
                    post = req.post_data or ""
                    body = resp.text()[:600]
                except Exception:
                    post, body = "", ""
                captured.append({
                    "status": resp.status,
                    "url": resp.url,
                    "method": req.method,
                    "post": post[:800],
                    "body": body,
                })

        page.on("response", on_response)
        page.goto("https://www.nmpa.gov.cn/datasearch/home-index.html", timeout=60000)
        page.wait_for_timeout(12000)
        try:
            with ctx.expect_page(timeout=20000) as popup_info:
                page.get_by_text("境内生产药品", exact=True).first.click()
            spage = popup_info.value
            spage.wait_for_load_state("domcontentloaded")
            spage.wait_for_timeout(5000)
            print("SEARCH PAGE TITLE:", spage.title())
            print("SEARCH PAGE BODY:", spage.evaluate("document.body.innerText.slice(0,200)").replace("\n", " "))
            # 填入产品名称并查询
            box = spage.locator("input").nth(1) if spage.locator("input").count() > 1 else spage.locator("input").first
            box.fill("阿托伐他汀")
            spage.keyboard.press("Enter")
            spage.wait_for_timeout(8000)
            page = spage
        except Exception as exc:
            print("UI 驱动失败:", exc)
        print("CAPTURED:", len(captured))
        for c in captured:
            print("===", c["status"], c["method"], c["url"][:110])
            print("POST:", c["post"][:500])
            print("BODY:", c["body"][:220].replace("\n", " "))
        with open(os.path.join(OUT_DIR, "nmpa_search_capture.json"), "w", encoding="utf-8") as f:
            json.dump(captured, f, ensure_ascii=False, indent=2)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
