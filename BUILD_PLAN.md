# SMC Bot — Manual Build Plan

A dependency-ordered guide to rebuilding this codebase by hand. Each step is a
separate build session with its own checkpoint. Line references point at the
current implementation so you can compare your version against it.

**Total surface:** ~2,560 lines across 12 files. Roughly a third of that
(`report.py`) is presentation you can defer indefinitely.

---

## Step 0 — Commit the spec

`TRADING_LOGIC.md` is **not in this repository**. Every module docstring cites
it as the source of truth — `config.py:1`, `indicators.py:2`, `strategy.py:2` —
but the file itself was never committed.

If you are rebuilding manually, that document is your specification. Put it in
the repo before you write a line of code.

---

## Step 1 — `config.py`

**74 lines. Write this first.** It imports nothing but `dataclass`, and every
other module imports it.

Writing it first forces you to name every parameter before you write logic that
depends on one. The derived properties at the bottom are what stop timeframe
lists from being duplicated across modules:

- `sl_buffer` — points → price
- `htf_list` — `[D1, H4, H1, M30]`, used by the bias loop
- `mid_tfs` — `[H4, H1, M30]`, used by the alignment check

### Parameters that are declared but never used

Fix these while you are rebuilding, rather than inheriting them:

| Parameter | Status |
|---|---|
| `slippage_points` (`config.py:41`) | **Never referenced anywhere in the codebase.** On an M1 strategy with 3-pip minimum stops, this is not a rounding error — it is a material share of edge. Wire it into the fill price in `strategy.run`, not into the metrics. |
| `commission_pct` (`config.py:40`) | Passed into `compute_metrics` by all three runners, then ignored — the function applies a flat `$0.70`/trade (`backtest.py:18`). Either implement the percentage model or delete the parameter. |
| `tp_max_targets` (`config.py:45`) | Honoured by `_collect_tp`, but every caller uses `tp_levels[0]` only (`strategy.py:508`, `:550`, `:588`). TP2 and TP3 are computed and discarded. |

---

## Step 2 — `indicators.py`

Already sectioned 1–9, and **the numbering is the dependency order.** Build it
in that order.

| § | Function | Line | Why it sits here |
|---|---|---|---|
| 1 | `detect_pivots` | `:16` | Everything structural depends on it |
| 2 | `compute_bias` | `:54` | Needs pivots |
| 3 | `compute_bos` | `:109` | Needs pivots |
| 4 | `compute_swing_levels` | `:186` | TP targets |
| 5 | `compute_rsi` → `compute_wyckoff_ranges` | `:222`, `:254` | Independent branch |
| 6 | `compute_order_blocks` | `:386` | **Needs BOS output** — cannot come earlier |
| 7 | `compute_fvg` | `:472` | Independent, pure 3-bar geometry |
| 8 | `compute_equal_hl` | `:552` | Needs pivots |
| 9 | `align_to_base` | `:621` | Three lines, but the entire MTF glue |

Write a chart-plotting sanity check after §1 and after §3. If pivots or BOS are
wrong, every number downstream is wrong and the backtest will not tell you.

---

## Step 3 — The concepts to study before writing strategy code

These are where the bugs live. Read them properly once; you will save days.

### 3a. The confirmation delay in `detect_pivots` (`indicators.py:29-40`)

A pivot found at bar `i` is stamped at `i + lookback`, not at `i`:

```python
confirm_idx = i + lookback     # :32 and :38
```

That single line is the whole anti-lookahead design — it mirrors Pine's
`ta.pivothigh`/`pivotlow` confirmation behaviour. Write the obvious version that
stamps at `i` and your backtest becomes excellent and meaningless.

### 3b. HTF alignment (`indicators.py:621` + `strategy.py:188-266`)

Every higher-timeframe series is `reindex(..., method="ffill")` onto the M1
index, so an M1 bar can only see the last *stamped* HTF bar. Combined with
`label='left'` resampling (step 4a), that stamp is the HTF bar's **opening**
time.

This is deliberate for structural bias, which is derived from already-confirmed
pivots. But if you add any indicator that reads the HTF bar's `close`, you have
leaked the future. Know which side of that line every field is on.

