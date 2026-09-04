# -*- coding: utf-8 -*-
"""Second-channel end-to-end proof: CDE 上市药品信息 -> 说明书 PDF.

1. Search the 上市药品信息 list by drug name (getListDrugInfoList).
2. Capture records (acceptid + acceptidCODE).
3. Open postmarketpage detail and find the 说明书 attachment anchor.
4. Download the PDF through the browser session and parse sections.

Usage:
    python tools/probe_cde_postmarket.py <drugname> [out_dir]
"""
import json
import os
import re
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DRUG = sys.argv[1] if len(sys.argv) > 1 else "贝福替尼"
OUT = sys.argv[2] if len(sys.argv) > 2 else "logs"
LIST_URL = ("https://www.cde.org.cn/main/xxgk/listpage/"
            "b40868b5e21c038a6aa8b4319d21b07d")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(user_agent=UA, locale="zh-CN",
                                  viewport={"width": 1440, "height": 960},
                                  accept_downloads=True)
        page = ctx.new_page()
        page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60000)
        for _ in range(6):
            time.sleep(2)
            if page.title() and "jsjiami" not in page.title().lower():
                break
        try:
            page.wait_for_function(
                "document.body.innerText.includes('共 ') && "
                "window.defaultObj", timeout=30000)
        except Exception as exc:
            print("INIT_WAIT_FAIL", repr(exc))
        time.sleep(1)

        page.fill("#drugname2", DRUG)
        bodies = []
        with page.expect_response(
                lambda r: "/xxgk/getPostMarketList" in r.url and
                          r.request.method == "POST", timeout=20000) as ri:
            page.evaluate("defaultObj.methods.getListDrugInfoList()")
        resp = ri.value
        payload = resp.json()
        data = payload.get("data") or {}
        recs = data.get("records") or []
        print("REC_COUNT", len(recs))
        for r in recs[:10]:
            print("REC", json.dumps(r, ensure_ascii=False))
        if not recs:
            browser.close()
            return
        code = recs[0].get("acceptidCODE") or ""
        acceptid = recs[0].get("acceptid") or ""
        print("PICK", acceptid, code)
        page.goto("https://www.cde.org.cn/main/xxgk/postmarketpage"
                  "?acceptidCODE=" + code, wait_until="domcontentloaded",
                  timeout=60000)
        for _ in range(8):
            time.sleep(2)
            if "相关附件信息" in page.inner_text("body"):
                break
        anchors = page.eval_on_selector_all(
            "a.textLink[data-fileid]",
            """els => els.map(e => ({
                fileid: e.getAttribute('data-fileid'),
                acceptid: e.getAttribute('data-acceptid'),
                filename: e.getAttribute('data-filename')
            }))""")
        print("ANCHORS", json.dumps(anchors, ensure_ascii=False))
        leaf = [a for a in anchors if "说明书" in (a.get("filename") or "")]
        if not leaf:
            print("NO_LEAFLET_ANCHOR")
            browser.close()
            return
        a = leaf[0]
        dl_url = ("https://www.cde.org.cn/main/xxgk/PostMarketDownload"
                  "?attidCODE=%s&tableid=%s" % (a["fileid"], a["acceptid"]))
        r2 = ctx.request.get(dl_url, timeout=120000)
        print("DOWNLOAD_STATUS", r2.status, r2.headers.get("content-type"),
              len(r2.body()))
        os.makedirs(OUT, exist_ok=True)
        safe = re.sub(r"[\\/:*?\"<>|]", "_", a["filename"] or acceptid)
        path = os.path.join(OUT, "pm_" + safe)
        with open(path, "wb") as fh:
            fh.write(r2.body())
        print("SAVED", path)
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                txt = "\n".join((p.extract_text() or "") for p in pdf.pages[:3])
            print("PDF_TEXT_HEAD", txt[:800].replace("\n", " | "))
        except Exception as exc:
            print("PDF_PARSE_FAIL", repr(exc))
        browser.close()


if __name__ == "__main__":
    main()
