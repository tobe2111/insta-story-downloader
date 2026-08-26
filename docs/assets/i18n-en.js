/**
 * 영어 사전 — 한국어 문장이 열쇠다 (2026-08-25).
 *
 * ■ 읽는 사람에게 (사장님 지시: "서비스 영어로도 만들어줘")
 *
 * 이 파일은 화면에 **실제로 보이는 문장**만 담는다. 코드 주석·문서는
 * 한국어로 둔다(개발용이고, 번역하면 두 벌이 갈라진다).
 *
 * ■ 규칙 세 가지
 *
 *   ① **모르면 비운다.** 사전에 없는 문장은 한국어로 남는다. 기계 번역으로
 *      메우지 않는다 — 이 사이트는 돈 이야기를 하는 공개 장부이고,
 *      "대충 맞는 영어"는 숫자 옆에서 사실이 아닌 주장이 된다.
 *   ② **숫자는 건드리지 않는다.** 금액·날짜·종목 수는 장부에서 온 값이다.
 *      숫자가 든 문장은 아래 rules(정규식)가 **꼬리말만** 바꾼다.
 *   ③ **한계는 한계 그대로 옮긴다.** "수익을 보장하지 않습니다"류 문장을
 *      영어에서 부드럽게 바꾸지 않는다. 그 문장들이 이 제품의 정체성이다.
 *
 * ■ 지금 덮은 범위
 *
 *   상단 바 · 코인 단타 · 미국주식 단타 · 코인 선물 · 주간 아카이브
 *
 * 첫 화면(index)·실기록(paper)·오늘의 판단(today)·기록 검증(trust)은
 * 분량이 커서 다음 차례다. 그 페이지들은 영어로 봐도 한국어가 남는다 —
 * 그 사실을 언어 버튼 옆에 적는다(지어내지 않는다).
 */
