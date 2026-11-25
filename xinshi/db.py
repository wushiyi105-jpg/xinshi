"""信使的持久层:邮件文本 + 分类结果 + 回信草稿。

刻意不接真实邮箱:粘贴进来的是文本,存在本机,发不出去也删得掉。
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "xinshi.db")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


class Database:
    def __init__(self, path: str | None = None):
        self.path = path or os.environ.get("XINSHI_DB") or DEFAULT_PATH
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS mails (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject TEXT NOT NULL,
                    sender TEXT DEFAULT '',
                    body TEXT NOT NULL,
                    category TEXT DEFAULT '',
                    priority INTEGER DEFAULT 0,
                    summary TEXT DEFAULT '',
                    todos TEXT DEFAULT '[]',
                    deadline TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS replies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mail_id INTEGER NOT NULL,
                    tone TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (mail_id) REFERENCES mails(id) ON DELETE CASCADE
                );
                """
            )
            self._conn.commit()

    def add_mail(self, subject: str, body: str, sender: str = "") -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO mails(subject, sender, body, created_at) VALUES(?,?,?,?)",
                (subject.strip() or "(无主题)", sender.strip(), body.strip(), _now()),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def _row(self, row) -> dict:
        d = dict(row)
        try:
            d["todos"] = json.loads(d.get("todos") or "[]")
        except json.JSONDecodeError:
            d["todos"] = []
        return d

    def get_mail(self, key: str | int):
        with self._lock:
            if str(key).isdigit() and len(str(key)) <= 6:
                row = self._conn.execute("SELECT * FROM mails WHERE id=?", (int(key),)).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT * FROM mails WHERE subject LIKE ? ORDER BY id DESC LIMIT 1", (f"%{key}%",)
                ).fetchone()
            return self._row(row) if row else None

    def list_mails(self, limit: int = 20) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, subject, sender, category, priority, summary, deadline, created_at, "
                "length(body) AS chars FROM mails ORDER BY priority DESC, id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def set_triage(self, mail_id: int, category: str, priority: int, summary: str,
                   todos: list[str], deadline: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE mails SET category=?, priority=?, summary=?, todos=?, deadline=? WHERE id=?",
                (category, priority, summary, json.dumps(todos, ensure_ascii=False), deadline, mail_id),
            )
            self._conn.commit()

    def add_reply(self, mail_id: int, tone: str, body: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO replies(mail_id, tone, body, created_at) VALUES(?,?,?,?)",
                (mail_id, tone, body, _now()),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def list_replies(self, mail_id: int | None = None) -> list[dict]:
        with self._lock:
            if mail_id:
                rows = self._conn.execute(
                    "SELECT * FROM replies WHERE mail_id=? ORDER BY id DESC", (mail_id,)
                ).fetchall()
            else:
                rows = self._conn.execute("SELECT * FROM replies ORDER BY id DESC LIMIT 20").fetchall()
            return [dict(r) for r in rows]

    def delete_mail(self, mail_id: int) -> bool:
        with self._lock:
            self._conn.execute("DELETE FROM replies WHERE mail_id=?", (mail_id,))
            cur = self._conn.execute("DELETE FROM mails WHERE id=?", (mail_id,))
            self._conn.commit()
            return cur.rowcount > 0

    def stats(self) -> dict:
        with self._lock:
            m = self._conn.execute("SELECT COUNT(*) c FROM mails").fetchone()
            t = self._conn.execute("SELECT COUNT(*) c FROM mails WHERE category<>''").fetchone()
            r = self._conn.execute("SELECT COUNT(*) c FROM replies").fetchone()
            return {"mails": m["c"], "triaged": t["c"], "replies": r["c"]}

    def close(self) -> None:
        with self._lock:
            self._conn.close()
