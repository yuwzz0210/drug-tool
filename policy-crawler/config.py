# -*- coding: utf-8 -*-
"""数据源注册、UA 列表、延迟/重试/日志保留等全局配置。"""
import json
import os


PROJECT_NAME = "医药流通政策信息聚合平台-爬虫"
VERSION = "0.1.0"

# 初始数据源清单（P0 实现 NMPA；其余来源按相同接口扩展）
SOURCES = {
    "nmpa": {
        "name": "国家药品监督管理局",
        "base": "https://www.nmpa.gov.cn",
        "list_url": "https://www.nmpa.gov.cn/xxgk/fgwj/gzwj/gzwjyp/",
        "parser": "nmpa",
        "keep_paths": ["/xxgk/fgwj/gzwj/gzwjyp/"],
        "enabled": True,
    },
    "nhsa": {
        "name": "国家医疗保障局",
        "base": "https://www.nhsa.gov.cn",
        "list_url": "https://www.nhsa.gov.cn/col/col104/index.html",
        "parser": "nhsa",
        "keep_paths": ["/art/"],
        "enabled": True,
    },
    "nhc": {
        "name": "国家卫生健康委",
        "base": "https://www.nhc.gov.cn",
        "list_url": "https://www.nhc.gov.cn/fzs/c100048/new_list.shtml",
        "parser": "nhc",
        "keep_paths": ["/fzs/"],
        "enabled": True,
    },
    "cde": {
        "name": "国家药监局药审中心",
        "base": "https://www.cde.org.cn",
        "list_url": "https://www.cde.org.cn/",
        "parser": "generic",
        "keep_paths": [],
        "enabled": False,
    },
}


def load_all_sources(regional_path=None):
    """合并内置国家数据源与 regional_sources.json（若存在）。"""
    if regional_path is None:
        regional_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "regional_sources.json")
    srcs = dict(SOURCES)
    if os.path.exists(regional_path):
        with open(regional_path, encoding="utf-8") as f:
            regional = json.load(f)
        srcs.update(regional)
    return srcs

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
]

# 合规基线：请求间隔 ≥4 秒，随机抖动 ±1 秒
REQUEST_DELAY_MIN = float(os.environ.get("REQUEST_DELAY_MIN", "4"))
REQUEST_DELAY_MAX = float(os.environ.get("REQUEST_DELAY_MAX", "5"))
RETRY_TIMES = int(os.environ.get("RETRY_TIMES", "2"))

# 日志保留 180 天（满足合规留痕 ≥6 个月）
LOG_RETENTION_DAYS = int(os.environ.get("LOG_RETENTION_DAYS", "180"))
LOG_DIR = os.environ.get("CRAWLER_LOG_DIR", "logs")

# 敏感配置走环境变量
DB_PATH = os.environ.get("CRAWLER_DB", "policy_crawler.db")
SMTP_HOST = os.environ.get("SMTP_HOST", "")

# 定时调度（每日两次）
CRON_TIMES = ("0 9 * * *", "0 15 * * *")