### 3c. The HTF range gate (`strategy.py:341-348`)

The largest deviation from a naive reading of the spec, and it is commented in
place. Wyckoff RSI range detection tags **93–97% of forex bars** as "in range",
so using it as a hard trade blocker produces zero trades.

The actual gate is structural:

```python
any_htf_blocking = (bd == 0)   # :348 — D1 bias of zero means ranging
```

Wyckoff survives only on M5, where it selects the entry *mode* rather than
permitting or blocking the trade.

### 3d. Level vs. edge (`strategy.py:213-219`)

```python
m5_bull_edge = (m5_bull_on_m1 & ~m5_bull_on_m1.shift(1, fill_value=False)).values
```

Forward-fill the boolean onto M1, then `x & ~x.shift(1)` to convert a **level**
("a BOS is active") into an **edge** ("a BOS just appeared on this M1 bar").
Without this conversion you re-trigger an entry on every bar for the entire life
of the BOS.

### 3e. Pip conversion in `_compute_sl` (`strategy.py:149`)

```python
min_sl_dist = self.cfg.min_sl_pips * self.cfg.point * 10
```

The `* 10` converts pips to price on a 5-digit quote. Get it wrong by a factor
of ten and your stops look plausible while being silently 10× too tight or too
wide.

### 3f. Do not rebuild the dead HTF machinery

The following are computed and maintained every bar, and **never read by any
entry condition**:

- `htf_breakout_confirmed`, `htf_bos_after_range`, `htf_range_max`, `htf_range_min` (`strategy.py:282-285`)
- `htf_in_range`, `htf_range_ceil`, `htf_range_floor` (`:196-203`)
- `m5_double_bos_confirmed` (`:288`) — written and updated, never gates anything

The HTF double-BOS breakout confirmation is dead weight in the current code.
Either skip it, or wire it into `m5_confirmed` deliberately — but know that
switching it on will change your trade count substantially.

---

## Step 4 — The data layer

Three files, one interface. Write the **contract** first:

```python
fetch_all_timeframes(symbol: str, timeframes: list[int], num_bars: int)
    -> dict[int, pd.DataFrame]
# key   = timeframe in minutes (1, 5, 30, 60, 240, 1440)
# value = DatetimeIndex + columns: open, high, low, close, volume
```

That is *all* `strategy.py` knows about data. Both loaders implement it
identically (`histdata_loader.py:9`, `mt5_data.py:64`), which is why swapping
sources is a one-line import change. Preserve that property or you lose it.

### 4a. `histdata_loader.py` — 48 lines, write this first

Offline CSV → resample. Lets you iterate on strategy logic without a broker
terminal running.

- Reads `data_1m_{SYMBOL}.csv`, resamples M1 up to everything else (`:22-43`)
- Resample rule chosen by divisibility (`:28-33`): `{n}D` / `{n}h` / `{n}min`
- **The line that matters most (`:35`):** `label='left', closed='left'` — each
  HTF bar carries its *opening* timestamp. See 3b for why this matters.
- `.dropna()` after resample (`:42`) removes forex weekend gaps
- `.tail(num_bars)` is applied **per timeframe after resampling** (`:43`), so
  all timeframes share an end date but not a start date

> **Known discrepancy, worth writing down:** `1D` resampling buckets on midnight
> UTC. MT5's real D1 bars bucket on broker server time (typically UTC+2/+3). D1
> bias from the CSV loader and from MT5 are *not the same series* for the same
> dates. Do not chase that difference in backtest results — this is the cause.

### 4b. `get_free_data.py` — only if you need the CSV

A histdata.com scraper, which exists because the `histdata` PyPI package is
broken.

- `download_zip` (`:8`) performs a token dance: GET the referer page → scrape
  `<input id="tk">` (`:22`) → POST that token to `get.php` with
  `tk/date/datemonth/platform/timeframe/fxpair` (`:27-36`). The `Referer` header
  is required; without it the response body is empty.
