# -*- coding: utf-8 -*-
"""PDF 与 OCR 文本提取：默认零依赖（未安装库时优雅返回空），支持注入引擎便于测试。"""
import io


class PDFExtractor:
    def __init__(self, engine=None):
        self._engine = engine

    def extract(self, src):
        """src 可为文件路径或 bytes。返回提取文本（可能为空）。"""
        if self._engine:
            return self._engine(src)
        return _pdf_default(src)


class OCRExtractor:
    def __init__(self, engine=None):
        self._engine = engine

    def extract(self, src):
        if self._engine:
            return self._engine(src)
        return _ocr_default(src)


def _stream(src):
    return io.BytesIO(src) if isinstance(src, bytes) else src


def _pdf_default(src):
    return _try_pdfplumber(src) or _try_pypdf(src) or _try_pypdf2(src)


def _try_pdfplumber(src):
    try:
        import pdfplumber
    except ImportError:
        return ""
    try:
        with pdfplumber.open(_stream(src)) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages).strip()
    except Exception:
        return ""


def _try_pypdf(src):
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(_stream(src))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except Exception:
        return ""


def _try_pypdf2(src):
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(_stream(src))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except Exception:
        return ""


def _ocr_default(src):
    try:
        import easyocr
    except ImportError:
        return ""
    try:
        reader = easyocr.Reader(["ch_sim", "en"], gpu=False)
        return " ".join(reader.readtext(src, detail=0)).strip()
    except Exception:
        return ""
