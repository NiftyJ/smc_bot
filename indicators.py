"""
Full SMC indicator suite — TRADING_LOGIC.md implementation.

Includes: pivot detection, bias, BOS/CHoCH, Wyckoff RSI ranges,
Order Blocks, FVGs, Equal Highs/Lows, HTF swing levels.
"""

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# 1. Pivot Detection
# ---------------------------------------------------------------------------

def detect_pivots(df: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """
    Detect pivot highs/lows with confirmation delay.
    Pivot high at bar i: high[i] is highest in [i-lookback, i+lookback].
    Confirmed lookback bars late (like Pine ta.pivothigh/low).
    """
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)

    ph = np.full(n, np.nan)
    pl = np.full(n, np.nan)

    for i in range(lookback, n - lookback):
        window_h = highs[i - lookback: i + lookback + 1]
        if highs[i] == window_h.max() and np.sum(window_h == highs[i]) == 1:
            confirm_idx = i + lookback
            if confirm_idx < n:
                ph[confirm_idx] = highs[i]

        window_l = lows[i - lookback: i + lookback + 1]
        if lows[i] == window_l.min() and np.sum(window_l == lows[i]) == 1:
            confirm_idx = i + lookback
            if confirm_idx < n:
                pl[confirm_idx] = lows[i]

    result = df[["open", "high", "low", "close"]].copy()
    if "volume" in df.columns:
        result["volume"] = df["volume"]
    result["pivot_high"] = ph
    result["pivot_low"] = pl
    return result


# ---------------------------------------------------------------------------
# 2. Bias Calculation (HH/HL/LH/LL + BOS override)
# ---------------------------------------------------------------------------

def compute_bias(df: pd.DataFrame, lookback: int, use_close: bool) -> pd.Series:
    """
    Structural bias per bar.
    HH + HL => bull (1), LH + LL => bear (-1).
    BOS (close breaking swing level) also shifts bias.
    """
    df_piv = detect_pivots(df, lookback)
    n = len(df_piv)
    bias = np.zeros(n, dtype=int)

    sh1 = sh2 = sl1 = sl2 = np.nan
    current_bias = 0

    closes = df_piv["close"].values
    highs = df_piv["high"].values
    lows = df_piv["low"].values
    phs = df_piv["pivot_high"].values
    pls = df_piv["pivot_low"].values

    for i in range(n):
        if not np.isnan(phs[i]):
            sh2 = sh1
            sh1 = phs[i]
        if not np.isnan(pls[i]):
            sl2 = sl1
            sl1 = pls[i]

        if not np.isnan(sh1) and not np.isnan(sh2) and \
           not np.isnan(sl1) and not np.isnan(sl2):
            if sh1 > sh2 and sl1 > sl2:
                current_bias = 1
            elif sh1 < sh2 and sl1 < sl2:
                current_bias = -1

        break_src = closes[i] if use_close else highs[i]
        break_src_low = closes[i] if use_close else lows[i]

        if i > 0 and not np.isnan(sh1):
            prev = closes[i - 1] if use_close else highs[i - 1]
            if break_src > sh1 and prev <= sh1:
                current_bias = 1
        if i > 0 and not np.isnan(sl1):
            prev = closes[i - 1] if use_close else lows[i - 1]
            if break_src_low < sl1 and prev >= sl1:
                current_bias = -1

        bias[i] = current_bias

    return pd.Series(bias, index=df.index, name="bias")


# ---------------------------------------------------------------------------
# 3. BOS / CHoCH Detection
# ---------------------------------------------------------------------------

