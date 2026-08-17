"""내 전략 고정(pin) — 설치형 사용자가 자기 계좌에서 자기 전략으로 매매하게 한다.

왜 있는가
    이 시스템의 기본은 "검증한 것만 쓴다"이다: 사용자가 넣은 전략(PDF·
    유튜브·직접 입력)은 도전자로 서고, 오디션을 이겨야만 매매를 맡는다.
    그런데 **자기 돈에는 자기 전략을 쓸 권리가 있다.** 설치형 사용자가
    "심사 결과와 무관하게 이 전략으로 매매해"라고 명시하면 그렇게 한다.

무엇을 팔고 무엇을 지키는가 — 전략은 사용자의 것, 안전장치는 우리의 것
    · **성적표**: 고정하기 전에 그 전략의 검증 성적(과최적화 지표, 오디션
      이력)을 보여주고, 확인 문구를 직접 타이핑해야 고정된다.
    · **브레이크는 어떤 전략 위에도 걸린다**: 킬스위치·변동성 타깃·검증
      게이트·레버리지 금지선은 신호가 어디서 왔는지 보지 않는다. 이 모듈은
      **신호의 출처만 바꾸고 크기 결정에는 손대지 않는다** — 여기에 사이징
      코드가 한 줄이라도 생기면 브레이크를 우회할 길이 생긴다.

설계 원칙
    · 고정은 별도 파일(state/pins.json)에 산다. 챔피언 기록(champions.json)은
      계속 "시스템이라면 무엇을 골랐을까"를 기록한다 — 고정을 풀면 그 판단이
      즉시 복귀하고, 고정돼 있는 동안에도 오디션은 매일 돌아 성적표가 쌓인다.
    · 고정할 때 전략 명세를 **통째로 얼려 저장**한다. 자료 폴더를 나중에
      고쳐도 고정된 전략은 바뀌지 않는다 — 결정의 전제는 결정과 함께
      보존한다(감사 습관). 바꾸려면 다시 고정해야 하고, 그때 새 성적표를 본다.
    · 우리 공개 실험 계좌에는 고정이 없다(파일이 없으면 아무 일도 없다).
      판정 시계·심사 원칙은 그대로다.
"""
from __future__ import annotations

import datetime as _dt
import json
import os

from quant.utils.logging import get_logger

log = get_logger("live.pin")

PINS_FILE = "pins.json"

# 고정할 때 사용자가 그대로 타이핑해야 하는 문구 — 클릭 한 번의 "확인"과
# 문장을 옮겨 적는 것은 다른 행동이다(실전 전환의 '실전' 타이핑과 같은 원리).
ACK_PHRASE = "검증되지 않은 전략임을 이해하고 고정합니다"


def _path(state_dir: str) -> str:
    return os.path.join(state_dir, PINS_FILE)


def load_pins(state_dir: str = "state") -> dict:
    """{key: {"name", "spec", "since", "ack"}} — 없으면 빈 dict."""
    p = _path(state_dir)
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError) as exc:
        # 깨진 고정 파일은 '고정 없음'으로 조용히 넘기면 안 된다 — 사용자는
        # 자기 전략이 돌고 있다고 믿는데 실제로는 시스템 챔피언이 돈다.
        log.error("고정 파일을 읽지 못했습니다(%s) — 고정을 무시하지 않고 "
                  "중단합니다. state/pins.json을 고치거나 지우세요.", exc)
        raise RuntimeError(f"고정 파일 손상: {exc}") from exc


def pinned_spec(market: str, symbol: str, state_dir: str = "state") -> dict | None:
    """이 종목에 고정된 전략 스펙 — 없으면 None (그러면 챔피언이 맡는다)."""
    entry = load_pins(state_dir).get(f"{market}:{symbol}")
    if not entry:
        return None
    return {"strategy": "spec", "params": {"spec": entry["spec"]}}


