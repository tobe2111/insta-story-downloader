"""자료 → 글자. PDF·유튜브 자막·트레이딩뷰 Pine Script.

⚠️ 이 파일은 **글자를 꺼내오기만 한다.** 규칙 해석은 extract.py가, 실행 가능
   여부 판정은 spec.py가 한다. 셋을 섞으면 "왜 이 전략이 나왔는지"를 되짚을 수
   없게 된다.

⚠️ 실패는 **조용히 넘어가지 않는다.** 스캔한 이미지 PDF에서 글자가 안 나오면
   빈 문자열이 나오는데, 그걸 그냥 넘기면 사용자는 "내 자료엔 규칙이 없나 보다"로
   읽는다. 사실은 **읽지를 못한 것**이고, 할 일이 전혀 다르다(OCR을 돌리거나
   글자가 살아 있는 PDF를 다시 받아야 한다).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


class SourceError(RuntimeError):
    """자료를 글자로 못 바꿨다 — 이유를 사람 말로 담는다."""


@dataclass
class Loaded:
    text: str
    title: str
    source: dict          # {"kind": "pdf", "ref": ..., "pages": N}


# ── PDF ──────────────────────────────────────────────────────────

def load_pdf(path: str | Path, *, max_pages: int = 60) -> Loaded:
    """PDF에서 글자를 꺼낸다. pypdf가 없거나 이미지 PDF면 이유를 던진다."""
    p = Path(path)
    if not p.exists():
        raise SourceError(f"파일이 없습니다: {p}")
    try:
        from pypdf import PdfReader
    except ImportError as exc:      # noqa: PERF203
        raise SourceError(
            "PDF를 읽으려면 pypdf가 필요합니다 — `pip install pypdf` 후 다시 "
            "시도해 주세요. (핵심 기능이 아니라서 기본 설치에는 넣지 "
            "않았습니다.)") from exc
    try:
        reader = PdfReader(str(p))
        pages = list(reader.pages)[:max_pages]
        text = "\n".join((pg.extract_text() or "") for pg in pages)
    except Exception as exc:        # noqa: BLE001
        raise SourceError(f"PDF를 여는 데 실패했습니다: {exc}") from exc
    if not text.strip():
        raise SourceError(
            "이 PDF에서 글자를 한 자도 찾지 못했습니다 — 스캔한 이미지로 만든 "
            "PDF일 가능성이 높습니다. 글자가 살아 있는 PDF를 넣거나, OCR로 "
            "글자를 입힌 뒤 다시 시도해 주세요. "
            "**빈 자료를 '규칙이 없다'로 처리하지 않습니다.**")
    return Loaded(text, p.stem, {"kind": "pdf", "ref": p.name,
                                 "pages": len(pages)})


# ── 유튜브 ────────────────────────────────────────────────────────

_YT = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)([\w-]{11})")


def youtube_id(url: str) -> str | None:
    m = _YT.search(str(url or ""))
    return m.group(1) if m else None


def load_youtube(url: str, *, languages=("ko", "en")) -> Loaded:
    """유튜브 자막을 받아 글자로. 자막이 없으면 그렇게 말한다.

    ⚠️ **자동 생성 자막은 숫자를 자주 틀린다** — "이십일선"이 "20일선"으로 안
       나오거나 "60"이 "육십"으로 남는다. 그래서 못 뽑는 경우가 흔하고, 그건
       영상에 규칙이 없다는 뜻이 아니다. 이 사실을 사용자에게 그대로 알린다.
    """
    vid = youtube_id(url)
    if not vid:
        raise SourceError(
            f"유튜브 주소로 보이지 않습니다: {url}\n"
            f"youtube.com/watch?v=… 또는 youtu.be/… 형태여야 합니다.")
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        raise SourceError(
            "유튜브 자막을 받으려면 youtube-transcript-api가 필요합니다 — "
            "`pip install youtube-transcript-api` 후 다시 시도해 주세요.") from exc
    try:
        # ⚠️ 라이브러리 1.x에서 API가 통째로 바뀌었다(2026-08-18 실측):
        #    구버전 classmethod `get_transcript`가 사라지고 인스턴스
        #    `.fetch()`가 됐다. 새로 설치한 사용자는 전부 신버전을 받으므로
        #    두 세대를 모두 지원한다 — 안 하면 "자막이 없다"는 엉뚱한
        #    안내가 나간다(실제 원인은 우리 호출 방식).
        if hasattr(YouTubeTranscriptApi, "get_transcript"):
            parts = YouTubeTranscriptApi.get_transcript(
                vid, languages=list(languages))
        else:
            fetched = YouTubeTranscriptApi().fetch(vid,
                                                   languages=list(languages))
            parts = [{"text": getattr(s, "text", "")} for s in fetched]
    except Exception as exc:        # noqa: BLE001
        raise SourceError(
            f"이 영상의 자막을 받지 못했습니다({exc}). 자막이 꺼져 있거나 "
            f"{'/'.join(languages)} 자막이 없는 영상일 수 있습니다 — 영상에 "
            f"규칙이 없다는 뜻은 아닙니다.") from exc
    text = " ".join(str(x.get("text", "")) for x in parts)
    if not text.strip():
        raise SourceError("자막을 받았지만 내용이 비어 있습니다.")
    return Loaded(text, f"youtube-{vid}",
                  {"kind": "youtube", "ref": vid, "segments": len(parts)})


# ── 트레이딩뷰 Pine Script ────────────────────────────────────────
#
# ⚠️ Pine을 **해석**하지 않는다. Pine은 프로그래밍 언어라 우리 명세보다 훨씬
#    넓고, 절반만 옮기면 "당신 전략을 검증했습니다"가 거짓이 된다.
#    여기서는 주석과 흔한 관용구에서 **읽을 수 있는 것만** 글자로 넘기고,
#    나머지는 extract.py가 판단하게 둔다. 못 옮기는 Pine은 못 옮긴다고 말한다.

_PINE_HINT = re.compile(r"\b(ta\.(?:sma|ema|rsi|crossover|crossunder|highest|lowest))",
                        re.I)


def load_pine(path_or_text: str) -> Loaded:
    """Pine Script → 글자. 파일 경로거나 코드 본문."""
    p = Path(path_or_text)
    # ⚠️ 붙여넣은 **코드 본문**을 경로로 착각해 exists()를 부르면, 리눅스는
    #    한 경로 조각이 255바이트를 넘는 순간 False가 아니라 OSError(이름이
    #    너무 김)를 던진다 — 길이 4096 관문만으로는 못 막는다(2026-08-18,
    #    공개 스크립트 수집 시연에서 실제로 죽었다). 경로 확인이 어떤 이유로든
    #    실패하면 그냥 본문으로 다룬다 — 붙여넣기가 죽는 것보다 낫다.
    try:
        is_file = len(str(path_or_text)) < 4096 and p.exists()
    except OSError:
        is_file = False
    if is_file:
        body, title = p.read_text(encoding="utf-8", errors="replace"), p.stem
    else:
        body, title = str(path_or_text), "pine"
    if not body.strip():
        raise SourceError("Pine 스크립트가 비어 있습니다.")

    # ta.sma(close, 20) → "20봉 이동평균" 처럼 **읽을 수 있는 문장**으로 옮긴다.
    # 근거(quote)로 원본 줄이 그대로 남게 줄 단위로 처리한다.
    lines: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("//"):
            lines.append(line.lstrip("/ ").strip())      # 주석은 그대로 문장
            continue
        m = re.search(r"ta\.crossover\s*\(\s*ta\.sma\s*\([^,]+,\s*(\d+)\s*\)\s*,"
                      r"\s*ta\.sma\s*\([^,]+,\s*(\d+)\s*\)", line, re.I)
        if m:
            lines.append(f"{m.group(1)}일 이동평균선이 {m.group(2)}일 "
                         f"이동평균선을 상향 돌파하면 매수한다.")
            continue
        m = re.search(r"ta\.crossunder\s*\(\s*ta\.sma\s*\([^,]+,\s*(\d+)\s*\)\s*,"
                      r"\s*ta\.sma\s*\([^,]+,\s*(\d+)\s*\)", line, re.I)
        if m:
            lines.append(f"{m.group(1)}일 이동평균선이 {m.group(2)}일 "
                         f"이동평균선을 하향 돌파하면 매도한다.")
            continue
        m = re.search(r"ta\.rsi\s*\([^,]+,\s*(\d+)\s*\)\s*(<=?|>=?)\s*(\d+)", line, re.I)
        if m:
            way = "이하" if m.group(2).startswith("<") else "이상"
            what = "매수" if m.group(2).startswith("<") else "매도"
            lines.append(f"RSI가 {m.group(3)} {way}이면 {what}한다.")
            continue

    text = "\n".join(lines)
    if not text.strip():
        hint = ("이 스크립트에는 우리가 읽을 수 있는 부분이 없습니다."
                if not _PINE_HINT.search(body) else
                "이 스크립트는 우리 명세로 옮길 수 없는 계산을 씁니다.")
        raise SourceError(
            f"{hint}\n"
            f"Pine Script는 프로그래밍 언어라 여기서 쓰는 규칙 형식보다 훨씬 "
            f"넓습니다. **절반만 옮기면 '당신 전략을 검증했다'는 말이 거짓이 "
            f"되므로** 옮기지 않습니다.\n"
            f"대신 두 가지 길이 있습니다: ① 트레이딩뷰 알림(웹훅)을 연결하면 "
            f"스크립트는 그대로 두고 신호만 받아 실행합니다. ② 규칙을 한국어 "
            f"문장으로 적어 주시면 그대로 검증합니다.")
    return Loaded(text, title, {"kind": "pine", "ref": title})


# ── 무엇이든 받아서 알아서 ────────────────────────────────────────

def load_any(ref: str) -> Loaded:
    """경로·URL을 보고 알맞은 로더로. 모르면 글 파일로 읽는다."""
    s = str(ref)
    if youtube_id(s):
        return load_youtube(s)
    p = Path(s)
    if p.suffix.lower() == ".pdf":
        return load_pdf(p)
    if p.suffix.lower() in (".pine", ".ps"):
        return load_pine(str(p))
    if p.exists():
        body = p.read_text(encoding="utf-8", errors="replace")
        if not body.strip():
            raise SourceError(f"파일이 비어 있습니다: {p}")
        return Loaded(body, p.stem, {"kind": "text", "ref": p.name})
    raise SourceError(
        f"무엇인지 모르겠습니다: {ref}\n"
        f"지원: PDF(.pdf) · 유튜브 주소 · Pine 스크립트(.pine) · 글 파일(.txt/.md)")