def compute_bos(df: pd.DataFrame, lookback: int, use_close: bool) -> pd.DataFrame:
    """
    Detect Break of Structure events.
    Returns: bos_bull, bos_bear, bos_dir, bos_count,
             bos_break_high, bos_break_low, sh1, sl1.
    """
    df_piv = detect_pivots(df, lookback)
    n = len(df_piv)

    bos_bull = np.zeros(n, dtype=bool)
    bos_bear = np.zeros(n, dtype=bool)
    bos_dir = np.zeros(n, dtype=int)
    bos_count = np.zeros(n, dtype=int)
    bos_break_high = np.full(n, np.nan)
    bos_break_low = np.full(n, np.nan)
    sh1_arr = np.full(n, np.nan)
    sl1_arr = np.full(n, np.nan)

    sh1 = sl1 = np.nan
    _dir = 0
    _count = 0
    _bh = _bl = np.nan

    closes = df_piv["close"].values
    highs = df_piv["high"].values
    lows = df_piv["low"].values
    phs = df_piv["pivot_high"].values
    pls = df_piv["pivot_low"].values

    for i in range(n):
        if not np.isnan(phs[i]):
            sh1 = phs[i]
        if not np.isnan(pls[i]):
            sl1 = pls[i]

        sh1_arr[i] = sh1
        sl1_arr[i] = sl1

        if i > 0 and not np.isnan(sh1):
            if closes[i] > sh1 and closes[i - 1] <= sh1:
                bos_bull[i] = True
                if _dir == 1:
                    _count += 1
                else:
                    _dir = 1
                    _count = 1
                _bh = highs[i]
                _bl = lows[i]

        if i > 0 and not np.isnan(sl1):
            if closes[i] < sl1 and closes[i - 1] >= sl1:
                bos_bear[i] = True
                if _dir == -1:
                    _count += 1
                else:
                    _dir = -1
                    _count = 1
                _bh = highs[i]
                _bl = lows[i]

        bos_dir[i] = _dir
        bos_count[i] = _count
        bos_break_high[i] = _bh
        bos_break_low[i] = _bl

    return pd.DataFrame({
        "bos_bull": bos_bull, "bos_bear": bos_bear,
        "bos_dir": bos_dir, "bos_count": bos_count,
        "bos_break_high": bos_break_high, "bos_break_low": bos_break_low,
        "sh1": sh1_arr, "sl1": sl1_arr,
    }, index=df.index)


# ---------------------------------------------------------------------------
# 4. Swing Levels (for TP targets)
# ---------------------------------------------------------------------------

