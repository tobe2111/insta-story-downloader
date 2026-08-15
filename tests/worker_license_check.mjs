/**
 * 워커의 **라이선스 발급**을 진짜로 실행해 검사한다 (감사 251).
 *
 * 이 저장소에는 같은 알고리즘의 구현이 **둘** 있다:
 *
 *     발급  worker.js `issueKey`        (Cloudflare, 판매자가 누르는 버튼)
 *     검증  quant/licensing.py `generate_key` (구매자 컴퓨터)
 *
 * 둘이 어긋나면 **판 키가 전부 무효**가 된다. 지문(fingerprint) 장치가
 * 있지만 그건 '비밀이 같은가'만 본다 — 알고리즘이 갈라지면(자르는 길이,
 * 그룹 크기, 소유자 정규화) **지문은 그대로인데 키만 안 맞는다.**
 *
 * 그런데 worker.js에는 변이 항목이 **0건**이었고, 발급 경로를 도는 검사도
 * 없었다. 결함이 아직 안 났을 뿐, 막는 장치가 없었다(FROZEN ② — 검사가
 * 초록인 것과 장치가 동작하는 것은 다르다).
 *
 * 정답 벡터는 파이썬이 만들어 argv로 넘긴다 — 진실의 출처는 하나다.
 * 실행: node tests/worker_license_check.mjs '<JSON>'   (실패 시 종료코드 1)
 */
import worker from "../worker.js";

/**
 * 인자가 없으면(변이 시험은 인자 없이 부른다) **못 박아 둔 정답 벡터**를 쓴다.
 * 이 값들은 quant/licensing.generate_key가 같은 비밀로 낸 것이고,
 * tests/test_the_two_key_makers_agree.py가 매번 파이썬으로 다시 만들어
 * 이 상수가 아직 맞는지 대조한다 — 못 박은 값이 조용히 낡는 것을 막는다.
 */
const PINNED = {
  secret: "감사251-테스트-비밀",
  fingerprint: "3357dad8b539",
  cases: [
    { owner: "buyer@x.com", key: "QUANT-EPUDPB-AKGK7C-VE6UGW-DYEMZS" },
    { owner: "BUYER@X.COM", key: "QUANT-EPUDPB-AKGK7C-VE6UGW-DYEMZS" },
    { owner: "  buyer@x.com  ", key: "QUANT-EPUDPB-AKGK7C-VE6UGW-DYEMZS" },
    { owner: "한글이름@메일.한국", key: "QUANT-KDELPY-ZXMFK6-7IKYOH-BAI2X7" },
    { owner: "a+tag@sub.domain.co.kr", key: "QUANT-LNTHMU-CXFPJW-FJEKCO-4XIB5R" },
  ],
};

const given = process.argv[2] ? JSON.parse(process.argv[2]) : null;
const spec = given || {
  secret: PINNED.secret,
  cases: PINNED.cases.map((c) => ({ ...c, fingerprint: PINNED.fingerprint })),
};
const fails = [];
const check = (name, cond, detail) => {
  if (!cond) fails.push(name + (detail ? " — " + detail : ""));
};

const ASSETS = { fetch: async () => new Response("assets", { status: 200 }) };
const basic = (id, pw) =>
  "Basic " + Buffer.from(`${id}:${pw}`).toString("base64");

async function call(path, { env = {}, headers = {} } = {}) {
  const r = await worker.fetch(
    new Request("https://quant.example" + path, { headers }),
    { ASSETS, ...env }, {});
  let body = null;
  try { body = await r.clone().json(); } catch (e) { body = null; }
  return { status: r.status, body, headers: r.headers };
}

const FULL = { ADMIN_ID: "boss", ADMIN_PW: "pw", LICENSE_SECRET: spec.secret };
const AUTH = { Authorization: basic("boss", "pw") };

