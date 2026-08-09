"""SNS 자동 게시 콘텐츠 생성 — 매일의 장부를 카드·캡처·설명글로 만든다.

매일 아침(자동화) 스레드·인스타그램에 올릴 재료를 만든다:
    1. 이미지 계획: 카드 썸네일(오늘의 성적표) + 사이트 페이지 캡처 여러 장
       — 실제 스크린샷은 워크플로의 헤드리스 크롬이 찍는다(이 모듈은 계획만).
    2. 설명글(캡션): 장부(status.json)에서 그날의 숫자를 읽어 정직하게 쓴다.
       인스타용(김)과 스레드용(500자 제한) 두 벌.

⚠️ 정직 원칙 — 캡션은 절대 수익을 약속하지 않는다. 모의투자임을 매번 밝히고,
   실제 장부 숫자(마이너스 포함)를 그대로 쓴다. 잘 나온 날만 올리는 선택 편향도
   없다: 매일 그날의 숫자가 그대로 나간다. 이것이 이 채널의 정체성이다.
"""
from __future__ import annotations

import json
import os

# 게시 이미지 계획 — (파일명, 사이트 상대경로). 워크플로가 이 순서대로 캡처한다.
# 사이트 화면 캡처가 아니라 인스타그램 카드뉴스 비율(4:5, 1080×1350)로
# 디자인된 전용 템플릿(sns_card.html)을 촬영한다. 3장 구성:
#   ①표지(훅) ②오늘의 숫자 ③새벽의 오디션 ④배분 ⑤판단의 속
#   ⑥확률 채점 ⑦왜 믿나 ⑧내일 예고·CTA — 페이지마다 메시지 하나씩
CAPTURE_PLAN = [(f"{i:02d}_card.png", f"sns_card.html?n={i}")
                for i in range(1, 9)]          # 8장 스토리 카드뉴스

# 카드뉴스 캔버스 크기 — 인스타 피드 최적(4:5). 워크플로 캡처 창 크기와 일치.
CARD_SIZE = (1080, 1350)

DEFAULT_SITE_URL = "https://quant.jiwon-1a2.workers.dev"
THREADS_TEXT_LIMIT = 500

HASHTAGS = "#퀀트 #AI투자 #모의투자 #알고리즘트레이딩 #8마일챌린지"


def _fmt_won(v: float) -> str:
    return f"{v:,.0f}원"


def _today_numbers(status: dict) -> dict:
    """status.json에서 캡션에 쓸 그날의 숫자를 뽑는다 (없는 값은 None)."""
    port = (status.get("paper") or {}).get("portfolio:ALL") or {}
    hist = port.get("history") or []
    last = hist[-1] if hist else {}
    date = last.get("date") or status.get("updated", "")[:10]
    # 그날의 재학습 결과 — 교체/유지 수 (retrain_recent에서 그날 것만 집계)
    recent = [r for r in (status.get("retrain_recent") or [])
              if r.get("asof") == date]
    swaps = sum(1 for r in recent if r.get("promoted"))
    # 배분 상위 종목 — "오늘 AI가 어디에 실었나"의 하이라이트
    alloc = last.get("alloc") or {}
    names = status.get("symbols") or {}
    top = sorted(alloc.items(), key=lambda kv: -kv[1])[:3]
    top_names = [names.get(k, {}).get("name") or k.split(":")[-1]
                 for k, v in top if v > 0]
    return {
        "date": date,
        "equity": last.get("equity"),
        "return_pct": last.get("return_pct"),
        "twr_pct": last.get("twr_pct"),
        "gross": last.get("weight"),
        "risk_scale": last.get("risk_scale", 1.0),
        "n_symbols": (last.get("champion") or {}).get("symbols"),
        "retrain_total": len(recent),
        "retrain_swaps": swaps,
        "top_names": top_names,
        "day_no": len(hist),
    }


