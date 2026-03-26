import pandas as pd
import os

TF_NAMES = {
    1: "M1", 5: "M5", 15: "M15", 30: "M30",
    60: "H1", 240: "H4", 1440: "D1",
}

def fetch_all_timeframes(symbol: str, timeframes: list[int], num_bars: int = 500000):
    """
    Load data from local 1M CSV and resample to required timeframes.
    Returns dict mapping tf_minutes -> DataFrame.
    """
    filename = f"data_1m_{symbol.upper()}.csv"
    if not os.path.exists(filename):
        raise FileNotFoundError(f"Local data file {filename} not found. Please run get_free_data.py first.")
        
    print(f"    Loading {filename}...")
    df_1m = pd.read_csv(filename, parse_dates=["time"], index_col="time")
    
    data = {}
    for tf in timeframes:
        name = TF_NAMES.get(tf, f"{tf}m")
        if tf == 1:
            df = df_1m.tail(num_bars).copy()
        else:
            # Resample M1 to higher timeframes
            if tf % 1440 == 0:
                rule = f"{tf//1440}D"
            elif tf % 60 == 0:
                rule = f"{tf//60}h"
            else:
                rule = f"{tf}min"
                
            resampled = df_1m.resample(rule, label='left', closed='left').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            })
            resampled.dropna(inplace=True)
            df = resampled.tail(num_bars).copy()
            
        print(f"    {name}: {len(df)} bars, {df.index[0]} to {df.index[-1]}")
        data[tf] = df
        
    return data
