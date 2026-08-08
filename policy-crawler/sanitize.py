# -*- coding: utf-8 -*-
"""HTML 清洗、敏感信息脱敏、发文字号提取。"""
import html as _html
import re
from html.parser import HTMLParser


_BLOCK_TAGS = {"p", "div", "li", "br", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "ul", "ol"}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        if data.strip():
            self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")


def clean_html_text(raw):
    """去掉 HTML 标签，保留段落换行，返回纯文本。"""
    if not raw:
        return ""
    parser = _TextExtractor()
    try:
        parser.feed(raw)
    except Exception:
        return _html.unescape(re.sub(r"<[^>]+>", "", raw))
    text = "".join(parser.parts)
    text = _html.unescape(text)
    text = re.sub(r"[ \t\u3000]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


_ID_CARD_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
_MOBILE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")


def scrub_pii(text):
    """擦除身份证号与手机号等个人敏感信息（先身份证后手机号，避免号码内含匹配）。"""
    if not text:
        return text
    text = _ID_CARD_RE.sub("[身份证号已脱敏]", text)
    text = _MOBILE_RE.sub("[手机号已脱敏]", text)
    return text


_DOC_NUMBER_RE = re.compile(r"([^\s，。；、]{0,30}?[〔(]\s*\d{4}\s*[〕)][^\s，。；、]{0,20}?号)")


def extract_doc_number(text):
    """提取发文字号，如：国药监药管〔2026〕18号。"""
    if not text:
        return ""
    m = _DOC_NUMBER_RE.search(text)
    return m.group(1).strip() if m else ""
