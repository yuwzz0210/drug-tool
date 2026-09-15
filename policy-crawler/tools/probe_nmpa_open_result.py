# -*- coding: utf-8 -*-
"""Open the result page with a keyword, then try clearing it to load the full
dataset (to decide whether full-enumeration is feasible via the UI)."""
import io
import json
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
HOME = "https://www.nmpa.gov.cn/datasearch/home-index.html"


def main():
    bodies = []

    def on_resp(resp):
        if "dataCenter" in resp.url and resp.request.method == "POST":
            try:
                bodies.append((resp.url, resp.json()))
            except Exception:
                pass

    with sync_playwright() as pw:
        b = pw.chromium.launch(
            headless=True, args=["--disable-blink-features=AutomationControlled"])
        c = b.new_context(user_agent=UA, locale="zh-CN",
                          viewport={"width": 1440, "height": 960})
        p = c.new_page()
        p.goto(HOME, wait_until="domcontentloaded", timeout=60000)
        time.sleep(12)
        box = next((el for el in p.locator("input").all()
                    if "请选择" not in (el.get_attribute("placeholder") or "")
                    and el.is_visible()), None)
        print("box", box is not None)
        if box:
            box.fill("阿")
            box.press("Enter")
        time.sleep(10)
        result = None
        for pg in c.pages:
            if "search-result" in pg.url:
                result = pg
        print("result found", result is not None)
        if result is None:
            b.close()
            return
        result.on("response", on_resp)
        result.wait_for_timeout(5000)
        print("bodies", len(bodies))
        for url, js in bodies[:2]:
            d = js.get("data") or {}
            print("after keyword total", d.get("total"), "rows",
                  len(d.get("list") or []))
        # inspect inputs/buttons/dropdowns on result page
        try:
            inputs = result.locator("input")
            phs = []
            for i in range(inputs.count()):
                try:
                    inp = inputs.nth(i)
                    if inp.is_visible():
                        phs.append(inp.get_attribute("placeholder"))
                except Exception:
                    continue
            print("visible inputs placeholders", phs)
            btns = result.eval_on_selector_all(
                "button", "els => els.map(e => (e.innerText||'').trim()).filter(Boolean)")
            print("buttons", btns[:20])
        except Exception as exc:
            print("inspect err", repr(exc)[:120])
        # clear all visible inputs and press Enter
        try:
            for i in range(inputs.count()):
                try:
                    inp = inputs.nth(i)
                    if inp.is_visible():
                        inp.fill("")
                except Exception:
                    continue
            visible = [inputs.nth(i) for i in range(inputs.count())
                       if inputs.nth(i).is_visible()]
            if visible:
                visible[0].press("Enter")
        except Exception as exc:
            print("clear enter err", repr(exc)[:120])
        time.sleep(8)
        print("bodies2", len(bodies))
        for url, js in bodies[-3:]:
            d = js.get("data") or {}
            print("after clear total", d.get("total"), "rows",
                  len(d.get("list") or []))
            lst = d.get("list") or []
            if lst:
                print("keys", sorted(lst[0].keys()))
                print("row0", json.dumps(lst[0], ensure_ascii=False)[:350])
        b.close()


if __name__ == "__main__":
    main()
