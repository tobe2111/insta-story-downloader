"""KRX 투자자별 수급 — 외국인·기관 순매수를 피처로 (한국 주식의 진짜 수급).

한국 시장은 외국인·기관의 순매수 방향이 지수·개별주 단기 흐름과 상관이
높다는 게 오래된 관찰이다(인과 주장 아님 — 피처로 줄 뿐, 채택은 오디션이
결정한다). KRX 정보데이터시스템의 공개 통계를 pykrx로 받는다 — 무료·공개
데이터라 스냅샷·해시에 남아 재현 가능하다.

정규화: 순매수 '금액'은 종목 시총에 따라 규모가 제각각이라 그대로 못 쓴다.
5일 순매수 합을 60일 롤링 z-점수로 표준화한다(모두 과거 창 — 룩어헤드 없음).

pykrx 미설치·조회 실패 시 원본 df 그대로(예외 없음) — 선택적 피처 원칙.
"""
from __future__ import annotations

import datetime as _dt

import numpy as np
import pandas as pd

from quant.data.source_health import note_exception, note_source_failure
from quant.utils.logging import get_logger

log = get_logger("data.krx")


def fetch_investor_net(symbol: str, limit: int = 160) -> pd.DataFrame | None:
    """일자별 외국인/기관 순매수대금 DataFrame(컬럼 frgn, inst).

    ⚠️ **실패의 종류를 뭉개지 않는다** (감사 272). 예전에는 라이브러리
    없음·조회 예외·컬럼 이름 변경이 전부 `None` 하나로 돌아왔다. 그래서
    장부에는 매번 "KRX 순매수가 비어 있음(미설치·코드 불일치·조회 실패
    가능)"이라는 **세 가지 가능성을 나열한 한 문장**만 남았고, 수급 피처
    2개가 몇 주 동안 안 붙는 동안 아무도 원인을 좁히지 못했다. 배치에는
    pykrx가 설치돼 있으므로 그 셋 중 첫 번째는 애초에 답이 아니었는데,
    문구가 그렇게 적혀 있으니 계속 그쪽을 의심하게 만들었다.

    이제 원인을 아는 실패는 **그 사유를 그대로 들고 예외로 올라간다** —
    부착 함수가 받아 장부에 적는다. 한국 종목이 아닌 경우만 None이다
    (그건 실패가 아니라 해당 없음).
    """
    code = symbol.split(".")[0]
    if not code.isdigit():
        return None
    try:
        from pykrx import stock
    except ImportError as exc:
        raise RuntimeError("pykrx 미설치 — 배치에는 설치돼 있어야 한다") from exc
    end = _dt.date.today()
    start = end - _dt.timedelta(days=int(limit * 1.6))   # 휴장일 여유
    try:
        raw = stock.get_market_trading_value_by_date(
            start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), code)
    except Exception as exc:  # noqa: BLE001 — 스크래핑 실패는 흔하다(무해해야)
        log.warning("KRX 수급 조회 실패 %s: %s", symbol, exc)
        raise RuntimeError(
            f"KRX 조회 실패({type(exc).__name__}: {exc})") from exc
    if raw is None or len(raw) == 0:
        raise RuntimeError(
            f"KRX가 {start:%Y-%m-%d}~{end:%Y-%m-%d} 구간에 빈 표를 줬다")
    cols = {}
    for name in raw.columns:
        if "외국인" in str(name):
            cols.setdefault("frgn", raw[name])
        elif "기관" in str(name):
            cols.setdefault("inst", raw[name])
        elif "개인" in str(name):
            # 개인 순매수 (2026-08-18) — 사장님이 주신 수급 논문 재현 재료.
            # ⚠️ **수집만 한다.** 챔피언 피처 부착(attach_krx_flows)은
            #    외국인·기관 그대로다 — 피처 구성은 동결(STRUCTURE_EPOCH)
            #    상태고, 외부 검토 ③도 "피처는 추가가 아니라 삭제"였다.
            #    이 열은 수급 3주체를 함께 보는 **도전자**만 읽는다.
            cols.setdefault("indi", raw[name])
    if "frgn" not in cols:
        # 컬럼 이름이 바뀌면 값은 멀쩡한데 피처만 사라진다 — 가장 찾기 어려운
        # 고장이므로, 실제로 뭐가 왔는지를 장부에 그대로 남긴다.
        raise RuntimeError(
            f"'외국인' 컬럼이 없다 — 받은 컬럼: {list(raw.columns)[:6]}")
    out = pd.DataFrame(cols)
    out.index = pd.DatetimeIndex(out.index).normalize()
    return out[~out.index.duplicated(keep="last")].sort_index()


