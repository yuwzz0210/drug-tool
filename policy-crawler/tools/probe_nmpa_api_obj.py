# -*- coding: utf-8 -*-
"""探针 v9：加载混淆后的 api.js/ajax.js，运行时解出真实接口方法与 URL。"""
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
        page.wait_for_timeout(10000)
        # 在空页面上按顺序加载 api.js / ajax.js，读取运行时对象
        page.evaluate("""async () => {
          const load = (src) => new Promise((res, rej) => {
            const s = document.createElement('script');
            s.src = src; s.onload = res; s.onerror = () => rej(new Error(src));
            document.body.appendChild(s);
          });
          await load('/datasearch/js/api.js');
          await load('/datasearch/js/ajax.js');
          return true;
        }""")
        page.wait_for_timeout(3000)
        info = page.evaluate("""() => {
          const out = {};
          for (const name of ['api', 'ajax', 'Ajax', 'API']) {
            const obj = window[name];
            if (obj && typeof obj === 'object') {
              const keys = [];
              for (const k of Object.keys(obj)) {
                let v = obj[k];
                if (typeof v === 'function') v = v.toString().slice(0, 260);
                else if (typeof v === 'string') v = v.slice(0, 200);
                keys.push([k, v]);
              }
              out[name] = keys;
            }
          }
          return out;
        }""")
        with open(os.path.join(OUT_DIR, "nmpa_api_obj.json"), "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
        for name, keys in info.items():
            print("== window." + name, "keys:", len(keys))
            for k, v in keys:
                print("  ", k, "=", str(v)[:180].replace("\n", " "))
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
