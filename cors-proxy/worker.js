// ai_signal_tracker — 自托管 CORS 代理（Cloudflare Worker）
// 用途：在浏览器里跨域抓取文章原文，交由 Mozilla Readability 提取正文，规避公共代理被墙。
// 部署（免费）：
//   1) 打开 https://workers.new  （需 Cloudflare 账号，免费）
//   2) 把本文件全部内容粘贴进编辑器
//   3) 点击「Deploy」→ 获得 https://<你的子域>.workers.dev
//   4) 在看板右上角「⚙ 抓取代理」中填入： https://<你的子域>.workers.dev/?url={url}
// 说明：workers.dev 在国内多数地区可直连；若个别地区不稳，可在 Cloudflare 绑定自有域名（免费支持）。
//      本代理仅转发 GET 请求，不做缓存、不记录内容，请仅用于抓取公开网页。
addEventListener('fetch', event => event.respondWith(handle(event.request)));

async function handle(request) {
  if (request.method === 'OPTIONS') {
    return new Response(null, {
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, OPTIONS',
        'Access-Control-Allow-Headers': '*'
      }
    });
  }
  const url = new URL(request.url);
  const target = url.searchParams.get('url');
  if (!target) {
    return new Response('用法： ?url=https://example.com/article', {
      headers: { 'content-type': 'text/plain; charset=utf-8' }
    });
  }
  if (!/^https?:\/\//i.test(target)) {
    return new Response('invalid url', { status: 400 });
  }
  try {
    const resp = await fetch(target, {
      method: 'GET',
      headers: { 'User-Agent': 'Mozilla/5.0 (compatible; ai-signal-tracker/1.0)' },
      redirect: 'follow'
    });
    const headers = new Headers(resp.headers);
    headers.set('Access-Control-Allow-Origin', '*');
    headers.set('Access-Control-Allow-Methods', 'GET, OPTIONS');
    headers.set('Access-Control-Allow-Headers', '*');
    return new Response(resp.body, { status: resp.status, headers });
  } catch (e) {
    return new Response('fetch error: ' + e.message, { status: 502 });
  }
}
