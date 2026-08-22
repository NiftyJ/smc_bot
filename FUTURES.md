# Trading the SMC bot on futures (ES / NQ) instead of FX

## Why this change

On the FX account the bot's edge was real but a big slice of it went to the
broker: **$277.64 of commission against $955.74 of gross profit — roughly 29%
of the take** — plus swap on anything held overnight, plus a variable spread.

Futures do **not** remove commission, so it is worth being precise: CME
futures carry a round-turn commission too (broker + exchange + NFA fees),
typically **~$1.20 per micro contract** and **~$4.20 per E-mini contract**.
What changes is the ratio. On MES at $250 of risk per trade you pay about
$7–12 of commission on a trade risking $250 (≈3–5%), against the 20–30%
the FX account was charging, and:

* the spread is one tick, visible in the order book, not a broker markup;
* there is no swap/financing — futures roll quarterly instead;
* the tick value is fixed and known, so PnL is exact rather than
  quote-currency dependent.

Both cost models are now modelled explicitly, so the backtest tells you the
truth for whichever you run.

## What the migration changed

| Area | Before (FX) | Now |
|---|---|---|
| Symbol | `EURUSD`, hardcoded `point = 0.00001` | `instruments.py` registry; `Config` derives tick size, digits and costs from the symbol |
| Sizing | `qty = risk / sl_distance` (fractional units) | whole contracts, rounded **down**, so a trade never exceeds the risk budget |
| PnL | `price_move * qty` | `price_move * multiplier * contracts` (ES point = $50, MES = $5, NQ = $20, MNQ = $2) |
| Commission | flat `$0.70` per trade placeholder | real round-turn rate per contract, overridable per broker |
| Slippage | unused config field | charged per side, per contract, in the trade log |
| Stops | `min_sl_pips`, `sl_buffer_points` | `min_sl_ticks`, `sl_buffer_ticks`, snapped to a tradable tick |
| Session | none (FX is 24/5) | optional `--rth-only` (CME RTH 08:30–15:00 US/Central) |
| Report | prices at 5 dp | precision follows the tick size; contracts and costs shown per trade |

## Usage

```bash
python run.py --list-instruments          # ES, MES, NQ, MNQ, YM, MYM, RTY, M2K, CL, GC ...
python run.py --symbol MES                # Micro E-mini S&P 500
python run.py --symbol NQ --risk 500      # E-mini Nasdaq-100
python run.py --symbol MNQ --rth-only     # skip the thin overnight session
python run.py --symbol MES --commission 0.74   # your broker's real rate
python run_backtest_1y.py MES MNQ         # 1-year run, one HTML report each
python test_instruments.py                # contract-math tests
```

FX still works unchanged: `python run.py --symbol EURUSD` falls back to the FX
spec (unit sizing, per-lot commission).

## Sizing reality check on a $10k account

Risk is `contracts = floor(risk_budget / (stop_distance × $/point))`:

| Contract | $/point | $250 risk buys | Note |
|---|---|---|---|
| MES | $5 | 6 contracts on an 8-point stop | granular enough to size properly |
| MNQ | $2 | 12 contracts on a 10-point stop | granular |
| ES | $50 | 0 contracts on an 8-point stop | one contract alone risks $400 |
| NQ | $20 | 1 contract on a 12-point stop | workable but chunky |

**Start on the micros (MES/MNQ).** With $10k, a full-size ES contract cannot
be sized to $250 of risk on a typical intraday stop — the strategy will simply
skip those trades (`qty = 0`) rather than over-risk. Pass `--allow-min-qty` to
force one contract anyway, but that breaks the risk model and the backtest
will show it.

Note the default `risk_per_trade` dropped from $500 to $250: 5% of a $10k
account per trade is aggressive for an instrument with overnight gap risk.

## Data

MT5 futures symbols vary by broker — `ES`, `ESU5`, `ES.cme`, `SP500_F` — so
`mt5_data.resolve_broker_symbol()` searches Market Watch for the root and its
aliases and picks the front month. If it warns that nothing matched, check
that your broker actually offers CME futures (many FX-only brokers do not; you
may need a futures broker and a different data path).

`get_free_data.py` pulls HistData, which is **FX only**. For offline futures
backtests, export M1 bars from MT5 or a data vendor to
`data_1m_MES.csv` with columns `time,open,high,low,close,volume` and run
`python run_backtest_offline.py MES`.

## Before going live

The strategy logic is unchanged — only the money math is. Two things still
need validating on real futures data:

1. **Re-tune the tick-based parameters.** `min_sl_ticks` (8 for ES, 16 for NQ)
   and `tp_dedupe_ticks` are sensible starting points, not optimised values;
   NQ ranges several times wider than ES per unit of time.
2. **Re-check the session assumption.** The FX results came from a 24/5 market.
   CME index futures are thinnest between 16:00 and 18:00 US/Central; compare
   an `--rth-only` run against the full-session run before trusting either.
