"""离线模式:关键词分类 + 句式抽待办 + 回信骨架。

回信这件事,规则引擎写不出真话——它不知道你要答应还是拒绝。
所以离线回信只给骨架(确认收到 / 结论 / 下一步 / 时间),不假装是成稿。
"""

from __future__ import annotations

from . import tools

TONE_NAME = {"formal": "正式", "friendly": "友好", "brief": "简短"}


def triage(mail: dict) -> dict:
    subject, body = mail.get("subject", ""), mail.get("body", "")
    c = tools.classify(subject, body)
    p = tools.priority(subject, body, c["category"])
    todos = tools.extract_todos(body)
    dates = tools.find_dates(body)
    return {
        "category": c["category"],
        "priority": p,
        "summary": tools.summary(subject, body),
        "todos": todos,
        "deadline": dates[0] if dates else "",
        "scores": c["scores"],
        "offline": True,
        "checks": ["离线模式:分类与待办由关键词规则给出"],
    }


def reply(mail: dict, tone: str) -> dict:
    subj = mail.get("subject", "")
    todos = tools.extract_todos(mail.get("body", ""))
    who = mail.get("sender", "") or "对方"
    label = TONE_NAME.get(tone, tone)
    lines = [f"【离线模式:{label}骨架,内容需要你自己填】", ""]
    if tone == "brief":
        lines += ["收到,我这边确认一下,今天内回你结论。", ""]
    else:
        lines += [f"{who},", "", f"收到你关于「{subj}」的邮件。", ""]
    lines.append("要点:")
    if todos:
        for i, t in enumerate(todos, 1):
            lines.append(f"  {i}. {t}")
    else:
        lines.append("  1. (这封邮件里没有待办句,你自己补一句结论)")
    lines += ["", "下一步:", "  - 需要我做什么:", "  - 什么时候给你答复:", "", "——"]
    return {"tone": tone, "body": "\n".join(lines), "offline": True,
            "checks": ["离线模式:只给回信骨架,没有替你表态"]}
