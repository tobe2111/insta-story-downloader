"""변이 시험 — 안전장치를 일부러 망가뜨려, 계약 검사가 정말 잡는지 확인한다.

    python scripts/mutation_check.py                # 전수(무겁다 — 야간 잡)
    python scripts/mutation_check.py --dry-run      # 목록 정합성만(몇 초 — CI)
    python scripts/mutation_check.py 의회            # 부분 실행(설명·검사 이름)

⚠️ **손으로 전수를 돌릴 땐 작업 트리 말고 별도 워크트리에서 돌릴 것**(감사 183).
   이 도구는 도는 내내 `quant/` 소스를 **실제로 고쳤다가 되돌린다.** 그래서
   돌아가는 동안 `git status`가 계속 더러워 보이고, 그때 무심코 커밋하면
   **일부러 심어 둔 결함이 그대로 올라간다.** 실측: `quant/strategies/ml.py`가
   `df.index[hi] → df.index[-1]`(룩어헤드) 상태로 잡힌 적이 있다.

       git worktree add --detach /tmp/sweep-wt HEAD
       (cd /tmp/sweep-wt && python3 scripts/mutation_check.py)

   전수는 328건 기준 **약 15분**이 걸린다(항목당 2~3초). 야간 잡은 러너를
   통째로 버리므로 이 문제가 없다 — 손으로 돌릴 때만 해당한다.

⚠️ **2026-08-12 감사 125까지 이 도구는 CI에서 한 번도 돌지 않았다.**
   121개 항목을 쌓아 두고 손으로 부를 때만 돌렸다 — 다른 모든 안전장치를
   지키는 도구가 정작 아무도 안 지키는 상태였다. 이 저장소가 이미 겪은 병과
   같다(verify 명령이 있었지만 어떤 워크플로도 실행하지 않았던 것).
   지금은 두 갈래로 돈다: PR마다 `--dry-run`(ci.yml), 야간에 전수
   (.github/workflows/mutation-sweep.yml).

왜 필요한가(2026-08-11 감사 58): 계약 검사가 초록이라는 것은 '검사가
통과했다'는 뜻이지 '장치가 동작한다'는 뜻이 아니다. 이 프로젝트의 검사
상당수가 소스에 특정 문자열이 있는지만 봤고, 그런 검사는 **배선이
사라지는 것은 잡아도 배선이 무력화되는 것은 못 잡는다.** 그리고 그날
잡은 결함은 전부 후자였다 — 킬스위치가 스케일러에 지워지고, 켈리 상한이
되돌려지고, 실적 가드가 사라지는 식.

그래서 반대로 확인한다: 프로덕션 코드를 한 줄씩 일부러 망가뜨리고 해당
검사를 돌린다. 검사가 **실패해야** 그 검사가 살아 있는 것이다. 통과하면
그 검사는 장식이고, 그 안전장치는 지금 아무도 지키지 않고 있다.

1차(8건) 결과 3건이 장식이었다.
  · 켈리 상한 — clip을 지워도 통과(테스트가 소스 문자열만 봄)
  · 통합 계좌 데이터 무결성 게이트 — 꺼도 통과(행동 검사가 종목별 경로뿐)
  · CSRF 가드 — do_GET의 호출을 무력화해도 통과(함수는 옳지만 호출되는지를
    아무도 안 봄)

2차(8건 추가) 결과 3건이 더 나왔다.
  · 통합 계좌가 **합성 폴백 데이터**로도 매매 — 사이트가 "실데이터로만
    판단한다"고 말하는 그 규칙
  · **선발전이 결승 구간을 미리 보게** 만들어도 통과 — 오디션 전체에서
    가장 중요한 장치인데 아무도 안 지키고 있었다
  · 다중검정 보정 문턱(select_t)을 0으로 내려도 통과

3차(5건 추가) 결과 **5건 전부** 무방비였다.
  · 배포판 실거래 잠금 — 규제·책임 방어선인데 조건을 무력화해도 통과
  · 어드민 '총노출 배수' — 손잡이를 무시해도 통과(오늘 아침 고친 그 장치)
  · 같은 봉 재실행 멱등 가드 — 08-07 중복 기록 사고의 방어선
  · 주식의 '다음 세션 시가' 체결 규칙 — 결정 당일 종가로 즉시 체결시켜도 통과
  · 실측 비용 왕복 단위 — 편도로 되돌려 마찰을 절반으로 써도 통과

4차(5건 추가) 결과 2건이 더 나왔다.
  · 실적 가드 — 항상 비발동으로 만들어도 통과
  · 재조정 쿨다운 — 항상 통과시켜(회전율 통제 해제) 만들어도 통과

그리고 이 도구 자신이 두 가지 병에 걸려 있었다.

  ① 존재하지 않는 테스트 파일을 지정하면 pytest가 4(사용 오류)를 주는데,
     그것을 '검사가 실패했다 = 잡았다'로 세고 있었다. 실제로 없는 검사가
     ✅로 찍혔다. → 변이 전에 기준선을 먼저 돌려, 원본 코드에서 통과하는
     검사만 대상으로 삼는다(파일 없음·기준선 실패는 💥로 따로 센다).
  ② **아무것도 바꾸지 않는 변이를 '못 잡음'으로 셌다.** 확률 보정 항목에서
     record가 이미 만들어진 뒤에 지역변수 weight를 덮어썼는데, 그 줄은
     동작에 영향이 없다. 검사가 약한 게 아니라 부술 것이 없었다.
     → 변이가 실제로 동작을 바꾸는지부터 확인할 것. 못 잡았다고 보고하기
     전에 그 변이가 진짜 결함인지 먼저 따져야 한다.

누적 26건 중 13건(50%)이 장식이었다. 전부 행동 검사로 메웠고 지금은
26/26을 잡는다.

교훈: 이 프로젝트에서 '기능을 만들었다'와 '기능이 지켜진다' 사이의 간격은
절반이었다. 새 안전장치를 만들면 여기 변이 항목을 함께 추가할 것 —
추가하지 않은 장치는 다음 리팩터링에서 조용히 사라진다.

⚠️ 원본 문자열이 안 맞으면 그 항목은 건너뛴다(⏭️). 건너뜀은 통과가
   아니다 — 코드가 바뀌었다는 뜻이므로 변이 문자열을 갱신해야 한다.
   조용히 넘어가지 않도록 결과에 함께 센다.

⚠️ 이 스크립트는 실행 중 소스 파일을 잠깐 고쳤다가 되돌린다. 돌아가는
   동안 git status를 보면 변조된 상태가 잡히므로, **커밋과 동시에 돌리지
   말 것.** 중단되면 해당 파일이 변조된 채로 남을 수 있다(그때는
   `git checkout <파일>`로 되돌린다).

⚠️ 세 번째 자기 결함(감사 72): 복원 후에도 **변조된 .pyc가 재사용**됐다.
   파이썬은 .pyc 유효성을 (원본 mtime, 원본 크기)로 판단하는데, 변조와
   복원이 같은 초 안에 일어나고 바뀐 글자 수가 같으면(`gate` → `None`,
   둘 다 4글자) 복원본이 '변경 없음'으로 보인다. 그 결과 이후 테스트가
   디스크에 없는 코드로 돌아 멀쩡한 검사 두 개가 실패했다 — 도구가 남긴
   오염이 진짜 결함처럼 보였다. 이제 변조·복원 양쪽에서 해당 모듈의 .pyc를
   지우고, 하위 프로세스는 PYTHONDONTWRITEBYTECODE=1로 돌린다.
"""
import atexit
import os
import signal
import pathlib, subprocess, sys

