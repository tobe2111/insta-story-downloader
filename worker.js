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
    if (url.pathname === "/api/admin/issue") {
      return issueKey(url, env);        // adminGate 통과 후에만 도달
    }
    if (url.pathname === "/api/quotes") {
      return quotes(url, ctx);
    }
    return env.ASSETS.fetch(request);
  },
};

/**
 * 라이선스 키 발급(서버측) — 발급 비밀은 Cloudflare 시크릿 LICENSE_SECRET에만
 * 존재한다(공개 저장소·브라우저에 없음). 어드민 로그인(adminGate) 뒤에서만
 * 호출되므로, 로그인한 관리자는 이메일만 넣으면 키가 나온다.
 * quant/licensing.py generate_key와 같은 알고리즘:
 *   HMAC-SHA256(비밀, 소문자 이메일) 앞 15바이트 → base32 24자 → 6자 그룹.
 */
const B32_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

function b32(bytes) {
  let out = "", bits = 0, val = 0;
  for (const b of bytes) {
    val = (val << 8) | b; bits += 8;
    while (bits >= 5) { out += B32_ALPHABET[(val >>> (bits - 5)) & 31]; bits -= 5; }
  }
  if (bits > 0) out += B32_ALPHABET[(val << (5 - bits)) & 31];
  return out;
}

async function issueKey(url, env) {
  // 안전장치: 어드민 로그인(ADMIN_ID/PW)이 꺼져 있으면 발급도 잠근다 —
  // 로그인 없는 상태에서 발급 API가 열리면 누구나 키를 찍을 수 있게 된다.
  if (!env.ADMIN_ID || !env.ADMIN_PW) {
    return json({ error: "어드민 로그인(ADMIN_ID/PW) 설정 후에만 발급 가능" },
                403, { "Cache-Control": "no-store" });
  }
  if (!env.LICENSE_SECRET) {
    return json({ error: "LICENSE_SECRET 미설정 — Cloudflare 시크릿에 추가하세요" },
                501, { "Cache-Control": "no-store" });
  }
  const owner = (url.searchParams.get("owner") || "").trim().toLowerCase();
  if (!owner || owner.indexOf("@") < 1) {
    return json({ error: "owner(구매자 이메일) 필요" }, 400,
                { "Cache-Control": "no-store" });
  }
  const enc = new TextEncoder();
  const k = await crypto.subtle.importKey(
    "raw", enc.encode(env.LICENSE_SECRET),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", k, enc.encode(owner)));
  const key = "QUANT-" + b32(sig.slice(0, 15)).replace(/(.{6})(?=.)/g, "$1-");
  // 지문 — '발급하는 비밀'과 '배포본이 검증하는 비밀'이 같은지 대조하는 값.
  // 둘이 어긋나면 발급한 키가 구매자 컴퓨터에서 전부 무효인데, 예전에는
  // 그걸 알려주는 장치가 없어 환불 요청으로만 알 수 있었다(2026-08-11).
  // 배포본에서 `quant fingerprint`(또는 릴리스 빌드 로그)와 대조할 것.
  // 비밀 자체는 노출되지 않는다(HMAC 단방향 + 12자 절단).
  const fp = await fingerprint(env.LICENSE_SECRET);
  return json({ owner, key, fingerprint: "hmac:" + fp }, 200,
              { "Cache-Control": "no-store" });
}

/** quant/licensing.secret_fingerprint와 동일: HMAC(비밀, 고정문구) 앞 12자. */
async function fingerprint(secret) {
  const enc = new TextEncoder();
  const k = await crypto.subtle.importKey(
    "raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = new Uint8Array(await crypto.subtle.sign(
    "HMAC", k, enc.encode("quant-license-fingerprint")));
  return [...sig].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 12);
}

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

/**
 * JSON 응답. 교차출처 허용(*)은 '공개 시세'에만 붙인다 — 예전에는 모든
 * 응답에 붙어 라이선스 발급 응답까지 열려 있었다. 브라우저가 교차출처에
 * 기본 인증을 실어 보내지 않아 실제 유출 경로는 아니었지만, 어드민 API에
 * 와일드카드를 달아둘 이유가 없다(2026-08-11 감사).
 */
function json(obj, status = 200, extra = {}, cors = false) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      "Content-Type": "application/json;charset=utf-8",
      ...(cors ? { "Access-Control-Allow-Origin": "*" } : {}),
      ...extra,
    },
  });
}

async function quotes(url, ctx) {
  const raw = (url.searchParams.get("symbols") || "").slice(0, 400);
  const syms = [...new Set(raw.split(",").map((s) => s.trim())
    .filter((s) => SYM_RE.test(s)))].slice(0, MAX_SYMBOLS);
  if (!syms.length) return json({ error: "symbols 필요" }, 400, {}, true);

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
    200, { "Cache-Control": "public, max-age=" + CACHE_TTL }, true);
  ctx.waitUntil(cache.put(cacheKey, resp.clone()));
  return resp;
}
