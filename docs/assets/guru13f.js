/* 저명 투자자 13F 카드 — **모든 공개 페이지가 같은 한 벌**을 쓴다.
 *
 * 사장님 지시(2026-10-01): "13F 관련 내용도 홈페이지 각 페이지들에 보여야 해."
 *
 * 쓰는 법: 페이지에 <div data-guru13f></div> 하나를 두고 이 파일을 싣는다.
 * 숫자는 여기서 계산하지 않는다 — 배치가 status.json의 `guru13f`에 실어
 * 보낸 값을 그리기만 한다(화면이 자기 계산을 시작하면 장부와 갈라진다).
 *
 * ⚠️ **빈 칸의 이유를 말한다**(감사 331). 출시 후 이 칸은 줄곧 비어 있었는데
 *    원인은 "아무도 안 샀다"가 아니라 "SEC 서버가 요청 과다(429)로 막았다"
 *    였다. 둘은 화면에서 똑같이 비어 보인다 — 그래서 수집 상태를 먼저 적는다.
 *
 * ⚠️ 한국어 조각은 **값과 다른 텍스트 노드**에 둔다. 번역기는 노드를 통째로
 *    사전에서 찾는다 — 숫자가 섞인 문장은 사전 열쇠가 매일 바뀐다.
 */
