"""Fetch OHLCV data from MetaTrader 5 terminal."""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone

from instruments import resolve

TF_MAP = {
    1: mt5.TIMEFRAME_M1,
    5: mt5.TIMEFRAME_M5,
    15: mt5.TIMEFRAME_M15,
    30: mt5.TIMEFRAME_M30,
    60: mt5.TIMEFRAME_H1,
    240: mt5.TIMEFRAME_H4,
    1440: mt5.TIMEFRAME_D1,
}

TF_NAMES = {
    1: "M1", 5: "M5", 15: "M15", 30: "M30",
    60: "H1", 240: "H4", 1440: "D1",
}


def init_mt5() -> bool:
    """Initialize MT5 connection. Returns True on success."""
    if not mt5.initialize():
        print(f"MT5 initialize() failed: {mt5.last_error()}")
        return False
    info = mt5.terminal_info()
    if info:
        print(f"  MT5 connected: {info.name} (build {info.build})")
    return True


def shutdown_mt5():
    mt5.shutdown()


def resolve_broker_symbol(symbol: str) -> str:
    """
    Find the broker's spelling of a symbol and make sure it is selected.

    Futures symbols vary a lot between MT5 brokers — the ES E-mini can appear
    as "ES", "ESU5", "ES.cme", "SP500_F" or "[SP500]" — so match on the
    instrument root and its known aliases, preferring the front month.
    Returns the broker symbol, or the input unchanged if nothing better fits.
    """
    if mt5.symbol_info(symbol) is not None:
        mt5.symbol_select(symbol, True)
        return symbol

    spec = resolve(symbol)
    roots = [spec.name] + [a for a in spec.aliases]
    all_syms = mt5.symbols_get() or []

    def norm(s: str) -> str:
        return "".join(ch for ch in s.upper() if ch.isalnum())

    matches = []
    for s in all_syms:
        n = norm(s.name)
        for root in roots:
            r = norm(root)
            # exact root, or root + contract-month suffix (e.g. MESU5, ESZ25)
            if n == r or (n.startswith(r) and len(n) - len(r) <= 3):
                matches.append(s.name)
                break

    if not matches:
        print(f"  WARNING: no broker symbol found for {symbol} "
              f"({spec.description}). Check Market Watch / symbol naming.")
        return symbol

    # Prefer the shortest (continuous/front-month) spelling
    matches.sort(key=lambda x: (len(x), x))
    chosen = matches[0]
    if chosen != symbol:
        print(f"  Symbol '{symbol}' -> broker symbol '{chosen}' "
              f"({spec.description})")
    mt5.symbol_select(chosen, True)
    return chosen


def fetch_ohlcv(symbol: str, tf_minutes: int, num_bars: int) -> pd.DataFrame:
    """
    Fetch OHLCV data from MT5.
    Returns DataFrame with DatetimeIndex and columns: open, high, low, close, volume.
    """
    mt5_tf = TF_MAP.get(tf_minutes)
    if mt5_tf is None:
        raise ValueError(f"Unsupported timeframe: {tf_minutes} minutes")

    rates = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, num_bars)
    if rates is None or len(rates) == 0:
        raise RuntimeError(
            f"Failed to fetch {TF_NAMES.get(tf_minutes, tf_minutes)} data for {symbol}: "
            f"{mt5.last_error()}"
        )

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    df.rename(columns={"tick_volume": "volume"}, inplace=True)
    df = df[["open", "high", "low", "close", "volume"]].copy()
    df.sort_index(inplace=True)
    return df


def fetch_all_timeframes(symbol: str, timeframes: list[int],
                         num_bars: int = 100000) -> dict[int, pd.DataFrame]:
    """
    Fetch data for all required timeframes from MT5.
    Returns dict mapping tf_minutes -> DataFrame.
    """
    data = {}
    symbol = resolve_broker_symbol(symbol)
    for tf in timeframes:
        name = TF_NAMES.get(tf, f"{tf}m")
        # Scale bars relative to M1 request; cap per-TF to avoid MT5 errors
        if tf == 1:
            bars = min(num_bars, 99000)
        elif tf == 5:
            bars = min(num_bars // 5 + 1000, 80000)
        elif tf <= 30:
            bars = min(num_bars // tf + 500, 30000)
        elif tf <= 240:
            bars = min(num_bars // tf + 500, 15000)
        else:
            bars = min(num_bars // tf + 500, 10000)
        df = fetch_ohlcv(symbol, tf, bars)
        print(f"    {name}: {len(df)} bars, {df.index[0]} to {df.index[-1]}")
        data[tf] = df
    return data
