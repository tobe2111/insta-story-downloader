"""매일 시장 브리핑 — 주요 뉴스 헤드라인 수집 (표시 전용).

방송·사이트에 "오늘의 시장 브리핑"으로 보여줄 헤드라인을 무료 RSS(구글 뉴스)
에서 모은다. 외부 키가 필요 없고 표준 라이브러리만으로 파싱한다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 정직성 원칙: 이 브리핑은 매매 판단에 사용되지 않는다.
    뉴스 감성을 신호로 쓰려면 '그 해석법이 과거에 통했다'는 검증이 필요한데,
    과거 뉴스는 미래를 미리 안 것처럼 계산되는 오염(look-ahead)이 생기기 쉽다.
    그래서 브리핑은 시청자용 참고 정보로만 표시하고, 화면에도 그렇게 명시한다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET

from quant.utils.logging import get_logger

log = get_logger("live.briefing")

STATE_DIR = "state"
BRIEFING_FILE = "briefing.json"
NOTE = "판단에 사용되지 않는 참고 정보입니다 — 매매는 검증된 챔피언 전략만 수행합니다."

# 무료·무키 RSS 피드 — 구글 뉴스 검색 결과. 카테고리별 상위 몇 개만 쓴다.
FEEDS = [
    ("증시", "https://news.google.com/rss/search?"
             "q=%EC%A6%9D%EC%8B%9C%20OR%20%EC%BD%94%EC%8A%A4%ED%94%BC%20OR%20"
             "%EB%82%98%EC%8A%A4%EB%8B%A5&hl=ko&gl=KR&ceid=KR:ko"),
    ("금리·환율", "https://news.google.com/rss/search?"
             "q=%EA%B8%88%EB%A6%AC%20OR%20%ED%99%98%EC%9C%A8%20OR%20"
             "%EC%97%B0%EC%A4%80&hl=ko&gl=KR&ceid=KR:ko"),
    ("코인", "https://news.google.com/rss/search?"
             "q=%EB%B9%84%ED%8A%B8%EC%BD%94%EC%9D%B8%20OR%20"
             "%EC%9D%B4%EB%8D%94%EB%A6%AC%EC%9B%80&hl=ko&gl=KR&ceid=KR:ko"),
]


def parse_rss(xml_text: str, category: str, top_n: int = 4) -> list[dict]:
    """RSS 2.0 문서에서 상위 헤드라인을 뽑는다 (표준 라이브러리만 사용).

    형식이 어긋난 항목은 조용히 건너뛴다 — 뉴스 하나 때문에 브리핑 전체가
    죽으면 안 된다. 반환: [{"cat","title","source","link","time"}].
    """
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    for item in root.iter("item"):
        if len(items) >= top_n:
            break
        try:
            title = (item.findtext("title") or "").strip()
            if not title:
                continue
            # 구글 뉴스 제목은 "제목 - 언론사" 형식 — 언론사를 분리한다
            source = (item.findtext("source") or "").strip()
            if not source and " - " in title:
                title, source = title.rsplit(" - ", 1)
            items.append({
                "cat": category,
                "title": title[:120],
                "source": source[:40],
                "link": (item.findtext("link") or "").strip()[:500],
                "time": (item.findtext("pubDate") or "").strip()[:40],
            })
        except Exception:  # noqa: BLE001
            continue
    return items


def collect_briefing(state_dir: str = STATE_DIR, *,
                     date: str | None = None) -> dict:
    """피드를 순회해 브리핑을 만들고 state/briefing.json에 저장한다.

    네트워크 실패는 피드 단위로 격리 — 일부만 성공해도 그만큼 보여준다.
    전 피드 실패면 items가 빈 브리핑이 저장된다(화면은 섹션을 생략).
    """
    from datetime import date as _date

    from quant.utils.http import get_text
    from quant.utils.jsonio import atomic_write_json

    items: list[dict] = []
    seen: set[str] = set()
    for category, url in FEEDS:
        try:
            xml_text = get_text(url, {"User-Agent": "Mozilla/5.0 (quant-briefing)"},
                                timeout=15)
        except Exception as exc:  # noqa: BLE001
            log.warning("브리핑 피드 실패(%s): %s", category, exc)
            continue
        for it in parse_rss(xml_text, category):
            if it["title"] in seen:            # 카테고리 간 중복 제거
                continue
            seen.add(it["title"])
            items.append(it)

    briefing = {"date": date or _date.today().isoformat(),
                "items": items, "note": NOTE}
    atomic_write_json(os.path.join(state_dir, BRIEFING_FILE), briefing)
    print(f"📰 시장 브리핑: {len(items)}건 수집 ({briefing['date']})"
          + ("" if items else " — 전 피드 실패(다음 실행에서 재시도)"))
    return briefing


def load_briefing(state_dir: str = STATE_DIR) -> dict | None:
    """저장된 브리핑을 읽는다. 없거나 손상이면 None (화면은 섹션 생략)."""
    path = os.path.join(state_dir, BRIEFING_FILE)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None
