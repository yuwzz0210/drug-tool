# -*- coding: utf-8 -*-
"""CDE 上市药品信息 -> 说明书(PDF) 采集器（步骤3 第二通道）。

第一通道（化学药品目录集）只覆盖过评/参比制剂；原研/进口/生物制品/新分类
仿制药的说明书在 CDE「上市药品信息」（按受理号）里。本采集器:
    按药品名称检索上市药品信息
        -> 受理记录（acceptid + acceptidCODE + 企业）
        -> 公司名/品名匹配防张冠李戴（唯一或公司命中才自动关联）
        -> 详情页取"说明书"附件
        -> /xxgk/PostMarketDownload 下载 PDF -> 关键节解析

合规：>=4 秒间隔 + 随机抖动；仅访问公开页面与附件。
用法:
    python -m collectors.cde_postmarket --db policy_crawler.db --out work/pi_pm \
        --delay 4 --results logs/cde_pm_full.jsonl
"""
import argparse
import json
import logging
import os
import random
import re
import sqlite3
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from collectors.cde_leaflets import parse_leaflet_sections  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

log = logging.getLogger("policy-crawler.collectors.cde_postmarket")

LIST_URL = ("https://www.cde.org.cn/main/xxgk/listpage/"
            "b40868b5e21c038a6aa8b4319d21b07d")
DETAIL_URL = ("https://www.cde.org.cn/main/xxgk/postmarketpage"
              "?acceptidCODE={}")
DOWNLOAD_URL = ("https://www.cde.org.cn/main/xxgk/PostMarketDownload"
                "?attidCODE={}&tableid={}")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def load_targets(db_path, limit=None):
    """Products without a leaflet, with names/companies for pass-B search."""
    db = sqlite3.connect(db_path)
    rows = db.execute("""
        SELECT p.product_id, p.generic_name, p.manufacturer_norm,
               r.approval_number, r.holder, m.generic_name
        FROM drug_product p
        LEFT JOIN drug_registration r ON r.product_id = p.product_id
        LEFT JOIN drug_molecule m ON m.molecule_id = p.molecule_id
        WHERE (p.package_insert_url IS NULL OR p.package_insert_url = '')
        ORDER BY p.product_id
    """).fetchall()
    db.close()
    out = []
    seen = set()
    for r in rows:
        pid = r[0]
        if pid in seen:
            continue
        seen.add(pid)
        out.append({
            "product_id": pid,
            "name": r[1] or r[5] or "",
            "manufacturer": r[2] or "",
            "approval_number": r[3] or "",
            "holder": r[4] or "",
        })
    if limit:
        out = out[:limit]
    return out


def name_matches(product_name, drgnamecn):
    """Loose match: 品种核心名命中受理记录名（容忍盐基/剂型差异）。"""
    p = re.sub(r"[（(].*?[)）]|注射液|注射用|片|胶囊|颗粒|散|溶液|口服", "",
               product_name or "")
    d = re.sub(r"[（(].*?[)）]", "", drgnamecn or "")
    if not p or not d:
        return False
    return p in d or d in p


def company_matches(company_a, company_b):
    """Two company strings overlap on a >=4 char token."""
    def tokens(s):
        return {t for t in re.split(r"[;；,，、\s]+", s or "")
                if len(t) >= 4}
    return bool(tokens(company_a) & tokens(company_b)) or (
        (company_a or "") in (company_b or "") or
        (company_b or "") in (company_a or ""))


def company_token_set(companys):
    """Normalize repeated/split company strings into one token set."""
    return frozenset(
        t for t in re.split(r"[;；,，、/\s]+", companys or "") if len(t) >= 4)


def token_sets_overlap(a, b):
    """True when any token contains or is contained by a token of the other."""
    a, b = set(a), set(b)
    if a & b:
        return True
    return any(x in y or y in x for x in a for y in b)