def compute_swing_levels(df: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """Track last two swing highs and lows over time."""
    df_piv = detect_pivots(df, lookback)
    n = len(df_piv)

    sw_h1 = np.full(n, np.nan)
    sw_h2 = np.full(n, np.nan)
    sw_l1 = np.full(n, np.nan)
    sw_l2 = np.full(n, np.nan)

    _sh1 = _sh2 = _sl1 = _sl2 = np.nan
    phs = df_piv["pivot_high"].values
    pls = df_piv["pivot_low"].values

    for i in range(n):
        if not np.isnan(phs[i]):
            _sh2 = _sh1
            _sh1 = phs[i]
        if not np.isnan(pls[i]):
            _sl2 = _sl1
            _sl1 = pls[i]
        sw_h1[i] = _sh1
        sw_h2[i] = _sh2
        sw_l1[i] = _sl1
        sw_l2[i] = _sl2

    return pd.DataFrame({
        "sw_h1": sw_h1, "sw_h2": sw_h2,
        "sw_l1": sw_l1, "sw_l2": sw_l2,
    }, index=df.index)


# ---------------------------------------------------------------------------
# 5. Wyckoff RSI Range Detection
# ---------------------------------------------------------------------------

def compute_rsi(closes: np.ndarray, length: int) -> np.ndarray:
    """Compute RSI."""
    n = len(closes)
    rsi = np.full(n, np.nan)
    if n < length + 1:
        return rsi

    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = np.mean(gains[:length])
    avg_loss = np.mean(losses[:length])

    if avg_loss == 0:
        rsi[length] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi[length] = 100.0 - (100.0 / (1.0 + rs))

    for i in range(length, len(deltas)):
        avg_gain = (avg_gain * (length - 1) + gains[i]) / length
        avg_loss = (avg_loss * (length - 1) + losses[i]) / length
        if avg_loss == 0:
            rsi[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i + 1] = 100.0 - (100.0 / (1.0 + rs))

    return rsi


def compute_wyckoff_ranges(df: pd.DataFrame, rsi_length: int = 14,
                           sensitivity: int = 20,
                           show_cont: bool = False) -> pd.DataFrame:
    """
    Wyckoff RSI range detection.
    Returns per-bar columns:
      in_range: bool — currently inside a sideways range
      range_ceiling: float — highest high of current/last range
      range_floor: float — lowest low of current/last range
      range_type: str — 'accumulation', 'distribution', or ''
      rsi: float — RSI value
      rsi_state: str — 'bull', 'bear', or 'side'
    """
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)

    rsi = compute_rsi(closes, rsi_length)

    upper = 50 + sensitivity
    lower = 50 - sensitivity

    # RSI state classification
    in_range = np.zeros(n, dtype=bool)
    range_ceiling = np.full(n, np.nan)
    range_floor = np.full(n, np.nan)
    range_type = np.full(n, "", dtype=object)
    rsi_state = np.full(n, "", dtype=object)

    _in_range = False
    _ceil = np.nan
    _floor = np.nan
    _range_start_trend = 0  # market structure trend at range start
    _last_type = ""

    # Simple trend tracker for range classification
    _sh1 = _sh2 = _sl1 = _sl2 = np.nan
    _structure_trend = 0

    # Pivot detection for structure (using lookback=5 matching Pine source)
    piv_lb = 5
    df_piv = detect_pivots(df, piv_lb)
    phs = df_piv["pivot_high"].values
    pls = df_piv["pivot_low"].values

    for i in range(n):
        # Update structure tracking
        if not np.isnan(phs[i]):
            _sh2 = _sh1
            _sh1 = phs[i]
        if not np.isnan(pls[i]):
            _sl2 = _sl1
            _sl1 = pls[i]

        if not np.isnan(_sh1) and not np.isnan(_sh2) and \
           not np.isnan(_sl1) and not np.isnan(_sl2):
            if _sh1 > _sh2 and _sl1 > _sl2:
                _structure_trend = 1
            elif _sh1 < _sh2 and _sl1 < _sl2:
                _structure_trend = -1

        # RSI state
        r = rsi[i]
        if np.isnan(r):
            rsi_state[i] = "side"
            in_range[i] = _in_range
            range_ceiling[i] = _ceil
            range_floor[i] = _floor
            range_type[i] = _last_type
            continue

        # side = RSI in neutral zone (or was in neutral zone on prev bar)
        prev_r = rsi[i - 1] if i > 0 and not np.isnan(rsi[i - 1]) else r
        is_side = (lower < r < upper) or (lower < prev_r < upper)
        is_bull = r > upper and prev_r > upper
        is_bear = r < lower and prev_r < lower

        if is_bull:
            rsi_state[i] = "bull"
        elif is_bear:
            rsi_state[i] = "bear"
        else:
            rsi_state[i] = "side"

        # Range transitions
        was_side = _in_range

        if is_side and not was_side:
            # Range starts
            _in_range = True
            _ceil = highs[i]
            _floor = lows[i]
            _range_start_trend = _structure_trend

        elif is_side and was_side:
            # Still in range — expand box
            _ceil = max(_ceil, highs[i]) if not np.isnan(_ceil) else highs[i]
            _floor = min(_floor, lows[i]) if not np.isnan(_floor) else lows[i]

        elif not is_side and was_side:
            # Range ends — classify
            if is_bull:
                _last_type = "accumulation"
                # Filter: only show reversal ranges (or all if show_cont)
                if not show_cont and _range_start_trend == 1:
                    _last_type = ""  # continuation, skip
            elif is_bear:
                _last_type = "distribution"
                if not show_cont and _range_start_trend == -1:
                    _last_type = ""
            _in_range = False

        in_range[i] = _in_range
        range_ceiling[i] = _ceil
        range_floor[i] = _floor
        range_type[i] = _last_type

    return pd.DataFrame({
        "in_range": in_range,
        "range_ceiling": range_ceiling,
        "range_floor": range_floor,
        "range_type": range_type,
        "rsi": rsi,
        "rsi_state": rsi_state,
    }, index=df.index)


# ---------------------------------------------------------------------------
# 6. Order Blocks
# ---------------------------------------------------------------------------

