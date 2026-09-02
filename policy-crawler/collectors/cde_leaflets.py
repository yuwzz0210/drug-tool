# -*- coding: utf-8 -*-
"""CDE 化学药品目录集 -> 说明书(PDF) 采集器（步骤3 核心）。

数据链路（全部为 CDE 主动公开页面）:
    目录集列表页搜索批准文号/注册证号
        -> 记录行（含 detailPage/{idCode}）
        -> 详情页渲染 DOM（下载附件按钮携带 smsContent 文件 ID）
        -> /hymlj/download/sms/{smsContent} 下载说明书 PDF
        -> pdfplumber 抽取【适应症】【用法用量】【贮藏】等关键节

合规: 逐条搜索间隔 >= 4 秒 + 随机抖动; 仅访问公开页面与附件;
      不绕过任何鉴权/验证码（页面自身的 JS 挑战由真实浏览器自然通过）。

用法:
    python -m collectors.cde_leaflets --db policy_crawler.db --out ../work/pi \
        --limit 20 --delay 4
    python -m collectors.cde_leaflets --approval-num 国药准字H20193006 --out ../work/pi

当前只落 PDF 与结果 JSONL（不写库），入库由 tools/import_cde_leaflets.py 完成。
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
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

log = logging.getLogger("policy-crawler.collectors.cde_leaflets")

CATALOG_LIST_URL = ("https://www.cde.org.cn/hymlj/listpage/"
                    "9cd8db3b7530c6fa0c86485e563f93c7")
DETAIL_URL = "https://www.cde.org.cn/hymlj/detailPage/{}"
DOWNLOAD_URL = "https://www.cde.org.cn/hymlj/download/sms/{}"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

SECTION_HEADINGS = [
    "适应症", "用法用量", "不良反应", "禁忌", "注意事项", "孕妇及哺乳期妇女用药",
    "儿童用药", "老年用药", "药物相互作用", "药物过量", "药理毒理", "药代动力学",
    "贮藏", "有效期", "执行标准", "批准文号", "药品上市许可持有人", "生产企业",
]


def load_targets(db_path, limit=None, only_missing=True):
    """Approval numbers of products lacking a leaflet (catalog order by id)."""
    db = sqlite3.connect(db_path)
    sql = """
        SELECT DISTINCT r.approval_number, p.product_id, p.generic_name,
               p.dosage_form, p.specification, p.trade_name, p.package_insert_url
        FROM drug_registration r
        JOIN drug_product p ON p.product_id = r.product_id
    """
    where = []
    if only_missing:
        where.append("(p.package_insert_url IS NULL OR p.package_insert_url = '')")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY p.product_id"
    rows = db.execute(sql).fetchall()
    db.close()
    if limit:
        rows = rows[:limit]
    return [
        {
            "approval_number": r[0] or "",
            "product_id": r[1],
            "generic_name": r[2] or "",
            "dosage_form": r[3] or "",
            "specification": r[4] or "",
            "trade_name": r[5] or "",
        }
        for r in rows if r[0]
    ]


class CdeLeafletCollector:
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

    def _wait_challenge(self, timeout=25):
        """CDE 首页/页面带 JS 挑战; 等待真实页面标题出现。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                title = self.page.title() or ""
            except Exception:
                title = ""
            if title and "jsjiami" not in title.lower():
                return True
            time.sleep(2)
        return False

    def open_catalog(self):
        """打开目录集列表页并等待首屏数据渲染完成。"""
        self.page.goto(CATALOG_LIST_URL, wait_until="domcontentloaded",
                       timeout=60000)
        if not self._wait_challenge():
            raise RuntimeError("CDE JS challenge not resolved on catalog page")
        self.page.wait_for_function(
            "document.body && document.body.innerText.includes('共 ')",
            timeout=40000)
        self._ready = True
        log.info("catalog ready: %s", self.page.url)

    def search_by_approval(self, pzwh):
        """Search catalog for one approval number; return matched records.

        The response of the page's own getList call is captured, so we get the
        authoritative JSON (incl. idCode for the detail page) without guessing
        from the DOM. The list page must stay current (details use detail_page).
        """
        self.page.fill("#pzwh", pzwh)
        with self.page.expect_response(
                lambda r: "/hymlj/getList" in r.url and
                          r.request.method == "POST", timeout=20000) as ri:
            self.page.locator("button:has-text('查')").first.click()
        resp = ri.value
        try:
            payload = resp.json()
        except Exception:
            payload = {}
        data = (payload.get("data") or {}) if isinstance(payload, dict) else {}
        records = data.get("records") or []
        matched = [r for r in records if (r.get("pzwh") or "") == pzwh]
        return matched or records[:0]

    @staticmethod
    def _detail_script():
        return """
        () => {
          const out = {};
          document.querySelectorAll('td[id]').forEach(td => {
            const t = (td.innerText || '').trim();
            if (t) out[td.id] = t;
          });
          const dl = document.querySelector('a.download');
          if (dl) out._dl_onclick = dl.getAttribute('onclick') || '';
          return out;
        }
        """

    def open_detail(self, rid):
        """Open detailPage/{rid}; wait for fields; return parsed detail dict."""
        self.detail_page.goto(DETAIL_URL.format(rid),
                              wait_until="domcontentloaded", timeout=60000)
        try:
            self.detail_page.wait_for_function(
                """() => {
                   const body = document.body.innerText || '';
                   return body.includes('活性成分') || body.includes('暂无');
                }""", timeout=25000)
        except Exception:
            pass
        time.sleep(0.8)
        return self.detail_page.evaluate(self._detail_script())

    def download_pdf(self, file_id, filename, dest):
        """Download leaflet PDF through the challenged browser session."""
        resp = self._ctx.request.get(DOWNLOAD_URL.format(file_id), timeout=120000)
        if resp.status != 200:
            raise RuntimeError("download HTTP %s" % resp.status)
        data = resp.body()
        with open(dest, "wb") as fh:
            fh.write(data)
        return len(data)

    def polite_pause(self, label):
        jitter = random.uniform(0, 1.0)
        wait = self.delay + jitter
        log.info("%s pause %.1fs", label, wait)
        time.sleep(wait)


