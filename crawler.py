# -*- coding: utf-8 -*-
"""各信源抓取与归一化。返回统一结构的条目列表（不含 id/翻译，由 run.py 补全）。"""
import re, json, time, html, socket
import requests, feedparser
from config import (X_BEARER_TOKEN, X_HANDLES, INSTITUTION_FEEDS, PLATFORMS,
                    CN_FEEDS, NEWSLETTERS, KARPATHY_OPML, MAX_PER_SOURCE)
from translate import is_chinese

socket.setdefaulttimeout(12)  # 保护 feedparser（无内置超时），避免个别死源卡死

UA = {"User-Agent": "Mozilla/5.0 (compatible; AISignalTracker/1.0)"}
SESSION = requests.Session()
SESSION.headers.update(UA)

def _norm(source, category, sub, author, title, text, url, published, lang=None):
    lang = lang or ("zh" if is_chinese(title or text) else "en")
    return {
        "source": source, "category": category, "sub": sub or "",
        "author": author or "", "title": (title or "").strip(),
        "text": (text or "").strip(), "url": url or "",
        "published": published or "", "lang": lang,
    }

def _iso(dt):
    if not dt:
        return ""
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", dt)
    except Exception:
        return str(dt)

# ---------- arXiv ----------
def fetch_arxiv(url, name, cat):
    out = []
    try:
        d = feedparser.parse(url)
        for e in d.entries[:MAX_PER_SOURCE]:
            pub = e.get("published_parsed") or e.get("updated_parsed")
            out.append(_norm(name, cat, "", "", e.get("title", ""),
                             e.get("summary", ""), e.get("link", ""),
                             _iso(pub), "en"))
    except Exception as ex:
        print(f"  [arxiv] {name} 失败: {ex}")
    return out

# ---------- 通用 RSS ----------
def fetch_rss(url, name, cat, sub="", limit=None):
    out = []
    try:
        d = feedparser.parse(url)
        for e in d.entries[:limit or MAX_PER_SOURCE]:
            pub = e.get("published_parsed") or e.get("updated_parsed")
            body = e.get("summary", "") or e.get("description", "")
            body = re.sub("<[^>]+>", " ", body)
            out.append(_norm(name, cat, sub, "", e.get("title", ""),
                             body, e.get("link", ""), _iso(pub)))
    except Exception as ex:
        print(f"  [rss] {name} 失败: {ex}")
    return out

# ---------- Hacker News (Algolia) ----------
def fetch_hn(url, name, cat):
    out = []
    try:
        r = SESSION.get(url, timeout=15); r.raise_for_status()
        for h in r.json().get("hits", [])[:MAX_PER_SOURCE]:
            txt = h.get("story_text") or h.get("comment_text") or ""
            txt = re.sub("<[^>]+>", " ", txt)
            out.append(_norm(name, cat, "", h.get("author", ""),
                             h.get("title", ""), txt,
                             h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                             h.get("created_at", ""), "en"))
    except Exception as ex:
        print(f"  [hn] {name} 失败: {ex}")
    return out

# ---------- Reddit（.json 失败则退 RSS）----------
def fetch_reddit(url, name, cat):
    out = []
    try:
        r = SESSION.get(url, timeout=15, headers={"User-Agent": UA["User-Agent"]})
        r.raise_for_status()
        for c in r.json().get("data", {}).get("children", [])[:MAX_PER_SOURCE]:
            d = c["data"]
            out.append(_norm(name, cat, "", "u/" + d.get("author", ""),
                             d.get("title", ""), d.get("selftext", ""),
                             "https://www.reddit.com" + d.get("permalink", ""),
                             _iso(time.gmtime(d.get("created_utc", 0))), "en"))
    except Exception as ex:
        try:
            sub = re.search(r"reddit\.com/r/([^/]+)/", url).group(1)
            d = feedparser.parse(f"https://www.reddit.com/r/{sub}/hot.rss")
            for e in d.entries[:MAX_PER_SOURCE]:
                out.append(_norm(name, cat, "", "", e.get("title", ""),
                                 re.sub("<[^>]+>", " ", e.get("summary", "")),
                                 e.get("link", ""), _iso(e.get("published_parsed")), "en"))
        except Exception as ex2:
            print(f"  [reddit] {name} 失败: {ex} / {ex2}")
    return out

