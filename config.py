"""Strategy configuration — all parameters from TRADING_LOGIC.md."""

from dataclasses import dataclass


@dataclass
class Config:
    # Symbol
    symbol: str = "EURUSD"
    point: float = 0.00001  # 5-digit broker

    # Timeframes (minutes)
    tf_d1: int = 1440
    tf_h4: int = 240
    tf_h1: int = 60
    tf_m30: int = 30
    tf_m5: int = 5
    tf_m1: int = 1

    # Structure detection
    swing_lookback: int = 10       # HTF pivot lookback
    m1_swing_lookback: int = 3     # M1 trigger pivot lookback
    use_close_break: bool = True   # BOS requires candle close beyond level

    # Wyckoff RSI range detection
    rsi_length: int = 14
    rsi_sensitivity: int = 20      # RSI neutral zone: 50 +/- this

    # Mid-TF alignment
    min_mid_tf_agree: int = 2      # Min mid-TFs agreeing with D1 (out of 3)

    # Stop loss
    sl_buffer_points: int = 3      # Points beyond SL level
    min_sl_pips: float = 3.0       # Minimum SL distance in pips
    min_rr: float = 2.0            # Minimum reward-to-risk

    # Risk
    risk_per_trade: float = 500.0
    initial_capital: float = 10000.0

    # Transaction costs
    # A raw/ECN ("zero spread") account charges a near-zero spread plus an
    # explicit per-lot commission; a standard account charges $0 commission
    # and buries the same cost in a wider spread. Model both so the two
    # account types can be compared on total cost, not on the label.
    contract_size: int = 100_000     # Units per standard lot
    commission_per_lot: float = 7.0  # Round turn, per standard lot
    spread_pips: float = 0.2         # Half-spread is paid on entry fill
    slippage_points: int = 2         # Adverse points on entry fill

    # Entry / cooldown
    max_entry_attempts: int = 2    # Entries before range cooldown
    tp_max_targets: int = 3

    # POI detection
    eql_range_percent: float = 0.01  # Range % for equal level grouping
    ob_max_age_bars: int = 500       # Max bars to look back for OBs
    fvg_max_age_bars: int = 500

    # Ranges
    show_cont_ranges: bool = False   # Show continuation ranges (vs reversal only)

    # Trade date filter
    trade_start: str = ""
    trade_end: str = ""

    # MT5 data
    mt5_bars: int = 100000           # Max bars to fetch per timeframe

    @property
    def pip(self) -> float:
        """Price move of one pip (10 points on a 5-digit feed)."""
        return self.point * 10

    @property
    def entry_cost_price(self) -> float:
        """Adverse price offset applied to every entry fill."""
        return self.spread_pips * self.pip + self.slippage_points * self.point

    @property
    def sl_buffer(self) -> float:
        return self.sl_buffer_points * self.point

    @property
    def htf_list(self) -> list[int]:
        """All higher timeframes for bias calculation."""
        return [self.tf_d1, self.tf_h4, self.tf_h1, self.tf_m30]

    @property
    def mid_tfs(self) -> list[int]:
        """Mid timeframes for alignment check."""
        return [self.tf_h4, self.tf_h1, self.tf_m30]
