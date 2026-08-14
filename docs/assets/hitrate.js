/**
 * 적중률을 **표본이 감당하는 만큼만** 말하는 규칙 — 화면 두 곳이 공유한다.
 *
 * ⚠️ 왜 이 파일이 생겼나 (2026-08-14, 사장님 지적).
 *    "64% n=11 솔라나의 적중률은 이런 식으로 잘못 나오고 있어."
 *
 *    20종목을 전부 재 봤더니 **19개**의 95% 신뢰구간이 50%를 품고 있었다.
 *    즉 "동전던지기가 아니다"라고 말할 수 없는 숫자들인데, 화면은 그것을
 *    단정적인 퍼센트로 내보내고 있었다.
 *
 *        솔라나   58%  n=12  구간 32~81%   ← 아무 말도 할 수 없다
 *        SK하이닉스 60%  n=81  구간 50~70%   ← 이것도 마찬가지다
 *        KODEX200 67%  n=63  구간 54~77%   ← 유일하게 구별되는 하나
 *
 *    그때까지의 규칙(감사 111)은 **n<20이면 n을 흐리게 병기**였다. 방향은
 *    맞았지만 기준이 틀렸다 — n=81짜리 60%는 아무 단서 없이 "60%"라는
 *    단정으로 나갔다. **표본 크기가 아니라 신뢰구간이 판정한다.**
 *
 * 규칙은 한 곳에만 둔다(FROZEN_IDEAS ①). 파이썬 쪽 짝은
 * quant/robustness/accuracy.py의 wilson_ci·is_conclusive이고,
 * tests/hitrate_check.mjs가 이 파일을 그대로 실행해 값으로 확인한다.
 */
(function (root) {
  "use strict";

  var COIN_FLIP = 0.5;

  /** 윌슨 신뢰구간(95%) — 소표본·극단 비율에서도 [0,1]을 안 벗어난다. */
  function wilsonCI(k, n, z) {
    z = z || 1.96;
    if (!(n > 0)) return [NaN, NaN];
    var p = k / n;
    var denom = 1 + (z * z) / n;
    var center = (p + (z * z) / (2 * n)) / denom;
    var half = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / denom;
    return [Math.max(0, center - half), Math.min(1, center + half)];
  }

  /** 이 표본이 '동전던지기가 아니다'라고 말할 수 있는가. */
  function isConclusive(k, n) {
    var ci = wilsonCI(k, n);
    if (!(ci[0] === ci[0]) || !(ci[1] === ci[1])) return false;
    return !(ci[0] <= COIN_FLIP && COIN_FLIP <= ci[1]);
  }

  /**
   * 장부 기록 하나를 화면 문자열로 — {text, dim, title}.
   *
   *   text  화면에 쓸 문자열
   *   dim   흐리게 표시할지(단정할 수 없는 숫자)
   *   title 마우스오버 설명(구간·표본)
   *
   * 장부에 hit_lo/hit_hi/hit_conclusive가 있으면 그대로 쓰고, 없으면(옛
   * 기록) n으로 다시 계산한다. **화면이 자기 기준을 새로 만들지는 않는다.**
   */
  function format(rec) {
    rec = rec || {};
    var r = rec.hit_rate;
    if (typeof r !== "number" || !(r === r)) {
      return { text: "—", dim: true, title: "채점 가능한 봉이 없습니다" };
    }
    var n = (typeof rec.hit_n === "number") ? rec.hit_n : null;
    var lo = rec.hit_lo, hi = rec.hit_hi;
    var sure = rec.hit_conclusive;
    if (typeof sure !== "boolean" && n !== null) {   // 옛 기록 보정
      var ci = wilsonCI(Math.round(r * n), n);
      lo = ci[0]; hi = ci[1];
      sure = isConclusive(Math.round(r * n), n);
    }
    var pct = Math.round(r * 100) + "%";
    if (n === null) {
      // 표본을 모르면 그 비율로 아무 말도 할 수 없다 — 감사 111 이전 기록.
      return { text: pct + " (표본 미상)", dim: true,
               title: "표본 수가 기록되지 않은 옛 기록입니다 — 이 비율로는 " +
                      "실력을 판단할 수 없습니다" };
    }
    var band = (typeof lo === "number" && typeof hi === "number" && lo === lo)
      ? Math.round(lo * 100) + "~" + Math.round(hi * 100) + "%" : "?";
    var title = "표본 " + n + "봉 · 95% 신뢰구간 " + band +
      (sure ? " — 동전던지기(50%)와 구별됩니다"
            : " — 구간이 50%를 품고 있어 동전던지기와 구별되지 않습니다");
    if (!sure) {
      // 단정하지 않는다. 숨기지도 않는다 — 값과 구간을 함께 보여준다.
      return { text: pct + " (판정 불가 " + band + " · n=" + n + ")",
               dim: true, title: title };
    }
    return { text: pct + " (" + band + " · n=" + n + ")",
             dim: false, title: title };
  }

  root.QuantHitRate = { wilsonCI: wilsonCI, isConclusive: isConclusive,
                        format: format, COIN_FLIP: COIN_FLIP };
})(typeof globalThis !== "undefined" ? globalThis : this);

if (typeof module !== "undefined" && module.exports) {
  module.exports = (typeof globalThis !== "undefined" ? globalThis : this).QuantHitRate;
}
