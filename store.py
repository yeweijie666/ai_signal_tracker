# -*- coding: utf-8 -*-
"""SQLite 存储：去重、按时间索引、缓存翻译；导出 JSON 供看板使用。"""
import os, sqlite3, hashlib, json, time
from config import LOOKBACK_DAYS

DB = os.path.join(os.path.dirname(__file__), "signals.db")
EXPORT = os.path.join(os.path.dirname(__file__), "signals.json")

def _hid(it):
    # 以 url 为主键：同一篇文章每次重抓 id 稳定，可原地更新(含 source 改名)，
    # 不再因 title/published 格式化差异生成新行而累积重复。
    url = (it.get("url") or "").strip()
    if url:
        return hashlib.md5(("u:" + url).encode("utf-8")).hexdigest()
    # 无 url 时退化为 标题+时间
    base = (it.get("title") or "")[:120] + "|" + (it.get("published") or "")
    return hashlib.md5(("t:" + base).encode("utf-8")).hexdigest()

def conn():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS items(
        id TEXT PRIMARY KEY, source TEXT, category TEXT, sub TEXT, author TEXT,
        title TEXT, text TEXT, url TEXT, published TEXT, lang TEXT,
        zh_title TEXT, zh_text TEXT, fetched_at TEXT, content TEXT)""")
    # 旧库兼容：补充 content 列（服务端预提取的正文 HTML）
    try:
        c.execute("ALTER TABLE items ADD COLUMN content TEXT")
    except Exception:
        pass
    return c

def upsert(items, translate_fn):
    c = conn(); n_new = 0; n_upd = 0
    cutoff = time.time() - LOOKBACK_DAYS * 86400
    for it in items:
        iid = _hid(it)
        cur = c.execute("SELECT id FROM items WHERE id=?", (iid,)).fetchone()
        zh_title = it.get("zh_title") or ""
        zh_text = it.get("zh_text") or ""
        # 仅对“近期英文条目”翻译，避免对历史归档浪费翻译额度
        recent = True
        pub = it.get("published", "")
        if pub:
            try:
                ts = time.mktime(time.strptime(pub, "%Y-%m-%dT%H:%M:%SZ"))
                recent = ts >= cutoff
            except Exception:
                recent = True
        if it.get("lang") == "en" and not zh_title and recent:
            try:
                zh_title = translate_fn(it.get("title", "")) or ""
                zh_text = translate_fn(it.get("text", "")) or ""
            except Exception:
                pass
        row = (iid, it.get("source", ""), it.get("category", ""), it.get("sub", ""),
               it.get("author", ""), it.get("title", ""), it.get("text", ""),
               it.get("url", ""), it.get("published", ""), it.get("lang", ""),
               zh_title, zh_text, time.strftime("%Y-%m-%dT%H:%M:%SZ"))
        if cur:
            c.execute("""UPDATE items SET source=?,category=?,sub=?,author=?,title=?,
                text=?,url=?,published=?,lang=?,zh_title=?,zh_text=?,fetched_at=? WHERE id=?""",
                row[1:] + (iid,))
            n_upd += 1
        else:
            c.execute("""INSERT INTO items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", row + (None,))
            n_new += 1
    c.commit(); c.close()
    print(f"  入库：新增 {n_new}，更新 {n_upd}")
    return n_new, n_upd

def export_json():
    c = conn()
    cutoff = time.time() - LOOKBACK_DAYS * 86400
    rows = c.execute("""SELECT source,category,sub,author,title,text,url,published,lang,zh_title,zh_text,content
                        FROM items ORDER BY published DESC""").fetchall()
    c.close()
    out = []
    for r in rows:
        pub = r[7]
        try:
            ts = time.mktime(time.strptime(pub, "%Y-%m-%dT%H:%M:%SZ")) if pub else 0
        except Exception:
            ts = 0
        if ts and ts < cutoff:
            continue
        out.append(dict(zip(
            ["source","category","sub","author","title","text","url","published","lang","zh_title","zh_text","content"], r)))
    with open(EXPORT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"  导出 {len(out)} 条 -> signals.json")
    return len(out)


def _esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def enrich_content(max_workers=10):
    """为文章预提取正文（含图 HTML）写入 content 列，供看板秒开、免逐篇走代理。

    - 已有 content（含 '<'）的跳过，保留历史缓存；
    - 长摘要(text 清洗后 >=200 字) 直接包成段落当 content，免联网；
    - 其余有链接且近期的，并发联网抓取并用 readability 抽正文（含图）。
    失败/被墙/无正文的条目 content 留空，看板自动回退代理或本地摘要。
    """
    try:
        from extract_content import extract
    except Exception:
        print("  [enrich] 未找到 extract_content，跳过正文预提取")
        return 0
    import concurrent.futures as cf
    c = conn()
    rows = c.execute("SELECT id,url,text,published,content FROM items").fetchall()
    cutoff = time.time() - LOOKBACK_DAYS * 86400
    updates = {}
    to_fetch = []
    for iid, url, text, pub, content in rows:
        if content and "<" in content:
            continue  # 已缓存 HTML，保留
        if text and len(text.strip()) >= 200:
            updates[iid] = "<p>" + _esc(text.strip()) + "</p>"
            continue
        ts = 0
        if pub:
            try:
                ts = time.mktime(time.strptime(pub, "%Y-%m-%dT%H:%M:%SZ"))
            except Exception:
                ts = 0
        if url and (ts == 0 or ts >= cutoff):
            to_fetch.append((iid, url))

    def do(iu):
        iid, url = iu
        try:
            return iid, extract(url)
        except Exception:
            return iid, ""

    fetched = {}
    if to_fetch:
        with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
            for iid, html in ex.map(do, to_fetch):
                if html:
                    fetched[iid] = html
    updates.update(fetched)
    if updates:
        c.executemany("UPDATE items SET content=? WHERE id=?",
                      [(v, k) for k, v in updates.items()])
        c.commit()
    c.close()
    print(f"  预提取正文：更新 {len(updates)} 条（联网抓取 {len(fetched)} 条，长摘要转内容 {len(updates) - len(fetched)} 条）")
    return len(updates)