def parse_leaflet_sections(pdf_path):
    """Extract text and 【section】 blocks from an official package insert PDF."""
    try:
        import pdfplumber
    except ImportError:
        return {"text": "", "sections": {}, "ok": False, "error": "pdfplumber missing"}
    try:
        pages_text = []
        with pdfplumber.open(pdf_path) as pdf:
            for p in pdf.pages:
                t = p.extract_text() or ""
                if t:
                    pages_text.append(t)
        text = "\n".join(pages_text)
    except Exception as exc:
        return {"text": "", "sections": {}, "ok": False, "error": repr(exc)}
    if not text.strip():
        return {"text": "", "sections": {}, "ok": True, "error": "empty text"}
    sections = {}
    # 【xxx】 blocks; heading may be wrapped across lines in extraction
    for m in re.finditer(r"【([^】]{2,20})】", text):
        name = m.group(1).strip()
        if any(h == name or h in name for h in SECTION_HEADINGS):
            start = m.end()
            nxt = re.search(r"【[^】]{2,20}】", text[start:])
            end = start + nxt.start() if nxt else len(text)
            sections[name] = text[start:end].strip()
    return {"text": text, "sections": sections, "ok": True, "error": ""}


def classify_storage(storage_text):
    """Normalize the 【贮藏】 section into a cold-chain class."""
    t = storage_text or ""
    if any(k in t for k in ("冷冻", "零下", "-20", "-18", "-80", "2℃以下",
                            "2°C以下")):
        return "冷冻"
    if any(k in t for k in ("冷藏", "2-8", "2~8", "2～8", "2-8℃", "2~8℃",
                            "2～8℃", "2°C~8°C", "冷处")):
        return "冷藏(2~8℃)"
    if any(k in t for k in ("阴凉", "不超过20", "≤20", "20℃以下", "避光且不超过20")):
        return "阴凉(≤20℃)"
    if not t or t in ("遮光，密闭保存", "密闭保存", "密封保存"):
        return "常温"
    return "常温"


def classify_route(route_text):
    """Normalize CDE 给药途径 to molecule.route vocabulary."""
    t = (route_text or "").strip()
    if not t:
        return ""
    if "吸入" in t:
        return "吸入"
    if any(k in t for k in ("注射", "静注", "皮下", "肌注", "静脉", "肌肉", "皮内")):
        return "注射"
    if any(k in t for k in ("口服", "含服", "舌下", "嚼服", "吞服")):
        return "口服"
    if any(k in t for k in ("外用", "局部", "贴", "涂", "滴", "喷", "直肠", "阴道")):
        return "外用"
    return t[:20]


def extract_leaflet_date(text):
    """Find 说明书修订/核准/批准日期 from the PDF text; return ISO date."""
    pats = [
        r"(修订日期|核准日期|批准日期)\s*[:：]?\s*(\d{4})[年\-/](\d{1,2})[月\-/](\d{1,2})日?",
    ]
    found = []
    for pat in pats:
        for m in re.finditer(pat, text or ""):
            kw = m.group(1)
            found.append((kw, "%04d-%02d-%02d" % (
                int(m.group(2)), int(m.group(3)), int(m.group(4)))))
    if not found:
        return ""
    for kw in ("修订日期", "核准日期"):
        for k, d in found:
            if k == kw:
                return d
    return found[-1][1]


