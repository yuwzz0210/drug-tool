# -*- coding: utf-8 -*-
"""按日切割日志，保留 180 天（合规留痕 ≥6 个月）。"""
import logging
import os
from logging.handlers import TimedRotatingFileHandler

from config import LOG_DIR, LOG_RETENTION_DAYS


def setup_logger(name="policy-crawler", level=logging.INFO, log_dir=None):
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)
    log_dir = log_dir or LOG_DIR
    try:
        os.makedirs(log_dir, exist_ok=True)
        file_handler = TimedRotatingFileHandler(
            os.path.join(log_dir, "crawler.log"),
            when="midnight",
            backupCount=LOG_RETENTION_DAYS,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except OSError as exc:
        logger.warning("文件日志初始化失败，仅控制台输出：%s", exc)
    return logger