def fetch_fundamental(symbol: str, limit: int = 800) -> pd.DataFrame | None:
    """일자별 PER·PBR·배당수익률 — KRX 공개 통계(pykrx). 한국 종목만.

    2026-08-19, 사장님이 주신 KIS API 가치투자 사례의 채택. KRX가 매일
    산출·공표하는 값이라 무료·공개·재현 가능하다. 실패 규약은 수급과 같다:
    원인을 아는 실패는 사유를 들고 예외로 올라간다.
    """
    code = symbol.split(".")[0]
    if not code.isdigit():
        return None
    try:
        from pykrx import stock
    except ImportError as exc:
        raise RuntimeError("pykrx 미설치 — 배치에는 설치돼 있어야 한다") from exc
    end = _dt.date.today()
    start = end - _dt.timedelta(days=int(limit * 1.6))
    try:
        raw = stock.get_market_fundamental_by_date(
            start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), code)
    except Exception as exc:  # noqa: BLE001
        log.warning("KRX 재무 조회 실패 %s: %s", symbol, exc)
        raise RuntimeError(
            f"KRX 재무 조회 실패({type(exc).__name__}: {exc})") from exc
    if raw is None or len(raw) == 0:
        raise RuntimeError(
            f"KRX가 {start:%Y-%m-%d}~{end:%Y-%m-%d} 재무 표를 비워서 줬다")
    cols = {}
    for name in raw.columns:
        key = str(name).upper()
        if key == "PER":
            cols["per"] = raw[name]
        elif key == "PBR":
            cols["pbr"] = raw[name]
        elif key == "DIV":
            cols["div"] = raw[name]
    if "pbr" not in cols:
        raise RuntimeError(
            f"PBR 컬럼이 없다 — 받은 컬럼: {list(raw.columns)[:6]}")
    out = pd.DataFrame(cols)
    out.index = pd.DatetimeIndex(out.index).normalize()
    return out[~out.index.duplicated(keep="last")].sort_index()


def attach_krx_value(df: pd.DataFrame, symbol: str,
                     fetch=fetch_fundamental) -> pd.DataFrame:
    """val_per·val_pbr·val_div를 부착한다(도전자 전용). 실패 시 원본.

    ⚠️ 이름이 x_로 시작하지 않는 것은 flow_indi5와 같은 동결 장치다 —
       챔피언 피처 빌더(ml._features)는 x_* 컬럼을 전부 자동 포함하므로,
       x_ 이름으로 붙이면 챔피언 입력이 조용히 바뀐다(구조 동결 위반).
       이 컬럼들은 가치 도전자(value_anchor)만 읽는다.
    수준(레벨) 그대로 붙인다 — 가치는 z-점수가 아니라 수준 자체가 뜻이다
    (PBR 0.8과 8.0의 차이). 0 이하 값(적자 PER 등)은 결측으로 둔다.
    """
    try:
        fund = fetch(symbol)
        if fund is None or fund.empty:
            note_source_failure(df, "krx_value",
                                f"KRX 재무가 비어 있음({symbol}이 한국 종목 "
                                "코드가 아닐 수 있다)")
            return df
        out = df.copy()
        target = pd.DatetimeIndex(out.index).normalize()
        for col, feat in (("per", "val_per"), ("pbr", "val_pbr"),
                          ("div", "val_div")):
            if col not in fund.columns:
                continue
            s = pd.to_numeric(fund[col], errors="coerce")
            if col in ("per", "pbr"):
                # 0·음수 PER/PBR(적자·자본잠식 표기)은 '싸다'가 아니라
                # '재지 못한다'다 — 결측으로 둔다. 배당 0은 진짜 0이다.
                s = s.where(s > 0)
            out[feat] = pd.Series(s.reindex(target, method="ffill").to_numpy(),
                                  index=out.index)
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("KRX 재무 부착 실패 %s: %s", symbol, exc)
        note_exception(df, "krx_value", exc)
        return df


