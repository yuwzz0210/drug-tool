# -*- coding: utf-8 -*-
"""探针 v13：dump 页面全文与含「117」的元素，点击结果链接触发列表加载。"""
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
        box = page.locator("input[placeholder*='请输入']").first
        box.click()
        box.fill("阿托伐他汀")
        page.wait_for_timeout(6000)
        print("BODY TEXT:", page.evaluate("document.body.innerText.slice(0,1200)").replace("\n", " | "))
        nodes = page.evaluate("""() => {
          const out = [];
          const all = document.querySelectorAll('a, li, div, span, button');
          all.forEach((el, i) => {
            const t = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
            if (t && t.length < 80 && (t.includes('117') || t.includes('阿托伐他汀'))) {
              out.push({i, tag: el.tagName, cls: (el.className||'').toString().slice(0,50),
                text: t, vis: !!el.offsetParent});
            }
          });
          return out.slice(0, 30);
        }""")
        print("117 节点:", json.dumps(nodes, ensure_ascii=False)[:1200])
        clicked = False
        for n in nodes:
            if n["vis"]:
                try:
                    page.evaluate(
                        "(i) => { const el = document.querySelectorAll('a, li, div, span, button')[i]; el && el.click(); }",
                        n["i"],
                    )
                    print("已点击:", n["text"][:40])
                    clicked = True
                    break
                except Exception as exc:
                    print("点击失败:", exc)
        if not clicked:
            print("无可点节点，尝试文本点击")
            try:
                page.get_by_text("117", exact=False).first.click(timeout=3000)
                clicked = True
            except Exception as exc:
                print("文本点击失败:", str(exc)[:120])
        page.wait_for_timeout(8000)
        print("CAPTURED:", len(captured))
        for c in captured:
            print(" ", c["status"], c["url"][:240])
            print("   BODY:", c["body"][:500].replace("\n", " "))
        with open(os.path.join(OUT_DIR, "nmpa_resultlink_capture.json"), "w", encoding="utf-8") as f:
            json.dump(captured, f, ensure_ascii=False, indent=2)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
