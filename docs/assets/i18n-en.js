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
    partial: ["index.html", "paper.html"],

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
      "구글(A주)": "Google (Class A)",
      "구글(C주)": "Google (Class C)",
      // 2026-08-19 유니버스 확장(20 → 42종목)으로 들어온 자산군 코어.
      // ⚠️ "은"은 조사가 아니라 **종목 이름**이다(SLV) — 이 자리를 문장
      //    조각이 차지하고 있었다.
      "금": "Gold",
      "은": "Silver",
      "금 (한국 상장)": "Gold (Korea-listed)",
      "달러": "US dollar",
      "미국 장기국채": "US long-term Treasuries",
      "미국 중기국채": "US intermediate Treasuries",
      "미국 물가연동국채": "US inflation-linked Treasuries",
      "미국 우량 회사채": "US investment-grade corporate bonds",
      "미국 에너지주": "US energy stocks",
      "미국 전기·가스주": "US utilities",
      "미국 생활필수품주": "US consumer staples",
      "미국 부동산": "US real estate",
      "원자재 묶음": "Commodity basket",
      "일본 주식": "Japanese equities",
      "유럽 주식": "European equities",
      "신흥국 주식": "Emerging-market equities",
      "미국 나스닥100 (한국 상장)": "US Nasdaq 100 (Korea-listed)",
      "한국 국고채 10년": "Korea 10-year government bonds",
      "한국 종합채권": "Korea aggregate bonds",
      "한국 화장품주": "Korean cosmetics stocks",

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
      "수수료 빼기 전": "Before fees",
      "수수료와 자금조달을 내기 전 자산 기준입니다. 전략 자체가 얼마나 벌었는지를 보여줍니다.":
        "Equity before fees and funding. Shows what the strategy itself earned.",
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
      // ⚠️ 짝의 **양쪽을 다 적는다.** 사전을 쓸 때 계좌가 롱이라 이 줄만
      //    넣었고, 계좌가 숏으로 돌아선 순간 영어 화면에 한국어가 남았다
      //    (2026-08-26 CI). 화면에 지금 안 보이는 쪽도 언젠가 보인다.
      "숏(내림에 걺)": "Short (betting on a fall)",
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
      "실측 최악 아직 모름(기록이 모자람)":
        "worst observed gap not yet known (too few records)",
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

      // ══ 첫 화면 (index) — 2026-08-25 2단계 ═══════════════════
      "통합 계좌": "Combined account",
      "장단기 금리차": "Yield curve spread",
      "하이일드 스프레드": "High-yield spread",
      "달러인덱스": "Dollar index",
      "한눈에": "At a glance",
      "가상 자금 · 실제 돈이 아닙니다": "Play money · not real money",
      "넣은 돈 (원금)": "Money put in (principal)",
      "(일봉 기준)": "(daily bars)",
      "이익": "Profit",
      "손해": "Loss",
      "기준일": "As of",
      "— 매일 새벽 한 번 확정합니다(실시간이 아닙니다). 다음 확정 전이라 날짜가 하루 전인 것이":
        "— settled once each morning, not live. Before the next settlement the date being a day old is",
      "정상": "normal",
      "지만, 서로 비슷하게 움직이는 만큼을 걷어내면":
        ", but once the part that moves together is stripped out, that is worth",
      "의 정보입니다(평균 동조 7%). 이 숫자를 키우려고 금·채권·원자재처럼":
        "of independent information (average co-movement 7%). To raise that number we add things that",
      "다르게 움직이는 자산": "move differently — gold, bonds, commodities",
      "을 넣습니다.": ".",
      "· 현금": "· cash",
      "코인": "Crypto",
      "한국주식": "Korean stocks",
      "미국주식": "US stocks",
      "(신호 관망 중 — 안 하는 게 아닙니다)":
        "(standing aside on the signal — not the same as doing nothing)",
      "📊 같은 기간": "📊 Over the same period",
      "그냥 전 종목을 사서 들고만 있었다면":
        "buying every symbol on day one and just holding would be",
      "양쪽 다": "Both figures are",
      "의 숫자입니다 — 그냥 보유도 살 때 한 번은 수수료를 냅니다(2026-08-19 교정). 지금 증명하려는 것은":
        " — buy & hold also pays a fee once, at purchase (corrected 2026-08-19). What is being proven right now is",
      "1억이 아니라 \"그냥 보유보다 낫다\"":
        "not 100 million won, but \"better than just holding\"",
      "하나입니다.": " — that one thing.",
      "안전장치를 다 풀면?": "What if every safeguard were removed?",
      "가상 실험 · 위험 비교용": "Simulated · for risk comparison",
      "· 최대낙폭": "· max drawdown",
      "본 계좌와 같은 신호를 받되 안전장치(변동성 타깃·킬스위치·검증 게이트·켈리 상한)를 전부 뗀 가상 계좌입니다(무레버리지만 유지). 이 계좌가 앞서는 구간은 실력이 아니라 위험을 더 진 대가일 수 있습니다 — 반드시 최대낙폭과 함께 읽으세요. 종가 평가·수수료만 차감이라 본 계좌와 절대 비교는 안 되고, 제약의 효과를 보는 용도입니다.":
        "A simulated account taking the same signals as the main account with every safeguard removed — volatility target, kill switch, validation gate, Kelly cap (it stays unleveraged). Where this account leads, that may not be skill but the price of carrying more risk — always read it next to the max drawdown. It marks to the close and deducts fees only, so it cannot be compared to the main account in absolute terms; it exists to show what the constraints cost.",
      "● 매일 새벽 자동 운용 · 기록 전체 공개":
        "● Runs automatically every morning · the whole record is public",
      "으로 굴리는 자동매매,": "traded automatically, and",
      "매일 그대로 공개": "published every day exactly as it happened",
      "됩니다.": ".",
      "2026-08-13 원화 계좌로 재개설(이전 기록은 그대로 공개)":
        "Reopened as a won-denominated account on 2026-08-13 (earlier records stay public)",
      "백테스트부터 과최적화 검증(워크포워드·PBO·CPCV), 페이퍼 트레이딩까지 한 프로그램에. 설치 없이 더블클릭하면 5분 안에 첫 백테스트가 돌아갑니다.":
        "Backtesting, overfitting checks (walk-forward, PBO, CPCV) and paper trading in one program. No installer — double-click and your first backtest runs within five minutes.",
      "여기 보이는 기록은 우리가 실제로 돌리는 계좌":
        "The record shown here is the account we actually run",
      "이고, 틀린 날도 지우지 않습니다.":
        ", and the days it was wrong are not deleted.",
      "Linux 다운로드": "Download for Linux",
      "zip — 압축 해제 후 실행": "zip — unzip and run",
      "무설치 · 무료 · 회원가입 없음 · 서명되지 않은 개인 빌드라 \"알 수 없는 개발자\" 경고가 뜰 수 있습니다 ·":
        "No installer · free · no sign-up · an unsigned personal build, so your OS may warn about an \"unidentified developer\" ·",
      "수익을 보장하지 않습니다 — 백테스트·페이퍼 검증 후 사용하세요.":
        "No return is guaranteed — verify with backtests and paper trading before use.",
      "100만 챌린지 · 통합 실기록":
        "1M Won Challenge · the full combined record",
      "판정 시계": "Verdict clock",
      "검증한 도전자": "Challengers tested",
      "전략 vs 첫날 균등 매수 후 보유 · 매일 새벽 확정":
        "Strategy vs buying every symbol equally on day one and holding · settled each morning",
      "챔피언 교체": "Champion swap",
      "선이": "A",
      "끊긴 구간": "break in the line",
      "은 기록이 없는 날입니다 — 이어 그리면 그날도 그렇게 움직인 것처럼 보이므로 잇지 않습니다.":
        "is a day with no record — joining it up would make that day look as if it had moved, so we leave the gap.",
      "🕰 이 성적, 언제부터 공식인가":
        "🕰 When does this result become official?",
      "지금 구조로 90일을 채워야 \"우연이 아니다\"라고 말할 수 있어서, 그때까지는 모든 수익률을":
        "Only after 90 days on the current structure can we say \"this is not chance\", so until then every return is read as",
      "중간 기록": "an interim record",
      "으로만 읽습니다.": " and nothing more.",
      "현재 구조": "Current structure",
      "관찰": "observed",
      "/ 판정 기준 90일 (2026-08-13~). 구조가 바뀌면 통계의 시계도 0일부터 다시 셉니다.":
        "/ 90 days required (from 2026-08-13). If the structure changes, the statistical clock restarts from day zero.",
      "사이징·체결 구조": "how positions are sized and executed",
      "가 바뀌어도 리셋합니다: 노출이 다른 두 구간의 수익률은 같은 통계가 아니기 때문입니다.":
        "changing also resets it: returns from two stretches with different exposure are not the same statistic.",
      "지금 모델이": "What the model is",
      "실제로 보고 있는": "actually looking at",
      "참고 지표": "reference indicators",
      "— 2026-08-18부터 이 구성이 유지되고 있습니다. 외부 자료가 끊기거나 되살아나":
        "— this configuration has held since 2026-08-18. If an outside feed dies or comes back and",
      "보는 것이 달라지면": "what it sees changes",
      "(3일 연속) 그날부터 시계를 다시 셉니다. \"무엇을 본다\"고 적어 둔 이름표만 믿으면, 자료가 끊긴 구간과 살아 있던 구간이 한 통계로 섞입니다.":
        "for three days running, the clock restarts from that day. Trusting only the label that says \"it looks at X\" would blend the stretches where the data was dead into the same statistic as the stretches where it was alive.",
      "🎯 리스크 설정": "🎯 Risk settings",
      "목표 변동성": "Target volatility",
      "회전율(자산 대비 매매금액) 최근 9일 평균":
        "Turnover (traded value against equity), 9-day average",
      "회전율(자산 대비 매매금액) 최근 8일 평균":
        "Turnover (traded value against equity), 8-day average",
      "→ 연 비용 약": "→ roughly this much cost per year",
      "vs 기대수익 12% ⚠️ 비용이 수익을 먹는 구간":
        "vs an expected 12% return ⚠️ costs are eating the return here",

      // ── 잔고 · 거래내역 (첫 화면) ───────────────────────────
      "잔고": "Holdings",
      "전부 원화 환산": "all converted to won",
      "보유수량": "Qty held",
      "→ 현재가": "→ last price",
      "매입금액": "Cost basis",
      "→ 평가금액": "→ market value",
      "평가손익": "Unrealized P&L",
      "계좌 비중": "Share of account",
      "실제 보유": "Actually held",
      "현금": "Cash",
      "아직 어느 종목에도 들어가지 않은 돈":
        "money not yet put into any symbol",
      "합계": "Total",
      "이 표의 손익": "The P&L in this table,",
      ", 기준은": " is measured",
      ", 이쪽 기준은": " is measured",
      "매입금액 대비": "against cost basis",
      "입니다. 맨 위": ". The one at the top,",
      "은 이미 낸 매매 수수료로, 계좌에서 빠져나가 어느 칸에도 남아 있지 않습니다.":
        " is the trading fees already paid — it left the account and sits in no column.",
      "거래내역": "Trade history",
      "날짜": "Date",
      "구분": "Type",
      "체결가": "Fill price",
      "체결 방식": "Fill type",
      "시가": "Open",
      "즉시": "Immediate",
      "주문 실패": "Order failed",
      "현금 부족 — 미체결": "not enough cash — unfilled",
      "이 기록을 만든 프로그램을 직접 돌려볼 수 있습니다 —":
        "You can run the program that produced this record yourself —",
      "백테스트·검증·모의투자 전용": "backtesting, validation and paper trading only",
      "(실거래 기능 없음).": "(no live-trading function).",
      "간단히 보기 ▴": "Show less ▴",
      "자세히 보기 ▾": "Show more ▾",
      "종목별 현황 · 판정 시계 · 리스크 설정 · 체결 검증 · 오답 노트 · 탈락자 · 프로그램 소개":
        "Per-symbol status · verdict clock · risk settings · fill verification · error log · dropped candidates · about the program",
      "종목별 현황": "Status by symbol",
      "현지 통화": "Local currency",
      "일간": "Daily",
      "누적": "Cumulative",
      "종목계좌 비중": "Share of symbol account",
      "현재 보유": "Currently held",
      "통합 보유": "Combined holding",
      "평가금액 · 오늘 목표": "Market value · today's target",
      "적중률": "Hit rate",
      "과거 400봉 · 실전": "past 400 bars · live",
      "새벽 판단": "Morning call",
      "⚠ 소수 주": "⚠ fractional share",
      "실전 —": "live —",

      // ── 실시간 vs 확정 · 체결 가정 검증 ─────────────────────
      "이 표의 숫자는": "The numbers in this table are what",
      "매일 새벽 배치가 하루 한 번 확정": "the morning batch settles once a day",
      "한 값입니다 — 실시간이 아닙니다. 살아 있는 시세는":
        " — they are not live. Live quotes appear in",
      "맨 위 시세띠": "the ticker strip at the top",
      "와 잔고 표의 \'지금\' 줄에 나오며(코인은 거래소 스트림으로 체결 즉시, 주식은 장중 15초 간격),":
        "and in the \"now\" row of the holdings table (crypto streams from the exchange on each fill, stocks every 15 seconds during the session), and they",
      "판단·체결·평가에는 쓰지 않습니다":
        "are never used for calls, fills or valuation",
      "🧾 거래 비용, 가정이 실제와 맞나":
        "🧾 Trading costs — does the assumption match reality?",
      "체결 가정 검증": "Fill-assumption check",
      "백테스트가 가정한 수수료·미끄러짐(주문 순간 가격이 살짝 불리해지는 것)이 실제 체결과 얼마나 다른지 매일 잽니다 — 가정이 후하면 성적이 부풀려 보이기 때문입니다.":
        "Every day we measure how far the fees and slippage assumed in the backtest (the price moving slightly against you at the moment of the order) differ from the real fills — because a generous assumption makes the record look better than it is.",
      "시장": "Market",
      "실측 불리": "Measured adverse move",
      "가정": "Assumed",
      "판정": "Verdict",
      "가정 안": "within assumption",
      "🧨 위기 재생·스트레스": "🧨 Crisis replay and stress test",
      "시뮬레이션": "Simulation",
      "지난 위기 재생": "Replaying past crises",
      "브레이크 없음": "No brakes",
      "브레이크 적용": "With brakes",
      "최대낙폭": "Max drawdown",
      "연 변동성": "Annualised volatility",
      "(목표 12.0%)": "(target 12.0%)",
      "최악 20일": "Worst 20 days",
      "내일 아침 스트레스": "Stress test for tomorrow morning",
      "시나리오": "Scenario",
      "계좌 손실": "Account loss",
      "브레이크 반응": "Brake response",
      "하룻밤 갭 -10% (전 종목 동반 하락, 상관 1)":
        "Overnight gap -10% (everything falls together, correlation 1)",
      "하룻밤 갭 -20% (2020-03 규모)":
        "Overnight gap -20% (the scale of March 2020)",
      "하룻밤 갭 -30% (역대급 단일일)":
        "Overnight gap -30% (a record single day)",
      "닷새 연속 -8% (2022 루나·FTX형 연쇄 붕괴)":
        "-8% five days running (a 2022 Luna/FTX-style cascade)",
      "20일 연속 -2% (완만한 침식형 약세)":
        "-2% for twenty days running (a slow grinding decline)",
      "원/달러 +15% — 외화 자산(100%)만 영향":
        "USD/KRW +15% — affects only the foreign-currency assets (100%)",
      "원/달러 -15% — 외화 자산(100%)만 영향":
        "USD/KRW -15% — affects only the foreign-currency assets (100%)",
      "시세가 5일 멈춘 사이 시장 -20% — 장부는 그동안 낙폭 0을 보고한다":
        "The market falls 20% while quotes are frozen for five days — the ledger reports zero drawdown the whole time",
      "⚠️ 못 봄 — 멈춘 시세 감시가 방어선":
        "⚠️ Blind — the stale-quote watchdog is the only defence",
      "정상 유지": "holds normally",
      "🟡 노출 절반": "🟡 exposure halved",
      "여기 숫자는 전부": "Every number here is",
      "입니다(실측 장부와 다른 파일에 삽니다). 거래 비용·슬리피지 미반영 — 낙폭·변동성 측정 목적. 수익 배수를 성과로 읽지 말 것 · 지금 살아 있는 종목만 포함(생존 편향) — 낙폭이 실제보다 얕게 나올 수 있음 · 전략 신호 없는 균등 바스켓 — 위험 층의 검증이지 수익 엔진의 검증이 아님 · 수익률은 각 종목의 현지 통화 기준 — 환율 변동의 위험이 빠져 있음":
        " (it lives in a different file from the measured ledger). Trading costs and slippage are not included — the purpose is to measure drawdown and volatility. Do not read the return multiple as performance · only symbols still alive today are included (survivorship bias), so the drawdown may come out shallower than it really was · it is an equal-weight basket with no strategy signal — this validates the risk layer, not the return engine · returns are in each symbol's local currency, so exchange-rate risk is absent",
      "오답 노트": "Error log",
      "상시 공개": "always public",
      "자산": "Equity",
      "사후에 지우거나 꾸밀 수 없는 구조(git 장부)입니다.":
        "By construction it cannot be deleted or dressed up afterwards (a git ledger).",
      "스스로 고친 기록": "A record of fixing itself",
      "자동 발행": "published automatically",
      "이 시스템은 매일 자신의 결함을 찾아 고칩니다. 아래는 그 기록이며,":
        "This system looks for its own defects every day and fixes them. Below is that record —",
      "사람이 따로 적는 일지가 아니라": "not a diary someone writes by hand, but",
      "개선이 저장소에 합쳐지는 순간 자동으로 남는 이력입니다. 성적이 나쁜 날의 수정도 그대로 실립니다. 아래 항목은 저장소의 커밋 제목을 그대로 옮긴 것입니다.":
        "a history left automatically the moment a fix is merged into the repository. Fixes made on bad days are published just the same. The entries below quote the repository's commit titles verbatim, so they stay in Korean.",

      // ── 나머지 첫 화면 문구 ─────────────────────────────────
      "보유 없음": "not held",
      "탈락자 아카이브": "Archive of rejected challengers",
      "다중검정 정직성": "multiple-testing honesty",
      "시도가 쌓일수록 승격 문턱이 자동으로 올라갑니다(다중검정 보정) — 탈락시킨 수를 공개하는 것이 \"운 좋은 승자\"가 아니라는 증거입니다.":
        "The bar for promotion rises automatically as attempts accumulate (a multiple-testing correction) — publishing how many were rejected is the evidence that a winner is not merely lucky.",
      "후원 랭킹": "Supporter ranking",
      "매칭 입금 — 챌린지 계좌 원금과 회계 분리":
        "Matching deposits — accounted separately from the challenge account's principal",
      "거래소 가입으로 챌린지 응원하기":
        "Support the challenge by signing up at an exchange",
      "투명 고지": "Disclosure",
      ": 아래 링크로 가입하시면 운영자가 거래소로부터 수수료 일부를":
        ": if you sign up through the link below, the operator receives part of the trading fee from the exchange as a",
      "리베이트": "rebate",
      "로 받습니다(가입자 추가 부담 없음). 특정 거래소를 추천·보증하지 않으며, 투자 판단과 책임은 본인에게 있습니다.":
        "(at no extra cost to you). No exchange is recommended or endorsed, and investment decisions and their consequences are yours.",
      "지금 받아서 5분 안에 첫 백테스트":
        "Download now and run your first backtest within five minutes",
      "받은 프로그램은 백테스트·검증·모의투자·조회 전용입니다. 실거래 기능은 배포판에 넣지 않았습니다 — 구매자 손에서 실계좌가 도는 일을 기술적으로 막아뒀습니다.":
        "The program you download does backtesting, validation, paper trading and lookups only. Live trading is not in the distributed build — running a real account from a buyer's hands is blocked technically.",
      "다른 OS / 이전 버전": "Other operating systems / earlier versions",
      "⚠️ 이 사이트의 모든 기록은": "⚠️ Every record on this site is",
      "페이퍼(모의) 운용": "paper trading",
      "입니다 — 실제 돈이 오가지 않으며, 좋은 결과도 미래 수익을 보장하지 않습니다. 투자 판단과 책임은 본인에게 있습니다. 기록 원본은 저장소":
        " — no real money changes hands, and a good result guarantees nothing about the future. Investment decisions and their consequences are yours. The original records sit in the repository's",
      "폴더에 그대로 있습니다 —": "folder exactly as written —",
      "조작이 불가능한 이유 →": "why they cannot be tampered with →",
      "🕰 언제부터 공식 성적인가": "🕰 When does the record become official?",
      "(판정 시계)": "(verdict clock)",
      "구조": "Structure",
      "/ 90일": "/ 90 days",
      "엣지 판정은 시계가 다 돌기 전엔 하지 않습니다.":
        "No edge verdict is made before the clock runs out.",
      "💰 돈이 지금 어디 있나": "💰 Where the money is right now",
      "🚩 지금 켜진 경고": "🚩 Warnings currently lit",
      "리스크 잠금": "Risk locked",
      "데이터 품질": "Data quality",
      "운용 종목": "Symbols in play",
      "🏆 최근 챔피언 교체": "🏆 Recent champion swaps",
      "전일 확정 · 현지통화": "settled yesterday · local currency",
      "이 계좌는 하루 단위(일봉)로 판단합니다. 오늘 봉은 하루가 끝나야 닫히므로, 새벽 배치가 확정하는 것은 전날까지의 값입니다. 코인 단타는 1시간봉을 15분마다 보므로 하루 종일 움직입니다 — 둘 다 정상이고 판단 주기가 다를 뿐입니다.":
        "This account decides once a day, on daily bars. Today's bar only closes when the day ends, so what the morning batch settles is the value through yesterday. The crypto intraday track looks at hourly bars every 15 minutes, so it moves all day — both are normal; they simply decide on different cycles.",
      "위: 산 가격의 평균(수수료 반영) · 아래: 장부가 마지막으로 확인한 가격 — 실시간이 아닙니다":
        "Top: average purchase price (fees included) · bottom: the last price the ledger confirmed — not live",
      "위: 그 종목에 넣은 돈 · 아래: 지금 값":
        "Top: money put into that symbol · bottom: what it is worth now",
      "위: 넣은 돈 대비 얼마가 늘거나 줄었나 · 아래: 그것을 비율로":
        "Top: how much it has gained or lost against the money put in · bottom: the same as a percentage",
      "누르면 차트와 장부를 함께 봅니다":
        "Click to see the chart and the ledger side by side",
      "실제로 체결된 가격": "The price actually filled",
      "판 시점에 확정된 손익입니다 — 평균 매입가와 비교하고, 그 거래의 수수료·세금·미끄러짐까지 뺀 값입니다. 매수에는 없습니다(아직 확정된 것이 없으므로).":
        "P&L locked in at the sale — measured against average cost and net of that trade's fees, taxes and slippage. Buys have none (nothing is locked in yet).",
      "시가=결정 다음 세션 시가에 체결 · 즉시=코인 24시간 시장":
        "Open = filled at the next session's open after the decision · Immediate = the 24-hour crypto market",
      "주문은 냈지만 체결되지 않았습니다 — 누르면 차트와 장부를 함께 봅니다":
        "An order was placed but never filled — click to see the chart and the ledger",
      "그 종목이 거래되는 통화 그대로입니다 — 미국주식은 달러, 코인은 USDT, 한국주식은 원. 위 잔고 표(원화 환산)와 단위가 다릅니다.":
        "In the currency that symbol trades in — dollars for US stocks, USDT for crypto, won for Korean stocks. That is a different unit from the holdings table above, which is converted to won.",
      "그 종목만 굴리는 독립 계좌가 지금 들고 있는 비중입니다. 주식은 다음 세션 시가에 체결되므로, 오늘 내린 결정이 다르면 \'→ N% 예정\'으로 함께 표시합니다.":
        "The weight held right now by the standalone account that trades only that symbol. Stocks fill at the next session's open, so when today's decision differs it is shown alongside as \"→ N% planned\".",
      "통합 계좌(100만 챌린지 본체)가 이 종목에 실제로 넣어 둔 돈입니다 — 원화 환산 평가금액. 아래 줄은 그 금액이 계좌에서 차지하는 노출(배분 슬라이스·변동성 타깃·킬스위치 반영)과 보유 수량입니다. 안 들고 있으면 \'—\'입니다.":
        "The money the combined account (the 1M Won Challenge itself) actually has in this symbol — market value converted to won. The line below is the exposure that amount takes up in the account (after the allocation slice, volatility target and kill switch) and the quantity held. A dash means it is not held.",
      "채점 가능한 봉이 없습니다": "There are no bars that can be scored",
      "소수점 매매가 없는 시장인데 소수 주를 들고 있습니다 — 실계좌에서는 이대로 재현할 수 없습니다":
        "A fractional share is held in a market that does not trade fractions — a real account could not reproduce this exactly",
      "그 종목만 굴리는 참고 계좌가 **지금 들고 있는** 비중 — 통합 계좌 보유량이 아닙니다":
        "The weight held right now by the reference account that trades only that symbol — not the combined account's holding",
      "닫기": "Close",
      "· 감사 320 — 사이트를 영어로도 읽는다 (KO/EN 토글, 1단계) (#280)":
        "· Audit 320 — the site reads in English too (KO/EN toggle, phase 1) (#280)",

      "─ 계좌 자산 · ┄ 원금 · ⋯ 첫날 전 종목 균등 매수 후 그대로 보유했다면 ·":
        "─ account equity · ┄ principal · ⋯ buying every symbol equally on day one and holding ·",
      "마지막 리셋 2026-08-13 — 계좌 통화를 원화로 통일(감사 212) — 그전에는 해외 종목 가격을 환산하지 않아 한 계좌에 원화(한국주식)와 달러(미국주식·코인)가 섞여 있었다. 자산 합계가 진짜 원화가 아니었고 환위험이 통째로 빠져 있었다. 이제 체결·평가를 원/달러로 환산해, 환율 변동이 매일의 재평가로 자산에 반영된다. 신호는 현지 통화 그대로라 전략 동작은 그대로. 옛 계좌는 소급 환산이 불가능해(현금까지 단위가 섞였다) 그대로 보관하고 원화 계좌를 새로 열었다. 직전 구조(sz2): 포트폴리오 변동성 타깃 + 회전율 통제 + 안전장치 복구. 피처뿐 아니라":
        "Last reset 2026-08-13 — the account was unified on the won (audit 212). Before that, overseas prices were never converted, so one account mixed won (Korean stocks) with dollars (US stocks and crypto). The equity total was not really a won figure and exchange-rate risk was missing entirely. Fills and valuation are now converted at the USD/KRW rate, so currency moves flow into equity through the daily revaluation. Signals still use local currency, so strategy behaviour is unchanged. The old account could not be converted retroactively (even the cash was mixed), so it is kept as it is and a new won account was opened. Previous structure (sz2): portfolio volatility target + turnover control + safeguards restored. It is not only features —",

      "라 값이 다릅니다 — 차이": ", so the two differ — the gap,",
      "\'시가\'는 다음 장 개장가, \'즉시\'는 24시간 코인 시장입니다. 🚨 1건은 그날 계좌 자산보다 큰 금액이 적혀 있어 \'확인 필요\'로 두었습니다 — 통화 환산이 빠졌을 때 생기는 모양입니다. 기록은 지우지 않았고, 경위는 기록 검증 페이지에 있습니다. ⚠ \'주문 실패\' 1건은 주문은 냈지만 한 주도 체결되지 않은 것입니다 — 그래서 잔고에도 없습니다. 장부에 남은 그날의 기록은 지우지 않고 그대로 두고, 무엇이 사실이었는지만 여기서 밝힙니다.":
        "\"Open\" means the next session's opening price; \"Immediate\" means the 24-hour crypto market. 🚨 One entry records an amount larger than the account's equity that day, so it is marked \"needs checking\" — that is the shape a missing currency conversion leaves. The record was not deleted; the account of what happened is on the Verify the Record page. ⚠ One \"order failed\" entry means an order was placed but not a single share filled — which is why it does not appear in the holdings either. The day's record stays in the ledger untouched; all we do here is say what was actually true.",

      "\'5분마다\'는 예약일 뿐이며 실제 간격은 실측(observed_gap_minutes)이 말합니다 — 공용 러너는 예약을 크게 밀 수 있습니다":
        "\"every 5 minutes\" is only the schedule; the real gap is what we measure (observed_gap_minutes) — shared runners can push a schedule far back",

      // ══ 머신러닝 성적표 (ml.html) ═══════════════════════════
      "머신러닝 성적표": "Machine-learning report card",
      "시뮬레이션 · 좋은 숫자만 고르지 않습니다":
        "Simulation · we do not cherry-pick the good numbers",
      "이 시스템의 판단 대부분은": "Most of this system's calls come from a",
      "머신러닝 모델": "machine-learning model",
      "이 냅니다. 이 페이지는 그 모델이": ". This page shows, as it is,",
      "어떻게 판단하는지": "how that model decides",
      "지금까지 얼마나 맞혔는지": "and how often it has been right so far",
      "를 그대로 보여 줍니다. 성적이 나쁜 구간도 지우지 않습니다 — 지우는 순간 이 기록은 아무 의미가 없어집니다.":
        ". Bad stretches are not deleted — the moment they are, this record means nothing.",
      "지금 한 줄로 말하면": "In one line, right now",
      "실전 적중률이": "the live hit rate is",
      "우연과 구별되지 않습니다": "indistinguishable from chance",
      "— 아직 잘한다는 증거도, 못한다는 증거도 없습니다.":
        "— there is as yet no evidence that it is good, and none that it is bad.",
      "실전 적중률": "Live hit rate",
      "연습(인샘플) 적중률": "Practice (in-sample) hit rate",
      "확신할수록 덜 맞히고 있습니다.":
        "The more confident it is, the less often it is right.",
      "적중률은": "A hit rate says",
      "방향을 맞혔나": "was the direction right",
      "이지": ", not",
      "돈을 벌었나": "did it make money",
      "가 아닙니다 — 작게 여러 번 맞고 크게 한 번 틀리면 적중률은 높고 잔고는 줄어듭니다.":
        ". Being right small many times and wrong big once leaves a high hit rate and a smaller balance.",
      "어떻게 판단하나": "How it decides",
      "사람이 규칙을 정하지 않습니다": "no person writes the rules",
      "가격에서 재료를 만든다": "It builds inputs out of price",
      "최근 며칠 오르내린 폭, 거래량의 변화, 변동성 같은 것들을 숫자로 뽑습니다. 뉴스나 소문은 쓰지 않습니다 — 숫자로 셀 수 없는 것은 나중에 검증할 수도 없기 때문입니다.":
        "How much it rose and fell over recent days, how volume changed, how volatile it has been — all pulled out as numbers. News and rumour are not used: what cannot be counted cannot be verified later either.",
      "과거로 시험을 본다": "It sits an exam on the past",
      "\"이런 재료였던 날, 다음 날 올랐나 내렸나\"를 과거 데이터로 반복해서 맞혀 봅니다. ⚠️ 이때":
        "\"On days that looked like this, did the next day rise or fall?\" — asked over and over against past data. ⚠️ While doing so,",
      "미래를 절대 보여 주지 않습니다.": "it is never shown the future.",
      "2026년 3월 판단을 만들 때는 3월까지의 데이터만 씁니다. 이 규칙이 깨지면 성적표가 통째로 거짓말이 됩니다.":
        "A call for March 2026 uses data only through March. If that rule breaks, the whole report card is a lie.",
      "오늘의 확률을 말한다": "It states today's probability",
      "모델이 내놓는 것은 \"산다/안 산다\"가 아니라":
        "What the model produces is not \"buy / don't buy\" but a number like",
      "\"오를 확률 62%\"": "\"62% chance of a rise\"",
      "같은 숫자입니다. 확신이 없으면 없다고 말할 수 있어야 하기 때문입니다.":
        ". It has to be able to say when it is not confident.",
      "확률을 금액으로 바꾼다": "It turns the probability into an amount",
      "확률이 높을수록 크게 삽니다. 문턱(보통 55%) 아래면 아예 사지 않습니다. 그래서":
        "The higher the probability, the larger the purchase. Below the threshold (usually 55%) it does not buy at all. That is why",
      "확률이 맞는지가 적중률보다 중요합니다":
        "whether the probability is honest matters more than the hit rate",
      "— 크게 거는 날일수록 더 자주 틀린다면 잔고는 줄어듭니다.":
        "— if the days it bets big are the days it is more often wrong, the balance shrinks.",
      "안전장치가 마지막에 깎는다": "Safeguards trim it at the end",
      "과최적화 검증에서 의심스러운 종목은 비중을 절반으로 줄이거나 아예 관망합니다. 실적 발표 임박, 급락 중일 때도 줄입니다. 아래 \'안전장치가 붙잡은 것\'에 지금 상태가 나옵니다.":
        "Symbols that look suspect in the overfitting checks get their weight halved or stand aside entirely. It also trims near an earnings release and during a sharp fall. The current state is under \"What the safeguards caught\" below.",
      "매일 다시 배운다": "It relearns every day",
      "새 하루가 지나면 그 하루를 포함해 다시 학습합니다. 오래된 시장 국면은 버립니다. 도전자 전략이 챔피언을 이기면 자리를 바꿉니다.":
        "When a day ends it retrains including that day, and discards old market regimes. If a challenger strategy beats the champion, they swap places.",
      "지금 무엇이 굴리고 있나": "What is running right now",
      "굴리는 종목": "Symbols in play",
      "규칙이 판단 (": "Rule-based call (",
      "머신러닝이 판단": "decided by machine learning",
      "규칙이 판단 (ma_cross)": "decided by a rule (ma_cross)",
      "도전자가 챔피언을 이긴 횟수": "Times a challenger beat the champion",
      "도전자가 거의 못 이긴다는 것은": "Challengers almost never winning can be read as",
      "안정": "stability",
      "으로도,": ", or as",
      "정체": "stagnation",
      "로도 읽힙니다. 숫자만 적고 해석은 열어 둡니다. 머신러닝이 아닌 종목이 있다는 것은, 그 종목에서는":
        ". We record the number and leave the reading open. Where a symbol is not run by machine learning, it means that there",
      "단순한 규칙이 머신러닝을 이겼다": "a simple rule beat the model",
      "는 뜻입니다.": ".",
      "얼마나 맞혔나": "How often it was right",
      "실전과 연습을 나눠서 셉니다": "counted separately for live and practice",
      "불러오는 중…": "Loading…",
      "확률이 맞는가": "Is the probability honest?",
      "이 표가 이 페이지에서 가장 중요합니다":
        "this is the most important table on the page",
      "모델이": "Days the model called",
      "\"오를 확률 70%\"": "\"70% chance of a rise\"",
      "라고 말한 날들을 모아, 실제로 몇 %나 올랐는지 센 표입니다. 두 숫자가 가까울수록 모델이 자기 확신을 정직하게 말하고 있다는 뜻입니다.":
        "are gathered here, and counted for how many actually rose. The closer the two numbers, the more honestly the model is stating its own confidence.",
      "모델이 말한 확률": "Probability the model stated",
      "표본": "Sample",
      "모델이 말한 평균": "Model's average",
      "실제로 오른 비율": "Share that actually rose",
      "차이": "Gap",
      "표본부족": "sample too small",
      "확정": "confirmed",
      "모은 (예측, 결과) 짝": "(prediction, outcome) pairs collected",
      "건 · 예측확률과 실제결과의 상관계수":
        "· correlation between predicted probability and actual outcome",
      "(0에 가까우면 예측과 결과가 서로 무관하다는 뜻, 음수면 거꾸로 간다는 뜻입니다.)":
        "(near zero means prediction and outcome are unrelated; negative means they run the wrong way.)",
      "\'확정\'은 그 확률대의 어긋남이": "\"Confirmed\" means the mismatch in that probability band has",
      "통계로 굳어졌다": "hardened statistically",
      "는 뜻입니다(\'표본부족\'은 아직 판단을 유보한다는 뜻이지 괜찮다는 뜻이 아닙니다).":
        " (\"sample too small\" means judgement is withheld, not that it is fine).",
      "학습 때와 지금이 얼마나 다른가": "How different today is from training time",
      "드리프트": "drift",
      "모델은": "The model learned on",
      "과거 시장": "a past market",
      "에서 배웠습니다. 지금 시장이 그때와 많이 다르면, 모델은":
        ". If today's market differs a lot from that one, the model is deciding in a situation it has",
      "본 적 없는 상황": "never seen",
      "에서 판단하고 있는 것입니다. 틀렸다는 증거는 아니지만 맞을 이유도 그만큼 약해집니다.":
        ". That is not evidence it is wrong, but the reason to expect it to be right is weaker.",
      "주의 (표본 잡음 범위)": "caution (within sampling noise)",
      "심한 드리프트": "severe drift",

      "기준선을 넘은 종목": "Symbols past the line",
      "안전장치가 붙잡은 것": "What the safeguards caught",
      "경보가 아니라 실제로 손을 묶습니다":
        "not a warning — it actually ties the hands",
      "오늘 관망 (비중 0)": "standing aside today (weight 0)",
      "비중 절반으로": "weight halved",
      "깎이지 않음": "not trimmed",
      "⚠️ 지금": "⚠️ Right now",
      "모든 종목이 붙잡혀 있습니다.": "every symbol is being held back.",
      "시스템이 스스로 \"이 모델들을 지금 그대로 믿기 어렵다\"고 판단한 상태입니다. 이건 고장이 아니라 안전장치가 설계대로 작동하는 모습입니다 — 다만 그만큼 지금 굴리는 금액이 작다는 뜻이기도 합니다.":
        "The system has decided for itself that \"these models are hard to trust as they stand\". That is not a fault; it is the safeguards working as designed — though it also means the amount being put to work right now is small.",
      "비중 배수": "Weight multiplier",
      "이유": "Reason",
      "과최적화란": "Overfitting means",
      "과거에만 잘 맞도록 맞춰진 것": "being tuned to fit only the past",
      "을 말합니다. 시험 문제를 통째로 외운 학생이 새 문제를 못 푸는 것과 같습니다. 이 검사는 그 위험을 확률로 재고, 높으면 실제로 비중을 깎습니다.":
        ". It is the student who memorised the exam paper and cannot answer a new question. This check measures that risk as a probability, and when it is high it actually trims the weight.",
      "적중률은 \'방향을 맞혔나\'이지 \'돈을 벌었나\'가 아닙니다 — 작게 여러 번 맞고 크게 한 번 틀리면 적중률은 높고 잔고는 줍니다":
        "A hit rate says \"was the direction right\", not \"did it make money\" — being right small many times and wrong big once leaves a high hit rate and a smaller balance",
      "실전 표본이 얇으면 신뢰구간이 넓습니다. 구간이 50%를 품고 있으면 \'못한다\'가 아니라 \'아직 모른다\'입니다":
        "A thin live sample makes the confidence interval wide. An interval containing 50% means \"we do not know yet\", not \"it is bad\"",
      "인샘플 적중률은 모델이 이미 본 구간이라 실력의 증거가 아닙니다":
        "The in-sample hit rate covers ground the model has already seen, so it is not evidence of skill",
      "확률 보정은 지금 **표시 전용**입니다 — 어긋남이 확정돼도 그것만으로 비중을 줄이지는 않습니다(과최적화 검증 게이트는 줄입니다)":
        "Probability calibration is display-only for now — even a confirmed mismatch does not by itself cut the weight (the overfitting gate does)",
      "여기 숫자는 전부 시뮬레이션 장부에서 셌습니다. 실제 체결·호가를 겪은 값이 아닙니다":
        "Every number here was counted from a simulated ledger. None of it met a real fill or a real order book",
      "이 페이지의 숫자는 배치가 매일 계산해 커밋하는":
        "Every number on this page is read only from",
      "에서만 읽습니다 — 원본을 직접 볼 수 있습니다.":
        ", which the batch computes and commits daily — you can read the source yourself.",
      "가상 자금 시뮬레이션입니다. 실제 돈이 아니며 투자 권유가 아닙니다. 수익을 보장하지 않습니다.":
        "This is a play-money simulation. It is not real money, not investment advice, and no return is guaranteed.",

      // ══ 오늘의 판단 (today.html) ═════════════════════════════
      "오늘의 판단 — 100만 챌린지": "Today's call — 1M Won Challenge",
      "100만 챌린지 · 100만원 → 1억":
        "1M Won Challenge · KRW 1,000,000 → 100,000,000",
      "어젯밤 재학습: 전 종목 챔피언 유지 (확실히 나은 후보 없음 — 정상)":
        "Last night's retraining: every champion kept (no clearly better candidate — normal)",
      "오늘의 자세": "Today's stance",
      "판단 근거 (새벽 기준)": "Reasoning (as of the morning call)",
      "관망 (현금)": "Standing aside (cash)",

      "95% 신뢰구간": "95% confidence interval",
      "95% 구간": "95% interval",

      // ══ 실기록 (paper.html) ══════════════════════════════════
      "● 라이브 보는 중": "● Watching live",
      // ── 계좌가 **아무것도 안 들고 있을 때**만 뜨는 문구들 ─────────
      // ⚠️ 사전을 쓴 날 계좌가 종목을 들고 있어서 이 가지가 화면에 없었다.
      //    2026-08-26에 코인 단타가 전량 현금이 되자 한꺼번에 드러났다.
      //    "지금 화면에 있는 것"만 사전에 담으면 계좌 상태가 바뀔 때마다
      //    영어가 조금씩 무너진다 — 안 보이는 가지도 언젠가 보인다.
      "지금은 아무것도 안 들고 있습니다":
        "Nothing is held right now",
      "아직 잴 수 있는 보유가 없습니다.":
        "There are no holdings to measure yet.",
      "전량 현금(관망)입니다": "All cash (standing aside)",
      "— 신호가 약하면 조금만 사거나 아예 안 삽니다. 전량 현금은 고장이 아니라 \"지금은 살 이유가 없다\"는 판단입니다.":
        "— when the signal is weak it buys little or nothing at all. All cash is not a failure; it is the call that there is no reason to buy right now.",
      "실시간": "live",
      // 셋으로 갈린다: 실시간 / 지연 시세 / 전일 확정(index.html).
      "지연 시세": "delayed quote",
      "전일 확정": "settled yesterday",
      "100만 챌린지 — 매일 자동 페이퍼":
        "1M Won Challenge — automated paper trading, every day",
      "통합 계좌는": "The combined account spreads risk across several symbols with",
      "가상 자금": "play money",
      "으로 여러 종목에 위험 분산하며, 클라우드가 매일 새벽(한국시간) 챔피언 전략으로 자동 모의 매매한 결과입니다.":
        ", and this is the result of the cloud running the champion strategies as automated paper trades every morning (Korean time).",
      "그대로 공개": "published as it is",
      "⚠️ 아래": "⚠️ The",
      "종목별 참고 계좌": "per-symbol reference accounts",
      "는 종목마다 따로 굴리는": "below are run separately for each symbol —",
      "별개의 1만원 계좌": "separate KRW 10,000 accounts",
      "입니다 — 합계가 통합 계좌 원금을 넘는 것이 정상이며, 통합 계좌의 보유량이 아닙니다. 여러분은 아무것도 하지 않아도 됩니다.":
        ". Their total exceeding the combined account's principal is normal, and it is not what the combined account holds. Nothing is required of you.",
      "가짜 돈": "not real money",
      "이며, 좋은 결과도 미래 수익을 보장하지 않습니다.":
        ", and a good result guarantees nothing about the future.",
      "원금 (매칭 입금 포함)": "Principal (matching deposits included)",
      "운용 손익": "Trading P&L",
      "실력 지표 (시간가중 TWR)": "Skill measure (time-weighted return)",
      "무작위 전략 1,000개 대비": "against 1,000 random strategies",
      "상위 0%": "top 0%",
      "진화 없이 고정 전략이었다면": "if the strategy had been frozen with no evolution",
      "첫날 균등 매수 후 보유했다면":
        "if everything had been bought equally on day one and held",
      "전략 − 보유 (초과성과)": "Strategy − buy & hold (excess)",
      "─ 계좌 자산 · ┄ 원금 · ⋯ 그냥 보유 · ● 챔피언 교체 · ▲ 매칭 입금 ·":
        "─ account equity · ┄ principal · ⋯ buy & hold · ● champion swap · ▲ matching deposit ·",
      "구조 교체(이후 0일부터 다시)": "structure change (the count restarts from zero)",
      "현재 챔피언:": "Current champion:",
      "거래일": "Trading days",
      "계좌 자산": "Account equity",
      "총노출": "Gross exposure",
      "과거 400봉 · 인샘플": "past 400 bars · in-sample",
      "주간 수익률 보기 (최근 8주)": "Show weekly returns (last 8 weeks)",
      "주간": "Weekly",
      "매일 새벽 확정 기록": "Settled each morning",
      "아래는": "Below are",
      "종목마다 따로 굴리는 참고용 계좌":
        "reference accounts run separately for each symbol",
      "이며, 여기 자산·비중이 통합 계좌의 보유량은 아닙니다. 통합 계좌가 실제로 얼마를 들고 있는지는 위 카드의":
        ". The equity and weights here are not what the combined account holds. For what the combined account actually holds, see",
      "과": "and",
      "첫 화면의 \'통합 노출\' 열": "the \"combined exposure\" column on the first screen",
      "을 보세요.": ".",
      "참고계좌 자산": "Reference-account equity",
      "참고계좌 비중": "Reference-account weight",
      "추이(30일)": "Trend (30 days)",
      "배분 방식 실험": "Allocation-method experiment",
      "가상 자금 · 상대 비교 전용":
        "play money · for relative comparison only",
      "(사전 등록 — 기준은": "(pre-registered — the criteria are published",
      "에 공개)": ")",
      "배분 방법": "Allocation method",
      "실험계좌 자산": "Experiment equity",
      "HRP (현행)": "HRP (current)",
      "위험기여 균등": "Equal risk contribution",
      "자본 균등": "Equal capital",
      "역변동성": "Inverse volatility",
      "— 본 계좌는 신호가 켜진 종목에 **똑같이** 나눠 담습니다(균등 조각). 이 그림자는 같은 신호를 받되 **줄을 세워 상위 몇 개에만**, 그것도 점수에 비례해 담습니다 — 확신이 두 배면 금액도 두 배입니다. 집중은 공짜가 아니라서 맞을 때 더 벌고 틀릴 때 더 잃습니다. 반드시 최대낙폭과 함께 읽으세요. 종가 평가·수수료만 차감이라 본 계좌와 절대 비교는 안 되고, 배분 방식의 효과를 보는 용도입니다.":
        "— the main account splits equally across every symbol whose signal is on. This shadow takes the same signals but ranks them and buys only the top few, in proportion to score: twice the conviction, twice the amount. Concentration is not free — it earns more when right and loses more when wrong. Always read it next to the max drawdown. It marks to the close and deducts fees only, so it cannot be compared to the main account in absolute terms; it exists to show the effect of the allocation method.",
      "담은 종목 수": "Symbols taken",
      "조기 판정 진도": "Progress toward an early verdict",
      "— 경계를 넘으면 그 시점에 조기 판정이 납니다. 넘기 전에는 \'진행 중\'이며, 진행 중은 \'아직 모른다\'이지 \'차이가 없다\'가 아닙니다. 이 경계는 결과를 보기 전에 등록했고, 매일 들여다봐도 거짓 승리 확률이 5%를 넘지 않는다는 것을 시뮬레이션 검사로 확인합니다.":
        "— crossing the boundary produces an early verdict at that moment. Before it is crossed the state is \"in progress\", and in progress means \"we do not know yet\", not \"there is no difference\". The boundary was registered before any result was seen, and simulation checks confirm that even looking at it every day keeps the false-victory rate under 5%.",
      "비교": "Comparison",
      "상태": "State",
      "경계까지": "To the boundary",
      "표본 부족": "sample too small",
      "AI 확률의 정직성 검증": "Checking whether the AI's probabilities are honest",
      "보정": "calibration",
      "된 것이고, 크게 어긋나면 그 사실이 그대로 여기 보입니다. 예측은 새벽에 먼저 기록되고 결과는 다음 날 붙습니다. 신뢰구간(95%)이 좁아질 때까지는 비율보다 구간을 믿으세요.":
        ", and a large mismatch shows up right here as it is. The prediction is recorded in the morning and the outcome is attached the next day. Until the 95% confidence interval narrows, trust the interval rather than the ratio.",
      "예측 확률": "Predicted probability",
      "일수": "Days",

      // ══ 매일 새벽 배치가 만드는 판단 설명 — **절 단위** ══════
      //
      // 통째로는 매일 글자가 달라 사전이 못 찾는다. 절(clause)로 끊으면
      // 틀이 몇 개 안 되고, 모르는 절은 한국어로 남는다(엔진의 clauses()).
      "관망 (현금)": "Standing aside (cash)",
      "최근 변동성이 커서 위험 조절이 비중을 낮게 잡음":
        "recent volatility is high, so risk control set the weight low",
      "🛡 실적 가드: 발표 임박 → 비중 절반":
        "🛡 Earnings guard: a release is imminent → weight halved",

      "위 설명은 의석 1위 의원의 논리이며, 오늘의 비중은 의원 신호를 의석 비중으로 가중 평균한 값입니다":
        "the explanation above is the reasoning of the largest seat-holder; today's weight is the seat-weighted average of every member's signal",
      "다음 시가(주식)": "next open (stocks)",
      "개장 시가": "opening price",
      "다음 장 시가": "next session's open",
      "판단 재료": "inputs behind the call",
      "합산": "pooled",

      // ══ 기록 검증 (trust.html) ═══════════════════════════════
      "이 기록은 조작할 수 없습니다": "This record cannot be tampered with",
      "\"수익률을 그럴듯하게 꾸민 것 아니냐\"는 의심은 정당합니다 — 인터넷의 수익 인증 대부분이 실제로 그렇기 때문입니다. 그래서 이 챌린지는":
        "\"Aren't the returns just dressed up?\" is a fair suspicion — most profit screenshots on the internet are exactly that. So this challenge made",
      "기록 구조 자체를 공개 장부로": "the record structure itself a public ledger",
      "만들었습니다. 누구든 아래 방법으로 직접 검증할 수 있습니다.":
        ". Anyone can verify it directly, in the ways below.",
      "어떻게 조작이 불가능한가": "Why tampering is impossible",
      "모든 기록은 공개 저장소에 git 커밋으로 쌓입니다.":
        "Every record accumulates as a git commit in a public repository.",
      "매일 새벽 자동화가 매매 결과를": "Each morning the automation commits the trading result to the",
      "state/ 폴더에 커밋": "state/ folder",
      "하며, 각 커밋에는 시각·내용·서명이 영구히 남습니다. 과거 기록을 몰래 고치면 커밋 역사에 흔적이 남아 즉시 드러납니다.":
        ", and every commit keeps its time, contents and signature permanently. Quietly editing a past record leaves a mark in the commit history and shows up immediately.",
      "계산 코드도 전부 공개입니다.": "The calculation code is public too.",
      "수익률 계산·매매 로직·검증 절차가": "Return calculations, trading logic and validation procedures are",
      "오픈소스": "open source",
      "라 \"어떻게 계산했는지\"를 직접 확인할 수 있습니다.":
        ", so you can check \"how was this calculated\" for yourself.",
      "가짜 데이터 차단이 코드에 박혀 있습니다.":
        "The block on fake data is built into the code.",
      "실제 시세를 받지 못한 날은 기록을 남기지 않고 건너뜁니다 — 합성 데이터로 기록을 채우는 경로 자체가 없으며, 이 동작은 자동 테스트로 고정돼 있습니다.":
        "A day whose real quotes could not be fetched is skipped with no record — there is no code path at all that fills a record with synthetic data, and that behaviour is pinned down by automated tests.",
      "불리한 숫자도 함께 보여줍니다.": "The unflattering numbers are shown too.",
      "전략 수익률만이 아니라 \"그냥 보유했다면\"과 최대낙폭을 나란히 표시합니다 — 전략이 지고 있으면 지고 있다고 화면에 그대로 나옵니다.":
        "Not just the strategy's return: \"what if you had simply held\" and the max drawdown sit right beside it — when the strategy is losing, the screen says so.",
      "재현성 — 같은 입력이면 같은 결과가 나옵니다":
        "Reproducibility — the same input produces the same result",
      "매일 새벽의 판단 기록에는 세 가지 지문이 함께 저장됩니다.":
        "Every morning's decision record is stored with three fingerprints.",
      "코드 커밋 해시": "Code commit hash",
      "— 그날 어떤 버전의 코드가 판단했는지.":
        "— which version of the code made that day's call.",
      "입력 데이터 SHA-256": "Input data SHA-256",
      "— 그날 판단에 쓴 시세 데이터의 해시. 데이터 원본도":
        "— the hash of the price data used that day. The raw data is kept in",
      "에 그대로 보관됩니다.": "as it was.",
      "난수 시드": "Random seed",
      "— 도전자 전략을 만들 때 쓴 시드(날짜 기반 고정값).":
        "— the seed used to generate challenger strategies (fixed, derived from the date).",
      "그래서 누구든 저장소를 받아": "So anyone can clone the repository, run",
      "를 실행하면 그날의 재학습을": ", and reproduce that day's retraining",
      "그대로 재현": "exactly",
      "해 기록과 일치하는지 기계적으로 확인할 수 있습니다. \"조작 불가\"가 주장이 아니라 검증 가능한 사실이 되는 구조입니다.":
        "to check mechanically that it matches the record. That structure is what turns \"cannot be tampered with\" from a claim into a verifiable fact.",
      "스스로를 의심하는 장치들": "Devices that doubt ourselves",
      "체결가 현실성": "Realistic fill prices",
      "— 새벽에 내린 판단은 그 시점 종가가 아니라":
        "— a call made in the morning is not filled at that moment's close but at the",
      "다음 거래 세션의 시가": "next trading session's opening price",
      "로 체결됩니다(코인만 24시간 시장이라 즉시). 개장 갭이 불리하게 벌어지면 그 손해를 그대로 떠안고, 수수료·거래세· 슬리피지를 뺀 \"깎인 숫자\"만 기록합니다.":
        "(crypto alone fills immediately, being a 24-hour market). If the opening gap goes against us we take that loss as it comes, and only the \"trimmed number\" — after fees, transaction tax and slippage — is recorded.",
      "다중검정 보정": "Multiple-testing correction",
      "— 도전자를 많이 시험할수록 우연히 좋아 보이는 전략이 나올 확률도 커집니다. 그래서 검증 횟수를 저장하고, 횟수가 늘수록 챔피언 교체 문턱을 자동으로":
        "— the more challengers we test, the greater the chance that one looks good by luck. So the number of tests is stored, and as it grows the bar for replacing a champion automatically",
      "더 높입니다": "rises",
      "그날의 도전자 수": "that day's challenger count",
      "최근 1년 도전자 수": "the last year's challenger count",
      "투명성 표시용": "for transparency only",
      "긴 검증": "The long validation",
      "— 오늘의 전략 설정을": "— today's strategy settings are applied to a",
      "훨씬 긴 과거": "much longer past",
      "(약 10년)에 적용해 시기별로 몇 번 통했는지 셉니다. 반년짜리 성적으로는 \"이 설정이 진짜인가\"에 답할 수 없기 때문입니다.":
        "(about ten years) to count how often they worked, period by period. Half a year of results cannot answer \"are these settings real?\"",
      "배우는 구간은 늘리지 않습니다": "The learning window is not extended",
      "— 10년치로 배우게 하면 이미 죽은 패턴(2015년의 시장)을 익히므로, 늘리는 것은":
        "— learning on ten years would teach it patterns that are already dead (the market of 2015), so what gets extended is only the",
      "시험 구간": "testing window",
      "뿐입니다.": ".",
      "⚠️ 이 숫자에는": "⚠️ These numbers carry",
      "생존 편향": "survivorship bias",
      "이 있습니다. 10년을 돌리는 이 종목들은": ". The symbols run over ten years are the ones that",
      "오늘 살아남아 저희가 고른": "survived to today and that we then chose",
      "종목입니다. 10년 전의 저희는 이것들을 고를 수 없었고, 그때 골랐을 종목 중 사라진 것들의 손실은 여기에 없습니다 —":
        ". We could not have picked them ten years ago, and the losses from the ones we would have picked that later vanished are not in here —",
      "그래서 실제로 얻을 수 있었던 것보다 좋게 나옵니다.":
        "so the result comes out better than what was actually achievable.",
      "얼마나 좋은지는 모릅니다(모르는 것을 안다고 적지 않습니다). 설정 자체도 최근 데이터에서 뽑혔으니 과거 구간에 대해서는 \'답을 보고 고른\' 설정입니다. 그래서 이 값은":
        "By how much, we do not know (we do not write down what we do not know as if we did). The settings themselves were drawn from recent data, so with respect to past periods they are settings \"chosen after seeing the answer\". For that reason these values are",
      "관찰로만 남기고 전략 교체 판정에 쓰지 않습니다":
        "kept as observation only and never used to decide a strategy swap",
      ". 매주 월요일 자동으로 계산되며, 위 두 문장이 보고서에 항상 함께 실립니다.":
        ". It is computed automatically every Monday, and the two sentences above always ride along with the report.",
      "\'그냥 보유했다면\'을 반드시 나란히": "\"what if you had simply held\" right alongside, always",
      "보유를 이긴 구간은 31%": "only 31% of periods beat holding",
      "지금 이 설정은 장기 보유를 이기지 못합니다.":
        "As it stands, these settings do not beat long-term holding.",
      "상승장에서는 플러스 비율이 저절로 높아지므로, 그 숫자만 내는 것은 자기를 속이는 일입니다. 왜 그런지도 숫자로 나옵니다 — 전략이 시장에 들어가 있는 시간이":
        "In a rising market the share of positive periods goes up by itself, so publishing that number alone is self-deception. Why it happens shows up in the numbers too — the time the strategy spends in the market is",

      "뿐이고 들어갈 때도 조금씩만 삽니다. 그래서": ", and even when it does go in it buys only a little at a time. So",
      "비중을 정하는 방식": "the way weights are decided",
      "을 매일 밤 오디션의 후보로 세웠습니다(지금까지 그 항목만 한 번도 시험되지 않았습니다). 손으로 바꾸지 않고":
        "was entered as a candidate in the nightly audition (that one item had never been tested until now). It is not changed by hand — it has to",
      "다른 후보와 똑같은 심사를 이겨야": "win the same audition as every other candidate",
      "반영됩니다.": "before it takes effect.",
      "숏(공매도)과 레버리지는 잠겨 있습니다 — 왜인지 숫자로 밝힙니다":
        "Shorting and leverage are locked — and we say why, in numbers",
      "켤 수 있는 상태인지 먼저 돌려봤고, 셋 다 아니었습니다.":
        "we first ran the checks on whether it could be switched on. Three answers came back, and none of them was yes.",
      "5,000만원어치가 그대로 체결": "KRW 50,000,000 worth filled exactly as ordered",
      "비용(대차료)이 전 시장 0원": "cost of borrowing was zero in every market",
      "파산 확률을 아직 못 잰다": "we cannot yet measure the probability of ruin",
      "현실에서는 낼 수 없는 성적": "results that could not be produced in reality",
      "켤 수 있게": "able to be switched on",
      "숏이 공짜가 아니게": "shorting no longer free",
      "기록이 쌓여야": "only once the record accumulates",
      "열립니다. 코드가 아니라 시간의 문제입니다.":
        ". It is a question of time, not of code.",
      "섀도 대조군": "Shadow control arm",
      "— 챔피언을 한 번도 바꾸지 않는 고정 전략 포트폴리오를 병행 운용해 나란히 공개합니다. 진화 시스템이 실제로 가치를 더하는지, 아니면 그냥 시장 덕인지 비교로 드러납니다.":
        "— a portfolio whose champions never change is run alongside and published next to ours. Whether the evolution actually adds value, or whether it is just the market, shows up in the comparison.",
      "의회 운용": "Parliament",
      "— 오디션을 통과한 전략에게만": "— only strategies that pass the audition get a",
      "의석(비중)": "seat (a share of the weight)",
      "을 주고, 최대 3석까지 나눠 갖게 하는 구조입니다. 비중은 홀드아웃 성과에 따라 서서히만 이동하고, 서로 너무 비슷한(수익 상관 과다) 전략은 한 자리만 남깁니다.":
        ", up to three seats shared between them. Weights move only slowly, following hold-out performance, and strategies too similar to each other (returns too correlated) are collapsed into one seat.",
      "지금 42개 계좌 중": "Right now, of 42 accounts,",
      "42개가 2석 이상": "42 hold two seats or more",
      "돈의 분산은 다른 이야기": "spreading the money is another story",
      "무작위 벤치마크": "Random benchmark",
      "— 매일 무작위 매매 전략 1,000개를 같은 조건으로 돌려 우리 성과가 그 분포에서 상위 몇 %인지 표시합니다. 동전 던지기보다 정말 나은지 매일 검증받는 셈입니다.":
        "— every day a thousand random trading strategies are run under the same conditions, and we show where our result sits in that distribution. It amounts to being tested daily on whether we really beat a coin flip.",
      "아직 심사받지 않은 종목": "Symbols not yet auditioned",
      "계산 중…": "Calculating…",
      "운용 종목을 늘리면 그날부터 매매는 시작되지만,":
        "Adding a symbol starts the trading that same day, but the",
      "오디션(매일 밤 후보 수십 개와 겨루는 심사)":
        "audition (a nightly contest against dozens of candidates)",
      "은 순서를 기다립니다. 아직 차례가 안 온 종목은 자기 전략이 없어":
        "has to wait its turn. A symbol whose turn has not come has no strategy of its own and runs on the",
      "기본 전략": "default strategy",
      "으로 돕니다 — 그 전략이 그 종목에서 통하는지 확인된 적이 없다는 뜻입니다.":
        "— meaning nobody has confirmed that the strategy works on that symbol.",
      "그래서 이런 종목은": "So such symbols have their",
      "비중을 4분의 1로": "weight cut to a quarter",
      "줄입니다. 검증이 하루 늦은 것 (절반)보다 더 세게 줄이는 이유는":
        ". The reason it is cut harder than a symbol whose validation is merely a day late (which is halved) is that we",
      "더 모르기 때문": "know even less about it",
      "입니다. 2026-08-23 이전에는 이 둘을 구별하지 않고 똑같이 절반만 줄이고 있었습니다 — 그때 계좌의 절반 넘는 돈이 한 번도 심사받지 않은 종목 위에 있었습니다.":
        ". Before 2026-08-23 the two were not distinguished and both were merely halved — at that time more than half the account's money sat on symbols that had never been auditioned.",
      "지금 이 관문을 넘으려면 무엇이 필요한가":
        "What it would take to clear this gate right now",
      "중 통과": "passing",
      ". DSR(운이 아니라 실력일 확률) 최고값은":
        ". The best DSR (the probability that it is skill rather than luck) is",
      "이고 통과선은": "and the passing line is",
      "지금 표본은 종목당": "The sample is currently",
      "이고 누적 시행은": "per symbol, with a cumulative",
      "표본을 늘리는 길": "Ways to grow the sample",
      "판단 횟수": "Number of calls",
      "필요 샤프": "Sharpe required",

      ". 정확히 말하면 선발전 문턱은": ". Precisely: the qualifying bar rises with",
      "로, 결승전 문턱은": ", and the final bar with",
      "로 올립니다(각각 t≥√(2·ln n), t≥1+0.5·log₁₀(1+n/1000), 상한 1.35). 누적 총계를 쓰면 문턱이 영원히 올라가 진화가 완전히 멈추기 때문이며, 누적 총계는 문턱이 아니라":
        "(t≥√(2·ln n) and t≥1+0.5·log₁₀(1+n/1000) respectively, capped at 1.35). Using the running total would push the bar up forever and stop evolution altogether; the running total is published not as a bar but",
      "(2026-08-11 수정: 이 문단은 \"누적 횟수로 문턱을 높인다\"고 적혀 있었지만 코드는 롤링 1년 + 상한이었습니다. 코드가 아니라 설명이 틀렸던 것이라 설명을 고쳤습니다.)":
        "(Corrected 2026-08-11: this paragraph said \"the bar rises with the cumulative count\", but the code used a rolling year plus a cap. The description was wrong, not the code, so the description was fixed.)",
      "(2026-08-18 보강: 상한이 있는 공식은 시도가 아주 많아지면 더 오르지 않습니다 — 그 빈틈을 막으려고 결승 통과자에게 관문을 하나 더 달았습니다. 그날 링에 선":
        "(Strengthened 2026-08-18: a capped formula stops rising once attempts get very numerous — to close that gap, finalists face one more gate. Taking the out-of-sample results of",
      "모든 후보": "every candidate",
      "의 최근 미공개 구간 성적을 놓고 \"이 중 최고가 순전히 우연으로 나올 확률\"을 무작위 재추출(부트스트랩, 고정 시드라 재현 가능)로 직접 재서, 그 확률이 10%보다 크면 결승 점수를 넘었어도 승격을 보류합니다. 후보를 많이 세울수록 이 관문은 자동으로 엄격해집니다 — 상한이 필요 없는 보정입니다.)":
        "that stood in the ring that day, we measure directly by resampling (bootstrap, fixed seed so it is reproducible) the probability that the best of them arose purely by chance. If that probability exceeds 10%, promotion is withheld even for a candidate that cleared the final score. The more candidates enter, the stricter this gate becomes automatically — a correction that needs no cap.)",
      "냅니다. 처음 만들었을 때는 \"구간의 62%가 플러스\"라고만 적었는데, 대조군을 붙이니":
        ". When it was first built it said only \"62% of periods were positive\"; once a control arm was attached,",
      "였습니다. 예를 들어 SK하이닉스는 전략이": ". For example, on SK hynix the strategy returned",
      ", 그냥 들고 있었으면": ", while simply holding returned",
      "였습니다.": ".",
      "① 100만원 계좌에 −500%를 지시하니":
        "① Ordering −500% on a KRW 1,000,000 account produced",
      "됐습니다 — 빌릴 주식이 있는지도, 담보가 있는지도 안 보는 계좌였습니다. ② 빌린 주식을 들고 있는":
        ". The account checked neither whether the shares could be borrowed nor whether there was collateral. ② The",
      "이었습니다 — 공짜로 무한정 들고 있을 수 있다는 뜻입니다. ③ 레버리지는 이미 잠겨 있었고, 이유는 \"":
        "— meaning a position could be held free of charge, indefinitely. ③ Leverage was already locked, and the reason given was \"",
      "\"였습니다 (기록이 3일치뿐입니다). ①②를 그대로 두고 숏 전략을 매일 밤 심사에 올리면,":
        "\" (there were only three days of record). Putting short strategies into the nightly audition with ① and ② left as they were would select strategies on",
      "으로 전략이 뽑힙니다. 그래서 켜는 대신": ". So instead of switching it on, we made it",
      "만들었습니다 — 가진 것보다 많이 파는 것을 막고(팔고 나오는 길은 그대로 열어 둡니다), 담보를 넣은 만큼만 열리게 하고, 대차료를 시장별로 채워":
        ": selling more than is held is blocked (the exit from a position stays open), the size opens only as far as posted collateral allows, and borrowing costs were filled in per market to make",
      "했습니다. 레버리지는 손대지 않았습니다 — 그 자물쇠는":
        ". Leverage was left untouched — that lock opens",
      "으로 분산 운용 중입니다(최대 3석 / 상한 3석). 다만 자리 수와":
        "(maximum 3 seats / cap 3). But the number of seats and",
      "(2026-08-13 정정: 이 문단은 \"통과자 최대 3개가 의석을 나눠 갖고… 단일 전략 붕괴가 계좌 붕괴가 되는 구조를":
        "(Corrected 2026-08-13: this paragraph said, in the present tense, that \"up to three qualifiers share the seats… so a single strategy collapsing no longer collapses the account\" —",
      "없앤 것": "eliminated",
      "현재형으로": "in the present tense",
      "적혀 있었습니다. 그런데 실제 장부는 전 계좌가": ". But the actual ledger showed every account on",
      "1석": "one seat",
      "이었습니다 — 한 번도 2석이 된 적이 없습니다. 의석은 2단계 오디션을 통과한 승격자만 얻는데 승격이 139회 중 1회였고, 그 1회조차 챔피언의 파라미터 변형이라 상관 게이트가 곧바로 한 석으로 합쳤기 때문입니다. 구조는 있지만 아직 잠들어 있었고, 하필 이 장치는":
        "— never two. Seats go only to those promoted through the two-stage audition, and there was one promotion in 139; even that one was a parameter variant of the champion, so the correlation gate collapsed it straight back into one seat. The structure exists but was asleep, and this particular device",
      "작동할 때만 자기를 알리고 잠들어 있을 때는 침묵":
        "announces itself only while working and stays silent while asleep",
      "했습니다. 코드가 아니라 문장이 틀렸으므로 문장을 고치고, 잠든 상태 자체를 매일 숫자로 내보내 위 문장이 그 숫자를 읽게 했습니다. 즉 지금 이 계좌는":
        ". The sentence was wrong, not the code, so the sentence was fixed — and the sleeping state itself is now published as a daily number that the sentence above reads. In other words this account currently",
      "사실상 단일 전략으로 굴러갑니다": "runs on effectively a single strategy",
      "입니다. 이 조건에서 통과선에 닿으려면": ". To reach the passing line under these conditions,",
      "가 필요합니다 — 세계 최상위 펀드가 좋은 해에 내는 수준입니다.":
        "would be required — the level a world-leading fund produces in a good year.",
      "지금 — 하루 1회 판단 · 3년": "Now — one call a day · 3 years",
      "종목을 묶어 한 모델로(실효 표본 1.78배)":
        "pooling symbols into one model (1.78× effective sample)",
      "하루 1회 판단 · 6년": "one call a day · 6 years",
      "1시간마다 판단 · 3년": "a call every hour · 3 years",
      "15분마다 판단 · 3년": "a call every 15 minutes · 3 years",
      "이 칸은 나쁜 소식을 적는 자리입니다.": "This box is where bad news is written.",
      "2026-08-19, 전 종목 과최적화 검증이 처음으로 끝까지 돌았고":
        "On 2026-08-19 the overfitting validation ran to completion across every symbol for the first time, and",
      "통과한 종목은 하나도 없었습니다": "not one symbol passed",
      ". 여기서 \"전략이 나쁘다\"와 \"지금 표본으로는 넘을 수 없는 관문이다\"는 대응이 정반대라, 추측하지 않고 역산했습니다 — 위 숫자가 그 답입니다.":
        ". \"The strategy is bad\" and \"the gate cannot be cleared with this sample\" call for opposite responses, so rather than guess we worked it backwards — the numbers above are the answer.",
      "관문은 낮추지 않습니다.": "The gate will not be lowered.",
      "결과를 보고 기준을 고치는 것이 이 제품이 하지 않겠다고 약속한 바로 그 일(골대 이동)입니다. 정공법은":
        "Changing the criteria after seeing the result is precisely what this product promised not to do (moving the goalposts). The honest route is to",
      "표본을 늘리는 것": "grow the sample",
      "이고, 장중 트랙(하루 여러 번 판단하는 별도 실험 계좌)이 그 실험입니다. 그동안 이 계좌는":
        ", and the intraday tracks (separate experimental accounts that decide several times a day) are that experiment. Meanwhile this account runs at",
      "절반 이하 노출": "half exposure or less",
      "로 굴러갑니다 — 고장이 아니라 설계입니다.":
        "— by design, not by fault.",
      "가동률 — 자동화가 실제로 매일 돌았는가":
        "Uptime — did the automation actually run every day?",
      "지난": "Over the last",

      "\"이라고": "\" —",
      "기록 — 가동률": "records — uptime",
      "· 결측": "· missing",
      "(기록을 지어내지 않고 비워 둔 날)":
        "(days left blank rather than invented)",
      "새벽 자동화가 API 장애 등으로 기록을 남기지 못한 날은":
        "On a day when the morning automation could not record — an API outage, say — we",
      "기록을 지어내지 않고 결측으로 남깁니다":
        "leave it missing rather than invent a record",
      ". 결측 일수 자체를 공개하는 것이 회복력의 증거입니다(달력일 기준 보수적 계산). 잡 실패 시에는 디스코드로 즉시 경보가 옵니다.":
        ". Publishing the number of missing days is itself the evidence of resilience (counted conservatively, by calendar day). A failed job raises an immediate Discord alert.",
      "재출발·기준 변경 기록 (숨기지 않습니다)":
        "Restarts and changes of criteria (nothing hidden)",
      "어떤 환율을 썼는지도 함께 공개합니다.":
        "The exchange rate used is published too.",
      "환산을 한다고 말하면서 환율을 밝히지 않으면 그냥 믿어 달라는 말이 됩니다. 그날 배치가 적용한 원/달러는 장부의 각 기록에":
        "Saying that a conversion was made without naming the rate amounts to asking to be believed. The USD/KRW rate the batch applied that day is kept in each ledger record as",
      "로 남고, 잔고 표 아래에 \"원/달러 ○○○원을 적용해 환산했습니다\"로 표시됩니다 — 누구든 그 값으로 직접 곱해 검산할 수 있습니다. 환율은 매일 새벽 배치가 공개 시세(KRW=X)의 마지막 종가로 한 번 잡습니다.":
        ", and shown under the holdings table as \"converted at KRW ○○○ per USD\" — anyone can multiply it out and check. The rate is fixed once each morning by the batch, from the last close of a public quote (KRW=X).",
      "실시간 환율이 아닙니다": "It is not a live rate",
      "— 하루 한 번 확정되는 값이고, 확인하지 못한 날에는 해외 종목을 아예 기록하지 않습니다(1.0으로 때우지 않습니다).":
        "— it is settled once a day, and on a day we cannot confirm it, overseas holdings are not recorded at all (we do not paper over it with 1.0).",
      "화면에 단위가 다른 두 가격이 나옵니다 — 둘 다 맞습니다.":
        "Two prices in different units appear on screen — both are correct.",
      "\'잔고\' 표는 통합 계좌라": "The holdings table is the combined account, so it is",
      "전부 원화로 환산": "entirely converted to won",
      "한 값이고, \'종목별 현황\' 표와 하단 티커는": ", while the per-symbol table and the ticker at the bottom are",
      "그 종목이 거래되는 통화 그대로": "in the currency that symbol trades in",
      "입니다 (미국주식 달러 · 코인 USDT · 한국주식 원). 종목별 참고 계좌는 그 종목만 따로 굴리는 단일 통화 장부라 현지 통화로 재는 것이 맞기 때문입니다. 그래서 같은 종목의 \'현재가\'가 두 표에서 1,400배 가까이 차이 날 수 있습니다 — 어느 쪽도 틀리지 않았지만 혼동하기 쉬워, 각 표에 단위를 적어 두었습니다.":
        "(dollars for US stocks, USDT for crypto, won for Korean stocks). Each per-symbol reference account is a single-currency ledger trading that symbol alone, so measuring it in local currency is the right thing. That is why the same symbol's \"last price\" can differ by nearly 1,400× between the two tables — neither is wrong, but it is easy to confuse, so each table states its unit.",
      "주가는 실시간이 아닙니다.": "Prices are not live.",
      "매매·평가에 쓰는 가격은": "The price used for trading and valuation is the close of the",
      "마지막으로 완성된 봉": "last completed bar",
      "의 종가입니다(코인은 진행 중인 봉의 현재가로 체결하되 판단은 완성 봉으로 합니다 — 위 항목 참조). 첫 화면 하단의 티커만 거래소 공개 API로 준실시간 시세를 보여주며, 그 값은":
        "(crypto fills at the current price of the bar in progress but decides on completed bars — see above). Only the ticker at the bottom of the first screen shows near-live quotes from a public exchange API, and those values",
      "장부에 들어가지 않습니다": "never enter the ledger",
      ". 잔고·수익률·낙폭은 전부 확정된 기록에서 나옵니다.":
        ". Holdings, returns and drawdowns all come from settled records.",
      "2026-08-18, 판정 시계의 규칙을 바꿨습니다 — 앞으로는 개선해도 시계를 리셋하지 않습니다.":
        "2026-08-18 — the verdict clock's rule changed: from now on, an improvement no longer resets it.",
      "지금까지는 구조(피처·사이징 등)가 바뀔 때마다 \"엣지 입증\" 판정 시계를 0일부터 다시 세웠습니다. 운영자 결정으로 측정 대상을 재선언합니다: 우리가 재는 것은 얼어붙은 전략 하나가 아니라":
        "Until now, every change of structure (features, sizing and so on) restarted the \"edge proven\" clock from day zero. By the operator's decision we restate what is being measured: not one frozen strategy, but",
      "개선을 계속하는 과정 전체": "the whole process of continuing to improve",
      "입니다. 그래서 시계는 현 계좌 탄생일(2026-08-13)부터 연속으로 흐릅니다. 대신 세 가지를 약속합니다 — ① 시계가 도는 동안의":
        ". So the clock runs continuously from the current account's birth (2026-08-13). In exchange, three promises — ① every structural change while the clock runs is",
      "모든 구조 변경을 날짜와 함께 공개": "published with its date",
      "2026-08-18, 외부 검토를 받았고 — 가장 아픈 지적 둘을 그대로 적습니다.":
        "2026-08-18 — we had an outside review, and the two most painful findings are written here as they were given.",
      "이 시스템의 투자 방식 설명서를 외부에 보여 개선점을 요청했습니다. 받은 지적 중 두 가지는 우리가 스스로 못 본 것이라, 좋게 포장하지 않고 그대로 공개합니다.":
        "We showed an outside party the description of how this system invests and asked what to improve. Two of the findings were things we had not seen ourselves, so we publish them as they are, without dressing them up.",
      "① 운용 종목 20개는 2026년에 사람이 골랐습니다 — 생존 편향이 있습니다.":
        "① The 20 traded symbols were chosen by a person, in 2026 — there is survivorship bias.",
      "사실을 공개": "publish the fact",
      "최우선": "top priority",
      "규칙 유니버스를 즉시 부착": "a rule-based universe was attached immediately",
      "② 장중 실험의 판정 기간 30일은 너무 짧았습니다 — 90일로 고칩니다.":
        "② The intraday experiment's 30-day verdict window was too short — it is changed to 90 days.",
      "기간": "elapsed time",
      "지금 고치면 정직한 수정이고, 30일 뒤에 고치면 골대 이동입니다.":
        "Changing it now is an honest amendment; changing it after 30 days would be moving the goalposts.",
      "2026-08-19, 돌고 있는 실험 4개의 판정 기준을 사전 등록합니다.":
        "2026-08-19 — the verdict criteria for the four running experiments are pre-registered.",
      "결과를 보고 나서 기준을 정하면 그 선택 자체가 결과에 오염됩니다(골대 이동). 그래서 데이터가 쌓이기 전인 지금, 각 실험의 판정일과 판정 방법을 박아서 공개합니다 — 몇 달 뒤의 판정이 의심받지 않게 하기 위해서입니다.":
        "Setting criteria after seeing the result contaminates the choice with the result (moving the goalposts). So now, before the data accumulates, each experiment's verdict date and method are fixed and published — so that the verdict months from now is not open to doubt.",
      "장중 1시간봉 vs 본 계좌": "Intraday hourly bars vs the main account",
      "— 판정": "— verdict",
      "주기 사다리(1시간·15분·5분)": "Interval ladder (1 hour · 15 min · 5 min)",
      "(90일), 트랙 쌍 3개의 검정에 다중비교 보정(본페로니)을 적용합니다.":
        "(90 days), with a multiple-comparison correction (Bonferroni) applied across the three track pairs.",
      "지정가 그림자": "Limit-order shadow",

      "으로 계속 공개합니다.":
        "and it stays published.",
      "(90일). 지정가가 이겨도":
        "(90 days). Even if limit orders win,",
      "미체결율 20% 초과면 채택 보류":
        "adoption is withheld if the unfilled rate exceeds 20%",
      "— 체결 안 되는 이득은 이득이 아닙니다.":
        "— a gain you never get filled on is not a gain.",
      "배분 사다리(HRP·위험기여 균등·자본 균등·역변동성)":
        "Allocation ladder (HRP · equal risk contribution · equal capital · inverse volatility)",
      "미국주식 장중 1시간봉":
        "US stocks, intraday hourly bars",
      "미국 지정가 그림자":
        "US limit-order shadow",
      "(2026-08-19 추가 등록) — 판정":
        "(registered 2026-08-19) — verdict",
      "2026-08-19 정정 — 판정 방식에 '조기 판정'을 더합니다.":
        "2026-08-19 amendment — an early verdict is added to the method.",
      "사장님 지시로 기간 단축 방법을 검토한 결과입니다. 원래 방식은 판정일에":
        "This came from reviewing, at the owner's request, how the window could be shortened. The original method looked at the data",
      "딱 한 번":
        "exactly once",
      "대신":
        "instead",
      "훔쳐볼 권리를 미리 사 두는":
        "buying the right to peek, in advance",
      "판정일 자체는 바꾸지 않았습니다.":
        "The verdict date itself was not changed.",
      "정직하게 덧붙이면,":
        "To be honest about it,",
      "속도는 효과 크기로 삽니다.":
        "speed is bought with effect size.",
      "실험 1~4일차인 지금":
        "now, on days 1-4 of the experiment",
      "2세대 집중 배분":
        "Generation-2 concentrated allocation",
      "(120일). 지금 본 계좌는 신호가 켜진 종목에":
        "(120 days). Today the main account splits across every symbol whose signal is on,",
      "똑같이":
        "equally",
      "나눠 담습니다. 이 실험은 같은 신호를":
        "This experiment takes the same signals and",
      "줄 세워 상위 몇 개에만, 점수에 비례해":
        "ranks them, buying only the top few, in proportion to score",
      "담습니다 — 확신이 두 배면 금액도 두 배입니다. 집중이 이겨도":
        "— twice the conviction, twice the amount. Even if concentration wins,",
      "최대낙폭이 본 계좌의 1.5배를 넘으면 채택 보류":
        "adoption is withheld if the max drawdown exceeds 1.5× the main account's",
      "입니다(수익이 위험을 사서 온 것이면 승리가 아닙니다).":
        "(a return bought with risk is not a win).",
      "일곱 실험 모두, 기준 미달의 결과는 같습니다:":
        "For all seven experiments, falling short of the criteria has the same consequence:",
      "현행 유지 + 결과 그대로 공개.":
        "keep what we have, and publish the result as it is.",
      "그 페이지를 열면":
        "Opening that page showed",
      "\"기록을 불러오지 못했습니다\"":
        "\"could not load the record\"",
      "한 줄만 보였습니다. 원인은 사소합니다 — 페이지가 불러오는":
        "and nothing else. The cause was trivial — one of the",
      "파일 이름 하나가 틀려 있었습니다":
        "file names the page loaded was wrong",
      "읽는 쪽에서만 보이지 않았고":
        "it was invisible only to the reader",
      ", 화면은 그것을 \"오늘은 기록이 없나 보다\"로 읽히게 두었습니다.":
        ", and the screen let it read as \"there must be no record today\".",
      "모르는 것과 아닌 것은 다릅니다":
        "\"we do not know\" and \"it did not happen\" are different",
      "아무도 몰랐다는 사실":
        "the fact that nobody noticed",
      "첫 화면 하나에만":
        "only on the first screen",
      "\"다 그리지 못했습니다\"라고 말하고":
        "says \"it could not be fully drawn\" and",
      "원본 기록이 있는 곳을 알려 줍니다, ③":
        "points to where the original record lives, ③",
      "공개되는 모든 페이지":
        "every page that is published",
      "종목을 눌렀을 때 열리는 차트":
        "the chart that opens when a symbol is clicked",
      "도 절반이 죽어 있어 함께 정리했습니다.":
        "was half dead too, and was cleaned up along with it.",
      "그동안 잘못 보였던 화면은 되돌리지 않습니다":
        "The screens that were wrong in the meantime are not rolled back",
      "— 무엇이 얼마나 안 보였는지 여기 적는 것으로 대신합니다.":
        "— writing down what was invisible, and for how long, takes their place.",
      "손으로 숫자를 적는 대신":
        "instead of writing the numbers in by hand",
      "결과는":
        "The result",
      "안 맞았습니다.":
        "did not match.",
      "으로 나왔는데, 그날 시스템이 실제로 말한 값은":
        "came out, but what the system actually said that day was",
      "입니다 —":
        "—",
      "5.24% 높습니다.":
        "5.24% higher.",
      "방향이 중요합니다.":
        "The direction matters.",
      "하필 좋아 보이는 쪽으로 틀렸습니다.":
        "It was wrong in exactly the flattering direction.",
      "이 문단은 그 장치가 실제로 작동했다는 기록입니다.":
        "This paragraph is the record that the safeguard actually worked.",
      "대신 첫 화면이":
        "Instead the first screen shows",
      "그날 시스템이 뭐라고 했는지":
        "what the system said that day",
      "계좌 장부가 아닙니다.":
        "It is not the account ledger.",
      "2026-08-16은 다릅니다. 그날은":
        "2026-08-16 is different. On that day",
      "결과 자체가 없습니다.":
        "there is no result at all.",
      "일어나지 않은 날":
        "a day that did not happen",
      "이라, 채울 것이 없습니다.":
        ", so there is nothing to fill in.",
      "사장님 폰에 이렇게 남았습니다.":
        "This is what was left on the owner's phone.",
      "앞의 둘은 저장되지 않았습니다.":
        "The first two were never saved.",
      "배치의 순서가":
        "The batch's order was",
      "①계산 → ②알림 → ③검사 → ④저장":
        "① compute → ② notify → ③ check → ④ save",
      "사람은 위부터 읽습니다.":
        "People read from the top.",
      "지금은 알림을":
        "Now a notification goes out",
      "저장이 끝난 뒤에만":
        "only after the save is finished",
      "실패 경보만":
        "only a failure alert",
      "나갑니다.":
        "goes out.",
      "같은 날 하나 더 고쳤습니다. 코인 5종이":
        "One more fix the same day. Five crypto symbols were reading",
      "165일 묵은 시세":
        "a quote 165 days stale",
      "\"오늘 이미 했다\"로 읽고 조용히 건너뛰었습니다.":
        "as \"already done today\" and quietly skipping.",
      "'오늘'이 아니라 5개월 반 전이었습니다. 이제 시세가 묵으면 그 종목은":
        "It was not \"today\" but five and a half months earlier. Now, when a quote goes stale, that symbol",
      "소리 내어 실패합니다":
        "fails out loud",
      "장중 감시 경보도 손봤습니다. 지금까지":
        "The intraday watchdog alert was fixed too. Until now it reported only the",
      "최악 간격(9.3시간)":
        "worst gap (9.3 hours)",
      "만 말했는데, 실측 117회의":
        "— but across 117 measurements the",
      "중앙값은 29분":
        "median is 29 minutes",
      "위험 한도 계산은 계속 최악값으로 합니다":
        "Risk limits are still computed from the worst case",
      "(안전한 쪽).":
        "(the safe side).",
      "사장님 지적으로 찾았습니다:":
        "Found because the owner pointed it out:",
      "\"투자한 잔고는 지금 코인밖에 없고, 거래내역에는 주식이 있고...\"":
        "\"the holdings are all crypto right now, but the trade history has stocks…\"",
      "맞습니다. 거래내역에는":
        "He was right. The trade history had",
      "\"2026-08-15 · 아마존 · 매수\"":
        "\"2026-08-15 · Amazon · buy\"",
      "가 있는데 잔고에 아마존은 없었습니다.":
        "while Amazon was nowhere in the holdings.",
      "그날 기록에는 같은 종목이":
        "That day's record has the same symbol on",
      "두 줄로":
        "two lines",
      "동시에":
        "at once",
      "적혀 있습니다. 진실은 후자입니다.":
        ". The latter is the truth.",
      "한 주도 사지 않았습니다.":
        "Not a single share was bought.",
      "더 아픈 것은":
        "What stings more is",
      "이 사고를 이미 한 번 다뤘다는 사실":
        "that this incident had already been handled once",
      "입니다. 2026-08-17에 같은 자리를 고치면서":
        ". On 2026-08-17, fixing the same spot, only the",
      "금액만":
        "amount",
      "숫자를 가려도 주장은 그대로 남습니다.":
        "Hiding the number leaves the claim standing.",
      "지금은 그 줄이":
        "Now that line reads",
      "\"주문 실패 — 현금 부족으로 한 주도 체결되지 않았습니다\"":
        "\"order failed — not enough cash, not a single share filled\"",
      "로 나갑니다. 첫 화면의 거래내역과 '오늘의 판단' 페이지가":
        ". The first screen's trade history and the Today's Call page now use the",
      "같은 판정":
        "same verdict",
      "기록은 지우지 않습니다":
        "The record is not deleted",
      "같은 날 첫 화면도 손봤습니다. 종목별 현황이":
        "The first screen was fixed the same day. The per-symbol status was",
      "스무 줄":
        "twenty rows",
      "오늘 돈이 들어가 있는 종목부터":
        "the symbols with money in them today come first",
      "보이게 했으며, 몇 종목을 접었는지는 표 제목이 말합니다.":
        ", and the table's title says how many were folded away.",
      "장부는":
        "The ledger",
      "2026-08-15에서 08-18로 건너뜁니다.":
        "jumps from 2026-08-15 to 08-18.",
      "그 이틀은 시장이 쉰 날도, 성적이 나쁜 날도 아닙니다.":
        "Those two days were neither market holidays nor bad days.",
      "기록을 만드는 자동 배치가 실패했습니다.":
        "The automated batch that writes the record failed.",
      "검사가 죽으면 기록을 쓰지 않습니다":
        "If the checks die, no record is written",
      "(잘못된 기록은 다음 날의 출발점이 되기 때문입니다).":
        "(a wrong record becomes the next day's starting point).",

      "(2026-08-19 추가 등록 — 첫 회차가 돌기 전에 등록했습니다) — 판정":
        "(registered 2026-08-19, before the first round ran) — verdict",
      "2026-08-17 자산이":
        "On 2026-08-17 the equity came out as",
      "2026-08-17 밤, 알림이 \"일어나지 않은 일\"을 사실처럼 방송했습니다.":
        "On the night of 2026-08-17 a notification broadcast something that never happened as if it were fact.",
      "08:23 🚨 'Nightly Retrain' 실패 (2026-08-17)":
        "08:23 🚨 'Nightly Retrain' failed (2026-08-17)",
      "를 받고 있었는데, 그 묵은 날짜가 \"마지막으로 학습한 날짜\"와 같아서 프로그램이":
        ", and because that stale date matched \"the date last trained on\", the program read it",
      "2026-08-18까지 사흘 동안, 화면이 \"사지 않은 것을 샀다\"고 말했습니다.":
        "For three days, up to 2026-08-18, the screen said it had bought something it never bought.",
      "절반만 고친 것이고, 그 절반이 사장님 눈에 \"일관성이 없다\"로 보였습니다.":
        "Only half of it was fixed, and that half looked to the owner like \"this is inconsistent\".",
      "을 씁니다.":
        "is used.",
      "은 매매 계산 중에 오류가 나서 그날 배치가 죽었습니다(본실행과 재시도 모두).":
        "hit an error mid-calculation and the batch died that day (both the main run and the retry).",
      "\"없음\"을 빈칸으로 표현한 것이 어떤 컴퓨터에서는 \"있음\"으로 읽혔습니다.":
        "Representing \"none\" as an empty value read as \"present\" on some machines.",
      "없는 기록을 나중에 채워 넣지 않습니다.":
        "A missing record is not filled in afterwards.",
      "지금 계산해서 만들면 그날 실제로 무엇을 했는지가 아니라":
        "Computing it now would give not what was actually done that day but",
      "오늘 다시 계산한 값":
        "a value recalculated today",
      "이틀 연속으로 놓친 것이 가장 아픈 부분입니다.":
        "Missing it two days running is the part that stings most.",
      "\"조용히 틀리느니 시끄럽게 멈춘다\"":
        "\"stop loudly rather than be wrong quietly\"",
      "같은 실수가 다시 나오지 않도록":
        "so the same mistake cannot recur",
      "관문 자신이 고장 원인":
        "the gate itself becomes the cause of the failure",
      "이 되기 때문입니다.":
        ".",
      "사장님이 물으셨습니다:":
        "The owner asked:",
      "\"지금 투자 자동으로 하고있는 방식이 가장 이상적인 형태인지 궁금해.\"":
        "\"I wonder whether the way this invests automatically right now is the ideal form.\"",
      "정직하게 답하면":
        "The honest answer is",
      "아닙니다.":
        "no.",
      "세 가지를 그대로 적습니다.":
        "Three things, written as they are.",
      "① 목표와 설정이 같은 세상의 숫자가 아닙니다.":
        "① The goal and the settings are not numbers from the same world.",
      "이 계좌는":
        "This account runs at",
      "연 변동성 12%":
        "12% annualised volatility",
      "100배":
        "100×",
      "가 필요합니다.":
        "is required.",
      "한 해 평균 수익률":
        "Average annual return",
      "1억까지":
        "to 100 million won",
      "79년":
        "79 years",
      "41년":
        "41 years",
      "28년":
        "28 years",
      "이건 고쳐야 할 결함이 아니라":
        "This is not a defect to fix but",
      "규율의 결과":
        "the result of discipline",
      "일부러 잠가 둡니다.":
        "is deliberately kept locked.",
      "② 그래서 지금 점수는 \"1억\"이 아니라 \"그냥 보유보다 나은가\"입니다.":
        "② So the score right now is not \"100 million won\" but \"is it better than simply holding?\"",
      "같은 기간 전 종목을 그냥 사서 들고만 있었다면 얼마였는지":
        "what it would have been had every symbol simply been bought and held over the same period",
      "를 나란히 적습니다. 실측 2026-08-15 기준, 그냥 보유는":
        "is written right beside it. Measured as of 2026-08-15, buy & hold was",
      "이고 이 시스템은":
        "and this system was",
      "좋아 보이지 않는 숫자지만 그게 지금의 사실입니다.":
        "It is not a flattering number, but it is the current fact.",
      "③ 20종목이 사실상 하나의 베팅이었습니다.":
        "③ Twenty symbols were effectively one bet.",
      "20개 계좌의 판단 방식이":
        "Of the twenty accounts' decision methods,",
      "19개가 완전히 동일":
        "nineteen were completely identical",
      "했습니다(나머지 1개도 문턱 하나만 다름). 종목은 스무 개인데":
        "(the remaining one differed by a single threshold). Twenty symbols, but",
      "판단하는 머리는 하나":
        "one head doing the deciding",
      "들어오는 문이 하나뿐":
        "there was only one door in",
      "이어서였습니다. 그 문은":
        ". That door asked only",
      "\"새 방식이 지금 방식보다 더 나은가?\"":
        "\"is the new method better than the current one?\"",
      "만 물었고, 그 문은":
        ", and it opened",
      "189번 중 1번":
        "once in 189 tries",
      "열렸습니다. 그래서 두 번째 문을 달았습니다 —":
        ". So a second door was added —",
      "\"지금 방식만큼 하면서, 서로 다른 때에 맞고 틀리는가?\"":
        "\"does it do as well as the current method, while being right and wrong at different times?\"",
      "성적이 같아도":
        "Even with equal results,",
      "서로 다른 시점에 틀리는 두 방식":
        "two methods that are wrong at different moments",
      "을 섞으면 계좌가 덜 출렁입니다. 그 문도 공짜가 아닙니다: 최근 성적이":
        "mixed together make the account swing less. That door is not free either: recent results must be",
      "유의하게 나쁘지 않을 것":
        "not significantly worse",
      ", 미공개 구간에서":
        ", it must be",
      "다시 확인할 것":
        "confirmed again out of sample",
      ", 기존 방식과":
        ", and its movement must be",
      "움직임이 충분히 다를 것":
        "sufficiently different from the existing method",
      "— 셋을 다 통과해야 하고, 자리도 승격자보다 작게 줍니다.":
        "— all three must pass, and it gets a smaller seat than a promoted challenger.",
      "기존 승격 문턱은 하나도 낮추지 않았습니다.":
        "Not one of the existing promotion bars was lowered.",
      "2026-08-17, 사이트가 계좌보다 큰 금액을 사실처럼 보여주고 있었습니다.":
        "2026-08-17 — the site was presenting amounts larger than the account as if they were fact.",
      "사장님이":
        "The owner said,",
      "\"홈페이지 숫자들이 다 맞진 않은 것 같은데? 금액이 말이야\"":
        "\"I don't think all the numbers on the site are right — the amounts, I mean\"",
      "라고 하셔서 전부 대조했고, 맞았습니다.":
        "so everything was cross-checked, and he was right.",
      "· 오늘의 체결 —":
        "· today's fill —",
      "(자산의 6.4배)":
        "(6.4× the equity)",
      "· 지금 켜진 경고 — 비앤비":
        "· warnings currently lit — BNB",
      "· 리플":
        "· XRP",
      "· 비트코인":
        "· Bitcoin",
      "(합계 자산의 9.8배)":
        "(9.8× the equity in total)",
      "세 갈래가 겹쳤습니다.":
        "Three threads overlapped.",
      "① 사지 않은 주문이 '매수'로 적혔습니다.":
        "① An order that was never filled was recorded as a \"buy\".",
      "같은 날 장부에는 그 아마존이":
        "The same day's ledger also says that Amazon was",
      "현금 부족으로 거부됐다":
        "rejected for lack of cash",
      "고도 적혀 있습니다 — 즉":
        "— that is,",
      "한 주도 사지 않았는데":
        "not a single share was bought",
      "주식 쪽만 그대로였습니다.":
        "only the stock side was left as it was.",
      "② 금액을 아무도 검사하지 않았습니다.":
        "② Nobody was checking the amounts.",
      "비중은 검사하고 있었고 그날 비중은":
        "Weights were being checked, and that day's weights were",
      "전부 정상 범위":
        "all within the normal range",
      "③ 화면에 통화 표시가 없었습니다.":
        "③ The screen carried no currency label.",
      "남은 절반":
        "the remaining half",
      "입니다. 그날 자산·현금· 잔고는 바로잡았는데":
        ". Equity, cash and holdings were corrected that day, but",
      "체결 기록과 예산 기록은 잘못된 값 그대로 남았고":
        "the fill records and the budget records were left with the wrong values",
      "한 건·한 종목이 그날 계좌보다 클 수 없다":
        "no single fill and no single symbol may exceed that day's account",
      "\"표시하지 않음\"":
        "\"not shown\"",

      "2026-08-16부터 하루 넘게, '오늘의 판단' 페이지가 통째로 죽어 있었습니다.":
        "From 2026-08-16, for more than a day, the Today's Call page was entirely dead.",
      "배치를 돌리는 컴퓨터에는 브라우저가 없는데 있다고 착각해 검사가 죽었고, 이 시스템은":
        "The machine running the batch has no browser, but the check assumed it did and died — and this system",
      "2026-08-17, \"1억\"의 산수를 그대로 적습니다 — 지금 설정으로는 수십 년입니다.":
        "2026-08-17 — the arithmetic of \"100 million won\", written plainly: with today's settings it takes decades.",
      "입니다. 위험을 키우면 기간은 줄지만,":
        ". Raising the risk shortens the time, but raising it",
      "에서 위험을 키우는 것은 도박입니다. 그래서 장부에는 매일 이렇게 적힙니다 —":
        "is gambling. So the ledger records this every day —",
      ", \"판정 시계 진행 중\". 90일을 채워 실력이 증명되기 전까지 이 상한은":
        ", \"verdict clock running\". Until 90 days are complete and skill is proven, this cap",
      "으로 두고 여기로 안내합니다, ④ 체결가에 통화를 적습니다.":
        "and points here instead; ④ the fill price carries its currency.",
      "이미 저장된 2026-08-15 기록은 고치지 않습니다":
        "The 2026-08-15 record already stored is not corrected",
      "그날의 체결·예산 표시":
        "that day's fill and budget display",
      "2026-08-17, 장부가 '판다'와 '산다'를 같은 숫자로 적고 있었습니다.":
        "2026-08-17 — the ledger was writing \"sell\" and \"buy\" as the same number.",
      "종목별로 얼마를 실었는지 적는 칸이":
        "The column recording how much was placed on each symbol",
      "방향을 지우고 크기만":
        "erased the direction and kept only the size",
      "\"아마존 30% 보유\"":
        "\"holding 30% Amazon\"",
      "라고 말하면서 계좌는 아마존을":
        "while the account had Amazon",
      "팔아 둔":
        "sold short",
      "판 종목이 화면에서 통째로 사라지는":
        "a sold symbol vanishing from the screen entirely",
      "여전히 잠겨 있습니다":
        "it remains locked",
      "새벽 자동화가 통째로 멈추는 결함":
        "a defect that stops the whole morning automation",
      "도 나왔습니다: 파는 주문이 담보 부족으로 거부되면 그 사실을 기록하는 코드가":
        "also turned up: when a sell order is rejected for lack of collateral, the code that records it",
      "다른 종류의 거부와 형식을 혼동해":
        "confused the format with a different kind of rejection",
      "프로그램을 그대로 죽였습니다. 실행해 보고서야 알았습니다.":
        "and killed the program outright. We only found out by running it.",
      "브레이크는 다릅니다":
        "The brakes are different",
      "지금의 브레이크 그대로":
        "with today's brakes as they are",
      ", 브레이크를 걸면":
        "; with the brakes on,",
      ". 킬스위치는 3년간 3번 발동했고, 첫 발동일은":
        ". The kill switch fired three times in three years, the first on",
      "스트레스 시나리오":
        "Stress scenarios",
      "정직한 사실 셋:":
        "Three honest facts:",
      "① 이 숫자는 전부":
        "① All of these numbers come from",
      "실전 코드와 같은 함수":
        "the same functions as the live code",
      "저희 모델은 가격 말고도":
        "Besides price, our model also uses",
      "몇 주 동안 한 번도 붙지 않았습니다.":
        "had not connected once in weeks.",
      "원인은":
        "The cause was",
      "같은 규칙을 두 곳에 적어 둔 것":
        "the same rule written in two places",
      "이었습니다. 시세를 받아오는 쪽은 한 거래소가 막히면 다른 거래소로 순서대로 넘어가는":
        ". The price-fetching side had a",
      "대체 목록":
        "fallback list",
      "첫 번째 거래소 이름만 코드에 박혀":
        "only the first exchange's name was baked into the code",
      "시세와 똑같은 대체 목록":
        "the very same fallback list as the prices",
      "을 따라갑니다 — 목록은 한 곳에만 적혀 있고, 양쪽이 그 하나를 읽습니다. 그리고":
        ". The list lives in one place and both sides read that one. And",
      "그날 어느 거래소에서 받았는지":
        "which exchange it came from that day",
      "거래소별로 왜 실패했는지":
        "why each exchange failed",
      "정직한 한계:":
        "An honest limit:",
      "이 저장소 안에서는 거래소 접속이 막혀 있어 실제로 붙는지 확인할 수 없었습니다. 확인은":
        "Inside this repository the exchange connection is blocked, so we could not confirm that it actually connects. Confirmation comes from",
      "다음 자동 배치":
        "the next automated batch",
      "저희는 \"성과가 실력인지 운인지\"를":
        "We say whether the result is skill or luck only",
      "90일을 채운 뒤에":
        "after 90 days are complete",
      "사람이 손으로 적어 둔 이름표":
        "a label written in by hand",
      "였습니다. 위의 참고 지표 3개가 죽어 있는 동안에도 이름표는 그대로였고, 그것을 되살리면":
        ". While the three reference indicators above were dead the label stayed the same, and reviving them would have produced a state where",
      "모델이 보는 것은 달라지는데 시계는 안 멈추는":
        "what the model sees changes while the clock keeps running",
      "상태가 됩니다. 그러면 90일 뒤에 발표할 표본이":
        ". Then the sample published after 90 days would be",
      "앞부분(지표 없음)과 뒷부분(지표 있음)이 섞인 것":
        "a mix of an early part (no indicators) and a later part (with indicators)",
      "이 되고, 그 사실은 90일이 지나서야 알게 됩니다. 그래서 이제 시계는 이름표가 아니라":
        ", and we would only learn that after the 90 days had passed. So the clock now runs not on the label but on",
      "그날 밤 실제로 붙은 지표 목록":
        "the list of indicators that actually connected that night",
      "을 보고 돕니다. 구성이 달라지면 그날부터 다시 셉니다. 다만":
        ". If the configuration changes, the count restarts from that day. That said,",
      "하루이틀짜리 자료 장애로는 리셋되지 않습니다":
        "a one- or two-day data outage does not reset it",
      "4일차에서 0일차로":
        "from day 4 back to day 0",
      "돌아갑니다. 4일을 잃는 대신, 90일 표본이 처음부터 한 가지 구조로 모입니다.":
        ". Four days are lost, and in exchange the 90-day sample is gathered under one structure from the start.",
      "기록은 시장별로 따로 쌓이는데(코인은 매일, 주식은 거래일에만), 어느 시장이":
        "Records accumulate per market (crypto daily, stocks on trading days only), and which market",
      "기록에 처음 등장하는 날":
        "first appears in the record",
      "관찰 기간을 실제보다 짧게":
        "understates the observation period",
      "말하는 쪽이라, 반대 방향(더 오래 봤다고 말하는 것)보다 낫다고 판단했습니다.":
        ", which we judged better than the opposite error (claiming to have watched longer).",
      "\"라이브러리 없음·종목코드 불일치·조회 실패 가능\"":
        "\"library missing · ticker mismatch · lookup may have failed\"",
      "이라는":
        "— a",
      "가능성 나열":
        "list of possibilities",
      "자기 이유를 그대로":
        "its own reason, as it is",
      "남깁니다 — 조회가 거절당했는지, 표가 비어서 왔는지, 자료 제공처가":
        "— whether the lookup was refused, whether the table came back empty, or whether the provider",
      "열 이름을 바꿨는지":
        "renamed a column",
      "(이 경우 값은 멀쩡한데 지표만 사라져서 가장 찾기 어렵습니다)까지 구별됩니다.":
        "(the hardest to find, because the values look fine while the indicator quietly disappears).",
      "아직 원인은 모릅니다.":
        "We do not yet know the cause.",
      "다음 배치가 이유를 적어 주면 그때 고칩니다 — 모르는 것을 안다고 적지 않습니다.":
        "When the next batch writes down the reason, we will fix it then — we do not write down what we do not know as if we did.",
      "2026-08-16, 실제로 돈이 나가는 쪽에 자동 브레이크가 안 걸려 있었습니다.":
        "2026-08-16 — the side where money actually leaves had no automatic brakes wired to it.",
      "저희 모의 계좌에는 자동 브레이크가 둘 있습니다.":
        "Our paper account has two automatic brakes.",
      "손실이 커지면 스스로 투자 규모를 줄이는 장치":
        "a device that shrinks the position size on its own as losses grow",
      "\"이 성과가 착각인지\" 검사 결과를 그 종목 투자 비중에 곱하는 장치":
        "a device that multiplies each symbol's weight by the result of the \"is this result an illusion?\" check",
      "실제 증권사로 주문을 내는 경로에는 둘 다 배선돼 있지 않았습니다.":
        "Neither was wired into the path that places orders with a real broker.",
      "거기 있던 것은 사람이 손으로 돌리는 조절기와 일시정지뿐이었습니다.":
        "All that lived there was a hand-turned dial and a pause button.",
      "더 나쁜 것은":
        "Worse,",
      "잴 재료조차 없었다":
        "there was not even the material to measure with",
      "는 점입니다. 실거래 장부는 주문 한 줄마다 '현금 + 그 종목' 값만 남기고":
        ". The live ledger recorded only \"cash + that symbol\" per order and",
      "계좌 전체 자산은 어디에도 기록하지 않았습니다.":
        "never recorded the account's total equity anywhere.",
      "손실이 얼마나 났는지 재려면 계좌 자산이 있어야 하는데, 그 숫자가 없었습니다.":
        "Measuring the loss requires the account equity, and that number did not exist.",
      "고쳤습니다. 이제 실거래 경로도":
        "Fixed. The live path now also",
      "주문을 내기 전에 계좌 자산을 재고, 모의 계좌와 똑같은 브레이크를 똑같은 함수로 적용":
        "measures the account equity before placing an order and applies the same brakes as the paper account, through the same functions",
      "정직한 사실 셋.":
        "Three honest facts.",
      "① 실거래는 아직":
        "① Live trading has",
      "한 번도 켜진 적이 없습니다":
        "never once been switched on",
      "(증권사 키 미발급 + 이중 잠금). 그래서 이 결함으로 잃은 돈은":
        "(no broker key issued, plus a double lock). So the money lost to this defect is",
      "없습니다":
        "none",
      ". ② 하지만 실거래 전환에 남은 절차가 사실상 '키 발급'뿐이었으므로,":
        ". ② But since the only step left before going live was effectively \"issue the key\",",
      "키가 생기는 날 브레이크 없이 돌 뻔했습니다.":
        "it would have run without brakes on the day that key appeared.",
      "③ 이 브레이크들은 여전히":
        "③ These brakes still",
      "실제 증권사 API로는 검증되지 않았습니다":
        "have not been verified against a real broker API",
      "— 가상 시험으로만 확인했습니다.":
        "— only against simulated tests.",
      "어제 장중 감시를 붙이면서 저희는 이렇게 적었습니다.":
        "When the intraday watchdog was attached yesterday, we wrote this.",
      "우리가 실제로 얼마나 자주 봤는가의 기록":
        "the record of how often we actually looked",
      "오늘 그 기록을 처음 읽어 봤습니다.":
        "Today we read that record for the first time.",
      "08-15 17:20 → 08-16 02:37, 무려 558분(9.3시간)":
        "08-15 17:20 → 08-16 02:37 — a full 558 minutes (9.3 hours)",
      "\"15분마다 봅니다\"는 설정을 옮겨 적은 문장이었지 사실이 아니었습니다.":
        "\"We look every 15 minutes\" was a sentence copied from a setting, not a fact.",
      "다행히":
        "Fortunately",
      "설계는 제대로 작동했습니다":
        "the design itself worked correctly",
      "— 레버리지 한도는 예약값이 아니라":
        "— the leverage limit is computed not from the schedule but from",
      "실제로 관측된 최악의 간격":
        "the worst gap actually observed",
      "진짜 문제는 아무도 그 기록을 읽지 않았다는 것":
        "The real problem was that nobody read that record",
      "기록하는 것과 읽는 것은 다른 일입니다.":
        "Recording and reading are different acts.",
      "이제 실제 간격이 예약보다 크게 벌어지면":
        "Now, when the real gap opens well beyond the schedule,",
      "알림으로 나갑니다.":
        "an alert goes out.",
      "대외 문구에서 \"15분마다 감시합니다\"라고 쓰면 안 됩니다.":
        "Public copy must not say \"we monitor every 15 minutes\".",
      "정확한 문장은":
        "The accurate sentence is",
      "\"15분마다 돌도록 예약했고, 실제 간격을 기록해 공개한다\"":
        "\"it is scheduled to run every 15 minutes, and the real gap is recorded and published\"",
      "입니다. 지난 기록은 고치지 않고 그대로 두었습니다.":
        ". Past records were left exactly as they were.",

      "합니다(첫 화면 판정 시계에 이력 표시), ② 과거 기록은 절대 소급 수정하지 않습니다, ③ 경계 날짜를 남겨 구간별 성적을 따로 볼 수 있게 합니다 — 옛 성적으로 새 구성을 포장하는 착시는 리셋이 아니라 공개된 경계가 막습니다. 이 수정 자체도 직전 리셋 이틀 뒤, 결과가 쌓이기 전에 한 것입니다 — 결과를 보고 고치면 골대 이동이지만 지금 고치면 정직한 수정이라는, 장중 실험 30일→90일 수정과 같은 원칙입니다.":
        "(shown as history on the first screen's verdict clock); ② past records are never retroactively edited; ③ boundary dates are kept so each period's results can be read separately — the illusion of dressing up a new configuration with old results is prevented not by a reset but by a published boundary. This amendment itself was made two days after the previous reset, before results accumulated — the same principle as the intraday 30→90 day change: fixing it after seeing the result would be moving the goalposts, fixing it now is an honest amendment.",
      "지금 잘나가는 종목(엔비디아·비트코인 등)이 유니버스에 있다는 것 자체가 사후 선택입니다. 과거 데이터로 잰 백테스트·적중률·검증 수치에는 \"이미 살아남아 유명해진 종목만 골랐다\"는 유리함이 깔려 있고, 그만큼 실제보다 좋게 보일 수 있습니다. 당장 종목을 바꾸면 진행 중인 90일 공개 측정이 오염되므로 지금은":
        "That today's winners (NVIDIA, Bitcoin and so on) are in the universe at all is a choice made after the fact. Every backtest, hit rate and validation number measured on past data carries the advantage of \"only symbols that already survived and became famous were picked\", and may look that much better than reality. Changing the symbols right now would contaminate the 90-day public measurement under way, so for now we",
      "하고, 측정이 끝나는 경계(2세대)에서 \"시가총액 상위 N개처럼 사람 손을 타지 않는 규칙\"으로 유니버스를 다시 정의하는 것을":
        "and, at the boundary where the measurement ends (generation 2), redefining the universe by \"a rule untouched by human hands, such as the top N by market capitalisation\" has been made the",
      "과제로 올렸습니다. 그때까지 이 사이트의 과거 구간 수치는 이 편향을 안고 있는 숫자로 읽어 주세요.":
        "task. Until then, please read this site's past-period numbers as numbers carrying that bias.",
      "(2026-08-18 당일 수정: 운영자 지시(\"개선을 미루지 않는다\")로 2세대까지 기다리지 않고":
        "(Amended the same day, 2026-08-18: on the operator's instruction — \"do not postpone improvements\" — rather than waiting for generation 2,",
      "했습니다 — 매월 1회, 코인은 거래대금 순위·한국은 시가총액 순위·미국은 같은 날 저녁부터 시가총액 순위(나스닥 공개 스크리너)로 재선정하며, 산출에 쓴 순위표가 스냅샷에 남고 변경은 판정 시계의 버전 이력에 공개됩니다(리셋 없음). 과거 구간 수치에 위 편향이 깔려 있다는 사실은 그대로 유효합니다.)":
        ". Once a month, crypto is reselected by turnover rank, Korea by market capitalisation, and the US by market capitalisation from that same evening (a public Nasdaq screener); the ranking table used is kept in the snapshot and changes are published in the verdict clock's version history (no reset). The fact that past-period numbers carry the bias above remains true.)",
      "두 계좌(하루 1회 vs 1시간마다)의 성과 차이는 수익률 차이라서, 통계적 판정의 힘은 봉 개수가 아니라":
        "The performance difference between the two accounts (once a day vs every hour) is a difference in returns, so the power of a statistical verdict is governed not by the number of bars but by",
      "이 정합니다. 30일로는 진짜 우위를 놓칠 확률과 우연을 우위로 읽을 확률이 둘 다 높습니다. 실험 첫날, 기록이 반나절치뿐인 지금 고칩니다 —":
        ". At 30 days both the chance of missing a real edge and the chance of reading luck as an edge are high. We change it now, on the experiment's first day, with only half a day of record —",
      "수정 사실과 이유는 실험 페이지의 판정 기준 옆에 함께 실렸습니다. 30일 시점에는 중간 참고 판독만 하고, 확정 판정은 90일입니다.":
        "The amendment and its reason ride alongside the criteria on the experiment page. Day 30 gives an interim read only; the binding verdict is at 90 days.",
      "(120일 — 배분 차이는 신호보다 느리게 갈라져 90일로는 검정력이 얇습니다). 대안 3개의 검정에 본페로니 보정.":
        "(120 days — allocation differences separate more slowly than signal differences, so 90 days gives thin power). A Bonferroni correction across the three alternatives.",
      "(90일), 본 계좌 대비 일수익 차이의 통계 검정(유의수준 5%). 통화가 달라(달러 가상 계좌) 비교는 퍼센트 수익률로만 합니다. 9월 18일에 중간 참고 판독(확정 아님).":
        "(90 days), a statistical test of the daily-return difference against the main account (5% significance). The currency differs (a dollar play-money account), so the comparison is by percent return only. An interim read on 18 September (not binding).",
      "(90일). 주식은 호가 간격이 코인과 달라 \"값을 걸고 기다리는 체결\"의 값어치가 다를 수 있어 따로 잽니다. 코인 쪽과 같이":
        "(90 days). Stocks have different tick sizes from crypto, so the value of \"posting a price and waiting\" may differ; it is measured separately. As on the crypto side,",
      "만 볼 수 있었습니다 — 중간에 들여다보며 \"지금 이겼네\"를 찾으면, 진짜 차이가 없어도 언젠가 우연히 문턱을 넘기 때문입니다(그래서 지금까지 안 봤습니다).":
        "was all we could look at — peeking along the way for \"we're winning now\" would eventually cross the threshold by chance even with no real difference (which is why we have not looked until now).",
      "방법을 넣었습니다. 경계선을 데이터가 쌓이기 전인 지금 박아 두면, 매일 들여다봐도 거짓 승리 확률이 약속한 5%를 넘지 않습니다. 우위가 뚜렷하면 판정일보다 먼저 결론이 나고, 뚜렷하지 않으면 원래 판정일이 그대로 적용됩니다.":
        "method was added. Fixing the boundary now, before the data accumulates, keeps the false-victory rate under the promised 5% even when looked at daily. If the edge is clear the conclusion arrives before the verdict date; if it is not, the original verdict date applies unchanged.",
      "저장소에서 돌린 실측으로, 하루 평균 0.6%p 우위면 중앙값 32일, 0.35%p면 66일에 판정이 납니다 — 우위가 작으면 이 방법으로도 빨라지지 않습니다. 이 수정을":
        "Measured by running it in the repository: an average edge of 0.6 percentage points a day gives a verdict in a median of 32 days, and 0.35 points in 66 — a small edge is not sped up by this method either. The reason for making this amendment",
      "하는 이유도 같습니다: 지금 고치면 정직한 수정이고, 10월에 고치면 골대 이동입니다. 매일 봐도 거짓 승리가 늘지 않는다는 것은 주장이 아니라, 차이가 없는 데이터 400벌을 만들어 매일 들여다보는 검사로 확인합니다.":
        "is the same: fixing it now is honest, fixing it in October would be moving the goalposts. That daily looking does not increase false victories is not a claim — it is checked by generating 400 sets of no-difference data and peeking at them every day.",
      "등록 후 기준을 바꿔야 할 정당한 이유가 생기면 몰래 고치지 않고 이 자리에 정정을 병기합니다. 등록 원문은 저장소 코드(quant/live/prereg.py)와 status.json에 그대로 실려 있습니다.":
        "If a legitimate reason to change the criteria arises after registration, it is not changed quietly — a correction is published alongside, right here. The registered text itself sits in the repository code and in status.json.",
      "(있지도 않은 파일을 부르고 있었습니다). 하지만 결과는 사소하지 않습니다. 그날의 판단·보유·체결이 전부 정상적으로 기록되고 있었는데":
        "(it was calling a file that does not exist). The consequence was not trivial, though. That day's calls, holdings and fills were all being recorded normally, but",
      "— 이 사이트에서 가장 하면 안 되는 일이 그 둘을 같아 보이게 만드는 것입니다. 더 나쁜 것은":
        "— and making those two look the same is the one thing this site must never do. Worse still was",
      "입니다. 페이지 안에서 오류가 나면 그것을 통째로 삼키는 코드가 있어서, 화면에도 개발자 도구에도 아무 말이 남지 않았습니다. 자동 검사도 매일 초록이었습니다 — 진짜 브라우저로 페이지를 띄워 보는 검사가":
        ". Code inside the page swallowed the error whole, so nothing was left on screen or in the developer tools. The automated checks were green every day too — because the check that opens the page in a real browser",
      "있었기 때문입니다. 2026-08-17에 셋 다 고쳤습니다. ① 파일 이름을 바로잡았고, ② 이제 이 페이지도 실패하면":
        "existed for the first screen alone. All three were fixed on 2026-08-17: ① the file name was corrected; ② this page now, when it fails,",
      "를 실제 브라우저로 띄워 보는 검사를 세웠습니다(스크립트가 던지거나, 없는 파일을 부르거나, 실패 문구가 뜨면 검사가 깨집니다). 같은 자리에서 첫 화면의":
        "is opened in a real browser by a new check (it breaks if a script throws, a missing file is requested, or a failure message appears). At the same spot, the first screen's",
      "2026-08-19, 빠진 사흘을 채워 보려다 그만뒀습니다 — 다시 계산하니 5.24% 더 좋게 나왔기 때문입니다.":
        "2026-08-19 — we tried to fill in the three missing days and stopped, because recomputing came out 5.24% better.",
      "2026-08-16·17·18 사흘은 장부가 비어 있습니다. 운영자가 \"어차피 나왔을 결과이니 채워 넣자\"고 하셨고, 저희도 그렇게 생각했습니다. 그래서":
        "The ledger is empty for 2026-08-16, 17 and 18. The operator said \"the result would have come out anyway, so fill it in\", and we thought so too. So",
      "그날 봉까지만 잘라 같은 계산을 다시 돌리고, 그날 실행 기록에 찍힌 자산과 맞는지 검산하는 장치를 만들어 실제로 돌렸습니다.":
        "we built a device that truncates the bars to that day, reruns the same calculation, and cross-checks it against the equity stamped in that day's run log — and we actually ran it.",
      "그날의 재료가 더는 남아 있지 않기 때문입니다. 코인 시세를 주던 곳이 바뀌어 같은 날 가격이 9~20% 다르게 오고, 한국 지수 ETF는 오늘 18일치만 와서 계산에서 아예 빠졌습니다.":
        "Because the ingredients from that day no longer exist. The source of crypto prices changed, so the same day's prices now arrive 9-20% different, and the Korean index ETF returns only 18 days today and dropped out of the calculation entirely.",
      "그 숫자를 장부에 넣으면 실제로 없었던 5만원이 성적표에 생기고, 그 성적표가 다음 날의 출발점이 됩니다. 그래서 검산 장치가 스스로 멈추고 장부를 원래대로 되돌렸습니다.":
        "Putting that number into the ledger would create KRW 50,000 that never existed on the report card, and that report card becomes the next day's starting point. So the cross-check stopped itself and rolled the ledger back.",
      "자산 숫자만 끼워 넣으면 그날의 보유 종목과 현금이 비어, 다음 날 계산이 어긋나기 때문입니다. \"모른다\"와 \"알지만 장부엔 못 넣었다\"는 다른 말이고, 화면은 후자라고 적습니다.":
        "Slotting in only the equity figure would leave that day's holdings and cash empty, throwing off the next day's calculation. \"We do not know\" and \"we know but could not put it in the ledger\" are different statements, and the screen says the latter.",
      "코인 시세가 165일 멈춰 있어 '판단 기준일'이 08-14로 뒷걸음쳤고, 이미 적힌 날을 한 번 더 적으려다 검사에 막혔습니다. 성적이 나쁜 날이 아니라":
        "Crypto prices had been frozen for 165 days, so the \"as-of\" date walked backwards to 08-14; writing an already-written day a second time was blocked by a check. Not a bad day, but",
      "그날 장부는 2026-08-15에 멈춰 있고, 전략 설정 파일의 마지막 수정도 08-16입니다. 계산은 됐지만 그 뒤 기록을 검사하는 관문이 죽어 저장이 막혔기 때문입니다.":
        "That day's ledger stops at 2026-08-15, and the strategy config file was last modified on 08-16 too. The calculation ran, but the gate that checks the record afterwards died and the save was blocked.",
      "이었습니다. ③에서 죽으면 ②는 이미 나간 뒤입니다. 같은 메시지 아래에 실패 경보가 함께 있었지만":
        ". If it dies at ③, ② has already gone out. A failure alert sat under the same message, but",
      "내보냅니다. 배치는 알림을 보내지 않고 쌓아 두었다가, 저장이 성공한 다음에야 한꺼번에 보냅니다. 검사에서 멈춘 밤은 쌓아 둔 알림이 그대로 버려지고":
        "The batch now holds notifications rather than sending them, and only sends them together once the save succeeds. On a night that stops at the checks, the held notifications are discarded and",
      "— 묵은 시세로 전략을 다시 뽑는 것보다 안 뽑는 쪽이 낫습니다. (다른 종목은 그대로 계속 돕니다.)":
        "— not reselecting a strategy is better than reselecting it on a stale quote. (Other symbols carry on as usual.)",
      "이고 60분을 넘은 것은 3%입니다. 꼬리 하나로 전체를 설명하면 그것도 사실과 다릅니다 — 이제 둘 다 적습니다.":
        "and only 3% exceeded 60 minutes. Explaining the whole by one tail is also untrue — now both are written down.",
      "들어 있습니다 — \"샀다\"(체결)와 \"현금이 6,365,505원 필요한데 677,061원뿐이라 못 샀다\"(현금 부족)가":
        "— \"bought\" (a fill) and \"could not buy: KRW 6,365,505 needed but only 677,061 available\" (insufficient cash), both",
      "가렸습니다(\"확인 필요\"). 그래서 화면에는 여전히 \"아마존 · 매수\"라고 적혀 있었습니다 —":
        "was masked (\"needs checking\"). So the screen still read \"Amazon · buy\" —",
      "— 그날 장부에 무엇이 적혔는지는 그대로 두고, 화면이 같은 기록의 다른 칸을 읽어 무엇이 사실이었는지 고릅니다.":
        "— what was written in the ledger that day stays as it is, and the screen reads another column of the same record to pick out what was actually true.",
      "이었고 그중 열다섯 줄이 \"보유 없음 · 0.00%\"였습니다. 처음 온 사람에게 그것은 정보가 아니라 벽입니다. 지우지 않고":
        "and fifteen of them read \"not held · 0.00%\". To a first-time visitor that is not information but a wall. Without deleting anything,",
      "2026-08-16과 08-17, 이틀 치 기록이 아예 없습니다 — 빈칸의 이유를 적습니다.":
        "2026-08-16 and 08-17 — two days have no record at all. Here is why the blank is there.",
      "은 원인이 다릅니다 — 그날 낮에 저희가 넣은 수정이 배치를 죽였습니다. 자동 검사 하나가 \"웹 브라우저가 없으면 건너뛴다\"고 판단하는 부분에서,":
        "had a different cause — a change we made that afternoon killed the batch. In the part where one automated check decides \"skip if there is no web browser\",",
      "이 됩니다 — 그것은 기록이 아니라 재구성입니다. 그래서 빈칸은 빈칸으로 둡니다. 대신 이 문단이 그 자리를 설명합니다.":
        "— that is a reconstruction, not a record. So a blank stays a blank, and this paragraph explains the spot instead.",
      "는 원칙대로 멈춘 것은 맞지만, 시끄럽게 멈춘 것을 빨리 고치지 못하면 결국 기록이 사라집니다. 08-17분은":
        "did stop as the principle requires, but stopping loudly still loses the record if it is not fixed quickly. The 08-17 case",
      "네 가지 검사를 새로 걸었습니다 — 그중 하나는 \"기록을 쓰기 직전의 검사가 브라우저 같은 무거운 것에 의존하지 않는가\"를 봅니다. 관문이 넓어질수록":
        "Four new checks were added — one of them asks \"does the check just before writing the record depend on anything heavy, like a browser?\" The wider a gate gets,",
      "를 목표로 굴립니다 — 즉 \"1년에 자산이 평균 12%쯤 출렁이는 정도만 위험을 진다\"는 뜻입니다. 100만원을 1억으로 만들려면":
        "as its target — meaning \"take only about as much risk as makes the equity swing 12% in a year\". Turning KRW 1,000,000 into 100,000,000 requires",
      "첫 화면이 절대 손익만 말하고 있었습니다 — 그러면 시장이 오른 날은 실력처럼 보이고 내린 날은 억울해 보입니다. 이제":
        "The first screen was reporting only absolute profit and loss — which makes a rising market look like skill and a falling one look unfair. Now",
      "였다는 뜻이고, 그 머리가 틀리는 국면에서는 스무 종목이 동시에 틀립니다. 원인은 구조가 없어서가 아니라":
        "— and in a regime where that head is wrong, all twenty symbols are wrong at once. The cause was not a missing structure but that",
      "의 2026-08-15 기록에 이런 숫자들이 남아 있었고 화면이 그대로 읽어 주고 있었습니다.":
        "had these numbers in its 2026-08-15 record, and the screen was reading them out as they were.",
      "화면은 \"아마존 매수\"라고 말했고, 같은 화면의 잔고 표에 아마존은 없었습니다. 코인 쪽은 이미 \"주문과 체결은 다르다\"를 구별하고 있었는데":
        "The screen said \"Amazon buy\" while the holdings table on the same screen had no Amazon. The crypto side already distinguished \"an order is not a fill\", but",
      "였습니다 — 비중과 금액이 서로 다른 화폐 단위로 계산되면 비중만 보는 검사는 그냥 통과합니다.":
        "— when weights and amounts are computed in different currency units, a check that looks only at weights simply passes.",
      "같은 열에 비트코인 89,883,874.8(원)과 아마존 264.88(달러)이 나란히 찍혀, 아마존을 264원에 산 것처럼 읽혔습니다. 원인은 2026-08-15 통화 사고(위 항목)의":
        "Bitcoin at 89,883,874.8 (won) and Amazon at 264.88 (dollars) sat side by side in the same column, reading as though Amazon had been bought for 264 won. The cause was the",
      ", 사이트가 그것을 읽고 있었습니다. 2026-08-17에 고쳤습니다. ① 거부되거나 체결되지 않은 주문은 이제 체결로 적지 않습니다(실제 체결 수량만 적습니다), ②":
        ", and the site was reading it. Fixed on 2026-08-17: ① a rejected or unfilled order is no longer recorded as a fill (only the quantity actually filled is recorded); ②",
      "는 산술 검사를 새로 세웠습니다 — 걸리면 기록에 표시가 남고 알림이 갑니다, ③ 화면은 그 숫자를":
        "is a new arithmetic check — when it catches something, a mark stays in the record and an alert goes out; ③ the screen leaves that number",
      "— 지우면 사고가 없었던 것처럼 보입니다. 그 계좌의 자산·현금·수익률은 처음부터 정상이었고, 잘못된 것은":
        "— deleting it would make the incident look as if it never happened. That account's equity, cash and returns were correct from the start; what was wrong was",
      "남기고 있었습니다. 지금은 파는 쪽(공매도)이 잠겨 있어 실제로 틀린 숫자가 나간 적은 없습니다. 하지만 그 문을 여는 날, 화면은":
        "was being recorded. Shorting is locked right now, so no wrong number has actually gone out. But on the day that door opens, the screen would be in a state where",
      "상태가 됩니다 — 그리고 그날 이 줄을 기억하는 사람은 없습니다. 화면·SNS 카드·캡션 네 곳이 각자 \"값이 0보다 크면 들고 있는 것\"이라고 판단하고 있어서, 방향을 살리면 이번에는":
        "— and on that day nobody will remember this line. Four places (the screen, the SNS card and the captions) each decided for themselves that \"a value above zero means it is held\", so reviving the direction brings",
      "문제가 따라옵니다. 그래서 \"들고 있는가\"라는 판단을 한 곳에 모으고 네 화면이 모두 그것만 쓰게 했습니다. 파는 쪽은":
        "as the next problem. So the judgement \"is it held?\" was gathered into one place and all four screens now use only that. The selling side",
      "— 이건 문을 여는 일이 아니라, 열었을 때 화면이 거짓말하지 않게 하는 일입니다. 같은 자리에서":
        "— this is not opening the door but making sure the screen does not lie when it is opened. At the same spot,",
      "2026-08-17, 지난 3년의 위기로 브레이크를 시험했습니다 — 그리고 앞으로 매일 밤 \"내일 아침 시나리오\"를 계산해 공개합니다.":
        "2026-08-17 — the brakes were tested against three years of crises, and from now on a \"tomorrow morning scenario\" is computed and published every night.",
      "수익은 과거로 증명할 수 없습니다(지금의 전략은 과거를 보고 골랐으니, 같은 과거에서의 성적은 실력이 아니라 기억입니다). 하지만":
        "Returns cannot be proven with the past (today's strategy was chosen by looking at the past, so its result on that same past is memory, not skill). But",
      "— \"폭락에서 물러나는가\"는 전략 선택과 무관한 기계적 성질이라, 과거 위기로 시험하는 것이 정당합니다. 그래서 매일 배치가 보존해 온 데이터 스냅샷으로 2023~2026년을":
        "— \"does it back away in a crash?\" is a mechanical property independent of strategy choice, so testing it against past crises is legitimate. Using the data snapshots the daily batch has preserved, 2023-2026 was",
      "다시 지나가 봤습니다(전략 신호 없이, 전 종목을 균등하게 든 바스켓으로 — 위험 장치만을 검증하기 위해서입니다). 결과: 브레이크 없이 들고 있었다면 최대낙폭":
        "walked through again (with no strategy signal, as an equal-weight basket of every symbol — to validate the risk layer alone). Result: holding without brakes gives a max drawdown of",
      "— 실제로 세계 증시가 급락한 바로 그 주입니다. 시나리오가 아니라 달력이 맞다는 뜻입니다. 여기에 더해 매일 밤":
        "— exactly the week world markets fell sharply. That means the calendar agrees, not just the scenario. On top of that, every night",
      "(하룻밤 -10/-20/-30%, 닷새 연쇄 폭락, 단일 종목 -50%, 환율 ±15%, 멈춘 시세 속 하락)를 지금 계좌의 실제 노출로 다시 계산해 첫 화면에 공개합니다.":
        "(overnight -10/-20/-30%, a five-day cascade, a single symbol -50%, ±15% on the exchange rate, a fall behind frozen quotes) are recomputed against the account's actual exposure and published on the first screen.",
      "이며 실측 장부와 다른 파일에 삽니다 — 섞어 읽으면 안 되고, 섞이지 않게 만들었습니다. ② 실현 변동성(16%)이 목표(12%)보다 높았습니다 — 변동성 추정은 폭락을 하루이틀 늦게 따라갑니다. 이 지연은 구조적이며, \"12% 목표\"를 \"12% 보장\"으로 읽으면 안 되는 이유입니다. ③ 재생에 쓴 브레이크는":
        "and lives in a different file from the measured ledger — the two must not be read together, and were built so they cannot be. ② Realised volatility (16%) ran above target (12%) — a volatility estimate follows a crash a day or two late. That lag is structural, and it is why \"a 12% target\" must not be read as \"a 12% guarantee\". ③ The brakes used in the replay are",
      "입니다 — 복사본을 시험하면 복사본만 안전해지기 때문에, 같은 규칙을 두 곳에 적지 않는다는 이 저장소의 원칙이 여기에도 적용됩니다.":
        "— testing a copy makes only the copy safe, so this repository's principle of never writing the same rule twice applies here too.",
      "2026-08-17, 코인 참고 지표 3개가 몇 주 동안 하나도 붙지 않고 있었습니다 — 막힌 문을 매일 두드리고 있었습니다.":
        "2026-08-17 — three crypto reference indicators had not connected once in weeks; we had been knocking on a blocked door every day.",
      "를 함께 봅니다. 코인 쪽에는 그중 세 가지가 있습니다 — 선물 시장에서 한쪽으로 쏠린 사람들이 반대쪽에 내는 수수료(펀딩비), 그 수수료의 변화, 그리고 아직 정리되지 않은 계약이 얼마나 쌓였는지(미결제약정)의 변화입니다. 이 셋이":
        "as well. Three of them are on the crypto side — the fee that a crowded side of the futures market pays to the other (funding), the change in that fee, and the change in how many contracts remain unsettled (open interest). Those three",
      "을 갖고 있고, 실제로 그 두 번째 거래소에서 시세를 받아 왔습니다. 그런데 참고 지표를 받아오는 쪽에는":
        "that steps through exchanges in order when one is blocked, and prices were in fact being fetched from that second exchange. But on the side that fetches the reference indicators,",
      "있었습니다. 시세는 우회하는데 참고 지표만 막힌 문 앞에서 매일 되돌아온 것입니다. 이제 참고 지표도":
        "So prices took the detour while the indicators alone turned back at a blocked door, every day. Now the indicators follow",
      "를 기록에 남깁니다(거래소마다 계산 방식이 조금씩 달라서, 값이 갑자기 튀면 출처가 바뀐 날부터 의심할 수 있어야 합니다). 다 실패한 날에는":
        "is recorded (each exchange computes slightly differently, so when a value jumps you need to be able to suspect the day the source changed). On a day when all of them fail,",
      "가 기록에 남습니다 — 예전에는 \"없음\" 한 마디만 남아서, 다음 사람이 매번 처음부터 조사해야 했습니다.":
        "is left in the record — before, only the word \"none\" was left, so the next person had to investigate from scratch every time.",
      "에서 됩니다. 안 붙으면 이제 그 이유가 기록에 남으므로, 이번에는 원인을 좁힐 수 있습니다.":
        ". If it still does not connect, the reason is now recorded, so this time the cause can be narrowed down.",
      "2026-08-17, 그래서 90일 시계를 0일차로 되돌렸습니다 — 4일을 손해 보는 쪽을 택했습니다.":
        "2026-08-17 — so the 90-day clock was reset to day zero; we chose to lose four days.",
      "판정합니다. 그리고 판단 구조가 바뀌면 그 시계를 0일부터 다시 셉니다 — 구조가 다른 두 구간의 성적을 하나로 합치면 그건 다른 시스템 둘의 평균이지 어느 쪽의 실력도 아니기 때문입니다. 그런데 지금까지 \"구조가 바뀌었다\"의 판정 재료가":
        "And when the decision structure changes, that clock restarts from day zero — merging results from two periods with different structures gives the average of two different systems, and the skill of neither. Until now, though, the material for judging \"the structure changed\" was",
      "— 매일 0일차로 돌아가는 시계는 없는 시계와 같아서, 사흘 연속 달라져야 새 구조로 봅니다. 이 변경으로 시계는":
        "— a clock that returns to day zero every day is the same as no clock, so it counts as a new structure only after three days running. With this change the clock goes",
      "도 지금은 시계를 다시 시작하게 만듭니다. 그래서 앞으로 며칠 안에 한 번 더 0일차로 돌아갈 수 있습니다. 실제로 달라진 것이 없는데도 그렇습니다 — 다만 이 방향의 오차는":
        "will also restart the clock for now. So it may return to day zero once more within a few days, even with nothing actually different — but an error in this direction",
      "2026-08-17, 한국 수급 지표가 왜 안 붙는지 물으면 \"세 가지 중 하나\"라는 답만 돌아왔습니다.":
        "2026-08-17 — asking why the Korean flow indicators would not connect returned only \"one of three things\".",
      "한국 주식에는 외국인·기관이 얼마나 사고팔았는지를 보는 지표가 둘 있는데, 이것도 안 붙고 있습니다. 그런데 기록에 남는 이유가":
        "Korean stocks have two indicators showing how much foreign and institutional investors bought and sold; these were not connecting either. But the reason left in the record was",
      "이었습니다. 셋은 전혀 다른 대응이 필요한 사건이고, 그중 첫 번째는 자동 배치에서는 애초에 답이 아니었는데도 계속 그쪽을 의심하게 만들었습니다. 이제 각 실패가":
        ". The three call for entirely different responses, and the first was never the answer in an automated batch at all, yet it kept drawing suspicion. Now each failure leaves",
      "합니다. 문턱값(-3% 같은 숫자)은 실거래 쪽에 다시 적지 않았습니다 — 같은 규칙을 두 곳에 적으면 언젠가 한 곳만 고쳐지고, 저희는 이번 주에 그 일을 이미 두 번 겪었습니다.":
        ". The threshold values (numbers like -3%) were not rewritten on the live side — writing the same rule in two places means one of them eventually gets fixed alone, and we have already been through that twice this week.",
      "2026-08-16, \"장중 감시를 15분마다 돌립니다\"는 사실이 아니었습니다 — 실제로는 9시간 넘게 벌어진 적이 있습니다.":
        "2026-08-16 — \"the intraday watch runs every 15 minutes\" was not true; the gap once opened to more than nine hours.",
      "이다. 15분마다 돌게 설정해 놓고 그렇게 적기는 쉽지만, 작업이 밀리거나 죽으면 실제 간격은 몇 시간이다.\"":
        ". Setting it to run every 15 minutes and then writing that down is easy, but when a job is delayed or dies the real gap is hours.\"",
      "이 비어 있었습니다. 클라우드의 공용 실행 환경은 촘촘한 예약을 크게 밀거나 아예 건너뜁니다. 즉":
        "was empty. A shared cloud runner pushes a tight schedule far back, or skips it entirely. In other words,",
      "으로 계산하게 만들어 뒀고, 그래서 한도는 안전한 쪽으로 잡힙니다(레버리지는 어차피 잠겨 있습니다).":
        "so the limit lands on the safe side (leverage is locked anyway).",
      "이었습니다. 기록은 매 회차 남고 있었고, 공개 페이지는 계속 15분이라고 말하고 있었습니다.":
        ". The record was being written every round, and the public page kept saying 15 minutes.",
      "예약이 한두 번 밀린 정도로는 울리지 않고, 기록이 충분히 쌓이기 전에는 판정하지 않습니다(세 번 뛴 기록으로 \"9시간!\"이라고 단정하면 이제 막 켠 장치를 고장으로 신고하게 됩니다).":
        "It does not fire for one or two delayed runs, and it makes no judgement before enough record has accumulated (declaring \"nine hours!\" from three heartbeats would report a freshly switched-on device as broken).",
      "2026-08-16, 장부가 \"몇 개를 보고 판단했는지\"를 말하지 않고 있었습니다.":
        "2026-08-16 — the ledger was not saying how many bars the call was based on.",
      "저희 장부는 마지막 시세가":
        "Our ledger records how",
      "얼마나 오래됐는지":
        "old the last quote is",
      "얼마나 만들어진 봉인지":
        "how many bars had formed",

      "가 확정 봉과 달랐고, 종가 차이는 평균 66.8bp (최대 150.8bp), 고저 레인지는 평균 36% 짧게(최대 89%) 잡혔습니다. 같은 기간 주식 28봉은 0건입니다. 결과는 세 가지입니다 — ① 레인지가 짧게 잡히면 변동성 추정이 낮아져 목표보다 큰 비중이 실립니다 ② 백테스트는 완성된 봉으로 평가하는데 실전은 미완성 봉으로 굴리므로 그만큼 조건이 다릅니다 ③":
        "differed from the settled bar; the closing price differed by 66.8 basis points on average (150.8 at most), and the high-low range came out 36% too short on average (89% at most). Over the same period, 28 stock bars showed zero such cases. Three consequences — ① a short range lowers the volatility estimate, so a larger-than-target weight goes on; ② the backtest evaluates on completed bars while live trading runs on incomplete ones, so the conditions differ by that much; ③",
      "— 08-10 스냅샷으로 다시 계산해 보니 코인 5종목의 그날 비중이 평균 0.049, 최대 0.107(BNB 0.111→0.217, 거의 두 배) 달라졌습니다. 방향은 날마다 다르고 예측할 수 없습니다. 변동성 추정만 보면 2.3% 커지지만(비중은 그만큼 작아지는 쪽), 실제로는 모델이 보는 피처가 바뀌는 효과가 더 큽니다. 그래서 이 변경의 근거는":
        "— recomputing from the 08-10 snapshot, that day's weights for the five crypto symbols shifted by 0.049 on average and 0.107 at most (BNB 0.111→0.217, nearly double). The direction varies by day and cannot be predicted. Looking at the volatility estimate alone it grows 2.3% (which shrinks the weight), but in practice the larger effect is that the features the model sees change. So the basis for this change is",
      "썼습니다. 그래서 META를 596.98(달러)에 산 것으로 기록하고 832,868(원)로 평가했습니다. 계좌는 자기가 7,154만원어치를 들고 있다고 믿었습니다. 현실에서는 낼 수 없는 주문입니다 — 같은 날 아마존 주문(24,017주)은 실제로 \"돈이 모자란다\"며 거부됐고, META만 달러 기준 금액이 작아서 통과했을 뿐입니다.":
        "was used. So META was recorded as bought at 596.98 (dollars) and valued at 832,868 (won). The account believed it held KRW 71,540,000 worth. That is an order that could not exist in reality — the same day's Amazon order (24,017 shares) was in fact rejected for \"insufficient funds\", and META passed only because its dollar-denominated amount was small.",
      "— 그날 실제로 그렇게 내보냈고, 아카이브는 '무엇을 내보냈는가'의 기록이지 '무엇을 내보냈어야 했는가'의 기록이 아니기 때문입니다. 덧붙여, 그 아카이브를 나중에 조용히 덮어쓸 수 있던 구멍(재생성 명령이 경고 없이 과거 폴더를 덮어썼습니다)도 같은 날 막았습니다 — 이제 내용이 달라지면 명령이 거부하고 이 문단으로 안내합니다.":
        "— that is what actually went out that day, and an archive is a record of what was sent, not of what should have been sent. In addition, the hole that would have allowed that archive to be quietly overwritten later (a regeneration command overwrote past folders without warning) was closed the same day — the command now refuses when the contents differ and points here.",
      "— 이 저장소가 이번 주 내내 찾아서 고친 바로 그 종류의 결함입니다. 그래서 순서를 뒤집지 않았습니다: ① 강제청산까지 얼마나 여유가 있는지 계산하고 ② 장중에도 감시가 돌게 하고 ③ \"평균은 좋은데 도중에 죽는\" 경우를 재는 검사를 붙인 다음에야 ④ 셋을 다 통과할 때만 열리는 관문을 뒀습니다. 기본값은 잠김이고,":
        "— exactly the kind of defect this repository spent the week finding and fixing. So the order was not reversed: ① compute how much room there is before forced liquidation, ② make the watchdog run intraday too, ③ attach a check that measures the \"good average but dies along the way\" case — and only then ④ put in a gate that opens only when all three pass. The default is locked, and",
      "일관됐기 때문에 오래 드러나지 않았습니다. 숫자가 서로 맞는다는 것과 사실이라는 것은 다릅니다. 이제 체결·평가 가격을 원/달러로 환산하므로 환율 변동이 매일의 재평가를 통해 자산에 반영됩니다(신호는 현지 통화 그대로라 전략 동작은 그대로입니다). 환율을 확인하지 못한 날에는 해외 종목을":
        "was internally consistent, so it stayed hidden for a long time. Numbers agreeing with each other is not the same as their being true. Fill and valuation prices are now converted at the USD/KRW rate, so currency moves reach the equity through the daily revaluation (signals stay in local currency, so strategy behaviour is unchanged). On a day when the rate cannot be confirmed, overseas symbols are",
      "평소에는 맞기 때문에 아무도 의심하지 않는, 가장 잡기 어려운 종류입니다. 이제 설명 문구를 장부에서 읽어 그날의 실제 방식을 적고, 폴백이 일어난 날은 첫 화면의 '지금 켜진 경고'에도 표시합니다. (지금까지 기록된 날은 모두 HRP였습니다 — 폴백으로 잘못 나간 날은 없었습니다.)":
        "the hardest kind to catch, because it is right most of the time and nobody suspects it. The description is now read from the ledger and states the method actually used that day, and a day that fell back is also shown under \"warnings currently lit\" on the first screen. (Every day recorded so far used HRP — no day went out wrongly on a fallback.)",
      "고장난 계측기와 보이지 않는 계측기가 서로를 가려 주고 있었고, 표시하기로 결정하자마자 고장이 드러났습니다. 검사 픽스처까지 같은 유령 이름을 적어 두어 검사도 초록이었습니다. 같은 날 이름을 바로잡고, 목록의 이름이 실제로 만들어지는지 매번 확인하는 검사를 넣었습니다.":
        "A broken instrument and an invisible instrument were covering for each other, and the breakage surfaced the moment we decided to display it. Even the test fixture carried the same ghost name, so the tests were green too. The name was corrected the same day, and a check was added that verifies every time that the names in the list are actually produced.",
      "는 -0.05%였습니다. 지금은 차이가 0.01%p라 눈에 띄지 않지만, 누적이 +40%가 되면 매일 \"오늘 +40%\"를 방송하게 되는 구조였습니다 — 정직성이 유일한 자산인 채널에서 가장 치명적인 종류의 오류라 그대로 적습니다. 같은 날 고쳐, 이제 캡션은":
        "was -0.05%. The gap is 0.01 percentage points today and goes unnoticed, but the structure was one that, once the cumulative figure reached +40%, would broadcast \"+40% today\" every single day — the most fatal kind of error on a channel whose only asset is honesty, so it is written here as it is. Fixed the same day; the caption now",
      "— 그건 일어나지 않은 거래를 지어내는 일입니다. 되돌리기 전 숫자와 지운 체결 내용은 기록 안에 그대로 남겨 뒀고, 첫 화면에도 \"이 날의 기록은 나중에 되돌렸습니다\"라고 띄웁니다. 다시 일어나지 않게 두 가지를 했습니다. 바꾸는 일을":
        "— that would be inventing trades that never happened. The numbers before the rollback and the deleted fill contents were left inside the record, and the first screen shows \"this day's record was rolled back later\". Two things were done so it cannot recur. The act of changing",
      "만들면서 저희 계산이 틀린 것을 두 번 잡았습니다 — 특히 \"자주 보면 안전하다\"는 답이 나왔을 때가 그랬습니다. 가격은 눈을 깜빡이는 사이에 통째로 뛰기 때문에 (급락·개장 갭·거래소 장애) 자주 보는 것으로는 그걸 못 피합니다.":
        "caught our own arithmetic being wrong twice while it was being built — especially when the answer came out as \"looking more often is safer\". Prices jump wholesale in the blink of an eye (a crash, an opening gap, an exchange outage), and looking more often does not avoid that.",
      "주식은 장 마감 전의 '오늘' 봉을 버리는 장치가 있지만, 코인은 24시간 시장이라 UTC 일봉의 '오늘' 봉이 항상 진행 중이고 그 장치가 없었습니다. 저장된 스냅샷으로 직접 쟀습니다(2026-08-07~09, 코인 5종목):":
        "Stocks have a device that discards \"today's\" bar before the close, but crypto is a 24-hour market where the UTC daily bar for \"today\" is always in progress — and that device was missing. We measured it directly from stored snapshots (2026-08-07 to 09, five crypto symbols):",
      "(어느 종목에 얼마를 배정할지)이라 모델이 관망한 종목에도 붙어 있는데, 카드가 그 값을 그대로 '매수 비중'이라 불렀습니다. 같은 카드의 다른 종목들도 예산(애플 15.0%)을 매수 비중처럼 보이게 적었고, 같은 게시물 캡션은":
        "(how much to allocate to which symbol), so it is attached even to symbols the model stood aside on — and the card called that value a \"buy weight\" outright. Other symbols on the same card presented the budget (Apple 15.0%) as if it were a buy weight too, and the caption on the same post",
      "였던 \"현금이 모자라 주문이 거부됨\"은 새벽 5시 30분에 이미 장부에 남아 있었지만, 화면에만 표시되고 알림으로는 나가지 않았습니다. 화면은 열어야 보입니다. 이제 이런 \"나오면 안 되는 값\"은 알림으로 곧장 나갑니다.":
        "— \"the order was rejected for lack of cash\" — was already in the ledger at 05:30, but it appeared only on screen and never went out as a notification. A screen has to be opened to be seen. Now a \"value that should not appear\" like this goes straight out as an alert.",
      "과거를 손대지 않는 것이 이 실험의 전제이고, 불편한 날을 지우기 시작하면 좋은 날의 숫자도 믿을 수 없게 됩니다. 대신 같은 일이 다시 일어나지 않게 두 겹으로 막았습니다 — 예비 배치를 자정에서 90분 떼어 놓았고,":
        "Not touching the past is this experiment's premise, and once you start deleting inconvenient days the good days' numbers cannot be trusted either. Instead it was blocked twice over so the same thing cannot recur — the backup batch was moved 90 minutes away from midnight, and",
      "두고 있었습니다(직전 주 기록이 없으면 빈칸) — 20종목 중 13종목이 그랬습니다. 같은 셈이 두 벌이었던 것이 원인입니다. 텔레그램 주간 리포트 쪽은 2026-08-14에 고쳤는데(그때도 부호가 반대였습니다),":
        "was left blank when there was no prior-week record — 13 of 20 symbols. The cause was that the same calculation existed in two copies. The Telegram weekly report side was fixed on 2026-08-14 (the sign was reversed there too), but",
      "매일 새벽 배치가 남기는 커밋에는 \"검사를 건너뛰라\"는 표식이 붙어 있기 때문입니다(장중 감시가 15분마다 돌아 하루 96번 전체 검사를 돌릴 수는 없어서 붙인 것이라, 표식 자체는 이유가 있습니다). 결과적으로":
        "because the commits the morning batch leaves carry a \"skip the checks\" marker (added because the intraday watch runs every 15 minutes and the full suite cannot run 96 times a day, so the marker itself has a reason). As a result,",
      "8종목은 통계적으로 분산이 부족해 운의 비중이 컸기 때문입니다. '8마일'은 시작 금액(8만원) 컨셉으로 유지하며, 통합 계좌의 자산·기록은 그대로 이어집니다(리셋 아님). 같은 날부터 자본 균등(1/n) 대신":
        "because eight symbols is statistically too little diversification and luck carried too much weight. The \"8 Mile\" name is kept as the starting-amount concept (KRW 80,000), and the combined account's equity and record carry on unchanged (not a reset). From the same day, instead of equal capital (1/n),",
      "\"우리는 검증한 것만 씁니다\"가 거짓말이 되기 때문입니다. 그리고 후보가 늘어난 만큼 승격 문턱도 같이 올렸습니다 — 많이 던져서 하나 맞히는 것을 실력으로 세면 안 되니까요. 이 기능에서 가장 중요한 동작은":
        "because otherwise \"we only use what we validated\" becomes a lie. And the promotion bar was raised in step with the growing candidate pool — throwing a lot and hitting one must not count as skill. The most important behaviour in this feature is",
      "사장님이 \"수수료도 계산한 거 맞지?\"라고 물으셨을 때 답할 자리가 화면에 없었던 것입니다. 이제 '한눈에'가 누적 비용과 그날 낸 비용을 함께 적습니다. 이 칸이 생기기 전의 금액은 체결 기록을 되짚어 채운":
        "was that when the owner asked \"the fees are counted too, right?\", the screen had nowhere to answer. \"At a glance\" now carries both the cumulative cost and the cost paid that day. Amounts from before this box existed were filled in by walking back through the fill records,",
      "이며(그 되짚기는 같은 날 기록이 스스로 \"못 샀다\"고 적어 둔 체결은 세지 않습니다 — 2026-08-15에 현금 부족으로 거부된 주문이 체결처럼 남아 있습니다), 이후로는 돈을 뺄 때마다 실제로 셉니다.":
        "(that walk-back does not count fills the same day's record itself marked \"could not buy\" — the order rejected for lack of cash on 2026-08-15 is still sitting there looking like a fill), and from then on it is counted for real each time money leaves.",
      "— 장부는 이미 100만원인데 그 상수만 뒤처져 있어서, 계좌를 새로 만드는 경로가 돌면 8만원짜리 계좌가 생길 자리였습니다(선언과 실제가 어긋난 자리였고, 이 저장소가 가장 경계하는 종류입니다).":
        "— the ledger already said KRW 1,000,000 while that constant lagged behind, so any path that created a new account would have created an 80,000-won one (a place where the declaration and the reality diverged, the kind this repository guards against most).",
      "이 됐습니다(2026-08-13). '8마일'이 가리키던 여덟도 만원도 남지 않은 셈이라, 이름만 남으면 처음 오신 분이 계좌를 8만원짜리로 읽게 됩니다. 이름은 설명이어야지 장식이면 안 됩니다.":
        "(2026-08-13). Neither the eight nor the ten-thousand that \"8 Mile\" referred to remains, so keeping only the name would have a first-time visitor read the account as an 80,000-won one. A name must be a description, not an ornament.",
      "냅니다(그냥 보유는 사고 나면 팔지 않고, 우리도 아직 들고 있는 몫은 파는 값을 안 냈으므로 진입 비용만 맞추면 눈금이 같아집니다). 비율은 그날 바구니에 담긴 종목들이 속한 시장의 평균이며,":
        "(buy & hold never sells after buying, and we have not paid the selling cost on what we still hold either, so matching only the entry cost puts both on the same scale). The rate is the average across the markets of the symbols in that day's basket, and",
      "(운영 일수만큼). 차이가 작지 않습니다 — SK하이닉스 60.5% → 실전 33%(3번 중 1번), S&P500 ETF 50.0% → 실전 25%(4번 중 1번). 표본이 이렇게 작을 때는":
        "(as many as the days of operation). The difference is not small — SK hynix 60.5% → 33% live (1 of 3), S&P 500 ETF 50.0% → 25% live (1 of 4). With a sample this small,",
      "— \"과거를 고치지 않는다\"가 먼저이기 때문입니다. 대신 읽는 쪽에서 날짜순으로 정렬해 계산하도록 바꿨고, 새 기록은 시간순 자리에 삽입됩니다. 어긋난 배열은 장부에 증거로 그대로 남습니다.":
        "— because \"do not edit the past\" comes first. Instead the reading side now sorts by date before computing, and new records are inserted in chronological position. The out-of-order arrangement stays in the ledger as evidence.",
      ". 그리고 되돌려진 날의 글은 관리 화면에서 \"올리지 마세요\"가 숫자보다 먼저 뜹니다 — 정정문을 폴더에만 두면 폴더를 여는 사람만 보고, 정작 글을 복사하는 사람은 못 보기 때문입니다.":
        ". And for a rolled-back day, the admin screen shows \"do not post this\" ahead of the numbers — leaving the correction only in a folder means only whoever opens the folder sees it, and not the person copying the text.",
      "됩니다 — 브레이크가 가장 필요한 국면에서 한 단계 덜 걸리는 구조였습니다. 지금은 원금을 고점 후보에 넣어 잽니다. 이익이 난 계좌의 낙폭 계산은 그대로입니다(그쪽은 원래 맞았습니다).":
        "— a structure that applied one step less braking exactly when braking was needed most. The principal is now included as a high-water candidate. Drawdown for an account in profit is unchanged (that side was correct all along).",
      "더하고 있었습니다(S&P500 ETF 772). 그래서 장부에 \"S&P500 ETF 12.25주 = 9,466원\"이라는 줄이 남았습니다 — 실제로 그 12주는 1,300만원어치입니다.":
        "was being added in (S&P 500 ETF at 772). So the ledger holds the line \"S&P 500 ETF 12.25 shares = KRW 9,466\" — those 12 shares are actually worth about 13 million won.",
      "가 있습니다. 뒤쪽은 \"이 종목만 굴렸다면?\"을 재는 참고 장부인데, 페이퍼 페이지의 표가 그 숫자를 아무 설명 없이 '종목별 현황'으로 보여줬습니다. 그래서 8만원짜리 실험 페이지에":
        "The latter is a reference ledger measuring \"what if only this symbol were traded?\", but the table on the paper page presented those numbers as \"status by symbol\" with no explanation. So on an 80,000-won experiment page,",
      "씩, 합쳐 8만원으로 시작한다는 뜻이었고 영화 '8 Mile'에서 따왔습니다. 그런데 그 뒤로 후보가 20종목이 됐고(2026-08-05), 원금은 매칭 입금과 원화 재개설을 거쳐":
        "each, KRW 80,000 in total to start — the name came from the film \"8 Mile\". Since then the candidate pool grew to 20 symbols (2026-08-05), and the principal, after matching deposits and the won-denominated reopening, became",
      "가격만 달러였던 것이 아니라 그 가격으로 판 돈이 현금에 섞여 있어, 환율을 소급해 곱하는 것은 환산이 아니라 과거를 지어내는 일이기 때문입니다. 옛 장부는 한 글자도 고치지 않고":
        "because it was not only the prices that were in dollars — the proceeds of sales at those prices were mixed into the cash, so multiplying by a rate retroactively would not be conversion but inventing a past. The old ledger was not edited by a single character and",
      "에 그대로 남아 있습니다. 정식 방송 시작 전의 컨셉 변경이며, 이런 변경 자체도 공개 커밋으로만 가능합니다 — 조용히 새로 시작해 좋은 구간만 보여주는 것이 불가능한 구조입니다.":
        "remains exactly as it was. It was a change of concept before the official broadcast began, and even a change like this is possible only through a public commit — the structure makes it impossible to restart quietly and show only the good stretches.",
      "→ 08-10 순으로 배열돼 있었습니다. 데이터 소스가 한때 아직 닫히지도 않은 08-07 봉을 먼저 내보낸 탓이며, 그 원인(미완결 봉 제거)은 이미 고쳐진 상태입니다. 각 날의":
        "→ 08-10. The cause was that the data source once emitted the 08-07 bar first, before it had even closed; that cause (removing incomplete bars) is already fixed. Each day's",
      "이름도 '매수'가 아니라 '배분'으로 적습니다. 캡션의 \"오늘 배분 상위\"는 확인 결과 8월 10일·9일 모두 실제로 보유한 종목만 불렀습니다 — 잘못 나간 것은 카드 쪽입니다.":
        "and the label reads \"allocation\", not \"buy\". On checking, the caption's \"top allocations today\" named only genuinely held symbols on both 10 and 9 August — what went out wrong was the card.",
      "그래서 손실이 커지면 물러나는 장치(킬스위치)가 하루에 한 번만 돌아도 됐습니다 — 최악이어도 다음 날 아침에 처리하면 되니까요. 레버리지는 그 전제를 깹니다. 거래소는":
        "So the device that backs away as losses grow (the kill switch) only had to run once a day — the worst case could be handled the next morning. Leverage breaks that premise. An exchange",
      "(사이트에 표시되는, 아무렇게나 매매했을 때와 비교한 순위)입니다. 초반 구간이 다른 시장 국면이었다면 그 기간의 사실만 빠진 채 판정이 났습니다. 이제 잘라내지 않고":
        "(the ranking shown on the site, against trading at random). Had the early period been a different market regime, a verdict would have been reached with only that period's facts missing. Now, rather than cutting it away,",
      "거래정지·상하한가·저유동 국내주식은 보합이 잦고 코인은 거의 없어서, 같은 실력이어도 종목에 따라 적중률이 다르게 나왔습니다. 이제 방향이 없던 날은 분모에서 빼되,":
        "Suspended, limit-up/limit-down and thinly traded Korean stocks go flat often while crypto almost never does, so the same skill produced different hit rates by symbol. Days with no direction are now removed from the denominator, but",
      "그 화면에 편향된 숫자를 아무 표시 없이 매일 띄우는 것은 그 주장 자체를 무너뜨립니다. 이제 두 숫자를 나란히 보여줍니다 — 위는 과거 400봉(인샘플), 아래는":
        "putting a biased number on that screen every day with no label destroys the claim itself. Two numbers are now shown side by side — above, the past 400 bars (in-sample); below,",
      "입니다 — 15분마다 돌게 설정해 놓고 그렇게 적기는 쉽지만, 작업이 밀리거나 죽으면 실제 간격은 몇 시간입니다. 그래서 매 회차를 기록으로 남기고, 위험 한도는":
        "— setting it to run every 15 minutes and writing that down is easy, but when a job is delayed or dies the real gap is hours. So every round is recorded, and the risk limit is",
      "(하룻밤에 5배가 뛰는 가격은 시장이 아니라 코드가 만든 숫자입니다). 막힌 사실도 화면에 뜹니다. 이 결함은 2026-08-13에 고쳤다고 적었던 그 결함의":
        "(a price that jumps fivefold overnight is a number made by code, not by a market). The fact that it was blocked also appears on screen. This defect is the",
      "대가는 정직하게 적습니다: 마지막 몇 시간의 가격 움직임을 신호가 보지 못합니다. 그래도 '선발되는 조건'과 '실제로 굴리는 조건'을 맞추는 쪽을 택했습니다.":
        "The cost is stated honestly: the signal does not see the last few hours of price movement. Even so, we chose to match \"the conditions under which it is selected\" to \"the conditions under which it actually runs\".",
      "이전 기록은 새벽 판단을 그 시점 종가로 즉시 체결한 것처럼 계산했는데, 주식 시장이 닫힌 시간이라 실제로는 불가능한 가격입니다. v0.5.0부터는 주식을":
        "Earlier records treated a morning call as filled immediately at that moment's close — a price that is impossible in reality, because the stock market is shut at that hour. From v0.5.0, stocks are",
      "손댄 날의 성적은 전략만의 결과가 아닌데, 읽는 사람은 알 방법이 없었습니다. 이제 개입이 있으면 사이트의 '지금 켜진 경고', 카드, 캡션 세 곳 모두에":
        "A day that was touched by hand is not the strategy's result alone, and the reader had no way of knowing. Now, when there is an intervention, all three places — the site's \"warnings currently lit\", the card and the caption —",
      "— 계좌보다 큰 금액을 막는 장치는 이미 있었지만 전부 홈페이지 쪽이었고, 홈페이지 밖으로 나가 낯선 사람에게 닿는 유일한 통로에는 없었습니다. 이제":
        "— devices blocking amounts larger than the account already existed, but all of them were on the website side, and none on the only channel that leaves the site and reaches a stranger. Now",
      "고친 것이 언젠가 다시 풀리거나, 다른 데이터 제공처에서 같은 일이 생겨도 이제는 그날 바로 보입니다. 정상인 날에는 아무 말도 하지 않습니다.":
        "If the fix ever comes undone, or the same thing happens at another data provider, it is now visible the same day. On a normal day it says nothing.",
      "2026-08-15, 레버리지(빌린 돈으로 더 큰 금액을 굴리는 것)를 열기 전에 관문 세 개를 먼저 세웠습니다 — 문은 아직 잠겨 있습니다.":
        "2026-08-15 — before opening leverage (running a larger amount with borrowed money), three gates were built first. The door is still locked.",
      "예비 배치가 실행 지연으로 밤 11시 58분에 시작해 도중에 세계표준시 자정을 넘겼습니다. 코인의 하루 봉은 그 자정에 날짜가 바뀌기 때문에,":
        "The backup batch started at 23:58 because of an execution delay and crossed UTC midnight partway through. Because a crypto daily bar changes date at that midnight,",
      "전체 검사가 아니라 장부를 보는 것만 돌리므로 1초도 걸리지 않습니다 — 비용 때문에 못 한다는 말은 이제 성립하지 않습니다. 검사에 걸리면":
        "it runs only the ledger check rather than the full suite, so it takes less than a second — \"we cannot afford it\" no longer holds. When the check catches something,",
      "보다 큰, 성립할 수 없는 숫자입니다(사이트에 표시되는 값은 아니지만 공개 장부에 그대로 남아 있었습니다). 같은 날 바로잡았고, 이제":
        "— a number larger than that, which cannot hold (not a value shown on the site, but it was sitting in the public ledger). Corrected the same day, and now",
      "입니다. 나빠 보이는 쪽만 문제가 아닙니다 — \"70% 이상 → 실제 상승 64%\"(구간 39~84%)도 증거처럼 읽힙니다. 사이트보다":
        ". The unflattering side is not the only problem — \"70% or more → 64% actually rose\" (interval 39-84%) also reads like evidence. Ahead of the site,",

      "(시작 + 120일) · 본페로니 3 · 이겨도 최대낙폭이 현행의 1.5배를 넘으면 채택 보류. 이 축은 오디션이 184회 동안 한 번도 흔들지 않았습니다 — 다만 실측 확률에서 현행은 켈리 절반과 거의 같아(0.087 vs 0.089)":
        "(start + 120 days) · Bonferroni 3 · even on a win, adoption is withheld if the max drawdown exceeds 1.5× the current one. This axis went unmoved through 184 auditions — though at the measured probabilities the current setting is almost identical to half-Kelly (0.087 vs 0.089),",
      "— 그중 70%는 후보들을 겨루게 한 선발전 구간입니다. 챔피언은 그 데이터에서 이겼기 때문에 뽑혔으니, 같은 데이터로 성적을 매기면":
        "— 70% of which is the qualifying stretch where the candidates competed. The champion was selected because it won on that data, so scoring it on the same data",
      "라 찍고, 첫 장의 문구까지 그 값으로 골랐습니다(누적이 커지면 크게 잃은 날에도 \"좋은 날\" 문구가 붙는 구조입니다). 이제 카드는":
        "and even the wording on the first slide was chosen from that value (a structure in which, once the cumulative figure grows, a \"good day\" phrase attaches even to a day of large losses). The card now",
      "2026-08-15 기록에 100만원 계좌의 자산이 7,249만원(+7,150%)으로 찍혔습니다 — 불가능한 체결이라 되돌렸습니다.":
        "In the 2026-08-15 record, a KRW 1,000,000 account showed equity of 72,490,000 (+7,150%) — an impossible fill, so it was rolled back.",
      "2026-08-14, 내 자료(PDF·유튜브·트레이딩뷰)로 전략을 넣을 수 있게 했습니다 — 다만 '적용'이 아니라 '심사'입니다.":
        "2026-08-14 — you can now feed in a strategy from your own material (a PDF, a YouTube video, a TradingView script). But it is submitted for audition, not applied.",
      "으로 계산하는데, 그 '가격'이 시장마다 다른 통화였습니다: 한국 주식은 진짜 원화 (삼성전자 239,500), 미국 주식과 코인은":
        "but that \"price\" was in a different currency per market: Korean stocks in real won (Samsung Electronics 239,500), while US stocks and crypto",
      "입니다 — 신호·피처·공분산은 확정된 봉까지만 보고, 체결가와 평가액은 현재가를 씁니다. 실제 트레이더가 하는 것과 같고, 무엇보다":
        "— signals, features and covariances look only as far as settled bars, while fill prices and valuations use the current price. It is what a real trader does, and above all",
      "을 열어 아무 날짜나 골라 보세요. 그날의 자산·수익률이 사이트 표시와 일치하는지, 커밋 시각이 매일 새벽인지 확인할 수 있습니다.":
        "and pick any date. You can check that the equity and return for that day match what the site shows, and that the commit time is each morning.",
      "셈입니다. 같은 날 고쳐, 카드도 구간을 함께 찍고 표본 30일 미만이면 \"아직 수집 중\"이라고 먼저 밝힙니다. 이미 나간 카드는":
        "Fixed the same day: the card now stamps the interval as well, and with a sample under 30 days it says \"still collecting\" first. Cards already published",
      "를 받고, 과최적화 검증까지 통과해야 실제 비중을 받습니다. 대부분은 떨어집니다. 그렇게 한 이유는, 검증이 이 제품의 전부인데":
        "and must also pass the overfitting validation before receiving any real weight. Most are rejected. The reason is that validation is the whole of this product, and",
      "이고, 거기 미래 날짜가 박혀 있으면 \"언제 것인지\"를 확인하려는 분이 처음부터 어긋난 자료를 보게 됩니다. 이제 표시용 카드는":
        "and a future date stamped on it means anyone checking \"when is this from?\" sees mismatched material from the start. The display card now",
      "이지만 배열 순서가 뒤집혀 있어, '직전 날'을 참조하는 계산(하루치 수익률·낙폭)이 엉뚱한 날을 전날로 잡을 수 있었습니다.":
        "but the ordering was reversed, so calculations referring to \"the previous day\" (daily return, drawdown) could take the wrong day as yesterday.",
      "— 기준선이 낮아져 우리가 더 앞서 보입니다. 그래서 숨기지 않고 여기 적습니다. 실측(2026-08-19 기준): 그냥 보유":
        "— the baseline drops, which makes us look further ahead. So it is not hidden but written here. Measured as of 2026-08-19: buy & hold",
      "이었으나, 운영자 지시로 조기 착수했습니다 — 문턱을 낮춘 것이 아니라 문턱과 무관하게 \"재 보라\"는 결정이 있었던 것입니다.":
        "but work began early on the operator's instruction — the bar was not lowered; there was simply a decision to \"go measure it\" regardless of the bar.",
      "(총노출 상한 100%). 그런데 \"나중에 열 수도 있다\"는 이야기가 나오는 순간, 먼저 확인해야 할 것이 있었습니다.":
        "(gross exposure capped at 100%). But the moment \"we might open it later\" was said, something had to be checked first.",
      "지금까지는 손실 감시가 새벽 배치에서 하루 한 번만 돌았습니다. 이제 장중에도 자산을 다시 재고, 정해둔 선을 넘으면":
        "Until now the loss watch ran only once a day, in the morning batch. Equity is now remeasured intraday too, and when it crosses the set line",
      "— 다음 배치부터 새 계산으로 적힙니다. 그전 기록에 적힌 낙폭은 실제보다 얕을 수 있고, 그 사실을 여기 남깁니다.":
        "— from the next batch onward it is written with the new calculation. Drawdowns in earlier records may be shallower than reality, and that fact is left here.",
      "— 원화가 절상되면 실제로는 손실인데 장부에는 그 손실이 존재하지 않았습니다. 수익률은 모든 계산이 같은 왜곡을 겪어":
        "— when the won appreciates it is a real loss, yet that loss did not exist in the ledger. The return figures, every calculation suffering the same distortion,",
      "장부에는 매일 \"정상\"이라고 적혔습니다. 그 사이에 그 코인들의 성적도, \"이 성과가 착각인가\"를 재는 수치도 전부":
        "the ledger recorded \"normal\" every day. Meanwhile both those coins' results and the figures measuring \"is this result an illusion?\" were all",
      "— \"과거를 고치지 않는다\"는 약속이 회계 기준 개선보다 우선하기 때문입니다. 대신 모든 새 기록에는 기준 태그 (":
        "— because the promise \"do not edit the past\" comes before improving an accounting convention. Instead every new record carries a basis tag (",
      "숫자는 전부 맞았지만, 무엇의 숫자인지 알 수 없으면 틀린 숫자와 같은 효과를 냅니다. 이제 표 제목과 열 이름이":
        "Every number was correct, but a number whose subject is unknown has the same effect as a wrong one. The table titles and column names now",
      "이 됐습니다. 예를 들어 100만원으로 시작해 90만 → 72만원이 된 계좌는 실제로 28%를 잃었는데 장부에는":
        "For example, an account that started at KRW 1,000,000 and went 900,000 → 720,000 actually lost 28%, but the ledger recorded",
      "의 지난 캡션들은 그때 쓴 그대로입니다. 과거를 고치지 않는 것이 이름을 맞추는 것보다 먼저입니다. 같은 날":
        "past captions stay exactly as they were written then. Not editing the past comes before making a name consistent. The same day,",
      "모델의 보조 지표가 외부 데이터 실패로 조용히 사라지는 것을 잡으려고 만든 장치인데, 목록에 적힌 11개 중":
        "It was built to catch the model's auxiliary indicators quietly disappearing when an external feed fails — and of the 11 on the list,",
      "(인샘플). 화면에는 \"적중률(전체)\"이라고만 적혀 있어 읽는 사람은 이 실험의 실전 성적으로 읽었습니다.":
        "(in-sample). The screen said only \"hit rate (overall)\", so readers took it as this experiment's live result.",
      "2026-08-05, v0.5.0부터 회계 기준을 보수적으로 변경했습니다 — 이전 숫자는 낙관적이었습니다.":
        "2026-08-05 — from v0.5.0 the accounting convention became more conservative; the earlier numbers were optimistic.",
      "라고 말합니다 — 한 종목이 전체 노출보다 크다는, 성립할 수 없는 조합이었습니다. 같은 날 고쳐, 장부가":
        "— a combination that cannot hold, with one symbol larger than the total exposure. Fixed the same day, so the ledger",
      "만 바꾼 가상 계좌 넷(현행·켈리·켈리 절반·전량). 진입 조건은 넷이 같아 크기 축만 격리됩니다. 판정일":
        "Four play-money accounts differing only in that (current, Kelly, half-Kelly, full). Entry conditions are identical across the four, isolating the sizing axis alone. Verdict date",
      "이었습니다. 같은 규칙을 두 곳에 나눠 적으면 언젠가 한 곳이 빠진다는 것을, 저희가 또 확인했습니다.":
        "Once again we confirmed that splitting the same rule across two places eventually leaves one of them behind.",
      "2026-08-13, 통합 계좌를 원화 계좌로 다시 열었습니다 — 그전 계좌는 통화가 섞여 있었습니다.":
        "2026-08-13 — the combined account was reopened as a won account; the previous one mixed currencies.",
      "· 트랙 2개(짝지어 비교). 정직 사항: 원래 착수 문턱은 두 비중의 거리 0.2였고 실측 첫 값은":
        "· two tracks (compared pairwise). For honesty: the original trigger was a distance of 0.2 between the two weightings, and the first measured value was",
      "2026-08-14, 첫 화면의 '적중률'이 어떤 숫자인지 밝히고 실전 적중률을 나란히 올렸습니다.":
        "2026-08-14 — the first screen now says what its \"hit rate\" actually is, with the live hit rate published beside it.",
      "이 시스템은 낙폭이 커지면 스스로 투자 비중을 줄입니다(킬스위치). 위 예에서 진짜 낙폭 28%라면":
        "This system reduces its own position size as the drawdown grows (the kill switch). In the example above, a true drawdown of 28% would",
      "이라, 남기면 오염이 이어집니다. 기록이 멈추면 별도의 감시 장치가 다음 날 아침에 잡아냅니다 —":
        "so leaving it in would carry the contamination forward. When the record stops, a separate watchdog catches it the next morning —",
      "로 남아 있습니다(정상인 날은 전부 0입니다). 코인 매매는 그 시점 현재가로 정상 체결됐습니다.":
        "(every normal day is zero). Crypto trades filled normally at that moment's price.",
      "입니다. 상관 추정에 쓸 데이터가 모자란 날에는 조용히 아래 칸으로 내려갑니다. 장부는 그 흔적을":
        "On a day with too little data to estimate correlations, it quietly steps down a level. The ledger keeps that trace",
      "— \"하루에 자산이 50% 넘게 변하면 사고를 의심한다\"는 검사가 오래전부터 있었습니다. 그런데":
        "— a check saying \"suspect an incident if equity moves more than 50% in a day\" had existed for a long time. But",
      "입니다. 투자 자료 대부분이 그렇고, 거기서 억지로 규칙을 짜내면 그건 그 자료의 전략이 아니라":
        "Most investment material is like that, and forcing a rule out of it produces not that material's strategy but",
      "— 두 화면이 다른 값을 말할 수 없는 구조로 바꿨습니다. 기준선은 직전 주의 마지막 자산이며,":
        "— restructured so the two screens cannot say different things. The baseline is the previous week's last equity, and",
      ", 합이 총노출과 같습니다)을 남기고 카드·캡션은 그 숫자만 씁니다. 그 값이 없는 과거 기록은":
        ", summing to the gross exposure), and the card and caption use only that number. Past records without that value",
      "이 그대로 보였습니다. 운영자 본인이 \"8만원인데 왜 20만원이지?\"라고 물어서 발견했습니다 —":
        "was showing as it was. It was found because the operator himself asked \"it is 80,000 won, so why does it say 200,000?\" —",
      "그날 그 값으로 계산해 내보냈고, 그것이 그날의 사실입니다. 다만 이 날 이전과 이후의 적중률은":
        "It was computed and published with that value that day, and that is the fact of that day. The hit rates before and after this day, however,",
      ". 룩어헤드(미래를 미리 본 것처럼 계산하는 오염)를 막는 장치이고, 거기서는 옳습니다. 그런데":
        ". It is a device against look-ahead (contamination that computes as if the future had been seen), and there it is right. But",
      "2026-08-14, 낙폭을 원금 대비로 다시 재기 시작했습니다 — 그전에는 얕게 나왔습니다.":
        "2026-08-14 — drawdown is measured against the principal again; before, it came out shallow.",
      "코드로도 막았습니다. 시각만으로 막으면 실행 지연이 길어지는 날 언젠가 또 넘기기 때문입니다.":
        "It was blocked in code as well. Blocking by clock time alone would eventually cross again on a day with a long delay.",
      "하나뿐입니다. 판단에서 뺐다고 사실을 숨기지는 않으므로, 그 봉이 몇 % 만들어진 상태였는지(":
        "is the only one. Excluding it from the decision does not mean hiding the fact, so how far that bar had formed (",
      "적고 하루치는 입금 효과를 제거해 계산합니다(입금한 날 \"+100%\"가 나가는 일이 없도록).":
        "and the daily figure is computed with the deposit effect removed (so that \"+100%\" never goes out on a deposit day).",
      "2026-08-11, 위에 적은 '누적을 오늘이라 불렀다'가 카드에는 그대로 남아 있었습니다.":
        "2026-08-11 — the \"cumulative called today\" issue written above was still present on the card.",
      "이라 성적을 부풀리지는 않았지만, 그래도 틀린 숫자입니다. 더 중요한 문제는 따로 있습니다 —":
        "so it did not inflate the result, but it is still a wrong number. The more important problem lies elsewhere —",
      "저희는 거시 지표(금리차·하이일드 스프레드·달러인덱스·기대인플레)를 FRED에서 받아 쓰는데,":
        "We take macro indicators (the yield spread, the high-yield spread, the dollar index, inflation expectations) from FRED, and",
      "거기에는 \"72,488,498원 · 오늘 +7,149.96%\"라고 적혀 있습니다. 그 폴더는":
        "It reads \"KRW 72,488,498 · today +7,149.96%\". That folder is",
      "이라, 숫자가 틀렸다고 덮어쓰면 그날 하지 않은 말을 한 것으로 남습니다. 대신 같은 폴더에":
        "so overwriting it because the number is wrong would leave us having said something we did not say that day. Instead, in the same folder,",
      "을 함께 넣었습니다. 틀린 것을 지우는 대신 틀렸다고 적어 두는 것이 이 제품의 방식입니다.":
        "was placed alongside. Writing down that something was wrong, rather than deleting it, is this product's way.",
      "이었습니다. 열 제목은 \"주간 수익률\"이었습니다. 실측(2026-08-10 주): 페이지에는":
        "The column heading read \"weekly return\". Measured (week of 2026-08-10): the page showed",
      "— 공개 차트와 대조하시면 코인은 매일 어긋나 보입니다. 조작이 아니라 이 구조 때문입니다.":
        "— compared against a public chart, crypto will look off every day. That is this structure, not tampering.",
      "이었습니다. 주문은 곱해서 나가는데 장부에만 빠져 있어, 8월 10일 KODEX200 체결이":
        "The order went out multiplied while only the ledger left it out, so the KODEX 200 fill on 10 August",
      "2026-08-12, '오늘의 거시' 카드가 데이터에 없는 날짜를 기록에 남기고 있었습니다.":
        "2026-08-12 — the \"macro today\" card was recording a date that does not exist in the data.",
      "첫째, 자산 \"79,251원\"은 진짜 원화 금액이 아니라 단위가 섞인 합계였습니다. 둘째,":
        "First, equity of \"KRW 79,251\" was not a real won figure but a total with mixed units. Second,",
      "2026-08-11, 코인은 '아직 만들어지는 중인 봉'으로 판단하고 있음을 확인했습니다.":
        "2026-08-11 — confirmed that crypto was deciding on a bar still in the making.",
      "2026-08-19 교정 — '그냥 보유했다면' 기준선이 사는 값을 물지 않고 있었습니다.":
        "2026-08-19 correction — the \"what if you had simply held\" baseline was not paying the cost of buying.",
      ". 이 페이지는 기록이 진짜임을 보증할 뿐, 전략이 앞으로 돈을 번다는 보증이 아닙니다.":
        ". This page guarantees only that the record is genuine — not that the strategy will make money.",
      "입니다. 미국 종목은 달러로 거래되니, 계좌에 담을 때 원화로 바꿔서 담습니다. 그런데":
        "US symbols trade in dollars, so they are converted to won when placed in the account. But",
      "로만 체결하고 (개장 갭 감수) 거래세·슬리피지까지 뺀 숫자를 기록합니다. 과거 기록은":
        "only, taking the opening gap as it comes, and the number recorded is net of transaction tax and slippage. Past records",
      "\"노출이 줄어서\"가 아니라 \"모델이 학습·검증에서 본 것과 같은 종류의 입력을 받아서\"":
        "not \"because exposure fell\" but \"because the model receives the same kind of input it saw in training and validation\"",
      "이 함께 나갑니다. 같은 점검에서, 스레드 캡션이 500자를 넘겨 짧은 판으로 바뀔 때":
        "goes out alongside. In the same review, when a Threads caption exceeds 500 characters and switches to the short version,",
      "\"보조 지표 0/11, 전부 누락\"을 기록했습니다. 아무도 몰랐던 이유가 중요합니다 —":
        "recorded \"auxiliary indicators 0/11, all missing\". Why nobody noticed matters —",

      "(90일), 두 계좌\n일수익 차이의 통계 검정(유의수준 5%). 9월 17일에 중간 참고 판독(확정 아님).":
        "(90 days), a statistical test of the difference in daily returns between the two accounts (5% significance). An interim, non-binding reading is due on September 17.",
      "를 그대로 보여줍니다 —\n08-17 999,268원, 08-18 1,000,117원. 저희가 고칠 수 없는 실행 기록(깃허브)\n링크도 함께 답니다. 다만 그 숫자는":
        "exactly as they stand — 999,268 KRW on 08-17, 1,000,117 KRW on 08-18. We also attach a link to the execution log on GitHub, which we cannot edit. That said, those numbers are",
      "07:52 　📦 통합 분산 계좌: 자산":
        "07:52 　📦 Combined diversified account: equity",
      "08:23 　🔁 챔피언 교체: SPY, QQQ": "08:23 　🔁 Champion swap: SPY, QQQ",
      "\"이 성과가 실력인지 운인지\"를 아직 증명하지 못한 상태":
        "we have not yet shown whether this result is skill or luck",
      "8,702원(0.87%p) 뒤집니다.": "by 8,702 KRW (0.87 percentage points).",
      "자산 997,198원짜리 계좌": "an account holding 997,198 KRW",
      "아마존 매수 6,361,688원": "buy Amazon, 6,361,688 KRW",
      "(킬스위치)와,": "(the kill switch), and",
      "입니다. 그런데": "But",
      "\"이 장치의 진짜\n산출물은 감시가 아니라":
        "the real output of this device is not the watching but",
      "는\n매일 적습니다. 그런데 정작":
        "every day. But the one thing it did not write down was",
      "몇 개의 시세를 보고 판단했는지":
        "how many price bars the decision actually looked at",
      "는 적지\n않았습니다. 그래서 이런 일이 몇 주 동안 보이지 않았습니다 —":
        ". Because of that, this went unseen for weeks —",
      "코인 5종목이 800개를 요청하고 300개만 받고 있었습니다.":
        "five crypto symbols were asking for 800 bars and receiving only 300.",
      "(주 거래소가 막혀 넘어간 보조 거래소가 한 번에 300개까지만 주는 곳이었습니다.)":
        "(The primary exchange was blocked, and the backup we fell back to hands out at most 300 bars at a time.)",
      "모자란 표본 위에서": "on a short sample",
      "나왔습니다.\n받는 양을 안 적으면": "If you never write down how much you received,",
      "덜 받은 것을 알 방법이 없습니다.": "there is no way to notice that you got less.",
      "시세를 더 받아 오는 문제는 어제 고쳤습니다. 오늘 고친 것은 그":
        "Fetching more price bars was fixed yesterday. What we fixed today is the",
      "다음": "next part",
      "입니다 — 요청한 것보다 적게 받으면": "— when we receive less than we asked for,",
      "그 사실이 장부에 남고, 화면과\n알림으로 나갑니다.":
        "that fact is written into the ledger and goes out on the site and in alerts.",
      "⚠️ 대외 소통에서 유의할 점: 표본이 모자랐다는 것은":
        "⚠️ A note for how we talk about this: a short sample does not mean",
      "\"성적이 나빴다\"가\n아니라 \"그 성적을 말할 근거가 얇았다\"":
        "\"the result was bad\" — it means \"the ground for stating that result was thin\"",
      "는 뜻입니다. 둘은 다릅니다.": ". Those are two different things.",
      "2026-08-16, 자동 배치가 만든 기록을 아무도 검사하지 않고 있었습니다.":
        "2026-08-16 — nobody was checking the records the automated batch produced.",
      "어제 자산이 7,249만원으로 찍힌 사고에는 뒷이야기가 있습니다.":
        "There is a back story to yesterday's accident, when equity printed as 72.49 million KRW.",
      "그 값이\n틀렸다는 것을 우리 검사는 이미 알고 있었습니다":
        "our checks already knew that figure was wrong",
      "그 검사는\n그 기록을 한 번도 보지 못했습니다.":
        "those checks never once saw that record.",
      "배치가 만든 기록에만 검사가 안 걸리는 구멍":
        "a hole through which records made by the batch escaped every check",
      "이\n있었고, 어제 숫자는 그 구멍으로 반나절을 살아남았습니다. 발견도 우연이었습니다.":
        ", and yesterday's number survived half a day through it. Even finding it was an accident.",
      "이제": "Now",
      "계좌를 건드리는 배치는 기록을 남기기 직전에 장부 검사를 먼저\n돌립니다.":
        "any batch that touches an account runs the ledger checks first, right before it writes.",
      "그 기록을 아예 남기지 않습니다.": "the record is not written at all.",
      "틀린 기록은 그날의 성적표일 뿐 아니라":
        "A wrong record is not only that day's report card but",
      "다음 날의 출발점": "the next day's starting point",
      "조용히 틀리느니 시끄럽게 멈추는\n쪽": "stopping loudly over being wrong quietly",
      "을 택했습니다.": "is what we chose.",
      "함께: 어제 사고의": "Also: yesterday's accident had",
      "가장 이른 신호": "an earlier signal",
      "저희 계좌는": "Our account is",
      "원화 계좌": "a won-denominated account",
      "바꾸는 자리가 두 군데였고 한 군데만 고쳐져\n있었습니다":
        "the conversion happened in two places and only one of them had been fixed",
      "— 평가할 때는 원화로 바꿨는데,": "— valuation converted to won, but",
      "살 때는 달러 가격을 그대로": "buying used the dollar price as-is",
      "그 체결을 없던 일로 되돌리고 쓴 돈을 현금으로 돌려놨습니다.":
        "We unwound that fill and returned the money spent to cash.",
      "자산은\n997,197원(전날 대비 -0.26%)입니다.":
        "Equity is 997,197 KRW (-0.26% versus the previous day).",
      "\"제대로 바꿨다면 얼마였을까\"를 계산해 넣지는 않았습니다":
        "we did not compute and insert \"what it would have been had the conversion been right\"",
      "한 곳에서만": "in one place only",
      "하도록\n합치고, 그래도 빠졌을 때를 대비해":
        ", and in case it is still missed somewhere,",
      "체결가와 평가가격의 자릿수가 안 맞으면\n주문 자체를 막습니다":
        "an order is blocked outright when the fill price and the valuation price differ by an order of magnitude",
      "나머지 절반": "the other half",
      "그날 만들어진 SNS 카드와 캡션은 고치지 않고 그대로 둡니다.":
        "The social cards and captions made that day are left untouched.",
      "그날 시스템이 말한 것의 기록": "a record of what the system said that day",
      "무엇이 틀렸고 실제 값이\n얼마인지 적은 정정문":
        "a correction stating what was wrong and what the real figure is",
      "2026-08-18 추가:": "Added 2026-08-18:",
      "그때 정정문은 사람이 손으로 넣었습니다. 정작":
        "that correction was inserted by hand. Meanwhile,",
      "글이 만들어지는 자리에는 아무 관문도 없었습니다":
        "there was no gate at all where the post itself is written",

      "하루 등락이 계좌\n전체보다 클 수 없다":
        "a day's move cannot be larger than the whole account",
      "는 선을 글 만드는 자리에 걸어 두었습니다. 넘으면\n글을 고쳐서 내보내지 않고":
        "is now a line drawn where the post is written. If it is crossed, the post is not quietly patched and sent —",
      "만들기를 멈추고 경보를 울립니다": "writing stops and an alarm goes off",
      "지금 이 시스템은": "As it stands the system",
      "내 돈을 넘겨서 사지 않습니다": "never buys beyond its own money",
      "지금 안전장치는 전부 \"돈이 0 아래로는 안 간다\"는 전제 위에 서 있습니다.":
        "Every safeguard today rests on the assumption that money cannot go below zero.",
      "실시간으로": "in real time",
      "강제청산하는데 우리는 하루에 한 번 보고 있었으니,\n그 사이에 끝나면 킬스위치는":
        "liquidates you, while we were looking once a day — so if it ends in between, the kill switch is",
      "선언만 남습니다": "left as a declaration only",
      "하나라도 답을 모르면 잠깁니다.":
        "If even one of them has no answer, it stays locked.",
      "이 변경으로 지금의 매매는 한 글자도 바뀌지 않습니다.":
        "This change alters not one character of how we trade today.",
      "2026-08-15, 장중 감시를 15분마다 돌립니다.":
        "2026-08-15 — intraday monitoring now runs every 15 minutes.",
      "그 자리에서": "on the spot",
      "노출을 줄입니다.\n다만 이 장치의 진짜 산출물은 감시 자체가 아니라":
        "exposure is cut. But the real output of this device is not the watching itself —",
      "\"우리가 실제로 얼마나 자주\n봤는가\"의 기록":
        "it is the record of how often we actually looked",
      "설정값이 아니라 실제로 벌어졌던 최악의 간격":
        "not the configured value but the worst gap that actually happened",
      "으로\n계산합니다.": "is what we compute from.",
      "넣은 전략은 매일 밤 다른 후보들과":
        "A strategy you submit goes through the same nightly audition",
      "같은 심사": "as every other candidate",
      "새 전략만 그것을 건너뛰면": "if only the new strategy skipped that,",
      "\"이 자료에는 검증 가능한 규칙이 없습니다\"라고\n말하는 것":
        "saying \"this material contains no verifiable rule\"",
      "저희가 지어낸 전략": "a strategy we made up",
      "2026-08-14, 이름을 '8마일 챌린지'에서 '100만 챌린지'로 바꿨습니다.":
        "2026-08-14 — the name changed from \"8 Mile Challenge\" to \"1M Won Challenge\".",
      "원래 이름은": "The original name meant",
      "여덟": "eight",
      "종목에": "symbols at",
      "만원": "10,000 won",
      "100만원": "1,000,000 won",
      "그 이름으로 이미 나간 기록과 SNS 캡션은 한 글자도 고치지 않습니다":
        "Records and social captions already published under that name are not edited by a single character",
      "—\n아래": "— see",
      "코드의 시작금\n상수도 8만원에서 100만원으로 맞췄습니다":
        "the starting-capital constant in the code was also moved from 80,000 won to 1,000,000 won",
      "2026-08-15, 주간 아카이브의 '주간 수익률'이 그 주 마지막":
        "2026-08-15 — the weekly archive's \"weekly return\" was really that week's last",
      "하루치": "single day",
      "였습니다\n— 부호가 반대로 나갔습니다.": "— and the sign went out backwards.",
      "주간 아카이브 페이지는 주간 성적을 자기 힘으로\n계산하고 있었는데, 계산에 쓴 값이":
        "The weekly archive page was computing the weekly result on its own, and the value it used was",
      "그 주 마지막 날 하루 수익률": "the return of the final day of that week",
      "가 떠 있었고, 사실은 원금 100만원 대비":
        "was displayed, when against the 1,000,000 won principal it was really",
      "였습니다.\n그리고 종목 표는 계좌를 연":
        "And the per-symbol table left the first week after the account opened",
      "첫 주를 통째로 비워": "entirely blank",
      "공개 페이지 쪽 복사본은\n그대로 남아":
        "the copy living on the public page stayed as it was",
      "있었습니다. 이제 셈은 배치가 한 곳에서 하고":
        "Now the batch does the arithmetic in one place and",
      "페이지는 읽기만\n합니다": "the page only reads it",
      "입니다.\n입금은 수익이 아니므로 그 주 유입액을 빼고 잽니다.":
        "A deposit is not a profit, so that week's inflow is subtracted before measuring.",
      "과거 기록은 고치지 않습니다": "Past records are not edited",
      "— 바뀐 것은 그 기록을 읽어 보여주는\n방식이고, 원본은 그대로입니다.":
        "— what changed is how those records are read and shown; the originals stand.",
      "종목표의 적중률은": "The hit rate in the symbol table was",
      "과거 400봉에 오늘의 챔피언\n전략을 적용해":
        "measured by applying today's champion strategy to the past 400 bars",
      "잰 값이었습니다. 그런데 그 400봉은": "But those 400 bars",
      "그 챔피언을 뽑은\n오디션(800봉)과 100% 겹칩니다":
        "overlap 100% with the audition (800 bars) that picked that champion",
      "실제보다 좋게 나옵니다": "it comes out better than reality",
      "이 제품은 '선택 편향 없는 공개 실험'을 내걸고 있습니다.":
        "This product claims to be a public experiment free of selection bias.",
      "이 계좌의 실제 기록만으로": "from this account's actual record alone",
      "잰 값입니다. 아래쪽은 아무도 고르지 않은\n구간이라 정직하지만":
        "The lower figure is honest because nobody chose that window, but",
      "표본이 아주 작습니다": "the sample is very small",
      "어느 쪽도 실력의\n증거가 아닙니다.": "Neither one is evidence of skill.",
      "— 실전 적중률은 다음 배치부터 장부에\n적힙니다.":
        "— the live hit rate is written into the ledger from the next batch onward.",
      "낙폭(고점 대비 얼마나 빠졌나)을 재는 기준선에":
        "The baseline for measuring drawdown (how far below the peak) was missing",
      "원금 자체가 빠져 있었습니다.": "the principal itself.",
      "그래서 계좌가 원금을 한 번도 넘지\n못한 구간에서는":
        "So during stretches where the account never rose above its principal,",
      "첫 기록의 손실이 그대로 기준선":
        "the loss in the first record became the baseline itself",
      "로 적혔습니다.": "was what got recorded.",
      "왜 중요한가 — 이 숫자가 브레이크를 겁니다.":
        "Why it matters — this number is what pulls the brake.",
      "전량 정지": "a full stop",
      "인데, 20%로 읽히면": "but read as 20% it becomes",
      "절반만 축소": "only a halving",
      "이미 기록된 값은 고치지 않습니다": "Figures already recorded are not edited",
      "2026-08-14 기록은 하루 묵은 주식 데이터로 판단됐습니다 — 그대로\n둡니다.":
        "The 2026-08-14 record was decided on day-old stock data — it stands.",
      "0.03%만 만들어진 봉": "a bar only 0.03% formed",
      "이 \"8월 14일\"이라는 새 하루를 열어\n버렸습니다. 그 기록의 주식 판단은":
        "opened a whole new day called \"August 14\". The stock decision in that record was made on",
      "전날 봉": "the previous day's bar",
      "으로 내려진 것입니다 —\n장부의": "— so the ledger's",
      "에": "in",
      "이 기록을 지우거나 고치지 않습니다.": "This record is neither deleted nor edited.",
      "어느 정도 형태를 갖춘 봉만\n새 하루를 열 수 있게":
        "so that only a bar with some substance can open a new day",
      "계좌 자산은": "Account equity was",
      "달러 표시 가격을 원화처럼":
        "dollar-denominated prices treated as if they were won",
      "두 가지가 사실이 아니었습니다.": "two things were not true.",
      "환위험이 통째로 빠져 있었습니다": "currency risk was missing entirely",
      "내부적으로는": "internally",
      "기록하지 않습니다": "we do not record it",
      "— 1.0으로\n때우지 않습니다.": "— we do not paper over it with 1.0.",
      "과거는 소급 환산하지 않았습니다.": "The past was not retroactively converted.",
      "으로 그대로 보관되며, 7일치\n기록은 이전 세대로 계속 공개됩니다.":
        "is kept as it is, and the seven days of records remain public as the previous generation.",
      "판정 시계는 0일부터 다시 돕니다": "The judgement clock restarts from day zero",
      "—\n통화 기준이 다른 두 구간의 수익률은 같은 통계가 아니기 때문입니다.":
        "— returns from two windows on different currency bases are not the same statistic.",

      "2026-08-05, 통합 계좌를 '8마일 챌린지'로 재출발했습니다":
        "2026-08-05 — the combined account was restarted as the \"8 Mile Challenge\"",
      "— 시작금\n8만원(8종목 × 만원). 그 이전 이틀간의 만원 기록은 삭제되지 않고":
        "— starting capital 80,000 won (8 symbols × 10,000 won). The two prior days of 10,000-won records were not deleted but kept in",
      "git\n이력": "the git history",
      "다음 세션 시가": "the next session's open",
      "재계산하지 않고 그대로 둡니다": "are left as they are, not recomputed",
      ")가 붙어 어느 기준의 숫자인지 영구히 구분됩니다.":
        ") is attached, so which basis a number belongs to stays distinguishable forever.",
      "2026-08-11, 기록 배열 순서 오류를 발견했습니다.":
        "2026-08-11 — we found an ordering error in the record array.",
      "한국 주식 6종목의 기록이 08-05 →":
        "The records for six Korean stocks ran 08-05 →",
      "숫자 자체는 그날의 진짜 기록": "the numbers themselves are that day's real record",
      "저장된 기록은 고치지 않았습니다": "the stored records were not edited",
      "결정에 쓴 봉 15개 중 15개": "15 of the 15 bars used in the decision",
      "코인 기록의 price는\n그날의 일봉 종가가 아닙니다":
        "the price in a crypto record is not that day's daily close",
      "같은 날 고쳤습니다.": "Fixed the same day.",
      "이제 규칙은": "The rule is now",
      "\"완성된 정보로 판단하고, 지금 가격에 체결한다\"":
        "\"decide on completed information, fill at the current price\"",
      "오디션(백테스트)이 완성 봉으로 평가하는 것과 조건이\n같아집니다.":
        "This puts it on the same footing as the audition (backtest), which evaluates on completed bars.",
      "영향은 작지 않습니다": "The impact is not small",
      ")는 계속 장부에 남깁니다. 이 변경 이전의\n기록은":
        ") is still written into the ledger. Records from before this change are",
      "고치지 않습니다": "not edited",
      "— 그때는 그 값으로 판단했고, 그것이 그날의 진짜\n기록이기 때문입니다.":
        "— the decision was made on that value at the time, and that is that day's true record.",
      "2026-08-11, SNS 게시물이 '누적 수익률'을 '오늘'이라\n불렀습니다.":
        "2026-08-11 — a social post called the cumulative return \"today\".",
      "8월 10일에 나간 글은": "The post published on August 10 said",
      "라고 적었지만,\n-0.06%는 원금 대비": "but -0.06% was, against the principal,",
      "수치였습니다. 그날의": "That day's",
      "누적과 하루치를 나란히": "cumulative and daily side by side",
      "8월 10일 게시물은 고치지 않습니다": "The August 10 post is not edited",
      "2026-08-11, SNS 카드가 사지 않은 종목을 \"매수\"라고\n적었습니다.":
        "2026-08-11 — a social card wrote \"buy\" for a symbol we did not buy.",
      "8월 10일 카드 4장째(\"돈이 간 곳\")는":
        "The fourth card of August 10 (\"where the money went\") said",
      "나스닥100 ETF 매수 8.0%": "buy Nasdaq-100 ETF 8.0%",
      "라고 적었지만, 그날 그 종목의 장부는":
        "but that day the ledger for that symbol showed",
      "원인은 장부의 두 숫자를 같은 것으로 다룬 데 있습니다.":
        "The cause was treating two different ledger numbers as the same thing.",
      "배분 예산": "the allocation budget",
      "총노출 7%": "total exposure 7%",
      "종목별 실제 적용 노출": "the exposure actually applied per symbol",
      "그날 비중이 0이었던 종목을 빼고":
        "symbols whose weight was zero that day are dropped",
      "8월 10일 게시물과 이미지는 고치지 않습니다.":
        "The August 10 post and images are not edited.",
      "같은 계열을 하나 더 찾았습니다:": "We found one more of the same family:",
      "체결 기록의 비중도 배분 슬라이스를 곱하기\n전 값":
        "the weight in fill records was also the value before multiplying by the allocation slice",
      "로 적혀 있습니다 — 같은 날 계좌 총노출":
        "— on the same day the account's total exposure was",
      "체결 하나가 그날 총노출보다 클 수 없다":
        "no single fill can exceed that day's total exposure",
      "는 산술 검사가 새 기록을\n매번 확인합니다. 이전 기록은":
        "is an arithmetic check that now inspects every new record. Earlier records are",
      "고치지 않습니다.": "not edited.",
      "2026-08-11, SNS 카드가 신뢰구간 없이 적중 비율을\n방송하고 있었습니다.":
        "2026-08-11 — social cards were broadcasting hit rates with no confidence interval.",
      "이 사이트의 보정 표는 윌슨 95% 신뢰구간을 함께\n적고":
        "The calibration table on this site prints the Wilson 95% confidence interval alongside and advises",
      "\"구간이 좁아질 때까지는 비율보다 구간을 믿으세요\"":
        "\"until the interval narrows, trust the interval rather than the ratio\"",
      "라고 안내합니다.\n그런데": "But",
      "같은 집계를 쓰는 SNS 카드에는 그 구간이 없었습니다.":
        "the social cards, which use the same tally, had no interval.",
      "예를 들어\n\"55~60%라 말한 날 8일 ·":
        "For instance \"8 days where we said 55–60% ·",
      "실제 상승 12%": "actual rise 12%",
      "\"가 그대로 나갔는데, 표본 8일의\n실제 95% 구간은":
        "went out as-is, while the real 95% interval on a sample of 8 days is",
      "더 멀리 퍼지는 화면이 더 느슨했던":
        "the screen that travels furthest was the loosest",
      "8월 10일에 캡션을 고치고 이 문단에\n공개했는데,":
        "On August 10 we fixed the caption and disclosed it in this paragraph, but",
      "같은 결함의 형제인 SNS 카드를 찾지 않았습니다.":
        "we did not go looking for the sibling of the same defect in the social cards.",
      "카드는\n계속 누적 수치를 큰 글씨로":
        "The cards kept printing the cumulative figure in large type",
      "누적과 오늘을 나란히": "cumulative and today side by side",
      "적고 문구도 하루치로\n고릅니다.": "and the wording is chosen for the daily figure.",
      "고친 결함의 형제를 찾지 않은 것":
        "Failing to look for the sibling of a defect we had just fixed",
      "이 저희가 오늘 하루에만\n여러 번 반복한 실패라, 그 사실까지 그대로 적습니다.":
        "is a failure we repeated several times in this one day, so we write that down too.",
      "2026-08-11, 사람이 손댄 날을 방송이 말하지\n않았습니다.":
        "2026-08-11 — our broadcasts did not say when a human had intervened.",
      "이 시스템에서 사람이 결과를 바꿀 수 있는 통로는 딱 둘입니다 —":
        "There are exactly two channels through which a human can change outcomes in this system —",
      "신규 주문 일시정지": "pausing new orders",
      "노출 배수 조정": "adjusting the exposure multiplier",
      ". 장부는 그 둘을 \"숨기지 않고\n기록한다\"는 주석과 함께 매일 남기고 있었지만,":
        ". The ledger recorded both every day, with a comment saying they are logged rather than hidden, but",
      "사이트·카드·캡션 어디에도\n표시되지 않았습니다.":
        "they appeared nowhere on the site, the cards, or the captions.",
      "\"✋ 사람의 개입\"": "\"✋ human intervention\"",
      "킬스위치 고지가 하이라이트와 함께 잘려 나가던 것":
        "the kill-switch notice being truncated along with the highlights",
      "도 고쳤습니다 —\n쓸 말이 많은 날일수록 경고가 사라지는 구조였습니다.":
        "was fixed too — the structure made the warning vanish precisely on the days with the most to say.",
      "2026-08-11, 배분 방식이 화면에 산문으로 박혀\n있었습니다.":
        "2026-08-11 — the allocation method was hard-coded into the page as prose.",
      "페이퍼 페이지는 통합 계좌를 언제나":
        "The paper page always described the combined account as",
      "이라고 설명했는데,\n실제 코드는": "while the actual code used",
      "HRP → ERC → 자본 균등의 폴백 사다리":
        "a fallback ladder of HRP → ERC → equal capital",
      "로 매일 남기고 있었지만(주석에도 \"폴백 흔적\"이라\n적혀 있습니다)":
        "was written every day (the comment even calls it a \"fallback trace\"), but",
      "어느 화면도 그 값을 읽지 않았습니다.": "no screen ever read that value.",
      "2026-08-12, 계좌가 두 종류인데 그 사실을 적지\n않았습니다.":
        "2026-08-12 — there are two kinds of account, and we never said so.",
      "이 실험에는": "This experiment has",
      "통합 계좌 하나(8만원)": "one combined account (80,000 won)",
      "종목별 참고 계좌 20개(각 1만원)":
        "20 per-symbol reference accounts (10,000 won each)",
      "합계 20만원": "200,000 won in total",
      "만든 사람이 헷갈리면 읽는 사람은\n반드시 헷갈립니다.":
        "If the people who built it are confused, the people reading it certainly will be.",
      "임을 밝히고, 합계를 장부에서 계산해 표 위에 먼저\n적습니다.":
        "is stated, and the total is computed from the ledger and printed above the table first.",

      "2026-08-12, 피처 건강 계측기가 존재하지 않는\n이름을 세고 있었습니다.":
        "2026-08-12 — the feature health meter was counting names that do not exist.",
      "8개가 실제로는\n만들어지지 않는 이름":
        "eight of them were names that are never actually produced",
      "이었습니다(": "(",
      "← 실제": "← actual",
      "은 아예 없음). 그래서 장치가": "does not exist at all). So the device",
      "태어날 때부터 매일": "every day since the day it was born",
      "그 값을 어느 화면에도 보여주지\n않았습니다.": "the value was never shown on any screen.",
      "교정 이전 기록은 고치지 않으며":
        "Records from before the correction are not edited",
      ", 사이트는 그 기록을 \"계측 교정 전\"\n이라고 밝혀 오늘의 사실처럼 말하지 않습니다.":
        ", and the site labels them \"before meter correction\" so they are not presented as today's facts.",
      "2026-08-12, 적중률이 '맞출 방향이 없던 날'을\n틀렸다고 세고 있었습니다.":
        "2026-08-12 — the hit rate was counting days with no direction to get right as wrong.",
      "적중률은 \"다음 봉 방향을 맞혔는가\"를 재는\n숫자인데, 다음 날이":
        "The hit rate measures whether the next bar's direction was called correctly, but when the next day is",
      "정확히 보합": "exactly flat",
      "이면 오르지도 내리지도 않았으므로\n채점할 방향이 없습니다. 그런데 계산이 그 날을":
        "it neither rose nor fell, so there is no direction to grade. Yet the calculation counted that day as",
      "무조건 오답": "automatically wrong",
      "으로\n넣었습니다. 실측하면 상승 6·하락 2·보합 2인 구간에서":
        "Measured, over a window of 6 up, 2 down and 2 flat days it comes out as",
      "로 나옵니다 —\n방향이 있던 8일만 보면":
        "— looking only at the 8 days that had a direction, it is",
      "입니다. 15%p 차이입니다.\n이 오류는":
        "A 15 percentage-point difference. This error ran",
      "저희에게 불리한 방향": "against us",
      "보합이 생기는\n빈도는 종목마다 다릅니다.":
        "How often flat days occur differs by symbol.",
      "몇 날을 뺐는지\n(": "how many days were excluded (",
      ") 장부에 함께 남깁니다": ") is written into the ledger alongside",
      "— 빼고 숨기면 \"보합이\n없었다\"와 구별되지 않기 때문입니다.":
        "— excluding them silently would be indistinguishable from \"there were no flat days\".",
      "교정 이전 기록은 고치지 않습니다.":
        "Records from before the correction are not edited.",
      "계산 기준이 다르므로 곧바로 비교하지 마세요.":
        "The basis of calculation differs, so do not compare them directly.",
      "2026-08-12, 통계 재추출이 표본의 앞부분을\n덜 쓰고 있었습니다.":
        "2026-08-12 — statistical resampling was under-using the front of the sample.",
      "저희는 \"이 성적이 운이 아닌가\"를 확인할 때":
        "To check whether a result is just luck we use",
      "블록 부트스트랩": "the block bootstrap",
      "을 씁니다 — 수익률을 낱개로 섞으면 연속된 흐름이\n사라지므로,":
        "— shuffling returns one by one destroys the continuity of the flow, so instead we",
      "연속 구간(블록) 단위로": "resample in contiguous blocks",
      "수천 번 다시 뽑아 분포를 만드는\n방법입니다. 그런데 구간을 뽑을 때":
        "thousands of times to build a distribution. But when picking a block it",
      "끝에서 잘라내는 방식": "truncated at the end",
      "이라, 앞쪽\n날짜일수록 뽑힐 기회가 적었습니다. 실측하면":
        ", so the earlier the date, the less chance it had of being drawn. Measured, the",
      "맨 앞 날은 균등한 경우의\n약 10분의 1":
        "very first day got about one tenth of what an even draw would give",
      ", 앞 10일 평균은 약": ", and the first 10 days averaged about",
      "였습니다(중간·뒷부분은 정상).\n쉽게 말해":
        "(the middle and the tail were fine). Put simply,",
      "기록 초반이 조용히 절반쯤 무시되고":
        "the early part of the record was quietly being half ignored",
      "있었습니다.\n이 계산은 두 곳에 쓰입니다 —": "This calculation is used in two places —",
      "전략 A/B 유의성 검정": "the A/B significance test between strategies",
      "(어제의 전략을\n바꿀지 정하는 자리)과":
        "(where we decide whether to change yesterday's strategy) and",
      "'무작위 대비 백분위'": "the percentile versus random",
      "처음으로 감아\n돌려": "wrapping the blocks around to the beginning",
      "모든 날짜가 똑같은 확률로 뽑히게 고쳤습니다(원형 블록 부트스트랩).":
        "so every date is drawn with equal probability (the circular block bootstrap).",
      "다만 이 날 이전과 이후의\n'무작위 대비 백분위'는":
        "That said, the percentile versus random before and after this date is",
      "판단에 쓸 때는": "when it is used for a decision",
      "\"그날 실제로 알 수 있었던 값만 쓴다\"는 원칙에 따라":
        "following the principle of using only what could actually have been known on the day,",
      "발표 시차만큼 날짜를\n뒤로 밉니다": "the date is pushed back by the publication lag",
      "화면에 보여줄 카드": "the card shown on screen",
      "가 그렇게 밀린 날짜를\n그대로 \"이 값의 날짜\"로":
        "took that shifted date and printed it as \"the date of this value\"",
      "에 실었습니다. 이 네 지표는\n모두 시차가 1일이라":
        "All four of these indicators have a one-day lag, so",
      "관측일보다 하루 뒤": "one day after the observation date",
      "가 찍혔고, FRED가 당일치를\n내놓는 날에는":
        "was printed, and on days when FRED publishes same-day figures,",
      "내일 날짜": "tomorrow's date",
      "가 공개 기록에 남았습니다.\n값 자체(":
        "ended up in the public record. The value itself (",
      "·5일 변화율)는 시차와 무관하게 같았으므로":
        "and the 5-day change) was the same regardless of the lag, so",
      "숫자가 틀린 적은 없고": "no number was ever wrong",
      ", 이 카드는 매매를 바꾸지 않습니다. 그래도":
        "and this card does not change any trade. Even so,",
      "은 이 실험을": "is, for this experiment,",
      "남이 검증하라고 공개해 둔 장부": "a ledger published so that others can verify it",
      "FRED의 실제 관측일": "FRED's actual observation date",
      "을\n적습니다(판단 경로의 시차 보정은 그대로입니다).":
        "is what we print (the lag adjustment on the decision path is unchanged).",
      "이 사이트가 증명하려는 것은 '1억'이 아니라":
        "What this site tries to prove is not \"100 million\" but",
      "\"그냥 보유보다 낫다\"": "\"better than simply holding\"",
      "하나이고, 첫 화면은 그 비교를 크게 적습니다. 그런데":
        "— that one thing, and the front page prints that comparison large. But",
      "우리 성적은 수수료·세금·미끄러짐을 전부 낸 뒤의 값":
        "our result is net of every commission, tax and slippage",
      "인 반면, 나란히 놓인\n기준선은": "whereas the baseline placed next to it",
      "사는 값조차 한 푼도 내지 않은 값": "had not paid a single won even to buy",
      "이었습니다. 같은 자에 눈금이\n둘이었던 셈입니다. 이제 기준선도":
        "It amounted to two scales on one ruler. Now the baseline also",
      "사는 값을 한 번": "pays the cost of buying once",
      "화면이 고르지 않고 장부가 계산해 남긴 값":
        "the value the ledger computed and stored, not one the screen picked",
      "만 씁니다.": "is all we use.",
      "⚠️ 이 교정은 우리에게 유리한 방향입니다": "⚠️ This correction runs in our favour",
      "996,500원 → 995,337원": "996,500 KRW → 995,337 KRW",
      ", 우리 우위": ", our edge",
      ".\n같은 날 장중 실험 페이지의 기준선도 같은 이유로":
        "The same day, the baseline on the intraday experiment page moved for the same reason to",
      "로\n바뀌었습니다.": ".",
      "2026-08-19 추가 — 이미 낸 비용을 첫 화면에\n적습니다.":
        "Added 2026-08-19 — the costs already paid are printed on the front page.",
      "비용은 예전부터 자산에서 제대로 빠지고 있었지만,":
        "Costs had always been deducted from equity correctly, but",
      "얼마나\n빠졌는지는 어디에도 없었습니다.":
        "how much had been deducted appeared nowhere.",
      "추정": "estimated",

      "2026-08-05, 유니버스를 8종목에서 20종목으로\n확장했습니다.":
        "2026-08-05 — the universe was expanded from 8 symbols to 20.",
      "위험기여 균등(ERC)": "equal risk contribution (ERC)",
      "배분과 낙폭 단계별": "allocation and a drawdown-tiered",
      "자동 킬스위치": "automatic kill switch",
      "가\n적용됩니다 — 이 변경도 이 문단과 공개 커밋으로만 이뤄집니다.":
        "apply — this change too is made only through this paragraph and a public commit.",
      "이것은": "This is",
      "모의투자(가짜 돈)": "a simulation (play money)",
      "입니다. 실제 주문·체결·세금의 마찰은 근사치\n(수수료·슬리피지 모델)로만 반영됩니다.":
        "The friction of real orders, fills and taxes is reflected only as an approximation (a commission and slippage model).",
      "⑧ 사이징 사다리": "⑧ The sizing ladder",
      "— 같은 확률에": "— at the same probability,",
      "얼마를 걸까": "how much do you stake",
      "틀린 값이 아니라 안 재본 값": "not a wrong value but a value never measured",
      "⑨ 다양성 가중 그림자": "⑨ The diversity-weighted shadow",
      "(2026-08-23 등록) — 여러 전략이 한 계좌에 앉을 때":
        "(registered 2026-08-23) — when several strategies sit in one account,",
      "섞는 비중만": "only the blending weights",
      "바꾼 가상 계좌 둘: 지금 규칙(성적 기반) vs 전략끼리의 상관까지 본 비중. 판정일":
        "differ between two virtual accounts: the current rule (performance-based) versus weights that also account for the correlation between strategies. Judgement date",
      "0.196으로 문턱 미달": "0.196, below the threshold",
      "과거·현재 성과는": "Past and present performance",
      "미래 수익을 보장하지 않습니다": "does not guarantee future returns",
      "본 사이트와 방송은": "This site and its broadcasts are",
      "투자 자문·권유가 아닙니다": "not investment advice or solicitation",
      "⚠️ 직접 검증하는 법: 저장소의":
        "⚠️ How to verify it yourself: in the repository, the",
      "state/ 커밋\n목록": "commit list for state/",
      "→ 100만 챌린지 실기록 보기": "→ See the 1M Won Challenge live record",

      "오늘의 체결": "Today's fills",
      "진입 시점·가격 — 장부 그대로": "Entry time and price — straight from the ledger",
      "체결가(원)": "Fill price (KRW)",
      "체결 금액": "Fill amount",
      "체결 시점": "Fill time",
      "즉시(코인)": "immediate (crypto)",
      "새벽 결정 직후": "right after the dawn decision",
      "예약 주문": "queued order",
      "오늘 새벽 결정 → 다음 장 시가 체결":
        "Decided at dawn today → filled at the next session's open",
      "통합 계좌 목표 비중": "Target weight in the combined account",
      "체결 예정": "to be filled",
      "오늘 손대지 않은 이유": "Why we left it alone today",
      "비용이 이득보다 크면 안 하는 것도 판단입니다":
        "When the cost outweighs the gain, doing nothing is also a decision",
      "사유": "Reason",
      "대상": "Applies to",
      "설명": "Explanation",
      "잔돈 주문 차단": "Odd-lot order blocked",
      "재조정 쿨다운": "Rebalance cooldown",
      "코인 재조정 밴드": "Crypto rebalance band",
      "왕복비용 30bp(가정) 기준 — 이보다 덜 벗어나면 그대로 둡니다":
        "Based on a 30bp round-trip cost (assumed) — anything inside that is left alone",
      "한국주식 재조정 밴드": "Korean stock rebalance band",
      "미국주식 재조정 밴드": "US stock rebalance band",
      "※ 주식은 \"결정한 날 종가에 산 척\"하지 않고\n      실제로 가능한 체결(다음 세션 개장 시가, 갭 감수)만 인정합니다 — 백테스트 눈속임 방지 규칙.":
        "※ For stocks we do not pretend to have bought at the close of the deciding day; only a fill that was actually possible counts (the next session's opening price, gap included) — a rule against backtest sleight of hand.",
      "실시간 차트": "Live chart",
      "TradingView · 표시 전용(판단은 새벽 데이터)":
        "TradingView · display only (decisions run on dawn data)",
      "quant.jiwon-1a2.workers.dev · 가상 자금 모의투자 —":
        "quant.jiwon-1a2.workers.dev · play-money simulation —",
      "실제 돈이 아니며 수익을 보장하지 않습니다":
        "not real money, and no returns are guaranteed",
      "· 판단은 매일 새벽 1회(일봉 기준)":
        "· one decision per day at dawn (on daily bars)",
      "※ '일간'은 그 종목\n    계좌 자산의 어제 대비 변화입니다. '오늘의 자세'는 새벽의 결정이라, 관망이어도\n    어제 보유분의 손익·체결 시차(주식은 다음 시가 체결)·수수료가 일간에 남을 수\n    있습니다. 어제도 완전 현금이었던 종목만 정확히 0.00%입니다.":
        "※ \"Daily\" is the change in that symbol's account equity versus yesterday. \"Today's stance\" is the dawn decision, so even when it stands aside, yesterday's holdings, the fill lag (stocks fill at the next open) and commissions can still show up in the daily figure. Only a symbol that was fully in cash yesterday too reads exactly 0.00%.",

      "전일 수익률": "previous-day return",
      "5일 수익률": "5-day return",
      "10일 수익률": "10-day return",
      "변동성(20일)": "volatility (20-day)",
      "변동성 레짐(단/장기)": "volatility regime (short/long)",
      "RSI(14)": "RSI (14)",
      "RSI(7)": "RSI (7)",
      "20일선 이격": "distance from the 20-day average",
      "50일선 이격": "distance from the 50-day average",
      "20일 모멘텀": "20-day momentum",
      "60일 모멘텀": "60-day momentum",
      "MACD 히스토그램": "MACD histogram",
      "볼린저 위치": "position in the Bollinger band",
      "평균 진폭(ATR)": "average range (ATR)",
      "거래량 이상치": "volume outlier",
      "GK 변동성(고저가 기반)": "GK volatility (from highs and lows)",
      "실현변동성 비율(5/60일)": "realised volatility ratio (5/60 days)",
      "펀딩비(포지셔닝 과열도)": "funding rate (how crowded positioning is)",
      "펀딩비 변화(수급 모멘텀)": "change in funding rate (flow momentum)",
      "비트코인 5일 흐름": "Bitcoin's 5-day move",
      "미국 S&P500 5일 흐름": "the S&P 500's 5-day move",
      "미 10년물 금리 5일 변화": "5-day change in the US 10-year yield",
      "원/달러 5일 변화": "5-day change in KRW/USD",
      "공포탐욕지수(시장 심리)": "fear and greed index (market mood)",
      "미결제약정 5일 변화(수급)": "5-day change in open interest (flow)",
      "장단기 금리차(경기 신호)": "yield curve spread (a signal on the economy)",
      "VIX 변동성지수(옵션시장 공포)":
        "VIX volatility index (fear in the options market)",
      "김치 프리미엄(국내 수급)": "kimchi premium (domestic flow)",
      "VIX 기간구조(공포의 급성도)": "VIX term structure (how acute the fear is)",
      "외국인 5일 순매수(z)": "5-day net foreign buying (z)",
      "기관 5일 순매수(z)": "5-day net institutional buying (z)",
      "하이일드 스프레드(신용 스트레스)": "high-yield spread (credit stress)",
      "달러인덱스 5일 변화": "5-day change in the dollar index",
      "기대인플레 5일 변화": "5-day change in expected inflation",
      "과매도권": "oversold",
      "과열권": "overbought",
      "중립": "neutral",
      "선 위": "above the line",
      "선 아래": "below the line",
      "변동성 확장 국면": "volatility expanding",
      "변동성 수축 국면": "volatility contracting",
      "보통 수준": "ordinary levels",
      "+(상승 우위)": "+ (upside has the edge)",
      "−(하락 우위)": "− (downside has the edge)",
      "상단 접근": "near the upper band",
      "하단 접근": "near the lower band",
      "밴드 중간": "mid-band",
      "거래량 급증": "volume spike",
      "거래량 급감": "volume collapse",
      "평소 수준": "usual levels",
      "신용 경색 경보": "credit-crunch warning",
      "신용시장 안정": "credit markets calm",
      "달러 강세(위험자산 역풍)": "dollar strength (a headwind for risk assets)",
      "달러 약세(위험자산 순풍)": "dollar weakness (a tailwind for risk assets)",
      "인플레 기대 상승": "inflation expectations rising",
      "인플레 기대 하락": "inflation expectations falling",
      "강한 순매수": "strong net buying",
      "강한 순매도": "strong net selling",
      "중립 수급": "neutral flow",
      "백워데이션(스트레스 급성기)": "backwardation (acute stress)",
      "깊은 콘탱고(안정)": "deep contango (calm)",
      "보통(콘탱고)": "ordinary (contango)",
      "공포 구간": "in fear territory",
      "안도 구간": "in relief territory",
      "국내 매수 과열": "domestic buying overheated",
      "역프리미엄(국내 이탈)": "reverse premium (money leaving Korea)",
      "극단적 공포": "extreme fear",
      "공포": "fear",
      "극단적 탐욕": "extreme greed",
      "탐욕": "greed",
      "롱 과열": "longs overcrowded",
      "숏 과열": "shorts overcrowded",
      "외국인": "foreign investors",
      "기관": "institutions",

      "이 목록은 깃 커밋 이력에서 자동으로 뽑습니다 — 사람이 따로 적는 일지가 아니라, 개선이 저장소에 합쳐지는 순간 남는 기록의 사본입니다. 자동 배치의 운행 기록(장부 커밋)은 제외합니다.":
        "This list is drawn automatically from the git commit history — not a diary written by hand, but a copy of the record left the moment a fix is merged. The automated batch's operating commits (ledger commits) are excluded.",

      "같은 신호에 배분 방법만 바꾼 가상 계좌들입니다(종가 평가·수수료만, 본 계좌의 변동성 타깃·킬스위치 등은 없음 — 배분 간 상대 비교 전용). 트랙이 4개라 우연히 좋아 보이는 승자가 나올 확률도 4배입니다 — 판정은 곡선이 충분히 갈라진 뒤에만 의미가 있습니다.":
        "Virtual accounts fed the same signals, differing only in how they allocate (valued at the close, commissions only — none of the live account's volatility target or kill switch; for comparing allocation methods against each other). With four tracks, the chance that one merely looks good by luck is four times higher — a verdict only means something once the curves have separated enough.",
      "모델이 말한 상승확률\n        구간별로, 실제로 오른 날의 비율입니다. \"60%라고 한 날들\"이 실제로 약\n        60% 오르면 확률이":
        "For each band of the model's stated probability of a rise, the share of days that actually rose. If the days it called 60% really rose about 60% of the time, the probability is",
      "실제 상승 비율": "Share that actually rose",
      "45% 미만(하락 쪽)": "below 45% (leaning down)",
      "⚠️ 보정 어긋남": "⚠️ Calibration off",
      "45~55% (중립권)": "45–55% (neutral)",
      "70% 이상": "70% or more",
      "가장 크게 틀린 날들 — always public":
        "The days we were most wrong — always public",
      "모델이 가장 크게\n        틀린 날을 먼저 보여드립니다. 그날 새벽의 판단 근거도 그대로 —\n        사후에 지우거나 꾸밀 수 없는 구조(git 장부)입니다.":
        "We show the days the model was most wrong first, together with that dawn's reasoning exactly as it stood — a structure that cannot be erased or dressed up after the fact (a git ledger).",
      "통합 계좌 자산": "Combined account equity",
      "그날 가장 아팠던 종목과 새벽 판단":
        "The symbol that hurt most that day, and the dawn call",
      "지금까지 누적": "Cumulative so far",
      "의 도전자를 검증해 대부분을\n        떨어뜨렸습니다. 시도가 쌓일수록 승격 문턱이 자동으로 올라갑니다\n        (다중검정 보정) — 탈락시킨 수를 공개하는 것이 \"운 좋은 승자\"가\n        아니라는 증거입니다.":
        "challengers have been vetted and most were turned down. The more attempts pile up, the higher the promotion bar rises automatically (a multiple-testing correction) — publishing how many were rejected is the evidence that the winner is not merely a lucky one.",
      "후보": "Candidate",
      "결과": "Outcome",
      "유지": "kept",
      "왜 이 종목들인가": "Why these symbols",
      "시장 3곳(코인·한국·미국)을\n      각각":
        "Three markets (crypto, Korea, the US), each split between",
      "대표 종목": "a representative symbol",
      "으로 나눠 담고(2026-08 8→20종목\n확장 — 분산이 곧 통계적 신뢰), 전부 유동성\n      최상위 자산만 골랐습니다 — 시세 데이터가 깨끗하고 실전 이전이 쉬운\n      종목들입니다. 소형주·테마주는 검증이 어려워 제외했습니다.":
        ", widened from 8 to 20 symbols in August 2026 — diversification is what makes the statistics trustworthy. Every one is a top-liquidity asset: the price data is clean and moving to live trading is easy. Small caps and theme stocks were left out because they are hard to validate.",
      "— 최대 거래소 생태계 코인 — 거래소 경기 민감 표본":
        "— the token of the largest exchange ecosystem — a sample sensitive to exchange activity",
      "— 암호화폐 시가총액 1위 — 코인 시장 전체를 대표":
        "— the largest crypto asset by market value — stands for the crypto market as a whole",
      "— 시총 2위 · 스마트컨트랙트 플랫폼 대표":
        "— second by market value · the leading smart-contract platform",
      "— 고변동 알트코인 표본 — 변동성 큰 자산에서의 전략 검증용":
        "— a high-volatility altcoin sample — for testing strategies on violently moving assets",
      "— 결제 특화 대형 알트 — BTC와 상관이 낮은 구간이 있는 표본":
        "— a large payments-focused altcoin — a sample that sometimes decouples from BTC",
      "— 메모리 반도체 — 엔비디아와 공급망으로 얽힌 사이클주":
        "— memory semiconductors — a cyclical tied to NVIDIA through the supply chain",
      "— 수출 제조 대형주 — 환율 민감 표본":
        "— a large export manufacturer — a sample sensitive to the exchange rate",
      "— 한국 시가총액 1위 대표주": "— Korea's largest company by market value",
      "— 한국 인터넷 플랫폼 대표 — 성장주 표본":
        "— Korea's leading internet platform — a growth-stock sample",
      "— 배터리·화학 사이클주 — 원자재 민감 표본":
        "— a battery and chemicals cyclical — a sample sensitive to raw materials",
      "— 코스피200 ETF — 한국 시장 전체":
        "— a KOSPI 200 ETF — the Korean market as a whole",
      "— 은행 대표주 — 금리 민감 저변동 표본":
        "— a leading bank — a low-volatility sample sensitive to interest rates",
      "— 세계 시총 최상위 — 소비자 기술주 대표":
        "— among the world's largest by market value — the leading consumer technology stock",
      "— 이커머스·클라우드 — 경기민감 성장주 표본":
        "— e-commerce and cloud — a cyclical growth sample",
      "— 광고 경기 민감 기술주 — 변동성 중상 표본":
        "— a technology stock sensitive to the advertising cycle — a moderately volatile sample",
      "— 미국 초대형 기술주 — 낮은 변동성 대형주 표본":
        "— a US mega-cap technology stock — a low-volatility large-cap sample",
      "— AI 반도체 대표 개별주 — 지수와 다른 개별주 움직임 표본":
        "— the leading AI semiconductor name — a sample of single-stock behaviour that differs from the index",
      "— 미국 기술주 전체 — 성장주 시장 대표 지수":
        "— US technology as a whole — the benchmark index for growth",
      "— 미국 시장 전체 — 세계에서 가장 유동성 높은 ETF":
        "— the US market as a whole — the most liquid ETF in the world",
      "— 고변동 대형주 — 개별주 리스크 관리 검증용":
        "— a high-volatility large cap — for testing single-stock risk control",
      "구조가 바뀌면 0일부터 다시 셉니다":
        "If the structure changes, the count restarts from day zero",
      "현재 구조(": "Current structure (",
      ") 관찰": ") observed",
      "백테스트는 결정 종가\n      체결 + 고정 슬리피지 가정이지만, 페이퍼는 다음 세션":
        "The backtest assumes a fill at the deciding day's close plus fixed slippage, while the paper account fills only at the next session's",
      "에만\n      체결합니다. 결정→체결 사이 실제로 겪은 개장 갭(불리한 방향이 +)이\n      가정을 넘으면 백테스트가 낙관적이라는 뜻 — 그 판정도 여기 그대로\n      표시됩니다.":
        ". If the opening gap actually experienced between decision and fill (adverse direction counted as +) exceeds the assumption, the backtest is optimistic — and that verdict is shown here as it stands.",
      "평균 |갭|": "Average |gap|",
      "불리 방향 평균": "Average in the adverse direction",
      "가정(수수료+슬리피지)": "Assumption (commission + slippage)",
      "오늘의 거시": "Today's macro",
      "FRED · 발표 시차 보정": "FRED · corrected for the publication lag",
      "10년 기대인플레": "10-year expected inflation",
      "금리 곡선 정상": "yield curve normal",
      "오늘의 시장 브리핑": "Today's market briefing",
      "증시": "Equities",
      "금리·환율": "Rates and FX",
      "⚠️ 판단에 사용되지 않는 참고 정보입니다 — 매매는 검증된 챔피언 전략만 수행합니다.":
        "⚠️ Reference only; this feeds no decision — trading is done solely by the validated champion strategy. Headlines are shown in the original Korean.",
      "이후 기록은 주식을 다음 세션 시가로만\n체결(개장 갭 감수)하고 수수료·거래세·슬리피지를 뺀 값입니다. 과거 기록은\n재계산하지 않고 그대로 둡니다(":
        "From then on, stocks are filled only at the next session's open (taking the gap as it comes) and the figures are net of commission, transaction tax and slippage. Past records are left as they are, not recomputed (",
      "과거 불변 약속": "the promise that the past stays untouched",
      "챔피언은 매일 밤 챔피언/챌린저 2단계 검증 + 돌연변이 진화 탐색으로\n재평가되며, 확실히 나은 후보가 있을 때만 교체됩니다(안 바뀌는 날이 정상).\n날짜는 해당 시장의 거래일 기준이고, 갱신은 매일 새벽 5:30(KST) 무렵입니다.\n\"그냥 보유\"는":
        "The champion is re-evaluated every night through two-stage champion/challenger validation plus a mutation search, and is replaced only when a candidate is clearly better (no change is the normal outcome). Dates follow the trading calendar of the market in question, and the update lands around 05:30 KST. \"Simply holding\" means",
      "첫 기록일에 같은 돈으로 전 종목을 균등 매수해\n그대로 들고만 있었을 때":
        "buying every symbol equally with the same money on the first recorded day and then just holding",
      "의 자산입니다. 아무것도 안 하고 현금으로 뒀다는\n뜻이 아니라":
        ". It does not mean sitting in cash doing nothing, but",
      "시장에 그냥 맡겨 뒀다면": "leaving the money to the market",
      "이라는 뜻이라, 시장이 빠진 날은\n이 값도 원금 아래로 내려갑니다 — 전략이 이 값을\n꾸준히 못 이기면 전략의 의미가 없으므로 함께 보여드립니다.\n💝":
        ", so on days the market falls this figure drops below the principal too. If the strategy cannot beat it consistently there is no point to the strategy, which is why it is shown alongside. 💝",
      ": 방송 후원금 자체를 운용하는 것이 아니라, 후원과 동일한\n금액만큼 운영자가 '가상 원금'을 늘리는 이벤트입니다(대가·지분 없음). 원금과\n운용 손익은 분리 표시되며, 실력 지표(TWR)는 입금 효과를 제거한 값입니다.\n기록 원본: 저장소":
        ": the donations themselves are not traded; the operator increases the virtual principal by the same amount (no consideration, no equity). Principal and trading profit are shown separately, and the skill measure (TWR) strips out the effect of deposits. Source of record: the repository's",
      "폴더 —": "folder —",

      "1억원": "KRW 100 million",
      "이 기록이 조작 불가능한 이유 →": "Why this record cannot be faked →",

      "어드민": "Admin",
      "운영 설정": "Operating settings",
      "연결": "Connect",
      "삭제": "Delete",
      "· 목표": "· target",
      "메모": "Note",
      "스레드 캡션": "Threads caption",
      "기록": "Record",
      "저장": "Save",
      "키 발급": "Issue key",


      "백테스트": "Backtest",
      "포트폴리오": "Portfolio",
      "종목선별": "Screener",
      "민감도": "Sensitivity",
      "최적화": "Optimise",
      "검증": "Validate",
      "감시": "Monitor",
      "내 전략": "My strategy",
      "입금": "Deposit",
      "긴급 정지": "Emergency stop",
      "수집 동의": "Data consent",
      "과거 데이터로 전략을 돌려 성과를 확인합니다. 처음이라면 시장을\n'모의 데이터'로 두고 감부터 잡아보세요 — 인터넷 없이도 됩니다.":
        "Run a strategy over past data and see how it did. If this is your first time, leave the market on \"synthetic data\" and get a feel for it — it works without an internet connection.",
      "1단계": "Step 1",
      "2단계": "Step 2",
      "3단계": "Step 3",
      "4단계": "Step 4",
      "과거로 감 잡기": "Get a feel from the past",
      "과최적화 걸러내기": "Filter out overfitting",
      "페이퍼": "Paper",
      "가짜 돈 실전 연습": "Practice with play money",
      "실전": "Live",
      "소액부터, 직접 결정": "Small amounts, decided by you",
      "모의 데이터 · 연습용 (synthetic)": "Synthetic data · for practice (synthetic)",
      "코인 (암호화폐) (crypto)": "Crypto (crypto)",
      "미국주식 (us_stock)": "US equities (us_stock)",
      "국내주식 (kr_stock)": "Korean equities (kr_stock)",
      "코인: BTC/USDT · 미국주식: AAPL, SPY":
        "Crypto: BTC/USDT · US equities: AAPL, SPY",
      "전략": "Strategy",
      "이동평균 교차 · 추세추종 (ma_cross)":
        "Moving-average cross · trend following (ma_cross)",
      "모멘텀 · 추세추종 (momentum)": "Momentum · trend following (momentum)",
      "평균회귀 · 되돌림 매수 (mean_reversion)":
        "Mean reversion · buy the pullback (mean_reversion)",
      "RSI 과매도 반등 (rsi)": "RSI oversold bounce (rsi)",
      "채널 돌파 · 추세추종 (breakout)":
        "Channel breakout · trend following (breakout)",
      "터틀 트레이딩 · 20일 돌파 + 2N 손절 (turtle)":
        "Turtle trading · 20-day breakout + 2N stop (turtle)",
      "볼린저밴드 · 박스권/수축돌파 (bollinger)":
        "Bollinger bands · range and squeeze breakout (bollinger)",
      "파라볼릭 SAR · 추세 반전점 (psar)":
        "Parabolic SAR · trend reversal points (psar)",
      "일목균형표 · 호전 + 구름 돌파 (ichimoku)":
        "Ichimoku · bullish cross + cloud breakout (ichimoku)",
      "듀얼 스러스트 · 시가 기준 범위 돌파 (dual_thrust)":
        "Dual thrust · range breakout from the open (dual_thrust)",
      "수급 SOM · 외인·기관 순매수 군집 (supply_som)":
        "Flow SOM · clusters of foreign and institutional net buying (supply_som)",
      "가치 닻 · 자기 역사 대비 저평가 보유 (value_anchor)":
        "Value anchor · hold when cheap against its own history (value_anchor)",
      "슈퍼트렌드 · ATR 밴드 래칫 추세 (supertrend)":
        "Supertrend · ratcheting ATR band trend (supertrend)",
      "코너스 RSI(2) · 추세 위 눌림 매수, 단기선 복귀 청산 (connors_rsi2)":
        "Connors RSI(2) · buy the dip in an uptrend, exit on the short-term line (connors_rsi2)",
      "MACD 히스토그램 (macd)": "MACD histogram (macd)",
      "켈트너 채널 돌파 (keltner)": "Keltner channel breakout (keltner)",
      "스토캐스틱 (stochastic)": "Stochastic (stochastic)",
      "머신러닝 · 상승확률 예측 (ml)": "Machine learning · probability of a rise (ml)",
      "앙상블 · 여러 전략 결합 (ensemble)":
        "Ensemble · several strategies combined (ensemble)",
      "챔피언 · 야간 재학습 1위 (champion)":
        "Champion · the winner of nightly retraining (champion)",
      "타임프레임": "Timeframe",
      "1d=일봉 · 1h=시간봉": "1d = daily bars · 1h = hourly bars",
      "봉 개수": "Number of bars",
      "일봉 500개 ≈ 2년": "500 daily bars ≈ 2 years",
      "백테스트 실행": "Run backtest",
      "⚠️ 과거 성과는 미래 수익을 보장하지 않습니다. 실거래 전 반드시 검증하세요.":
        "⚠️ Past performance guarantees no future return. Validate before trading live.",
      "계산 중입니다…": "Working…",
      "머신러닝 전략은 20~30초 걸릴 수 있어요. 창을 닫지 마세요.":
        "A machine-learning strategy can take 20–30 seconds. Do not close the window.",
      "포트폴리오 백테스트": "Portfolio backtest",
      "여러 종목에 분산투자해 변동성을 낮춥니다. 종목은 쉼표로 구분하세요.":
        "Spread across several symbols to lower volatility. Separate symbols with commas.",
      "종목 (쉼표 구분)": "Symbols (comma separated)",
      "배분 방식": "Allocation method",
      "변동성 역가중 · 안정적 배분 (inverse_vol)":
        "Inverse volatility · steadier allocation (inverse_vol)",
      "동일 비중 (equal)": "Equal weight (equal)",
      "계층적 리스크 패리티 (HRP) (hrp)": "Hierarchical risk parity (HRP) (hrp)",
      "⚠️ 과거 성과는 미래 수익을 보장하지 않습니다.":
        "⚠️ Past performance guarantees no future return.",
      "종목 선별 (팩터 스크리너)": "Symbol screening (factor screener)",
      "관심 종목을 넣으면 재무 팩터(밸류·퀄리티)로 상위 종목을 자동\n선별합니다. 미국주식 티커 권장(FMP 기준). 환경변수":
        "Enter the symbols you care about and the top ones are selected automatically on financial factors (value and quality). US tickers are recommended (FMP data). The environment variable",
      "필요.": "is required.",
      "후보 종목 (쉼표 구분)": "Candidate symbols (comma separated)",
      "선택 개수 (top N)": "How many to pick (top N)",
      "팩터": "Factor",
      "밸류+퀄리티 (PER↓·PBR↓·ROE↑)": "Value + quality (P/E↓ · P/B↓ · ROE↑)",
      "밸류 (PER↓·PBR↓)": "Value (P/E↓ · P/B↓)",
      "퀄리티 (ROE↑)": "Quality (ROE↑)",
      "선별 실행": "Run screening",
      "⚠️ 팩터 프리미엄은 수년씩 부진할 수 있습니다. 선별 결과를 맹신하지 마세요.":
        "⚠️ A factor premium can underperform for years. Do not treat the screening result as certainty.",
      "워크포워드 최적화": "Walk-forward optimisation",
      "과거 구간(IS)에서 최적 파라미터를 찾고,":
        "It finds the best parameters on a past window (in-sample) and validates them on",
      "보지 않은 미래 구간(OOS)": "a future window it has not seen (out-of-sample)",
      "에서\n검증합니다. IS와 OOS 성적 격차가 크면 과최적화예요.":
        ". A large gap between the two means overfitting.",
      "학습(IS) 길이": "Training (IS) length",
      "검증(OOS) 길이": "Validation (OOS) length",
      "최적화 실행": "Run optimisation",
      "과최적화 검증 (워크포워드+DSR · PBO · CPCV)":
        "Overfitting checks (walk-forward + DSR · PBO · CPCV)",
      "\"이 전략을 믿어도 되는가\"를 세 가지 과최적화 탐지 도구로 한 화면에서\n확인합니다. 셋 다":
        "\"Can this strategy be trusted?\" — checked on one screen with three overfitting detectors. All three are",
      "탐지": "detection",
      "도구입니다 — 통과가 곧 수익은 아닙니다.":
        "tools — passing is not the same as making money.",
      "검증 3종 실행": "Run all three checks",
      "⚠️ 세 검증을 모두 통과해도 미래 수익은 보장되지 않습니다.\n다음 단계는 페이퍼 트레이딩(learn)으로 실데이터 검증입니다.":
        "⚠️ Passing all three guarantees no future return. The next step is paper trading (learn) on real data.",
      "파라미터 민감도 히트맵": "Parameter sensitivity heat map",
      "이동평균 교차(단기×장기)의 성과 지형을 그립니다.\n넓은 초록 고원=견고, 외딴 점=과최적화.":
        "It draws the performance terrain of the moving-average cross (short × long). A wide green plateau means robust; a lone dot means overfitted.",
      "목표 지표": "Objective",
      "히트맵 생성": "Draw the heat map",

      "매칭 입금 (100만 챌린지 · 100만원 → 1억)":
        "Matching deposit (1M Won Challenge · 1,000,000 KRW → 100 million)",
      "방송 후원이 들어오면 같은 금액만큼 통합 계좌의":
        "When a donation comes in during a broadcast, the combined account's",
      "가상 원금": "virtual principal",
      "을\n늘립니다. 아직 통합 계좌 기록이 없습니다 (매일 새벽 자동 생성)":
        "is increased by the same amount. There is no combined-account record yet (one is created automatically each morning)",
      "연결 설정이 필요합니다 (최초 1회).": "A connection has to be set up once.",
      "입금 버튼이 GitHub의 입금 워크플로를 대신 눌러주려면 접근 토큰이 필요합니다.":
        "For the deposit button to press GitHub's deposit workflow for you, an access token is needed.",
      "설정 방법 보기": "Show me how",
      "이 저장소만": "this repository only",
      "선택": "select",
      "발급된 토큰을 프로그램 폴더의": "Add the issued token as one line to the",
      "파일에 한 줄 추가:": "file in the program folder:",
      "웹 조종석 재시작": "Restart the web cockpit",
      "토큰 없이도 GitHub 앱/웹 → Actions →\n\"Deposit (100만 챌린지 매칭 입금)\" → Run workflow 로 직접 등록할 수 있습니다.":
        "Without a token you can register it yourself through the GitHub app or website: Actions → \"Deposit (1M Won Challenge matching deposit)\" → Run workflow.",
      "입금액(원)": "Amount (KRW)",
      "1회 최대 1,000만원 — 예: 10000":
        "Up to 10,000,000 KRW at a time — e.g. 10000",
      "메모 (선택)": "Memo (optional)",
      "장부와 방송 배너에 함께 표시됩니다":
        "It appears in the ledger and in the broadcast banner",
      "입금 등록": "Register the deposit",
      "⚠️ 법적 구조: 후원금 자체를 운용하지 않습니다. 후원과 동일한 금액만큼":
        "⚠️ The legal structure: the donations themselves are never traded. It is a matching event that increases the",
      "가상 계좌의 원금": "virtual account's principal",
      "을 늘리는 매칭 이벤트이며(대가·지분 없음), 모든 입금은 git 커밋 장부로 공개됩니다. 수익률은 원금과 분리 계산(TWR)되어 입금이 실력처럼 보이지 않습니다.":
        "by the same amount (no consideration, no equity), and every deposit is published in the git commit ledger. The return is computed separately from the principal (TWR), so a deposit never looks like skill.",
      "봇 감시": "Bot monitor",
      "실행 중인 페이퍼/실거래 세션이 없습니다.": "No paper or live session is running.",
      "페이퍼(가짜 돈) 봇 시작하기": "Start the paper (play money) bot",
      "윈도우는": "On Windows,",
      "더블클릭,\n또는 터미널에서:": "double-click it; or from a terminal:",
      "봇이 상태 파일을 쓰기 시작하면 이 페이지에 자산·포지션·주문이\n실시간으로 나타납니다.":
        "Once the bot starts writing its state file, equity, positions and orders appear on this page live.",
      "🟢 긴급 정지 — 꺼져 있음(정상 운용 중)": "🟢 Emergency stop — off (running normally)",
      "무언가 이상하다고 느끼면 아래 버튼으로": "If something feels wrong, the button below",
      "전체 매매를 즉시 멈출 수 있습니다.": "stops all trading immediately.",
      "자동 브레이크(킬스위치·서킷브레이커)와 별개로 동작하며, 멈춰도 보유 포지션은 그대로 둡니다.":
        "It works independently of the automatic brakes (kill switch, circuit breaker), and stopping leaves existing positions untouched.",
      "지금 전체 매매 정지": "Stop all trading now",
      "데이터 수집 동의": "Consent to data collection",
      "제작사 데이터 수집 안내": "What the maker collects",
      "현재 상태:": "Current status:",
      "동의 안 함": "not consented",
      "(아무것도 전송되지 않습니다)": "(nothing is sent)",
      "이 프로그램을 계속 사용하며 아래에 동의하면, 다음이 제작사(운영자)에게\n전송·수집됩니다.":
        "If you keep using this program and consent below, the following is sent to and collected by the maker (the operator).",
      "등록한 전략의": "the rule specification of",
      "규칙 명세": "a strategy you registered",
      "(무엇을 언제 사고파는지)": "(what it buys and sells, and when)",
      "계좌별": "per account,",
      "성과 요약": "a summary of performance",
      "— 수익률·최대낙폭·평가자산·기록 길이":
        "— return, max drawdown, equity, length of record",
      "앱 버전과": "the app version and",
      "익명 설치 식별자": "an anonymous installation id",
      "(누구인지는 식별하지 않는 임의 번호)":
        "(a random number that does not identify who you are)",
      "수집하지 않는 것(보안):": "What is never collected (security):",
      "비밀번호,\n증권사·거래소 API 키, 세션 토큰 등 자격증명은":
        "passwords, broker and exchange API keys, session tokens and any other credential are",
      "절대 전송되지 않습니다": "never sent",
      "—\n이건 동의로도 바뀌지 않는 안전선입니다.": "— that is a line consent cannot move.",
      "수집 목적: 제품 개선과 전략 성과 파악. 동의는\n언제든 이 화면에서 철회할 수 있고, 철회하면 그 시점부터 전송이 멈춥니다.":
        "Why it is collected: to improve the product and understand how strategies perform. You can withdraw consent from this screen at any time, and sending stops from that moment.",
      "동의하고 수집 허용": "Consent and allow collection",
      "동의 철회 / 수집 안 함": "Withdraw consent / do not collect",

      "내 전략 — 자료에서 규칙 뽑기": "My strategy — pulling rules out of a document",
      "책·PDF·유튜브 자막·직접 쓴 글에서":
        "From a book, a PDF, YouTube subtitles or something you wrote yourself, it looks for",
      "숫자로 적힌 매매 규칙": "trading rules written as numbers",
      "을\n찾아 전략으로 만듭니다. 읽을 수 있는 규칙 9종: 이동평균 교차 · RSI ·\n가격 vs 이동평균 · 신고가/신저가 · 볼린저밴드 · 거래량 배수 · 연속 양봉/음봉 ·\nMACD · 손절/익절 %.":
        "and turns them into a strategy. Nine kinds of rule can be read: moving-average cross · RSI · price vs moving average · new highs and lows · Bollinger bands · volume multiples · consecutive up/down bars · MACD · stop-loss and take-profit percentages.",
      "규칙이 없으면 \"없다\"고 말합니다": "If there is no rule, it says so",
      "— 없는 규칙을\n지어내지 않는 것이 이 기능의 핵심입니다.":
        "— not inventing rules that are not there is the whole point of this feature.",
      "자료 본문 붙여넣기": "Paste the text here",
      "또는 아래에 PDF 파일 경로나 유튜브 주소를 입력하세요\n    (둘 다 있으면 경로/주소를 씁니다)":
        "or enter a PDF path or a YouTube URL below (if both are given, the path or URL wins)",
      "PDF 경로 · 유튜브 주소 (선택)": "PDF path · YouTube URL (optional)",
      "전략 이름 (선택)": "Strategy name (optional)",
      "읽어 보기 (아직 저장 안 함)": "Read it (nothing is saved yet)",
      "읽힌 전략은": "A strategy that was read becomes",
      "도전자": "a challenger",
      "로 등록됩니다 —\n등록만으로는 매매하지 않고, 매일 밤 심사(선발전·결승전)를 이겨야 매매를\n맡습니다. 심사와 무관하게 쓰고 싶다면 저장 후":
        "— registering alone trades nothing; it has to win the nightly audition (a qualifier and a final) before it trades. To use it regardless of the audition, save it and then",
      "고정": "pin it",
      "으로.": ".",
      "Quant · 내 전략 — 자료 읽기": "Quant · My strategy — reading a document",

      // ── 주간 아카이브 ──────────────────────────────────────
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
      ["^(\\d{4}-\\d{2}-\\d{2}) 시작$", "started $1"],
      ["^(\\d{4}-\\d{2}-\\d{2}) 확정$", "settled $1"],
      // 판단 근거(매일 새로 만들어진다) — 피처 이름과 상태 이름은
      //   사전에서 찾고($*n), 값은 그대로 흘려보낸다. 일반 규칙보다
      //   먼저 와야 한다 — 아래 ^(\\d+)일 (.+)$ 가 "20일 모멘텀"을
      //   가로채면 이름의 절반이 한국어로 남는다.
      ["^판단 재료: (.+) / (.+) / (.+)$",
       "inputs behind the call: $*1 / $*2 / $*3"],
      ["^판단 재료: (.+) / (.+)$", "inputs behind the call: $*1 / $*2"],
      ["^판단 재료: (.+)$", "inputs behind the call: $*1"],
      ["^(외국인|기관) 수급 z=([−+\\-][\\d\\.]+)\\((.+)\\)$", "$*1 flow z=$2 ($*3)"],
      ["^펀딩비 ([−+\\-][\\d\\.]+)%\\((.+)\\)$", "funding rate $1% ($*2)"],
      ["^(VIX\\ 변동성지수\\(옵션시장\\ 공포\\)|하이일드\\ 스프레드\\(신용\\ 스트레스\\)|VIX\\ 기간구조\\(공포의\\ 급성도\\)|미\\ 10년물\\ 금리\\ 5일\\ 변화|미결제약정\\ 5일\\ 변화\\(수급\\)|미국\\ S\\&P500\\ 5일\\ 흐름|실현변동성\\ 비율\\(5/60일\\)|GK\\ 변동성\\(고저가\\ 기반\\)|김치\\ 프리미엄\\(국내\\ 수급\\)|장단기\\ 금리차\\(경기\\ 신호\\)|펀딩비\\ 변화\\(수급\\ 모멘텀\\)|공포탐욕지수\\(시장\\ 심리\\)|외국인\\ 5일\\ 순매수\\(z\\)|펀딩비\\(포지셔닝\\ 과열도\\)|기관\\ 5일\\ 순매수\\(z\\)|변동성\\ 레짐\\(단/장기\\)|기대인플레\\ 5일\\ 변화|달러인덱스\\ 5일\\ 변화|MACD\\ 히스토그램|비트코인\\ 5일\\ 흐름|원/달러\\ 5일\\ 변화|평균\\ 진폭\\(ATR\\)|변동성\\(20일\\)|10일\\ 수익률|20일\\ 모멘텀|20일선\\ 이격|50일선\\ 이격|60일\\ 모멘텀|RSI\\(14\\)|거래량\\ 이상치|5일\\ 수익률|RSI\\(7\\)|볼린저\\ 위치|전일\\ 수익률) 일 ([\\d\\.]+)%$",
       "$*1 $2%/day"],
      ["^(VIX\\ 변동성지수\\(옵션시장\\ 공포\\)|하이일드\\ 스프레드\\(신용\\ 스트레스\\)|VIX\\ 기간구조\\(공포의\\ 급성도\\)|미\\ 10년물\\ 금리\\ 5일\\ 변화|미결제약정\\ 5일\\ 변화\\(수급\\)|미국\\ S\\&P500\\ 5일\\ 흐름|실현변동성\\ 비율\\(5/60일\\)|GK\\ 변동성\\(고저가\\ 기반\\)|김치\\ 프리미엄\\(국내\\ 수급\\)|장단기\\ 금리차\\(경기\\ 신호\\)|펀딩비\\ 변화\\(수급\\ 모멘텀\\)|공포탐욕지수\\(시장\\ 심리\\)|외국인\\ 5일\\ 순매수\\(z\\)|펀딩비\\(포지셔닝\\ 과열도\\)|기관\\ 5일\\ 순매수\\(z\\)|변동성\\ 레짐\\(단/장기\\)|기대인플레\\ 5일\\ 변화|달러인덱스\\ 5일\\ 변화|MACD\\ 히스토그램|비트코인\\ 5일\\ 흐름|원/달러\\ 5일\\ 변화|평균\\ 진폭\\(ATR\\)|변동성\\(20일\\)|10일\\ 수익률|20일\\ 모멘텀|20일선\\ 이격|50일선\\ 이격|60일\\ 모멘텀|RSI\\(14\\)|거래량\\ 이상치|5일\\ 수익률|RSI\\(7\\)|볼린저\\ 위치|전일\\ 수익률) ([−+\\-]?[\\d\\.,]+)(%p|%)?\\((.+)\\)$",
       "$*1 $2$3 ($*4)"],
      ["^(VIX\\ 변동성지수\\(옵션시장\\ 공포\\)|하이일드\\ 스프레드\\(신용\\ 스트레스\\)|VIX\\ 기간구조\\(공포의\\ 급성도\\)|미\\ 10년물\\ 금리\\ 5일\\ 변화|미결제약정\\ 5일\\ 변화\\(수급\\)|미국\\ S\\&P500\\ 5일\\ 흐름|실현변동성\\ 비율\\(5/60일\\)|GK\\ 변동성\\(고저가\\ 기반\\)|김치\\ 프리미엄\\(국내\\ 수급\\)|장단기\\ 금리차\\(경기\\ 신호\\)|펀딩비\\ 변화\\(수급\\ 모멘텀\\)|공포탐욕지수\\(시장\\ 심리\\)|외국인\\ 5일\\ 순매수\\(z\\)|펀딩비\\(포지셔닝\\ 과열도\\)|기관\\ 5일\\ 순매수\\(z\\)|변동성\\ 레짐\\(단/장기\\)|기대인플레\\ 5일\\ 변화|달러인덱스\\ 5일\\ 변화|MACD\\ 히스토그램|비트코인\\ 5일\\ 흐름|원/달러\\ 5일\\ 변화|평균\\ 진폭\\(ATR\\)|변동성\\(20일\\)|10일\\ 수익률|20일\\ 모멘텀|20일선\\ 이격|50일선\\ 이격|60일\\ 모멘텀|RSI\\(14\\)|거래량\\ 이상치|5일\\ 수익률|RSI\\(7\\)|볼린저\\ 위치|전일\\ 수익률) (\\+\\(상승 우위\\)|−\\(하락 우위\\))$",
       "$*1 $*2"],
      ["^(VIX\\ 변동성지수\\(옵션시장\\ 공포\\)|하이일드\\ 스프레드\\(신용\\ 스트레스\\)|VIX\\ 기간구조\\(공포의\\ 급성도\\)|미\\ 10년물\\ 금리\\ 5일\\ 변화|미결제약정\\ 5일\\ 변화\\(수급\\)|미국\\ S\\&P500\\ 5일\\ 흐름|실현변동성\\ 비율\\(5/60일\\)|GK\\ 변동성\\(고저가\\ 기반\\)|김치\\ 프리미엄\\(국내\\ 수급\\)|장단기\\ 금리차\\(경기\\ 신호\\)|펀딩비\\ 변화\\(수급\\ 모멘텀\\)|공포탐욕지수\\(시장\\ 심리\\)|외국인\\ 5일\\ 순매수\\(z\\)|펀딩비\\(포지셔닝\\ 과열도\\)|기관\\ 5일\\ 순매수\\(z\\)|변동성\\ 레짐\\(단/장기\\)|기대인플레\\ 5일\\ 변화|달러인덱스\\ 5일\\ 변화|MACD\\ 히스토그램|비트코인\\ 5일\\ 흐름|원/달러\\ 5일\\ 변화|평균\\ 진폭\\(ATR\\)|변동성\\(20일\\)|10일\\ 수익률|20일\\ 모멘텀|20일선\\ 이격|50일선\\ 이격|60일\\ 모멘텀|RSI\\(14\\)|거래량\\ 이상치|5일\\ 수익률|RSI\\(7\\)|볼린저\\ 위치|전일\\ 수익률) ([−+\\-]?[\\d\\.,]+)(%p|%)?$",
       "$*1 $2$3"],
      // ⚠️ 여기 있던 ["^(\\d+)일 (.+)$", "$1 days: $2"]를 뺐다
      //    (2026-08-26). 뒷부분을 그대로 흘려보내는 규칙이라 모르는
      //    문장에서 "90 days: 수정과 같은 원칙입니다."처럼 **반쪽
      //    영어**를 만들었다. 반쪽은 한국어보다 나쁘다 — 읽는 사람이
      //    고장으로 읽는다. 날짜가 든 문장은 문장마다 적는다.
      ["^수수료·세금·미끄러짐 · 위 이익은 이걸 뺀 값 · 이 기록일에 ([\\d,]+)원$",
       "Fees, taxes and slippage · the figure above is net of this · KRW $1 on this record day"],
      ["^([\\d,\\.]+)개 몫$", "the equivalent of $1"],
      ["^([\\d,]+)원 ·$", "KRW $1 ·"],
      ["^([\\d,]+)원입니다 — 지금 이 시스템은 그보다$",
       "KRW $1 — this system is currently"],
      ["^([\\d,]+)원 (뒤집니다|앞섭니다)$", "KRW $1 behind/ahead"],
      ["^원금 대비 · 누적 기준 · 오늘 (.+) · 마지막 기록 (.+)$",
       "against principal · cumulative · today $1 · last record $2"],
      ["^(\\d+)일차$", "day $1"],
      ["^현재 구조 (.+) · 판정 기준 (\\d+)일$",
       "current structure $1 · $2 days required"],
      ["^최근 오디션 (\\d+)회 · 승격 (\\d+)회$",
       "$1 auditions recently · $2 promotions"],
      ["^연 ([\\d\\.]+)%$", "$1% a year"],
      ["^· 사전 추정 ([\\d\\.]+)% · 배수 ([\\d\\.]+)배$",
       "· prior estimate $1% · multiplier $2x"],
      ["^([\\d\\.]+)%\\/일$", "$1% a day"],
      ["^· (\\d+)일째$", "· day $1"],
      ["^(\\d+)종목 · 시세 기준 (.+)$", "$1 symbols · prices as of $2"],
      ["^→ ([\\d,]+)원$", "→ KRW $1"],
      ["^종목 매입금액 ([\\d,]+)원 \\+ 현금 ([\\d,]+)원$",
       "cost basis KRW $1 + cash KRW $2"],
      ["^평가금액은 장부가 마지막으로 확인한 가격 기준입니다 — 실시간 시세가 아닙니다\\. 합계는 현금을 포함한 계좌 자산입니다\\. 해외 종목\\(미국주식·코인\\)은 원\\/달러 ([\\d,\\.]+)원 을 적용해 원화로 환산했습니다\\.$",
       "Market value uses the last price the ledger confirmed — not a live quote. The total is account equity including cash. Overseas holdings (US stocks and crypto) were converted at KRW $1 per USD."],
      ["^최근 체결 (\\d+)건 · 체결되지 않은 주문 (\\d+)건$",
       "$1 recent fills · $2 order(s) that never filled"],
      ["^매일 새벽 확정 기록 · 오늘 보유 (\\d+)종목 표시 · 관망 (\\d+)종목은 \'자세히 보기\'에서$",
       "Settled each morning · showing the $1 symbols held today · the $2 standing aside are under \"Show more\""],
      ["^(\\d+)% \\(판정 불가 (\\d+)~(\\d+)% · n=(\\d+)\\)$",
       "$1% (not conclusive, $2-$3% · n=$4)"],
      ["^실전 (\\d+)% \\(판정 불가 (\\d+)~(\\d+)% · n=(\\d+)\\)$",
       "live $1% (not conclusive, $2-$3% · n=$4)"],
      ["^오늘 목표 ([\\d\\.]+)% · ([\\d\\.]+)주$", "today's target $1% · $2 shares"],
      ["^→ ([\\d\\.]+)% 예정$", "→ $1% planned"],
      ["^([\\d\\.]+)주$", "$1 shares"],
      ["^백테스트 가정보다 실제 체결이 불리하면 그 사실을 그대로 표시합니다 \\(최근 (\\d+)일 · (\\d+)건\\)\\.$",
       "When real fills come out worse than the backtest assumed, we show that as it is (last $1 days · $2 fills)."],
      ["^\\((\\d{4}-\\d{2}-\\d{2})~(\\d{4}-\\d{2}-\\d{2}) · (\\d+)종목 ·$",
       "($1 to $2 · $3 symbols ·"],
      ["^\\(지금 노출 ([\\d\\.]+)% 기준 ·$", "(at the current exposure of $1% ·"],
      ["^최대 비중 종목\\(([\\d\\.]+)%\\) 하루 -50%$",
       "The largest holding ($1% of the account) falls 50% in a day"],
      ["^🟡 노출 절반 \\((\\d+)일째\\)$", "🟡 exposure halved (day $1)"],
      ["^지난 기록 (\\d+)건 더 보기$", "Show $1 more past entries"],
      ["^킬스위치 발동 (\\d+)회 — 첫 발동 (.+) \\(실제 급락일과 일치\\) · 실현 변동성이 목표보다 높습니다: 변동성 추정은 폭락을 하루이틀 늦게 따라갑니다\\. 이 지연은 구조적이며 숨기지 않습니다\\.$",
       "Kill switch fired $1 times — first on $2 (matching a real crash day) · realised volatility runs above target: a volatility estimate follows a crash a day or two late. That lag is structural and we do not hide it."],
      ["^표본 (\\d+)봉 · 95% 신뢰구간 (\\d+)~(\\d+)% — 구간이 50%를 품고 있어 동전던지기와 구별되지 않습니다$",
       "Sample of $1 bars · 95% confidence interval $2-$3% — the interval contains 50%, so it is indistinguishable from a coin flip"],
      ["^표본 (\\d+)봉 · 95% 신뢰구간 (\\d+)~(\\d+)% — 동전던지기\\(50%\\)와 구별됩니다$",
       "Sample of $1 bars · 95% confidence interval $2-$3% — distinguishable from a coin flip (50%)"],
      ["^종목계좌 ([\\d\\.]+)%$", "symbol account $1%"],
      ["^통합 ([\\d\\.]+)%$", "combined $1%"],
      ["^투자 중 ([\\d,]+)원$", "invested KRW $1"],
      ["^현금 ([\\d,]+)원$", "cash KRW $1"],
      ["^총 (\\d+)건 · 최근 (.+) · 이 목록은 깃 커밋 이력에서 자동으로 뽑습니다 — 사람이 따로 적는 일지가 아니라, 개선이 저장소에 합쳐지는 순간 남는 기록의 사본입니다\\. 자동 배치의 운행 기록\\(장부 커밋\\)은 제외합니다\\.$",
       "$1 entries in total · most recent $2 · this list is pulled automatically from the git commit history — not a diary someone keeps, but a copy of what is left the moment a fix is merged. The automated batch's own run records (ledger commits) are excluded."],
      ["^— 엣지 미입증이라 목표 변동성을 연 ([\\d\\.]+)%로 제한 중$",
       "— the edge is unproven, so target volatility is capped at $1% a year"],
      ["^피처 드리프트 (\\d+)종목$", "Feature drift on $1 symbols"],
      ["^— 최근 분포가 학습 시점과 통계적으로 다릅니다\\(표본 잡음 범위를 넘음\\)\\. 판단 신뢰도에 주의$",
       "— the recent distribution differs statistically from the one at training time (beyond sampling noise). Treat the calls with caution"],
      ["^검증 게이트: 관망 (\\d+)종목$", "Validation gate: standing aside on $1 symbols"],
      ["^검증 게이트: 절반 감쇠 (\\d+)종목$", "Validation gate: halved on $1 symbols"],
      ["^— 이상 급변 (\\d+)건 · 거래량 0 (\\d+)건이 원천 데이터에 있었습니다$",
       "— the source data contained $1 abnormal jumps and $2 zero-volume bars"],
      ["^살 수 없는 종목 (\\d+)개$", "$1 symbols that could not be bought"],
      ["^예산을 끌어 쓴 종목 (\\d+)개$", "$1 symbols that borrowed budget"],
      ["^페이퍼 매매 부분 실패 (\\d+)종목$", "Paper trading partly failed on $1 symbol(s)"],
      ["^(\\d{4}-\\d{2}-\\d{2}) · (.+) → (.+)$", "$1 · $2 → $3"],
      ["^마지막 갱신: (.+)$", "Last updated: $1"],
      // ⚠️ 수정 공지의 날짜도 장부(amended.on)에서 온다 — 사전 열쇠에 박으면
      //    공지가 갱신되는 날 영어가 사라진다. 2026-08-26에 새로 붙인
      //    검사(test_no_dictionary_key_pins_a_date)가 남아 있던 이 하나를
      //    찾아냈다. 화면이 괄호를 붙이는 쪽과 안 붙이는 쪽이 둘 다 있다
      //    (intraday·index).
      ["^수정 공지 \\((\\d{4}-\\d{2}-\\d{2})\\)$", "Amendment notice ($1)"],
      // 판정 시계의 수정 공지는 **문장 전체가 실행 중에 조립된다** — 날짜도
      // 이력 개수도 이력 목록도 장부에서 온다. 사전에 통째로 넣으면 구조
      // 변경이 하나 늘어나는 날 영어가 사라진다(2026-08-26 검사가 잡음).
      // 꼬리(이력 목록)는 한국어로 남는다 — 지어내지 않는 것이 규칙이다.
      ["^📝 수정 공지 (\\d{4}-\\d{2}-\\d{2}): 개선해도 시계는 리셋하지 않습니다 — 대신 변경 이력을 전부 공개합니다\\. 이력 (\\d+)건: (.+)$",
       "📝 Amendment notice $1: improving the system does not reset the clock — every change is published instead. $2 changes: $3"],
      ["^📝 수정 공지 (\\d{4}-\\d{2}-\\d{2}): 개선해도 시계는 리셋하지 않습니다 — 대신 변경 이력을 전부 공개합니다\\. \\(아직 변경 없음\\)$",
       "📝 Amendment notice $1: improving the system does not reset the clock — every change is published instead. (no changes yet)"],
      ["^의 숫자입니다 — 그냥 보유도 살 때 한 번은 수수료를 냅니다\\((\\d{4}-\\d{2}-\\d{2}) 교정\\)\\. 본 계좌는 하루 한 번 새벽에 확정되므로 마지막 확정일\\((\\d{4}-\\d{2}-\\d{2})\\) 기준입니다\\. 실험 시작\\((\\d{4}-\\d{2}-\\d{2})\\) 이후의 변화율끼리 비교합니다 — 표본이 판정 기준\\(위\\)을 채우기 전의 우열은 운과 구별되지 않습니다\\.$",
       " figures — buy & hold also pays a fee once, at purchase (corrected $1). The main account settles once a day at dawn, so it is shown as of its last settlement ($2). The comparison is between rates of change since the experiment began ($3) — any lead before the sample meets the criteria above is indistinguishable from luck."],
      ["^평균 수익률의 95% 하한이 0 이하 — 우연과 구별되지 않는다 — 1배로 둡니다$",
       "the 95% lower bound on the average return is at or below zero — indistinguishable from chance — held at 1x"],
      // 실측값이 든 자리 — 장부에서 온 숫자라 **매 회차 바뀐다**.
      // 사전 열쇠에 값을 박으면(옛 "실측 최악 113분") 다음 측정에 만료된다.
      // 날짜에서 배운 것과 같은 병이다(2026-08-26) — 그때는 날짜만 규칙으로
      // 옮기고 **측정 숫자는 놓쳤다.** 형제를 찾기 전까지 고친 게 아니다.
      // 같은 병의 셋째·넷째 얼굴(2026-08-27) — 전략 수·분산 거리·왕복비용은
      // 전부 장부에서 계산돼 매일 바뀐다. 옛 열쇠는 24종/27%/46.8bp/52건에
      // 박혀 있어 값이 바뀌자 그대로 만료됐다.
      ["^입니다 — 전략은 ([\\d,]+)종인데 그중 가장 큰 하나가 자금의$",
       "are different questions — there are $1 strategies, and the largest single one holds"],
      ["^를 쥐고 있습니다\\. 상관까지 고려한 비중과의 거리는 ([\\d.]+)%입니다\\(([\\d,]+)계좌 실측 · 재기만 하고 매매에는 쓰지 않습니다 — 배분을 바꾸면 판정 시계가 리셋되기 때문입니다\\)\\.$",
       "of the money. The distance from a correlation-aware weighting is $1% (measured over $2 accounts · measured only, never traded on — changing the allocation would reset the verdict clock)."],
      ["^왕복비용 ([\\d.]+)bp\\(실측 · 표본 ([\\d,]+)건\\) 기준 — 이보다 덜 벗어나면 그대로 둡니다$",
       "Based on a $1bp round-trip cost (measured · $2 samples) — anything inside that is left alone"],
      ["^실측 최악 ([\\d,]+)분$", "worst observed gap $1 min"],
      ["^· 감시 주기 예약 ([\\d,]+)분 /$",
       "· watch scheduled every $1 min /"],
      ["^원금\\(([\\d,]+)원\\) 대비$",
       "against the principal (KRW $1)"],
      ["^🔒 엣지 미입증 — 검증 목표로 잠금 중\\. 판정 시계 진행 중 — (.+) (\\d+)일차\\/(\\d+)일 · 그동안 개선 (\\d+)회 공개$",
       "🔒 Edge unproven — locked to the validation target. Verdict clock running — $1, day $2 of $3 · $4 improvements published in the meantime"],
      ["^\\/ (\\d+)종목 · 가장 심한 곳: (.+)$",
       "/ $1 symbols · worst offenders: $2"],
      ["^과최적화 확률\\(PBO\\) (\\d+)% — 문서가 \'버릴 것\'이라 정한 선\\((\\d+)%\\)을 넘었습니다\\. 오늘 이 종목은 관망합니다\\.$",
       "Overfitting probability (PBO) $1% — past the $2% line the documentation defines as \"discard\". This symbol stands aside today."],
      // ⚠️ 같은 문장에 **꼬리가 붙는 경우**가 따로 있다(만료된 실패 기록).
      //    위 규칙은 "$" 로 끝나서 꼬리가 붙는 순간 통째로 안 맞았고,
      //    영어 화면에 한국어 문장이 그대로 남았다(2026-08-29 실측).
      ["^과최적화 확률\\(PBO\\) (\\d+)% — 문서가 \'버릴 것\'이라 정한 선\\((\\d+)%\\)을 넘었습니다\\. 오늘 이 종목은 관망합니다\\. \\(기록이 (\\d+)일 전 것이지만 판정은 그대로다\\)$",
       "Overfitting probability (PBO) $1% — past the $2% line the documentation defines as \"discard\". This symbol stands aside today. (The record is $3 days old, but the verdict stands.)"],
      ["^검증 기록이 (\\d+)일 전 것입니다\\(유통기한 (\\d+)일\\) — 오늘의 판정으로 쓸 수 없어 비중을 절반으로 줄입니다\\.$",
       "The validation record is $1 days old (it keeps for $2 days) — it cannot stand as today's verdict, so the weight is halved."],
      // ⚠️ **전략 이름이 문장 안에 들어간다.** 사전이 문장 통째로 열쇠를
      //    삼으므로, 새 전략이 챔피언이 되는 날 그 문장만 조용히 한국어로
      //    남는다 — 실제로 bollinger·turtle·cross_rank가 그렇게 남았다.
      //    이름은 코드값이라 번역하지 않고 그대로 싣는다.
      ["^(.+) 전략 신호에 따름$", "following the $1 strategy's signal"],
      ["^규칙이 판단 \\((.+)\\)$", "decided by a rule ($1)"],
      ["^CPCV 최악 경로 수익률 (.+) \\(기준: (.+) 초과\\) · 과최적화 확률\\(PBO\\) (\\d+)% > 기준 (\\d+)% · 보정 샤프\\(DSR\\) (.+) < 기준 (.+) — 비중을 절반으로 줄입니다\\.$",
       "CPCV worst-path return $1 (threshold: above $2) · overfitting probability (PBO) $3% > threshold $4% · deflated Sharpe (DSR) $5 < threshold $6 — the weight is halved."],
      ["^CPCV 최악 경로 수익률 (.+) \\(기준: (.+) 초과\\) · 보정 샤프\\(DSR\\) (.+) < 기준 (.+) — 비중을 절반으로 줄입니다\\.$",
       "CPCV worst-path return $1 (threshold: above $2) · deflated Sharpe (DSR) $3 < threshold $4 — the weight is halved."],
      ["^과최적화 확률\\(PBO\\) (\\d+)% > 기준 (\\d+)% · 보정 샤프\\(DSR\\) (.+) < 기준 (.+) — 비중을 절반으로 줄입니다\\.$",
       "Overfitting probability (PBO) $1% > threshold $2% · deflated Sharpe (DSR) $3 < threshold $4 — the weight is halved."],
      ["^보정 샤프\\(DSR\\) (.+) < 기준 (.+) — 비중을 절반으로 줄입니다\\.$",
       "Deflated Sharpe (DSR) $1 < threshold $2 — the weight is halved."],
      ["^\\((\\d+)\\/(\\d+)건\\)$", "($1 of $2)"],
      ["^\\((\\d+)건\\)$", "($1 cases)"],
      ["^모델이 오른다고 본 날\\((\\d+)건\\)은 실제로 ([\\d\\.]+)% 올랐고, 내린다고 본 날\\((\\d+)건\\)은 ([\\d\\.]+)% 올랐습니다 — 순서가 뒤집혀 있습니다\\. 표본이 얇아 확정은 아니지만, 이 시스템이 확률을 금액으로 바꾸는 이상 가장 눈여겨볼 신호입니다\\.$",
       "On the $1 days the model called a rise, $2% actually rose; on the $3 days it called a fall, $4% rose — the order is inverted. The sample is thin so this is not settled, but as long as this system turns probabilities into amounts it is the signal most worth watching."],
      ["^오늘 ([-−+][\\d\\.]+)%$", "today $1%"],
      ["^· 최대낙폭 (.+)$", "· max drawdown $1"],
      ["^매수 (\\d+)%$", "Buy $1%"],
      ["^매도 (\\d+)%$", "Sell $1%"],
      ["^(\\d+)회$", "$1 times"],
      ["^([\\d\\.]+)% · 목표 ([\\d,]+)원$", "$1% · target KRW $2"],
      ["^(\\d+)개 \\/ 후보 중 상위 (\\d+)$", "$1 of the top $2 candidates"],
      ["^상위 비중: (.+)$", "Largest weights: $1"],
      ["^신뢰도 곡선 · 표본 (\\d+)일$", "Reliability curve · sample of $1 days"],
      ["^(\\d{4}-\\d{2}-\\d{2})에 원화 계좌로 다시 열었습니다 — 이전 기록은$",
       "Reopened as a won account on $1 — the earlier record is"],
      ["^([\\d,]+)원으로 시작한 가상 자금 · 최대낙폭$",
       "play money started at KRW $1 · max drawdown"],
      ["^100만 챌린지 · ([\\d,]+)원 → 1억$",
       "1M Won Challenge · KRW $1 → 100,000,000"],
      ["^([\\d,]+)원으로 시작$", "started at KRW $1"],
      ["^해 그 종목만 매매한 결과라, (\\d+)개를 합치면 ([\\d,]+)원가 됩니다\\.$",
       "and traded that symbol alone, so adding up all $1 of them comes to KRW $2."],
      ["^100만 챌린지 본 계좌\\(원금 ([\\d,]+)원\\)와는 별개의 장부$",
       "a ledger separate from the 1M Won Challenge's main account (principal KRW $1)"],
      ["^입니다 — 각각$", "— each",],
      // ── 판단 설명의 절(clause) — 위 clauses()가 끊어서 넘긴다 ──
      ["^매수 \\+(\\d+)%$", "Buy +$1%"],
      ["^매도 ([-−]\\d+)%$", "Sell $1%"],
      ["^소액 매수 \\+([\\d\\.]+)%$", "Small buy +$1%"],
      ["^소액 매도 ([-−][\\d\\.]+)%$", "Small sell $1%"],
      ["^이동평균 교차: (\\d+)일선이 (\\d+)일선 위 \\(상승 추세 지속 판단\\)$",
       "Moving-average cross: the $1-day line is above the $2-day line (read as an uptrend continuing)"],
      // ⚠️ 이 규칙은 **한 번도 맞은 적이 없었다**(2026-08-29 실측). 코드가
      //    찍는 글자는 "하락/횡보 추세"인데 사전에는 "하락 추세"라고 적혀
      //    있었다 — 사전을 실제 문장이 아니라 짐작으로 썼다. ma_cross는
      //    지금 운용 중인 챔피언이라(코인 2종), 그 종목이 하락·횡보로
      //    돌아선 날마다 영어 화면에 한국어가 남았다.
      ["^이동평균 교차: (\\d+)일선이 (\\d+)일선 아래 \\(하락\\/횡보 추세 판단\\)$",
       "Moving-average cross: the $1-day line is below the $2-day line (read as a downtrend or a sideways market)"],
      ["^로지스틱회귀·풀링\\(전 종목 합산 학습\\) 모델이 내일 상승확률을 약 (\\d+)%로 추정\\(기준 (\\d+)% 초과\\)$",
       "the logistic-regression, pooled (trained on every symbol together) model puts tomorrow's chance of a rise at about $1% (above the $2% threshold)"],
      ["^로지스틱회귀·풀링\\(전 종목 합산 학습\\) 모델의 상승확률이 기준\\((\\d+)%\\)에 못 미쳐 관망$",
       "the logistic-regression, pooled (trained on every symbol together) model's chance of a rise falls short of the $1% threshold, so it stands aside"],
      ["^로지스틱회귀 모델이 내일 상승확률을 약 (\\d+)%로 추정\\(기준 (\\d+)% 초과\\)$",
       "the logistic-regression model puts tomorrow's chance of a rise at about $1% (above the $2% threshold)"],
      ["^로지스틱회귀 모델의 상승확률이 기준\\((\\d+)%\\)에 못 미쳐 관망$",
       "the logistic-regression model's chance of a rise falls short of the $1% threshold, so it stands aside"],
      ["^랜덤포레스트·풀링\\(전 종목 합산 학습\\) 모델이 내일 상승확률을 약 (\\d+)%로 추정\\(기준 (\\d+)% 초과\\)$",
       "the random-forest, pooled (trained on every symbol together) model puts tomorrow's chance of a rise at about $1% (above the $2% threshold)"],
      ["^랜덤포레스트·풀링\\(전 종목 합산 학습\\) 모델의 상승확률이 기준\\((\\d+)%\\)에 못 미쳐 관망$",
       "the random-forest, pooled (trained on every symbol together) model's chance of a rise falls short of the $1% threshold, so it stands aside"],
      ["^랜덤포레스트 모델이 내일 상승확률을 약 (\\d+)%로 추정\\(기준 (\\d+)% 초과\\)$",
       "the random-forest model puts tomorrow's chance of a rise at about $1% (above the $2% threshold)"],
      ["^랜덤포레스트 모델의 상승확률이 기준\\((\\d+)%\\)에 못 미쳐 관망$",
       "the random-forest model's chance of a rise falls short of the $1% threshold, so it stands aside"],
      ["^그라디언트부스팅·풀링\\(전 종목 합산 학습\\) 모델이 내일 상승확률을 약 (\\d+)%로 추정\\(기준 (\\d+)% 초과\\)$",
       "the gradient-boosting, pooled (trained on every symbol together) model puts tomorrow's chance of a rise at about $1% (above the $2% threshold)"],
      ["^그라디언트부스팅·풀링\\(전 종목 합산 학습\\) 모델의 상승확률이 기준\\((\\d+)%\\)에 못 미쳐 관망$",
       "the gradient-boosting, pooled (trained on every symbol together) model's chance of a rise falls short of the $1% threshold, so it stands aside"],
      ["^그라디언트부스팅 모델이 내일 상승확률을 약 (\\d+)%로 추정\\(기준 (\\d+)% 초과\\)$",
       "the gradient-boosting model puts tomorrow's chance of a rise at about $1% (above the $2% threshold)"],
      ["^그라디언트부스팅 모델의 상승확률이 기준\\((\\d+)%\\)에 못 미쳐 관망$",
       "the gradient-boosting model's chance of a rise falls short of the $1% threshold, so it stands aside"],
      ["^앙상블·풀링\\(전 종목 합산 학습\\) 모델이 내일 상승확률을 약 (\\d+)%로 추정\\(기준 (\\d+)% 초과\\)$",
       "the ensemble, pooled (trained on every symbol together) model puts tomorrow's chance of a rise at about $1% (above the $2% threshold)"],
      ["^앙상블·풀링\\(전 종목 합산 학습\\) 모델의 상승확률이 기준\\((\\d+)%\\)에 못 미쳐 관망$",
       "the ensemble, pooled (trained on every symbol together) model's chance of a rise falls short of the $1% threshold, so it stands aside"],
      ["^앙상블 모델이 내일 상승확률을 약 (\\d+)%로 추정\\(기준 (\\d+)% 초과\\)$",
       "the ensemble model puts tomorrow's chance of a rise at about $1% (above the $2% threshold)"],
      ["^앙상블 모델의 상승확률이 기준\\((\\d+)%\\)에 못 미쳐 관망$",
       "the ensemble model's chance of a rise falls short of the $1% threshold, so it stands aside"],
      ["^사이징: 신호 원비중 (\\d+)% → 변동성 타깃 조절 후 (\\d+)%$",
       "sizing: raw signal weight $1% → $2% after the volatility target"],
      // ── 전략별 해설 문장 (quant/live/explain.py의 가지들) ──────────────
      // ⚠️ 여기 빠진 가지는 **그 전략이 챔피언이 되는 날** 영어 화면에
      //    한국어로 튀어나온다. 사전은 그날까지 아무 말도 안 한다.
      ["^채널 돌파: 최근 돌파 후 추세 추종 중$",
       "channel breakout: riding the trend after a recent breakout"],
      ["^채널 돌파: (\\d+)일 최고가\\(([\\d,\\.]+)\\) 돌파 대기$",
       "channel breakout: waiting for a break above the $1-day high ($2)"],
      ["^모멘텀: 최근 (\\d+)일 수익률 ([-−+][\\d\\.]+)% \\(상승 흐름 추종\\)$",
       "momentum: $2% over the last $1 days (riding the up-move)"],
      ["^모멘텀: 최근 (\\d+)일 수익률 ([-−+][\\d\\.]+)% \\(흐름 약화 → 축소\\/관망\\)$",
       "momentum: $2% over the last $1 days (momentum fading → trim or stand aside)"],
      ["^RSI\\((\\d+)\\)=(\\d+) \\(과매도 반등 노림\\)$",
       "RSI($1)=$2 (playing for an oversold bounce)"],
      ["^RSI\\((\\d+)\\)=(\\d+) \\(과매수 경계\\)$",
       "RSI($1)=$2 (wary of overbought)"],
      ["^RSI\\((\\d+)\\)=(\\d+) \\(중립 구간\\)$",
       "RSI($1)=$2 (neutral zone)"],
      ["^매매 없이 보유: 이 종목은 오디션에서 \\*\\*아무것도 하지 않는 쪽\\*\\*이 AI 전략을 이겼습니다\\(2단계 심사 통과\\)\\. 매수·매도 없이 계속 들고 갑니다 — 하락도 그대로 겪습니다$",
       "hold without trading: for this symbol, **doing nothing** beat the AI strategies in the audition (it passed both rounds). It is simply held — no buying, no selling — and it takes the drawdowns as they come."],
      ["^챔피언 전략 신호에 따름$", "following the champion strategy's signal"],
      ["^🏛 의회 운용: (.+)$", "🏛 Parliament: $1"],
      ["^참고: 전 종목 합산으로 모델이 (\\d+)%±(\\d+)%p라 말한 (\\d+)번의 실제 상승 비율 (\\d+)% \\(95% 신뢰구간 (\\d+)%~(\\d+)% · 보합 (\\d+)일 포함 · 봉이 빠진 (\\d+)번은 제외 · 이 종목 단독 표본은 (\\d+)번으로 축적 중\\)$",
       "note: pooled across every symbol, of the $3 times the model said $1%±$2%pt, $4% actually rose (95% CI $5-$6% · including $7 flat days · excluding $8 rounds with a missing bar · this symbol alone is still accumulating, $9 so far)"],
      ["^참고: 전 종목 합산으로 모델이 (\\d+)%±(\\d+)%p라 말한 (\\d+)번의 실제 상승 비율 (\\d+)% \\(95% 신뢰구간 (\\d+)%~(\\d+)% · 봉이 빠진 (\\d+)번은 제외 · 이 종목 단독 표본은 (\\d+)번으로 축적 중\\)$",
       "note: pooled across every symbol, of the $3 times the model said $1%±$2%pt, $4% actually rose (95% CI $5-$6% · excluding $7 rounds with a missing bar · this symbol alone is still accumulating, $8 so far)"],
      ["^참고: 이 확률대\\((\\d+)%±(\\d+)%p\\)의 과거 성적은 표본 축적 중 \\(종목 (\\d+)건부터 표시\\)$",
       "note: the past record in this probability band ($1%±$2%pt) is still accumulating (shown from $3 cases per symbol)"],
      ["^(\\d{4}-\\d{2}-\\d{2}) 기준$", "as of $1"],
      ["^(\\d+)종목$", "$1 symbols"],
      ["^(\\d+)봉$", "$1 bars"],
      ["^(\\d+)회$", "$1 runs"],
      ["^연환산 샤프 ([\\d\\.]+)$", "an annualised Sharpe of $1"],
      ["^\\((\\d{4}-\\d{2}-\\d{2}) 추가\\) 이 보고서는$",
       "(added $1) This report always publishes"],
      ["^\\((\\d{4}-\\d{2}-\\d{2})\\) 사장님이 \"숏도 레버리지도 열어 달라\"고 하셔서$",
       "($1) When the owner asked to open up both shorting and leverage,"],
      ["^(\\d+)일$", "$1 days"],
      ["^중$", "of which"],
      ["^\\((\\d+)일\\), 두 계좌 일수익 차이의 통계 검정\\(유의수준 5%\\)\\. (.+)에 중간 참고 판독\\(확정 아님\\)\\.$",
       "($1 days), a statistical test of the daily-return difference between the two accounts (5% significance). An interim read on $2 (not binding)."],
      ["^([-−+])([\\d,]+)원$", "$1KRW $2"],
      ["^([\\d,\\.]+)개$", "$1"],
      ["^\\(([+−][\\d\\.]+)%\\) · 최대낙폭$", "($1) · max drawdown"],
      ["^([−+]?[\\d,\\.]+)원 손해$", "KRW $1 loss"],
      ["^([−+]?[\\d,\\.]+)원 이익$", "KRW $1 profit"],
      ["^(\\d{4}-\\d{2}-\\d{2}) 주$", "Week of $1"],
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
      ["^(\\d{4}-\\d{2}-\\d{2}) 새벽 확정$", "settled at dawn, $1"],
      ["^통합 계좌 \\(오늘 (\\d+)종목 보유 / 후보 (\\d+)종목 · 시작 ([\\d,]+)원\\)$",
       "Combined account (holding $1 symbols today / $2 candidates · started at KRW $3)"],
      ["^원금\\(매칭 포함\\) ([\\d,]+)원 ·\\s+실력 지표\\(TWR\\)$",
       "Principal (including the matching deposit) KRW $1 · skill measure (TWR)"],
      ["^·\\s+최대낙폭 ([−+\\-][\\d\\.]+)%$", "· max drawdown $1%"],
      ["^참고: 이 확률대\\((\\d+)%±(\\d+)%p\\)의 과거 성적은 표본 축적 중 \\(종목 n=(\\d+) · 합산 n=(\\d+), (\\d+)건부터 표시\\)$",
       "note: the past record in this probability band ($1%±$2%pt) is still accumulating (symbol n=$3 · pooled n=$4, shown from $5 cases)"],
      ["^참고: 전 종목 합산으로 모델이 (\\d+)%±(\\d+)%p라 말한 (\\d+)건의 실제 상승 비율 (\\d+)% \\(95% 신뢰구간 (\\d+)%~(\\d+)% · 보합 (\\d+)일 포함 · 이 종목 단독 표본은 (\\d+)건으로 축적 중\\)$",
       "note: pooled across every symbol, of the $3 cases where the model said $1%±$2%pt, $4% actually rose (95% CI $5-$6% · including $7 flat day(s) · this symbol alone is still accumulating, $8 so far)"],
      ["^🛡 실적 가드: 발표\\((\\d{4}-\\d{2}-\\d{2})\\) 임박 → 비중 절반$",
       "🛡 Earnings guard: the release ($1) is close → weight halved"],
      ["^(\\d{4}-\\d{2}-\\d{2}) 개장 시가$", "the opening price on $1"],

      ["^오늘 목표 ([−+\\-]?[\\d\\.]+)%$", "Today's target $1%"],
      ["^지난 기록 (\\d+)건 더 보기$", "Show $1 earlier entries"],
      ["^총 (\\d+)건$", "$1 entries in total"],
      ["^최근 (\\d{4}-\\d{2}-\\d{2})$", "latest $1"],
      ["^의 도전자를 검증해 대부분을 떨어뜨렸습니다\\. 최근 오디션 (\\d+)회$",
       "challengers have been vetted and most were turned down. $1 auditions recently"],
      ["^후보 ([\\d,]+)명 중 승격 (\\d+)회\\.$", "$1 candidates, $2 promoted."],
      ["^1주 값에 못 미쳐 못 산 종목 (\\d+)개$",
       "$1 symbols went unbought because the budget fell short of a single share"],
      ["^목표를 잡은 (\\d+)곳 중 (\\d+)곳만 담김 \\(주문액이 최소 금액에 못 미쳐 (\\d+)곳 · 최근에 사고팔아 쉬는 중이라 (\\d+)곳\\)$",
       "only $2 of the $1 targeted positions were filled (order value below the minimum in $3 · resting after a recent trade in $4)"],
      ["^— (.+)\\. 과최적화 확률이 '버릴 것' 기준을 넘어 오늘 이 종목은 사지 않습니다$",
       "— $1. Their overfitting probability crossed the \"discard\" line, so they are not bought today"],
      ["^— (.+)\\. 검증 기준 미달이거나 아직 측정되지 않아 비중을 절반으로 줄였습니다 \\(측정 안 됨은 '통과'가 아닙니다\\)$",
       "— $1. They fell short of the validation bar or have not been measured yet, so their weight was halved (not measured is not a pass)"],
      ["^— 배정 예산이 1주 값에 못 미쳐 담기지 못했습니다\\((.+)\\)\\. 분산 종목 수가 표시보다 적습니다$",
       "— the allocated budget fell short of one share, so these were left out ($1). The count of diversified holdings is smaller than shown"],
      ["^— ([^·]+)\\(([\\d,]+)원/배정 ([\\d,]+)원\\)\\. 대신 ([^·]+)$",
       "— $*1 (KRW $2 / allocated KRW $3). In their place, $*4"],
      ["^([^·]+)\\(([\\d,]+)원/배정 ([\\d,]+)원\\)\\. 대신 ([^·]+)$",
       "$*1 (KRW $2 / allocated KRW $3). In their place, $*4"],
      ["^— ([^·]+)\\(([\\d,]+)원/배정 ([\\d,]+)원\\)$",
       "— $*1 (KRW $2 / allocated KRW $3)"],
      ["^([^·]+)\\(([\\d,]+)원/배정 ([\\d,]+)원\\)$",
       "$*1 (KRW $2 / allocated KRW $3)"],
      ["^([^·]+)이\\(가\\) 자리를 내줬습니다\\. 확신도가 높은 쪽부터 채우기 때문이며, 그만큼 종목 수는 줄어듭니다$",
       "$*1 gave up their slots. Positions are filled from the highest conviction down, and the number of holdings shrinks accordingly"],
      ["^— (.+)\\. 그 종목은 그날 판단·기록이 없고 이전 판단을 그대로 씁니다 \\((\\d{4}-\\d{2}-\\d{2})\\)$",
       "— $1. There was no decision or record for it that day, so the previous decision stands ($2)"],
      ["^([^·]+) → ([^·]+)$", "$*1 → $*2"],
      ["^([\\d\\.]+)% · 목표 ([\\d,]+)원$", "$1% · target KRW $2"],
      ["^판정 (\\d{4}-\\d{2}-\\d{2})$", "verdict due $1"],
      ["^해 그 종목만 매매한 결과라,\\s+(\\d+)개를 합치면 ([\\d,]+)원가 됩니다\\.$",
       "and traded that symbol alone, so all $1 together come to KRW $2."],
      ["^최근 오디션 (\\d+)회 · 후보 ([\\d,]+)명 중 승격 (\\d+)회$",
       "$1 auditions recently · $3 promotions out of $2 candidates"],
      ["^실측 개장 갭 vs 백테스트 가정 · 최근 (\\d+)일 · (\\d+)건$",
       "Measured opening gap vs the backtest assumption · last $1 days · $2 samples"],
      ["^(\\d+)건$", "$1 samples"],
      ["^\\((\\d+)일 ([−+\\-][\\d\\.]+)%\\)$", "($1-day $2%)"],
      ["^/ 판정 기준 (\\d+)일 \\((\\d{4}-\\d{2}-\\d{2})~\\)\\s+— 엣지 유무는 이 시계가 다 돌기 전엔 판정하지 않습니다\\. 그 전의 수익률은 통계가 아니라 소음일 수 있습니다\\.$",
       "/ verdict window $1 days (from $2) — whether there is an edge is not judged until this clock has run out. Returns before then may be noise rather than statistics."],
      ["^(\\d{4}-\\d{2}-\\d{2})\\(v([\\d\\.]+)\\)부로 회계 기준을 보수적으로 변경했습니다\\s*— 이전 숫자는 낙관적이었습니다\\.$",
       "From $1 (v$2) the accounting basis was made conservative — the earlier numbers were optimistic."],
      ["^시장 전체\\(지수\\)$", "the market as a whole (an index)"],
      ["^([\\d\\.]+)% · 목표 (.+)$", "$1% · target $*2"],
      ["^([^·—]+) ([−+\\-][\\d\\.]+)%$", "$*1 $2%"],
      ["^참고\\(장부 (\\d{4}-\\d{2}-\\d{2}) 그대로\\): 후보$",
       "For reference (straight from the ledger, $1): candidate"],
    ],
  };
})(window);
