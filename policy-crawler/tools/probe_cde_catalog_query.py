# -*- coding: utf-8 -*-
"""End-to-end proof for the CDE catalog -> leaflet chain.

1. Search the catalog by approval number (pzwh).
2. Capture the getList JSON (record ids, field names).
3. Open the first detail page and capture getInfoById JSON (incl. smsContent).
4. Download the leaflet PDF through the browser session and check it parses.

Usage:
    python tools/probe_cde_catalog_query.py <pzwh> [out_dir]
"""
import json
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PZWH = sys.argv[1] if len(sys.argv) > 1 else "国药准字H20193006"
OUT = sys.argv[2] if len(sys.argv) > 2 else "logs"
CATALOG_URL = ("https://www.cde.org.cn/hymlj/listpage/"
               "9cd8db3b7530c6fa0c86485e563f93c7")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def main():
    from playwright.sync_api import sync_playwright

    bodies = []

    def on_response(resp):
        url = resp.url
        if "/hymlj/getList" not in url and "/hymlj/getInfoById" not in url:
            return
        try:
            body = resp.text()
        except Exception:
            body = ""
        bodies.append({"url": url, "status": resp.status, "body": body})

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(user_agent=UA, locale="zh-CN",
                                  viewport={"width": 1440, "height": 960},
                                  accept_downloads=True)
        page = ctx.new_page()
        page.on("response", on_response)
        page.goto(CATALOG_URL, wait_until="domcontentloaded", timeout=60000)
        for _ in range(6):
            time.sleep(2)
            if page.title() and "jsjiami" not in page.title().lower():
                break
        # wait until the initial list has rendered before searching, so the
        # search response is the last getList captured
        try:
            page.wait_for_function(
                "document.body.innerText.includes('共 ') && "
                "document.body.innerText.includes('条')", timeout=30000)
        except Exception as exc:
            print("INIT_WAIT_FAIL", repr(exc))
        time.sleep(1)
        bodies.clear()
        page.fill("#pzwh", PZWH)
        # 查询 button contains 查 询; click the first visible one in the form
        page.locator("button:has-text('查')").first.click()
        try:
            page.wait_for_function(
                "document.body.innerText.includes(%s)" % json.dumps(PZWH),
                timeout=20000)
        except Exception as exc:
            print("SEARCH_WAIT_FAIL", repr(exc))
        time.sleep(1)
        text = page.inner_text("body")
        idx = text.find("序号")
        print("LIST_TEXT", text[idx:idx + 900].replace("\n", " | "))

        getlist = [b for b in bodies if "/hymlj/getList" in b["url"]]
        if not getlist:
            print("NO_GETLIST", json.dumps(
                [{"u": b["url"], "s": b["status"]} for b in bodies],
                ensure_ascii=False))
            browser.close()
            return
        print("LIST_JSON", getlist[-1]["body"][:3000])
        data = json.loads(getlist[-1]["body"]).get("data") or {}
        recs = data.get("records") or data.get("list") or []
        print("REC_COUNT", len(recs))
        print("REC0", json.dumps(recs[0], ensure_ascii=False) if recs else "{}")

        if not recs:
            browser.close()
            return
        rid = recs[0].get("idCode")
        row = page.query_selector("a[href*='detailPage']")
        if row:
            href = row.get_attribute("href")
            rid = rid or href.rsplit("/", 1)[-1]
            print("ROW_HREF", href)
        if not rid:
            print("NO_RECORD_ID")
            browser.close()
            return

        bodies.clear()
        page.goto("https://www.cde.org.cn" + href, wait_until="domcontentloaded",
                  timeout=60000)
        for _ in range(10):
            time.sleep(2)
            if any("/hymlj/getInfoById" in b["url"] for b in bodies):
                break
        info = [b for b in bodies if "/hymlj/getInfoById" in b["url"]]
        print("DETAIL_NET", json.dumps(
            [{"u": b["url"], "s": b["status"]} for b in bodies[-6:]],
            ensure_ascii=False))
        print("DETAIL_BODY_HEAD", (page.inner_text("body") or "")[:600]
              .replace("\n", " | "))
        print("DETAIL_JSON", info[-1]["body"][:2500] if info else "NONE")
        detail = (json.loads(info[-1]["body"]).get("data") or {}
                  if info else {})
        sms = detail.get("smsContent") or ""
        fname = detail.get("smsAttname") or PZWH + ".pdf"
        print("SMS_CONTENT", sms, "ATNAME", fname)

        if not sms:
            browser.close()
            return
        dl_url = "https://www.cde.org.cn/hymlj/download/sms/" + sms
        resp = ctx.request.get(dl_url, timeout=90000)
        print("DOWNLOAD_STATUS", resp.status, resp.headers.get("content-type"),
              len(resp.body()))
        os.makedirs(OUT, exist_ok=True)
        path = os.path.join(OUT, "pi_" + PZWH + ".pdf")
        with open(path, "wb") as fh:
            fh.write(resp.body())
        print("SAVED", path)
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                pages = pdf.pages[:3]
                txt = "\n".join((p.extract_text() or "") for p in pages)
            print("PDF_TEXT_HEAD", txt[:1500].replace("\n", " | "))
        except Exception as exc:
            print("PDF_PARSE_FAIL", repr(exc))
        browser.close()


if __name__ == "__main__":
    main()
