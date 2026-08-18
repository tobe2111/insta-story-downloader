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
const LIVE_TTL = 3;                   // 초 — 실시간 소스(KIS·Finnhub)용
const MAX_SYMBOLS = 25;
const SYM_RE = /^[A-Za-z0-9.^=-]{1,12}$/;

/* ── 시세 소스 사다리 (2026-08-13) ───────────────────────────────
 * 사장님 요청: "신선도를 최대한 실시간으로, 무료 선에서."
 *
 *   한국주식 : 한국투자증권 OpenAPI(KIS) — 무료·공식·실시간.
 *              계좌 + 앱키가 있어야 하므로 시크릿이 있을 때만 켜진다.
 *              없으면 야후로 폴백(야후 .KS는 약 20분 지연).
 *   미국주식 : Finnhub 무료 티어(분당 60회) — 있으면 실시간, 없으면 야후.
 *   환율     : 야후 KRW=X — 초 단위로 볼 이유가 없다.
 *   코인     : 워커를 거치지 않는다(브라우저가 바이낸스 WebSocket 직결).
 *
 * ⚠️ 어떤 소스로 받았는지를 응답에 `source`로 실어 보낸다. 화면이
 *    "실시간"이라고 쓸지 "지연"이라고 쓸지는 **받은 사실**로 정해야지
 *    코드에 박아 두면 안 된다 — 감사 229가 정확히 그 반대 경우였다
 *    (라벨은 준실시간인데 요청이 매번 거부당하고 있었다).
 *
 * ⚠️ 앱키·시크릿은 코드에 없다. Cloudflare 시크릿(KIS_APP_KEY,
 *    KIS_APP_SECRET, FINNHUB_TOKEN)에만 존재한다.
 */
const KIS_BASE = "https://openapi.koreainvestment.com:9443";
const KIS_TOKEN_TTL = 3600 * 20;      // 초 — 발급 토큰은 24시간, 여유 4시간
const KR_SUFFIX = /\.(KS|KQ)$/;

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
      return quotes(url, env, ctx);
    }
    // 고객이 동의하고 보낸 전략 명세 수집함 (2026-08-18 사장님 지시:
    // "고객들이 등록하는 자료들은 내 어드민 대시보드에서도 확보").
    // 저장은 KV(SUBMISSIONS)가 연결돼 있을 때만 — 미설정이면 정직한 503.
    if (url.pathname === "/api/submit-spec") {
      return submitSpec(request, env);
    }
    if (url.pathname === "/api/telemetry") {
      return submitTelemetry(request, env);
    }
    if (url.pathname === "/api/admin/submissions") {
      return listSubmissions(env);      // adminGate 통과 후에만 도달
    }
    return env.ASSETS.fetch(request);
  },
};

// ── 고객 등록 전략 수집함 ─────────────────────────────────────────
// 저장을 켜려면: Cloudflare 대시보드 → Storage & Databases → KV에서
// 네임스페이스를 만들고, wrangler.jsonc에 아래 한 줄을 추가한다.
//   "kv_namespaces": [{ "binding": "SUBMISSIONS", "id": "<네임스페이스 ID>" }]
// 미설정이어도 사이트는 정상이며, 제출자는 '수집함 미설정' 안내를 받는다.
// 개인정보는 받지 않는다 — 클라이언트가 보내는 것은 전략 명세(규칙)와
// 앱 버전뿐이고, 동의 체크박스를 켠 제출만 여기 도착한다.

const SUBMIT_MAX_BYTES = 65536;        // 64KB — 명세는 이보다 훨씬 작다

async function submitSpec(request, env) {
  if (request.method !== "POST") {
    return json({ error: "POST만 받습니다" }, 405);
  }
  if (!env.SUBMISSIONS) {
    return json({ error: "수집함 미설정 — 관리자가 Cloudflare에서 KV " +
                 "네임스페이스(SUBMISSIONS)를 연결해야 저장됩니다" }, 503);
  }
  const body = await request.text();
  if (body.length > SUBMIT_MAX_BYTES) {
    return json({ error: "명세가 너무 큽니다(64KB 상한)" }, 413);
  }
  let doc;
  try { doc = JSON.parse(body); } catch (e) {
    return json({ error: "JSON이 아닙니다" }, 400);
  }
  if (!doc || typeof doc !== "object" || !doc.spec) {
    return json({ error: "spec 필드가 없습니다" }, 400);
  }
  const rec = {
    received: new Date().toISOString(),
    app_version: String(doc.app_version || "").slice(0, 40),
    name: String(doc.name || "").slice(0, 120),
    spec: doc.spec,
  };
  const key = "spec:" + Date.now() + ":" + crypto.randomUUID().slice(0, 8);
  await env.SUBMISSIONS.put(key, JSON.stringify(rec));
  return json({ ok: true });
}

