"""Instrument specifications.

The strategy was written for 5-digit forex: ``point`` was hardcoded to 0.00001
and stop distances were expressed in forex pips. Index futures and gold have
completely different tick sizes and contract values, so running the bot on them
without a spec produces nonsense stops and position sizes.

Sizing note: the strategy computes ``qty = risk_per_trade / sl_dist``, which has
units of "account currency per 1.0 of price move". Dividing that by
``value_per_point`` gives the number of contracts (or lots) to trade, which is
what commission is charged on.

All commission and spread figures are typical retail round-turn values. Replace
them with your broker's actual schedule before trusting any result.
"""

from dataclasses import dataclass

from costs import CostModel


@dataclass(frozen=True)
class Instrument:
    """Market microstructure and cost profile for one tradeable symbol.

    Attributes:
        symbol: Ticker as used by the data feed.
        name: Human-readable description.
        tick_size: Smallest price increment the market quotes.
        value_per_point: Account currency gained by 1 contract per 1.0 of price.
        commission_rt: Round-turn commission per contract / lot.
        spread_ticks: Typical round-turn spread + slippage, in ticks.
        min_stop_ticks: Floor on stop distance, in ticks.
        sl_buffer_ticks: Padding beyond the structural stop level, in ticks.
        tp_dedup_ticks: Take-profit levels closer than this are merged.
        whole_contracts: True for exchange-traded contracts, which cannot be
            traded fractionally; False for forex/CFD lots, which can.
    """

    symbol: str
    name: str
    tick_size: float
    value_per_point: float
    commission_rt: float
    spread_ticks: float
    min_stop_ticks: float
    sl_buffer_ticks: float
    tp_dedup_ticks: float
    whole_contracts: bool = True

    @property
    def tick_value(self) -> float:
        """Account currency gained by 1 contract per 1 tick of price."""
        return self.tick_size * self.value_per_point

    @property
    def min_stop_price(self) -> float:
        """Minimum stop distance expressed in price."""
        return self.min_stop_ticks * self.tick_size

    @property
    def sl_buffer(self) -> float:
        """Stop padding expressed in price."""
        return self.sl_buffer_ticks * self.tick_size

    @property
    def tp_dedup(self) -> float:
        """Take-profit merge distance expressed in price."""
        return self.tp_dedup_ticks * self.tick_size

    def contracts(self, qty: float) -> float:
        """Contracts implied by a ``risk / sl_dist`` sizing figure."""
        return abs(qty) / self.value_per_point

    def cost_model(self) -> CostModel:
        """Cost model matching this instrument's contract and fee structure."""
        return CostModel(
            name=f"{self.symbol} ({self.name})",
            contract_size=self.value_per_point,
            commission_per_contract=self.commission_rt,
            spread_points=self.spread_ticks * self.tick_size,
            point=1.0,  # spread_points is already in price terms
            whole_contracts=self.whole_contracts,
        )


# ---------------------------------------------------------------------------
# Specs. Tick sizes and contract values are exchange definitions; commission and
# spread are typical retail round-turn estimates and should be overridden.
# ---------------------------------------------------------------------------

INSTRUMENTS: dict[str, Instrument] = {
    # --- CME equity index futures -----------------------------------------
    "ES": Instrument(
        symbol="ES", name="E-mini S&P 500",
        tick_size=0.25, value_per_point=50.0,   # $12.50 per tick
        commission_rt=4.00, spread_ticks=2.0,
        min_stop_ticks=16.0,                    # 4 index points
        sl_buffer_ticks=2.0, tp_dedup_ticks=8.0,
    ),
    "MES": Instrument(
        symbol="MES", name="Micro E-mini S&P 500",
        tick_size=0.25, value_per_point=5.0,    # $1.25 per tick
        commission_rt=1.20, spread_ticks=2.0,
        min_stop_ticks=16.0,
        sl_buffer_ticks=2.0, tp_dedup_ticks=8.0,
    ),
    "NQ": Instrument(
        symbol="NQ", name="E-mini Nasdaq 100",
        tick_size=0.25, value_per_point=20.0,   # $5.00 per tick
        commission_rt=4.00, spread_ticks=2.0,
        min_stop_ticks=80.0,                    # 20 index points
        sl_buffer_ticks=4.0, tp_dedup_ticks=20.0,
    ),
    "MNQ": Instrument(
        symbol="MNQ", name="Micro E-mini Nasdaq 100",
        tick_size=0.25, value_per_point=2.0,    # $0.50 per tick
        commission_rt=1.20, spread_ticks=2.0,
        min_stop_ticks=80.0,
        sl_buffer_ticks=4.0, tp_dedup_ticks=20.0,
    ),
    # --- Gold --------------------------------------------------------------
    "XAUUSD": Instrument(
        symbol="XAUUSD", name="Spot gold, 100oz lot",
        tick_size=0.01, value_per_point=100.0,  # $1.00 per tick per lot
        commission_rt=7.00, spread_ticks=25.0,  # ~$0.25 round-turn spread
        min_stop_ticks=100.0,                   # $1.00
        sl_buffer_ticks=10.0, tp_dedup_ticks=50.0,
        whole_contracts=False,                  # lots are fractional
    ),
    "GC": Instrument(
        symbol="GC", name="COMEX gold future, 100oz",
        tick_size=0.10, value_per_point=100.0,  # $10.00 per tick
        commission_rt=4.00, spread_ticks=1.0,
        min_stop_ticks=10.0,                    # $1.00
        sl_buffer_ticks=1.0, tp_dedup_ticks=5.0,
    ),
    "MGC": Instrument(
        symbol="MGC", name="COMEX micro gold future, 10oz",
        tick_size=0.10, value_per_point=10.0,   # $1.00 per tick
        commission_rt=1.20, spread_ticks=2.0,
        min_stop_ticks=10.0,
        sl_buffer_ticks=1.0, tp_dedup_ticks=5.0,
    ),
    # --- Forex, for comparison with the original configuration -------------
    "EURUSD": Instrument(
        symbol="EURUSD", name="Euro/US dollar, 100k lot",
        tick_size=0.00001, value_per_point=100_000.0,
        commission_rt=7.00, spread_ticks=3.0,
        min_stop_ticks=30.0,                    # 3 pips, the original default
        sl_buffer_ticks=3.0, tp_dedup_ticks=20.0,
        whole_contracts=False,
    ),
}

# Common feed aliases mapped onto the contract they track.
ALIASES = {
    "NAS100": "NQ", "USTEC": "NQ", "NSXUSD": "NQ", "US100": "NQ",
    "SPX500": "ES", "US500": "ES", "SPXUSD": "ES", "ESMINI": "ES",
    "GOLD": "XAUUSD", "XAU": "XAUUSD",
}


def get_instrument(symbol: str) -> Instrument:
    """Look up an instrument spec by symbol or feed alias."""
    key = symbol.upper().strip()
    key = ALIASES.get(key, key)
    if key not in INSTRUMENTS:
        raise ValueError(
            f"No spec for {symbol!r}. Known: {', '.join(sorted(INSTRUMENTS))} "
            f"(aliases: {', '.join(sorted(ALIASES))})"
        )
    return INSTRUMENTS[key]
