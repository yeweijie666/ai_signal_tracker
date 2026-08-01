# -*- coding: utf-8 -*-
"""SQLite 存储：去重、按时间索引、缓存翻译；导出 JSON 供看板使用。"""
import os, sqlite3, hashlib, json, time
from config import LOOKBACK_DAYS

DB = os.path.join(os.path.dirname(__file__), "signals.db")
EXPORT = os.path.join(os.path.dirname(__file__), "signals.json")

def _hid(it):
    base = (it.get("url") or "") + "|" + (it.get("title") or "")[:80] + "|" + (it.get("published") or "")
    return hashlib.md5(base.encode("utf-8")).hexdigest()

def conn():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS items(
        id TEXT PRIMARY KEY, source TEXT, category TEXT, sub TEXT, author TEXT,
        title TEXT, text TEXT, url TEXT, published TEXT, lang TEXT,
        zh_title TEXT, zh_text TEXT, fetched_at TEXT)""")
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
            c.execute("""INSERT INTO items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", row)
            n_new += 1
    c.commit(); c.close()
    print(f"  入库：新增 {n_new}，更新 {n_upd}")
    return n_new, n_upd

def export_json():
    c = conn()
    cutoff = time.time() - LOOKBACK_DAYS * 86400
    rows = c.execute("""SELECT source,category,sub,author,title,text,url,published,lang,zh_title,zh_text
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
            ["source","category","sub","author","title","text","url","published","lang","zh_title","zh_text"], r)))
    with open(EXPORT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"  导出 {len(out)} 条 -> signals.json")
    return len(out)
