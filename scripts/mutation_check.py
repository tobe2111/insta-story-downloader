"""변이 시험 — 안전장치를 일부러 망가뜨려, 계약 검사가 정말 잡는지 확인한다.

    python scripts/mutation_check.py

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

print(f"{'결과':4s} {'설명':60s} 검사")
print("─" * 110)
caught = missed = skipped = broken = 0
_baseline: dict = {}
for desc, path, old, new, test in MUTATIONS:
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
sys.exit(1 if (missed or broken) else 0)
