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
    # 兼容旧库：缺少 content 列时补上
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
        # 读取已缓存的正文，更新时务必保留（不覆盖服务端提取结果）
        cur = c.execute("SELECT content FROM items WHERE id=?", (iid,)).fetchone()
        existing_content = cur[0] if cur else None
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
                text=?,url=?,published=?,lang=?,zh_title=?,zh_text=?,fetched_at=?, content=?
                WHERE id=?""",
                row[1:] + (existing_content, iid))
            n_upd += 1
        else:
            c.execute("""INSERT INTO items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", row + (None,))
            n_new += 1
    c.commit(); c.close()
    print(f"  入库：新增 {n_new}，更新 {n_upd}")
    return n_new, n_upd


def enrich_content(max_workers=10, min_text=200):
    """服务端补全文（借鉴 Fluent Reader：在服务端抓取+提取并缓存）。

    仅对「近期 + 有链接 + RSS 摘要偏短」的条目联网抓取全文；已有较长正文的条目
    直接把 text 记为 content（前端会按 text 渲染，无需代理）。提取结果写回 content
    列并随 JSON 导出。并发抓取 + 每请求超时，控制总耗时；失败留空（次日重试）。
    """
    try:
        from extract_content import extract
    except Exception as ex:
        print(f"  [enrich] 未安装提取依赖，跳过：{ex}")
        return
    import concurrent.futures as cf
    c = conn()
    cutoff = time.time() - LOOKBACK_DAYS * 86400
    rows = c.execute("SELECT id,url,text,published FROM items").fetchall()
    c.close()
    todo, upd_long = [], []
    for iid, url, text, pub in rows:
        recent = True
        if pub:
            try:
                ts = time.mktime(time.strptime(pub, "%Y-%m-%dT%H:%M:%SZ"))
                recent = ts >= cutoff
            except Exception:
                recent = True
        if not recent or not url:
            continue
        if text and len(text) >= min_text:
            upd_long.append((text, iid))   # 已有长正文，直接采用，避免反复入选
        else:
            todo.append((iid, url))        # 短摘要，需联网提取
    if upd_long:
        c2 = conn()
        c2.executemany("UPDATE items SET content=? WHERE id=?", upd_long)
        c2.commit(); c2.close()
        print(f"  [enrich] 长正文直接采用 {len(upd_long)} 条")
    if todo:
        print(f"  [enrich] 联网提取全文 {len(todo)} 条（并发 {max_workers}）…")
        results = []
        with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
            fut = {ex.submit(extract, u): iid for iid, u in todo}
            for f in cf.as_completed(fut):
                iid = fut[f]
                try:
                    txt = f.result() or ""
                except Exception:
                    txt = ""
                if txt:
                    results.append((txt, iid))
        if results:
            c3 = conn()
            c3.executemany("UPDATE items SET content=? WHERE id=?", results)
            c3.commit(); c3.close()
        print(f"  [enrich] 全文提取完成，成功 {len(results)}/{len(todo)}")

def export_json():
    c = conn()
    cutoff = time.time() - LOOKBACK_DAYS * 86400
    rows = c.execute("""SELECT source,category,sub,author,title,text,url,published,lang,zh_title,zh_text,content
                        FROM items ORDER BY published DESC""").fetchall()
    c.close()
    keys = ["source","category","sub","author","title","text","url","published","lang","zh_title","zh_text","content"]
    out = []
    for r in rows:
        pub = r[7]
        try:
            ts = time.mktime(time.strptime(pub, "%Y-%m-%dT%H:%M:%SZ")) if pub else 0
        except Exception:
            ts = 0
        if ts and ts < cutoff:
            continue
        out.append(dict(zip(keys, r)))
    with open(EXPORT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"  导出 {len(out)} 条 -> signals.json")
    return len(out)
