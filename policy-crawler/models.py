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
    source_url TEXT DEFAULT '',
    notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS drug_insurance_entry (
    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES drug_product(product_id) ON DELETE CASCADE,
    catalog_id INTEGER REFERENCES insurance_catalog(catalog_id),
    category TEXT DEFAULT '',
    insurance_code TEXT DEFAULT '',
    payment_scope TEXT DEFAULT '',
    price TEXT DEFAULT '',
    effective_date TEXT DEFAULT '',
    expire_date TEXT DEFAULT '',
    is_current INTEGER DEFAULT 1
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
"""


# PostgreSQL 药品/器械域 DDL（路线 A：迁移到 Supabase/Neon 时直接执行）
DRUG_POSTGRES_DDL = """
CREATE TABLE IF NOT EXISTS drug_product (
    product_id BIGSERIAL PRIMARY KEY,
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
    source_url TEXT DEFAULT '',
    notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS drug_insurance_entry (
    entry_id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES drug_product(product_id) ON DELETE CASCADE,
    catalog_id BIGINT REFERENCES insurance_catalog(catalog_id),
    category VARCHAR(30) DEFAULT '',
    insurance_code VARCHAR(50) DEFAULT '',
    payment_scope TEXT DEFAULT '',
    price TEXT DEFAULT '',
    effective_date DATE,
    expire_date DATE,
    is_current BOOLEAN DEFAULT TRUE
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
"""
