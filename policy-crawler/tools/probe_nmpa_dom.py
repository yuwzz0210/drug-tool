# -*- coding: utf-8 -*-
"""探针 v11：输入→点查询→dump 下拉 DOM，定位数据集行并点击，捕获带 sign 的列表请求。"""
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
            if "/datasearch/data/nmpadata/" in resp.url and "search" in resp.url:
                captured.append({"status": resp.status, "url": resp.url, "body": resp.text()[:800] if resp.status == 200 else ""})

        page.on("response", on_response)
        page.goto("https://www.nmpa.gov.cn/datasearch/search-result.html?itemId=" + ITEM_ID, timeout=60000)
        page.wait_for_timeout(12000)
        page.evaluate("document.querySelectorAll('.introjs-overlay,.introjs-helperLayer,.introjs-tooltip,.introjs-arrow').forEach(e=>e.remove())")
        box = page.locator("input[placeholder*='请输入']").first
        box.click()
        box.fill("阿托伐他汀")
        page.wait_for_timeout(2500)
        try:
            page.locator("button:visible").first.click()
        except Exception:
            pass
        page.wait_for_timeout(3500)
        dom = page.evaluate("""() => {
          const out = [];
          const nodes = document.querySelectorAll(
            '[class*=dropdown],[class*=suggest],[class*=popover],[class*=result],[class*=list] li,[class*=option]');
          nodes.forEach((el, i) => {
            const t = (el.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 60);
            if (t) out.push({i, tag: el.tagName, cls: (el.className||'').toString().slice(0,40),
              text: t, vis: !!el.offsetParent});
          });
          return out.slice(0, 40);
        }""")
        print("DOM:", json.dumps(dom, ensure_ascii=False)[:1500])
        # 点击可见的下拉项
        clicked = False
        for item in dom:
            if item["vis"] and ("境内生产药品" in item["text"] or "117" in item["text"] or "阿托伐他汀" in item["text"]):
                try:
                    page.evaluate(
                        "(i) => { const el = document.querySelectorAll('[class*=dropdown],[class*=suggest],[class*=popover],[class*=result],[class*=list] li,[class*=option]')[i]; el && el.click(); }",
                        item["i"],
                    )
                    print("JS 点击:", item["text"])
                    clicked = True
                    break
                except Exception as exc:
                    print("点击失败:", exc)
        if not clicked:
            try:
                page.get_by_text("境内生产药品", exact=True).nth(2).click(timeout=3000)
                print("点击 nth(2)")
            except Exception as exc:
                print("nth(2) 失败:", str(exc)[:100])
        page.wait_for_timeout(8000)
        print("CAPTURED search:", len(captured))
        for c in captured:
            print(" ", c["status"], c["url"][:260])
            print("   BODY:", c["body"][:400].replace("\n", " "))
        with open(os.path.join(OUT_DIR, "nmpa_list_sign_capture.json"), "w", encoding="utf-8") as f:
            json.dump(captured, f, ensure_ascii=False, indent=2)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
