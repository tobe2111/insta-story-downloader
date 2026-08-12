"""데이터 품질 이상 탐지 — 백테스트 전에 '데이터부터' 의심한다.

전략이 아무리 정교해도 입력 데이터가 오염돼 있으면(분할 미조정 스파이크,
중복 봉, 음수 가격, high<low 같은 모순) 백테스트는 그럴듯한 거짓말을 한다.
이 모듈은 OHLCV DataFrame을 스캔해 의심 항목을 '보고만' 한다 — 절대 데이터를
고치거나 지우지 않는다. 무엇을 고칠지는 사람이 원본을 확인하고 결정할 일이다.

⚠️ 탐지 항목이 0이라고 데이터가 깨끗하다는 보장은 없고, 탐지됐다고 반드시
   오류인 것도 아니다(예: 급락장은 실제로 하루 -20%가 난다). 이 스캔은
   '들여다볼 곳'을 알려주는 도구일 뿐이다.
"""
from __future__ import annotations

import pandas as pd

# 이 항목들이 하나라도 있으면 데이터 자체의 무결성이 깨진 것이므로
# 백테스트 결과를 신뢰하기 전에 반드시 원본을 확인해야 한다.
SEVERE_KEYS = ("duplicate_index", "nonpositive_price", "ohlc_violations")


def scan_ohlcv(df: pd.DataFrame, spike_threshold: float = 0.2) -> dict:
    """OHLCV DataFrame을 스캔해 의심 항목별 건수를 반환한다 (비파괴).

    반환 dict:
        gaps             : 추정 주기 대비 누락된 인덱스 스텝 수.
                           ⚠️ 일봉 주식은 주말·휴장이 갭으로 집계되므로
                           절대값보다 '갑작스러운 증가'를 볼 것.
        spikes           : |종가 등락률| > spike_threshold(기본 20%)인 봉 수.
                           분할·배당 미조정의 전형적 흔적 — 단, 실제 폭락일 수도 있다.
        zero_volume      : 거래량이 0 이하이거나 **결측**인 봉 수
                           (거래정지·수집 오류 의심. 지수·환율은 거래량이
                           원래 없으므로 전 구간이 여기 잡히는 것이 정상).
        duplicate_index  : 중복된 타임스탬프 수.
        nonpositive_price: O/H/L/C 중 0 이하가 있는 봉 수.
        ohlc_violations  : high < low 이거나 **open·close**가 [low, high] 밖인 봉 수.
    """
    findings = {
        "gaps": 0, "spikes": 0, "zero_volume": 0,
        "duplicate_index": 0, "nonpositive_price": 0, "ohlc_violations": 0,
    }
    if df is None or len(df) == 0:
        return findings

    # 중복 인덱스 — 같은 봉이 두 번 들어오면 수익률 계산이 왜곡된다.
    findings["duplicate_index"] = int(df.index.duplicated().sum())

    # 인덱스 갭 — 연속 봉 간격의 중앙값을 '정상 주기'로 추정하고,
    # 그보다 1.5배 넘게 벌어진 곳의 누락 스텝 수를 센다.
    if isinstance(df.index, pd.DatetimeIndex) and len(df.index) >= 3:
        diffs = pd.Series(df.index).sort_values().diff().dropna()
        step = diffs.median()
        if step is not pd.NaT and step > pd.Timedelta(0):
            ratio = diffs / step
            missing = (ratio[ratio > 1.5].round() - 1).clip(lower=1)
            findings["gaps"] = int(missing.sum())

    # 급등락 스파이크 — 분할/배당 조정 누락은 대개 ±20~90%의 계단으로 나타난다.
    if "close" in df.columns and len(df) >= 2:
        pct = df["close"].pct_change().abs()
        findings["spikes"] = int((pct > spike_threshold).sum())

    if "volume" in df.columns:
        # 결측도 함께 센다(감사 163). `_validate`는 이제 거래량이 없다고
        # 가격 봉을 지우지 않는다 — 지수·환율은 거래량 자체가 없기 때문이다.
        # 그래서 결측 거래량이 프레임에 남는데, `<= 0`은 NaN을 False로 봐서
        # 그 사실이 보고서에서 통째로 안 보이게 된다. 무결성 위반은 아니므로
        # (SEVERE_KEYS 아님) 매매를 막지는 않고, 사람이 볼 줄에만 남긴다.
        vol = df["volume"]
        findings["zero_volume"] = int((vol.isna() | (vol <= 0)).sum())

    price_cols = [c for c in ("open", "high", "low", "close") if c in df.columns]
    if price_cols:
        findings["nonpositive_price"] = int((df[price_cols] <= 0).any(axis=1).sum())

    if all(c in df.columns for c in ("high", "low")):
        # ⚠️ **시가도 봐야 한다**(감사 161). 예전에는 close만 밴드 검사를
        #    했다. 그런데 이 시스템은 주식 체결을 **다음 봉 시가**로 한다
        #    (`_first_bar_after`가 `float(r["open"])`을 그대로 체결가로 쓴다).
        #    즉 무결성 관문이 **체결에 쓰는 바로 그 값**을 안 보고 있었다.
        #
        #    실측: 밴드가 99~101인 봉의 시가만 5000으로 바꿔도
        #        ohlc_violations 0 · is_severe False  → 관문 통과
        #    같은 크기로 종가를 망가뜨리면 1건·True로 잡힌다.
        #
        #    is_severe는 페이퍼·포트폴리오 배치 양쪽의 입구 관문이라,
        #    통과하면 그 값이 그대로 체결가가 되고 장부에 남는다.
        bad = df["high"] < df["low"]
        for col in ("open", "close"):
            if col in df.columns:
                bad = bad | (df[col] > df["high"]) | (df[col] < df["low"])
        findings["ohlc_violations"] = int(bad.sum())

    return findings