async function submitTelemetry(request, env) {
  // 사용 원격 측정 — 동의한 설치가 보내는 전략·성과 요약. 개인정보 없음.
  if (request.method !== "POST") return json({ error: "POST만 받습니다" }, 405);
  if (!env.SUBMISSIONS) {
    return json({ error: "수집함 미설정 — 관리자가 KV(SUBMISSIONS)를 연결해야 합니다" }, 503);
  }
  const body = await request.text();
  if (body.length > SUBMIT_MAX_BYTES) return json({ error: "본문이 너무 큽니다" }, 413);
  let doc;
  try { doc = JSON.parse(body); } catch (e) { return json({ error: "JSON이 아닙니다" }, 400); }
  if (!doc || typeof doc !== "object") return json({ error: "형식 오류" }, 400);
  const rec = {
    received: new Date().toISOString(),
    kind: "telemetry",
    install_id: String(doc.install_id || "").slice(0, 32),
    app_version: String(doc.app_version || "").slice(0, 40),
    strategies: doc.strategies || [],
    performance: doc.performance || [],
  };
  const key = "tele:" + Date.now() + ":" + crypto.randomUUID().slice(0, 8);
  await env.SUBMISSIONS.put(key, JSON.stringify(rec));
  return json({ ok: true });
}

async function listSubmissions(env) {
  if (!env.SUBMISSIONS) {
    return json({ error: "수집함 미설정 — KV(SUBMISSIONS) 연결 필요",
                  items: [] }, 200);
  }
  const specs = await env.SUBMISSIONS.list({ prefix: "spec:", limit: 1000 });
  const tele = await env.SUBMISSIONS.list({ prefix: "tele:", limit: 1000 });
  const listed = { keys: specs.keys.concat(tele.keys),
                   list_complete: specs.list_complete && tele.list_complete };
  const items = [];
  for (const k of listed.keys) {
    const v = await env.SUBMISSIONS.get(k.name);
    if (!v) continue;
    try { items.push({ key: k.name, ...JSON.parse(v) }); } catch (e) { /* skip */ }
  }
  items.sort((a, b) => (b.received || "").localeCompare(a.received || ""));
  return json({ items: items, truncated: Boolean(listed.list_complete === false) });
}

// json() 헬퍼는 아래 기존 것을 그대로 쓴다 — 같은 이름을 두 번 선언하면
// ES 모듈 빌드가 통째로 죽는다(2026-08-18 워커 배포 실패의 원인이 그거였다).

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

/** 야후 시세 — 무료·무계정. 미국주식은 준실시간, 한국주식은 약 20분 지연. */
async function yahooQuote(s) {
  const r = await fetch(
    "https://query1.finance.yahoo.com/v8/finance/chart/" +
    encodeURIComponent(s) + "?range=1d&interval=5m",
    { headers: { "User-Agent": "Mozilla/5.0 (quant-ticker)" },
      cf: { cacheTtl: CACHE_TTL } });
  if (!r.ok) return null;
  const d = await r.json();
  const m = d?.chart?.result?.[0]?.meta;
  if (!m || m.regularMarketPrice == null) return null;
  const prev = m.chartPreviousClose ?? m.previousClose ?? null;
  return {
    price: m.regularMarketPrice,
    prev_close: prev,
    change_pct: prev ? (m.regularMarketPrice / prev - 1) * 100 : null,
    currency: m.currency || null,
    market_time: m.regularMarketTime || null,
    // 야후 무료 시세의 지연을 숨기지 않는다 — 화면이 이 값으로 라벨을 정한다
    source: "yahoo",
    delayed: KR_SUFFIX.test(s),
  };
}

/**
 * KIS 접근토큰 — 발급은 하루 한 번이면 충분하므로 엣지 캐시에 담아 둔다.
 * ⚠️ 토큰을 매 요청 발급하면 KIS가 유량 제한으로 막는다(그리고 그 실패는
 *    조용하다). 캐시 키는 오리진 내부 경로라 외부에서 읽을 수 없다.
 */
let kisInflight = null;               // 같은 요청 안의 동시 발급 합치기

async function kisToken(env, ctx) {
  const cache = caches.default;
  const key = new Request("https://kis-token.internal/access");
  const hit = await cache.match(key);
  if (hit) return (await hit.json()).access_token || null;
  // ⚠️ 종목별 조회가 Promise.all로 동시에 들어오면 캐시에 아직 아무것도
  //    없으므로 **전부 각자 발급**한다. 7종목이면 발급 7회 — KIS 유량
  //    제한에 걸리고, 그 실패는 조용하다(값이 안 오면 야후로 내려갈 뿐).
  //    동작 검사(tests/worker_ladder_check.mjs)가 실제로 발급 3회를
  //    잡아냈다. 소스만 읽는 검사는 "캐시를 쓴다"만 보고 통과했었다.
  if (kisInflight) return kisInflight;
  kisInflight = (async () => await issueKisToken(env, ctx, cache, key))();
  try {
    return await kisInflight;
  } finally {
    kisInflight = null;
  }
}

async function issueKisToken(env, ctx, cache, key) {
  const r = await fetch(KIS_BASE + "/oauth2/tokenP", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      grant_type: "client_credentials",
      appkey: env.KIS_APP_KEY,
      appsecret: env.KIS_APP_SECRET,
    }),
  });
  if (!r.ok) return null;
  const d = await r.json();
  if (!d.access_token) return null;
  ctx.waitUntil(cache.put(key, json(
    { access_token: d.access_token }, 200,
    { "Cache-Control": "public, max-age=" + KIS_TOKEN_TTL })));
  return d.access_token;
}

