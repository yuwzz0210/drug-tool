# -*- coding: utf-8 -*-
"""解析器：按来源注册。P0 NMPA 已用真实页面校验；P1 NHSA/NHC 已用真实详情页校验。"""
import html as _html
import re
import urllib.parse

from sanitize import clean_html_text, extract_doc_number


_DATE_RE = re.compile(r"(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})")
_ANCHOR_RE = re.compile(r"<a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>", re.S)
_LI_RE = re.compile(r"<li\b[^>]*>(.*?)</li>", re.S)
_NOISE_TITLES = ("网站声明", "网站使用指南", "网站管理", "联系我们", "无障碍",
                 "隐私政策", "站点地图", "关于我们", "免责声明", "友情链接", "更多")
_ATTACHMENT_RE = re.compile(r'<a[^>]+href="([^"]+\.(?:pdf|docx?|zip|txt))"[^>]*>', re.I)
_DOWNFILE_RE = re.compile(r'<a[^>]+href="([^"]*downfile\.jsp[^"]*)"[^>]*>', re.I)
_IMAGE_RE = re.compile(r'<img[^>]+src="([^"]+)"', re.I)

_CONTENT_BASE_PATTERNS = [
    r'(?is)<div[^>]*class=["\']text["\'][^>]*>(.*?)</div>',
    r'(?is)<div[^>]*id=["\']zoom["\'][^>]*>(.*?)</div>',
    r'(?is)<div[^>]*class=["\'][^"\']*TRS_Editor[^"\']*["\'][^>]*>(.*?)</div>',
]


def _content_patterns(extra_classes, extra_ids=()):
    pats = [(p, 20) for p in _CONTENT_BASE_PATTERNS]
    for cls in extra_classes:
        pats.append((
            r'(?is)<div[^>]*class=["\'][^"\']*{0}[^"\']*["\'][^>]*>(.*?)</div>'.format(re.escape(cls)),
            20,
        ))
    for cid in extra_ids:
        pats.append((
            r'(?is)<div[^>]*id=["\']{0}["\'][^>]*>(.*?)</div>'.format(re.escape(cid)),
            20,
        ))
    pats.append((
        r'(?is)<div[^>]*class=["\'][^"\']*article[^"\']*["\'][^>]*>(.*?)</div>',
        50,
    ))
    pats.append((
        r'(?is)<div[^>]*class=["\'][^"\']*content[^"\']*["\'][^>]*>(.*?)</div>',
        50,
    ))
    return pats


class BaseParser:
    name = "base"

    def parse_list(self, html, base_url="", keep_paths=None):
        raise NotImplementedError

    def parse_detail(self, html, url=""):
        raise NotImplementedError


class GovListParser(BaseParser):
    """政府列表页通用解析器：按 <li> 提取，目录前缀过滤 + 噪音标题排除。"""

    name = "gov"
    content_classes = ()
    content_ids = ()
    item_url_re = None
    default_base = ""

    def __init__(self):
        self._content_patterns = _content_patterns(self.content_classes, self.content_ids)

    def parse_list(self, html, base_url="", keep_paths=None):
        base_url = base_url or self.default_base
        items = []
        for li in _LI_RE.findall(html):
            m = _ANCHOR_RE.search(li)
            if not m:
                continue
            href = m.group(1).strip()
            title = clean_html_text(m.group(2))
            if len(title) < 4 or not re.search(r"\.s?html?$", href.lower(), re.I):
                continue
            if any(noise in title for noise in _NOISE_TITLES):
                continue
            url = urllib.parse.urljoin(base_url, href)
            if keep_paths:
                path = urllib.parse.urlparse(url).path
                if not any(path.startswith(p) for p in keep_paths):
                    continue
            if self.item_url_re and not self.item_url_re.search(url):
                continue
            items.append({"url": url, "title": title, "date": self._li_date(li, m.end())})
        return items

    def _li_date(self, li, anchor_end):
        """优先取条目锚点之后的合法日期；索引号之类（如 2026-02-00018）判非法跳过。"""
        matches = list(_DATE_RE.finditer(li))
        for dm in matches:
            if dm.start() >= anchor_end and self._valid_date(dm):
                return self._fmt_date(dm)
        for dm in matches:
            if self._valid_date(dm):
                return self._fmt_date(dm)
        return ""

    @staticmethod
    def _valid_date(dm):
        month, day = int(dm.group(2)), int(dm.group(3))
        return 1 <= month <= 12 and 1 <= day <= 31

    @staticmethod
    def _fmt_date(dm):
        return "{}-{:02d}-{:02d}".format(dm.group(1), int(dm.group(2)), int(dm.group(3)))

    def _extract_title(self, html):
        m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
        if m:
            title = clean_html_text(m.group(1))
            if title:
                return title
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S)
        return clean_html_text(m.group(1)) if m else ""

    def _extract_date(self, html):
        m = re.search(r"(?:发布时间|发布日期|时间)\s*[：:]\s*(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})", html)
        if m:
            return "{}-{:02d}-{:02d}".format(m.group(1), int(m.group(2)), int(m.group(3)))
        return ""

    def _extract_doc_number(self, html):
        return ""

    def _extract_authority(self, html):
        return ""

    def parse_detail(self, html, url=""):
        title = self._extract_title(html)
        publish_date = self._extract_date(html)
        content = self._extract(html)
        doc_number = extract_doc_number(content) or self._extract_doc_number(html)
        attachments = []
        seen_urls = set()
        for href in _ATTACHMENT_RE.findall(html) + _DOWNFILE_RE.findall(html):
            abs_url = urllib.parse.urljoin(url, _html.unescape(href))
            if abs_url not in seen_urls:
                seen_urls.add(abs_url)
                attachments.append({"url": abs_url})
        images = []
        seen_urls = set()
        for src in _IMAGE_RE.findall(html):
            abs_url = urllib.parse.urljoin(url, _html.unescape(src))
            if abs_url not in seen_urls:
                seen_urls.add(abs_url)
                images.append({"url": abs_url})
        return {
            "title": title,
            "doc_number": doc_number,
            "publish_date": publish_date,
            "implement_date": "",
            "content": content,
            "source_url": url,
            "raw_html": html,
            "issuing_authority": self._extract_authority(html),
            "images": images,
            "attachments": attachments,
        }

    def _extract(self, html):
        for pat, min_len in self._content_patterns:
            m = re.search(pat, html)
            if m:
                text = clean_html_text(m.group(1))
                if len(text) >= min_len:
                    return text
        return clean_html_text(html)


