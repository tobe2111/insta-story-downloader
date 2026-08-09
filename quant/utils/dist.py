"""배포판 판별 — 실거래 경로를 '소스 설치 전용'으로 잠그는 표식.

배포되는 실행파일(릴리스 빌드)은 빌드 단계에서 quant/_dist_build.py
(DISTRIBUTION=True)를 구워 넣는다. 판매·배포본에 실계좌 주문 경로가
존재하면 구매자가 실거래로 돌리다 손실이 났을 때 "모의였다"는 방어가
성립하지 않는다(규제·책임 리스크). 그래서 배포판은 백테스트·검증·
페이퍼(모의)·조회 전용이며, 실거래는 소스 설치 환경에서만 동작한다.

소스 설치(깃 클론)에는 이 파일이 없으므로 아무 것도 잠기지 않는다.
"""
from __future__ import annotations


def is_distribution_build() -> bool:
    """릴리스 빌드에 구워진 배포판 표식이 있으면 True."""
    try:
        from quant import _dist_build  # type: ignore[attr-defined]
        return bool(getattr(_dist_build, "DISTRIBUTION", False))
    except ImportError:
        return False


def block_live_in_distribution() -> None:
    """배포판이면 실거래 진입을 명확한 한국어 메시지와 함께 중단한다."""
    if is_distribution_build():
        raise SystemExit(
            "🚫 이 배포판에는 실거래 기능이 없습니다 — 백테스트·검증·"
            "페이퍼(모의)·조회 전용입니다.\n   실거래는 소스 설치"
            "(git clone) 환경에서만 지원합니다.")
