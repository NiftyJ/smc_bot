"""Compare a trade log's net result across venues.

Usage:
    python compare_venues.py trades.csv

The strategy's own PnL never changes — only the cost of executing it does.
This shows whether the edge survives each venue's fee structure, and how much
of gross profit each one consumes.
"""

import sys

import pandas as pd

from backtest import compute_metrics
from costs import PRESETS


def compare(trades: pd.DataFrame, initial_capital: float = 10_000.0) -> pd.DataFrame:
    """Recompute metrics under every cost preset."""
    rows = []
    for venue in PRESETS:
        m = compute_metrics(trades, initial_capital, venue)
        gross = m["net_pnl"] + m["total_commissions"]
        rows.append({
            "venue": venue,
            "net_pnl": m["net_pnl"],
            "gross_pnl": round(gross, 2),
            "costs": m["total_commissions"],
            "cost_per_trade": m["avg_commission"],
            "cost_pct_of_gross": (round(m["total_commissions"] / abs(gross) * 100, 1)
                                  if gross else float("inf")),
            "profit_factor": m["profit_factor"],
            "max_dd_pct": m["max_drawdown_pct"],
        })
    return pd.DataFrame(rows)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    trades = pd.read_csv(sys.argv[1])
    capital = float(sys.argv[2]) if len(sys.argv) > 2 else 10_000.0

    if "qty" not in trades.columns:
        print("WARNING: trade log has no 'qty' column — costs cannot be scaled "
              "to position size and this comparison is meaningless.")

    df = compare(trades, capital)
    print(f"\n{len(trades)} trades, ${capital:,.0f} starting capital\n")
    print(df.to_string(index=False))

    avg_qty = trades["qty"].mean() if "qty" in trades.columns else float("nan")
    print(f"\nAvg position size: {avg_qty:,.0f} units "
          f"({avg_qty / 100_000:,.1f} standard lots)")


if __name__ == "__main__":
    main()
