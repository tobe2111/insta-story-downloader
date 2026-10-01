/* 시장 민감도 카드 — "그냥 시황을 따라가는 것 아니냐"에 숫자로 답한다.
 *
 * 사장님 질문(2026-10-01): "나스닥 시장 안좋으면 주식 떨어지고 오르면 같이
 * 오르고 이러면 자동투자매매가 의미가 있나?"
 *
 * 쓰는 법: <div data-market-beta="main"></div> (트랙 하나) 또는
 *          <div data-market-beta="all"></div> (모든 계좌).
 * 숫자는 배치가 status.json의 `market_beta`에 실어 보낸 값이다 — 여기서
 * 계산하지 않는다(파이썬 짝: quant/reporting/market_beta.py).
 *
 * ⚠️ 판정 문구는 **숫자에서 기계적으로** 고른다. 표본이 짧거나 t가 문턱
 *    아래면 알파가 플러스여도 "우연과 구별 안 됨"이다 — 좋은 숫자를 실력처럼
 *    보이게 하는 것이 이 칸이 막으려는 바로 그 일이다.
 */
(function (root) {
  "use strict";

  var CSS =
    ".mb{border:1px solid var(--line,#ddd);border-radius:10px;padding:14px 16px;" +
    "margin:14px 0;background:var(--bg2,transparent);color:var(--fg,inherit);" +
    "font-size:14px;line-height:1.6}" +
    ".mb h2{font-size:16px;margin:0 0 6px}" +
    ".mb .sub{color:var(--muted,#777);font-size:12.5px}" +
    ".mb .tw{overflow-x:auto;-webkit-overflow-scrolling:touch}" +
    ".mb table{border-collapse:collapse;width:100%;font-size:13px;margin-top:8px}" +
    ".mb th,.mb td{border-bottom:1px solid var(--line,#eee);padding:5px 6px;" +
    "text-align:left;white-space:nowrap}" +
    ".mb td.n{text-align:right;font-variant-numeric:tabular-nums}" +
    ".mb .up{color:var(--up,#1a7f37)}.mb .down{color:var(--down,#c0392b)}" +
    ".mb ul{margin:6px 0 0;padding-left:18px}";

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.appendChild(document.createTextNode(String(text)));
    return e;
  }

  function fx(v, d) {
    var n = Number(v);
    if (!isFinite(n)) return "—";
    var s = Math.abs(n).toFixed(d);
    return (n < 0 ? "−" : "") + s;
  }

  /* 민감도를 말로 — 구간은 고정이고 숫자에서 기계적으로 고른다. */
  function follow(beta) {
    var b = Number(beta);
    if (!isFinite(b)) return "—";
    if (b < -0.2) return "반대로 움직임";
    if (b < 0.2) return "거의 안 따라감";
    if (b < 0.6) return "일부 따라감";
    if (b <= 1.2) return "지수만큼 따라감";
    return "지수보다 크게 움직임";
  }

  function verdict(r) {
    if (r.short) return {t: "표본 부족", c: ""};
    if (!r.significant) return {t: "우연과 구별 안 됨", c: ""};
    return Number(r.alpha_bp) > 0
      ? {t: "시장을 이김 — 우연과 구별됨", c: "up"}
      : {t: "시장에 짐 — 우연과 구별됨", c: "down"};
  }

  function render(box, mb, which) {
    box.innerHTML = "";
    var tracks = (mb.tracks || []).filter(function (t) {
      return which === "all" || t.track === which;
    });
    if (!tracks.length) return;
    var card = el("div", "mb");
    card.appendChild(el("h2", null, "시장 따라가기 vs 자기 실력 — 지수를 빼고 보면"));
    card.appendChild(el("div", "sub",
      "계좌의 하루 수익을 지수의 하루 수익에 견줘 둘로 나눕니다. 지수를 따라 움직인 몫(민감도)과, 그 몫을 빼고 남은 몫(자동매매가 스스로 더하거나 잃은 것)입니다."));

    var tw = el("div", "tw");
    var t = el("table");
    var hr = el("tr");
    ["계좌", "견준 지수", "민감도", "따라 움직인 정도", "상관", "시장을 뺀 하루 평균", "t", "판정"].forEach(function (h) {
      hr.appendChild(el("th", null, h));
    });
    t.appendChild(hr);
    tracks.forEach(function (tr) {
      (tr.vs || []).forEach(function (r, i) {
        var row = el("tr");
        row.appendChild(el("td", null, i === 0 ? tr.label : ""));
        row.appendChild(el("td", null, r.bench_name));
        if (r.short) {
          row.appendChild(el("td", "n", "—"));
          row.appendChild(el("td", null, "—"));
          row.appendChild(el("td", "n", "—"));
          row.appendChild(el("td", "n", "—"));
          row.appendChild(el("td", "n", "—"));
        } else {
          row.appendChild(el("td", "n", fx(r.beta, 2)));
          row.appendChild(el("td", null, follow(r.beta)));
          row.appendChild(el("td", "n", fx(r.corr, 2)));
          var a = Number(r.alpha_bp);
          row.appendChild(el("td", "n " + (a > 0 ? "up" : a < 0 ? "down" : ""),
                             (a > 0 ? "+" : "") + fx(a / 100, 3) + "%"));
          row.appendChild(el("td", "n", fx(r.t, 2)));
        }
        var v = verdict(r);
        row.appendChild(el("td", v.c, v.t));
        t.appendChild(row);
      });
    });
    tw.appendChild(t);
    card.appendChild(tw);

    var ul = el("ul", "sub");
    [
      "민감도 1은 지수를 그대로 산 것과 같고, 0은 지수와 무관하다는 뜻입니다. 0.1이면 지수가 1% 움직일 때 평균 0.1% 움직였습니다.",
      "시장을 뺀 하루 평균이 플러스여도 t가 2보다 작으면 운으로 설명됩니다 — 그래서 판정은 '우연과 구별 안 됨'입니다.",
      "비용(수수료·세금)을 뺀 장부 자산으로 쟀습니다. 매매 판단은 이 숫자를 읽지 않습니다 — 보여 주기만 합니다."
    ].forEach(function (s) { ul.appendChild(el("li", null, s)); });
    card.appendChild(ul);
    box.appendChild(card);
  }

  function boot() {
    var boxes = document.querySelectorAll("[data-market-beta]");
    if (!boxes.length) return;
    if (!document.getElementById("mb-css")) {
      var st = document.createElement("style");
      st.id = "mb-css";
      st.textContent = CSS;
      document.head.appendChild(st);
    }
    fetch("status.json").then(function (r) { return r.ok ? r.json() : null; })
      .then(function (s) {
        var mb = s && s.market_beta;
        Array.prototype.forEach.call(boxes, function (b) {
          if (mb) render(b, mb, b.getAttribute("data-market-beta") || "all");
        });
      })
      .catch(function () {});
  }

  root.MarketBeta = {render: render, follow: follow, verdict: verdict};
  if (typeof document === "undefined") return;   // node 검사에서 불러올 때
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})(typeof window !== "undefined" ? window : this);
