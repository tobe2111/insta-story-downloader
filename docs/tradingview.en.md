# TradingView integration guide

This program receives alerts from a **Pine Script strategy** on TradingView and
puts them through its validated execution layer — risk sizing, dead band,
market-hours guard, fill confirmation, kill switch — before placing an order.

> 🇰🇷 Korean original: [tradingview.md](tradingview.md).

> ⚠️ **Read this first.** This feature opens a door on the internet that
> executes orders — the most dangerous thing in this system. Validate it
> thoroughly in paper mode and switch to live trading only with every security
> setting below in place. This program does not guarantee returns.

## What you need

- **A paid TradingView plan** — webhook alerts are a Pro-and-above feature.
- **A public URL** — TradingView has to reach your server. From a home PC that
  means port forwarding or a tunnel (cloudflared and the like), and putting it
  **behind an HTTPS reverse proxy is strongly recommended** (a secret key must
  never travel over plain HTTP).
- **A long random secret** — the `QUANT_WEBHOOK_SECRET` below.

## 1. Run the server (on paper first)

```bash
export QUANT_WEBHOOK_SECRET='a-very-long-random-string'   # never share or commit
python -m quant webhook --market crypto --symbols BTC/USDT --tradingview-ips
```

- `--tradingview-ips`: allow TradingView's official sending IPs only
  (recommended). ⚠️ The IPs can change, so check the current list in the
  [TradingView documentation](https://www.tradingview.com/support/solutions/43000529348/)
  and pass `--allow-ips 1.2.3.4,5.6.7.8` if it differs. Behind a reverse proxy
  (where the sender appears to be the proxy), omit the IP options.
- `--symbols`: an allow-list of symbols. Set it and signals for anything else
  are rejected.
- Add `--live` for real trading (a confirmation prompt plus real money). For
  stocks the market-hours guard applies automatically.

## 2. Setting up the Pine Script alert

Put **JSON** in the alert's Message field (with your own secret):

```json
{"secret": "a-very-long-random-string", "action": "{{strategy.order.action}}", "symbol": "BTC/USDT", "price": {{close}}}
```

- `action`: one of `long`/`buy`, `short`/`sell`, `flat`/`close`/`exit`. Pine's
  `{{strategy.order.action}}` sends buy/sell; send a separate alert with
  `"action":"flat"` to close. For a partial weight, add `"weight": 0.5`.
- `price`: put `{{close}}` in and it executes at that price with no network
  lookup.
- Put your server address (`https://your-domain/`) in the alert's **Webhook
  URL**.

## 3. How it behaves, and the safeguards

- **Idempotent**: `action` is read as a *target weight*. Receiving the same
  `long` twice moves the position to the same target rather than buying twice
  (the dead band also filters out leftover adjustments).
- **Five layers of security**: ① constant-time comparison of the secret
  ② an IP allow-list ③ replay/duplicate rejection ④ (optional) timestamp
  freshness ⑤ a body-size limit. Without a secret the server does not start at
  all.
- **The existing execution layer is reused**: risk sizing, market impact, kill
  switch, market hours and fill confirmation all still apply. The webhook
  decides only *what*; *how safely* stays with the existing code.

## Honest limits

- TradingView **has no personal price or order API.** This integration
  *receives TradingView's signals*; it does not fetch its data. Backtesting and
  validation still run on this program's own data (ccxt / yfinance).
- Webhook receipt and order mapping are covered by tests, but **end-to-end
  validation in your own environment (public URL, proxy, real account) must be
  done on paper first.**
- The quality — the profitability — of a TradingView signal is entirely down to
  your own Pine Script strategy. This program executes that signal safely; it
  does not make it better.
