# -*- coding: utf-8 -*-
"""编排：抓取 -> 翻译 -> 入库 -> 导出 JSON。每日定时运行此脚本。"""
import time
from crawler import collect_all
from store import upsert, export_json
from translate import translate

if __name__ == "__main__":
    t0 = time.time()
    print("=== AI 信源定时爬取开始 ===")
    items = collect_all()
    upsert(items, translate)
    export_json()
    print(f"=== 完成，耗时 {time.time()-t0:.1f}s ===")
