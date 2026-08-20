"""
SMC Multi-Timeframe Strategy — Main Runner.

Usage:
  python run.py                  # default settings
  python run.py --bars 50000     # limit bars
  python run.py --start 2024-06-01 --end 2024-12-31
  python run.py --plot           # show equity curve
"""

import sys
import argparse
import time

import pandas as pd
import numpy as np

# Add parent for imports
sys.path.insert(0, ".")

from config import Config
from mt5_data import init_mt5, shutdown_mt5, fetch_all_timeframes, TF_NAMES
from strategy import SMCStrategy
from backtest import compute_metrics, print_report
from report import build_report, save_report


def parse_args():
    p = argparse.ArgumentParser(description="SMC MTF Strategy Backtest")
    p.add_argument("--symbol", default="EURUSD", help="Symbol (default EURUSD)")
    p.add_argument("--bars", type=int, default=100000, help="Max M1 bars to fetch")
    p.add_argument("--start", default="", help="Trade start date (YYYY-MM-DD)")
    p.add_argument("--end", default="", help="Trade end date (YYYY-MM-DD)")
    p.add_argument("--capital", type=float, default=10000, help="Initial capital")
    p.add_argument("--risk", type=float, default=500, help="Risk per trade ($)")
    p.add_argument("--min-rr", type=float, default=2.0, help="Minimum RR to enter")
    p.add_argument("--venue", default="forex_ecn",
                   help="Cost model: forex_ecn, forex_standard, futures_6e, "
                        "futures_m6e, crypto_perp, legacy_flat")
    p.add_argument("--plot", action="store_true", help="Show equity/drawdown plot")
    p.add_argument("--csv", default="", help="Export trades to CSV")
    return p.parse_args()


def main():
    args = parse_args()

    cfg = Config(
        symbol=args.symbol,
        mt5_bars=args.bars,
        initial_capital=args.capital,
        risk_per_trade=args.risk,
        min_rr=args.min_rr,
        trade_start=args.start,
        trade_end=args.end,
        venue=args.venue,
    )

    # ---- Connect to MT5 ----
    print("[1/4] Connecting to MetaTrader 5...")
    if not init_mt5():
        print("ERROR: Could not connect to MT5. Is the terminal running?")
        sys.exit(1)

    try:
        # ---- Fetch data ----
        print(f"[2/4] Fetching {cfg.symbol} data (up to {cfg.mt5_bars} M1 bars)...")
        timeframes = [cfg.tf_d1, cfg.tf_h4, cfg.tf_h1, cfg.tf_m30, cfg.tf_m5, cfg.tf_m1]
        t0 = time.time()
        data = fetch_all_timeframes(cfg.symbol, timeframes, cfg.mt5_bars)
        print(f"  Data fetched in {time.time() - t0:.1f}s")

        # ---- Compute indicators ----
        print("[3/4] Computing indicators...")
        strategy = SMCStrategy(cfg)
        t0 = time.time()
        ind = strategy.precompute(data)
        print(f"  Indicators computed in {time.time() - t0:.1f}s")

        # ---- Run strategy ----
        print("[4/4] Running strategy...")
        t0 = time.time()
        trades = strategy.run(data, ind)
        elapsed = time.time() - t0
        print(f"  Strategy run in {elapsed:.1f}s ({len(data[cfg.tf_m1])} M1 bars)")

    finally:
        shutdown_mt5()

    if trades.empty:
        print("\nNo trades generated. Check your date range and parameters.")
        return

    # ---- Metrics ----
    metrics = compute_metrics(trades, cfg.initial_capital, cfg.cost_model)
    print_report(metrics, trades)

    # ---- CSV export ----
    if args.csv:
        trades.to_csv(args.csv, index=False)
        print(f"\nTrades exported to {args.csv}")

    # ---- HTML Report (always generated) ----
    print("\nGenerating HTML report...")
    html = build_report(trades, metrics, data, cfg)
    report_path = f"report_{cfg.symbol}.html"
    save_report(html, report_path)

    # Auto-open in browser
    import webbrowser, os
    webbrowser.open("file://" + os.path.abspath(report_path))


if __name__ == "__main__":
    main()