(function (root) {
  "use strict";

  var CSS =
    ".g13{border:1px solid var(--line,#ddd);border-radius:10px;padding:14px 16px;" +
    "margin:14px 0;background:var(--bg2,transparent);color:var(--fg,inherit);" +
    "font-size:14px;line-height:1.6}" +
    ".g13 h2{font-size:16px;margin:0 0 6px}" +
    ".g13 .sub{color:var(--muted,#777);font-size:12.5px}" +
    // ⚠️ 이름이 `g13-`로 시작한다 — 페이지마다 `.warn`이 상자 모양으로 따로
    //    정의돼 있어, 같은 이름을 쓰면 칩 안의 ▼가 노란 상자가 된다.
    ".g13 .g13-warn{color:var(--down,#c0392b)}.g13 .g13-up{color:var(--up,#16a34a)}" +
    ".g13 .chips{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}" +
    ".g13 .chip{border:1px solid var(--line,#ddd);border-radius:999px;padding:2px 10px;" +
    "font-size:13px}" +
    ".g13 .tw{overflow-x:auto;-webkit-overflow-scrolling:touch}" +
    ".g13 table{border-collapse:collapse;width:100%;font-size:13px;margin-top:6px}" +
    ".g13 th,.g13 td{border-bottom:1px solid var(--line,#eee);padding:5px 6px;" +
    "text-align:left;white-space:nowrap}" +
    ".g13 ul{margin:6px 0 0;padding-left:18px}" +
    ".g13 details{margin-top:8px}.g13 summary{cursor:pointer}";

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.appendChild(document.createTextNode(String(text)));
    return e;
  }

  /* 한 줄을 [한국어 조각, 값, 한국어 조각 …] 으로 만든다 — 노드가 갈린다. */
  function line(cls, parts) {
    var p = el("div", cls);
    parts.forEach(function (x) {
      if (x == null || x === "") return;
      if (typeof x === "object" && x.b != null) p.appendChild(el("b", null, x.b));
      else p.appendChild(el("span", null, x));
    });
    return p;
  }

  function statusLine(g) {
    var f = g.fetch || {};
    var pts = Number(g.history_points) || 0;
    if (!f.on) {
      return line("sub g13-warn", ["아직 수집 기록이 없습니다 — 밤 배치가 처음 받아 오면 여기에 채워집니다."]);
    }
    if (pts === 0) {
      return line("sub g13-warn", ["마지막 수집이 실패했습니다", " · ", {b: f.on},
        " · ", f.last_error || "", " — ",
        "받지 못한 것을 '아무도 안 샀다'로 그리지 않습니다."]);
    }
    var parts = ["마지막 수집", " ", {b: f.on}, " · ", "투자자", " ",
                 {b: (f.filers_seen || 0) + "/" + (f.filers_total || 0)}];
    if (f.kept_previous) parts.push(" · ", "오늘은 일부를 못 받아 이전 기록을 유지합니다");
    return line("sub", parts);
  }

  function render(box, g) {
    box.innerHTML = "";
    var card = el("div", "g13");
    card.appendChild(el("h2", null, "저명 투자자 13F — 큰손들이 공시한 미국주식 보유"));
    card.appendChild(line("sub", [
      "13F는 1억 달러 넘게 굴리는 기관이 분기마다 미국 증권거래위원회(SEC)에 내는 보유 목록입니다. 우리는 그중 여러 명이 같은 종목을 함께 들고 있는지(겹쳐 담기)만 봅니다."]));
    card.appendChild(statusLine(g));

    var names = g.names || [];
    if (names.length) {
      card.appendChild(line(null, ["우리 미국 종목 중 겹쳐 담긴 종목"]));
      var chips = el("div", "chips");
      names.forEach(function (r) {
        var c = el("span", "chip");
        c.appendChild(el("b", null, r.symbol));
        c.appendChild(document.createTextNode(" "));
        var tot = (g.fetch && g.fetch.filers_total) || g.filers_total || "";
        c.appendChild(el("span", null, String(r.count) + (tot ? "/" + tot : "")));
        // 직전 분기 대비 흐름 — 담은 사람 ▲ · 줄이거나 판 사람 ▼ (감사 333)
        if (Number(r.buy) > 0) c.appendChild(el("span", "g13-up", " ▲" + r.buy));
        if (Number(r.sell) > 0) c.appendChild(el("span", "g13-warn", " ▼" + r.sell));
        chips.appendChild(c);
      });
      card.appendChild(chips);
      card.appendChild(line("sub", ["▲ 직전 분기보다 새로 담거나 늘린 투자자 수 · ▼ 줄이거나 판 투자자 수"]));
    } else if ((Number(g.history_points) || 0) > 0) {
      card.appendChild(line("sub", ["지금 우리 미국 종목을 들고 있는 저명 투자자는 없습니다."]));
    }

    var exited = g.exited || [];
    if (exited.length) {
      card.appendChild(line("sub", ["직전 분기에 들고 있다가 이번 공시에서 모두 판 종목", " ", {b: exited.join(", ")}]));
    }

    var filers = g.filers || [];
    if (filers.length) {
      var tw = el("div", "tw");
      var t = el("table");
      var hr = el("tr");
      ["투자자", "마지막 공시일", "기준 분기말", "우리 종목 중 보유", "새로 담거나 늘림", "줄이거나 판 종목"].forEach(function (h) {
        hr.appendChild(el("th", null, h));
      });
      t.appendChild(hr);
      filers.forEach(function (r) {
        var tr = el("tr");
        var nm = el("td", null, r.name);
        if (r.stale) {
          // 공시가 멈춘 투자자 — 묵은 보유를 지금 든 것처럼 세지 않는다.
          nm.appendChild(document.createTextNode(" "));
          nm.appendChild(el("span", "sub g13-warn", "(공시 멈춤 — 집계 제외)"));
        }
        tr.appendChild(nm);
        tr.appendChild(el("td", null, r.filed || "—"));
        tr.appendChild(el("td", null, r.report || "—"));
        tr.appendChild(el("td", null, (r.holds && r.holds.length) ? r.holds.join(", ") : "—"));
        tr.appendChild(el("td", null, (r.bought && r.bought.length) ? r.bought.join(", ") : "—"));
        tr.appendChild(el("td", null, (r.sold && r.sold.length) ? r.sold.join(", ") : "—"));
        t.appendChild(tr);
      });
      tw.appendChild(t);
      card.appendChild(tw);
      var opts = filers.reduce(function (a, r) { return a + (Number(r.options_excluded) || 0); }, 0);
      if (opts > 0) {
        card.appendChild(line("sub", ["옵션(풋·콜) 줄은 보유로 세지 않았습니다", " ",
          {b: String(opts)}, " ", "줄 — 풋옵션은 하락에 거는 것이라 '들고 있다'와 반대입니다."]));
      }
    }
    var unv = (g.fetch && g.fetch.unverified) || [];
    if (unv.length) {
      card.appendChild(line("sub g13-warn", ["SEC에 등록된 이름이 맞지 않아 뺀 투자자 번호", " ",
        {b: unv.map(function (u) { return u.cik || u; }).join(", ")}]));
    }

    var d = el("details");
    d.appendChild(el("summary", null, "이 정보를 어디에 어떻게 쓰나"));
    var ul = el("ul");
    (g.uses || []).forEach(function (u) {
      var li = el("li");
      li.appendChild(el("b", null, u.where));
      li.appendChild(document.createTextNode(" — "));
      li.appendChild(el("span", null, u.how));
      ul.appendChild(li);
    });
    var li2 = el("li");
    li2.appendChild(el("span", null, "장중 실험이 지금 13F로 키우는 최대 폭"));
    li2.appendChild(document.createTextNode(" "));
    li2.appendChild(el("b", null, "+" + (g.strength_pct != null ? g.strength_pct : 15) + "%"));
    if (g.strength_why) {
      li2.appendChild(document.createTextNode(" — "));
      li2.appendChild(el("span", null, g.strength_why));
    }
    ul.appendChild(li2);
    d.appendChild(ul);
    if (g.caveat) d.appendChild(line("sub", ["⚠️ ", g.caveat]));
    card.appendChild(d);
    box.appendChild(card);
  }

  function boot() {
    var boxes = document.querySelectorAll("[data-guru13f]");
    if (!boxes.length) return;
    if (!document.getElementById("g13-css")) {
      var st = document.createElement("style");
      st.id = "g13-css";
      st.textContent = CSS;
      document.head.appendChild(st);
    }
    fetch("status.json").then(function (r) { return r.ok ? r.json() : null; })
      .then(function (s) {
        var g = s && s.guru13f;
        Array.prototype.forEach.call(boxes, function (b) {
          if (g) render(b, g);
          else b.innerHTML = "";        // 배치가 아직 이 칸을 안 실었다 — 빈 상자로 두지 않는다
        });
      })
      .catch(function () {});
  }

  root.Guru13F = {render: render};
  if (typeof document === "undefined") return;   // node 검사에서 불러올 때
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})(typeof window !== "undefined" ? window : this);
