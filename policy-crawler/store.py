# -*- coding: utf-8 -*-
"""存储抽象：SqliteStore（默认零依赖）/ PostgresStore（可选 psycopg2）。"""
import json
import sqlite3

from models import SQLITE_SCHEMA


class Store:
    def exists(self, source_url):
        raise NotImplementedError

    def upsert_policy(self, policy):
        raise NotImplementedError

    def get_by_url(self, source_url):
        raise NotImplementedError

    def get_by_id(self, policy_id):
        raise NotImplementedError

    def query_policies(self, filters=None):
        raise NotImplementedError

    def added_since(self, days):
        raise NotImplementedError

    def log_run(self, **kwargs):
        raise NotImplementedError

    def list_logs(self):
        raise NotImplementedError


class SqliteStore(Store):
    def __init__(self, db_path=":memory:"):
        # 本地 API 服务在多个线程中复用连接（每次操作用事务，写入量小）
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SQLITE_SCHEMA)
        self._conn.commit()

    def close(self):
        self._conn.close()

    def exists(self, source_url):
        cur = self._conn.execute("SELECT 1 FROM policies WHERE source_url=?", (source_url,))
        return cur.fetchone() is not None

    def upsert_policy(self, policy):
        if self.exists(policy.source_url):
            self._conn.execute(
                """UPDATE policies SET title=?, doc_number=?, issuing_authority=?,
                   publish_date=?, implement_date=?, validity_status=?, content=?,
                   raw_html=?, attachment_links=?, tags=?, updated_at=datetime('now','localtime')
                   WHERE source_url=?""",
                (policy.title, policy.doc_number, policy.issuing_authority,
                 policy.publish_date, policy.implement_date, policy.validity_status,
                 policy.content, policy.raw_html, policy.attachment_links, policy.tags,
                 policy.source_url),
            )
            self._conn.commit()
            return False
        self._conn.execute(
            """INSERT INTO policies (title, doc_number, issuing_authority, publish_date,
               implement_date, validity_status, source_url, content, raw_html,
               attachment_links, tags)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (policy.title, policy.doc_number, policy.issuing_authority,
             policy.publish_date, policy.implement_date, policy.validity_status,
             policy.source_url, policy.content, policy.raw_html,
             policy.attachment_links, policy.tags),
        )
        self._conn.commit()
        return True

    def get_by_url(self, source_url):
        cur = self._conn.execute("SELECT * FROM policies WHERE source_url=?", (source_url,))
        row = cur.fetchone()
        return dict(row) if row else None

    def get_by_id(self, policy_id):
        cur = self._conn.execute("SELECT * FROM policies WHERE id=?", (policy_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def query_policies(self, filters=None):
        filters = filters or {}
        sql = "SELECT * FROM policies WHERE 1=1"
        args = []
        kw = (filters.get("keyword") or "").strip()
        if kw:
            sql += " AND (title LIKE ? OR content LIKE ? OR doc_number LIKE ?)"
            like = "%" + kw + "%"
            args += [like, like, like]
        au = (filters.get("authority") or "").strip()
        if au:
            sql += " AND issuing_authority LIKE ?"
            args.append("%" + au + "%")
        tag = (filters.get("tag") or "").strip()
        if tag:
            sql += " AND tags LIKE ?"
            args.append("%" + tag + "%")
        st = (filters.get("status") or "").strip()
        if st:
            sql += " AND validity_status=?"
            args.append(st)
        df = (filters.get("date_from") or "").strip()
        if df:
            sql += " AND publish_date>=?"
            args.append(df)
        dt = (filters.get("date_to") or "").strip()
        if dt:
            sql += " AND publish_date<=?"
            args.append(dt)
        sql += " ORDER BY publish_date DESC, id DESC"
        cur = self._conn.execute(sql, args)
        return [dict(r) for r in cur.fetchall()]

    def added_since(self, days):
        import datetime

        if days <= 0:
            today = datetime.date.today().isoformat()
            cur = self._conn.execute(
                "SELECT COUNT(*) FROM policies WHERE date(created_at)=?", (today,)
            )
        else:
            since = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
            cur = self._conn.execute(
                "SELECT COUNT(*) FROM policies WHERE date(created_at)>=?", (since,)
            )
        return cur.fetchone()[0]

    def log_run(self, task_name, start_time, end_time, total_fetched,
                new_added, error_count, error_details="", status="SUCCESS"):
        self._conn.execute(
            """INSERT INTO crawler_logs (task_name, start_time, end_time, total_fetched,
               new_added, error_count, error_details, status)
               VALUES (?,?,?,?,?,?,?,?)""",
            (task_name, start_time, end_time, total_fetched, new_added,
             error_count, error_details, status),
        )
        self._conn.commit()

    def list_logs(self, limit=20):
        cur = self._conn.execute(
            "SELECT * FROM crawler_logs ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [dict(r) for r in cur.fetchall()]


class PostgresStore(Store):
    """对齐规格书 PostgreSQL；需安装 psycopg2-binary 并设置 DB_URL。"""

    def __init__(self, db_url):
        import psycopg2  # 延迟导入，未安装时仅在显式选择时失败
        from models import POSTGRES_DDL

        self._conn = psycopg2.connect(db_url)
        self._conn.autocommit = True
        cur = self._conn.cursor()
        cur.execute(POSTGRES_DDL)
        cur.close()

    def exists(self, source_url):
        cur = self._conn.cursor()
        cur.execute("SELECT 1 FROM policies WHERE source_url=%s", (source_url,))
        exists = cur.fetchone() is not None
        cur.close()
        return exists

    def upsert_policy(self, policy):
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO policies (title, doc_number, issuing_authority, publish_date,
                implement_date, validity_status, source_url, content, raw_html,
                attachment_links, tags, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, NOW())
            ON CONFLICT (source_url) DO UPDATE SET
                title=EXCLUDED.title, content=EXCLUDED.content, updated_at=NOW()
            RETURNING (xmax = 0) AS inserted
            """,
            (policy.title, policy.doc_number, policy.issuing_authority,
             policy.publish_date or None, policy.implement_date or None,
             policy.validity_status, policy.source_url, policy.content,
             policy.raw_html, json.dumps(policy.attachment_links),
             json.dumps(policy.tags)),
        )
        row = cur.fetchone()
        inserted = bool(row and row[0])
        cur.close()
        return inserted

    def get_by_url(self, source_url):
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM policies WHERE source_url=%s", (source_url,))
        row = cur.fetchone()
        cur.close()
        return dict(row) if row else None

    def log_run(self, **kwargs):
        cur = self._conn.cursor()
        cur.execute(
            """INSERT INTO crawler_logs (task_name, start_time, end_time, total_fetched,
               new_added, error_count, error_details, status)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (kwargs.get("task_name"), kwargs.get("start_time"), kwargs.get("end_time"),
             kwargs.get("total_fetched", 0), kwargs.get("new_added", 0),
             kwargs.get("error_count", 0), kwargs.get("error_details", ""),
             kwargs.get("status", "SUCCESS")),
        )
        cur.close()

    def list_logs(self, limit=20):
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM crawler_logs ORDER BY id DESC LIMIT %s", (limit,))
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.close()
        return rows
