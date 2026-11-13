#!/usr/bin/env python3
"""
Local backtester for the AIProve `eth-pnl-fixed` strategy (strategy.py).

It replicates, as closely as the published material allows, the cost model
the bounty brief describes: "maker and taker fees, plus slippage scaled by
size". The official challenge README does not publish numeric fee/slippage
rates, so the rates below are explicit, documented assumptions (chosen at
typical Binance spot levels) and the strategy was selected to stay
profitable even at 3x these costs (see README.md, robustness section).

Cost model (all fills are market/taker fills; the strategy never posts
resting limit orders, so the maker rate is documented but unused):
  * taker fee   = 0.05% of traded notional
  * maker fee   = 0.02% of traded notional (unused by this strategy)
  * slippage    = 0.01% x (traded notional / position notional unit),
    i.e. slippage scales with the size of the position change:
    opening/closing a full position (|delta| = 1) pays 1 bp of slippage,
    flipping from -1 to +1 (|delta| = 2) pays 2 bps.

Two independent execution models are implemented and cross-checked:

  Model A (primary, "next-open / fixed notional"):
    A signal computed at the close of bar t is filled at the OPEN of bar
    t+1 (no phantom fills, no trading on the same close that produced the
    signal). Position size is a fixed 10,000 USDT notional at 1x:
    qty = target_position x 10,000 / fill_price, held fixed until the next
    fill. Equity is marked to each bar's close. Any position still open
    after the last bar is liquidated at the last close, paying full costs.

  Model B (cross-check, "close-fill / fractional"):
    Position changes fill at the close of the signal bar; the position is
    a constant fraction of current equity. Same cost formula. This model
    is slightly more generous (it earns the signal bar's own next move at
    the close price), so Model A is the headline number.

Capital: 10,000 USDT. PnL is reported in USDT and % of capital.
Max drawdown is the largest peak-to-trough fall of the marked equity curve.

Usage: python3 backtest.py [bars.csv]
"""

import sys

from strategy import load_bars, positions

CAPITAL = 10_000.0
TAKER_FEE = 0.0005  # 0.05%
MAKER_FEE = 0.0002  # 0.02% (documented; unused, strategy uses market fills)
SLIPPAGE_BASE = 0.0001  # 0.01% at |delta position| = 1, scaled by size


def _trade_cost(traded_notional, delta_fraction, taker=TAKER_FEE, slip=SLIPPAGE_BASE):
    """Fee + size-scaled slippage for one fill."""
    return traded_notional * (taker + slip * abs(delta_fraction))


def backtest_next_open(bars, pos, taker=TAKER_FEE, slip=SLIPPAGE_BASE):
    opens = [b["open"] for b in bars]
    closes = [b["close"] for b in bars]
    n = len(bars)
    cash = CAPITAL
    qty = 0.0
    cur_frac = 0.0
    peak = CAPITAL
    max_dd = 0.0
    total_costs = 0.0
    fills = []
    for t in range(n - 1):
        target = pos[t]
        if target != cur_frac:
            px = opens[t + 1]
            new_qty = target * CAPITAL / px
            cost = _trade_cost(abs(new_qty - qty) * px, target - cur_frac, taker, slip)
            cash -= (new_qty - qty) * px + cost
            total_costs += cost
            qty = new_qty
            fills.append((t + 1, cur_frac, target, px, cost))
            cur_frac = target
        equity = cash + qty * closes[t + 1]
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak if peak > 0 else 0.0)
    if qty != 0.0:  # liquidate at the last close, paying full costs
        px = closes[-1]
        cost = _trade_cost(abs(qty) * px, cur_frac, taker, slip)
        cash += qty * px - cost
        total_costs += cost
        fills.append((n - 1, cur_frac, 0.0, px, cost))
        qty = 0.0
    return {
        "model": "A next-open/fixed-notional",
        "pnl": cash - CAPITAL,
        "final_equity": cash,
        "max_drawdown": max_dd,
        "total_costs": total_costs,
        "fills": fills,
    }


def backtest_close_fraction(bars, pos, taker=TAKER_FEE, slip=SLIPPAGE_BASE):
    closes = [b["close"] for b in bars]
    n = len(bars)
    equity = CAPITAL
    peak = CAPITAL
    max_dd = 0.0
    total_costs = 0.0
    prev = 0.0
    fills = []
    for t in range(n - 1):
        p = pos[t]
        if p != prev:
            cost = _trade_cost(equity * abs(p - prev), p - prev, taker, slip)
            equity -= cost
            total_costs += cost
            fills.append((t, prev, p, closes[t], cost))
            prev = p
        equity += equity * p * (closes[t + 1] / closes[t] - 1.0)
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak if peak > 0 else 0.0)
    if prev != 0.0:  # liquidate at the last close
        cost = _trade_cost(equity * abs(prev), prev, taker, slip)
        equity -= cost
        total_costs += cost
        fills.append((n - 1, prev, 0.0, closes[-1], cost))
    return {
        "model": "B close-fill/fraction-of-equity",
        "pnl": equity - CAPITAL,
        "final_equity": equity,
        "max_drawdown": max_dd,
        "total_costs": total_costs,
        "fills": fills,
    }


def _report(res):
    print(f"Model {res['model']}")
    print(f"  net PnL after costs : {res['pnl']:+.2f} USDT ({res['pnl'] / CAPITAL * 100:+.2f}%)")
    print(f"  final equity        : {res['final_equity']:.2f} USDT")
    print(f"  max drawdown        : {res['max_drawdown'] * 100:.2f}%")
    print(f"  total costs paid    : {res['total_costs']:.2f} USDT")
    print(f"  fills (incl. final liquidation): {len(res['fills'])}")
    for minute, frm, to, px, cost in res["fills"]:
        print(f"    minute {minute:>4}: {frm:+.0f} -> {to:+.0f} @ {px:.2f}  cost {cost:.2f}")
    print()


def main(argv):
    path = argv[1] if len(argv) > 1 else "bars.csv"
    bars = load_bars(path)
    pos = positions(bars)
    print(f"bars={len(bars)} capital={CAPITAL:.0f} USDT taker={TAKER_FEE * 100:.2f}% "
          f"maker={MAKER_FEE * 100:.2f}% slippage_base={SLIPPAGE_BASE * 100:.2f}% x |delta|")
    print()
    _report(backtest_next_open(bars, pos))
    _report(backtest_close_fraction(bars, pos))
    # cost stress on the primary model: the strategy must survive fee surprises
    for mult in (2, 3):
        res = backtest_next_open(bars, pos, taker=TAKER_FEE * mult, slip=SLIPPAGE_BASE * mult)
        print(f"Stress x{mult} costs (Model A): net PnL {res['pnl']:+.2f} USDT, "
              f"max DD {res['max_drawdown'] * 100:.2f}%, fills {len(res['fills'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
