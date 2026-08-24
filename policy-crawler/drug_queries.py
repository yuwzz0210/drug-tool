# -*- coding: utf-8 -*-
"""药品/器械域 API 查询层：列表、详情、统计（与存储解耦，便于单测）。"""


def list_drugs(store, keyword="", page=1, size=20):
    total, rows = store.fetch_products(keyword=keyword, page=page, size=size)
    items = []
    for r in rows:
        items.append({
            "product_id": r["product_id"],
            "generic_name": r["generic_name"],
            "trade_name": r["trade_name"],
            "dosage_form": r["dosage_form"],
            "specification": r["specification"],
            "manufacturer": r["manufacturer_norm"],
            "drug_type": r["drug_type"],
            "is_otc": bool(r["is_otc"]),
            "is_verified": bool(r["is_verified"]),
            "updated_at": r["updated_at"],
        })
    return {"total": total, "page": page, "size": size, "items": items}


def drug_detail(store, product_id):
    return store.fetch_product_detail(product_id)


def list_devices(store, keyword="", page=1, size=20):
    total, rows = store.fetch_devices(keyword=keyword, page=page, size=size)
    items = []
    for r in rows:
        items.append({
            "device_id": r["device_id"],
            "registration_number": r["registration_number"],
            "product_name": r["product_name"],
            "management_category": r["management_category"],
            "manufacturer": r["manufacturer"],
            "approval_date": r["approval_date"],
            "is_verified": bool(r["is_verified"]),
        })
    return {"total": total, "page": page, "size": size, "items": items}


def drug_stats(store):
    return store.stats()
