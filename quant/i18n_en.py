"""프로그램이 하는 말의 영어판 사전 (2026-08-26 감사 326).

⚠️ 규칙은 사이트의 사전(docs/assets/i18n-en.js)과 같다.

  · **열쇠는 한국어 원문 그대로.** 소스의 문자열을 고치면 그 문장은 사전에서
    빠지고 **영어가 낡는 대신 한국어로 되돌아간다** — 틀린 영어가 남는 것보다
    낫다.
  · **날짜·금액처럼 매일 바뀌는 값은 열쇠에 넣지 않는다.** 그런 문장은
    RULES(정규식)가 숫자를 잡아 **그대로 흘려보낸다.**
  · '수익 보장'류는 어느 언어로도 쓰지 않는다(사기죄 위험).
"""
from __future__ import annotations

# 정확히 같은 글자를 찾는다.
STRINGS: dict = {
    "퀀트 트레이딩 CLI":
        "Quant trading CLI",
    "화면·로그 언어 (기본: 한국어. QUANT_LANG 로도 지정)":
        "language for screens and logs (default: Korean; QUANT_LANG also works)",
    "전략 백테스트 실행":
        "run a strategy backtest",
    "HTML 리포트 저장 경로":
        "where to save the HTML report",
    "리밸런스 데드밴드(권장 0.02~0.05). 미세 조정 거래를 생략해 왕복비용을 아낀다. 0=비활성":
        "rebalance dead band (0.02-0.05 recommended); skips tiny adjustments to save the round-trip cost. 0 = off",
    "스톱 발동 후 N봉 재진입 금지(채찍질 비용 방지). 0=비활성":
        "no re-entry for N bars after a stop (avoids whipsaw costs). 0 = off",
    "자산곡선이 자체 MA 하회 시 익스포저 축소":
        "cut exposure when the equity curve falls below its own moving average",
    "트로틀 히스테리시스 밴드(예: 0.01). 0=즉시 전환":
        "hysteresis band for the throttle (e.g. 0.01). 0 = switch immediately",
    "손절/익절을 봉 내 고저가로 판정(실전에 더 가까움 — 종가 판정은 봉 중간 관통을 놓쳐 손실을 과소평가)":
        "judge stops and take-profits on the bar's high and low (closer to reality — judging on the close misses intrabar touches and understates losses)",
    "시장별 현실 비용 프리셋 적용(한국주식 거래세 등 — 근사치, 본인 브로커 기준 확인 필요)":
        "apply realistic per-market cost presets (Korean transaction tax and so on — approximate; check your own broker)",
    "파라미터 민감도 히트맵":
        "parameter sensitivity heat map",
    "로컬 웹 UI 실행":
        "run the local web UI",
    "브라우저 자동 열기":
        "open the browser automatically",
    "자동 페이퍼 트레이딩 + 지속 재학습 + 정확도 추적":
        "automatic paper trading + continuous retraining + accuracy tracking",
    "champion(기본, 야간 재학습 챔피언 자동 추종) | ml | ensemble | 개별 전략 이름":
        "champion (default; follows the nightly retraining champion) | ml | ensemble | a strategy name",
    "0=무기한, N=N회 후 종료":
        "0 = forever, N = stop after N cycles",
    "사이클 간격(초)":
        "seconds between cycles",
    "과최적화 검증 3종(워크포워드+DSR·PBO·CPCV)을 한 번에 실행":
        "run all three overfitting checks at once (walk-forward + DSR · PBO · CPCV)",
    "운용 대상 전 종목(quant.markets.AUTO_TARGETS)을 차례로 검증한다 — 종목 목록을 워크플로가 아니라 코드가 갖게 해, 종목을 늘려도 검증이 따라온다":
        "validate every traded symbol (quant.markets.AUTO_TARGETS) in turn — the list lives in the code rather than the workflow, so validation follows when symbols are added",
    "파라미터 그리드 JSON (예: '{\"fast\":[5,10],\"slow\":[40,60]}')":
        "parameter grid as JSON (e.g. '{\"fast\":[5,10],\"slow\":[40,60]}')",
    "검증 결과(DSR·PBO)를 JSON 장부에 누적 저장 (예: state/validation.json) — flag_watch가 읽어 경보한다":
        "append the results (DSR, PBO) to a JSON ledger (e.g. state/validation.json) — flag_watch reads it and raises alerts",
    "검증 결과를 그래프 HTML 리포트로 저장(예: results/validate.html)":
        "save the results as an HTML report with charts (e.g. results/validate.html)",
    "매일 1사이클 자동 페이퍼 운용 — 챔피언 추종, 상태 이어받기(멱등)":
        "one automatic paper cycle a day — follows the champion and continues the state (idempotent)",
    "docs/status.json 갱신(사이트에 결과 표시)":
        "update docs/status.json (shows the result on the site)",
    "합성 폴백 데이터 허용(테스트 전용)":
        "allow the synthetic data fallback (tests only)",
    "AUTO_TARGETS 전 종목 순회(야간 자동화용)":
        "walk every AUTO_TARGETS symbol (for the nightly automation)",
    "하루 1회 국내주식 실거래 집행 — 페이퍼와 같은 결정을 KIS 계좌로 (기본 모의투자, 실전은 --real + QUANT_LIVE_REAL=1)":
        "execute Korean equities live once a day — the same decision as paper, sent to a KIS account (simulation by default; live needs --real plus QUANT_LIVE_REAL=1)",
    "실전 계좌 사용(환경변수 QUANT_LIVE_REAL=1 필요)":
        "use the live account (requires QUANT_LIVE_REAL=1)",
    "증권사 선택(기본: QUANT_KR_BROKER 환경변수 → kis)":
        "which broker (default: the QUANT_KR_BROKER variable, then kis)",
    "실거래 전환 준비 진단 — 키·인증·잔고를 주문 없이 확인":
        "readiness check for going live — keys, authentication and balance, with no orders",
    "실전 도메인으로 진단":
        "run the check against the live domain",
    "100만 챌린지 매칭 입금 (100만원→1억) — 후원 금액만큼 통합 계좌 원금 증액":
        "1M Won Challenge matching deposit (1,000,000 KRW → 100 million) — raises the combined account's principal by the donated amount",
    "입금액(원)":
        "amount (KRW)",
    "예: '슈퍼챗 ○○님'":
        "e.g. \"super chat from ○○\"",
    "통합 계좌를 원화 계좌로 다시 연다 (감사 212) — 한 번만 실행":
        "reopen the combined account on a won basis (audit 212) — run once",
    "새 원화 계좌의 원금(원)":
        "principal of the new won account (KRW)",
    "섀도 대조군은 portfolio_SHADOW.json (감사 215)":
        "the shadow control arm is portfolio_SHADOW.json (audit 215)",
    "확인 없이 실행 (워크플로용)":
        "run without confirmation (for workflows)",
    "실시간 루프 — 챔피언(야간 진화) 자동 추종 · 기본 페이퍼, --real 시 실전":
        "the live loop — follows the champion as it evolves nightly · paper by default, live with --real",
    "같은 시장 다중 종목 분산 운용 — 예: \"BTC/USDT,ETH/USDT,SOL/USDT\"":
        "spread across several symbols of one market — e.g. \"BTC/USDT,ETH/USDT,SOL/USDT\"",
    "1d=챔피언 검증과 같은 일봉 기준(권장)":
        "1d = the same daily bars the champion was validated on (recommended)",
    "champion=야간 재학습 챔피언 자동 추종(기본), 또는 전략 이름":
        "champion = follow the nightly retraining champion (default), or a strategy name",
    "⚠️ 실거래 — 실제 자금. 타이핑 확인을 거칩니다":
        "⚠️ live trading — real money. You will be asked to type a confirmation",
    "페이퍼 모드 시작 자금(실전에서는 무시 — 계좌 잔고 사용)":
        "starting cash in paper mode (ignored when live — the account balance is used)",
    "자산 대비 최대 포지션 비중 (기본 0.5 = 절반)":
        "maximum position weight against equity (default 0.5 = half)",
    "일일 손실 킬스위치 한도 (기본 0.03 = -3%%)":
        "daily-loss kill switch limit (default 0.03 = -3%%)",
    "최대낙폭 서킷브레이커 한도 (기본 0.15 = -15%%)":
        "drawdown circuit-breaker limit (default 0.15 = -15%%)",
    "반복 횟수(기본 무한)":
        "how many cycles (default: unlimited)",
    "상태 저장 경로(웹 조종석 감시 탭이 읽음)":
        "where to write the state (the cockpit's Monitor tab reads it)",
    "재현성 검증 — 스냅샷·시드로 그날의 재학습 결정을 재실행해 대조":
        "reproducibility check — re-run that day's retraining decision from the snapshot and seed and compare",
    "예: 2026-08-06":
        "e.g. 2026-08-06",
    "비우면 전체":
        "leave empty for all",
    "종목 표본 수(0=전체). 날짜 시드로 결정적 선택 — 매일 다른 표본이라 한 주면 전 종목을 훑는다":
        "how many symbols to sample (0 = all). The choice is seeded by the date, so a different sample each day covers everything within a week",
    "미뤄 둔 알림 내보내기 — 커밋·푸시가 끝난 뒤에만 부른다(감사 283)":
        "flush deferred alerts — call this only after the commit and push are done (audit 283)",
    "쌓인 알림을 보낸다":
        "send the queued alerts",
    "쌓인 알림을 버린다(저장되지 않은 일은 방송하지 않는다)":
        "drop the queued alerts (what was not saved is not broadcast)",
    "시장 브리핑 수집(무료 RSS) — 방송·사이트 표시 전용, 판단 미사용":
        "collect the market briefing (free RSS) — display only on the site and broadcast; it feeds no decision",
    "주간 요약 — 시장별 주간 수익·최악일·챔피언 교체 이력(텔레그램 전송)":
        "weekly summary — weekly return by market, the worst day, and champion swaps (sent to Telegram)",
    "텔레그램 전송 없이 출력만":
        "print only, do not send to Telegram",
    "긴 검증 — 챔피언 설정을 최장 과거에 적용한 구간별 성적(생존 편향 고지 포함, 승격에 쓰지 않는 관찰값)":
        "the long validation — the champion's settings applied to the longest past, window by window (carries the survivorship-bias notice; observation only, never used for promotion)",
    "목표 봉 수(기본 2,500 ≈ 주식 10년)":
        "how many bars to aim for (default 2,500 ≈ 10 years of stocks)",
    "네트워크 없이 저장된 스냅샷만 사용":
        "use stored snapshots only, no network",
    "결과 JSON 저장 경로(예: docs/walkforward.json)":
        "where to save the result JSON (e.g. docs/walkforward.json)",
    "알림 전송 없이 출력만":
        "print only, do not send alerts",
    "SNS 게시 콘텐츠 생성 — 캡션(인스타/스레드)·메타를 docs/social/에 쓴다":
        "build the social content — captions (Instagram, Threads) and metadata into docs/social/",
    "보관할 날짜 폴더 수(오래된 것 정리)":
        "how many dated folders to keep (older ones are removed)",
    "이미 공개된 날의 캡션을 덮어쓴다 — 과거 기록을 바꾸는 행위이므로 의도적일 때만 쓸 것(감사 86)":
        "overwrite a caption already published — this changes the past record, so use it only deliberately (audit 86)",
    "SNS 게시 실행 — Threads/Instagram API (환경변수 미설정 시 건너뜀)":
        "post to social — the Threads and Instagram APIs (skipped when the variables are unset)",
    "콘텐츠 폴더(docs/social/<날짜>)":
        "the content folder (docs/social/<date>)",
    "야간 자동 재학습 — 챔피언/챌린저 2단계 검증, 이길 때만 교체":
        "nightly retraining — two-stage champion/challenger validation; swap only on a win",
    "결승전(최근 미공개 구간) 봉 수":
        "bars for the final (the recent window it has not seen)",
    "합성 폴백 데이터 허용(테스트 전용 — 실서비스 금지)":
        "allow the synthetic data fallback (tests only — never in production)",
    "내 자료(PDF·유튜브·트레이딩뷰)에서 전략을 뽑아 도전자로 등록":
        "pull a strategy out of your own material (PDF, YouTube, TradingView) and register it as a challenger",
    "PDF 경로 · 유튜브 주소 · .pine · .txt/.md":
        "a PDF path · a YouTube URL · .pine · .txt/.md",
    "전략 이름(생략 시 파일명)":
        "strategy name (defaults to the file name)",
    "명세를 저장할 곳(생략 시 ./specs_user)":
        "where to save the specification (defaults to ./specs_user)",
    "저장하지 않고 무엇이 뽑혔는지만 본다":
        "show what was extracted without saving it",
    "내 전략을 이 종목에 고정 — 심사와 무관하게 내 전략으로 매매(설치형 사용자용, 성적표 확인 + 타이핑 확인 필요)":
        "pin your strategy to this symbol — trade it regardless of the audition (for installed users; shows the report card and asks you to type a confirmation)",
    "ingest로 저장한 전략 이름":
        "the name of a strategy saved by ingest",
    "고정 해제 — 시스템 챔피언 판단이 즉시 복귀":
        "unpin — the system's own champion takes over again immediately",
    "지금 고정된 전략 목록":
        "what is pinned right now",
    "장중 감시 1회 — 지금 자산으로 낙폭을 재고 킬스위치를 즉시 적용":
        "one intraday check — measure the drawdown on current equity and apply the kill switch at once",
    "웹 조종석 로그인 설정 — 아이디·비밀번호(해시로만 저장)":
        "set up cockpit login — an id and password (stored only as a hash)",
    "장중 도전자 1회 — 챔피언 규칙을 1시간봉에 적용하는 분리 실험(가상 USDT · 본 계좌와 무관)":
        "one intraday challenger round — the champion's rules on hourly bars, as a separate experiment (virtual USDT, unrelated to the main account)",
    "선물 도전자 1회 — 같은 규칙을 **양방향**(롱/숏)으로 돌리는 분리 실험(가상 USDT · 레버리지 없음 · 본 계좌와 무관)":
        "one futures challenger round — the same rules run **both ways** (long and short) as a separate experiment (virtual USDT, no leverage, unrelated to the main account)",
    "API 키 대화형 설정(.env 저장 + 연결 확인)":
        "set up API keys interactively (saves to .env and checks the connection)",
    "트레이딩뷰 등 알림 웹훅 수신 → 주문 실행(기본 페이퍼, 비밀키 필수)":
        "receive alert webhooks (TradingView and the like) and place orders (paper by default; a secret is required)",
    "허용 종목(쉼표 구분). 미지정 시 전체 허용":
        "allowed symbols (comma separated). Everything is allowed when unset",
    "실거래(⚠️ 실제 자금)":
        "live trading (⚠️ real money)",
    "페이퍼 초기자본":
        "starting capital in paper mode",
    "신호당 최대 목표 비중(0~1)":
        "maximum target weight per signal (0-1)",
    "트레이딩뷰 공식 IP만 허용(권장)":
        "allow TradingView's official IPs only (recommended)",
    "허용 발신 IP 목록(쉼표 구분). 리버스 프록시 뒤면 생략":
        "allowed sender IPs (comma separated). Omit when behind a reverse proxy",
    ">0이면 payload timestamp가 이 초보다 오래되면 거부":
        "when > 0, reject a payload whose timestamp is older than this many seconds",
    "봇 상태 파일에서 거래 성과 복기(거래 단위 통계)":
        "review trading results from the bot's state file (per-trade statistics)",
    "손익분기 비용 분석(수수료 스윕+손익분기) — 비용을 이기는지 확인":
        "break-even cost analysis (a fee sweep plus break-even) — does it beat the costs",
    "전략 A/B 유의성 검정 — 차이가 노이즈인지 실제 개선인지":
        "an A/B significance test between strategies — is the difference noise or a real improvement",
    "공개 장부에 원화 환산을 덧붙인다(참고 값 — 계좌 단위는 그대로)":
        "attach a won conversion to the public ledger (a reading aid — the account's own unit is unchanged)",
    "머신러닝 성적표(docs/ml.json) — 적중률·보정·드리프트·검증 게이트":
        "the machine-learning report card (docs/ml.json) — hit rate, calibration, drift, validation gate",
    "기준일(YYYY-MM-DD). 생략하면 오늘":
        "as-of date (YYYY-MM-DD). Defaults to today",
    "백테스트+리포트+몬테카를로 통합 실행":
        "backtest + report + Monte Carlo, all in one",
    "⚠️ 과거 성과는 미래 수익을 보장하지 않습니다.":
        "⚠️ Past performance guarantees no future return.",
    "⚠️ 정확도는 50~55%에서 오르내립니다. 100%로 오르지 않습니다 — 그게 정상입니다.":
        "⚠️ Accuracy hovers between 50 and 55%. It does not climb to 100% — that is normal.",
    "⚠️ 페이퍼(모의) 운용입니다 — 실제 돈이 오가지 않으며, 결과가 좋아도 미래 수익 보장이 아닙니다.":
        "⚠️ This is paper (simulated) trading — no real money moves, and a good result guarantees nothing about the future.",
    "⚠️ 후원금 자체를 굴리는 것이 아니라, 같은 금액만큼 가상 계좌 원금을 늘리는 '매칭' 이벤트입니다(대가·지분 없음).":
        "⚠️ The donation itself is never traded; this is a matching event that raises the virtual account's principal by the same amount (no consideration, no equity).",
    "⚠️ 브리핑은 표시 전용입니다 — 매매 판단에 사용되지 않습니다.":
        "⚠️ The briefing is display only — it feeds no trading decision.",
    "🔐 저장했습니다(.env — 해시만 저장, 커밋 금지 목록). 웹 조종석을 다시 켜면 로그인 화면이 뜹니다.":
        "🔐 Saved to .env (the hash only, and the file is not committed). Restart the web cockpit and a login screen appears.",
    "✅ 이렇게 읽었습니다:":
        "✅ Here is what was read:",
    "근거가 된 문장:":
        "The sentence it came from:",
    "이제 매일 밤 재학습에서 **도전자로** 링에 섭니다. 등록만으로는 매매하지 않습니다 — 다른 후보와 같은 2단계 심사를 이기고, 과최적화 검증까지 통과해야 실제 비중을 받습니다. 대부분은 떨어집니다.":
        "From tonight it enters the ring as a **challenger** in the nightly retraining. Registering alone trades nothing — it has to win the same two-stage audition as every other candidate and clear the overfitting checks before it gets any real weight. Most do not.",
    "오디션은 계속 돕니다 — 성적표가 매일 갱신되고, `unpin`으로 언제든 시스템 판단으로 돌아갈 수 있습니다.":
        "The audition keeps running — the report card updates daily, and `unpin` hands the decision back to the system at any time.",
    "⚠️ 챔피언이 안 바뀌는 날이 대부분입니다 — 확실히 나은 후보가 없었다는 뜻이고, 그게 이 장치가 일하는 방식입니다.":
        "⚠️ On most days the champion does not change — it means no candidate was clearly better, and that is this device working as intended.",
    "[1/4] 워크포워드 (롤링 IS→OOS)":
        "[1/4] Walk-forward (rolling in-sample → out-of-sample)",
    "[2/4] PBO (백테스트 과적합 확률)":
        "[2/4] PBO (probability of backtest overfitting)",
    "[3/4] CPCV (다중 OOS 경로 분포)":
        "[3/4] CPCV (the distribution across many out-of-sample paths)",
    "[4/4] 파라미터 안정성 (고원 vs 외딴 봉우리)":
        "[4/4] Parameter stability (a plateau versus a lone peak)",
    "⚠️ 세 검증을 모두 통과해도 미래 수익은 보장되지 않습니다. 다음 단계는 페이퍼 트레이딩(learn)으로 실데이터 검증입니다.":
        "⚠️ Passing all three guarantees no future return. The next step is paper trading (learn) on real data.",
    "🔑 API 키 설정 마법사":
        "🔑 API key setup wizard",
    "· 백테스트·검증·페이퍼 트레이딩에는 키가 전혀 필요 없습니다.":
        "· Backtesting, validation and paper trading need no keys at all.",
    "· 키 '발급'은 계좌 본인 인증이 필요해 직접 하셔야 하지만,":
        "· Issuing a key needs identity verification, so you have to do that part,",
    "발급 후 입력·저장·확인은 여기서 한 번에 끝납니다.":
        "but entering, storing and checking it all happens here in one go.",
    "· 저장 위치: .env (git 미포함 · 리눅스/맥은 본인만 읽기 권한)":
        "· Where it is stored: .env (not committed; readable only by you on Linux and macOS)",
    "· 각 그룹은 건너뛸 수 있습니다(엔터).":
        "· You can skip any group by pressing enter.",
    "⚠️ 키는 절대 커밋·공유하지 마세요. 실거래 키는 출금 권한을 꺼두세요.":
        "⚠️ Never commit or share a key. On live-trading keys, disable withdrawal permission.",
    "Pine Script 알림 메시지(JSON) 예시:":
        "An example Pine Script alert message (JSON):",
    "⚠️ 이 포트를 인터넷에 열 때는 HTTPS(리버스 프록시) 뒤에 두세요.":
        "⚠️ If you open this port to the internet, put it behind HTTPS (a reverse proxy).",
    "⚠️ 데이터 품질 경고 — 아래 항목을 확인한 뒤 결과를 해석하세요.":
        "⚠️ Data quality warning — read the items below before interpreting the result.",
    "⚠️ 통합 계좌를 닫고 원화 계좌를 새로 엽니다. 옛 장부는 portfolio_ALL.pre-krw.json 으로 그대로 보관되지만, 현재 보유·현금은 새 계좌로 이어지지 않습니다.":
        "⚠️ This closes the combined account and opens a new won-denominated one. The old ledger is kept as portfolio_ALL.pre-krw.json, but current holdings and cash do not carry over.",
    "✅ 준비 완료 — live-daily로 모의투자 리허설을 시작할 수 있습니다.":
        "✅ Ready — you can start the simulated rehearsal with live-daily.",
    "야간 재학습이 챔피언을 교체하면 재시작 없이 자동 반영됩니다.":
        "When nightly retraining swaps the champion, it applies with no restart.",
    "⚠️ 실전 모드 — 실제 자금으로 주문합니다.":
        "⚠️ Live mode — orders go out with real money.",
    "⚠️ 갭·급변 구간에서는 한도를 넘는 손실이 날 수 있습니다(보장 아님).":
        "⚠️ In a gap or a sudden move the loss can exceed the limit — this is not a guarantee.",
    "잃어도 되는 소액으로만 시작하세요. 수익 보장은 없습니다.":
        "Start only with an amount you can afford to lose. Nothing here is a guarantee of returns.",
    "📝 페이퍼 모드 (실제 자금 사용 안 함) — 실전은 --real":
        "📝 Paper mode (no real money) — use --real for live",
    "✅ 모든 결정이 재현되었습니다 — 같은 데이터·같은 코드에서 같은 결과가 나옵니다.":
        "✅ Every decision reproduced — the same data and the same code give the same result.",
    "⚠️ 일부 검증 실패 — 위 상세를 확인하세요.":
        "⚠️ Some checks failed — see the detail above.",
    "아이디가 비어 있습니다 — 중단합니다.":
        "The id is empty — stopping.",
    "두 입력이 다릅니다 — 중단합니다.":
        "The two entries differ — stopping.",
    "8자 이상으로 해주세요 — 중단합니다.":
        "Please use at least 8 characters — stopping.",
    "기록이 없어 낙폭을 잴 수 없습니다 — 심장박동만 남깁니다.":
        "There is no record, so the drawdown cannot be measured — only a heartbeat is written.",
    "전략을 만들지 않았습니다 — 없는 규칙을 지어내지 않습니다.":
        "No strategy was created — rules that are not there are not invented.",
    "(--dry-run: 저장하지 않았습니다)":
        "(--dry-run: nothing was saved)",
    "고정된 전략이 없습니다 — 모든 종목이 심사(오디션) 결과를 따릅니다.":
        "Nothing is pinned — every symbol follows the audition result.",
    "변경 없음 — 종료합니다.":
        "Nothing changed — exiting.",
    "파일 권한: 600 (본인만 읽기) — 확인됨":
        "File permissions: 600 (readable only by you) — confirmed",
    "❌ 환경변수 QUANT_WEBHOOK_SECRET(공유 비밀키)이 필요합니다.\n   인증 없는 주문 엔드포인트는 누구나 내 계좌로 주문을 낼 수 있어 실행할 수 없습니다.\n   예: export QUANT_WEBHOOK_SECRET='아주-긴-무작위-문자열'":
        "❌ The QUANT_WEBHOOK_SECRET environment variable (the shared secret) is required.\n   An order endpoint with no authentication lets anyone place orders on your account, so it will not start.\n   e.g. export QUANT_WEBHOOK_SECRET='a-very-long-random-string'",
    "📝 페이퍼 모드 — 실제 자금 사용 안 함":
        "📝 Paper mode — no real money",
    "⚠️ IP 허용목록 미설정 — --tradingview-ips 권장(공식 IP만 허용).":
        "⚠️ No IP allow-list — --tradingview-ips is recommended (official IPs only).",
    "⚠️ 신선도 검사 꺼짐 — 5분 지난 캡처 신호도 통과합니다. 알림 JSON에 \"timestamp\": {{timenow}} 를 넣고 --max-age 300 을 주면 막힙니다.":
        "⚠️ The freshness check is off — a captured signal five minutes old still gets through. Put \"timestamp\": {{timenow}} in the alert JSON and pass --max-age 300 to stop that.",
    "취소했습니다.":
        "Cancelled.",
    "취소되었습니다.":
        "Cancelled.",
    "⚠️ 파일 권한: 윈도우에서는 '본인만 읽기'를 보장할 수 없습니다.":
        "⚠️ File permissions: on Windows \"readable only by you\" cannot be guaranteed.",
    ".env 를 다른 사람이 쓰는 계정과 공유되지 않는 폴더에 두세요.":
        "Keep .env in a folder that is not shared with anyone else's account.",
    "⚠️ 파일 권한을 600으로 조이지 못했습니다 — 같은 기계의 다른":
        "⚠️ Could not tighten the file permissions to 600 — another user on the",
    "사용자가 키를 읽을 수 있습니다. `chmod 600 .env` 를 직접 실행하세요.":
        "same machine could read the key. Run `chmod 600 .env` yourself.",
    "📨 텔레그램: 테스트 메시지를 보냈습니다(수신 확인하세요).":
        "📨 Telegram: a test message was sent (please check that it arrived).",
    "💡 넓은 초록 고원=견고, 외딴 점=과최적화":
        "💡 A wide green plateau means robust; a lone dot means overfitted",
    "고정하려면 다음 문구를 그대로 입력하세요:":
        "To pin it, type the following exactly:",
    "❌ 자료를 읽지 못했습니다.":
        "❌ Could not read the material.",
    "예":
        "yes",
    "아니오":
        "no",
    "없음":
        "none",
    "실패":
        "failed",
    "성공":
        "ok",
    "✅ 벤치마크 초과":
        "✅ beats the benchmark",
    "⚠️ 벤치마크 하회":
        "⚠️ below the benchmark",
    "아직 완결된 거래(라운드트립)가 없습니다. 더 오래 운용한 뒤 다시 복기하세요.":
        "No completed round trips yet. Run it longer and review again.",
    "기록이 없습니다.":
        "There is no record.",
    "장부가 비어 있습니다.":
        "The ledger is empty.",
    "취소":
        "cancel",
    "확인":
        "confirm",
}

