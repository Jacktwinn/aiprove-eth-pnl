#!/usr/bin/env python3
"""
Strategy for the AIProve `eth-pnl-fixed` bounty: trade the frozen ETH
1-minute dataset (bars.csv, 1,440 bars) for the highest net PnL after costs,
with max drawdown as the tie-break.

Strategy: multi-horizon momentum ensemble with persistence confirmation.

  * At each bar t, five momentum voters look back 30 / 60 / 120 / 240 / 480
    bars and each votes +1 if close[t] > close[t-lookback], else -1.
  * The raw signal is +1 (long) when the vote sum is >= +3, -1 (short) when
    it is <= -3, and 0 (flat) otherwise. A majority of horizons must agree
    on the same direction before the strategy commits.
  * A raw signal only becomes the target position after it has persisted,
    unchanged, for 30 consecutive bars (confirmation). Any flicker resets
    the counter. This is what keeps the strategy flat through sideways,
    choppy stretches where cost-bearing whipsaws destroy fast systems.

Positions are target fractions of capital in {-1.0, 0.0, +1.0}
(-1 = fully short, 0 = flat, +1 = fully long, 1x, no leverage).

The strategy is strictly causal: the position for bar t is computed only
from bars <= t. No future data is ever read.

Interfaces provided (sandbox-friendly, stdlib only):
  * positions(bars)      -> list[float]  one target position per bar
  * strategy(bars)       -> alias of positions()
  * Strategy             -> incremental: .on_bar(bar) -> target position
  * CLI: python3 strategy.py bars.csv [-o positions.csv]
    writes a CSV with columns minute,target_position and prints a summary.

A "bar" may be a dict with a "close" key (as parsed from bars.csv), an
object with a .close attribute, or a plain number (the close itself).
"""

import csv
import sys

LOOKBACKS = (30, 60, 120, 240, 480)
VOTE_THRESHOLD = 3
CONFIRM_BARS = 30


def _close_of(bar):
    if isinstance(bar, (int, float)):
        return float(bar)
    if isinstance(bar, dict):
        return float(bar["close"])
    return float(bar.close)


def _raw_signal(closes, t):
    votes = 0
    for look in LOOKBACKS:
        if t >= look:
            votes += 1 if closes[t] > closes[t - look] else -1
    if votes >= VOTE_THRESHOLD:
        return 1.0
    if votes <= -VOTE_THRESHOLD:
        return -1.0
    return 0.0


def positions(bars):
    """Return the target position (in {-1.0, 0.0, 1.0}) for every bar."""
    closes = [_close_of(b) for b in bars]
    out = []
    current = 0.0
    pending = None
    run = 0
    for t in range(len(closes)):
        sig = _raw_signal(closes, t)
        if sig == current:
            pending, run = None, 0
        elif sig == pending:
            run += 1
        else:
            pending, run = sig, 1
        if pending is not None and run >= CONFIRM_BARS:
            current, pending, run = pending, None, 0
        out.append(current)
    return out


# The sandbox may look for a plainly-named entry point; provide the alias.
def strategy(bars):
    return positions(bars)


class Strategy:
    """Incremental form of the same logic: feed bars, get target positions.

    Produces exactly the same position series as positions() (covered by
    test_strategy.py).
    """

    def __init__(self):
        self._closes = []
        self._current = 0.0
        self._pending = None
        self._run = 0

    def on_bar(self, bar):
        self._closes.append(_close_of(bar))
        t = len(self._closes) - 1
        sig = _raw_signal(self._closes, t)
        if sig == self._current:
            self._pending, self._run = None, 0
        elif sig == self._pending:
            self._run += 1
        else:
            self._pending, self._run = sig, 1
        if self._pending is not None and self._run >= CONFIRM_BARS:
            self._current, self._pending, self._run = self._pending, None, 0
        return self._current


def load_bars(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    bars = []
    for r in rows:
        bars.append(
            {
                "minute": int(r["minute"]),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": float(r["volume"]),
            }
        )
    return bars


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    src = argv[1]
    out_path = "positions.csv"
    if "-o" in argv:
        out_path = argv[argv.index("-o") + 1]
    bars = load_bars(src)
    pos = positions(bars)
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["minute", "target_position"])
        for i, p in enumerate(pos):
            w.writerow([i, int(p)])
    changes = sum(1 for i in range(1, len(pos)) if pos[i] != pos[i - 1])
    if pos and pos[0] != 0.0:
        changes += 1
    print(
        f"bars={len(bars)} position_changes={changes} "
        f"final_position={pos[-1] if pos else 0:+.0f} wrote={out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
