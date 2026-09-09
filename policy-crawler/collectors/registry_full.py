# -*- coding: utf-8 -*-
"""全量药品注册库抓取/导入程序（合规、防乱套、可续跑）。

目标：把库内品种扩到“目前国内已上市药品”全集。数据一律来自官方公开渠道
（NMPA 数据查询 / 国家医保目录 / 国家及联盟集采公告），或用户提供的官方文件；
不做任何推断填充——缺批准文号或药品名称的行整行拒绝；同一批准文号若与库内
已有品种身份不一致，仅记冲突日志，绝不覆盖（防“乱套”）。

模式：
    nmpa        浏览器分页抓取 NMPA 数据查询列表（国产/进口），落库+审计 JSONL
    insurance   调用现有医保目录导入器（自动发现最新官方目录）
    import-file 导入官方集采/目录文件（csv/xlsx/json），可选写入中选价

用法：
    python -m collectors.registry_full --db policy_crawler.db --mode nmpa \
        --dataset domestic --max-pages 100 --audit logs/registry_nmpa.jsonl
    python -m collectors.registry_full --db policy_crawler.db --mode insurance
    python -m collectors.registry_full --db policy_crawler.db --mode import-file \
        --file 集采结果.xlsx --source-name 国家集采第12批 --audit logs/registry_file.jsonl

合规：真实浏览器自然过 JS 挑战；逐页请求间隔 >=4s+抖动；仅公开页面；日志留痕。
易联招采等会员站：需账号登录，见 --cookie-file 说明（路线B，不匿名抓取）。
"""
import argparse
import csv
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

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

log = logging.getLogger("policy-crawler.collectors.registry_full")

NMPA_HOME = "https://www.nmpa.gov.cn/datasearch/home-index.html"
NMPA_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
APPROVAL_RE = re.compile(r"^国药准字\s*[HSZJ]\s*\d+$")

NAME_KEYS = ["通用名", "通用名称", "药品名称", "产品名称", "名称", "药品通用名"]
FORM_KEYS = ["剂型", "产品剂型", "药品剂型"]
SPEC_KEYS = ["规格", "药品规格", "产品规格"]
MFG_KEYS = ["生产单位", "生产企业", "生产厂家", "上市许可持有人", "持证商", "企业名称"]
APPROVAL_KEYS = ["批准文号", "注册证号", "药品批准文号", "批准文号/注册证号"]
DATE_KEYS = ["批准日期", "发证日期", "批准时间"]
PRICE_KEYS = ["中选价格", "挂网价格", "价格", "支付标准"]
UNIT_KEYS = ["计价单位", "单位"]


def identity_card(rec):
    """每个品种/规格的“身份牌”。

    入库前必须先取得、且只能由官方数据给出：
      - 第1层：批准文号/注册证号（每规格唯一硬标识）
      - 第2层：规范通用名 + 剂型 + 规格 + 厂家（业务键，防止同名错配）
    两者任一缺失即视为“无身份牌”，整行拒绝，禁止用推断值顶替。
    """
    return {
        "approval_number": (rec.get("approval_number") or "").strip(),
        "generic_name": (rec.get("generic_name") or "").strip(),
        "dosage_form": (rec.get("dosage_form") or "").strip(),
        "specification": (rec.get("specification") or "").strip(),
        "manufacturer": (rec.get("manufacturer") or "").strip(),
    }


def _first(row, keys):
    for k in keys:
        for ck in (k, k.lower()):
            if ck in row and row[ck] not in (None, ""):
                return str(row[ck]).strip()
    return ""


def validate_registry_record(rec):
    """严格校验：缺批准文号或药品名称的行整行拒绝（不许臆造/半截入库）。"""
    card = identity_card(rec)
    if not card["approval_number"]:
        return False, "missing approval_number"
    if not APPROVAL_RE.match(card["approval_number"]):
        return False, "approval_number malformed: %s" % card["approval_number"]
    missing = [k for k, v in card.items()
               if k != "approval_number" and not v]
    if missing:
        return False, "identity card incomplete: %s" % ",".join(missing)
    return True, ""


