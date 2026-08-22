"""Strategy configuration — all parameters from TRADING_LOGIC.md."""

from dataclasses import dataclass

from instruments import Instrument, resolve


@dataclass
class Config:
    # Symbol / instrument
    symbol: str = "MES"
    instrument: Instrument | None = None   # auto-resolved from `symbol` if None

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

    # Stop loss (all distances in TICKS of the instrument)
    sl_buffer_ticks: int = 0       # 0 = use the instrument default
    min_sl_ticks: int = 0          # 0 = use the instrument default
    min_rr: float = 2.0            # Minimum reward-to-risk

    # Risk
    risk_per_trade: float = 250.0
    initial_capital: float = 10000.0
    allow_min_qty: bool = False    # Take 1 contract even if it over-risks
    apply_slippage: bool = True    # Charge assumed slippage on entry + exit
    commission_override: float = -1.0  # Round-turn $/contract; <0 = instrument default

    # Session filter (futures trade nearly 24h; overnight liquidity is thin)
    rth_only: bool = False         # Restrict entries to Regular Trading Hours
    data_tz: str = "UTC"           # Timezone of the bar timestamps in the feed

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

    def __post_init__(self):
        """Resolve the instrument spec from the symbol unless one was supplied."""
        if self.instrument is None:
            self.instrument = resolve(self.symbol)

    # ---- instrument-derived helpers -------------------------------

    @property
    def point(self) -> float:
        """Minimum price increment (tick size) of the instrument."""
        return self.instrument.tick_size

    @property
    def digits(self) -> int:
        return self.instrument.digits

    @property
    def sl_buffer(self) -> float:
        """SL buffer in price units."""
        ticks = self.sl_buffer_ticks or self.instrument.sl_buffer_ticks
        return ticks * self.instrument.tick_size

    @property
    def min_sl_dist(self) -> float:
        """Minimum stop distance in price units."""
        ticks = self.min_sl_ticks or self.instrument.min_sl_ticks
        return ticks * self.instrument.tick_size

    @property
    def tp_dedupe_dist(self) -> float:
        """Merge TP candidates closer together than this (price units)."""
        return self.instrument.tp_dedupe_ticks * self.instrument.tick_size

    @property
    def commission_per_contract(self) -> float:
        """Round-turn commission per contract, in account currency."""
        if self.commission_override >= 0:
            return self.commission_override
        return self.instrument.commission_per_contract

    @property
    def is_futures(self) -> bool:
        return self.instrument.kind == "futures"

    def size_position(self, sl_distance: float) -> float:
        return self.instrument.size_position(
            self.risk_per_trade, sl_distance, self.allow_min_qty
        )

    def pnl(self, direction: int, entry: float, exit_price: float, qty: float) -> float:
        return self.instrument.pnl(direction, entry, exit_price, qty)

    @property
    def htf_list(self) -> list[int]:
        """All higher timeframes for bias calculation."""
        return [self.tf_d1, self.tf_h4, self.tf_h1, self.tf_m30]

    @property
    def mid_tfs(self) -> list[int]:
        """Mid timeframes for alignment check."""
        return [self.tf_h4, self.tf_h1, self.tf_m30]
