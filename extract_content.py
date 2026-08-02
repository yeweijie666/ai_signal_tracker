# -*- coding: utf-8 -*-
"""服务端正文提取（借鉴 Fluent Reader：在服务端抓取并提取，缓存后前端瞬时渲染）。

Fluent Reader 之所用起来快且稳，关键在于它的 RSS 拉取 + 正文提取都发生在
Electron 的 main 进程（相当于「服务端」），完全没有浏览器 CORS 限制，且结果本地缓存，
绝不每次点开都现抓。本模块就是这一思路在服务端 crawler 里的等价实现：

  1) 直接用 requests 抓取文章 HTML（服务端无 CORS 限制，比浏览器走代理稳得多）；
  2) 用 Python 版 Mozilla Readability（readability-lxml，Apache/MIT 同族算法，
     与 Fluent Reader 用的 Mercury Parser 思路一致）抽取正文；
  3) 清洗为标准纯文本返回（紧凑、安全，前端直接渲染）。

仅对「近期 + 有链接 + RSS 摘要偏短」的条目调用；已有较长正文的条目前端会直接按 text 渲染。
"""
import re
import html
import requests

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
SESSION = requests.Session()
SESSION.headers.update(UA)

_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_RE = re.compile(r"(?i)</(p|div|li|h[1-6]|br|tr|article)>")
_WS_RE = re.compile(r"[ \t]+")
_BLANK_RE = re.compile(r"\n{3,}")


def _html_to_text(h):
    """把抽取出的正文 HTML 转成干净的纯文本（保留段落换行）。"""
    h = _BLOCK_RE.sub("\n", h)
    h = _TAG_RE.sub("", h)
    h = html.unescape(h)
    h = _WS_RE.sub(" ", h)
    h = _BLANK_RE.sub("\n\n", h)
    return h.strip()


def extract(url, timeout=12):
    """抓取 url 并用 Readability 抽取正文，返回纯文本；任何失败返回 ''。"""
    if not url or not url.startswith(("http://", "https://")):
        return ""
    try:
        r = SESSION.get(url, timeout=timeout, allow_redirects=True)
        if r.status_code != 200:
            return ""
        ctype = r.headers.get("Content-Type", "").lower()
        if "html" not in ctype:
            return ""  # 非 HTML（图片/PDF/视频等）跳过
        r.encoding = r.apparent_encoding or "utf-8"
        raw = r.text
        if len(raw) < 500:
            return ""
        try:
            from readability.readability import Document
            summary = Document(raw).summary()  # 抽取后的正文 HTML
            text = _html_to_text(summary)
        except Exception:
            # Readability 未安装时退化为「去标签的全文」，保证至少有内容
            text = _html_to_text(raw)
        if len(text) < 200:
            return ""  # 太短视为抽取失败
        return text
    except Exception as ex:
        print(f"    [extract] 失败 {str(url)[:90]}: {ex}")
        return ""


if __name__ == "__main__":
    import sys
    for u in sys.argv[1:]:
        t = extract(u)
        print(f"\n=== {u} ===\n长度 {len(t)}\n{t[:500]}")