MUTATIONS = [
    # (설명, 파일, 원본, 변조, 돌릴 테스트)
    # ── 감사 120 — 변이 사각지대 18개 파일 소거 ──
    #
    # ⚠️ 이 항목이 감사 120을 낳았다. 처음엔 test_killswitch.py를 가리켰고
    #    통과했다 — 그래서 **전체 검사**로 다시 돌렸더니 1,580개가 전부
    #    통과했다. 낙폭 자동 브레이크를 통째로 지워도 아무도 몰랐다.
    #    킬스위치 검사가 셋이나 있었지만 전부 `_kill_switch_scale`을 순수
    #    함수로 부르거나 소스 문자열을 볼 뿐, "낙폭이 커지면 노출이 준다"를
    #    확인하지 않았다. 부품 검사와 배선 검사는 다른 것이다.
    ("킬스위치 단계 축소를 무효화한다(낙폭에도 노출 유지)",
     "quant/live/daily.py",
     "    risk_scale = _kill_switch_scale(float(st.get(\"risk_scale\", 1.0)), drawdown)",
     "    risk_scale = 1.0",
     "tests/test_killswitch_is_wired_to_the_brake.py"),

    # 이 항목도 처음엔 test_license_gate.py를 가리켜 통과했다. 전체로
    # 돌리니 test_dist_guard_generation.py가 잡았다 — 장치는 지켜지고
    # 있었고 **가리킨 곳이 틀렸다.** 못 잡음으로 세면 없는 결함을 만든다.
    ("배포판 실거래 잠금 표식 판정을 끈다",
     "quant/utils/dist.py",
     "        return bool(getattr(_dist_build, \"DISTRIBUTION\", False))",
     "        return False",
     "tests/test_dist_guard_generation.py"),

    ("봉내 스톱 판정을 끈다(손절이 봉 안에서 안 걸림)",
     "quant/backtest/engine.py",
     "        if self.intrabar_stops:\n            high = df[\"high\"].to_numpy()",
     "        if False:\n            high = df[\"high\"].to_numpy()",
     "tests/test_intrabar_stops.py"),

    # ── 감사 121·122 — 킬스위치와 같은 병(순수 함수는 옳고 배선은 무방비) ──
    #
    # 둘 다 처음엔 전체 1,580개 검사가 통과했다. 게이트·상한을 부르는
    # 한 줄을 지워도 아무도 몰랐다.
    ("미검증 엣지 변동성 게이트를 무시하고 목표를 20%로 올린다",
     "quant/live/daily.py",
     "    tgt_vol, vol_proven, vol_why = target_vol_now(state_dir)",
     "    tgt_vol, vol_proven, vol_why = 0.20, True, \"게이트무시\"",
     "tests/test_risk_limits_are_wired_to_the_batch.py"),

    ("한 종목 과집중 상한(3/n)을 푼다",
     "quant/live/daily.py",
     "        cap = 3.0 / n\n"
     "        slices = {k: min(v * budget / tot, cap) for k, v in tilted.items()}",
     "        cap = 1e9\n"
     "        slices = {k: min(v * budget / tot, cap) for k, v in tilted.items()}",
     "tests/test_risk_limits_are_wired_to_the_batch.py"),

    # ── 위험 한도(돈이 실제로 움직이는 경로) ──
    #
    # (레버리지 금지선과 미입증 목표 변동성 잠금은 아래 '무레버리지 상한을
    #  3배로 푼다'·'엣지 미입증인데 목표 변동성 잠금을 푼다'가 **같은 줄**을
    #  이미 찌른다. 2026-08-12에 여기 중복으로 넣었다가 목록을 세어 보고
    #  지웠다 — 중복 금지 규칙을 만든 바로 그 회차에 내가 어겼다.)

    # (코인 미완성 봉은 아래 '코인도 진행 중인 봉으로 신호를 내게 되돌린다'가
    #  이미 같은 장치를 찌른다 — 중복 항목은 넣지 않는다. 항목 수를 부풀리면
    #  '몇 개를 지키고 있나'라는 이 도구의 유일한 숫자가 거짓이 된다.)
    ("주식 미완결·유령 일봉 제거를 끈다(멱등 가드 무력화의 원인)",
     "quant/data/stock.py",
     "                out = self._drop_unclosed(self._validate(df))",
     "                out = self._validate(df)",
     "tests/test_bar_completeness.py"),

    ("지정가 주문을 봉이 안 닿아도 체결시킨다(백테스트 낙관)",
     "quant/broker/paper.py",
     "        crossed = (bar_low <= limit_price) if side == \"buy\" \\\n"
     "            else (bar_high >= limit_price)",
     "        crossed = True",
     "tests/test_limit_order.py"),

    ("소유자 전역 스위치의 '일시정지' 판정을 끈다",
     "quant/utils/settings.py",
     "    return bool(s.get(\"trading_paused\")), min(1.0, max(0.0, scale))",
     "    return False, min(1.0, max(0.0, scale))",
     "tests/test_owner_gate_covers_all_paths.py"),

    # ── 의회(실제로 매매하는 혼합 전략)의 관문 ──
    ("결승전을 통과하지 않은 후보도 의회에 입성시킨다",
     "quant/live/retrain.py",
     "        promoted_spec=decision[\"champion\"] if decision[\"promoted\"] else None)",
     "        promoted_spec=decision[\"champion\"])",
     "tests/test_parliament.py"),

    ("의회 다양성 강제(상관 상한)를 끈다 — 같은 베팅에 두 자리",
     "quant/live/parliament.py",
     "                if c != c or c > CORR_CAP:\n                    dup = True",
     "                if False:\n                    dup = True",
     "tests/test_parliament.py"),

    ("상관을 못 재면 '무상관'으로 본다(감사 53 되돌리기 — 실패가 곧 통과)",
     "quant/live/parliament.py",
     '                    c = float("nan")',
     "                    c = 0.0",
     "tests/test_parliament_moves_slowly_and_diversely.py"),

    ("의석 비중 급변 방지(EMA)를 끈다 — 하루 만에 전액 이동",
     "quant/live/parliament.py",
     "            w = (1 - EMA_STEP) * prev + EMA_STEP * target",
     "            w = target",
     "tests/test_parliament_moves_slowly_and_diversely.py"),
    ("1석짜리 계좌도 '분산 운용 중'이라고 말한다(감사 225)",
     "quant/live/parliament.py",
     '        "diversified": multi > 0,',
     '        "diversified": True,',
     "tests/test_the_parliament_is_a_fact_not_a_promise.py"),
    ("의석 1석을 '2석 이상'으로 센다 — 잠든 구조가 켜진 것으로 보인다",
     "quant/live/parliament.py",
     "    multi = sum(1 for v in counts.values() if v >= 2)",
     "    multi = sum(1 for v in counts.values() if v >= 1)",
     "tests/test_the_parliament_is_a_fact_not_a_promise.py"),
    ("의석 현황을 사이트에 싣지 않는다 — 문장만 남고 사실이 사라진다",
     "quant/live/daily.py",
     '        if census["accounts"]:',
     "        if False:",
     "tests/test_the_parliament_is_a_fact_not_a_promise.py"),
    ("재학습에서 건너뛴 종목을 성공으로 센다(감사 226 되돌리기)",
     "quant/live/retrain.py",
     '            (skipped if out.get("skipped") else ok).append(key)',
     "            ok.append(key)",
     "tests/test_a_skip_is_not_a_success.py"),
    ("페이퍼에서 건너뛴 종목을 성공으로 센다 — 얼어붙은 날도 초록",
     "quant/live/daily.py",
     '            (skipped if records[key].get("skipped") else ok).append(key)',
     "            ok.append(key)",
     "tests/test_a_skip_is_not_a_success.py"),
    ("건너뜀 수를 장부에 0으로 적는다 — 세 칸이 다시 두 칸이 된다",
     "quant/live/daily.py",
     '             "skipped": len(skip_set),',
     '             "skipped": 0,',
     "tests/test_a_skip_is_not_a_success.py"),
    ("정체 문턱을 '이상'으로 바꾼다 — 정상 연휴에도 경보가 울린다",
     "quant/live/retrain.py",
     "        if days > threshold:",
     "        if days >= threshold:",
     "tests/test_a_skip_is_not_a_success.py"),
    ("며칠째 정체된 종목을 경보로 올리지 않는다 — 조용한 정지",
     "quant/live/flag_watch.py",
     "        if not stale:",
     "        if True:",
     "tests/test_a_skip_is_not_a_success.py"),
    ('체결비용 표본이 아카이브 사본을 또 하나의 계좌로 센다(감사 227)',
     'quant/reporting/fill_gap.py',
     '    for path in ledger_files(state_dir):',
     '    import glob\n    for path in sorted(glob.glob(os.path.join(state_dir, "paper", "*.json"))):',
     'tests/test_an_archive_is_not_a_second_account.py'),
    ("합산 확률 표본이 아카이브를 두 번 센다 — 적중률이 촘촘해 보인다",
     "quant/live/daily.py",
     '        if "portfolio" in os.path.basename(pth).lower():\n            continue',
     '        if False:\n            continue',
     "tests/test_an_archive_is_not_a_second_account.py"),
    ("장부 목록에서 보관본 필터를 뺀다 — 여섯 경로가 한꺼번에 샌다(감사 228)",
     "quant/live/ledger_basics.py",
     "            and (include_archives or not is_archive(name))]",
     "            ]",
     "tests/test_an_archive_is_not_a_second_account.py"),
    ("엣지 판정이 보관본까지 표본에 넣는다 — 사본이 '입증'을 만들어낸다",
     "quant/risk/portfolio_vol.py",
     "        for f in ledger_files(state_dir):",
     '        import glob\n        for f in glob.glob(os.path.join(state_dir, "paper", "*.json")):',
     "tests/test_an_archive_is_not_a_second_account.py"),
    ("종목표가 보유액을 장부에서 읽지 않는다 — 잔고 표와 갈라진다",
     "docs/index.html",
     "  ((pf&&pf.holdings)||[]).forEach(h=>{if(h&&h.key)held[h.key]=h;});",
     "  ;",
     "tests/test_the_symbol_table_says_how_much.py"),
    ("갱신 주기 안내를 지운다 — 실시간인지 아닌지 물어봐야 알게 된다",
     "docs/index.html",
     "        이 표의 숫자는 <b>매일 새벽 배치가 하루 한 번 확정</b>한 값입니다 —",
     "        이 표의 숫자는",
     "tests/test_the_symbol_table_says_how_much.py"),
    ("시세 요청에 장부 키를 그대로 보낸다 — 워커가 전부 거부한다(감사 229)",
     "docs/index.html",
     '    fetch("/api/quotes?symbols="+encodeURIComponent(syms.concat("KRW=X").join(",")))',
     '    fetch("/api/quotes?symbols="+encodeURIComponent(ks.concat("KRW=X").join(",")))',
     "tests/test_the_live_quotes_actually_arrive.py"),
    ("화면이 준실시간 평가를 스스로 다시 계산한다 — 잔고 표와 갈라진다",
     "docs/index.html",
     "    const m=QuantLive.markHoldings(all,live,liveFx);",
     "    const m={rows:{},missing:[],marked:0,total:0,complete:false};",
     "tests/test_the_live_quotes_actually_arrive.py"),
    ("일부 종목 시세를 못 받으면 합계를 말없이 지운다(조용한 침묵)",
     "docs/index.html",
     "    }else if(m.missing.length&&m.marked>0){",
     "    }else if(false){",
     "tests/test_the_live_quotes_actually_arrive.py"),
    ("대폭 감액을 다시 평활한다 — '팔아라'를 반만 듣는다(감사 230)",
     "quant/live/daily.py",
     "        elif abs(p) > 0 and abs(w) <= cut * abs(p):",
     "        elif False:",
     "tests/test_a_sell_signal_is_heard_in_full.py"),
    ("방향 전환도 평활한다 — 숏 신호를 받고 롱에 남는다",
     "quant/live/daily.py",
     "        elif p and (w > 0) != (p > 0):",
     "        elif False:",
     "tests/test_a_sell_signal_is_heard_in_full.py"),
    ("감액 문턱을 1.0으로 — 모든 축소가 즉시가 되어 회전율 통제가 사라진다",
     "quant/live/daily.py",
     "SMOOTH_CUT_RATIO = 0.5",
     "SMOOTH_CUT_RATIO = 1.0",
     "tests/test_a_sell_signal_is_heard_in_full.py"),
    ("조종석이 시세를 원화로 환산하지 않는다 — 계좌가 27.9%로 쪼그라든다",
     "quant/web/app.py",
     "                    px = to_krw(market, float(df[\"close\"].iloc[-1]), rate)",
     "                    px = float(df[\"close\"].iloc[-1])",
     "tests/test_the_cockpit_counts_in_won.py"),
    ("보유 종목 시세를 직접 안 받는다 — 종목 계좌에 얹혀 간다(감사 231)",
     "quant/web/app.py",
     "        for k in (a.get(\"positions\") or {}):",
     "        for k in ():",
     "tests/test_the_cockpit_counts_in_won.py"),
    ("조종석 시세 중계가 실패를 옛 값으로 채운다 — 없는 것을 지어낸다",
     "quant/web/app.py",
     '        return _json.dumps({"quotes": {}, "error": str(exc)[:120]})',
     '        return _json.dumps({"quotes": {"x": {"price": 1}}})',
     "tests/test_the_cockpit_counts_in_won.py"),
    ("화면 평가가 환율 없이 해외 종목 값을 만든다(1.0으로 때우기)",
     "docs/assets/live-marks.js",
     "    if (!fx) return null;",
     "    return qty * lv.px;",
     "tests/test_the_price_freshness_is_what_it_claims.py"),
    ("일부만 받아도 합계를 낸다 — 계좌가 실제보다 작게 보인다",
     "docs/assets/live-marks.js",
     "    var complete = n > 0 && missing.length === 0;",
     "    var complete = n > 0;",
     "tests/test_the_price_freshness_is_what_it_claims.py"),
    ("신선도를 세지 않고 '전부 실시간'이라 단정한다",
     "docs/assets/live-marks.js",
     "      if (lv.delayed) late += 1; else fresh += 1;",
     "      fresh += 1;",
     "tests/test_the_price_freshness_is_what_it_claims.py"),
    ("장 마감 시간에도 장중으로 판정한다 — 무료 한도를 밤새 태운다",
     "docs/assets/live-marks.js",
     "    if (d === 0) return false;                       // 일요일(KST) — 양쪽 휴장",
     "    return true;",
     "tests/test_the_price_freshness_is_what_it_claims.py"),
    ("넘겨받은 시각을 무시하고 벽시계를 본다 — 하루 중 세 시간만 빨간 검사",
     "quant/live/daily.py",
     'def _signal_frame(market: str, df, timeframe: str = "1d", now=None):',
     'def _signal_frame(market: str, df, timeframe: str = "1d", now=None):\n    now = None',
     "tests/test_bar_completeness.py"),
    ("예산을 끌어 쓴 사실을 화면에서 지운다 — '못 샀다'만 말하고 '누가 가져갔나'는 감춘다",
     "docs/index.html",
     "    const lp=pfLast.lot_priority||null;",
     "    const lp=null;",
     "tests/test_ledger_fields_reach_the_screen.py"),
    ("묵은 봉으로 판단한 시장을 화면에서 지운다(감사 220의 흔적이 사라진다)",
     "docs/index.html",
     "    const ba=pfLast.bar_age_days||null;",
     "    const ba=null;",
     "tests/test_ledger_fields_reach_the_screen.py"),
    ("갓 시작한 봉이 하루를 열게 둔다 — 재시도가 다음 날을 선점한다(감사 232)",
     "quant/live/daily.py",
     "    bar = judgement_day(last_bars, partial_bars)",
     "    bar = max(str(b)[:10] for b in last_bars.values())",
     "tests/test_a_new_day_needs_a_real_bar.py"),
    ("하루를 여는 문턱을 0으로 내린다 — 가드가 이름만 남는다",
     "quant/live/daily.py",
     "NEW_DAY_MIN_ELAPSED = 0.10          # = UTC 02:24 이전 봉은 하루를 열지 못한다",
     "NEW_DAY_MIN_ELAPSED = 0.0",
     "tests/test_a_new_day_needs_a_real_bar.py"),
    ("완성된 봉을 '완성도 0'으로 읽는다 — 주식만 있는 계좌가 하루도 못 연다",
     "quant/live/daily.py",
     "              if float(partial_bars.get(k, 1.0)) >= min_elapsed]",
     "              if float(partial_bars.get(k, 0.0)) >= min_elapsed]",
     "tests/test_a_new_day_needs_a_real_bar.py"),
    ("주간 리포트가 첫 기록을 자기 자신과 비교한다 — 첫날 손실이 사라진다(감사 241)",
     "quant/live/daily.py",
     "            else _week_base_principal(st, window[0][\"date\"]))",
     '            else window[0]["equity"])',
     "tests/test_the_weekly_report_counts_the_first_day.py"),
    ("주간 기준선에 입금을 더한다 — 입금이 통째로 손실로 보인다(-92%)",
     "quant/live/daily.py",
     "    return base if base > 0 else float(st[\"history\"][0][\"equity\"])",
     '    return base + sum(float(d["amount"]) for d in st.get("deposits") or [])',
     "tests/test_the_weekly_report_counts_the_first_day.py"),
    ("입금 귀속을 창만 보고 잡는다 — 옛 입금이 창 첫날로 끌려온다",
     "quant/live/daily.py",
     "    src = hist                  # 귀속은 창이 아니라 **전체 기록**(감사 241)",
     "    src = window",
     "tests/test_the_weekly_report_counts_the_first_day.py"),
    ("주간 화살표가 화면의 숫자가 아니라 원본 부호를 본다 — '🔺 -0.00%'",
     "quant/live/daily.py",
     '        shown = round(m["week_return_pct"], 2) + 0.0    # -0.0 → 0.0',
     '        shown = m["week_return_pct"]',
     "tests/test_the_weekly_report_counts_the_first_day.py"),
    ("장부 적중률을 기록하지 않는다 — 화면에 인샘플 숫자만 남는다(감사 240)",
     "quant/live/daily.py",
     '        "live_hit": _lh.get("hit_rate"),',
     '        "live_hit": None,',
     "tests/test_the_hit_rate_says_where_it_came_from.py"),
    ("관망한 날도 적중률에 넣는다 — 방향을 안 걸었는데 채점한다",
     "quant/live/ledger_basics.py",
     "        if abs(w) < 1e-9 or pa <= 0 or pb <= 0:",
     "        if pa <= 0 or pb <= 0:",
     "tests/test_the_hit_rate_says_where_it_came_from.py"),
    ("보합 봉을 오답으로 센다 — 종목 간 비교가 왜곡된다(감사 168 되돌리기)",
     "quant/live/ledger_basics.py",
     "        if pb == pa:\n            flat += 1\n            continue",
     "        pass",
     "tests/test_the_hit_rate_says_where_it_came_from.py"),
    ("표본이 없을 때 적중률 0%를 낸다 — '한 번도 못 맞혔다'로 읽힌다",
     "quant/live/ledger_basics.py",
     '    return {"hit_rate": (hits / n) if n else None, "n": n, "n_flat": flat}',
     '    return {"hit_rate": (hits / n) if n else 0.0, "n": n, "n_flat": flat}',
     "tests/test_the_hit_rate_says_where_it_came_from.py"),
    ("화면이 실전 적중률을 안 보여준다 — 인샘플만 남는다",
     "docs/index.html",
     "          '<div class=\"cd\">'+lhr+'</div></td>'+",
     "          '</td>'+",
     "tests/test_the_hit_rate_says_where_it_came_from.py"),
    ("최대낙폭이 원금을 고점으로 안 친다 — 킬스위치가 한 단계 덜 걸린다(감사 239)",
     "quant/live/ledger_basics.py",
     "    peak, mdd = INDEX_ORIGIN, 0.0",
     "    peak, mdd = 0.0, 0.0",
     "tests/test_the_drawdown_counts_from_the_principal.py"),
    ("현재 낙폭이 원금을 고점으로 안 친다 — 두 함수가 다른 말을 한다",
     "quant/live/ledger_basics.py",
     "    peak = max(max(index), INDEX_ORIGIN)",
     "    peak = max(index)",
     "tests/test_the_drawdown_counts_from_the_principal.py"),
    ("원점을 1.0이 아닌 값으로 옮긴다 — 기준선이 조용히 어긋난다",
     "quant/live/ledger_basics.py",
     "INDEX_ORIGIN = 1.0",
     "INDEX_ORIGIN = 0.9",
     "tests/test_the_drawdown_counts_from_the_principal.py"),
    ("성장 지수에 원점을 끼워 넣는다 — 낙폭 차트가 하루씩 밀린다",
     "quant/live/ledger_basics.py",
     "    out: list[float] = []\n    idx, prev = 1.0, float(start_cash)",
     "    idx, prev = 1.0, float(start_cash)\n    out: list[float] = [idx]",
     "tests/test_the_drawdown_counts_from_the_principal.py"),
    ("캡션이 목표 노출을 '실제 투자'라고 말한다 — 27%를 46%로 방송한다(감사 238)",
     "quant/reporting/social.py",
     '        money = f"투자 중 {inv * 100:.0f}% · 현금 {(1 - inv) * 100:.0f}%"',
     '        money = f"총노출 {gross}"',
     "tests/test_the_caption_says_what_is_actually_invested.py"),
    ("잔고를 모르는 옛 기록에서 목표를 '투자 중'이라고 말한다",
     "quant/reporting/social.py",
     '        money = f"목표 노출 {gross}"',
     '        money = f"투자 중 {gross}"',
     "tests/test_the_caption_says_what_is_actually_invested.py"),
    ("스레드 캡션만 옛 표현으로 되돌린다 — 짧은 판이 뒤처진다",
     "quant/reporting/social.py",
     '    short_money = (f"투자 {inv * 100:.0f}%(목표 {gross})" if inv is not None',
     '    short_money = (f"노출 {gross}" if inv is not None',
     "tests/test_the_caption_says_what_is_actually_invested.py"),
    ("아직 안 산 종목에 '(대기)' 표시를 지운다 — 산 것처럼 방송된다",
     "quant/reporting/social.py",
     '                 + ("(대기)" if k in _pending else "")',
     '                 + ""',
     "tests/test_the_caption_says_what_is_actually_invested.py"),
    ("보유 종목 수를 목표 종목 수로 센다 — 한 주도 없는데 '7종목 보유'",
     "quant/reporting/social.py",
     '        "n_held": (len(port["holdings"]) if port.get("holdings")',
     '        "n_held": (len(keep) if False',
     "tests/test_the_caption_says_what_is_actually_invested.py"),
    ("실제 투자 비율을 잔고가 아니라 목표에서 읽는다 — 두 화면이 갈라진다",
     "quant/reporting/social.py",
     "    holdings = port.get(\"holdings\")",
     "    holdings = None",
     "tests/test_the_caption_says_what_is_actually_invested.py"),
    ("모르는 종목에 트레이딩뷰 심볼을 지어낸다 — 엉뚱한 회사 차트가 뜬다",
     "docs/assets/tv-symbols.js",
     "    return null;      // upbit·synthetic 등 — 모르면 안 만든다",
     '    return "NASDAQ:" + symbol;',
     "tests/tv_symbols_check.mjs"),
    ("국내 종목 코드에서 접미사만 떼고 검사를 안 한다 — 형식이 다르면 깨진다",
     "docs/assets/tv-symbols.js",
     '      var m = /^(\\d{6})\\.(KS|KQ)$/.exec(symbol);\n      return m ? "KRX:" + m[1] : null;',
     '      return "KRX:" + symbol.split(".")[0];',
     "tests/tv_symbols_check.mjs"),
    ("미국주식 거래소를 생략한다 — 같은 티커가 여러 곳에 있으면 엉뚱한 게 걸린다",
     "docs/assets/tv-symbols.js",
     "      return ex ? ex + \":\" + symbol : null;",
     "      return symbol;",
     "tests/tv_symbols_check.mjs"),
    ("차트 창에서 종목을 갈아탈 수 있게 둔다 — '이 종목'을 보는 창이 아니게 된다",
     "docs/assets/tv-symbols.js",
     '      "allow_symbol_change=0",   // 다른 종목으로 갈아타지 못하게 — 이 창은',
     '      "allow_symbol_change=1",   //',
     "tests/tv_symbols_check.mjs"),
    ("임베드 주소에 인자를 그대로 박는다 — 주입 경로가 열린다",
     "docs/assets/tv-symbols.js",
     '      "interval=" + encodeURIComponent(o.interval || "D"),',
     '      "interval=" + (o.interval || "D"),',
     "tests/tv_symbols_check.mjs"),
    ("차트가 남의 데이터라는 사실을 화면에서 지운다 — 장부와 같은 출처로 읽힌다",
     "docs/index.html",
     "'<b>매매·수익률은 위 장부에서만 나옵니다.</b></div>'+",
     "'</div>'+",
     "tests/test_the_symbol_dialog_keeps_the_sources_apart.py"),
    ("상세 창을 닫아도 차트를 안 치운다 — 배경에서 계속 돈다",
     "docs/index.html",
     '    document.getElementById("dlg-chart").innerHTML="";',
     "    void 0;",
     "tests/test_the_symbol_dialog_keeps_the_sources_apart.py"),
    ("브리핑이 죽은 피드를 장부에 안 남긴다 — 반쪽만 보여주고 조용하다(감사 237)",
     "quant/live/briefing.py",
     '                "items": items, "note": NOTE, "sources": health}',
     '                "items": items, "note": NOTE}',
     "tests/test_the_briefing_says_which_sources_died.py"),
    ("종목 뉴스가 통째로 사라져도 흔적을 안 남긴다",
     "quant/live/briefing.py",
     '            health["symbols_failed"][sym_key] = f"{type(exc).__name__}: {exc}"[:120]',
     "            pass",
     "tests/test_the_briefing_says_which_sources_died.py"),
    ("살아 있는 소스를 세지 않는다 — '몇 개 중 몇 개'가 사라진다",
     "quant/live/briefing.py",
     '        health["feeds_ok"].append(category)',
     "        pass",
     "tests/test_the_briefing_says_which_sources_died.py"),
    ("멀쩡한 날에도 실패 경고를 띄운다 — 경고가 무뎌진다",
     "quant/live/briefing.py",
     '    if health["feeds_failed"]:',
     "    if True:",
     "tests/test_the_briefing_says_which_sources_died.py"),
    ("호가 단위 하한을 없앤다 — 낼 수 없는 비용으로 백테스트를 돌린다",
     "quant/backtest/costs.py",
     "        slip = max(self.slippage, self.slippage_floor(price))",
     "        slip = self.slippage",
     "tests/test_the_spread_cannot_be_cheaper_than_a_tick.py"),
    ("하한을 가정 대신 써 버린다 — 하한이 더 싼 종목의 비용이 내려간다",
     "quant/backtest/costs.py",
     "        if not self.market or price is None:\n            return 0.0",
     "        if not self.market or price is None:\n            return 1.0",
     "tests/test_the_spread_cannot_be_cheaper_than_a_tick.py"),
    ("스프레드 전체를 편도에 물린다 — 왕복 비용이 두 배가 된다",
     "quant/backtest/tick.py",
     "    return (t / 2.0) / float(price)",
     "    return t / float(price)",
     "tests/test_the_spread_cannot_be_cheaper_than_a_tick.py"),
    ("ETF에 주식 호가 단위를 물린다 — KODEX 200에 20배를 씌운다",
     "quant/backtest/tick.py",
     "    if etf:\n        return KRX_ETF_TICK",
     "    pass",
     "tests/test_the_spread_cannot_be_cheaper_than_a_tick.py"),
    ("모르는 시장에도 하한을 지어낸다 — '확실히 이보다 싸지 않다'가 깨진다",
     "quant/backtest/tick.py",
     '    if m == "us_stock":\n        return US_TICK\n    return None',
     '    return US_TICK',
     "tests/test_the_spread_cannot_be_cheaper_than_a_tick.py"),
    ("엔진이 체결 가격을 비용 계산에 안 넘긴다 — 하한이 영영 안 걸린다",
     "quant/backtest/engine.py",
     "                cost = cm.turnover_cost(turnover, vol[i], price=price)",
     "                cost = cm.turnover_cost(turnover, vol[i])",
     "tests/test_the_spread_cannot_be_cheaper_than_a_tick.py"),
    ("실측 비용으로 갈아탈 때 시장·ETF 표시를 흘린다 — 하한이 조용히 사라진다",
     "quant/live/daily.py",
     "                     market=base.market, is_etf=base.is_etf)",
     "                     )",
     "tests/test_the_spread_cannot_be_cheaper_than_a_tick.py"),
    ("종목의 ETF 표시를 안 읽는다 — 전부 주식 호가 단위가 된다",
     "quant/live/daily.py",
     '    return bool((SYMBOL_INFO.get(f"{market}:{symbol}") or {}).get("etf"))',
     "    return False",
     "tests/test_the_spread_cannot_be_cheaper_than_a_tick.py"),
    ("휴장일을 무시하고 장을 연다 — 명절 내내 무료 시세 한도를 태운다",
     "quant/live/market_hours.py",
     "    if is_holiday(key, local.date(), holidays):\n        return False",
     "    pass",
     "tests/test_the_calendar_knows_the_holidays.py"),
    ("달력이 없는 날 '공휴일 아님'이라고 단정한다 — 휴장을 장애로 오해하게 만든다",
     "quant/live/market_hours.py",
     '    tail = ("" if holidays and holidays.get(key)',
     '    tail = ("" if True',
     "tests/test_the_calendar_knows_the_holidays.py"),
    ("휴장일을 주말까지 포함해 만든다 — 요일 판정과 두 곳에서 갈라진다",
     "quant/data/market_calendar.py",
     "        if day.weekday() < 5:                      # 주말은 이미 아는 사실",
     "        if True:",
     "tests/test_the_calendar_knows_the_holidays.py"),
    ("달력을 못 만들면 옛 캐시도 버린다 — 있는 정보를 없앤다",
     "quant/data/market_calendar.py",
     '        return cache.get("markets") or {}',
     "        return {}",
     "tests/test_the_calendar_knows_the_holidays.py"),
    ("낡은 달력을 그대로 쓴다 — 작년 공휴일로 올해를 판단한다",
     "quant/data/market_calendar.py",
     "    if fresh and isinstance(cache.get(\"markets\"), dict):",
     "    if isinstance(cache.get(\"markets\"), dict):",
     "tests/test_the_calendar_knows_the_holidays.py"),
    # 감사 243 — 정체 경보가 재학습 쪽에만 배선돼 있던 자리.
    # 실측: 2026-08-14 배치 run_health.paper = 성공 0 · 건너뜀 20, 경보 0건.
    ("페이퍼 배치가 정체를 안 넘긴다 — 얼어붙은 시세가 영영 안 울린다",
     "quant/live/daily.py",
     "                      stale=paper_stale_targets(skipped, _sd),",
     "                      stale=None,",
     "tests/test_the_frozen_feed_does_not_look_like_a_weekend.py"),
    ("정체를 거래일이 아니라 달력 일수로 센다 — 주말이 장애로 보고된다",
     "quant/data/market_calendar.py",
     "        if market not in EXCHANGES:                 # 24/7 시장 — 매일이 세션",
     "        if True:",
     "tests/test_the_frozen_feed_does_not_look_like_a_weekend.py"),
    ("정체를 셀 때 공휴일을 거래일로 센다 — 연휴가 시세 장애로 보고된다",
     "quant/live/daily.py",
     "        holidays = holiday_map(state_dir)",
     "        holidays = {}",
     "tests/test_the_frozen_feed_does_not_look_like_a_weekend.py"),
    ("달력이 지나간 날을 안 담는다 — 방금 지난 연휴가 '빠뜨린 세션'이 된다",
     "quant/data/market_calendar.py",
     "    start = today - _dt.timedelta(days=lookback_days)",
     "    start = today",
     "tests/test_the_calendar_knows_the_holidays.py"),
    ("화면이 정체 단위를 지어낸다 — 거래일과 달력 일수를 한 말로 섞는다",
     "quant/live/flag_watch.py",
     '        unit = str(r.get("stale_unit") or "일")',
     '        unit = "일"',
     "tests/test_the_frozen_feed_does_not_look_like_a_weekend.py"),

    # 감사 245 — 배치 건강이 브라우저까지 실려 왔는데 화면이 안 읽던 자리.
    ("화면이 배치 부분 실패를 안 말한다 — 절반 마비가 평범한 하루로 보인다",
     "docs/index.html",
     "      if(nf>0)flags.push(\"<b>\"+esc(lab)+\" 부분 실패 \"+nf+\"종목</b> — \"+",
     "      if(false)flags.push(\"<b>\"+esc(lab)+\" 부분 실패 \"+nf+\"종목</b> — \"+",
     "tests/run_health_flags_check.mjs"),
    ("화면이 배치 정체를 안 말한다 — 얼어붙은 시세가 화면에서 조용하다",
     "docs/index.html",
     "      const stl=r.stale||null, sk=stl?Object.keys(stl):[];",
     "      const stl=null, sk=[];",
     "tests/run_health_flags_check.mjs"),
    ("화면이 정체 단위를 지어낸다 — 거래일 5를 '5일'로 읽는다",
     "docs/index.html",
     '        const u=esc(r.stale_unit||"일");',
     '        const u="일";',
     "tests/run_health_flags_check.mjs"),
    ("장부 렌더가 예외를 통째로 삼킨다 — 반쪽만 그려진 화면이 정상으로 보인다",
     "docs/index.html",
     "}).catch(err=>{",
     "}).catch(()=>{});\nif(false){((err)=>{",
     "tests/test_the_front_page_says_when_it_breaks.py"),
    ("렌더가 죽어도 화면은 아무 말 안 한다 — 빈칸이 '그런 일 없었다'로 읽힌다",
     "docs/index.html",
     "  el.innerHTML='<div class=\"t\">⚠️ 화면을 다 그리지 못했습니다</div>'+",
     "  el.innerHTML=el.innerHTML||'<div class=\"t\">🚩 지금 켜진 경고</div>'+",
     "tests/test_the_front_page_says_when_it_breaks.py"),

    ("주말에도 배치 경고를 띄운다 — 매일 울리는 경보는 꺼진 경보다",
     "docs/index.html",
     "      const nf=Number(r.failed)||0;",
     "      const nf=Number(r.skipped)||0;",
     "tests/run_health_flags_check.mjs"),

    ("사이트에 휴장일 달력을 안 실어 보낸다 — 화면은 영영 주말만 안다",
     "quant/live/daily.py",
     '            status["holidays"] = {m: [d for d in days if _from <= d <= _to]',
     '            _drop = {m: [d for d in days if _from <= d <= _to]',
     "tests/test_the_calendar_knows_the_holidays.py"),
    ("화면이 미국장 휴일을 KST 날짜로 본다 — 새벽 세션이 엉뚱한 날을 본다",
     "docs/assets/live-marks.js",
     "      var sess = new Date(kst.getTime() - (h < 5.2 ? 86400000 : 0));",
     "      var sess = kst;",
     "tests/live_marks_check.mjs"),
    ("화면 장중 판정이 달력을 무시한다",
     "docs/assets/live-marks.js",
     '      return !isHoliday(holidays, "kr_stock", kst);',
     "      return true;",
     "tests/live_marks_check.mjs"),
    ("달력이 없는데 '휴장'이라고 단정한다 — 모르면 막지 않아야 한다",
     "docs/assets/live-marks.js",
     "    if (!holidays) return false;",
     "    if (!holidays) return true;",
     "tests/live_marks_check.mjs"),
    ("민감도 스윕에서 합성 데이터 경고를 뗀다 — 가짜 데이터로 파라미터를 고른다(감사 236)",
     "quant/web/app.py",
     '        "<h1", _NAV + "\\n" + _fallback_banner(df) + used_note + "<h1", 1)',
     '        "<h1", _NAV + "\\n" + used_note + "<h1", 1)',
     "tests/test_the_cockpit_says_what_it_actually_did.py"),
    ("실제로 쓴 조건을 화면에서 지운다 — 요청과 다른 값으로 계산해 놓고 말하지 않는다",
     "quant/web/app.py",
     "    parts, changed = [], []",
     "    return ''\n    parts, changed = [], []",
     "tests/test_the_cockpit_says_what_it_actually_did.py"),
    ("조정 사실만 뺀다 — 숫자는 적되 '바꿨다'는 말을 안 한다",
     "quant/web/app.py",
     "        if int(used) != int(want):",
     "        if False:",
     "tests/test_the_cockpit_says_what_it_actually_did.py"),
    ("요청값을 실제값으로 덮어쓴다 — 항상 '그대로 썼다'가 된다",
     "quant/web/app.py",
     "    return val, want",
     "    return val, val",
     "tests/test_the_cockpit_says_what_it_actually_did.py"),
    ("입력 하한을 없앤다 — 50봉짜리 워크포워드가 그대로 돈다",
     "quant/web/app.py",
     "    val = max(lo, want if hi is None else min(hi, want))",
     "    val = want",
     "tests/test_the_cockpit_says_what_it_actually_did.py"),
    ("조건 줄 라벨을 이스케이프하지 않는다",
     "quant/web/app.py",
     '        parts.append(f"{html.escape(str(label))} <b>{used:,}</b>")',
     '        parts.append(f"{label} <b>{used:,}</b>")',
     "tests/test_the_cockpit_says_what_it_actually_did.py"),
    ("오디션 결과를 장부에 안 싣는다 — 왜 안 바뀌었는지 영영 모른다(감사 235)",
     "quant/live/retrain.py",
     '        "audition_result": audition_evidence(decision),',
     '        "audition_result": None,',
     "tests/test_the_audition_records_what_it_measured.py"),
    ("1등 후보의 t를 안 남긴다 — '문턱이 높다'와 '후보가 무의미하다'를 못 가른다",
     "quant/live/retrain.py",
     "    ranked = sorted((c for c in cands if _t(c) is not None),",
     "    ranked = []\n    _unused = sorted((c for c in cands if _t(c) is not None),",
     "tests/test_the_audition_records_what_it_measured.py"),
    ("결승전 기록을 빠뜨린다 — 무엇이 모자랐는지가 사라진다",
     "quant/live/retrain.py",
     '    fin = decision.get("final")',
     "    fin = None",
     "tests/test_the_audition_records_what_it_measured.py"),
    ("t 내림차순을 오름차순으로 — 꼴찌가 '1등'으로 기록된다",
     "quant/live/retrain.py",
     "                    key=lambda c: _t(c), reverse=True)",
     "                    key=lambda c: _t(c))",
     "tests/test_the_audition_records_what_it_measured.py"),
    ("장부의 폴드 수를 숫자로 박는다 — verify 재현이 조용히 어긋난다",
     "quant/live/retrain.py",
     '        "select_folds": SELECT_FOLDS,  # 폴드 일관성 게이트 — verify 재현용',
     '        "select_folds": 3,',
     "tests/test_the_audition_records_what_it_measured.py"),
    ("실제 호출에 폴드 수를 안 넘긴다 — 기본값이 바뀌는 날 장부만 옛 값을 말한다",
     "quant/live/retrain.py",
     "                               select_folds=SELECT_FOLDS)",
     "                               )",
     "tests/test_the_audition_records_what_it_measured.py"),
    ("백테스트 자본이 NaN이 돼도 성적을 낸다 — 망가진 후보가 챔피언이 된다(감사 234)",
     "quant/backtest/engine.py",
     "            if not math.isfinite(cash_equity):",
     "            if False:",
     "tests/test_a_broken_backtest_is_not_a_score.py"),
    ("고장 난 자본을 0으로 눌러 '파산'으로 둔갑시킨다",
     "quant/backtest/engine.py",
     "                raise ValueError(\n                    f\"백테스트 자본이 계산 불가 값이 됐습니다({cash_equity}) — \"",
     "                cash_equity = 0.0\n                ruined = True\n                _unused = (\n                    f\"({cash_equity}) — \"",
     "tests/test_a_broken_backtest_is_not_a_score.py"),
    ("파산한 계좌를 계속 굴린다 — 0 × inf 로 자본이 NaN이 된다",
     "quant/backtest/engine.py",
     "            if ruined:\n                equity[i] = 0.0\n                held[i] = 0.0\n                continue",
     "            if False:\n                pass",
     "tests/test_a_broken_backtest_is_not_a_score.py"),
    ("지표가 자본곡선 한가운데 구멍을 조용히 지운다 — 그럴듯한 성적이 나온다",
     "quant/backtest/metrics.py",
     "        if not np.isfinite(_tail).all():",
     "        if False:",
     "tests/test_a_broken_backtest_is_not_a_score.py"),
    ("지표가 앞머리 결측까지 고장으로 본다 — 정상 곡선이 성적을 못 낸다",
     "quant/backtest/metrics.py",
     "    _first = equity.first_valid_index()",
     "    _first = equity.index[0] if len(equity) else None",
     "tests/test_a_broken_backtest_is_not_a_score.py"),
    ("브로커가 NaN 수량을 그대로 체결한다 — 계좌가 통째로 NaN이 된다(감사 233)",
     "quant/broker/paper.py",
     '        quantity = _positive(quantity, "주문 수량")   # 감사 233',
     "        quantity = float(quantity)",
     "tests/test_the_broker_cannot_conjure_money.py"),
    ("브로커가 음수·inf 가격을 그대로 받는다 — 매수가 현금을 늘린다",
     "quant/broker/paper.py",
     '        price = _positive(price, "체결 가격")',
     "        price = float(price)",
     "tests/test_the_broker_cannot_conjure_money.py"),
    ("현금 한도를 없앤다 — 100만원 계좌가 500만원어치를 산다",
     "quant/broker/paper.py",
     "        if side == \"buy\" and not self.allow_margin \\\n                and cost + fee > self._cash + _DUST:",
     "        if False:",
     "tests/test_the_broker_cannot_conjure_money.py"),
    ("한도에서 수수료를 뺀다 — 현금이 -1원이 되는 신용거래를 허용한다",
     "quant/broker/paper.py",
     "                and cost + fee > self._cash + _DUST:",
     "                and cost > self._cash + _DUST:",
     "tests/test_the_broker_cannot_conjure_money.py"),
    ("매도까지 현금 한도로 막는다 — 빠져나오는 길이 덫이 된다",
     "quant/broker/paper.py",
     '        if side == "buy" and not self.allow_margin \\',
     '        if not self.allow_margin \\',
     "tests/test_the_broker_cannot_conjure_money.py"),
    ("지정가 경로가 거부를 '전량 체결'로 덮어쓴다",
     "quant/broker/paper.py",
     '        if order.status == "rejected":\n            return order',
     "        pass",
     "tests/test_the_broker_cannot_conjure_money.py"),
    ("장부가 주문 로그를 상태 확인 없이 베낀다 — 미체결이 '오늘 산 것'이 된다",
     "quant/live/daily.py",
     '        if getattr(o, "status", "filled") not in ("filled", "partial"):\n            continue',
     "        pass",
     "tests/test_the_broker_cannot_conjure_money.py"),
    ("예비 배치를 다시 자정 가까이 붙인다(감사 232 되돌리기)",
     ".github/workflows/daily-paper.yml",
     '    - cron: "30 22 * * *"',
     '    - cron: "15 23 * * *"',
     "tests/test_the_batch_runs_after_the_markets_it_trades.py"),

    # ── 오디션·학습의 미래 차단(가장 비싸고 조용한 계열) ──
    ("크로스에셋 정렬을 최근접으로 바꾼다(미래 벤치마크가 과거 봉에 붙는다)",
     "quant/data/crossasset.py",
     "    return pd.Series(feature.reindex(target, method=\"ffill\").to_numpy(),",
     "    return pd.Series(feature.reindex(target, method=\"nearest\").to_numpy(),",
     # ⚠️ 처음엔 test_alpha5_crossasset.py를 가리켰고 통과했다. 그 파일의
     #    정렬 검사는 '벤치가 df보다 일찍 끝나는' 경우만 본다 — 최근접이든
     #    전진충전이든 끝 이후에는 같은 값이라 차이가 안 난다. **가운데
     #    구멍**을 보는 test_lookahead_external.py가 잡는다.
     "tests/test_lookahead_external.py"),

    ("풀링 학습의 상한을 없앤다(미래 종목의 행까지 학습에 섞는다)",
     "quant/strategies/ml.py",
     "        sel = dates < cut",
     "        sel = dates == dates",
     "tests/test_alpha12_pooled.py"),

    # 감사 128 — 실제로 이 모습이었다. 정수 epoch 비교라 단위가 어긋나도
    # 조용히 통과했고, 미래 행이 모든 학습 블록에 들어갔다.
    ("풀 날짜를 정수 epoch로 되돌린다(단위 어긋남 → 미래 행이 전부 통과)",
     "quant/strategies/ml.py",
     "                idx = pd.DatetimeIndex(pdf.index).normalize().to_numpy(\n"
     "                    dtype=\"datetime64[ns]\")",
     "                idx = pd.DatetimeIndex(pdf.index).normalize().asi8",
     "tests/test_alpha12_pooled.py"),

    # 감사 129 — 풀링을 살리자 드러난 세 번째 결함. 스냅샷 폴더를 프레임
    # **끝** 날짜로 한 번만 고르면, 같은 과거 봉이라도 뒤에 미래가 얼마나
    # 붙어 있느냐에 따라 풀이 달라진다 — 인과성이 깨진다(링 검사 54봉).
    ("스냅샷 풀을 프레임 끝 날짜로 한 번만 고른다(미래를 자르면 과거가 바뀐다)",
     "quant/strategies/ml.py",
     "                        rows = self._pool_at(feats.columns, df.index[hi])",
     "                        rows = self._pool_at(feats.columns, df.index[-1])",
     "tests/test_lookahead_challenger_ring.py"),

    # 감사 127 — 풀링이 통째로 죽어 있어도 아무도 몰랐다.
    # ⚠️ 이 항목의 원본 문자열은 감사 129에서 호출부를 리팩터링하며 한 번
    #    어긋났고, **CI의 `--dry-run`이 즉시 잡았다**(감사 125가 만들어진
    #    바로 그 이유). 항목을 옮기지 말고 갱신할 것.
    ("풀링을 조용히 끈다(넣으나 마나 같아진다)",
     "quant/strategies/ml.py",
     "                    rows = pool_rows",
     "                    rows = None",
     "tests/test_alpha12_pooled.py"),

    ("스냅샷 풀이 당일 폴더까지 읽는다(채우는 중이라 verify 재현이 깨진다)",
     "quant/utils/repro.py",
     "    days = sorted(d for d in os.listdir(base) if d < cutoff[:10])",
     "    days = sorted(d for d in os.listdir(base) if d <= cutoff[:10])",
     "tests/test_alpha12_pooled.py"),

    ("메타라벨과 풀링의 동시 사용 금지를 푼다",
     "quant/strategies/ml.py",
     "        if pool is not None and meta:",
     "        if False:",
     "tests/test_alpha12_pooled.py"),

    ("스톱 발동 후 재진입 금지를 끈다(스톱이 무의미해진다)",
     "quant/strategies/stop_guard.py",
     "            if stopped:\n                w[t] = 0.0",
     "            if False:\n                w[t] = 0.0",
     "tests/test_alpha11_kelly_stop.py"),

    # ── 검증 리포트·요약·상수(변이가 한 번도 닿지 않던 파일들) ──
    ("돌지 못한 검증을 '신뢰할 만함'으로 넘긴다",
     "quant/reporting/validation_report.py",
     "    elif \"unknown\" in vset:",
     "    elif False:",
     "tests/test_validation_report.py"),

    ("실패한 단계를 '측정 실패' 대신 숫자로 채운다(안 잰 값을 잰 것처럼)",
     "quant/reporting/validation_report.py",
     "        if key in failed:",
     "        if False:",
     "tests/test_validation_report.py"),

    ("날짜 롤오버 가드를 없앤다(일일 요약이 사이클마다 중복 전송)",
     "quant/live/summary.py",
     "    if last_date is None or last_date == t:\n        return t, None",
     "    if False:\n        return t, None",
     "tests/test_live_summary.py"),

    ("정규장이 있는 시장의 실거래 브로커 매핑을 지운다",
     "quant/markets.py",
     "    \"kr_stock\": \"kr_live\",",
     "    \"kr_stock\": None,",
     "tests/test_markets_constants.py"),

    ("보유 포지션을 장부에 저장하지 않는다(다음 실행이 빈 계좌로 시작)",
     "quant/live/daily.py",
     "    st[\"positions\"] = {\n"
     "        p.symbol: {\"quantity\": p.quantity, \"avg_price\": p.avg_price,",
     "    st[\"positions\"] = {}",
     "tests/test_daily_paper.py"),

    ("VIX를 100으로 나누지 않고 그대로 피처에 넣는다(스케일 100배)",
     "quant/data/crossasset.py",
     "                out[\"x_vix\"] = _align(vix / 100.0, out.index)\n"
     "                v3m = _bench_close(\"us_stock\", \"^VIX3M\", fetch=fetch)",
     "                out[\"x_vix\"] = _align(vix, out.index)\n"
     "                v3m = _bench_close(\"us_stock\", \"^VIX3M\", fetch=fetch)",
     "tests/test_alpha6_vix_kimchi_calguard.py"),

    # 감사 139 — 거래소 규격 검사가 통째로 꺼져 있었다(아무도 안 물었다).
    ("주문 직전에 거래소 규격을 묻지 않는다(최소금액 미만도 그대로 전송)",
     "quant/broker/retry.py",
     "        spec = self._spec_for(symbol)",
     "        spec = self.spec",
     "tests/test_exchange_specs_actually_bind.py"),

    ("코인 어댑터가 규격을 안 알려 준다",
     "quant/broker/crypto_live.py",
     "            return from_ccxt_market(\n"
     '                m, getattr(self.client, "precisionMode", None)) if m else None',
     "            return None",
     "tests/test_exchange_specs_actually_bind.py"),

    # 감사 138 — 접수 건수와 실제로 산 건수를 한 숫자로 합쳐 말했다.
    ("0주로 잘린 주문도 '주문 N건'에 넣는다(안 샀는데 샀다고 보고)",
     "quant/live/daily_live.py",
     "    placed = len(orders) - len(zero_qty)",
     "    placed = len(orders)",
     "tests/test_live_reports_what_it_actually_bought.py"),

    ("0주가 된 이유(목표 금액 vs 1주 값)를 안 남긴다",
     "quant/live/daily_live.py",
     "                if order.status == \"skipped\":",
     "                if False:",
     "tests/test_live_reports_what_it_actually_bought.py"),

    # 감사 137 — 실계좌에서 1주도 못 사는 보유를 장부가 인정하는가.
    ("미룬 종목을 장부에서 숨긴다(못 사는 종목을 조용히 넘김)",
     "quant/live/daily.py",
     "              \"lot_infeasible\": deferred_lots or None,",
     "              \"lot_infeasible\": None,",
     "tests/test_the_ledger_admits_what_cannot_be_bought.py"),

    # 2026-08-13 예산 유연화로 이 줄이 want(원하는 주수) 계산으로 바뀌었다.
    # 지키는 계약은 그대로 — 소수점 주를 산 것으로 기록하면 안 된다.
    ("정수 주 내림을 끈다(못 사는 수량을 산 것으로 기록)",
     "quant/live/daily.py",
     "        want = math.floor(abs(w) * equity / px)",
     "        want = abs(w) * equity / px",
     "tests/test_the_ledger_admits_what_cannot_be_bought.py"),

    ("미룬 예산을 재배분하지 않는다(총노출이 목표보다 낮아짐)",
     "quant/live/daily.py",
     "    if freed > 1e-12:",
     "    if False:",
     "tests/test_the_ledger_admits_what_cannot_be_bought.py"),

    ("주문과 장부가 다시 각자 계산하게 되돌린다",
     "quant/live/daily.py",
     "        tw = fitted_w[key]             # 예산까지 반영한 최종 목표 비중",
     "        tw = _target_w(key, w)",
     "tests/test_the_ledger_admits_what_cannot_be_bought.py"),

    ("국내주식도 소수점 매매가 되는 것으로 친다",
     "quant/live/daily.py",
     "FRACTIONAL_MARKETS = {\"crypto\", \"synthetic\", \"us_stock\"}",
     "FRACTIONAL_MARKETS = {\"crypto\", \"synthetic\", \"us_stock\", \"kr_stock\"}",
     "tests/test_the_ledger_admits_what_cannot_be_bought.py"),

    # 감사 136 — 장부 키를 바꾸고 소비처를 안 찾아 경보가 죽어 있었다.
    ("회전율 경보가 없는 키를 0으로 읽게 되돌린다(경보가 영원히 안 울린다)",
     "quant/live/flag_watch.py",
     "        vals = [r[\"turnover\"].get(\"traded\") for r in recent]",
     "        vals = [r[\"turnover\"].get(\"ratio\") or 0.0 for r in recent]",
     "tests/test_flag_watch.py"),

    # 감사 135 — 제공자는 소스를 적고 있었는데 읽는 곳이 한 곳도 없었다.
    ("시세 소스를 장부에서 뺀다(무조정가 폴백을 아무도 모르게)",
     "quant/live/daily.py",
     "              \"data_source\": sources or None,",
     "              \"data_source\": None,",
     "tests/test_data_source_is_recorded.py"),

    ("보조 소스를 1차와 구분하지 않는다(무조정가가 조정가인 척)",
     "quant/live/daily.py",
     "        if want and name != want:",
     "        if False:",
     "tests/test_data_source_is_recorded.py"),

    # ── 모든 판정의 분모(성과 지표)와 안전장치 본체 ──
    #
    # 이 세 파일은 변이가 한 번도 닿지 않았다(감사 140). 샤프·MDD가 틀리면
    # 오디션 승격·엣지 입증 게이트·사이트의 모든 숫자가 **동시에** 틀린다.
    ("샤프지수 연율화를 뺀다(전 판정의 분모가 √252배 작아진다)",
     "quant/backtest/metrics.py",
     "        else excess.mean() / _sd * np.sqrt(periods_per_year)",
     "        else excess.mean() / _sd",
     "tests/test_performance_metrics_are_exact.py"),

    ("최대낙폭을 고점 대비가 아니라 시작 대비로 잰다",
     "quant/backtest/metrics.py",
     "    cummax = equity.cummax()\n    drawdown = equity / cummax - 1.0",
     "    cummax = equity.cummax()\n    drawdown = equity / equity.iloc[0] - 1.0",
     "tests/test_backtest.py"),

    ("CAGR 복리 구간 수를 한 칸 늘린다(수익률 부풀림)",
     "quant/backtest/metrics.py",
     "    intervals = max(1, len(equity) - 1)",
     "    intervals = max(1, len(equity))",
     "tests/test_performance_metrics_are_exact.py"),

    ("일일 손실 킬스위치 문턱 판정을 끈다",
     "quant/live/killswitch.py",
     "            if daily <= -self.daily_max_loss:",
     "            if False:",
     "tests/test_killswitch.py"),

    ("킬스위치 할트를 즉시 풀어 준다(중단 기간이 사라진다)",
     "quant/live/killswitch.py",
     "            if today < self.halted_until:\n                return True",
     "            if False:\n                return True",
     "tests/test_killswitch.py"),

    ("서킷브레이커 최대낙폭 트립을 끈다",
     "quant/live/circuit_breaker.py",
     "            if dd <= -cfg.max_drawdown:",
     "            if False:",
     "tests/test_circuit_breaker.py"),

    # ── 감사 198: 브레이크가 스스로 꺼지던 자리 ──────────────────
    # 세 항목 모두 "장치가 꺼졌다"가 아니라 "장치가 **조용히** 꺼졌다"를
    # 지킨다. 원래 상태는 사고가 나기 전까지 아무도 모른다.
    ("서킷브레이커가 NaN 자산값을 기준선으로 받아들인다(세션 내내 꺼진다)",
     "quant/live/circuit_breaker.py",
     "        eq = usable_equity(equity, \"서킷브레이커\")\n"
     "        if eq is None:\n"
     "            return self.tripped",
     "        eq = float(equity)\n"
     "        if False:\n"
     "            return self.tripped",
     "tests/test_the_brakes_do_not_switch_themselves_off.py"),

    ("킬스위치가 NaN 자산값을 그날 기준 자본으로 받아들인다(하루 종일 꺼진다)",
     "quant/live/killswitch.py",
     "        eq = usable_equity(equity, \"일일 손실 킬스위치\")\n"
     "        if eq is None:\n"
     "            return False",
     "        eq = float(equity)\n"
     "        if False:\n"
     "            return False",
     "tests/test_the_brakes_do_not_switch_themselves_off.py"),

    ("손실 한도의 분수/퍼센트 검증을 끈다(0.03을 3으로 적으면 영영 발동 안 함)",
     "quant/live/riskguard.py",
     "    if not 0.0 < v <= 1.0:",
     "    if False:",
     "tests/test_the_brakes_do_not_switch_themselves_off.py"),

    # 감사 197 — 조종석·감시 탭이 입금을 수익으로 세던 자리(실측 +1087.50%).
    ("두 화면이 입금 효과 제거를 건너뛴다(입금이 실력으로 찍힌다)",
     "quant/live/ledger_basics.py",
     "    deposits = state.get(\"deposits\") or []\n"
     "    if deposits:",
     "    deposits = state.get(\"deposits\") or []\n"
     "    if False:",
     "tests/test_the_cockpit_does_not_count_deposits_as_skill.py"),

    # 감사 211 — 197의 거울상. 반영되지 않은 입금을 원금에 더하면 그 금액이
    # 통째로 **손실**로 보인다(실측 -920,749원).
    ("반영 전 입금까지 원금에 더한다(입금액이 그대로 손실로 찍힌다)",
     "quant/live/ledger_basics.py",
     "    return float(start_cash) + sum(float(d[\"amount\"])\n"
     "                                   for d in settled_deposits(deposits))",
     "    return float(start_cash) + sum(float(d[\"amount\"])\n"
     "                                   for d in deposits or [])",
     "tests/test_a_deposit_is_not_a_loss.py"),

    ("정산 도장을 무시하고 전부 반영됐다고 본다",
     "quant/live/ledger_basics.py",
     '    return bool(dep.get("settled_bar"))',
     "    return True",
     "tests/test_a_deposit_is_not_a_loss.py"),

    # 도장이 있으면 그 봉으로 귀속해야 한다. 입금 날짜로만 찾으면 봉 날짜가
    # 달력보다 뒤처진 사이의 입금이 **귀속처를 못 찾아 통째로 무시**되고,
    # 다음 배치에서 자산만 뛴 것으로 보여 실력이 +1149%로 남는다.
    ("입금 귀속을 정산된 봉이 아니라 입금 날짜로만 찾는다(TWR이 입금만큼 뛴다)",
     "quant/live/ledger_basics.py",
     '    return str(dep.get("settled_bar") or dep.get("date") or "")',
     '    return str(dep.get("date") or "")',
     "tests/test_a_deposit_is_not_a_loss.py"),

    # 도장을 찍는 자리는 자산을 다시 잰 배치 하나뿐이다. 안 찍으면 입금이
    # 영원히 '접수됨'으로 남아 원금이 오르지 않는다 — 이번엔 수익 착시.
    ("배치가 입금 정산 도장을 안 찍는다(반영된 입금이 원금에 영영 안 들어간다)",
     "quant/live/daily.py",
     "        if not _d.get(\"settled_bar\"):\n"
     "            _d[\"settled_bar\"] = bar",
     "        if False:\n"
     "            _d[\"settled_bar\"] = bar",
     "tests/test_a_deposit_is_not_a_loss.py"),

    # ── 얇은 파일 전수조사 (감사 214) ────────────────────────────
    # 변이 1건 이하였던 23개 파일. "검사가 있다"와 "검사가 무언가를
    # 지킨다"는 다르다 — 여기 있던 파일들은 앞의 것만 사실이었다.

    # stop_guard — 실측: 숏 88봉 → 0봉. 스톱을 씌우면 숏이 통째로 사라졌다.
    ("스톱 래퍼가 숏 허용을 물려받지 않는다(감싸는 순간 숏이 전부 사라진다)",
     "quant/strategies/stop_guard.py",
     "        self.allow_short = base.allow_short",
     "        pass",
     "tests/test_the_stop_guard_does_not_eat_half_the_strategy.py"),

    ("스톱이 롱에서 발동하지 않는다(가드가 이름만 남는다)",
     "quant/strategies/stop_guard.py",
     "                hit = c < extreme * (1.0 - self.trail)",
     "                hit = False",
     "tests/test_the_stop_guard_does_not_eat_half_the_strategy.py"),

    ("숏은 스톱 없이 방치한다(한쪽만 지키는 '가드')",
     "quant/strategies/stop_guard.py",
     "                hit = c > extreme * (1.0 + self.trail)",
     "                hit = False",
     "tests/test_the_stop_guard_does_not_eat_half_the_strategy.py"),


    # 유동성 필터 — 거래대금이 마른 구간을 막는 것이 존재 이유다.

    ("거래대금을 모르는 구간(NaN)에서 진입을 허용한다",
     "quant/strategies/liquidity.py",
     "        allowed = allowed.where(dollar_vol.notna(), 0.0)",
     "        allowed = allowed.where(dollar_vol.notna(), 1.0)",
     "tests/test_filter_wrappers.py"),

    # ADX 필터 — 추세가 약할 때 매매를 막는다.

    # 신호 정규화 — 모든 전략이 지나가는 문.

    ("목표 비중의 [-1,1] 상한을 없앤다(자본 이상으로 실린다)",
     "quant/strategies/base.py",
     '        return signal.clip(-1.0, 1.0).rename("target")',
     '        return signal.rename("target")',
     "tests/test_every_strategy_obeys_its_own_rule.py"),

    # 전략별 방향 규칙 — 반대로 매매하면 그것이 가장 큰 손실이다.






    ("평균회귀의 중심선 복귀 청산을 없앤다(들어가면 안 나온다)",
     "quant/strategies/mean_reversion.py",
     "            elif position == 1 and c[i] >= m[i]:\n                position = 0                # 중심선 복귀 → 롱 청산",
     "            elif False:\n                position = 0                # 중심선 복귀 → 롱 청산",
     "tests/test_every_strategy_obeys_its_own_rule.py"),

    # 이벤트 가드 — 판단한 쪽이 설명을 남긴다(감사 70).
    ("이벤트 창에서 비중을 줄이지 않는다(가드가 이름만 남는다)",
     "quant/strategies/event_guard.py",
     "            [self.factor if getattr(ix, \"date\", lambda: None)() in guarded\n             else 1.0 for ix in df.index],",
     "            [1.0 for ix in df.index],",
     "tests/test_briefing_events.py"),

    # 탐색 — 방향을 잘못 잡으면 최악을 최고로 뽑는다.

    ("잘못된 파라미터 조합에서 탐색이 통째로 죽는다",
     "quant/optimize/grid.py",
     "        except (ValueError, TypeError):\n            continue  # 잘못된 조합 (예: fast >= slow) 은 건너뜀",
     "        except (ValueError, TypeError):\n            raise  # 잘못된 조합 (예: fast >= slow) 은 건너뜀",
     "tests/test_optimize.py"),


    # 데이터 계약 — 가격 없는 봉만 버린다(감사 163).



    # 스크리너 — 재무를 못 받은 종목을 후보로 세면 안 된다.

    # 튜닝 — 정직성 안내문이 사라지면 룩어헤드 여부를 아무도 못 읽는다.

    # 얇았던 파일들 — 기존 항목과 **다른 계약**을 하나씩 더 건다(감사 214).

    # 조종석 렌더 — 여기는 변이가 한 건도 없었다.
    ("조종석이 잘려나간 과거의 손익·낙폭 보정을 건너뛴다(위험 지표가 저절로 좋아진다)",
     "quant/reporting/dashboard.py",
     "    _k = equity_curve_kpis(state)",
     '    _k = {"current": 0.0, "pnl": 0.0, "max_drawdown": 0.0}',
     "tests/test_the_cockpit_does_not_count_deposits_as_skill.py"),

    ("조종석이 그릴 값이 없는데도 곡선을 그린다",
     "quant/reporting/dashboard.py",
     "    span = axis_span(vals)\n    if span is None:",
     "    span = axis_span(vals) or (0.0, 1.0, 1.0)\n    if False:",
     "tests/test_a_missing_value_cannot_erase_a_chart.py"),

    # 안전장치 기준값 — NaN·inf를 기준선으로 삼으면 조용히 꺼진다.
    ("안전장치가 NaN·inf 자산값을 기준선으로 받아들인다(브레이크가 조용히 꺼진다)",
     "quant/live/riskguard.py",
     "    if not math.isfinite(v):\n        log.error(",
     "    if False:\n        log.error(",
     "tests/test_the_brakes_do_not_switch_themselves_off.py"),

    # 공포탐욕 — 0~100을 0~1로 맞추지 않으면 피처 스케일이 100배 틀어진다.
    ("공포탐욕지수를 0~1로 정규화하지 않는다(피처 크기가 100배가 된다)",
     "quant/data/sentiment.py",
     '    return (s / 100.0).to_frame("fear_greed")',
     '    return s.to_frame("fear_greed")',
     "tests/test_the_thin_files_are_actually_guarded.py"),

    # 전략 청산 규칙 — 진입만 검사하면 '들어가면 안 나오는' 전략을 못 잡는다.
    ("RSI 롱 청산(중심선 복귀)을 없앤다(한 번 사면 안 판다)",
     "quant/strategies/rsi.py",
     "            elif pos > 0 and v >= 50:      # 롱: 중심선 복귀 시 청산",
     "            elif False:      # 롱: 중심선 복귀 시 청산",
     "tests/test_every_strategy_obeys_its_own_rule.py"),

    ("스토캐스틱 숏 청산을 없앤다(롱만 대칭으로 빠져나온다)",
     "quant/strategies/stochastic.py",
     "            elif pos < 0 and v <= 50:      # 숏: 중심선 복귀 시 청산(대칭)",
     "            elif False:      # 숏: 중심선 복귀 시 청산(대칭)",
     "tests/test_the_thin_files_are_actually_guarded.py"),

    # 파라미터 검증 — fast >= slow는 교차 자체가 성립하지 않는다.
    ("이동평균의 fast/slow 순서 검증을 끈다(교차가 성립하지 않는 조합이 통과한다)",
     "quant/strategies/moving_average.py",
     '        if fast >= slow:\n            raise ValueError("fast는 slow보다 작아야 합니다.")',
     "        if False:\n            raise ValueError(\"fast는 slow보다 작아야 합니다.\")",
     "tests/test_optimize.py"),

    ("MACD의 fast/slow 순서 검증을 끈다",
     "quant/strategies/macd.py",
     '        if fast >= slow:\n            raise ValueError("fast는 slow보다 작아야 합니다.")',
     "        if False:\n            raise ValueError(\"fast는 slow보다 작아야 합니다.\")",
     "tests/test_the_thin_files_are_actually_guarded.py"),

    # 모멘텀 숏 — 문턱을 대칭으로 쓰지 않으면 관망 구간이 사라진다.
    ("모멘텀의 숏 문턱에서 부호를 뺀다(중립 구간이 사라져 늘 어느 한쪽에 실린다)",
     "quant/strategies/momentum.py",
     "        signal[past_return < -self.threshold] = -1.0",
     "        signal[past_return < self.threshold] = -1.0",
     "tests/test_the_thin_files_are_actually_guarded.py"),

    # 켈트너 — 돌파 상태를 유지하지 않으면 밴드 안에서 매번 관망으로 튄다.
    ("켈트너가 돌파 상태를 이어가지 않는다(밴드 안에서 매일 청산·재진입한다)",
     "quant/strategies/keltner.py",
     "        signal = signal.ffill().fillna(0.0)",
     "        signal = signal.fillna(0.0)",
     "tests/test_the_thin_files_are_actually_guarded.py"),

    # ADX — 방향성 0인 봉의 NaN이 period봉 동안 전파돼 과도하게 게이팅한다.
    ("ADX에서 방향성 0인 봉의 NaN을 0으로 채우지 않는다(추세강도가 며칠씩 0이 된다)",
     "quant/strategies/adx.py",
     "          / (plus_di + minus_di).replace(0, np.nan)).fillna(0.0)",
     "          / (plus_di + minus_di).replace(0, np.nan))",
     "tests/test_the_thin_files_are_actually_guarded.py"),

    # 스크리너 — top_n을 넘기지 않으면 상위 선별이 통째로 사라진다.
    ("스크리너가 상위 N 제한을 넘기지 않는다(후보 전체가 편입된다)",
     "quant/portfolio/screener.py",
     "    weights = rank_factors(ratios, factors, top_n=top_n)",
     "    weights = rank_factors(ratios, factors)",
     "tests/test_the_thin_files_are_actually_guarded.py"),

    # 리포트 매매 마커 — 언제 사고팔았는지가 곡선 위에서 사라지면 안 된다.
    ("리포트 차트에서 매매 시점 마커를 지운다(언제 사고팔았는지가 안 보인다)",
     "quant/reporting/html_report.py",
     "    line = \" \".join(f\"{x:.1f},{y:.1f}\"\n"
     "                    for x, y in plot_points(close, width, height, lo, rng))",
     "    line = \"\"\n"
     "    _ = plot_points(close, width, height, lo, rng)",
     "tests/test_the_thin_files_are_actually_guarded.py"),

    # 코인 보조 거래소 — 단일 거래소 의존이 야간 자동화의 최약점이었다.
    ("코인이 기본 거래소만 시도한다(점검·지역차단 하나로 그날 기록이 빈다)",
     "quant/data/crypto.py",
     "        attempts += [(ex, None) for ex in _FALLBACK_EXCHANGES\n"
     "                     if ex != self.exchange_id]",
     "        pass",
     "tests/test_data_fallback.py"),

    # 데이터 계약 — 중복 타임스탬프가 남으면 같은 봉이 두 번 계산된다.
    ("중복 타임스탬프를 지우지 않는다(같은 봉이 두 번 수익률로 들어간다)",
     "quant/data/base.py",
     "        df = df[~df.index.duplicated(keep=\"last\")].sort_index()",
     "        df = df.sort_index()",
     "tests/test_the_thin_files_are_actually_guarded.py"),

    # 튜닝 — 정직성 안내문이 사라지면 룩어헤드 여부를 읽을 방법이 없다.
    ("워크포워드 튜닝 결과에서 정직성 안내문을 뺀다",
     "quant/optimize/tuning.py",
     '    return {**result, "note": HONESTY_NOTE}',
     "    return result",
     "tests/test_optimize.py"),

    # 감사 223 — 조종석이 실제 보유 옆에 '오늘의 결정'을 비중이라 붙이던 자리.
    ("조종석이 보유 대신 오늘의 결정을 비중으로 보여준다(보유 중인데 0%)",
     "quant/web/app.py",
     '                position["weight"] = _hw',
     '                position["weight"] = _last.get("weight")',
     "tests/test_the_cockpit_tells_the_same_story.py"),

    ("옛 기록의 보유 비중을 계산하지 않고 버린다(정보가 있는데 모름으로 둔다)",
     "quant/web/app.py",
     "                    if isinstance(_px, (int, float)) and _eq:",
     "                    if False:",
     "tests/test_the_cockpit_tells_the_same_story.py"),

    # 감사 224 — 낙폭 차트를 원자산으로 그리던 자리(입금이 손실을 지운다).
    ("조종석에 입금 제거 성장 지수를 안 보낸다(낙폭 차트가 원자산으로 돌아간다)",
     "quant/web/app.py",
     '                      "spark_twr": [round(x, 6) for x in _idx[-60:]],',
     '                      "spark_twr": None,',
     "tests/test_the_cockpit_tells_the_same_story.py"),

    # 감사 222 — 소수점 매매가 없는 시장의 소수 주 보유를 밝히는 자리.
    ("실계좌에서 재현 불가한 소수 주 보유를 장부가 숨긴다",
     "quant/live/daily.py",
     '        "fractional_lot": (\n'
     "            bool(pos and pos.quantity\n"
     "                 and market not in FRACTIONAL_MARKETS",
     '        "fractional_lot": (\n'
     "            bool(False\n"
     "                 and market not in FRACTIONAL_MARKETS",
     "tests/test_the_thin_files_are_actually_guarded.py"),

    # 감사 221 — 배치 시각을 미국장 마감 뒤로 옮긴 자리(연중 안전).
    ("배치 시각을 미국장 마감 전으로 되돌린다(겨울에 미국 신호가 한 세션 뒤처진다)",
     ".github/workflows/daily-paper.yml",
     '    - cron: "15 22 * * *"',
     '    - cron: "30 20 * * *"',
     "tests/test_the_batch_runs_after_the_markets_it_trades.py"),

    ("SNS 게시를 배치보다 앞으로 되돌린다(어제 숫자가 오늘 것으로 방송된다)",
     ".github/workflows/social-post.yml",
     '    - cron: "45 23 * * *"',
     '    - cron: "45 21 * * *"',
     "tests/test_the_batch_runs_after_the_markets_it_trades.py"),

    # 감사 220 — 배치 시각과 시장 마감이 어긋나면 한 시장만 뒤처지던 자리.
    ("시장별 판단 봉의 나이를 장부에 안 남긴다(겨울에 미국만 뒤처져도 모른다)",
     "quant/live/daily.py",
     '              "bar_age_days": bar_age or None,',
     '              "bar_age_days": None,',
     "tests/test_the_thin_files_are_actually_guarded.py"),

    ("한 시장만 뒤처져도 경고하지 않는다",
     "quant/live/daily.py",
     "    if stale_gap >= 2:",
     "    if False:",
     "tests/test_the_thin_files_are_actually_guarded.py"),

    # 감사 219 — 주간 리포트가 입금 귀속의 옛 복사본을 들고 있던 자리.
    # 실측: 주간 요약 +1149.06% / 장부 TWR -0.94%
    ("주간 요약이 입금 귀속을 손으로 다시 계산한다(입금이 주간 수익으로 둔갑)",
     "quant/live/daily.py",
     '    flows = _flows_by_date(src, st.get("deposits") or [])',
     "    flows = {}",
     "tests/test_a_deposit_is_not_a_loss.py"),

    # 감사 218 — 캡션이 코드 상수의 시작금을 방송에 내보내던 자리.
    ("SNS 캡션이 지금 원금 대신 코드 상수를 말한다(방송에 낡은 금액이 나간다)",
     "quant/reporting/social.py",
     '    _p = x.get("principal")',
     '    _p = None',
     "tests/test_social_path_stays_light.py"),

    ("계좌를 다시 연 사실을 캡션이 숨긴다(기록 0일이 고장으로 읽힌다)",
     "quant/reporting/social.py",
     '    if rs.get("date") and not x.get("equity"):',
     "    if False:",
     "tests/test_social_path_stays_light.py"),

    # 감사 217 — 표시되는 '비중'이 잔고가 아니라 오늘의 결정이던 자리.
    ("종목 계좌가 실제 보유 비중을 기록하지 않는다(매도 예정 종목이 '0%'로 보인다)",
     "quant/live/daily.py",
     '        "held_weight": (round(pos.quantity * price / equity, 4)\n'
     "                        if pos and equity else 0.0),",
     '        "held_weight": round(weight, 4),',
     "tests/test_two_ledgers_are_not_confused.py"),

    # 감사 216 — 환산은 했는데 **어떤 환율로 했는지**를 안 남기던 자리.
    ("그날 적용한 환율을 장부에 안 남긴다(나중에 아무도 검산할 수 없다)",
     "quant/live/daily.py",
     '              "fx_usdkrw": (round(float(fx_rate), 4)\n'
     "                            if fx_rate is not None else None),",
     '              "fx_usdkrw": None,',
     "tests/test_two_ledgers_are_not_confused.py"),

    ('적용 환율을 사이트로 내보내지 않는다',
     'quant/live/daily.py',
     '            if hist and hist[-1].get("fx_usdkrw") is not None:\n                status["paper"][key]["fx_usdkrw"] = hist[-1]["fx_usdkrw"]',
     '            if False:\n                status["paper"][key]["fx_usdkrw"] = hist[-1]["fx_usdkrw"]',
     'tests/test_two_ledgers_are_not_confused.py'),

    ('계좌 통화를 사이트로 내보내지 않는다(어느 단위인지 화면이 말 못 한다)',
     'quant/live/daily.py',
     '            status["paper"][key]["currency"] = st.get("currency")',
     '            pass',
     'tests/test_two_ledgers_are_not_confused.py'),

    # 감사 215 — 통합 계좌만 원화로 열고 섀도 대조군을 빠뜨린 자리.
    ("정리 안 된(단위 혼재) 장부 위에서도 배치를 돌린다(자산이 환율 배수만큼 뛴다)",
     "quant/live/daily.py",
     '    if st.get("currency") != "KRW" and (st.get("positions") or st.get("history")):',
     "    if False:",
     "tests/test_the_account_speaks_one_currency.py"),

    ("새로 만드는 장부에 원화 표시를 안 남긴다(다음 배치가 스스로를 거절한다)",
     "quant/live/daily.py",
     '        st = {"market": mkt_tag, "symbol": sym_tag, "currency": "KRW",',
     '        st = {"market": mkt_tag, "symbol": sym_tag,',
     "tests/test_the_account_speaks_one_currency.py"),

    # 감사 213 — 값 하나가 결측이면 차트가 통째로 사라지던 자리.
    # (`hi - lo or 1.0`은 NaN을 못 막는다 — NaN은 참이다)
    ("차트 범위 계산에서 결측·무한값을 거르지 않는다(차트가 조용히 사라진다)",
     "quant/reporting/scale.py",
     "        if math.isfinite(f):\n            out.append(f)",
     "        out.append(f)",
     "tests/test_a_missing_value_cannot_erase_a_chart.py"),

    ("그릴 값이 없어도 가짜 평평한 범위를 돌려준다(없는 데이터가 생긴다)",
     "quant/reporting/scale.py",
     "    if not vals:\n        return None",
     "    if not vals:\n        return (0.0, 1.0, 1.0)",
     "tests/test_a_missing_value_cannot_erase_a_chart.py"),

    ("좌표 생성에서 결측 봉을 건너뛰지 않는다(점 하나가 nan이면 선이 통째로 버려진다)",
     "quant/reporting/scale.py",
     "        if not math.isfinite(f):\n            continue",
     "        if False:\n            continue",
     "tests/test_a_missing_value_cannot_erase_a_chart.py"),

    ("히트맵이 모르는 값을 색으로 칠한다('중립'으로 읽힌다)",
     "quant/reporting/heatmap.py",
     '        return "hsl(0 0% 72%)"          # 회색 = 값 없음(중립 아님)',
     '        t = 0.5',
     "tests/test_a_missing_value_cannot_erase_a_chart.py"),

    # 감사 210 — 교차 검증 판정이 인자 순서에 따라 뒤집히던 자리.
    ("교차 검증 분모를 첫 인자 기준으로 되돌린다(순서만 바꿔도 판정이 뒤집힌다)",
     "quant/data/crosscheck.py",
     '    denom = pd.concat([pair["a"].abs(), pair["b"].abs()], axis=1).max(axis=1)',
     '    denom = pair["a"].abs()',
     "tests/test_two_sources_agree_regardless_of_order.py"),

    ("비교 못 한 봉이 있어도 '통과'라고 말한다(검증 못 함은 통과가 아니다)",
     "quant/data/crosscheck.py",
     '        "ok": bool(n_blind == 0 and len(valid) and max_diff <= tolerance),',
     '        "ok": bool(len(valid) and max_diff <= tolerance),',
     "tests/test_two_sources_agree_regardless_of_order.py"),

    # 감사 212 — 한 계좌에 원화와 달러가 섞여 있던 자리.
    ("해외 종목을 환산하지 않고 달러 가격 그대로 계좌에 담는다",
     "quant/live/daily.py",
     "            px_krw = _to_krw_or_die(market, float(df[\"close\"].iloc[-1]),\n                                    fx_rate)",
     "            px_krw = float(df[\"close\"].iloc[-1])",
     "tests/test_the_account_speaks_one_currency.py"),

    ("환율을 모를 때 1.0으로 때운다(고치기 전 상태로 되돌아간다)",
     "quant/data/fx.py",
     "    if rate is None:\n        return None\n    return p * float(rate)",
     "    if rate is None:\n        return p\n    return p * float(rate)",
     "tests/test_the_account_speaks_one_currency.py"),

    ("원화 종목까지 환율을 곱한다(자산이 1,470배가 된다)",
     "quant/data/fx.py",
     "    return market in USD_MARKETS",
     "    return True",
     "tests/test_the_account_speaks_one_currency.py"),

    ("말도 안 되는 환율(뒤집힌 계열)을 그대로 받아들인다",
     "quant/data/fx.py",
     "    if rate is not None and not (FX_MIN <= rate <= FX_MAX):",
     "    if False:",
     "tests/test_the_account_speaks_one_currency.py"),

    ("환율 조회 실패를 캐시한다(일시적 장애가 프로세스 내내 남는다)",
     "quant/data/fx.py",
     "        log.warning(\"원/달러를 확인하지 못했습니다 — 해외 종목을 원화로 \"\n"
     "                    \"환산할 수 없습니다. 1.0으로 대신하지 않습니다.\")\n"
     "        return None",
     "        _MEMO[\"usdkrw\"] = None\n"
     "        return None",
     "tests/test_the_account_speaks_one_currency.py"),

    ("계좌를 두 번 다시 열 수 있게 한다(지금 기록이 통째로 사라진다)",
     "quant/live/ledger_basics.py",
     "    if old.get(\"currency\") == \"KRW\":",
     "    if False:",
     "tests/test_the_account_speaks_one_currency.py"),

    # 보관본이 산 계좌를 덮어쓰던 자리 — 새 계좌를 열었는데 사이트는
    # 닫힌 옛 계좌를 계속 보여줬다(실측).
    ("보관된 옛 장부를 살아 있는 계좌로 읽는다(닫힌 계좌가 사이트를 덮는다)",
     "quant/live/ledger_basics.py",
     "    return ARCHIVE_MARK in os.path.basename(filename)",
     "    return False",
     "tests/test_the_account_speaks_one_currency.py"),

    ('사이트 장부 목록에서 보관본을 걸러내지 않는다',
     'quant/live/daily.py',
     '    for path in ledger_files(state_dir):\n        with open(path, encoding="utf-8") as f:\n            st = json.load(f)\n        if st.get("market") == "portfolio":',
     '    import glob\n    for path in sorted(glob.glob(os.path.join(state_dir, "paper", "*.json"))):\n        with open(path, encoding="utf-8") as f:\n            st = json.load(f)\n        if st.get("market") == "portfolio":',
     'tests/test_the_account_speaks_one_currency.py'),

    ("옛 장부를 보관하지 않고 덮어쓴다(과거가 사라진다)",
     "quant/live/ledger_basics.py",
     "    shutil.copy2(path, archive)          # 옛 장부는 한 글자도 고치지 않는다",
     "    pass",
     "tests/test_the_account_speaks_one_currency.py"),

    # 잔고 표 — 현금까지 자산과 같은 시점이어야 표의 합이 맞는다.
    # 안 빼면 보유 37,341 + 현금 961,910 = 999,251 ≠ 자산 79,251이 된다.
    ('잔고 표의 현금에서 반영 전 입금을 안 뺀다(표의 합이 자산을 넘어선다)',
     'quant/live/daily.py',
     '                float(st.get("cash") or 0.0)\n                - sum(float(d["amount"]) for d in waiting), 2)',
     '                float(st.get("cash") or 0.0), 2)',
     'tests/test_a_deposit_is_not_a_loss.py'),

    ("시세를 못 받은 종목을 '정상 평가'로 표시한다(손익 0이 사실처럼 보인다)",
     "quant/live/ledger_basics.py",
     "        marked = px is not None",
     "        marked = True",
     "tests/test_a_deposit_is_not_a_loss.py"),

    ("잔고의 매입금액을 평가금액과 같게 만든다(평가손익이 항상 0)",
     "quant/live/ledger_basics.py",
     "        cost, value = qty * avg, qty * px",
     "        cost, value = qty * px, qty * px",
     "tests/test_a_deposit_is_not_a_loss.py"),

    ("사이트에서 '반영 대기 중인 입금'을 지운다(넣었는데 화면이 그대로다)",
     'quant/live/daily.py',
     '            if waiting:\n                status["paper"][key]["pending_deposits"] = waiting',
     '            if False:\n                status["paper"][key]["pending_deposits"] = waiting',
     'tests/test_a_deposit_is_not_a_loss.py'),

    # 감시 탭이 서버 값을 쓰지 않고 자기가 계산하면 5초 뒤 덮어쓴다.
    ("감시 탭에 서버가 잰 KPI를 안 실어 보낸다(브라우저가 옛 계산으로 돌아간다)",
     "quant/web/app.py",
     "        st[\"kpi\"] = equity_curve_kpis(st)",
     "        st[\"kpi\"] = {}",
     "tests/test_history_truncation.py"),

    # ── 사이징·비용(오디션 성적과 실제 노출을 동시에 좌우) ──
    ("실현변동성 0을 NaN으로 바꾸는 가드를 뺀다(거래정지 종목이 최대 레버리지)",
     "quant/risk/manager.py",
     "            realized = realized.where(realized > 1e-9, np.nan)",
     "            realized = realized",
     "tests/test_risk_limits_bind_at_the_source.py"),

    ("변동성 타깃 레버리지 상한(3배)을 푼다",
     "quant/risk/manager.py",
     "            scale = (cfg.target_vol / realized).clip(upper=3.0).fillna(0.0)",
     "            scale = (cfg.target_vol / realized).clip(upper=1e9).fillna(0.0)",
     "tests/test_risk_limits_bind_at_the_source.py"),

    ("최대 포지션 한도를 걸지 않는다",
     "quant/risk/manager.py",
     "        sized = (target * scale).clip(-cfg.max_position, cfg.max_position)",
     "        sized = (target * scale)",
     "tests/test_risk_limits_bind_at_the_source.py"),

    ("회전 비용에서 슬리피지를 뺀다(백테스트가 낙관적으로 바뀐다)",
     "quant/backtest/costs.py",
     "        return (self.fee + slip + self.impact_coef * vol) * turnover",
     "        return (self.fee + self.impact_coef * vol) * turnover",
     "tests/test_costs.py"),

    ("펀딩비 이상치 상한을 푼다(거래소 오류값이 성적을 통째로 왜곡)",
     "quant/backtest/costs.py",
     "        return max(-self._FUNDING_RATE_CAP, min(self._FUNDING_RATE_CAP, v))",
     "        return v",
     "tests/test_risk_limits_bind_at_the_source.py"),

    # ── 승격 판정의 심장(오디션 결승) ──
    #
    # 이 파일이 "새 챔피언으로 바꿀 것인가"를 최종 결정한다. 문턱 세 개가
    # 모두 통과해야 교체인데, 셋 다 변이가 닿은 적이 없었다(감사 142).
    ("승격에서 t-검정 조건을 뺀다(통계 없이 교체)",
     "quant/live/champion_challenger.py",
     "        swap = bool(n >= self.min_obs and mean > self.edge and t_stat > self.t_threshold)",
     "        swap = bool(n >= self.min_obs and mean > self.edge)",
     "tests/test_promotion_gates_actually_gate.py"),

    ("관망 봉까지 t-검정 표본에 넣는다(0으로 표본을 부풀려 판단 왜곡)",
     "quant/live/champion_challenger.py",
     "        diff = (rh - rc)[active].dropna()",
     "        diff = (rh - rc).dropna()",
     "tests/test_promotion_gates_actually_gate.py"),

    ("결승전이 지정 구간을 무시하고 전 기간을 본다",
     "quant/live/champion_challenger.py",
     "            rc, rh = rc.iloc[-tail:], rh.iloc[-tail:]",
     "            rc, rh = rc, rh",
     "tests/test_promotion_gates_actually_gate.py"),

    # ── 장 시간 가드(닫힌 시장에 주문을 내지 않게) ──
    ("주말 휴장 판정을 끈다(토·일에도 개장으로 봄)",
     "quant/live/market_hours.py",
     "    if local.weekday() >= 5:            # 토(5)·일(6) 휴장\n        return False",
     "    if False:                           # 토(5)·일(6) 휴장\n        return False",
     "tests/test_fill_and_hours.py"),

    ("정규장 시간 판정을 통과시킨다(새벽에도 개장)",
     "quant/live/market_hours.py",
     "    return open_t <= local.time() <= close_t",
     "    return True",
     "tests/test_fill_and_hours.py"),

    ("시장 시간대 변환을 없앤다(UTC 시각을 현지 시각으로 착각)",
     "quant/live/market_hours.py",
     "    return now.astimezone(ZoneInfo(tzname))",
     "    return now",
     "tests/test_fill_and_hours.py"),

    # 감사 143 — 동작을 고치고 설명을 안 고쳐 장부가 낡은 말을 했다.
    ("미완성 봉 기록이 다시 '결정에 쓴 봉'이라고 말하게 되돌린다",
     "quant/data/barclock.py",
     "            \"note\": \"체결·평가에 쓴 마지막 봉이 아직 만들어지는 중이었다 — \"",
     "            \"note\": \"결정 시점에 아직 만들어지는 중이던 봉 — \"",
     "tests/test_signal_frame.py"),

    # ── 워크포워드 검증(‘신뢰할 만함’ 판정의 근거) ──
    ("최적화 구간이 검증 구간까지 미리 본다(워크포워드의 존재 이유가 사라짐)",
     "quant/optimize/walkforward.py",
     "        is_slice = df.iloc[start : start + is_window]",
     "        is_slice = df.iloc[start : start + is_window + gap + oos_window]",
     "tests/test_walkforward_really_holds_out.py"),

    ("엠바고 갭을 없앤다(학습 직후 봉이 검증에 바로 들어간다)",
     "quant/optimize/walkforward.py",
     "        oos_start = start + is_window + gap        # 엠바고 갭만큼 띄운다",
     "        oos_start = start + is_window              # 엠바고 갭만큼 띄운다",
     "tests/test_walkforward_really_holds_out.py"),

    ("워밍업 구간까지 OOS 성과로 센다(관망 봉이 성적을 희석)",
     "quant/optimize/walkforward.py",
     "        oos_ret = res.returns.iloc[-oos_window:]",
     "        oos_ret = res.returns",
     "tests/test_walkforward_really_holds_out.py"),

    # ── PBO(과적합 확률) — '선택 절차가 노이즈를 고르는가'의 답 ──
    ("IS 1등 대신 OOS 1등을 고른다(PBO가 구조적으로 0이 된다)",
     "quant/robustness/pbo.py",
     "        best = int(np.argmax(sr_is))                 # IS 1등 설정",
     "        best = int(np.argmax(sr_oos))                # IS 1등 설정",
     "tests/test_pbo_knows_overfitting_when_it_sees_it.py"),

    ("PBO 판정 부호를 뒤집는다(과적합을 건전으로 보고)",
     "quant/robustness/pbo.py",
     "        \"pbo\": float((lam <= 0).mean()),",
     "        \"pbo\": float((lam >= 0).mean()),",
     "tests/test_pbo_knows_overfitting_when_it_sees_it.py"),

    ("조합 대칭 교차검증을 조합 하나로 줄인다(CSCV의 핵심이 사라짐)",
     "quant/robustness/pbo.py",
     "    for is_idx in combinations(range(S), S // 2):",
     "    for is_idx in [tuple(range(S // 2))]:",
     "tests/test_pbo_knows_overfitting_when_it_sees_it.py"),

    # ── DSR·PSR(엣지 입증 게이트가 읽는 값) ──
    ("다중검정 보정을 빼고 벤치마크를 0으로 둔다(운 좋은 승자를 실력으로)",
     "quant/robustness/deflated_sharpe.py",
     "    sr_star = expected_max_sharpe(n_trials, trials_sharpe_std) if n_trials > 1 else 0.0",
     "    sr_star = 0.0",
     "tests/test_deflated_sharpe_matches_the_paper.py"),

    ("왜도·첨도 보정을 뺀다(가끔 크게 터지는 전략이 안전한 전략과 같은 점수)",
     "quant/robustness/deflated_sharpe.py",
     "    denom = np.sqrt(max(1e-12, 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr ** 2))",
     "    denom = 1.0",
     "tests/test_deflated_sharpe_matches_the_paper.py"),

    ("기대 최대 샤프의 두 계수를 뒤바꾼다",
     "quant/robustness/deflated_sharpe.py",
     "        (1.0 - _EULER) * _ND.inv_cdf(1.0 - 1.0 / N)\n"
     "        + _EULER * _ND.inv_cdf(1.0 - 1.0 / (N * np.e))",
     "        _EULER * _ND.inv_cdf(1.0 - 1.0 / N)\n"
     "        + (1.0 - _EULER) * _ND.inv_cdf(1.0 - 1.0 / (N * np.e))",
     "tests/test_deflated_sharpe_matches_the_paper.py"),

    # 감사 146 — 부동소수 잡음이 0 판정을 뚫는다.
    ("분산 퇴화 판정을 다시 `sd <= 0`으로 되돌린다(상수 계열이 DSR 1.0)",
     "quant/robustness/deflated_sharpe.py",
     "    if degenerate_spread(sd, np.abs(r).mean()):",
     "    if sd <= 0:",
     "tests/test_deflated_sharpe_matches_the_paper.py"),

    ("샤프의 분산 퇴화 판정을 되돌린다(상수 수익이 천문학적 샤프)",
     "quant/backtest/metrics.py",
     "    _degenerate = degenerate_spread(_sd, float(returns.abs().mean()))",
     "    _degenerate = _sd <= 0",
     "tests/test_performance_metrics_are_exact.py"),

    ("A/B 비교의 분산 퇴화 판정을 되돌린다(상수 팔이 모든 재추출에서 압승)",
     "quant/robustness/compare.py",
     "    if degenerate_spread(sd, float(np.abs(r).mean())):   # 감사 146",
     "    if sd <= 0:",
     "tests/test_compare.py"),

    ("PBO의 분산 퇴화 판정을 되돌린다(평평한 구간이 IS 1등을 훔침)",
     "quant/robustness/pbo.py",
     "    ok = np.isfinite(sd) & (sd > SHARPE_REL_EPS * np.maximum(scale, 1e-300))",
     "    ok = sd > 0",
     "tests/test_pbo_knows_overfitting_when_it_sees_it.py"),

    # 감사 147 — A등급(돈이 움직임) 파일의 핵심 규칙에 처음 칼을 댄다.
    ("HRP 이분 배분을 뒤집는다(변동성 큰 군집에 예산을 더 준다)",
     "quant/live/hrp.py",
     "            alpha = 1.0 - v_l / (v_l + v_r)",
     "            alpha = v_l / (v_l + v_r)",
     "tests/test_alpha8_hrp_regime.py"),

    # ⚠️ '준대각화를 뺀다'는 변이는 넣지 않는다 — 우리 조건에서 **행동이
    #    거의 같다.** 군집 분산을 역분산으로 재는 순간 섞인 군집도 순수 군집과
    #    비슷한 값을 내서, 잎 순서를 버려도 저변동 군집 예산이 0.801 → 0.783
    #    (2%p)밖에 안 움직인다. 행동이 같은 변이를 '놓침'으로 세면 검사를
    #    존재하지 않는 피해에 못 박게 된다(FROZEN_IDEAS ㉚).
    ("HRP 입력 열 순서 고정을 푼다(종목 목록 순서가 배분을 바꾼다)",
     "quant/live/hrp.py",
     "        returns = returns[sorted(returns.columns, key=str)]",
     "        pass",
     "tests/test_allocation_does_not_depend_on_list_order.py"),

    ("HRP 군집분산을 역분산이 아닌 균등가중으로 잰다(위험 패리티가 사라짐)",
     "quant/live/hrp.py",
     "    ivp = 1.0 / np.maximum(np.diag(sub), 1e-16)",
     "    ivp = np.ones(len(sub), dtype=float)",
     "tests/test_allocation_does_not_depend_on_list_order.py"),

    ("켈리 공식에서 손익비 나눗셈을 뺀다(비율이 b배 부풀어 과대 베팅)",
     "quant/risk/kelly.py",
     "    f = (p * b - (1.0 - p)) / b",
     "    f = p * b - (1.0 - p)",
     "tests/test_kelly.py"),

    ("부분 켈리를 풀 켈리로 바꾼다(추정 오차에 장기 성장률이 무너진다)",
     "quant/risk/kelly.py",
     "    return min(top, frac * f)",
     "    return min(top, f)",
     "tests/test_kelly.py"),

    ("켈리 최소 표본 요건을 없앤다(거래 3번의 승률로 사이징)",
     "quant/risk/kelly.py",
     "    if n < max(1, int(min_trades)) or frac <= 0.0 or top <= 0.0:",
     "    if frac <= 0.0 or top <= 0.0:",
     "tests/test_kelly.py"),

    # ⚠️ 'arange(lo, i-1) → arange(lo, i)'는 변이로 넣지 않는다 — **룩어헤드가
    #    아니다.** 그 한 봉의 타깃은 rv[i]이고 예측 시점 i에 이미 확정돼 있다.
    #    값은 0.0039 달라지지만 접두사 안정성은 그대로 0.0이다(FROZEN_IDEAS ㉚).
    ("HAR 변동성을 전 구간으로 학습한다(예측이 미래를 본다)",
     "quant/risk/volforecast.py",
     "        rows = np.arange(lo, i - 1)",
     "        rows = np.arange(lo, n - 1)",
     "tests/test_vol_forecast_cannot_see_the_future.py"),

    ("HAR 예측의 안전 클립을 사실상 푼다(예측이 후행의 1/1000까지 내려가 비중 폭주)",
     "quant/risk/volforecast.py",
     "    pred_var = pred_var.clip(lower=base_var * 0.25, upper=base_var * 4.0)",
     "    pred_var = pred_var.clip(lower=base_var * 1e-6, upper=base_var * 1e6)",
     "tests/test_vol_forecast_cannot_see_the_future.py"),

    ("VaR 분위수 보간을 선형으로 되돌린다(손실을 과소평가)",
     "quant/risk/portfolio.py",
     '    q = float(r.quantile(1.0 - alpha, interpolation="lower"))',
     "    q = float(r.quantile(1.0 - alpha))",
     "tests/test_risk_portfolio.py"),

    ("CVaR를 VaR와 같은 값으로 만든다(꼬리 평균 손실이 사라짐)",
     "quant/risk/portfolio.py",
     "    cvar = -float(tail.mean()) if len(tail) else var",
     "    cvar = var",
     "tests/test_risk_portfolio.py"),

    # 감사 148 — 무인 실거래 경로만 견고화가 빠져 있었다.
    ("무인 실거래 배치의 견고화 래퍼를 벗긴다(재시도·체결확인·규격 전부 사라짐)",
     "quant/live/daily_live.py",
     "    return RobustBroker(broker, retries=3, backoff=2.0,",
     "    return broker\n    return RobustBroker(broker, retries=3, backoff=2.0,",
     "tests/test_live_orders_are_hardened.py"),

    ("실거래 체결 확인을 끈다(접수를 체결로 보고)",
     "quant/live/daily_live.py",
     "                        confirm_fills=True, fill_timeout=90.0,",
     "                        confirm_fills=False, fill_timeout=90.0,",
     "tests/test_live_orders_are_hardened.py"),

    ("장부에서 실제 체결 수량 칸을 뺀다(접수만으로 '샀다'가 된다)",
     "quant/live/daily_live.py",
     '                if order.status not in ("skipped",) and filled <= 0:',
     "                if False:",
     "tests/test_live_orders_are_hardened.py"),

    ("국내주식 주문 규격 선언을 지운다(1주 미만이 그대로 브로커까지 내려감)",
     "quant/broker/kr_live.py",
     "        return MarketSpec(min_qty=1.0, qty_step=1.0)",
     "        return MarketSpec()",
     "tests/test_live_orders_are_hardened.py"),

    ("미국주식을 정수 주로 잘라 버린다(소수점 예산이 통째로 사라짐)",
     "quant/broker/us_live.py",
     "        return MarketSpec(min_notional=1.0)",
     "        return MarketSpec(min_qty=1.0, qty_step=1.0, min_notional=1.0)",
     "tests/test_live_orders_are_hardened.py"),

    # 감사 149 — 분모가 사실상 0인 종목이 포트폴리오를 통째로 가져간다.
    ("역분산 배분의 퇴화 판정을 되돌린다(거래정지 종목이 비중 100%)",
     "quant/portfolio/allocation.py",
     "        ok &= var > REL_EPS * float(np.max(var[ok]))",
     "        pass",
     "tests/test_a_halted_symbol_cannot_take_the_book.py"),

    ("역변동성 배분의 퇴화 판정을 되돌린다",
     "quant/portfolio/allocation.py",
     "    inv = inv.where(vol.gt(floor, axis=0), np.nan)",
     "    inv = inv",
     "tests/test_a_halted_symbol_cannot_take_the_book.py"),

    ("오디션 배분의 과집중 상한을 없앤다(한 종목이 전부를 가져갈 수 있다)",
     "quant/portfolio/allocation.py",
     "    cap = min(1.0, mult / n)",
     "    cap = 1.0",
     "tests/test_a_halted_symbol_cannot_take_the_book.py"),

    ("HRP에서 퇴화 열 제외를 끈다(군집 분산이 그 열을 가장 안전하다고 본다)",
     "quant/live/hrp.py",
     "        if len(_keep) < 2:\n            return None                      # 쓸 수 있는 열이 둘 미만이면 폴백\n        returns = returns[_keep]",
     "        if len(_keep) < 2:\n            return None                      # 쓸 수 있는 열이 둘 미만이면 폴백",
     "tests/test_a_halted_symbol_cannot_take_the_book.py"),

    # ⚠️ ERC의 `R = R[_keep]`은 변이로 넣지 않는다 — **행동이 같다.**
    #    바로 아래 `capped.update({c: 0.0 for c in _dropped})`가 어차피 그
    #    종목을 0으로 덮어써서, 열을 빼든 안 빼든 결과가 같다. 두 줄 중
    #    실제로 판정을 바꾸는 건 아래쪽이고 그건 따로 걸어 두었다.
    #    (열 제외 자체는 반복법이 헛돌지 않게 하는 값어치가 있어 남긴다.)

    ("퇴화 종목의 키를 슬라이스에서 지운다(호출자가 기본 1/n을 준다)",
     "quant/live/daily.py",
     "        capped.update({c: 0.0 for c in _dropped})   # 퇴화 열은 명시적 0",
     "        pass",
     "tests/test_a_halted_symbol_cannot_take_the_book.py"),

    ("오디션 HRP의 열 순서 고정을 푼다(감사 147의 형제)",
     "quant/portfolio/allocation.py",
     "    win = win[sorted(win.columns, key=str)]",
     "    pass",
     "tests/test_allocation_does_not_depend_on_list_order.py"),

    # ⚠️ 이 항목도 감사 183에서 갈아 끼웠다. 예전 변이는 `hrp_weights` 안의
    #    합계 검사를 껐는데, 거기까지 오면 바로 위 `w / w.sum()`이 이미 합을
    #    1로 만들어 놓은 뒤라 **어떤 입력으로도 안 걸리는 방어**였다. 진짜
    #    위험한 자리는 배분을 받아들이는 호출부다 — 전부 0인 dict는 truthy라
    #    `or` 폴백을 그냥 통과한다.
    ("전부 0인 배분을 폴백 없이 채택한다(하루 통째로 관망인데 장부엔 hrp라 적힌다)",
     "quant/live/daily.py",
     "    hrp = hrp if is_allocation(hrp) else None",
     "    hrp = hrp",
     "tests/test_a_halted_symbol_cannot_take_the_book.py"),

    # 감사 150 — 같은 판정을 두 곳에서 다르게 쓰면 가장 극단이 빠져나간다.
    ("보정 구간 판정을 표와 다르게 되돌린다(확률 1.0이 경험 보정을 피해 간다)",
     "quant/live/calibration_guard.py",
     "        if row[\"confirmed\"] and _bin_of(row[\"lo\"], bins) == k:",
     "        if row[\"confirmed\"] and row[\"lo\"] <= p < row[\"hi\"]:",
     "tests/test_the_correction_reaches_the_most_confident_call.py"),

    ("경험 보정을 통째로 끈다(모델의 과신이 그대로 나간다)",
     "quant/live/calibration_guard.py",
     "            return row[\"actual\"], True",
     "            return p, False",
     "tests/test_the_correction_reaches_the_most_confident_call.py"),

    ("주문 단위 감사 로그 기록을 뺀다(증권사 체결 내역과 대사할 기록이 사라짐)",
     "quant/live/daily_live.py",
     "                record_order(",
     "                _ = lambda *a, **k: None; _(",
     "tests/test_live_orders_are_hardened.py"),

    # 감사 151 — 같은 규칙이 경로마다 달랐다(자동학습 루프).
    ("자동학습 루프가 진행 중인 봉으로 판단하게 되돌린다(변동성 과소추정)",
     "quant/live/autolearn.py",
     "        df_sig = self._signal_frame(df)",
     "        df_sig = df",
     "tests/test_the_learning_loop_judges_on_closed_bars.py"),

    ("자동학습 루프의 무행동 밴드를 없앤다(매 사이클 잔조정으로 수수료 누수)",
     "quant/live/autolearn.py",
     "                                      equity, rebalance_band=REBALANCE_BAND)",
     "                                      equity)",
     "tests/test_the_learning_loop_judges_on_closed_bars.py"),

    ("적중률을 판단과 다른 프레임으로 잰다(성적과 근거가 어긋난다)",
     "quant/live/autolearn.py",
     "        acc = directional_accuracy(df_sig, signals, window=self.accuracy_window)",
     "        acc = directional_accuracy(df, signals, window=self.accuracy_window)",
     "tests/test_the_learning_loop_judges_on_closed_bars.py"),

    # 감사 152 — 데이터 장애가 손실을 지운다.
    ("시세를 못 받은 종목을 매입가로 평가하게 되돌린다(손실이 장부에서 사라짐)",
     "quant/live/daily.py",
     "    marks = {**{k: v[\"price\"] for k, v in stale_marks.items()}, **prices}",
     "    marks = dict(prices)",
     "tests/test_a_data_outage_cannot_erase_a_loss.py"),

    ("마지막 시세를 상태에 안 남긴다(다음 날 매입가로 떨어진다)",
     "quant/live/daily.py",
     '                   "last_price": marks.get(p.symbol, p.avg_price),',
     '                   "last_price": None,',
     "tests/test_a_data_outage_cannot_erase_a_loss.py"),

    ("낡은 시세로 평가한 사실을 장부에서 지운다(정상 평가인 척)",
     "quant/live/daily.py",
     '                  {k: {"price": round(v["price"], 6), "as_of": v["as_of"]}\n'
     '                   for k, v in stale_marks.items()} or None),',
     "                  None),",
     "tests/test_a_data_outage_cannot_erase_a_loss.py"),

    # 감사 153 — 비용이 체결보다 한 봉 먼저 부과됐다.
    ("거래비용을 체결 봉이 아니라 결정 봉에 부과한다(포지션 전에 비용부터)",
     "quant/portfolio/backtest.py",
     "        cost = self.cost * turnover.shift(1).fillna(0.0)",
     "        cost = self.cost * turnover.fillna(0.0)",
     "tests/test_costs_are_charged_when_the_trade_happens.py"),

    ("포트폴리오 백테스트에서 거래비용을 통째로 뺀다(오디션이 비용을 무시)",
     "quant/portfolio/backtest.py",
     "        port_ret = (port_ret_gross - cost).rename(\"returns\")",
     "        port_ret = port_ret_gross.rename(\"returns\")",
     "tests/test_costs_are_charged_when_the_trade_happens.py"),

    # 감사 154 — 이벤트 달력이 조용히 만료된다.
    ("추정 일정을 빼서 달력을 공표분에서 끊는다(2027년 뒤 가드가 영구 정지)",
     "quant/events.py",
     "    for y in range(PUBLISHED_END_YEAR + 1, end + 1):",
     "    for y in []:",
     "tests/test_the_event_calendar_does_not_expire_silently.py"),

    ("공표 끝을 목록이 아니라 손으로 적은 값으로 되돌린다(목록과 어긋난다)",
     "quant/events.py",
     "PUBLISHED_END = date.fromisoformat(max(FOMC_DATES))",
     "PUBLISHED_END = date(2027, 12, 31)",
     "tests/test_the_event_calendar_does_not_expire_silently.py"),

    ("추정 일정도 공표와 같은 좁은 패딩으로 가린다(며칠 어긋나면 그냥 뚫린다)",
     "quant/events.py",
     "ESTIMATED_PAD_DAYS = 3",
     "ESTIMATED_PAD_DAYS = 1",
     "tests/test_the_event_calendar_does_not_expire_silently.py"),

    ("추정으로 판단했다는 사실을 판단문에서 지운다(근거의 급이 안 보인다)",
     "quant/strategies/event_guard.py",
     "                projected = is_projected_day(last) if last else False",
     "                projected = False",
     "tests/test_the_event_calendar_does_not_expire_silently.py"),

    ("마이너 달력의 끝을 오늘이 아니라 공표 끝에 묶는다(옵션만기 가드가 먼저 꺼진다)",
     "quant/events.py",
     "    end_year = _horizon() if end_year is None else int(end_year)",
     "    end_year = PUBLISHED_END_YEAR if end_year is None else int(end_year)",
     "tests/test_the_event_calendar_does_not_expire_silently.py"),

    # 감사 156 — CPCV(조합 퍼지 교차검증). 챔피언을 뽑는 자리.
    ("CPCV 검증에 미래 데이터를 준다(경로 성적이 룩어헤드로 부풀어 오름)",
     "quant/optimize/cpcv.py",
     "                             periods_per_year=periods_per_year).run(df.iloc[:hi])",
     "                             periods_per_year=periods_per_year).run(df)",
     "tests/test_cpcv_really_holds_out.py"),

    ("CPCV 엠바고를 없앤다(검증 구간과 맞닿은 학습 경계에서 정보가 샌다)",
     "quant/optimize/cpcv.py",
     "            if seg[0] > 0 and (seg[0] - 1) in test_idx:\n                lo += embargo",
     "            if False:\n                lo += embargo",
     "tests/test_cpcv_really_holds_out.py"),

    ("CPCV 경로 배정을 한 경로로 뭉갠다(분포가 사라져 과적합 탐지가 무의미)",
     "quant/optimize/cpcv.py",
     "            path_returns[occurrence[g]].append(grp_ret)",
     "            path_returns[0].append(grp_ret)",
     "tests/test_cpcv_really_holds_out.py"),

    ("CPCV 목적함수 방향을 무시한다(작을수록 좋은 지표를 크게 고른다)",
     "quant/optimize/cpcv.py",
     "        sign = -1.0 if objective in LOWER_IS_BETTER else 1.0",
     "        sign = 1.0",
     "tests/test_cpcv_really_holds_out.py"),

    # 감사 157 — '외딴 봉우리' 판정이 사람에게 닿는가.
    ("견고성 1등 대신 원점수 1등을 고른다(외딴 봉우리를 그대로 승인)",
     "quant/optimize/stability.py",
     "        if sign * v > best_val:",
     "        if False:",
     "tests/test_the_lonely_peak_warning_reaches_someone.py"),

    ("이웃 점수를 안 모은다(모든 조합이 자기 점수만 보고 고원이 된다)",
     "quant/optimize/stability.py",
     "                    if key in index and math.isfinite(index[key]):\n                        neigh.append(index[key])",
     "                    if False:\n                        neigh.append(index[key])",
     "tests/test_the_lonely_peak_warning_reaches_someone.py"),

    ("외딴 봉우리 판정을 장부에서 지운다(콘솔에만 찍히고 사라진다)",
     "quant/cli.py",
     '            "peak_only": peak_only,',
     '            "peak_only": None,',
     "tests/test_the_lonely_peak_warning_reaches_someone.py"),

    ("외딴 봉우리 경보를 끈다(장부에 남아도 아무도 안 읽는다)",
     "quant/live/flag_watch.py",
     '        if r.get("peak_only"):',
     "        if False:",
     "tests/test_the_lonely_peak_warning_reaches_someone.py"),

    # 감사 158 — 민감도 히트맵(고원 vs 봉우리를 눈으로 보는 도구).
    ("히트맵 축을 뒤바꾼다(x·y 라벨이 실제 파라미터와 어긋난다)",
     "quant/optimize/sweep.py",
     "            params = {**base, x_param: x, y_param: y}",
     "            params = {**base, x_param: y, y_param: x}",
     "tests/test_the_heatmap_axes_do_not_lie.py"),

    ("히트맵 격자의 행·열을 뒤집는다(전치된 그림을 보고 파라미터를 고른다)",
     "quant/optimize/sweep.py",
     "            grid[i][j] = float(getattr(res.metrics, objective))",
     "            grid[j][i] = float(getattr(res.metrics, objective))",
     "tests/test_the_heatmap_axes_do_not_lie.py"),

    ("잘못된 조합을 0점으로 채운다(빈칸이 '성과 0'인 유효 조합처럼 보인다)",
     "quant/optimize/sweep.py",
     "            except (ValueError, TypeError):\n                continue",
     "            except (ValueError, TypeError):\n                grid[i][j] = 0.0\n                continue",
     "tests/test_the_heatmap_axes_do_not_lie.py"),

    ("튜닝 진입점이 워크포워드를 안 거치게 한다(전체 데이터로 튜닝 = 룩어헤드)",
     "quant/optimize/tuning.py",
     "    result = walk_forward(df, strategy_cls, param_grid, is_window, oos_window, **kwargs)",
     "    from quant.optimize.grid import grid_search\n"
     "    gs = grid_search(df, strategy_cls, param_grid)\n"
     "    result = {\"oos_metrics\": gs[\"best_metrics\"], \"segments\": [], \"equity\": None}",
     "tests/test_the_heatmap_axes_do_not_lie.py"),

    # 감사 159 — 문턱 하나로 두 질문을 재고 있었다.
    ("몬테카를로 샤프의 퇴화 판정을 되돌린다(상수 계열이 샤프 8e12)",
     "quant/robustness/monte_carlo.py",
     "        sharpe[i] = (0.0 if degenerate_spread(std, np.abs(sample).mean())\n"
     "                     else sample.mean() / std * np.sqrt(periods_per_year))",
     "        sharpe[i] = sample.mean() / std * np.sqrt(periods_per_year) if std > 0 else 0.0",
     "tests/test_two_thresholds_two_questions.py"),

    ("샤프 문턱을 잡음 문턱으로 되돌린다(예금형 계열이 간발의 차로 통과)",
     "quant/utils/numerics.py",
     "SHARPE_REL_EPS = 1e-6",
     "SHARPE_REL_EPS = 1e-12",
     "tests/test_two_thresholds_two_questions.py"),

    ("잡음 문턱을 샤프 문턱까지 올린다(조용한 자산이 배분에서 지워진다)",
     "quant/utils/numerics.py",
     "REL_EPS = 1e-12",
     "REL_EPS = 1e-6",
     "tests/test_two_thresholds_two_questions.py"),

    # 감사 160 — 과대확신을 한쪽에서만 봤다.
    ("과대확신을 상승 쪽에서만 본다(하락 쪽 과대확신이 조용히 통과)",
     "quant/robustness/calibration.py",
     '        gap = (r["mean_prob"] - r["frac_positive"] if r["mean_prob"] >= 0.5\n'
     '               else r["frac_positive"] - r["mean_prob"])',
     '        gap = (r["mean_prob"] - r["frac_positive"]\n'
     '               if r["mean_prob"] > 0.5 else -1.0)',
     "tests/test_overconfidence_has_two_directions.py"),

    ("과대확신 문턱을 없앤다(잘 보정된 모델까지 매일 경보)",
     "quant/robustness/calibration.py",
     "        if gap > 0.1:",
     "        if gap > -1.0:",
     "tests/test_overconfidence_has_two_directions.py"),

    ("브라이어 점수의 제곱을 뺀다(오차 방향이 상쇄돼 나쁜 모델이 좋아 보인다)",
     "quant/robustness/calibration.py",
     "    return sum((p - t) ** 2 for t, p in pairs) / len(pairs)",
     "    return sum((p - t) for t, p in pairs) / len(pairs)",
     "tests/test_overconfidence_has_two_directions.py"),

    # 감사 161 — 무결성 관문이 체결에 쓰는 값을 안 봤다.
    ("OHLC 밴드 검사에서 시가를 뺀다(체결가가 오염돼도 관문을 통과)",
     "quant/data/quality.py",
     '        for col in ("open", "close"):',
     '        for col in ("close",):',
     "tests/test_the_integrity_gate_checks_the_fill_price.py"),

    ("밴드 하한 검사를 뺀다(가격이 아래로 튀는 오염을 놓친다)",
     "quant/data/quality.py",
     '                bad = bad | (df[col] > df["high"]) | (df[col] < df["low"])',
     '                bad = bad | (df[col] > df["high"])',
     "tests/test_the_integrity_gate_checks_the_fill_price.py"),

    ("OHLC 모순을 무결성 위반 목록에서 뺀다(깨진 데이터로 그대로 매매)",
     "quant/data/quality.py",
     'SEVERE_KEYS = ("duplicate_index", "nonpositive_price", "ohlc_violations")',
     'SEVERE_KEYS = ("duplicate_index", "nonpositive_price")',
     "tests/test_the_integrity_gate_checks_the_fill_price.py"),

    # 감사 162 — 캐시를 켜면 데이터가 조용히 달라졌다.
    ("잘린 캐시를 온전한 것처럼 내준다(3개월 묵은 봉이 '오늘'이 된다)",
     "quant/data/cache.py",
     "                rows = meta.get(\"rows\")\n"
     "                if rows is not None and int(rows) != len(df):",
     "                rows = meta.get(\"rows\")\n"
     "                if False:",
     "tests/test_the_cache_is_transparent.py"),

    ("캐시 저장 시 봉 수를 안 남긴다(잘린 것을 대조할 근거가 없어진다)",
     "quant/data/cache.py",
     '        payload = {"attrs": dict(df.attrs), "rows": int(len(df))}',
     '        payload = {"attrs": dict(df.attrs)}',
     "tests/test_the_cache_is_transparent.py"),

    ("CSV를 다시 비원자적으로 쓴다(쓰다 죽으면 반쪽 파일이 남는다)",
     "quant/data/cache.py",
     "            self._atomic_write(path, df.to_csv())",
     "            df.to_csv(path)",
     "tests/test_the_cache_is_transparent.py"),

    ("캐시가 출처(attrs)를 안 싣는다(무조정가로 받은 사실이 사라진다)",
     "quant/data/cache.py",
     '                df.attrs.update(meta.get("attrs") or {})',
     "                pass",
     "tests/test_the_cache_is_transparent.py"),

    ("캐시 왕복 정확도를 포기한다(같은 데이터인데 값이 1.4e-14 달라진다)",
     "quant/data/cache.py",
     '                df = pd.read_csv(path, index_col=0, parse_dates=True,\n'
     '                                 float_precision="round_trip")',
     "                df = pd.read_csv(path, index_col=0, parse_dates=True)",
     "tests/test_the_cache_is_transparent.py"),

    ("오래된 캐시를 지울 때 메타를 안 지운다(짝 잃은 JSON이 무한히 쌓인다)",
     "quant/data/cache.py",
     "                self._meta_path(p).unlink(missing_ok=True)    # 짝도 함께",
     "                pass",
     "tests/test_the_cache_is_transparent.py"),

    # 감사 163 — 검증이 비운 프레임을 '성공'이라고 했다.
    ("거래량이 없다고 가격 봉을 통째로 지운다(지수·환율 계열이 0봉이 된다)",
     "quant/data/base.py",
     "        return df.dropna(subset=PRICE_COLUMNS)",
     "        return df.dropna()",
     "tests/test_an_empty_result_is_not_a_success.py"),

    ("주식: 검증 후 빈 결과를 성공으로 반환한다(보조 소스 2개를 건너뛴다)",
     "quant/data/stock.py",
     '                if out.empty:\n'
     '                    raise ValueError("검증 후 빈 결과")',
     "                if False:\n"
     "                    pass",
     "tests/test_an_empty_result_is_not_a_success.py"),

    ("코인: 검증 후 빈 결과를 성공으로 반환한다(보조 거래소를 건너뛴다)",
     "quant/data/crypto.py",
     '        if out.empty:\n'
     '            raise ValueError("검증 후 빈 결과")',
     "        if False:\n"
     "            pass",
     "tests/test_an_empty_result_is_not_a_success.py"),

    ("야후 HTTP 소스에서 거래량 결측으로 봉을 지운다",
     "quant/data/stock.py",
     "        ).dropna(subset=_PRICE_COLS)   # 거래량 결측으로 봉을 지우지 않는다(감사 163)",
     "        ).dropna()",
     "tests/test_an_empty_result_is_not_a_success.py"),

    ("stooq 소스에서 거래량 결측으로 봉을 지운다",
     "quant/data/stock.py",
     "        df = df[[\"open\", \"high\", \"low\", \"close\", \"volume\"]].dropna(\n"
     "            subset=_PRICE_COLS)        # 거래량 결측으로 봉을 지우지 않는다(감사 163)",
     '        df = df[["open", "high", "low", "close", "volume"]].dropna()',
     "tests/test_an_empty_result_is_not_a_success.py"),

    ("결측 거래량을 품질 보고서에서 안 센다(거래량 없는 계열이 안 보인다)",
     "quant/data/quality.py",
     '        findings["zero_volume"] = int((vol.isna() | (vol <= 0)).sum())',
     '        findings["zero_volume"] = int((vol <= 0).sum())',
     "tests/test_an_empty_result_is_not_a_success.py"),

    # 감사 164 — 눈금에 딱 맞는 수량이 한 칸 깎여 나갔다.
    ("눈금에 붙은 수량을 그대로 내림한다(0.3개 청산이 0.2개만 나간다)",
     "quant/broker/specs.py",
     "            nearest = round(n)\n"
     "            if math.isclose(n, nearest, rel_tol=1e-9, abs_tol=1e-9):\n"
     "                n = nearest",
     "            nearest = round(n)\n"
     "            if False:\n"
     "                n = nearest",
     "tests/test_the_order_quantity_survives_rounding.py"),

    ("1 이상인 수량 단위를 '제약 없음'으로 버린다(정수 단위 시장이 거절당한다)",
     "quant/broker/specs.py",
     "    if mode == TICK_SIZE:\n"
     "        return float(prec) if prec > 0 else 0.0",
     "    if mode == TICK_SIZE:\n"
     "        return float(prec) if 0 < prec < 1 else 0.0",
     "tests/test_the_order_quantity_survives_rounding.py"),

    ("거래소 precision 모드를 무시하고 값만 보고 추측한다",
     "quant/broker/specs.py",
     '        qty_step=_step(precision.get("amount"), precision_mode),',
     '        qty_step=_step(precision.get("amount")),',
     "tests/test_the_order_quantity_survives_rounding.py"),

    # (crypto_live의 규격 조회 줄은 "코인 어댑터가 규격을 안 알려 준다"가 이미
    #  덮고 있다. 같은 줄에 두 항목을 두지 않는다 — _assert_no_duplicates.
    #  모드를 안 넘기는 경우는 specs 쪽 '추측한다' 항목이 행동으로 잡는다.)

    ("딱 최소금액인 주문을 부동소수 오차로 거절한다",
     "quant/broker/specs.py",
     "        if self.min_notional > 0 and qty * price < self.min_notional * (1 - 1e-9):",
     "        if self.min_notional > 0 and qty * price < self.min_notional:",
     "tests/test_the_order_quantity_survives_rounding.py"),

    # 감사 165 — 종목 선별이 근거 없이 흔들렸다.
    ("결측 팩터를 '딱 평균'으로 채운다(자료 부실한 종목이 상을 받는다)",
     "quant/data/fundamentals.py",
     "    score = Z.mean(axis=1).where(have >= need).dropna()",
     "    score = Z.fillna(0.0).mean(axis=1)",
     "tests/test_the_screener_does_not_reward_missing_data.py"),

    ("팩터 최소 보유 개수를 없앤다(팩터 하나만 있어도 후보가 된다)",
     "quant/data/fundamentals.py",
     "    need = max(1, math.ceil(len(Z.columns) * MIN_FACTOR_COVERAGE))",
     "    need = 1",
     "tests/test_the_screener_does_not_reward_missing_data.py"),

    ("잡음 수준의 팩터를 진짜 신호처럼 쓴다(의미 없는 열이 선택을 지운다)",
     "quant/data/fundamentals.py",
     "        if not np.isfinite(std) or degenerate_spread(\n"
     "                std, float(col.abs().mean())):",
     "        if not np.isfinite(std) or std == 0:",
     "tests/test_the_screener_does_not_reward_missing_data.py"),

    ("동점을 입력 순서로 가른다(목록 순서만 바꿔도 다른 종목을 산다)",
     "quant/data/fundamentals.py",
     "    order = sorted(score.index, key=lambda s: (-float(score[s]), str(s)))",
     "    order = list(score.sort_values(ascending=False).index)",
     "tests/test_the_screener_does_not_reward_missing_data.py"),

    # 감사 166 — 상위 시간봉 게이트가 한 봉이 아니라 두 봉을 기다렸다.
    ("상위 시간봉 라벨을 pandas 기본값에 맡긴다(규칙마다 지연이 달라진다)",
     "quant/strategies/multitimeframe.py",
     '        htf_close = (close.resample(self.htf, label="right", closed="right")\n'
     "                     .last().dropna())",
     "        htf_close = close.resample(self.htf).last().dropna()",
     "tests/test_the_higher_timeframe_gate_waits_exactly_one_bar.py"),

    ("완성 라벨에 shift를 더 건다(새 추세마다 상위 봉 하나를 더 쉰다)",
     "quant/strategies/multitimeframe.py",
     "        up = (htf_close > htf_ma).astype(float)\n"
     '        return up.reindex(close.index, method="ffill").fillna(0.0)',
     "        up = (htf_close > htf_ma).astype(float).shift(1)\n"
     '        return up.reindex(close.index, method="ffill").fillna(0.0)',
     "tests/test_the_higher_timeframe_gate_waits_exactly_one_bar.py"),

    # 감사 167 — 망가진 숫자가 그대로 주문이 됐다.
    ("주문 직전 유한성 검사를 없앤다(NaN 수량이 조용히 매도로 나간다)",
     "quant/broker/base.py",
     "        if not all(math.isfinite(v) for v in\n"
     "                   (float(weight), float(price), float(equity))):\n"
     "            return None",
     "        if False:\n"
     "            return None",
     "tests/test_a_broken_number_cannot_become_an_order.py"),

    ("계산 결과 수량의 유한성 검사를 없앤다(나눗셈이 넘쳐도 그대로 전송)",
     "quant/broker/base.py",
     "        if not math.isfinite(qty) or qty <= 0:\n"
     "            return None",
     "        if False:\n"
     "            return None",
     "tests/test_a_broken_number_cannot_become_an_order.py"),

    ("웹훅 시세 헬퍼의 값을 안 거른다(헬퍼가 NaN을 주면 그대로 주문가가 된다)",
     "quant/live/webhook.py",
     "                p = float(self.price_fn(symbol))\n"
     "                return p if p > 0 else 0.0",
     "                return float(self.price_fn(symbol))",
     "tests/test_a_broken_number_cannot_become_an_order.py"),

    # 감사 168 — 보합 봉이 '틀린 예측'으로 채점됐다.
    ("보합 봉을 오답으로 채점한다(맞출 방향이 없던 봉을 틀렸다고 한다)",
     "quant/robustness/accuracy.py",
     "    moved = ret_next != 0\n"
     "    active = held & moved",
     "    moved = ret_next.notna()\n"
     "    active = held & moved",
     "tests/test_a_flat_bar_is_not_a_wrong_guess.py"),

    ("채점에서 뺀 보합 봉 수를 안 돌려준다(뺀 사실이 안 보인다)",
     "quant/robustness/accuracy.py",
     '                 "n_flat": int((held & ~moved).sum()),\n',
     "",
     "tests/test_a_flat_bar_is_not_a_wrong_guess.py"),

    ("장부에 보합 제외 봉 수를 안 남긴다",
     "quant/live/daily.py",
     '        "hit_flat": acc.get("n_flat"),',
     "",
     "tests/test_a_flat_bar_is_not_a_wrong_guess.py"),

    # 감사 169 — 전략 신호기 8종. 결함은 못 찾았고, 계약을 고정한다.
    # (이 파일들에는 변이 항목이 한 건도 없었다 — 부등호를 뒤집어도 초록이었다.)
    ("이동평균 교차의 롱 조건을 뒤집는다",
     "quant/strategies/moving_average.py",
     "        signal[fast_ma > slow_ma] = 1.0",
     "        signal[fast_ma < slow_ma] = 1.0",
     "tests/test_every_strategy_obeys_its_own_rule.py"),

    ("모멘텀의 진입 방향을 뒤집는다",
     "quant/strategies/momentum.py",
     "        signal[past_return > self.threshold] = 1.0",
     "        signal[past_return < self.threshold] = 1.0",
     "tests/test_every_strategy_obeys_its_own_rule.py"),

    ("MACD가 신호선 대신 0선을 본다(규칙이 통째로 달라진다)",
     "quant/strategies/macd.py",
     "        out[macd_line > signal_line] = 1.0",
     "        out[macd_line > 0] = 1.0",
     "tests/test_every_strategy_obeys_its_own_rule.py"),

    ("돌파 채널에서 shift를 뺀다(그 봉 자신의 고가로 돌파를 판정)",
     "quant/strategies/breakout.py",
     '        upper = df["high"].rolling(self.window).max().shift(1).to_numpy()',
     '        upper = df["high"].rolling(self.window).max().to_numpy()',
     "tests/test_every_strategy_obeys_its_own_rule.py"),

    ("평균회귀가 상단 밴드에서 매수한다(방향을 뒤집는다)",
     "quant/strategies/mean_reversion.py",
     "                if c[i] < lo[i]:",
     "                if c[i] > lo[i]:",
     "tests/test_every_strategy_obeys_its_own_rule.py"),

    ("RSI 과매도 진입 문턱을 없앤다(아무 때나 진입)",
     "quant/strategies/rsi.py",
     "                if v < self.oversold:",
     "                if v < 100:",
     "tests/test_every_strategy_obeys_its_own_rule.py"),

    ("스토캐스틱의 롱 청산을 없앤다(한 번 사면 안 판다)",
     "quant/strategies/stochastic.py",
     "            elif pos > 0 and v >= 50:      # 롱: 중심선 복귀 시 청산",
     "            elif pos > 0 and v >= 1e9:     # 롱: 중심선 복귀 시 청산",
     "tests/test_every_strategy_obeys_its_own_rule.py"),

    ("켈트너 상단 돌파 조건을 뒤집는다",
     "quant/strategies/keltner.py",
     '        signal[df["close"] > upper] = 1.0',
     '        signal[df["close"] < upper] = 1.0',
     "tests/test_every_strategy_obeys_its_own_rule.py"),

    ("숏 금지를 무시한다(롱 온리 계정에 숏이 나간다)",
     "quant/strategies/base.py",
     "        if not self.allow_short:\n"
     "            signal = signal.clip(lower=0.0)",
     "        if False:\n"
     "            signal = signal.clip(lower=0.0)",
     "tests/test_every_strategy_obeys_its_own_rule.py"),

    # 감사 170 — 리다이렉트 한 번에 실거래 키가 평문으로 나갔다.
    ("리다이렉트에서 호스트만 보고 스킴 강등을 놓친다(https→http에 키가 따라간다)",
     "quant/utils/http.py",
     '            downgrade = old.scheme == "https" and nxt.scheme != "https"\n'
     "            if old.netloc != nxt.netloc or downgrade:",
     "            if old.netloc != nxt.netloc:",
     "tests/test_credentials_do_not_leak_over_http.py"),

    ("교차 호스트 리다이렉트에서 인증 헤더를 안 뗀다(키가 남의 서버로 간다)",
     "quant/utils/http.py",
     "                for h in [k for k in new.headers if k.lower() in _SENSITIVE_HEADERS]:\n"
     "                    del new.headers[h]",
     "                pass",
     "tests/test_credentials_do_not_leak_over_http.py"),

    ("오류 본문을 안 가린다(서버가 되울린 URL로 키가 로그에 남는다)",
     "quant/utils/http.py",
     '        detail = _redact_url(exc.read().decode(errors="replace")[:2000])',
     '        detail = exc.read().decode(errors="replace")[:2000]',
     "tests/test_credentials_do_not_leak_over_http.py"),

    # 감사 264 — 사용자 자료에서 **못 옮긴 규칙을 말하지 않던** 자리.
    # 실측: "손절 -8%, 익절 +20%"가 언급조차 없이 사라졌다.
    ("못 옮긴 규칙을 조용히 버린다(사용자는 전부 반영된 줄 안다)",
     "quant/ingest/extract.py",
     "    unread = [s for s in sentences if s not in used and _RULEISH.match(s)]",
     "    unread = []",
     "tests/test_only_real_rules_become_strategies.py"),
    ("'뚫다'를 못 읽는다(매도 규칙만 조용히 사라진다)",
     "quant/ingest/extract.py",
     'rf"위로\\s*(?:돌파|뚫)|아래로\\s*(?:돌파|뚫)|"',
     'rf"위로\\s*돌파|아래로\\s*돌파|"',
     "tests/test_only_real_rules_become_strategies.py"),
    # 감사 263 — 실제로 돈이 나가는 경로에 킬스위치·검증 게이트가 없던 자리.
    # 실측: run_daily_live는 어드민 노출 배수만 곱하고 있었다.
    ("킬스위치가 실거래 노출에 안 걸린다(낙폭이 깊어도 그대로 산다)",
     "quant/live/daily_live.py",
     "    eff_exposure = exposure * risk_scale",
     "    eff_exposure = exposure",
     "tests/test_the_real_money_path_has_the_same_brakes.py"),
    ("검증 게이트가 실거래 비중에 안 곱해진다(미측정 종목을 전액으로 산다)",
     "quant/live/daily_live.py",
     '            weight *= valid_damp.get(f"{market}:{symbol}", 1.0)',
     "            pass",
     "tests/test_the_real_money_path_has_the_same_brakes.py"),
    ("실거래 장부가 계좌 자산을 안 남긴다(낙폭을 잴 재료가 사라진다)",
     "quant/live/daily_live.py",
     '               "equity": round(account_equity, 2) if account_equity else None,',
     '               "equity": None,',
     "tests/test_the_real_money_path_has_the_same_brakes.py"),
    ("한 종목 조회 실패가 계좌 자산 전체를 0으로 만든다(없던 폭락)",
     "quant/live/daily_live.py",
     "        except Exception:  # noqa: BLE001 — 한 종목 조회 실패로 자산을 왜곡하지 않는다",
     "        except Exception:  # noqa: BLE001\n            return 0.0",
     "tests/test_the_real_money_path_has_the_same_brakes.py"),
    ("검증 게이트가 고장나면 감쇠 없이 통과시킨다(고장난 날 가장 공격적)",
     "quant/live/daily_live.py",
     "        return dict.fromkeys(keys, 0.5)",
     "        return dict.fromkeys(keys, 1.0)",
     "tests/test_the_real_money_path_has_the_same_brakes.py"),
    # 감사 262 — 장중 감시가 예약대로 안 도는 것을 아무도 안 읽던 자리.
    # 실측: 예약 15분 / 관측 최악 간격 558분(2026-08-16 심장박동).
    ("감시가 몇 시간 멈춰도 알림이 안 나간다(문서는 계속 15분이라 말한다)",
     "quant/live/flag_watch.py",
     "        if gap is not None and interval > 0 and gap > limit:",
     "        if False:",
     "tests/test_the_guard_admits_how_often_it_actually_ran.py"),
    ("지각 문턱이 실제 사고(558분)를 놓친다",
     "quant/live/guard.py",
     "GUARD_LATE_FACTOR = 4.0",
     "GUARD_LATE_FACTOR = 100.0",
     "tests/test_the_guard_admits_how_often_it_actually_ran.py"),
    ("예약 주기가 워크플로와 갈라져도 아무도 모른다",
     "quant/live/guard.py",
     "GUARD_INTERVAL_MINUTES = 15",
     "GUARD_INTERVAL_MINUTES = 60",
     "tests/test_the_guard_admits_how_often_it_actually_ran.py"),
    ("status에 감시 실측을 안 싣는다(판정할 재료가 사라진다)",
     "quant/live/daily.py",
     '            status["guard"] = {"observed_gap_min": round(float(_gap), 1),',
     '            status["_guard_unused"] = {"observed_gap_min": round(float(_gap), 1),',
     "tests/test_the_guard_admits_how_often_it_actually_ran.py"),
    # 감사 261 — 몇 봉으로 판단했는지를 장부가 말하지 않던 자리.
    # 실측: 코인 5종목이 800봉 요청에 300봉 수신(2026-08-15 스냅샷).
    ("표본이 모자라도 장부에 안 남는다(300봉짜리 결론이 800봉으로 읽힌다)",
     "quant/live/daily.py",
     "            if got < int(lookback * BARS_SHORTFALL_RATIO):",
     "            if False:",
     "tests/test_the_ledger_says_how_many_bars_it_judged_on.py"),
    ("표본 부족 문턱이 실제 사고(800→300)를 놓친다",
     "quant/live/daily.py",
     "BARS_SHORTFALL_RATIO = 0.9",
     "BARS_SHORTFALL_RATIO = 0.3",
     "tests/test_the_ledger_says_how_many_bars_it_judged_on.py"),
    ("표본 부족이 알림으로 안 나간다(또 몇 주 동안 안 보인다)",
     "quant/live/flag_watch.py",
     '        bs = last.get("bars_short") or {}',
     "        bs = {}",
     "tests/test_the_ledger_says_how_many_bars_it_judged_on.py"),
    ("가장 심한 종목이 아니라 아무거나 예로 든다(심각도가 가려진다)",
     "quant/live/flag_watch.py",
     '            worst = min(bs.items(), key=lambda kv: kv[1]["got"] / kv[1]["asked"])',
     "            worst = max(bs.items(), key=lambda kv: kv[1][\"got\"] / kv[1][\"asked\"])",
     "tests/test_the_ledger_says_how_many_bars_it_judged_on.py"),
    # 감사 260 — 배치가 만든 기록에 아무 검사도 안 걸리던 자리.
    # 실측: 2026-08-15 +7,150% 기록이 [skip actions] 구멍으로 반나절 생존.
    ("장부 관문이 실패를 삼킨다(오염된 기록이 그대로 커밋된다)",
     ".github/workflows/daily-paper.yml",
     "          python scripts/ledger_gate.py",
     "          python scripts/ledger_gate.py || true",
     "tests/test_the_batch_checks_what_it_just_wrote.py"),
    ("장부 오류와 검사기 고장을 같은 문구로 말한다(엉뚱한 곳을 뒤지게 된다)",
     "scripts/ledger_gate.py",
     "    if rc == _PYTEST_FAILED:",
     "    if True:",
     "tests/test_the_batch_checks_what_it_just_wrote.py"),
    ("검사가 0개 수집돼도 '못 돌았다'로 안 본다(이름만 바뀌어도 관문이 사라진다)",
     "scripts/ledger_gate.py",
     '_PYTEST_CANT_RUN = {2: "중단됨", 3: "내부 오류", 4: "사용법 오류",\n                    5: "검사가 하나도 수집되지 않음"}',
     '_PYTEST_CANT_RUN = {2: "중단됨", 3: "내부 오류", 4: "사용법 오류"}',
     "tests/test_the_batch_checks_what_it_just_wrote.py"),
    ("검사 파일이 없어도 장부 관문이 초록을 준다",
     "scripts/ledger_gate.py",
     "    if missing:",
     "    if False:",
     "tests/test_the_batch_checks_what_it_just_wrote.py"),
    ("현금 부족 거부가 알림으로 안 나간다(사고의 첫 신호를 아무도 못 본다)",
     "quant/live/flag_watch.py",
     '        cs = last.get("cash_short") or []',
     "        cs = []",
     "tests/test_the_batch_checks_what_it_just_wrote.py"),
    ("자릿수 불일치로 거부된 체결이 알림으로 안 나간다",
     "quant/live/flag_watch.py",
     '        fr = last.get("fill_refused") or {}',
     "        fr = {}",
     "tests/test_the_batch_checks_what_it_just_wrote.py"),
    # 감사 254 — 통합 계좌가 달러로 사고 원화로 평가하던 자리.
    # 실측: 2026-08-15 META 596.98(달러)에 체결 → 832,868(원)로 평가 →
    #       100만원 계좌의 자산이 7,249만원(+7,150%)으로 기록됨.
    ("대기 주문 체결가를 환산 없이 담는다(달러로 사서 원화로 평가한다)",
     "quant/live/daily.py",
     "                    (fbar, _to_krw_or_die(market, fopen, fx_rate))",
     "                    (fbar, fopen)",
     "tests/test_one_account_cannot_hold_two_currencies.py"),
    ("환율을 모를 때 1.0으로 때운다(감사 212가 고친 결함이 되돌아온다)",
     "quant/live/daily.py",
     '    krw = to_krw(market, float(price), fx_rate)\n    if krw is None:',
     '    krw = to_krw(market, float(price), fx_rate)\n    if False:',
     "tests/test_one_account_cannot_hold_two_currencies.py"),
    ("자릿수가 안 맞는 체결을 그냥 통과시킨다(환산이 또 빠져도 안 막힌다)",
     "quant/live/daily.py",
     "FILL_MARK_MAX_RATIO = 5.0",
     "FILL_MARK_MAX_RATIO = 1e9",
     "tests/test_one_account_cannot_hold_two_currencies.py"),
    ("거부한 체결을 장부에 안 남긴다(이유 없이 덜 산 채로 굴러간다)",
     "quant/live/daily.py",
     '              "fill_refused": fill_refused or None,',
     '              "fill_refused": None,',
     "tests/test_one_account_cannot_hold_two_currencies.py"),
    # 감사 255 — 같은 설정을 20종목에 적용한 횡단면 증거. 실측: 주식 t=+4.37 /
    # 코인 t=-1.76 (종목별 오디션은 이 차이를 못 본다).
    ("횡단면에서 주식 종목을 통째로 빠뜨린다(20종목이 5종목으로 보인다)",
     "quant/live/crosssection.py",
     "            symbol = stem[len(market) + 1:]",
     "            symbol = stem.split(\"_\", 1)[1]",
     "tests/test_the_same_setting_is_judged_across_symbols.py"),
    ("표본 1개로도 t를 만든다(한 종목으로 통계를 지어낸다)",
     "quant/live/crosssection.py",
     "    if n >= 2:",
     "    if n >= 1:",
     "tests/test_the_same_setting_is_judged_across_symbols.py"),
    ("횡단면 숫자가 인샘플이라는 표식을 지운다(실전 성적으로 읽힌다)",
     "quant/live/crosssection.py",
     '        "in_sample": True,          # ⚠️ 이 값을 지우면 화면이 실전 성적으로 읽는다',
     '        "in_sample": False,',
     "tests/test_the_same_setting_is_judged_across_symbols.py"),
    ("반쪽만 찍힌 스냅샷 날을 그대로 쓴다(20종목이 5종목으로, 결론이 뒤집힌다)",
     "quant/utils/repro.py",
     "    return max(recent, key=lambda d: (\n"
     "        len([f for f in os.listdir(os.path.join(base, d))\n"
     '             if f.endswith(".csv.gz")]), d))',
     "    return recent[-1]",
     "tests/test_the_same_setting_is_judged_across_symbols.py"),

    ("횡단면 증거를 사이트에 안 실어 보낸다",
     "quant/live/daily.py",
     '            status["crosssection"] = xs',
     "            pass",
     "tests/test_the_same_setting_is_judged_across_symbols.py"),

    # 감사 252 — 환율 캐시가 안 늙어 장수 프로세스에서 얼어 있던 자리.
    # 실측: 1416.46을 받은 뒤 1500으로 움직여도 refresh=True가 1416.46 반환.
    ("환율 캐시가 늙지 않는다(며칠 도는 프로세스에서 환율이 얼어붙는다)",
     "quant/data/fx.py",
     "    fresh = (clock() - _MEMO_AT) < FX_TTL_SEC",
     "    fresh = True",
     "tests/test_the_exchange_rate_does_not_freeze.py"),
    ("환율을 다시 받아도 아래 메모가 옛 값을 준다(refresh가 이름뿐이 된다)",
     "quant/data/fx.py",
     '        s = _bench_close("us_stock", "KRW=X", limit=30, fetch=fetch,\n                         refresh=True)',
     '        s = _bench_close("us_stock", "KRW=X", limit=30, fetch=fetch)',
     "tests/test_the_exchange_rate_does_not_freeze.py"),
    ("벤치마크 메모가 refresh를 무시한다(위층이 무엇을 해도 옛 값)",
     "quant/data/crossasset.py",
     "    if refresh:\n        _MEMO.pop(key, None)",
     "    if False:\n        _MEMO.pop(key, None)",
     "tests/test_the_exchange_rate_does_not_freeze.py"),
    ("성공한 환율의 시각을 안 남긴다(캐시가 영원히 신선하다고 읽힌다)",
     "quant/data/fx.py",
     "    _MEMO_AT = clock()",
     "    pass",
     "tests/test_the_exchange_rate_does_not_freeze.py"),

    # 감사 251 — worker.js(336줄)에 변이 항목이 **0건**이던 자리. 발급·인증
    # 안전장치가 다 있는데, 그것을 지우는 변이를 아무도 잡아 본 적이 없었다.
    ("어드민 로그인이 꺼져 있어도 키를 발급한다(누구나 키를 찍는다)",
     "worker.js",
     "  if (!env.ADMIN_ID || !env.ADMIN_PW) {",
     "  if (false) {",
     "tests/worker_license_check.mjs"),
    ("어드민 문을 통째로 연다(시크릿 미설정을 '통과'로 읽는다)",
     "worker.js",
     "  if (!env.ADMIN_ID || !env.ADMIN_PW) return null;   // 시크릿 미설정 → 보호 없음",
     "  return null;",
     "tests/worker_license_check.mjs"),
    ("어드민 비밀번호를 확인하지 않는다(아이디만 맞으면 통과)",
     "worker.js",
     "          && dec.slice(i + 1) === env.ADMIN_PW) return null;",
     "          ) return null;",
     "tests/worker_license_check.mjs"),
    ("발급 시 소유자 정규화를 뺀다(대문자 이메일에 다른 키가 나간다)",
     "worker.js",
     '  const owner = (url.searchParams.get("owner") || "").trim().toLowerCase();',
     '  const owner = (url.searchParams.get("owner") || "");',
     "tests/worker_license_check.mjs"),
    ("키 자르는 길이를 바꾼다(발급한 키가 구매자 컴퓨터에서 전부 무효)",
     "worker.js",
     '  const key = "QUANT-" + b32(sig.slice(0, 15)).replace(/(.{6})(?=.)/g, "$1-");',
     '  const key = "QUANT-" + b32(sig.slice(0, 16)).replace(/(.{6})(?=.)/g, "$1-");',
     "tests/worker_license_check.mjs"),
    ("발급 응답을 교차출처로 연다(어드민 API에 와일드카드를 단다)",
     "worker.js",
     '  return json({ owner, key, fingerprint: "hmac:" + fp }, 200,\n              { "Cache-Control": "no-store" });',
     '  return json({ owner, key, fingerprint: "hmac:" + fp }, 200,\n              { "Cache-Control": "no-store" }, true);',
     "tests/worker_license_check.mjs"),

    # 감사 250 — 분석 도구가 합성 데이터 결과를 진짜처럼 보고하던 자리.
    # 실측: 네트워크 차단 환경에서 quant backtest가 "샤프 2.10 · 승률 57%"를
    # 지어낸 가격 위에서 출력했고, 본문에는 가짜라는 말이 없었다.
    ("분석 결과가 합성 데이터라는 사실을 안 밝힌다(지어낸 가격 위의 샤프가 진짜로 읽힌다)",
     "quant/cli.py",
     '    if bool(getattr(df, "attrs", {}).get("synthetic_fallback")):',
     "    if False:",
     "tests/test_the_analysis_says_what_data_it_ran_on.py"),
    ("백테스트가 어떤 데이터로 돌았는지 말하지 않는다",
     "quant/cli.py",
     "    print(_data_note(df, args.market))\n    from quant.data.quality import is_severe, quality_report, scan_ohlcv",
     "    from quant.data.quality import is_severe, quality_report, scan_ohlcv",
     "tests/test_the_analysis_says_what_data_it_ran_on.py"),
    ("손익분기 비용 분석이 어떤 데이터로 돌았는지 말하지 않는다",
     "quant/cli.py",
     '    print(f"\\n=== 손익분기 비용: {args.strategy} · {args.symbol} ({len(df)}봉) ===")\n    print(_data_note(df, args.market))',
     '    print(f"\\n=== 손익분기 비용: {args.strategy} · {args.symbol} ({len(df)}봉) ===")',
     "tests/test_the_analysis_says_what_data_it_ran_on.py"),
    ("연습용 모의 데이터를 실제 시세라고 말한다",
     "quant/cli.py",
     '    if market == "synthetic":',
     "    if False:",
     "tests/test_the_analysis_says_what_data_it_ran_on.py"),

    # 감사 249 — 못 돈 검증이 사이트에서 조용하던 자리. 실측: BTC/USDT는
    # DSR이 null(봉 300개)인데 PBO 경보만 떴다.
    ("돌지 못한 검증을 화면이 말하지 않는다(재지 못한 것이 통과로 읽힌다)",
     "quant/live/flag_watch.py",
     '        missing = [k for k in ("dsr", "pbo") if _unmeasured(k)]',
     "        missing = []",
     "tests/test_a_validation_that_did_not_run_is_not_a_pass.py"),
    ("0.0을 '못 쟀다'로 읽는다(측정된 0이 판정 불가로 둔갑)",
     "quant/live/flag_watch.py",
     "            return _r.get(k) is None        # 0.0은 '못 쟀다'가 아니라 '측정된 0'",
     "            return not _r.get(k)",
     "tests/test_a_validation_that_did_not_run_is_not_a_pass.py"),
    ("검증이 건너뛴 이유를 장부에 안 남긴다(사이트가 왜 없는지 모른다)",
     "quant/cli.py",
     '            "skipped": dict(skipped) or None,',
     '            "skipped": None,',
     "tests/test_a_validation_that_did_not_run_is_not_a_pass.py"),

    # 감사 248 — 가리개가 '?'·'&' 뒤에서만 작동하던 자리. 이 저장소는 토큰을
    # **본문(form)**으로 보내므로 되울린 본문의 토큰이 그대로 새어 나갔다.
    # 그 문자열은 docs/ 안의 posted.json에 쓰여 **공개 사이트로 배포된다.**
    ("비밀 가리개를 쿼리스트링에서만 작동하게 한다(본문에 실린 토큰이 그대로 샌다)",
     "quant/utils/http.py",
     '    r"(?i)(^|[?&\\s\\"\'{,\\[])((?:api[_-]?key|apikey|access[_-]?token|token|"',
     '    r"(?i)()([?&](?:api[_-]?key|apikey|access[_-]?token|token|"',
     "tests/test_a_secret_is_hidden_everywhere_not_just_in_urls.py"),
    ("공개되는 게시 결과 파일에 예외 원문을 그대로 붓는다",
     "quant/reporting/social_post.py",
     "    return redact_secrets(str(exc))[:limit]",
     "    return str(exc)",
     "tests/test_a_secret_is_hidden_everywhere_not_just_in_urls.py"),
    ("스레드 게시 실패 사유를 안 가리고 공개 파일에 적는다",
     "quant/reporting/social_post.py",
     '            results["threads_error"] = _safe_error(exc)',
     '            results["threads_error"] = str(exc)',
     "tests/test_a_secret_is_hidden_everywhere_not_just_in_urls.py"),

    ("상태 파일 임시 이름을 고정한다(두 프로세스가 같은 임시 파일을 밟는다)",
     "quant/utils/jsonio.py",
     '    tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")',
     '    tmp = p.with_name(p.name + ".tmp")',
     "tests/test_credentials_do_not_leak_over_http.py"),

    # 감사 171 — 앙상블·게이트·유틸 7파일. 결함 없음, 계약 고정.
    ("앙상블 손익 계산에서 지연을 뺀다(그 봉의 신호로 그 봉의 손익을 만든다)",
     "quant/strategies/ensemble.py",
     "        {i: sigs[i].shift(1).fillna(0.0) * rets for i in range(len(sigs))})",
     "        {i: sigs[i].fillna(0.0) * rets for i in range(len(sigs))})",
     "tests/test_the_wrappers_and_utils_keep_their_contracts.py"),

    ("롤링 HRP가 이번 봉까지 포함해 가중을 만든다(미래를 본다)",
     "quant/strategies/ensemble.py",
     "                pnl.iloc[i - lookback:i]).reindex(cols).fillna(0.0).values",
     "                pnl.iloc[i - lookback:i + 1]).reindex(cols).fillna(0.0).values",
     "tests/test_the_wrappers_and_utils_keep_their_contracts.py"),

    ("앙상블 가중치 정규화를 끈다(행 합이 1이 아니게 되어 숨은 레버리지)",
     "quant/strategies/ensemble.py",
     "    out = w.div(rs, axis=0)",
     "    out = w",
     "tests/test_the_wrappers_and_utils_keep_their_contracts.py"),

    ("ADX 게이트를 항상 열어 둔다(횡보장에서도 매매)",
     "quant/strategies/adx.py",
     "        allowed = (strength >= self.min_adx).astype(float)  # 추세 강할 때만 매매",
     "        allowed = (strength >= 0.0).astype(float)",
     "tests/test_the_wrappers_and_utils_keep_their_contracts.py"),

    ("유동성 게이트를 항상 열어 둔다(거래대금 미달 종목도 매매)",
     "quant/strategies/liquidity.py",
     "        allowed = (dollar_vol >= self.min_dollar_vol).astype(float)",
     "        allowed = (dollar_vol >= 0.0).astype(float)",
     "tests/test_the_wrappers_and_utils_keep_their_contracts.py"),

    ("스크리너가 재무를 못 받은 종목도 후보에 넣는다",
     "quant/portfolio/screener.py",
     "        if r:\n            ratios[sym] = r",
     "        ratios[sym] = r",
     "tests/test_the_wrappers_and_utils_keep_their_contracts.py"),

    (".env가 셸 환경변수를 덮어쓴다(직접 준 키가 파일 값으로 바뀐다)",
     "quant/utils/envfile.py",
     "        if override or k not in os.environ:",
     "        if True:",
     "tests/test_the_wrappers_and_utils_keep_their_contracts.py"),

    ("데이터 지문에서 행 수를 뺀다(행이 늘어도 같은 지문)",
     "quant/utils/manifest.py",
     "                       (index_first, index_last, int(n_rows),\n"
     "                        close_first, close_last))",
     "                       (index_first, index_last, close_first, close_last))",
     "tests/test_the_wrappers_and_utils_keep_their_contracts.py"),

    ("JSON 로그에서 컨텍스트 필드를 빠뜨린다(주문 추적 정보가 사라진다)",
     "quant/utils/logging.py",
     "        if isinstance(ctx, dict):\n            for k, v in ctx.items():",
     "        if False:\n            for k, v in ctx.items():",
     "tests/test_the_wrappers_and_utils_keep_their_contracts.py"),

    # 감사 172 — 이미지가 정상 공개된 순간 SNS 게시가 죽었다.
    ("이미지 공개 확인을 본문 디코드로 되돌린다(PNG를 받는 순간 게시가 죽는다)",
     "quant/reporting/social_post.py",
     "    from quant.utils.http import url_ok\n"
     "    fetch = http_get or (lambda u: url_ok(u, timeout=20))",
     "    from quant.utils.http import get_text\n"
     "    fetch = http_get or (lambda u: get_text(u, timeout=20))",
     "tests/test_the_image_check_does_not_kill_the_post.py"),

    ("공개 확인이 응답 코드를 안 본다(404도 '공개됨'으로 읽는다)",
     "quant/utils/http.py",
     "            return 200 <= int(getattr(resp, \"status\", 200) or 200) < 300",
     "            return True",
     "tests/test_the_image_check_does_not_kill_the_post.py"),

    ("첫 이미지만 확인하고 나머지를 건너뛴다(카드 8장 중 1장만 본다)",
     "quant/reporting/social_post.py",
     "        if not ok:\n"
     '            raise RuntimeError(f"이미지가 공개되지 않음(배포 지연/실패?): {u}")',
     "        if False:\n"
     '            raise RuntimeError(f"이미지가 공개되지 않음(배포 지연/실패?): {u}")',
     "tests/test_the_image_check_does_not_kill_the_post.py"),

    # 감사 173 — 붙이는 피처(펀딩·미결제·수급)의 시점 계약.
    ("수급 표준편차 0을 pd.NA로 바꾼다(astype(float)이 터져 수급 피처가 통째로 사라진다)",
     "quant/data/krx.py",
     "            sd = s5.rolling(60).std().replace(0.0, np.nan)",
     "            sd = s5.rolling(60).std().replace(0.0, pd.NA)",
     "tests/test_attached_features_cannot_see_the_future.py"),

    ("수급 z점수 클립을 없앤다(극단값이 사이징까지 흔든다)",
     "quant/data/krx.py",
     '            z = ((s5 - mu) / sd).astype(float).clip(-4.0, 4.0)',
     "            z = ((s5 - mu) / sd).astype(float)",
     "tests/test_attached_features_cannot_see_the_future.py"),

    ("미결제약정을 후진충전으로 붙인다(다음 값이 이번 봉에 실린다 = 룩어헤드)",
     "quant/data/openinterest.py",
     '        out["oi"] = pd.Series(s.reindex(target, method="ffill").to_numpy(),',
     '        out["oi"] = pd.Series(s.reindex(target, method="bfill").to_numpy(),',
     "tests/test_attached_features_cannot_see_the_future.py"),

    ("펀딩 정산을 봉 경계에서 한 칸 당긴다(그날 장중 정산이 그날 봉에 실린다)",
     "quant/data/funding.py",
     '    pos = bar_index.searchsorted(f.index, side="left")',
     '    pos = bar_index.searchsorted(f.index, side="right")',
     "tests/test_attached_features_cannot_see_the_future.py"),

    ("펀딩 값의 유한성 검사를 뺀다(NaN·inf가 비용 계열을 오염시킨다)",
     "quant/data/funding.py",
     "        if p < len(bar_index) and math.isfinite(float(v)):",
     "        if p < len(bar_index):",
     "tests/test_attached_features_cannot_see_the_future.py"),

    # 감사 174 — 감사 로그가 매매를 죽일 수 있었다.
    ("주문 감사 로그 실패를 좁게만 삼킨다(직렬화 오류가 배치를 죽인다)",
     "quant/live/journal.py",
     "    except Exception as exc:  # noqa: BLE001 — 감사 로그가 매매를 죽이면 안 된다",
     "    except OSError as exc:",
     "tests/test_the_audit_log_never_kills_the_batch.py"),

    ("망가진 줄을 만나면 감사 로그 읽기를 통째로 포기한다",
     "quant/live/journal.py",
     "        try:\n"
     "            out.append(json.loads(line))\n"
     "        except ValueError:\n"
     "            continue",
     "        out.append(json.loads(line))",
     "tests/test_the_audit_log_never_kills_the_batch.py"),

    ("복기가 표본 부족을 무시하고 통계를 낸다",
     "quant/live/journal.py",
     "    if len(rows) < 3:",
     "    if len(rows) < 0:",
     "tests/test_the_audit_log_never_kills_the_batch.py"),

    # 감사 175 — 보낼 곳이 없는데 '보냈다'로 기록됐다.
    ("바깥 채널이 없어도 전달 성공으로 본다(경보가 영원히 다시 안 온다)",
     "quant/live/notifications.py",
     '        if not any(getattr(n, "external", True) for n in self.notifiers):',
     "        if False:",
     "tests/test_an_alarm_with_nowhere_to_go_is_not_delivered.py"),

    ("콘솔을 '바깥으로 나가는 채널'로 표시한다",
     "quant/live/notifications.py",
     "    external = False\n\n    def send(self, message: str, level: str = \"info\") -> bool:",
     "    external = True\n\n    def send(self, message: str, level: str = \"info\") -> bool:",
     "tests/test_an_alarm_with_nowhere_to_go_is_not_delivered.py"),

    ("웹훅 URL을 오류 로그에서 안 가린다(토큰이 그대로 남는다)",
     "quant/live/notifications.py",
     "    return _URL_RE.sub(lambda m: f\"{m.group(1)}/…(redacted)\", str(exc))",
     "    return str(exc)",
     "tests/test_an_alarm_with_nowhere_to_go_is_not_delivered.py"),

    # 감사 176 — 아직 안 판 포지션이 '완결 거래'로 세어졌다.
    ("미청산 포지션을 완결 거래로 센다(평가손익이 승률·기대손익에 섞인다)",
     "quant/backtest/trades.py",
     "    closed = [t for t in trades if not getattr(t, \"is_open\", False)]",
     "    closed = list(trades)",
     "tests/test_an_open_position_is_not_a_finished_trade.py"),

    ("미청산 표시를 안 남긴다(무엇을 뺐는지 알 수 없다)",
     "quant/backtest/trades.py",
     "            is_open=bool(still_open),",
     "            is_open=False,",
     "tests/test_an_open_position_is_not_a_finished_trade.py"),

    ("복기 보고서가 뺀 거래를 말하지 않는다",
     "quant/live/journal.py",
     '    if review.get("num_open"):',
     "    if False:",
     "tests/test_an_open_position_is_not_a_finished_trade.py"),

    # 감사 177 — 탐색과 그림의 '좋다' 방향. 결함 없음, 계약 고정.
    ("목적함수 방향 집합을 비운다(작을수록 좋은 지표에서 최악을 최적으로 고른다)",
     "quant/objective.py",
     'LOWER_IS_BETTER = frozenset({"volatility"})',
     "LOWER_IS_BETTER = frozenset()",
     "tests/test_the_best_marker_points_at_the_best.py"),

    ("히트맵이 최고값을 방향과 무관하게 max로 고른다(★가 최악에 붙는다)",
     "quant/reporting/heatmap.py",
     "    best = (min(flat) if lower_better else max(flat)) if flat else None",
     "    best = max(flat) if flat else None",
     "tests/test_the_best_marker_points_at_the_best.py"),

    ("히트맵 색 방향 반전을 없앤다(나쁜 쪽이 초록으로 칠해진다)",
     "quant/reporting/heatmap.py",
     "    clo, chi = (hi, lo) if lower_better else (lo, hi)   # 색 방향 지정",
     "    clo, chi = (lo, hi)",
     "tests/test_the_best_marker_points_at_the_best.py"),

    ("탐색의 부호 반전을 없앤다(변동성 최소화가 최대화가 된다)",
     "quant/optimize/grid.py",
     "        cmp = -score if lower_better else score   # 작을수록 좋은 지표는 부호 반전",
     "        cmp = score",
     "tests/test_the_best_marker_points_at_the_best.py"),

    # 감사 178 — 세 곳이 공용 HTTP 문을 지나지 않았다.
    ("응답 크기 상한을 없앤다(초대형 응답이 그대로 메모리에 올라온다)",
     "quant/utils/http.py",
     "            raw = resp.read(_MAX_RESPONSE_BYTES + 1)\n"
     "            if len(raw) > _MAX_RESPONSE_BYTES:",
     "            raw = resp.read()\n"
     "            if False:",
     "tests/test_every_download_goes_through_the_same_door.py"),

    ("공포탐욕 파서가 중복 날짜를 안 지운다(같은 날이 두 번 들어간다)",
     "quant/data/sentiment.py",
     "    return s[~s.index.duplicated(keep=\"last\")]",
     "    return s",
     "tests/test_every_download_goes_through_the_same_door.py"),

    ("합성 데이터가 종목별 시드를 안 쓴다(전 종목이 같은 계열이 된다)",
     "quant/data/synthetic.py",
     "        rng = np.random.default_rng(self.seed + _symbol_seed(symbol))",
     "        rng = np.random.default_rng(self.seed)",
     "tests/test_every_download_goes_through_the_same_door.py"),

    # 감사 179 — 사람이 읽는 네 산출물. 결함 없음, 계약 고정.
    # 감사 197에서 이 계산이 dashboard.py → ledger_basics.py로 옮겨졌다
    # (조종석과 감시 탭이 각자 계산하던 것을 한 곳으로 모음). 대상 파일만
    # 따라 옮긴다 — 지키는 계약은 그대로다.
    ("대시보드가 잘려 나간 과거의 낙폭을 잊는다(위험 지표가 저절로 좋아진다)",
     "quant/live/ledger_basics.py",
     '    max_dd = float(summ.get("max_drawdown") or 0.0)',
     "    max_dd = 0.0",
     "tests/test_the_reports_do_not_flatter_us.py"),

    ("체결 격차의 불리 방향을 뒤집는다(낙관을 보수로 둔갑시킨다)",
     "quant/reporting/fill_gap.py",
     "        dirn = 1.0 if target > prev_w + 1e-9 else (\n"
     "            -1.0 if target < prev_w - 1e-9 else 0.0)",
     "        dirn = -1.0 if target > prev_w + 1e-9 else (\n"
     "            1.0 if target < prev_w - 1e-9 else 0.0)",
     "tests/test_the_reports_do_not_flatter_us.py"),

    ("체결 격차를 배열 순서대로 읽는다(장부가 날짜순이 아니면 '직전'이 미래가 된다)",
     "quant/reporting/fill_gap.py",
     "    hist = chrono(hist)",
     "    hist = list(hist)",
     "tests/test_the_reports_do_not_flatter_us.py"),

    ("기여도 힌트를 근거 없이도 만든다(전부 손실인데 '75% 기여'라고 말한다)",
     "quant/reporting/attribution.py",
     "    if total > 0:",
     "    if True:",
     "tests/test_the_reports_do_not_flatter_us.py"),

    # 감사 180 — 우리를 검사하는 도구들. 손익분기 대조에서 결함 1건.
    ("손익분기 대조를 수수료끼리만 한다(슬리피지가 비용의 5/6인 미국주식이 빠진다)",
     "quant/backtest/cost_sensitivity.py",
     "            if total > be_total:",
     '            if float(preset["fee"]) > be_total:',
     "tests/test_the_tools_that_check_us_are_checked_too.py"),

    ("엣지 없는 전략에도 손익분기를 붙인다('이 정도까지는 된다'로 읽힌다)",
     "quant/backtest/cost_sensitivity.py",
     "    if base_ret <= 0.0:",
     "    if False:",
     "tests/test_the_tools_that_check_us_are_checked_too.py"),

    ("교차검증에서 '겹침 없음'을 통과로 만든다(검증 못 한 걸 일치라 부른다)",
     "quant/data/crosscheck.py",
     '             "n_exceed": 0, "n_unverifiable": 0, "ok": False}',
     '             "n_exceed": 0, "n_unverifiable": 0, "ok": True}',
     "tests/test_the_tools_that_check_us_are_checked_too.py"),

    ("레짐 임계값을 전체 구간에서 뽑는다(오늘 라벨이 내일 데이터로 정해진다)",
     "quant/robustness/regime.py",
     "    thresh = vol.expanding(min_periods=vol_window * 2).quantile(vol_quantile)",
     "    thresh = pd.Series(vol.quantile(vol_quantile), index=vol.index)",
     "tests/test_the_tools_that_check_us_are_checked_too.py"),

    ("이력이 짧은 초반 레짐을 강세로 채운다(중립이어야 할 자리가 매수 신호가 된다)",
     "quant/robustness/regime.py",
     '    trend_up = reg["trend"].map({"bull": 1.0, "bear": 0.0}).fillna(0.5)',
     '    trend_up = reg["trend"].map({"bull": 1.0, "bear": 0.0}).fillna(1.0)',
     "tests/test_the_tools_that_check_us_are_checked_too.py"),

    ("HTML 리포트의 최대낙폭을 0으로 찍는다(리포트만 보면 무손실로 보인다)",
     "quant/reporting/html_report.py",
     '        ("최대낙폭", f"{m.max_drawdown:.2%}"),',
     '        ("최대낙폭", f"{0.0:.2%}"),',
     "tests/test_the_tools_that_check_us_are_checked_too.py"),

    # 감사 181 — 표시 전용 카드도 공개 기록이다. 거시 날짜에서 결함 1건.
    ("거시 카드에 발표 시차만큼 밀린 날짜를 찍는다(공개 기록에 미래 날짜가 남는다)",
     "quant/live/macro_brief.py",
     "            s = fred_series(sid, lag_days=0)",
     "            s = fred_series(sid)",
     "tests/test_the_display_only_cards_tell_the_truth.py"),

    ("장단기 금리 해석의 부호를 뒤집는다(역전을 '정상'이라 말한다)",
     "quant/live/macro_brief.py",
     '        parts.append("장단기 금리 역전(경기침체 신호)" if t < 0',
     '        parts.append("장단기 금리 역전(경기침체 신호)" if t > 0',
     "tests/test_the_display_only_cards_tell_the_truth.py"),

    ("브리핑에서 같은 기사를 중복 제거하지 않는다(같은 헤드라인이 여러 번 뜬다)",
     "quant/live/briefing.py",
     '            if it["title"] in seen:            # 카테고리 간 중복 제거\n'
     "                continue",
     "            if False:\n"
     "                continue",
     "tests/test_the_display_only_cards_tell_the_truth.py"),

    ("브리핑 헤드라인 상한을 무시한다(피드 하나가 화면을 다 잡아먹는다)",
     "quant/live/briefing.py",
     "        if len(items) >= top_n:",
     "        if len(items) >= top_n * 100:",
     "tests/test_the_display_only_cards_tell_the_truth.py"),

    ("피드 하나가 죽으면 브리핑 전체를 죽인다(뉴스 한 곳 장애로 그날 기록이 빈다)",
     "quant/live/briefing.py",
     '            log.warning("브리핑 피드 실패(%s): %s", category, exc)\n'
     '            health["feeds_failed"][category] = f"{type(exc).__name__}: {exc}"[:120]\n'
     "            continue",
     "            raise",
     "tests/test_the_display_only_cards_tell_the_truth.py"),

    ("`python -m quant` 진입점이 CLI를 안 부른다(모든 야간 잡이 조용히 무동작)",
     "quant/__main__.py",
     "    main()",
     "    pass",
     "tests/test_the_display_only_cards_tell_the_truth.py"),

    # 감사 182 — 전수조사 마지막 파일(kiwoom_live) + 형제(kr_live). 결함 3건.
    ("키움: 주문 방향 정규화를 건너뛴다('BUY'라고 쓰면 팔린다)",
     "quant/broker/kiwoom_live.py",
     "        side = normalize_side(side)",
     "        side = str(side)",
     "tests/test_a_renamed_field_cannot_empty_the_account.py"),

    # 감사 199에서 이 판정이 base.require_field로 모였다(형제가 넷이었다).
    # 항목은 브로커마다 남긴다 — 한 브로커가 공통 판정을 안 부르게 되는
    # 것이 정확히 감사 182에서 일어난 사고다.
    ("키움: 보유목록 키가 없어도 '0주 보유'라 답한다(목표만큼 다시 사서 두 배가 된다)",
     "quant/broker/kiwoom_live.py",
     '        holdings = require_field(data, self.HOLDINGS_KEY, "보유목록 키", "키움")',
     "        holdings = data.get(self.HOLDINGS_KEY)",
     "tests/test_a_renamed_field_cannot_empty_the_account.py"),

    ("키움: 예수금 필드가 없어도 '현금 0'이라 답한다(평가금액이 꺼져 청산 지시가 난다)",
     "quant/broker/kiwoom_live.py",
     '        raw = require_field(data, self.CASH_FIELD, "예수금 필드", "키움")',
     "        raw = data.get(self.CASH_FIELD, 0)",
     "tests/test_a_renamed_field_cannot_empty_the_account.py"),

    ("코인: 가용 잔고 키가 없어도 '현금 0'이라 답한다(청산 지시가 난다)",
     "quant/broker/crypto_live.py",
     '        free = require_field(bal, "free", "가용 잔고", f"거래소({self.exchange})")',
     '        free = bal.get("free", {})',
     "tests/test_a_renamed_field_cannot_empty_the_account.py"),

    ("코인: 총 잔고 키가 없어도 '0개 보유'라 답한다(목표만큼 다시 사서 두 배가 된다)",
     "quant/broker/crypto_live.py",
     '        total = require_field(bal, "total", "총 잔고", f"거래소({self.exchange})")',
     '        total = bal.get("total", {})',
     "tests/test_a_renamed_field_cannot_empty_the_account.py"),

    ("알파카: 총자산 필드가 없어도 '0원'이라 답한다(전 종목 청산 지시가 난다)",
     "quant/broker/us_live.py",
     '        return safe_amount(require_field(acct, "equity", "총자산", "Alpaca"))',
     '        return safe_amount(acct.get("equity", 0.0))',
     "tests/test_a_renamed_field_cannot_empty_the_account.py"),

    ("알파카: 현금 필드가 없어도 '0원'이라 답한다",
     "quant/broker/us_live.py",
     '        cash = require_field(acct, "cash", "현금", "Alpaca")',
     '        cash = acct.get("cash", 0.0)',
     "tests/test_a_renamed_field_cannot_empty_the_account.py"),

    # ── 감사 209: 멈춘 시세가 최대 노출을 받던 자리 ──────────────
    ("멈춘 시세(수익률 대부분 0) 가드를 끈다(거래정지 종목이 100% 비중을 받는다)",
     "quant/risk/manager.py",
     "            realized = realized.where(zero_share < 0.8, np.nan)",
     "            realized = realized",
     "tests/test_risk_limits_bind_at_the_source.py"),

    # ── 감사 208: 로그가 자기 시각·메시지를 잃던 자리 ────────────
    ("컨텍스트가 로그의 예약 키를 덮어쓴다(로그가 시각·메시지를 거짓으로 말한다)",
     "quant/utils/logging.py",
     "                payload[f\"ctx_{k}\" if k in payload else k] = v",
     "                payload[k] = v",
     "tests/test_the_wrappers_and_utils_keep_their_contracts.py"),

    # ── 감사 206·207: 모름을 반대로 처리·지문이 버전에 흔들리던 자리 ─
    ("변동성 필터가 판정 불가 구간을 통과시킨다(못 재는 구간에만 매매가 열린다)",
     "quant/strategies/regime.py",
     "            hot = (vol > self.max_daily_vol) | vol.isna()",
     "            hot = vol > self.max_daily_vol",
     "tests/test_regime.py"),

    ("데이터 지문을 repr로 적는다(numpy를 올리면 같은 데이터의 지문이 바뀐다)",
     "quant/utils/manifest.py",
     "    payload = \"|\".join(_stable(v) for v in",
     "    payload = \"|\".join(repr(v) for v in",
     "tests/test_manifest.py"),

    # ── 감사 205: 한 계열 안에서 단위가 섞이던 자리 ──────────────
    ("미결제약정 필드를 계열마다 고르지 않고 행마다 or로 떨어뜨린다(단위가 섞인다)",
     "quant/data/openinterest.py",
     "            v = float(row.get(field))",
     "            v = float(row.get(\"openInterestAmount\")\n"
     "                      or row.get(\"openInterestValue\"))",
     "tests/test_attached_features_cannot_see_the_future.py"),

    # ── 감사 204: 재는 자가 어긋나 완성 봉이 버려지던 자리 ───────
    ("신호 프레임이 실제 타임프레임 대신 항상 일봉 자로 잰다(완성 봉이 버려진다)",
     "quant/live/daily.py",
     "    if len(df) < 2 or bar_status(market, df.index[-1], timeframe, now) is None:",
     "    if len(df) < 2 or bar_status(market, df.index[-1], \"1d\", now) is None:",
     "tests/test_bar_completeness.py"),

    ("판정 불가를 '완성됨'과 같은 답으로 낸다(미완결 봉 제거가 조용히 꺼진다)",
     "quant/data/barclock.py",
     "    if frac is None:",
     "    if False:",
     "tests/test_bar_completeness.py"),

    ("미래 봉을 '0% 진행 중'이라고 적는다(없는 사실이 장부에 남는다)",
     "quant/data/barclock.py",
     "    if frac <= 0.0 and _is_future(last_bar, now):",
     "    if False:",
     "tests/test_bar_completeness.py"),

    # ── 감사 203: 폴백이 요청과 다른 길이의 봉을 내주던 자리 ─────
    ("모르는 타임프레임을 조용히 일봉으로 떨어뜨린다(24배 긴 봉을 30분봉으로 받는다)",
     "quant/data/synthetic.py",
     "        if timeframe not in _TIMEFRAMES:",
     "        if False:",
     "tests/test_synthetic_fallback_never_trades.py"),

    ("30분봉을 합성 제공자에서 뺀다(시계는 아는데 폴백만 몰라 길이가 갈라진다)",
     "quant/data/synthetic.py",
     '    "30m": (timedelta(minutes=30), "30min"),',
     "",
     "tests/test_synthetic_fallback_never_trades.py"),

    # ── 감사 202: 망가진 전략 하나가 나머지를 지우던 자리 ────────
    ("측정 불가를 'nan'으로 사람에게 보여준다(0인지 실패인지 알 수 없다)",
     "quant/reporting/attribution.py",
     "    if not math.isfinite(f):\n        return \"측정 불가\"",
     "    if False:\n        return \"측정 불가\"",
     "tests/test_the_reports_do_not_flatter_us.py"),

    # ── 감사 201: 표본이 모자란 종목이 '분산'으로 세어지던 자리 ───
    ("표본 부족 검사를 끈다(10봉짜리 종목이 '분산된 종목'으로 세어진다)",
     "quant/live/daily.py",
     "            if len(df_sig) < need:",
     "            if False:",
     "tests/test_a_thin_sample_is_not_a_decision.py"),

    ("필요 봉수를 챔피언 파라미터 대신 상수로 둔다(긴 창 전략이 무방비가 된다)",
     "quant/live/daily.py",
     "            longest = max(longest, int(abs(v)))",
     "            longest = 0",
     "tests/test_a_thin_sample_is_not_a_decision.py"),

    # ── 감사 200: 장부를 쓰는 마지막 관문 ────────────────────────
    ("직렬화 최후 수단을 끈다(모르는 값 하나에 그날 장부가 통째로 사라진다)",
     "quant/utils/jsonio.py",
     "    text = json.dumps(sanitize(obj), ensure_ascii=False, indent=indent,\n"
     "                      default=_last_resort)",
     "    text = json.dumps(sanitize(obj), ensure_ascii=False, indent=indent)",
     "tests/test_the_ledger_survives_what_it_did_not_expect.py"),

    ("numpy 스칼라를 문자열로 뭉갠다(사이트가 숫자로 못 읽는다)",
     "quant/utils/jsonio.py",
     "    item = getattr(obj, \"item\", None)          # numpy 스칼라 → 파이썬 값",
     "    item = None",
     "tests/test_the_ledger_survives_what_it_did_not_expect.py"),

    ("잘려나간 구간의 최고점을 요약에 안 접는다(낙폭이 저절로 좋아진다)",
     "quant/utils/jsonio.py",
     "        peak = e if peak is None else max(peak, e)",
     "        peak = e",
     "tests/test_the_ledger_survives_what_it_did_not_expect.py"),

    # ── 예산 유연화(사장님 결정 2026-08-13) ──────────────────────
    # "예산이 있는대로 유연하게" + "비율이 아니라 수익률이 더 높을 것이라
    # 판단되는 최우선 선택". 세 항목이 그 결정을 지킨다.
    ("확신도 순서를 버리고 dict 순서로 예산을 채운다(아무 종목이나 먼저 산다)",
     "quant/live/daily.py",
     "    lot_keys.sort(key=lambda k: (-abs(float(conv.get(k, targets[k]))), k))",
     "    pass",
     "tests/test_the_budget_buys_the_best_idea_first.py"),

    ("자기 배정금액을 못 넘게 되돌린다(국내주식을 한 종목도 못 산다)",
     "quant/live/daily.py",
     "        if want <= 0 and abs(w) > 0:\n"
     "            want = 1          # 자기 예산으로 못 사도 1주는 노린다(② 유연화)",
     "        if False:\n"
     "            want = 1",
     "tests/test_the_budget_buys_the_best_idea_first.py"),

    ("매도 선집행을 끈다(판 돈이 같은 사이클 매수에 안 쓰인다)",
     "quant/live/daily.py",
     "    for key in sorted(weights, key=_sell_first):",
     "    for key in weights:",
     "tests/test_the_budget_buys_the_best_idea_first.py"),

    ("잔고 필드 검사 자체를 끈다(네 브로커가 한꺼번에 '0'을 답하게 된다)",
     "quant/broker/base.py",
     "    if not isinstance(data, dict) or key not in data:",
     "    if False:",
     "tests/test_a_renamed_field_cannot_empty_the_account.py"),

    ("KIS: 주문 방향 정규화를 건너뛴다(형제 쪽만 살아 있으면 더 나쁘다)",
     "quant/broker/kr_live.py",
     "        side = normalize_side(side)",
     "        side = str(side)",
     "tests/test_a_renamed_field_cannot_empty_the_account.py"),

    ("KIS: 보유목록(output1)이 없어도 '0주 보유'라 답한다",
     "quant/broker/kr_live.py",
     '        holdings = require_field(data, "output1", "보유목록", "KIS") or []',
     '        holdings = data.get("output1") or []',
     "tests/test_a_renamed_field_cannot_empty_the_account.py"),

    ("KIS: 요약(output2)이 없어도 '현금 0'이라 답한다",
     "quant/broker/kr_live.py",
     '        summary = require_field(data, "output2", "요약", "KIS") or []',
     '        summary = data.get("output2") or []',
     "tests/test_a_renamed_field_cannot_empty_the_account.py"),

    # 감사 184 — 모든 성적이 나오는 자리. 결함 3건.
    ("신호와 봉이 어긋나도 그냥 계산한다(그럴듯한 오답이 나와 사람이 못 잡는다)",
     "quant/backtest/engine.py",
     "        if not desired.index.equals(df.index):",
     "        if False:",
     "tests/test_the_engine_that_makes_every_number.py"),

    ("파산 바닥을 없앤다(음수 자산에 음수를 곱해 날아간 계좌가 +100%가 된다)",
     "quant/backtest/engine.py",
     "            if not ruined and cash_equity <= 0.0:",
     "            if False:",
     "tests/test_the_engine_that_makes_every_number.py"),

    ("진입가를 체결가가 아니라 결정가로 적는다(손절선이 뜻대로 안 걸린다)",
     "quant/backtest/engine.py",
     "                    pending_entry = use_next_open",
     "                    pending_entry = False",
     "tests/test_the_engine_that_makes_every_number.py"),

    # 감사 247 — '다음 날'이 실은 '다음 기록'이던 자리. 실측: 전 종목 143쌍
    # 중 6쌍이 두 세션짜리(코인 5 + 국내 1, 08-06 결측). 합산 50%대 상승
    # 비율 57% → 61%, 60%대 48% → 53%로 움직인다.
    ("건너뛴 봉을 '다음 날'로 채점한다 — 이틀치 움직임이 하루 예측의 성적이 된다",
     "quant/live/ledger_basics.py",
     "            if n is not None and n != 1:",
     "            if False:",
     "tests/test_the_next_day_is_actually_the_next_session.py"),
    ("주말을 결측으로 센다 — 금요일→월요일 짝이 통째로 사라진다",
     "quant/live/ledger_basics.py",
     "            n = missed_sessions(market, a.get(\"date\"), b.get(\"date\"), holidays)",
     "            n = 99",
     "tests/test_the_next_day_is_actually_the_next_session.py"),
    ("뺀 짝의 수를 화면에 안 밝힌다 — '그런 날이 없었다'로 읽힌다",
     "quant/live/explain.py",
     '    return f" · 봉이 빠진 {n}번은 제외" if n else ""',
     '    return ""',
     "tests/test_the_next_day_is_actually_the_next_session.py"),
    ("확률 경험 보정이 세션 규칙을 안 쓴다 — 표시 확률이 다른 표본으로 정해진다",
     "quant/live/calibration_guard.py",
     "        rows, _dropped = next_session_pairs(history, market, holidays)",
     "        rows = list(zip(history, history[1:]))",
     "tests/test_the_next_day_is_actually_the_next_session.py"),
    ("합산 장부에 시장을 안 싣는다 — 하루 결측과 주말을 구별할 수 없다",
     "quant/live/daily.py",
     '                out.append((str(d.get("market") or ""), h))',
     "                out.append((\"\", h))",
     "tests/test_the_next_day_is_actually_the_next_session.py"),

    # 감사 187 — 방송에서 말하는 숫자 + 재현성 지문. 결함 1건(보합 미고지).
    ("확률대 표본에서 보합을 말하지 않는다(종목마다 비율이 갈리는데 이유를 숨긴다)",
     "quant/live/explain.py",
     '    return f" · 보합 {n}일 포함" if n else ""',
     '    return ""',
     "tests/test_the_numbers_we_say_out_loud.py"),

    ("소표본에서도 비율을 말한다(n=8의 비율이 확신처럼 읽힌다)",
     "quant/live/explain.py",
     "MIN_BAND_SAMPLES = 25",
     "MIN_BAND_SAMPLES = 1",
     "tests/test_the_numbers_we_say_out_loud.py"),

    ("의존성 범위 위반 판정을 끈다(검사와 실전이 다른 세계가 된다)",
     "quant/utils/repro.py",
     "        if got and not version_satisfies(str(got), specs):",
     "        if False:",
     "tests/test_the_numbers_we_say_out_loud.py"),

    # 감사 188 — 블록 부트스트랩이 표본 앞부분을 깎고 있었다. 형제 2곳.
    ("A/B 검정 재추출에서 블록을 끝에서 자른다(표본 앞부분이 반쯤 깎인다)",
     "quant/robustness/compare.py",
     "        idx.extend((start + k) % n for k in range(block))",
     "        idx.extend(range(start, min(start + block, n)))",
     "tests/test_the_resampling_does_not_forget_the_beginning.py"),

    ("무작위 벤치마크 재추출에서 블록을 끝에서 자른다(사이트 백분위의 분모가 흔들린다)",
     "quant/robustness/monte_carlo.py",
     "        out.extend(r[(start + k) % n] for k in range(block))",
     "        out.extend(r[start : start + block])",
     "tests/test_the_resampling_does_not_forget_the_beginning.py"),

    ("재추출을 낱개로 바꾼다(자기상관 보존이라는 목적이 사라진다)",
     "quant/robustness/compare.py",
     "        start = int(rng.integers(0, n))\n"
     "        idx.extend((start + k) % n for k in range(block))",
     "        idx.extend(int(rng.integers(0, n)) for _ in range(block))",
     "tests/test_the_resampling_does_not_forget_the_beginning.py"),

    # 감사 189 — 드리프트 경보. 결함 없음, 계약 고정.
    ("드리프트 판정에서 표본 크기 보정을 끈다(잡음의 절반이 '드리프트'가 된다)",
     "quant/robustness/drift.py",
     "        ref = psi_null(int(n_ref), int(n_new), bins)",
     "        ref = {}",
     "tests/test_the_drift_alarm_knows_its_own_noise.py"),

    ("계산 불가를 0(안정)으로 위장한다(경보가 조용히 꺼진다)",
     "quant/robustness/drift.py",
     "    if exp[0] == exp[-1]:                    # 상수 피처 — 분포 비교 불가\n"
     '        return float("nan")',
     "    if exp[0] == exp[-1]:\n        return 0.0",
     "tests/test_the_drift_alarm_knows_its_own_noise.py"),

    # 감사 190 — 실거래 키 파일을 제자리에서 자르고 있었다.
    ("비밀 파일을 원자 교체 없이 제자리에서 자른다(쓰기 실패 시 API 키가 사라진다)",
     "quant/utils/envfile.py",
     "        os.replace(tmp, fp)",
     "        os.replace(fp, fp)",
     "tests/test_a_failed_write_does_not_eat_the_keys.py"),

    ("비밀 파일을 평범한 권한으로 만든다(같은 기계의 다른 사용자가 키를 읽는다)",
     "quant/utils/envfile.py",
     "        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)",
     "        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)",
     "tests/test_a_failed_write_does_not_eat_the_keys.py"),

    # 감사 191 — 조회 실패를 '오늘 받아온 사실'로 도장 찍고 있었다.
    ("실적 캘린더 조회 실패를 신선한 캐시로 적는다(가드가 발표일에 꺼져 있다)",
     "quant/data/earnings.py",
     '                 "fetched": today.isoformat() if ok\n'
     '                 else (entry or {}).get("fetched", "")}',
     '                 "fetched": today.isoformat()}',
     "tests/test_a_failed_lookup_does_not_become_a_fact.py"),

    ("실적 가드 창을 발표 이전으로만 좁힌다(갭이 가장 큰 다음 날이 무방비)",
     "quant/data/earnings.py",
     "        d = nearest_earnings_date(symbol, asof, state_dir, fetch=fetch)",
     "        d = next_earnings_date(symbol, asof, state_dir, fetch=fetch)",
     "tests/test_a_failed_lookup_does_not_become_a_fact.py"),

    # 감사 192 — 주문 방향 판정을 한 곳으로 모았다(감사 182의 형제 둘 더).
    ("공용 판정에서 모르는 방향을 통과시킨다(모든 브로커가 한꺼번에 무방비)",
     "quant/broker/base.py",
     '    if s not in ("buy", "sell"):\n'
     '        raise ValueError(f"알 수 없는 주문 방향: {side!r} (buy/sell만 허용)")',
     "    if False:\n        pass",
     "tests/test_one_place_decides_which_way_the_order_goes.py"),

    ("페이퍼 브로커가 방향을 확인하지 않는다(모든 기록이 여기서 나온다)",
     "quant/broker/paper.py",
     "        side = normalize_side(side)   # 모르는 방향이 매도가 되면 안 된다(감사 192)",
     "        side = str(side)",
     "tests/test_one_place_decides_which_way_the_order_goes.py"),

    ("지정가 체결 판정 전에 방향을 확인하지 않는다(안 닿아도 체결된다)",
     "quant/broker/paper.py",
     "        side = normalize_side(side)\n"
     '        crossed = (bar_low <= limit_price) if side == "buy" \\',
     '        crossed = (bar_low <= limit_price) if side == "buy" \\',
     "tests/test_one_place_decides_which_way_the_order_goes.py"),

    # 감사 193 — 일일 요약이 막 시작한 날을 요약하고 있었다.
    ("일일 요약이 끝난 날 대신 시작한 날을 보고한다(늘 '사이클 0회'로 찍힌다)",
     "quant/live/summary.py",
     "    return t, build_daily_summary(state, today=last_date)",
     "    return t, build_daily_summary(state, today=t)",
     "tests/test_the_daily_summary_reports_the_day_that_ended.py"),

    ("요약이 그 날이 아니라 전체 마지막 기록을 읽는다(어제 요약에 오늘 자산)",
     "quant/live/summary.py",
     "    last = same_day[-1] if same_day else (\n"
     "        history[-1] if history and isinstance(history[-1], dict) else {})",
     "    last = history[-1] if history and isinstance(history[-1], dict) else {}",
     "tests/test_the_daily_summary_reports_the_day_that_ended.py"),

    # 감사 194 — 유니버스 정의. 결함 없음, 계약 고정.
    ("같은 종목을 유니버스에 두 번 넣는다(그 종목 비중이 두 배가 된다)",
     "quant/markets.py",
     '    ("crypto", "ETH/USDT"),',
     '    ("crypto", "BTC/USDT"),',
     "tests/test_the_universe_says_what_it_is.py"),

    ("설명 없는 종목을 유니버스에 넣는다(사이트가 종목코드를 그대로 노출한다)",
     "quant/markets.py",
     '    ("crypto", "XRP/USDT"),',
     '    ("crypto", "DOGE/USDT"),',
     "tests/test_the_universe_says_what_it_is.py"),

    # 감사 195 — 끄려고 적은 글자가 켜는 결과를 냈다.
    ("설정 불린을 파이썬 truthiness로 읽는다('false'라고 적으면 켜진다)",
     "quant/utils/settings.py",
     "    if isinstance(value, bool):\n        return value",
     "    if True:\n        return bool(value)",
     "tests/test_the_switch_means_what_it_says.py"),

    ("모르는 설정 값을 참으로 추측한다(위험 상한 해제가 오타로 켜진다)",
     "quant/utils/settings.py",
     "    if text in _FALSE:\n        return False",
     "    if False:\n        return False",
     "tests/test_the_switch_means_what_it_says.py"),

    # 감사 196 — 거시 피드. 사이트 파괴 결함은 없었고(아래층이 막는다) 원천 방어 추가.
    ("FRED 값의 nan·inf를 그대로 피처로 넘긴다(학습·예측이 오염된다)",
     "quant/data/macro.py",
     "        if not math.isfinite(val):\n            continue",
     "        if False:\n            continue",
     "tests/test_the_macro_feed_does_not_poison_the_model.py"),

    ("거시 프레임을 뒤에서 앞으로도 채운다(발표 전 날짜에 미래 값이 샌다)",
     "quant/data/macro.py",
     "    df = pd.DataFrame(cols).sort_index().ffill()",
     "    df = pd.DataFrame(cols).sort_index().ffill().bfill()",
     "tests/test_the_macro_feed_does_not_poison_the_model.py"),

    # ── 어드민·웹 경로 ──
    # 감사 186 — 조종석에서 바깥이 바뀌는 자리. 새 결함 없음, 계약 고정.
    ("입금액 상·하한 검사를 끈다(공개 장부의 원금이 아무 값이나 된다)",
     "quant/web/app.py",
     "    if not (0 < amount <= 10_000_000):",
     "    if False:",
     "tests/test_the_cockpit_does_not_hand_out_the_wheel.py"),

    ("방송 현재가에 합성 폴백을 허용한다(가짜 시세가 생방송에 나간다)",
     "quant/web/app.py",
     '                if len(df) and not df.attrs.get("synthetic_fallback"):',
     "                if len(df):",
     "tests/test_the_cockpit_does_not_hand_out_the_wheel.py"),

    ("입금 메모 길이 상한을 없앤다",
     "quant/web/app.py",
     '    memo = str(params.get("memo", ""))[:80]',
     '    memo = str(params.get("memo", ""))',
     "tests/test_the_cockpit_does_not_hand_out_the_wheel.py"),

    ("입금 라우트를 CSRF 보호 목록에서 뺀다(<img> 한 줄로 가짜 입금)",
     "quant/web/server.py",
     '    _MUTATING = ("/deposit/run", "/optimize/run", "/sweep/run",',
     '    _MUTATING = ("/optimize/run", "/sweep/run",',
     "tests/test_the_cockpit_does_not_hand_out_the_wheel.py"),

    ("웹 토큰 인증을 통과시킨다(노출 시 무인증 접근)",
     "quant/web/server.py",
     "        return hmac.compare_digest(supplied, token)",
     "        return True",
     "tests/test_web.py"),

    ("합성 폴백 데이터 배너를 끈다(가짜 데이터를 진짜처럼)",
     "quant/web/app.py",
     '    if any(getattr(df, "attrs", {}).get("synthetic_fallback") for df in dfs):',
     "    if False:",
     "tests/test_web.py"),

    ("종목 수 비율을 다시 회전율로 써서 비용을 계산한다",
     "docs/index.html",
     "    const withT=hs.filter(r=>typeof r.turnover.traded===\"number\");",
     "    const withT=hs;",
     "tests/test_turnover_is_money_not_symbols.py"),

    ("어드민 참고 변동성을 다시 산문에 박는다",
     "docs/admin.html",
     '<span id="volref">참고 수치를 장부에서 읽는 중…</span></span></span>',
     '참고: 20종목 무레버리지 전액투자의 예상 변동성이 약 8.8%입니다.</span></span>',
     "tests/test_site_numbers_track_the_code.py"),

    ("오늘의 판단이 후보 수를 '분산'이라 말하게 되돌린다",
     "docs/today.html",
     '<div class="k">통합 계좌 (${spread} · 시작 ',
     '<div class="k">통합 계좌 (${rest.length}종목 분산 · 시작 ',
     "tests/test_broadcast_tells_the_whole_truth.py"),

    ("사이드바 '종목계좌' 라벨을 맨 '비중'으로 되돌린다",
     "docs/index.html",
     '">종목계좌 \'+((r.w||0)*100).toFixed(1)+\'%\'',
     '">비중 \'+((r.w||0)*100).toFixed(1)+\'%\'',
     "tests/test_two_ledgers_are_not_confused.py"),

    ("표지가 '사람의 개입은 없습니다'라고 단언하게 되돌린다",
     "docs/sns_card.html",
     "      +(owner?'오늘은 <b>사람이 손을 댔습니다</b> — '+owner+'.</div>'\n"
     "             :'오늘은 사람의 개입이 없었습니다.</div>'));",
     "      +'사람의 개입은 없습니다.</div>');",
     "tests/test_broadcast_tells_the_whole_truth.py"),

    ("캡션이 후보 수를 '분산'이라 말하게 되돌린다",
     "quant/reporting/social.py",
     'f"📈 {money} · {spread}(코인·한국·미국)\\n"',
     'f"📈 {money} · {n_sym}종목 분산(코인·한국·미국)\\n"',
     "tests/test_broadcast_tells_the_whole_truth.py"),

    ("적중률 라벨이 무엇을 잰 값인지 안 밝힌다 — '전체 기간'으로 읽힌다",
     "docs/index.html",
     '>적중률<br><span class="sub" style="font-weight:400">과거 400봉 · 실전</span></th>',
     '>적중률(전체)</th>',
     "tests/test_hit_rate_carries_its_sample.py"),

    ("적중률에서 표본 수를 뗀다(n=3 우연이 실력처럼)",
     "quant/live/daily.py",
     '        "hit_n": acc.get("n"),',
     '        "hit_n": None,',
     "tests/test_hit_rate_carries_its_sample.py"),

    ("카드 표에서 통합/종목 계좌 구분을 지운다(같은 이름 두 뜻)",
     "docs/paper.html",
     '<th title="${isPf?"통합 계좌가 실제로 들고 있는 비중의 합(총노출)":"그 종목만 굴리는 참고 계좌 안에서의 비중"}">${isPf?"총노출":"참고계좌 비중"}</th>',
     '<th>비중</th>',
     "tests/test_two_ledgers_are_not_confused.py"),

    ("벤치마크 라벨에서 '무엇을 보유했나'를 지운다",
     "docs/index.html",
     '⋯ 첫날 전 종목 균등 매수 후 그대로 보유했다면',
     '⋯ 그냥 보유했다면',
     "tests/test_benchmark_label_says_what_it_is.py"),

    ("전략이 미래 종가를 앞당겨 본다(성적 부풀리기)",
     "quant/strategies/breakout.py",
     '        close = df["close"].to_numpy()',
     '        close = df["close"].shift(-1).ffill().to_numpy()',
     "tests/test_leakage.py"),

    ("룩어헤드 검사에서 미래 교란을 뺀다(1봉 누수 눈감기)",
     "tests/test_leakage.py",
     "        _compare_perturbed(full, make_strategy, name, cut)",
     "        pass",
     "tests/test_lookahead_challenger_ring.py"),

    ("두 계좌 구분을 지운다(20만원이 8만원처럼 보임)",
     "docs/paper.html",
     '<div class="card"><h2>종목별 참고 계좌',
     '<div class="card"><h2>종목별 현황',
     "tests/test_two_ledgers_are_not_confused.py"),

    ("피처 계측 목록을 유령 이름으로 되돌린다",
     "quant/strategies/ml.py",
     '    "x_btc_ret5", "x_spy_ret5",            # 크로스에셋 — 코인/미국 조류',
     '    "x_btc", "x_spy",                      # 크로스에셋 — 코인/미국 조류',
     "tests/test_feature_health_measures_real_columns.py"),

    ("deadman을 23:30 UTC로 되돌린다(하루 누락 맹점 부활)",
     ".github/workflows/deadman.yml",
     '    - cron: "30 3 * * *"',
     '    - cron: "30 23 * * *"',
     "tests/test_deadman_window.py"),

    ("deadman 창을 26시간으로 되돌린다(어제 커밋이 오늘을 덮음)",
     ".github/workflows/deadman.yml",
     'LOG="$(git log --since="24 hours ago" --pretty=%s)"',
     'LOG="$(git log --since="26 hours ago" --pretty=%s)"',
     "tests/test_deadman_window.py"),

    ("배치 커밋 표식을 [skip ci]로 되돌린다(사이트 배포 정지)",
     ".github/workflows/social-post.yml",
     'git commit -m "SNS 게시 콘텐츠: $(date -u +%F) [skip actions]"',
     'git commit -m "SNS 게시 콘텐츠: $(date -u +%F) [skip ci]"',
     "tests/test_deadman_window.py"),

    ("재현 경보를 산문 매칭으로 되돌린다(통과 줄에 헛울림)",
     "scripts/verify_gate.py",
     '        if "✔" in ln:',
     '        if "✔" in ln and "불일치" not in ln:',
     "tests/test_verify_gate.py"),

    ("캡션이 다시 매매 엔진(numpy)을 끌어오게 한다",
     "quant/reporting/social.py",
     "    from quant.live.ledger_basics import PORTFOLIO_START_CASH",
     "    from quant.live.daily import PORTFOLIO_START_CASH",
     "tests/test_social_path_stays_light.py"),

    ("사이트 자바스크립트에 문법 오류를 심는다",
     "docs/index.html",
     '  const applied=(pfLast.applied)||null;',
     '  const applied=(pfLast.applied)||;',
     "tests/test_site_scripts_parse.py"),

    ("종목계좌 비중을 통합 노출인 것처럼 되돌린다",
     "docs/index.html",
     '>종목계좌 비중<br><span class="sub" style="font-weight:400">현재 보유</span></th>',
     '>비중</th>',
     "tests/test_two_kinds_of_weight_are_labeled.py"),

    ("드리프트 등급을 대표본 관행 문턱으로 되돌린다",
     "quant/robustness/drift.py",
     '    if n_ref and n_new:\n        ref = psi_null(int(n_ref), int(n_new), bins)',
     '    if False:\n        ref = psi_null(int(n_ref), int(n_new), bins)',
     "tests/test_drift_alarm_is_calibrated.py"),

    ("사이트가 배분 방식을 다시 산문에 박는다(폴백 은폐)",
     "docs/paper.html",
     '?rest.length+"종목 위험 분산("+(AMN[am]||"방식 기록 없음")+") (각 종목의 챔피언 전략 추종)"',
     '?rest.length+"종목 위험 분산(HRP·계층적 리스크 패리티) (각 종목의 챔피언 전략 추종)"',
     "tests/test_ledger_fields_reach_the_screen.py"),

    ("카드가 누적을 '오늘'이라 부르던 때로 되돌린다",
     "docs/sns_card.html",
     "  var hd=dayp;",
     "  var hd=ret;",
     "tests/test_broadcast_tells_the_whole_truth.py"),

    ("사람의 개입(일시정지·노출 배수)을 캡션에서 뺀다",
     "quant/reporting/social.py",
     '    if x.get("paused"):\n        hands.append("신규 주문 일시정지(보유 유지)")',
     '    if False:\n        hands.append("신규 주문 일시정지(보유 유지)")',
     "tests/test_broadcast_tells_the_whole_truth.py"),

    ("길이 초과 시 짧은 판이 고지까지 잘라내게 되돌린다",
     "quant/reporting/social.py",
     'f"💰 {eq} (누적 {ret}{day_line}){kill}{owner}\\n"\n'
     '            f"⚠️ 모의투자 — 수익 보장 없음. 매일 그날 숫자 그대로.\\n"',
     'f"💰 {eq} (누적 {ret})\\n"\n'
     '            f"⚠️ 모의투자 — 수익 보장 없음. 매일 그날 숫자 그대로.\\n"',
     "tests/test_broadcast_tells_the_whole_truth.py"),

    ("SNS 카드에서 신뢰구간을 뺀다(소표본을 확정처럼 방송)",
     "docs/sns_card.html",
     "        +'<span style=\"font-size:24px;color:var(--muted);font-weight:600\"> (95% '\n"
     "        +(ci[0]*100).toFixed(0)+'~'+(ci[1]*100).toFixed(0)+'%)</span></span></div>'}).join(\"\");",
     "        +'</span></div>'}).join(\"\");",
     "tests/test_card_shows_uncertainty.py"),

    ("주문이 실패한 종목까지 노출로 기록한다(다종목)",
     "quant/live/multi.py",
     '"weight": float(sum(abs(v) for v in placed.values())),',
     '"weight": float(sum(abs(v) for v in weights.values())),',
     "tests/test_recorded_exposure_is_what_was_ordered.py"),

    ("체결 기록에서 배분 슬라이스를 다시 빼먹는다(주문≠장부)",
     "quant/live/daily.py",
     '"weight": round(float(pend["weight"]) * sl, 4),',
     '"weight": round(float(pend["weight"]), 4),',
     "tests/test_fill_records_match_the_orders.py"),

    ("배분 예산을 매수 비중이라 부른다(관망 종목 방송)",
     "quant/reporting/social.py",
     "    keep = (list(src) if applied\n"
     "            else [k for k in src if _held_on(status, k, date)])",
     "    keep = list(src)",
     "tests/test_alloc_is_not_a_purchase.py"),

    # ⚠️ 이 항목은 감사 183에서 갈아 끼웠다. 예전 변이는
    #        w * eff_scale * vscale * guard_damp  →  w * eff_scale * guard_damp * vscale
    #    였는데 **곱셈은 교환법칙이 성립한다** — 값이 똑같으니 어떤 검사도
    #    잡을 수 없는 무의미한 변이였다(전수 시험에서 '못 잡음'으로 나왔다).
    #    진짜 결함은 순서가 아니라 **vscale을 무엇으로 계산하느냐**다:
    #    감쇠된 비중을 넣으면 스케일러가 "위험이 줄었다"며 되돌려 키워
    #    브레이크가 사라진다. 그 자리를 겨눈다.
    ("변동성 배수를 감쇠된 비중으로 계산한다(킬스위치가 통째로 무효가 된다)",
     "quant/live/daily.py",
     "    vscale, ex_ante = vol_scale(base_w, rets_map, tgt_vol)",
     "    vscale, ex_ante = vol_scale({k: v * eff_scale for k, v in base_w.items()},\n"
     "                                rets_map, tgt_vol)",
     "tests/test_killswitch_is_wired_to_the_brake.py"),

    ("켈리 상한 clip을 지운다(무효화)",
     "quant/live/daily.py",
     "        kcap = kelly_caps.get(key)\n        if kcap is not None:\n            eff = float(np.clip(eff, -kcap, kcap))",
     "        kcap = kelly_caps.get(key)\n        if kcap is not None:\n            pass",
     "tests/test_guards_actually_bind.py"),

    ("데이터 무결성 게이트를 끈다",
     "quant/live/daily.py",
     "            if is_severe(q):",
     "            if False and is_severe(q):",
     "tests/test_guards_actually_bind.py"),

    ("입금을 낙폭 계산에서 다시 빼먹는다",
     "quant/live/daily.py",
     "    drawdown = drawdown_from_index(_series)",
     "    drawdown = 0.0 if not st['history'] else min(0.0, equity / max(float(h.get('equity', 0)) for h in st['history']) - 1.0)",
     "tests/test_killswitch_deposits.py"),

    ("CSRF 가드를 끈다",
     "quant/web/server.py",
     "if not self._same_site_ok(parsed):",
     "if False and not self._same_site_ok(parsed):",
     "tests/test_web_csrf.py"),

    # chrono는 2026-08-11 감사 102에서 의존성 없는 ledger_basics로 옮겼다
    # (SNS 게시 경로가 numpy를 끌어오지 않게). daily는 재수출만 한다.
    ("장부 정렬(chrono)을 없앤다",
     "quant/live/ledger_basics.py",
     'return sorted(history or [], key=lambda r: str(r.get("date", "")))',
     "return list(history or [])",
     "tests/test_ledger_integrity.py"),

    ("알림 실패를 성공으로 기록한다(경보 유실)",
     "quant/live/flag_watch.py",
     "        if notifier.send(cur[k]) is False:",
     "        if False:",
     "tests/test_flag_watch.py"),

    ("부분 체결 뒤 전량 재주문(160% 초과 체결)",
     "quant/broker/retry.py",
     "                    remaining = max(0.0, qty - landed)",
     "                    remaining = qty",
     "tests/test_broker_retry_partial.py"),

    # 감사 242 — 이미 체결된 것이 '주문 실패'에 묻히던 자리.
    # 실측: 거래소 0.6 보유 / 우리 장부 없음(종목이 skipped로 기록됨).
    ("확인한 부분 체결을 실패로 마감한다 — 거래소에만 있는 포지션이 생긴다",
     "quant/broker/retry.py",
     "        if landed_before > 0 and not unverified:",
     "        if False:",
     "tests/test_a_landed_fill_is_not_erased_by_a_failure.py"),

    ("잔량 재주문이 실패하면 이미 체결된 것까지 없던 일로 만든다",
     "quant/broker/retry.py",
     "                if filled_total <= 0:",
     "                if True:",
     "tests/test_a_landed_fill_is_not_erased_by_a_failure.py"),

    ("보낼 수 없는 잔량(최소금액 미만)을 계속 재주문한다",
     "quant/broker/retry.py",
     "                    if not rspec.is_tradeable(rspec.round_qty(remaining), price):",
     "                    if False:",
     "tests/test_a_landed_fill_is_not_erased_by_a_failure.py"),

    # ── 2차: 오디션·리스크·인증 계열 ──────────────────────────

    ("합성 폴백 데이터로도 매매하게 만든다",
     "quant/live/daily.py",
     '            if df.empty or (require_real_data\n'
     '                            and df.attrs.get("synthetic_fallback")):',
     "            if df.empty:",
     "tests/test_audition_gates_bind.py"),

    ("무레버리지 상한을 3배로 푼다",
     "quant/risk/portfolio_vol.py",
     "MAX_GROSS_EXPOSURE = 1.0",
     "MAX_GROSS_EXPOSURE = 3.0",
     "tests/test_killswitch_effective.py"),

    ("엣지 미입증인데 목표 변동성 잠금을 푼다",
     "quant/risk/portfolio_vol.py",
     "    if not proven and not override:\n        base = min(base, VERIFY_TARGET_VOL)",
     "    if False:\n        base = min(base, VERIFY_TARGET_VOL)",
     "tests/test_settings_contract.py"),

    ("결승전 구간을 선발전에도 보여준다(오디션 오염)",
     "quant/live/retrain.py",
     "    select_df = df.iloc[:-confirm_window]",
     "    select_df = df",
     "tests/test_audition_gates_bind.py"),

    ("폴드 과반 게이트를 없앤다",
     "quant/live/retrain.py",
     'return c["fold_wins"] >= c["n_folds"] // 2 + 1',
     "return True",
     "tests/test_alpha7_volforecast_folds.py"),

    ("선별 문턱을 0으로 내린다(잡음 후보가 그대로 결승행)",
     "quant/live/retrain.py",
     "SELECT_SCREEN_T = 1.0",
     "SELECT_SCREEN_T = 0.0",
     "tests/test_audition_gates_bind.py"),

    ("결승 문턱의 다중검정 보정을 상수로 만든다",
     "quant/live/retrain.py",
     "    return min(CONFIRM_T_CAP,\n               1.0 + 0.5 * math.log10(1 + max(0, trials_recent) / 1000))",
     "    return 1.0",
     "tests/test_audition_gates_bind.py"),

    ("선별기가 검정보다 엄격해지도록 클램프를 없앤다(결승전 무력화)",
     "quant/live/retrain.py",
     "    if clamp_screen and select_t > confirm_t:",
     "    if False and select_t > confirm_t:",
     "tests/test_audition_gates_bind.py"),

    ("무효 후보(챔피언 사본)를 링에 그대로 세운다",
     "quant/live/retrain.py",
     '        if r.get("identical"):',
     "        if False:",
     "tests/test_audition_gates_bind.py"),

    ("무효 후보 탐지를 항상 거짓으로 만든다",
     "quant/live/champion_challenger.py",
     "        identical = bool(",
     "        identical = False and bool(",
     "tests/test_audition_gates_bind.py"),

    ("오디션 링에서 벤치마크(보유)를 뺀다 — '들고 있는 게 낫다'를 영영 못 본다",
     "quant/live/retrain.py",
     '    {"strategy": "buy_hold", "params": {}},',
     "",
     "tests/test_the_benchmark_is_in_the_ring.py"),

    ("검증 게이트를 최종 비중에서 뗀다(경보만 울리던 시절로 복귀)",
     "quant/live/daily.py",
     "               * valid_damp.get(key, 1.0))",
     "               * 1.0)",
     "tests/test_the_validation_gate_actually_gates.py"),

    ("만료를 실패보다 먼저 본다(오래된 '버릴 것'이 오히려 덜 깎인다)",
     "quant/live/validation_gate.py",
     "    if pbo is not None and pbo > PBO_FAIL:\n        stale =",
     "    if age is not None and age > MAX_AGE_DAYS:\n        pass\n    if False:\n        stale =",
     "tests/test_the_validation_gate_actually_gates.py"),

    ("반쪽 측정(한쪽만 잰 기록)을 통과로 취급한다",
     "quant/live/validation_gate.py",
     '        reasons.append("보정 샤프(DSR)가 측정되지 않음")',
     "        pass",
     "tests/test_the_validation_gate_actually_gates.py"),

    ("날짜 없는 기록을 신선한 것으로 취급한다(옛 도장이 영원히 유효)",
     "quant/live/validation_gate.py",
     '        reasons.append(f"측정 날짜가 없어 신선도를 확인할 수 없음"',
     '        _unused = (f"측정 날짜가 없어 신선도를 확인할 수 없음"',
     "tests/test_the_validation_gate_actually_gates.py"),

    ("미측정 종목을 '통과'로 취급한다(검증이 죽은 날 가장 공격적으로 굴린다)",
     "quant/live/validation_gate.py",
     "SCALE_WARN = 0.5",
     "SCALE_WARN = 1.0",
     "tests/test_the_validation_gate_actually_gates.py"),

    ("PBO 실패선을 없앤다(과최적화 확률 78%도 그대로 굴린다)",
     "quant/live/validation_gate.py",
     "    if pbo is not None and pbo > PBO_FAIL:",
     "    if False:",
     "tests/test_the_validation_gate_actually_gates.py"),

    ("검증 결과에서 날짜를 뺀다(옛 검증이 영원히 통과 도장을 찍는다)",
     "quant/cli.py",
     '            "asof": str(df.index[-1])[:10] if len(df) else None,',
     "",
     "tests/test_the_validation_gate_actually_gates.py"),

    ("야간 검증을 두 종목으로 되돌린다",
     ".github/workflows/nightly-validate.yml",
     "          python -m quant validate --all \\",
     "          python -m quant validate --market crypto --symbol BTC/USDT \\",
     "tests/test_nightly_workflow.py"),

    ("의회에서 NaN 상관을 '다양성 통과'로 되돌린다",
     "quant/live/parliament.py",
     "                if c != c or c > CORR_CAP:",
     "                if c == c and c > CORR_CAP:",
     "tests/test_parliament_moves_slowly_and_diversely.py"),

    ("무포지션 의원에게도 의석을 준다(현금이 의석을 갖는다)",
     "quant/live/parliament.py",
     "            if idle[i]:",
     "            if False:",
     "tests/test_parliament_moves_slowly_and_diversely.py"),

    ("소스 실패 사유 기록을 끈다(왜 안 붙었는지 다시 사라진다)",
     "quant/data/source_health.py",
     "        errs[str(source)] = str(reason)[:MAX_REASON]",
     "        pass",
     "tests/test_feature_health.py"),

    ("거래소 페이지네이션을 없앤다(코인이 다시 300봉으로 굶는다)",
     "quant/data/crypto.py",
     "        raw = _fetch_paged(client, symbol, timeframe, since, limit)",
     "        raw = client.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)",
     "tests/test_a_capped_exchange_does_not_starve_the_model.py"),

    ("공회전 오디션을 다시 '정상'이라고 적는다",
     "quant/live/retrain.py",
     "    vacuous = bool(inert) and len(candidates) <= max(1, len(inert) // 4)",
     "    vacuous = False",
     "tests/test_audition_gates_bind.py"),

    ("피처 계측의 분모를 시장 무시하고 전체 목록으로 되돌린다",
     "quant/strategies/ml.py",
     "    names = MARKET_OPTIONAL_FEATURES.get(market)",
     "    names = None",
     "tests/test_feature_health.py"),

    ("웹훅 서명 검증을 통과시킨다",
     "quant/live/webhook.py",
     "    return hmac.compare_digest(got, expected)",
     "    return True",
     "tests/test_webhook.py"),

    ("잔돈 주문 차단을 끈다",
     "quant/live/daily.py",
     "    delta = abs(target_w * equity - cur_notional)\n    return delta < floor",
     "    return False",
     "tests/test_position_read_failure.py"),

    # ── 3차: 운영 손잡이·배포 잠금·회계 계열 ──────────────────

    ("배포판에서 실거래 차단을 푼다",
     "quant/utils/dist.py",
     "    if is_distribution_build():\n        raise SystemExit(",
     "    if False:\n        raise SystemExit(",
     "tests/test_license_path.py"),

    ("어드민 '일시정지'를 무시한다",
     "quant/live/daily.py",
     "    eff_scale = risk_scale * float(settings[\"exposure_scale\"])",
     "    eff_scale = risk_scale",
     "tests/test_guards_actually_bind.py"),

    ("같은 봉 재실행 멱등 가드를 없앤다(중복 기록)",
     "quant/live/daily.py",
     '    if st.get("last_bar") == bar:',
     "    if False:",
     "tests/test_guards_actually_bind.py"),

    ("주식도 결정 당일 종가에 즉시 체결시킨다(실현 불가 가격)",
     "quant/live/daily.py",
     'IMMEDIATE_FILL_MARKETS = {"crypto", "synthetic"}',
     'IMMEDIATE_FILL_MARKETS = {"crypto", "synthetic", "us_stock", "kr_stock"}',
     "tests/test_intrabar_next_open.py"),

    ("실측 비용을 왕복이 아닌 편도로 되돌린다(비용 절반)",
     "quant/live/daily.py",
     "        return 2.0 * one_way_bp / 1e4          # 왕복",
     "        return one_way_bp / 1e4",
     "tests/test_alpha14_fill_gap.py"),

    # ── 4차: 리포팅·외부 데이터·부분 실패 계열 ────────────────

    ("FRED 거시 데이터의 발표 지연을 없앤다(발표 전 값을 미리 씀)",
     "quant/data/macro.py",
     "        s.index = s.index + pd.Timedelta(days=int(lag))",
     "        pass",
     "tests/test_lookahead_external.py"),

    ("새벽 배치 부분 실패 기록을 끈다(절반 마비를 성공으로)",
     "quant/live/daily.py",
     "def _write_run_health(state_dir: str, kind: str, ok: list, failed: dict,",
     "def _write_run_health(*a, **kw) -> None:\n    return\ndef _unused(state_dir: str, kind: str, ok: list, failed: dict,",
     "tests/test_run_health.py"),

    # 감사 246 — 공개 주간 아카이브가 '그 주 마지막 하루치'를 주간 수익률로
    # 내보내던 자리. 실측 2026-08-10 주: 페이지 +0.02% / 사실 -0.02%.
    ("주 경계를 일요일 시작으로 민다 — 화면과 배치가 다른 주를 본다",
     "quant/live/daily.py",
     "    return (d - timedelta(days=d.weekday())).isoformat()",
     "    return (d - timedelta(days=(d.weekday() + 1) % 7)).isoformat()",
     "tests/test_the_weekly_archive_agrees_with_the_report.py"),
    ("주간 집계를 사이트에 안 실어 보낸다 — 아카이브가 영영 '집계 없음'이다",
     "quant/live/daily.py",
     '            status["weekly"] = wk',
     "            pass",
     "tests/test_the_weekly_archive_agrees_with_the_report.py"),

    # 감사 244 — 예비 크론이 본 크론의 성적을 지우던 자리.
    # 실측 2026-08-14: paper ok=20 → ok=0(skip=20)으로 덮여 화면에 남았다.
    ("예비 크론이 본 크론의 성적을 덮어쓴다 — 잘 돈 날이 '아무 일도 안 한 날'이 된다",
     "quant/live/daily.py",
     '    if str(prev.get("date")) == today:',
     "    if False:",
     "tests/test_the_retry_cron_does_not_erase_the_first_run.py"),

    ("이미 성공한 종목을 건너뜀으로 되돌린다 — 성공 수가 매일 0이 된다",
     "quant/live/daily.py",
     "    skip_set -= ok_set | set(failed_map)",
     "    pass",
     "tests/test_the_retry_cron_does_not_erase_the_first_run.py"),

    ("합치면서 실패를 삼킨다 — 끝까지 실패한 종목이 성공으로 남는다",
     "quant/live/daily.py",
     '    failed_map = {k: v for k, v in failed_map.items() if k not in ok_set}',
     "    failed_map = {}",
     "tests/test_the_retry_cron_does_not_erase_the_first_run.py"),

    ("어제 성적을 오늘로 끌고 온다 — 배치가 죽어도 화면은 영원히 초록이다",
     "quant/live/daily.py",
     "        entry_runs = int(prev.get(\"runs\") or 1) + 1\n    else:\n        entry_runs = 1",
     "        entry_runs = 1\n    if True:\n        ok_set |= set(prev.get(\"ok_keys\") or [])",
     "tests/test_the_retry_cron_does_not_erase_the_first_run.py"),

    ("실적 가드를 항상 비발동으로 만든다",
     "quant/data/earnings.py",
     "    if d is not None and abs((d - asof).days) <= pad_days:",
     "    if False:",
     "tests/test_earnings_guard.py"),

    ("쿨다운을 항상 통과시킨다(회전율 통제 해제)",
     "quant/live/daily.py",
     "    last = last_trade.get(key)\n    if not last:",
     "    last = None\n    if not last:",
     "tests/test_turnover_control.py"),

    # ⚠️ 처음에는 여기서 `weight = float(adj)`를 심어 '보정이 사이징에
    #    개입한다'를 흉내 내려 했는데, 그 줄은 record가 이미 만들어진
    #    **뒤**에 있어 아무것도 바꾸지 않는 무의미한 변이였다(감사 62).
    #    못 잡은 것이 아니라 부술 것이 없었던 것이다 — 변이가 실제로
    #    동작을 바꾸는지부터 확인해야 한다. 대신 '증거 없이 보정값을
    #    표시한다'를 변이한다: active 판정을 무시하면 표본이 없는
    #    확률대에도 경험 보정값이 붙어, 근거 없는 숫자가 화면에 나간다.
    ("종목별 경로의 실적 가드를 무력화한다",
     "quant/live/daily.py",
     "            weight = float(weight * ef)",
     "            pass",
     "tests/test_earnings_guard.py"),

    ("주식 대기 주문의 시가 체결을 종가 체결로 바꾼다",
     "quant/live/daily.py",
     '            key, float(pend["weight"]) * sl, fopen, eq_now,',
     '            key, float(pend["weight"]) * sl, prices.get(key, fopen), eq_now,',
     "tests/test_intrabar_next_open.py"),

    ("레짐 필터가 판단 근거를 안 남기게 한다(설명이 재계산으로 되돌아감)",
     "quant/strategies/regime.py",
     "        self.last_gate_ = gate",
     "        self.last_gate_ = None",
     "tests/test_filter_wrappers.py"),

    # ⚠️ 처음에는 event_guard가 last_gate_를 안 남기게 변이했는데 안 잡혔다.
    #    확인해 보니 **결함이 아니었다** — 설명문의 폴백이 마이너 달력과
    #    factor를 모두 정확히 다루므로, 기록이 없어도 옳은 말을 한다.
    #    (레짐 쪽은 폴백이 변동성 필터를 모르니 기록이 사라지면 틀린다.)
    #    그래서 실제 결함이었던 것을 그대로 되살린다: 설명이 주요 이벤트만
    #    보는 is_event_day로 되돌아가면 옵션만기 날 "매매 허용"이라 말한다.
    ("이벤트 설명을 주요 이벤트만 보던 옛 방식으로 되돌린다",
     "quant/live/explain.py",
     "        gate = getattr(strategy, \"last_gate_\", None)\n        if gate is None:                       # 실행 전 미리보기 폴백\n            from quant.events import event_dates",
     "        gate = None\n        if gate is None:\n            from quant.events import event_dates as _unused_ed\n            from quant.events import is_event_day\n            _d0 = df.index[-1]\n            _dd = _d0.date() if hasattr(_d0, \"date\") else _date.today()\n            gate = ({\"open\": False, \"reason\": \"이벤트 창\"} if is_event_day(_dd, pad)\n                    else {\"open\": True, \"reason\": \"오늘은 주요 이벤트 없음(매매 허용)\"})\n        if False:\n            from quant.events import event_dates",
     "tests/test_filter_wrappers.py"),

    ("코인도 진행 중인 봉으로 신호를 내게 되돌린다",
     "quant/live/daily.py",
     "            df_sig = _signal_frame(market, df, timeframe)",
     "            df_sig = df",
     "tests/test_signal_frame.py"),

    ("증거 없이도 확률 보정값을 표시한다",
     "quant/live/daily.py",
     "        if active:\n            record[\"prob_up_cal\"] = round(float(adj), 4)",
     "        if True:\n            record[\"prob_up_cal\"] = round(float(adj), 4)",
     "tests/test_drift_calibration.py"),

    # 결함 73 — 공개 게이트가 draft를 태그로 찾아 영원히 못 찾던 자리.
    # 세 OS 빌드가 다 성공한 v0.17.1이 이 한 줄 때문에 보류됐다.
    ("draft 릴리스를 태그로 조회하게 되돌린다(영원히 못 찾음)",
     "scripts/publish_release.py",
     "        batch = api(f\"/releases?per_page=100&page={page}\") or []\n"
     "        hits += [r for r in batch if r.get(\"tag_name\") == version]",
     "        one = api(f\"/releases/tags/{version}\")\n"
     "        hits += [one] if one else []",
     "tests/test_publish_release.py"),

    ("자산이 갈라진 중복 draft 중 하나를 그냥 공개한다(반쪽 릴리스)",
     "scripts/publish_release.py",
     "    if len(hits) > 1:",
     "    if False:",
     "tests/test_publish_release.py"),

    ("자산 확인 없이 공개한다(빠진 파일 무시)",
     "scripts/publish_release.py",
     "    missing = [f for f in required if f not in have]",
     "    missing = []",
     "tests/test_publish_release.py"),

    # `quant setup` — 구매자가 처음 치는 명령. 커버리지 0이었던 53줄.
    ("지키지 못한 파일 권한 약속을 지켰다고 말한다(결함 ㊾ 재발)",
     "quant/cli.py",
     "    if private:\n"
     "        print(\"   파일 권한: 600 (본인만 읽기) — 확인됨\")",
     "    if True:\n"
     "        print(\"   파일 권한: 600 (본인만 읽기) — 확인됨\")",
     "tests/test_cli_setup.py"),

    ("합성 폴백을 '거래소 연결 정상'으로 보고한다",
     "quant/cli.py",
     "            fb = bool(df.attrs.get(\"synthetic_fallback\"))",
     "            fb = False",
     "tests/test_cli_setup.py"),

    ("API 시크릿을 화면에 그대로 보이는 input으로 받는다",
     "quant/cli.py",
     "            val = (getpass.getpass(prompt) if secret else input(prompt)).strip()",
     "            val = input(prompt).strip()",
     "tests/test_cli_setup.py"),

    # 감사 74 — 밴드가 가정→실측으로 갈아타며 2.67배 뛰는데 흔적이 없던 자리.
    ("재조정 밴드 근거를 장부에서 뺀다(왜 오늘 매매가 멎었는지 알 수 없게)",
     "quant/live/daily.py",
     "              \"rebalance_band\": {m: rebalance_band_basis(m, state_dir)",
     "              \"rebalance_band\": None and {m: rebalance_band_basis(m, state_dir)",
     "tests/test_rebalance_band_basis.py"),

    ("실측 표본이 얇아도 실측 비용으로 밴드를 넓힌다(소표본 과잉반응)",
     "quant/live/daily.py",
     "        if not row or row.get(\"n\", 0) < MEASURED_COST_MIN_SAMPLES:",
     "        if not row:",
     "tests/test_rebalance_band_basis.py"),

    # 감사 75 — do_GET의 라우트 분기 79줄이 미실행이었다. 누른 버튼과 도는
    # 계산이 어긋나도 아무 검사가 실패하지 않았다.
    ("웹 조종석에서 '최적화'를 누르면 스윕이 돌게 한다(라우트 교차)",
     "quant/web/server.py",
     "                self._send(run_optimize_html(params))",
     "                self._send(run_sweep_html(params))",
     "tests/test_web_routes.py"),

    # 감사 76 — 팔아서 돈을 받은 라이선스 키를 0o644로 저장하던 자리.
    # .env의 API 키는 ㊾에서 조여 놓고 정작 파는 물건이 열려 있었다.
    ("구매자의 라이선스 키를 남도 읽을 수 있게 저장한다",
     "quant/licensing.py",
     "                private = write_private(path, f\"owner: {owner}\\nkey:   {key}\\n\")",
     "                private = True; path.write_text(f\"owner: {owner}\\nkey:   {key}\\n\", encoding=\"utf-8\")",
     "tests/test_license_prompt.py"),

    ("남에게 발급된 키도 통과시킨다(1인 1키 붕괴)",
     "quant/licensing.py",
     "        if owner and key and verify_key(owner, key):",
     "        if owner and key:",
     "tests/test_license_prompt.py"),

    # 감사 78 — 노출을 키워도 되는지 판정하는 유일한 관문.
    # 커버리지 25줄 중 22줄이 미실행이었다(판정 로직 자체가 미검사).
    ("'운 좋은 승자'도 엣지 입증으로 인정한다(신뢰구간 하한 무시)",
     "quant/risk/portfolio_vol.py",
     "        if lo <= 0.5:",
     "        if False:",
     "tests/test_edge_proven_gate.py"),

    ("표본이 얇아도 엣지 입증으로 인정한다",
     "quant/risk/portfolio_vol.py",
     "        if n < MIN_EDGE_SAMPLES:",
     "        if False:",
     "tests/test_edge_proven_gate.py"),

    ("90일 판정 시계를 안 기다리고 노출을 푼다",
     "quant/risk/portfolio_vol.py",
     "        if gen[\"days\"] < gen[\"target_days\"]:",
     "        if False:",
     "tests/test_edge_proven_gate.py"),

    ("통합 계좌 장부까지 세어 방향 표본을 부풀린다(같은 매매 이중 계상)",
     "quant/risk/portfolio_vol.py",
     "            if str(st.get(\"market\", \"\")).startswith(\"portfolio\"):\n"
     "                continue",
     "            if False:\n"
     "                continue",
     "tests/test_edge_proven_gate.py"),

    ("판정에 실패하면 '입증'으로 넘어간다(모를 때 잠그지 않는다)",
     "quant/risk/portfolio_vol.py",
     "        return False, f\"판정 불가({exc})\"",
     "        return True, f\"판정 불가({exc})\"",
     "tests/test_edge_proven_gate.py"),

    # 감사 79 — LiveTrader.step 24줄 미실행. 부품(KillSwitch·is_market_open)은
    # 검사돼 있었지만 그 부품이 주문 경로에 꽂혀 있는지는 아무도 안 봤다.
    ("닫힌 시장에도 주문을 낸다(장 시간 가드 무력화)",
     "quant/live/engine.py",
     "            if not is_market_open(self.market, holidays=_hol):",
     "            if False:",
     "tests/test_engine_step_guards.py"),

    ("단일 종목 루프의 킬스위치를 무력화한다",
     "quant/live/engine.py",
     "        if self.kill_switch is not None and self.kill_switch.update(equity):",
     "        if False:",
     "tests/test_engine_step_guards.py"),

    ("단일 종목 루프의 서킷브레이커를 무력화한다",
     "quant/live/engine.py",
     "            if self.circuit_breaker.update(equity, day):",
     "            if False:",
     "tests/test_engine_step_guards.py"),

    # 감사 80 — "전 종목 청산"이라 말하고 시세 받은 종목만 비우던 자리.
    ("킬스위치가 시세 받은 종목만 청산한다(나머지는 열린 채 남는다)",
     "quant/live/multi.py",
     "        for s in self.symbols:\n"
     "            try:\n"
     "                held = float(self.broker.get_position(s).quantity)",
     "        for s in list(prices):\n"
     "            try:\n"
     "                held = float(self.broker.get_position(s).quantity)",
     "tests/test_multi_killswitch_liquidation.py"),

    ("못 비운 종목을 장부·알림에서 지운다(반쪽 청산을 완전 청산으로 보고)",
     "quant/live/multi.py",
     "        self._kill_unflattened = unflat",
     "        self._kill_unflattened = []; unflat = []",
     "tests/test_multi_killswitch_liquidation.py"),

    ("서킷브레이커 청산만 옛 방식으로 되돌린다(같은 규칙을 두 곳에 적기)",
     "quant/live/multi.py",
     "                self._flatten_all(prices, equity, \"서킷브레이커\")",
     "                [self.broker.target_weight(s, 0.0, p, equity)\n"
     "                 for s, p in prices.items() if p]",
     "tests/test_multi_killswitch_liquidation.py"),

    # 감사 81 — 한 종목 주문 실패가 나머지 주문과 그날 기록을 통째로 날리던 자리.
    ("한 종목 주문이 거부되면 나머지 주문과 그날 기록을 통째로 버린다",
     "quant/live/multi.py",
     "            except Exception as exc:  # noqa: BLE001 — 한 종목 실패가 전체를 막지 않게\n"
     "                log.error(\"주문 실패(%s): %s\", s, exc)\n"
     "                failed.append(f\"{s}({type(exc).__name__})\")\n"
     "                continue",
     "            except Exception:\n"
     "                raise",
     "tests/test_multi_killswitch_liquidation.py"),

    # 감사 82 — 어드민 전역 스위치가 웹훅 주문 경로를 덮지 않던 자리.
    ("어드민 '일시정지' 중에도 웹훅 알림으로 주문을 낸다",
     "quant/live/webhook.py",
     "        if bool(settings.get(\"trading_paused\")):",
     "        if False:",
     "tests/test_webhook_owner_switches.py"),

    ("총노출 배수를 웹훅 주문에는 적용하지 않는다",
     "quant/live/webhook.py",
     "            weight *= float(settings.get(\"exposure_scale\", 1.0))",
     "            pass",
     "tests/test_webhook_owner_switches.py"),

    ("웹훅에서도 닫힌 시장에 주문을 낸다",
     "quant/live/webhook.py",
     "            if not is_market_open(self.market, holidays=_hol):",
     "            if False:",
     "tests/test_webhook_owner_switches.py"),

    # 감사 83 — 어드민 전역 스위치가 연속 실행 루프(quant live --real)를
    # 덮지 않던 자리. 규칙이 경로마다 따로 적혀 있어 세 곳이 뒤처져 있었다.
    ("quant live(단일 종목)가 어드민 일시정지를 무시한다",
     "quant/live/engine.py",
     "        if paused:\n"
     "            log.info(\"⏸ 어드민 일시정지 — 신규 주문 없음(보유 유지)\")\n"
     "            return",
     "        if False:\n"
     "            log.info(\"⏸ 어드민 일시정지 — 신규 주문 없음(보유 유지)\")\n"
     "            return",
     "tests/test_engine_step_guards.py"),

    ("quant live가 총노출 배수를 무시한다",
     "quant/live/engine.py",
     "        weight *= exposure",
     "        pass",
     "tests/test_engine_step_guards.py"),

    ("다종목 루프가 어드민 일시정지를 무시한다",
     "quant/live/multi.py",
     "        if paused:\n"
     "            log.info(\"⏸ 어드민 일시정지 — 신규 주문 없음(보유 유지)\")\n"
     "            return",
     "        if False:\n"
     "            log.info(\"⏸ 어드민 일시정지 — 신규 주문 없음(보유 유지)\")\n"
     "            return",
     "tests/test_multi_killswitch_liquidation.py"),

    # 감사 84 — 룩어헤드 차단막. quant verify가 과거 결정을 재현할 때
    # 미래 봉을 못 보게 막는 자리인데 커버리지 0이었다.
    ("주식 시세에서 end 이후 봉을 안 자른다(검증이 미래 데이터로 통과)",
     "quant/data/stock.py",
     "    if end is not None:\n"
     "        df = df[df.index <= _align_ts(pd.Timestamp(end), df.index)]",
     "    if end is not None:\n"
     "        pass",
     "tests/test_stock_range_cut.py"),

    ("시간대 정렬을 없앤다(분봉에서 TypeError → 조용한 합성 폴백)",
     "quant/data/stock.py",
     "    if tz is not None and ts.tzinfo is None:\n"
     "        return ts.tz_localize(tz)                       # naive ts → 인덱스 tz",
     "    if False:\n"
     "        return ts.tz_localize(tz)",
     "tests/test_stock_range_cut.py"),

    # 감사 85 — 거래소가 전부 실패하면 GBM 난수 걷기(시작가 100)가 오는데,
    # 연속 실행 루프는 그걸 걸러내지 않았다. 실제 BTC 6천만 원 기준 주문
    # 수량이 60만 배 틀린다 — 존재하지 않는 시장에 대고 매매하는 셈이다.
    ("합성 폴백 시세를 매매 가능한 데이터로 통과시킨다",
     "quant/data/guard.py",
     "    if require_real_data and attrs.get(\"synthetic_fallback\"):",
     "    if False:",
     "tests/test_synthetic_fallback_never_trades.py"),

    ("quant live(단일 종목)가 데이터 검문을 건너뛴다",
     "quant/live/engine.py",
     "        why = unusable_reason(df, require_real_data=self.require_real_data)",
     "        why = None if len(df) else \"데이터 없음\"",
     "tests/test_synthetic_fallback_never_trades.py"),

    ("다종목 루프가 데이터 검문을 건너뛴다",
     "quant/live/multi.py",
     "            why = unusable_reason(df, require_real_data=self.require_real_data)",
     "            why = None if len(df) else \"데이터 없음\"",
     "tests/test_synthetic_fallback_never_trades.py"),

    ("웹훅이 합성 폴백 가격으로 주문 수량을 정한다",
     "quant/data/guard.py",
     "    if unusable_reason(df, check_quality=False):\n        return 0.0",
     "    if False:\n        return 0.0",
     "tests/test_synthetic_fallback_never_trades.py"),

    # 감사 86 — 공개한 글의 아카이브를 조용히 덮어쓰던 자리.
    ("이미 공개한 날의 SNS 캡션을 경고 없이 덮어쓴다(과거를 고친다)",
     "quant/reporting/social.py",
     "        if changed:",
     "        if False:",
     "tests/test_social_archive_immutable.py"),

    # 감사 87 — 실거래 집행 바로 앞 관문이 종료코드로 실패를 말하지 않던 자리.
    ("실거래 준비 진단이 미비해도 성공으로 끝난다(관문이 안 막는다)",
     "quant/cli.py",
     "    raise SystemExit(\n"
     "        \"\\n❌ 미비 항목이 있습니다 — 'python -m quant setup'으로 키를 \"",
     "    print(\n"
     "        \"\\n❌ 미비 항목이 있습니다 — 'python -m quant setup'으로 키를 \"",
     "tests/test_live_check_gates.py"),

    ("점검 항목이 0건이어도 '준비 완료'로 통과시킨다",
     "quant/cli.py",
     "    if not rows:",
     "    if False:",
     "tests/test_live_check_gates.py"),

    # 감사 88 — 실거래 집행 단계의 파이프가 실패를 가리던 자리.
    ("실거래 집행 단계에서 pipefail을 없앤다(실패해도 잡이 초록)",
     ".github/workflows/kr-live.yml",
     "        shell: bash\n        run: |\n          if [ \"$IN_REAL\" = \"true\" ]; then",
     "        run: |\n          if [ \"$IN_REAL\" = \"true\" ]; then",
     "tests/test_workflow_timeouts.py"),

    # 감사 89 — 사이트의 '20종목' 주장이 실제 유니버스와 연결돼 있지 않던 자리.
    # 기존 검사는 코드(len==20)와 HTML("20종목")을 **따로** 고정해, 유니버스를
    # 바꾸면 사이트만 옛 숫자를 말한 채 통과했다.
    ("사이트가 실제 유니버스와 다른 종목 수를 말한다",
     "docs/index.html",
     '매일 새벽 확정 기록 · 20종목',
     '매일 새벽 확정 기록 · 25종목',
     "tests/test_site_numbers_track_the_code.py"),

    # 감사 90 — 어드민이 '코드 기본값'을 산문에 박아, 코드가 바뀌면
    # 사장님이 위험을 정하는 화면이 거짓말을 하던 자리.
    ("목표 변동성 기본값을 바꿔도 어드민 안내가 뒤처지지 않는가",
     "quant/risk/portfolio_vol.py",
     "VERIFY_TARGET_VOL = 0.12",
     "VERIFY_TARGET_VOL = 0.10",
     "tests/test_site_numbers_track_the_code.py"),

    # ── 2026-08-14 · 적중률이 표본이 감당 못 하는 단정을 하던 자리 ──────
    #
    # 사장님: "64% n=11 솔라나의 적중률은 이런 식으로 잘못 나오고 있어."
    # 20종목 중 19개의 95% 구간이 50%를 품고 있었는데, 화면은 그 비율을
    # 단정으로 내보내고 있었다. 옛 규칙('n<20이면 흐리게')은 n=81짜리
    # 60%를 그냥 통과시켰다 — **n이 아니라 구간이 판정한다.**

    ("판정 기준을 표본 크기로 되돌린다(n=81짜리 60%가 단정으로 나간다)",
     "quant/robustness/accuracy.py",
     "    return not (lo <= COIN_FLIP <= hi)",
     "    return n >= 20",
     "tests/test_the_hit_rate_says_only_what_the_sample_supports.py"),

    ("표본 없는 구간을 판정 가능으로 센다(n=0이 '실력'이 된다)",
     "quant/robustness/accuracy.py",
     "    if lo != lo or hi != hi:            # NaN — 표본 없음\n        return False",
     "    if lo != lo or hi != hi:            # NaN — 표본 없음\n        return True",
     "tests/test_the_hit_rate_says_only_what_the_sample_supports.py"),

    ("표본 미상 기록을 그냥 비율로 내보낸다(옛 기록이 확신처럼 읽힌다)",
     "quant/robustness/accuracy.py",
     'return f"{r:.0%} (표본 미상)"',
     'return f"{r:.0%}"',
     "tests/test_the_hit_rate_says_only_what_the_sample_supports.py"),

    ("판정 불가인데 '판정 불가'를 안 붙인다",
     "quant/robustness/accuracy.py",
     'return f"{r:.0%} (판정 불가 {band} · n={n})"',
     'return f"{r:.0%} ({band} · n={n})"',
     "tests/test_the_hit_rate_says_only_what_the_sample_supports.py"),

    ("최근 적중률의 분모를 안 남긴다(표본 없이 단정하게 된다)",
     "quant/live/autolearn.py",
     '            "recent_n": recent_n,                 # 그 비율의 분모(채점된 봉)\n',
     "",
     "tests/test_the_hit_rate_says_only_what_the_sample_supports.py"),

    ("화면 쪽 판정만 되돌린다(파이썬과 갈라져 페이지마다 다른 확신)",
     "docs/assets/hitrate.js",
     "    return !(ci[0] <= COIN_FLIP && COIN_FLIP <= ci[1]);",
     "    return n >= 20;",
     "tests/test_the_hit_rate_says_only_what_the_sample_supports.py"),

    ("옛 기록을 되계산하지 않는다(표본 있는 옛 기록이 단정으로 나간다)",
     "docs/assets/hitrate.js",
     '    if (typeof sure !== "boolean" && n !== null) {   // 옛 기록 보정',
     '    if (false) {   // 옛 기록 보정',
     "tests/test_the_hit_rate_says_only_what_the_sample_supports.py"),

    ("조종석이 공용 규칙 파일을 안 싣는다(5초 뒤 옛 서식으로 되돌아간다)",
     "quant/web/app.py",
     'f\'{_inline_asset("hitrate.js")}\'\n',
     "",
     "tests/test_the_hit_rate_says_only_what_the_sample_supports.py"),

    # ── 2026-08-14 · 첫 화면에서 종목을 눌러도 차트가 없던 자리 ──────────
    #
    # 매핑이 today.html 안에만 있었다. 사본을 만들면 상장 시장이 바뀔 때
    # 한쪽만 고쳐지고, 매핑이 틀리면 차트는 **조용히** 안 뜬다.





    # ── 2026-08-14 · 시작금이 8만원에서 100만원으로, 이름도 함께 ─────────
    #
    # 사장님: "모든 페이지를 확인해서 더이상 8마일이 아닌 100만원으로
    #          시작한다는걸로 업데이트 해줘"
    #
    # 장부는 2026-08-13부터 이미 100만원이었는데 코드 상수만 8만원에
    # 멈춰 있었다. 화면은 장부를 먼저 읽으므로(감사 218) 겉으로는 안
    # 드러났지만, 계좌를 새로 만드는 경로는 전부 이 상수를 쓴다.

    ("시작금 상수를 8만원으로 되돌린다(새 계좌가 계좌와 다른 원금으로 생긴다)",
     "quant/live/ledger_basics.py",
     "PORTFOLIO_START_CASH = 1_000_000.0",
     "PORTFOLIO_START_CASH = 80_000.0",
     "tests/test_daily_paper.py"),

    ("첫 화면 기본 원금만 8만원으로 되돌린다(장부를 못 읽는 순간 갈라진다)",
     "docs/index.html",
     "const h=pf.history,base=pf.start_cash||1000000;",
     "const h=pf.history,base=pf.start_cash||80000;",
     "tests/test_site_numbers_track_the_code.py"),

    ("산문에 옛 시작금을 다시 박는다(사이트가 계좌와 다른 말을 한다)",
     "docs/index.html",
     "100만 챌린지 · 통합 실기록",
     "8만원으로 시작하는 실기록",
     "tests/test_site_provenance.py"),

    ("캡션이 장부 원금 대신 코드 기본값을 쓴다(재개설 뒤 옛 금액이 방송된다)",
     "quant/reporting/social.py",
     '    _p = x.get("principal")\n',
     "    _p = None\n",
     "tests/test_sns_provenance.py"),


    # ── 2026-08-14 · 내 자료로 전략 넣기 (PDF·유튜브·트레이딩뷰) ─────────
    #
    # 사장님: "각 유저마다 투자 관련한 자료를 넣으면 그 전략이 적용되게끔도
    #          할 수 있어?"
    #
    # 이 기능의 가장 큰 위험은 **없는 규칙을 지어내는 것**이고, 두 번째는
    # **후보를 늘리면서 다중검정 보정을 안 올리는 것**이다. 둘 다 조용히
    # 일어나고, 둘 다 이 제품의 심장을 끈다.

    ("규칙이 없는 자료에서도 전략을 만들어 낸다(지어낸 전략을 사용자 것이라 한다)",
     "quant/ingest/extract.py",
     "    if not entry:\n",
     "    if False:\n",
     "tests/test_only_real_rules_become_strategies.py"),

    ("근거 문장 없이도 조건을 만든다(자료에서 뽑았다는 말이 거짓이 된다)",
     "quant/ingest/spec.py",
     "    if not str(c.quote).strip():",
     "    if False:",
     "tests/test_only_real_rules_become_strategies.py"),

    ("명세로 레버리지를 들여올 수 있게 한다",
     "quant/ingest/spec.py",
     "        if not (0.0 < float(self.weight) <= 1.0):",
     "        if not (0.0 < float(self.weight) <= 100.0):",
     "tests/test_only_real_rules_become_strategies.py"),

    ("돌파만 있고 청산이 없는 명세를 통과시킨다(하루 들고 파는 전략이 된다)",
     "quant/ingest/spec.py",
     "        if self.entry and all(c.op in _EVENTS for c in self.entry) and not self.exit:",
     "        if False:",
     "tests/test_only_real_rules_become_strategies.py"),

    ("신고가에 오늘 고가를 포함시킨다(조건이 늘 참이 되어 매일 산다)",
     "quant/ingest/spec.py",
     '        return df["high"].astype(float).rolling(p).max().shift(1)',
     '        return df["high"].astype(float).rolling(p).max()',
     "tests/test_only_real_rules_become_strategies.py"),

    ("매도 문장을 매수 조건으로 넣는다(정반대로 매매한다)",
     "quant/ingest/extract.py",
     "    if sell and not buy:\n        return None, cond\n    if buy and not sell:\n        return cond, None\n    # 한 문장에 둘 다",
     "    if True:\n        return cond, None\n    if buy and not sell:\n        return cond, None\n    # 한 문장에 둘 다",
     "tests/test_only_real_rules_become_strategies.py"),

    ("사용자 전략을 링에 안 세운다(등록해도 한 번도 심사받지 않는다)",
     "quant/live/retrain.py",
     "    challengers += _user_specs(state_dir)\n",
     "",
     "tests/test_ingested_specs_must_win_the_audition.py"),

    ("사용자 전략 수에 상한을 없앤다(한 사람의 자료가 전체 진화를 멈춘다)",
     "quant/ingest/registry.py",
     "MAX_USER_CHALLENGERS = 12",
     "MAX_USER_CHALLENGERS = 500",
     "tests/test_ingested_specs_must_win_the_audition.py"),

    ("깨진 명세 파일을 조용히 건너뛴다(안 서는 전략을 선다고 믿게 된다)",
     "quant/ingest/registry.py",
     '            problems.append(f"{fp.name}: {exc}")',
     "            pass",
     "tests/test_ingested_specs_must_win_the_audition.py"),

    ("재현할 때 장부 대신 오늘 폴더를 읽는다(어제를 오늘 자료로 재현한다)",
     "quant/live/retrain.py",
     '        challengers += list(rec.get("user_specs") or [])',
     "        pass",
     "tests/test_ingested_specs_must_win_the_audition.py"),


    # ── 2026-08-14 · 선물 준비 ①②③④ — 레버리지를 열기 전에 관문부터 ────
    #
    # 사장님: "모두 순서대로 가장 이상적이고 영구적으로 진행해줘."
    #
    # 이 저장소가 이번 주 내내 고친 결함은 전부 "선언만 돼 있고 안 막는 장치"
    # 였다. 레버리지는 그 결함이 나면 **계좌가 없어지는** 영역이다.

    ("청산 관문을 자주 보는 것만으로 뚫리게 한다(점프 바닥 제거)",
     "quant/risk/liquidation.py",
     "    return max(floor, float(daily_vol) * scale * float(sigma))",
     "    return float(daily_vol) * scale * float(sigma)",
     "tests/test_liquidation_cannot_beat_the_killswitch.py"),

    ("모르는 시장에 가장 관대한 점프 바닥을 준다",
     "quant/risk/liquidation.py",
     "DEFAULT_JUMP_FLOOR = 0.20   # 모르면 가장 나쁜 쪽",
     "DEFAULT_JUMP_FLOOR = 0.02   # 모르면 가장 나쁜 쪽",
     "tests/test_liquidation_cannot_beat_the_killswitch.py"),

    ("변동성을 모르는데 레버리지를 통과시킨다(모름을 안전으로 읽는다)",
     "quant/risk/liquidation.py",
     "        if leverage <= 1.0:\n            return Headroom(True, x_liq, 0.0, float(\"inf\"), measured,",
     "        if True:\n            return Headroom(True, x_liq, 0.0, float(\"inf\"), measured,",
     "tests/test_liquidation_cannot_beat_the_killswitch.py"),

    ("여유 배수를 1배로 낮춘다(이론상 아슬아슬하게 사는 것을 통과로 친다)",
     "quant/risk/liquidation.py",
     "SAFETY_FACTOR = 2.0",
     "SAFETY_FACTOR = 1.0",
     "tests/test_liquidation_cannot_beat_the_killswitch.py"),

    ("파산을 최종 자산으로만 판정한다(도중에 죽은 경로가 무사가 된다)",
     "quant/robustness/ruin.py",
     "    ruined = (equity <= ruin_level).any(axis=1)    # **경로 어느 지점에서든**",
     "    ruined = equity[:, -1] <= ruin_level",
     "tests/test_a_good_average_can_still_go_bankrupt.py"),

    ("블록 부트스트랩을 하루 단위로 바꾼다(뭉친 하락이 흩어져 안전해 보인다)",
     "quant/robustness/ruin.py",
     "    block = max(5, min(20, r.size // 10))          # 연속 하락을 살리는 블록 길이",
     "    block = 1",
     "tests/test_a_good_average_can_still_go_bankrupt.py"),

    ("표본이 모자라도 파산확률을 통과시킨다",
     "quant/robustness/ruin.py",
     "    if r.size < 30:",
     "    if False:",
     "tests/test_a_good_average_can_still_go_bankrupt.py"),

    ("파산 허용 기준을 느슨하게 한다(관문이 장식이 된다)",
     "quant/robustness/ruin.py",
     "RUIN_PASS = 0.01",
     "RUIN_PASS = 0.50",
     "tests/test_a_good_average_can_still_go_bankrupt.py"),

    ("감시 간격을 실측이 아니라 설정값으로 쓴다(밀린 회차를 못 본다)",
     "quant/live/guard.py",
     "    if now_iso:\n",
     "    if False:\n",
     "tests/test_leverage_stays_locked_until_all_three_gates_pass.py"),

    ("심장박동이 모자라도 간격을 0으로 친다(모름을 '완벽한 감시'로 읽는다)",
     "quant/live/guard.py",
     "    if len(stamps) < MIN_BEATS_FOR_GAP:\n        return None",
     "    if len(stamps) < MIN_BEATS_FOR_GAP:\n        return 0.0",
     "tests/test_leverage_stays_locked_until_all_three_gates_pass.py"),

    ("장중 감시가 킬스위치 규칙을 자기가 다시 적는다(새벽 배치와 갈라진다)",
     "quant/live/guard.py",
     "    from quant.live.daily import _kill_switch_scale\n",
     "    _kill_switch_scale = lambda prev, dd: 1.0 if dd > -0.25 else 0.0\n",
     "tests/test_leverage_stays_locked_until_all_three_gates_pass.py"),

    ("감시 실적이 없어도 레버리지를 연다",
     "quant/risk/leverage_gate.py",
     '        return LeverageDecision(1.0, "장중 감시 실적 없음", checks)',
     "        observed = 1.0",
     "tests/test_leverage_stays_locked_until_all_three_gates_pass.py"),

    ("파산확률을 못 재도 레버리지를 연다",
     "quant/risk/leverage_gate.py",
     '        return LeverageDecision(1.0, "파산확률 미측정", checks)',
     "        ruin_cap = HARD_CAP",
     "tests/test_leverage_stays_locked_until_all_three_gates_pass.py"),

    ("절대 상한을 없앤다(모든 가정이 동시에 낙관적일 때 막을 것이 없다)",
     "quant/risk/leverage_gate.py",
     "HARD_CAP = 3.0",
     "HARD_CAP = 1000.0",
     "tests/test_leverage_stays_locked_until_all_three_gates_pass.py"),

    ("관문 중 가장 큰 값을 쓴다(제일 약한 고리가 아니라 제일 관대한 것을 따른다)",
     "quant/risk/leverage_gate.py",
     "    cap, binding = min(limits, key=lambda x: x[0])",
     "    cap, binding = max(limits, key=lambda x: x[0])",
     "tests/test_leverage_stays_locked_until_all_three_gates_pass.py"),

    ("장중 감시가 노출 축소를 장부에 안 적는다(다음 배치가 되돌린다)",
     "quant/cli.py",
     '        st["risk_scale"] = v.scale\n',
     "",
     "tests/test_leverage_stays_locked_until_all_three_gates_pass.py"),


    # ── 2026-08-15 · 미뤄 뒀던 것 정리 ────────────────────────────────
    ("워크플로가 선택 의존성을 버전 없이 덧붙인다(그날 PyPI 최신을 받는다)",
     ".github/workflows/daily-paper.yml",
     "pip install -r requirements.txt -r requirements-extra.txt",
     "pip install -r requirements.txt pykrx",
     "tests/test_declared_dependencies_match_reality.py"),

    ("선택 의존성 파일에서 버전 범위를 뗀다",
     "requirements-extra.txt",
     "pykrx>=1.0,<2            # KRX 투자자별 순매수 → x_frgn5·x_inst5",
     "pykrx            # KRX 투자자별 순매수 → x_frgn5·x_inst5",
     "tests/test_declared_dependencies_match_reality.py"),

    ("전 종목 검증 리포트를 한 파일에 덮어쓴다(마지막 종목 것만 남는다)",
     "quant/cli.py",
     '                one.report = str(rp.with_name(f"{rp.stem}_{safe}{rp.suffix}"))',
     "                pass",
     "tests/test_the_validation_gate_actually_gates.py"),


    # ── 감사 256 — 긴 검증(워크포워드)과 생존 편향 고지 ─────────────
    # 학습창은 250봉 그대로 두고 검증 구간만 과거 전체로 넓힌 관찰값.
    # 이 숫자는 오늘 살아남은 종목으로만 계산하므로 반드시 고지가 붙어야 한다.
    ("학습창 구간을 성적에 넣는다(아직 시작 안 한 0이 무성과로 찍힌다)",
     "quant/live/walkforward.py",
     "    oos = returns.iloc[warmup:] if warmup > 0 else returns",
     "    oos = returns",
     "tests/test_the_long_check_says_it_is_biased.py"),

    ("구간 수를 표본과 무관하게 고정한다(50봉을 8등분한다)",
     "quant/live/walkforward.py",
     "    k = max(1, min(int(segments), n // MIN_SEGMENT_BARS))",
     "    k = int(segments)",
     "tests/test_the_long_check_says_it_is_biased.py"),

    ("샤프 판정을 절대 비교로 되돌린다(상쇄된 1e-19로 나눠 샤프 수천이 나온다)",
     "quant/live/walkforward.py",
     "    if not math.isfinite(sd) or degenerate_spread(sd, float(returns.abs().mean())):",
     "    if not math.isfinite(sd) or sd <= 0:",
     "tests/test_the_long_check_says_it_is_biased.py"),

    ("합성 폴백으로 10년 성적을 만든다(가짜 시세로 만든 그럴듯한 거짓말)",
     "quant/live/walkforward.py",
     '    if df is None or df.empty or df.attrs.get("synthetic_fallback"):',
     "    if df is None or df.empty:",
     "tests/test_the_long_check_says_it_is_biased.py"),

    ("주간 보고서가 '대결 안 열림'을 세지 않는다(승격 0회와 구별이 사라진다)",
     "quant/live/daily.py",
     '                    auditions["vacuous"] += 1',
     '                    auditions["vacuous"] += 0',
     "tests/test_an_empty_audition_reaches_the_report.py"),

    # ── 감사 261 — 800봉을 다 받고도 최신 165일을 못 받았다(실전 사고) ──
    ("이어받기를 개수로 멈춘다(가장 오래된 800봉만 받고 최근 165일을 버린다)",
     "quant/data/crypto.py",
     "        if (last_ts + step > now_ms) if tail else (len(rows) >= limit):\n"
     "            break",
     "        if len(rows) >= limit:\n"
     "            break",
     "tests/test_the_bars_reach_today.py"),

    ("페이지 요청을 남은 개수로 조른다(마지막 페이지가 잘려 최신 봉을 놓친다)",
     "quant/data/crypto.py",
     "        page = client.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor,\n"
     "                                  limit=limit if tail else limit - len(rows))",
     "        page = client.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor,\n"
     "                                  limit=limit - len(rows))",
     "tests/test_the_bars_reach_today.py"),

    # ── 감사 260 — 증거금 없는 무제한 공매도가 열려 있었다 ─────────────
    ("보유를 넘어서는 매도를 그냥 체결한다(100만원 계좌가 5,000만원어치 숏)",
     "quant/broker/paper.py",
     "            if quantity > allowance + _DUST:",
     "            if False:",
     "tests/test_a_naked_short_is_not_free.py"),

    ("증거금 없이도 숏을 조금 열어 준다(기본이 금지가 아니게 된다)",
     "quant/broker/paper.py",
     "            allowance = max(0.0, old_qty)          # 팔 수 있는 보유 수량",
     "            allowance = max(0.0, old_qty) + 1e9",
     "tests/test_a_naked_short_is_not_free.py"),

    ("초과 매도를 통째로 거부한다(청산이 막혀 덫이 된다)",
     "quant/broker/paper.py",
     "                quantity = allowance",
     "                quantity = 0.0",
     "tests/test_a_naked_short_is_not_free.py"),

    ("증거금 한도를 무시한다(50%를 줘도 무한정 열린다)",
     "quant/broker/paper.py",
     "                allowance += max(0.0, self._cash) / (price * self.short_margin)",
     "                allowance += 1e9",
     "tests/test_a_naked_short_is_not_free.py"),

    ("한국 대주료를 미국 수준으로 낮춘다(개인이 못 빌리는 것을 싸게 친다)",
     "quant/backtest/costs.py",
     "_BORROW_KR = 0.025 / 252       # 한국 개인 대주 ~연 2.5% (가능할 때)",
     "_BORROW_KR = 0.0001 / 252",
     "tests/test_a_naked_short_is_not_free.py"),

    ("대차료를 0으로 되돌린다(숏을 공짜로 무한정 들고 있게 된다)",
     "quant/backtest/costs.py",
     "_BORROW_US = 0.0025 / 252      # 미국 대형주 일반 대차 ~연 0.25%",
     "_BORROW_US = 0.0",
     "tests/test_a_naked_short_is_not_free.py"),

    # ── 감사 259 — 횡단면 랭킹("오를까"가 아니라 "누가 더 셀까") ────────
    ("스냅샷 폴더를 넘겨받은 데이터의 마지막 봉으로 고른다(미래를 자르면 과거가 바뀐다)",
     "quant/strategies/cross_rank.py",
     "            frames = load_snapshot_pool_day(\n"
     "                self.state_dir, fullest_snapshot_day(self.state_dir))",
     "            from quant.utils.repro import load_snapshot_pool\n"
     "            frames = load_snapshot_pool(self.state_dir, str(index[-1])[:10])",
     "tests/test_lookahead_challenger_ring.py"),

    ("또래 시세를 뒤채움으로 맞춘다(내일 가격이 오늘 순위에 실린다 = 룩어헤드)",
     "quant/strategies/cross_rank.py",
     "            cols[f\"p{i}\"] = mom.reindex(mom.index.union(index)).ffill().reindex(index)",
     "            cols[f\"p{i}\"] = mom.reindex(mom.index.union(index)).bfill().reindex(index)",
     "tests/test_the_ranking_cannot_see_tomorrow.py"),

    ("순위 부등호를 뒤집는다(가장 약한 종목을 산다)",
     "quant/strategies/cross_rank.py",
     "        below = mat.lt(mine, axis=0).sum(axis=1)",
     "        below = mat.gt(mine, axis=0).sum(axis=1)",
     "tests/test_the_ranking_cannot_see_tomorrow.py"),

    ("상위 컷을 무시하고 늘 산다(순위가 아니라 그냥 보유가 된다)",
     "quant/strategies/cross_rank.py",
     "        w[known & (pct >= (1.0 - self.top_frac))] = 1.0",
     "        w[known] = 1.0",
     "tests/test_the_ranking_cannot_see_tomorrow.py"),

    ("순위가 성립 안 하는 봉을 그냥 판단한다(모르는 구간에서 최대 숏을 잡는다)",
     "quant/strategies/cross_rank.py",
     "        known = mine.notna() & (valid > 0)",
     "        known = mine.notna() | (valid >= 0)",
     "tests/test_the_ranking_cannot_see_tomorrow.py"),

    ("또래가 없어도 순위를 지어낸다(혼자서 1등이 된다)",
     "quant/strategies/cross_rank.py",
     "        if len(cols) < self.min_peers:\n            return None",
     "        if False:\n            return None",
     "tests/test_the_ranking_cannot_see_tomorrow.py"),

    ("말이 안 되는 상위 비율을 조용히 받는다(0%면 아무것도 안 산다)",
     "quant/strategies/cross_rank.py",
     "        if not 0.0 < float(top_frac) <= 1.0:",
     "        if False:",
     "tests/test_the_ranking_cannot_see_tomorrow.py"),

    ("횡단면 후보에서 숏을 몰래 켠다(체결·차입비용 검증 없이 실전과 벌어진다)",
     "quant/strategies/cross_rank.py",
     "        self.allow_short = bool(allow_short)",
     "        self.allow_short = True",
     "tests/test_the_ranking_cannot_see_tomorrow.py"),

    ("횡단면 전략을 링에서 뺀다(만들어 놓고 아무도 안 부른다)",
     "quant/live/retrain.py",
     '    {"strategy": "cross_rank", "params": {"lookback": 20, "top_frac": 0.3}},',
     "",
     "tests/test_the_ranking_cannot_see_tomorrow.py"),

    # ── 감사 258 — 장부가 아무도 넘은 적 없는 문턱을 적고 있었다 ───────
    ("장부가 조정 전 문턱을 적는다(175/175건이 '선발 t≥2.52'였다)",
     "quant/live/retrain.py",
     '        "select_t_used": round(effective_select_t(select_t_eff, confirm_t_eff), 3),',
     '        "select_t_used": round(select_t_eff, 3),',
     "tests/test_the_ledger_records_the_threshold_it_used.py"),

    ("화면이 조정 전 문턱을 찍는다(매일 틀린 숫자로 판단하게 된다)",
     "quant/live/retrain.py",
     "    select_t_used = effective_select_t(select_t_eff, confirm_t_eff)",
     "    select_t_used = select_t_eff",
     "tests/test_the_ledger_records_the_threshold_it_used.py"),

    ("문턱 조정을 늘 건다(선별기가 결승보다 느슨해도 끌어내린다)",
     "quant/live/retrain.py",
     "    if clamp_screen and select_t > confirm_t:\n        return float(confirm_t)",
     "    if clamp_screen:\n        return float(confirm_t)",
     "tests/test_the_ledger_records_the_threshold_it_used.py"),

    ("옛 관문(gate_version 1)까지 조정한다(과거 결정이 재현되지 않는다)",
     "quant/live/retrain.py",
     "def effective_select_t(select_t: float, confirm_t: float,\n"
     "                       clamp_screen: bool = True) -> float:",
     "def effective_select_t(select_t: float, confirm_t: float,\n"
     "                       clamp_screen: bool = False) -> float:",
     "tests/test_the_ledger_records_the_threshold_it_used.py"),

    # ── 감사 257 — 대조군 없는 성적표 · 안 흔든 사이징 축 ─────────────
    ("긴 검증에서 '그냥 보유' 대조군을 뗀다(플러스 62%만 남고 이김 31%가 사라진다)",
     "quant/live/walkforward.py",
     "        segs = segment_scores(res.returns, warmup, market, segments, hold=hold)",
     "        segs = segment_scores(res.returns, warmup, market, segments)",
     "tests/test_the_report_shows_what_holding_would_have_done.py"),

    ("보유 대비 판정을 뒤집는다(지고 있는데 이겼다고 적는다)",
     "quant/live/walkforward.py",
     '            row["beat_hold"] = bool(row["total_return"] > hr)',
     '            row["beat_hold"] = bool(row["total_return"] < hr)',
     "tests/test_the_report_shows_what_holding_would_have_done.py"),

    ("대조군을 날짜 정렬 없이 앞에서부터 갖다 붙인다(딴 구간과 비교한다)",
     "quant/live/walkforward.py",
     "        bh = hold.reindex(oos.index).fillna(0.0)",
     "        bh = hold.reset_index(drop=True).set_axis(oos.index).fillna(0.0)",
     "tests/test_the_report_shows_what_holding_would_have_done.py"),

    ("굴린 자본을 안 잰다(자본의 절반이 현금인 것을 아무도 모른다)",
     "quant/live/walkforward.py",
     '            "avg_exposure": round(float(pos.mean()), 4) if len(pos) else None,',
     '            "avg_exposure": None,',
     "tests/test_the_report_shows_what_holding_would_have_done.py"),

    ("주간 보고서가 굴린 자본을 안 싣는다(장부에 있는데 아무도 안 읽는다)",
     "quant/live/daily.py",
     '                health["deployed"] = {',
     '                _unused = {',
     "tests/test_the_report_shows_what_holding_would_have_done.py"),

    ("사이징을 오디션 탐색 축에서 뺀다(없는 축은 영원히 진다)",
     "quant/live/retrain.py",
     '                               "sample_weight", "sizing"])',
     '                               "sample_weight"])',
     "tests/test_the_report_shows_what_holding_would_have_done.py"),

    ("사이징 후보를 고정 링에서 뺀다(돌연변이 운에만 맡긴다)",
     "quant/live/retrain.py",
     '    {"model": "logreg", "threshold": 0.55, "sizing": "binary"},',
     '    {"model": "logreg", "threshold": 0.55},',
     "tests/test_the_report_shows_what_holding_would_have_done.py"),

    ("생존 편향 표식을 끈다(화면이 '실제로 벌 수 있었던 돈'으로 읽는다)",
     "quant/live/walkforward.py",
     '        "survivorship_biased": True,',
     '        "survivorship_biased": False,',
     "tests/test_the_long_check_says_it_is_biased.py"),
]

