"""머신러닝이 실제로 어떻게 돌고 있는가 — 화면이 읽을 재료를 모은다.

사장님 지시(2026-08-24): *"지금까지 계속 투자하면서 머신러닝 잘 돌아가고
있는지 확인해줘"*, *"홈페이지에 머신러닝 전용 페이지도 만들어야겠는데?
히스토리나 검증 결과 등에 대해서도 보이면 좋지 않을까? 어떠한 구조로
머신러닝이 되는지 등 말이야."*

■ 이 파일이 지키는 것

  · **숫자는 전부 장부에서 센다.** 이 모듈은 아무것도 예측하지 않고,
    이미 일어난 일을 세기만 한다. 화면이 자기 계산을 시작하면 장부와
    갈라진다(감사 197).
  · **모르는 것은 None이다.** 표본이 없으면 비운다. 0으로 적으면
    '0%였다'는 뜻이 되고, 그건 사실이 아니다.
  · **나쁜 숫자를 빼지 않는다.** 이 제품의 정체성은 선택 편향 없는 공개
    실험이다. 적중률이 우연과 구별 안 되면 그렇게 적는다.

■ 왜 '인샘플'과 '실전'을 나눠 세나

모델이 이미 본 구간에서 잘 맞히는 것은 실력의 증거가 아니다. 시험 문제를
미리 본 학생의 점수와 같다. **실전(OOS)**은 모델이 학습에 쓰지 않은
날짜에, 실제로 돈이 걸린 상태에서 내린 판단만 센 것이다. 둘을 한 숫자로
합치면 좋은 쪽이 나쁜 쪽을 가린다(감사 240에서 실제로 그랬다).

■ 왜 '보정'을 따로 재나

적중률만 보면 "반은 맞힌다"에서 멈춘다. 그런데 이 시스템은 확률을 **금액**
으로 바꾼다 — 0.70이라고 말하면 그만큼 크게 산다. 그러니 "0.70이라고 말한
날 정말 70% 올랐나"가 적중률보다 중요하다. 확신할 때 더 틀린다면, 크게
거는 판단일수록 더 자주 틀린다는 뜻이다.
"""
from __future__ import annotations

import json
import math
import os

# 확률이 이보다 높으면 '모델이 오른다고 본 판단', 낮으면 '내린다고 본 판단'.
# 두 무리의 실제 상승률을 비교하면 방향을 아는지가 한 줄로 드러난다.
CONFIDENT_UP = 0.60
CONFIDENT_DOWN = 0.40

# 학습 때 본 데이터와 지금 데이터가 얼마나 다른가(PSI). 업계 관행선.
PSI_NOTABLE = 0.25


def _paper_files(state_dir: str = "state") -> list:
    """살아 있는 종목별 장부만.

    ⚠️ 목록을 **직접 훑지 않는다**(감사 228). 여기서 `glob`을 쓰면 보관본
       (archive)이 섞이고, 같은 기록이 두 번 세어져 표본 수 n만 부푼다.
       그런데 윌슨 하한은 n이 커질수록 올라간다 — 즉 사본 하나가
       "동전과 구별 불가"를 "엣지 입증"으로 뒤집는다. 하필 이 모듈이
       그 판정을 화면에 그리는 곳이다.

       이 검사는 사람의 기억이 아니라 검사가 지킨다
       (tests/test_an_archive_is_not_a_second_account.py).
    """
    from quant.live.ledger_basics import ledger_files
    return [f for f in ledger_files(state_dir)
            # 통합 계좌는 종목별 모델 기록이 아니다 — 세면 이중 계산이다.
            if not os.path.basename(f).startswith("portfolio")]


def _histories(state_dir: str = "state") -> list:
    out = []
    for f in _paper_files(state_dir):
        try:
            h = (json.load(open(f, encoding="utf-8")).get("history") or [])
        except (OSError, ValueError):
            continue        # 못 읽는 장부는 없는 셈 친다 — 지어내지 않는다
        if h:
            out.append((os.path.basename(f)[:-5], h))
    return out


def _wilson(hits: int, n: int) -> tuple:
    """윌슨 신뢰구간 — **공용 규칙을 빌려 쓴다.**

    ⚠️ 여기에 식을 베껴 적으면 안 된다(FROZEN_IDEAS ①). 같은 표본이
       화면·카드·알림에서 서로 다른 폭으로 나가기 시작한다 — 실제로
       paper.html과 sns_card.html이 각자 적고 있었고, 그중 하나는 주석에
       "같은 식"이라고 써 두기까지 했다. 검사가 사본을 직접 찾아낸다
       (tests/test_hit_rate_carries_its_sample.py).

    표본이 없으면 (None, None)이다 — 공용 함수의 NaN을 그대로 실으면
    JSON에서 깨지고, 화면은 그것을 '0%'로 읽는다.
    """
    from quant.robustness.accuracy import wilson_ci
    lo, hi = wilson_ci(int(hits), int(n))
    if lo != lo or hi != hi:            # NaN — 표본 없음
        return (None, None)
    return (round(lo, 4), round(hi, 4))


