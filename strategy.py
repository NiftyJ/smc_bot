"""
Full SMC Multi-Timeframe Strategy — TRADING_LOGIC.md implementation.

Flow:
  D1 Bias -> Mid-TF Alignment -> HTF Range Check (Wyckoff + Double BOS)
  -> M5 Confirmation -> Entry Mode (Momentum M1 BOS / Ranging M1 OB Retouch)
  -> POI-based TPs (OBs + FVGs + EQH/EQL + Swing Levels)
"""

import numpy as np
import pandas as pd
from config import Config
from indicators import (
    compute_bias, compute_bos, compute_swing_levels,
    compute_wyckoff_ranges, compute_order_blocks, compute_fvg,
    compute_equal_hl, compute_rsi, align_to_base,
)


class SMCStrategy:
    """Runs the full strategy logic bar-by-bar on pre-computed indicator data."""

    def __init__(self, cfg: Config):
        self.cfg = cfg

    # ------------------------------------------------------------------
    # Pre-compute all indicators
    # ------------------------------------------------------------------
    def precompute(self, data: dict[int, pd.DataFrame]) -> dict:
        cfg = self.cfg
        ind = {}

        # Bias on all HTFs
        for tf in cfg.htf_list:
            ind[f"bias_{tf}"] = compute_bias(data[tf], cfg.swing_lookback, cfg.use_close_break)

        # Wyckoff ranges on HTFs (D1, H4, H1) for range gating
        for tf in [cfg.tf_d1, cfg.tf_h4, cfg.tf_h1]:
            ind[f"wrange_{tf}"] = compute_wyckoff_ranges(
                data[tf], cfg.rsi_length, cfg.rsi_sensitivity, cfg.show_cont_ranges
            )

        # M5: bias, BOS, Wyckoff range, RSI
        ind["m5_bias"] = compute_bias(data[cfg.tf_m5], cfg.swing_lookback, cfg.use_close_break)
        ind["m5_bos"] = compute_bos(data[cfg.tf_m5], cfg.swing_lookback, cfg.use_close_break)
        ind["m5_wrange"] = compute_wyckoff_ranges(
            data[cfg.tf_m5], cfg.rsi_length, cfg.rsi_sensitivity, cfg.show_cont_ranges
        )

        # M1: bias, BOS
        m1_lb = min(cfg.swing_lookback, 5)
        ind["m1_bias"] = compute_bias(data[cfg.tf_m1], m1_lb, cfg.use_close_break)
        ind["m1_bos"] = compute_bos(data[cfg.tf_m1], cfg.m1_swing_lookback, cfg.use_close_break)

        # POIs on D1 and H4: Order Blocks, FVGs, EQH/EQL, Swing Levels
        for tf in [cfg.tf_d1, cfg.tf_h4]:
            bos = compute_bos(data[tf], cfg.swing_lookback, cfg.use_close_break)
            ind[f"ob_{tf}"] = compute_order_blocks(data[tf], bos, cfg.ob_max_age_bars)
            ind[f"fvg_{tf}"] = compute_fvg(data[tf], cfg.fvg_max_age_bars)
            ind[f"eqhl_{tf}"] = compute_equal_hl(data[tf], cfg.swing_lookback, cfg.eql_range_percent)
            ind[f"swings_{tf}"] = compute_swing_levels(data[tf], cfg.swing_lookback)

        # M5 POIs for nearer TP targets
        ind[f"ob_{cfg.tf_m5}"] = compute_order_blocks(data[cfg.tf_m5], ind["m5_bos"], cfg.ob_max_age_bars)
        ind[f"fvg_{cfg.tf_m5}"] = compute_fvg(data[cfg.tf_m5], cfg.fvg_max_age_bars)
        ind[f"swings_{cfg.tf_m5}"] = compute_swing_levels(data[cfg.tf_m5], cfg.swing_lookback)

        # H1 POIs
        h1_bos = compute_bos(data[cfg.tf_h1], cfg.swing_lookback, cfg.use_close_break)
        ind[f"ob_{cfg.tf_h1}"] = compute_order_blocks(data[cfg.tf_h1], h1_bos, cfg.ob_max_age_bars)
        ind[f"fvg_{cfg.tf_h1}"] = compute_fvg(data[cfg.tf_h1], cfg.fvg_max_age_bars)
        ind[f"swings_{cfg.tf_h1}"] = compute_swing_levels(data[cfg.tf_h1], cfg.swing_lookback)

        # M1 OBs for ranging entry mode
        ind["m1_ob"] = compute_order_blocks(
            data[cfg.tf_m1],
            ind["m1_bos"],
            max_age=200,
        )

        print(f"  Indicators computed for {len(ind)} items")
        return ind

    # ------------------------------------------------------------------
    # Collect TP candidates from POIs
    # ------------------------------------------------------------------
    def _collect_tp(self, direction: int, price: float, poi_row: dict,
                    max_targets: int) -> list[float]:
        """Collect TP levels from OBs, FVGs, EQH/EQL, and swing levels.
        Searches M5, H1, H4, D1 — nearest first."""
        candidates = []
        poi_tfs = [self.cfg.tf_m5, self.cfg.tf_h1, self.cfg.tf_h4, self.cfg.tf_d1]

        if direction == 1:  # Long — collect levels above price
            for tf in poi_tfs:
                v = poi_row.get(f"ob_{tf}_ob_bear_bot")
                if v is not None and not np.isnan(v) and v > price:
                    candidates.append(v)
                v = poi_row.get(f"fvg_{tf}_fvg_bear_mid")
                if v is not None and not np.isnan(v) and v > price:
                    candidates.append(v)
                for col in ["sw_h1", "sw_h2"]:
                    v = poi_row.get(f"swings_{tf}_{col}")
                    if v is not None and not np.isnan(v) and v > price:
                        candidates.append(v)
            # EQH only on H4/D1
            for tf in [self.cfg.tf_h4, self.cfg.tf_d1]:
                v = poi_row.get(f"eqhl_{tf}_eqh_level")
                if v is not None and not np.isnan(v) and v > price:
                    candidates.append(v)

        else:  # Short — collect levels below price
            for tf in poi_tfs:
                v = poi_row.get(f"ob_{tf}_ob_bull_top")
                if v is not None and not np.isnan(v) and v < price:
                    candidates.append(v)
                v = poi_row.get(f"fvg_{tf}_fvg_bull_mid")
                if v is not None and not np.isnan(v) and v < price:
                    candidates.append(v)
                for col in ["sw_l1", "sw_l2"]:
                    v = poi_row.get(f"swings_{tf}_{col}")
                    if v is not None and not np.isnan(v) and v < price:
                        candidates.append(v)
            for tf in [self.cfg.tf_h4, self.cfg.tf_d1]:
                v = poi_row.get(f"eqhl_{tf}_eql_level")
                if v is not None and not np.isnan(v) and v < price:
                    candidates.append(v)

        # Sort by distance, deduplicate (merge levels within 20 points)
        candidates.sort(key=lambda x: abs(x - price))
        deduped = []
        for c in candidates:
            if not deduped or abs(c - deduped[-1]) > 20 * self.cfg.point:
                deduped.append(c)
            if len(deduped) >= max_targets:
                break
        return deduped

    # ------------------------------------------------------------------
    # Compute SL
    # ------------------------------------------------------------------
    def _compute_sl(self, direction: int, price: float,
                    m1_sh1: float, m1_sl1: float,
                    m5_bos_break_high: float, m5_bos_break_low: float,
                    ob_top: float = np.nan, ob_bot: float = np.nan,
                    is_ob_entry: bool = False) -> float:
        """Compute stop loss price. Enforces minimum SL distance."""
        buf = self.cfg.sl_buffer
        min_sl_dist = self.cfg.min_sl_pips * self.cfg.point * 10  # pips to price

        sl = np.nan

        if is_ob_entry:
            if direction == 1 and not np.isnan(ob_bot):
                sl = ob_bot - buf
            elif direction == -1 and not np.isnan(ob_top):
                sl = ob_top + buf

        if np.isnan(sl):
            if direction == 1:
                if not np.isnan(m1_sl1) and m1_sl1 < price:
                    sl = m1_sl1 - buf
                elif not np.isnan(m5_bos_break_low) and m5_bos_break_low < price:
                    sl = m5_bos_break_low - buf
            else:
                if not np.isnan(m1_sh1) and m1_sh1 > price:
                    sl = m1_sh1 + buf
                elif not np.isnan(m5_bos_break_high) and m5_bos_break_high > price:
                    sl = m5_bos_break_high + buf

        # Enforce minimum SL distance
        if not np.isnan(sl):
            if direction == 1 and (price - sl) < min_sl_dist:
                sl = price - min_sl_dist
            elif direction == -1 and (sl - price) < min_sl_dist:
                sl = price + min_sl_dist

        return sl

    # ------------------------------------------------------------------
    # Run strategy
    # ------------------------------------------------------------------
    def run(self, data: dict[int, pd.DataFrame], ind: dict) -> pd.DataFrame:
        cfg = self.cfg
        m1 = data[cfg.tf_m1]
        base_idx = m1.index

        # ---- Align all HTF indicators to M1 ----
        # Biases
        bias_d = align_to_base(ind[f"bias_{cfg.tf_d1}"], base_idx).values.astype(int)
        bias_h4 = align_to_base(ind[f"bias_{cfg.tf_h4}"], base_idx).values.astype(int)
        bias_h1 = align_to_base(ind[f"bias_{cfg.tf_h1}"], base_idx).values.astype(int)
        bias_m30 = align_to_base(ind[f"bias_{cfg.tf_m30}"], base_idx).values.astype(int)

        # HTF Wyckoff ranges (D1, H4, H1) — for range gating
        htf_in_range = {}
        htf_range_ceil = {}
        htf_range_floor = {}
        for tf in [cfg.tf_d1, cfg.tf_h4, cfg.tf_h1]:
            wr = ind[f"wrange_{tf}"]
            htf_in_range[tf] = align_to_base(wr["in_range"], base_idx).fillna(False).values
            htf_range_ceil[tf] = align_to_base(wr["range_ceiling"], base_idx).values
            htf_range_floor[tf] = align_to_base(wr["range_floor"], base_idx).values

        # M5 BOS
        m5_bos_aligned = align_to_base(ind["m5_bos"], base_idx)
        m5_bos_dir = m5_bos_aligned["bos_dir"].fillna(0).values.astype(int)
        m5_bos_cnt = m5_bos_aligned["bos_count"].fillna(0).values.astype(int)
        m5_bbh = m5_bos_aligned["bos_break_high"].values
        m5_bbl = m5_bos_aligned["bos_break_low"].values

        # M5 BOS edge detection
        m5_bos_bull_raw = ind["m5_bos"]["bos_bull"]
        m5_bos_bear_raw = ind["m5_bos"]["bos_bear"]
        m5_bull_on_m1 = m5_bos_bull_raw.reindex(base_idx, method="ffill").fillna(False)
        m5_bear_on_m1 = m5_bos_bear_raw.reindex(base_idx, method="ffill").fillna(False)
        m5_bull_edge = (m5_bull_on_m1 & ~m5_bull_on_m1.shift(1, fill_value=False)).values
        m5_bear_edge = (m5_bear_on_m1 & ~m5_bear_on_m1.shift(1, fill_value=False)).values

        # M5 Wyckoff range (for entry mode selection)
        m5_wr = ind["m5_wrange"]
        m5_in_range = align_to_base(m5_wr["in_range"], base_idx).fillna(False).values
        m5_rsi_state = align_to_base(m5_wr["rsi_state"], base_idx).fillna("side").values
        m5_range_ceil = align_to_base(m5_wr["range_ceiling"], base_idx).values
        m5_range_floor = align_to_base(m5_wr["range_floor"], base_idx).values

        # M1 BOS
        m1_bos = ind["m1_bos"]
        m1_bull_bos = m1_bos["bos_bull"].values
        m1_bear_bos = m1_bos["bos_bear"].values
        m1_sh1 = m1_bos["sh1"].values
        m1_sl1 = m1_bos["sl1"].values

        # M1 OBs (for ranging entry)
        m1_ob = ind["m1_ob"]
        m1_ob_bull_top = m1_ob["ob_bull_top"].values
        m1_ob_bull_bot = m1_ob["ob_bull_bot"].values
        m1_ob_bear_top = m1_ob["ob_bear_top"].values
        m1_ob_bear_bot = m1_ob["ob_bear_bot"].values
        m1_ob_bull_mit = m1_ob["ob_bull_mitigated"].values
        m1_ob_bear_mit = m1_ob["ob_bear_mitigated"].values

        # POIs aligned to M1 (for TP collection)
        poi_arrays = {}
        for tf in [cfg.tf_d1, cfg.tf_h4, cfg.tf_h1, cfg.tf_m5]:
            for prefix in ["ob", "fvg", "swings"]:
                key_name = f"{prefix}_{tf}"
                if key_name not in ind:
                    continue
                df_poi = ind[key_name]
                aligned = align_to_base(df_poi, base_idx)
                for col in aligned.columns:
                    key = f"{prefix}_{tf}_{col}"
                    poi_arrays[key] = aligned[col].values
        # EQH/EQL only on D1/H4
        for tf in [cfg.tf_d1, cfg.tf_h4]:
            key_name = f"eqhl_{tf}"
            if key_name in ind:
                df_poi = ind[key_name]
                aligned = align_to_base(df_poi, base_idx)
                for col in aligned.columns:
                    poi_arrays[f"eqhl_{tf}_{col}"] = aligned[col].values

        # M5 close aligned for range tracking
        m5_close = data[cfg.tf_m5]["close"].reindex(base_idx, method="ffill").values

        # ---- Bar-by-bar simulation ----
        n = len(m1)
        closes = m1["close"].values
        highs = m1["high"].values
        lows = m1["low"].values

        trades = []
        position = None
        entry_attempts = 0
        range_cooldown = False
        range_ceiling = np.nan
        range_floor = np.nan
        prev_bias_d = 0

        # Double BOS tracking for HTF range breakout
        htf_breakout_confirmed = {tf: False for tf in [cfg.tf_d1, cfg.tf_h4, cfg.tf_h1]}
        htf_bos_after_range = {tf: 0 for tf in [cfg.tf_d1, cfg.tf_h4, cfg.tf_h1]}
        htf_range_max = {tf: np.nan for tf in [cfg.tf_d1, cfg.tf_h4, cfg.tf_h1]}
        htf_range_min = {tf: np.nan for tf in [cfg.tf_d1, cfg.tf_h4, cfg.tf_h1]}

        # M5 double BOS tracking
        m5_double_bos_confirmed = False
        m5_bos_count_since_range = 0
        m5_range_max = np.nan
        m5_range_min = np.nan
        prev_m5_in_range = False

        trade_start = pd.Timestamp(cfg.trade_start) if cfg.trade_start else None
        trade_end = pd.Timestamp(cfg.trade_end) if cfg.trade_end else None

        def _trade(pos, exit_time, exit_price, pnl, exit_reason):
            d = "LONG" if pos["direction"] == 1 else "SHORT"
            return {
                "entry_time": pos["entry_time"],
                "exit_time": exit_time,
                "direction": d,
                "entry_price": pos["entry_price"],
                "exit_price": exit_price,
                "sl": pos["sl"],
                "tp": pos["tp"],
                "qty": pos["qty"],
                "lots": pos["qty"] / cfg.contract_size,
                "sl_pips": abs(pos["entry_price"] - pos["sl"]) / cfg.pip,
                "pnl": pnl,
                "exit_reason": exit_reason,
                "bias_d": pos.get("bias_d", 0),
                "bias_h4": pos.get("bias_h4", 0),
                "bias_h1": pos.get("bias_h1", 0),
                "bias_m30": pos.get("bias_m30", 0),
                "mid_agree": pos.get("mid_agree", 0),
                "m5_bos_dir": pos.get("m5_bos_dir", 0),
                "m5_bos_cnt": pos.get("m5_bos_cnt", 0),
                "trigger": pos.get("trigger", ""),
                "entry_mode": pos.get("entry_mode", ""),
                "rr": pos.get("rr", 0),
            }

        for i in range(1, n):
            bar_time = base_idx[i]
            c = closes[i]
            h = highs[i]
            lo = lows[i]

            bd = bias_d[i]
            bh4 = bias_h4[i]
            bh1 = bias_h1[i]
            bm30 = bias_m30[i]

            # ---- Mid-TF alignment ----
            mid_agree = (
                (1 if bh4 == bd and bd != 0 else 0) +
                (1 if bh1 == bd and bd != 0 else 0) +
                (1 if bm30 == bd and bd != 0 else 0)
            )
            bias_confirmed = bd != 0 and mid_agree >= cfg.min_mid_tf_agree

            # ---- HTF Range Gating ----
            # NOTE: Wyckoff RSI range detection on H4/H1 classifies 93-97%
            # of bars as "in range" for forex, making it unsuitable as a
            # hard trade blocker.  Instead, gating uses the structural
            # bias system: if D1 bias = 0 (no clear HH/HL or LH/LL),
            # the market is ranging and we skip.  The Wyckoff RSI state
            # is still used on M5 to select entry mode (momentum vs OB).
            any_htf_blocking = (bd == 0)

            # ---- M5 Range and Double BOS ----
            cur_m5_in_range = m5_in_range[i]

            if cur_m5_in_range and not prev_m5_in_range:
                # Entered M5 range
                m5_double_bos_confirmed = False
                m5_bos_count_since_range = 0
                m5_range_max = m5_range_ceil[i] if not np.isnan(m5_range_ceil[i]) else c
                m5_range_min = m5_range_floor[i] if not np.isnan(m5_range_floor[i]) else c

            if cur_m5_in_range:
                # Update range bounds
                if not np.isnan(m5_range_ceil[i]):
                    m5_range_max = max(m5_range_max, m5_range_ceil[i]) if not np.isnan(m5_range_max) else m5_range_ceil[i]
                if not np.isnan(m5_range_floor[i]):
                    m5_range_min = min(m5_range_min, m5_range_floor[i]) if not np.isnan(m5_range_min) else m5_range_floor[i]
                m5_double_bos_confirmed = False
                m5_bos_count_since_range = 0

            elif not m5_double_bos_confirmed and not np.isnan(m5_range_max):
                # After M5 range — track double BOS
                if bd == 1 and c > m5_range_max:
                    m5_bos_count_since_range += 1
                    m5_range_max = c
                elif bd == -1 and c < m5_range_min:
                    m5_bos_count_since_range += 1
                    m5_range_min = c

                if m5_bos_count_since_range >= 2:
                    m5_double_bos_confirmed = True

            prev_m5_in_range = cur_m5_in_range

            # ---- M5 structure confirmation ----
            m5_dir_i = m5_bos_dir[i]
            m5_cnt_i = m5_bos_cnt[i]
            m5_confirmed = (
                bias_confirmed
                and m5_dir_i == bd
                and m5_cnt_i >= 1
                and not any_htf_blocking
            )

            # ---- Entry mode: momentum vs ranging ----
            # Trending if M5 has 2+ BOS in same direction OR RSI is trending
            m5_is_trending = m5_cnt_i >= 2 or m5_rsi_state[i] in ("bull", "bear")

            # ---- Range cooldown tracking ----
            if m5_confirmed:
                rng_ceil = m5_range_ceil[i]
                rng_flr = m5_range_floor[i]
                if bd == 1 and not np.isnan(rng_ceil):
                    range_ceiling = rng_ceil if np.isnan(range_ceiling) else max(range_ceiling, rng_ceil)
                if bd == -1 and not np.isnan(rng_flr):
                    range_floor = rng_flr if np.isnan(range_floor) else min(range_floor, rng_flr)

            if range_cooldown:
                if bd == 1 and not np.isnan(range_ceiling) and m5_close[i] > range_ceiling:
                    range_cooldown = False
                    entry_attempts = 0
                    range_ceiling = np.nan
                if bd == -1 and not np.isnan(range_floor) and m5_close[i] < range_floor:
                    range_cooldown = False
                    entry_attempts = 0
                    range_floor = np.nan

            # ---- Daily bias change -> full reset ----
            if bd != prev_bias_d or bd == 0:
                entry_attempts = 0
                range_cooldown = False
                range_ceiling = np.nan
                range_floor = np.nan
                # Also reset HTF breakout tracking on D1 bias change
                for tf in htf_breakout_confirmed:
                    htf_breakout_confirmed[tf] = True  # allow trading
                    htf_bos_after_range[tf] = 0
                m5_double_bos_confirmed = True
            prev_bias_d = bd

            # ---- Check position TP/SL ----
            if position is not None:
                hit = False
                if position["direction"] == 1:
                    if lo <= position["sl"]:
                        pnl = (position["sl"] - position["entry_price"]) * position["qty"]
                        trades.append(_trade(position, bar_time, position["sl"], pnl, "SL"))
                        position = None
                        hit = True
                    elif h >= position["tp"]:
                        pnl = (position["tp"] - position["entry_price"]) * position["qty"]
                        trades.append(_trade(position, bar_time, position["tp"], pnl, "TP"))
                        position = None
                        hit = True
                else:
                    if h >= position["sl"]:
                        pnl = (position["entry_price"] - position["sl"]) * position["qty"]
                        trades.append(_trade(position, bar_time, position["sl"], pnl, "SL"))
                        position = None
                        hit = True
                    elif lo <= position["tp"]:
                        pnl = (position["entry_price"] - position["tp"]) * position["qty"]
                        trades.append(_trade(position, bar_time, position["tp"], pnl, "TP"))
                        position = None
                        hit = True

                if not hit:
                    # M5 BOS flip invalidation
                    if position["direction"] == 1 and m5_bear_edge[i]:
                        pnl = (c - position["entry_price"]) * position["qty"]
                        trades.append(_trade(position, bar_time, c, pnl, "M5_BOS_FLIP"))
                        position = None
                    elif position["direction"] == -1 and m5_bull_edge[i]:
                        pnl = (position["entry_price"] - c) * position["qty"]
                        trades.append(_trade(position, bar_time, c, pnl, "M5_BOS_FLIP"))
                        position = None

            # ---- Entry logic (only if flat) ----
            if position is not None:
                continue

            if trade_start and bar_time < trade_start:
                continue
            if trade_end and bar_time > trade_end:
                continue

            if range_cooldown or not m5_confirmed:
                continue

            # Build POI row for TP collection
            poi_row = {}
            for key, arr in poi_arrays.items():
                poi_row[key] = arr[i]

            # ======== MODE A: Momentum Entry (M1 BOS) ========
            if m5_is_trending:
                # Direct M5 BOS entry
                m5_long = bool(m5_bull_edge[i]) and bd == 1
                m5_short = bool(m5_bear_edge[i]) and bd == -1

                # M1 BOS refinement
                m1_long = bool(m1_bull_bos[i]) and bd == 1
                m1_short = bool(m1_bear_bos[i]) and bd == -1

                long_trigger = m5_long or m1_long
                short_trigger = m5_short or m1_short

                if long_trigger or short_trigger:
                    direction = 1 if long_trigger else -1
                    trigger_type = "M5_BOS" if (
                        (direction == 1 and m5_long) or (direction == -1 and m5_short)
                    ) else "M1_BOS"

                    sl = self._compute_sl(
                        direction, c,
                        m1_sh1[i], m1_sl1[i],
                        m5_bbh[i], m5_bbl[i],
                    )
                    tp_levels = self._collect_tp(direction, c, poi_row, cfg.tp_max_targets)
                    tp1 = tp_levels[0] if tp_levels else np.nan

                    if not np.isnan(sl) and not np.isnan(tp1):
                        fill = c + direction * cfg.entry_cost_price
                        sl_dist = abs(fill - sl)
                        tp_dist = abs(tp1 - fill)
                        rr = tp_dist / sl_dist if sl_dist > 0 else 0.0

                        if rr >= cfg.min_rr and sl_dist > 0:
                            qty = cfg.risk_per_trade / sl_dist
                            entry_attempts += 1
                            position = {
                                "direction": direction,
                                "entry_price": fill,
                                "sl": sl, "tp": tp1, "qty": qty,
                                "entry_time": bar_time,
                                "bias_d": bd, "bias_h4": bh4,
                                "bias_h1": bh1, "bias_m30": bm30,
                                "mid_agree": mid_agree,
                                "m5_bos_dir": m5_dir_i, "m5_bos_cnt": m5_cnt_i,
                                "trigger": trigger_type,
                                "entry_mode": "MOMENTUM",
                                "rr": round(rr, 2),
                            }
                            if entry_attempts >= cfg.max_entry_attempts:
                                range_cooldown = True

            # ======== MODE B: Ranging Entry (M1 OB Retouch) ========
            else:
                # M5 was ranging or just broke out — look for OB retouch on M1
                if bd == 1 and not m1_ob_bull_mit[i]:
                    ob_top = m1_ob_bull_top[i]
                    ob_bot = m1_ob_bull_bot[i]
                    # Price touching OB zone (aggressive entry)
                    if not np.isnan(ob_top) and not np.isnan(ob_bot) and lo <= ob_top:
                        entry_price = ob_top  # enter at OB top (limit fill)
                        sl = self._compute_sl(
                            1, entry_price,
                            m1_sh1[i], m1_sl1[i],
                            m5_bbh[i], m5_bbl[i],
                            ob_top, ob_bot, is_ob_entry=True,
                        )
                        tp_levels = self._collect_tp(1, entry_price, poi_row, cfg.tp_max_targets)
                        tp1 = tp_levels[0] if tp_levels else np.nan

                        if not np.isnan(sl) and not np.isnan(tp1):
                            fill = entry_price + (1) * cfg.entry_cost_price
                            sl_dist = abs(fill - sl)
                            tp_dist = abs(tp1 - fill)
                            rr = tp_dist / sl_dist if sl_dist > 0 else 0.0

                            if rr >= cfg.min_rr and sl_dist > 0:
                                qty = cfg.risk_per_trade / sl_dist
                                entry_attempts += 1
                                position = {
                                    "direction": 1,
                                    "entry_price": fill,
                                    "sl": sl, "tp": tp1, "qty": qty,
                                    "entry_time": bar_time,
                                    "bias_d": bd, "bias_h4": bh4,
                                    "bias_h1": bh1, "bias_m30": bm30,
                                    "mid_agree": mid_agree,
                                    "m5_bos_dir": m5_dir_i, "m5_bos_cnt": m5_cnt_i,
                                    "trigger": "M1_OB",
                                    "entry_mode": "RANGING",
                                    "rr": round(rr, 2),
                                }
                                if entry_attempts >= cfg.max_entry_attempts:
                                    range_cooldown = True

                elif bd == -1 and not m1_ob_bear_mit[i]:
                    ob_top = m1_ob_bear_top[i]
                    ob_bot = m1_ob_bear_bot[i]
                    if not np.isnan(ob_top) and not np.isnan(ob_bot) and h >= ob_bot:
                        entry_price = ob_bot
                        sl = self._compute_sl(
                            -1, entry_price,
                            m1_sh1[i], m1_sl1[i],
                            m5_bbh[i], m5_bbl[i],
                            ob_top, ob_bot, is_ob_entry=True,
                        )
                        tp_levels = self._collect_tp(-1, entry_price, poi_row, cfg.tp_max_targets)
                        tp1 = tp_levels[0] if tp_levels else np.nan

                        if not np.isnan(sl) and not np.isnan(tp1):
                            fill = entry_price + (-1) * cfg.entry_cost_price
                            sl_dist = abs(fill - sl)
                            tp_dist = abs(tp1 - fill)
                            rr = tp_dist / sl_dist if sl_dist > 0 else 0.0

                            if rr >= cfg.min_rr and sl_dist > 0:
                                qty = cfg.risk_per_trade / sl_dist
                                entry_attempts += 1
                                position = {
                                    "direction": -1,
                                    "entry_price": fill,
                                    "sl": sl, "tp": tp1, "qty": qty,
                                    "entry_time": bar_time,
                                    "bias_d": bd, "bias_h4": bh4,
                                    "bias_h1": bh1, "bias_m30": bm30,
                                    "mid_agree": mid_agree,
                                    "m5_bos_dir": m5_dir_i, "m5_bos_cnt": m5_cnt_i,
                                    "trigger": "M1_OB",
                                    "entry_mode": "RANGING",
                                    "rr": round(rr, 2),
                                }
                                if entry_attempts >= cfg.max_entry_attempts:
                                    range_cooldown = True

        # Close any open position at end
        if position is not None:
            c = closes[-1]
            if position["direction"] == 1:
                pnl = (c - position["entry_price"]) * position["qty"]
            else:
                pnl = (position["entry_price"] - c) * position["qty"]
            trades.append(_trade(position, base_idx[-1], c, pnl, "END_OF_DATA"))

        return pd.DataFrame(trades)
