# -*- coding: utf-8 -*-
"""探针 v6：触发搜索后抓完整列表请求；必要时直接探测候选列表端点。"""
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
        )
        page = ctx.new_page()

        def on_response(resp):
            url = resp.url
            if "/datasearch/data/" in url:
                try:
                    body = resp.text()[:2000]
                except Exception:
                    body = ""
                captured.append({"status": resp.status, "url": url, "body": body})

        page.on("response", on_response)
        page.goto(
            "https://www.nmpa.gov.cn/datasearch/search-result.html?itemId=" + ITEM_ID,
            timeout=60000,
        )
        page.wait_for_timeout(10000)
        # 移除引导遮罩，避免拦截点击
        page.evaluate("""
          () => {
            document.querySelectorAll('.introjs-overlay,.introjs-helperLayer,.introjs-tooltip,.introjs-arrow')
              .forEach(el => el.remove());
            if (window.introJs) { try { window.introJs().exit(); } catch (e) {} }
          }
        """)
        box = page.locator("input[placeholder*='请输入']").first
        box.fill("阿托伐他汀")
        page.evaluate("""
          () => {
            document.querySelectorAll('.introjs-overlay,.introjs-helperLayer,.introjs-tooltip,.introjs-arrow')
              .forEach(el => el.remove());
          }
        """)
        page.locator("button:visible").first.click()
        page.wait_for_timeout(3000)
        # countNums 后点击下拉结果中的数据集行，触发列表加载
        try:
            page.get_by_text("境内生产药品", exact=True).last.click()
            print("已点击数据集行")
        except Exception as exc:
            print("点击数据集行失败:", exc)
        page.wait_for_timeout(12000)
        print("触发搜索后捕获:", len(captured))
        for c in captured:
            print(" ", c["status"], c["url"][:170])
            print("   BODY:", c["body"][:260].replace("\n", " "))

        # 若列表未出现，直接探测候选端点
        if not any("select" in c["url"] or "list" in c["url"] or "query" in c["url"] for c in captured):
            print("\n== 探测候选列表端点 ==")
            for name in ("selectList", "queryList", "getList", "listData", "pageData", "searchList", "selectData"):
                url = ("https://www.nmpa.gov.cn/datasearch/data/nmpadata/%s"
                       "?itemIds=%s&searchValue=%s&page=1&pageSize=5"
                       % (name, ITEM_ID, "阿托伐他汀"))
                try:
                    result = page.evaluate(
                        "async (u) => { const r = await fetch(u, {headers:{'Content-Type':'application/json'}});"
                        " const t = await r.text(); return {status: r.status, text: t.slice(0,500)}; }",
                        url,
                    )
                    print(name, "→", result["status"], result["text"][:200].replace("\n", " "))
                except Exception as exc:
                    print(name, "→ 异常", exc)
        with open(os.path.join(OUT_DIR, "nmpa_list_capture.json"), "w", encoding="utf-8") as f:
            json.dump(captured, f, ensure_ascii=False, indent=2)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
