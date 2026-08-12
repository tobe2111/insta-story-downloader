"""포트폴리오 자산배분(allocation) 방식.

전략이 각 종목의 '방향(롱/숏/관망)'을 정하면, 여기서 '각 종목에 자본을
얼마나 배분할지'를 정한다. 분산투자는 공짜 점심에 가장 가까운 것으로,
동일 기대수익에서 변동성을 낮춰 장기 복리를 개선한다.

모든 함수는 동일 시그니처를 따른다:
    fn(returns: DataFrame, signals: DataFrame, window: int) -> weights DataFrame
컬럼 = 종목, 값 = 목표 비중(부호 포함). 각 시점 |비중| 합이 대략 1을 넘지 않게 정규화.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant.utils.numerics import REL_EPS

# 한 종목이 가져갈 수 있는 최대 비중 = 균등가중의 이 배수 (감사 149).
# 실거래 경로(_erc_slices·_hrp_slices)가 쓰는 3/n과 같은 값으로 맞춘다 —
# 오디션이 현실보다 관대한 배분을 쓰면 승격된 전략이 실전에서 다르게 돈다.
MAX_CONCENTRATION = 3.0


def equal_weight(returns: pd.DataFrame, signals: pd.DataFrame, window: int = 30) -> pd.DataFrame:
    """활성(신호≠0) 종목에 자본을 균등 배분한다."""
    direction = np.sign(signals)
    active = (signals.abs() > 0).astype(float)
    n = active.sum(axis=1).replace(0, np.nan)
    magnitude = active.div(n, axis=0).fillna(0.0)
    return (direction * magnitude).fillna(0.0)


def inverse_vol(returns: pd.DataFrame, signals: pd.DataFrame, window: int = 30) -> pd.DataFrame:
    """변동성 역가중(리스크 패리티 근사).

    변동성이 낮은 종목에 더 많이 배분해 각 종목의 리스크 기여를 균등화한다.

    ⚠️ 분모가 작을수록 많이 사는 규칙이라 **분모가 사실상 0인 종목이 전부를
       가져간다**(감사 149). 거래정지·저유동 종목이 30일에 한 번 1틱만 움직여도
       실측 비중이 0.997이 나왔다. `1/vol`이 inf가 되는 경우만 막아서는 부족하다
       — inf가 아니라 8.5e37 같은 유한한 거대값으로 나오기 때문이다.
       그래서 (1) 그 봉의 최대 변동성에 견주어 무시할 만큼 작은 종목은 빼고,
       (2) 남은 종목에도 균등가중 3배 상한을 건다(실거래 경로와 같은 값).
    """
    vol = returns.rolling(window).std()
    inv = (1.0 / vol).replace([np.inf, -np.inf], np.nan)
    # 봉마다 '그 봉의 최대 변동성' 대비 상대 문턱 — 절대 문턱은 시장마다
    # 스케일이 달라 코인에서는 헐겁고 채권 ETF에서는 덫이 된다.
    floor = vol.max(axis=1) * REL_EPS
    inv = inv.where(vol.gt(floor, axis=0), np.nan)
    inv = inv.where(signals.abs() > 0, 0.0).fillna(0.0)
    total = inv.sum(axis=1).replace(0, np.nan)
    magnitude = inv.div(total, axis=0).fillna(0.0)
    magnitude = pd.DataFrame(
        [_cap_concentration(row) for row in magnitude.to_numpy()],
        index=magnitude.index, columns=magnitude.columns)
    return (np.sign(signals) * magnitude).fillna(0.0)


def _cap_concentration(w: np.ndarray, mult: float = MAX_CONCENTRATION) -> np.ndarray:
    """한 종목이 균등가중의 mult배를 넘지 못하게 자르고 나머지에 재분배한다.

    역분산·HRP는 '분모가 작을수록 많이'라서 상한이 없으면 한 종목이 전부를
    가져갈 수 있다(감사 149의 실측: 99.7%). 실거래 경로는 이미 3/n으로
    자르고 있었는데 **오디션이 쓰는 이 파일에만 상한이 없었다.**

    잘라낸 몫은 아직 상한에 안 닿은 종목들에 비율대로 나눠 준다 —
    그냥 버리면 총 노출이 조용히 줄어 '배분 규칙'이 '사이징 규칙'이 된다.
    """
    w = np.asarray(w, dtype=float).copy()
    n = len(w)
    if n == 0 or not np.isfinite(w).all() or w.sum() <= 0:
        return w
    w = w / w.sum()
    cap = min(1.0, mult / n)
    for _ in range(n):                       # 재분배가 다시 상한을 넘길 수 있다
        over = w > cap + 1e-15
        if not over.any():
            break
        excess = float((w[over] - cap).sum())
        w[over] = cap
        room = ~over & (w < cap - 1e-15)
        if not room.any() or w[room].sum() <= 0:
            break                            # 나눠 줄 곳이 없다 — 합<1을 허용
        w[room] += excess * (w[room] / w[room].sum())
    return w


def _inv_var_weights(cov: pd.DataFrame) -> pd.Series:
    """역분산 가중 (HRP 실패 시 폴백).

    ⚠️ `1/분산`을 그대로 쓰면 안 된다(감사 149). 값이 고정된 종목(거래정지,
       고정 시세, 상장 직후)의 분산은 **정확히 0이 아니라** 1e-38 언저리로
       나오고, `np.isfinite`는 그걸 정상값으로 통과시킨다. 실측:

           s0~s3 분산 1e-4 → 역분산 1.2e4
           HALT  분산 1.2e-38 → 역분산 8.5e37
           → HALT 비중 1.000   (포트폴리오 전부)

       감사 146(샤프의 분모)과 같은 병이 **배분의 분모**에 있었다.
       패널 안 최대 분산에 견주어 무시할 만큼 작은 열은 제외한다.
    """
    var = np.asarray(np.diag(cov.values), dtype=float)
    ok = np.isfinite(var) & (var > 0.0)
    if ok.any():
        ok &= var > REL_EPS * float(np.max(var[ok]))
    ivp = np.where(ok, 1.0 / np.where(ok, var, 1.0), 0.0)
    s = ivp.sum()
    if s <= 0:
        ivp = np.ones(len(cov)) / max(1, len(cov))
    else:
        ivp = _cap_concentration(ivp / s)
    return pd.Series(ivp, index=cov.index)


def _cluster_var(cov: pd.DataFrame, items: list) -> float:
    sub = cov.loc[items, items]
    w = _inv_var_weights(sub).values
    return float(w @ sub.values @ w)


def _quasi_diag(link) -> list:
    """계층 클러스터 링크를 준대각(quasi-diagonal) 순서로 펼친다 (López de Prado)."""
    link = link.astype(int)
    sort_ix = pd.Series([link[-1, 0], link[-1, 1]])
    num_items = link[-1, 3]
    while sort_ix.max() >= num_items:
        sort_ix.index = range(0, sort_ix.shape[0] * 2, 2)
        df0 = sort_ix[sort_ix >= num_items]
        i = df0.index
        j = df0.values - num_items
        sort_ix[i] = link[j, 0]
        df0 = pd.Series(link[j, 1], index=i + 1)
        sort_ix = pd.concat([sort_ix, df0]).sort_index()
        sort_ix.index = range(sort_ix.shape[0])
    return sort_ix.tolist()


def _hrp_weights(win: pd.DataFrame) -> pd.Series:
    """한 구간의 수익률로 HRP 가중치(합=1, 롱 온리)를 계산한다.

    상관관계를 계층적으로 군집화해 준대각으로 정렬한 뒤, 재귀적 이분할로
    역분산 배분한다. 공분산 역행렬을 쓰지 않아 상관 급변장에서도 안정적이다.
    실패(자산<2, 특이 공분산, scipy 부재)하면 역분산 가중으로 폴백한다.
    """
    # ⚠️ 이름순으로 고정한 뒤 계산한다 — 감사 147과 같은 병이다(형제, ⑭).
    #    단일 연결 군집의 잎 순서가 입력 열 순서로 갈리고, 재귀 이분은 그
    #    순서를 그대로 비중으로 옮긴다. 147에서 quant/live/hrp.py만 고치고
    #    **이 파일을 못 찾았다** — 오디션·포트폴리오 백테스트가 쓰는 쪽이다.
    win = win[sorted(win.columns, key=str)]
    # 퇴화 열(거래정지·고정 시세)을 먼저 뺀다(감사 149). 군집 분산은
    # '역분산으로 들었을 때의 분산'이라 분산 1e-38짜리 열이 섞이면 그 군집이
    # **가장 안전한 자산**으로 보여 예산을 독식한다. 군집이 한 열뿐이면
    # 자기 자신 대비로는 퇴화를 판정할 수 없으므로 여기서 걸러야 한다.
    _all = list(win.columns)                 # 반환 인덱스는 항상 원래 열 전부
    _v = win.var()
    _keep = [c for c in _all
             if np.isfinite(_v[c]) and _v[c] > REL_EPS * float(_v.max())]
    if len(_keep) >= 2:
        win = win[_keep]
    cols = list(win.columns)
    cov = win.cov()
    if len(cols) < 2 or not np.isfinite(cov.values).all():
        return _inv_var_weights(cov) if len(cols) else pd.Series(dtype=float)
    try:
        from scipy.cluster.hierarchy import linkage
        from scipy.spatial.distance import squareform

        corr = win.corr().fillna(0.0)
        dist = np.sqrt(((1.0 - corr) / 2.0).clip(lower=0.0).values)
        np.fill_diagonal(dist, 0.0)
        link = linkage(squareform(dist, checks=False), method="single")
        order = [cols[i] for i in _quasi_diag(link)]
    except Exception:  # noqa: BLE001  # scipy 부재/특이값 → 폴백
        return _inv_var_weights(cov)

    w = pd.Series(1.0, index=order)
    clusters = [order]
    while clusters:
        nxt = []
        for c in clusters:
            if len(c) <= 1:
                continue
            half = len(c) // 2
            left, right = c[:half], c[half:]
            v_left, v_right = _cluster_var(cov, left), _cluster_var(cov, right)
            alpha = 1.0 - v_left / (v_left + v_right) if (v_left + v_right) > 0 else 0.5
            w[left] *= alpha
            w[right] *= 1.0 - alpha
            nxt += [left, right]
        clusters = nxt
    # 걸러낸 퇴화 열은 비중 0으로 되돌려 넣는다 — 인덱스가 사라지면
    # 호출자의 reindex가 조용히 NaN→0으로 바꾸고 그 사실이 안 보인다.
    # ⚠️ `cols + _dropped`로 쓰면 안 된다 — 열이 둘 미만이라 필터를 건너뛴
    #    경우 cols에 이미 그 열이 들어 있어 **중복 인덱스**가 되고
    #    reindex가 ValueError를 던진다(전체 검사가 잡았다).
    return w.reindex(_all).fillna(0.0)


def hrp(returns: pd.DataFrame, signals: pd.DataFrame, window: int = 60,
        rebalance: int = 21) -> pd.DataFrame:
    """계층적 리스크 패리티(HRP) 배분.

    최근 window봉 수익률로 HRP 가중을 구하고 rebalance봉마다 갱신한다(과거만
    사용 → 룩어헤드 없음). 활성(신호≠0) 종목으로 마스킹·재정규화한 뒤 방향을 곱한다.
    """
    cols = list(returns.columns)
    n = len(returns)
    base = pd.DataFrame(0.0, index=returns.index, columns=cols)
    last = None
    for i in range(n):
        if i >= window and (last is None or i % max(1, rebalance) == 0):
            last = _hrp_weights(returns.iloc[i - window:i])
        if last is not None:
            base.iloc[i] = last.reindex(cols).fillna(0.0).values

    active = (signals.abs() > 0).astype(float)
    w = base * active.values
    total = w.sum(axis=1).replace(0, np.nan)
    magnitude = w.div(total, axis=0).fillna(0.0)
    # 과집중 상한 — 실거래 경로(_hrp_slices)가 이미 3/n으로 자르고 있었다.
    magnitude = pd.DataFrame(
        [_cap_concentration(row) for row in magnitude.to_numpy()],
        index=magnitude.index, columns=magnitude.columns)
    return (np.sign(signals) * magnitude).fillna(0.0)


_SCHEMES = {
    "equal": equal_weight,
    "inverse_vol": inverse_vol,
    "hrp": hrp,
}


def get_scheme(name: str):
    if name not in _SCHEMES:
        raise ValueError(f"알 수 없는 배분 방식: {name}. 사용 가능: {list(_SCHEMES)}")
    return _SCHEMES[name]


def list_schemes() -> list[str]:
    return list(_SCHEMES)
