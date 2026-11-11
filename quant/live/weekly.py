"""주간 리포트 — 주간 수익 셈·아카이브·텔레그램 문구 (감사 381로 `daily.py`에서 분리).

동작은 한 칸도 안 바꿨다. 함수 본문은 옮기기 전 그대로이고, `daily.py`가 같은
이름으로 다시 내보내므로 부르는 쪽(`from quant.live.daily import weekly_summary`)은
그대로다.

⚠️ `_generation_info`는 `daily.py`에 남아 있어 **부르는 자리에서** 가져온다 —
   모듈 머리에서 가져오면 `daily → weekly → daily` 순환이 된다.
"""
from __future__ import annotations

import json
import os

from quant.live.ledger_basics import _flows_by_date, chrono, ledger_files
from quant.live.retrain import STATE_DIR


def _week_base_principal(st: dict, first_date: str) -> float:
    """계좌가 그 주를 시작할 때 갖고 있던 원금 (감사 241).

    **시작금 그 자체**다. 입금을 여기 더하면 안 된다 — 계좌에 기록이 하나도
    없던 시절의 입금은 필연적으로 첫 기록의 자산에 들어가 있고, 주간 수익
    계산의 `flows`가 그 첫 기록에서 이미 빼 준다. 둘 다 하면 두 번 세는 것이
    되어 **입금이 통째로 손실로 보인다**(실측: -92%).

    시작금을 모르면 첫 기록의 자산으로 물러난다 — 옛 장부는 그 필드가
    없을 수 있고, 그때는 지금까지와 같은 값이 나온다(하위 호환).
    """
    del first_date          # 규칙이 날짜에 의존하지 않는다는 것을 명시
    try:
        base = float(st.get("start_cash"))
    except (TypeError, ValueError):
        return float(st["history"][0]["equity"])
    return base if base > 0 else float(st["history"][0]["equity"])


def _window_return(hist: list, window: list, st: dict) -> tuple[float, list]:
    """구간 수익률(%)과 (날짜, 그날 %) 목록 — **주간 셈은 여기 한 곳에서 한다.**

    ⚠️ 이 셈이 두 벌이었다(감사 246). 텔레그램 주간 리포트는 여기(파이썬),
       공개 주간 아카이브 페이지는 자기 자바스크립트 복사본을 갖고 있었고,
       그 복사본은 아예 **다른 값**을 쓰고 있었다:

           const ret = cur.day_pct != null ? cur.day_pct : ...

       `day_pct`는 **그 주 마지막 날 하루치**다. 열 제목은 "주간 수익률"인데
       매주 마지막 하루를 주간 성적으로 내보내고 있었다. 실측(2026-08-10 주):

           아카이브 페이지  **+0.02%**   ← 08-14 하루치
           사실(원금 대비)  **-0.02%**

       **부호가 반대다.** 감사 241에서 파이썬 쪽을 고쳤는데, 같은 병을 가진
       화면 쪽은 그대로 남아 있었다 — 형제를 안 찾은 자리다(㉞ 같은 판정을
       두 곳에서 쓰면 언젠가 갈라진다).

    규칙(감사 241과 같다):
      · 기준선은 창 직전 마지막 기록. 없으면 **원금**(첫날 손익이 사라지지
        않게).
      · 입금은 수익이 아니다 — 그날 유입액을 빼고 구간수익을 연쇄 곱한다.
      · 입금 귀속은 `_flows_by_date`가 **전체 기록**으로 잡는다.
    """
    idx0 = hist.index(window[0])
    base = (hist[idx0 - 1]["equity"] if idx0 > 0
            else _week_base_principal(st, window[0]["date"]))
    src = hist                  # 귀속은 창이 아니라 **전체 기록**(감사 241)
    flows = _flows_by_date(src, st.get("deposits") or [])
    days_chg: list = []
    chain, prev = 1.0, base
    for r in window:
        if prev:
            r_t = (float(r["equity"]) - flows.get(r["date"], 0.0)) / prev - 1
            chain *= 1.0 + r_t
            days_chg.append((r["date"], r_t * 100))
        prev = float(r["equity"])
    return ((chain - 1) * 100 if base else 0.0), days_chg


def _monday_of(day: str) -> str:
    """그 날짜가 속한 주의 월요일(ISO) — 화면과 배치가 같은 주 경계를 쓴다."""
    from datetime import date, timedelta

    d = date.fromisoformat(str(day)[:10])
    return (d - timedelta(days=d.weekday())).isoformat()


