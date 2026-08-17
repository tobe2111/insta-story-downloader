/**
 * 노출 표시 규칙을 **실행해서** 검사한다 (docs/assets/exposure.js).
 *
 * ⚠️ 왜 이 하네스가 있나 (2026-08-17, 감사 264).
 *    장부가 노출을 `abs()`로 적어서 **숏 -30%와 롱 +30%가 화면에 똑같이
 *    `30%`로 남았다.** 부호를 살리자 이번에는 화면 네 곳이 각각
 *    `applied[k] > 0`을 "들고 있다"로 쓰고 있어서 **숏이 통째로 사라졌다.**
 *
 *    문자열만 읽는 검사는 이런 결함을 못 잡는다 — 코드가 거기 있다는 것과
 *    옳은 답을 낸다는 것은 다른 말이다(감사 229). 그래서 값으로 확인한다.
 *
 * 실행: node tests/exposure_check.mjs   (실패 시 종료코드 1)
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(here, "..", "docs", "assets", "exposure.js"), "utf8");
new Function(src)();                       // 페이지가 하는 것과 같은 방식으로 적재
const Q = globalThis.QuantExposure;

const fails = [];
const check = (name, cond, detail) => {
  if (!cond) fails.push(name + (detail ? " — " + detail : ""));
};

/* ── 1. "잡고 있나" — 숏도 보유다 ──────────────────────────────── */
check("롱은 보유", Q.held(0.3) === true);
check("숏도 보유", Q.held(-0.3) === true);      // ← 이 파일이 생긴 이유
check("0은 보유 아님", Q.held(0) === false);
check("없는 값은 보유 아님", Q.held(undefined) === false && Q.held(null) === false);
check("숫자가 아니면 보유 아님", Q.held("아마존") === false);
check("NaN도 보유 아님", Q.held(NaN) === false);

/* ── 2. 세기 ───────────────────────────────────────────────────── */
{
  const a = { A: 0.3, B: -0.2, C: 0.0 };
  check("롱+숏을 함께 센다", Q.count(a) === 2, String(Q.count(a)));
  check("빈 장부는 0", Q.count(null) === 0 && Q.count({}) === 0);
}

/* ── 3. 화면 문자열 — 방향은 부호가 아니라 글자로 ──────────────── */
check("롱은 그냥 퍼센트", Q.text(0.3) === "30.00%", Q.text(0.3));
// "-30%"라고만 쓰면 방송에서 "손실 30%"로 읽힌다. 그래서 '숏'이라 적는다.
check("숏은 '숏'이라 적는다", Q.text(-0.3) === "숏 30.00%", Q.text(-0.3));
check("숏 표기에 마이너스 기호는 없다", !/-/.test(Q.text(-0.3)), Q.text(-0.3));
check("자릿수를 고를 수 있다", Q.text(-0.3, 1) === "숏 30.0%", Q.text(-0.3, 1));
check("0은 0%", Q.text(0) === "0%");
check("없는 값도 안 터진다", Q.text(undefined) === "0%");
check("방향 접두어", Q.side(-0.1) === "숏 " && Q.side(0.1) === "");

/* ── 4. 상위 목록 — 크기 기준이다 ──────────────────────────────── */
{
  // 부호로 정렬하면 **가장 큰 자리**인 -0.5가 맨 끝으로 밀린다.
  const a = { A: 0.1, B: -0.5, C: 0.3, D: 0 };
  const t = Q.top(a, 3);
  check("가장 큰 자리가 숏이어도 1위", t[0][0] === "B", JSON.stringify(t));
  check("크기 순", t.map(e => e[0]).join("") === "BCA", JSON.stringify(t));
  check("0은 목록에 없다", t.length === 3, JSON.stringify(t));
  check("개수를 자른다", Q.top(a, 2).length === 2);
  check("빈 장부는 빈 목록", Q.top(null).length === 0);
}

/* ── 5. 총노출과 순노출은 다른 질문이다 ────────────────────────── */
{
  // 롱숏이 반반이면 시장에 나간 돈은 100%인데 시장 방향 노출은 0%다.
  const neutral = { A: 0.5, B: -0.5 };
  check("총노출은 Σ|w|", Math.abs(Q.gross(neutral) - 1.0) < 1e-9, String(Q.gross(neutral)));
  check("순노출은 Σw", Math.abs(Q.net(neutral)) < 1e-9, String(Q.net(neutral)));
  // 대조군 — 롱만 있으면 둘은 같다. 여기서 갈리면 부호 처리가 틀린 것이다.
  const longOnly = { A: 0.5, B: 0.2 };
  check("롱만 있으면 총=순", Math.abs(Q.gross(longOnly) - Q.net(longOnly)) < 1e-9,
        `${Q.gross(longOnly)} vs ${Q.net(longOnly)}`);
  check("빈 장부는 0", Q.gross(null) === 0 && Q.net(null) === 0);
}

if (fails.length) {
  console.error("노출 표시 규칙 검사 실패:\n  - " + fails.join("\n  - "));
  process.exit(1);
}
console.log("노출 표시 규칙 검사 통과");
