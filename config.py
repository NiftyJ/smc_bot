"""Strategy configuration — all parameters from TRADING_LOGIC.md."""

from dataclasses import dataclass, replace

from costs import CostModel, get_model
from instruments import Instrument, get_instrument


@dataclass
class Config:
    # Symbol. Tick size, contract value, minimum stop and costs are taken from
    # the instrument spec in instruments.py — see the properties below.
    symbol: str = "EURUSD"
    point: float | None = None  # override instrument tick size (rarely needed)

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

    # Stop loss. None means "use the instrument default"; set a number to
    # override in ticks. min_rr applies to every instrument.
    sl_buffer_ticks: float | None = None   # Ticks beyond the SL level
    min_sl_ticks: float | None = None      # Minimum SL distance in ticks
    min_rr: float = 2.0                    # Minimum reward-to-risk

    # Risk
    risk_per_trade: float = 500.0
    initial_capital: float = 10000.0

    # Trading costs. By default they come from the instrument spec; set venue
    # to a costs.PRESETS name to force a different fee structure.
    venue: str | None = None

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
    def instrument(self) -> Instrument:
        """Spec for the configured symbol."""
        return get_instrument(self.symbol)

    @property
    def tick_size(self) -> float:
        """Smallest price increment, overridable via ``point``."""
        return self.point if self.point is not None else self.instrument.tick_size

    @property
    def cost_model(self) -> CostModel:
        """Costs for this instrument, or for an explicitly forced venue."""
        if self.venue is not None:
            return replace(get_model(self.venue), point=self.tick_size)
        return self.instrument.cost_model()

    @property
    def sl_buffer(self) -> float:
        """Stop padding in price."""
        ticks = (self.sl_buffer_ticks if self.sl_buffer_ticks is not None
                 else self.instrument.sl_buffer_ticks)
        return ticks * self.tick_size

    @property
    def min_sl_price(self) -> float:
        """Minimum stop distance in price."""
        ticks = (self.min_sl_ticks if self.min_sl_ticks is not None
                 else self.instrument.min_stop_ticks)
        return ticks * self.tick_size

    @property
    def tp_dedup(self) -> float:
        """Take-profit levels closer together than this are merged."""
        return self.instrument.tp_dedup_ticks * self.tick_size

    @property
    def htf_list(self) -> list[int]:
        """All higher timeframes for bias calculation."""
        return [self.tf_d1, self.tf_h4, self.tf_h1, self.tf_m30]

    @property
    def mid_tfs(self) -> list[int]:
        """Mid timeframes for alignment check."""
        return [self.tf_h4, self.tf_h1, self.tf_m30]
