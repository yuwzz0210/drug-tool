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