def group_by_owner(matched):
    """Group records whose company token sets overlap (transitive)."""
    groups = []
    for r in matched:
        key = company_token_set(r.get("companys", ""))
        placed = False
        for g in groups:
            if token_sets_overlap(key, g["key"]):
                g["key"] |= set(key)
                g["recs"].append(r)
                placed = True
                break
        if not placed:
            groups.append({"key": set(key), "recs": [r]})
    return [g["recs"] for g in groups]


def decide_acceptance(product, records):
    """Pick the acceptance record(s) safe to auto-link, or mark ambiguous."""
    matched = [r for r in records
               if name_matches(product.get("name"), r.get("drgnamecn"))]
    if not matched:
        return [], "no_name_match"
    groups = group_by_owner(matched)
    if len(groups) == 1:
        return matched, "unique"
    our_company = product.get("holder") or product.get("manufacturer") or ""
    if not our_company:
        return [], "ambiguous_no_company"
    our_tokens = company_token_set(our_company)
    hits = [g for g in groups
            if g and token_sets_overlap(company_token_set(
                g[0].get("companys", "")), our_tokens)]
    if len(hits) == 1:
        return hits[0], "company_match"
    if len(hits) > 1:
        return [r for g in hits for r in g], "company_match_multi"
    return [], "company_no_match"


class CdePostmarketCollector:
    def __init__(self, out_dir, headless=True, delay=4.0):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"])
        self._ctx = self._browser.new_context(
            user_agent=UA, locale="zh-CN",
            viewport={"width": 1440, "height": 960},
            accept_downloads=True)
        self.page = self._ctx.new_page()
        self.detail_page = self._ctx.new_page()
        self.out_dir = out_dir
        os.makedirs(out_dir, exist_ok=True)
        self.delay = float(delay)
        self._ready = False

    def close(self):
        try:
            self._browser.close()
        finally:
            self._pw.stop()

    def open_list(self):
        self.page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60000)
        deadline = time.time() + 25
        while time.time() < deadline:
            title = self.page.title() or ""
            if title and "jsjiami" not in title.lower():
                break
            time.sleep(2)
        self.page.wait_for_function(
            "window.defaultObj && document.body.innerText.includes('上市药品信息')",
            timeout=40000)
        self._ready = True
        time.sleep(1.0)
        log.info("postmarket list ready")

    def search_by_name(self, name):
        parse_js = """() => {
          const rows = [];
          document.querySelectorAll('#listDrugInfoTbody tr').forEach(tr => {
            const tds = tr.querySelectorAll('td');
            if (tds.length < 7) return;
            const m = (tr.getAttribute('ondblclick') || '')
                .match(/openListDrugInfoDetail\\('([^']+)'\\)/);
            rows.push({
              acceptid: (tds[1].innerText || '').trim(),
              drgnamecn: (tds[2].innerText || '').trim(),
              drugtype: (tds[3].innerText || '').trim(),
              registerkind: (tds[4].innerText || '').trim(),
              companys: (tds[5].innerText || '').trim(),
              createddate: (tds[6].innerText || '').trim(),
              acceptidCODE: m ? m[1] : ''
            });
          });
          return rows;
        }"""
        before = self.page.evaluate(
            "(document.getElementById('listDrugInfoTbody')||{innerText:''}).innerText")
        self.page.fill("#drugname2", name)
        self.page.evaluate("defaultObj.methods.getListDrugInfoList()")
        deadline = time.time() + 25
        rows = []
        while time.time() < deadline:
            now = self.page.evaluate(
                "(document.getElementById('listDrugInfoTbody')||{innerText:''}).innerText")
            if now != before:
                rows = self.page.evaluate(parse_js)
                break
            time.sleep(0.4)
        return rows

    def open_detail(self, acceptcode):
        self.detail_page.goto(DETAIL_URL.format(acceptcode),
                              wait_until="domcontentloaded", timeout=60000)
        try:
            self.detail_page.wait_for_function(
                "document.body.innerText.includes('相关附件信息') || "
                "document.body.innerText.includes('受理号')", timeout=25000)
        except Exception:
            pass
        time.sleep(0.8)
        anchors = self.detail_page.eval_on_selector_all(
            "a.textLink[data-fileid]",
            """els => els.map(e => ({
                fileid: e.getAttribute('data-fileid'),
                acceptid: e.getAttribute('data-acceptid'),
                filename: e.getAttribute('data-filename')
            }))""")
        return anchors

    def download_pdf(self, fileid, acceptid, dest):
        resp = self._ctx.request.get(
            DOWNLOAD_URL.format(fileid, acceptid), timeout=120000)
        if resp.status != 200:
            raise RuntimeError("download HTTP %s" % resp.status)
        data = resp.body()
        with open(dest, "wb") as fh:
            fh.write(data)
        return len(data)

    def polite_pause(self):
        time.sleep(self.delay + random.uniform(0, 1.0))