class NmpaParser(GovListParser):
    name = "nmpa"
    default_base = "https://www.nmpa.gov.cn"


class NhsaParser(GovListParser):
    name = "nhsa"
    item_url_re = re.compile(r"/art/[\d/]+art_\d+_\d+\.html")

    def _cms_field(self, html, field):
        """大汉版通 CMS 标记字段，如 <!--<$[标题]>begin-->...<!--<$[标题]>end-->。"""
        m = re.search(
            r"<!--<\$\[{}\]>begin-->(.*?)<!--<\$\[{}\]>end-->".format(field, field),
            html, re.S,
        )
        return clean_html_text(m.group(1)) if m else ""

    def _extract_title(self, html):
        return self._cms_field(html, "标题") or super()._extract_title(html)

    def _extract_date(self, html):
        m = re.search(r"发布日期[\s\S]{0,200}?(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})", html)
        if m:
            return "{}-{:02d}-{:02d}".format(m.group(1), int(m.group(2)), int(m.group(3)))
        return super()._extract_date(html)

    def _extract_doc_number(self, html):
        return self._cms_field(html, "引题")

    def _extract_authority(self, html):
        m = re.search(r"发布机构\s*[：:]\s*</span>\s*<span[^>]*>(.*?)</span>", html, re.S)
        return clean_html_text(m.group(1)) if m else ""

    def _extract(self, html):
        text = self._cms_field(html, "信息内容")
        if len(text) >= 10:
            return text
        return super()._extract(html)


class NhcParser(GovListParser):
    name = "nhc"
    content_ids = ("xw_box",)
    item_url_re = re.compile(r"/fzs/\w+/20\d{4}/\w+\.shtml")

    def _extract_title(self, html):
        m = re.search(r'<meta name="ArticleTitle" content="([^"]*)"', html)
        if m and m.group(1).strip():
            return m.group(1).strip()
        m = re.search(r'<div class="tit">(.*?)</div>', html, re.S)
        if m:
            title = clean_html_text(m.group(1))
            if title:
                return title
        return super()._extract_title(html)

    def _extract_authority(self, html):
        m = re.search(r"来源\s*[：:]\s*([^<\r\n]{1,60})", html)
        return m.group(1).strip() if m else ""


class GenericParser(BaseParser):
    """占位：适配新数据源时继承 GovListParser 并覆盖 content_classes。"""

    name = "generic"

    def __init__(self):
        self._inner = NmpaParser()

    def parse_list(self, html, base_url="", keep_paths=None):
        return self._inner.parse_list(html, base_url, keep_paths)

    def parse_detail(self, html, url=""):
        return self._inner.parse_detail(html, url)


PARSERS = {
    "nmpa": NmpaParser(),
    "nhsa": NhsaParser(),
    "nhc": NhcParser(),
    "generic": GenericParser(),
}