def compute_order_blocks(df: pd.DataFrame, bos_df: pd.DataFrame,
                         max_age: int = 500) -> pd.DataFrame:
    """
    Detect Order Blocks after each BOS.
    Bullish OB: candle with lowest low between swing low and BOS break bar.
    Bearish OB: candle with highest high between swing high and BOS break bar.

    Returns per-bar: ob_bull_top, ob_bull_bot, ob_bear_top, ob_bear_bot,
                     ob_bull_mitigated, ob_bear_mitigated
    """
    n = len(df)
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values

    ob_bull_top = np.full(n, np.nan)
    ob_bull_bot = np.full(n, np.nan)
    ob_bear_top = np.full(n, np.nan)
    ob_bear_bot = np.full(n, np.nan)
    ob_bull_mitigated = np.ones(n, dtype=bool)  # start as mitigated (no OB)
    ob_bear_mitigated = np.ones(n, dtype=bool)

    bos_bull = bos_df["bos_bull"].values
    bos_bear = bos_df["bos_bear"].values

    # Active OBs (list of dicts)
    active_bull_obs = []  # [{"top": float, "bot": float, "bar": int}]
    active_bear_obs = []

    for i in range(n):
        # Detect new bullish OB on bullish BOS
        if bos_bull[i]:
            # Find candle with lowest low between current bar and max_age bars back
            look_start = max(0, i - max_age)
            if look_start < i:
                segment_lows = lows[look_start:i]
                min_idx = look_start + np.argmin(segment_lows)
                ob_top = highs[min_idx]
                ob_bot = lows[min_idx]
                active_bull_obs.append({"top": ob_top, "bot": ob_bot, "bar": i})

        if bos_bear[i]:
            look_start = max(0, i - max_age)
            if look_start < i:
                segment_highs = highs[look_start:i]
                max_idx = look_start + np.argmax(segment_highs)
                ob_top = highs[max_idx]
                ob_bot = lows[max_idx]
                active_bear_obs.append({"top": ob_top, "bot": ob_bot, "bar": i})

        # Check mitigation of active OBs
        # Bullish OB mitigated when close < ob_bot
        active_bull_obs = [
            ob for ob in active_bull_obs
            if closes[i] >= ob["bot"]
        ]
        # Bearish OB mitigated when close > ob_top
        active_bear_obs = [
            ob for ob in active_bear_obs
            if closes[i] <= ob["top"]
        ]

        # Record nearest active OB
        if active_bull_obs:
            nearest = active_bull_obs[-1]  # most recent
            ob_bull_top[i] = nearest["top"]
            ob_bull_bot[i] = nearest["bot"]
            ob_bull_mitigated[i] = False
        if active_bear_obs:
            nearest = active_bear_obs[-1]
            ob_bear_top[i] = nearest["top"]
            ob_bear_bot[i] = nearest["bot"]
            ob_bear_mitigated[i] = False

    return pd.DataFrame({
        "ob_bull_top": ob_bull_top, "ob_bull_bot": ob_bull_bot,
        "ob_bear_top": ob_bear_top, "ob_bear_bot": ob_bear_bot,
        "ob_bull_mitigated": ob_bull_mitigated,
        "ob_bear_mitigated": ob_bear_mitigated,
    }, index=df.index)


# ---------------------------------------------------------------------------
# 7. Fair Value Gaps
# ---------------------------------------------------------------------------

def compute_fvg(df: pd.DataFrame, max_age: int = 500) -> pd.DataFrame:
    """
    Detect Fair Value Gaps (3-candle imbalances).
    Bullish FVG: candle[i-1].high < candle[i+1].low (gap up)
    Bearish FVG: candle[i-1].low > candle[i+1].high (gap down)

    Returns per-bar: fvg_bull_top, fvg_bull_bot, fvg_bear_top, fvg_bear_bot,
                     fvg_bull_mid, fvg_bear_mid (50% levels for TP)
    """
    n = len(df)
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    opens = df["open"].values

    fvg_bull_top = np.full(n, np.nan)
    fvg_bull_bot = np.full(n, np.nan)
    fvg_bear_top = np.full(n, np.nan)
    fvg_bear_bot = np.full(n, np.nan)
    fvg_bull_mid = np.full(n, np.nan)
    fvg_bear_mid = np.full(n, np.nan)

    active_bull_fvgs = []  # [{"top": float, "bot": float, "bar": int}]
    active_bear_fvgs = []

    for i in range(2, n):
        # Bullish FVG: gap between candle[i-2].high and candle[i].low
        # Middle candle (i-1) is bullish
        if lows[i] > highs[i - 2] and closes[i - 1] > opens[i - 1]:
            fvg_top = lows[i]
            fvg_bot = highs[i - 2]
            active_bull_fvgs.append({"top": fvg_top, "bot": fvg_bot, "bar": i})

        # Bearish FVG: gap between candle[i].high and candle[i-2].low
        if highs[i] < lows[i - 2] and closes[i - 1] < opens[i - 1]:
            fvg_top = lows[i - 2]
            fvg_bot = highs[i]
            active_bear_fvgs.append({"top": fvg_top, "bot": fvg_bot, "bar": i})

        # Mitigate: bullish FVG filled when low touches top
        active_bull_fvgs = [
            f for f in active_bull_fvgs
            if lows[i] <= f["top"] or i - f["bar"] < max_age
            # Keep if not yet filled AND not too old
        ]
        # Actually: mitigated when price fills the gap (low < fvg_bot)
        active_bull_fvgs = [
            f for f in active_bull_fvgs
            if not (lows[i] < f["bot"]) and (i - f["bar"] < max_age)
        ]

        active_bear_fvgs = [
            f for f in active_bear_fvgs
            if not (highs[i] > f["top"]) and (i - f["bar"] < max_age)
        ]

        # Record nearest unmitigated FVG
        if active_bull_fvgs:
            nearest = active_bull_fvgs[-1]
            fvg_bull_top[i] = nearest["top"]
            fvg_bull_bot[i] = nearest["bot"]
            fvg_bull_mid[i] = (nearest["top"] + nearest["bot"]) / 2

        if active_bear_fvgs:
            nearest = active_bear_fvgs[-1]
            fvg_bear_top[i] = nearest["top"]
            fvg_bear_bot[i] = nearest["bot"]
            fvg_bear_mid[i] = (nearest["top"] + nearest["bot"]) / 2

    return pd.DataFrame({
        "fvg_bull_top": fvg_bull_top, "fvg_bull_bot": fvg_bull_bot,
        "fvg_bear_top": fvg_bear_top, "fvg_bear_bot": fvg_bear_bot,
        "fvg_bull_mid": fvg_bull_mid, "fvg_bear_mid": fvg_bear_mid,
    }, index=df.index)