def weekly_archive(state_dir: str = STATE_DIR, weeks: int = 52) -> dict:
    """주 단위 아카이브 — 계좌별 {월요일: {수익률·자산·입금}} (감사 246).

    공개 주간 아카이브 페이지가 읽는 재료다. **페이지는 이제 계산하지 않고
    읽기만 한다** — 같은 판정을 두 곳에서 하면 언젠가 갈라지고, 실제로
    갈라져 있었다(위 `_window_return` 참고).
    """
    from datetime import date

    out: dict = {}
    for path in ledger_files(state_dir):
        try:
            with open(path, encoding="utf-8") as f:
                st = json.load(f)
        except (OSError, ValueError):
            continue
        hist = chrono(st.get("history") or [])
        if not hist:
            continue
        key = f"{st.get('market', '?')}:{st.get('symbol', '?')}"
        deposits = st.get("deposits") or []
        by_week: dict = {}
        for r in hist:
            by_week.setdefault(_monday_of(r["date"]), []).append(r)
        rows: dict = {}
        for wk in sorted(by_week)[-weeks:]:
            window = by_week[wk]
            ret, _ = _window_return(hist, window, st)
            dep = 0.0
            for d in deposits:
                when = d.get("settled_bar") or d.get("date")
                try:
                    if _monday_of(when) == wk:
                        dep += float(d.get("amount") or 0.0)
                except (TypeError, ValueError):
                    continue
            rows[wk] = {"return_pct": round(ret, 2),
                        "equity": window[-1].get("equity"),
                        "deposit": round(dep, 2) or None,
                        "n_days": len(window)}
        if rows:
            out[key] = rows
    del date
    return out


