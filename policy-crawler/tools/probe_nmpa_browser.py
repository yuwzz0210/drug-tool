# -*- coding: utf-8 -*-
"""探针：用 Playwright 真浏览器访问 NMPA 数据查询，验证能否自动通过 JS 挑战并拿到接口数据。"""
import sys

from playwright.sync_api import sync_playwright


def main():
    captured = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
            locale="zh-CN",
            viewport={"width": 1366, "height": 900},
        )
        page = ctx.new_page()

        def on_response(resp):
            url = resp.url
            if "dataCenter" in url or "datasearch" in url:
                try:
                    body = resp.text()[:400]
                except Exception:
                    body = "<no-body>"
                captured.append((resp.status, url, body))

        page.on("response", on_response)
        page.goto("https://www.nmpa.gov.cn/datasearch/home-index.html", timeout=60000)
        page.wait_for_timeout(15000)  # 等待 JS 挑战执行
        title = page.title()
        body_text = page.evaluate("document.body ? document.body.innerText.slice(0,300) : ''")
        print("TITLE:", title)
        print("BODY:", body_text.replace("\n", " ")[:300])
        # 尝试在搜索框输入并触发查询
        try:
            box = page.locator("input[type=text]").first
            box.fill("阿托伐他汀")
            box.press("Enter")
            page.wait_for_timeout(8000)
        except Exception as exc:
            print("UI 操作失败:", exc)
        print("CAPTURED:", len(captured))
        for status, url, body in captured:
            print(" ", status, url[:100], "|", body[:180].replace("\n", " "))
        ctx.storage_state(path="work/nmpa_browser_state.json")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
