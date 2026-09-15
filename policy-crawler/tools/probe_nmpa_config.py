# -*- coding: utf-8 -*-
"""探针 v2：在浏览器会话内读取 NMPA 数据查询的配置，还原接口调用格式。"""
import json
import os
import sys

from playwright.sync_api import sync_playwright


OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "work",
)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
            locale="zh-CN",
        )
        page = ctx.new_page()
        page.goto("https://www.nmpa.gov.cn/datasearch/home-index.html", timeout=60000)
        page.wait_for_timeout(12000)

        result = page.evaluate("""
        async () => {
          const res = await fetch('/datasearch/config/NMPA_DATA.json?t=' + Date.now());
          const data = await res.json();
          const drug = (data || []).find(d => (d.itemList||[]).some(i => i.itemName.includes('境内生产药品')));
          const item = drug ? drug.itemList.find(i => i.itemName.includes('境内生产药品')) : null;
          let cfg = null;
          if (item) {
            const c = await fetch('/datasearch/config/' + item.itemId + '.json?t=' + Date.now());
            cfg = await c.json();
          }
          return {data: data, item: item, cfg: cfg};
        }
        """)
        with open(os.path.join(OUT_DIR, "nmpa_config_dump.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        item = result.get("item") or {}
        print("ITEM:", json.dumps(item, ensure_ascii=False)[:500])
        cfg = result.get("cfg") or {}
        print("CFG keys:", list(cfg.keys()))
        print("queryItemFeild:", json.dumps(cfg.get("queryItemFeild", []), ensure_ascii=False)[:800])
        print("列表页字段:", json.dumps(cfg.get("listFeild", cfg.get("listField", [])), ensure_ascii=False)[:800])
        ctx.storage_state(path=os.path.join(OUT_DIR, "nmpa_browser_state.json"))
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
