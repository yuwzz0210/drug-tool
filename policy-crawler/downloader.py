# -*- coding: utf-8 -*-
"""下载器：UA 轮换、合规延迟、重试、403 暂停信号、请求留痕、可选代理池。"""
import logging
import random
import ssl
import time
import urllib.request

from config import REQUEST_DELAY_MAX, REQUEST_DELAY_MIN, RETRY_TIMES, USER_AGENTS


log = logging.getLogger("policy-crawler.downloader")


class PauseSignal(Exception):
    """遇到 403/验证码等反爬信号，任务应立即暂停并告警。"""


_SSL_HINTS = ("ssl", "handshake", "cipher", "tls", "certificate", "security level")


def _is_ssl_error(exc):
    """判断异常是否与 TLS 握手/密码套件相关（用于兼容降级重试）。"""
    text = "{} {}".format(type(exc).__name__, exc).lower()
    return any(hint in text for hint in _SSL_HINTS)


def _default_fetcher(url, ua, context=None):
    """带浏览器请求头的默认抓取器；context 为空时使用 urllib 默认 TLS 配置。"""
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "close",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30, context=context) as resp:
        return resp.status, resp.read().decode("utf-8", "replace")


def _relaxed_fetcher(url, ua):
    """TLS 兼容降级：允许旧政务站常用的低安全级别密码套件（OpenSSL 3 SECLEVEL=1）。"""
    ctx = ssl.create_default_context()
    try:
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    except ssl.SSLError:
        pass
    return _default_fetcher(url, ua, context=ctx)


class Downloader:
    def __init__(self, ua_list=None, delay_range=None, retries=None,
                 fetcher=None, on_request=None, proxy_pool=None):
        self._uas = ua_list or USER_AGENTS
        self._delay = delay_range or (REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
        self._retries = RETRY_TIMES if retries is None else retries
        self._fetcher = fetcher or _default_fetcher
        self._on_request = on_request
        self._pool = proxy_pool
        self._ua_index = 0

    def _next_ua(self):
        ua = self._uas[self._ua_index % len(self._uas)]
        self._ua_index += 1
        return ua

    def _polite_sleep(self):
        if self._delay[0] > 0 or self._delay[1] > 0:
            time.sleep(random.uniform(self._delay[0], self._delay[1]))

    def _proxied_fetch(self, url, ua, proxy):
        handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        opener = urllib.request.build_opener(handler)
        req = urllib.request.Request(url, headers={"User-Agent": ua})
        with opener.open(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")

    def fetch(self, url):
        last_error = None
        relaxed_attempted = False
        for attempt in range(self._retries + 1):
            ua = self._next_ua()
            self._polite_sleep()
            proxy = self._pool.next() if self._pool else None
            start = time.time()
            try:
                if proxy:
                    status, body = self._proxied_fetch(url, ua, proxy)
                else:
                    status, body = self._fetcher(url, ua)
            except Exception as exc:
                if proxy and self._pool:
                    self._pool.mark_bad(proxy)
                elapsed = time.time() - start
                log.warning("请求失败 url=%s attempt=%s err=%s elapsed=%.2fs", url, attempt + 1, exc, elapsed)
                self._notify(url, 0, elapsed)
                last_error = exc
                if not proxy and not relaxed_attempted and _is_ssl_error(exc):
                    relaxed_attempted = True
                    start = time.time()
                    try:
                        status, body = _relaxed_fetcher(url, ua)
                    except Exception as exc2:
                        log.warning("TLS 兼容降级失败 url=%s err=%s", url, exc2)
                        last_error = exc2
                        continue
                    elapsed = time.time() - start
                    log.info("TLS 兼容降级成功 url=%s status=%s elapsed=%.2fs", url, status, elapsed)
                    self._notify(url, status, elapsed)
                    return status, body
                continue
            elapsed = time.time() - start
            if proxy and self._pool:
                self._pool.mark_ok(proxy)
            log.info("REQ url=%s status=%s elapsed=%.2fs ua=%s", url, status, elapsed, ua[:30])
            self._notify(url, status, elapsed)
            if status == 403:
                raise PauseSignal("HTTP 403 触发反爬，暂停任务并告警: {}".format(url))
            return status, body
        raise last_error or RuntimeError("请求失败: {}".format(url))

    def _notify(self, url, status, elapsed):
        if self._on_request:
            self._on_request(url, status, elapsed)
