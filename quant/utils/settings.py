"""운영 설정(config/settings.json) — 어드민 대시보드가 쓰고 자동화가 읽는다.

사장님이 사이트의 admin.html에서 클릭으로 바꾸는 값들이다(깃허브 커밋으로
저장). 새벽 자동화는 실행 시점에 이 파일을 읽어 따른다:

    trading_paused : true면 신규 매매 중단 — 보유 포지션은 유지, 대기 주문은
                     폐기(며칠 뒤 옛 시가로 체결되는 회계 왜곡 방지). 재학습·
                     기록은 계속 돈다(학습은 매매가 아니다).
    exposure_scale : 총노출 배수 [0,1] — 킬스위치와 곱으로 적용된다.
                     예: 0.5면 모든 목표 비중이 절반.
    social_post    : false면 SNS 자동 게시 중단(콘텐츠 생성도 건너뜀).
    note           : 어드민 메모(표시 전용).
    portfolio_target_vol : 통합 계좌의 목표 연 변동성. null이면 코드 기본값
                     (미입증 12% / 입증 후 20%)을 따른다. **미입증 상태에서는
                     아래 risk_override_ack 없이는 검증 목표를 넘길 수 없다** —
                     quant/risk/portfolio_vol.target_vol_now()가 상한을 건다.
    risk_override_ack : true면 엣지 미입증 상태에서도 목표를 상향할 수 있다.
                     소유자의 명시적 확인 — 실수로 켜지지 않게 별도 키다.

⚠️ 파일이 없거나 깨져도 자동화는 절대 죽지 않는다 — 안전한 기본값(정상
운용)으로 폴백한다. 설정 실수로 새벽 잡이 통째로 실패하는 것을 막기 위함.
다만 **조용히 폴백하지는 않는다**(감사 53). 폴백은 곧 "사장님이 누른
일시정지·노출 축소가 무시된다"는 뜻이라, 파일이 깨진 날에 시스템은 아무
일 없다는 듯 전액 노출로 매매한다. 파싱에 실패하면 경고를 남겨 새벽 잡
로그에 그대로 보이게 한다 — 죽지는 않되 숨기지도 않는다.

⚠️ 화이트리스트 규칙: load_settings()가 명시적으로 옮겨 담지 않은 키는 조용히
버려진다. 즉 **DEFAULTS에 없는 키는 코드가 아무리 읽어도 항상 None이다.**
2026-08-11에 portfolio_target_vol / risk_override_ack가 정확히 이 병으로
'아무도 못 돌리는 손잡이'였다 — tests/test_settings_contract.py가 코드가 읽는
모든 설정 키가 여기 있는지 검사한다.
"""
from __future__ import annotations

import json
import os

# 목표 변동성 허용 범위(연율) — 오타 방어. 상한 60%는 '무레버리지 전액투자
# 최악의 국면'보다도 위라 실질적으로 총노출 상한이 먼저 걸린다.
MIN_TARGET_VOL = 0.01
MAX_TARGET_VOL = 0.60

DEFAULTS = {
    "trading_paused": False,
    "exposure_scale": 1.0,
    "social_post": True,
    "note": "",
    # None = 코드 기본값(판정 게이트가 정한 값)을 쓴다
    "portfolio_target_vol": None,
    "risk_override_ack": False,
}

SETTINGS_PATH = os.path.join("config", "settings.json")


def _log():
    # 지연 임포트 — settings는 아주 이른 시점에도 불리므로 순환을 피한다.
    from quant.utils.logging import get_logger
    return get_logger("settings")


def load_settings(path: str = SETTINGS_PATH) -> dict:
    """설정을 읽어 검증·클램프한다. 없거나 깨지면 기본값(정상 운용)."""
    out = dict(DEFAULTS)
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            out["trading_paused"] = bool(raw.get("trading_paused", False))
            try:
                scale = float(raw.get("exposure_scale", 1.0))
            except (TypeError, ValueError):
                # 값이 있는데 못 읽었다 = 사장님이 줄이려던 노출이 100%로
                # 되돌아간다. 죽이지는 않되 반드시 로그에 남긴다.
                _log().warning(
                    "설정 exposure_scale 값을 읽지 못해 1.0(전액)으로 폴백합니다: %r "
                    "— 의도한 노출 축소가 무시되고 있습니다",
                    raw.get("exposure_scale"))
                scale = 1.0
            # [0,1] 클램프 — 오타(예: 10)가 10배 레버리지가 되면 안 된다
            out["exposure_scale"] = min(1.0, max(0.0, scale))
            out["social_post"] = bool(raw.get("social_post", True))
            out["note"] = str(raw.get("note", ""))[:500]
            tv = raw.get("portfolio_target_vol")
            if tv is not None and str(tv).strip() != "":
                try:
                    out["portfolio_target_vol"] = min(
                        MAX_TARGET_VOL, max(MIN_TARGET_VOL, float(tv)))
                except (TypeError, ValueError):
                    out["portfolio_target_vol"] = None
            out["risk_override_ack"] = bool(raw.get("risk_override_ack", False))
    except FileNotFoundError:
        pass                       # 파일 없음 = 아직 아무것도 안 바꿈(정상)
    except (OSError, ValueError) as exc:
        # 손상된 설정 파일 → 기본값으로 정상 운용. 하지만 그 기본값은
        # trading_paused=False, exposure_scale=1.0이다. 즉 사장님이 눌러 둔
        # 일시정지·노출 축소가 이 한 줄에서 사라진다. 조용히 넘기면 안 된다.
        _log().error(
            "설정 파일을 읽지 못해 기본값(정상 운용·전액 노출)으로 폴백합니다: "
            "%s — 일시정지/노출 축소 설정이 무시되고 있습니다: %s", path, exc)
    return out
