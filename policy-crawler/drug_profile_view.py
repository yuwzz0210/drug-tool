# -*- coding: utf-8 -*-
"""drug_profile 视图 v2：把逐行相关子查询改写为一次性的预聚合 CTE。

v1 的每条记录要执行约 25 个相关子查询（适应症/医保/价格/集采/政策/国谈/双通道…），
品种库从 1,600 行扩到 26,000 行后导出耗时超过 10 分钟。
v2 对每张子表只做一次聚合/取最新（窗口函数 ROW_NUMBER），再 LEFT JOIN 回主表，
列名与口径与 v1 完全一致，前端无需改动。

口径对齐（与 v1 相同）：
- 说明书/医保/价格/集采均取「最新一条」：医保先按 is_current=1 过滤；
- 适应症、集采事件、政策关联为计数或聚合；
- 国谈、双通道按 molecule_id 关联（分子层级事实）。
"""

DRUG_PROFILE_VIEW_SQL_V2 = """
CREATE VIEW IF NOT EXISTS drug_profile AS
WITH
latest_leaflet AS (
    SELECT product_id, leaflet_date, usage_dosage, storage FROM (
        SELECT product_id, leaflet_date, usage_dosage, storage,
               ROW_NUMBER() OVER (PARTITION BY product_id
                                  ORDER BY updated_at DESC, leaflet_id DESC)
               AS rn
          FROM drug_leaflet)
     WHERE rn = 1
),
indication_agg AS (
    SELECT product_id,
           COUNT(*) AS indication_count,
           GROUP_CONCAT(indication_text, '；') AS indications_text
      FROM drug_indication
     GROUP BY product_id
),
manufacturer_agg AS (
    SELECT molecule_id, COUNT(DISTINCT manufacturer_norm) AS followers_count
      FROM drug_product
     WHERE molecule_id IS NOT NULL
     GROUP BY molecule_id
),
latest_insurance AS (
    SELECT product_id, category, insurance_code, region, reimbursement_ratio,
           payment_scope, supplement_status, catalog_id FROM (
        SELECT product_id, category, insurance_code, region,
               reimbursement_ratio, payment_scope, supplement_status,
               catalog_id,
               ROW_NUMBER() OVER (PARTITION BY product_id
                                  ORDER BY catalog_id DESC, entry_id DESC) AS rn
          FROM drug_insurance_entry
         WHERE is_current = 1)
     WHERE rn = 1
),
insurance_since AS (
    SELECT ie.product_id,
           MIN(ic.publish_date) AS insurance_since_date
      FROM drug_insurance_entry ie
      JOIN insurance_catalog ic ON ic.catalog_id = ie.catalog_id
     WHERE ic.publish_date IS NOT NULL AND ic.publish_date <> ''
     GROUP BY ie.product_id
),
latest_listed_price AS (
    SELECT product_id, price, region, effective_date FROM (
        SELECT product_id, price, region, effective_date,
               ROW_NUMBER() OVER (PARTITION BY product_id
                                  ORDER BY effective_date DESC,
                                           price_id DESC) AS rn
          FROM price_history
         WHERE price_type = '挂网')
     WHERE rn = 1
),
latest_vbp AS (
    SELECT product_id, price, batch FROM (
        SELECT product_id, price, batch,
               ROW_NUMBER() OVER (PARTITION BY product_id
                                  ORDER BY updated_at DESC,
                                           result_id DESC) AS rn
          FROM procurement_result)
     WHERE rn = 1
),
vbp_agg AS (
    SELECT product_id,
           COUNT(*) AS vbp_event_count,
           GROUP_CONCAT(DISTINCT batch) AS vbp_batches
      FROM procurement_result
     GROUP BY product_id
),
policy_agg AS (
    SELECT product_id, COUNT(*) AS policy_count
      FROM policy_drug_relation
     GROUP BY product_id
),
latest_negotiation AS (
    SELECT molecule_id, category, pay_standard, agreement_period, batch_year,
           event_count FROM (
        SELECT molecule_id, category, pay_standard, agreement_period,
               batch_year,
               COUNT(*) OVER (PARTITION BY molecule_id) AS event_count,
               ROW_NUMBER() OVER (PARTITION BY molecule_id
                                  ORDER BY negotiation_id DESC) AS rn
          FROM negotiation_result
         WHERE molecule_id IS NOT NULL)
     WHERE rn = 1
),
dual_agg AS (
    SELECT molecule_id,
           GROUP_CONCAT(DISTINCT CASE WHEN status = '纳入' THEN region END)
               AS dual_channel_regions,
           COUNT(DISTINCT region) AS dual_channel_region_count
      FROM dual_channel
     WHERE molecule_id IS NOT NULL
     GROUP BY molecule_id
)
SELECT
    p.product_id,
    r.approval_number,
    p.generic_name,
    p.trade_name,
    p.manufacturer_norm AS manufacturer,
    r.holder,
    p.dosage_form,
    p.specification,
    r.registration_date AS approval_date,
    CASE WHEN COALESCE(r.approval_number, '') LIKE '国药准字J%'
         THEN '进口' ELSE '国产' END AS origin_type,
    p.molecule_id,
    m.generic_name AS molecule_name,
    m.atc_code,
    m.mechanism_summary,
    m.route,
    m.cold_chain,
    m.generation,
    m.iteration_chain,
    m.guideline_level,
    m.extra_indications,
    m.therapeutic_area,
    m.disease,
    m.sub_disease,
    m.classification_confidence,
    p.package_insert_url AS leaflet_url,
    p.source_url,
    lf.leaflet_date,
    lf.usage_dosage,
    lf.storage,
    ia.indications_text,
    COALESCE(ia.indication_count, 0) AS indication_count,
    COALESCE(ma.followers_count, 0) AS followers_count,
    CASE WHEN ma.followers_count = 1 THEN 1 ELSE 0 END AS is_exclusive,
    ins.category AS insurance_category,
    ins.insurance_code,
    ins.region AS insurance_region,
    ins.reimbursement_ratio,
    ins.payment_scope,
    ins.supplement_status,
    ic.version_name AS insurance_catalog_version,
    isd.insurance_since_date,
    lp.price AS latest_listed_price,
    lp.region AS listed_price_region,
    lp.effective_date AS listed_price_date,
    lv.price AS latest_vbp_price,
    lv.batch AS latest_vbp_batch,
    COALESCE(va.vbp_event_count, 0) AS vbp_event_count,
    va.vbp_batches,
    COALESCE(pa.policy_count, 0) AS policy_count,
    ng.category AS negotiation_status,
    ng.pay_standard AS negotiation_pay_standard,
    ng.agreement_period AS negotiation_period,
    ng.batch_year AS negotiation_batch_year,
    COALESCE(ng.event_count, 0) AS negotiation_event_count,
    da.dual_channel_regions,
    COALESCE(da.dual_channel_region_count, 0) AS dual_channel_region_count,
    datetime('now', 'localtime') AS generated_at
FROM drug_product p
LEFT JOIN drug_registration r ON r.product_id = p.product_id
LEFT JOIN drug_molecule m ON m.molecule_id = p.molecule_id
LEFT JOIN latest_leaflet lf ON lf.product_id = p.product_id
LEFT JOIN indication_agg ia ON ia.product_id = p.product_id
LEFT JOIN manufacturer_agg ma ON ma.molecule_id = p.molecule_id
LEFT JOIN latest_insurance ins ON ins.product_id = p.product_id
LEFT JOIN insurance_catalog ic ON ic.catalog_id = ins.catalog_id
LEFT JOIN insurance_since isd ON isd.product_id = p.product_id
LEFT JOIN latest_listed_price lp ON lp.product_id = p.product_id
LEFT JOIN latest_vbp lv ON lv.product_id = p.product_id
LEFT JOIN vbp_agg va ON va.product_id = p.product_id
LEFT JOIN policy_agg pa ON pa.product_id = p.product_id
LEFT JOIN latest_negotiation ng ON ng.molecule_id = p.molecule_id
LEFT JOIN dual_agg da ON da.molecule_id = p.molecule_id;
"""

