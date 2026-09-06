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
from normalize import (  # noqa: E402
    norm_roman,
    strip_dosage_form,
    strip_salt,
    to_half_width,
)

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
               p.trade_name, r.approval_number, r.holder, m.generic_name
        FROM drug_product p
        LEFT JOIN drug_registration r ON r.product_id = p.product_id
        LEFT JOIN drug_molecule m ON m.molecule_id = p.molecule_id
        WHERE (p.package_insert_url IS NULL OR p.package_insert_url = '')
        ORDER BY p.product_id
    """).fetchall()
    db.close()
    by_pid = {}
    for r in rows:
        pid = r[0]
        item = by_pid.setdefault(pid, {
            "product_id": pid,
            "name": r[1] or r[6] or "",
            "manufacturer": r[2] or "",
            "trade_name": r[3] or "",
            "approval_number": r[4] or "",
            "holder": r[5] or "",
            "approval_numbers": [],
        })
        if r[4]:
            item["approval_numbers"].append(r[4])
    out = []
    for item in by_pid.values():
        item["approval_numbers"] = sorted(set(item["approval_numbers"]))
        out.append(item)
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


def search_name_variants(name):
    """Candidate search terms: original, normalized, without trailing roman."""
    hw = norm_roman(to_half_width(name or ""))
    core = re.sub(r"[（(][IⅠVⅣXⅩ1-9]{1,4}[）)]\s*$", "", hw or "")
    core = core.strip()
    out = []
    for v in (name, hw, core):
        if v and v not in out:
            out.append(v)
    return out


def drug_core(name):
    """Normalized molecule/drug core (salt & dosage form stripped)."""
    core = norm_roman(to_half_width(name or ""))
    core = re.sub(r"[（(][IⅠVⅣXⅩ1-9]{1,4}[）)]\s*$", "", core)
    return strip_salt(strip_dosage_form(core)).strip()


def candidate_matches(product, drgnamecn):
    """Candidate belongs to the same product core (no combo/other drug)."""
    a, b = drug_core(product.get("name") or ""), drug_core(drgnamecn or "")
    return bool(a) and a == b


def extract_approval_codes(text):
    """All 国药准字/注册证号 codes mentioned in a leaflet PDF text."""
    found = re.findall(r"国药准字\s*[HSZJ]\s*\d+", text or "")
    return {re.sub(r"\s+", "", m) for m in found}


def extract_trade_name(text):
    """商品名称 from the official insert header block, if present."""
    for line in (text or "").splitlines():
        line = line.strip()
        m = re.match(r"商品名称\s*[:：]\s*(.+)", line)
        if m:
            name = m.group(1).strip()
            if name and name not in ("-", "—", "——", "无"):
                return name
    m = re.search(r"商品名称\s*[:：]\s*([^\n\r]{1,60})", text or "")
    return m.group(1).strip() if m else ""


def match_leaflet_text_to_product(text, product):
    """Try to lock an ambiguous leaflet to our product.

    Uses the strongest official keys inside the insert itself: 【批准文号】
    (approval-code level, exact) then 【商品名称】(trade-name level).
    """
    codes = extract_approval_codes(text)
    mine = set(product.get("approval_numbers") or [])
    hit = codes & mine
    if hit:
        return "approval_code", sorted(hit)
    trade = extract_trade_name(text)
    mine_trade = (product.get("trade_name") or "").strip()
    if mine_trade and trade and (mine_trade in trade or trade in mine_trade):
        return "trade_name", trade
    return None


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


def write_live_stats(path, stats):
    """Atomically persist a small progress/QC snapshot for mid-run checks."""
    try:
        with open(path + ".tmp", "w", encoding="utf-8") as fh:
            json.dump(stats, fh, ensure_ascii=False, indent=1)
        os.replace(path + ".tmp", path)
    except Exception as exc:
        log.warning("live stats write failed: %s", exc)


def qc_imported_leaflet(db, rec, payload):
    """Verify one imported leaflet row: linkage + content completeness."""
    issues = []
    row = db.execute(
        """SELECT l.pdf_url, l.source_url, l.indications, l.cold_chain,
                  l.raw_text, p.product_id, p.package_insert_url
           FROM drug_leaflet l
           JOIN drug_product p ON p.product_id = l.product_id
           WHERE l.approval_number=? AND l.catalog_rid=?""",
        (payload["approval_number"], payload["catalog_rid"])).fetchone()
    if not row:
        return "fail", ["no db row"]
    if not (row[0] or "").startswith("https://"):
        issues.append("pdf_url")
    if not (row[1] or "").startswith("https://"):
        issues.append("source_url")
    if not (row[2] or "").strip():
        issues.append("indications_empty")
    if not (row[3] or "").strip():
        issues.append("cold_chain_empty")
    if len(row[4] or "") < 300:
        issues.append("raw_text_short")
    if row[6] != row[0]:
        issues.append("product_url_mismatch")
    if not row[5]:
        issues.append("no_product_id")
    return ("pass" if not issues else "review", issues)


def live_import_record(db_path, rec, parsed=None):
    """Import one already-downloaded record and QC it; returns (stats, qc)."""
    dest = rec.get("dest") or ""
    parsed = parsed or (parse_leaflet_sections(dest) if dest else None)
    if parsed is None or not parsed.get("ok"):
        return {"live_import": "skip_no_pdf"}, {"status": "fail",
                                               "issues": ["pdf_missing"]}
    if not (parsed.get("text") or "").strip():
        return {"live_import": "skip_needs_ocr"}, {"status": "fail",
                                                   "issues": ["needs_ocr"]}
    db = sqlite3.connect(db_path)
    try:
        from models import DRUG_SCHEMA
        db.executescript(DRUG_SCHEMA)
        from tools.import_cde_leaflets import import_one, leaflet_payload
        payload = leaflet_payload(rec, parsed)
        eff = import_one(db, payload)
        db.commit()
        status, issues = qc_imported_leaflet(db, rec, payload)
        db.close()
        return {"live_import": ",".join(eff["effects"]),
                "qc": status, "qc_issues": issues}
    except Exception as exc:
        try:
            db.close()
        except Exception:
            pass
        return {"live_import": "error", "qc": "fail",
                "qc_issues": [repr(exc)[:200]]}


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
        self._search_cache = {}
        self._detail_cache = {}
        self.last_cache_hit = False

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
        for variant in search_name_variants(name):
            # clear previous results first so an empty table = no match (fast)
            self.page.evaluate("""() => {
              const t = document.getElementById('listDrugInfoTbody');
              if (t) t.innerHTML = '';
              const p = document.getElementById('listDrugInfoPage');
              if (p) p.innerHTML = '';
            }""")
            self.page.fill("#drugname2", variant)
            self.page.evaluate("defaultObj.methods.getListDrugInfoList()")
            deadline = time.time() + 5
            while time.time() < deadline:
                rows = self.page.evaluate(parse_js)
                if rows:
                    return rows
                time.sleep(0.25)
        return []

    def search_by_name_cached(self, name):
        """Same-name products (roman/paren variants normalized) share one query."""
        key = norm_roman(to_half_width(name or "")) or (name or "")
        if key in self._search_cache:
            self.last_cache_hit = True
            return self._search_cache[key]
        self.last_cache_hit = False
        rows = self.search_by_name(name)
        self._search_cache[key] = rows
        return rows

    def open_detail(self, acceptcode):
        if acceptcode in self._detail_cache:
            return self._detail_cache[acceptcode]
        last_err = None
        for attempt in range(1, 4):
            try:
                self.detail_page.goto(DETAIL_URL.format(acceptcode),
                                      wait_until="domcontentloaded",
                                      timeout=60000)
                try:
                    self.detail_page.wait_for_function(
                        "document.body.innerText.includes('相关附件信息') || "
                        "document.body.innerText.includes('受理号')",
                        timeout=25000)
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
                self._detail_cache[acceptcode] = anchors
                return anchors
            except Exception as exc:
                last_err = exc
                msg = repr(exc)
                if attempt < 3 and ("ERR_NETWORK_CHANGED" in msg
                                    or "Timeout" in msg or "net::" in msg):
                    log.warning("detail %s attempt %d failed, retry: %s",
                                acceptcode, attempt, msg[:120])
                    time.sleep(8)
                    continue
                break
        raise last_err if last_err else RuntimeError("open_detail failed")

    def download_pdf(self, fileid, acceptid, dest):
        last_err = None
        for attempt in range(1, 4):
            try:
                resp = self._ctx.request.get(
                    DOWNLOAD_URL.format(fileid, acceptid), timeout=120000)
                if resp.status != 200:
                    raise RuntimeError("download HTTP %s" % resp.status)
                data = resp.body()
                with open(dest, "wb") as fh:
                    fh.write(data)
                return len(data)
            except Exception as exc:
                last_err = exc
                msg = repr(exc)
                if attempt < 3 and ("ERR_NETWORK_CHANGED" in msg
                                    or "Timeout" in msg or "net::" in msg
                                    or "HTTP" in msg):
                    log.warning("download %s attempt %d failed, retry: %s",
                                acceptid, attempt, msg[:120])
                    time.sleep(8)
                    continue
                break
        raise last_err if last_err else RuntimeError("download failed")

    def polite_pause(self):
        time.sleep(self.delay + random.uniform(0, 1.0))


def try_resolve_ambiguous(col, product, records, out_dir):
    """Multi-owner records: download each owner's newest insert and lock the
    match by the 【批准文号】/【商品名称】 printed inside the PDF itself."""
    matched = [r for r in records
               if candidate_matches(product, r.get("drgnamecn"))]
    if not matched:
        return None
    # no key in our DB to lock against -> downloads cannot resolve it
    if not (product.get("approval_numbers")
            or (product.get("trade_name") or "").strip()
            or (product.get("holder") or "").strip()
            or (product.get("manufacturer") or "").strip()):
        return None
    groups = group_by_owner(matched)
    our_tokens = company_token_set(
        product.get("holder") or product.get("manufacturer") or "")
    for g in groups:
        g.sort(key=lambda r: r.get("createddate") or "")
    # owner groups matching our company first; newest acceptance within each
    ranked = []
    for g in groups:
        rank = 0 if (our_tokens and token_sets_overlap(
            company_token_set(g[0].get("companys", "")), our_tokens)) else 1
        ranked.append((rank, g[-1].get("createddate") or "", g))
    ranked.sort(key=lambda t: t[0])
    groups0 = [t[2] for t in ranked if t[0] == 0]
    groups1 = [t[2] for t in ranked if t[0] == 1]
    groups0.sort(key=lambda g: g[-1].get("createddate") or "", reverse=True)
    groups1.sort(key=lambda g: g[-1].get("createddate") or "", reverse=True)
    reps = []
    seen = set()
    for g in (groups0 + groups1):
        for r in reversed(g):  # newest first inside each owner group
            key = (r.get("acceptid") or r.get("acceptidCODE"))
            if key and key not in seen:
                seen.add(key)
                reps.append(r)
            if len(reps) >= 12:
                break
        if len(reps) >= 12:
            break
    for a in reps:
        try:
            anchors = col.open_detail(a.get("acceptidCODE") or "")
            leaf = [x for x in anchors
                    if "说明书" in (x.get("filename") or "")]
            if not leaf:
                continue
            x = leaf[-1]
            dest = os.path.join(out_dir,
                                "_resolve_%s.pdf" % (a.get("acceptid") or "x"))
            col.download_pdf(x["fileid"], x["acceptid"], dest)
            parsed = parse_leaflet_sections(dest)
            hit = match_leaflet_text_to_product(
                parsed.get("text", ""), product)
            if hit:
                return a, x, dest, parsed, hit[0]
        except Exception as exc:
            log.warning("resolve attempt %s failed: %s",
                        a.get("acceptid"), exc)
    return None


def run_batch(targets, out_dir, delay=4.0, headless=True, results_path=None,
              live_import=False, db_path=None, live_state_path=None):
    col = CdePostmarketCollector(out_dir, headless=headless, delay=delay)
    results = []
    rf = open(results_path, "a", encoding="utf-8") if results_path else None
    stats = {"processed": 0, "ok": 0, "imported_ok": 0, "qc_pass": 0,
             "qc_review": 0, "ambiguous": 0, "not_found": 0,
             "no_leaflet": 0, "errors": 0, "skipped_import": 0}

    def commit_ok(rec, a, x, dest, parsed):
        size = os.path.getsize(dest) if os.path.exists(dest) else 0
        rec.update(
            status="ok", acceptid=a.get("acceptid"),
            acceptcode=a.get("acceptidCODE"),
            drgnamecn=a.get("drgnamecn"),
            createddate=a.get("createddate"),
            companys=a.get("companys"),
            file_id=x["fileid"], filename=x["filename"],
            catalog_rid=a.get("acceptidCODE") or "",
            pdf_url=DOWNLOAD_URL.format(x["fileid"], x["acceptid"]),
            source_url=DETAIL_URL.format(a.get("acceptidCODE") or ""),
            dest=dest, size=size,
            section_keys=list(parsed["sections"].keys()),
            parse_error=parsed.get("error"))
        stats["ok"] += 1
        if live_import and db_path:
            li = live_import_record(db_path, rec, parsed)
            rec.update({k: v for k, v in li.items()})
            if li.get("live_import", "").startswith("leaflet"):
                stats["imported_ok"] += 1
                if li.get("qc") == "pass":
                    stats["qc_pass"] += 1
                else:
                    stats["qc_review"] += 1
            elif li.get("live_import") == "error":
                stats["errors"] += 1
            else:
                stats["skipped_import"] += 1

    def handle_acceptance(rec, tgt, a):
        anchors = col.open_detail(a.get("acceptidCODE") or "")
        leaf = [x for x in anchors
                if "说明书" in (x.get("filename") or "")]
        if not leaf:
            rec.update(status="no_leaflet",
                       note="detail has no insert attachment")
            stats["no_leaflet"] += 1
            return
        x = leaf[-1]
        safe = re.sub(r"[\\/:*?\"<>|]", "_",
                      x["filename"] or a.get("acceptid"))
        dest = os.path.join(out_dir, safe)
        col.download_pdf(x["fileid"], x["acceptid"], dest)
        parsed = parse_leaflet_sections(dest)
        commit_ok(rec, a, x, dest, parsed)

    try:
        col.open_list()
        total = len(targets)
        for i, tgt in enumerate(targets, 1):
            rec = dict(tgt)
            rec["channel"] = "postmarket"
            rec["status"] = "pending"
            try:
                records = col.search_by_name_cached(tgt.get("name") or "")
                if not records:
                    rec.update(status="not_found",
                               note="postmarket no record for name")
                    stats["not_found"] += 1
                else:
                    picks, how = decide_acceptance(tgt, records)
                    rec["accepts"] = records
                    rec["match"] = how
                    if picks:
                        picks.sort(key=lambda r: r.get("createddate") or "")
                        handle_acceptance(rec, tgt, picks[-1])
                    else:
                        # auto-resolve by approval code / trade name in PDF
                        resolved = try_resolve_ambiguous(
                            col, tgt, records, out_dir)
                        if resolved:
                            a, x, dest, parsed, how2 = resolved
                            rec["match"] = "auto:" + how2
                            commit_ok(rec, a, x, dest, parsed)
                        else:
                            rec.update(
                                status="ambiguous",
                                note="no auto-match (manual review needed)")
                            stats["ambiguous"] += 1
            except Exception as exc:
                log.exception("product %s failed", tgt.get("product_id"))
                rec.update(status="error", error=repr(exc))
                stats["errors"] += 1
            results.append(rec)
            if rf:
                rf.write(json.dumps(rec, ensure_ascii=False) + "\n")
                rf.flush()
            log.info("[%d/%d] product=%s name=%s status=%s", i, total,
                     tgt.get("product_id"), tgt.get("name"), rec.get("status"))
            stats["processed"] += 1
            if live_state_path and (i % 10 == 0 or rec.get("status") == "ok"):
                write_live_stats(live_state_path, stats)
            did_network = (not col.last_cache_hit
                           or rec.get("status") != "not_found")
            if i < total and did_network:
                col.polite_pause()
    finally:
        if live_state_path:
            write_live_stats(live_state_path, stats)
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
    ap.add_argument("--live-import", action="store_true",
                    help="import + QC each downloaded leaflet immediately")
    ap.add_argument("--live-state", default=None,
                    help="JSON file for realtime progress/QC stats")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    targets = load_targets(args.db, limit=args.limit)
    done = set()
    if args.results and os.path.exists(args.results):
        with open(args.results, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                # ambiguous rows are re-processed now that auto-resolution by
                # approval code / trade name is part of the crawl
                if rec.get("status") in ("ok", "not_found") and \
                        rec.get("product_id"):
                    done.add(rec["product_id"])
    targets = [t for t in targets if t["product_id"] not in done]
    print("TARGETS_REMAINING", len(targets))
    results = run_batch(targets, args.out, delay=args.delay,
                        results_path=args.results,
                        live_import=args.live_import,
                        db_path=args.db,
                        live_state_path=args.live_state
                        or (args.results + ".live.json" if args.results
                            else None))
    from collections import Counter
    st = Counter(r.get("status") for r in results)
    print("SUMMARY", json.dumps(st, ensure_ascii=False))


if __name__ == "__main__":
    main()
