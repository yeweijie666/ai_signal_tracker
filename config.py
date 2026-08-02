# -*- coding: utf-8 -*-
"""
信源配置：从《Situational Awareness》必追踪清单提取，并标注抓取方式。
- X(Twitter) 无法免费合规抓取，留 Bearer Token 接口，无 token 时跳过（可手动补）。
- 其余信源均用免费 API / RSS 抓取。
"""

# ---- X / Twitter（可选，需付费 API v2 Bearer Token）----
import os as _os
# 优先读环境变量（GitHub Actions 里设 Secret 名为 X_BEARER_TOKEN 即可云端启用），
# 本地也可直接在下方引号里填。留空则跳过并在日志提示。
X_BEARER_TOKEN = _os.environ.get("X_BEARER_TOKEN", "")
X_HANDLES = [
    ("@karpathy", "核心大脑"), ("@sama", "核心大脑"), ("@darioamodei", "核心大脑"),
    ("@ylecun", "核心大脑"), ("@AndrewYNg", "核心大脑"),
    ("@simonw", "工程与工具"), ("@hwchase17", "工程与工具"), ("@jerryjliu0", "工程与工具"),
    ("@rasbt", "工程与工具"), ("@ID_AA_Carmack", "工程与工具"),
    ("@_akhaliq", "信号放大器"), ("@GergelyOrosz", "信号放大器"), ("@lexfridman", "信号放大器"),
    ("@kaifulee", "信号放大器"), ("@AnthropicAI", "信号放大器"),
]

# ---- 机构报告（周期性报告，监控发布页 RSS / 列表）----
INSTITUTION_FEEDS = [
    # name, category, sub, url, type
    ("麦肯锡 McKinsey AI", "机构报告", "投行/咨询", "https://www.mckinsey.com/insights/rss", "rss"),
    ("高盛 Goldman Sachs Tech", "机构报告", "投行/咨询", "https://www.goldmansachs.com/insights/technology/rss", "rss"),
    ("红杉资本 Sequoia", "机构报告", "投行/咨询", "https://www.sequoiacap.com/rss", "rss"),
    ("CB Insights", "机构报告", "数据机构", "https://www.cbinsights.com/rss", "rss"),
    ("Gartner", "机构报告", "数据机构", "https://www.gartner.com/en/information-technology/rss", "rss"),
    ("The Information", "机构报告", "数据机构", "https://www.theinformation.com/rss", "rss"),
    ("FutureThink 未来智库", "机构报告", "宏观趋势", "https://www.futurethink.com/rss", "rss"),
]

# ---- 硬核内容平台 ----
PLATFORMS = [
    ("arXiv cs.CL", "硬核平台", "https://export.arxiv.org/api/query?search_query=cat:cs.CL&sortBy=submittedDate&sortOrder=descending&max_results=30", "arxiv"),
    ("arXiv cs.AI", "硬核平台", "https://export.arxiv.org/api/query?search_query=cat:cs.AI&sortBy=submittedDate&sortOrder=descending&max_results=30", "arxiv"),
    ("Hugging Face Blog", "硬核平台", "https://huggingface.co/blog/feed.xml", "rss"),
    ("Papers With Code", "硬核平台", "https://paperswithcode.com/latest/rss", "rss"),
    ("GitHub Trending (llm)", "硬核平台", "https://github.com/trending?since=daily&spoken_language_code=", "github"),
    ("Hacker News", "硬核平台", "https://hn.algolia.com/api/v1/search_by_date?tags=story&query=ai&hitsPerPage=30", "hn"),
    ("Reddit r/MachineLearning", "硬核平台", "https://www.reddit.com/r/MachineLearning/hot.json?limit=25", "reddit"),
    ("Reddit r/LocalLLaMA", "硬核平台", "https://www.reddit.com/r/LocalLLaMA/hot.json?limit=25", "reddit"),
]

# ---- 中文资讯 ----
CN_FEEDS = [
    ("机器之心", "中文资讯", "https://www.jiqizhixin.com/rss", "rss"),
    ("量子位", "中文资讯", "https://www.qbitai.com/feed", "rss"),
    ("AITOP100", "中文资讯", "https://www.aitop100.cn/feed", "rss"),
]

# ---- Newsletter（RSS）----
NEWSLETTERS = [
    ("The Batch", "Newsletter", "https://www.deeplearning.ai/feed/", "rss"),
    ("Import AI", "Newsletter", "https://importai.substack.com/feed", "rss"),
    ("Interconnects (Nathan Lambert)", "Newsletter", "https://www.interconnects.ai/rss.xml", "rss"),
]

# ---- RSS：Karpathy 92 源 OPML（首次运行自动展开为多个 RSS）----
KARPATHY_OPML = "https://t.co/dwAiIjlXet"

# ---- 翻译配置（可配置引擎，适配国内网络）----
# engine: google(默认, 国内可能墙) / deepl / baidu / libretranslate
# baidu/deepl 需填 key；libretranslate 填 self_hosted_url
TRANSLATE = {
    "engine": "google",
    "baidu_appid": "",
    "baidu_key": "",
    "deepl_key": "",
    "libretranslate_url": "",  # 例如 http://localhost:5000/translate
}

# 抓取时间窗（只取最近 N 天内的条目，避免历史堆积）
# 设为 30 天：避免“短期无更新 / 本次云端抓取偶发超时”的源从看板消失。
LOOKBACK_DAYS = 30
MAX_PER_SOURCE = 40
