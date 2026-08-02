# -*- coding: utf-8 -*-
"""服务端全文提取：抓取文章原始 HTML，用 readability-lxml 抽正文，
保留并修正图片地址，返回含图 HTML；失败或正文过短返回空串。

仅服务端（GitHub Actions / 本地爬虫）使用，无 CORS 限制；
结果缓存进 SQLite 的 content 列，看板直接渲染，免逐篇走浏览器代理。
"""
import re
from urllib.parse import urljoin
import requests

try:
    from readability import Document
    _HAVE_RD = True
except Exception:
    _HAVE_RD = False

UA = {"User-Agent": "Mozilla/5.0 (compatible; AISignalTracker/1.0)"}
_TIMEOUT = 15


def _sanitize(s):
    """去掉可能执行脚本/样式的标签与属性，保留正文与图片。"""
    if not s:
        return ""
    s = re.sub(r"<script[\s\S]*?</script>", "", s, flags=re.I)
    s = re.sub(r"<style[\s\S]*?</style>", "", s, flags=re.I)
    s = re.sub(r"<iframe[\s\S]*?</iframe>", "", s, flags=re.I)
    s = re.sub(r"<noscript[\s\S]*?</noscript>", "", s, flags=re.I)
    s = re.sub(r'\son\w+\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)', "", s, flags=re.I)
    s = re.sub(r"javascript:", "", s, flags=re.I)
    return s


def _fix_imgs(html, base):
    """相对图片地址转绝对（src / srcset），避免看板里图片裂图。"""
    if not html:
        return ""

    def repl(m):
        tag = m.group(0)
        # 图片懒加载：data-src -> src（很多站点用 data-src 延迟加载，否则图片裂）
        ms = re.search(r'src\s*=\s*"([^"]*)"', tag, re.I)
        mds = re.search(r'data-src\s*=\s*"([^"]*)"', tag, re.I)
        if (not ms or not ms.group(1).strip()) and mds:
            tag = tag[:mds.start()] + 'src="%s"' % mds.group(1) + tag[mds.end():]
        for attr in ("src", "srcset"):
            mm = re.search(attr + r'\s*=\s*"([^"]*)"', tag, re.I)
            if not mm:
                continue
            val = mm.group(1)
            if attr == "srcset":
                val = val.split(",")[0].split(" ")[0]
            if val and not val.startswith(("http://", "https://", "data:")):
                val = urljoin(base, val)
            tag = tag[:mm.start()] + '%s="%s"' % (attr, val) + tag[mm.end():]
        return tag

    return re.sub(r"<img\b[^>]*>", repl, html, flags=re.I)


def _clean(summary):
    """readability 偶尔返回完整 <html> 文档，收敛到 <body> 内内容。"""
    m = re.search(r"<body[^>]*>([\s\S]*?)</body>", summary, re.I)
    if m:
        return m.group(1)
    return summary


def _text_len(s):
    return len(re.sub("<[^>]+>", "", s or ""))


def extract(url):
    """返回含图正文 HTML；失败 / 正文过短返回空串。"""
    if not url or not _HAVE_RD:
        return ""
    raw = ""
    for _ in range(2):  # 允许一次瞬时重试
        try:
            r = requests.get(url, headers=UA, timeout=_TIMEOUT, allow_redirects=True)
            if r.status_code < 400:
                raw = r.text
            break
        except Exception:
            raw = ""
    if not raw:
        return ""
    try:
        doc = Document(raw)
        summary = doc.summary()
    except Exception:
        return ""
    summary = _clean(summary)
    if _text_len(summary) < 120:  # 太短（追踪像素 / 登录墙 / 无正文）视为无效
        return ""
    summary = _fix_imgs(summary, url)
    return _sanitize(summary)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(extract(sys.argv[1])[:500])