- `process_zip` (`:45`) parses the ASCII format: semicolon-separated, **no
  header row**, `YYYYMMDD HHMMSS;O;H;L;C;V` (`:53-58`)
- **Volume is always 0 in histdata ASCII.** Never build an indicator on it.
- Combine → sort → `set_index` → dedupe on index (`:103-108`). The dedupe
  matters when a month zip overlaps the year zip.

Parameterize two things immediately: the years are hardcoded (2024 full-year
zip, 2025 month-by-month — `:80`, `:89`) and the symbol list is hardcoded in
`__main__` (`:115-116`).

### 4c. `mt5_data.py` — write last

- `TF_MAP` (`:8`) translates integer-minutes into `mt5.TIMEFRAME_*` constants.
  Keeping config in plain minutes and translating only here is what keeps MT5
  out of the rest of the codebase.
- `fetch_ohlcv` (`:39`): `copy_rates_from_pos(symbol, tf, 0, num_bars)` (`:48`)
  pulls the most recent N bars; `tick_volume` → `volume` (`:58`)
- Timestamps via `to_datetime(unit="s")` (`:56`) are **naive, in broker server
  time**. `cfg.trade_start` strings are compared directly against them, so those
  are broker time too.
- **The per-timeframe bar budget (`:74-83`) is the non-obvious part.** MT5 errors
  rather than truncating when you request too many bars, so the requested M1
  count is scaled down per timeframe and capped: M1→99k, M5→80k, ≤M30→30k,
  ≤H4→15k, D1→10k. Skip this and you get a `RuntimeError` from `:50` and assume
  the symbol is wrong.

> **Checkpoint 4:** load both sources for the same symbol and period, then diff
> bar counts per timeframe. Expect D1 to differ (bucketing). Expect M5/H1 to
> match closely. Wildly different M1 counts mean your CSV has gaps.

---

## Step 5 — `strategy.py`

Do not write this top to bottom. It is four independently testable pieces.

### 5a. `precompute` (`:29-85`) — pure wiring, no logic

Builds one flat dict keyed by the convention `f"{kind}_{tf}"`. That convention
is load-bearing: `run` and `_collect_tp` look POIs up by constructed string
(`poi_row.get(f"ob_{tf}_ob_bear_bot")`), so a typo surfaces as *silently missing
TP targets*, never as an exception.

| Lines | What | Note |
|---|---|---|
| `:33-34` | Bias on D1/H4/H1/M30 | all use `cfg.swing_lookback` |
| `:37-40` | Wyckoff ranges on D1/H4/H1 | for gating — mostly unused, see 3c |
| `:43-47` | M5 bias, BOS, wrange | M5 is the confirmation timeframe |
| `:50-52` | M1 bias + BOS | **two different lookbacks**: `min(swing_lookback,5)` for bias, `cfg.m1_swing_lookback`=3 for BOS |
| `:55-60` | D1/H4 POIs: OB, FVG, EQH/EQL, swings | OB needs BOS computed first |
| `:63-71` | M5 and H1 POIs | nearer TP targets |
| `:74-78` | M1 OBs | `max_age=200` is **hardcoded**, not from config |

Two improvements while rebuilding: hoist that `max_age=200` into `Config`, and
cache `compute_bos` — it is recomputed for D1/H4/H1 inside the POI loop (`:56`,
`:69`) after already existing for M5.

**Test standalone:** assert every expected key is present and no frame is 100%
NaN. A silently empty `eqhl_1440` costs you TP targets and raises nothing.

### 5b. `_collect_tp` (`:87-137`) and `_compute_sl` (`:142-179`) — before `run`

Both are pure functions. Feed them synthetic dicts and assert on output. This is
the only part of the strategy that is cheap to unit-test, so do it.

**`_collect_tp`** — for a long, you collect **bearish** POIs above price:
`ob_bear_bot`, `fvg_bear_mid` (`:96-99`). Opposing-side zones are where price is
expected to stall. Searches M5 → H1 → H4 → D1, sorts by distance, merges levels
within 20 points (`:112-116`), returns at most 3. Only `tp_levels[0]` is ever
consumed.

**`_compute_sl`** priority chain:

