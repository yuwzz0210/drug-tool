# -*- coding: utf-8 -*-
"""数据模型：Policy 与建表 DDL（SQLite 默认 + PostgreSQL 对齐规格书）。"""
from dataclasses import dataclass, field


@dataclass
class Policy:
    title: str
    source_url: str = ""
    doc_number: str = ""
    issuing_authority: str = ""
    publish_date: str = ""
    implement_date: str = ""
    validity_status: str = "有效"
    content: str = ""
    raw_html: str = ""
    images: str = "[]"
    attachment_links: str = "[]"
    tags: str = "[]"


# ---------- 药品 / 器械 域（P1：品种主库） ----------


@dataclass
class DrugProduct:
    generic_name: str
    dosage_form: str = ""
    specification: str = ""
    manufacturer_norm: str = ""
    trade_name: str = ""
    atc_code: str = ""
    drug_type: str = ""
    is_otc: bool = False
    package_insert_url: str = ""
    source_url: str = ""
    is_verified: bool = False
    extra_data: str = "{}"


@dataclass
class DrugMolecule:
    """品种聚合层（molecule）：规范通用名，聚合多厂家/文号/规格的注册记录。"""
    generic_name: str
    atc_code: str = ""
    drug_type: str = ""
    mechanism_summary: str = ""
    is_verified: bool = False
    guideline_level: str = ""      # 指南推荐等级：1类/2A/2B/不推荐/未收录
    route: str = ""                # 给药途径：口服/注射/外用/吸入
    cold_chain: str = ""           # 冷链：常温/2-8℃冷藏/冷冻
    patent_expiry: str = ""
    iteration_chain: str = ""
    generation: str = ""
    extra_indications: str = ""
    reviewed_at: str = ""


@dataclass
class PriceRecord:
    """价格时序记录：1 次价格 = 1 行（挂网/中标/集采中选/零售）。"""
    product_id: int
    price: float
    price_type: str = "挂网"
    unit: str = ""
    effective_date: str = ""
    expire_date: str = ""
    source_url: str = ""
    reviewed_at: str = ""
    reviewed_by: str = ""
    notes: str = ""


@dataclass
class DrugMarket:
    """市场层：患者池/确诊率/处方渗透率/年销售额（估算，带置信度与口径）。"""
    molecule_id: int
    region: str = "全国"
    sales_year: int = 0
    patient_count: float = 0
    diagnosis_rate: float = 0
    prescription_penetration: float = 0
    annual_sales: str = ""
    formula: str = ""
    confidence: str = "中"
    source: str = ""
    estimated_date: str = ""
    reviewed_at: str = ""


@dataclass
class DrugRegistration:
    product_id: int
    approval_number: str = ""
    registration_date: str = ""
    expire_date: str = ""
    status: str = "有效"
    holder: str = ""
    source_url: str = ""


@dataclass
class DrugIndication:
    product_id: int
    indication_text: str
    indication_norm: str = ""
    approval_status: str = ""
    effective_date: str = ""
    is_current: bool = True


@dataclass
class DrugMechanism:
    product_id: int
    target_name: str = ""
    mechanism_text: str = ""
    is_current: bool = True


@dataclass
class DrugIngredient:
    product_id: int
    ingredient_name: str
    strength: str = ""
    unit: str = ""


@dataclass
class InsuranceCatalog:
    version_name: str
    publish_date: str = ""
    source_url: str = ""
    notes: str = ""


@dataclass
class DrugInsuranceEntry:
    product_id: int
    catalog_id: int = 0
    category: str = ""
    insurance_code: str = ""
    payment_scope: str = ""
    price: str = ""
    effective_date: str = ""
    expire_date: str = ""
    is_current: bool = True


@dataclass
class DeviceProduct:
    registration_number: str
    product_name: str
    management_category: str = ""
    intended_use: str = ""
    structural_composition: str = ""
    manufacturer: str = ""
    approval_date: str = ""
    source_url: str = ""
    is_verified: bool = False
    extra_data: str = "{}"


@dataclass
class PolicyDrugRelation:
    policy_id: int
    product_id: int
    relation_type: str = ""
    confidence: float = 0.0
    is_manual_confirmed: bool = False


@dataclass
class PolicyDeviceRelation:
    policy_id: int
    device_id: int
    relation_type: str = ""
    confidence: float = 0.0
    is_manual_confirmed: bool = False


SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS policies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    doc_number TEXT,
    issuing_authority TEXT,
    publish_date TEXT,
    implement_date TEXT,
    validity_status TEXT DEFAULT '有效',
    source_url TEXT UNIQUE NOT NULL,
    content TEXT,
    raw_html TEXT,
    attachment_links TEXT DEFAULT '[]',
    tags TEXT DEFAULT '[]',
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    parent_id INTEGER REFERENCES categories(id)
);
CREATE TABLE IF NOT EXISTS policy_category (
    policy_id INTEGER REFERENCES policies(id) ON DELETE CASCADE,
    category_id INTEGER REFERENCES categories(id) ON DELETE CASCADE,
    PRIMARY KEY (policy_id, category_id)
);
CREATE TABLE IF NOT EXISTS crawler_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name TEXT,
    start_time TEXT,
    end_time TEXT,
    total_fetched INTEGER DEFAULT 0,
    new_added INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    error_details TEXT,
    status TEXT DEFAULT 'SUCCESS'
);
"""

# drug_profile v1：一行 = 一个批准文号（无文号品种 approval_number 为空），
# “最新值”统一在此定义，前端/快照不再各自取数。
# v1（保留备查）：逐行相关子查询，品种库过万后导出过慢 → 见 drug_profile_view.py v2
DRUG_PROFILE_VIEW_SQL_V1 = """
CREATE VIEW IF NOT EXISTS drug_profile AS
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
    CASE WHEN COALESCE(r.approval_number,'') LIKE '国药准字J%'
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
    (SELECT l.leaflet_date FROM drug_leaflet l
      WHERE l.product_id=p.product_id
      ORDER BY l.updated_at DESC, l.leaflet_id DESC LIMIT 1) AS leaflet_date,
    (SELECT l.usage_dosage FROM drug_leaflet l
      WHERE l.product_id=p.product_id
      ORDER BY l.updated_at DESC, l.leaflet_id DESC LIMIT 1) AS usage_dosage,
    (SELECT l.storage FROM drug_leaflet l
      WHERE l.product_id=p.product_id
      ORDER BY l.updated_at DESC, l.leaflet_id DESC LIMIT 1) AS storage,
    (SELECT GROUP_CONCAT(di.indication_text, '；')
       FROM drug_indication di WHERE di.product_id=p.product_id)
        AS indications_text,
    (SELECT COUNT(*) FROM drug_indication di
      WHERE di.product_id=p.product_id) AS indication_count,
    (SELECT COUNT(DISTINCT p2.manufacturer_norm) FROM drug_product p2
      WHERE p2.molecule_id=p.molecule_id AND p2.molecule_id IS NOT NULL)
        AS followers_count,
    CASE WHEN m.molecule_id IS NOT NULL AND
         (SELECT COUNT(DISTINCT p2.manufacturer_norm) FROM drug_product p2
           WHERE p2.molecule_id=p.molecule_id)=1
         THEN 1 ELSE 0 END AS is_exclusive,
    (SELECT ie.category FROM drug_insurance_entry ie
      WHERE ie.product_id=p.product_id AND ie.is_current=1
      ORDER BY ie.catalog_id DESC, ie.entry_id DESC LIMIT 1)
        AS insurance_category,
    (SELECT ie.insurance_code FROM drug_insurance_entry ie
      WHERE ie.product_id=p.product_id AND ie.is_current=1
      ORDER BY ie.catalog_id DESC, ie.entry_id DESC LIMIT 1)
        AS insurance_code,
    (SELECT ie.region FROM drug_insurance_entry ie
      WHERE ie.product_id=p.product_id AND ie.is_current=1
      ORDER BY ie.catalog_id DESC, ie.entry_id DESC LIMIT 1)
        AS insurance_region,
    (SELECT ie.reimbursement_ratio FROM drug_insurance_entry ie
      WHERE ie.product_id=p.product_id AND ie.is_current=1
      ORDER BY ie.catalog_id DESC, ie.entry_id DESC LIMIT 1)
        AS reimbursement_ratio,
    (SELECT ie.payment_scope FROM drug_insurance_entry ie
      WHERE ie.product_id=p.product_id AND ie.is_current=1
      ORDER BY ie.catalog_id DESC, ie.entry_id DESC LIMIT 1)
        AS payment_scope,
    (SELECT ie.supplement_status FROM drug_insurance_entry ie
      WHERE ie.product_id=p.product_id AND ie.is_current=1
      ORDER BY ie.catalog_id DESC, ie.entry_id DESC LIMIT 1)
        AS supplement_status,
    (SELECT ic.version_name FROM drug_insurance_entry ie
       JOIN insurance_catalog ic ON ic.catalog_id=ie.catalog_id
      WHERE ie.product_id=p.product_id AND ie.is_current=1
      ORDER BY ic.catalog_id DESC LIMIT 1)
        AS insurance_catalog_version,
    (SELECT MIN(ic.publish_date) FROM drug_insurance_entry ie
       JOIN insurance_catalog ic ON ic.catalog_id=ie.catalog_id
      WHERE ie.product_id=p.product_id AND ic.publish_date IS NOT NULL
        AND ic.publish_date != '')
        AS insurance_since_date,
    (SELECT ph.price FROM price_history ph
      WHERE ph.product_id=p.product_id AND ph.price_type='挂网'
      ORDER BY ph.effective_date DESC, ph.price_id DESC LIMIT 1)
        AS latest_listed_price,
    (SELECT ph.region FROM price_history ph
      WHERE ph.product_id=p.product_id AND ph.price_type='挂网'
      ORDER BY ph.effective_date DESC, ph.price_id DESC LIMIT 1)
        AS listed_price_region,
    (SELECT ph.effective_date FROM price_history ph
      WHERE ph.product_id=p.product_id AND ph.price_type='挂网'
      ORDER BY ph.effective_date DESC, ph.price_id DESC LIMIT 1)
        AS listed_price_date,
    (SELECT pr.price FROM procurement_result pr
      WHERE pr.product_id=p.product_id AND pr.price IS NOT NULL
      ORDER BY pr.updated_at DESC, pr.result_id DESC LIMIT 1)
        AS latest_vbp_price,
    (SELECT pr.batch FROM procurement_result pr
      WHERE pr.product_id=p.product_id
      ORDER BY pr.updated_at DESC, pr.result_id DESC LIMIT 1)
        AS latest_vbp_batch,
    (SELECT COUNT(*) FROM procurement_result pr
      WHERE pr.product_id=p.product_id) AS vbp_event_count,
    (SELECT GROUP_CONCAT(DISTINCT pr.batch) FROM procurement_result pr
      WHERE pr.product_id=p.product_id) AS vbp_batches,
    (SELECT COUNT(*) FROM policy_drug_relation pdr
      WHERE pdr.product_id=p.product_id) AS policy_count,
    (SELECT nr.category FROM negotiation_result nr
      WHERE nr.molecule_id=m.molecule_id
      ORDER BY nr.negotiation_id DESC LIMIT 1) AS negotiation_status,
    (SELECT nr.pay_standard FROM negotiation_result nr
      WHERE nr.molecule_id=m.molecule_id
      ORDER BY nr.negotiation_id DESC LIMIT 1) AS negotiation_pay_standard,
    (SELECT nr.agreement_period FROM negotiation_result nr
      WHERE nr.molecule_id=m.molecule_id
      ORDER BY nr.negotiation_id DESC LIMIT 1) AS negotiation_period,
    (SELECT nr.batch_year FROM negotiation_result nr
      WHERE nr.molecule_id=m.molecule_id
      ORDER BY nr.negotiation_id DESC LIMIT 1) AS negotiation_batch_year,
    (SELECT COUNT(*) FROM negotiation_result nr
      WHERE nr.molecule_id=m.molecule_id) AS negotiation_event_count,
    (SELECT GROUP_CONCAT(DISTINCT dc.region) FROM dual_channel dc
      WHERE dc.molecule_id=m.molecule_id AND dc.status='纳入')
        AS dual_channel_regions,
    (SELECT COUNT(DISTINCT dc.region) FROM dual_channel dc
      WHERE dc.molecule_id=m.molecule_id) AS dual_channel_region_count,
    datetime('now','localtime') AS generated_at