def _purge_bytecode(path: pathlib.Path) -> None:
    """변조/복원한 모듈의 .pyc 캐시를 지운다.

    ⚠️ 왜 필요한가(2026-08-11 감사 72 — 이 도구 자신의 결함): 파이썬은
    .pyc의 유효성을 (원본 mtime, 원본 크기)로 판단한다. 변조와 복원이 같은
    초 안에 일어나고 **바뀐 글자 수가 같으면**(예: `gate` → `None`, 둘 다
    4글자) 복원 후에도 파이썬이 변조된 .pyc를 그대로 재사용한다.

    실제로 그 일이 일어났다: 복원이 끝났는데도 이후 테스트가 변조된
    바이트코드로 돌아 두 개가 실패했고, 디스어셈블해 보니 디스크에는
    `self.last_gate_ = gate`인데 실행되는 코드는 `= None`이었다. 도구가
    남긴 오염이 '진짜 결함'처럼 보인 것이다 — 오늘 내내 경계한 바로 그
    형태를 도구 자신이 만들고 있었다.
    """
    pyc_dir = path.parent / "__pycache__"
    if not pyc_dir.is_dir():
        return
    for f in pyc_dir.glob(path.stem + ".*.pyc"):
        try:
            f.unlink()
        except OSError:
            pass


