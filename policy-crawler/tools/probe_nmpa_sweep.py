# -*- coding: utf-8 -*-
"""探针 v7：在浏览器会话内批量探测 nmpadata 列表端点（GET+POST），找 200。"""
import os
import sys

from playwright.sync_api import sync_playwright


OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "work",
)
ITEM_ID = "ff80808183cad75001840881f848179f"
CANDIDATES = [
    "queryData", "selectData", "selectList", "queryList", "getData", "dataList",
    "pageList", "searchData", "getList", "selectPage", "selectDataList",
    "getDataList", "search", "query", "list", "select", "data", "searchList",
    "nmpadata", "tableData", "getTable", "queryAll", "selectAll", "getSearchList",
]


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
            locale="zh-CN",
        )
        page = ctx.new_page()
        page.goto("https://www.nmpa.gov.cn/datasearch/search-result.html?itemId=" + ITEM_ID, timeout=60000)
        page.wait_for_timeout(10000)
        base = "https://www.nmpa.gov.cn/datasearch/data/nmpadata/"
        hits = []
        for name in CANDIDATES:
            url = base + name
            result = page.evaluate(
                """async (u) => {
                  const out = [];
                  try {
                    let r = await fetch(u + '?itemIds=%s&searchValue=%s&page=1&pageSize=5',
                        {headers: {'Accept': 'application/json'}});
                    let t = await r.text();
                    out.push('GET ' + r.status + ' ' + t.slice(0, 200));
                  } catch (e) { out.push('GET ERR ' + e.message); }
                  try {
                    let r = await fetch(u, {method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({itemIds: '%s', searchValue: '阿托伐他汀', page: 1, pageSize: 5})});
                    let t = await r.text();
                    out.push('POST ' + r.status + ' ' + t.slice(0, 200));
                  } catch (e) { out.push('POST ERR ' + e.message); }
                  return out;
                }""" % (ITEM_ID, "阿托伐他汀", ITEM_ID),
                url,
            )
            for line in result:
                if line.startswith(("GET 200", "POST 200")):
                    hits.append(name + " :: " + line)
            print(name, "→", " / ".join(x[:80] for x in result))
        print("\n=== 200 命中 ===")
        for h in hits:
            print(h[:220])
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
