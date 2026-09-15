# -*- coding: utf-8 -*-
"""探针 v14：定位 iframe，在框架内驱动搜索并点击结果，捕获带 sign 的列表请求。"""
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
        page.goto("https://www.nmpa.gov.cn/datasearch/home-index.html", timeout=60000)
        page.wait_for_timeout(12000)
        page.evaluate("document.querySelectorAll('.introjs-overlay,.introjs-helperLayer,.introjs-tooltip,.introjs-arrow').forEach(e=>e.remove())")
        # 点击「境内生产药品」数据集卡片（el-link active），跟随新窗口
        # JS 直接触发卡片链接点击，然后等待跳转/新窗口
        page.evaluate("""
          () => {
            const link = Array.from(document.querySelectorAll('a'))
              .find(a => (a.innerText || '').trim() === '境内生产药品');
            if (link) { link.click(); return true; }
            return false;
          }
        """)
        page.wait_for_timeout(10000)
        print("当前 URL:", page.url[:160])
        print("所有页面:", [pg.url[:120] for pg in ctx.pages])
        spage = None
        for pg in ctx.pages:
            if any(k in pg.url for k in ("search", "result", "query", "app-search")):
                spage = pg
                break
        if spage is None:
            spage = page
        page = spage
        # 在（可能含 iframe 的）搜索页驱动查询
        search_page = page
        for f in page.frames:
            if "search" in f.url or "result" in f.url or "query" in f.url:
                search_page = f
                break
        print("搜索载体:", search_page.url[:120])
        box = search_page.locator("input[placeholder*='请输入']").first
        box.click()
        box.fill("阿托伐他汀")
        search_page.wait_for_timeout(5000)
        print("搜索页 TEXT:", search_page.evaluate("document.body.innerText.slice(0,700)").replace("\n", " | "))
        nodes = search_page.evaluate("""() => {
          const out = [];
          document.querySelectorAll('a, li, div, span, button').forEach((el, i) => {
            const t = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
            if (t && t.length < 80 && t.includes('117')) out.push({i, tag: el.tagName, text: t, vis: !!el.offsetParent});
          });
          return out.slice(0, 20);
        }""")
        print("117 节点:", json.dumps(nodes, ensure_ascii=False)[:900])
        for n in nodes:
            if n["vis"]:
                try:
                    search_page.evaluate(
                        "(i) => { const el = document.querySelectorAll('a, li, div, span, button')[i]; el && el.click(); }",
                        n["i"],
                    )
                    print("已点击:", n["text"][:40])
                    break
                except Exception as exc:
                    print("点击失败:", str(exc)[:100])
        search_page.wait_for_timeout(8000)
        print("CAPTURED:", len(captured))
        for c in captured:
            print(" ", c["status"], c["url"][:240])
            print("   BODY:", c["body"][:500].replace("\n", " "))
        with open(os.path.join(OUT_DIR, "nmpa_frame_capture.json"), "w", encoding="utf-8") as f:
            json.dump(captured, f, ensure_ascii=False, indent=2)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