def _assert_no_duplicates() -> None:
    """같은 장치를 두 번 찌르는 항목이 없는가 — 도구 자신의 네 번째 결함.

    2026-08-12: '레버리지 금지선'과 '미입증 목표 변동성 잠금'을 넣었는데
    둘 다 이미 있던 항목과 **같은 파일의 같은 줄**을 찌르는 것이었다.
    항목 수는 이 도구가 내놓는 유일한 숫자다("N개 장치를 지키고 있다").
    중복이 섞이면 그 숫자가 조용히 부풀고, 부푼 숫자는 안심을 만든다.

    주의: 앞으로 이 검사에 걸리면 **항목을 지우는 것이 정답**이다.
    두 항목이 정말 다른 장치를 찌른다면 원본 문자열이 달라야 한다.
    """
    seen: dict = {}
    dups = []
    for desc, path, old, _new, _test in MUTATIONS:
        k = (path, old)
        if k in seen:
            dups.append(f"  · {desc}\n    ↔ {seen[k]}\n    ({path})")
        seen[k] = desc
    if dups:
        print("💥 변이 항목이 같은 줄을 두 번 찌른다 — 목록을 정리할 것:\n"
              + "\n".join(dups))
        sys.exit(2)


_assert_no_duplicates()


# ── 죽어도 원본을 되돌린다 ────────────────────────────────────
#
# ⚠️ 이 도구는 **운영 코드를 실제로 망가뜨렸다가 되돌린다.** 되돌리는 일은
#    `finally`가 하는데, `finally`는 파이썬이 예외를 처리할 때만 돈다.
#    바깥에서 SIGTERM으로 죽이면(타임아웃·CI 취소) **변조된 채로 남는다.**
#
#    2026-08-12 감사 171에서 실제로 그랬다: `timeout 110`이 이 프로세스를
#    잡았고, quant/portfolio/screener.py가 `if r:` 가드가 빠진 상태로 작업
#    트리에 남았다. 그대로 커밋됐으면 재무를 못 받은 종목이 후보에 섞이는
#    코드가 배포된다. 도구가 자기 안전장치를 안 갖추고 있었던 것이다.
#
#    (1) 지금 무엇을 망가뜨렸는지 전역에 적어 두고
#    (2) SIGTERM·SIGINT를 받으면 되돌린 뒤 죽고
#    (3) 어떤 경로로 끝나든 atexit이 한 번 더 확인한다.
_IN_FLIGHT: dict = {}


