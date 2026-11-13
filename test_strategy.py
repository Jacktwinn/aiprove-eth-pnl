#!/usr/bin/env python3
"""Sanity tests for strategy.py. Run: python3 test_strategy.py"""
import copy

from strategy import Strategy, load_bars, positions


def main():
    bars = load_bars("bars.csv")
    pos = positions(bars)

    # shape and domain
    assert len(pos) == len(bars) == 1440, len(pos)
    assert all(p in (-1.0, 0.0, 1.0) for p in pos)

    # incremental Strategy() must reproduce the batch series exactly
    s = Strategy()
    inc = [s.on_bar(b) for b in bars]
    assert inc == pos, "incremental and batch positions differ"

    # causality: truncating or altering FUTURE bars must not change past positions
    cut = 1000
    assert positions(bars[:cut]) == pos[:cut], "lookahead detected (truncation)"
    mutated = copy.deepcopy(bars)
    for b in mutated[cut:]:
        b["close"] = b["close"] * 1.5
        b["open"] = b["open"] * 1.5
    assert positions(mutated)[:cut] == pos[:cut], "lookahead detected (mutation)"

    # few trades by design (cost discipline)
    changes = sum(1 for i in range(1, len(pos)) if pos[i] != pos[i - 1])
    assert changes <= 10, f"too many position changes: {changes}"

    print(f"OK: {len(pos)} bars, {changes} position changes, "
          f"long bars={sum(1 for p in pos if p > 0)}, "
          f"short bars={sum(1 for p in pos if p < 0)}, "
          f"flat bars={sum(1 for p in pos if p == 0)}")


if __name__ == "__main__":
    main()
