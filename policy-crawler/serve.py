# -*- coding: utf-8 -*-
"""零依赖 REST API（标准库 http.server），端点为规格书 7 章接口。"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from queries import (
    get_policy,
    health_summary,
    list_policies,
    list_scenarios,
    scenario_policies,
    stats_latest,
)

VIEWER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "policy-viewer.html")


class PolicyHandler(BaseHTTPRequestHandler):
    store = None

    @staticmethod
    def _cors_headers():
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        }

    @staticmethod
    def _int_param(qs, key, default, lo, hi):
        try:
            value = int(qs.get(key, [str(default)])[0])
        except (TypeError, ValueError):
            value = default
        return max(lo, min(hi, value))

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for key, value in self._cors_headers().items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Content-Length", "0")
        for key, value in self._cors_headers().items():
            self.send_header(key, value)
        self.end_headers()

    def _serve_viewer(self):
        try:
            with open(VIEWER_PATH, encoding="utf-8") as f:
                body = f.read().encode("utf-8")
        except OSError:
            self._json({"error": "viewer file missing"}, 500)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for key, value in self._cors_headers().items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)
        try:
            if path in ("", "/policy-viewer.html", "/index.html"):
                self._serve_viewer()
            elif path == "/api/policies":
                self._json(list_policies(
                    self.store,
                    page=self._int_param(qs, "page", 1, 1, 10 ** 6),
                    size=self._int_param(qs, "size", 20, 1, 100),
                    keyword=qs.get("keyword", [""])[0],
                    authority=qs.get("authority", [""])[0],
                    tag=qs.get("tag", [""])[0],
                    status=qs.get("status", [""])[0],
                    date_from=qs.get("date_from", [""])[0],
                    date_to=qs.get("date_to", [""])[0],
                ))
            elif path.startswith("/api/policies/"):
                row = get_policy(self.store, path.split("/")[-1])
                self._json(row if row else {"error": "not found"}, 200 if row else 404)
            elif path == "/api/scenarios":
                self._json({"items": list_scenarios()})
            elif path.startswith("/api/scenarios/"):
                parts = path.split("/")
                sid = parts[-2] if parts[-1] == "policies" else parts[-1]
                self._json({"scenario_id": sid, "items": scenario_policies(self.store, sid)})
            elif path == "/api/stats/latest":
                self._json(stats_latest(self.store))
            elif path == "/api/health":
                self._json(health_summary(self.store))
            else:
                self._json({"error": "not found"}, 404)
        except Exception as exc:
            self._json({"error": str(exc)}, 500)

    def log_message(self, fmt, *args):
        pass


def serve(store, host="127.0.0.1", port=8000):
    PolicyHandler.store = store
    return ThreadingHTTPServer((host, port), PolicyHandler)