# ---------------------------------------------------------------------------
# 8. Equal Highs / Equal Lows
# ---------------------------------------------------------------------------

def compute_equal_hl(df: pd.DataFrame, lookback: int,
                     range_pct: float = 0.01) -> pd.DataFrame:
    """
    Detect equal highs/lows — swing levels clustered within range_pct of each other.
    Returns: eqh_level, eql_level, eqh_swept, eql_swept
    """
    df_piv = detect_pivots(df, lookback)
    n = len(df_piv)
    closes = df_piv["close"].values
    phs = df_piv["pivot_high"].values
    pls = df_piv["pivot_low"].values

    eqh_level = np.full(n, np.nan)
    eql_level = np.full(n, np.nan)
    eqh_swept = np.ones(n, dtype=bool)
    eql_swept = np.ones(n, dtype=bool)

    swing_highs = []  # list of (bar_idx, price)
    swing_lows = []

    active_eqh = []  # [{"level": float, "swept": bool}]
    active_eql = []

    for i in range(n):
        if not np.isnan(phs[i]):
            swing_highs.append((i, phs[i]))
            # Check for equal highs cluster
            recent = [p for (_, p) in swing_highs[-10:]]  # last 10 swings
            if len(recent) >= 2:
                # Group by proximity
                for j in range(len(recent) - 1):
                    for k in range(j + 1, len(recent)):
                        avg = (recent[j] + recent[k]) / 2
                        if avg > 0 and abs(recent[j] - recent[k]) / avg < range_pct:
                            active_eqh.append({"level": avg})
                            break

        if not np.isnan(pls[i]):
            swing_lows.append((i, pls[i]))
            recent = [p for (_, p) in swing_lows[-10:]]
            if len(recent) >= 2:
                for j in range(len(recent) - 1):
                    for k in range(j + 1, len(recent)):
                        avg = (recent[j] + recent[k]) / 2
                        if avg > 0 and abs(recent[j] - recent[k]) / avg < range_pct:
                            active_eql.append({"level": avg})
                            break

        # Sweep check: EQH swept when close > level, EQL swept when close < level
        active_eqh = [e for e in active_eqh if closes[i] <= e["level"]]
        active_eql = [e for e in active_eql if closes[i] >= e["level"]]

        if active_eqh:
            eqh_level[i] = active_eqh[-1]["level"]
            eqh_swept[i] = False
        if active_eql:
            eql_level[i] = active_eql[-1]["level"]
            eql_swept[i] = False

    return pd.DataFrame({
        "eqh_level": eqh_level, "eql_level": eql_level,
        "eqh_swept": eqh_swept, "eql_swept": eql_swept,
    }, index=df.index)


# ---------------------------------------------------------------------------
# 9. Helpers: forward-fill HTF to base index
# ---------------------------------------------------------------------------

def align_to_base(series_or_df, base_index: pd.DatetimeIndex):
    """Forward-fill a higher-timeframe series/df onto the base (M1) index."""
    return series_or_df.reindex(base_index, method="ffill")
