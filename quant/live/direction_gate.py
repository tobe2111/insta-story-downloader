"""방향 관문 — **내림 예측을 쓰는 것이 정말 나은가**를 기계가 판정한다.

사장님 (2026-09-03): *"하락장에선 대응 여력없이 수익을 못내네..?
특히 선물은 롱숏 포지션 다 가능한데 더 손해가 커."*

■ 재 보니 그 말이 맞았고, 더 나쁜 사실이 하나 있었다

선물 트랙 문서의 첫 문단은 이렇게 약속한다 —
*"믿지 않고 나란히 돌려서 잰다 — 같은 규칙, 같은 비용, 같은 종목,
방향 허용 여부만 다르게."* 그런데 **나란히 도는 반대쪽이 없었다.**
``build_two_sided``가 챔피언 위에 방향 허용을 켜서 그 한 팔만 굴렸고,
같은 챔피언이 롱 전용이었으면 얼마를 벌었을지는 **아무도 계산하지 않았다.**

즉 열흘 −4.17%가 나온 뒤에도 "숏 때문인가"에 답할 근거가 장부에 없었다.
그리고 그 상태를 알려 주는 빨간불도 없었다 — 화면에는 롱 포지션 수와 숏
포지션 수가 나란히 떠 있어서, 마치 둘을 비교하고 있는 것처럼 보였다.

■ 왜 손으로 "숏을 끄자"고 정하지 않는가

사장님 방침(2026-08-27): *"투자 로직의 경우에는 머신러닝으로 개선을 계속할
수 있게끔 해야지 너가 수동으로 고치는 방향 말고."* 방향을 쓸지 말지는
**무엇을 사고파는가**의 로직이므로 사람이 값을 적는 자리가 아니다. 여기서
하는 일은 손잡이를 돌리는 것이 아니라 **그 손잡이를 판정하는 장치**를 놓는
것이다.

■ ⚠️ 왜 코인 5종목이 아니라 **운용 전 종목**에서 재는가 (실측으로 고쳤다)

처음에는 선물 트랙 안에서 코인 5종목만 재게 만들었다. 스냅샷으로 돌려 보고
그 설계가 **처음부터 죽어 있다**는 것을 알았다:

    코인 5종목 중 숏을 낼 수 있는 챔피언은 **2개뿐**이다
    (BTC·ETH·BNB는 규칙 전략이라 음수 신호를 아예 안 낸다).
    패널 최소 종목 수는 5다 → **영원히 판정 불가.**

장부에 "재료 부족"만 매일 쌓이고 관문은 한 번도 안 열리는, 이 저장소가
가장 싫어하는 종류의 조용한 죽음이다.

그런데 질문 자체가 코인 것이 아니다 — **"모델의 내림 예측에 정보가 있는가"**
는 머신러닝 챔피언 전부에 걸린 질문이고, 운용 40종목 중 **32종목**이 머신러닝
챔피언이다. 그래서 밤 오디션이 종목을 도는 김에 각 종목에서 '양방향 −
롱 전용'을 함께 재고, 날짜별 횡단 평균으로 한 번에 판정한다.

⚠️ 그 대신 정직하게 적어 둔다 — **판정 모집단이 코인보다 넓다.** 대차료와
   시장 구조는 시장마다 다르므로, 여기서 "도움이 된다"가 나와도 그것이 코인
   무기한선물에서 그대로 성립한다는 보장은 없다. 시장별 숫자도 함께 남겨,
   나중에 코인만으로 판정할 종목 수가 모이면 그때 좁혀 볼 수 있게 한다.

■ 관측 단위는 종목이 아니라 **날짜**다 (패널 관문과 같은 규약)

"XRP에서 숏이 좋았나"가 아니라 "**방향을 쓰는 것 자체가** 여러 종목에서
같은 방향으로 도움이 되나"를 묻는다. 계산은 ``quant/live/panel_gate.py``의
것을 그대로 빌려 쓴다 — 같은 규칙을 두 곳에 적으면 언젠가 갈라진다.

■ 판정이 무엇을 바꾸는가 — 그리고 **무엇을 바꾸지 않는가**

  · 판정이 없으면 **막지 않는다.** 못 잰 것과 나쁜 것은 다른 사건이다
    (패널 관문과 같은 규약). 첫날부터 실험이 얼어붙으면 안 된다.
  · 유의하게 **나쁠 때만** 롱 전용으로 돌린다(t < −문턱). "유의하지 않다"는
    실험을 계속한다는 뜻이지 끄라는 뜻이 아니다 — 이 트랙의 존재 이유가
    "숏이 도움이 되는가"를 재는 것이고, 답이 안 나왔다고 실험을 접으면
    영영 못 잰다.
  · 판정은 **낡으면 안 쓴다**(``MAX_AGE_NIGHTS``). 그 사이 챔피언이 바뀌면
    옛 판정은 다른 규칙에 대한 판정이고, 그걸로 오늘을 막으면 근거 없는
    제약이 된다.
  · **본 계좌는 이 관문이 안 건드린다.** 100만원 계좌는 현물이라 애초에
    숏을 못 낸다 — 여기서 "숏이 좋다"가 나와도 본 계좌가 숏을 열지 않는다.
    재현할 수 없는 매매를 페이퍼 장부에 적는 것이 이 제품에서 가장 비싼
    거짓말이기 때문이다.

■ ⚠️ 정직하게 — 이 비교에 **펀딩비는 안 들어 있다**

비용 기준은 다른 모든 트랙과 같은 하나다(``measured_cost_model``). 거기에는
체결 비용과 **숏 차입료**가 들어 있지만 펀딩비는 없다. 펀딩은 부호가
방향마다 반대라(양수 요율이면 롱이 내고 숏이 받는다) 대칭으로 물리면 숏을
부당하게 불리하게 만들고, 실데이터 계열 없이 부호를 넣으면 숫자를 지어내는
일이 된다. 그래서 **빼고 재고, 뺐다고 적는다.**

  → 방향은 분명하다: 실제 세계에서 숏은 펀딩을 **받는** 쪽인 경우가 많으므로
    이 관문은 숏에 **불리한 쪽으로 보수적**이다. 여기서 "유의하게 나쁘다"가
    나오면 펀딩 덕을 빼고도 나쁘다는 뜻이고, 반대로 "좋다"가 안 나온 것을
    숏이 나쁘다는 증거로 읽으면 안 된다.
"""
from __future__ import annotations