def attach_krx_flows(df: pd.DataFrame, symbol: str,
                     fetch=fetch_investor_net) -> pd.DataFrame:
    """x_frgn5·x_inst5(5일 순매수 합의 60일 z-점수)를 부착한다. 실패 시 원본."""
    try:
        flows = fetch(symbol)
        if flows is None or flows.empty:
            # 여기 남는 것은 '한국 종목이 아니다' 정도다. 원인을 아는 실패는
            # 예외로 올라와 아래 except가 **그 사유 그대로** 적는다(감사 272).
            note_source_failure(df, "krx_flows",
                                f"KRX 투자자별 순매수가 비어 있음({symbol}이 "
                                "한국 종목 코드가 아닐 수 있다)")
            return df
        out = df.copy()
        target = pd.DatetimeIndex(out.index).normalize()
        # flow_indi5(개인)는 2026-08-18부터 붙는 **도전자 전용** 컬럼이다.
        # ⚠️ 이름이 x_로 시작하지 않는 것은 실수가 아니라 동결 장치다:
        #    챔피언의 피처 빌더(ml._features)는 x_* 컬럼을 **전부 자동
        #    포함**하므로, x_indi5로 붙이면 챔피언 입력이 조용히 바뀐다
        #    (구조 동결 위반). x_ 규약 밖 이름은 챔피언 세계(피처 행렬·
        #    건강 계측기)에 보이지 않고, 수급 3주체를 함께 보는 도전자
        #    (supply_som)만 이 컬럼을 읽는다(논문 원형 재현).
        for col, feat in (("frgn", "x_frgn5"), ("inst", "x_inst5"),
                          ("indi", "flow_indi5")):
            if col not in flows.columns:
                continue
            s5 = flows[col].rolling(5).sum()
            mu = s5.rolling(60).mean()
            # ⚠️ `pd.NA`가 아니라 `np.nan`이어야 한다(감사 173).
            #    `replace(0.0, pd.NA)`는 계열을 **object dtype**으로 바꾸고,
            #    바로 다음 줄의 `.astype(float)`가 NAType에서 터진다:
            #        TypeError: float() argument must be ... not 'NAType'
            #    그 예외를 아래 `except Exception`이 삼켜서 **수급 피처
            #    두 개가 통째로 사라진다** — 그 구간만이 아니라 그 종목의
            #    그날 전체가 없어진다. 로그 한 줄 말고는 흔적이 없다.
            #
            #    표준편차가 정확히 0이 되는 때: 5일 합이 60일 내내 같을 때
            #    (수급이 0으로만 기록되는 저유동 종목·장기 거래정지·API가
            #    결측을 0으로 채우는 경우). 흔치 않지만 하필 그런 종목에서
            #    맥락 피처가 조용히 사라지는 것이 제일 나쁘다.
            sd = s5.rolling(60).std().replace(0.0, np.nan)
            z = ((s5 - mu) / sd).astype(float).clip(-4.0, 4.0)
            out[feat] = pd.Series(z.reindex(target, method="ffill").to_numpy(),
                                  index=out.index)
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("KRX 수급 부착 실패 %s: %s", symbol, exc)
        note_exception(df, "krx_flows", exc)
        return df
