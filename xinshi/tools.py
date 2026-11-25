"""纯函数层:邮件分类、优先级、待办抽取、日期识别。

分类与优先级用关键词表算,待办用句式抽——这三件事都不该让模型自由发挥,
因为它们在邮件里是有固定信号词的。
"""

from __future__ import annotations

import re

CATEGORIES = ("重要", "待办", "通知", "垃圾")

_IMPORTANT = ("合同", "发票", "报销", "面试", "录取", "报价", "签字", "法务", "逾期", "违约", "工资", "领导")
_TODO = ("请", "麻烦", "需要你", "需要您", "尽快", "务必", "回复", "确认", "提交", "请于", "截至", "截止")
_NOTICE = ("通知", "公告", "发布会", "活动", "会议邀请", "提醒", "更新", "上线", "系统维护")
_SPAM = ("中奖", "优惠券", "秒杀", "退订", "推广", "免费领取", "限时", "点击链接", "赚", "贷款")

_DATE = re.compile(r"(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}\s*月\s*\d{1,2}\s*[日号]|本周[一二三四五六日天]|下周[一二三四五六日天]|今天|明天|后天)")
_NUM = re.compile(r"\d+(?:\.\d+)?")


def split_sentences(text: str) -> list[str]:
    out, buf = [], ""
    for ch in text or "":
        buf += ch
        if ch in "。！？；!?;\n":
            if buf.strip():
                out.append(buf.strip())
            buf = ""
    if buf.strip():
        out.append(buf.strip())
    return out


def normalize(text: str) -> str:
    return re.sub(r"[\s\u3000，。、；：！？,.;:!?\"“”‘’（）()【】\[\]—…·]", "", text or "")


def contains_quote(source: str, quote: str) -> bool:
    q = normalize(quote)
    if len(q) < 6:
        return False
    return q in normalize(source)


def hit_score(text: str, words: tuple[str, ...]) -> int:
    return sum(1 for w in words if w in (text or ""))


def classify(subject: str, body: str) -> dict:
    """四类判定按优先级走:垃圾信号强先判垃圾,再看待办,再看重要。

    「待办」优先于「重要」是刻意的:一封既要你签字又要你回复的邮件,
    真正该做的是回复,标记成"重要"只会让它在收件箱里躺着。
    """
    text = f"{subject}\n{body}"
    scores = {
        "重要": hit_score(text, _IMPORTANT),
        "待办": hit_score(text, _TODO),
        "通知": hit_score(text, _NOTICE),
        "垃圾": hit_score(text, _SPAM),
    }
    if scores["垃圾"] >= 2 or (scores["垃圾"] >= 1 and scores["待办"] == 0 and scores["重要"] == 0):
        category = "垃圾"
    elif scores["待办"] >= 1:
        category = "待办"
    elif scores["重要"] >= 1:
        category = "重要"
    elif scores["通知"] >= 1:
        category = "通知"
    else:
        category = "通知" if len(text) < 200 else "待办"
    return {"category": category, "scores": scores}


def priority(subject: str, body: str, category: str) -> int:
    """优先级 0~3:有截止/紧急词最高,垃圾最低。"""
    text = f"{subject}\n{body}"
    if category == "垃圾":
        return 0
    p = 1
    if any(w in text for w in ("尽快", "务必", "紧急", "今天", "明天", "逾期", "截止", "截至")):
        p += 1
    if find_dates(text):
        p += 1
    if category == "重要":
        p += 1
    return min(3, p)


def find_dates(text: str) -> list[str]:
    return [d.strip() for d in _DATE.findall(text or "")]


def extract_todos(text: str) -> list[str]:
    """待办句:带请求/截止信号的句子,原样保留。"""
    out = []
    for s in split_sentences(text):
        if any(w in s for w in _TODO) or _DATE.search(s):
            if len(s) <= 120:
                out.append(s)
    return out[:5]


def summary(subject: str, body: str) -> str:
    """离线摘要:主题 + 第一句原句截断,不做概括性改写(改写要靠模型)。"""
    sents = split_sentences(body)
    head = sents[0] if sents else ""
    if len(head) > 60:
        head = head[:60] + "…"
    return f"{subject or '(无主题)'}:{head}"


def numbers(text: str) -> list[str]:
    return _NUM.findall(text or "")


def new_numbers(before: str, after: str) -> list[str]:
    old = set(numbers(before))
    return [n for n in numbers(after) if n not in old]


TOOLS = [
    {"name": "get_mail", "desc": "取回邮件全文。", "args": {}},
    {"name": "find_dates", "desc": "列出邮件里出现的日期表达。", "args": {}},
]


def tool_list_text() -> str:
    return "\n".join(f"- {t['name']}({', '.join(t['args']) or '无'}):{t['desc']}" for t in TOOLS)


def execute(name: str, args: dict, mail: dict) -> dict:
    if name == "get_mail":
        return {"subject": mail["subject"], "sender": mail.get("sender", ""), "body": mail["body"]}
    if name == "find_dates":
        return {"dates": find_dates(mail["body"])}
    return {"error": f"未知工具: {name}"}


def dump(obj) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False)