// ① 두 구현이 **같은 키**를 만드는가 (이 검사의 본체)
for (const c of spec.cases || []) {
  const r = await call("/api/admin/issue?owner=" + encodeURIComponent(c.owner),
                       { env: FULL, headers: AUTH });
  check(`발급 200 (${c.owner})`, r.status === 200, `status=${r.status}`);
  check(`키가 파이썬과 같다 (${c.owner})`, r.body && r.body.key === c.key,
        `worker=${r.body && r.body.key} python=${c.key}`);
  check(`지문이 파이썬과 같다 (${c.owner})`,
        r.body && r.body.fingerprint === "hmac:" + c.fingerprint,
        `worker=${r.body && r.body.fingerprint} python=hmac:${c.fingerprint}`);
}

// ② 로그인이 꺼져 있으면 **발급도 잠긴다** — 열려 있으면 누구나 키를 찍는다
{
  const r = await call("/api/admin/issue?owner=a@b.com",
                       { env: { LICENSE_SECRET: spec.secret } });
  check("로그인 미설정이면 발급 거부", r.status === 403, `status=${r.status}`);
  check("거부 응답에 키가 없다", !(r.body && r.body.key), JSON.stringify(r.body));
}

// ③ 자격증명이 틀리면 401 — 그리고 키는 나오지 않는다
for (const [id, pw, label] of [["boss", "틀림", "비번 오류"],
                               ["남", "pw", "아이디 오류"],
                               ["boss", "", "빈 비번"]]) {
  const r = await call("/api/admin/issue?owner=a@b.com",
                       { env: FULL, headers: { Authorization: basic(id, pw) } });
  check(`${label} → 401`, r.status === 401, `status=${r.status}`);
  check(`${label} → 키 없음`, !(r.body && r.body.key));
}
{
  const r = await call("/api/admin/issue?owner=a@b.com", { env: FULL });
  check("인증 헤더 없음 → 401", r.status === 401, `status=${r.status}`);
  const r2 = await call("/api/admin/issue?owner=a@b.com",
                        // 헤더 값은 Latin-1만 담긴다 — 한글을 넣으면 워커가
                        // 아니라 Request 생성에서 터져 검사가 헛돈다.
                        { env: FULL, headers: { Authorization: "Basic !!not-base64!!" } });
  check("망가진 인증 헤더 → 401", r2.status === 401, `status=${r2.status}`);
}

// ④ 어드민 페이지도 같은 문으로 막힌다(문이 아니라 경로가 되면 안 된다)
{
  const r = await call("/admin.html", { env: FULL });
  check("어드민 페이지 401", r.status === 401, `status=${r.status}`);
  const r2 = await call("/admin.html", { env: FULL, headers: AUTH });
  check("자격증명 있으면 통과", r2.status === 200, `status=${r2.status}`);
}

// ⑤ 이메일이 아니면 발급하지 않는다(오타 하나로 엉뚱한 키가 팔린다)
for (const bad of ["", "   ", "@nolocal", "이름만"]) {
  const r = await call("/api/admin/issue?owner=" + encodeURIComponent(bad),
                       { env: FULL, headers: AUTH });
  check(`잘못된 소유자 거부 (${JSON.stringify(bad)})`, r.status === 400,
        `status=${r.status}`);
}

// ⑥ 발급 응답은 교차출처로 열지 않는다 — 공개 시세만 열린다
{
  const r = await call("/api/admin/issue?owner=a@b.com",
                       { env: FULL, headers: AUTH });
  check("발급 응답에 CORS 없음",
        !r.headers.get("Access-Control-Allow-Origin"),
        r.headers.get("Access-Control-Allow-Origin"));
  check("발급 응답은 캐시 금지",
        (r.headers.get("Cache-Control") || "").includes("no-store"),
        r.headers.get("Cache-Control"));
}

// ⑦ 비밀이 없으면 '키처럼 생긴 것'을 지어내지 않는다
{
  const r = await call("/api/admin/issue?owner=a@b.com",
                       { env: { ADMIN_ID: "boss", ADMIN_PW: "pw" },
                         headers: AUTH });
  check("비밀 미설정 → 501", r.status === 501, `status=${r.status}`);
  check("비밀 미설정 → 키 없음", !(r.body && r.body.key));
}

if (fails.length) {
  console.error("❌ 워커 라이선스 발급 검사 실패:\n  · " + fails.join("\n  · "));
  process.exit(1);
}
console.log("✅ 워커 발급 — 파이썬 검증기와 같은 키 · 로그인 없으면 잠김");
