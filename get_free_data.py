import os
import zipfile
import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime

def download_zip(year: str, pair: str, month=None):
    """Downloads the ZIP file from histdata.com bypassing the buggy python package."""
    pair = pair.lower()
    if month is None:
        referer = f"https://www.histdata.com/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/{pair}/{year}"
    else:
        referer = f"https://www.histdata.com/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/{pair}/{year}/{month}"
    
    headers = {'Referer': referer, 'User-Agent': 'Mozilla/5.0'}
    try:
        r = requests.get(referer, headers=headers)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content, 'html.parser')
        token = soup.find('input', {'id': 'tk'}).attrs['value']
    except Exception as e:
        print(f"      - Could not get token: {e}")
        return None

    data = {
        'tk': token,
        'date': str(year),
        'datemonth': f"{year}{str(month).zfill(2)}" if month is not None else str(year),
        'platform': 'ASCII',
        'timeframe': 'M1',
        'fxpair': pair.upper()
    }
    
    r2 = requests.post('https://www.histdata.com/get.php', data=data, headers=headers)
    if len(r2.content) == 0:
        return None
        
    out = f"DAT_{pair.upper()}_{year}{str(month).zfill(2) if month else ''}.zip"
    with open(out, 'wb') as f:
         f.write(r2.content)
    return out

def process_zip(zip_path, all_dfs):
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            csv_files = [f for f in zip_ref.namelist() if f.endswith('.csv')]
            for csv_file in csv_files:
                zip_ref.extract(csv_file, path=".")
                
                # Format for HistData ASCII:
                # YYYYMMDD HHMMSS;Open;High;Low;Close;Volume
                df = pd.read_csv(
                    csv_file,
                    sep=';',
                    names=['time', 'open', 'high', 'low', 'close', 'volume']
                )
                
                # Convert 'time' string to datetime
                df['time'] = pd.to_datetime(df['time'], format='%Y%m%d %H%M%S')
                all_dfs.append(df)
                
                # Cleanup extracted csv
                os.remove(csv_file)
    except Exception as e:
        print(f"    Error processing zip: {e}")
    finally:
        os.remove(zip_path)

def download_symbol(symbol: str, out_file: str):
    """Download HistData M1 CSVs for 2024 and 2025."""
    symbol = symbol.lower()
    all_dfs = []
    
    print(f"\n--- Downloading data for {symbol.upper()} ---")
    
    # 2024 (past year) is a single zip
    print(f"  Fetching full year 2024...")
    zip_path_2024 = download_zip(year='2024', pair=symbol, month=None)
    if zip_path_2024 and os.path.exists(zip_path_2024):
        print("    Downloaded 2024 successfully.")
        process_zip(zip_path_2024, all_dfs)
    else:
        print("    Failed to download 2024.")
         
    # 2025 (current year) requires downloading monthly
    print(f"  Fetching 2025 months...")
    for m in range(1, datetime.now().month + 1):
        month_str = str(m)
        print(f"    Month {month_str.zfill(2)}...")
        zip_path = download_zip(year='2025', pair=symbol, month=month_str)
        if zip_path and os.path.exists(zip_path):
             process_zip(zip_path, all_dfs)
        else:
             print(f"    (Skipped {m}: not fully available)")

    if not all_dfs:
        print(f"No data recovered for {symbol}.")
        return None
        
    print(f"  Combining all downloaded data for {symbol.upper()}...")
    combined = pd.concat(all_dfs, ignore_index=True)
    combined.sort_values('time', inplace=True)
    combined.set_index('time', inplace=True)
    
    # Drop duplicates
    combined = combined[~combined.index.duplicated(keep='first')]
    
    print(f"  Saving to {out_file} ({len(combined)} rows)")
    combined.to_csv(out_file)
    return out_file

# HistData publishes index and metal M1 bars alongside the forex pairs. These
# are cash/CFD quotes, not exchange futures prints: the price path tracks the
# front-month contract closely but session hours, gaps and spread do not match,
# so treat results as an approximation of the futures market, not a replica.
HISTDATA_SYMBOLS = {
    "NQ": "nsxusd",       # Nasdaq 100 cash index
    "ES": "spxusd",       # S&P 500 cash index
    "XAUUSD": "xauusd",   # Spot gold
    "EURUSD": "eurusd",
    "GBPUSD": "gbpusd",
}


if __name__ == "__main__":
    import sys

    wanted = [s.upper() for s in sys.argv[1:]] or ["NQ", "ES", "XAUUSD"]
    for sym in wanted:
        if sym not in HISTDATA_SYMBOLS:
            print(f"No HistData feed known for {sym}. "
                  f"Options: {', '.join(HISTDATA_SYMBOLS)}")
            continue
        download_symbol(HISTDATA_SYMBOLS[sym], f"data_1m_{sym}.csv")
    print("\nDownload complete!")