def save_pin(market: str, symbol: str, spec_name: str, ack: str,
             state_dir: str = "state") -> dict:
    """전략을 이 종목에 고정한다 — 확인 문구가 정확해야만.

    spec_name: `python -m quant ingest`로 저장된 전략 명세의 이름.
    ack: 사용자가 타이핑한 확인 문구(ACK_PHRASE와 정확히 일치해야 한다).
    """
    if ack.strip() != ACK_PHRASE:
        raise ValueError(
            f"확인 문구가 다릅니다. 정확히 이렇게 입력하세요: {ACK_PHRASE!r}")
    from quant.ingest.registry import load_specs
    specs, problems = load_specs(state_dir)
    match = [s for s in specs if s.name == spec_name]
    if not match:
        names = " · ".join(s.name for s in specs) or "(없음)"
        raise ValueError(
            f"'{spec_name}' 전략을 찾지 못했습니다. 저장된 전략: {names}"
            + (f" / 못 읽은 파일: {'; '.join(problems)}" if problems else ""))
    pins = dict(load_pins(state_dir))
    entry = {
        "name": spec_name,
        # 명세를 통째로 얼린다 — 자료 폴더를 나중에 고쳐도 고정은 그대로.
        "spec": match[0].to_dict(),
        "since": _dt.date.today().isoformat(),
        "ack": ACK_PHRASE,
    }
    pins[f"{market}:{symbol}"] = entry
    os.makedirs(state_dir, exist_ok=True)
    with open(_path(state_dir), "w", encoding="utf-8") as fh:
        json.dump(pins, fh, ensure_ascii=False, indent=2)
    return entry


def remove_pin(market: str, symbol: str, state_dir: str = "state") -> bool:
    """고정을 푼다 — 다음 실행부터 시스템 챔피언 판단이 즉시 복귀한다."""
    pins = dict(load_pins(state_dir))
    if pins.pop(f"{market}:{symbol}", None) is None:
        return False
    with open(_path(state_dir), "w", encoding="utf-8") as fh:
        json.dump(pins, fh, ensure_ascii=False, indent=2)
    return True


def scorecard(market: str, symbol: str, spec_name: str,
              state_dir: str = "state") -> list[str]:
    """고정 전에 보여주는 성적표 — 아는 것은 숫자로, 모르는 것은 모른다고.

    고정을 막는 장치가 아니다. **알고 고정하게 하는** 장치다.
    """
    key = f"{market}:{symbol}"
    lines = [f"📋 성적표 — {spec_name} @ {key}"]

    # ① 이 전략이 오디션에서 이긴 적이 있는가 (retrain_history에서)
    won = fought = 0
    path = os.path.join(state_dir, "retrain_history.jsonl")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for ln in fh:
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                if r.get("market") != market or r.get("symbol") != symbol:
                    continue
                for c in (r.get("user_specs") or []):
                    if (c.get("params") or {}).get("spec", {}).get("name") \
                            == spec_name:
                        fought += 1
                        if r.get("promoted") and (
                                (r.get("champion") or {}).get("strategy")
                                == "spec"):
                            won += 1
    if fought:
        lines.append(f"  · 오디션 출전 {fought}회 · 승격 {won}회"
                     + ("" if won else " — 아직 시스템 챔피언을 이긴 적 없음"))
    else:
        lines.append("  · 이 종목 오디션 기록 없음 — 내일 밤부터 도전자로 서며,"
                     " 고정과 무관하게 성적이 매일 쌓입니다")

    # ② 이 종목의 과최적화 검증 성적 (전략 무관, 종목 기준)
    try:
        from quant.live.validation_gate import validation_grades
        grade = validation_grades([key], state_dir).get(key)
        lines.append(f"  · 이 종목 과최적화 검증: {grade or '미측정'}"
                     " (미측정이면 투자 비중이 절반으로 깎입니다)")
    except Exception:  # noqa: BLE001
        lines.append("  · 이 종목 과최적화 검증: 확인 불가")

    lines.append("  · 고정해도 킬스위치·변동성 타깃·검증 게이트·레버리지"
                 " 금지선은 **그대로 걸립니다** — 전략은 당신의 것,"
                 " 브레이크는 꺼지지 않습니다")
    lines.append("  ⚠️ 이 전략은 승격 심사를 통과하지 않았습니다. 고정 중의"
                 " 손익은 시스템의 판단이 아니라 고정한 사람의 판단입니다.")
    return lines
