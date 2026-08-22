"""
Instrument specifications — futures contracts and FX.

The strategy logic is instrument-agnostic (it works in price space), but
position sizing, PnL and costs are not. This module holds everything that
differs between an FX pair and a futures contract:

  * tick size / tick value (futures PnL is quantised, not linear in price)
  * contract multiplier
  * commission per contract, round turn (futures DO have commission — it is
    just much smaller relative to position size than an FX broker's markup,
    and there is no swap/financing on intraday futures)
  * exchange session hours (for optional RTH-only trading)

Prices for CME index futures are quoted in index points: ES 5432.25,
NQ 19875.50. One ES point = 4 ticks = $50; one MES point = $5.
"""

from dataclasses import dataclass, field
from datetime import time as dtime


@dataclass(frozen=True)
class Instrument:
    """Everything the sizing/PnL layer needs to know about a tradable symbol."""

    name: str                    # canonical name, e.g. "MES"
    description: str
    kind: str                    # "futures" | "forex"
    tick_size: float             # minimum price increment
    tick_value: float            # account currency per tick per contract
    multiplier: float            # account currency per 1.0 price point per contract
    commission_per_contract: float  # ROUND TURN, per contract/lot
    currency: str = "USD"
    min_qty: float = 1.0         # smallest tradable size
    qty_step: float = 1.0        # size granularity (1 contract for futures)
    min_sl_ticks: int = 8        # sanity floor for stop distance
    sl_buffer_ticks: int = 2     # buffer beyond the structural SL level
    slippage_ticks: float = 1.0  # assumed slippage per side
    tp_dedupe_ticks: int = 20    # merge TP levels closer than this
    # Regular Trading Hours in exchange local time (CME: US/Central).
    rth_start: dtime = dtime(8, 30)
    rth_end: dtime = dtime(15, 0)
    exchange_tz: str = "America/Chicago"
    # Broker symbol spellings that map to this instrument (MT5 feeds vary).
    aliases: tuple = field(default_factory=tuple)

    # ---------------- derived helpers ----------------

    @property
    def digits(self) -> int:
        """Decimal places implied by the tick size (for display/rounding)."""
        s = f"{self.tick_size:.10f}".rstrip("0")
        return len(s.split(".")[1]) if "." in s else 0

    @property
    def point(self) -> float:
        """Alias used by the strategy for the minimum price increment."""
        return self.tick_size

    def ticks(self, price_distance: float) -> float:
        """Convert a price distance to ticks."""
        return abs(price_distance) / self.tick_size

    def round_price(self, price: float) -> float:
        """Snap a price to a valid tick."""
        return round(round(price / self.tick_size) * self.tick_size, self.digits)

    def value_per_price_unit(self, qty: float) -> float:
        """Account-currency PnL per 1.0 of price movement, for `qty` contracts."""
        return self.multiplier * qty

    def pnl(self, direction: int, entry: float, exit_: float, qty: float) -> float:
        """Signed PnL in account currency (gross of commission)."""
        move = (exit_ - entry) if direction == 1 else (entry - exit_)
        return move * self.multiplier * qty

    def risk_per_contract(self, sl_distance: float) -> float:
        """Account-currency loss of one contract if the stop is hit."""
        return abs(sl_distance) * self.multiplier

    def size_position(self, risk_amount: float, sl_distance: float,
                      allow_min_qty: bool = False) -> float:
        """
        Contracts to trade so that hitting the stop costs ~`risk_amount`.

        Futures are integral: the size is rounded DOWN to the contract step so
        the trade never risks more than requested. Returns 0.0 when even one
        contract exceeds the risk budget — unless `allow_min_qty` is set, in
        which case the minimum size is taken (and the trade over-risks).
        """
        per_contract = self.risk_per_contract(sl_distance)
        if per_contract <= 0:
            return 0.0
        raw = risk_amount / per_contract
        if self.qty_step <= 0:
            return raw
        qty = int(raw / self.qty_step) * self.qty_step
        if qty < self.min_qty:
            return self.min_qty if allow_min_qty else 0.0
        return qty

    def commission(self, qty: float) -> float:
        """Round-turn commission for a position of `qty` contracts."""
        return self.commission_per_contract * qty

    def slippage_cost(self, qty: float) -> float:
        """Assumed slippage cost (entry + exit) in account currency."""
        return 2.0 * self.slippage_ticks * self.tick_size * self.multiplier * qty

    def summary(self) -> str:
        return (
            f"{self.name} ({self.description}) | tick {self.tick_size:g} = "
            f"${self.tick_value:g} | ${self.multiplier:g}/point | "
            f"comm ${self.commission_per_contract:g} round turn"
        )


# ----------------------------------------------------------------------
# Registry — CME index futures (full-size + micros) and a few others.
# Commissions are typical retail all-in round-turn rates
# (broker + exchange + NFA); override per broker via Config.
# ----------------------------------------------------------------------

def _fut(name, desc, tick, tick_val, comm, aliases=(), **kw) -> Instrument:
    return Instrument(
        name=name, description=desc, kind="futures",
        tick_size=tick, tick_value=tick_val,
        multiplier=tick_val / tick,
        commission_per_contract=comm,
        aliases=tuple(aliases), **kw
    )


