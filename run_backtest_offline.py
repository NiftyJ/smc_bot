import sys
import time
import pandas as pd
from datetime import datetime

sys.path.insert(0, ".")

from config import Config
from histdata_loader import fetch_all_timeframes
from strategy import SMCStrategy
from backtest import compute_metrics, print_report
from report import build_report, save_report

SYMBOLS = ["EURUSD", "GBPUSD"]
MAX_BARS = 500000

def run_symbol(symbol: str):
    print(f"\n{'='*60}")
    print(f"  OFFLINE BACKTESTING {symbol}")
    print(f"{'='*60}")

    # Initialize config, using default dates which will be overwritten by data bounds in report
    cfg = Config(
        symbol=symbol,
        mt5_bars=MAX_BARS,
        initial_capital=10000,
        risk_per_trade=500,
        min_rr=2.0
    )

    print(f"\n[1/4] Loading local {symbol} data...")
    timeframes = [cfg.tf_d1, cfg.tf_h4, cfg.tf_h1, cfg.tf_m30, cfg.tf_m5, cfg.tf_m1]
    t0 = time.time()
    try:
        data = fetch_all_timeframes(symbol, timeframes, MAX_BARS)
    except Exception as e:
        print(f"Error loading data: {e}")
        return None
    print(f"  Data loaded and resampled in {time.time() - t0:.1f}s")
    
    # Adjust config dates to match actual loaded data range
    start_dt = data[1].index[0].strftime("%Y-%m-%d")
    end_dt = data[1].index[-1].strftime("%Y-%m-%d")
    cfg.trade_start = start_dt
    cfg.trade_end = end_dt
    
    print(f"  Period: {start_dt} to {end_dt}")

    print("[2/4] Computing indicators...")
    strategy = SMCStrategy(cfg)
    t0 = time.time()
    ind = strategy.precompute(data)
    print(f"  Indicators computed in {time.time() - t0:.1f}s")

    print("[3/4] Running strategy...")
    t0 = time.time()
    trades = strategy.run(data, ind)
    elapsed = time.time() - t0
    print(f"  Strategy run in {elapsed:.1f}s ({len(data[cfg.tf_m1])} M1 bars)")

    if trades.empty:
        print(f"\n  No trades generated for {symbol}.")
        return None

    metrics = compute_metrics(trades, cfg.initial_capital, cfg.cost_model)
    print_report(metrics, trades)

    print("\n[4/4] Generating HTML report...")
    html = build_report(trades, metrics, data, cfg)
    report_name = f"backtest_offline_{symbol}_{start_dt}_to_{end_dt}.html"
    save_report(html, report_name)

    csv_name = f"trades_offline_{symbol}.csv"
    trades.to_csv(csv_name, index=False)
    print(f"  Trades exported to {csv_name}")

    return report_name

def main():
    print("SMC Multi-Timeframe Strategy — Offline Backtest")
    print(f"Symbols: {', '.join(SYMBOLS)}")

    reports = []
    for symbol in SYMBOLS:
        result = run_symbol(symbol)
        if result:
            reports.append(result)

    print(f"\n{'='*60}")
    print(f"  DONE — {len(reports)} reports generated:")
    for r in reports:
        print(f"    {r}")
    print(f"{'='*60}")

    import webbrowser, os
    for r in reports:
        webbrowser.open("file://" + os.path.abspath(r))

if __name__ == "__main__":
    main()
