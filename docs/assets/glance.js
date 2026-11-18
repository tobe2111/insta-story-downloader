/**
 * 한눈에 카드 — 트랙 페이지 셋(코인 단타 · 미국 단타 · 코인 선물)의 첫 카드 (2026-11-18).
 *
 * 사장님: "이 4개 페이지 모두 좀 일관성이 있어야하지 않겠어? … 지금 모두 다
 * 무슨 말을 하는지도 모르겠고"
 *
 * 그때까지 세 페이지는 첫 화면이 시즌 이력 · 긴 설명 · 실험 세부로 시작했고,
 * "그래서 지금 얼마인가"는 몇 번 내려가야 나왔다. 100만 챌린지는 이미 '한눈에'
 * 카드로 시작한다. 이 파일이 같은 질문에 **같은 순서·같은 말**로 답한다:
 *
 *   이 계좌는 무엇을 하나 → 넣은 돈 → 지금 → 이익/손해 → 이미 낸 비용 →
 *   같은 기간 그냥 들고만 있었다면 → 지금 기계가 고른 방식 → 다음 공식 판정
 *
 * ⚠️ 계산하지 않는다 — 장부(JSON)에 이미 있는 값만 옮긴다. 화면이 자기 계산을
 *    시작하면 장부와 갈라진다(감사 197).
 * ⚠️ '지금'은 **운용 계좌**(기계가 실제로 고른 방식으로 굴리는 계좌)다. 실험
 *    계좌(사전 등록 규칙대로 계속 매매)는 비교용으로 아래 한 줄에 적는다.
 * ⚠️ 이 페이지들은 완역 대상이다 — 한국어 조각은 하나씩 따로 두고 숫자와 섞지
 *    않는다(번역기는 텍스트 조각을 통째로 찾는다).
 *
 * 쓰는 법: <div class="card" data-glance="intraday.json" data-prereg="intraday_s2"
 *          data-unit="USDT"></div>
 *
 * 같은 파일이 '간단히 / 자세히' 스위치도 단다 — 100만 챌린지와 같은 열쇠
 * (`quant.detail`)를 쓰므로 한 페이지에서 고른 보기가 다른 페이지에도 이어진다.
 * 접는 것은 화면뿐이다. 숫자는 그대로 문서 안에 있다.
 */