def run_batch(targets, out_dir, delay=4.0, headless=True, results_path=None):
    """Run the catalog->detail->PDF chain for a list of approval numbers."""
    col = CdeLeafletCollector(out_dir, headless=headless, delay=delay)
    results = []
    rf = open(results_path, "a", encoding="utf-8") if results_path else None
    try:
        col.open_catalog()
        total = len(targets)
        for i, tgt in enumerate(targets, 1):
            pzwh = tgt["approval_number"]
            rec = {"pzwh": pzwh, "status": "pending"}
            try:
                rows = col.search_by_approval(pzwh)
                if not rows:
                    rec.update(status="not_found", note="catalog no record")
                else:
                    rec["rows"] = rows
                    hits = 0
                    for row in rows:
                        rid = row.get("idCode") or ""
                        if not rid:
                            raise RuntimeError("no idCode in catalog record")
                        detail = col.open_detail(rid)
                        rec["detail"] = {k: v for k, v in detail.items()
                                         if not k.startswith("_")}
                        onclick = detail.get("_dl_onclick", "")
                        m = re.search(
                            r"downloadFile\('([^']+)'\s*,\s*'([^']*)'\)",
                            onclick or "")
                        if not m:
                            continue
                        file_id, fname = m.group(1), m.group(2)
                        safe = re.sub(r"[\\/:*?\"<>|]", "_", fname or pzwh)
                        dest = os.path.join(out_dir, safe)
                        size = col.download_pdf(file_id, fname, dest)
                        parsed = parse_leaflet_sections(dest)
                        hits += 1
                        rec.update(
                            status="ok", file_id=file_id, filename=fname,
                            dest=dest, size=size,
                            section_keys=list(parsed["sections"].keys()),
                            text_head=parsed["text"][:200],
                            parse_error=parsed.get("error"))
                    rec["hits"] = hits
                    if hits == 0:
                        rec.update(
                            status="no_leaflet",
                            note="no downloadable leaflet on record(s)")
            except Exception as exc:
                log.exception("pzwh %s failed", pzwh)
                rec.update(status="error", error=repr(exc))
            results.append(rec)
            if rf:
                rf.write(json.dumps(rec, ensure_ascii=False) + "\n")
                rf.flush()
            summary = {k: rec.get(k) for k in
                       ("pzwh", "status", "size", "section_keys", "error", "note")}
            log.info("[%d/%d] %s", i, total, json.dumps(summary, ensure_ascii=False))
            if i < total:
                col.polite_pause(pzwh)
    finally:
        if rf:
            rf.close()
        col.close()
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="policy_crawler.db")
    ap.add_argument("--out", default="work/pi")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--approval-num", default=None,
                    help="single approval number (overrides --db)")
    ap.add_argument("--approval-nums", default=None,
                    help="comma separated approval numbers (overrides --db)")
    ap.add_argument("--delay", type=float, default=4.0)
    ap.add_argument("--headless", type=int, default=1)
    ap.add_argument("--results", default=None, help="JSONL output path")
    ap.add_argument("--skip-existing", type=int, default=1,
                    help="skip approval numbers already 'ok' in --results")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    done = set()
    if args.results and args.skip_existing and os.path.exists(args.results):
        with open(args.results, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("status") == "ok":
                    done.add(rec.get("pzwh"))

    nums = []
    if args.approval_nums:
        nums = [n.strip() for n in args.approval_nums.split(",") if n.strip()]
    elif args.approval_num:
        nums = [args.approval_num]
    if nums:
        targets = [{"approval_number": num,
                    "product_id": None, "generic_name": "",
                    "dosage_form": "", "specification": "",
                    "trade_name": ""} for num in nums]
    else:
        targets = load_targets(args.db, limit=args.limit)
    targets = [t for t in targets
               if not done or t["approval_number"] not in done]
    if not targets:
        print("NO_TARGETS")
        return
    print("TARGETS", len(targets))
    results = run_batch(targets, args.out, delay=args.delay,
                        headless=bool(args.headless),
                        results_path=args.results)
    ok = [r for r in results if r["status"] == "ok"]
    nf = [r for r in results if r["status"] == "not_found"]
    nl = [r for r in results if r["status"] == "no_leaflet"]
    err = [r for r in results if r["status"] == "error"]
    print("SUMMARY ok=%d not_found=%d no_leaflet=%d error=%d" %
          (len(ok), len(nf), len(nl), len(err)))
    for r in results:
        print(json.dumps({k: r.get(k) for k in
                          ("pzwh", "status", "size", "section_keys",
                           "error", "note")}, ensure_ascii=False))
    if args.results:
        print("RESULTS_PATH", args.results)


if __name__ == "__main__":
    main()
