/**
 * "그냥 보유했다면" 계산을 **실행해서** 확인한다 (docs/assets/benchmark.js).
 *
 * ⚠️ 왜 이 하네스가 있나 (2026-08-17, 감사 276). 첫 화면이 절대 수익만
 *    말하고 있었다 — "손해 −2,802원". 같은 기간 그냥 보유는 1,005,900원이라
 *    진짜 성적은 −8,702원(−0.87%p)이었다.
 *
 * 실행: node tests/benchmark_check.mjs   (실패 시 종료코드 1)
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(here, "..", "docs", "assets", "benchmark.js"), "utf8");
new Function(src)();
const Q = globalThis.QuantBench;

const fails = [];
const check = (n, c, d) => { if (!c) fails.push(n + (d ? " — " + d : "")); };
const near = (a, b, t) => Math.abs(a - b) < (t || 1e-6);

/* ── 1. 실측 그 값 (2026-08-13 ~ 08-15 장부) ───────────────────── */
{
  const h = [{ date: "2026-08-13", price: 100.0, equity: 999635 },
             { date: "2026-08-14", price: 100.02, equity: 999847 },
             { date: "2026-08-15", price: 100.59, equity: 997197.56 }];
  const b = Q.vsHold(h, 1000000);
  check("보유 금액", near(b.hold, 1005900, 1), String(b.hold));
  check("차이", near(b.diff, -8702.44, 0.5), String(b.diff));
  check("%p", near(b.diff_pct, -0.865, 0.01), String(b.diff_pct));
  check("지고 있다", b.ahead === false);
}

/* ── 2. 대조군 — 이기는 날은 이겼다고 말해야 한다 ──────────────── */
{
  const h = [{ price: 100, equity: 1000000 },
             { price: 100, equity: 1050000 }];
  const b = Q.vsHold(h, 1000000);
  check("보유가 제자리면 초과가 곧 수익", near(b.diff, 50000), String(b.diff));
  check("앞선다", b.ahead === true);
}
{
  // 시장이 올랐고 전략도 올랐지만 **덜** 올랐다 — 절대는 이익, 성적은 패배.
  // 이 줄이 이 파일의 존재 이유다.
  const h = [{ price: 100, equity: 1000000 },
             { price: 110, equity: 1050000 }];
  const b = Q.vsHold(h, 1000000);
  check("시장이 오른 날의 이익은 실력이 아니다", b.ahead === false,
        JSON.stringify(b));
  check("보유였다면 110만", near(b.hold, 1100000), String(b.hold));
}

/* ── 3. 모르면 지어내지 않는다 ─────────────────────────────────── */
check("기록 한 줄이면 판정 불가", Q.vsHold([{ price: 100, equity: 1 }], 1e6) === null);
check("빈 기록", Q.vsHold([], 1e6) === null && Q.vsHold(null, 1e6) === null);
check("원금 미상", Q.vsHold([{ price: 100, equity: 1 }, { price: 101, equity: 2 }], null) === null);
check("첫날 지수 없음",
      Q.vsHold([{ equity: 1 }, { price: 101, equity: 2 }], 1e6) === null);
check("오늘 지수 없음",
      Q.vsHold([{ price: 100, equity: 1 }, { equity: 2 }], 1e6) === null);
check("지수 0(나눗셈 불가)",
      Q.vsHold([{ price: 0, equity: 1 }, { price: 101, equity: 2 }], 1e6) === null);
check("자산 없음",
      Q.vsHold([{ price: 100, equity: 1 }, { price: 101 }], 1e6) === null);

if (fails.length) {
  console.error("보유 대비 성적 검사 실패:\n  - " + fails.join("\n  - "));
  process.exit(1);
}
console.log("보유 대비 성적 검사 통과");
