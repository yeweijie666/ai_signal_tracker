# -*- coding: utf-8 -*-
"""
读取 signals.json，生成每日摘要邮件并通过 SMTP(SSL) 发送。
环境变量（在 GitHub Secrets / 本地环境变量中配置）：
  SMTP_HOST    默认 smtp.qq.com
  SMTP_PORT    默认 465
  QQ_EMAIL     发件人（也是你的 QQ 邮箱），如 270665534@qq.com
  QQ_AUTH_CODE QQ 邮箱“授权码”（非登录密码），在 QQ 邮箱设置→账户→开启SMTP 后生成
  TO_ADDR      收件人，默认与 QQ_EMAIL 相同（发给自己）
signals.json 路径可用 SIGNAL_FILE 覆盖。
"""
import os, json, smtplib, ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from collections import Counter

SIGNAL_FILE = os.environ.get("SIGNAL_FILE", "signals.json")
HOST = os.environ.get("SMTP_HOST", "smtp.qq.com")
PORT = int(os.environ.get("SMTP_PORT", "465"))
USER = os.environ.get("QQ_EMAIL", "")
PASS = os.environ.get("QQ_AUTH_CODE", "")
TO = os.environ.get("TO_ADDR", USER or "270665534@qq.com")

BJ = timezone(timedelta(hours=8))
DASHBOARD = "https://yeweijie666.github.io/ai_signal_tracker/dashboard.html"


def load_items():
    if not os.path.exists(SIGNAL_FILE):
        return []
    with open(SIGNAL_FILE, encoding="utf-8") as f:
        return json.load(f)


def to_bj(s):
    try:
        dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return dt.astimezone(BJ)
    except Exception:
        return None


def build_html(items):
    now = datetime.now(BJ)
    today = now.strftime("%Y-%m-%d")
    # 近 24 小时优先；不足则取最新 20 条
    recent = [x for x in items if (to_bj(x.get("published", "")) is not None
              and (now - to_bj(x["published"])) <= timedelta(hours=24))]
    if len(recent) < 5:
        recent = sorted(items, key=lambda x: x.get("published", ""), reverse=True)[:20]
    recent.sort(key=lambda x: x.get("published", ""), reverse=True)

    en = [x for x in items if x.get("lang") == "en"]
    tr = [x for x in en if x.get("zh_title")]
    cat = Counter(x.get("category", "") for x in items)

    rows = []
    for x in recent:
        b = to_bj(x.get("published", ""))
        bt = b.strftime("%m-%d %H:%M") if b else ""
        src = x.get("source", "")
        cate = x.get("category", "")
        title = (x.get("title") or "").strip()
        zh = (x.get("zh_title") or "").strip()
        url = x.get("url") or "#"
        block = f'''
        <div style="margin:10px 0;padding:8px 10px;border-left:3px solid #4a90d9;background:#f7f9fc;">
          <div style="color:#888;font-size:12px;margin-bottom:3px;">{bt} · {src} · {cate}</div>
          <div style="font-size:14px;"><a href="{url}" style="color:#1a5fb4;text-decoration:none;">{title}</a></div>'''
        if zh and zh != title:
            block += f'\n          <div style="color:#333;font-size:13px;margin-top:2px;">🇨🇳 {zh}</div>'
        block += "\n        </div>"
        rows.append(block)
    rows_html = "\n".join(rows) if rows else '<p style="color:#888;">近 24 小时暂无新条目。</p>'

    cat_html = " · ".join(f"{k} {v}" for k, v in cat.most_common())
    return f'''
    <div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:680px;margin:0 auto;color:#222;">
      <h2 style="margin:0 0 4px;">🤖 AI 硬核信源日报 · {today}</h2>
      <p style="color:#666;margin:0 0 12px;">累计 {len(items)} 条（英文 {len(en)}，已译 {len(tr)}）｜ 分类：{cat_html}</p>
      <p style="margin:0 0 14px;">👉 <a href="{DASHBOARD}" style="color:#1a5fb4;">打开完整时间线看板</a></p>
      <hr style="border:none;border-top:1px solid #e5e5e5;margin:12px 0;">
      {rows_html}
      <hr style="border:none;border-top:1px solid #e5e5e5;margin:16px 0;">
      <p style="color:#999;font-size:12px;">由 GitHub Actions 自动生成 · 数据来源：arXiv/HN/HF/GitHub/Reddit/RSS(Karpathy 92源)/Newsletter/中文站</p>
    </div>'''


def send(subject, html):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = USER
    msg["To"] = TO
    msg.attach(MIMEText(html, "html", "utf-8"))
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(HOST, PORT, context=ctx) as s:
        s.login(USER, PASS)
        s.send_message(msg)
    print(f"已发送邮件 -> {TO}")


def main():
    if not USER or not PASS:
        print("[skip] 未配置 QQ_EMAIL / QQ_AUTH_CODE，跳过发信（不影响爬取与提交）")
        return
    items = load_items()
    if not items:
        print("[skip] signals.json 为空，跳过发信")
        return
    now = datetime.now(BJ)
    subject = f"AI 信源日报 {now.strftime('%Y-%m-%d')}"
    send(subject, build_html(items))
    print("邮件发送完成")


if __name__ == "__main__":
    main()
