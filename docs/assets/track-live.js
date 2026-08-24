/* 트랙 페이지 실시간 평가 — 코인 단타·미국 단타·코인 선물이 같은 한 곳을 쓴다.
 *
 * 사장님 지시(2026-08-23): "홈페이지에 계속 마지막 회차 기준이라고 떠있는데
 * 실시간으로 자산이 얼마인지 계속 볼 수 있게 가능해? 모든 투자페이지들."
 * 홈(100만)은 이미 준실시간 참고 평가가 있는데 트랙 페이지 셋은 회차 확정값
 * 만 보여주고 있었다 — 여기서 같은 규약으로 확장한다.
 *
 * 정직 규약(홈의 QuantLive와 같은 원칙):
 *   · 실시간 값은 **참고**다. 확정 기록(수익률·판정·곡선)을 덮어쓰지 않는다.
 *   · **전부 값이 있을 때만** 합계를 낸다 — 일부만 더한 합계는 거짓말이다.
 *     못 받은 종목은 이름을 말한다(조용히 비우지 않는다).
 *   · 시세를 못 받으면 못 받았다고 말하고 확정값이 그대로 남는다.
 *   · 화면 계산은 여기 한 곳에만 있고(감사 197 — 페이지마다 복사하면
 *     갈라진다) 순수 계산부는 tests/track_live_check.mjs가 값으로 검사한다.
 *
 * 계산: 실시간 자산 = 확정 자산 + Σ 부호수량 × (지금 시세 − 회차 확정가).
 * 현금을 몰라도 되는 형태라 세 계좌(현물 USDT·현물 USD·선물 숏 포함)에
 * 똑같이 성립한다. 숏은 가격이 오르면 잃는다 — 부호가 그 사실을 담는다.
 *
 * 시세 소스: 심볼에 '/'가 있으면 코인 → 바이낸스 공개 REST(브라우저 직결,
 * CORS 허용)를 4초마다. 아니면 주식 → 워커 프록시(/api/quotes, 15초 엣지
 * 캐시)를 15초마다. 어떤 소스로 받았는지가 아니라 **받았는지**가 표시를
 * 정한다.
 */
