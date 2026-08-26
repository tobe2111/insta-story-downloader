# Connecting live quotes — what you have to do

Settings that get the freshest quotes available for free. **Do nothing and the
site still works** — it falls back to Yahoo's free feed and the screen labels
itself "delayed".

> 🇰🇷 Korean original: [REALTIME_SETUP.md](REALTIME_SETUP.md).

---

## Where it stands now (before setup)

| Asset | Source | Freshness |
|---|---|---|
| Crypto | Binance WebSocket | **on every trade** (no setup needed) |
| US equities | Yahoo, free | refreshed every 15s during the session · Yahoo's own delay |
| Korean equities | Yahoo, free | refreshed every 15s during the session · **about 20 minutes delayed** |
| KRW/USD | Yahoo `KRW=X` | refreshed every 15s during the session |

## After setup

| Asset | Source | Freshness |
|---|---|---|
| Crypto | Binance WebSocket | on every trade |
| US equities | Finnhub, free tier | **live** |
| Korean equities | Korea Investment | **live** |
| KRW/USD | Yahoo `KRW=X` | 15s (plenty — there is no reason to watch an exchange rate by the second) |

---

## ① Korea Investment (live Korean equity quotes)

Free, and an official API. It is effectively the only place that gives live
Korean equity quotes for free (the Naver and Daum endpoints are unofficial and
must not be used).

1. Open a Korea Investment account (this can be done remotely).
2. Apply for an app at **KIS Developers**
   (`apiportal.koreainvestment.com`).
3. You receive an **App Key** and an **App Secret**.
4. In the Cloudflare dashboard → Workers → `quant` → Settings →
   **Variables and Secrets**, add these two as **Secrets**:

   ```
   KIS_APP_KEY      = (the app key you were issued)
   KIS_APP_SECRET   = (the app secret you were issued)
   ```

5. Save and you are done. No deployment, no code change — the worker checks
   whether the keys exist and switches itself to the live source.

> ⚠️ These keys **never go into the repository.** They exist only as Cloudflare
> secrets; the code contains nothing but the name `env.KIS_APP_KEY`. A test
> (`test_no_credentials_are_committed`) stops a key from being baked into the
> code.

> A simulated-trading account works too, though the simulation domain has
> tighter rate limits.

## ② Finnhub (live US equity quotes)

1. Sign up free at `finnhub.io` → issue an API token (60 calls a minute).
2. Add a Secret in the same place:

   ```
   FINNHUB_TOKEN = (the token you were issued)
   ```

You can skip this — Yahoo is reasonably fresh for US equities. The difference
is nothing like the Korean case.

---

## How to tell whether it worked

Open the site and look at the **ticker strip at the top**.

- `live` after a Korean stock → KIS is connected.
- `delayed` → it is still Yahoo (no key, a wrong key, or KIS did not answer).

The sentence under the balance table changes with it — "every holding is on
**live** quotes", or "live on N, delayed on M".

**The label is not hard-coded.** The worker reports which source it actually
used in its response and the screen just reads that value, so on a day when the
live source dies the screen turns itself back to "delayed". (This rule exists
because of the exact opposite situation in audit 229 — the label said
"near-live" while every request was being rejected.)

---

## Using it from the cockpit (`python -m quant web`)

The cockpit does **not** rebuild the source ladder; it hands the question to
the deployed worker. The default is already the deployed address, so it usually
just works. If you use a different address:

```bash
export QUANT_QUOTES_URL="https://<your-worker-address>/api/quotes"
python -m quant web --open
```

Leave the address empty and the cockpit shows settled values only — it does not
fill a missing value with an old quote and call it "live".

---

## Cost — all of it inside the free tiers

- Cloudflare Workers free tier: **100,000 requests a day**
- The worker sorts symbols and caches, so however many people are watching, the
  upstream is called **once every three seconds** (when a live source is on)
- The browser only calls **during the session, and only when the tab is
  visible** → about 3,100 calls per viewer per day
- Crypto goes straight from the browser to Binance, so it costs the worker
  **nothing**

That means about 30 concurrent viewers stay inside the free tier. Past that,
raise `STOCK_MS_OPEN` (the in-session refresh interval) — a test ties that
number to the wording on screen, so one cannot change without the other.

---

## What does not change

**Decisions, fills and records still use only the settled dawn bar.**

Live quotes are for *showing*. Returns, max drawdown, TWR and the kill switch
are all computed from the ledger's settled values. Two reasons:

1. If the valuation moves by the second, so does the drawdown — but the brake
   (the kill switch) runs once, at dawn. The screen and the brake would be
   looking at different numbers.
2. "The same data reproduces the same decision" — this product's central claim
   — would stop being checkable.

So the screen puts the settled value first and prints the "now" value
**underneath** it. The two differing is normal, and the screen always says
which is which.