def _hook(x: dict) -> str:
    """첫 줄(훅) — 그날 실제로 일어난 일에서 나온다. 과장 금지, 데이터 결정적.

    잘 쓴 훅은 감탄사가 아니라 '숨기지 않는 태도'다: 손실이 나면 손실이
    첫 줄이다. 그게 이 계정을 다른 수익 인증 계정과 다르게 만든다.
    """
    r = x["return_pct"]
    if x["risk_scale"] < 1.0:
        return ("킬스위치가 작동 중입니다. 손실이 한도를 넘으면 시스템이 "
                "스스로 물러나는 게 규칙이고, 오늘이 그 날입니다.")
    if r is None:
        return "오늘의 장부를 공개합니다."
    if r <= -1.0:
        return (f"오늘 {r:+.2f}%. 아픈 날도 그대로 올립니다 — "
                "그게 이 계정의 규칙입니다.")
    if r < 0:
        return f"오늘 {r:+.2f}%. 이 마이너스도 기록의 일부입니다."
    if r == 0:
        return "오늘은 거의 움직이지 않았습니다. 지루한 날도 기록입니다."
    if r < 1.0:
        return f"오늘 {r:+.2f}%. 작지만, 하루하루가 쌓여야 복리입니다."
    return (f"오늘 {r:+.2f}%. 좋은 날이지만 하루로는 아무것도 "
            "증명되지 않습니다 — 분포가 증명합니다.")


def build_captions(status: dict, site_url: str = DEFAULT_SITE_URL) -> dict:
    """장부 숫자로 인스타/스레드 캡션을 만든다. 반환: {"instagram", "threads", "date"}.

    구조(수동 게시에도 그대로 쓸 수 있는 완성 원고):
        훅(그날의 사건) → 실험 소개 한 줄 → 숫자 블록 → 오늘 AI가 한 일 →
        정직 고지 → 링크·태그.
    스레드는 500자 제한이 있어 짧은 판을 따로 만든다(자르다 만 문장 금지).
    """
    x = _today_numbers(status)
    date = x["date"] or "오늘"
    day = f"D+{x['day_no']}" if x["day_no"] else ""
    eq = _fmt_won(x["equity"]) if x["equity"] is not None else "—"
    ret = (f"{x['return_pct']:+.2f}%" if x["return_pct"] is not None else "—")
    twr = (f"{x['twr_pct']:+.2f}%" if x.get("twr_pct") is not None else None)
    gross = (f"{x['gross'] * 100:.0f}%" if x["gross"] is not None else "—")
    tops = " · ".join(x["top_names"]) if x["top_names"] else "전 종목 관망"
    kill = ("" if x["risk_scale"] >= 1.0 else
            f"\n🛑 킬스위치 — 낙폭 한도 초과로 노출 {x['risk_scale']:.0%} 제한")

    # "오늘 AI가 한 일" — 교체가 있으면 교체가 뉴스, 없으면 유지가 뉴스다
    if not x["retrain_total"]:
        work = "오늘 새벽 재학습 기록이 없습니다(휴장 또는 지연)."
    elif x["retrain_swaps"]:
        work = (f"오늘 새벽 {x['retrain_total']}개 종목을 재학습해 "
                f"{x['retrain_swaps']}개 종목의 전략이 교체됐습니다. "
                "교체는 2단계 검증(선발전+결승전)을 통과했을 때만 일어납니다.")
    else:
        work = (f"오늘 새벽 {x['retrain_total']}개 종목을 재학습했지만 "
                "챔피언을 이긴 후보가 없어 전부 유지 — 교체가 없는 날이 "
                "정상입니다. 확실히 나은 것만 바꾸는 게 규칙이니까요.")

    twr_line = f" · 실력지표(TWR) {twr}" if twr else ""
    ig = (
        f"{_hook(x)}\n"
        f"\n"
        f"📊 8마일 챌린지 {day} — {date}\n"
        f"가짜 돈 8만원으로 시작해 매일 새벽 AI가 스스로 재학습·매매하는 "
        f"공개 실험. 목표는 1억이 아니라, '이 과정 전체를 숨김없이 "
        f"보여주는 것'입니다.\n"
        f"\n"
        f"💰 자산 {eq} ({ret}){twr_line}\n"
        f"📈 총노출 {gross} · 20종목 분산(코인·한국·미국)\n"
        f"🎯 오늘 배분 상위: {tops}{kill}\n"
        f"\n"
        f"🤖 {work}\n"
        f"\n"
        f"⚠️ 모의투자(페이퍼)입니다. 수익을 보장하지 않으며, 방향 적중률의 "
        f"현실적 상한은 52~55%입니다. 잘된 날만 골라 올리지 않습니다 — "
        f"매일, 그날 숫자가 그대로 나갑니다. 판단·장부·코드 전부가 "
        f"공개돼 있어 누구든 검증할 수 있습니다.\n"
        f"\n"
        f"🔗 {site_url}\n"
        f"{HASHTAGS}"
    )

    th = (
        f"{_hook(x)}\n"
        f"\n"
        f"📊 8마일 챌린지 {day} · {date}\n"
        f"💰 {eq} ({ret}) · 노출 {gross}\n"
        f"🎯 배분 상위: {tops}{kill}\n"
        f"⚠️ 모의투자 — 수익 보장 없음. 매일 그날 숫자 그대로.\n"
        f"🔗 {site_url}"
    )
    if len(th) > THREADS_TEXT_LIMIT:      # 링크·고지는 지키고 하이라이트를 줄인다
        th = (
            f"📊 8마일 챌린지 {day} · {date}\n"
            f"💰 {eq} ({ret})\n"
            f"⚠️ 모의투자 — 수익 보장 없음. 매일 그날 숫자 그대로.\n"
            f"🔗 {site_url}"
        )
    return {"instagram": ig, "threads": th, "date": date}