INSTRUMENTS: dict[str, Instrument] = {
    # ---- E-mini / Micro E-mini equity index ----
    "ES": _fut("ES", "E-mini S&P 500", 0.25, 12.50, 4.20,
               aliases=("ESZ", "ES1!", "SP500_F", "US500_F"),
               min_sl_ticks=8, tp_dedupe_ticks=8),
    "MES": _fut("MES", "Micro E-mini S&P 500", 0.25, 1.25, 1.20,
                aliases=("MESZ", "MES1!",),
                min_sl_ticks=8, tp_dedupe_ticks=8),
    "NQ": _fut("NQ", "E-mini Nasdaq-100", 0.25, 5.00, 4.20,
               aliases=("NQZ", "NQ1!", "NAS100_F", "USTEC_F"),
               min_sl_ticks=16, tp_dedupe_ticks=20),
    "MNQ": _fut("MNQ", "Micro E-mini Nasdaq-100", 0.25, 0.50, 1.20,
                aliases=("MNQZ", "MNQ1!"),
                min_sl_ticks=16, tp_dedupe_ticks=20),
    "YM": _fut("YM", "E-mini Dow", 1.0, 5.00, 4.20, aliases=("YM1!",),
               min_sl_ticks=20, tp_dedupe_ticks=20),
    "MYM": _fut("MYM", "Micro E-mini Dow", 1.0, 0.50, 1.20, aliases=("MYM1!",),
                min_sl_ticks=20, tp_dedupe_ticks=20),
    "RTY": _fut("RTY", "E-mini Russell 2000", 0.10, 5.00, 4.20, aliases=("RTY1!",),
                min_sl_ticks=20, tp_dedupe_ticks=20),
    "M2K": _fut("M2K", "Micro E-mini Russell 2000", 0.10, 0.50, 1.20, aliases=("M2K1!",),
                min_sl_ticks=20, tp_dedupe_ticks=20),
    # ---- Commodities (RTH times differ; energy/metals trade nearly 24h) ----
    "CL": _fut("CL", "Crude Oil", 0.01, 10.00, 4.20, aliases=("CL1!",),
               min_sl_ticks=10, tp_dedupe_ticks=15,
               rth_start=dtime(8, 0), rth_end=dtime(13, 30)),
    "MCL": _fut("MCL", "Micro Crude Oil", 0.01, 1.00, 1.20, aliases=("MCL1!",),
                min_sl_ticks=10, tp_dedupe_ticks=15,
                rth_start=dtime(8, 0), rth_end=dtime(13, 30)),
    "GC": _fut("GC", "Gold", 0.10, 10.00, 4.20, aliases=("GC1!",),
               min_sl_ticks=10, tp_dedupe_ticks=15,
               rth_start=dtime(7, 20), rth_end=dtime(12, 30)),
    "MGC": _fut("MGC", "Micro Gold", 0.10, 1.00, 1.20, aliases=("MGC1!",),
                min_sl_ticks=10, tp_dedupe_ticks=15,
                rth_start=dtime(7, 20), rth_end=dtime(12, 30)),
}


def forex_instrument(symbol: str) -> Instrument:
    """
    Fallback spec for an FX pair so the old behaviour still works.

    Sizing is in units of base currency (qty_step 1000 = micro lot) and the
    commission is a per-lot round turn scaled to the traded size.
    """
    sym = symbol.upper()
    jpy = sym.endswith("JPY")
    tick = 0.001 if jpy else 0.00001
    # Sizing is per unit of base currency, so one tick on one unit is worth
    # exactly the tick size in quote currency (multiplier 1.0).
    return Instrument(
        name=sym, description=f"FX {sym}", kind="forex",
        tick_size=tick, tick_value=tick,
        multiplier=1.0,                     # PnL = price move * units
        commission_per_contract=7.0 / 100_000,   # ~$7 per standard lot, per unit
        min_qty=1000.0, qty_step=1000.0,
        min_sl_ticks=30, sl_buffer_ticks=3, slippage_ticks=2.0,
        tp_dedupe_ticks=20,
        rth_start=dtime(0, 0), rth_end=dtime(23, 59),
        exchange_tz="UTC",
    )


def resolve(symbol: str) -> Instrument:
    """
    Map a user/broker symbol to an Instrument spec.

    Handles broker decorations: "MESU5", "ES.CME", "NQ-1224", "MNQ.fut",
    "es_mini". Unknown non-futures symbols fall back to an FX spec.
    """
    raw = (symbol or "").strip().upper()
    if not raw:
        raise ValueError("Empty symbol")

    if raw in INSTRUMENTS:
        return INSTRUMENTS[raw]

    # Common spoken forms
    spoken = {
        "ES MINI": "ES", "ES_MINI": "ES", "EMINI": "ES", "E-MINI": "ES",
        "SP500": "ES", "S&P": "ES", "SPX": "ES",
        "NASDAQ": "NQ", "NAS100": "NQ", "USTEC": "NQ", "NDX": "NQ",
        "MICRO ES": "MES", "MICRO NQ": "MNQ",
    }
    if raw in spoken:
        return INSTRUMENTS[spoken[raw]]

    cleaned = raw.replace("-", "").replace("_", "").replace(".", "")
    for name, spec in INSTRUMENTS.items():
        if cleaned == name:
            return spec
        for alias in spec.aliases:
            if cleaned == alias.replace("-", "").replace("_", "").replace(".", ""):
                return spec

    # Futures contract codes: root + month letter + year digits, e.g. MESU5, ESZ25
    for name in sorted(INSTRUMENTS, key=len, reverse=True):
        if cleaned.startswith(name):
            tail = cleaned[len(name):]
            if tail and tail[0] in "FGHJKMNQUVXZ" and tail[1:].isdigit():
                return INSTRUMENTS[name]
            if tail in ("FUT", "CME", "CBOT", "COMEX", "NYMEX"):
                return INSTRUMENTS[name]

    return forex_instrument(raw)


def is_futures(symbol: str) -> bool:
    return resolve(symbol).kind == "futures"


def list_futures() -> list[str]:
    return list(INSTRUMENTS.keys())
