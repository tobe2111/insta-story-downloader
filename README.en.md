# Quant — a quantitative trading system for stocks and crypto

> 🇰🇷 **한국어 원문: [README.md](README.md)** — the Korean file is the original.
> When the two disagree, the Korean one is right and this one is stale; please
> open an issue.

![CI](https://github.com/tobe2111/insta-story-downloader/actions/workflows/ci.yml/badge.svg)

A Python **quantitative trading framework** for crypto, Korean equities and US
equities. It is built so that a strategy earns its way forward one step at a
time: **backtest → paper trading → live trading**.

Live public record (updated every morning):
**<https://quant.jiwon-1a2.workers.dev>** — the site reads in English too; if
your browser does not ask for Korean first, it opens in English automatically.

---

## ⚠️ Read this first (disclaimer)

- **This system does not guarantee profits. No system does.** Any automated
  trading bot advertising guaranteed returns is either a fraud or an overfitted
  backtest.
- What keeps a quantitative investor alive over the long run is not a magic
  forecast — it is **disciplined risk management and repeated validation.**
- This code is for **education and research**. Any loss from real trading is
  entirely the user's own responsibility.
- Before trading real money, work through **backtest → paper trading** and give
  it time.
- **Remember survivorship bias.** The only symbols you can download data for
  are the ones that survived. Everything that was delisted or collapsed never
  appears in the backtest, so a backtest run on today's symbols
  **systematically overstates** performance. When a screening or portfolio
  backtest looks good, the honest assumption is that part of it is this bias.

---

## 🚀 The easiest way to start

### Option 1 — a prebuilt executable (no Python needed)

**Nothing to install.** Download the file and double-click it:

1. From the
   **[Releases page](https://github.com/tobe2111/insta-story-downloader/releases/latest)**,
   download the zip for your OS:
   - Windows: `quant-cockpit-windows.zip`
   - macOS: `quant-cockpit-macos.zip` · Linux: `quant-cockpit-linux.zip`
2. Unzip and **double-click the `quant-cockpit` executable**.
3. The cockpit opens in your browser — everything from there is clicks.

> Two free ways to publish the landing page (`docs/`):
> - **Cloudflare (recommended, free forever)**: connect the repository to
>   Cloudflare Workers & Pages; it reads `wrangler.jsonc` (static assets only,
>   no build) and serves `docs/` as is, redeploying on every push to `main`.
>   ⚠️ Leave **Build command empty** in the Cloudflare project settings.
> - **GitHub Pages**: Settings → Pages → Source → `main` and the `/docs`
>   folder → published at `https://<account>.github.io/<repo>/`.
>
> **Cutting a release — three ways**
> 1. **[automatic, recommended]** Change the `VERSION` file at the repository
>    root and merge to `main`; the tag and release build with no clicks
>    (e.g. commit `VERSION` as `v0.2.3` → release v0.2.3). Per-OS files are
>    attached to Releases about five minutes later.
> 2. Actions tab → "Build App" → Run workflow → type the version (manual).
> 3. Push a `v*` tag.
>
> Windows gets the raw `.exe` (no unzipping); macOS and Linux get zips.

> ⚠️ Windows and macOS may warn about an "unknown developer" — these are
> unsigned personal builds. You built it yourself, so choose "run anyway".

### Option 2 — the double-click launcher (if you already have Python)

- **Windows**: double-click `start.bat`
- **macOS / Linux**: run `start.sh` (or `python3 start.py`)

It installs the required libraries once, starts the web cockpit and
**opens your browser** for you. Everything after that is clicks.

> If it is already installed, `python -m quant web --open` does the same thing.

### Updating after installation

Nothing updates itself. The code on your machine stays exactly as you received
it; to run a newer version you have to fetch it once.

- **Windows**: double-click `update.bat`
- **macOS / Linux**: run `update.sh` (or `python3 update.py`)

It pulls the latest code (when installed via `git`), installs any newly
required libraries and tells you what changed. If you use the executable
(option 1), download the new one and overwrite. Your outputs — `data_cache`,
state files — are never touched.

> ⚠️ An update only brings the *code* up to date; it does not raise returns.
> The ceiling on directional accuracy (usually 52–55%) is not something any
> update breaks through.

### Licence keys (optional, for one-off sales)

A lightweight authenticity check for selling the program as a **one-off
purchase**. Keys are **permanent** — no expiry, no subscription, no remote
kill — so one purchase stays valid.

- **Seller**: pick and store a strong secret
  (`export QUANT_LICENSE_SECRET='…'`), then issue a key per buyer with
  `python -m quant.licensing gen --owner buyer@email.com`. Builds put the
  secret in `quant/_license_key.py` (not committed) and set
  `QUANT_REQUIRE_LICENSE=1`.
- **Buyer**: create `license.key` in the program folder:
  ```
  owner: buyer@email.com
  key:   QUANT-XXXXXX-XXXXXX-XXXXXX-XXXXXX
  ```
  (No key is needed when `QUANT_REQUIRE_LICENSE` is off, i.e. running from
  source.)

> ⚠️ **An honest limit**: the verification secret ships with the distributed
> code, so a determined person can bypass it. This is not DRM — it is an
> authenticity check that discourages casual sharing. **Subscription and expiry
> gating are deliberately absent**: in Korea an unregistered paid
> auto-investment service risks breaking the Capital Markets Act. Before
> selling, ask a fintech lawyer whether you must register as an investment
> advisory business, and **never write "guaranteed returns"** (that is fraud).
> Position the product as a tool (backtesting and research).

---

## Design philosophy

```
data → strategy (signals) → risk (sizing/stops) → backtest/execution → analysis
```

1. **Data layer** (`quant/data`) — crypto, US and Korean data behind one
   interface. With no network it falls back to synthetic data, so validation
   still runs offline.
2. **Strategy layer** (`quant/strategies`) — momentum, moving-average cross,
   mean reversion and so on. A strategy computes one thing only: the target
   position weight (−1.0 to 1.0).
3. **Risk layer** (`quant/risk`) — position sizing, stops, drawdown limits.
   **This is the part that actually protects the money.**
4. **Backtest layer** (`quant/backtest`) — commissions and slippage included,
   look-ahead bias prevented; Sharpe, max drawdown, hit rate and the rest.
5. **Broker/execution layer** (`quant/broker`, `quant/live`) — paper trading
   and live trading (ccxt and others) behind the same interface.

## Install and develop

```bash
pip install -r requirements.txt   # or: make install
pytest -q                          # the whole suite (or: make test)
python -m py_compile $(find quant examples tests -name "*.py")  # syntax check
```

> CI (GitHub Actions) runs the whole suite on Python 3.11 and 3.12 for every
> push and pull request. With no data source it falls back to synthetic data,
> so the tests pass offline too.

## The unified CLI (recommended)

> 🌐 **In English**: add `--lang en`, or set `QUANT_LANG=en` once and every
> command follows. The web cockpit switches with the same button as the site,
> and opens in English by itself when your browser does not ask for Korean
> first. Anything not yet in the dictionary **stays in Korean** rather than
> being machine-translated — a rough translation next to a number is a claim
> that is not true.

One command runs each of the main jobs:

```bash
python -m quant backtest --strategy ma_cross --report results/r.html
python -m quant validate --strategy ma_cross                 # the 3 overfitting checks
python -m quant sweep --market crypto --symbol BTC/USDT      # sensitivity heat map
python -m quant web --port 8000                              # local web UI
python -m quant pipeline                                     # backtest + report + Monte Carlo
python -m quant --help                                       # every command
```

The backtester has turnover (cost) options — not a better forecast, just the
**deterministic cost arithmetic** of not paying the round trip on tiny
adjustments:

```bash
python -m quant backtest --strategy ml --rebalance-band 0.03 --stop-cooldown 5
```

## Three overfitting checks — "can this strategy be trusted?"

**Run these, in this order, before putting a strategy anywhere near trading
(paper included).** None of the three makes money; all three filter out
plausible lies.

```bash
python -m quant validate --market crypto --symbol BTC/USDT --strategy ma_cross
```

| Step | Tool | What it looks at | Conventional pass mark |
|---|---|---|---|
| 1 | Walk-forward + **DSR** | Out-of-sample result, Sharpe confidence corrected for multiple testing | DSR ≥ 0.95 |
| 2 | **PBO** | Whether the in-sample winner is a coin flip out of sample | PBO < 0.2 |
| 3 | **CPCV** | Whether the result holds across many out-of-sample paths | worst-path Sharpe > 0 |

> Passing all three **still guarantees nothing about future returns.** It means
> only that the selection procedure is not picking noise. The next step is
> paper trading (`learn.bat`) on real data. Conversely, if one of them fails
> badly, do not put that strategy or parameter set into trading.

### In automated operation these checks **scale the weight** (the validation gate)

Every night the whole universe (`quant.markets.AUTO_TARGETS`) is re-measured,
and the result multiplies the next day's target weights in the **combined
diversified account**. It applies **after** the kill switch and the volatility
target, so no scaler can undo it.

> **Which account, exactly.** The batch runs two kinds of account.
> · The **combined diversified account** (`run_daily_portfolio`, the public
>   challenge) — where the money actually moves. **The gate applies.**
> · The **per-symbol reference accounts** (`run_daily_paper`) — instruments
>   that measure how a strategy behaves on that symbol. The gate is
>   **deliberately not applied.**
>
> Gating the instrument would make it circular: the damped returns accumulate
> in the ledger, and the Kelly cap drawn from that ledger then sets the
> combined account's weights. Damping the instrument by the very thing it
> measures would mean never learning how the strategy actually behaves. That
> is why the per-symbol screens on the site show pre-damping values.

| Grade | Condition | Weight |
|---|---|---|
| Pass | PBO ≤ 0.2 **and** DSR ≥ 0.95 **and** worst CPCV path > 0 | ×1.00 |
| Warn | in between · **or any one of the three unmeasured** | ×0.50 |
| Fail | PBO > 0.7 (conventionally "discard") | ×0.00 (stand aside that day) |
| Unmeasured / stale | no record / no date / older than 7 days | ×0.50 |

> ⚠️ **Unmeasured is not a pass.** Treating "we never checked" the same as "we
> checked and it was fine" means the system trades most aggressively on the day
> validation dies altogether.
>
> ⚠️ Why not all-or-nothing — PBO and DSR are not pass/fail stamps but
> continuous confidence measures, and they swing hard on small samples. A
> binary cut would turn measurement noise into an account switch. So confidence
> is translated into weight.
>
> ⚠️ **Half a measurement is not a pass either.** A record with PBO but no DSR
> is common (walk-forward returns null when it cannot compute one); letting
> such a record score full marks breaks the rule above at field level. The same
> goes for a record with no date, whose freshness cannot be checked.
>
> ⚠️ **Until 2026-08-14, CPCV was computed, printed on screen and thrown away.**
> We called it a triple gate while the third was never even stored, so it
> touched no decision. It is stored now and it enters the gate.
>
> ⚠️ Before 2026-08-14 this validation **raised alarms and blocked nothing.**
> The documentation said "we only use strategies that pass" while a symbol with
> PBO 0.78 traded every day. Implementation: `quant/live/validation_gate.py`

## Nightly retraining — champion/challenger (replaced only when beaten)

Every night (GitHub Actions, 05:00 KST) ML candidates are trained on the latest
real data and put against the current champion in a **two-stage** contest:

1. **Qualifier** (past window): every candidate vs the champion — the best one
   above the t-statistic threshold advances.
2. **Final** (a recent window the qualifier never saw): only that one is
   re-tested, and it must win here too to be promoted.

Challengers are **fixed candidates (ML variants plus classical strategies) plus
mutations of the champion** — each night the current champion's settings are
perturbed to create new ones. The winning mutation becomes the next day's
champion and the search continues around it: **hill-climbing evolution**, so
settings outside the candidate list get explored over time. The promotion gate
is unchanged, so a wider search does not weaken the defence against
overfitting.

Decisions are committed automatically to `state/champions.json` and
`state/retrain_history.jsonl`, and a status card appears in the **Monitor** tab
of the web cockpit. To run it by hand:

```bash
python -m quant retrain --market crypto --symbol BTC/USDT
```

**The champion is actually used** — paper learning (`learn.bat` /
`python -m quant learn`) defaults to the `champion` strategy, so when nightly
retraining swaps the champion a running bot switches on the next cycle
**without a restart**. You can also pick `champion` in the web backtest form to
validate the current one, and `examples/run_live.py --strategy champion`
follows it live. (Promotion records accumulate in `state/` in the repository,
so a bot on your own machine needs one `update.bat` to receive a new champion;
with no record it runs the default champion, ml logreg.)

> ⚠️ **Retraining is not a device that keeps raising the win rate.** The
> realistic ceiling on directional accuracy is about 52–55%; the point of this
> loop is to keep the model from falling behind a changing market and to adopt
> **only improvements that passed validation.** A champion that does not change
> for a long time is normal, not broken.

### The long validation — same training window, a much longer test

```bash
python -m quant walkforward                 # the longest history (2,500 bars ≈ 10 years of stocks)
python -m quant walkforward --offline       # stored snapshots only, no network
```

It applies today's champion settings to a **far longer past** and counts how
often they worked, window by window. It is the same question as
`crosssection` (how many *symbols* the same settings worked on) asked
**backwards** instead of sideways. A weekly workflow runs it every Monday and
sends the result.

**The training window stays at 250 bars.** Train on ten years and the model
learns patterns that are already dead (the market of 2015) — only the test
window grows.

> ⚠️ **Survivorship bias** — this score is computed only on symbols that
> survived *to today*. Ten years ago you could not have picked these twenty,
> and the losses of the ones you would have picked and that then disappeared
> are not in here. **So it comes out better than what was actually
> achievable.** The report always carries this sentence, and the number is not
> used for promotion decisions (observation only).

**A control arm ("simply holding") is always reported alongside.** Looking at
the share of positive windows alone flatters any bull market — the real
question is whether it beat just holding.

Measured (2026-08-14 snapshot, offline, 20 symbols, 125 windows):

| | |
|---|---|
| Positive windows | 78 (62%) |
| **Windows that beat simply holding** | **39 (31%)** |
| Symbols beating hold in most windows | 3 / 20 |
| Average exposure per symbol | 9% (per-symbol reference accounts) |

Example: SK hynix, strategy +21.6% vs holding +852.4%. **These settings do not
beat long-term holding** — we do not hide that; it goes out in the same table
every week.

> ⚠️ The 9% exposure figure is per **single-symbol reference account**. The
> combined account across 20 symbols runs 42–51% total exposure (the "capital
> deployed" line in the weekly report). Blurring the two produces the false
> conclusion that 91% of the capital sits in cash.

## The 1M Won Challenge — from 1,000,000 KRW toward 100,000,000

A combined virtual account starts at **1,000,000 KRW** and heads for
100 million.

> ### ⚠️ The honest number first — right now it is worse than simply holding
>
> On 2026-08-16 we measured this three independent ways and **all three agreed**.
>
> | How it was measured | Result |
> |---|---|
> | Long validation (per window) | **39 of 125 (31%)** windows beat simply holding |
> | Nightly audition | on SPY and QQQ the winning strategy was **`buy_hold`** |
> | Cross-sectional evidence | 19 of 20 symbols share the **same champion** — effectively one experiment |
>
> Example: SK hynix, strategy **+21.6%** vs simply holding **+852.4%**.
>
> **And 100 million is 100×.** At what we actually measure today (Sharpe ~0.5,
> exposure 45%) the return is single-digit percent a year, and at that speed
> 100× takes **decades**. That is arithmetic, not a bug.
>
> So what this repository is trying to prove is not "100 million" but
> **"better than simply holding."** That has to come first for anything else to
> mean something. While we are failing at it, this table says so.

> The original name was the "8 Mile Challenge" (8 symbols × 10,000 KRW =
> 80,000 KRW, after the film *8 Mile*). Once the universe grew to 20 symbols
> and the principal to 1,000,000 KRW the name explained nothing, so it changed
> on 2026-08-14. **Records and captions already published under the old name
> are not edited** — that was the name at the time, and not editing the past
> comes first. Each per-symbol account keeps its own 10,000 KRW reference record.

When a donation comes in during a broadcast, the operator **increases the
virtual account's principal by the same amount**. ⚠️ **The donations themselves
are never traded** (no consideration, no equity) — changing that structure
(managing other people's money) would create real regulatory exposure.

- Registering a deposit (easiest): web cockpit → **Deposit** tab → amount and
  memo. A GitHub token is needed once and the screen explains it
  (`QUANT_GH_TOKEN`).
- From a phone: GitHub app/web → Actions → **Deposit** → Run workflow → amount
  and memo. Either way the site and the broadcast update automatically and a
  banner appears.
- CLI: `python -m quant deposit --amount 10000 --memo "super chat from ○○"`
- The accounting **separates principal from trading profit**: the return is
  against principal, while the skill measure is a time-weighted return (TWR)
  with the deposit effect removed. The chart shows a principal step line and ▲
  deposit markers, so "jumps are donations, slope is skill" stays visible.
- Every deposit is publicly recorded in the git ledger (`deposits`) and cannot
  be altered afterwards.

## Fully automated operation — every day, with nothing from you

No PC to leave on, no program to run. The cloud (GitHub Actions) does it every
morning, Korean time:

| Time (KST) | What happens |
|---|---|
| 04:00 | **Nightly validation** — the three overfitting checks, re-run on real data |
| 05:00 | **Nightly retraining** — the two-stage champion/challenger contest; swap only on a win |
| 05:30 | **Daily paper** — one day of simulated trading with that day's champion, continuing the account |
| 05:30 | **Market briefing** — headlines from free RSS feeds, shown on the site and the broadcast. ⚠️ Display only — it feeds no trading decision (we do not use signals we cannot validate) |
| 07:45 | **Automatic social posting** — the day's report card, a screenshot of the site and a written explanation go to Threads and Instagram (when tokens are set). Losing days go out unchanged — a public experiment with no selection bias |

The retraining ring also includes **event-guard variants** (stand aside inside
an announced macro window such as an FOMC meeting) alongside champion mutations
and regime-filter variants — event calendars are published years ahead, so they
are reproducible and testable, and such a variant becomes champion only by
passing the same two-stage validation.

Results land on the site's **[paper trading page](docs/paper.html)**
(`docs/paper.html`, deployed automatically) and refresh daily — just open it in
a browser.

### Setting up automatic social posting (optional)

To post the report card to Threads and Instagram each morning, register tokens
under **Settings → Secrets and variables → Actions** in the GitHub repository.
Without tokens the content (images and captions) is still generated into
`docs/social/` and only the posting is skipped.

| Secret | Where to get it |
|---|---|
| `THREADS_USER_ID` · `THREADS_ACCESS_TOKEN` | [Meta developer console](https://developers.facebook.com) → create a Threads API app → issue a long-lived token |
| `IG_USER_ID` · `IG_ACCESS_TOKEN` | Connect an Instagram **business/creator account** to a Facebook page → issue a Graph API token |

Manual run: Actions tab → **Social Post** → Run workflow. Captions use the
ledger's own numbers (losses included) and always carry the simulation notice.
Manual run: `python -m quant paper-daily --market crypto --symbol BTC/USDT`

> ⚠️ This is paper (simulated) trading — no real money moves, and **an
> automatic switch to live trading was deliberately not built.** Watch good
> paper results for long enough (months), then decide live trading yourself,
> with an amount you can afford to lose.

## Going live — running a real account with the evolving champion (manual switch)

This is the command that puts the champion grown by nightly retraining onto a
real account. **It never turns itself on** — a person runs it, and even then
must type two Korean characters (`실전`, "live") to start.

```bash
python -m quant setup                 # ① store exchange/broker API keys (.env, once)
python -m quant live                  # ② watch the champion on paper first (default)
python -m quant live --real           # ③ live — with a small amount!
```

- **Follows the champion automatically**: when nightly retraining swaps the
  champion, the new strategy applies from the next cycle with no restart — the
  evolution reaches live trading.
- **Multiple symbols**: `--symbols "BTC/USDT,ETH/USDT,SOL/USDT"` — several
  symbols of one market in a single account with inverse-volatility
  allocation, each following its own champion.
- **Safeguards (on by default)**: −3% daily-loss kill switch · −15% drawdown
  circuit breaker · 50% maximum weight · a market-hours guard for stocks ·
  order retries and fill confirmation. Limits are tunable with
  `--daily-max-loss`, `--max-drawdown` and `--max-weight`.
- **Intraday monitoring** (from 2026-08-15): loss monitoring used to run once a
  day inside the dawn batch; it now runs every 15 minutes
  (`python -m quant guard`). The real output is not the watching itself but the
  **measured record of how often we actually looked** — the worst observed gap,
  not the configured interval, is what risk limits rest on.
- **Leverage: not used** (total exposure capped at 100%). On 2026-08-15 three
  gates were built for opening it later (liquidation headroom · a track record
  of intraday monitoring · probability of ruin), and it opens **only when all
  three pass.** The default is locked, and unknown means locked.
  ⚠️ Marketing material must not say "leverage available".
- Supported markets: crypto (ccxt) · US equities (Alpaca) · Korean equities
  (Korea Investment / Kiwoom).
- Status is visible live in the **Monitor** tab of the web cockpit.

> ⚠️ Safeguards **cannot guarantee that losses are stopped** (gaps and sudden
> moves). Use only money you can afford to lose, and only after months of paper
> validation. Nothing here is a guarantee of returns.

### Switching the 1M Won Challenge to live trading (once a day — ready to go)

`live-daily` sends **the same decision** the dawn paper batch makes (champion,
HAR sizing, Kelly cap, admin settings) to a KIS account. All that is missing is
the keys:

**Choosing a broker**: Korea Investment (KIS) or Kiwoom —
`--broker kis|kiwoom`, or the `QUANT_KR_BROKER` environment variable (a
dropdown when running the Action). Both adapters share one interface, so the
execution code is identical and only the keys differ.

1. **Register an app with the broker** — Korea Investment:
   apiportal.koreainvestment.com / Kiwoom: apiportal.kiwoom.com (including the
   simulated-trading application).
2. **Register the keys** — locally with `python -m quant setup`; for GitHub
   Actions, as Secrets: for KIS `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_CANO`
   (plus `KIS_ACNT_PRDT_CD`, usually 01); for Kiwoom `KIWOOM_APP_KEY`,
   `KIWOOM_SECRET`, `KIWOOM_ACCOUNT`.
3. **Diagnose** — `python -m quant live-check --broker kis` (keys → auth →
   balance, no orders). In Actions, running the `KR Live` workflow by hand does
   the diagnosis plus a simulated-trading rehearsal.
4. **Simulated rehearsal** — `python -m quant live-daily` (simulation is the
   default). It accumulates alongside the paper ledger, so the slippage
   difference becomes data.
5. **Going live (a double lock)** — real orders require the `--real` flag
   **and** the environment variable `QUANT_LIVE_REAL=1` (a Variable in
   Actions). Daily automatic execution comes from uncommenting the schedule in
   `.github/workflows/kr-live.yml`.

> A suggested bar for switching: paper TWR in the upper range of the random
> benchmark **and** excess return over buy-and-hold, sustained for 90 days or
> more. Going live before that is gambling, not statistics.

## Deployment (Docker) — one line onto a PC or VPS

```bash
docker compose up            # web cockpit (:8000) + paper bot together
# or just the web UI:
docker build -t quant . && docker run --rm -p 8000:8000 quant
```

`docker compose up` starts the **web cockpit** and the **paper trading bot**
together and shares the bot's state (`results/`) so the 📺 Monitor tab shows it
live. For 24-hour operation, put this compose file on a small VPS. See the
comments in `docker-compose.yml` for switching to live trading.

## Quick start (backtesting)

```bash
# runs immediately on synthetic data (no network needed)
python examples/run_backtest.py

# on real crypto data
python examples/run_backtest.py --market crypto --symbol BTC/USDT --timeframe 1d

# US equities
python examples/run_backtest.py --market us_stock --symbol AAPL
```

## Advanced: ensembles · regime filters · Monte Carlo

Genuinely robust performance comes from these three, not from parameter tuning.

**① Strategy ensemble** — combine weakly correlated strategies to smooth the
equity curve.
```python
from quant.strategies import StrategyEnsemble, MovingAverageCross, Breakout, RSIReversion
ens = StrategyEnsemble([MovingAverageCross(), Breakout(), RSIReversion()])
```

**② Regime filter** — stand aside automatically in bear markets and
high-volatility regimes to avoid large drawdowns.
```python
from quant.strategies import RegimeFilter
strat = RegimeFilter(ens, trend_window=200)   # stop trading below the long MA
```

**③ Monte Carlo confidence intervals** — do not be fooled by a single Sharpe
ratio. Resample thousands of times and look at the distribution of the real
skill. If the 5% lower bound sits near zero, it was luck.
```python
from quant.robustness import bootstrap_metrics, summarize
print(summarize(bootstrap_metrics(result.returns)))
```

**All at once** — backtest + HTML report + Monte Carlo:
```bash
python examples/run_config.py --config config/config.yaml
```

## Web UI (local web server)

Pick a market, symbol and strategy in the browser, press a button, read the
report. **No external web framework** — the Python standard library's
`http.server`.

```bash
python examples/run_web.py          # open http://127.0.0.1:8000
# or: python -m quant.web.server
```

Choose market, symbol, strategy and timeframe in the form → "run backtest" →
the equity curve (with a benchmark overlay) and the performance report appear.
It binds to localhost only.

The top navigation moves between **backtest ↔ sensitivity sweep (heat map)**,
so strategy research and validation happen in one browser window (the cockpit
approach).

## Portfolio backtests (multiple symbols)

Spread across symbols to lower volatility. Allocation: `equal`, or
`inverse_vol` (inverse-volatility weighting ≈ risk parity).

```bash
python examples/run_portfolio.py --market crypto --symbols BTC/USDT ETH/USDT SOL/USDT
python examples/run_portfolio.py --market us_stock --symbols AAPL MSFT NVDA --allocation inverse_vol
```

## Parameter sensitivity heat map (an overfitting diagnostic)

Sweep two parameters over a grid and draw the performance terrain. **A wide
green plateau means robust; a lone green dot means overfitted.** This is the
single most useful visual check before trading.

```bash
python examples/run_sweep.py --market crypto --symbol BTC/USDT --objective sharpe
```
→ writes `results/heatmap.html` (inline HTML, no matplotlib needed).

## Parameter optimisation + walk-forward validation

**The most important tool here.** Simply maximising past returns overfits.
Walk-forward repeats "optimise on the past, test on a future it has not seen"
to measure **what you can actually expect in live trading.**

```bash
python examples/run_optimize.py --market crypto --symbol BTC/USDT --strategy ma_cross
```
> A large gap between the in-sample Sharpe and the out-of-sample Sharpe means
> the strategy is overfitted.

## Multi-symbol live operation + alerts + robust orders

Run several symbols at once, get fills and errors on Telegram or Slack, and
retry failed orders automatically.

```bash
python examples/run_multi.py --paper --market crypto \
    --symbols BTC/USDT ETH/USDT SOL/USDT --iters 3
```

- **Alerts** — enabled automatically when the environment variables are set
  (console only otherwise): `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`,
  `SLACK_WEBHOOK_URL`, `DISCORD_WEBHOOK_URL` (for Discord: channel settings →
  Integrations → create a webhook → copy the URL. Register the same names as
  GitHub Secrets and the cloud batches send there too).
- **Robust orders** — `RobustBroker` wraps any broker to add exponential
  backoff retries, minimum-quantity and step rounding, and failure alerts
  (defence against exchange rejections and rate limits).

```python
from quant.broker import RobustBroker, get_broker
from quant.live import get_notifier
broker = RobustBroker(get_broker("crypto_live"), retries=3, backoff=2.0,
                      min_qty=0.0001, notifier=get_notifier())
```

## Paper and live trading

```bash
# paper (safe, recommended)
python examples/run_live.py --paper --market crypto --symbol BTC/USDT --iters 5

# live — one broker per market (API keys via environment variables)
python examples/run_live.py --live --market crypto  --symbol BTC/USDT   # ccxt
python examples/run_live.py --live --market us_stock --symbol AAPL       # Alpaca
python examples/run_live.py --live --market kr_stock --symbol 005930     # Korea Investment
```

While it runs, `results/dashboard.html` refreshes every cycle. Leave it open in
a browser to watch equity, profit and loss, positions and recent orders,
auto-refreshing every 30 seconds (rendered with the standard library alone, no
pandas).

### API keys — when, and which

**Backtesting, `validate` and paper trading need no keys at all.** Keys are
needed only for ① live orders ② alerts ③ auxiliary data (macro and
fundamentals).

Issuing a key has to be done by you because of identity verification, but after
that the setup wizard takes you from entry to storage (`.env`, not committed,
readable only by you) to a connection check in one go:

```bash
python -m quant setup
```

Every command then reads `.env` automatically (values exported in the shell
win). ⚠️ On live-trading keys, **always disable withdrawal permission** at the
exchange.

Live-trading API keys:

| Market | Environment variables |
|------|----------|
| Crypto (ccxt, 100+ exchanges: Upbit, Bithumb, Coinone, Korbit, Binance, Bybit, OKX and more) | `EXCHANGE_API_KEY`, `EXCHANGE_SECRET`, (some) `EXCHANGE_PASSWORD`, (optional) `EXCHANGE_QUOTE` |
| US equities (Alpaca) | `ALPACA_API_KEY`, `ALPACA_SECRET` |
| Korean equities (Korea Investment, KIS) | `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_CANO`, `KIS_ACNT_PRDT_CD` |
| Korean equities (Kiwoom, beta) | `KIWOOM_APP_KEY`, `KIWOOM_SECRET`, `KIWOOM_ACCOUNT` |

> For crypto you only change the exchange:
> `get_broker("crypto_live", exchange="upbit")` (Upbit and Bithumb default to
> KRW). For Korean equities **only Korea Investment and Kiwoom** are supported,
> because they are the ones with a personal REST API — Daishin and LS are
> Windows COM only, and Samsung, Mirae Asset and Toss have no personal API at
> all.

### Safeguards for live stock trading (and their honest limits)

Unlike crypto, stocks ① trade only during set hours and ② have a delay between
a market order being accepted and being filled, so there are matching devices:

- **Market-hours guard**: no order goes out outside the regular session
  (US 09:30–16:00 ET / Korea 09:00–15:30 KST, weekdays). It applies
  automatically whenever live trading meets stocks, as in
  `run_live.py --live --market us_stock`.
- **Fill confirmation**: an accepted market order is never counted as a fill.
  After the acceptance response it **polls for the actual position change** to
  measure the real filled quantity (using only the verified balance query
  rather than adding speculative endpoints), and if it is not filled in time it
  honestly reports it as unfilled — it does not re-order and double-execute.

> ⚠️ **Honest limits — check these before using a real account.** ① Everything
> above, and the broker parsing, is verified with mock tests but **not yet
> against a real exchange API** — if a response field differs from our
> assumption, the first real order may go wrong. **Put a small real order
> through the free simulated accounts KIS and Alpaca provide first.** ② The
> market-hours guard **has no holiday calendar** (it judges by weekday and time
> only) — public and ad-hoc closures rely on the broker rejecting the order.
> ③ Kiwoom is beta.

## Adding your own strategy

You can plug in your own idea without touching the source. Subclass `Strategy`
so that `generate_signals(df)` returns target weights (−1 to 1), and you are
done. Copy `examples/custom_strategy.py` to start.

```python
from quant.strategies.base import Strategy
class MyStrategy(Strategy):
    name = "my_strategy"
    def generate_signals(self, df):
        signal = ...                      # compute target weight from df (no look-ahead)
        return self._finalize(signal, df.index)
```

Put the file in the **`strategies_user/` folder** and it registers itself,
becoming fully equal to the built-in strategies — backtest, **overfitting
checks (`validate`)**, paper, live and the web dropdown:

```bash
python -m quant backtest --strategy my_strategy
python -m quant validate --strategy my_strategy --grid '{"window":[20,50,100]}'
```

You can also register from code: `from quant.strategies import register_strategy`.
If writing code is a barrier, TradingView (Pine Script) strategies can arrive
by webhook instead.

> ⚠️ Run a custom strategy through `validate` (the overfitting checks) and then
> paper, in that order. `tests/test_leakage.py` catches look-ahead
> automatically.

### Without coding: extract a strategy from a document → audition → (optionally) pin

```bash
# ① pull rules out of a PDF, a YouTube link or a TradingView script and register them
python -m quant ingest my_strategy.pdf --name my_strategy
#    → it is auditioned nightly as a challenger (qualifier and final); win and it becomes champion.
#    If no rule can be found it says so — it does not invent rules that are not there.

# ② to trade your own strategy regardless of the audition — pin it
python -m quant pin --market crypto --symbol BTC/USDT --name my_strategy
#    → it shows the report card first (audition history, overfitting checks),
#      and you have to type a confirmation phrase yourself to pin it.
python -m quant pins     # what is pinned right now
python -m quant unpin --market crypto --symbol BTC/USDT   # back to the system's own choice
```

> **The strategy is yours; the brakes are ours.** Pinning still leaves the kill
> switch, the volatility target, the validation gate and the no-leverage line
> in place — pinning changes *what* is bought and sold, never *how much*. The
> screen also states that profit and loss while pinned is not the outcome of
> the system's own selection.

## TradingView integration

You can receive alerts from a TradingView Pine Script strategy and place orders
(webhook). TradingView has no personal price or order API, so the standard
route is an **alert webhook**: the signal alone comes in and rides this
program's validated execution layer (risk, kill switch, market hours, fill
confirmation).

```bash
export QUANT_WEBHOOK_SECRET='a-very-long-random-string'
python -m quant webhook --market crypto --symbols BTC/USDT --tradingview-ips   # paper
```

> ⚠️ This is the most dangerous feature here — it opens a door on the internet
> that places orders. A secret key, an IP allow-list and replay protection are
> built in, and the server refuses to start without a secret. Validate it on
> paper and put it behind HTTPS. Setup and a Pine Script template:
> [docs/tradingview.md](docs/tradingview.md).

## Project layout

```
quant/
├── data/         data providers (crypto / us_stock / kr_stock / synthetic)
├── strategies/   strategies (MA / momentum / mean reversion / RSI / breakout / MACD / Keltner / stochastic / ML / ensemble / regime / ADX)
├── risk/         risk management (sizing, stops, take-profit)
├── backtest/     single-symbol backtest engine + performance metrics
├── portfolio/    multi-symbol allocation + backtests
├── optimize/     grid search + walk-forward + parallel sweeps/sensitivity
├── robustness/   Monte Carlo bootstrap (confidence intervals)
├── reporting/    HTML reports + live dashboard + sensitivity heat maps (zero dependencies)
├── broker/       order execution (paper / ccxt / Alpaca / KIS / RobustBroker + exchange specs)
├── live/         live loops (single and multi symbol) + alerts (Telegram/Slack)
├── web/          local web server (http.server based, run backtests from a browser)
└── utils/        logging, HTTP helpers
```

## Roadmap

- [x] Backtest engine + performance metrics
- [x] Multiple strategies + risk management
- [x] Paper trading + live integration for crypto, US and Korean markets
- [x] Multi-symbol portfolio allocation and backtests
- [x] Walk-forward validation / parameter optimisation
- [x] Strategy ensembles + regime filter (drawdown defence)
- [x] Monte Carlo confidence intervals + HTML reports
- [x] Live trading loop + live monitoring dashboard
- [x] Simultaneous multi-symbol live operation (MultiTrader)
- [x] Alerts (Telegram/Slack) + robust orders (retry, backoff, rounding)
- [x] Partial-fill tracking + per-exchange quantity/price specs (MarketSpec)
- [x] Parallel parameter sweeps + sensitivity heat maps (overfitting diagnostic)