(function (root) {
  "use strict";

  root.QUANT_EN = {
    /** 아직 영어가 덜 채워진 페이지 — 화면이 그렇다고 밝힌다. */
    partial: ["index.html", "paper.html", "today.html", "trust.html",
              "ml.html", "admin.html"],

    strings: {
      // ── 상단 바 ────────────────────────────────────────────
      "100만 챌린지": "1M Won Challenge",
      "코인 단타": "Crypto Intraday",
      "미국주식 단타": "US Stocks Intraday",
      "코인 선물": "Crypto Futures",
      "머신러닝": "Machine Learning",
      "실기록 (100만)": "Full Record (1M)",
      "오늘의 판단": "Today's Call",
      "기록 검증": "Verify the Record",
      "주간 아카이브": "Weekly Archive",
      "무료 다운로드": "Free download",
      "대시보드": "Dashboard",
      "대시보드 (운영 설정)": "Dashboard (operator settings)",
      "운영 설정(로그인 필요)": "Operator settings (login required)",
      "메뉴 열기": "Open menu",
      "메뉴 닫기": "Close menu",

      // ── 종목 이름 ──────────────────────────────────────────
      "비트코인": "Bitcoin",
      "이더리움": "Ethereum",
      "솔라나": "Solana",
      "비앤비": "BNB",
      "리플": "XRP",
      "엔비디아": "NVIDIA",
      "아마존": "Amazon",
      "애플": "Apple",
      "마이크로소프트": "Microsoft",
      "메타": "Meta",
      "테슬라": "Tesla",
      "삼성전자": "Samsung Electronics",
      "SK하이닉스": "SK hynix",
      "현대차": "Hyundai Motor",
      "LG화학": "LG Chem",
      "KB금융": "KB Financial",
      "나스닥100 ETF": "Nasdaq-100 ETF",

      // ── 표 머리글 · 짧은 라벨 ──────────────────────────────
      "종목": "Symbol",
      "수량": "Qty",
      "금액": "Amount",
      "현재가": "Last price",
      "평균매입가": "Avg cost",
      "수익률": "Return",
      "손익": "P&L",
      "실현 손익": "Realized P&L",
      "평가금액": "Market value",
      "방향": "Side",
      "롱": "Long",
      "숏": "Short",
      "비용": "Cost",
      "신호": "Signal",
      "매수": "Buy",
      "매도": "Sell",
      "매수/매도": "Buy / Sell",
      "사기": "Buy",
      "팔기": "Sell",
      "청산": "Liquidation",
      "주문": "Order",
      "결과 방향": "Resulting side",
      "체결": "Fills",
      "회차": "Rounds",
      "주기": "Bar interval",
      "총 노출": "Gross exposure",
      "증거금률": "Margin ratio",
      "낸 비용": "Costs paid",
      "자금조달 누계": "Funding paid (cumulative)",
      "시드 (가상)": "Seed (simulated)",
      "마지막 회차 확정": "Last round settled",
      "체결 / 회차": "Fills / rounds",
      "이미 낸 비용": "Costs already paid",
      "비용을 뺀 뒤": "after costs",
      "비용 뺀 뒤": "after costs",
      "총수익률": "Gross return",
      "비용 물기 전": "before costs",
      "같은 기간 보유": "Buy & hold, same period",
      "누적 비용": "Cumulative cost",
      "매도만 · 비용 뺀 뒤": "Sells only · after costs",
      "시각 (한국)": "Time (KST)",
      "시각(한국 시간)": "Time (KST)",
      "금액(USDT)": "Amount (USDT)",
      "비용(USDT)": "Cost (USDT)",
      "입니다.": ".",
      "와": "and",
      "· 감시 주기 예약 5분 /": "· watch scheduled every 5 min /",
      "(한국 시간)": "(KST)",
      "1시간봉": "1-hour bars",
      "1시간 (본 실험)": "1 hour (this experiment)",
      "15분": "15 min",
      "5분": "5 min",
      "4종목": "4 symbols",
      "0종목": "0 symbols",
      "1배": "1x",
      "낮은": "low",
      "가정치": "an assumption",
      "참고 진단": "a diagnostic, not a verdict",
      "판정 기준": "Decision criteria",
      "등록일": "Registered on",
      "관찰 진도:": "Observation progress:",
      "정직한 한계": "Honest limits",
      "숨기지 않습니다": "nothing hidden",
      "자산 곡선": "Equity curve",
      "USDT 기준": "in USDT",
      "최근 체결": "Recent fills",
      "종목별 손익": "P&L by symbol",
      "지금 들고 있는 것": "What it holds right now",
      "본 계좌와 나란히": "Side by side with the main account",
      "같은 기간 · % 수익률": "same period · % return",
      "주기 사다리": "Interval ladder",
      "체결 방식 실험": "Execution-style experiment",
      "같은 신호 · 시장가 vs 지정가": "same signal · market vs limit",
      "지정가 체결/미체결": "Limit filled / unfilled",
      "용어:": "Terms:",
      "본 계좌와 완전히 분리": "fully separate from the main account",
      "롱과 숏을 같이 봅니다": "Longs and shorts side by side",
      "롱(오름에 걺)": "Long (betting on a rise)",
      "선물 실험 자산 곡선": "Futures experiment equity curve",
      "코인 단타 실험 자산 곡선": "Crypto intraday experiment equity curve",
      "USDT 기준 · 비용과 자금조달을 뺀 뒤":
        "in USDT · after costs and funding",
      "언제 무엇을 얼마에 샀나": "what was bought, when, at what price",
      "지금 얼마 벌고 있나 · 아직 안 판 평가액":
        "what it is up or down right now · unrealized",
      "1시간 vs 15분 vs 5분 — 어느 주기가 비용을 이기나":
        "1 hour vs 15 min vs 5 min — which interval beats its costs",
      "시장가 (본 실험) · 그림자 시작 이후":
        "Market orders (this experiment) · since the shadow began",
      "지정가 (그림자) · 같은 기간":
        "Limit orders (shadow) · same period",
      "장중 실험 (1시간마다)": "Intraday experiment (hourly)",
      "본 계좌 (하루 1회) · 같은 기간":
        "Main account (once a day) · same period",
      "그냥 보유 (첫 회차에 사서 그대로) · 사는 비용 포함":
        "Buy & hold (bought at round one) · entry cost included",
      "셋 다": "All three are",
      "마지막 회차:": "Last round:",
      "그 전에는 어떤 승패 판정도 내리지 않습니다.":
        "Until then no win-or-lose verdict is made.",
      "사전 등록 — 결과를 보기 전에 정했습니다":
        "Pre-registered — written down before any result was seen",
      "이 트랙이 스스로에게 거는 제한":
        "Limits this track puts on itself",
      "결과를 보기 전에 정했습니다": "decided before seeing any result",
      "배율은 신호의 확신이 정합니다":
        "Leverage is set by the model's confidence",
      "(최대 3배). 예측이 자신 없는 날은":
        "(3x maximum). On days the prediction is not confident it stays at",

      // ── 미국주식 단타 ──────────────────────────────────────
      "미국주식 단타 실험": "US stocks intraday experiment",
      "시뮬레이션 · 가상 자금(USD)": "Simulation · play money (USD)",
      "미국 정규장에서만": "only during US regular hours",
      "도는 트랙입니다. 코인 단타와 같은 규칙·같은 비용 모델을 빌려 쓰고, 다른 것은 시장의 물리 조건 하나뿐입니다 — 장이 닫혀 있으면 판단도 체결도 기록도 없습니다.":
        ". It borrows the same rules and the same cost model as the crypto intraday track; the only difference is a physical fact about the market — when the exchange is closed there is no call, no fill and no record.",
      "실제 돈이 아니며": "This is not real money",
      ", 100만 챌린지 판단에는 쓰이지 않습니다.":
        ", and it is never used in the 1M Won Challenge's decisions.",
      "이 페이지는": "This page covers",
      "미국주식만": "US stocks only",
      "다룹니다 —": "—",
      "선물(양방향)": "futures (both directions)",
      "은 각각 자기 페이지가 있습니다. 계좌도 장부도 따로입니다.":
        "each have their own page. Separate accounts, separate ledgers.",
      "는 각각 자기 페이지가 있습니다. 계좌도 장부도 따로입니다.":
        "each have their own page. Separate accounts, separate ledgers.",
      "미국 정규장은 한국 시간으로": "US regular hours in Korean time are",
      "밤 10시 30분 ~ 새벽 5시": "22:30 – 05:00",
      "입니다(미국 서머타임 기준. 겨울에는 한 시간씩 밀립니다).":
        "(US daylight saving time; one hour later in winter).",
      "장 밖 시간에 기록이 없는 것은 고장이 아니라 정상":
        "An empty stretch outside those hours is normal, not a fault",
      "미국주식 장중 실험 — 가상 자금 · 실제 돈이 아닙니다":
        "US stocks intraday experiment — play money, not real money",
      "미국 정규장(뉴욕 09:30~16:00)에서만 판단·체결 — 장 밖 회차는 기록이 없습니다":
        "Calls and fills only during US regular hours (New York 09:30–16:00) — no records outside them",
      "시세 출처: 무료 공개 시세(야후) — 비공식 경로라 요청이 몰리면 막힐 수 있습니다. 못 받은 종목은 그 회차를 쉽니다":
        "Price source: free public quotes (Yahoo) — an unofficial route that can be blocked under load. A symbol we cannot fetch sits that round out.",
      "원/달러를 못 받아 원화 환산을 건너뜁니다 — 아무 값이나 넣어 적지 않습니다.":
        "No USD/KRW rate was available, so the won conversion is skipped — we do not fill the blank with a made-up number.",
      "산 가격의 평균 — 그 거래의 비용이 반영된 값입니다":
        "Average purchase price — the cost of those trades is included",
      "장부가 마지막으로 확인한 가격입니다 — 실시간이 아닙니다":
        "The last price the ledger confirmed — not live",
      "아직 안 판 평가 손익입니다. 팔 때 비용이 한 번 더 듭니다.":
        "Unrealized P&L. Selling costs money once more.",
      "판 시점에 확정된 손익입니다 — 비용을 뺀 값. 매수에는 없습니다.":
        "P&L locked in at the moment of the sale, after costs. Buys have none.",
      "0에 가까울수록 약한 신호입니다. 약하면 조금만 삽니다.":
        "The closer to zero, the weaker the signal — and the smaller the position.",
      "새로 여는 주문이거나, 평균매입가를 세기 전의 옛 기록입니다 — 0이라는 뜻이 아닙니다":
        "Either a newly opened order or an old record from before average cost was tracked — it does not mean zero",

      // ── 코인 단타 ──────────────────────────────────────────
      "코인 단타 실험": "Crypto intraday experiment",
      "시뮬레이션 · 가상 자금(USDT)": "Simulation · play money (USDT)",
      "코인을 더 자주 사고팔면 정말 더 버는가":
        "Does trading crypto more often actually earn more?",
      "— 믿음이 아니라 측정으로 답하기 위한 트랙입니다. 100만 챌린지에서 쓰는 것과 같은 규칙·같은 비용 모델을":
        "— a track built to answer that by measurement rather than belief. It applies the same rules and cost model used in the 1M Won Challenge to",
      "에 적용해, 매매를 늘리면 확실히 늘어나는 비용(수수료·미끄러짐)을 우위가 이기는지 잽니다.":
        ", and measures whether the edge beats the costs (fees and slippage) that trading more definitely adds.",
      "코인만": "crypto only",
      "장중 도전자 실험 — 가상 자금 · 실제 돈이 아닙니다":
        "Intraday challenger experiment — play money, not real money",
      "= 수수료 + 미끄러짐(주문 순간 가격이 살짝 불리해지는 것) ·":
        "= fees + slippage (the price moving slightly against you at the moment of the order) ·",
      "= 전략이 내린 매매 판단(사자/팔자/관망)":
        "= the strategy's call (buy / sell / stand aside)",
      "실측 최악 113분": "worst observed gap 113 min",
      "— 이 기준은 첫 기록이 쌓이기 전에 등록했고 바꾸지 않는다. 바꿔야 한다면 그 사실과 이유를 이 자리에 함께 공개한다.":
        "— these criteria were registered before the first record and are not changed. If they ever must change, the change and the reason are published right here.",
      "관찰 90일 이상 — 충족 전에는 어떤 승패 판정도 내리지 않는다(30일 시점은 중간 참고 판독만)":
        "At least 90 days of observation — no win-or-lose verdict before that (day 30 is an interim read only)",
      "비용을 뺀 누적 수익률이 같은 기간 본 계좌(하루 1회 판단)보다 높다":
        "Cumulative return after costs beats the main account (one call a day) over the same period",
      "일별 수익률 차이의 95% 신뢰구간이 0을 배제한다 — 우연으로 설명되는 차이는 무승부다":
        "The 95% confidence interval of the daily return difference excludes zero — a gap explainable by chance is a draw",
      "실험의 최대 낙폭이 같은 기간 본 계좌의 1.5배를 넘지 않는다 — 수익이 위험을 사서 온 것이면 승리가 아니다":
        "The experiment's max drawdown stays within 1.5x the main account's — a return bought with risk is not a win",
      "두 열을 같이 보세요.": "Read the two columns together.",
      "두 수익률의 차이가 곧": "The gap between the two returns is exactly",
      "가상 자금(USDT)입니다 — 실제 돈이 아니고, 실제 호가·유동성을 겪지 않습니다":
        "Play money (USDT) — not real money, and it never meets a real order book or real liquidity",
      "가상 자금(USD)입니다 — 실제 돈이 아니고, 실제 호가·유동성을 겪지 않습니다.":
        "Play money (USD) — not real money, and it never meets a real order book or real liquidity.",
      "비용은 실전과 같은 모델(수수료+미끄러짐)로 매 거래에 뺐지만, 실측 체결과 다를 수 있습니다.":
        "Costs are deducted on every trade with the same model as live (fees + slippage), but real fills may differ.",
      "비용은 실전 오디션과 같은 모델(수수료+슬리피지)로 매 거래에 뺐지만, 실측 체결과 다를 수 있습니다":
        "Costs are deducted on every trade with the same model as the live audition (fees + slippage), but real fills may differ",
      "정규장 밖에서는 아무 기록도 만들지 않습니다 — 시간외 거래를 흉내 내지 않습니다.":
        "Nothing is recorded outside regular hours — we do not simulate after-hours trading.",
      "시세를 실데이터로 못 받은 종목은 그 회차를 건너뛰고 그렇게 적습니다. 합성 시세로 가짜 체결을 만들지 않습니다.":
        "A symbol whose real quote we could not fetch sits the round out, and we say so. We never fabricate fills from synthetic prices.",
      "주기 사다리(1시간·15분·5분)는": "The interval ladder (1 hour, 15 min, 5 min) is",
      "입니다 — 판정은 사전에 등록한 1시간 트랙 하나로만 합니다. 나중에 좋은 주기를 골라 \"이겼다\"고 말하지 않기 위해서입니다.":
        "— the verdict rests on the pre-registered 1-hour track alone, so that nobody can pick the best-looking interval afterwards and call it a win.",
      "가상 자금 실험입니다. 실제 돈이 아니며 투자 권유가 아닙니다. 수익을 보장하지 않습니다.":
        "This is a play-money experiment. It is not real money, not investment advice, and no return is guaranteed.",
      "챔피언 파라미터는 일봉에서 뽑혔습니다 — 1시간봉 적용 자체가 이 실험의 가설이고, 검증된 전략이 아닙니다":
        "The champion parameters were selected on daily bars — applying them to hourly bars is this experiment's hypothesis, not a proven strategy",
      "본 계좌(100만 챌린지)와 완전히 분리돼 있고 그 판단에 쓰이지 않습니다 — 비교는 같은 기간 퍼센트 수익률로만 합니다":
        "Fully separate from the main account (1M Won Challenge) and never used in its decisions — comparison is by percent return over the same period only",
      "판정은 어떻게 하나": "How the verdict is made",
      "이 트랙이": "whether this track",
      "같은 기간의 본 계좌(하루 한 번 판단)":
        "the main account over the same period (one call a day)",
      "이 페이지의 숫자는 배치가 회차마다 커밋하는":
        "Every number on this page is read only from",
      "판 시점에 실제로 확정된 손익 — 평균 매입가와 비교하고, 그 거래의 비용까지 뺀 값입니다. 매수에는 없습니다(아직 확정된 것이 없으므로).":
        "P&L actually locked in at the sale — measured against average cost and after that trade's costs. Buys have none (nothing is locked in yet).",

      // ── 코인 선물 ──────────────────────────────────────────
      "무기한 선물 · 가상 자금(USDT) · 최대 3배":
        "Perpetual futures · play money (USDT) · up to 3x",
      "무엇으로 하나:": "What it trades:",
      "미국주식이나 ETF가 아니라": "not US stocks or ETFs, but",
      "코인 무기한 선물": "crypto perpetual futures",
      "입니다(비트코인·이더리움·솔라나· 바이낸스코인·리플). 코인 단타 트랙과":
        "(Bitcoin, Ethereum, Solana, BNB, XRP). It uses",
      "같은 다섯 종목": "the same five symbols",
      "을 씁니다 — 그래야 \"방향을 하나 더 쓰면 나아지는가\"라는 질문에서":
        "as the crypto intraday track — so that in the question \"does allowing a second direction help?\" ",
      "방향 말고는 다 같게": "everything except direction is held equal",
      "둘 수 있습니다. 종목까지 다르면 성적 차이가 무엇 때문인지 영영 모릅니다.":
        ". If the symbols differed too, we could never tell what caused the difference.",
      "지금까지 이 시스템은 모든 판단을": "Until now this system made every call",
      "“산다 / 안 산다”": "“buy / don't buy”",
      "둘로만 냈습니다. 그런데 머신러닝이 실제로 내놓는 것은":
        "— two options only. But what the model actually produces is",
      "오를 확률": "a probability of going up",
      "입니다. 확률이 높으면 삽니다. 그러면 확률이 아주":
        ". A high probability means buy. So what happens on days the probability is very",
      "날 — 모델이 “내릴 것”이라고 꽤 확신하는 날 — 은 어떻게 될까요?":
        "— days the model is fairly confident it will fall?",
      "“안 산다”로 뭉개져 버려집니다.":
        "They get flattened into “don't buy” and thrown away.",
      "“모르겠다”와 “내린다”가 같은 취급을 받는 것입니다.":
        "“I don't know” and “it will fall” are treated as the same thing.",
      "이 트랙은 그": "This track uses that",
      "버려지던 절반": "discarded half",
      "을 씁니다. 내릴 것 같으면 내리는 쪽에 겁니다(숏).":
        ". If it looks like a fall, it bets on the fall (short).",
      "같은 규칙 · 같은 종목 · 같은 비용":
        "Same rules · same symbols · same costs",
      "이고, 다른 것은 방향을 허용하느냐 하나뿐입니다 — 그래야 성적 차이가 무엇 때문인지 알 수 있습니다.":
        "; the only difference is whether the second direction is allowed — that is the only way to know what caused any difference in results.",
      "선물(양방향)만": "futures (both directions) only",
      "아직 가설입니다.": "This is still a hypothesis.",
      "“숏이 더 자주 나온다”와 “숏이 돈을 번다”는 전혀 다른 말입니다. 숏에는 롱에 없는 비용과 위험이 붙습니다(아래에 그대로 적습니다). 그래서 믿지 않고":
        "“shorts fire more often” and “shorts make money” are entirely different claims. Shorting carries costs and risks that longs do not (all written out below). So we do not assume — we",
      "나란히 돌려서 잽니다.": "run it side by side and measure.",
      "지금 허락된 배율을 읽지 못했습니다 — 표시가 없으면 1배로 보십시오.":
        "The currently permitted leverage could not be read — with no figure shown, assume 1x.",
      "그대로이고, 크게 확신하는 날에만 올라갑니다 — 매일 똑같이 최대치를 태우는 것은 확신이 아니라 습관입니다.":
        ", rising only on days of real conviction — running the maximum every day is habit, not conviction.",
      "다만 그 확신이 실제로 맞는지는 이 트랙이 아직 증명하지 않았습니다.":
        "Whether that conviction is actually right is something this track has not yet proven.",
      "배율은 우위를 만드는 장치가 아니라 이 실험의 결과를 크게 만드는 장치입니다 — 좋은 쪽으로도, 나쁜 쪽으로도.":
        "Leverage does not create an edge; it enlarges this experiment's outcome — in both directions.",
      "배율을 쓰면 청산이 생깁니다.": "Leverage brings liquidation.",
      "자산이 총 노출의": "If equity falls below",
      "밑으로 내려가면 전량 강제 청산합니다. 3배로 태운 자리는":
        "of gross exposure, everything is force-liquidated. A position run at 3x",
      "30%쯤 역행하면 거기서 끝":
        "ends right there after roughly a 30% move against it",
      "이고, 그 뒤 값이 되돌아와도 회복할 것이 없습니다. 유지증거금률은":
        ", and if the price comes back afterwards there is nothing left to recover. The maintenance margin rate is",
      "이며 실제 거래소와 다릅니다.": "and differs from a real exchange.",
      "자금조달 비용을 뭅니다.": "Funding is paid.",
      "무기한 선물은 8시간마다 포지션에 비례해 돈을 주고받습니다. 이걸 빼면 이 트랙만 유리한 자로 재게 됩니다. 요율은":
        "Perpetual futures exchange payments every 8 hours in proportion to the position. Leaving that out would measure this track with a friendlier ruler. The rate is",
      "입니다(8시간마다 0.010%) — 실제 요율을 받아 오지 않습니다.":
        "(0.010% every 8 hours) — we do not fetch the real rate.",
      "숏에는 손실 한도가 있습니다": "Shorts carry a loss cap",
      "(25%). 롱은 최악이라도 −100%에서 멈추지만(가격이 0), 숏은 가격이 오르는 만큼 계속 잃습니다.":
        "(25%). A long stops at −100% in the worst case (price hits zero); a short keeps losing as long as the price keeps rising.",
      "숏을 못 하는 종목은 못 한다고 적습니다.":
        "Where a short is impossible, we say so.",
      "규칙으로 매매하는 종목은 애초에 “내린다”는 신호를 내지 않습니다 — 억지로 만들지 않습니다. 지금 롱 전용:":
        "Rule-based symbols never emit a “it will fall” signal in the first place — and we do not manufacture one. Currently long-only:",
      "가상 자금(USDT)입니다 — 실제 돈이 아니고, 실제 호가·유동성·증거금을 겪지 않습니다":
        "Play money (USDT) — not real money, and it never meets a real order book, real liquidity or a real margin call",
      "숏은 머신러닝 챔피언이 붙은 종목에서만 가능합니다 — 규칙 전략은 음수 신호를 내지 않습니다":
        "Shorts are possible only on symbols whose champion is a machine-learning model — rule strategies emit no negative signal",
      "자산 ÷ 총 노출입니다. 이 값이 유지선 밑으로 내려가면 전량 강제 청산됩니다.":
        "Equity ÷ gross exposure. If it falls below the maintenance line, everything is force-liquidated.",
      "숏은 '내리면 버는' 자리입니다. 수량은 절댓값으로 적었고, 방향은 옆 칸에 있습니다.":
        "A short profits when the price falls. Quantities are shown as absolute values; the direction is in the next column.",
      "포지션을 덮은 시점에 확정된 손익 — 진입가와 비교하고 그 거래의 비용까지 뺀 값입니다. 새로 여는 주문에는 없습니다.":
        "P&L locked in when the position was closed — measured against the entry price and after that trade's costs. Newly opened orders have none.",

      // ── 2차 보완 (실제 화면에서 남은 것을 보고 채웠다) ────────
      "비용까지 그대로": "costs included",
      "시장 국면과 비용이 만든 것일 수 있어":
        "may be an artifact of the market regime and of costs, so",
      "돼 있습니다. 자기 장부만 쓰고, 여기 숫자는 100만 챌린지 판단에 쓰이지 않습니다.":
        ". It keeps its own ledger, and none of these numbers enter the 1M Won Challenge's decisions.",
      "확신도 눈금의 끝을 상승확률 1.00에서 0.70으로 당겼습니다 — 같은 예측에도 더 큰 금액이 나갑니다. 모델이 상승확률 0.80을 넘은 적이 한 번도 없어, 종목 몫의 10%쯤만 쓰이고 있었습니다. 이 날 이전 회차는 옛 눈금이며 그 기록은 고치지 않았습니다. 크게 굴린다고 더 버는 것은 아니며, 손실도 같은 배로 커집니다.":
        "The top of the conviction scale was pulled in from a 1.00 probability of a rise to 0.70 — the same prediction now sends out a larger amount. The model had never once exceeded 0.80, so only about 10% of each symbol's budget was being used. Rounds before this date used the old scale and those records are not rewritten. Betting bigger does not mean earning more; losses grow by the same multiple.",
      "배율을 켰습니다(최대 3배, 신호의 확신에 비례). 청산도 함께 모델에 넣었습니다. 사장님 지시 — \"그만큼 수익 실현에 확신이 있으면 하는거잖아\". 이 날 이전 회차는 전부 1배이며, 그 기록은 고치지 않았습니다.":
        "Leverage was switched on (3x maximum, in proportion to the signal's conviction), with liquidation modelled alongside it. Rounds before this date were all 1x and those records are not rewritten.",
      "레버리지를 씁니다(최대 3배). 배율은 **신호의 확신에 비례**합니다 — 확신이 없는 날은 1배입니다. 다만 그 확신이 실제로 맞는지는 이 트랙이 아직 증명하지 않았습니다":
        "It uses leverage (3x maximum), in proportion to the signal's conviction — 1x on days without conviction. Whether that conviction is actually right is something this track has not yet proven",
      "배율을 쓰면 **청산**이 생깁니다. 자산이 총 노출의 5% 밑으로 내려가면 전량 강제 청산합니다 — 그 뒤 가격이 되돌아와도 회복할 것이 없습니다. 유지증거금률 5%는 **가정치**이며 실제 거래소와 다릅니다":
        "Leverage brings liquidation. If equity falls below 5% of gross exposure, everything is force-liquidated — and if the price comes back afterwards there is nothing left to recover. The 5% maintenance margin is an assumption and differs from a real exchange",
      "자금조달 비용은 **가정치**입니다(8시간마다 0.01%) — 실제 요율을 받아 오지 않습니다. 실제와 다를 수 있습니다":
        "The funding cost is an assumption (0.01% every 8 hours) — we do not fetch the real rate, and reality may differ",
      "\'숏이 더 자주 발동한다\'와 \'숏이 돈을 번다\'는 다른 말입니다. 이 트랙은 후자를 아직 증명하지 않았습니다":
        "\"shorts fire more often\" and \"shorts make money\" are different claims. This track has not yet proven the second one",
      "\'5분마다\'는 예약일 뿐이며 실제 간격은 실측(observed_gap_minutes)이 말합니다 — 공용 러너는 예약을 크게 밀 수 있습니다":
        "\"every 5 minutes\" is only the schedule; the real gap is what we measure (observed_gap_minutes) — shared runners can push a schedule far back",
      "입니다 — 총수익률이 비슷한데 순수익률만 벌어졌다면 신호가 나쁜 것이 아니라 회전 비용을 못 견딘 것입니다(처방이 다릅니다: 전략 교체가 아니라 체결 개선). 짧은 구간의 순서는":
        " — if gross returns are similar but only the net returns diverge, the signal is not bad; it could not carry the turnover cost (a different prescription: improve execution, do not swap the strategy). Over short stretches the ordering",
      "우열 판정에 쓰지 않습니다. 주기별 트랙은 같은 전략·같은 체결 규칙에 봉 주기만 다릅니다. 트랙 수가 늘면 우연히 좋아 보이는 주기가 나올 확률도 늘어납니다 — 판정은 본 실험(1시간)의 90일 기준만 유효하고, 사다리는 참고 진단입니다.":
        "the ordering here is not used to declare a winner. The ladder tracks share the strategy and the execution rules and differ only in bar interval. More tracks mean more chances that one looks good by luck — only the 90-day criteria on the main experiment (1 hour) decide anything; the ladder is a diagnostic.",
      "보다 비용을 빼고도 퍼센트 수익률로 앞서는지를 봅니다. 표본이 얇을 때는 단정하지 않습니다 — 며칠치 우위는 운과 구별되지 않습니다. 이긴다는 것이 충분한 기록으로 증명되면, 지금 진행 중인 90일 공개 측정이 끝나는 경계(2세대)에서 본 계좌 적용을 검토합니다. 그 전에는 이 페이지 밖으로 나가지 않습니다.":
        " on percent return after costs. With a thin sample we state nothing — a few days of lead is indistinguishable from luck. If winning is ever proven by enough record, applying it to the main account will be considered at the boundary where the 90-day public measurement now under way ends (generation 2). Until then it does not leave this page.",
      ": 최소 관찰 기간 30일 → 90일 — 외부 검토 지적: 두 트랙의 성과 차이는 수익률 차이라 봉 수가 아니라 기간이 지배한다. 30일 신뢰구간은 폭이 넓어 진짜 우위를 놓칠 확률과 우연을 우위로 읽을 확률이 둘 다 높다. 첫 기록 반나절 시점(결과가 쌓이기 전)에 고친다 — 지금 고치면 정직한 수정이고 30일 뒤에 고치면 골대 이동이다. 30일 시점에는 중간 참고 판독만 하고 확정 판정은 90일이다.":
        ": minimum observation 30 days → 90 days. Raised by outside review: the difference between the two tracks is a difference in returns, so it is governed by elapsed time, not by the number of bars. A 30-day confidence interval is wide enough that both missing a real edge and reading luck as an edge are likely. Changed half a day after the first record, before results accumulated — changing it now is an honest amendment; changing it after 30 days would be moving the goalposts. Day 30 gives an interim read only; the binding verdict is at 90 days.",

      // ── 원화 환산 안내 (감사 312) ────────────────────────────
      "한국 돈으로 보면 지금": "In Korean won that is",
      "같은 환율": "the same rate",
      "환율 변동은 이 실험의 성적에 들어가지 않습니다":
        "moves in the exchange rate do not enter this experiment's result",
      ". USDT는 1달러로 가정했습니다 — 연동이 깨진 적이 있습니다.)":
        ". USDT is assumed to equal one dollar — that peg has broken before.)",

      // ── 스스로 정하는 배율 (감사 314) ────────────────────────
      "지금 허락된 배율 상한": "Leverage cap allowed right now",
      "(사람이 정한 절대 천장은 3배입니다 — 그 안에서":
        "(the hard ceiling a person set is 3x — within it,",
      "이 트랙의 기록이": "this track's own record",
      "오늘의 상한을 정합니다.)": "sets today's cap.)",

      "아직 증명되지 않았으므로": "not yet proven, so it stays at",
      "입니다. 1배는 실패가 아니라 \"지금은 크게 걸 이유가 없다\"는 답입니다 — 증거 없이 키우면 그건 학습이 아니라 요행입니다.":
        ". 1x is not a failure; it is the answer \"there is no reason to bet big yet\" — raising it without evidence is luck, not learning.",

      // ── 주간 아카이브 ──────────────────────────────────────
      // 레버리지 관문이 내는 사유 — quant/live/leverage.py가 만든다.
      // 표본 부족 사유는 아래 rules가 잡고, 이쪽은 바뀌는 부분이 없어
      // 문장 그대로 적는다.
      "평균 수익률의 95% 하한이 0 이하 — 우연과 구별되지 않는다 — 1배로 둡니다":
        "the 95% lower bound on the mean return is at or below zero — indistinguishable from luck — held at 1x",

      "주(월요일 시작)": "Week (starting Monday)",
      "주말 자산": "Equity at week end",
      "매칭 입금": "Matching deposit",
      "직전 주가 없으면 원금": "with the principal used when there is no prior week",
      "매일 새벽 확정된 페이퍼 기록을": "An archive that groups the paper records settled each morning",
      "주 단위(월요일 시작)": "by week (starting Monday)",
      "로 묶은 아카이브입니다. 가상 자금 모의투자이며, 좋은 주가 있어도 미래 수익을 보장하지 않습니다.":
        ". It is a play-money simulation; a good week guarantees nothing about the future.",
      "통합 계좌 (100만 챌린지)": "Combined account (1M Won Challenge)",
      "주간 수익률": "Weekly return",
      "종목별 주간 수익률": "Weekly return by symbol",
      "주": "Week",
      "주간 수익률 = 그 주 마지막 확정 자산 ÷":
        "Weekly return = equity settled at the end of that week ÷",
      "그 주 시작 시점의 자산": "equity at the start of that week",
      "− 1. 시작 시점은 직전 주의 마지막 확정 자산이고,":
        "− 1. The starting point is the previous week's last settled equity,",
      "입니다 — 그러지 않으면 계좌를 연 첫 주의 첫날 손익이 통째로 빠집니다. 입금은 수익이 아니므로 그 주 유입액을 빼고 계산하며(입금이 있는 주는 금액을 함께 표기합니다), 이 숫자는 텔레그램 주간 리포트와":
        "— otherwise the first day's P&L in the opening week would drop out entirely. Deposits are not returns, so the week's inflow is subtracted (weeks with a deposit show the amount), and this number is produced by",
      "같은 코드": "the same code",
      "가 냅니다. 모든 원본 기록은": "as the Telegram weekly report. Every original record can be verified in the",
      "git 장부": "git ledger",
      "에서 검증할 수 있습니다.": ".",
      "에서만 읽습니다 — 원본을 직접 볼 수 있습니다. 빈칸이 보이면 \"그런 일이 없었다\"가 아니라 \"아직 기록이 없다\"입니다.":
        ", which the batch commits every round — you can read the source yourself. A blank does not mean \"it did not happen\"; it means \"there is no record yet\".",
    },

    /**
     * 숫자가 든 문장 — 꼬리말만 바꾼다. 숫자·통화·날짜는 장부의 값이라
     * 절대 건드리지 않는다.
     */
    rules: [
      // ⚠️ 순서가 중요하다 — 먼저 맞는 규칙이 이긴다. "12,345원 손해"를
      //    일반 규칙(^(.+) 손해$)이 먼저 잡으면 "원"이 그대로 남는다.
      ["^([−+]?[\\d,\\.]+)원 손해$", "KRW $1 loss"],
      ["^([−+]?[\\d,\\.]+)원 이익$", "KRW $1 profit"],
      ["^(\\d{4}-\\d{2}-\\d{2}) 주$", "Week of $1"],
      // ⚠️ **날짜를 사전 열쇠에 박지 않는다** (2026-08-26에 배운 것).
      //    아래 두 문장은 사전에 통째로 들어 있었고, 그 열쇠에 그날의
      //    장부 날짜(2026-08-24)가 박혀 있었다. 사전을 쓴 08-25 아침에는
      //    맞았지만, 그날 밤 배치가 08-25를 쓰는 순간 열쇠가 어긋나
      //    영어 화면에 한국어가 남았다 — 그리고 검사가 빨개졌다.
      //    **매일 밤 스스로 만료되는 사전**이었던 셈이다. 날짜처럼 매일
      //    바뀌는 자리는 사전이 아니라 여기(규칙)에서 붙잡는다.
      ["^마지막 갱신: (\\d{4}-\\d{2}-\\d{2})$", "Last updated: $1"],
      // 수정 공지의 날짜도 장부(amended.on)에서 온다 — 사전에 박으면
      // 공지가 갱신되는 날 영어가 사라진다. 화면이 괄호를 붙이는 쪽과
      // 안 붙이는 쪽 둘 다 있어 규칙도 둘이다(intraday·index).
      ["^수정 공지 \\((\\d{4}-\\d{2}-\\d{2})\\)$", "Amendment notice ($1)"],
      ["^📝 수정 공지 (\\d{4}-\\d{2}-\\d{2})$", "📝 Amendment notice $1"],
      ["^의 숫자입니다 — 그냥 보유도 살 때 한 번은 수수료를 냅니다\\((\\d{4}-\\d{2}-\\d{2}) 교정\\)\\. 본 계좌는 하루 한 번 새벽에 확정되므로 마지막 확정일\\((\\d{4}-\\d{2}-\\d{2})\\) 기준입니다\\. 실험 시작\\((\\d{4}-\\d{2}-\\d{2})\\) 이후의 변화율끼리 비교합니다 — 표본이 판정 기준\\(위\\)을 채우기 전의 우열은 운과 구별되지 않습니다\\.$",
       " figures — buy & hold also pays a fee once, at purchase (corrected $1). The main account settles once a day at dawn, so it is shown as of its last settlement ($2). The comparison is between rates of change since the experiment began ($3) — any lead before the sample meets the criteria above is indistinguishable from luck."],
      ["^(\\d{4}-\\d{2}-\\d{2}) — 규칙이 바뀌었습니다\\.$",
       "$1 — the rules changed."],
      ["^\\(한국 시간\\) · 실측 판단 간격 ([\\d,\\.]+)분$",
       "(KST) · observed gap between calls: $1 min"],
      ["^실시간 시세 일부를 받지 못해\\((.+)\\) 합계는 표시하지 않습니다 — 위 확정값을 보세요\\.$",
       "Live quotes were missing for some symbols ($1), so no total is shown — read the settled figures above."],
      ["^주기 사다리: (.+) \\(참고 진단 — 판정은 1시간 트랙만\\)$",
       "Interval ladder: $1 (diagnostic only — the verdict rests on the 1-hour track)"],
      ["^미국 정규장\\(뉴욕 09:30~16:00\\)에서만 판단·체결 — 장 밖 회차는 기록이 없습니다 · 판정일 (.+) \\(사전 등록\\) · 시작 (.+) \\(한국 시간\\)$",
       "Calls and fills only during US regular hours (New York 09:30-16:00) — no records outside them · verdict date $1 (pre-registered) · started $2 (KST)"],
      ["^회차 (\\d+)개 · 최저 (.+) · 최고 (.+) — 회차 간격은 균등하지 않을 수 있습니다\\(실측 간격 참고\\)$",
       "$1 rounds · low $2 · high $3 — the gaps between rounds may not be even (see the observed gap)"],
      ["^같은 신호·지정가 체결 복제 계좌 — 슬리피지를 아끼는 대신 미체결 위험을 집니다\\. 본 실험과의 자산 차이가 체결 방식의 효과입니다\\. \\(시작 (.+) · 그림자 누적 비용 (.+)\\)$",
       "A mirror account on the same signals using limit orders — it saves slippage but takes on the risk of not being filled. The equity gap against the main experiment is the effect of the execution style. (started $1 · shadow cumulative cost $2)"],
      ["^배율 상한을 사람이 정하지 않고 \\*\\*이 트랙의 기록이\\*\\* 정하게 했습니다\\. (.*)$",
       "The leverage cap is no longer set by a person — this track's own record sets it. Before it is proven the cap is 1x, and it drops straight back to 1x whenever the drawdown deepens."],
      ["^이고, 시드 ([\\d,]+)원 대비$", ", against a seed of KRW $1:"],
      ["^\\(원\\/달러 ([\\d,\\.]+)원 기준 · 읽기 편하라고 덧붙인 환산이며 이 계좌의 단위는 (\\w+)입니다\\. 시드와 지금 자산을$",
       "(at KRW $1 per USD · a reading aid only — this account is denominated in $2. The seed and today's equity are both converted at"],
      ["^로 바꿨으므로 퍼센트 수익률은 (\\w+) 기준과 같고,$",
       ", so the percent return is identical to the $1 figure, and"],
      ["^([\\d,\\.]+)배$", "$1x"],
      ["^표본 (\\d+)회차 < (\\d+) — 1배로 둡니다$",
       "sample of $1 rounds < $2 — held at 1x"],
      ["^한 줄 요약: 지금까지$", "In short, so far:"],
      ["^이고, 그중 수수료·미끄러짐으로$", ", of which fees and slippage took"],
      ["^을 냈습니다\\.$", "."],
      ["^(.+) 손해$", "$1 loss"],
      ["^(.+) 이익$", "$1 profit"],
      ["^(\\d[\\d,\\.]*)원$", "KRW $1"],
      ["^(\\d+)건 / (\\d+)회$", "$1 fills / $2 rounds"],
      ["^(\\d+)종목$", "$1 symbols"],
      ["^들고 있는 것 전부 합치면 지금$", "Everything it holds adds up right now to"],
      ["^입니다 \\((\\d+)종목 기준\\)\\. 이 값은$", "across $1 symbols. That figure is"],
      ["^아직 안 판$", "unrealized"],
      ["^평가 손익입니다 — 팔 때 비용이 한 번 더 듭니다\\.$",
       "— selling costs money once more."],
      ["^지금 자산의$", "It is deploying"],
      ["^\\((.+)\\)를 굴리고 있고, 나머지$", "of its equity ($1); the rest,"],
      ["^은 현금입니다\\.$", ", sits in cash."],
      ["^지금까지 (\\d+)건을 체결했고, 위 표는 그중 마지막 (\\d+)건입니다\\.$",
       "$1 fills so far; the table above shows the last $2."],
      ["^(.+)일 / (\\d+)일$", "$1 of $2 days"],
      ["^시드 (.+) · (.+) 기준$", "Seed $1 · as of $2"],
      ["^/ 유지선 (.+)$", "/ maintenance line $1"],
      ["^(\\d+)개 회차 · (.+)$", "$1 rounds · $2"],
      ["^(\\d+)개 회차$", "$1 rounds"],
      ["^시작 (.+) · 마지막 회차 (.+)$", "Started $1 · last round $2"],
      ["^\\(한국 시간\\) · 실측 판단 간격 (.+)$",
       "(KST) · observed gap between calls: $1"],
    ],
  };
})(window);
