"""编排:模型分类与回信 + 本地硬校验 + 离线回退。

分类可以是模型给,但必须落在四类里;待办必须是原文的句子。
回信里凭空冒出原文没有的日期,一律判不过——写错截止日期比不写更糟。
"""

from __future__ import annotations

from . import llm, mock, tools

MAX_STEPS = 12

TRIAGE_SYSTEM = """你在给一封邮件做归类。只依据邮件内容。

输出 JSON:
{"category":"重要|待办|通知|垃圾","priority":0到3的整数,"summary":"80 字以内的摘要","todos":["需要你做的事,用原文里的句子"],"deadline":"邮件里出现的截止时间,没有就空字符串"}

规则:
- category 只能是这四个词之一。
- priority:3 最急(有明确截止或"尽快"),0 是垃圾邮件。
- todos 最多 5 条,每条必须是原文里的原句,不许改写、不许合并。
- summary 写清"谁要你做什么",不要复述客套话。
- 不要替用户判断邮件真假,只说内容。"""

REPLY_SYSTEM = """你在替用户起草一封回信。语气:__TONE__。

输出 JSON:
{"body":"回信正文","notes":"一句话说明你的取舍"}

规则:
- 不要替用户答应具体条件,拿不准的地方写成"[待确认]"。
- 不要出现邮件里没有的日期、金额、人名。
- 中文用全角标点;称呼与落款留空由用户补。
- brief 不超过 60 字,formal 不超过 200 字。"""


def _use_model(config: dict | None, force_mock: bool) -> bool:
    if force_mock:
        return False
    return bool({**llm.default_config(), **(config or {})}.get("api_key"))


def _cfg(config: dict | None) -> dict:
    return {**llm.default_config(), **(config or {})}


def _chat(messages, config, max_tokens=1000) -> str:
    return llm.chat(messages, config=_cfg(config), temperature=0.3, max_tokens=max_tokens)


def verify_triage(mail: dict, data: dict) -> tuple[dict, list[str]]:
    problems = []
    category = str(data.get("category", "")).strip()
    if category not in tools.CATEGORIES:
        problems.append(f"分类「{category}」不在四类里,已按关键词改判")
        category = tools.classify(mail.get("subject", ""), mail.get("body", ""))["category"]
    try:
        priority = int(data.get("priority", 1))
    except (TypeError, ValueError):
        priority = 1
        problems.append("priority 不是整数")
    priority = max(0, min(3, priority))

    kept = []
    for t in data.get("todos", [])[:5]:
        s = str(t).strip()
        if tools.contains_quote(mail.get("body", ""), s):
            kept.append(s)
        else:
            problems.append(f"待办在原文里查不到:{s[:20]}")
    summary = str(data.get("summary", "")).strip()
    fresh = tools.new_numbers(mail.get("body", ""), summary)
    if fresh:
        problems.append("摘要里多了原文没有的数字:" + "、".join(fresh[:3]))
    deadline = str(data.get("deadline", "")).strip()
    dates = tools.find_dates(mail.get("body", ""))
    if deadline and not any(d in deadline or deadline in d for d in dates):
        problems.append(f"截止时间「{deadline}」在原文里找不到")
        deadline = ""
    return {"category": category, "priority": priority, "summary": summary,
            "todos": kept, "deadline": deadline, "problems": problems, "offline": False}, problems


def triage(mail: dict, config: dict | None = None, force_mock: bool = False) -> dict:
    if not _use_model(config, force_mock):
        return mock.triage(mail)
    raw = _chat([
        {"role": "system", "content": TRIAGE_SYSTEM},
        {"role": "user", "content": f"发件人:{mail.get('sender', '')}\n主题:{mail['subject']}\n正文:\n{mail['body']}"},
    ], config)
    data = llm.extract_json(raw)
    result, _ = verify_triage(mail, data)
    result["checks"] = result.pop("problems") or ["硬校验通过:分类合法、待办可回查、摘要无新数字"]
    return result


def reply(mail: dict, tone: str, config: dict | None = None, force_mock: bool = False) -> dict:
    if not _use_model(config, force_mock):
        return mock.reply(mail, tone)
    system = REPLY_SYSTEM.replace("__TONE__", mock.TONE_NAME.get(tone, tone))
    raw = _chat([
        {"role": "system", "content": system},
        {"role": "user", "content": f"原邮件({mail.get('sender', '')}):{mail['subject']}\n{mail['body']}"},
    ], config, max_tokens=800)
    data = llm.extract_json(raw)
    body = str(data.get("body", "")).strip()
    problems = []
    fresh = tools.new_numbers(mail.get("body", ""), body)
    if fresh:
        problems.append("回信里多了原邮件没有的数字:" + "、".join(fresh[:3]))
    limit = 60 if tone == "brief" else 200 if tone == "formal" else 240
    if len(body) > limit:
        problems.append(f"长度 {len(body)} 超出 {limit} 字上限")
    if not body:
        problems.append("回信为空")
    return {"tone": tone, "body": body if not problems else mock.reply(mail, tone)["body"],
            "notes": data.get("notes", ""),
            "checks": problems or ["硬校验通过:没有新数字、长度合适"],
            "rejected": bool(problems), "offline": False}