def run_batch(targets, out_dir, delay=4.0, headless=True, results_path=None):
    col = CdePostmarketCollector(out_dir, headless=headless, delay=delay)
    results = []
    rf = open(results_path, "a", encoding="utf-8") if results_path else None
    try:
        col.open_list()
        total = len(targets)
        for i, tgt in enumerate(targets, 1):
            rec = dict(tgt)
            rec["channel"] = "postmarket"
            rec["status"] = "pending"
            try:
                records = col.search_by_name(tgt.get("name") or "")
                if not records:
                    rec.update(status="not_found",
                               note="postmarket no record for name")
                else:
                    picks, how = decide_acceptance(tgt, records)
                    rec["accepts"] = records
                    rec["match"] = how
                    if not picks:
                        rec.update(status="ambiguous",
                                   note="no safe acceptance match")
                    else:
                        # prefer newest createddate
                        picks.sort(key=lambda r: r.get("createddate") or "")
                        a = picks[-1]
                        anchors = col.open_detail(a.get("acceptidCODE") or "")
                        leaf = [x for x in anchors
                                if "说明书" in (x.get("filename") or "")]
                        if not leaf:
                            rec.update(status="no_leaflet",
                                       note="detail has no insert attachment")
                        else:
                            x = leaf[-1]
                            safe = re.sub(r"[\\/:*?\"<>|]", "_",
                                          x["filename"] or a.get("acceptid"))
                            dest = os.path.join(out_dir, safe)
                            size = col.download_pdf(x["fileid"],
                                                    x["acceptid"], dest)
                            parsed = parse_leaflet_sections(dest)
                            rec.update(
                                status="ok", acceptid=a.get("acceptid"),
                                acceptcode=a.get("acceptidCODE"),
                                drgnamecn=a.get("drgnamecn"),
                                createddate=a.get("createddate"),
                                companys=a.get("companys"),
                                file_id=x["fileid"], filename=x["filename"],
                                catalog_rid=a.get("acceptidCODE") or "",
                                pdf_url=DOWNLOAD_URL.format(
                                    x["fileid"], x["acceptid"]),
                                source_url=DETAIL_URL.format(
                                    a.get("acceptidCODE") or ""),
                                dest=dest, size=size,
                                section_keys=list(parsed["sections"].keys()),
                                parse_error=parsed.get("error"))
            except Exception as exc:
                log.exception("product %s failed", tgt.get("product_id"))
                rec.update(status="error", error=repr(exc))
            results.append(rec)
            if rf:
                rf.write(json.dumps(rec, ensure_ascii=False) + "\n")
                rf.flush()
            log.info("[%d/%d] product=%s name=%s status=%s", i, total,
                     tgt.get("product_id"), tgt.get("name"), rec.get("status"))
            if i < total:
                col.polite_pause()
    finally:
        if rf:
            rf.close()
        col.close()
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="policy_crawler.db")
    ap.add_argument("--out", default="work/pi_pm")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--delay", type=float, default=4.0)
    ap.add_argument("--results", default=None)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    targets = load_targets(args.db, limit=args.limit)
    print("TARGETS", len(targets))
    results = run_batch(targets, args.out, delay=args.delay,
                        results_path=args.results)
    from collections import Counter
    st = Counter(r.get("status") for r in results)
    print("SUMMARY", json.dumps(st, ensure_ascii=False))


if __name__ == "__main__":
    main()
