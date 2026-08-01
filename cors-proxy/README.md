# 自托管 CORS 代理（用于正文抓取）

看板右侧「去广告正文」默认走公共 CORS 代理（allorigins / corsproxy.io）和 Jina Reader，这些服务在国内经常被墙，导致抓取失败、只能显示本地摘要。

为提升稳定性，可部署一个**自己的** CORS 代理，看板会优先使用它。

## 一键部署（Cloudflare Workers，免费）

1. 打开 https://workers.new （需 Cloudflare 免费账号）
2. 把 `worker.js` 的全部内容粘贴进编辑器
3. 点「Deploy」，获得形如 `https://<子域>.workers.dev` 的地址
4. 打开看板，点右上角 **⚙ 抓取代理**，填入：
   `https://<子域>.workers.dev/?url={url}`
   （`{url}` 是占位符，看板会自动替换为文章链接）
5. 以后抓取正文会优先走你的代理；留空则回退公共代理。

## 说明

- `workers.dev` 在国内多数地区可直连；个别地区若不稳，可在 Cloudflare 给 Worker 绑定自有域名（免费额度支持自定义域）。
- 该代理只转发 GET 请求、不做缓存、不留存内容，请仅用于抓取公开网页。
- 也可使用其它自建 CORS 代理，只要支持 `?url=<目标>` 形式即可被看板识别。

## 抓取链路顺序

看板点击文章后会按以下顺序尝试，直到成功：

1. 你配置的自托管代理（若有）
2. 公共 CORS 代理：allorigins.win、corsproxy.io
3. Jina Reader 服务（r.jina.ai）
4. 本地已抓取摘要（兜底，无需联网）