1. OB edge, if this is an OB entry (`:154-158`)
2. M1 swing low/high (`:162-163`)
3. M5 BOS break level (`:164-165`)
4. The minimum-distance floor (`:149` — see 3e)

Returns `NaN` when nothing qualifies, and every caller checks for it (`:510`,
`:552`).

### 5c. `run` — three phases, in this order

**Phase 1 — alignment (`:188-266`).** Every HTF series becomes a plain numpy
array of length `len(m1)`. Write only this, assert all shapes are equal, and
stop. The edge conversion at `:213-219` is covered in 3d.

**Phase 2 — state and gating (`:275-296`, then `:330-427`).** The per-bar
decision cascade:

```
mid_agree        :334   how many of H4/H1/M30 agree with D1
bias_confirmed   :339   D1 non-zero AND mid_agree >= cfg.min_mid_tf_agree
any_htf_blocking :348   just (bd == 0)          <- the real range filter
m5_confirmed     :386   bias_confirmed + M5 BOS same direction + count >= 1
m5_is_trending   :395   selects Mode A vs Mode B
```

Then the cooldown machinery (`:398-413`) and the **D1 bias-change full reset**
(`:415-427`), which wipes `entry_attempts`, clears `range_cooldown`, and sets
the double-BOS flags permissive.

**Phase 3 — position management (`:429-460`), then entry (`:475-611`).** The
order inside the loop is not arbitrary:

1. Check SL/TP on the open position — **SL is tested before TP** (`:434-437`).
   When one M1 bar straddles both, you book the loss. Correct pessimistic
   default; keep it.
2. `M5_BOS_FLIP` invalidation runs only if SL/TP did not hit (`:449-459`) and
   exits at close, not at a level.
3. `continue` if still in a position (`:466-467`) — you never enter on the same
   bar you exited.
4. Date filter (`:469-473`), then the cooldown/confirmation gate (`:475`).
5. Mode A momentum (`:484-532`) or Mode B OB retouch (`:533-611`).
6. After the loop, force-close any open position as `END_OF_DATA` (`:613-621`).

> **The two entry modes have different fill assumptions.** Mode A fills at the M1
> **close** (`c`, `:503`). Mode B fills at the **OB edge** (`ob_top`/`ob_bot`,
> `:540`, `:578`) — an assumed limit fill at a price the bar merely touched. Mode
> B results are therefore more optimistic. The trade log already tags this via
> `entry_mode`, so compare them separately.

> **Checkpoint 5:** run on ~30 days of M1. You want a non-empty trade log
> containing both `MOMENTUM` and `RANGING` rows. Then hand-verify *one* trade
> against a chart: does the D1 bias direction match, is the SL where you would
> have put it, is TP1 an actual POI?

---

## Step 6 — `backtest.py`

Pure functions over the trades DataFrame, with zero strategy knowledge. About 90
lines of real work.

`compute_metrics` (`:7-102`) order: apply costs → split wins/losses → aggregate
→ equity curve → drawdown → streaks → breakdowns.

Three things to decide deliberately rather than copy:

- **Commission (`:17-21`).** Takes `commission_pct` and ignores it, applying a
  flat `$0.70` per trade. See step 1.
- **Sharpe (`:43-46`).** `(mean/std) * sqrt(252)` treats every *trade* as a
  *day*. With multiple trades per day or gaps between them, that annualization
  is meaningless. Usable as a relative knob between parameter sets; not
  comparable to any published Sharpe.
- **Slippage.** Never applied anywhere. See step 1.

The returned dict carries `equity_curve` and `drawdown_curve` as numpy arrays
(`:100-101`) — `report.py` reads those exact keys, so it is a real interface,
not diagnostics.

`print_report` (`:105-148`) is dumb formatting. Write it in ten minutes; it is
your primary debugging surface for the next week.

> **Checkpoint 6:** feed `compute_metrics` a hand-built 5-row DataFrame with
> known PnLs. Verify win rate, profit factor, and max drawdown by hand. Do this
> before trusting a single backtest number.

---

## Step 7 — `report.py`

