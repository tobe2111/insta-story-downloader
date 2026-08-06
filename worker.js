/**
 * Cloudflare Worker — 정적 사이트 서빙 + 주식 시세 프록시.
 *
 * 브라우저는 야후 파이낸스를 직접 못 부른다(CORS). 이 워커가 대신 받아
 * 30초 엣지 캐시로 서빙한다 — 사이트 티커바의 주식 시세가 '전일 확정'이
 * 아니라 준실시간으로 흐르게 하는 장치다. 코인은 바이낸스 공개 API가
 * CORS를 허용하므로 브라우저가 직접 부른다(여긴 관여 안 함).
 *
 *   GET /api/quotes?symbols=005930.KS,AAPL,SPY   (최대 25개)
 *   → {"quotes": {"AAPL": {"price":…, "prev_close":…, "change_pct":…}}, …}
 *
 * ⚠️ 시세는 표시 전용이다 — 매매 판단은 새벽 자동화(스냅샷·해시로 재현
 * 가능한 데이터)만 쓴다. 여기 시세가 틀려도 장부는 오염되지 않는다.
 */

const CACHE_TTL = 15;                 // 초 — 야후 부하와 실시간성의 절충
const MAX_SYMBOLS = 25;
const SYM_RE = /^[A-Za-z0-9.^=-]{1,12}$/;

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    // 어드민 보호 — Cloudflare 대시보드에서 ADMIN_ID/ADMIN_PW 시크릿을
    // 설정하면 브라우저 기본 로그인창(아이디/비밀번호)이 뜬다. 서버측
    // 검증이라 페이지 소스를 읽어도 우회할 수 없다. 미설정이면 현행 유지
    // (페이지는 열리지만 어차피 토큰 없이는 아무것도 못 바꾼다).
    if (url.pathname === "/admin.html" || url.pathname.startsWith("/api/admin")) {
      const denied = adminGate(request, env);
      if (denied) return denied;
    }
    if (url.pathname === "/api/quotes") {
      return quotes(url, ctx);
    }
    return env.ASSETS.fetch(request);
  },
};

function adminGate(request, env) {
  if (!env.ADMIN_ID || !env.ADMIN_PW) return null;   // 시크릿 미설정 → 보호 없음
  const h = request.headers.get("Authorization") || "";
  if (h.startsWith("Basic ")) {
    try {
      const dec = atob(h.slice(6));
      const i = dec.indexOf(":");
      if (i > 0 && dec.slice(0, i) === env.ADMIN_ID
          && dec.slice(i + 1) === env.ADMIN_PW) return null;
    } catch (e) { /* 잘못된 인코딩 → 거부 */ }
  }
  return new Response("어드민 로그인이 필요합니다", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="quant-admin", charset="UTF-8"' },
  });
}

function json(obj, status = 200, extra = {}) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      "Content-Type": "application/json;charset=utf-8",
      "Access-Control-Allow-Origin": "*",
      ...extra,
    },
  });
}

async function quotes(url, ctx) {
  const raw = (url.searchParams.get("symbols") || "").slice(0, 400);
  const syms = [...new Set(raw.split(",").map((s) => s.trim())
    .filter((s) => SYM_RE.test(s)))].slice(0, MAX_SYMBOLS);
  if (!syms.length) return json({ error: "symbols 필요" }, 400);

  // 심볼 순서와 무관하게 같은 캐시를 치도록 정렬 키 사용
  const cacheKey = new Request(
    url.origin + "/api/quotes?symbols=" + [...syms].sort().join(","));
  const cache = caches.default;
  const hit = await cache.match(cacheKey);
  if (hit) return hit;

  const out = {};
  await Promise.all(syms.map(async (s) => {
    try {
      const r = await fetch(
        "https://query1.finance.yahoo.com/v8/finance/chart/" +
        encodeURIComponent(s) + "?range=1d&interval=5m",
        { headers: { "User-Agent": "Mozilla/5.0 (quant-ticker)" },
          cf: { cacheTtl: CACHE_TTL } });
      if (!r.ok) return;
      const d = await r.json();
      const m = d?.chart?.result?.[0]?.meta;
      if (!m || m.regularMarketPrice == null) return;
      const prev = m.chartPreviousClose ?? m.previousClose ?? null;
      out[s] = {
        price: m.regularMarketPrice,
        prev_close: prev,
        change_pct: prev ? (m.regularMarketPrice / prev - 1) * 100 : null,
        currency: m.currency || null,
        market_time: m.regularMarketTime || null,
      };
    } catch (e) { /* 심볼 하나의 실패는 무시 — 나머지는 계속 */ }
  }));

  const resp = json(
    { quotes: out, cached_at: new Date().toISOString(), ttl: CACHE_TTL },
    200, { "Cache-Control": "public, max-age=" + CACHE_TTL });
  ctx.waitUntil(cache.put(cacheKey, resp.clone()));
  return resp;
}