/** 한국투자증권 실시간 현재가 — 무료·공식. 앱키가 없으면 호출되지 않는다. */
async function kisQuote(s, env, ctx) {
  const token = await kisToken(env, ctx);
  if (!token) return null;
  const code = s.replace(KR_SUFFIX, "");
  const r = await fetch(
    KIS_BASE + "/uapi/domestic-stock/v1/quotations/inquire-price" +
    "?FID_COND_MRKT_DIV_CODE=J&FID_INPUT_ISCD=" + encodeURIComponent(code),
    { headers: {
        "content-type": "application/json",
        authorization: "Bearer " + token,
        appkey: env.KIS_APP_KEY,
        appsecret: env.KIS_APP_SECRET,
        tr_id: "FHKST01010100",
      },
      cf: { cacheTtl: LIVE_TTL } });
  if (!r.ok) return null;
  const d = await r.json();
  const o = d?.output;
  const px = o && Number(o.stck_prpr);
  if (!px) return null;
  const base = Number(o.stck_sdpr) || null;      // 전일 종가(기준가)
  return {
    price: px,
    prev_close: base,
    change_pct: o.prdy_ctrt != null ? Number(o.prdy_ctrt)
                                    : (base ? (px / base - 1) * 100 : null),
    currency: "KRW",
    market_time: null,
    source: "kis",
    delayed: false,
  };
}

/** Finnhub 무료 티어 — 분당 60회. 토큰이 없으면 호출되지 않는다. */
async function finnhubQuote(s, env) {
  const r = await fetch(
    "https://finnhub.io/api/v1/quote?symbol=" + encodeURIComponent(s) +
    "&token=" + encodeURIComponent(env.FINNHUB_TOKEN),
    { cf: { cacheTtl: LIVE_TTL } });
  if (!r.ok) return null;
  const d = await r.json();
  if (!d || !d.c) return null;
  return {
    price: d.c,
    prev_close: d.pc ?? null,
    change_pct: d.dp ?? (d.pc ? (d.c / d.pc - 1) * 100 : null),
    currency: "USD",
    market_time: d.t || null,
    source: "finnhub",
    delayed: false,
  };
}

/**
 * 한 심볼의 시세 — 실시간 소스를 먼저, 실패하면 야후로 내려온다.
 *
 * ⚠️ 폴백은 **조용하지 않다.** 어느 소스로 받았는지가 응답의 source에
 *    남으므로, 실시간 소스가 죽은 날 화면은 "지연"이라고 정직하게 바뀐다.
 *    조용히 야후로 내려가면서 라벨만 '실시간'이면 그게 감사 229다.
 */
async function oneQuote(s, env, ctx) {
  try {
    if (KR_SUFFIX.test(s) && env.KIS_APP_KEY && env.KIS_APP_SECRET) {
      const q = await kisQuote(s, env, ctx);
      if (q) return q;
    } else if (!KR_SUFFIX.test(s) && s.indexOf("=") < 0 && env.FINNHUB_TOKEN) {
      const q = await finnhubQuote(s, env);      // 환율(KRW=X)은 야후로
      if (q) return q;
    }
  } catch (e) { /* 실시간 소스 실패 → 야후로 내려간다 */ }
  try {
    return await yahooQuote(s);
  } catch (e) {
    return null;                                  // 이 심볼만 포기
  }
}

async function quotes(url, env, ctx) {
  const raw = (url.searchParams.get("symbols") || "").slice(0, 400);
  const syms = [...new Set(raw.split(",").map((s) => s.trim())
    .filter((s) => SYM_RE.test(s)))].slice(0, MAX_SYMBOLS);
  if (!syms.length) return json({ error: "symbols 필요" }, 400, {}, true);

  // 실시간 소스가 하나라도 켜져 있으면 캐시를 짧게 — 3초 캐시면 상류
  // 호출은 초당 1회를 넘지 않으면서 화면은 사실상 실시간으로 흐른다.
  const live = Boolean((env.KIS_APP_KEY && env.KIS_APP_SECRET)
                       || env.FINNHUB_TOKEN);
  const ttl = live ? LIVE_TTL : CACHE_TTL;

  // 심볼 순서와 무관하게 같은 캐시를 치도록 정렬 키 사용
  const cacheKey = new Request(
    url.origin + "/api/quotes?symbols=" + [...syms].sort().join(","));
  const cache = caches.default;
  const hit = await cache.match(cacheKey);
  if (hit) return hit;

  const out = {};
  await Promise.all(syms.map(async (s) => {
    const q = await oneQuote(s, env, ctx);
    if (q) out[s] = q;
  }));

  const resp = json(
    { quotes: out, cached_at: new Date().toISOString(), ttl },
    200, { "Cache-Control": "public, max-age=" + ttl }, true);
  ctx.waitUntil(cache.put(cacheKey, resp.clone()));
  return resp;
}