def normalize_payload_row(row):
    """把一行（中文表头或 f0.. 编号键）映射成标准注册记录。"""
    rec = {
        "generic_name": _first(row, NAME_KEYS),
        "dosage_form": _first(row, FORM_KEYS),
        "specification": _first(row, SPEC_KEYS),
        "manufacturer": _first(row, MFG_KEYS),
        "approval_number": _first(row, APPROVAL_KEYS),
        "approval_date": _first(row, DATE_KEYS),
    }
    # f0.. numbered keys from the official datasearch payload
    if not rec["approval_number"] and any(k.startswith("f") for k in row):
        ordered = sorted((int(k[1:]), v) for k, v in row.items()
                         if re.fullmatch(r"f\d+", k))
        # 列顺序由首屏表头给出；此处保守：文号列名映射未开启时拒绝
        return rec
    return rec


def insert_registry_record(db, rec, source_name, audit_rows, dry_run=False):
    """写 product/registration；同文号身份不一致只记冲突不覆盖。"""
    ok, why = validate_registry_record(rec)
    if not ok:
        audit_rows.append({"action": "reject", "reason": why,
                           "row": rec})
        return "reject:" + why[:40]
    appr = rec["approval_number"]
    existing = db.execute(
        "SELECT product_id FROM drug_registration WHERE approval_number=?",
        (appr,)).fetchone()
    if existing:
        prod = db.execute(
            "SELECT generic_name, dosage_form, specification, manufacturer_norm "
            "FROM drug_product WHERE product_id=?", (existing[0],)).fetchone()
        same = (prod[0] == rec["generic_name"] and prod[1] == rec["dosage_form"]
                and prod[2] == rec["specification"]
                and prod[3] == rec["manufacturer"])
        if not same:
            audit_rows.append({"action": "conflict_skip",
                               "approval_number": appr,
                               "in_db": list(prod) if prod else None,
                               "new": [rec["generic_name"], rec["dosage_form"],
                                       rec["specification"], rec["manufacturer"]]})
            return "conflict_skip"
    if dry_run:
        audit_rows.append({"action": "dry_run",
                           "approval_number": appr,
                           "generic_name": rec["generic_name"],
                           "dosage_form": rec.get("dosage_form", ""),
                           "specification": rec.get("specification", ""),
                           "manufacturer": rec.get("manufacturer", "")})
        return "dry_run"
    pid = None
    key = (rec["generic_name"], rec["dosage_form"], rec["specification"],
           rec["manufacturer"])
    row = db.execute(
        """SELECT product_id FROM drug_product
           WHERE generic_name=? AND dosage_form=? AND specification=?
             AND manufacturer_norm=?""", key).fetchone()
    if row:
        pid = row[0]
    else:
        cur = db.execute(
            """INSERT INTO drug_product
               (generic_name, dosage_form, specification, manufacturer_norm,
                source_url, is_verified, extra_data)
               VALUES (?,?,?,?,?,0,'{}')""",
            (rec["generic_name"], rec["dosage_form"], rec["specification"],
             rec["manufacturer"], rec.get("source_url", "")))
        pid = cur.lastrowid
    db.execute(
        """INSERT INTO drug_registration
           (product_id, approval_number, registration_date, status, holder,
            source_url)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(approval_number) DO UPDATE SET
             product_id=excluded.product_id,
             registration_date=excluded.registration_date,
             holder=excluded.holder, source_url=excluded.source_url""",
        (pid, appr, rec.get("approval_date", ""), "有效",
         rec.get("manufacturer", ""), rec.get("source_url", "")))
    db.commit()
    audit_rows.append({"action": "insert", "approval_number": appr,
                       "generic_name": rec["generic_name"]})
    return "insert"


def parse_header_mapping(page):
    """NMPA 结果表头 -> 标准字段（用于 f0.. 编号键行）。"""
    try:
        headers = page.eval_on_selector_all(
            ".el-table__header th .cell, table thead th",
            "els => els.map(e => (e.innerText||'').trim())")
    except Exception:
        headers = []
    mapping = {}
    for idx, h in enumerate(headers):
        h2 = h.replace(" ", "")
        if any(k in h2 for k in ("批准文号", "注册证号")):
            mapping[idx] = "approval"
        elif any(k in h2 for k in ("通用名", "药品名称", "产品名称")):
            mapping[idx] = "generic"
        elif any(k in h2 for k in ("剂型",)):
            mapping[idx] = "form"
        elif any(k in h2 for k in ("规格",)):
            mapping[idx] = "spec"
        elif any(k in h2 for k in ("生产", "持有人", "企业")):
            mapping[idx] = "manufacturer"
        elif any(k in h2 for k in ("批准日期", "发证日期")):
            mapping[idx] = "date"
    return mapping