def _restore_in_flight() -> None:
    for path, text in list(_IN_FLIGHT.items()):
        try:
            p = pathlib.Path(path)
            if p.read_text(encoding="utf-8") != text:
                p.write_text(text, encoding="utf-8")
                _purge_bytecode(p)
                print(f"↩️  중단됨 — {path} 원본 복원", file=sys.stderr)
        except OSError:
            pass
        _IN_FLIGHT.pop(path, None)


def _on_signal(signum, _frame):
    _restore_in_flight()
    sys.exit(128 + signum)


atexit.register(_restore_in_flight)
for _sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
    try:
        signal.signal(_sig, _on_signal)
    except (ValueError, OSError, AttributeError):
        pass                  # 메인 스레드가 아니거나 없는 시그널이면 건너뛴다


def _dry_run() -> None:
    """--dry-run — pytest를 돌리지 않고 **목록 자체가 살아 있는지**만 본다.

    왜 필요한가(2026-08-12 감사 125): 이 도구는 **CI에서 한 번도 돌지
    않았다.** 다른 모든 안전장치를 지키는 도구가 정작 아무도 안 돌린다.
    그래서 원본 문자열이 리팩터링에 밀려 안 맞게 되면(⏭️ 건너뜀) 그 장치는
    조용히 무방비가 되고, 아무도 모른다.

    전체 변이 시험은 100건이 넘어 PR마다 돌리기엔 무겁다. 그래서 둘로
    나눈다 — 이 검사는 몇 초 만에 끝나고 PR마다 돌며, 진짜 변이 시험은
    야간에 돈다. 여기서 잡는 것은 '조용한 드리프트' 하나뿐이지만, 그것이
    이 도구가 죽는 가장 흔한 방식이다.
    """
    bad = []
    for desc, path, old, _new, test in MUTATIONS:
        p = pathlib.Path(path)
        if not p.exists():
            bad.append(f"  · {desc}\n    대상 파일 없음: {path}")
            continue
        n = p.read_text(encoding="utf-8").count(old)
        if n != 1:
            bad.append(f"  · {desc}\n    원본 문자열이 {n}회({path}) — "
                       f"코드가 바뀌었다. 변이 문자열을 갱신할 것")
        if not pathlib.Path(test).exists():
            bad.append(f"  · {desc}\n    검사 파일 없음: {test}")
    if bad:
        print(f"💥 변이 목록이 코드와 어긋난다({len(bad)}건) — "
              f"그만큼의 안전장치가 지금 무방비다:\n" + "\n".join(bad))
        sys.exit(1)
    print(f"✅ 변이 항목 {len(MUTATIONS)}건이 모두 코드와 맞물려 있다"
          f"(대상 파일·원본 문자열·검사 파일 확인). "
          f"실제 변이 시험은 야간 잡에서 돈다.")
    sys.exit(0)


