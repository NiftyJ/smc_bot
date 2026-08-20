"""Per-instrument cost arithmetic, independent of any price history.

Whether a fixed-R strategy survives its costs is decided by one ratio: the
round-turn cost of a trade divided by the money risked on it. That ratio
depends only on the stop distance and the contract spec, so it can be computed
without a single bar of data — and it sets a hard floor on the win rate the
strategy must clear before it can make money.

Usage:
    python cost_analysis.py                 # all instruments
    python cost_analysis.py NQ MNQ ES       # selected symbols
"""

import math
import sys

import pandas as pd

from instruments import INSTRUMENTS, get_instrument


def breakeven_win_rate(risk: float, cost: float, rr: float) -> float:
    """Win rate needed to break even at reward-to-risk ``rr`` after costs.

    A winner nets ``rr * risk - cost``; a loser costs ``risk + cost``.
    """
    return (risk + cost) / (risk * (rr + 1.0))


def analyse(symbol: str, risk_per_trade: float = 500.0, rr: float = 2.0,
            stop_ticks: list[float] | None = None) -> pd.DataFrame:
    """Cost and breakeven table across a range of stop distances."""
    inst = get_instrument(symbol)

    if stop_ticks is None:
        base = inst.min_stop_ticks
        stop_ticks = [base * m for m in (1, 2, 4, 8, 16)]

    rows = []
    for ticks in stop_ticks:
        stop_price = ticks * inst.tick_size
        risk_per_contract = stop_price * inst.value_per_point

        ideal = risk_per_trade / risk_per_contract
        traded = max(1, math.ceil(ideal)) if inst.whole_contracts else ideal
        actual_risk = traded * risk_per_contract

        commission = traded * inst.commission_rt
        spread = traded * inst.spread_ticks * inst.tick_value
        cost = commission + spread

        rows.append({
            "stop_ticks": ticks,
            "stop_price": round(stop_price, 5),
            "risk_per_contract": round(risk_per_contract, 2),
            "ideal_contracts": round(ideal, 2),
            "traded_contracts": round(traded, 2),
            "actual_risk": round(actual_risk, 2),
            "cost_rt": round(cost, 2),
            "cost_pct_of_risk": round(cost / actual_risk * 100, 1),
            f"breakeven_wr_{rr:g}R": round(
                breakeven_win_rate(actual_risk, cost, rr) * 100, 1),
        })
    return pd.DataFrame(rows)


def main():
    symbols = sys.argv[1:] or list(INSTRUMENTS)
    risk, rr = 500.0, 2.0

    print(f"\nRisk per trade ${risk:,.0f}, target {rr:g}R.")
    print(f"Breakeven win rate with zero costs would be "
          f"{breakeven_win_rate(risk, 0, rr) * 100:.1f}%.\n")

    for sym in symbols:
        inst = get_instrument(sym)
        print("=" * 78)
        print(f"{inst.symbol} — {inst.name}")
        print(f"  tick {inst.tick_size:g} = ${inst.tick_value:,.2f}/contract | "
              f"commission ${inst.commission_rt:.2f} RT | "
              f"spread {inst.spread_ticks:g} ticks")
        print(analyse(sym, risk, rr).to_string(index=False))
        print()


if __name__ == "__main__":
    main()
