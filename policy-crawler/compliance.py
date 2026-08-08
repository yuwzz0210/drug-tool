# -*- coding: utf-8 -*-
"""robots.txt 合规检查：解析并按路径前缀判断是否允许抓取。"""
import logging
import urllib.parse
import urllib.request


log = logging.getLogger("policy-crawler.compliance")


def _default_fetch(url, ua="policy-crawler/1.0"):
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.status, resp.read().decode("utf-8", "replace")


class RobotsChecker:
    """按 host 缓存 robots.txt，提供 allowed(url) 判断。"""

    def __init__(self, fetcher=None, ua="policy-crawler/1.0"):
        self._fetcher = fetcher or _default_fetch
        self._ua = ua
        self._cache = {}  # host -> [(kind, prefix), ...]

    def _load_rules(self, host):
        if host in self._cache:
            return self._cache[host]
        rules = []
        url = "https://{}/robots.txt".format(host)
        try:
            _, body = self._fetcher(url, self._ua)
        except Exception as exc:  # 拿不到 robots 时按“允许”处理并告警留痕
            log.warning("robots.txt 获取失败 host=%s err=%s，默认放行", host, exc)
            self._cache[host] = rules
            return rules
        agent_section = None
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, value = line.partition(":")
            key, value = key.strip().lower(), value.strip()
            if key == "user-agent":
                if value == "*" or value.lower() == self._ua.split("/")[0].lower():
                    agent_section = True
                elif agent_section is True:
                    agent_section = False
            elif key in ("allow", "disallow") and agent_section is not False:
                rules.append(("allow" if key == "allow" else "disallow", value or "/"))
        self._cache[host] = rules
        return rules

    def allowed(self, url):
        """最后一条匹配路径前缀的规则决定结果（标准 robots 语义）。"""
        parsed = urllib.parse.urlparse(url)
        path = parsed.path or "/"
        rules = self._load_rules(parsed.netloc)
        allowed_flag = True
        for kind, prefix in rules:
            if path.startswith(prefix):
                allowed_flag = kind == "allow"
        return allowed_flag