def map_numbered_row(row, mapping):
    out = {}
    for k, v in row.items():
        m = re.fullmatch(r"f(\d+)", str(k))
        if not m:
            continue
        col = int(m.group(1))
        role = mapping.get(col)
        if role and not out.get(role):
            out[role] = str(v or "").strip()
    return {
        "approval_number": out.get("approval", ""),
        "generic_name": out.get("generic", ""),
        "dosage_form": out.get("form", ""),
        "specification": out.get("spec", ""),
        "manufacturer": out.get("manufacturer", ""),
        "approval_date": out.get("date", ""),
    }


def crawl_nmpa(db, dataset, max_pages, delay, audit_path, dry_run=False,
               cookie_file=None):
    """Playwright 驱动 NMPA 数据查询，逐页抓列表并入库。"""
    from playwright.sync_api import sync_playwright
    audit_rows = []
    rf = open(audit_path, "a", encoding="utf-8") if audit_path else None
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"])
            ctx = browser.new_context(user_agent=NMPA_UA, locale="zh-CN",
                                      viewport={"width": 1440, "height": 960})
            if cookie_file and os.path.exists(cookie_file):
                ctx.add_cookies(json.load(open(cookie_file, encoding="utf-8")))
            page = ctx.new_page()
            page.goto(NMPA_HOME, wait_until="domcontentloaded", timeout=60000)
            time.sleep(12)  # JS 挑战
            # 首页输入框与“查询”按钮；空查询取当前库全集
            try:
                page.evaluate("""() => {
                  const inp=[...document.querySelectorAll('input')]
                    .find(e=>e.offsetParent!==null);
                  const btn=[...document.querySelectorAll('button')]
                    .find(e=>/查\\s*询/.test(e.innerText||''));
                  if(inp && btn) { inp.focus(); btn.click(); }
                }""")
            except Exception as exc:
                raise RuntimeError("search trigger failed: %s" % exc)
            time.sleep(8)
            result = None
            for pg in ctx.pages:
                if "search-result" in pg.url or len(ctx.pages) > 1:
                    result = pg
                    break
            if result is None:
                result = ctx.pages[-1]
            result.wait_for_timeout(5000)
            mapping = parse_header_mapping(result)
            log.info("header mapping: %s", mapping)

            def current_rows():
                try:
                    return result.evaluate(
                        """() => {
                          const trs=document.querySelectorAll('.el-table__body tbody tr');
                          return [...trs].map(tr=>{
                            const cells=[...tr.querySelectorAll('td')];
                            const o={};
                            cells.forEach((td,i)=>{ o['f'+i]=(td.innerText||'').trim(); });
                            return o;
                          }).filter(r=>Object.values(r).join('').trim());
                        }""")
                except Exception:
                    return []

            page_no = 0
            while page_no < max_pages:
                for row in current_rows():
                    rec = map_numbered_row(row, mapping)
                    if rec.get("approval_number"):
                        insert_registry_record(db, rec, dataset, audit_rows,
                                               dry_run=dry_run)
                page_no += 1
                log.info("page %d done, audit %d", page_no, len(audit_rows))
                if rf:
                    for a in audit_rows:
                        rf.write(json.dumps(a, ensure_ascii=False) + "\n")
                    audit_rows.clear()
                    rf.flush()
                if page_no >= max_pages:
                    break
                clicked = False
                for sel in ("button:has-text('下一页')",
                            ".el-pagination .btn-next",
                            ".el-pagination__next"):
                    try:
                        if result.locator(sel).first.is_visible():
                            result.locator(sel).first.click()
                            clicked = True
                            break
                    except Exception:
                        continue
                if not clicked:
                    log.info("no next page button; stop")
                    break
                time.sleep(delay + random.uniform(0, 1))
                result.wait_for_timeout(2500)
            browser.close()
    finally:
        if rf:
            rf.close()
    return len(audit_rows)


def member_channel_url(dataset):
    """Resolve eliancloud member URL for a dataset from procurement_channels.json."""
    here = os.path.dirname(os.path.abspath(__file__))
    cfg = json.load(open(os.path.join(here, "procurement_channels.json"),
                         encoding="utf-8"))
    base = cfg["members_base"].rstrip("/")
    key = "药品基础库_境内" if dataset == "domestic" else "药品基础库_境外"
    path = cfg["channels"][key]["member"]
    return base + path