import json
import logging
import os

log = logging.getLogger(__name__)

DIRECTION_FILE = "direction_history.jsonl"

# 판정을 며칠까지 유효하게 볼 것인가. 패널 관문과 같은 값·같은 이유다.
MAX_AGE_NIGHTS = 7


def t_threshold() -> float:
    """판정 문턱 — 패널 관문과 **같은 값**을 쓴다.

    여기서 따로 정하면 "방향만 문턱이 다르다"는 상태가 되고, 그건 관문이
    아니라 편의다. 한 곳에서 가져온다.
    """
    from quant.live.retrain import PANEL_T_REF
    return float(PANEL_T_REF)


def two_sided_spec(spec: dict) -> dict:
    """같은 챔피언, 방향 허용만 켠 설정.

    ⚠️ **다른 것은 하나도 바꾸지 않는다.** 하나라도 같이 바꾸면 성적 차이가
       무엇 때문인지 영영 모른다(``build_two_sided``와 같은 규약).
    """
    out = dict(spec)
    out["params"] = {**(spec.get("params") or {}), "allow_short": True}
    return out


def can_probe(spec: dict | None) -> bool:
    """이 챔피언에서 방향을 잴 수 있는가 — 머신러닝일 때만.

    규칙 전략(이동평균 교차·터틀 등)은 음수 신호를 아예 안 낸다. 그런
    종목을 '차이 0'으로 담으면 **없는 것을 관측으로 세는** 일이고, 패널
    평균이 인위적으로 0쪽으로 끌려간다.
    """
    from quant.live.futures_challenger import can_short
    return can_short(spec)


def judge(per_symbol: dict, *, night: str, n_symbols_seen: int,
          state_dir: str = "state", long_only: list | None = None,
          unmeasured: dict | None = None) -> dict:
    """모아 온 종목별 '양방향 − 롱 전용' 계열로 판정하고 장부 줄을 만든다.

    per_symbol: {종목키: 날짜 색인 초과수익 시리즈}
    """
    from quant.live.daily import cost_basis_bp
    from quant.live.panel_gate import daily_terms, panel_verdict

    thr = t_threshold()
    verdict = panel_verdict(per_symbol, t_threshold=thr)
    rec: dict = {
        "night": str(night),
        # 그 밤 실제로 판정에 선 종목과, 서지 못한 종목의 **이유**.
        # 이유를 안 적으면 "숏 못 내는 챔피언이라 빠졌다"와 "재다가 터졌다"가
        # 장부에서 똑같이 보인다 — 고칠 사람이 다른데.
        "symbols": sorted(per_symbol),
        "long_only_symbols": sorted(long_only or []),
        "unmeasured": dict(unmeasured or {}) or None,
        # 그 밤 오디션을 **실제로 연** 종목 수. 판정이 0인 밤에 이 숫자가
        # 0이면 "밤 배치가 안 돌았다"이고, 0이 아니면 "돌았는데 재료를 못
        # 모았다"(고장)이다 — 다른 사건이고 다른 사람이 고쳐야 한다.
        "n_symbols_seen": int(n_symbols_seen),
        "t_threshold": thr,
        # 비용 기준을 같이 적는다(2026-09-02 사장님 지시 — 모든 트랙이
        # 자기 수익률 옆에 자기 비용 기준을 적는다).
        "cost_basis_bp": cost_basis_bp(state_dir),
        # ⚠️ 펀딩비는 안 들어 있다(모듈 첫머리 참조). 칸으로 남겨야
        #    나중에 "왜 선물 실적과 안 맞나"에 장부가 답할 수 있다.
        "funding_excluded": True,
        **{k: (round(v, 8) if isinstance(v, float) else v)
           for k, v in verdict.items()},
    }
    # ⚠️ **밤의 두 회차를 나중에 합칠 재료**(패널 장부와 같은 이유).
    #    밤 배치는 하루 두 번 돌고 두 회차는 서로 겹치지 않는 종목을 본다.
    #    설정별 요약(t)만 남기면 서로 다른 종목 집합의 두 t로 union 의 t 를
    #    만들 수 없고, 그 재료는 지나가면 되살릴 수 없다(챔피언이 바뀐다).
    if per_symbol:
        rec["daily"] = daily_terms(per_symbol)
    return rec


