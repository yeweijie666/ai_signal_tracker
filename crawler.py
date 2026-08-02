# -*- coding: utf-8 -*-
"""各信源抓取与归一化。返回统一结构的条目列表（不含 id/翻译，由 run.py 补全）。"""
import re, json, time, html, socket, os
import requests, feedparser
from config import (X_BEARER_TOKEN, X_HANDLES, INSTITUTION_FEEDS, PLATFORMS,
                    CN_FEEDS, NEWSLETTERS, KARPATHY_OPML, MAX_PER_SOURCE)
from translate import is_chinese

socket.setdefaulttimeout(12)  # 保护 feedparser（无内置超时），避免个别死源卡死

UA = {"User-Agent": "Mozilla/5.0 (compatible; AISignalTracker/1.0)"}
SESSION = requests.Session()
SESSION.headers.update(UA)

def _norm(source, category, sub, author, title, text, url, published, lang=None, content=""):
    lang = lang or ("zh" if is_chinese(title or text) else "en")
    return {
        "source": source, "category": category, "sub": sub or "",
        "author": author or "", "title": (title or "").strip(),
        "text": (text or "").strip(), "url": url or "",
        "published": published or "", "lang": lang,
        "content": (content or "").strip(),
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
def fetch_rss(url, name, cat, sub="", limit=None, use_feed_title=False):
    out = []
    try:
        d = feedparser.parse(url)
    except Exception as ex:
        print(f"  [rss] {name} 解析失败(源跳过): {ex}")
        return out
    # 每个订阅源用真实 feed 标题做源名（用于看板按订阅源分别展开）；
    # 仅在显式要求且能拿到标题时覆盖，避免把机构/平台的中文别名丢掉。
    src = name
    if use_feed_title and d.get("feed"):
        ft = (d.feed.get("title") or "").strip()
        if ft:
            src = ft
    for e in d.entries[:limit or MAX_PER_SOURCE]:
        # —— 关键修复：逐条独立容错 ——
        # 旧写法 try 包住整个函数，任一畸形条目抛异常会清空整条源（导致“丢源”）。
        # 现在 feed 解析与单条解析分离：单条失败只跳过该条，源始终保留。
        try:
            pub = e.get("published_parsed") or e.get("updated_parsed")
            # —— 参照 Fluent Reader 算法：优先使用 RSS 自带的 content:encoded 全文 ——
            # Fluent Reader 默认直接渲染 item.content（零二次抓取，所以快）；
            # 仅当源只给摘要时才回退到 summary/description（后续由 enrich 用 Readability 兜底抓原网页）。
            full = ""
            ce = e.get("content")
            if isinstance(ce, list) and ce:
                full = (ce[0].get("value") or "") if isinstance(ce[0], dict) else str(ce[0])
            elif isinstance(ce, str):
                full = ce
            if not full:
                full = e.get("summary", "") or e.get("description", "")
            # content：含 HTML 标签才视为正文 HTML（Fluent Reader 直接渲染 item.content）
            content = full if ("<" in full) else ""
            # text：用于列表预览 + 服务端翻译，保持“短”以免全文翻译拖垮工作流/触发限流；
            # 优先取摘要纯文本，无摘要才回退正文纯文本并截断到 300 字。
            summary = e.get("summary", "") or e.get("description", "")
            text = re.sub(r"<[^>]+>", " ", summary)
            text = re.sub(r"\s+", " ", text).strip()
            if not text and full:
                text = re.sub(r"<[^>]+>", " ", full)
                text = re.sub(r"\s+", " ", text).strip()
            if len(text) > 300:
                text = text[:300].strip() + "…"
            out.append(_norm(src, cat, sub, "", e.get("title", ""),
                             text, e.get("link", ""), _iso(pub), content=content))
        except Exception as ex:
            print(f"  [rss] {name} 单条解析跳过: {ex}")
            continue
    return out

# ---------- Hacker News (Algolia) ----------
def fetch_hn(url, name, cat):
    out = []
    try:
        r = SESSION.get(url, timeout=15); r.raise_for_status()
        for h in r.json().get("hits", [])[:MAX_PER_SOURCE]:
            raw = h.get("story_text") or h.get("comment_text") or ""
            # 参照 Fluent Reader：含 HTML 的正文保留为 content，纯文本则留空由 enrich 处理
            content = raw if ("<" in raw) else ""
            txt = re.sub(r"<[^>]+>", " ", raw)
            txt = re.sub(r"\s+", " ", txt).strip()
            out.append(_norm(name, cat, "", h.get("author", ""),
                             h.get("title", ""), txt,
                             h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                             h.get("created_at", ""), "en", content=content))
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
# 返回 [(title, url), ...]：直接从 <outline> 的 text/title 属性取源名，
# 不再对每个 feed 二次抓取标题（云端网络下大量超时，会导致源名退回占位符）。
# 关键修复：在线展开失败时回退本地缓存，避免整批 Karpathy 源在云端偶发网络抖动时丢失。
_OPML_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "opml_cache.json")

def _load_opml_cache():
    try:
        if os.path.exists(_OPML_CACHE):
            with open(_OPML_CACHE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []

def _save_opml_cache(feeds):
    try:
        with open(_OPML_CACHE, "w", encoding="utf-8") as f:
            json.dump(feeds, f, ensure_ascii=False)
    except Exception:
        pass

def _parse_opml(raw):
    """从 OPML 文本解析出 [(title, url), ...]，只取含 xmlUrl 的 <outline>。"""
    feeds = []
    raw = raw.replace("&quot;", '"').replace("&amp;", "&")
    for m in re.finditer(r'<outline\b([^>]*)/?>', raw):
        attr = m.group(1)
        xu = re.search(r'xmlUrl="([^"]+)"', attr)
        if not xu:
            continue
        ti = re.search(r'title="([^"]*)"', attr)
        tx = re.search(r'text="([^"]*)"', attr)
        title = (ti.group(1) if ti else (tx.group(1) if tx else "")).strip() or "RSS源"
        feeds.append((title, xu.group(1)))
    return feeds

def expand_opml():
    # 1) 在线抓取
    online = None
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
        online = _parse_opml(raw)
    except Exception as ex:
        print(f"  [opml] 在线展开失败: {ex}")
        online = None
    # 2) 结果决策：在线成功且非空 -> 缓存并返回；否则回退缓存
    if online is None:
        cached = _load_opml_cache()
        if cached:
            print(f"  [opml] 在线失败，使用本地缓存 {len(cached)} 个 RSS")
            return cached
        print(f"  [opml] 在线失败且无缓存，本批 Karpathy 源暂缺")
        return []
    if not online:
        cached = _load_opml_cache()
        if cached:
            print(f"  [opml] 在线解析为空，使用本地缓存 {len(cached)} 个 RSS")
            return cached
        return []
    # 在线成功：写入缓存；并做“部分失败”防护——在线结果明显少于缓存时优先用缓存
    _save_opml_cache(online)
    cached = _load_opml_cache()
    if 0 < len(online) < 15 and len(cached) > len(online):
        print(f"  [opml] 在线仅 {len(online)} 个（疑似部分失败），缓存有 {len(cached)} 个，采用缓存")
        return cached
    print(f"  [opml] Karpathy 清单展开 {len(online)} 个 RSS")
    return online

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
    for title, fx in expand_opml():
        items += fetch_rss(fx, title, "RSS订阅", sub="Karpathy清单", limit=8)
    print(f"== 共获取 {len(items)} 条 ==")
    return items

if __name__ == "__main__":
    collect_all()
