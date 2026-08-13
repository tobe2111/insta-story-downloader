/**
 * 워커 시세 사다리 **동작** 검사 — 소스 문자열이 아니라 실제 호출로 본다.
 *
 * ⚠️ 왜 이렇게까지 하는가: 이 저장소에서 여러 번 겪었듯 소스를 문자열로
 *    확인하는 검사는 변이를 놓친다. 여기서는 fetch·caches를 가짜로 끼우고
 *    워커를 진짜로 실행해, "어느 소스로 갔는가 / 폴백이 실제로 도는가"를
 *    응답으로 확인한다.
 *
 * 실행: node tests/worker_ladder_check.mjs   (실패 시 종료코드 1)
 */
import worker from "../worker.js";

let calls = [];
const ok = (obj) => new Response(JSON.stringify(obj),
  { status: 200, headers: { "content-type": "application/json" } });

function stubFetch(plan) {
  globalThis.fetch = async (input, init) => {
    const url = String(input && input.url ? input.url : input);
    calls.push(url);
    for (const [frag, resp] of plan) {
      if (url.includes(frag)) {
        return typeof resp === "function" ? resp(url, init) : resp();
      }
    }
    return new Response("nope", { status: 404 });
  };
}

/** 캐시는 매 케이스마다 비운다 — 캐시 히트로 통과하는 착시를 막는다. */
function freshCaches() {
  const store = new Map();
  globalThis.caches = {
    default: {
      async match(req) { return store.get(String(req.url)) || undefined; },
      async put(req, resp) { store.set(String(req.url), resp); },
    },
  };
}

const ctx = { waitUntil(p) { return p; } };
const env0 = { ASSETS: { fetch: async () => new Response("static") } };

async function quotesFor(symbols, env) {
  const req = new Request("https://x.test/api/quotes?symbols=" +
    encodeURIComponent(symbols.join(",")));
  const r = await worker.fetch(req, { ...env0, ...env }, ctx);
  return (await r.json()).quotes;
}

const YAHOO = ["query1.finance.yahoo.com", (url) => ok({
  chart: { result: [{ meta: {
    regularMarketPrice: url.includes("KRW%3DX") ? 1418.2 : 100,
    chartPreviousClose: url.includes("KRW%3DX") ? 1412.5 : 99,
    currency: "KRW", regularMarketTime: 1786000000 } }] } })];
const KIS_TOKEN = ["/oauth2/tokenP", () => ok({ access_token: "T", expires_in: 86400 })];
const KIS_PRICE = ["inquire-price", () => ok({
  output: { stck_prpr: "167500", stck_sdpr: "166000", prdy_ctrt: "0.90" } })];
const FINNHUB = ["finnhub.io", () => ok({ c: 268.1, pc: 267.28, dp: 0.31 })];

const fails = [];
function check(name, cond, detail) {
  if (cond) return;
  fails.push(`${name}${detail ? " — " + detail : ""}`);
}

// ① 키가 없으면 전부 야후, 한국주식은 '지연'으로 표시된다
freshCaches(); calls = []; stubFetch([YAHOO, KIS_TOKEN, KIS_PRICE, FINNHUB]);
{
  const q = await quotesFor(["005930.KS", "AAPL", "KRW=X"], {});
  check("키 없음: 한국주식", q["005930.KS"]?.source === "yahoo");
  check("키 없음: 한국주식 지연 표기", q["005930.KS"]?.delayed === true);
  check("키 없음: 미국주식", q["AAPL"]?.source === "yahoo");
  check("키 없음: 미국주식은 지연 아님", q["AAPL"]?.delayed === false);
  check("키 없음: KIS를 부르지 않는다",
        !calls.some((u) => u.includes("koreainvestment")));
}

// ② KIS 키가 있으면 한국주식만 실시간으로 간다
freshCaches(); calls = []; stubFetch([KIS_TOKEN, KIS_PRICE, YAHOO, FINNHUB]);
{
  const q = await quotesFor(["005930.KS", "AAPL", "KRW=X"],
                            { KIS_APP_KEY: "k", KIS_APP_SECRET: "s" });
  check("KIS: 한국주식 실시간", q["005930.KS"]?.source === "kis",
        JSON.stringify(q["005930.KS"]));
  check("KIS: 지연 아님", q["005930.KS"]?.delayed === false);
  check("KIS: 값 파싱", q["005930.KS"]?.price === 167500);
  check("KIS: 전일종가 파싱", q["005930.KS"]?.prev_close === 166000);
  check("KIS: 미국주식은 여전히 야후", q["AAPL"]?.source === "yahoo");
  check("KIS: 환율은 야후", q["KRW=X"]?.source === "yahoo");
  check("KIS: 환율을 KIS에 묻지 않는다",
        !calls.some((u) => u.includes("inquire-price") && u.includes("KRW")));
}

// ③ Finnhub 토큰이 있으면 미국주식만 실시간, 환율은 야후 그대로
freshCaches(); calls = []; stubFetch([FINNHUB, YAHOO, KIS_TOKEN, KIS_PRICE]);
{
  const q = await quotesFor(["AAPL", "KRW=X", "005930.KS"],
                            { FINNHUB_TOKEN: "t" });
  check("Finnhub: 미국주식 실시간", q["AAPL"]?.source === "finnhub");
  check("Finnhub: 값 파싱", q["AAPL"]?.price === 268.1);
  check("Finnhub: 환율은 야후", q["KRW=X"]?.source === "yahoo");
  check("Finnhub: 한국주식은 야후(키 없음)", q["005930.KS"]?.source === "yahoo");
  check("Finnhub: 환율을 Finnhub에 묻지 않는다",
        !calls.some((u) => u.includes("finnhub.io") && u.includes("KRW")));
}

// ④ 실시간 소스가 죽으면 **조용히 굳지 않고** 야후로 내려가며 라벨도 바뀐다
freshCaches(); calls = []; stubFetch([
  ["/oauth2/tokenP", () => new Response("boom", { status: 500 })], YAHOO]);
{
  const q = await quotesFor(["005930.KS"], { KIS_APP_KEY: "k", KIS_APP_SECRET: "s" });
  check("폴백: 값은 온다", q["005930.KS"]?.price === 100);
  check("폴백: 출처가 야후로 바뀐다", q["005930.KS"]?.source === "yahoo");
  check("폴백: 지연 라벨로 바뀐다", q["005930.KS"]?.delayed === true);
}

// ⑤ 토큰은 재발급되지 않는다 — 여러 종목을 물어도 발급은 한 번
freshCaches(); calls = []; stubFetch([KIS_TOKEN, KIS_PRICE, YAHOO]);
{
  await quotesFor(["005930.KS", "000660.KS", "069500.KS"],
                  { KIS_APP_KEY: "k", KIS_APP_SECRET: "s" });
  const issued = calls.filter((u) => u.includes("/oauth2/tokenP")).length;
  check("토큰 재발급 없음", issued === 1, `발급 ${issued}회`);
}

// ⑥ 장부 키(us_stock:AAPL)는 여전히 거부된다 — 감사 229 회귀 방지
freshCaches(); calls = []; stubFetch([YAHOO]);
{
  const req = new Request(
    "https://x.test/api/quotes?symbols=" + encodeURIComponent("us_stock:AAPL"));
  const r = await worker.fetch(req, env0, ctx);
  check("장부 키는 400", r.status === 400, "status=" + r.status);
}

if (fails.length) {
  console.error("실패 " + fails.length + "건:");
  fails.forEach((f) => console.error("  ✗ " + f));
  process.exit(1);
}
console.log("워커 시세 사다리 동작 검사 통과");
