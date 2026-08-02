# -*- coding: utf-8 -*-
"""编排：抓取 -> 翻译 -> 入库 -> 导出 JSON。每日定时运行此脚本。"""
import time
from crawler import collect_all
from store import upsert, export_json, enrich_content, seed_from_previous, write_sources_meta
from translate import translate

if __name__ == "__main__":
    t0 = time.time()
    print("=== AI 信源定时爬取开始 ===")
    items, status = collect_all()
    seed_from_previous()          # 回填上一轮内容，失败源不丢历史
    upsert(items, translate)      # 写入本轮新抓取
    enrich_content()
    export_json()
    write_sources_meta(status)    # 写出信源状态，看板常驻展示
    print(f"=== 完成，耗时 {time.time()-t0:.1f}s ===")