def live_accuracy(state_dir: str = "state") -> dict:
    """실전(OOS) 적중률 — **실제로 돈이 걸린 판단만** 센다.

    돌려주는 ``beats_chance``는 신뢰구간이 50%를 배제할 때만 True다.
    표본이 얇으면 False이고, 그건 "못한다"가 아니라 **"아직 모른다"**다.
    두 문장은 다르고, 화면이 구별해서 말해야 한다.
    """
    hits = n = 0
    per = []
    for name, h in _histories(state_dir):
        last = h[-1]
        rate, cnt = last.get("live_hit"), last.get("live_hit_n")
        try:
            rate = float(rate)
            cnt = int(cnt)
        except (TypeError, ValueError):
            continue
        if cnt <= 0:
            continue
        k = int(round(rate * cnt))
        hits += k
        n += cnt
        per.append({"symbol": name, "hit_rate": round(rate, 4), "n": cnt})
    lo, hi = _wilson(hits, n)
    return {
        "hits": hits, "n": n,
        "hit_rate": (round(hits / n, 4) if n else None),
        "ci_lo": lo, "ci_hi": hi,
        # 우연(50%)을 배제했는가. 표본이 얇으면 False — '아직 모른다'다.
        "beats_chance": bool(n and lo is not None and lo > 0.5),
        "worse_than_chance": bool(n and hi is not None and hi < 0.5),
        "per_symbol": sorted(per, key=lambda r: -r["n"]),
    }


def insample_accuracy(state_dir: str = "state") -> dict:
    """인샘플 적중률 — 모델이 **이미 본 구간**이다. 실력의 증거가 아니다."""
    acc = 0.0
    n = 0
    for _name, h in _histories(state_dir):
        last = h[-1]
        try:
            acc += float(last["hit_rate"]) * int(last["hit_n"])
            n += int(last["hit_n"])
        except (TypeError, ValueError, KeyError):
            continue
    return {"hit_rate": (round(acc / n, 4) if n else None), "n": n}


def calibration(state_dir: str = "state") -> dict:
    """"0.70이라 말한 날 정말 70% 올랐나" — 확률대별 표.

    표는 라이브 가드(quant/live/calibration_guard.py)와 **같은 함수**로
    만든다. 화면용으로 따로 세면 같은 날 두 숫자가 갈라진다.
    """
    from quant.live.calibration_guard import calibration_table, collect_pairs
    hs = [h for _n, h in _histories(state_dir)]
    pairs = collect_pairs(hs)
    table = [
        {"lo": r["lo"], "hi": r["hi"], "n": r["n"],
         "said": r["pred_mean"], "actual": r["actual"],
         "ci_lo": r["ci_lo"], "ci_hi": r["ci_hi"],
         "confirmed": bool(r["confirmed"])}
        for r in calibration_table(hs)
    ]
    up = [b for a, b in pairs if a >= CONFIDENT_UP]
    dn = [b for a, b in pairs if a < CONFIDENT_DOWN]
    return {
        "pairs": len(pairs),
        "table": table,
        # 방향을 아는가 — 확신한 날이 부정한 날보다 실제로 더 올라야 한다.
        "confident_up": {"n": len(up),
                         "actual": (round(sum(up) / len(up), 4) if up else None)},
        "confident_down": {"n": len(dn),
                           "actual": (round(sum(dn) / len(dn), 4) if dn else None)},
        "correlation": _corr([a for a, _b in pairs], [float(b) for _a, b in pairs]),
    }


def _corr(xs: list, ys: list):
    """예측확률과 실제결과의 상관 — 0 근처면 서로 무관, 음수면 거꾸로."""
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    sy = math.sqrt(sum((b - my) ** 2 for b in ys))
    if sx <= 0 or sy <= 0:
        return None
    return round(sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / (sx * sy), 4)


def drift(state_dir: str = "state") -> dict:
    """학습 때 본 시장과 지금 시장이 얼마나 다른가(PSI).

    크면 모델이 **본 적 없는 국면**에서 판단하고 있다는 뜻이다. 틀렸다는
    증거는 아니지만, 맞을 이유도 그만큼 약해진다.
    """
    grades = {}
    rows = []
    for name, h in _histories(state_dir):
        last = h[-1]
        g = last.get("drift_grade")
        try:
            psi = float(last.get("drift_psi"))
        except (TypeError, ValueError):
            psi = None
        if g:
            grades[g] = grades.get(g, 0) + 1
        if psi is not None:
            rows.append({"symbol": name, "psi": round(psi, 4), "grade": g})
    rows.sort(key=lambda r: -r["psi"])
    return {"grades": grades, "worst": rows[:8],
            "notable_line": PSI_NOTABLE,
            "over_line": sum(1 for r in rows if r["psi"] > PSI_NOTABLE),
            "measured": len(rows)}