503 lines, zero logic, entirely presentation. Safe to defer indefinitely.

**Write `_candle_fig` (`:34-133`) first and render exactly one chart.** It is
called four times per trade, so every improvement multiplies. It draws
candlesticks → entry line and annotation → SL line → TP line → exit marker →
shaded profit/loss zones (`:102-117`).

Then `build_report` (`:136-497`), which is straight string concatenation:

1. Equity and drawdown subplots (`:151-193`), with a per-trade marker scatter on
   the curve (`:170-182`)
2. Per-trade loop (`:195-301`): slice each timeframe around the entry using
   `index.searchsorted(entry_t)` and a fixed window — **D1 ±30, H4 ±40, M5 ±60,
   M1 ±100 bars** (`:213-249`). Those four windows are the top-down "why did this
   trade fire" story.
3. Stats grid (`:303-357`), breakdown tables, CSS, HTML skeleton

**The one mechanical thing to get right:** Plotly loads once from CDN (`:383`),
and every figure is emitted with `include_plotlyjs=False` (`:295-298`, `:488`).
Flip that to `True` anywhere and you embed ~3 MB of JavaScript *per chart*.

**Scaling ceiling — plan for it up front.** Four figures per trade. At 200 trades
that is 800 Plotly figures in one file, well into tens of MB, and it will hang
the browser tab. Cap the per-trade section (last 50 trades, or losses only) or
emit charts to separate files from day one. Retrofitting is annoying.

---

## Step 8 — The runners (the part to build differently)

`run.py`, `run_backtest_1y.py` and `run_backtest_offline.py` are the **same
four-step pipeline** three times: fetch → precompute → run → metrics + report.

| File | Source | Symbols | Date window |
|---|---|---|---|
| `run.py` | MT5 | CLI `--symbol` | CLI `--start/--end` |
| `run_backtest_1y.py` | MT5 | hardcoded `["EURUSD","GBPUSD"]` (`:25`) | now − 365d (`:28-29`) |
| `run_backtest_offline.py` | CSV | hardcoded `["EURUSD","GBPUSD"]` (`:14`) | from data bounds (`:42-45`) |

Between the two multi-symbol runners the diff is *literally the import line* —
`histdata_loader` (`run_backtest_offline.py:9`) vs `mt5_data`
(`run_backtest_1y.py:19`) — plus where the dates come from. Both loaders already
expose the identical signature precisely so this can be one file.

**Build one runner with `--source {mt5,csv}` and a `--symbols` list.** A third of
the code, and one place to fix a pipeline bug.

One behaviour to notice: the offline runner sets `trade_start`/`trade_end` from
the data bounds (`:42-45`), which effectively *disables* the date filter, since
every bar falls inside the range. So the offline and 1y runners do not exercise
the same path through `strategy.run:469-473`.

---

## Build order with checkpoints

| # | Build | Stop when |
|---|---|---|
| 0 | Commit `TRADING_LOGIC.md` | Spec is in the repo |
| 1 | `config.py` | Every parameter named; dead ones resolved |
| 2 | `indicators.py` §1–§3 | Pivots and BOS verified on a plotted chart |
| 2 | `indicators.py` §4–§9 | All nine functions return correctly shaped frames |
| 4a | `histdata_loader.py` | Six timeframes load, bar counts sane |
| 4c | `mt5_data.py` | Same symbol matches 4a on M5/H1 |
| 5a | `precompute` | Every key present, no all-NaN frames |
| 5b | `_collect_tp` + `_compute_sl` | Unit tests pass on synthetic input |
| 5c-1 | `run` phase 1 | All aligned arrays are `len(m1)` |
| 5c-2 | `run` phases 2–3 | Non-empty trade log, both entry modes present |
| 6 | `compute_metrics` + `print_report` | Hand-verified on a 5-row fixture |
| 8 | One unified runner | End-to-end on 30 days |
| 7 | `report.py` | One trade card renders correctly |

The single highest-value stop is **5c-1**. If the aligned arrays are wrong,
everything downstream still runs, still produces trades, and still prints a
plausible report — it is just measuring a market that never existed.