# 숫자가 든 문장 — 숫자는 그대로, 꼬리말만 바꾼다.
# ⚠️ 순서가 중요하다 — 먼저 맞는 규칙이 이긴다.
RULES: list = [
    ("^===\\ (.+?)\\ ·\\ (.+?)\\ \\((.+?)봉\\)\\ ===$",
     "=== \\1 · \\2 (\\3 bars) ==="),
    ("^📊\\ 히트맵:\\ (.+)$",
     "📊 Heat map: \\1"),
    ("^🔁\\ 자동\\ 페이퍼\\ 학습\\ 시작:\\ (.+?)\\ ·\\ (.+?)\\ \\(주기\\ (.+?)s,\\ (.+?)\\)$",
     "🔁 Automatic paper learning started: \\1 · \\2 (every \\3s, \\4)"),
    ("^📺\\ 대시보드:\\ python\\ \\-m\\ quant\\ web\\ \\-\\-open\\ \\ →\\ \\ 감시\\ 탭에서\\ (.+?)\\ 확인$",
     "📺 Dashboard: python -m quant web --open  →  see \\1 in the Monitor tab"),
    ("^📺\\ 감시:\\ 웹\\ 조종석\\ '감시'\\ 탭\\ 또는\\ (.+)$",
     "📺 Monitor: the cockpit's Monitor tab, or \\1"),
    ("^🔍\\ 재현성\\ 검증:\\ (.+?)\\ ·\\ (.+)$",
     "🔍 Reproducibility check: \\1 · \\2"),
    ("^📉\\ 선물\\ 도전자\\ —\\ 자산\\ (.+?)\\ USDT\\ ·\\ 롱\\ (.+?)\\ ·\\ 숏\\ (.+?)\\ ·\\ 총노출\\ (.+?)\\ ·\\ 이번\\ 회차\\ 체결\\ (.+?)건\\ ·\\ 자금조달\\ 누적\\ (.+)$",
     "📉 Futures challenger — equity \\1 USDT · long \\2 · short \\3 · total exposure \\4 · \\5 fills this round · funding paid so far \\6"),
    ("^🏃\\ 장중\\ 도전자\\ —\\ 자산\\ (.+?)\\ USDT\\ \\((.+?)%\\)\\ ·\\ 이번\\ 회차\\ 체결\\ (.+?)건\\ ·\\ 건너뜀\\ (.+?)종목\\ ·\\ 누적\\ 비용\\ (.+?)\\ USDT$",
     "🏃 Intraday challenger — equity \\1 USDT (\\2%) · \\3 fills this round · \\4 symbols skipped · costs so far \\5 USDT"),
    ("^🛡️\\ 장중\\ 감시\\ —\\ (.+)$",
     "🛡️ Intraday check — \\1"),
    ("^📄\\ (.+?)\\ ·\\ (.+?)\\ —\\ 글자\\ (.+?)자$",
     "📄 \\1 · \\2 — \\3 characters"),
    ("^💾\\ 저장:\\ (.+)$",
     "💾 Saved: \\1"),
    ("^📌\\ 고정됨:\\ (.+?)/(.+?)\\ ←\\ (.+?)\\ \\((.+?)부터\\)$",
     "📌 Pinned: \\1/\\2 ← \\3 (from \\4)"),
    ("^🌙\\ 야간\\ 재학습:\\ (.+?)\\ \\(결승전\\ (.+?)봉,\\ 기록:\\ (.+?)/\\)$",
     "🌙 Nightly retraining: \\1 (final \\2 bars, record: \\3/)"),
    ("^===\\ 검증:\\ (.+?)\\ ·\\ (.+?)\\ \\((.+?)봉\\)\\ ===$",
     "=== Validation: \\1 · \\2 (\\3 bars) ==="),
    ("^그리드:\\ (.+)$",
     "Grid: \\1"),
    ("^✅\\ (.+?)개\\ 키를\\ \\.env에\\ 저장했습니다\\ \\(git\\ 미포함\\)\\.$",
     "✅ Saved \\1 keys to .env (not committed)."),
    ("^🔌\\ 웹훅\\ 서버\\ 시작\\ \\((.+?)\\)\\ —\\ (.+?):(.+)$",
     "🔌 Webhook server started (\\1) — \\2:\\3"),
    ("^\\{\"secret\":\"<비밀키>\",\"action\":\"long\",\"symbol\":\"(.+?)\",\"price\":\\{\\{close\\}\\}\\}$",
     "{\"secret\":\"<your-secret>\",\"action\":\"long\",\"symbol\":\"\\1\",\"price\":{{close}}}"),
    ("^===\\ 거래\\ 복기:\\ (.+?)\\ ===$",
     "=== Trade review: \\1 ==="),
    ("^===\\ 손익분기\\ 비용:\\ (.+?)\\ ·\\ (.+?)\\ \\((.+?)봉\\)\\ ===$",
     "=== Break-even cost: \\1 · \\2 (\\3 bars) ==="),
    ("^===\\ A/B\\ 비교:\\ A=(.+?)\\ vs\\ B=(.+?)\\ ·\\ (.+?)\\ \\((.+?)봉\\)\\ ===$",
     "=== A/B comparison: A=\\1 vs B=\\2 · \\3 (\\4 bars) ==="),
    ("^머신러닝\\ 성적표\\ →\\ (.+)$",
     "Machine-learning report card → \\1"),
    ("^실전\\ 적중\\ (.+?)\\ \\((.+?)/(.+?)건\\)\\ ·\\ 우연\\ 배제\\ (.+)$",
     "Live hit rate \\1 (\\2 of \\3) · chance ruled out: \\*4"),
    ("^검증\\ 게이트\\ —\\ 관망\\ (.+?)종목\\ ·\\ 절반\\ (.+?)종목\\ ·\\ 정상\\ (.+?)종목$",
     "Validation gate — standing aside \\1 · halved \\2 · full weight \\3"),
    ("^💸\\ 시장\\ 비용\\ 프리셋\\((.+?)\\):\\ 수수료\\ (.+?)\\ ·\\ 슬리피지\\ (.+?)\\ \\(편도,\\ 근사\\)$",
     "💸 Market cost preset (\\1): commission \\2 · slippage \\3 (one way, approximate)"),
    ("^📄\\ 리포트:\\ (.+)$",
     "📄 Report: \\1"),
    ("^🏆\\ 현재\\ 챔피언\\ 사용:\\ (.+?)\\ \\(야간\\ 재학습이\\ 교체하면\\ 자동\\ 반영됩니다\\)$",
     "🏆 Using the current champion: \\1 (a nightly swap applies automatically)"),
    ("^📅\\ 매일\\ 자동\\ 페이퍼\\ —\\ 전체\\ (.+?)종목\\ \\(챔피언\\ 추종\\)$",
     "📅 Daily automatic paper — all \\1 symbols (following the champion)"),
    ("^📅\\ 매일\\ 자동\\ 페이퍼:\\ (.+?)/(.+?)\\ \\(챔피언\\ 전략\\ 추종\\)$",
     "📅 Daily automatic paper: \\1/\\2 (following the champion strategy)"),
    ("^❌\\ 점검\\ 항목이\\ 하나도\\ 없습니다\\ —\\ 진단이\\ 돌지\\ 않았습니다\\(브로커\\ 이름\\ 확인:\\ (.+?)\\)$",
     "❌ Not a single check ran — the diagnosis did not execute (check the broker name: \\1)"),
    ("^안전장치:\\ 일일\\ 손실\\ 킬스위치\\ \\-(.+?)\\ ·\\ 최대낙폭\\ 서킷\\ \\-(.+?)\\ ·\\ 최대\\ 비중\\ (.+?)\\ ·\\ 주문\\ 재시도/체결\\ 확인$",
     "Safeguards: daily-loss kill switch -\\1 · drawdown circuit breaker -\\2 · maximum weight \\3 · order retries and fill confirmation"),
    ("^🗑\\ 미뤄\\ 둔\\ 알림\\ (.+?)건을\\ 버렸습니다\\(저장되지\\ 않은\\ 일이라\\ 방송하지\\ 않습니다\\)\\.$",
     "🗑 Dropped \\1 deferred alerts (they were never saved, so they are not broadcast)."),
    ("^미뤄\\ 둔\\ 알림\\ (.+?)건\\ \\((.+?)\\)\\.\\ 보내려면\\ \\-\\-flush\\.$",
     "\\1 deferred alerts (\\2). Pass --flush to send them."),
    ("^오래된\\ 게시\\ 폴더\\ (.+?)개\\ 정리:\\ (.+)$",
     "Removed \\1 old post folders: \\2"),
    ("^🛑\\ 숏\\ 하드\\ 스톱:\\ (.+)$",
     "🛑 Short hard stop: \\1"),
    ("^↗️\\ 롱\\ 전용\\(규칙\\ 전략이라\\ 숏\\ 불가\\):\\ (.+)$",
     "↗️ Long only (a rule strategy cannot go short): \\1"),
    ("^⏭️\\ 시세\\ 못\\ 받아\\ 건너뜀:\\ (.+)$",
     "⏭️ Skipped, no quote: \\1"),
    ("^→\\ 장부의\\ 노출\\ 배수를\\ (.+?)로\\ 낮췄습니다\\.$",
     "→ The exposure multiplier in the ledger was lowered to \\1."),
    ("^🔍\\ 문장\\ (.+?)개를\\ 봤지만\\ \\*\\*실행\\ 가능한\\ 규칙을\\ 찾지\\ 못했습니다\\.\\*\\*$",
     "🔍 Read \\1 sentences but **found no rule that can be executed.**"),
    ("^↩️\\ 고정\\ 해제:\\ (.+?)/(.+?)\\ —\\ 다음\\ 실행부터\\ 시스템\\ 챔피언\\ 판단이\\ 복귀합니다\\.$",
     "↩️ Unpinned: \\1/\\2 — the system's own champion returns from the next run."),
    ("^고정돼\\ 있지\\ 않습니다:\\ (.+?)/(.+)$",
     "Not pinned: \\1/\\2"),
    ("^📌\\ (.+?)\\ ←\\ (.+?)\\ \\((.+?)부터\\)\\ —\\ 심사\\ 결과가\\ 아니라\\ 사용자\\ 지정입니다$",
     "📌 \\1 ← \\2 (from \\3) — chosen by you, not by the audition"),
    ("^'(.+?)'의\\ 기본\\ 그리드가\\ 없습니다\\.\\ \\-\\-grid\\ JSON으로\\ 지정하세요\\.\\ \\(기본\\ 지원:\\ (.+?)\\)$",
     "There is no default grid for '\\1'. Give one with --grid JSON. (Built in for: \\2)"),
    ("^OOS\\ 샤프\\ (.+?)\\ ·\\ 총수익\\ (.+?)\\ ·\\ 최대낙폭\\ (.+?)\\ ·\\ 구간\\ (.+?)개$",
     "Out-of-sample Sharpe \\1 · total return \\2 · max drawdown \\3 · \\4 windows"),
    ("^DSR\\(시행\\ (.+?)회\\ 보정\\):\\ (.+?)\\ (.+)$",
     "DSR (corrected for \\1 trials): \\2 \\3"),
    ("^💾\\ 검증\\ 결과\\ 저장:\\ (.+)$",
     "💾 Validation result saved: \\1"),
    ("^📄\\ 검증\\ 리포트\\(그래프\\):\\ (.+)$",
     "📄 Validation report (charts): \\1"),
    ("^\\(알림\\ 전송\\ 실패:\\ (.+?)\\)$",
     "(Could not send the alert: \\1)"),
    ("^🗺\\ 규칙\\ 유니버스\\ 재계산\\ —\\ (.+?)종목\\ \\(기준일\\ (.+?)\\)$",
     "🗺 Recomputing the rule universe — \\1 symbols (as of \\2)"),
    ("^⚠️\\ 유니버스\\ 재계산\\ 실패\\ —\\ 직전\\ 구성\\ 유지:\\ (.+)$",
     "⚠️ Could not recompute the universe — keeping the previous set: \\1"),
    ("^\\(텔레메트리\\ 생략:\\ (.+?)\\)$",
     "(Telemetry skipped: \\1)"),
    ("^챔피언\\ 자동\\ 추종:\\ (.+?)\\ (.+)$",
     "Following the champion automatically: \\1 \\2"),
    ("^🇺🇸\\ 미국\\ 장중\\ 도전자\\ —\\ 회차\\ 없음:\\ (.+)$",
     "🇺🇸 US intraday challenger — no round: \\1"),
    ("^🇺🇸\\ 미국\\ 장중\\ 도전자\\ —\\ 자산\\ (.+?)\\ USD\\ \\((.+?)%\\)\\ ·\\ 체결\\ (.+?)건\\ ·\\ 누적\\ 비용\\ (.+?)\\ USD$",
     "🇺🇸 US intraday challenger — equity \\1 USD (\\2%) · \\3 fills · costs so far \\4 USD"),
    ("^🇺🇸\\ 미국\\ 장중\\ 도전자\\ 실패\\(코인\\ 트랙\\ 무관\\):\\ (.+)$",
     "🇺🇸 US intraday challenger failed (unrelated to the crypto track): \\1"),
    ("^❌\\ 장부를\\ 읽지\\ 못했습니다\\((.+?)\\):\\ (.+)$",
     "❌ Could not read the ledger (\\1): \\2"),
    ("^건너뜀:\\ (.+)$",
     "Skipped: \\1"),
    ("^'(.+?)'\\ 시장은\\ 실거래를\\ 지원하지\\ 않습니다\\.$",
     "The '\\1' market does not support live trading."),
    ("^⚠️\\ 통합\\ 포트폴리오\\ 실패\\ —\\ (.+)$",
     "⚠️ Combined portfolio failed — \\1"),
    ("^⚠️\\ 섀도\\ 대조군\\ 실패\\ —\\ (.+)$",
     "⚠️ Shadow control arm failed — \\1"),
    ("^챔피언\\((.+?)\\):\\ (.+?)\\ (.+)$",
     "Champion (\\1): \\2 \\3"),
    ("^⏳\\ 시간\\ 예산\\((.+?)초\\)\\ 소진\\ —\\ 남은\\ (.+?)종목은\\ 다음\\ 밤에\\ 먼저\\ 잽니다$",
     "⏳ Time budget (\\1s) spent — the remaining \\2 symbols are measured first tomorrow night"),
    ("^🔌\\ 거래소\\ 연결\\ 확인\\ 실패:\\ (.+)$",
     "🔌 Could not verify the exchange connection: \\1"),
    ("^📨\\ 텔레그램\\ 확인\\ 실패:\\ (.+)$",
     "📨 Could not verify Telegram: \\1"),
    ("^❌\\ (.+?):(.+?)\\ 검증\\ 실패:\\ (.+?):\\ (.+)$",
     "❌ \\1:\\2 validation failed: \\3: \\4"),
    ("^⚠️\\ 검증\\ 커서를\\ 남기지\\ 못했습니다:\\ (.+)$",
     "⚠️ Could not leave a validation cursor: \\1"),
    ("^총수익률\\s+: (.+)$",
     "Total return   : \\1"),
    ("^CAGR\\s+: (.+)$",
     "CAGR           : \\1"),
    ("^변동성\\(연\\)\\s+: (.+)$",
     "Volatility (yr): \\1"),
    ("^샤프지수\\s+: (.+)$",
     "Sharpe         : \\1"),
    ("^소르티노\\s+: (.+)$",
     "Sortino        : \\1"),
    ("^최대낙폭\\s+: (.+)$",
     "Max drawdown   : \\1"),
    ("^칼마지수\\s+: (.+)$",
     "Calmar         : \\1"),
    ("^승률\\s+: (.+)$",
     "Win rate       : \\1"),
    ("^이익팩터\\s+: (.+)$",
     "Profit factor  : \\1"),
    ("^거래횟수\\s+: (.+)$",
     "Trades         : \\1"),
    ("^시장노출\\s+: (.+)$",
     "Exposure       : \\1"),
    ("^매수후보유\\s+: (.+)$",
     "Buy and hold   : \\1"),
    ("^초과수익\\s+:(\\s+\\S+)\\s\\s(.+)$",
     "Excess return  :\\1  \\*2"),
    ("^ℹ️ 연습용 모의 데이터입니다\\(--market (.+)\\) — 실제 시장이 아닙니다\\.$",
     "ℹ️ This is synthetic practice data (--market \\1) — not a real market."),
]
