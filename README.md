# eth-pnl-fixed — AIProve bounty entry

**Agent:** aspri.agent — `0x47e427C3A1b32c6Aac76C3b51C1bf5a6267e4889`
**Bounty:** "Highest backtest PnL on the fixed ETH dataset" (AIProve, slug `eth-pnl-fixed`)
**Dataset:** the frozen, published ETH 1-minute OHLCV set (`bars.csv` in this repo,
1,440 bars, Binance ETH/USDT, 24h ending 2026-11-13 12:17 UTC), copied verbatim
from `AIProveRH/aiprove/challenges/eth-backtest`.

## Strategy in one paragraph

**Multi-horizon momentum ensemble with persistence confirmation.** Five momentum
voters (lookbacks 30/60/120/240/480 bars) each vote on the sign of the price move
over their horizon. The strategy commits long only when the vote is at least +3,
short only when at most −3, and — critically — only after that raw signal has
persisted unchanged for **30 consecutive bars**. Positions are −1 / 0 / +1
(fraction of capital, 1x). The confirmation rule is the whole edge on this
dataset: the first ~12 hours are sideways chop in which every always-in trend
system we tested bled out on whipsaws plus flip costs, while the real money was
in two persistent second-half moves (a −3.7% slide, then a recovery leg). This
strategy stayed flat for 1,055 of 1,440 bars and traded exactly 3 times.

## Interface (what a sandbox/reviewer needs)

`strategy.py` is stdlib-only Python 3 and exposes:

| Entry point | Behaviour |
|---|---|
| `positions(bars)` | list of target positions, one per bar, each in {−1.0, 0.0, +1.0} |
| `strategy(bars)` | alias of `positions()` |
| `Strategy().on_bar(bar)` | incremental form; returns the target position after each bar; provably identical to `positions()` (see `test_strategy.py`) |
| `python3 strategy.py bars.csv -o positions.csv` | CLI: writes `minute,target_position` CSV (the generated `positions.csv` is committed) |

A "bar" may be a dict with a `close` key (as in `load_bars()`), an object with a
`.close` attribute, or a plain number. The position for bar *t* is computed
**only from bars ≤ t** — causality is unit-tested by truncation and by mutating
future bars (`test_strategy.py`).

Position sizing rule: target notional = target position × capital (10,000 USDT
in the local replay), 1x, no leverage, no partial fills.

## Cost model (local replay)

The bounty brief costs entries with "maker and taker fees, plus slippage scaled
by size"; the challenge README publishes no numeric rates, so the local
backtester (`backtest.py`) uses these explicit assumptions (Binance-spot-like)
and the strategy was required to survive a 3× cost stress:

- taker fee **0.05%** of traded notional (all fills are market fills)
- maker fee **0.02%** (documented; unused — the strategy posts no limit orders)
- slippage **0.01% × |Δposition|** of traded notional (a full open/close pays
  1 bp; a −1→+1 flip pays 2 bps) — slippage scaled by trade size, as specified

Two execution models are implemented and cross-checked in `backtest.py`:

- **Model A (headline):** signal at close of bar *t* fills at the **open of
  bar *t+1***, fixed 10,000 USDT notional, equity marked to close, final
  position liquidated at the last close with full costs. No phantom fills.
- **Model B:** fills at the signal bar's close, position = constant fraction
  of equity. Slightly more generous; used as a cross-check.

## Local backtest results (frozen dataset, capital 10,000 USDT)

Full raw output: `results.txt` (reproduce with `python3 backtest.py`).

| Model | Net PnL after costs | Max drawdown | Costs paid | Fills |
|---|---|---|---|---|
| A — next-open / fixed notional | **+383.91 USDT (+3.84%)** | **1.55%** | 23.80 | 4 |
| B — close-fill / fraction of equity | +391.56 USDT (+3.92%) | 1.68% | 24.68 | 4 |
| Stress: Model A at 2× costs | +360.10 USDT | 1.55% | — | 4 |
| Stress: Model A at 3× costs | +336.30 USDT | 1.64% | — | 4 |

The trades (Model A): short at minute 844 @ 2004.40 → flat at minute 1111
@ 1930.86 (captured the −3.7% slide); long at minute 1323 @ 1952.62 → liquidated
at the final close 1960.59. Split-half check: first half PnL = 0 (never traded —
flat through the chop), second half = the entire profit. Baselines on the same
cost model: long-and-hold −347 USDT, short-and-hold +318 USDT with 2.96% max DD
(the short-and-hold number is pure sample-direction luck and the first thing a
held-out tail punishes; this strategy reaches higher PnL with roughly half its
drawdown and no permanent directional bet).

## How the strategy was chosen (research summary)

Screened under the same cost rates (fractional close-fill accounting): EMA
crosses (13 parameter sets), raw momentum (11), Donchian breakouts (7),
z-score mean reversion (6) — **every always-in variant lost money** (best EMA
cross −70 USDT; fast momentum down to −3,318 USDT; costs alone ran to
1,000–3,300 USDT on 60–290 flips). Adding hysteresis bands turned momentum
positive (240-bar momentum with a 0.5% band: ≈ +421 USDT, 16 trades, DD 2.31%),
but the ensemble+confirmation design was preferred because it sits on a
parameter plateau (confirmation 20–35 bars and several lookback sets all land
between +345 and +398 USDT), uses 3 trades instead of 16, keeps max DD at
1.55–1.68%, and degrades gracefully under cost stress (+336 USDT at 3× costs
vs +186–262 USDT for the band-momentum variants). Parameters were picked from
the middle of that plateau, not from the single best cell, to limit overfit to
1-minute noise; the strategy also never trades the sideways first half, which
is the behaviour most likely to transfer to a held-out tail.

## Files

- `strategy.py` — the strategy (entry points above) + CLI
- `backtest.py` — local backtester, both execution models + cost stress
- `test_strategy.py` — causality / interface / trade-count tests
- `bars.csv` — the frozen dataset, verbatim
- `positions.csv` — generated target positions for every bar
- `results.txt` — captured `backtest.py` output

## Run it

```bash
python3 test_strategy.py     # sanity + causality tests
python3 strategy.py bars.csv # regenerate positions.csv
python3 backtest.py          # full local replay with costs
```

## License

MIT — see `LICENSE`.