if "--dry-run" in sys.argv[1:]:
    _dry_run()


def _node() -> str:
    """node 실행기. CI에는 PATH에 있고, 이 저장소의 개발 환경에는 /opt에 있다."""
    import shutil
    return shutil.which("node") or "/opt/node22/bin/node"


def run(test):
    """그 검사를 돌리고 종료코드를 돌려준다(0=통과).

    ⚠️ **파이썬 검사만 돌리고 있었다**(2026-08-14). 이 저장소에는 사이트·
       워커의 돈 계산을 **실행해서** 확인하는 Node 하네스가 둘 있고
       (`live_marks_check.mjs`·`worker_ladder_check.mjs`), 그것들이 실제로
       결함을 잡았다(감사 229·231). 그런데 변이 시험은 pytest만 불러서,
       그 하네스를 검사로 지정하면 "원본 코드에서 이미 실패"로 찍혔다 —
       즉 **가장 잘 잡는 검사가 변이 시험에서는 없는 것과 같았다.**
       종료코드 규약(0=통과)이 같으므로 실행기만 갈라 주면 된다.
    """
    if str(test).endswith(".mjs"):
        r = subprocess.run([_node(), test],
                           capture_output=True, text=True, timeout=900)
        return r.returncode
    # 하위 프로세스가 새 .pyc를 굽지 않게 한다(오염 재발 방지).
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run([sys.executable, "-m", "pytest", test, "-q", "--no-header", "-x"],
                       capture_output=True, text=True, timeout=900, env=env)
    return r.returncode


