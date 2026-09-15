# -*- coding: utf-8 -*-
"""探针 v10：调用真实 search/queryDetail 接口，确定参数形态并保存样例响应。"""
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
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
            locale="zh-CN",
        )
        page = ctx.new_page()
        page.goto("https://www.nmpa.gov.cn/datasearch/home-index.html", timeout=60000)
        page.wait_for_timeout(10000)
        base = "https://www.nmpa.gov.cn/datasearch/data/nmpadata/"
        probes = [
            ("GET 多参", base + "search?itemIds=%s&searchValue=%s&page=1&pageSize=5" % (ITEM_ID, "阿托伐他汀")),
            ("GET 单参", base + "search?itemId=%s&searchValue=%s&page=1&pageSize=5" % (ITEM_ID, "阿托伐他汀")),
        ]
        js = """async (args) => {
              const res = {};
              for (const [name, url] of args) {
                try {
                  const r = await fetch(url, {headers: {'Accept': 'application/json'}});
                  const t = await r.text();
                  res[name] = {status: r.status, text: t.slice(0, 600)};
                } catch (e) { res[name] = {err: String(e)}; }
              }
              // POST form
              try {
                const body = new URLSearchParams();
                body.set('itemIds', '__ITEM__'); body.set('searchValue', '阿托伐他汀');
                body.set('page', '1'); body.set('pageSize', '5');
                const r = await fetch('__BASE__search', {method: 'POST',
                  headers: {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'},
                  body: body.toString()});
                res['POST form'] = {status: r.status, text: (await r.text()).slice(0, 600)};
              } catch (e) { res['POST form'] = {err: String(e)}; }
              // POST json
              try {
                const r = await fetch('__BASE__search', {method: 'POST',
                  headers: {'Content-Type': 'application/json'},
                  body: JSON.stringify({itemIds: '__ITEM__', searchValue: '阿托伐他汀', page: 1, pageSize: 5})});
                res['POST json'] = {status: r.status, text: (await r.text()).slice(0, 600)};
              } catch (e) { res['POST json'] = {err: String(e)}; }
              return res;
            }"""
        js = js.replace("__ITEM__", ITEM_ID).replace("__BASE__", base)
        out = page.evaluate(js, probes)
        for name, r in out.items():
            print(name, "→", json.dumps(r, ensure_ascii=False)[:350])
        with open(os.path.join(OUT_DIR, "nmpa_search_call.json"), "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