FROM drug_product p
LEFT JOIN drug_registration r ON r.product_id = p.product_id
LEFT JOIN drug_molecule m ON m.molecule_id = p.molecule_id;
"""

POSTGRES_DDL = """
CREATE TABLE IF NOT EXISTS policies (
    id SERIAL PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    doc_number VARCHAR(100),
    issuing_authority VARCHAR(200),
    publish_date DATE,
    implement_date DATE,
    validity_status VARCHAR(20) DEFAULT '有效',
    source_url VARCHAR(500) UNIQUE NOT NULL,
    content TEXT,
    raw_html TEXT,
    attachment_links JSONB,
    tags VARCHAR(50)[],
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    parent_id INT REFERENCES categories(id)
);
CREATE TABLE IF NOT EXISTS policy_category (
    policy_id INT REFERENCES policies(id) ON DELETE CASCADE,
    category_id INT REFERENCES categories(id) ON DELETE CASCADE,
    PRIMARY KEY (policy_id, category_id)
);
CREATE TABLE IF NOT EXISTS crawler_logs (
    id SERIAL PRIMARY KEY,
    task_name VARCHAR(50),
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    total_fetched INT,
    new_added INT,
    error_count INT,
    error_details TEXT,
    status VARCHAR(20) DEFAULT 'SUCCESS'
);
"""


# SQLite 药品/器械域建表（P1：与政策库同库，便于 serve.py 一站式提供）
DRUG_SCHEMA = """
CREATE TABLE IF NOT EXISTS drug_product (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    molecule_id INTEGER REFERENCES drug_molecule(molecule_id),
    generic_name TEXT NOT NULL,
    dosage_form TEXT DEFAULT '',
    specification TEXT DEFAULT '',
    manufacturer_norm TEXT DEFAULT '',
    trade_name TEXT DEFAULT '',
    atc_code TEXT DEFAULT '',
    drug_type TEXT DEFAULT '',
    is_otc INTEGER DEFAULT 0,
    package_insert_url TEXT DEFAULT '',
    source_url TEXT DEFAULT '',
    is_verified INTEGER DEFAULT 0,
    extra_data TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE (generic_name, dosage_form, specification, manufacturer_norm)
);
CREATE TABLE IF NOT EXISTS drug_molecule (
    molecule_id INTEGER PRIMARY KEY AUTOINCREMENT,
    generic_name TEXT NOT NULL UNIQUE,
    atc_code TEXT DEFAULT '',
    drug_type TEXT DEFAULT '',
    mechanism_summary TEXT DEFAULT '',
    is_verified INTEGER DEFAULT 0,
    guideline_level TEXT DEFAULT '',
    route TEXT DEFAULT '',
    cold_chain TEXT DEFAULT '',
    patent_expiry TEXT DEFAULT '',
    iteration_chain TEXT DEFAULT '',
    generation TEXT DEFAULT '',
    extra_indications TEXT DEFAULT '',
    therapeutic_area TEXT DEFAULT '',
    disease TEXT DEFAULT '',
    sub_disease TEXT DEFAULT '',
    classification_source TEXT DEFAULT '',
    classification_confidence TEXT DEFAULT '',
    reviewed_at TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS negotiation_result (
    negotiation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    molecule_id INTEGER REFERENCES drug_molecule(molecule_id) ON DELETE SET NULL,
    product_id INTEGER REFERENCES drug_product(product_id) ON DELETE SET NULL,
    catalog_id INTEGER REFERENCES insurance_catalog(catalog_id),
    catalog_entry_id INTEGER,
    batch_year TEXT DEFAULT '',
    drug_name TEXT NOT NULL,
    dosage_form TEXT DEFAULT '',
    category TEXT DEFAULT '',
    pay_standard TEXT DEFAULT '',
    agreement_period TEXT DEFAULT '',
    source_url TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE (catalog_entry_id)
);
CREATE TABLE IF NOT EXISTS dual_channel (
    dual_id INTEGER PRIMARY KEY AUTOINCREMENT,
    molecule_id INTEGER REFERENCES drug_molecule(molecule_id) ON DELETE SET NULL,
    product_id INTEGER REFERENCES drug_product(product_id) ON DELETE SET NULL,
    region TEXT NOT NULL DEFAULT '国家',
    drug_name TEXT NOT NULL,
    dosage_form TEXT DEFAULT '',
    specification TEXT DEFAULT '',
    status TEXT DEFAULT '纳入',
    effective_date TEXT DEFAULT '',
    batch TEXT DEFAULT '',
    source_url TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE (region, drug_name, dosage_form, specification)
);
CREATE TABLE IF NOT EXISTS price_history (
    price_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES drug_product(product_id) ON DELETE CASCADE,
    price_type TEXT NOT NULL DEFAULT '挂网',
    price REAL NOT NULL,
    unit TEXT DEFAULT '',
    region TEXT DEFAULT '',
    batch TEXT DEFAULT '',
    price_flag TEXT DEFAULT '',
    effective_date TEXT DEFAULT '',
    expire_date TEXT DEFAULT '',
    source_url TEXT DEFAULT '',
    reviewed_at TEXT DEFAULT '',
    reviewed_by TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE (product_id, price_type, region, batch, effective_date)
);
CREATE TABLE IF NOT EXISTS procurement_result (
    result_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch TEXT NOT NULL,
    batch_seq TEXT DEFAULT '',
    variety_name TEXT DEFAULT '',
    generic_name TEXT NOT NULL,
    dosage_form TEXT DEFAULT '',
    spec_pack TEXT DEFAULT '',
    packaging TEXT DEFAULT '',
    supplier TEXT NOT NULL,
    product_id INTEGER REFERENCES drug_product(product_id) ON DELETE SET NULL,
    price REAL,
    price_unit TEXT DEFAULT '',
    source TEXT DEFAULT '',
    source_url TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE (batch, batch_seq, generic_name, spec_pack, supplier)
);
CREATE TABLE IF NOT EXISTS drug_market (
    market_id INTEGER PRIMARY KEY AUTOINCREMENT,
    molecule_id INTEGER NOT NULL REFERENCES drug_molecule(molecule_id) ON DELETE CASCADE,
    region TEXT NOT NULL DEFAULT '全国',
    sales_year INTEGER,
    patient_count REAL DEFAULT 0,
    diagnosis_rate REAL DEFAULT 0,
    prescription_penetration REAL DEFAULT 0,
    annual_sales TEXT DEFAULT '',
    formula TEXT DEFAULT '',
    confidence TEXT DEFAULT '中',
    source TEXT DEFAULT '',
    estimated_date TEXT DEFAULT '',
    reviewed_at TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE (molecule_id, region, sales_year)
);
CREATE TABLE IF NOT EXISTS drug_registration (
    registration_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES drug_product(product_id) ON DELETE CASCADE,
    approval_number TEXT UNIQUE,
    registration_date TEXT DEFAULT '',
    expire_date TEXT DEFAULT '',
    status TEXT DEFAULT '有效',
    holder TEXT DEFAULT '',
    source_url TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS drug_indication (
    indication_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES drug_product(product_id) ON DELETE CASCADE,
    indication_text TEXT NOT NULL,
    indication_norm TEXT DEFAULT '',
    approval_status TEXT DEFAULT '',
    effective_date TEXT DEFAULT '',
    is_current INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS drug_mechanism (
    mechanism_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES drug_product(product_id) ON DELETE CASCADE,
    target_name TEXT DEFAULT '',
    mechanism_text TEXT DEFAULT '',
    is_current INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS drug_ingredient (
    ingredient_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES drug_product(product_id) ON DELETE CASCADE,
    ingredient_name TEXT NOT NULL,
    strength TEXT DEFAULT '',
    unit TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS insurance_catalog (
    catalog_id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_name TEXT UNIQUE,
    publish_date TEXT DEFAULT '',
    region TEXT DEFAULT '国家',
    catalog_type TEXT DEFAULT '国家医保药品目录',
    source_url TEXT DEFAULT '',
    notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS drug_insurance_entry (
    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES drug_product(product_id) ON DELETE CASCADE,
    catalog_id INTEGER REFERENCES insurance_catalog(catalog_id),
    region TEXT DEFAULT '国家',
    category TEXT DEFAULT '',
    insurance_code TEXT DEFAULT '',
    payment_scope TEXT DEFAULT '',
    reimbursement_ratio TEXT DEFAULT '',
    supplement_status TEXT DEFAULT '',
    price TEXT DEFAULT '',
    effective_date TEXT DEFAULT '',
    expire_date TEXT DEFAULT '',
    is_current INTEGER DEFAULT 1,
    source_url TEXT DEFAULT '',
    notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS insurance_catalog_entry (
    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    catalog_id INTEGER NOT NULL REFERENCES insurance_catalog(catalog_id) ON DELETE CASCADE,
    section TEXT DEFAULT '',
    category TEXT DEFAULT '',
    code TEXT DEFAULT '',
    name TEXT NOT NULL,
    dosage_form TEXT DEFAULT '',
    pay_standard TEXT DEFAULT '',
    payment_scope TEXT DEFAULT '',
    valid_until TEXT DEFAULT '',
    UNIQUE (catalog_id, code, name, dosage_form)
);
CREATE TABLE IF NOT EXISTS device_product (
    device_id INTEGER PRIMARY KEY AUTOINCREMENT,
    registration_number TEXT UNIQUE NOT NULL,
    product_name TEXT NOT NULL,
    management_category TEXT DEFAULT '',
    intended_use TEXT DEFAULT '',
    structural_composition TEXT DEFAULT '',
    manufacturer TEXT DEFAULT '',
    approval_date TEXT DEFAULT '',
    source_url TEXT DEFAULT '',
    is_verified INTEGER DEFAULT 0,
    extra_data TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS device_insurance_entry (
    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL REFERENCES device_product(device_id) ON DELETE CASCADE,
    catalog_id INTEGER REFERENCES insurance_catalog(catalog_id),
    category TEXT DEFAULT '',
    insurance_code TEXT DEFAULT '',
    price TEXT DEFAULT '',
    effective_date TEXT DEFAULT '',
    expire_date TEXT DEFAULT '',
    is_current INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS policy_drug_relation (
    relation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_id INTEGER NOT NULL REFERENCES policies(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES drug_product(product_id) ON DELETE CASCADE,
    relation_type TEXT DEFAULT '',
    confidence REAL DEFAULT 0,
    is_manual_confirmed INTEGER DEFAULT 0,
    UNIQUE (policy_id, product_id, relation_type)
);
CREATE TABLE IF NOT EXISTS policy_device_relation (
    relation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_id INTEGER NOT NULL REFERENCES policies(id) ON DELETE CASCADE,
    device_id INTEGER NOT NULL REFERENCES device_product(device_id) ON DELETE CASCADE,
    relation_type TEXT DEFAULT '',
    confidence REAL DEFAULT 0,
    is_manual_confirmed INTEGER DEFAULT 0,
    UNIQUE (policy_id, device_id, relation_type)
);
CREATE TABLE IF NOT EXISTS drug_change_history (
    change_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT DEFAULT 'product',
    entity_id INTEGER,
    change_type TEXT DEFAULT '',
    change_date TEXT DEFAULT '',
    description TEXT DEFAULT '',
    source_url TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS drug_leaflet (
    leaflet_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES drug_product(product_id) ON DELETE CASCADE,
    approval_number TEXT DEFAULT '',
    catalog_rid TEXT DEFAULT '',
    pdf_url TEXT DEFAULT '',
    source_url TEXT DEFAULT '',
    filename TEXT DEFAULT '',
    route TEXT DEFAULT '',
    storage TEXT DEFAULT '',
    cold_chain TEXT DEFAULT '',
    usage_dosage TEXT DEFAULT '',
    indications TEXT DEFAULT '',
    leaflet_date TEXT DEFAULT '',
    sections_json TEXT DEFAULT '{}',
    raw_text TEXT DEFAULT '',
    fetched_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE (product_id, catalog_rid)
);
"""

# 视图在 DRUG_SCHEMA 定义完成后追加，供 DrugStore 初始化与迁移脚本共用
# v2：预聚合 CTE 版本（性能），列名与 v1 完全一致
from drug_profile_view import (  # noqa: E402
    DRUG_PROFILE_INDEXES,
    DRUG_PROFILE_VIEW_SQL_V2,
)

DRUG_PROFILE_VIEW_SQL = DRUG_PROFILE_VIEW_SQL_V2
DRUG_SCHEMA = DRUG_SCHEMA + "\n" + DRUG_PROFILE_VIEW_SQL


# PostgreSQL 药品/器械域 DDL（路线 A：迁移到 Supabase/Neon 时直接执行）
DRUG_POSTGRES_DDL = """
CREATE TABLE IF NOT EXISTS drug_product (
    product_id BIGSERIAL PRIMARY KEY,
    molecule_id BIGINT REFERENCES drug_molecule(molecule_id),
    generic_name VARCHAR(200) NOT NULL,
    dosage_form VARCHAR(100) DEFAULT '',
    specification VARCHAR(200) DEFAULT '',
    manufacturer_norm VARCHAR(300) DEFAULT '',
    trade_name VARCHAR(200) DEFAULT '',
    atc_code VARCHAR(20) DEFAULT '',
    drug_type VARCHAR(50) DEFAULT '',
    is_otc BOOLEAN DEFAULT FALSE,
    package_insert_url TEXT DEFAULT '',
    source_url TEXT DEFAULT '',
    is_verified BOOLEAN DEFAULT FALSE,
    extra_data JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (generic_name, dosage_form, specification, manufacturer_norm)
);
CREATE TABLE IF NOT EXISTS drug_molecule (
    molecule_id BIGSERIAL PRIMARY KEY,
    generic_name VARCHAR(200) UNIQUE NOT NULL,
    atc_code VARCHAR(20) DEFAULT '',
    drug_type VARCHAR(50) DEFAULT '',
    mechanism_summary TEXT DEFAULT '',
    is_verified BOOLEAN DEFAULT FALSE,
    guideline_level VARCHAR(20) DEFAULT '',
    route VARCHAR(20) DEFAULT '',
    cold_chain VARCHAR(20) DEFAULT '',
    patent_expiry DATE,
    iteration_chain VARCHAR(200) DEFAULT '',
    generation VARCHAR(50) DEFAULT '',
    extra_indications TEXT DEFAULT '',
    therapeutic_area VARCHAR(100) DEFAULT '',
    disease VARCHAR(200) DEFAULT '',
    sub_disease VARCHAR(200) DEFAULT '',
    classification_source VARCHAR(200) DEFAULT '',
    classification_confidence VARCHAR(10) DEFAULT '',
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS price_history (
    price_id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES drug_product(product_id) ON DELETE CASCADE,
    price_type VARCHAR(20) NOT NULL DEFAULT '挂网',
    price NUMERIC(12,4) NOT NULL,
    unit VARCHAR(20) DEFAULT '',
    region VARCHAR(40) DEFAULT '',
    batch VARCHAR(60) DEFAULT '',
    price_flag VARCHAR(10) DEFAULT '',
    effective_date DATE,
    expire_date DATE,
    source_url TEXT DEFAULT '',
    reviewed_at TIMESTAMPTZ,
    reviewed_by VARCHAR(100) DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (product_id, price_type, region, batch, effective_date)
);
CREATE TABLE IF NOT EXISTS procurement_result (
    result_id BIGSERIAL PRIMARY KEY,
    batch VARCHAR(60) NOT NULL,
    batch_seq VARCHAR(20) DEFAULT '',
    variety_name VARCHAR(200) DEFAULT '',
    generic_name VARCHAR(200) NOT NULL,
    dosage_form VARCHAR(60) DEFAULT '',
    spec_pack VARCHAR(200) DEFAULT '',
    packaging TEXT DEFAULT '',
    supplier VARCHAR(300) NOT NULL,
    product_id BIGINT REFERENCES drug_product(product_id) ON DELETE SET NULL,
    price NUMERIC(12,4),
    price_unit VARCHAR(40) DEFAULT '',
    source VARCHAR(200) DEFAULT '',
    source_url VARCHAR(500) DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (batch, batch_seq, generic_name, spec_pack, supplier)
);
CREATE TABLE IF NOT EXISTS drug_market (
    market_id BIGSERIAL PRIMARY KEY,
    molecule_id BIGINT NOT NULL REFERENCES drug_molecule(molecule_id) ON DELETE CASCADE,
    region VARCHAR(20) NOT NULL DEFAULT '全国',
    sales_year INTEGER,
    patient_count NUMERIC(14,2) DEFAULT 0,
    diagnosis_rate NUMERIC(8,4) DEFAULT 0,
    prescription_penetration NUMERIC(8,4) DEFAULT 0,
    annual_sales TEXT DEFAULT '',
    formula TEXT DEFAULT '',
    confidence VARCHAR(10) DEFAULT '中',
    source TEXT DEFAULT '',
    estimated_date DATE,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (molecule_id, region, sales_year)
);
-- 国谈/竞价结果（来源：国家医保目录谈判与竞价条目）
CREATE TABLE IF NOT EXISTS negotiation_result (
    negotiation_id BIGSERIAL PRIMARY KEY,
    molecule_id BIGINT REFERENCES drug_molecule(molecule_id) ON DELETE SET NULL,
    product_id BIGINT REFERENCES drug_product(product_id) ON DELETE SET NULL,
    catalog_id BIGINT REFERENCES insurance_catalog(catalog_id),
    catalog_entry_id BIGINT,
    batch_year VARCHAR(20) DEFAULT '',
    drug_name VARCHAR(300) NOT NULL,
    dosage_form VARCHAR(100) DEFAULT '',
    category VARCHAR(30) DEFAULT '',
    pay_standard TEXT DEFAULT '',
    agreement_period TEXT DEFAULT '',
    source_url TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (catalog_entry_id)
);
-- 双通道（谈判药品定点医疗机构/定点零售药店）名单
CREATE TABLE IF NOT EXISTS dual_channel (
    dual_id BIGSERIAL PRIMARY KEY,
    molecule_id BIGINT REFERENCES drug_molecule(molecule_id) ON DELETE SET NULL,
    product_id BIGINT REFERENCES drug_product(product_id) ON DELETE SET NULL,
    region VARCHAR(40) NOT NULL DEFAULT '国家',
    drug_name VARCHAR(300) NOT NULL,
    dosage_form VARCHAR(100) DEFAULT '',
    specification VARCHAR(200) DEFAULT '',
    status VARCHAR(20) DEFAULT '纳入',
    effective_date DATE,
    batch VARCHAR(60) DEFAULT '',
    source_url TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (region, drug_name, dosage_form, specification)
);
CREATE TABLE IF NOT EXISTS drug_registration (
    registration_id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES drug_product(product_id) ON DELETE CASCADE,
    approval_number VARCHAR(50) UNIQUE,
    registration_date DATE,
    expire_date DATE,
    status VARCHAR(20) DEFAULT '有效',
    holder VARCHAR(300) DEFAULT '',
    source_url TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS drug_indication (
    indication_id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES drug_product(product_id) ON DELETE CASCADE,
    indication_text TEXT NOT NULL,
    indication_norm TEXT DEFAULT '',
    approval_status VARCHAR(30) DEFAULT '',
    effective_date DATE,
    is_current BOOLEAN DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS drug_mechanism (
    mechanism_id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES drug_product(product_id) ON DELETE CASCADE,
    target_name VARCHAR(200) DEFAULT '',
    mechanism_text TEXT DEFAULT '',
    is_current BOOLEAN DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS drug_ingredient (
    ingredient_id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES drug_product(product_id) ON DELETE CASCADE,
    ingredient_name VARCHAR(200) NOT NULL,
    strength VARCHAR(100) DEFAULT '',
    unit VARCHAR(50) DEFAULT ''
);
CREATE TABLE IF NOT EXISTS insurance_catalog (
    catalog_id BIGSERIAL PRIMARY KEY,
    version_name VARCHAR(100) UNIQUE,
    publish_date DATE,
    region VARCHAR(40) DEFAULT '国家',
    catalog_type VARCHAR(60) DEFAULT '国家医保药品目录',
    source_url TEXT DEFAULT '',
    notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS drug_insurance_entry (
    entry_id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES drug_product(product_id) ON DELETE CASCADE,
    catalog_id BIGINT REFERENCES insurance_catalog(catalog_id),
    region VARCHAR(40) DEFAULT '国家',
    category VARCHAR(30) DEFAULT '',
    insurance_code VARCHAR(50) DEFAULT '',
    payment_scope TEXT DEFAULT '',
    reimbursement_ratio VARCHAR(100) DEFAULT '',
    supplement_status VARCHAR(60) DEFAULT '',
    price TEXT DEFAULT '',
    effective_date DATE,
    expire_date DATE,
    is_current BOOLEAN DEFAULT TRUE,
    source_url VARCHAR(500) DEFAULT '',
    notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS insurance_catalog_entry (
    entry_id BIGSERIAL PRIMARY KEY,
    catalog_id BIGINT NOT NULL REFERENCES insurance_catalog(catalog_id) ON DELETE CASCADE,
    section VARCHAR(20) DEFAULT '',
    category VARCHAR(30) DEFAULT '',
    code VARCHAR(50) DEFAULT '',
    name VARCHAR(300) NOT NULL,
    dosage_form VARCHAR(100) DEFAULT '',
    pay_standard TEXT DEFAULT '',
    payment_scope TEXT DEFAULT '',
    valid_until TEXT DEFAULT '',
    UNIQUE (catalog_id, code, name, dosage_form)
);
CREATE TABLE IF NOT EXISTS device_product (
    device_id BIGSERIAL PRIMARY KEY,
    registration_number VARCHAR(100) UNIQUE NOT NULL,
    product_name VARCHAR(300) NOT NULL,
    management_category VARCHAR(10) DEFAULT '',
    intended_use TEXT DEFAULT '',
    structural_composition TEXT DEFAULT '',
    manufacturer VARCHAR(300) DEFAULT '',
    approval_date DATE,
    source_url TEXT DEFAULT '',
    is_verified BOOLEAN DEFAULT FALSE,
    extra_data JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS device_insurance_entry (
    entry_id BIGSERIAL PRIMARY KEY,
    device_id BIGINT NOT NULL REFERENCES device_product(device_id) ON DELETE CASCADE,
    catalog_id BIGINT REFERENCES insurance_catalog(catalog_id),
    category VARCHAR(30) DEFAULT '',
    insurance_code VARCHAR(50) DEFAULT '',
    price TEXT DEFAULT '',
    effective_date DATE,
    expire_date DATE,
    is_current BOOLEAN DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS policy_drug_relation (
    relation_id BIGSERIAL PRIMARY KEY,
    policy_id BIGINT NOT NULL REFERENCES policies(id) ON DELETE CASCADE,
    product_id BIGINT NOT NULL REFERENCES drug_product(product_id) ON DELETE CASCADE,
    relation_type VARCHAR(50) DEFAULT '',
    confidence NUMERIC(5,2) DEFAULT 0,
    is_manual_confirmed BOOLEAN DEFAULT FALSE,
    UNIQUE (policy_id, product_id, relation_type)
);
CREATE TABLE IF NOT EXISTS policy_device_relation (
    relation_id BIGSERIAL PRIMARY KEY,
    policy_id BIGINT NOT NULL REFERENCES policies(id) ON DELETE CASCADE,
    device_id BIGINT NOT NULL REFERENCES device_product(device_id) ON DELETE CASCADE,
    relation_type VARCHAR(50) DEFAULT '',
    confidence NUMERIC(5,2) DEFAULT 0,
    is_manual_confirmed BOOLEAN DEFAULT FALSE,
    UNIQUE (policy_id, device_id, relation_type)
);
CREATE TABLE IF NOT EXISTS drug_change_history (
    change_id BIGSERIAL PRIMARY KEY,
    entity_type VARCHAR(20) DEFAULT 'product',
    entity_id BIGINT,
    change_type VARCHAR(100) DEFAULT '',
    change_date DATE,
    description TEXT DEFAULT '',
    source_url TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS drug_leaflet (
    leaflet_id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES drug_product(product_id) ON DELETE CASCADE,
    approval_number VARCHAR(40) DEFAULT '',
    catalog_rid VARCHAR(80) DEFAULT '',
    pdf_url VARCHAR(500) DEFAULT '',
    source_url VARCHAR(500) DEFAULT '',
    filename VARCHAR(300) DEFAULT '',
    route VARCHAR(20) DEFAULT '',
    storage TEXT DEFAULT '',
    cold_chain VARCHAR(20) DEFAULT '',
    usage_dosage TEXT DEFAULT '',
    indications TEXT DEFAULT '',
    leaflet_date DATE,
    sections_json JSONB DEFAULT '{}'::jsonb,
    raw_text TEXT DEFAULT '',
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (product_id, catalog_rid)
);
"""
