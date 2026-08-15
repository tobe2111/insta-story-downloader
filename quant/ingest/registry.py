"""가져온 명세를 **도전자로** 등록한다 — 챔피언으로는 절대 못 간다.

⚠️ 이 파일의 전부는 한 문장이다: **자료에서 나온 전략은 도전자다.**

   사용자가 넣은 것을 바로 쓰면 이 제품은 그냥 "남이 시키는 대로 사는 봇"이
   된다. 검증이 제품의 전부인데 새 전략만 그 검증을 건너뛰면 앞뒤가 안 맞는다.
   그래서 명세는 매일 밤 링에 서고, 선발전·결승전을 이기고, 검증 게이트를
   통과해야 돈이 간다. 못 이기면 못 이겼다고 사용자에게 그대로 말한다.

⚠️ **후보가 늘면 다중검정 보정도 같이 올라가야 한다.** 1,000번 시도해서 1등을
   고르면 그 1등은 원래 좋아 보인다(DSR이 존재하는 이유). 사용자 자료로 후보를
   늘리면서 그 사실을 검정에 안 넘기면 **검증이 통째로 틀린다** — 그러면 이
   기능은 제품을 돕는 게 아니라 제품의 심장을 끄는 기능이 된다.

   다행히 여기서는 따로 셀 필요가 없다. retrain은 `len(challengers)`로 시도
   수를 세므로, 명세를 challengers에 넣기만 하면 문턱이 저절로 올라간다.
   tests/test_ingested_specs_raise_the_bar.py가 그게 실제로 그런지 값으로 본다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from quant.ingest.spec import SpecError, StrategySpec, spec_from_dict

# 사용자 명세가 사는 곳. 환경변수로 옮길 수 있다(여러 사용자·격리 실행).
SPEC_DIR_ENV = "QUANT_SPEC_DIR"
DEFAULT_SPEC_DIR = "specs_user"

# 한 종목이 하루에 받을 수 있는 사용자 도전자 수 상한.
#
# ⚠️ 상한이 없으면 사용자가 자료 500개를 넣는 순간 그날 후보가 500개가 되고,
#    다중검정 문턱이 치솟아 **다른 모든 후보가 영원히 승격 못 하게 된다.**
#    한 사람의 자료 더미가 시스템 전체의 진화를 멈추는 셈이다.
#    자르되 **자른 사실을 남긴다**(감사 습관: 조용한 절단 금지).
MAX_USER_CHALLENGERS = 12


def spec_dir(state_dir: str | None = None) -> Path:
    if state_dir:
        return Path(state_dir) / DEFAULT_SPEC_DIR
    return Path(os.getenv(SPEC_DIR_ENV) or DEFAULT_SPEC_DIR)


def save_spec(spec: StrategySpec, *, state_dir: str | None = None) -> Path:
    """명세를 JSON으로 저장한다 — git에 남아 누구든 읽고 고칠 수 있게."""
    spec.validate()
    d = spec_dir(state_dir)
    d.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in spec.name)
    path = d / f"{safe}.json"
    path.write_text(json.dumps(spec.to_dict(), ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path


def load_specs(state_dir: str | None = None) -> tuple[list[StrategySpec], list[str]]:
    """저장된 명세 전부. 못 읽은 파일은 **이름과 이유**를 함께 돌려준다.

    ⚠️ 조용히 건너뛰면 사용자는 자기 전략이 매일 밤 링에 서고 있다고 믿는데
       실제로는 한 번도 안 선다. 이 저장소가 계속 잡아온 바로 그 종류의 침묵이다.
    """
    d = spec_dir(state_dir)
    specs: list[StrategySpec] = []
    problems: list[str] = []
    if not d.exists():
        return specs, problems
    for fp in sorted(d.glob("*.json")):
        try:
            specs.append(spec_from_dict(json.loads(fp.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{fp.name}: 파일을 읽지 못했습니다 — {exc}")
        except SpecError as exc:
            problems.append(f"{fp.name}: {exc}")
    return specs, problems


def user_challengers(state_dir: str | None = None,
                     limit: int = MAX_USER_CHALLENGERS) -> tuple[list[dict], list[str]]:
    """저장된 명세 → retrain이 쓰는 도전자 dict 목록.

    반환: (도전자들, 사람에게 알릴 말). 두 번째가 비어 있어야 정상이다.
    """
    specs, notes = load_specs(state_dir)
    if len(specs) > limit:
        notes.append(
            f"사용자 전략이 {len(specs)}개인데 하루 링에는 {limit}개까지만 "
            f"세웁니다. 후보가 많을수록 승격 문턱이 올라가 **다른 전략까지** "
            f"승격하기 어려워지기 때문입니다. 이번에 빠진 전략: "
            + " · ".join(s.name for s in specs[limit:]))
        specs = specs[:limit]
    return ([{"strategy": "spec", "params": {"spec": s.to_dict()}} for s in specs],
            notes)
