"""命令行入口:python -m xinshi <命令> [选项]。"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__, agent, llm, mock
from . import db as dbmod
from .llm import LLMError

MOCK_BANNER = (
    "⚠️  当前为离线模式(未配置 LLM_API_KEY),分类走关键词,回信只给骨架。\n"
    "   在 .env 填入 LLM_API_KEY 后,摘要与回信草稿交给大模型。\n"
)

_OPEN: list = []


def _db(args) -> dbmod.Database:
    db = dbmod.Database(getattr(args, "db", None))
    _OPEN.append(db)
    return db


def _close_all() -> None:
    for d in _OPEN:
        d.close()
    _OPEN.clear()


def _read_input(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as f:
        return f.read()


def render_triage(r: dict) -> str:
    head = f"📬 {r['category']}  ·  优先级 {r['priority']}"
    if r.get("offline"):
        head += "  ·  离线模式"
    lines = [head, "", r.get("summary", "")]
    if r.get("deadline"):
        lines.append(f"截止:{r['deadline']}")
    if r.get("todos"):
        lines += ["", "待办:"]
        for i, t in enumerate(r["todos"], 1):
            lines.append(f"  {i}. {t}")
    for c in r.get("checks", []):
        lines.append(f"! {c}")
    return "\n".join(lines)


def cmd_add(args):
    db = _db(args)
    body = _read_input(args.file)
    if not body.strip():
        print("❌ 邮件正文为空", file=sys.stderr)
        sys.exit(1)
    mid = db.add_mail(args.subject or "(无主题)", body, args.sender or "")
    print(f"✅ 已收 [{mid}] {args.subject or '(无主题)'}  {len(body)} 字")


def cmd_list(args):
    db = _db(args)
    ms = db.list_mails(args.limit)
    if args.json:
        print(json.dumps(ms, ensure_ascii=False, indent=2))
        return
    if not ms:
        print("(没有邮件)用 xinshi add 粘贴一封")
        return
    for m in ms:
        tag = m["category"] or "未分类"
        print(f"[{m['id']}] P{m['priority']} {tag:<4} {m['subject']}  {m['created_at']}")


def cmd_show(args):
    db = _db(args)
    m = db.get_mail(args.key)
    if not m:
        print(f"❌ 找不到邮件:{args.key}", file=sys.stderr)
        sys.exit(1)
    print(f"📬 [{m['id']}] {m['subject']}  来自 {m['sender'] or '未知'}")
    if m["category"]:
        print(f"{m['category']} / 优先级 {m['priority']} / 截止 {m['deadline'] or '未识别'}")
        print(m["summary"])
    print("\n" + m["body"][:500])


def cmd_triage(args):
    db = _db(args)
    m = db.get_mail(args.key)
    if not m:
        print(f"❌ 找不到邮件:{args.key}", file=sys.stderr)
        sys.exit(1)
    r = agent.triage(m, config=llm.config_from_args(args), force_mock=args.mock)
    db.set_triage(m["id"], r["category"], r["priority"], r["summary"], r.get("todos", []), r.get("deadline", ""))
    print(json.dumps(r, ensure_ascii=False, indent=2) if args.json else render_triage(r))
    if not args.json:
        print("\n✅ 已存进这封邮件")


def cmd_reply(args):
    db = _db(args)
    m = db.get_mail(args.key)
    if not m:
        print(f"❌ 找不到邮件:{args.key}", file=sys.stderr)
        sys.exit(1)
    r = agent.reply(m, args.tone, config=llm.config_from_args(args), force_mock=args.mock)
    rid = db.add_reply(m["id"], r["tone"], r["body"])
    if args.json:
        print(json.dumps({**r, "reply_id": rid}, ensure_ascii=False, indent=2))
        return
    print(f"✉️  {mock.TONE_NAME.get(r['tone'], r['tone'])}回信" + ("  ·  离线模式" if r.get("offline") else ""))
    for c in r.get("checks", []):
        print(f"  · {c}")
    if r.get("rejected"):
        print("  ! 校验没过,已退回骨架版")
    print("\n" + r["body"])
    print(f"\n（草稿 #{rid},发不出去——信使不接真实邮箱）")


def cmd_replies(args):
    db = _db(args)
    rs = db.list_replies(args.mail)
    for r in rs:
        print(f"[{r['id']}] mail {r['mail_id']}  {r['tone']}  {r['created_at']}")
        print(r["body"][:200] + "\n")


def cmd_rm(args):
    db = _db(args)
    m = db.get_mail(args.key)
    if not m:
        print(f"❌ 找不到邮件:{args.key}", file=sys.stderr)
        sys.exit(1)
    db.delete_mail(m["id"])
    print(f"🗑  已删除 [{m['id']}] {m['subject']}")


def cmd_stats(args):
    print(json.dumps(_db(args).stats(), ensure_ascii=False))


def cmd_web(args):
    from . import web

    web.serve(host=args.host, port=args.port, db_path=args.db, force_mock=args.mock)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="xinshi", description="信使 · 邮件助手:分类、摘要、待办、回信草稿。")
    p.add_argument("--version", action="version", version=f"xinshi {__version__}")
    p.add_argument("--mock", action="store_true", help="强制离线模式")
    p.add_argument("--json", action="store_true")
    p.add_argument("--model")
    p.add_argument("--base-url")
    p.add_argument("--api-key")
    p.add_argument("--db")

    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("add", help="粘贴一封邮件(文件或 - 读 stdin)")
    a.add_argument("file")
    a.add_argument("--subject")
    a.add_argument("--sender")
    a.set_defaults(func=cmd_add)

    ls = sub.add_parser("list", help="邮件列表")
    ls.add_argument("--limit", type=int, default=20)
    ls.set_defaults(func=cmd_list)

    sh = sub.add_parser("show", help="看一封邮件")
    sh.add_argument("key")
    sh.set_defaults(func=cmd_show)

    tr = sub.add_parser("triage", help="分类 + 摘要 + 待办")
    tr.add_argument("key")
    tr.set_defaults(func=cmd_triage)

    rp = sub.add_parser("reply", help="回信草稿")
    rp.add_argument("key")
    rp.add_argument("--tone", choices=list(mock.TONE_NAME), default="formal")
    rp.set_defaults(func=cmd_reply)

    rs = sub.add_parser("replies", help="回信草稿列表")
    rs.add_argument("--mail", type=int)
    rs.set_defaults(func=cmd_replies)

    rm = sub.add_parser("rm", help="删一封邮件")
    rm.add_argument("key")
    rm.set_defaults(func=cmd_rm)

    st = sub.add_parser("stats", help="统计")
    st.set_defaults(func=cmd_stats)

    wb = sub.add_parser("web", help="启动 Web 界面")
    wb.add_argument("--host", default="127.0.0.1")
    wb.add_argument("--port", type=int, default=8000)
    wb.set_defaults(func=cmd_web)
    return p


GLOBAL_FLAGS = ("--mock", "--json")
GLOBAL_OPTS = ("--model", "--base-url", "--api-key", "--db")


def hoist_globals(argv: list[str]) -> list[str]:
    g, rest = [], []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in GLOBAL_FLAGS:
            g.append(a)
            i += 1
        elif a in GLOBAL_OPTS:
            g += [a, argv[i + 1]] if i + 1 < len(argv) else [a]
            i += 2
        elif any(a.startswith(o + "=") for o in GLOBAL_OPTS):
            g.append(a)
            i += 1
        else:
            rest.append(a)
            i += 1
    return g + rest


def main(argv=None):
    args = build_parser().parse_args(hoist_globals(list(sys.argv[1:] if argv is None else argv)))
    if not args.mock and args.command in ("triage", "reply"):
        if not llm.config_from_args(args).get("api_key"):
            print(MOCK_BANNER, file=sys.stderr)
    try:
        args.func(args)
    except LLMError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
    finally:
        _close_all()


if __name__ == "__main__":
    main()