(function (root) {
  "use strict";

  /** 부호 있는 수량 — 숏은 음수. 장부가 direction으로 말한 것을 따른다. */
  function signedQty(h) {
    var q = Math.abs(Number(h.quantity) || 0);
    return h.direction === "short" ? -q : q;
  }

  /**
   * 순수 계산 — 확정 자산 + 보유별 (지금 − 확정가) 재평가.
   *
   * prices: {심볼: 지금 시세}. 하나라도 없으면 complete=false이고
   * equityLive는 null이다(일부만 더한 합계를 만들지 않는다).
   */
  function markLive(equity, holdings, prices) {
    var rows = {}, missing = [], delta = 0, n = 0;
    (holdings || []).forEach(function (h) {
      if (!h || !h.symbol) return;
      var px = prices && Number(prices[h.symbol]);
      var ref = Number(h.last_price);
      if (!px || !isFinite(px) || !isFinite(ref) || ref <= 0) {
        missing.push(h.symbol);
        return;
      }
      var sq = signedQty(h);
      var d = sq * (px - ref);
      /* 줄 단위 참고값 — 평가액은 방향 무관하게 크기로, 손익은 평균단가
         대비(그 줄의 확정 pnl과 같은 기준)로 낸다. */
      var pnl = (h.avg_cost != null && isFinite(Number(h.avg_cost)))
        ? sq * (px - Number(h.avg_cost)) : null;
      rows[h.symbol] = { px: px, value: Math.abs(sq) * px, pnl: pnl };
      delta += d;
      n += 1;
    });
    var complete = n > 0 && missing.length === 0;
    return {
      equityLive: complete ? Number(equity) + delta : null,
      delta: complete ? delta : null,
      rows: rows, missing: missing, complete: complete, counted: n
    };
  }

  /**
   * 현금 + Σ 수량×지금가 — 조종석(프로그램)용 순수 계산.
   *
   * 프로그램의 상태 파일은 (현금, 보유 수량, 평단)을 알고 회차 확정가는
   * 모른다 — 그래서 델타가 아니라 절대값으로 낸다. 현금을 모르면(옛 버전
   * 봇의 상태 파일) null + 사유다. Number(null)이 0인 언어라서, 이 가드를
   * 지우면 '현금 모름'이 '현금 0원'으로 조용히 둔갑한다.
   */
  function equityFromCash(cash, positions, prices) {
    if (cash == null || !isFinite(Number(cash))) {
      return { equityLive: null, missing: [], complete: false,
               rows: {}, counted: 0, reason: "현금 미기록" };
    }
    var rows = {}, missing = [], sum = Number(cash), n = 0;
    (positions || []).forEach(function (p) {
      if (!p || !p.symbol || !Number(p.quantity)) return;
      var px = prices && Number(prices[p.symbol]);
      if (!px || !isFinite(px)) { missing.push(p.symbol); return; }
      var q = Number(p.quantity);
      rows[p.symbol] = {
        px: px, value: Math.abs(q) * px,
        pnl: (p.avg_price != null && isFinite(Number(p.avg_price)))
          ? q * (px - Number(p.avg_price)) : null
      };
      sum += q * px;
      n += 1;
    });
    var complete = missing.length === 0;   // 보유 0개 + 현금만도 성립한다
    return { equityLive: complete ? sum : null, missing: missing,
             complete: complete, rows: rows, counted: n };
  }

  /* ── 여기서부터는 화면·네트워크(검사 대상 아님 — 브라우저 전용) ── */

  function binanceSyms(holdings) {
    return (holdings || []).map(function (h) { return h.symbol; })
      .filter(function (s) { return s && s.indexOf("/") > 0; });
  }

  function fetchCrypto(syms) {
    var arg = encodeURIComponent(JSON.stringify(syms.map(function (s) {
      return s.replace("/", "");
    })));
    return fetch("https://api.binance.com/api/v3/ticker/price?symbols=" + arg)
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (arr) {
        if (!arr) return null;
        var out = {};
        arr.forEach(function (t) {
          syms.forEach(function (s) {
            if (s.replace("/", "") === t.symbol) out[s] = Number(t.price);
          });
        });
        return out;
      });
  }

  function fetchStocks(syms) {
    return fetch("/api/quotes?symbols=" +
      encodeURIComponent(syms.join(",")))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        if (!j || !j.quotes) return null;
        var out = {};
        syms.forEach(function (s) {
          var q = j.quotes[s];
          if (q && Number(q.price) > 0) out[s] = Number(q.price);
        });
        return out;
      });
  }

  function hhmmss() {
    var d = new Date();
    function z(n) { return (n < 10 ? "0" : "") + n; }
    return z(d.getHours()) + ":" + z(d.getMinutes()) + ":" + z(d.getSeconds());
  }

  function fmtNum(v, dec) {
    return Number(v).toLocaleString("ko-KR",
      { minimumFractionDigits: dec, maximumFractionDigits: dec });
  }

  /**
   * 시작점 — 요약 줄과 보유 표에 실시간 참고값을 계속 흘린다.
   *
   * opts: { equity, holdings, currency, lineEl, tbody,
   *         intervalMs(선택), fmt(선택) }
   * 확정 숫자는 건드리지 않는다 — lineEl 한 줄과, 표의 '지금' 주석만 산다.
   */
  function start(opts) {
    var holdings = opts.holdings || [];
    var lineEl = opts.lineEl;
    if (!lineEl || !holdings.length) return;    // 빈 계좌 — 흘릴 것이 없다
    var cur = opts.currency || "USDT";
    var crypto = binanceSyms(holdings);
    var stocks = holdings.map(function (h) { return h.symbol; })
      .filter(function (s) { return s && s.indexOf("/") < 0; });
    var fails = 0;

    function tick() {
      var jobs = [];
      if (crypto.length) jobs.push(fetchCrypto(crypto));
      if (stocks.length) jobs.push(fetchStocks(stocks));
      Promise.all(jobs).then(function (parts) {
        var prices = {};
        parts.forEach(function (p) {
          if (p) Object.keys(p).forEach(function (k) { prices[k] = p[k]; });
        });
        var m = markLive(opts.equity, holdings, prices);
        if (!m.complete) {
          fails += 1;
          /* 일부만 받았으면 합계를 지어내지 않고 이유를 말한다. 계속
             실패하면(예: 사내망 차단) 조용해진다 — 확정값이 이미 화면에
             있으므로 잃는 것이 없다. */
          if (fails <= 3 && m.missing.length) {
            lineEl.innerHTML = '<span class="sub">실시간 시세 일부를 받지 ' +
              '못해(' + m.missing.map(function (s) {
                return String(s).replace(/[&<>]/g, "");
              }).join(", ") + ') 합계는 표시하지 않습니다 — 위 확정값을 ' +
              '보세요.</span>';
          }
          return;
        }
        fails = 0;
        var up = m.delta >= 0;
        lineEl.innerHTML = '지금 <b class="' + (up ? "up" : "down") + '">' +
          fmtNum(m.equityLive, 2) + ' ' + cur + '</b> ' +
          '<span class="' + (up ? "up" : "down") + '">(' +
          (up ? "+" : "−") + fmtNum(Math.abs(m.delta), 2) +
          ' vs 마지막 회차)</span>' +
          ' <span class="sub">실시간 참고 · ' + hhmmss() +
          ' · 수익률·판정은 확정 기록만 씁니다</span>';
        annotate(opts.tbody, holdings, m.rows);
      }).catch(function () { /* 네트워크 실패 — 다음 틱에 재시도 */ });
    }

    tick();
    setInterval(tick, opts.intervalMs ||
      (crypto.length ? 4000 : 15000));
  }

  /** 보유 표의 '시세'·'평가손익' 칸에 지금 값을 **덧붙인다**(덮지 않는다). */
  function annotate(tbody, holdings, rows) {
    if (!tbody) return;
    var trs = tbody.querySelectorAll("tr");
    (holdings || []).forEach(function (h, i) {
      var r = rows[h.symbol], tr = trs[i];
      if (!r || !tr || tr.cells.length < 7) return;
      setLive(tr.cells[4], fmtNum(r.px, r.px >= 100 ? 2 : 4));
      if (r.pnl != null) {
        var w = r.pnl >= 0;
        setLive(tr.cells[6], '<span class="' + (w ? "up" : "down") + '">' +
          (w ? "+" : "−") + fmtNum(Math.abs(r.pnl), 2) + "</span>");
      }
    });
  }

  function setLive(cell, html) {
    var el = cell.querySelector(".tl-live");
    if (!el) {
      el = document.createElement("div");
      el.className = "tl-live sub";
      el.style.fontSize = "11px";
      cell.appendChild(el);
    }
    el.innerHTML = "지금 " + html;
  }

  root.TrackLive = { markLive: markLive, equityFromCash: equityFromCash,
                     start: start, signedQty: signedQty,
                     fetchCrypto: fetchCrypto, fetchStocks: fetchStocks };
})(typeof globalThis !== "undefined" ? globalThis : this);
