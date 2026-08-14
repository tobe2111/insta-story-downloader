/**
 * 적중률 표시 규칙을 **실행해서** 검사한다 (docs/assets/hitrate.js).
 *
 * ⚠️ 왜 이 하네스가 있나 (2026-08-14, 사장님 지적).
 *    "64% n=11 솔라나의 적중률은 이런 식으로 잘못 나오고 있어."
 *
 *    20종목을 재 봤더니 19개의 95% 신뢰구간이 50%를 품고 있었다 — 즉
 *    "동전던지기가 아니다"라고 말할 수 없는 숫자들인데 화면은 단정적인
 *    퍼센트로 내보내고 있었다. 그때 규칙은 'n<20이면 흐리게'였고, 그래서
 *    n=81짜리 60%(구간 50~70%)는 아무 단서 없이 나갔다.
 *
 *    문자열만 읽는 검사는 이런 결함을 못 잡는다 — 코드가 거기 있다는 것과
 *    옳은 답을 낸다는 것은 다른 말이다(감사 229). 그래서 값으로 확인한다.
 *
 * 실행: node tests/hitrate_check.mjs   (실패 시 종료코드 1)
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(here, "..", "docs", "assets", "hitrate.js"), "utf8");
new Function(src)();                       // 페이지가 하는 것과 같은 방식으로 적재
const Q = globalThis.QuantHitRate;

const fails = [];
const check = (name, cond, detail) => {
  if (!cond) fails.push(name + (detail ? " — " + detail : ""));
};
const near = (a, b, tol) => Math.abs(a - b) < (tol || 1e-6);

/* ── 1. 윌슨 구간 자체 ─────────────────────────────────────────── */
// 파이썬 짝(robustness/accuracy.py)이 내는 값과 같아야 한다 — 두 구현이
// 갈라지면 같은 종목이 사이트와 알림에서 다른 확신으로 나간다.
// (k=7, n=12 → 0.319507 ~ 0.806743)
{
  const [lo, hi] = Q.wilsonCI(7, 12);
  check("wilson(7,12) 하한", near(lo, 0.319507, 1e-5), String(lo));
  check("wilson(7,12) 상한", near(hi, 0.806743, 1e-5), String(hi));
}
// 표본이 없으면 **구간이 없다** — 0으로 나누지 않는다(옛 explain.py의 결함).
{
  const [lo, hi] = Q.wilsonCI(0, 0);
  check("n=0이면 NaN 구간", !(lo === lo) && !(hi === hi), `${lo},${hi}`);
  check("n=0은 판정 불가", Q.isConclusive(0, 0) === false);
}
// 극단 비율에서도 [0,1]을 안 벗어난다 — 정규근사가 못 하는 일이다.
{
  const [lo, hi] = Q.wilsonCI(5, 5);
  check("전승도 구간이 1을 안 넘는다", hi <= 1 && lo > 0.5, `${lo},${hi}`);
  const [lo0, hi0] = Q.wilsonCI(0, 5);
  check("전패도 구간이 0 아래로 안 간다", lo0 >= 0 && hi0 < 0.5, `${lo0},${hi0}`);
  // 전패도 **판정은 된다** — "동전던지기보다 못하다"는 것도 결론이다.
  check("전패는 나쁜 쪽으로 판정된다", Q.isConclusive(0, 5) === true);
}

/* ── 2. 판정 — n이 아니라 구간이 정한다 ──────────────────────────
   이 세 줄이 이 파일이 생긴 이유다. 실제 장부에서 측정한 값들이다. */
check("솔라나 58% n=12는 판정 불가", Q.isConclusive(7, 12) === false);
check("SK하이닉스 60% n=81도 판정 불가", Q.isConclusive(49, 81) === false);
check("KODEX200 67% n=63은 판정 가능", Q.isConclusive(42, 63) === true);
// ⚠️ n이 커도 판정이 안 될 수 있고(위 n=81), 작아도 될 수 있다.
//    'n<20이면 흐리게'라는 옛 규칙이 왜 틀렸는지를 이 두 줄이 못 박는다.
check("n=81이 n=63보다 표본은 크지만 판정은 못 한다",
      Q.isConclusive(49, 81) === false && Q.isConclusive(42, 63) === true);
check("n=12여도 전승이면 판정된다", Q.isConclusive(12, 12) === true);

/* ── 3. 화면 문자열 ────────────────────────────────────────────── */
{
  // 판정 불가: 값을 숨기지 않되 단정하지도 않는다.
  const f = Q.format({ hit_rate: 7 / 12, hit_n: 12, hit_lo: 0.319507,
                       hit_hi: 0.806743, hit_conclusive: false });
  check("판정 불가는 흐리게", f.dim === true);
  check("판정 불가 문구", /판정 불가/.test(f.text), f.text);
  check("판정 불가에도 값이 남는다", /58%/.test(f.text), f.text);
  check("표본 수를 함께 쓴다", /n=12/.test(f.text), f.text);
  check("구간을 함께 쓴다", /32~81%/.test(f.text), f.text);
}
{
  const f = Q.format({ hit_rate: 42 / 63, hit_n: 63, hit_lo: 0.54367,
                       hit_hi: 0.770506, hit_conclusive: true });
  check("판정 가능은 안 흐리다", f.dim === false);
  check("판정 가능엔 '판정 불가'가 없다", !/판정 불가/.test(f.text), f.text);
  check("판정 가능도 구간을 붙인다", /54~77%/.test(f.text), f.text);
}
{
  // 옛 기록(구간 필드 없음) — 화면이 **자기 기준을 새로 만들지 않고** n으로
  // 다시 계산한다. 이게 없으면 옛 기록만 단정적으로 나간다.
  const f = Q.format({ hit_rate: 7 / 12, hit_n: 12 });
  check("옛 기록도 같은 판정", f.dim === true && /판정 불가/.test(f.text), f.text);
  const g = Q.format({ hit_rate: 42 / 63, hit_n: 63 });
  check("옛 기록도 판정되면 단정", g.dim === false, g.text);
}
{
  // 표본 자체가 없는 옛 기록 — 비율만으로는 아무 말도 할 수 없다.
  const f = Q.format({ hit_rate: 0.64 });
  check("표본 미상은 흐리게", f.dim === true);
  check("표본 미상 문구", /표본 미상/.test(f.text), f.text);
}
{
  const f = Q.format({});
  check("채점 봉이 없으면 —", f.text === "—", f.text);
  const g = Q.format({ hit_rate: NaN, hit_n: 0 });
  check("NaN도 —", g.text === "—", g.text);
  const h = Q.format(null);
  check("null도 안 터진다", h.text === "—", h.text);
}
{
  // 마우스오버 설명은 **왜 흐린지**를 말해야 한다. "흐리다"만 보이면
  // 읽는 사람은 그것이 고장인지 판단인지 구별할 수 없다.
  const f = Q.format({ hit_rate: 7 / 12, hit_n: 12 });
  check("툴팁이 이유를 말한다", /동전던지기/.test(f.title), f.title);
  check("툴팁이 표본을 말한다", /12봉/.test(f.title), f.title);
}

/* ── 4. 50% 경계 — 이 지점이 규칙의 정의다 ─────────────────────── */
check("구간이 정확히 50%에 닿아도 판정 불가",
      Q.isConclusive(1, 2) === false);
check("동전던지기 기준값", Q.COIN_FLIP === 0.5);

if (fails.length) {
  console.error("적중률 표시 규칙 검사 실패:\n  - " + fails.join("\n  - "));
  process.exit(1);
}
console.log("적중률 표시 규칙 검사 통과");
