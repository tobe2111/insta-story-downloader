/**
 * 배치 건강 경고를 **실행해서** 검사한다 (docs/index.html 사이드바).
 *
 * 값(status.run_health)은 예전부터 브라우저까지 실려 왔는데 화면이 한 번도
 * 읽지 않았다(감사 245). 종목 절반이 실패한 날도 읽는 사람에게는 평범한
 * 하루로 보였다.
 *
 * 이 하네스는 index.html 안의 그 블록만 잘라 **진짜로 돌린다.** 문자열이
 * 들어 있는지 보는 검사는 동작을 확인하지 못하고, 이 저장소에서 여러 번
 * 헛돌았다("검사는 소스를 읽지 말고 돌려라").
 *
 * 실행: node tests/run_health_flags_check.mjs   (실패 시 종료코드 1)
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const html = readFileSync(join(here, "..", "docs", "index.html"), "utf8");

// 블록을 **구조로** 찾는다 — 앵커 한 줄에서 시작해 중괄호 균형으로 끝을 찾는다.
const anchor = html.indexOf("const rh=st.run_health");
if (anchor < 0) {
  console.error("배치 건강 블록이 없다 — 화면이 run_health를 안 읽는다");
  process.exit(1);
}
let open = html.lastIndexOf("{", anchor);
let depth = 0, end = -1;
for (let i = open; i < html.length; i++) {
  if (html[i] === "{") depth++;
  else if (html[i] === "}") { depth--; if (depth === 0) { end = i + 1; break; } }
}
if (end < 0) { console.error("블록의 끝을 못 찾았다"); process.exit(1); }
const block = html.slice(open, end);

const esc = (s) => String(s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/**
 * 그 블록을 진짜 실행해 경고 목록을 받는다.
 *
 * ⚠️ 넘겨주는 이름은 **그 자리에서 실제로 살아 있는 것만**이다(st·flags·
 *    syms·esc). 처음 판은 `nm`(종목 이름 함수)까지 주입했는데, 그건 위쪽
 *    다른 블록 안에서만 사는 const였다 — 하네스는 초록인데 브라우저에서는
 *    ReferenceError로 **사이드바가 통째로 비었다.** 없는 것을 주입하면
 *    검사가 현실이 아니라 자기 자신을 확인한다.
 */
function run(runHealth, names = {}) {
  const flags = [];
  const st = { run_health: runHealth };
  const syms = Object.fromEntries(
    Object.entries(names).map(([k, v]) => [k, { name: v }]));
  new Function("st", "flags", "syms", "esc", block)(st, flags, syms, esc);
  return flags;
}

const fails = [];
const check = (name, cond, detail) => {
  if (!cond) fails.push(name + (detail ? " — " + detail : ""));
};

// ① 부분 실패는 말한다 (실측: 20종목 중 19개 실패한 날이 초록이었다)
{
  const f = run({ paper: { date: "2026-08-14", ok: 1, failed: 19,
                           failed_keys: ["kr_stock:005930.KS"], skipped: 0 } });
  check("부분 실패를 말한다", f.length === 1, JSON.stringify(f));
  check("실패 종목 수가 보인다", /19종목/.test(f[0] || ""), f[0]);
  check("종목 이름이 보인다", /삼성전자/.test(
    run({ paper: { failed: 19, failed_keys: ["kr_stock:005930.KS"] } },
        { "kr_stock:005930.KS": "삼성전자" })[0] || ""));
}

// ② 정체는 말한다 — 그리고 **단위를 지어내지 않는다**(감사 243)
{
  const f = run({ paper: { date: "2026-08-18", ok: 0, failed: 0, skipped: 5,
                           stale: { "crypto:BTC/USDT": 5 },
                           max_stale_days: 5, stale_unit: "거래일" } });
  check("정체를 말한다", f.length === 1, JSON.stringify(f));
  check("거래일 단위로 말한다", /5거래일/.test(f[0] || ""), f[0]);
  check("달력 일수로 지어내지 않는다", !/5일째/.test(f[0] || ""), f[0]);
}
{
  const f = run({ retrain: { date: "2026-08-18", failed: 0, skipped: 1,
                             stale: { "crypto:BTC/USDT": 7 },
                             max_stale_days: 7 } });
  check("단위가 없으면 '일'이 기본", /7일/.test(f[0] || ""), f[0]);
}

// ③ 조용해야 할 때 조용한가 — 매일 울리는 경보는 꺼진 경보와 같다
check("멀쩡한 날은 조용하다",
      run({ paper: { date: "2026-08-14", ok: 20, failed: 0, skipped: 0 } })
        .length === 0);
check("주말(전 종목 건너뜀)은 조용하다",
      run({ paper: { date: "2026-08-15", ok: 0, failed: 0, skipped: 20,
                     skipped_keys: ["crypto:BTC/USDT"] } }).length === 0,
      "주말마다 울리면 진짜 신호가 묻힌다");
check("run_health가 없어도 안 죽는다", run({}).length === 0);
check("칸이 비어 있어도 안 죽는다", run({ paper: {} }).length === 0);

// ④ 두 배치를 각각 말한다 — 하나로 뭉치면 어느 쪽이 아픈지 모른다
{
  const f = run({ paper: { failed: 2, failed_keys: ["a"] },
                  retrain: { failed: 3, failed_keys: ["b"] } });
  check("두 배치를 따로 말한다", f.length === 2, JSON.stringify(f));
  check("페이퍼라고 이름 붙인다", f.some((x) => /페이퍼/.test(x)), f.join("|"));
  check("재학습이라고 이름 붙인다", f.some((x) => /재학습/.test(x)), f.join("|"));
}

// ⑤ 종목 이름을 화면에 그대로 꽂지 않는다(HTML 이스케이프)
{
  const f = run({ paper: { failed: 1, failed_keys: ["<img src=x>"] } });
  check("종목 이름을 이스케이프한다", !/<img/.test(f[0] || ""), f[0]);
}

if (fails.length) {
  console.error("❌ 배치 건강 경고 검사 실패:\n  · " + fails.join("\n  · "));
  process.exit(1);
}
console.log("✅ 배치 건강 경고 — 실패·정체는 말하고, 주말은 조용하다");
