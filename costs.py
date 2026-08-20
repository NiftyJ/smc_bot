"""Trading cost models — commission, spread and slippage per trade.

The backtest sizes every position as ``qty = risk_per_trade / sl_dist``, so a
tight stop produces a very large notional. Any realistic cost scales with that
notional, which is why a flat per-trade fee understates live costs badly.

All models return the *round-turn* cost (entry + exit) in account currency for
one trade of ``qty`` units of the base instrument.
"""

from dataclasses import dataclass


@dataclass
class CostModel:
    """Round-turn trading costs for one venue.

    Attributes:
        name: Human-readable venue label.
        contract_size: Units of base currency in one lot / contract.
        commission_per_contract: Round-turn commission per lot / contract ($).
        fee_bps: Round-turn fee as basis points of notional (crypto-style).
            Applied in addition to ``commission_per_contract``.
        spread_points: Round-turn price cost (spread + slippage) in points.
        point: Price value of one point for the instrument.
        whole_contracts: If True, size is rounded up to whole contracts when
            charging commission (futures behave this way; forex does not).
        flat_per_trade: Fixed round-turn cost per trade, independent of size.
    """

    name: str = "custom"
    contract_size: float = 100_000.0
    commission_per_contract: float = 0.0
    fee_bps: float = 0.0
    spread_points: float = 0.0
    point: float = 0.00001
    whole_contracts: bool = False
    flat_per_trade: float = 0.0

    def contracts(self, qty: float) -> float:
        """Number of lots / contracts represented by ``qty`` base units."""
        n = abs(qty) / self.contract_size
        if self.whole_contracts:
            import math
            n = math.ceil(n) if n > 0 else 0.0
        return n

    def commission(self, qty: float, price: float) -> float:
        """Round-turn commission for one trade."""
        c = self.flat_per_trade + self.contracts(qty) * self.commission_per_contract
        if self.fee_bps:
            c += abs(qty) * price * self.fee_bps / 10_000.0
        return c

    def price_cost(self, qty: float) -> float:
        """Round-turn spread + slippage cost, in account currency."""
        return self.spread_points * self.point * abs(qty)

    def total(self, qty: float, price: float) -> float:
        """Full round-turn cost of one trade."""
        return self.commission(qty, price) + self.price_cost(qty)


# ---------------------------------------------------------------------------
# Venue presets. Numbers are typical retail all-in figures — override them with
# your broker's actual schedule before trusting any comparison.
# ---------------------------------------------------------------------------

PRESETS: dict[str, CostModel] = {
    # Raw-spread forex: commission per standard lot plus a thin spread.
    "forex_ecn": CostModel(
        name="Forex ECN (raw spread + commission)",
        contract_size=100_000.0,
        commission_per_contract=7.00,   # $7 round turn per standard lot
        spread_points=3.0,              # ~0.3 pip round trip
        point=0.00001,
    ),
    # Commission-free forex: the cost is entirely in the wider spread.
    "forex_standard": CostModel(
        name="Forex standard (spread only)",
        contract_size=100_000.0,
        commission_per_contract=0.0,
        spread_points=12.0,             # ~1.2 pip spread
        point=0.00001,
    ),
    # CME 6E euro FX future: 125,000 EUR per contract, 0.00005 tick.
    "futures_6e": CostModel(
        name="CME 6E euro FX future",
        contract_size=125_000.0,
        commission_per_contract=4.00,   # broker + exchange + NFA, round turn
        spread_points=5.0,              # one tick round trip
        point=0.00001,
        whole_contracts=True,
    ),
    # CME E-micro 6E: one tenth the size, proportionally worse commission.
    "futures_m6e": CostModel(
        name="CME M6E micro euro FX future",
        contract_size=12_500.0,
        commission_per_contract=1.20,
        spread_points=10.0,             # micros quote wider in ticks
        point=0.00001,
        whole_contracts=True,
    ),
    # Crypto perpetual swap: taker fee on notional, both sides.
    "crypto_perp": CostModel(
        name="Crypto perpetual (taker fees)",
        contract_size=1.0,
        commission_per_contract=0.0,
        fee_bps=10.0,                   # 5 bps per side, round turn
        spread_points=0.0,
        point=0.00001,
    ),
    # The old backtest assumption, kept so historic runs can be reproduced.
    "legacy_flat": CostModel(
        name="Legacy flat $0.70 per trade",
        contract_size=1.0,
        commission_per_contract=0.0,
        spread_points=0.0,
        point=0.00001,
        flat_per_trade=0.70,
    ),
}


def get_model(venue: str) -> CostModel:
    """Look up a preset by name."""
    if venue not in PRESETS:
        raise ValueError(
            f"Unknown venue {venue!r}. Choose one of: {', '.join(sorted(PRESETS))}"
        )
    return PRESETS[venue]
