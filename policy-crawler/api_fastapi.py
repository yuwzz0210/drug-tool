# -*- coding: utf-8 -*-
"""FastAPI 薄包装（规格 7 章接口）。运行：pip install fastapi uvicorn
   uvicorn api_fastapi:app --reload --port 8000
"""
import os

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from config import DB_PATH
from drug_queries import drug_detail, drug_stats, list_devices, list_drugs
from drugstore import DrugStore
from queries import get_policy, list_policies, list_scenarios, scenario_policies, stats_latest
from store import SqliteStore

app = FastAPI(title="医药流通政策信息聚合平台 API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)
_store = SqliteStore(os.environ.get("CRAWLER_DB", DB_PATH))


@app.get("/api/policies")
def policies(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    keyword: str = "",
    authority: str = "",
    tag: str = "",
    status: str = "",
    date_from: str = "",
    date_to: str = "",
):
    return list_policies(_store, page=page, size=size, keyword=keyword,
                         authority=authority, tag=tag, status=status,
                         date_from=date_from, date_to=date_to)


@app.get("/api/policies/{policy_id}")
def policy_detail(policy_id: int):
    row = get_policy(_store, policy_id)
    if row is None:
        return {"error": "not found"}, 404
    return row


@app.get("/api/scenarios")
def scenarios():
    return {"items": list_scenarios()}


@app.get("/api/scenarios/{scenario_id}/policies")
def scenario_policies_view(scenario_id: str):
    return {"scenario_id": scenario_id, "items": scenario_policies(_store, scenario_id)}


@app.get("/api/stats/latest")
def stats():
    return stats_latest(_store)


@app.get("/api/drugs")
def drugs(
    search: str = "",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    return list_drugs(DrugStore.from_store(_store), keyword=search, page=page, size=size)


@app.get("/api/drugs/{product_id}")
def drug(product_id: int):
    row = drug_detail(DrugStore.from_store(_store), product_id)
    if row is None:
        return {"error": "not found"}, 404
    return row


@app.get("/api/devices")
def devices(
    search: str = "",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    return list_devices(DrugStore.from_store(_store), keyword=search, page=page, size=size)


@app.get("/api/stats/drugs")
def drugs_stats():
    return drug_stats(DrugStore.from_store(_store))