def is_severe(findings: dict) -> bool:
    """무결성 위반(중복·음수가격·OHLC 모순)이 하나라도 있으면 True.

    갭·스파이크·거래량 0은 정상 시장에서도 생기므로 여기에 넣지 않는다 —
    그것들은 보고서에서 사람이 맥락과 함께 판단한다.
    """
    return any(findings.get(k, 0) > 0 for k in SEVERE_KEYS)


def quality_report(df: pd.DataFrame, findings: dict | None = None,
                   spike_threshold: float = 0.2) -> str:
    """스캔 결과를 사람이 읽을 한국어 문자열로 요약한다 (비파괴 — 보고만)."""
    f = findings if findings is not None else scan_ohlcv(df, spike_threshold)
    n = len(df) if df is not None else 0
    lines = [
        f"데이터 품질 스캔 ({n}봉)",
        f"  인덱스 갭        : {f['gaps']}건 (일봉 주식은 주말·휴장 포함될 수 있음)",
        f"  급등락 스파이크  : {f['spikes']}건 (|등락률| > {spike_threshold:.0%} — 분할·배당 미조정 의심)",
        f"  거래량 0         : {f['zero_volume']}건",
        f"  중복 타임스탬프  : {f['duplicate_index']}건",
        f"  0 이하 가격      : {f['nonpositive_price']}건",
        f"  OHLC 모순        : {f['ohlc_violations']}건 (high<low 또는 시가·종가가 밴드 밖)",
    ]
    if is_severe(f):
        lines.append("  ⚠️ 무결성 위반이 있습니다 — 이 데이터로 만든 백테스트 결과를 "
                     "신뢰하기 전에 원본 소스를 확인하세요.")
    else:
        lines.append("  무결성 위반은 없습니다. 단, 스캔 통과가 데이터의 정확성을 "
                     "보장하지는 않습니다 — 가능하면 복수 소스로 교차 검증하세요.")
    return "\n".join(lines)