def write_content(docs_dir: str = "docs",
                  site_url: str = DEFAULT_SITE_URL) -> dict:
    """docs/social/<날짜>/ 에 캡션·메타를 쓴다. 반환: meta(dict).

    이미지 파일은 워크플로의 헤드리스 크롬이 CAPTURE_PLAN대로 같은 폴더에
    찍는다. 폴더가 날짜별이라 URL이 매일 달라 CDN 캐시 문제도 없다.
    """
    with open(os.path.join(docs_dir, "status.json"), encoding="utf-8") as f:
        status = json.load(f)
    caps = build_captions(status, site_url)
    date = caps["date"]
    out_dir = os.path.join(docs_dir, "social", date)
    os.makedirs(out_dir, exist_ok=True)
    meta = {
        "date": date,
        "site_url": site_url,
        "images": [f for f, _ in CAPTURE_PLAN],
        "pages": {f: p for f, p in CAPTURE_PLAN},
    }
    for name, text in (("caption_instagram.txt", caps["instagram"]),
                       ("caption_threads.txt", caps["threads"])):
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
            f.write(text)
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    # latest.json — 어드민의 '오늘의 SNS 콘텐츠' 카드가 읽는 포인터.
    # 수동 게시 흐름: 어드민 열기 → 캡션 복사 → 이미지 저장 → 업로드 끝.
    latest = {**meta, "path": f"social/{date}",
              "captions": {"instagram": caps["instagram"],
                           "threads": caps["threads"]}}
    with open(os.path.join(docs_dir, "social", "latest.json"), "w",
              encoding="utf-8") as f:
        json.dump(latest, f, ensure_ascii=False, indent=2)
    return {**meta, "dir": out_dir}


def prune_old(docs_dir: str = "docs", keep: int = 14) -> list[str]:
    """오래된 게시 폴더를 지운다(저장소 무한 성장 방지). 반환: 지운 폴더명."""
    import shutil
    root = os.path.join(docs_dir, "social")
    if not os.path.isdir(root):
        return []
    dirs = sorted(d for d in os.listdir(root)
                  if os.path.isdir(os.path.join(root, d)))
    removed = []
    for d in dirs[:-keep] if len(dirs) > keep else []:
        shutil.rmtree(os.path.join(root, d), ignore_errors=True)
        removed.append(d)
    return removed
