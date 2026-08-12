"""변이 시험 — 안전장치를 일부러 망가뜨려, 계약 검사가 정말 잡는지 확인한다.

    python scripts/mutation_check.py                # 전수(무겁다 — 야간 잡)
    python scripts/mutation_check.py --dry-run      # 목록 정합성만(몇 초 — CI)
    python scripts/mutation_check.py 의회            # 부분 실행(설명·검사 이름)

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
import os
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
     "                if c == c and c > CORR_CAP:",
     "                if False:",
     "tests/test_parliament.py"),

    ("상관을 못 재면 '무상관'으로 본다(감사 53 되돌리기 — 실패가 곧 통과)",
     "quant/live/parliament.py",
     "                    c = 1.0",
     "                    c = 0.0",
     "tests/test_parliament_moves_slowly_and_diversely.py"),

    ("의석 비중 급변 방지(EMA)를 끈다 — 하루 만에 전액 이동",
     "quant/live/parliament.py",
     "            w = (1 - EMA_STEP) * prev + EMA_STEP * target",
     "            w = target",
     "tests/test_parliament_moves_slowly_and_diversely.py"),

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
     "                if stopped:\n                    w[t] = 0.0",
     "                if False:\n                    w[t] = 0.0",
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
     "            return from_ccxt_market(m) if m else None",
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

    ("정수 주 내림을 끈다(못 사는 수량을 산 것으로 기록)",
     "quant/live/daily.py",
     "        lots = math.floor(abs(w) * equity / float(px))",
     "        lots = abs(w) * equity / float(px)",
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
     "        return (self.fee + self.slippage + self.impact_coef * vol) * turnover",
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

    ("HRP 비중 합 검사를 없앤다(전 종목 0인 배분이 폴백 없이 그대로 나간다)",
     "quant/live/hrp.py",
     "        if abs(sum(out.values()) - 1.0) > 1e-6:",
     "        if False:",
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

    # ── 어드민·웹 경로 ──
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
     '<div class="k">통합 계좌 (${spread} · 시작 ${won(p.start_cash||80000)})</div>',
     '<div class="k">통합 계좌 (${rest.length}종목 분산 · 시작 ${won(p.start_cash||80000)})</div>',
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
     'f"📈 총노출 {gross} · {spread}(코인·한국·미국)\\n"',
     'f"📈 총노출 {gross} · {n_sym}종목 분산(코인·한국·미국)\\n"',
     "tests/test_broadcast_tells_the_whole_truth.py"),

    ("적중률 라벨을 '(60일)'로 되돌린다(실제는 전체 기간)",
     "docs/paper.html",
     '<th title="포지션을 잡은 봉만 세어 낸 방향 적중률(기록 전체 기간)">적중률(전체)</th></tr>${rows}</table></div>',
     '<th>적중률(60일)</th></tr>${rows}</table></div>',
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
     '    - cron: "30 1 * * *"',
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
     '<th title="그 종목만 굴리는 독립 계좌에서의 비중">종목계좌 비중</th>',
     '<th>비중</th>',
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

    ("킬스위치 감쇠를 스케일러 앞으로 되돌린다(오늘 고친 결함 재현)",
     "quant/live/daily.py",
     "eff = w * eff_scale * vscale * guard_damp.get(key, 1.0)",
     "eff = w * eff_scale * guard_damp.get(key, 1.0) * vscale",
     "tests/test_killswitch_effective.py"),

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

    ("다중검정 보정 문턱을 0으로 내린다",
     "quant/live/retrain.py",
     "    select_t: float = 2.0,",
     "    select_t: float = 0.0,",
     "tests/test_audition_gates_bind.py"),

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
     "def _write_run_health(state_dir: str, kind: str, ok: list, failed: dict) -> None:",
     "def _write_run_health(state_dir: str, kind: str, ok: list, failed: dict) -> None:\n    return",
     "tests/test_run_health.py"),

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
     "            df_sig = _signal_frame(market, df)",
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
     "            if not is_market_open(self.market):",
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
     "            if not is_market_open(self.market):",
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


def run(test):
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
    p.write_text(src.replace(old, new), encoding="utf-8")
    _purge_bytecode(p)
    try:
        rc = run(test)
    finally:
        p.write_text(src, encoding="utf-8")
        _purge_bytecode(p)          # 복원본이 반드시 다시 컴파일되게
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