# 视图加速索引（幂等）
DRUG_PROFILE_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_leaflet_product_recent "
    "ON drug_leaflet(product_id, updated_at DESC, leaflet_id DESC)",
    "CREATE INDEX IF NOT EXISTS ix_indication_product "
    "ON drug_indication(product_id)",
    "CREATE INDEX IF NOT EXISTS ix_drug_product_molecule_mfr "
    "ON drug_product(molecule_id, manufacturer_norm)",
    "CREATE INDEX IF NOT EXISTS ix_insurance_product_current "
    "ON drug_insurance_entry(product_id, is_current, catalog_id)",
    "CREATE INDEX IF NOT EXISTS ix_price_product_type_date "
    "ON price_history(product_id, price_type, effective_date DESC)",
    "CREATE INDEX IF NOT EXISTS ix_procurement_product_recent "
    "ON procurement_result(product_id, updated_at DESC, result_id DESC)",
    "CREATE INDEX IF NOT EXISTS ix_policy_relation_product "
    "ON policy_drug_relation(product_id)",
    "CREATE INDEX IF NOT EXISTS ix_negotiation_molecule "
    "ON negotiation_result(molecule_id)",
    "CREATE INDEX IF NOT EXISTS ix_dual_channel_molecule "
    "ON dual_channel(molecule_id)",
    "CREATE INDEX IF NOT EXISTS ix_registration_product "
    "ON drug_registration(product_id)",
)
