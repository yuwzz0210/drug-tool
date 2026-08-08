# -*- coding: utf-8 -*-
"""管道：内容增强（PDF/OCR）→ PII 脱敏 → source_url 去重 → upsert → 运行统计。"""
import json
import logging
import time

from extractors import OCRExtractor, PDFExtractor
from queries import update_validity
from sanitize import scrub_pii


log = logging.getLogger("policy-crawler.pipeline")


class Pipeline:
    def __init__(self, store, task_name="policy_crawl", scrubbing=True,
                 pdf_extractor=None, ocr_extractor=None):
        self._store = store
        self._task = task_name
        self._scrubbing = scrubbing
        self._pdf = pdf_extractor or PDFExtractor()
        self._ocr = ocr_extractor or OCRExtractor()

    def enrich_content(self, item, pdf_extractor=None, ocr_extractor=None, url_fetch=None):
        """正文过短时尝试 PDF 附件提取、图片 OCR 补充（引擎与下载函数可注入）。"""
        pdf = pdf_extractor or self._pdf
        ocr = ocr_extractor or self._ocr
        content = item.content or ""
        if len(content) >= 100:
            return content
        for att in _json_list(item.attachment_links):
            url = att.get("url", "")
            if not url.lower().endswith((".pdf", ".docx", ".doc")):
                continue
            try:
                if att.get("file"):
                    text = pdf.extract(att["file"])
                elif url_fetch and url.lower().endswith(".pdf"):
                    text = pdf.extract(url_fetch(url))
                else:
                    continue
            except Exception:
                continue
            if text and text.strip():
                content = (content + "\n[附件] " + text.strip()).strip()
        if len(content) < 100:
            for img in _json_list(item.images):
                src = img.get("file") or img.get("data")
                if not src:
                    continue
                try:
                    text = ocr.extract(src)
                except Exception:
                    continue
                if text and text.strip():
                    content = (content + "\n[图片OCR] " + text.strip()).strip()
                    break
        item.content = content
        return content

    def process(self, items):
        start = time.strftime("%Y-%m-%d %H:%M:%S")
        total = len(items)
        new_added = 0
        errors = 0
        error_details = []
        for item in items:
            try:
                self.enrich_content(item)
                item.validity_status = update_validity({
                    "title": item.title, "publish_date": item.publish_date,
                })
                if self._scrubbing:
                    item.content = scrub_pii(item.content)
                    item.title = scrub_pii(item.title)
                if self._store.upsert_policy(item):
                    new_added += 1
            except Exception as exc:
                errors += 1
                error_details.append("{}: {}".format(item.source_url, exc))
                log.exception("入库失败 url=%s", item.source_url)
        end = time.strftime("%Y-%m-%d %H:%M:%S")
        status = "SUCCESS" if errors == 0 else ("PARTIAL" if new_added else "FAILED")
        self._store.log_run(
            task_name=self._task, start_time=start, end_time=end,
            total_fetched=total, new_added=new_added, error_count=errors,
            error_details="\n".join(error_details)[:4000], status=status,
        )
        log.info("管道完成 total=%s new=%s errors=%s status=%s", total, new_added, errors, status)
        return {"total": total, "new_added": new_added, "errors": errors, "status": status}


def _json_list(value):
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []
