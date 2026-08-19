#!/usr/bin/env python3
"""빠진 봉을 **다시 계산해서** 채운다 (2026-08-19, 사장님 지시).

⚠️ 이 도구가 왜 있나.

   2026-08-16·17·18 사흘 동안 페이퍼 배치가 계산은 끝내 놓고 커밋을 못 했다.
   장부 관문이 셋 다 **다른 이유로** 막았기 때문이다.

     08-16  판정일이 2026-08-14로 뒷걸음쳐 같은 날이 두 번 적히려 했다.
            코인 시세가 165일 묵어 있었다(감사 261·262). → **결과가 없다.**
            고장난 입력으로 만든 하루라 채울 것이 없다.
     08-17  브라우저를 못 띄워 관문 자체가 죽었다(감사 280).
            장부는 멀쩡했다 — `자산 999,267.50 (-0.07%) · 총노출 18%`.
     08-18  새로 넣은 필드가 화면에 없다고 막혔다(감사 286).
            장부는 멀쩡했다 — `자산 1,000,116.77 (+0.01%) · 총노출 25%`.

   즉 08-17·18은 **시스템이 실제로 낸 판단**이 있고 저장만 못 했다.
   그 이틀을 되살린다.

⚠️ **손으로 숫자를 적지 않는다.** 그날 봉까지만 잘라서 같은 계산을 다시
   돌린다. 잘 됐는지는 그날 로그에 찍힌 자산으로 **검산**한다 — 똑같이
   나오면 그날 결과가 맞다는 증거이고, 다르면 다르다고 보고한다.
   깃허브 로그는 우리가 못 고치는 제3자 기록이라 검산값으로 쓸 수 있다.

⚠️ 장부는 '그날 성적 목록'이 아니라 **굴러가는 계좌**다. 그래서 자산
   숫자만 끼워 넣는 방식은 쓰지 않는다 — 그 이틀의 보유·현금이 비면
   다음 날 계산이 통째로 어긋난다. 다시 돌리는 길만이 줄과 상태를
   함께 만든다.

쓰는 법 (네트워크가 열린 곳에서만 — 시세를 못 받으면 합성 데이터로
폴백하고, 합성으로 만든 기록은 이 도구가 거부한다):

    python3 scripts/recover_missing_bars.py \
        --bar 2026-08-17 --expect 999267.50 --crypto-asof 2026-03-04 \
        --bar 2026-08-18 --expect 1000116.77
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 검산 허용 오차(원). 0이면 완전 일치만 인정한다.
DEFAULT_TOLERANCE = 0.005


class _Truncated:
    """그날까지만 보이는 시세 제공자.

    ⚠️ 시장마다 자르는 날이 다를 수 있다. 2026-08-17 밤 실제 배치는 코인
       시세가 2026-03-04에 멈춘 상태로 판단했다(감사 261). 오늘은 그 경로가
       고쳐져 최신 봉이 오므로, 그날을 재현하려면 코인만 따로 잘라야 한다.
       **그날 시스템이 본 것과 같은 것을 보여 주는 것**이 재현이다 —
       오늘의 더 좋은 데이터를 넣으면 그건 재현이 아니라 새 계산이다.
    """

    def __init__(self, inner, asof: str, market: str, crypto_asof: str | None):
        self._inner = inner
        self._asof = asof
        self._market = market
        self._crypto_asof = crypto_asof

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def get_ohlcv(self, symbol, timeframe="1d", start=None, end=None,
                  limit=500, **kw):
        cut = (self._crypto_asof if (self._market == "crypto"
                                     and self._crypto_asof) else self._asof)
        # 자른 뒤에도 원하는 봉 수가 남도록 넉넉히 받아 온다.
        df = self._inner.get_ohlcv(symbol, timeframe, start=start, end=end,
                                   limit=int(limit) + 400, **kw)
        attrs = dict(getattr(df, "attrs", {}) or {})
        # 봉 끝시각이 그날 자정이라도 그날 봉이다 — 날짜로 자른다.
        keep = [i for i in df.index if str(i)[:10] <= cut]
        out = df.loc[keep].tail(int(limit))
        out.attrs.update(attrs)
        return out


def _install(asof: str, crypto_asof: str | None):
    import quant.data as qd

    real = qd.get_provider

    def patched(market, *a, **kw):
        return _Truncated(real(market, *a, **kw), asof, market, crypto_asof)

    qd.get_provider = patched
    return lambda: setattr(qd, "get_provider", real)


def _equity_of(state_dir: str) -> tuple[str | None, float | None]:
    p = os.path.join(state_dir, "paper", "portfolio_ALL.json")
    with open(p, encoding="utf-8") as f:
        st = json.load(f)
    hist = st.get("history") or []
    if not hist:
        return None, None
    return hist[-1].get("date"), hist[-1].get("equity")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bar", action="append", default=[],
                    help="되살릴 봉 날짜(YYYY-MM-DD). 순서대로 여러 번.")
    ap.add_argument("--expect", action="append", default=[],
                    help="그날 로그에 찍힌 자산(검산값). --bar와 같은 순서.")
    ap.add_argument("--crypto-asof", action="append", default=[],
                    help="코인만 다른 날로 자를 때(빈 문자열이면 --bar와 같음).")
    # 쉼표 목록으로도 받는다. 워크플로가 사용자 입력을 **셸에 펼치지 않고**
    # env로 넘길 수 있어야 하기 때문이다(스크립트 인젝션 방어 —
    # tests/test_workflow_injection.py가 이 저장소의 규칙으로 못 박아 두었다).
    ap.add_argument("--bars", default="", help="되살릴 봉들(쉼표)")
    ap.add_argument("--expects", default="", help="검산값들(쉼표·같은 순서)")
    ap.add_argument("--crypto-asofs", default="",
                    help="코인 기준일들(쉼표·같은 순서·빈칸 허용)")
    ap.add_argument("--state-dir", default="state")
    # ⚠️ 화면 파일 자리를 인자로 받는다. 기본값이 저장소의 진짜 파일이라
    #    검사가 이 도구를 부르면 그 파일을 덮어쓴다 — 실제로 한 번 그렇게
    #    깨뜨렸다(변이 시험 중 기록 3개짜리 status.json이 1개로 줄었고,
    #    화면 검사 여섯 개가 무너졌다). 부르는 쪽이 자기 상자를 지정할 수
    #    있어야 상자 밖으로 새지 않는다.
    ap.add_argument("--docs-status",
                    default=os.path.join("docs", "status.json"))
    ap.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    ap.add_argument("--write", action="store_true",
                    help="검산을 통과한 경우에만 장부에 남긴다(기본은 시험 실행).")
    args = ap.parse_args()

    def _split(v):
        return [x.strip() for x in v.split(",")] if v.strip() else []

    args.bar = args.bar or [x for x in _split(args.bars) if x]
    args.expect = args.expect or [x for x in _split(args.expects) if x]
    args.crypto_asof = args.crypto_asof or _split(args.crypto_asofs)

    if not args.bar:
        print("되살릴 봉이 없습니다 — --bar 를 주세요.")
        return 2
    if len(args.expect) != len(args.bar):
        print("❌ --bar 와 --expect 개수가 다릅니다. 검산값 없이는 되살리지 "
              "않습니다 — 검산 없는 복원은 그냥 새 계산입니다.")
        return 2
    casof = list(args.crypto_asof) + [""] * (len(args.bar) - len(args.crypto_asof))

    from quant.live.daily import run_daily_portfolio

    # 원본 장부를 지켜 둔다 — 한 봉이라도 검산에 실패하면 통째로 되돌린다.
    path = os.path.join(args.state_dir, "paper", "portfolio_ALL.json")
    with open(path, encoding="utf-8") as f:
        backup = f.read()

    results, ok = [], True
    try:
        for bar, expect, ca in zip(args.bar, args.expect, casof):
            print(f"\n─── {bar} 되살리는 중 "
                  f"(코인 기준일 {ca or bar}) ───", flush=True)
            undo = _install(bar, ca or None)
            try:
                out = run_daily_portfolio(state_dir=args.state_dir,
                                          require_real_data=True)
            except Exception as exc:            # noqa: BLE001
                # 시세를 못 받으면 배치가 스스로 멈춘다(합성 데이터로는
                # 매매하지 않는다). 그건 정상 동작이므로 역추적을 쏟아내지
                # 않고 사람이 읽을 한 줄로 보고한다.
                print(f"❌ {bar}: 다시 계산하지 못했습니다 — "
                      f"{type(exc).__name__}: {exc}")
                ok = False
                break
            finally:
                undo()
            if out.get("skipped"):
                print(f"❌ {bar}: 건너뜀 — {out}")
                ok = False
                break
            got_date, got_eq = _equity_of(args.state_dir)
            want = float(expect)
            diff = abs(float(got_eq) - want) if got_eq is not None else None
            hit = (got_date == bar and diff is not None
                   and diff <= args.tolerance)
            results.append({"bar": bar, "wrote": got_date, "equity": got_eq,
                            "expected": want, "diff": diff, "match": hit})
            print(f"   기록 날짜 {got_date} · 자산 {got_eq:,.2f} "
                  f"(로그 {want:,.2f} · 차이 {diff:,.2f})"
                  if got_eq is not None else f"   기록 실패 {out}")
            if not hit:
                print(f"❌ {bar}: 그날 로그와 다릅니다 — 되살리지 않습니다.")
                ok = False
                break
            print(f"✅ {bar}: 그날 로그와 일치합니다.")
    finally:
        if not (ok and args.write):
            with open(path, "w", encoding="utf-8") as f:
                f.write(backup)
            print("\n↩️  장부를 원래대로 되돌렸습니다"
                  + (" (시험 실행)." if ok else " (검산 실패)."))

    print("\n" + json.dumps(results, ensure_ascii=False, indent=2))
    if not ok:
        print("\n❌ 되살리기 중단 — 그날 로그와 다른 숫자는 기록하지 않습니다.\n"
              "   다르다는 사실 자체를 사장님께 보고하세요.")
        return 1
    if args.write:
        # 화면이 읽는 파일도 함께 갱신한다 — 장부만 고치고 사이트를 안
        # 고치면 "기록했다"와 "보여줬다"가 또 갈린다(감사 98).
        from quant.live.daily import write_docs_status
        write_docs_status(args.state_dir, args.docs_status)
    print("\n✅ 모든 봉이 그날 로그와 일치했습니다."
          + ("" if args.write else " (--write 를 주면 장부에 남깁니다)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