def record(rec: dict, state_dir: str = "state") -> dict:
    """장부에 한 줄 붙인다 — **못 잰 밤에도 붙인다.**

    안 남기면 "방향을 못 쟀다"(고장)와 "밤 배치가 아예 안 돌았다"(다른
    경보의 일)가 장부에서 똑같이 보인다. 없는 줄은 침묵이고, 침묵이 이
    저장소에서 가장 비싼 실패다.
    """
    try:
        os.makedirs(state_dir, exist_ok=True)
        with open(os.path.join(state_dir, DIRECTION_FILE), "a",
                  encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError as exc:                            # noqa: BLE001
        log.warning("방향 장부 기록 실패: %s", exc)
    return rec


def rows(state_dir: str = "state") -> list[dict]:
    path = os.path.join(state_dir, DIRECTION_FILE)
    if not os.path.exists(path):
        return []
    out: list[dict] = []
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    out.append(json.loads(ln))
                except ValueError:
                    continue
    except OSError:
        return []
    return out


def nights(state_dir: str = "state") -> dict:
    """밤별로 합친 판정 — 같은 밤의 여러 회차를 **날짜별 합·개수로** 더한다.

    ⚠️ 열쇠는 ``night``(한국 달력일)이지 마지막 봉 날짜가 아니다. 봉 날짜로
       묶으면 한 밤이 쪼개지고 두 밤이 붙는다(2026-09-01 패널 장부에서
       실제로 그 일이 났다).
    ⚠️ 두 회차가 **겹치는 종목**을 보면 합치지 않는다 — 그 종목이 두 표를
       행사해 평균이 그쪽으로 기운다. 합치지 않고 **겹쳤다고 말한다.**
    """
    from quant.live.panel_gate import merge_daily_terms, verdict_from_terms

    by_night: dict = {}
    for rec in rows(state_dir):
        key = str(rec.get("night") or "")
        if key:
            by_night.setdefault(key, []).append(rec)
    out: dict = {}
    for key, recs in by_night.items():
        base = max(recs, key=lambda r: len(r.get("symbols") or []))
        chunks = [r["daily"] for r in recs if r.get("daily")]
        if not chunks:
            # 옛 줄(합칠 재료 없음)은 **합치지 않고 그렇다고 말한다** —
            # 조용히 빼면 "그 밤엔 판정이 없었다"와 구별할 수 없다.
            out[key] = {**base, "merged": False,
                        "merge_note": "합칠 재료(날짜별 합·개수)가 없는 옛 줄입니다"}
            continue
        daily = merge_daily_terms(chunks)
        thr = float(base.get("t_threshold") or t_threshold())
        # ⚠️ 겹침 판정은 ``verdict_from_terms``가 한다 — 여기서 또 세면
        #    같은 규칙이 두 곳에 생기고 언젠가 갈라진다.
        v = verdict_from_terms(daily, t_threshold=thr)
        out[key] = {**base, "merged": True,
                    "symbols": list(daily.get("symbols") or []),
                    "n_symbols_seen": sum(int(r.get("n_symbols_seen") or 0)
                                          for r in recs),
                    **v}
    return out


def verdict(state_dir: str = "state",
            max_age_nights: int = MAX_AGE_NIGHTS) -> dict | None:
    """가장 최근의 **유효한** 판정. 없으면 None(그리고 None은 막지 않는다)."""
    import datetime as _dt

    from quant.live.retrain import night_key

    try:
        today = _dt.date.fromisoformat(night_key())
    except ValueError:
        return None
    best = None
    for key, rec in nights(state_dir).items():
        if rec.get("skipped") or rec.get("t_stat") is None:
            continue
        try:
            night = _dt.date.fromisoformat(str(key)[:10])
        except ValueError:
            continue
        age = (today - night).days
        if age < 0 or age >= max_age_nights:
            continue
        if best is None or night >= best[0]:
            best = (night, {**rec, "age_nights": age})
    return best[1] if best else None


def two_sided_allowed(state_dir: str = "state") -> tuple[bool, dict | None]:
    """지금 양방향을 써도 되는가 — (허용, 근거).

    ⚠️ **판정이 없으면 허용한다.** 못 잰 것을 위반으로 세면 첫날부터 실험이
       얼어붙고, 그러면 방향이 도움이 되는지를 영영 못 잰다.
    ⚠️ **유의하지 않은 것도 허용한다.** "아직 모른다"는 "끄라"가 아니다.
    """
    v = verdict(state_dir)
    if not v:
        return True, None
    try:
        t = float(v.get("t_stat"))
        thr = float(v.get("t_threshold") or t_threshold())
    except (TypeError, ValueError):
        return True, v
    return (t >= -thr), v
