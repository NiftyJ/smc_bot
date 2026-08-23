"""
Backtest SMC strategy on 1 year of data for EURUSD and GBPUSD.
Generates separate HTML reports for each symbol.

Usage:
  python run_backtest_1y.py
"""

import sys
import time
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

sys.path.insert(0, ".")

from config import Config
from mt5_data import init_mt5, shutdown_mt5, fetch_all_timeframes, TF_NAMES
from strategy import SMCStrategy
from backtest import compute_metrics, print_report
from report import build_report, save_report


SYMBOLS = ["EURUSD", "GBPUSD"]

# 1 year back from today
END_DATE = datetime.now().strftime("%Y-%m-%d")
START_DATE = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

# ~375k M1 bars covers 1 year of forex (260 trading days * 24h * 60m)
# Request 500k to have margin; MT5 will return what's available
MAX_BARS = 500000


def run_symbol(symbol: str):
    """Run full backtest for one symbol."""
    print(f"\n{'='*60}")
    print(f"  BACKTESTING {symbol}  |  {START_DATE} to {END_DATE}")
    print(f"{'='*60}")

    cfg = Config(
        symbol=symbol,
        mt5_bars=MAX_BARS,
        initial_capital=10000,
        risk_per_trade=500,
        min_rr=2.0,
        trade_start=START_DATE,
        trade_end=END_DATE,
    )

    # Fetch data
    print(f"\n[1/4] Fetching {symbol} data (up to {MAX_BARS} M1 bars)...")
    timeframes = [cfg.tf_d1, cfg.tf_h4, cfg.tf_h1, cfg.tf_m30, cfg.tf_m5, cfg.tf_m1]
    t0 = time.time()
    data = fetch_all_timeframes(symbol, timeframes, MAX_BARS)
    print(f"  Data fetched in {time.time() - t0:.1f}s")

    # Compute indicators
    print("[2/4] Computing indicators...")
    strategy = SMCStrategy(cfg)
    t0 = time.time()
    ind = strategy.precompute(data)
    print(f"  Indicators computed in {time.time() - t0:.1f}s")

    # Run strategy
    print("[3/4] Running strategy...")
    t0 = time.time()
    trades = strategy.run(data, ind)
    elapsed = time.time() - t0
    print(f"  Strategy run in {elapsed:.1f}s ({len(data[cfg.tf_m1])} M1 bars)")

    if trades.empty:
        print(f"\n  No trades generated for {symbol}.")
        return

    # Metrics
    metrics = compute_metrics(trades, cfg.initial_capital, cfg.commission_per_lot, cfg.contract_size)
    print_report(metrics, trades)

    # HTML Report
    print("\n[4/4] Generating HTML report...")
    html = build_report(trades, metrics, data, cfg)
    report_name = f"backtest_1y_{symbol}_{START_DATE}_to_{END_DATE}.html"
    save_report(html, report_name)

    # CSV export
    csv_name = f"trades_1y_{symbol}.csv"
    trades.to_csv(csv_name, index=False)
    print(f"  Trades exported to {csv_name}")

    return report_name


def main():
    print("SMC Multi-Timeframe Strategy — 1-Year Backtest")
    print(f"Symbols: {', '.join(SYMBOLS)}")
    print(f"Period:  {START_DATE} to {END_DATE}")

    # Connect to MT5
    print("\nConnecting to MetaTrader 5...")
    if not init_mt5():
        print("ERROR: Could not connect to MT5. Is the terminal running?")
        sys.exit(1)

    reports = []
    try:
        for symbol in SYMBOLS:
            result = run_symbol(symbol)
            if result:
                reports.append(result)
    finally:
        shutdown_mt5()

    # Summary
    print(f"\n{'='*60}")
    print(f"  DONE — {len(reports)} reports generated:")
    for r in reports:
        print(f"    {r}")
    print(f"{'='*60}")

    # Auto-open reports
    import webbrowser, os
    for r in reports:
        webbrowser.open("file://" + os.path.abspath(r))


if __name__ == "__main__":
    main()
