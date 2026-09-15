# -*- coding: utf-8 -*-
"""Dump the elian data-grid container HTML to locate its real pager control."""
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
        out = f.evaluate("""() => {
          let tbl = null;
          for (const t of document.querySelectorAll('table')) {
            const hs = [...t.querySelectorAll('thead th')]
                .map(e => (e.innerText||'').trim()).join('|');
            if (hs.includes('批准文号') && hs.includes('产品名称')) { tbl = t; break; }
          }
          if (!tbl) return {found:false};
          let node = tbl, chain = [];
          for (let i=0;i<7 && node;i++) {
            chain.push({cls:(node.className||'').toString(),
                        id:node.id||'', tag:node.tagName});
            node = node.parentElement;
          }
          const body = document.body.innerText || '';
          return {
            found: true,
            chain,
            tableTail: tbl.outerHTML.slice(-500),
            parentTail: (tbl.parentElement.outerHTML||'').slice(-1800),
            aroundPage: body.slice(Math.max(0, body.indexOf('共 1')-100),
                                   body.indexOf('共 1')+300),
            clickables: [...document.querySelectorAll(
                'a,button,div[onclick],li')]
                .filter(e => { const t=(e.innerText||'').trim();
                  return /下一页|下页|末页|尾页|^\\d{1,3}$/.test(t) ||
                         /page|pager|next|Page/i.test((e.className||'')+
                         (e.getAttribute('onclick')||'')); })
                .slice(0,40)
                .map(e => ({tag:e.tagName, text:(e.innerText||'').trim().slice(0,10),
                  cls:(e.className||'').toString().slice(0,90),
                  onclick:(e.getAttribute('onclick')||'').slice(0,120)}))
          };
        }""")
        print(json.dumps(out, ensure_ascii=False, indent=1)[:5500])
        b.close()


if __name__ == "__main__":
    main()
