# -*- coding: utf-8 -*-
"""探针 v8：带截图驱动 NMPA 搜索 UI，逐步观察下拉/结果状态。"""
import os
import sys

from playwright.sync_api import sync_playwright


OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "work",
)
ITEM_ID = "ff80808183cad75001840881f848179f"


def kill_intro(page):
    page.evaluate("""
      () => {
        document.querySelectorAll('.introjs-overlay,.introjs-helperLayer,.introjs-tooltip,.introjs-arrow')
          .forEach(el => el.remove());
        if (window.introJs) { try { window.introJs().exit(); } catch (e) {} }
      }
    """)


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
            url = resp.url
            if "/datasearch/data/" in url:
                try:
                    body = resp.text()[:800]
                except Exception:
                    body = ""
                captured.append({"status": resp.status, "url": url, "body": body})

        page.on("response", on_response)
        page.goto("https://www.nmpa.gov.cn/datasearch/search-result.html?itemId=" + ITEM_ID, timeout=60000)
        page.wait_for_timeout(12000)
        kill_intro(page)
        box = page.locator("input[placeholder*='请输入']").first
        box.click()
        box.fill("阿托伐他汀")
        page.wait_for_timeout(3000)
        page.screenshot(path=os.path.join(OUT_DIR, "nmpa_ui_1_typed.png"))
        # 点击页面中出现的“境内生产药品”文本（下拉项可能非 el-link）
        kill_intro(page)
        candidates = page.get_by_text("境内生产药品", exact=True)
        print("境内生产药品 元素数:", candidates.count())
        for i in range(candidates.count()):
            try:
                candidates.nth(i).click(timeout=3000)
                print("点击了第", i, "个")
                break
            except Exception as exc:
                print("第", i, "个点击失败:", str(exc)[:120])
        page.wait_for_timeout(6000)
        page.screenshot(path=os.path.join(OUT_DIR, "nmpa_ui_2_after_click.png"))
        print("CAPTURED:", len(captured))
        for c in captured:
            print(" ", c["status"], c["url"][:150])
            print("   BODY:", c["body"][:300].replace("\n", " "))
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