def weekly_summary(state_dir: str = STATE_DIR, days: int = 7) -> dict:
    """최근 7일(기록 기준) 요약 — 시장별 수익률·최고/최악일·챔피언 교체 이력.

    기준일은 벽시계가 아니라 '기록의 마지막 날짜'다 — 재실행해도 같은 결과가
    나오고(멱등), 데이터가 없는 날을 오늘로 착각하지 않는다.
    """
    from datetime import date, timedelta

    markets: dict = {}
    anchor: date | None = None
    states = []
    # 보관된 옛 장부는 살아 있는 계좌가 아니다(감사 212) — ledger_files가 뺀다
    for path in ledger_files(state_dir):
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
        if st.get("history"):
            states.append(st)
            d = date.fromisoformat(st["history"][-1]["date"])
            anchor = d if anchor is None else max(anchor, d)
    if anchor is None:
        return {"period": None, "markets": {}, "swaps": []}
    start = anchor - timedelta(days=days - 1)

    for st in states:
        key = f"{st.get('market', '?')}:{st.get('symbol', '?')}"
        hist = chrono(st["history"])          # 시간순 전제 — 배열 순서를 믿지 않는다
        window = [r for r in hist if date.fromisoformat(r["date"]) >= start]
        if not window:
            continue
        # 주간 수익 기준점: 창 직전 마지막 기록.
        #
        # ⚠️ **직전 기록이 없으면 원금이 기준이다**(2026-08-14 감사 241).
        #    예전에는 `window[0]["equity"]`, 즉 **첫 기록 자기 자신**을 기준
        #    으로 삼았다. 그러면 첫날 수익이 항상 0이 되고, 계좌가 문을 연
        #    첫 주의 성적에서 첫날의 움직임이 통째로 빠진다.
        #
        #    실측(원화 계좌 첫 주, 원금 1,000,000원):
        #        기록      999,635.06 → 999,847.15
        #        리포트    주간 **+0.02%** · 최악일 08-13 **+0.00%**
        #        사실      주간 **-0.0153%** · 최악일 08-13 **-0.0365%**
        #    **부호가 반대다.** 이 리포트는 월요일 아침 텔레그램으로 나간다.
        #
        #    감사 239(낙폭이 원금을 고점으로 안 친다)와 **같은 병**이다 —
        #    기준선에서 원금이 빠지면 첫날 손실이 사라진다.
        #
        #    창 시작 **전에** 정산된 입금은 그때 이미 자산에 들어가 있으므로
        #    기준에 더한다. 창 **안에서** 정산된 입금은 아래 `flows`가 따로
        #    빼므로 여기서 더하면 두 번 세는 것이 된다.
        # 이 셈은 `_window_return`이 한 곳에서 한다(감사 246) — 주간 아카이브
        # 페이지가 자기 복사본을 갖고 있다가 갈라진 자리다.
        # 입금은 수익이 아니다 — 자산 비율만 쓰면 매칭입금이 주간 수익으로
        # 둔갑한다(2026-08-11 감사에서 발견). TWR과 같은 규칙으로 그날의
        # 유입액을 빼고 구간수익을 연쇄 곱한다. 입금 날짜가 기록일 사이면
        # '그 이후 첫 기록일'에 귀속시킨다.
        # ⚠️ 귀속 규칙을 **여기서 다시 쓰지 않는다**(감사 219). 감사 211에서
        #    "입금은 날짜가 아니라 배치가 찍은 봉(settled_bar)으로 귀속한다"로
        #    바꾸면서 `_flows_by_date` 한 곳에 모았는데, 주간 요약만 자기
        #    복사본을 그대로 갖고 있었다. 그리고 이미 갈라져 있었다 —
        #    실측(입금 08-13 / 정산 봉 08-12):
        #        주간 요약  : +1149.06%   ← 92만원 입금이 '수익'
        #        장부(TWR) :    -0.94%
        #    이 숫자는 월요일 아침 주간 리포트로 나간다.
        # ⚠️ 귀속은 **전체 기록**으로 잡는다(감사 241). 창만 넘기면 창보다
        #    오래된 입금이 "창 첫 기록"으로 끌려와 그 주의 수익에서 빠진다 —
        #    그 돈은 이미 창 이전 자산에 들어가 있으므로 두 번 빼는 것이다.
        #    실측: 시작금 8만 + 08-01 입금 92만인 계좌의 첫 주가 **-92%**.
        week_ret, days_chg = _window_return(hist, window, st)
        best = max(days_chg, key=lambda x: x[1]) if days_chg else None
        worst = min(days_chg, key=lambda x: x[1]) if days_chg else None
        markets[key] = {
            "week_return_pct": round(week_ret, 2),
            "equity": window[-1]["equity"],
            "total_return_pct": window[-1].get("return_pct"),
            "n_days": len(window),
            "best_day": best and {"date": best[0], "pct": round(best[1], 2)},
            "worst_day": worst and {"date": worst[0], "pct": round(worst[1], 2)},
        }

    swaps = []
    # vacuous = **대결이 열리지 않은** 오디션. '승격 0회'와 전혀 다른 상태다 —
    # 후보가 못 이긴 것이 아니라 비교 자체가 성립하지 않은 것이다. 이 숫자는
    # 사이트(retrain_recent)에는 실려 있었지만 **주간 보고서에는 없었다**.
    # 사장님에게 실제로 도착하는 문서가 그 구별을 못 하면 없는 것과 같다.
    auditions = {"runs": 0, "candidates": 0, "promoted": 0, "vacuous": 0}
    hist_file = os.path.join(state_dir, "retrain_history.jsonl")
    if os.path.exists(hist_file):
        with open(hist_file, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not rec.get("asof"):
                    continue
                try:
                    in_window = date.fromisoformat(rec["asof"]) >= start
                except ValueError:
                    continue
                if not in_window:
                    continue
                # 이번 주 오디션 통계 — 몇 명이 도전해 몇 명이 승격했나
                auditions["runs"] += 1
                auditions["candidates"] += int(rec.get("n_candidates") or 0)
                if rec.get("vacuous"):
                    auditions["vacuous"] += 1
                if rec.get("promoted"):
                    auditions["promoted"] += 1
                    swaps.append({"asof": rec["asof"],
                                  "market": rec.get("market"),
                                  "symbol": rec.get("symbol"),
                                  "champion": rec.get("champion"),
                                  "strategy": rec.get("champion_strategy")})

    # 시스템 건강 — 수익률 밖의 상태(판정 시계·체결 가정·킬스위치)를 함께.
    # 주간 요약은 "이번 주 시스템 건강 보고서"다 — 숫자 자랑이 아니라.
    health: dict = {"auditions": auditions}
    # 굴린 자본 — **자산이 아니라 노출**. 100만원을 1억으로 만들겠다면서
    # 자본의 절반이 늘 현금이면 그 사실이 매주 눈에 보여야 한다. 이 숫자는
    # 장부에 계속 있었지만(`weight`) 어떤 보고서도 읽지 않았다.
    for st in states:
        if st.get("market") == "portfolio" and st.get("history"):
            w = [float(r["weight"]) for r in chrono(st["history"])[-days:]
                 if r.get("weight") is not None]
            if w:
                health["deployed"] = {
                    "gross_mean": round(sum(w) / len(w), 4),
                    "gross_last": round(w[-1], 4),
                    "n_days": len(w),
                }
    from quant.live.daily import _generation_info      # 지연 — 순환 방지
    gen = _generation_info(state_dir)
    if gen:
        health["generation"] = gen
    try:
        from quant.reporting.fill_gap import fill_gap_report
        fg = fill_gap_report(state_dir)
        if fg:
            health["fill_check"] = fg
    except Exception:  # noqa: BLE001 — 건강 항목 실패가 요약을 막으면 안 된다
        pass
    for st in states:
        if st.get("market") == "portfolio" and st.get("history"):
            last = st["history"][-1]
            rs = last.get("risk_scale")
            if rs is not None and float(rs) < 1.0:
                health["killswitch"] = {
                    "risk_scale": float(rs),
                    "drawdown_pct": last.get("drawdown_pct")}
    return {"period": [str(start), str(anchor)], "markets": markets,
            "swaps": swaps, "health": health}


def format_weekly(summary: dict) -> str:
    """weekly_summary 결과를 사람이 읽는 한국어 요약으로 만든다(텔레그램/콘솔 공용)."""
    if not summary.get("markets"):
        return "📭 지난주 페이퍼 기록이 없습니다."
    a, b = summary["period"]
    lines = [f"🗓️ 주간 요약 ({a} ~ {b}) — 가상 100만 챌린지"]
    for key, m in summary["markets"].items():
        # ⚠️ **화살표는 화면에 찍히는 숫자와 같은 값을 봐야 한다**
        #    (감사 241에서 함께 발견). 예전에는 원본 값의 부호를 썼는데,
        #    파이썬의 음의 0(-0.0)은 `>= 0`이 참이면서 `+.2f`로는 "-0.00"
        #    으로 찍힌다. 실제로 그렇게 나갔다 — "🔺 QQQ: 주간 -0.00%".
        #    화면이 스스로 모순되면 나머지 숫자도 함께 의심받는다.
        shown = round(m["week_return_pct"], 2) + 0.0    # -0.0 → 0.0
        sign = "🔺" if shown > 0 else ("🔻" if shown < 0 else "➖")
        line = (f"{sign} {key}: 주간 {m['week_return_pct']:+.2f}% · "
                f"자산 {m['equity']:,.0f} (누적 {m['total_return_pct']:+.2f}%)")
        if m.get("worst_day"):
            line += f" · 최악일 {m['worst_day']['date']} {m['worst_day']['pct']:+.2f}%"
        lines.append(line)
    if summary["swaps"]:
        for s in summary["swaps"]:
            lines.append(f"🔁 챔피언 교체: {s['market']}/{s['symbol']} → "
                         f"{s.get('strategy', '')} {s['champion']} ({s['asof']})")
    else:
        lines.append("🏆 챔피언 교체 없음 — 확실히 나은 후보가 없었다는 뜻(정상)")

    # 시스템 건강 보고 — 수익률 밖의 상태를 사이트 안 열어도 알 수 있게
    h = summary.get("health") or {}
    g = h.get("generation")
    if g:
        lines.append(f"🕰 판정 시계: 구조 {g['feature_set']} 관찰 "
                     f"{g['days']}일차/{g['target_days']}일 — 시계가 다 돌기 "
                     f"전의 수익률은 판정 근거가 아닙니다")
    a = h.get("auditions")
    if a and a["runs"]:
        lines.append(f"🎭 오디션: 이번 주 {a['runs']}회 · 후보 "
                     f"{a['candidates']}명 중 승격 {a['promoted']}회")
        # '승격 0회'는 정상일 수 있지만 '대결이 안 열림'은 절대 정상이 아니다.
        if a.get("vacuous"):
            lines.append(f"   ⚠️ 그중 {a['vacuous']}회는 **대결 자체가 열리지 "
                         "않았습니다** — 승격 없음이 아니라 심사 없음입니다")
    dep = h.get("deployed")
    if dep:
        lines.append(
            f"💰 굴린 자본: 평균 {dep['gross_mean']:.0%} · 최근 "
            f"{dep['gross_last']:.0%} (나머지는 현금 · {dep['n_days']}일 기준)")
    fc = h.get("fill_check")
    if fc:
        for mk, r in (fc.get("markets") or {}).items():
            mark = " ⚠️ 가정 초과(백테스트 낙관 의심)" if r["optimistic"] else ""
            lines.append(f"🧾 체결 검증 {mk}: 불리 갭 평균 "
                         f"{r['mean_adverse_bp']:+.1f}bp vs 가정 "
                         f"{r['assumed_bp']:.1f}bp (표본 {r['n']}건){mark}")
    ks = h.get("killswitch")
    if ks:
        lines.append(f"🛡 킬스위치 발동 중: 노출 {ks['risk_scale'] * 100:.0f}%"
                     + (f" (낙폭 {ks['drawdown_pct']}%)"
                        if ks.get("drawdown_pct") is not None else ""))
    lines.append("⚠️ 페이퍼(모의) 운용 — 실제 돈이 아니며 수익 보장이 아닙니다.")
    return "\n".join(lines)
