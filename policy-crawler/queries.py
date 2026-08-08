# -*- coding: utf-8 -*-
"""API 查询层：列表筛选、详情、业务场景专题、统计、效力状态规则（与存储解耦，可单测）。"""
import datetime

from config import load_all_sources


SCENARIOS = [
    {"id": "sc_license", "name": "药品经营许可审批", "keywords": ["经营许可", "许可证", "药品经营"]},
    {"id": "sc_gsp", "name": "GSP认证与飞行检查", "keywords": ["GSP", "质量管理规范", "飞行检查"]},
    {"id": "sc_insurance_point", "name": "医保定点机构申报", "keywords": ["医保定点", "定点医疗机构", "定点零售药店", "结算协议"]},
    {"id": "sc_vbp", "name": "国家药品集采参与", "keywords": ["集采", "带量采购", "中选", "集中采购"]},
    {"id": "sc_online_sales", "name": "药品网络销售合规", "keywords": ["网络销售", "处方药网络", "网售处方药", "药品网络"]},
    {"id": "sc_trace", "name": "药品追溯体系建设", "keywords": ["追溯", "追溯码", "药品信息化追溯"]},
]


def list_scenarios():
    return [{"id": s["id"], "name": s["name"]} for s in SCENARIOS]


def scenario_policies(store, scenario_id):
    sc = next((s for s in SCENARIOS if s["id"] == scenario_id), None)
    if not sc:
        return []
    rows = store.query_policies({})
    return [r for r in rows if _scenario_hit(r, sc["keywords"])]


def _scenario_hit(row, keywords):
    blob = " ".join(str(row.get(k) or "") for k in ("title", "content", "tags", "doc_number"))
    blob = blob.lower()
    return any(kw.lower() in blob for kw in keywords)


def list_policies(store, page=1, size=20, keyword="", authority="", tag="",
                  status="", date_from="", date_to=""):
    rows = store.query_policies({
        "keyword": keyword, "authority": authority, "tag": tag,
        "status": status, "date_from": date_from, "date_to": date_to,
    })
    total = len(rows)
    page = max(1, page)
    size = max(1, min(100, size))
    page_rows = rows[(page - 1) * size:page * size]
    return {"total": total, "page": page, "size": size,
            "items": [_brief(r) for r in page_rows]}


def _brief(row):
    keys = ("id", "title", "doc_number", "issuing_authority", "publish_date",
            "validity_status", "source_url", "tags")
    return {k: row.get(k) for k in keys}


def get_policy(store, policy_id):
    return store.get_by_id(policy_id)


def stats_latest(store, days=7):
    return {"today": store.added_since(0), "week": store.added_since(days)}


def health_summary(store):
    """监控用健康摘要：数据库可用、政策数量、启用数据源。"""
    rows = store.query_policies({})
    enabled = sorted(k for k, s in load_all_sources().items() if s.get("enabled"))
    return {
        "ok": True,
        "policies": len(rows),
        "sources_enabled": enabled,
        "time": datetime.datetime.now().isoformat(timespec="seconds"),
    }


def update_validity(policy):
    """效力状态规则：标题含废止/失效 → 废止；发布日期晚于今天 → 未生效；否则有效。"""
    title = policy.get("title") or ""
    if any(w in title for w in ("废止", "失效")):
        return "废止"
    pub = policy.get("publish_date") or ""
    if len(pub) >= 10:
        try:
            d = datetime.datetime.strptime(pub[:10], "%Y-%m-%d").date()
            if d > datetime.date.today():
                return "未生效"
        except ValueError:
            pass
    return "有效"