def _read_table(page):
    """Generic table read: return (headers, [row_dicts]) from the active page."""
    script = """() => {
      const tables = [...document.querySelectorAll('table')];
      let target = null;
      for (const t of tables) {
        const ths = [...t.querySelectorAll('thead th')]
            .map(e => (e.innerText||'').trim());
        const joined = ths.join('|');
        if (joined.includes('批准文号') && joined.includes('产品名称')) {
          target = t;
          break;
        }
      }
      if (!target) return {heads: [], rows: []};
      let heads = [...target.querySelectorAll('thead th')]
          .map(e => (e.innerText||'').trim());
      const apprIdx = heads.findIndex(h => h.includes('批准文号'));
      const allTrs = [...document.querySelectorAll('table tbody tr')];
      const rows = [];
      allTrs.forEach(tr => {
        const tds = [...tr.querySelectorAll('td')].map(td =>
            (td.innerText||'').trim());
        if (!tds.join('')) return;
        if (apprIdx >= 0 && !/^国药准字/.test(tds[apprIdx] || '')) return;
        const o = {};
        tds.forEach((v,i)=>{ if (heads[i]) o[heads[i]] = v; });
        rows.push(o);
      });
      return {heads, rows};
    }"""
    return page.evaluate(script)


def crawl_member_table(db, start_url, cookie_file, max_pages, delay,
                       audit_path, dry_run=False):
    """Crawl an eliancloud member data page (authorized session only)."""
    from playwright.sync_api import sync_playwright
    audit_rows = []
    rf = open(audit_path, "a", encoding="utf-8") if audit_path else None
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"])
            ctx = browser.new_context(user_agent=NMPA_UA, locale="zh-CN",
                                      viewport={"width": 1600, "height": 1000})
            if not cookie_file or not os.path.exists(cookie_file):
                raise SystemExit("elian mode requires --cookie-file "
                                 "(run tools/elian_login_save_cookies.py first)")
            ctx.add_cookies(json.load(open(cookie_file, encoding="utf-8")))
            page = ctx.new_page()
            page.goto(start_url, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(6000)
            # the data table lives in an inner iframe whose url matches the
            # DataQuery page
            data_frame = None
            for f in page.frames:
                url_path = f.url.split("?")[0]
                if ("/Member/DataQuery/DomesticList" in url_path
                        or "/Member/DataQuery/ImportList" in url_path):
                    data_frame = f
                    break
            if data_frame is None:
                data_frame = page
            log.info("data frame: %s", data_frame.url)
            page_no = 0
            while page_no < max_pages:
                data = _read_table(data_frame)
                log.info("page %d headers=%s rows=%d", page_no + 1,
                         data["heads"][:12], len(data["rows"]))
                for row in data["rows"]:
                    rec = normalize_payload_row(row)
                    if page_no == 0 and not rec.get("approval_number"):
                        log.info("sample row keys=%s values=%s",
                                 list(row.keys())[:6],
                                 list(row.values())[:6])
                    if not rec.get("approval_number") and not rec.get(
                            "generic_name"):
                        audit_rows.append({
                            "action": "reject:unmapped_fields",
                            "row_keys": list(row.keys())[:14],
                            "row_values": list(row.values())[:5]})
                        continue
                    insert_registry_record(db, rec, "elian:" + start_url,
                                           audit_rows, dry_run=dry_run)
                page_no += 1
                if rf:
                    for a in audit_rows:
                        rf.write(json.dumps(a, ensure_ascii=False) + "\n")
                    audit_rows.clear()
                    rf.flush()
                if page_no >= max_pages:
                    break
                clicked = False
                selectors = [
                    "button:has-text('下一页')",
                    "li[title*='下一页']",
                    ".ant-pagination-next",
                    ".el-pagination__next",
                    ".pagination .next",
                    "a.next",
                ]
                for sel in selectors:
                    try:
                        loc = data_frame.locator(sel).first
                        if loc.is_visible():
                            loc.click(timeout=3000)
                            clicked = True
                            break
                    except Exception:
                        continue
                if not clicked:
                    for txt in ("下一页", "下页", "next", ">", "»"):
                        try:
                            loc = data_frame.get_by_text(
                                txt, exact=False).first
                            if loc.is_visible() and loc.count():
                                loc.click(timeout=3000)
                                clicked = True
                                break
                        except Exception:
                            continue
                if not clicked:
                    # numeric page link "2"
                    try:
                        for num in ("2", "下一页"):
                            loc = data_frame.locator(
                                "text=%s" % num).first
                            if loc.is_visible():
                                loc.click(timeout=2000)
                                clicked = True
                                break
                    except Exception:
                        clicked = False
                if not clicked:
                    log.info("no next page; stop")
                    break
                page.wait_for_timeout(
                    int((delay + random.uniform(0, 1)) * 1000))
                data_frame.wait_for_timeout(2000)
            browser.close()
    finally:
        if rf:
            rf.close()
    return len(audit_rows)


def import_file(db, path, source_name, audit_path, dry_run=False):
    """导入官方目录/集采文件（csv/xlsx/json）。行校验失败整行拒绝。"""
    audit_rows = []
    rows = []
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        data = json.load(open(path, encoding="utf-8"))
        rows = data if isinstance(data, list) else data.get("rows", [])
    elif ext == ".csv":
        with open(path, encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
    elif ext in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        headers = [str(c.value or "").strip() for c in next(ws.iter_rows())]
        for row in ws.iter_rows(min_row=2):
            d = {h: (c.value if c.value is not None else "")
                 for h, c in zip(headers, row)}
            rows.append(d)
    else:
        raise ValueError("unsupported file type: %s" % ext)

    n_price = 0
    for r in rows:
        rec = normalize_payload_row(r)
        rec["source_url"] = source_name
        res = insert_registry_record(db, rec, source_name, audit_rows,
                                     dry_run=dry_run)
        price_txt = _first(r, PRICE_KEYS)
        if res == "insert" and price_txt:
            try:
                price = float(re.sub(r"[^\d.]", "", price_txt))
            except Exception:
                price = None
            if price:
                row = db.execute(
                    "SELECT product_id FROM drug_product "
                    "WHERE generic_name=? AND dosage_form=? AND specification=?"
                    " AND manufacturer_norm=?",
                    (rec["generic_name"], rec["dosage_form"],
                     rec["specification"], rec["manufacturer"])).fetchone()
                if row and not dry_run:
                    db.execute(
                        """INSERT INTO price_history
                           (product_id, price_type, price, unit, effective_date,
                            source_url)
                           VALUES (?,?,?,?,?,?)""",
                        (row[0], "集采中选", price,
                         _first(r, UNIT_KEYS), rec.get("approval_date", ""),
                         source_name))
                    db.commit()
                    n_price += 1
    stats = {"rows": len(rows), "prices": n_price,
             "audit": len(audit_rows)}
    if audit_path:
        with open(audit_path, "w", encoding="utf-8") as fh:
            for a in audit_rows:
                fh.write(json.dumps(a, ensure_ascii=False) + "\n")
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="policy_crawler.db")
    ap.add_argument("--mode", required=True,
                    choices=["nmpa", "insurance", "import-file", "elian"])
    ap.add_argument("--dataset", default="domestic",
                    choices=["domestic", "imported"])
    ap.add_argument("--max-pages", type=int, default=100)
    ap.add_argument("--delay", type=float, default=6.0)
    ap.add_argument("--audit", default=None)
    ap.add_argument("--file", default=None)
    ap.add_argument("--source-name", default="")
    ap.add_argument("--cookie-file", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    db = sqlite3.connect(args.db)
    if args.mode == "insurance":
        # 复用既有官方医保目录导入器（自动发现最新目录）
        from importers.insurance_catalog import main as ins_main
        sys.argv = ["insurance_catalog", "--auto", "--db", args.db]
        db.close()
        return ins_main()
    if args.mode == "nmpa":
        n = crawl_nmpa(db, args.dataset, args.max_pages, args.delay,
                       args.audit, dry_run=args.dry_run,
                       cookie_file=args.cookie_file)
        print("NMPA_PAGES_DONE", args.max_pages, "| remaining_audit", n)
    elif args.mode == "elian":
        if not args.cookie_file:
            raise SystemExit("--cookie-file required for elian mode")
        url = member_channel_url(args.dataset)
        print("ELIAN_URL", url)
        n = crawl_member_table(db, url, args.cookie_file, args.max_pages,
                               args.delay, args.audit,
                               dry_run=args.dry_run)
        print("ELIAN_PAGES_DONE", args.max_pages, "| remaining_audit", n)
    else:
        if not args.file:
            raise SystemExit("--file required for import-file mode")
        stats = import_file(db, args.file, args.source_name or args.file,
                            args.audit, dry_run=args.dry_run)
        print("IMPORT_STATS", json.dumps(stats, ensure_ascii=False))
    db.close()


if __name__ == "__main__":
    main()
