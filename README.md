# AI 硬核信源追踪系统

每天定时爬取《Situational Awareness》必追踪清单中的信源，按时间线排列，英文条目附带中文翻译。
**本地运行、数据存本机、不上传。**

## 目录结构
```
ai_signal_tracker/
├── config.py          # 信源清单 + 翻译引擎配置（改这里加源/换翻译）
├── crawler.py         # 各信源抓取与归一化
├── translate.py       # 翻译（可配置引擎，国内适配）
├── store.py           # SQLite 存储（去重、缓存翻译）+ 导出 JSON
├── run.py             # 一键编排：抓取→翻译→入库→导出
├── dashboard.html     # 时间线看板（按时间排序、原文+译文并排、筛选）
├── signals.db         # 本地数据库（自动生成）
├── signals.json       # 看板数据源（自动生成）
├── setup_daily_task.bat  # 注册 Windows 每日定时任务
└── venv 依赖（managed）
```

## 快速开始
1. **首次运行**：双击 `setup_daily_task.bat` 注册每天 08:00 自动爬取（需管理员）。
2. **立即跑一次**：在目录下执行
   ```
   C:\Users\27066\.workbuddy\binaries\python\envs\default\Scripts\python.exe run.py
   ```
3. **看时间线**：在目录下启动本地服务器（推荐，可自动读数据）
   ```
   C:\Users\27066\.workbuddy\binaries\python\envs\default\Scripts\python.exe -m http.server 8000
   ```
   浏览器打开 http://localhost:8000/dashboard.html
   > 若直接双击 dashboard.html 打开（file://），浏览器会拦截本地文件读取，
   > 此时点页面右上角「📂 打开 signals.json」手动选择同目录的 signals.json 即可。

## 已接入的信源（自动爬取）
- **硬核平台**：arXiv(cs.CL/cs.AI)、Hacker News、Hugging Face Blog、Papers With Code、GitHub Trending、Reddit(r/MachineLearning、r/LocalLLaMA)
- **机构报告**：麦肯锡、高盛、红杉、CB Insights、Gartner、The Information、FutureThink
- **中文资讯**：机器之心、量子位、AITOP100
- **Newsletter**：The Batch、Import AI、Interconnects
- **RSS**：Karpathy 92 源 OPML（自动展开）
- **X / Twitter**：见下方限制

## ⚠️ X(Twitter) 限制（重要）
X 已关闭免费 API，未登录抓取会被反爬拦截且违反 ToS，**无法免费合规地自动爬取**。
要自动抓 X，二选一：
1. 购买 **X API v2**（基础版约 $100/月），把 Bearer Token 填入 `config.py` 的 `X_BEARER_TOKEN`，脚本即可自动抓 15 个账号。
2. 暂时**手动补**：把想追的推文贴进 `signals.json`（或在未来版本加手动录入页）。

其余信源全部免费自动爬取。

## 翻译配置（适配国内网络）
`config.py` 的 `TRANSLATE`：
- 默认引擎 `google`（国内可能墙）。
- 主引擎失败会**自动回退 MyMemory**（免费、无需 key）。
- 如需更稳定，可改 `engine` 为 `deepl` / `baidu` / `libretranslate` 并填对应 key/url。
- 翻译结果随爬取**缓存进数据库**，只需成功一次，不重复翻译。

## 时间窗
`config.py` 的 `LOOKBACK_DAYS=3`：看板只展示最近 3 天；更早的仍存库但不在时间线显示。
`MAX_PER_SOURCE` 控制单源每次抓取上限。

## 自定义
- **加信源**：在 `config.py` 对应列表里加一行即可（RSS 加 url+type，X 加 handle）。
- **换抓取频率**：改 `setup_daily_task.bat` 里的 `/ST 08:00` 或加 `/RI 360` 改每 N 分钟。

---

## ☁️ 云端托管（GitHub Pages + 每日邮件）已部署

仓库：`https://github.com/yeweijie666/ai_signal_tracker`
看板（任意设备打开）：`https://yeweijie666.github.io/ai_signal_tracker/dashboard.html`

`.github/workflows/daily.yml` 在 GitHub 云端**每天北京时间 08:30** 自动：爬取 → 翻译 → **发邮件日报** → 提交数据 → Pages 自动重建。
完全不需要你的电脑开机。

### 开启每日邮件（只需做一次）
用你自己的 QQ 邮箱发给自己，免第三方服务。需要两个 GitHub Secret：

1. 登录 QQ 邮箱网页版 → **设置 → 账户 → 开启 IMAP/SMTP 服务** → 按提示生成**授权码**（不是登录密码）。
2. 进仓库 **Settings → Secrets and variables → Actions → New repository secret**，添加：
   - `QQ_EMAIL` = `270665534@qq.com`（发件人）
   - `QQ_AUTH_CODE` = 刚才生成的**授权码**
   - `TO_ADDR`（可选）= 收件人，默认同 `QQ_EMAIL`，即发给自己
3. 之后每天 08:30 爬完，日报自动发到 `270665534@qq.com`。

> 没填这两个 Secret 也能正常运行：脚本检测到缺配置会**自动跳过发信**，不影响爬取与看板更新。

### 想手动跑一次
仓库 **Actions → AI Signal Daily Crawl → Run workflow**。