# ---------- GitHub Trending (scrape) ----------
def fetch_github(url, name, cat):
    out = []
    try:
        r = SESSION.get("https://github.com/trending?since=daily", timeout=15)
        r.raise_for_status()
        blocks = r.text.split('<article class="Box-row">')[1:]
        for b in blocks[:MAX_PER_SOURCE]:
            m = re.search(r'href="/([^"]+)"', b)
            if not m:
                continue
            repo = m.group(1)
            dm = re.search(r'<p class="col-9[^"]*">\s*(.*?)\s*</p>', b, re.S)
            desc = html.unescape(re.sub("<[^>]+>", "", dm.group(1))) if dm else ""
            out.append(_norm(name, cat, "", "", repo, desc,
                             "https://github.com/" + repo, _iso(time.gmtime()), "en"))
    except Exception as ex:
        print(f"  [github] {name} 失败: {ex}")
    return out

# ---------- X / Twitter (需 Bearer Token) ----------
def fetch_x():
    out = []
    if not X_BEARER_TOKEN:
        print("  [x] 未配置 X_BEARER_TOKEN，跳过（可手动补或填入 token 后启用）")
        return out
    try:
        hed = {"Authorization": f"Bearer {X_BEARER_TOKEN}"}
        for handle, tier in X_HANDLES:
            uname = handle.lstrip("@")
            r = SESSION.get(f"https://api.twitter.com/2/users/by/username/{uname}",
                            headers=hed, timeout=15)
            if r.status_code != 200:
                continue
            uid = r.json()["data"]["id"]
            t = SESSION.get(f"https://api.twitter.com/2/users/{uid}/tweets",
                            headers=hed,
                            params={"max_results": 10, "tweet.fields": "created_at,text"},
                            timeout=15)
            for tw in t.json().get("data", []):
                out.append(_norm("@" + uname, "X账号", tier, "@" + uname,
                                 "", tw.get("text", ""),
                                 f"https://x.com/{uname}/status/{tw['id']}",
                                 tw.get("created_at", ""), "en"))
            time.sleep(1)
    except Exception as ex:
        print(f"  [x] 失败: {ex}")
    return out

# ---------- Karpathy OPML 展开（t.co -> GitHub Gist -> raw OPML）----------
def expand_opml():
    feeds = []
    try:
        r = SESSION.get(KARPATHY_OPML, timeout=20, allow_redirects=True)
        r.raise_for_status()
        raw = r.text
        mg = re.search(r'gist\.github\.com/(?:[^/]+/)?([0-9a-f]+)', r.url)
        if mg:
            api = SESSION.get(f"https://api.github.com/gists/{mg.group(1)}", timeout=20).json()
            files = api.get("files", {})
            # 优先取 .opml 文件（gist 可能含 README 等多文件）
            opml_file = next((v for k, v in files.items() if k.endswith(".opml")), None)
            if not opml_file:
                opml_file = next((v for v in files.values() if v.get("raw_url")), None)
            if opml_file and opml_file.get("raw_url"):
                raw = SESSION.get(opml_file["raw_url"], timeout=20).text
        raw2 = raw.replace("&quot;", '"').replace("&amp;", "&")
        feeds = re.findall(r'xmlUrl="([^"]+)"', raw2)
        if not feeds:
            feeds = re.findall(r'&quot;(https?://[^&]+)&quot;', raw)
        feeds = [u for u in feeds if u.startswith("http")]
        print(f"  [opml] Karpathy 清单展开 {len(feeds)} 个 RSS")
    except Exception as ex:
        print(f"  [opml] 展开失败: {ex}")
    return feeds

# ---------- 总调度 ----------
def collect_all():
    items = []
    print("== 抓取机构报告 ==")
    for name, cat, sub, url, typ in INSTITUTION_FEEDS:
        if typ == "rss":
            items += fetch_rss(url, name, cat, sub)
    print("== 抓取硬核平台 ==")
    for name, cat, url, typ in PLATFORMS:
        if typ == "arxiv":
            items += fetch_arxiv(url, name, cat)
        elif typ == "rss":
            items += fetch_rss(url, name, cat)
        elif typ == "hn":
            items += fetch_hn(url, name, cat)
        elif typ == "reddit":
            items += fetch_reddit(url, name, cat)
        elif typ == "github":
            items += fetch_github(url, name, cat)
    print("== 抓取中文资讯 ==")
    for name, cat, url, typ in CN_FEEDS:
        items += fetch_rss(url, name, cat)
    print("== 抓取 Newsletter ==")
    for name, cat, url, typ in NEWSLETTERS:
        items += fetch_rss(url, name, cat)
    print("== 抓取 X ==")
    items += fetch_x()
    print("== 抓取 Karpathy RSS 清单 ==")
    for fx in expand_opml():
        items += fetch_rss(fx, "RSS·Karpathy", "RSS订阅", limit=8)
    print(f"== 共获取 {len(items)} 条 ==")
    return items

if __name__ == "__main__":
    collect_all()