(function () {
  "use strict";

  // 이 계좌는 무엇을 하나 — 한 문장. 장부 파일 이름으로 고른다.
  const WHAT = {
    "intraday.json":
      "코인 다섯 종목을 1시간마다 보고, 자주 사고파는 것이 그냥 들고 있는 것보다 나은지 가상 자금으로 잽니다.",
    "intraday_us.json":
      "미국 주식을 장이 열린 시간에만 1시간마다 보고, 자주 사고파는 것이 그냥 들고 있는 것보다 나은지 가상 자금으로 잽니다.",
    "futures.json":
      "코인 선물로 오를 때뿐 아니라 내릴 때도 걸 수 있는 계좌입니다. 가상 자금이고 최대 3배까지만 겁니다.",
  };

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function fmt(v, unit) {
    const n = Number(v);
    if (!isFinite(n)) return "—";
    return n.toLocaleString("en-US", { maximumFractionDigits: 2 }) + (unit ? " " + unit : "");
  }
  function pct(v) {
    const n = Number(v);
    if (!isFinite(n)) return "—";
    return (n > 0 ? "+" : "") + n.toFixed(2) + "%";
  }
  function tone(v) {
    const n = Number(v);
    return n > 0.004 ? "up" : n < -0.004 ? "down" : "";
  }
  // 한 칸: 라벨(한국어 조각) · 큰 값 · 작은 설명(선택)
  function cell(label, value, valueCls, note) {
    const c = el("div", "gl-cell");
    c.appendChild(el("div", "gl-k", label));
    c.appendChild(el("div", "gl-v " + (valueCls || ""), value));
    if (note) c.appendChild(el("div", "gl-n", note));
    return c;
  }
  // 한 줄: 라벨 + 값 조각들(한국어 조각과 숫자를 따로)
  function line(label, parts) {
    const p = el("div", "gl-line");
    p.appendChild(el("span", "gl-k", label));
    (parts || []).forEach(x => {
      p.appendChild(document.createTextNode(" "));
      p.appendChild(typeof x === "string" ? el("b", "", x) : x);
    });
    return p;
  }

  function style() {
    if (document.getElementById("glance-style")) return;
    const s = document.createElement("style");
    s.id = "glance-style";
    s.textContent =
      ".gl-what{font-size:14px;margin:6px 0 12px}" +
      ".gl-grid{display:flex;flex-wrap:wrap;gap:22px 30px;align-items:flex-end}" +
      ".gl-k{font-size:12px;color:var(--muted);font-weight:600}" +
      ".gl-v{font-size:20px;font-weight:800;letter-spacing:-.3px}" +
      ".gl-cell.main .gl-v{font-size:30px}" +
      ".gl-n{font-size:11.5px;color:var(--dim)}" +
      ".gl-line{font-size:13.5px;margin-top:8px}" +
      ".gl-line .gl-k{font-size:13px}" +
      ".gl-rows{margin-top:14px;padding-top:10px;border-top:1px solid var(--line)}" +
      ".adv{display:none}body.detail .adv{display:block}" +
      ".gl-more{margin-top:14px;width:100%;text-align:left;cursor:pointer;" +
      "background:var(--bg3);color:var(--fg);border:1px solid var(--line-strong);" +
      "border-radius:10px;padding:10px 14px;font:inherit;font-size:14px;font-weight:700}";
    document.head.appendChild(s);
  }

  function moreButton(host) {
    const KEY = "quant.detail";
    const btn = el("button", "gl-more");
    btn.type = "button";
    const apply = on => {
      document.body.classList.toggle("detail", on);
      btn.setAttribute("aria-expanded", on ? "true" : "false");
      btn.textContent = "";
      btn.appendChild(document.createTextNode(on ? "간단히 보기 ▴" : "자세히 보기 ▾"));
      btn.appendChild(document.createTextNode(" "));
      // 무엇이 접혀 있는지 이름으로 말한다(감사 282) — 안 그러면 아무도 안 누른다.
      btn.appendChild(el("span", "sub", "시즌 기록 · 운용 계좌 상세 · 실험 세부 · 판정 기준"));
    };
    let saved = null;
    try { saved = localStorage.getItem(KEY); } catch (e) { /* 저장소 없음 */ }
    apply(saved === "1");
    btn.onclick = () => {
      const on = !document.body.classList.contains("detail");
      apply(on);
      try { localStorage.setItem(KEY, on ? "1" : "0"); } catch (e) { /* 저장소 없음 */ }
    };
    host.insertAdjacentElement("afterend", btn);
    // 아래 표(들고 있는 것 · 체결 · 손익 · 곡선)는 **비교용 실험 계좌**의 장부다.
    // 위 큰 숫자는 운용 계좌다 — 말하지 않으면 "현금으로 쉬는데 왜 코인을 들고
    // 있나"가 된다(선물 운용 계좌가 실제로 그 상태다).
    const note = el("div", "sub gl-whose");
    note.style.marginTop = "18px";
    note.appendChild(el("b", "", "아래 표는 비교용 실험 계좌의 기록입니다"));
    note.appendChild(document.createTextNode(" — "));
    note.appendChild(el("span", "", "위 큰 숫자(기계가 운용하는 계좌)와 다른 계좌입니다."));
    btn.insertAdjacentElement("afterend", note);
  }

  function render(host, d, status) {
    const unit = host.getAttribute("data-unit") || d.currency || "";
    const o = d.operated || {};
    const start = Number(d.start_cash);
    const eq = Number(o.equity != null ? o.equity : d.equity);
    const ret = o.return_pct != null ? o.return_pct : d.return_pct;
    const cost = o.cost_paid != null ? o.cost_paid : d.cost_paid;
    host.textContent = "";

    const h = el("h2", "", "한눈에");
    h.style.marginTop = "0";
    h.appendChild(document.createTextNode(" "));
    h.appendChild(el("span", "tag", "가상 자금 · 실제 돈이 아닙니다"));
    host.appendChild(h);

    const what = WHAT[host.getAttribute("data-glance")];
    if (what) host.appendChild(el("p", "gl-what", what));

    const g = el("div", "gl-grid");
    if (isFinite(start)) {
      // 시작일은 운용 계좌의 것(실험 계좌의 since는 시즌이 다시 열릴 때 옮겨진다).
      const since = o.since || d.since;
      g.appendChild(cell("넣은 돈 (원금)", fmt(start, unit), "",
        since ? String(since).slice(0, 10) : null));
    }
    const mainCell = cell("지금 (기계가 운용하는 계좌)", fmt(eq, unit), tone(ret));
    mainCell.classList.add("main");
    g.appendChild(mainCell);
    if (isFinite(start) && isFinite(eq)) {
      const pnl = eq - start;
      g.appendChild(cell(pnl >= 0 ? "이익" : "손해",
        (pnl >= 0 ? "+" : "−") + fmt(Math.abs(pnl), unit) + " (" + pct(ret) + ")", tone(ret)));
    }
    // ⚠️ 낸 비용은 운용 계좌가 **체결 장부**일 때만 적는다. 선물 운용 계좌는 배분
    //    장부라 자기가 갈아탈 때 낸 비용만 세고, 이어받은 실험 계좌의 지난 비용은 안
    //    센다 — 그 숫자를 손해 옆에 두면 "비용을 거의 안 냈다"로 읽힌다.
    if (cost != null && (o.positions || !d.operated)) {
      g.appendChild(cell("이미 낸 비용", fmt(cost, unit), "", "수수료·미끄러짐 · 위 이익은 이걸 뺀 값"));
    }
    // ⚠️ '그냥 들고만 있었다면'(hold_return_pct)은 일부러 안 싣는다 — 그 값은 실험
    //    계좌의 기간(시즌이 다시 열리면 옮겨진다)으로 잰 것이라 위 손익과 같은 기간이
    //    아니다. 기간이 다른 두 숫자를 나란히 두면 비교가 아니라 착시다.
    host.appendChild(g);

    const rows = el("div", "gl-rows");
    if (o.mode_label) {
      const parts = [o.mode_label];
      if (o.mode_since) {
        const s = el("span", "sub");
        s.appendChild(el("span", "", "고른 날"));
        s.appendChild(document.createTextNode(" " + String(o.mode_since).slice(0, 10)));
        parts.push(s);
      }
      rows.appendChild(line("지금 기계가 고른 방식", parts));
      // 방식은 '그냥 보유'인데 실제로는 아무것도 안 들고 있을 수 있다 — 손실 한도
      // 브레이크(고점 대비 −25%)가 전부 팔면 그렇다. 방식 이름만 적으면 거짓이 된다.
      if (o.mode !== "cash" && o.positions && typeof o.positions === "object"
          && Object.keys(o.positions).length === 0) {
        const w = el("div", "warn");
        w.style.marginTop = "6px";
        w.appendChild(el("b", "", "지금은 아무것도 들고 있지 않습니다 (전부 현금)"));
        w.appendChild(document.createTextNode(" — "));
        w.appendChild(el("span", "", "손실이 커지면 스스로 물러나는 브레이크가 걸려 있습니다."));
        rows.appendChild(w);
      }
      rows.appendChild(el("div", "gl-n",
        "기계가 최근 성적을 견줘 방식을 고릅니다 — 우연이 아닐 만큼 앞서야 바꿉니다."));
    }
    const se = d.season || {};
    if (se.n != null && se.operated_return_pct != null) {
      const s = el("span", "sub");
      s.appendChild(el("span", "", "시작"));
      s.appendChild(document.createTextNode(" " + String(se.since || "").slice(0, 10)));
      const v = el("b", tone(se.operated_return_pct), pct(se.operated_return_pct));
      rows.appendChild(line("이번 시즌 성적", [v, s]));
    }
    if (o.equity != null && d.equity != null) {
      rows.appendChild(line("비교용 실험 계좌 (규칙대로 계속 사고파는 계좌)",
        [fmt(d.equity, unit), el("b", tone(d.return_pct), "(" + pct(d.return_pct) + ")")]));
    }
    const key = host.getAttribute("data-prereg");
    const exps = (((status || {}).prereg || {}).experiments) || {};
    const judge = key && exps[key] && exps[key].judge_on;
    if (judge) rows.appendChild(line("다음 공식 판정", [String(judge)]));
    const when = d.last_time || d.updated;
    if (when) {
      const t = el("div", "gl-n");
      t.appendChild(el("span", "", "마지막 갱신"));
      t.appendChild(document.createTextNode(" " + String(when).replace("T", " ").slice(0, 16)));
      rows.appendChild(t);
    }
    host.appendChild(rows);
  }

  function init() {
    style();
    document.querySelectorAll("[data-glance]").forEach(host => {
      moreButton(host);
      const src = host.getAttribute("data-glance");
      Promise.all([
        fetch(src, { cache: "no-store" }).then(r => r.json()),
        fetch("status.json", { cache: "no-store" }).then(r => r.json()).catch(() => null),
      ]).then(([d, st]) => render(host, d, st)).catch(() => {
        host.textContent = "";
        host.appendChild(el("span", "err", "불러오지 못했습니다."));
      });
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
