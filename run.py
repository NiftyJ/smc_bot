"""
SMC Multi-Timeframe Strategy — Main Runner.

Usage:
  python run.py                          # default: MES (Micro E-mini S&P)
  python run.py --symbol NQ              # E-mini Nasdaq-100
  python run.py --symbol MNQ --risk 250  # Micro Nasdaq, $250 risk/trade
  python run.py --symbol MES --rth-only  # Regular Trading Hours entries only
  python run.py --bars 50000             # limit bars
  python run.py --start 2024-06-01 --end 2024-12-31
  python run.py --list-instruments       # show known futures contracts
"""

import sys
import argparse
import time

import pandas as pd
import numpy as np

# Add parent for imports
sys.path.insert(0, ".")

from config import Config
from instruments import INSTRUMENTS, resolve
from strategy import SMCStrategy
from backtest import compute_metrics, print_report
from report import build_report, save_report


def parse_args():
    p = argparse.ArgumentParser(description="SMC MTF Strategy Backtest")
    p.add_argument("--symbol", default="MES",
                   help="Symbol: ES, MES, NQ, MNQ, YM, RTY, CL, GC ... or an FX pair "
                        "(default MES)")
    p.add_argument("--bars", type=int, default=100000, help="Max M1 bars to fetch")
    p.add_argument("--start", default="", help="Trade start date (YYYY-MM-DD)")
    p.add_argument("--end", default="", help="Trade end date (YYYY-MM-DD)")
    p.add_argument("--capital", type=float, default=10000, help="Initial capital")
    p.add_argument("--risk", type=float, default=250, help="Risk per trade ($)")
    p.add_argument("--commission", type=float, default=-1.0,
                   help="Round-turn commission per contract ($); default = instrument rate")
    p.add_argument("--rth-only", action="store_true",
                   help="Only enter during Regular Trading Hours")
    p.add_argument("--data-tz", default="UTC",
                   help="Timezone of the broker's bar timestamps (default UTC)")
    p.add_argument("--allow-min-qty", action="store_true",
                   help="Take 1 contract even when it exceeds the risk budget")
    p.add_argument("--no-slippage", action="store_true", help="Disable slippage costs")
    p.add_argument("--list-instruments", action="store_true",
                   help="Print the known futures contracts and exit")
    p.add_argument("--min-rr", type=float, default=2.0, help="Minimum RR to enter")
    p.add_argument("--plot", action="store_true", help="Show equity/drawdown plot")
    p.add_argument("--csv", default="", help="Export trades to CSV")
    return p.parse_args()


def main():
    args = parse_args()

    if args.list_instruments:
        print("\nKnown futures contracts:\n")
        for spec in INSTRUMENTS.values():
            print(f"  {spec.name:<5} {spec.summary()}")
        print("\nAnything else is treated as an FX pair.\n")
        return

    cfg = Config(
        symbol=args.symbol,
        mt5_bars=args.bars,
        initial_capital=args.capital,
        risk_per_trade=args.risk,
        min_rr=args.min_rr,
        trade_start=args.start,
        trade_end=args.end,
        commission_override=args.commission,
        rth_only=args.rth_only,
        data_tz=args.data_tz,
        allow_min_qty=args.allow_min_qty,
        apply_slippage=not args.no_slippage,
    )

    print(f"\nInstrument: {cfg.instrument.summary()}")
    print(f"  Risk/trade ${cfg.risk_per_trade:,.0f} | min stop "
          f"{cfg.min_sl_dist:g} ({cfg.instrument.min_sl_ticks} ticks) | "
          f"RTH only: {cfg.rth_only}")
    if cfg.is_futures:
        one_contract_stop = cfg.risk_per_trade / cfg.instrument.multiplier
        print(f"  1 contract risks ${cfg.instrument.multiplier:g} per point — "
              f"${cfg.risk_per_trade:,.0f} of risk = a {one_contract_stop:.2f}-point "
              f"stop on 1 contract")

    # MT5 is Windows-only; import it only once we actually need data
    from mt5_data import init_mt5, shutdown_mt5, fetch_all_timeframes

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
    metrics = compute_metrics(trades, cfg.initial_capital, cfg)
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
