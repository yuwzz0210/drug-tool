# -*- coding: utf-8 -*-
"""代理 IP 池（P3 防封禁）：轮换使用、失败下线、成功恢复评分。

代理列表来源优先级：构造参数 > 文件（每行一个，支持 # 注释）> 环境变量 PROXY_LIST。
格式示例：http://user:pass@1.2.3.4:8080
"""
import os


DEFAULT_HEALTH = 5


class ProxyPool:
    def __init__(self, proxies=None, filepath=None, env_var="PROXY_LIST"):
        self._proxies = []
        self._health = {}
        self._index = 0
        if proxies:
            self._add_many(proxies)
        env_value = os.environ.get(env_var, "").strip()
        if env_value:
            self._add_many(env_value.replace(",", "\n").splitlines())
        if filepath:
            self.load(filepath)

    def _add_many(self, items):
        for item in items:
            item = (item or "").strip()
            if item.startswith("#"):
                continue
            if item and item not in self._health:
                self._proxies.append(item)
                self._health[item] = DEFAULT_HEALTH

    def load(self, filepath):
        """从文件加载代理，每行一个，'#' 开头为注释。"""
        with open(filepath, encoding="utf-8") as f:
            lines = [ln for ln in f.read().splitlines() if ln.strip()]
            self._add_many(lines)

    def next(self):
        """轮询返回下一个可用代理；全部下线或为空时返回 None。"""
        if not self._proxies:
            return None
        for _ in range(len(self._proxies)):
            proxy = self._proxies[self._index % len(self._proxies)]
            self._index += 1
            if self._health.get(proxy, 0) > 0:
                return proxy
        return None

    def mark_bad(self, proxy):
        """请求失败：下线该代理。"""
        if proxy in self._health:
            self._health[proxy] = 0

    def mark_ok(self, proxy):
        """请求成功：恢复健康评分（上限 DEFAULT_HEALTH）。"""
        if proxy in self._health and self._health[proxy] < DEFAULT_HEALTH:
            self._health[proxy] += 1

    def alive(self):
        """当前可用代理列表。"""
        return [p for p in self._proxies if self._health.get(p, 0) > 0]

    def __len__(self):
        return len(self._proxies)
