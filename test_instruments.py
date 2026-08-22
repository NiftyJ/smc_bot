"""
Contract-math tests for the futures migration.

Run: python test_instruments.py   (or: pytest test_instruments.py)
"""

import numpy as np
import pandas as pd

from config import Config
from instruments import resolve, INSTRUMENTS, forex_instrument
from strategy import SMCStrategy
from backtest import compute_metrics


def test_symbol_resolution():
    assert resolve("ES").name == "ES"
    assert resolve("mes").name == "MES"
    assert resolve("MESU5").name == "MES"      # contract month suffix
    assert resolve("ESZ25").name == "ES"
    assert resolve("NQ.CME").name == "NQ"
    assert resolve("es mini").name == "ES"
    assert resolve("NAS100").name == "NQ"
    assert resolve("EURUSD").kind == "forex"
    assert resolve("GBPJPY").tick_size == 0.001


def test_tick_value_consistency():
    """tick_value must equal tick_size * multiplier for every instrument."""
    for spec in list(INSTRUMENTS.values()) + [forex_instrument("EURUSD")]:
        assert abs(spec.tick_value - spec.tick_size * spec.multiplier) < 1e-9, spec.name


def test_known_contract_values():
    es, nq = resolve("ES"), resolve("NQ")
    assert (es.tick_size, es.tick_value, es.multiplier) == (0.25, 12.50, 50.0)
    assert (nq.tick_size, nq.tick_value, nq.multiplier) == (0.25, 5.00, 20.0)
    # 10 ES points on 2 contracts = 10 * $50 * 2
    assert es.pnl(1, 5000.0, 5010.0, 2) == 1000.0
    # a short that goes 4 points against you on 1 MNQ = -4 * $2
    assert resolve("MNQ").pnl(-1, 19000.0, 19004.0, 1) == -8.0


def test_sizing_is_integral_and_within_budget():
    mes = resolve("MES")
    # $250 risk, 8-point stop => $40/contract => 6 contracts ($240 risked)
    qty = mes.size_position(250.0, 8.0)
    assert qty == 6.0
    assert mes.risk_per_contract(8.0) * qty <= 250.0
    # A stop so wide that one contract busts the budget => no trade...
    assert mes.size_position(250.0, 60.0) == 0.0
    # ...unless explicitly allowed to take the minimum size
    assert mes.size_position(250.0, 60.0, allow_min_qty=True) == 1.0
    # Full-size ES needs 10x the stop room for the same budget
    assert resolve("ES").size_position(250.0, 8.0) == 0.0


def test_costs():
    cfg = Config(symbol="MES", risk_per_trade=250.0)
    assert cfg.commission_per_contract == 1.20
    assert abs(cfg.instrument.commission(6) - 7.2) < 1e-9
    # Broker override wins
    assert Config(symbol="MES", commission_override=0.74).commission_per_contract == 0.74
    # Slippage: 1 tick per side, both sides, per contract
    assert cfg.instrument.slippage_cost(6) == 2 * 1.0 * 1.25 * 6


def test_config_derives_from_instrument():
    es = Config(symbol="ES")
    assert es.point == 0.25 and es.digits == 2 and es.is_futures
    assert es.min_sl_dist == 8 * 0.25          # 8 ticks = 2 index points
    assert es.sl_buffer == 2 * 0.25
    fx = Config(symbol="EURUSD")
    assert fx.point == 0.00001 and fx.digits == 5 and not fx.is_futures
    # Explicit ticks override the instrument defaults
    assert Config(symbol="ES", min_sl_ticks=20).min_sl_dist == 5.0


def _synthetic_es(n=60_000, seed=11):
    """Random-walk M1 bars quantised to the ES tick, plus resampled TFs."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-02", periods=n, freq="1min")
    close = np.round((5000 + rng.normal(0, 0.35, n).cumsum()) / 0.25) * 0.25
    op = np.roll(close, 1); op[0] = close[0]
    m1 = pd.DataFrame({
        "open": op,
        "high": close + np.abs(rng.normal(0, 0.5, n)),
        "low": close - np.abs(rng.normal(0, 0.5, n)),
        "close": close,
        "volume": rng.integers(10, 500, n),
    }, index=idx)
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    return {tf: (m1 if tf == 1 else
                 m1.resample(f"{tf}min", label="left", closed="left").agg(agg).dropna())
            for tf in [1, 5, 30, 60, 240, 1440]}


def test_end_to_end_futures_backtest():
    cfg = Config(symbol="MES", initial_capital=10000, risk_per_trade=250)
    data = _synthetic_es()
    strat = SMCStrategy(cfg)
    trades = strat.run(data, strat.precompute(data))
    if trades.empty:
        return  # random data may not trigger; the invariants below need trades

    qty = trades["qty"].values
    assert np.all(qty == np.round(qty)) and np.all(qty >= 1), "contracts must be whole"
    assert np.all(trades["risk"].values <= cfg.risk_per_trade + 1e-6), "risk budget breached"

    # Stops must sit on a tradable tick
    ticks = np.abs(trades["sl"].values - trades["entry_price"].values) / cfg.point
    assert np.allclose(ticks, np.round(ticks), atol=1e-6)

    # PnL must be contract math, not price math
    sign = np.where(trades["direction"] == "LONG", 1, -1)
    expected = ((trades["exit_price"] - trades["entry_price"]) * sign
                * cfg.instrument.multiplier * trades["qty"])
    assert np.allclose(expected, trades["pnl"])

    # Costs are booked per contract and netted in the metrics
    assert np.allclose(trades["commission"], cfg.commission_per_contract * trades["qty"])
    m = compute_metrics(trades, cfg.initial_capital, cfg)
    assert abs(m["net_pnl"] - (m["gross_pnl_before_costs"]
                               - m["total_commissions"] - m["total_slippage"])) < 0.01


def test_rth_filter():
    cfg = Config(symbol="MES", rth_only=True, risk_per_trade=250)
    data = _synthetic_es()
    strat = SMCStrategy(cfg)
    trades = strat.run(data, strat.precompute(data))
    if trades.empty:
        return
    local = pd.DatetimeIndex(trades["entry_time"]).tz_localize("UTC").tz_convert("America/Chicago")
    assert local.hour.min() >= 8 and local.hour.max() < 15
    assert local.dayofweek.max() < 5


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