# 파일이 없거나 수집이 깨진 경우 pytest는 4(사용 오류)를 준다. 그것을
# '검사가 실패했다 = 잡았다'로 세면 **없는 검사가 잡은 것으로 보인다.**
# 실제로 그랬다: tests/test_calibration_guard.py는 존재하지도 않는데
# ✅로 찍혔다(감사 62 — 이 도구 자신의 같은 병). 그래서 변이 전에
# 기준선을 먼저 돌려, 원본 코드에서 통과하는 검사만 대상으로 삼는다.
BASELINE_OK = 0

# 부분 실행 — `python scripts/mutation_check.py 의회` 처럼 설명·검사 이름의
# 일부를 주면 그 항목만 돈다. 새 항목을 만들 때 전체(100건 이상)를 다시
# 돌리지 않기 위한 것이므로, **부분 실행 결과를 '전부 통과'로 보고하지 말 것.**
FILTER = sys.argv[1] if len(sys.argv) > 1 else ""
if FILTER:
    print(f"⚠️ 부분 실행: '{FILTER}' — 전체 결과가 아니다\n")

print(f"{'결과':4s} {'설명':60s} 검사")
print("─" * 110)
caught = missed = skipped = broken = 0
_baseline: dict = {}
for desc, path, old, new, test in MUTATIONS:
    if FILTER and FILTER not in desc and FILTER not in test:
        continue
    p = pathlib.Path(path)
    src = p.read_text(encoding="utf-8")
    if src.count(old) != 1:
        print(f"⏭️   {desc[:58]:60s} (원본 문자열 {src.count(old)}회 — 코드가 바뀜)")
        skipped += 1
        continue
    if test not in _baseline:
        if not pathlib.Path(test).exists():
            _baseline[test] = "파일 없음"
        else:
            _baseline[test] = ("" if run(test) == BASELINE_OK
                               else "원본 코드에서 이미 실패")
    if _baseline[test]:
        print(f"💥   {desc[:58]:60s} {test.split('/')[-1]}  ← {_baseline[test]}")
        broken += 1
        continue
    _IN_FLIGHT[str(p)] = src        # 죽어도 되돌릴 수 있게 원본을 등록해 둔다
    p.write_text(src.replace(old, new), encoding="utf-8")
    _purge_bytecode(p)
    try:
        rc = run(test)
    finally:
        p.write_text(src, encoding="utf-8")
        _purge_bytecode(p)          # 복원본이 반드시 다시 컴파일되게
        _IN_FLIGHT.pop(str(p), None)
    if rc != 0:
        print(f"✅   {desc[:58]:60s} {test.split('/')[-1]}")
        caught += 1
    else:
        print(f"❌   {desc[:58]:60s} {test.split('/')[-1]}  ← 못 잡음")
        missed += 1
print("─" * 110)
print(f"잡음 {caught} · 놓침 {missed} · 건너뜀 {skipped} · 검사 자체 고장 {broken}")
# ⚠️ 2026-08-12 감사 126 — 이 줄이 문서와 어긋나 있었다.
#    머리말은 "건너뜀은 통과가 아니다"라고 적어 놓고, 종료코드는
#    `1 if (missed or broken)`이라 **건너뜀을 통과로 취급**했다.
#    즉 116개 항목의 원본 문자열이 전부 안 맞게 돼도 이 도구는 0을 준다.
#    오늘 내내 잡아 온 '말과 행동의 불일치'가 감사 도구 자신에게 있었다.
sys.exit(1 if (missed or broken or skipped) else 0)
