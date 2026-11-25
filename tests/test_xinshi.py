"""信使离线单测:不联网、不花 token。"""

from __future__ import annotations

import io
import json
import os
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen

from xinshi import agent, cli, mock, tools, web
from xinshi.db import Database

SAMPLE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "mails-sample.json")


def load_sample() -> list[dict]:
    with open(SAMPLE, encoding="utf-8") as f:
        return json.load(f)


class BaseCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Database(os.path.join(self.tmp.name, "t.db"))
        self.ids = [self.db.add_mail(m["subject"], m["body"], m["sender"]) for m in load_sample()]

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()


class TestRules(unittest.TestCase):
    def test_classify_spam(self):
        c = tools.classify("限时秒杀", "点击链接免费领取,退订请回复 TD")
        self.assertEqual(c["category"], "垃圾")

    def test_classify_todo(self):
        c = tools.classify("报销材料", "请于 11 月 28 日前补齐并回复确认")
        self.assertEqual(c["category"], "待办")

    def test_priority_higher_with_deadline(self):
        p1 = tools.priority("通知", "系统维护,请谅解", "通知")
        p2 = tools.priority("报销", "请于 11 月 28 日前补齐", "待办")
        self.assertGreater(p2, p1)

    def test_extract_todos_keeps_sentence(self):
        todos = tools.extract_todos("请于 11 月 28 日前补齐发票。补齐后回复我确认。")
        self.assertTrue(todos)
        self.assertIn("11 月 28 日", todos[0])

    def test_find_dates(self):
        self.assertIn("11 月 28 日", tools.find_dates("请于 11 月 28 日前补齐"))

    def test_new_numbers(self):
        self.assertEqual(tools.new_numbers("11 月 28 日", "11 月 28 日,另需 500 元"), ["500"])


class TestDb(BaseCase):
    def test_triage_store(self):
        m = self.db.get_mail(self.ids[0])
        self.db.set_triage(m["id"], "待办", 3, "缺发票", ["请于 11 月 28 日前补齐"], "11 月 28 日")
        got = self.db.get_mail(self.ids[0])
        self.assertEqual(got["category"], "待办")
        self.assertEqual(got["todos"][0][:5], "请于 11")

    def test_list_orders_by_priority(self):
        self.db.set_triage(self.ids[2], "待办", 3, "面试", [], "12 月 2 日")
        self.assertEqual(self.db.list_mails()[0]["id"], self.ids[2])

    def test_reply_and_delete(self):
        self.db.add_reply(self.ids[0], "formal", "收到")
        self.assertTrue(self.db.delete_mail(self.ids[0]))
        self.assertEqual(self.db.list_replies(), [])

    def test_stats(self):
        self.assertEqual(self.db.stats()["mails"], 4)


class TestOffline(BaseCase):
    def test_mock_triage_offline(self):
        r = mock.triage(self.db.get_mail(self.ids[0]))
        self.assertTrue(r["offline"])
        self.assertIn(r["category"], tools.CATEGORIES)
        self.assertTrue(r["todos"])

    def test_mock_reply_is_skeleton(self):
        r = mock.reply(self.db.get_mail(self.ids[0]), "brief")
        self.assertIn("骨架", r["body"])

    def test_verify_drops_fake_todo(self):
        m = self.db.get_mail(self.ids[0])
        result, problems = agent.verify_triage(m, {
            "category": "待办", "priority": 3, "summary": "缺发票",
            "todos": ["请于 11 月 28 日前补齐", "原文没有这句待办"],
            "deadline": "11 月 28 日",
        })
        self.assertEqual(len(result["todos"]), 1)
        self.assertTrue(any("查不到" in p for p in problems))

    def test_verify_bad_category_falls_back(self):
        m = self.db.get_mail(self.ids[3])
        result, problems = agent.verify_triage(m, {"category": "广告", "priority": 2, "summary": "秒杀"})
        self.assertIn(result["category"], tools.CATEGORIES)
        self.assertTrue(problems)


class TestCli(BaseCase):
    def _run(self, argv, db_path):
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(["--db", db_path] + argv)
        return buf.getvalue()

    def test_add_triage_reply(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        db_path = os.path.join(tmp.name, "c.db")
        f = os.path.join(tmp.name, "m.txt")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(load_sample()[0]["body"])
        self.assertIn("已收", self._run(["add", f, "--subject", "报销材料"], db_path))
        out = self._run(["--mock", "triage", "1"], db_path)
        self.assertIn("离线模式", out)
        self.assertIn("待办", out)
        self.assertIn("骨架", self._run(["--mock", "reply", "1", "--tone", "brief"], db_path))
        tmp.cleanup()


class TestWeb(BaseCase):
    def test_api_triage_and_reply(self):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), web._make_handler(self.db, {"api_key": ""}, True))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        port = httpd.server_address[1]
        try:
            body = json.dumps({"subject": "报销", "body": "请于 11 月 28 日前补齐发票"}).encode("utf-8")
            req = Request(f"http://127.0.0.1:{port}/api/triage", data=body,
                          headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(req, timeout=15) as resp:
                r = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(r["offline"])
            self.assertEqual(r["category"], "待办")
            body2 = json.dumps({"mail_id": r["id"], "tone": "brief"}).encode("utf-8")
            req2 = Request(f"http://127.0.0.1:{port}/api/reply", data=body2,
                           headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(req2, timeout=15) as resp:
                self.assertIn("骨架", json.loads(resp.read().decode("utf-8"))["body"])
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
