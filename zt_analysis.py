# -*- coding: utf-8 -*-
"""
每日涨停板分析抓取（同花顺风格）。
数据源：东方财富「涨停板池」getTopicZTPool —— 与同花顺涨停板分析展示的是同一套行情数据
（涨停股、连板高度、涨停原因/题材、所属板块、封单额、首次封板时间、开板次数等）。
说明：同花顺自身接口有 hexin-v 反爬 token 校验，无法在无头 CI 环境直接调用，
故采用同源行情的东方财富涨停板池，字段一一对应。

输出：zt_analysis.json
  {
    "date": "2026-07-31",
    "source": "东方财富涨停板池",
    "updated_at": "2026-08-02T08:30:00",
    "empty": false,
    "stats": {"zt":..,"dt":..,"lbc":..,"sz":..,"xd":..},
    "boards": [{"name":"新能源汽车","count":12}, ...],   # 涨停原因/题材分布 TOP
    "streak_ladder": [{"lbc":5,"stocks":[...]}, ...],     # 连板梯队
    "stocks": [{"code","name","price","pct","lbc","reason","board",
                "fd_amount","fd_text","first_time","open_times","amount","circ_mv"}, ...]
  }

运行：python zt_analysis.py  （无参数；可选 ZT_DATE=YYYY-MM-DD 强制指定日期）
"""
import os, sys, json, time, datetime, requests

HOST = "https://push2ex.eastmoney.com"
UT = "7eea3edcaed734bea9cbfc24409ed989"
OUT = os.environ.get("ZT_OUT", "zt_analysis.json")
HDR = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
}

# ---- 数值友好化（元 -> 亿/万）----
def human(n):
    try:
        n = float(n)
    except Exception:
        return ""
    if n >= 1e8:
        return f"{n/1e8:.2f}亿"
    if n >= 1e4:
        return f"{n/1e4:.1f}万"
    return f"{n:.0f}"


def fetch_pool(date_str):
    """返回 (pool列表, tj统计字典)；无数据返回 ([], None)。"""
    url = (f"{HOST}/getTopicZTPool?ut={UT}&d={date_str}"
           f"&Pageindex=0&pagesize=300&sort=fbt:asc")
    try:
        r = requests.get(url, headers=HDR, timeout=20)
        j = r.json()
    except Exception as e:
        print(f"  [zt] {date_str} 请求失败: {e}")
        return [], None
    if j.get("rc") != 0 or not isinstance(j.get("data"), dict):
        return [], None
    data = j["data"]
    pool = data.get("pool") or []
    tj = data.get("tj") or {}
    return pool, tj


def norm_stock(it):
    """把东方财富原始字段归一化为前端友好结构。"""
    code = it.get("c", "")
    name = it.get("n", "")
    price = it.get("p", "")
    pct = it.get("zdp", "")          # 涨跌幅 %
    lbc = it.get("lbc", 0) or 0      # 连板天数
    reason = (it.get("ly") or "").strip()      # 涨停原因 / 题材
    board = (it.get("hy") or "").strip()       # 行业板块
    fd = it.get("fd", 0) or 0       # 封单额（元）
    fbt = it.get("fbt", "") or ""   # 首次封板时间 HH:MM:SS
    kb = it.get("kb", 0) or 0       # 开板次数
    amount = it.get("amount", 0) or 0   # 成交额（元）
    circ = it.get("lt", 0) or 0     # 流通市值（元）
    return {
        "code": code,
        "name": name,
        "price": price,
        "pct": pct,
        "lbc": int(lbc) if str(lbc).isdigit() else 0,
        "reason": reason or "—",
        "board": board or "—",
        "fd_amount": fd,
        "fd_text": human(fd),
        "first_time": (fbt[:5] if isinstance(fbt, str) and len(fbt) >= 5 else ""),
        "open_times": int(kb) if str(kb).isdigit() else 0,
        "amount_text": human(amount),
        "circ_mv_text": human(circ),
    }


def build(date_str, pool, tj):
    stocks = [norm_stock(it) for it in pool]

    # 涨停原因 / 题材分布
    from collections import Counter
    rc = Counter(s["reason"] for s in stocks if s["reason"] != "—")
    boards = [{"name": k, "count": v} for k, v in rc.most_common(15)]

    # 连板梯队（按连板天数降序）
    ladder_map = {}
    for s in stocks:
        ladder_map.setdefault(s["lbc"], []).append(s)
    ladder = []
    for k in sorted(ladder_map.keys(), reverse=True):
        if k <= 0:
            continue
        ladder.append({"lbc": k, "stocks": ladder_map[k]})

    stats = {
        "zt": tj.get("zt"),
        "dt": tj.get("dt"),
        "lbc": tj.get("lbc"),
        "sz": tj.get("sz"),
        "xd": tj.get("xd"),
    }
    stats = {k: v for k, v in stats.items() if v is not None}

    return {
        "date": date_str,
        "source": "东方财富涨停板池",
        "updated_at": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "empty": False,
        "stats": stats,
        "boards": boards,
        "streak_ladder": ladder,
        "stocks": stocks,
    }


def main():
    forced = os.environ.get("ZT_DATE", "").strip()
    if forced:
        candidates = [forced]
    else:
        today = datetime.date.today()
        # 今天 -> 往前回溯 12 个交易日（覆盖周末/假期）
        candidates = [(today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
                      for i in range(0, 13)]

    print(f"[zt] 尝试日期：{candidates[0]} 起，最多回溯 {len(candidates)} 天")
    for ds in candidates:
        pool, tj = fetch_pool(ds)
        if pool:
            print(f"[zt] {ds} 命中 {len(pool)} 只涨停股；统计={tj}")
            out = build(ds, pool, tj)
            with open(OUT, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=1)
            print(f"[zt] 已写入 {OUT}（涨停 {out['stats'].get('zt','?')} 只）")
            return
        else:
            print(f"  [zt] {ds} 无数据，继续回溯…")

    # 全部为空（极端情况：长期休市）
    print("[zt] 近 12 个交易日均无涨停板数据，写入空标记。")
    out = {
        "date": candidates[0],
        "source": "东方财富涨停板池",
        "updated_at": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "empty": True,
        "note": "近 12 个交易日未取到涨停板数据（可能处于长期休市或接口临时不可用）。",
        "stats": {}, "boards": [], "streak_ladder": [], "stocks": [],
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"[zt] 已写入 {OUT}（空）")


if __name__ == "__main__":
    main()
