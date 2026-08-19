/**
 * "그냥 보유했다면 얼마였나" — **이 단계에서 유일하게 의미 있는 점수.**
 *
 * ⚠️ 왜 이 파일이 생겼나 (2026-08-17, 감사 276).
 *    첫 화면은 "손해 −2,802원(−0.28%)"만 말하고 있었다. 그런데 같은 기간
 *    전 종목을 그냥 사서 들고 있었다면 **1,005,900원**이었다. 즉 진짜 성적은
 *    −2,802원이 아니라 **−8,702원(−0.87%p)**이다.
 *
 *    이 구별이 왜 중요한가. 이 저장소가 지금 증명하려는 것은 "1억"이 아니다
 *    — 변동성 타깃 12%로는 100배까지 40년이 걸린다는 산수를 README가 이미
 *    적어 두었다. 증명하려는 것은 **"그냥 보유보다 낫다"** 하나다.
 *    그렇다면 첫 화면의 점수판도 그 질문에 답해야 한다. 절대 수익만 크게
 *    적으면, 시장이 오른 날은 실력처럼 보이고 내린 날은 억울해 보인다.
 *
 * 기준선은 장부가 매일 남기는 `price`(첫날 전 종목 균등 매수 지수)다 —
 * 차트가 이미 그 값으로 점선을 그린다. **여기서 새로 계산하지 않는다.**
 * 화면 두 곳이 각자 기준선을 만들면 언젠가 다른 답을 말한다(㉞).
 *
 * 파이썬 짝은 quant/reporting/benchmark.py이고,
 * tests/benchmark_check.mjs가 이 파일을 그대로 실행해 값으로 확인한다.
 */
(function (root) {
  "use strict";

  /**
   * 반환: {hold, diff, diff_pct, ahead, cost_rate} — 못 재면 null.
   *   hold      그냥 보유했다면 지금 얼마인가(원)
   *   diff      전략 − 보유 (원). 음수면 지고 있다.
   *   diff_pct  같은 것을 %p로. (전략/보유 − 1) × 100
   *   ahead     앞서고 있는가
   *   cost_rate 기준선이 실제로 문 진입 비용률(0이면 안 물었다는 뜻)
   *
   * ⚠️ **그냥 보유도 살 때 한 번은 돈을 낸다** (2026-08-19 사장님 승인).
   *    예전에는 이 기준선이 비용을 한 푼도 안 물었다. 그런데 우리 성적은
   *    수수료·세금·미끄러짐을 전부 문 뒤의 값이다 — 같은 자에 눈금이 둘.
   *    비율은 여기서 고르지 않는다. 장부가 그날 바구니의 시장 구성으로
   *    계산해 남긴 값을 부르는 쪽이 넘긴다.
   */
  function vsHold(history, principal, costRate) {
    var h = history || [];
    var base = Number(principal);
    if (!(h.length >= 2) || !isFinite(base) || !(base > 0)) return null;
    var p0 = Number(h[0] && h[0].price);
    var last = h[h.length - 1] || {};
    var pn = Number(last.price);
    var eq = Number(last.equity);
    // ⚠️ 하나라도 없으면 **답을 지어내지 않는다.** 기준선을 모르는데
    //    "이겼다/졌다"를 적는 것이 이 사이트에서 가장 하면 안 되는 일이다.
    if (!isFinite(p0) || !(p0 > 0) || !isFinite(pn) || !(pn > 0)
        || !isFinite(eq)) return null;
    var c = Number(costRate);
    if (!isFinite(c) || !(c >= 0 && c < 1)) c = 0;
    // 비용을 물고 산 몫만 시장을 탄다.
    var hold = base * (1 - c) * pn / p0;
    if (!(hold > 0)) return null;
    var diff = eq - hold;
    return {
      hold: hold,
      diff: diff,
      diff_pct: (eq / hold - 1) * 100,
      ahead: diff >= 0,
      cost_rate: c,
    };
  }

  root.QuantBench = { vsHold: vsHold };
})(typeof globalThis !== "undefined" ? globalThis : this);
