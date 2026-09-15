# -*- coding: utf-8 -*-
"""Click the 搜索 button inside the elian DomesticList frame, then dump the
data grid + pager structure (also works if data loads only after search)."""
import io
import json
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from playwright.sync_api import sync_playwright

URL = ("https://yp.eliancloud.cn/Member/DataQuery/DomesticList"
       "?ChannelID=e759afea-713a-4439-8cf4-0ffad89578a3")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def main():
    with sync_playwright() as pw:
        b = pw.chromium.launch(
            headless=True, args=["--disable-blink-features=AutomationControlled"])
        c = b.new_context(user_agent=UA, locale="zh-CN",
                          viewport={"width": 1600, "height": 1000})
        c.add_cookies(json.load(open(r"logs/elian_cookies.json",
                                     encoding="utf-8")))
        p = c.new_page()
        p.goto(URL, wait_until="domcontentloaded", timeout=90000)
        time.sleep(8)
        f = next((fr for fr in p.frames
                  if "/Member/DataQuery/DomesticList" in fr.url.split("?")[0]),
                 p)
        clicked = False
        for txt in ("搜 索", "搜索"):
            try:
                loc = f.get_by_text(txt, exact=False).first
                if loc.is_visible():
                    loc.click(timeout=3000)
                    clicked = True
                    break
            except Exception:
                continue
        print("search clicked", clicked)
        time.sleep(6)
        out = f.evaluate("""() => {
          let tbl = null;
          for (const t of document.querySelectorAll('table')) {
            const hs = [...t.querySelectorAll('thead th')]
                .map(e => (e.innerText||'').trim()).join('|');
            if (hs.includes('批准文号') && hs.includes('产品名称')) { tbl = t; break; }
          }
          const body = document.body.innerText || '';
          const res = {found: !!tbl, bodyLen: body.length};
          if (tbl) {
            let node = tbl, chain = [];
            for (let i=0;i<7 && node;i++) {
              chain.push({cls:(node.className||'').toString(),
                          id:node.id||'', tag:node.tagName});
              node = node.parentElement;
            }
            res.chain = chain;
            res.parentTail = (tbl.parentElement.outerHTML||'').slice(-2500);
            res.clickables = [...document.querySelectorAll(
                'a,button,div[onclick],li,span')]
                .filter(e => { const t=(e.innerText||'').trim();
                  return /下一页|下页|末页|尾页|^\\d{1,3}$/.test(t) ||
                         /page|pager|next|Page/i.test((e.className||'')+
                         (e.getAttribute('onclick')||'')); })
                .slice(0,50)
                .map(e => ({tag:e.tagName, text:(e.innerText||'').trim().slice(0,10),
                  cls:(e.className||'').toString().slice(0,90),
                  onclick:(e.getAttribute('onclick')||'').slice(0,120)}));
          } else {
            res.snippet = body.slice(0, 900);
          }
          return res;
        }""")
        print(json.dumps(out, ensure_ascii=False, indent=1)[:7000])
        b.close()


if __name__ == "__main__":
    main()