def champions(state_dir: str = "state") -> dict:
    """지금 무엇이 굴리고 있나 — ML인가 규칙인가, 마지막 학습은 언제인가.

    ⚠️ 승격 횟수가 0이라는 것은 **도전자가 챔피언을 이긴 적이 없다**는
       뜻이다. 안정으로도 읽히고 정체로도 읽힌다 — 화면이 숫자만 보이고
       해석은 사람에게 맡긴다.
    """
    path = os.path.join(state_dir, "champions.json")
    try:
        d = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return {"total": 0, "by_strategy": {}, "rows": [], "promotions": 0}
    by = {}
    rows = []
    promos = 0
    for key, v in sorted(d.items()):
        if not isinstance(v, dict) or "strategy" not in v:
            continue
        s = str(v["strategy"])
        by[s] = by.get(s, 0) + 1
        promos += int(v.get("promotions") or 0)
        rows.append({"key": key, "strategy": s,
                     "trained_on": v.get("last_run_asof"),
                     "promotions": int(v.get("promotions") or 0),
                     "trials": int(v.get("trials_total") or 0)})
    return {"total": len(rows), "by_strategy": by, "rows": rows,
            "promotions": promos}


def gate(state_dir: str = "state", asof: str | None = None) -> dict:
    """과최적화 검증이 오늘 무엇을 붙잡고 있나.

    이 게이트는 **경보가 아니라 손을 묶는 장치**다. 비중 배수 0이면 그
    종목은 오늘 관망한다. 2026-08-14까지 이 검증은 경보만 울리고 아무것도
    막지 않았다 — 문서는 "통과한 전략만 씁니다"라고 말하는 동안.
    """
    try:
        from quant.live.validation_gate import validation_grades
        keys = [r["key"] for r in champions(state_dir)["rows"]]
        if not keys:
            return {"rows": [], "halted": 0, "halved": 0, "full": 0}
        g = validation_grades(keys, state_dir, asof or "")
    except Exception:                       # noqa: BLE001 — 없으면 빈 채로
        return {"rows": [], "halted": 0, "halved": 0, "full": 0}
    rows = []
    halted = halved = full = 0
    for key, v in sorted(g.items()):
        try:
            sc = float(v.get("scale"))
        except (TypeError, ValueError):
            continue
        if sc <= 0.0:
            halted += 1
        elif sc < 1.0:
            halved += 1
        else:
            full += 1
        if sc < 1.0:                        # 붙잡힌 것만 싣는다
            rows.append({"key": key, "scale": round(sc, 4),
                         "why": str(v.get("why") or "")[:300]})
    return {"rows": rows, "halted": halted, "halved": halved, "full": full}


def report(state_dir: str = "state", asof: str | None = None) -> dict:
    """화면(docs/ml.html)이 읽을 한 덩어리."""
    return {
        "kind": "ml-health",
        "asof": asof,
        "champions": champions(state_dir),
        "live": live_accuracy(state_dir),
        "insample": insample_accuracy(state_dir),
        "calibration": calibration(state_dir),
        "drift": drift(state_dir),
        "gate": gate(state_dir, asof),
        # 화면이 지어내지 않도록 한계도 장부가 싣는다.
        "limits": [
            "적중률은 '방향을 맞혔나'이지 '돈을 벌었나'가 아닙니다 — "
            "작게 여러 번 맞고 크게 한 번 틀리면 적중률은 높고 잔고는 줍니다",
            "실전 표본이 얇으면 신뢰구간이 넓습니다. 구간이 50%를 품고 있으면 "
            "'못한다'가 아니라 '아직 모른다'입니다",
            "인샘플 적중률은 모델이 이미 본 구간이라 실력의 증거가 아닙니다",
            "확률 보정은 지금 **표시 전용**입니다 — 어긋남이 확정돼도 "
            "그것만으로 비중을 줄이지는 않습니다(과최적화 검증 게이트는 줄입니다)",
            "여기 숫자는 전부 시뮬레이션 장부에서 셌습니다. 실제 체결·호가를 "
            "겪은 값이 아닙니다",
        ],
    }


def write_report(docs_dir: str = "docs", state_dir: str = "state",
                 asof: str | None = None) -> str:
    from quant.utils.jsonio import atomic_write_json
    os.makedirs(docs_dir, exist_ok=True)
    p = os.path.join(docs_dir, "ml.json")
    atomic_write_json(p, report(state_dir, asof))
    return p
