"""Web UI:http.server 单文件,零依赖。"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import agent, llm, mock
from .db import Database

PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>信使 · 谁还在等我回邮件</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#1d2229;--dim:#6c7681;--accent:#38506b;--line:#e0e5ea}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.7 "Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:880px;margin:0 auto;padding:30px 18px 60px}
h1{font-size:25px;margin:0 0 4px}.sub{color:var(--dim);margin:0 0 14px}
.badge{display:inline-block;padding:2px 10px;border-radius:99px;font-size:13px;margin-left:6px}
.tabs{display:flex;gap:8px;margin:14px 0}
.tab{padding:8px 16px;border:1px solid var(--line);background:var(--card);border-radius:8px;cursor:pointer}
.tab.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;margin-bottom:14px}
label{display:block;font-size:14px;color:var(--dim);margin:10px 0 4px}
input,textarea,select{width:100%;padding:9px 11px;border:1px solid var(--line);border-radius:8px;font:inherit;background:#fff}
textarea{min-height:130px;resize:vertical}
button{padding:9px 18px;border:0;border-radius:8px;background:var(--accent);color:#fff;font:inherit;cursor:pointer}
button:disabled{opacity:.55;cursor:wait}
.out{white-space:pre-wrap;font:14px/1.8 Consolas,"Microsoft YaHei",monospace;background:#fbfcfd;border:1px solid var(--line);border-radius:8px;padding:14px;margin-top:12px;min-height:40px}
.row{display:flex;gap:10px}.row>*{flex:1}
.list div{padding:7px 0;border-bottom:1px dashed var(--line);font-size:14px;display:flex;gap:10px}

:root{--maxw:960px;--bg:#f3f1e8;--card:#fffef9;--ink:#1d2a3a;--text:#1d2a3a;--dim:#68707a;--line:#d4d1c2;--accent:#1f4d7a;--muted:#68707a}
.wrap{max-width:960px}
body{background:#f3f1e8;color:#1d2a3a;font-family:"Songti SC","SimSun",Georgia,serif}
h1{color:#1d2a3a}
header{max-width:960px;margin:0 auto}
input,textarea,select{background:#fff;color:#1d2a3a;border-color:#d4d1c2;border-radius:2px}
button:not(.ghost):not(.tab){background:#1f4d7a;color:#fff;border-radius:2px}
button.ghost{background:transparent!important;color:#1f4d7a!important;border:1px solid #d4d1c2!important}
h2,h3{color:#1f4d7a}
pre{background:#fafaf6;color:#1d2a3a;border-color:#d4d1c2}
.item,.card{border-color:#d4d1c2;background:#fffef9}
.k,.empty,.hint{color:#68707a}

h1{font-size:clamp(31px,5vw,39px);line-height:1.26}
.prod{display:block;font-size:11px;line-height:1.4;letter-spacing:.18em;font-weight:650;margin-bottom:8px;opacity:.72}
.lede,.sub{max-width:62ch;line-height:1.75}
.route{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;margin:16px auto 20px;border:1px solid var(--line);background:var(--line);max-width:var(--maxw)}
.route span{padding:11px 13px;background:var(--card);font-size:12px;line-height:1.5}
.route b{display:block;font-size:10px;letter-spacing:.1em;margin-bottom:3px;opacity:.66}
button{min-height:46px}
input,select{min-height:44px}
pre{white-space:pre-wrap}
@media(max-width:680px){
  .wrap{padding:20px 16px 56px}
  .route{grid-template-columns:1fr}
  h1{font-size:30px!important}
  .row>div{min-width:100%!important}
  button{width:100%}
}

body{background:#f3f1e8;color:#1d2a3a}
h1{font-size:38px;line-height:1.25;color:#1d2a3a}
.sub{color:#68707a;font-family:"PingFang SC","Microsoft YaHei",sans-serif;font-size:14px}
.tabs{margin:16px 0}
.tab{border:1px solid #d4d1c2;border-radius:0;background:#fffef9;color:#68707a;padding:9px 16px}
.tab.on{background:#1f4d7a;color:#fff;border-color:#1f4d7a}
.card{background:#fffef9;border:1px solid #d4d1c2;border-left:5px solid #1f4d7a;border-radius:0;box-shadow:none}
button{background:#1f4d7a;color:#fff;border-radius:0;letter-spacing:.04em}
button:hover{background:#193e63}
input,textarea,select{background:#fff;border-color:#d0cdbf;border-radius:0;color:#1d2a3a}
input:focus,textarea:focus,select:focus{border-color:#1f4d7a;box-shadow:0 0 0 2px #d8e2ec}
.out{background:#fff8d8;border-color:#e3d28d;color:#1d2a3a;border-radius:0}
.list{border-color:#d4d1c2}
h2{color:#1f4d7a}


/* mobile-32 */

@media(max-width:760px){
  main{grid-template-columns:1fr!important}
  aside{border-right:0!important;border-bottom:1px solid #d4d1c2;width:auto!important}
  section{padding:16px!important}
  .row{flex-wrap:wrap!important}
  .row>div{min-width:100%!important}
  h1{font-size:30px!important}
  .route{grid-template-columns:1fr!important}
  button{min-height:48px}
  pre{overflow-x:auto}
}

/* mobile-height */
@media(max-width:760px){main{min-height:auto!important}aside{min-height:0!important}}
</style></head><body><div class="wrap">
<h1><span class="prod">信使</span>谁还在等我回邮件 <span id="st" class="badge"></span></h1>
<p class="sub">给管合作邮件的人：导入选中的邮件线程，识别对方问了什么、我承诺了什么、谁在等谁，生成保留原事实的回复草稿。</p>
<div class="tabs"><div class="tab on" data-t="in">收件</div><div class="tab" data-t="out">回信</div></div>


  <div class="route" aria-label="任务步骤"><span><b>01</b>选邮件线程</span><span><b>02</b>找承诺与等待</span><span><b>03</b>起回复草稿</span></div>
<div class="card" id="p-in">
  <label>主题</label><input id="mSub">
  <label>发件人</label><input id="mFrom">
  <label>正文</label><textarea id="mBody"></textarea>
  <div style="margin-top:12px"><button id="btnIn">分类并摘要</button></div>
  <div class="out" id="inOut"></div>
  <div class="list" id="mails" style="margin-top:12px"></div>
</div>

<div class="card" id="p-out" style="display:none">
  <label>针对哪封</label><select id="rSel"></select>
  <label>语气</label><select id="rTone"><option value="formal">正式</option><option value="friendly">友好</option><option value="brief">简短</option></select>
  <div style="margin-top:12px"><button id="btnOut">起稿</button></div>
  <div class="out" id="outOut"></div>
</div>
</div>
<script>
const $=id=>document.getElementById(id);
const esc=s=>String(s==null?'':s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
function loading(btn,on){if(on){btn.dataset.label=btn.dataset.label||btn.textContent.trim();btn.disabled=true;btn.textContent='处理中…';}else{btn.disabled=false;btn.textContent=btn.dataset.label||btn.textContent;}}
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x===t));['in','out'].forEach(k=>$('p-'+k).style.display=k===t.dataset.t?'block':'none');});
async function api(path,body){const r=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const j=await r.json();if(!r.ok)throw new Error(j.error||('HTTP '+r.status));return j;}
async function loadMails(){const ms=await api('/api/mails');
 $('mails').innerHTML=ms.map(m=>`<div><span>[${m.id}]</span><span>${esc(m.subject)}</span><span>${esc(m.category||'未分类')}</span><span>P${m.priority}</span></div>`).join('')||'<div>还没有邮件</div>';
 $('rSel').innerHTML=ms.map(m=>`<option value="${m.id}">[${m.id}] ${esc(m.subject)}</option>`).join('');}
$('btnIn').onclick=async()=>{const btn=$('btnIn');loading(btn,true);
 try{const r=await api('/api/triage',{subject:$('mSub').value,sender:$('mFrom').value,body:$('mBody').value});
  let t=(r.offline?'【离线模式】':'')+`${r.category} / 优先级 ${r.priority}\\n${r.summary}\\n`;
  if(r.deadline)t+='截止:'+r.deadline+'\\n';
  (r.todos||[]).forEach((x,i)=>t+=`${i+1}. ${x}\\n`);
  (r.checks||[]).forEach(c=>t+='! '+c+'\\n');
  $('inOut').textContent=t;await loadMails();}
 catch(e){$('inOut').textContent='❌ '+e.message;}finally{loading(btn,false);}};
$('btnOut').onclick=async()=>{const btn=$('btnOut');loading(btn,true);
 try{const r=await api('/api/reply',{mail_id:+$('rSel').value,tone:$('rTone').value});
  $('outOut').textContent=(r.offline?'【离线模式】':'')+(r.checks||[]).join(' · ')+'\\n\\n'+r.body;}
 catch(e){$('outOut').textContent='❌ '+e.message;}finally{loading(btn,false);}};
(async()=>{try{const s=await api('/api/status');const b=$('st');b.textContent=s.mock?'离线模式':'模型模式';b.style.background=s.mock?'#fdecd6':'#dcefe3';b.style.color=s.mock?'#8a4a12':'#245c31';}catch(e){}
 await loadMails();})();
</script></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    db: Database
    cfg: dict
    force_mock: bool

    def log_message(self, fmt, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _read_json(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        raw = self.rfile.read(n)
        for enc in ("utf-8", "gbk"):
            try:
                return json.loads(raw.decode(enc))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
        return {}

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/api/status":
            cfg = {**llm.default_config(), **self.cfg}
            self._json({"mock": self.force_mock or not cfg.get("api_key"), "model": cfg.get("model")})
        elif path == "/api/mails":
            self._json(self.db.list_mails())
        elif path == "/api/mail":
            key = self.path.split("id=")[-1] if "id=" in self.path else "0"
            m = self.db.get_mail(key)
            self._json(m or {"error": "邮件不存在"}, 200 if m else 404)
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        data = self._read_json()
        if path == "/api/triage":
            body = str(data.get("body", "")).strip()
            if not body:
                self._json({"error": "正文不能为空"}, 400)
                return
            mid = self.db.add_mail(str(data.get("subject", "")), body, str(data.get("sender", "")))
            m = self.db.get_mail(mid)
            try:
                r = agent.triage(m, config=self.cfg, force_mock=self.force_mock)
            except Exception as e:  # noqa: BLE001
                self._json({"error": str(e)}, 502)
                return
            self.db.set_triage(mid, r["category"], r["priority"], r["summary"],
                               r.get("todos", []), r.get("deadline", ""))
            r["id"] = mid
            self._json(r)
            return
        if path == "/api/reply":
            m = self.db.get_mail(data.get("mail_id"))
            if not m:
                self._json({"error": "邮件不存在"}, 404)
                return
            tone = str(data.get("tone", "formal"))
            if tone not in mock.TONE_NAME:
                self._json({"error": "不认识的语气"}, 400)
                return
            try:
                r = agent.reply(m, tone, config=self.cfg, force_mock=self.force_mock)
            except Exception as e:  # noqa: BLE001
                self._json({"error": str(e)}, 502)
                return
            r["reply_id"] = self.db.add_reply(m["id"], tone, r["body"])
            self._json(r)
            return
        self._json({"error": "not found"}, 404)


def _make_handler(db: Database, cfg: dict, force_mock: bool):
    class Handler(_Handler):
        pass

    Handler.db, Handler.cfg, Handler.force_mock = db, cfg, force_mock
    return Handler


def serve(host: str = "127.0.0.1", port: int = 8000, db_path: str | None = None, force_mock: bool = False):
    db = Database(db_path or os.environ.get("XINSHI_DB"))
    httpd = ThreadingHTTPServer((host, port), _make_handler(db, llm.default_config(), force_mock))
    print(f"📬 信使已启动  http://{host}:{httpd.server_address[1]}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        db.close()


if __name__ == "__main__":
    serve()
