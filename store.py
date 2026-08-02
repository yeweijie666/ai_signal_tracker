# -*- coding: utf-8 -*-
"""SQLite 存储：去重、按时间索引、缓存翻译；导出 JSON 供看板使用。"""
import os, sqlite3, hashlib, json, time
from config import LOOKBACK_DAYS, INSTITUTION_FEEDS, PLATFORMS, CN_FEEDS, NEWSLETTERS

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
        # 读取旧 content，便于“本次无全文时不覆盖历史已提取的内容”
        cur = c.execute("SELECT id,content FROM items WHERE id=?", (iid,)).fetchone()
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
        # content：优先用本次抓取带来的 RSS 全文（Fluent Reader 算法核心）；
        # 若本次无全文(content 为空)，则保留历史已由 enrich 提取的内容，不覆盖清空。
        old_content = cur[1] if cur else None
        new_content = (it.get("content") or "").strip()
        final_content = new_content if new_content else (old_content or "")
        row = (iid, it.get("source", ""), it.get("category", ""), it.get("sub", ""),
               it.get("author", ""), it.get("title", ""), it.get("text", ""),
               it.get("url", ""), it.get("published", ""), it.get("lang", ""),
               zh_title, zh_text, time.strftime("%Y-%m-%dT%H:%M:%SZ"), final_content)
        if cur:
            c.execute("""UPDATE items SET source=?,category=?,sub=?,author=?,title=?,
                text=?,url=?,published=?,lang=?,zh_title=?,zh_text=?,fetched_at=?,content=? WHERE id=?""",
                row[1:] + (iid,))
            n_upd += 1
        else:
            c.execute("""INSERT INTO items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", row)
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


# ===== 上一轮缓存回填 + 信源状态登记 =====
META = os.path.join(os.path.dirname(__file__), "sources_meta.json")

def _noop(s):
    return ""

def seed_from_previous():
    """每轮开始：把上一轮导出的 signals.json 回填进 DB。
    由于 signals.db 被 gitignore（不在仓库里），云端每次都是从空库起步；
    任何本轮抓取失败的源，其“上一轮还能抓到的”条目会借此保留，避免源在云端的
    偶发超时/拦截下彻底消失。回填条目用空翻译函数，避免重复消耗翻译额度。"""
    if not os.path.exists(EXPORT):
        print("  种子：无上一轮 signals.json，跳过")
        return 0
    try:
        prev = json.load(open(EXPORT, encoding="utf-8"))
    except Exception as e:
        print("  种子：读取上一轮 signals.json 失败：", e)
        return 0
    if not isinstance(prev, list):
        return 0
    upsert(prev, _noop)
    print(f"  种子：从上一轮 signals.json 回填 {len(prev)} 条（含失败源的缓存）")
    return len(prev)

def write_sources_meta(status):
    """写出 sources_meta.json：所有已配置信源的抓取状态，供看板常驻展示
    （即便某源本轮 0 条，也始终出现在侧栏，并标注 抓取失败/暂无更新）。"""
    cats = {}
    for name, info in status.items():
        cats.setdefault(info["cat"], []).append({
            "name": name, "sub": info.get("sub", ""),
            "status": info.get("status", ""), "count": info.get("count", 0),
            "error": info.get("error", ""),
        })
    meta = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"), "categories": cats}
    try:
        with open(META, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)
        print(f"  写出 sources_meta.json：{sum(len(v) for v in cats.values())} 个已配置源")
    except Exception as e:
        print("  写出 sources_meta.json 失败：", e)


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
            continue  # 已有 HTML 正文，保留（content:encoded 或历史缓存）
        if not url:
            # 无链接：用纯文本摘要兜底包成段落，避免正文空白
            if text and text.strip():
                updates[iid] = "<p>" + _esc(text.strip()) + "</p>"
            continue
        ts = 0
        if pub:
            try:
                ts = time.mktime(time.strptime(pub, "%Y-%m-%dT%H:%M:%SZ"))
            except Exception:
                ts = 0
        # 有链接且近期：联网用 Readability 抓真实正文（含图）—— Fluent Reader 的兜底逻辑；
        # 不再用“长摘要直接当正文”跳过抓取，确保摘要型源也能拿到完整全文。
        if ts == 0 or ts >= cutoff:
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
