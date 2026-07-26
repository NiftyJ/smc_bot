# `indicators.py` — line-by-line walkthrough with a worked example

This document explains every function, loop and branch in `indicators.py` by
running one hypothetical OHLC dataframe through it. Every number in the trace
tables below is **actual output** from running the real code against the sample
data — not hand-waved arithmetic.

---

## 0. The sample dataframe

24 hourly bars. Prices are whole numbers so the arithmetic is easy to follow.
The path is deliberately shaped: a rally that makes higher highs and higher
lows (bars 0–17), then a sell-off (bars 18–23).

| i | time | open | high | low | close |
|---|------|------|------|-----|-------|
| 0 | 00:00 | 99 | 102 | 98 | 101 |
| 1 | 01:00 | 101 | 104 | 100 | 103 |
| 2 | 02:00 | 103 | **106** | 102 | 104 |
| 3 | 03:00 | 103 | 103 | 99 | 100 |
| 4 | 04:00 | 100 | 101 | **97** | 99 |
| 5 | 05:00 | 101 | 105 | 101 | 104 |
| 6 | 06:00 | 105 | **109** | 105 | 108 |
| 7 | 07:00 | 107 | 107 | 103 | 104 |
| 8 | 08:00 | 104 | 104 | **100** | 101 |
| 9 | 09:00 | 106 | 110 | 106 | 109 |
| 10 | 10:00 | 110 | **114** | 110 | 113 |
| 11 | 11:00 | 112 | 112 | 108 | 109 |
| 12 | 12:00 | 108 | 108 | 104 | 105 |
| 13 | 13:00 | 105 | 106 | **102** | 103 |
| 14 | 14:00 | 107 | 111 | 107 | 110 |
| 15 | 15:00 | 112 | **116** | 112 | 115 |
| 16 | 16:00 | 113 | 113 | 109 | 110 |
| 17 | 17:00 | 109 | 109 | 105 | 106 |
| 18 | 18:00 | 105 | 105 | 101 | 102 |
| 19 | 19:00 | 101 | 101 | 97 | 98 |
| 20 | 20:00 | 98 | 99 | **95** | 96 |
| 21 | 21:00 | 99 | **103** | 99 | 102 |
| 22 | 22:00 | 100 | 100 | 96 | 97 |
| 23 | 23:00 | 97 | 97 | 93 | 94 |

Bold cells are the swing points the code will find. Throughout we use
`lookback = 2` (the real bot uses larger values; 2 keeps the trace short).

The index is a `DatetimeIndex`. That matters — several functions return
dataframes built with `index=df.index`, so the outputs line up with the input
bar-for-bar and can be `pd.concat`'d together.

---

## 1. `detect_pivots(df, lookback)` — lines 16–47

### What it does

Finds swing highs and swing lows, but **reports them late on purpose**. A pivot
high at bar `i` is only knowable after `lookback` more bars have printed, so the
function writes the pivot's *price* at bar `i + lookback`. This mimics Pine
Script's `ta.pivothigh()` and, crucially, avoids look-ahead bias in a backtest:
at bar 4 you are allowed to know "bar 2 was a swing high", because in real time
bar 4 is when you'd have found out.

### Line by line

```python
highs = df["high"].values      # 22-23: pull raw numpy arrays out of the frame.
lows  = df["low"].values       #        Indexing a numpy array in a tight loop is
n     = len(df)                #        far faster than df.iloc[i].

ph = np.full(n, np.nan)        # 26-27: output arrays, one slot per bar,
pl = np.full(n, np.nan)        #        pre-filled with NaN = "no pivot here".
```

```python
for i in range(lookback, n - lookback):
```
Line 29. `i` is the **candidate** bar. The range starts at `lookback` because a
bar needs `lookback` bars to its left to be comparable, and stops at
`n - lookback` because it needs `lookback` bars to its right. With `n = 24,
lookback = 2` this is `i = 2 … 21`. Bars 0, 1, 22 and 23 can never be candidates.

```python
window_h = highs[i - lookback: i + lookback + 1]
```
Line 30. A symmetric window of `2*lookback + 1 = 5` bars centred on `i`. The
`+ 1` on the end is because Python slices exclude the stop index.

For `i = 2`: `highs[0:5]` → `[102, 104, 106, 103, 101]`.

```python
if highs[i] == window_h.max() and np.sum(window_h == highs[i]) == 1:
```
Line 31. Two conditions joined by `and`:

1. `highs[i] == window_h.max()` — the candidate is the highest in the window.
2. `np.sum(window_h == highs[i]) == 1` — and it is the **only** bar at that
   price. `window_h == highs[i]` produces a boolean array like
   `[F, F, T, F, F]`; summing booleans counts the `True`s.

For `i = 2`: max is 106, `highs[2]` is 106 ✓, and only one bar equals 106 ✓ →
this is a pivot high.

> **Gotcha.** Condition 2 rejects *any* tie. If two bars in the window share the
> same high, neither becomes a pivot. On real M1 FX data — where the same high
> prints repeatedly during quiet sessions — this silently suppresses pivots, and
> everything downstream (bias, BOS, order blocks, EQH) goes quiet with it. If
> you ever see a stretch of the backtest with no signals, check here first.

```python
confirm_idx = i + lookback
if confirm_idx < n:
    ph[confirm_idx] = highs[i]
```
Lines 32–34. The delay. The pivot found at bar 2 is written into slot 4.

> **Note.** The `if confirm_idx < n` guard can never be false. The loop's upper
> bound is `n - lookback`, so the largest `i` is `n - lookback - 1`, making the
> largest `confirm_idx` equal to `n - 1`. It's harmless, just dead.

Lines 36–40 are the mirror image for lows: `.min()` instead of `.max()`, and the
same uniqueness test. Note that both blocks run for the same `i` — one bar can
in principle be checked as both a high and a low candidate (it just can't
usually satisfy both).

```python
result = df[["open", "high", "low", "close"]].copy()
if "volume" in df.columns:
    result["volume"] = df["volume"]
```
Lines 42–44. Builds the return frame. The `if` makes volume optional, because
some data sources (tick-derived FX) don't carry it.

> **Gotcha.** Only OHLC + volume survive. Any other column you attached to `df`
> before calling this — a session flag, an ATR column — is dropped from the
> returned frame.

### Trace

Loop iterations that fire:

| i (candidate) | window | verdict | written to |
|---|---|---|---|
| 2 | `highs[0:5] = [102,104,**106**,103,101]` | pivot high 106 | `ph[4] = 106` |
| 4 | `lows[2:7] = [102,99,**97**,101,105]` | pivot low 97 | `pl[6] = 97` |
| 6 | `highs[4:9] = [101,105,**109**,107,104]` | pivot high 109 | `ph[8] = 109` |
| 8 | `lows[6:11] = [105,103,**100**,106,110]` | pivot low 100 | `pl[10] = 100` |
| 10 | `highs[8:13] = [104,110,**114**,112,108]` | pivot high 114 | `ph[12] = 114` |
| 13 | `lows[11:16] = [108,104,**102**,107,112]` | pivot low 102 | `pl[15] = 102` |
| 15 | `highs[13:18] = [106,111,**116**,113,109]` | pivot high 116 | `ph[17] = 116` |
| 20 | `lows[18:23] = [101,97,**95**,99,96]` | pivot low 95 | `pl[22] = 95` |
| 21 | `highs[19:24] = [101,99,**103**,100,97]` | pivot high 103 | `ph[23] = 103` |

All other `i` values fail the `if` and write nothing.

Result columns:

| i | pivot_high | pivot_low |
|---|---|---|
| 4 | 106 | — |
| 6 | — | 97 |
| 8 | 109 | — |
| 10 | — | 100 |
| 12 | 114 | — |
| 15 | — | 102 |
| 17 | 116 | — |
| 22 | — | 95 |
| 23 | 103 | — |

Read that as: "at bar 4 we *learn* that bar 2 was a high of 106."

---

## 2. `compute_bias(df, lookback, use_close)` — lines 54–102

### What it does

Produces one integer per bar: `1` bullish, `-1` bearish, `0` undecided. Two
mechanisms can set it — a higher-high/higher-low structure test, and a
break-of-structure test.

### Line by line

```python
df_piv = detect_pivots(df, lookback)   # 60
bias = np.zeros(n, dtype=int)          # 62: default 0 everywhere
sh1 = sh2 = sl1 = sl2 = np.nan         # 64
current_bias = 0                       # 65
```

`sh1` = most recent swing high, `sh2` = the one before it; `sl1`/`sl2` likewise
for lows. These are **rolling state variables**: they persist across loop
iterations, which is what makes this a stateful scan rather than a vectorised
calculation.

```python
for i in range(n):
    if not np.isnan(phs[i]):
        sh2 = sh1
        sh1 = phs[i]
```
Lines 73–76. Every bar, check whether a pivot was confirmed here. `np.isnan` is
the test for "no pivot" because that's how `detect_pivots` marks empty slots.
The two-line shuffle pushes the old value down before overwriting — order
matters; swap those lines and you'd lose `sh2`.

Lines 77–79 do the same for lows.

```python
if not np.isnan(sh1) and not np.isnan(sh2) and \
   not np.isnan(sl1) and not np.isnan(sl2):
```
Lines 81–82. The structure test only runs once **all four** levels exist. In our
data that's bar 10 — you need two highs and two lows before you can say "higher
high and higher low".

```python
    if sh1 > sh2 and sl1 > sl2:
        current_bias = 1
    elif sh1 < sh2 and sl1 < sl2:
        current_bias = -1
```
Lines 83–86. Classic market structure. Note the missing `else`: if highs are
rising but lows are falling (a broadening pattern), **neither** branch fires and
`current_bias` keeps whatever it was. That's intentional — mixed structure is
not a reason to flip.

```python
break_src     = closes[i] if use_close else highs[i]
break_src_low = closes[i] if use_close else lows[i]
```
Lines 88–89. The `use_close` switch. With `True` a break must be confirmed by a
closing price (conservative, fewer signals). With `False` a wick through the
level counts (aggressive, earlier, more false breaks).

```python
if i > 0 and not np.isnan(sh1):
    prev = closes[i - 1] if use_close else highs[i - 1]
    if break_src > sh1 and prev <= sh1:
        current_bias = 1
```
Lines 91–94. The `i > 0` guard exists solely so `i - 1` doesn't wrap to the end
of the array. The inner `if` is a **crossover** test, not a level test: price
must be above `sh1` *now* and have been at-or-below it on the previous bar. That
`prev <= sh1` clause is what stops the bias re-firing on every bar of a trend.

Lines 95–98 mirror it downward.

```python
    bias[i] = current_bias   # 100
```
Whatever state we ended the bar in gets recorded.

### Trace

| i | event | sh2/sh1 | sl2/sl1 | structure test | BOS test | bias |
|---|---|---|---|---|---|---|
| 0–3 | — | —/— | —/— | skipped (NaNs) | skipped | 0 |
| 4 | ph 106 | —/106 | —/— | skipped | close 99 < 106 | 0 |
| 5 | — | —/106 | —/— | skipped | close 104 < 106 | 0 |
| 6 | pl 97 | —/106 | —/97 | skipped | **close 108 > 106, prev 104 ≤ 106 → bull** | **1** |
| 7 | — | —/106 | —/97 | skipped | no cross | 1 |
| 8 | ph 109 | 106/109 | —/97 | skipped (`sl2` NaN) | no cross | 1 |
| 9 | — | 106/109 | —/97 | skipped | no cross | 1 |
| 10 | pl 100 | 106/109 | 97/100 | **first run:** 109>106 ✓, 100>97 ✓ → bull | close 113 > 109, prev 109 ≤ 109 → bull | 1 |
| 11–18 | … | … | … | stays bull | no cross | 1 |
| 19 | — | 114/116 | 100/102 | 116>114 ✓ 102>100 ✓ → sets **1** | **close 98 < 102, prev 102 ≥ 102 → bear** | **-1** |
| 20 | — | 114/116 | 100/102 | 116>114 ✓ 102>100 ✓ → sets **1** again | close 96 < 102 but prev 98 < 102, no cross | **1** ⚠ |
| 21 | — | 114/116 | 100/102 | → 1 | no cross | 1 |
| 22 | pl 95 | 114/116 | 102/95 | 116>114 ✓ but 95>102 ✗; 116<114 ✗ → **no change** | close 97 > 95 | 1 |
| 23 | ph 103 | 116/103 | 102/95 | 103<116 ✓ 95<102 ✓ → **bear** | close 94 < 95, prev 97 ≥ 95 → bear | **-1** |

> ### ⚠ The bar-20 flip — read this one carefully
>
> At bar 19 the BOS check correctly flags bearish. At bar 20 the *structure*
> block runs again, from the exact same four unchanged swing values
> (`sh1=116, sh2=114, sl1=102, sl2=100`), re-concludes "higher high, higher
> low", and stamps `current_bias = 1` — wiping out the bear call.
>
> The cause is ordering: the structure block sits **above** the BOS block and
> re-evaluates on every single bar, whether or not new pivots arrived. So a BOS
> override only survives on the bar it fires; the next bar reverts it, and it
> stays reverted until fresh pivots change the four levels (here, bar 22).
>
> Compare with row 22: the structure test finds mixed evidence, hits neither
> branch, and correctly leaves the bias alone. That's the behaviour you'd want
> at bar 20 too. Fixes worth considering: only run the structure block on bars
> where a new pivot was confirmed, or move the BOS block above it, or track
> "bias was set by BOS at bar k" and require new pivots before structure can
> override it.

---

## 3. `compute_bos(df, lookback, use_close)` — lines 109–179

### What it does

Same crossover logic as the bias function, but instead of one number it emits a
full event record: which bar broke, in which direction, how many consecutive
breaks that direction has produced, and the high/low of the breaking candle.

### Line by line

```python
bos_bull = np.zeros(n, dtype=bool)   # 118: event flags, one-bar pulses
bos_bear = np.zeros(n, dtype=bool)   # 119
bos_dir  = np.zeros(n, dtype=int)    # 120: persistent state, current direction
bos_count = np.zeros(n, dtype=int)   # 121: persistent, consecutive breaks
bos_break_high = np.full(n, np.nan)  # 122: high of the last breaking candle
bos_break_low  = np.full(n, np.nan)  # 123
sh1_arr = np.full(n, np.nan)         # 124: the swing levels, exported for
sl1_arr = np.full(n, np.nan)         # 125: strategy/debugging use
```

The distinction matters downstream: `bos_bull` is `True` on exactly one bar
(the break), while `bos_dir` stays set until the opposite break happens.

```python
sh1 = sl1 = np.nan
_dir = 0
_count = 0
_bh = _bl = np.nan
```
Lines 127–130. Rolling state. The `_` prefix is a convention here for "loop-carried
variable". Note this function keeps only `sh1`/`sl1` — no `sh2`/`sl2`, because it
never does the higher-high/higher-low comparison.

```python
if not np.isnan(phs[i]):
    sh1 = phs[i]
if not np.isnan(pls[i]):
    sl1 = pls[i]
sh1_arr[i] = sh1
sl1_arr[i] = sl1
```
Lines 139–145. Update, then record. Because the record happens after the update,
a pivot confirmed at bar `i` is already reflected in `sh1_arr[i]`.

```python
if i > 0 and not np.isnan(sh1):
    if closes[i] > sh1 and closes[i - 1] <= sh1:
```
Lines 147–148. Note this function **always uses closes**, ignoring the
`use_close` parameter entirely.

> **Gotcha.** `use_close` is accepted in the signature but never read in the
> body. Passing `False` here changes nothing — unlike in `compute_bias`, where
> it does. If you're comparing bias against BOS output and they disagree on wick
> breaks, this is why.

```python
        bos_bull[i] = True
        if _dir == 1:
            _count += 1
        else:
            _dir = 1
            _count = 1
```
Lines 149–154. The counter. `if _dir == 1` means "we were already bullish, so
this is another leg in the same direction" → increment. The `else` covers both
"we were bearish" and "we had no direction yet" → reset direction and start the
count at 1. So `bos_count` reads as "how many bullish breaks in this run".

```python
        _bh = highs[i]
        _bl = lows[i]
```
Lines 155–156. The breaking candle's range. The strategy uses this for stop
placement — a bullish break's `_bl` is a natural invalidation point.

Lines 158–167 mirror everything for bearish breaks. Both blocks can theoretically
fire on the same bar (a huge bar that closes above `sh1` and below `sl1` is
impossible, so in practice they're exclusive — but the code doesn't enforce it).

Lines 169–172 snapshot the persistent state into the output arrays every bar.

### Trace

| i | close | sh1 | sl1 | bull? | bear? | dir | count | break_h / break_l |
|---|---|---|---|---|---|---|---|---|
| 0–3 | — | NaN | NaN | | | 0 | 0 | NaN / NaN |
| 4 | 99 | 106 | NaN | 99 > 106? no | `sl1` NaN → block skipped | 0 | 0 | NaN / NaN |
| 5 | 104 | 106 | NaN | no | skipped | 0 | 0 | NaN / NaN |
| **6** | 108 | 106 | 97 | **108>106, prev 104≤106 → yes** | 108 < 97? no | **1** | **1** | 109 / 105 |
| 7 | 104 | 106 | 97 | 104 > 106? no | no | 1 | 1 | 109 / 105 |
| 8 | 101 | 109 | 97 | no | no | 1 | 1 | 109 / 105 |
| 9 | 109 | 109 | 97 | 109 > 109? **no** (strict `>`) | no | 1 | 1 | 109 / 105 |
| **10** | 113 | 109 | 100 | **113>109, prev 109≤109 → yes** | no | 1 | **2** | 114 / 110 |
| 11–14 | … | 114 | 100/102 | no | no | 1 | 2 | 114 / 110 |
| **15** | 115 | 114 | 102 | **115>114, prev 110≤114 → yes** | no | 1 | **3** | 116 / 112 |
| 16–18 | … | 116 | 102 | no | no | 1 | 3 | 116 / 112 |
| **19** | 98 | 116 | 102 | no | **98<102, prev 102≥102 → yes** | **-1** | **1** (reset) | 101 / 97 |
| 20 | 96 | 116 | 102 | no | 96<102 but prev 98 already < 102 → no | -1 | 1 | 101 / 97 |
| 21 | 102 | 116 | 102 | no | 102 < 102? no | -1 | 1 | 101 / 97 |
| 22 | 97 | 116 | 95 | no | 97 < 95? no | -1 | 1 | 101 / 97 |
| **23** | 94 | 103 | 95 | no | **94<95, prev 97≥95 → yes** | -1 | **2** | 97 / 93 |

Two things to notice in this trace:

- **Bar 9 doesn't fire.** `close == sh1` exactly (109). The comparison is strict
  `>`, so touching the level isn't breaking it.
- **Bar 20 doesn't fire** even though price is well below `sl1`. The `prev >= sl1`
  clause requires the crossing *moment*. Once you're below, you're below — the
  event already happened at bar 19.

---

## 4. `compute_swing_levels(df, lookback)` — lines 186–215

The simplest function in the file. It is `compute_bias`'s bookkeeping half with
the decision logic stripped out: track the last two swing highs and last two
swing lows, and publish all four as columns.

```python
for i in range(n):
    if not np.isnan(phs[i]):
        _sh2 = _sh1        # 202: demote before overwriting
        _sh1 = phs[i]      # 203
    if not np.isnan(pls[i]):
        _sl2 = _sl1
        _sl1 = pls[i]
    sw_h1[i] = _sh1        # 207-210: snapshot every bar, pivot or not
    sw_h2[i] = _sh2
    sw_l1[i] = _sl1
    sw_l2[i] = _sl2
```

There is no `else` anywhere: on a bar with no pivot, the state simply carries
forward unchanged, which is exactly the forward-fill behaviour you want.

### Trace

| i | pivot arriving | sw_h1 | sw_h2 | sw_l1 | sw_l2 |
|---|---|---|---|---|---|
| 0–3 | — | NaN | NaN | NaN | NaN |
| 4 | ph 106 | 106 | NaN | NaN | NaN |
| 5 | — | 106 | NaN | NaN | NaN |
| 6 | pl 97 | 106 | NaN | 97 | NaN |
| 7 | — | 106 | NaN | 97 | NaN |
| 8 | ph 109 | 109 | **106** | 97 | NaN |
| 9 | — | 109 | 106 | 97 | NaN |
| 10 | pl 100 | 109 | 106 | 100 | **97** |
| 11 | — | 109 | 106 | 100 | 97 |
| 12 | ph 114 | 114 | 109 | 100 | 97 |
| 13–14 | — | 114 | 109 | 100 | 97 |
| 15 | pl 102 | 114 | 109 | 102 | 100 |
| 16 | — | 114 | 109 | 102 | 100 |
| 17 | ph 116 | 116 | 114 | 102 | 100 |
| 18–21 | — | 116 | 114 | 102 | 100 |
| 22 | pl 95 | 116 | 114 | 95 | 102 |
| 23 | ph 103 | **103** | **116** | 95 | 102 |

The purpose is take-profit targeting: in a long, `sw_h1` is the nearest overhead
swing to aim at, `sw_h2` the one beyond it.

Watch row 23: `sw_h1` (103) is now *lower* than `sw_h2` (116). "h1/h2" means
most-recent and second-most-recent **in time**, not highest and second highest.
Any code that assumes `sw_h1 > sw_h2` will be wrong in a downtrend.

---

## 5a. `compute_rsi(closes, length)` — lines 222–251

Standard Wilder RSI. Takes a plain numpy array, returns a plain numpy array.

```python
if n < length + 1:
    return rsi        # 226-227: all-NaN. Need length+1 closes for length deltas.
```

```python
deltas = np.diff(closes)                        # 229: len n-1. deltas[k] = closes[k+1]-closes[k]
gains  = np.where(deltas > 0, deltas,  0.0)     # 230
losses = np.where(deltas < 0, -deltas, 0.0)     # 231
```
`np.where(cond, a, b)` is a vectorised ternary: element-wise "if cond then a else
b". Losses are stored as **positive** numbers (note the unary minus), which is
what the ratio below expects.

```python
avg_gain = np.mean(gains[:length])     # 233: simple average for the seed
avg_loss = np.mean(losses[:length])    # 234
```
The first `length` deltas — i.e. closes 1 through `length`.

```python
if avg_loss == 0:
    rsi[length] = 100.0        # 236-237: no down moves at all → RSI pinned at 100
else:
    rs = avg_gain / avg_loss   # 239
    rsi[length] = 100.0 - (100.0 / (1.0 + rs))
```
The `if` is division-by-zero protection, and 100 is the mathematically correct
limit as `avg_loss → 0`. First value lands at index `length`, so indices
`0 … length-1` stay NaN — the warm-up period.

```python
for i in range(length, len(deltas)):
    avg_gain = (avg_gain * (length - 1) + gains[i]) / length   # 243
    avg_loss = (avg_loss * (length - 1) + losses[i]) / length  # 244
```
Wilder's smoothing. Equivalent to an EMA with `alpha = 1/length`: keep
`(length-1)/length` of the old average, add `1/length` of the new value. This is
what distinguishes Wilder RSI from a plain rolling-mean RSI.

The `i + 1` offsets on lines 247/249 convert delta-space back to bar-space:
`deltas[i]` describes the move *into* bar `i + 1`.

### Trace with `length = 5`

| i | close | Δ | RSI |
|---|---|---|---|
| 0 | 101 | — | NaN |
| 1 | 103 | +2 | NaN |
| 2 | 104 | +1 | NaN |
| 3 | 100 | −4 | NaN |
| 4 | 99 | −1 | NaN |
| 5 | 104 | +5 | 61.54 ← seed |
| 6 | 108 | +4 | 72.22 |
| 7 | 104 | −4 | 53.61 |
| 8 | 101 | −3 | 43.18 |
| 9 | 109 | +8 | 65.53 |
| 10 | 113 | +4 | 72.34 |
| 11 | 109 | −4 | 58.02 |
| 12 | 105 | −4 | 46.52 |
| 13 | 103 | −2 | 41.39 |
| 14 | 110 | +7 | 60.46 |
| 15 | 115 | +5 | 69.36 |
| 16 | 110 | −5 | 54.13 |
| 17 | 106 | −4 | 44.38 |
| 18 | 102 | −4 | 36.23 |
| 19 | 98 | −4 | 29.46 |
| 20 | 96 | −2 | 26.38 |
| 21 | 102 | +6 | 47.11 |
| 22 | 97 | −5 | 36.43 |
| 23 | 94 | −3 | 31.13 |

Seed check: gains of the first 5 deltas are `[2,1,0,0,5]` → mean 1.6; losses
`[0,0,4,1,0]` → mean 1.0. `rs = 1.6`, `100 - 100/2.6 = 61.54` ✓

---

## 5b. `compute_wyckoff_ranges(df, rsi_length, sensitivity, show_cont)` — lines 254–379

### What it does

Uses RSI to decide when the market is *ranging* rather than trending, draws a
box around that range (highest high / lowest low while inside it), and when the
range breaks, labels it **accumulation** (broke up) or **distribution** (broke
down).

### Setup

```python
upper = 50 + sensitivity     # 274 → 70
lower = 50 - sensitivity     # 275 → 50 - 20 = 30
```
`sensitivity` is a half-width around 50. Bigger = wider neutral zone = more bars
classified as ranging.

```python
range_type = np.full(n, "", dtype=object)   # 281
```
`dtype=object` because numpy has no native variable-length string type here;
`""` is the "unlabelled" marker.

```python
piv_lb = 5                            # 295: hardcoded, NOT the caller's lookback
df_piv = detect_pivots(df, piv_lb)    # 296
```
A second, independent pivot pass at lookback 5. It's used only to decide whether
a range was a *continuation* or a *reversal*. Note this is hardcoded to match
the original Pine source and doesn't follow the rest of the bot's lookback
setting.

### The loop

Lines 302–314 rebuild the same higher-high/higher-low tracker seen in
`compute_bias`, producing `_structure_trend ∈ {-1, 0, 1}`.

```python
r = rsi[i]
if np.isnan(r):
    rsi_state[i] = "side"
    in_range[i] = _in_range
    ...
    continue
```
Lines 317–324. The warm-up guard. During the first `rsi_length` bars there's no
RSI, so the function writes the current (empty) state and `continue`s straight to
the next bar. This is important: it prevents a range from being "started" on a
bar where we have no RSI reading.

```python
prev_r = rsi[i - 1] if i > 0 and not np.isnan(rsi[i - 1]) else r
```
Line 327. Read the conditional carefully: use the previous RSI, but if there
isn't one (bar 0, or the bar right after warm-up), fall back to `r` itself. The
fallback makes the two-bar tests below behave as if the previous bar matched the
current one.

```python
is_side = (lower < r < upper) or (lower < prev_r < upper)
is_bull = r > upper and prev_r > upper
is_bear = r < lower and prev_r < lower
```
Lines 328–330. Note the asymmetry — this is the heart of the function's
behaviour:

- `is_side` uses **or**: in-band on *either* bar counts. Very sticky.
- `is_bull` / `is_bear` use **and**: need *both* bars outside the band. Very
  reluctant.

Together this biases the whole function heavily toward "we're ranging". A single
bar poking above 70 will not end a range.

Lines 332–337 turn those into a label, with `is_bull` winning ties (it's checked
first) and `else` catching everything.

### The four-way range state machine (lines 340–365)

```python
was_side = _in_range
```
Line 340. Snapshot the previous state before mutating it — the four branches
below compare new vs. old.

| branch | condition | meaning | action |
|---|---|---|---|
| 1 | `is_side and not was_side` | range **begins** | set `_in_range=True`, seed `_ceil=high[i]`, `_floor=low[i]`, remember `_range_start_trend` |
| 2 | `is_side and was_side` | range **continues** | expand box: `_ceil = max(_ceil, high[i])`, `_floor = min(_floor, low[i])` |
| 3 | `not is_side and was_side` | range **ends** | classify it, set `_in_range=False` |
| 4 | *(implicit — no `elif`)* | `not is_side and not was_side` = trending | nothing; box values persist as the last range's box |

Branch 4 having no code is deliberate. Outside a range, the previous box stays
published so the strategy can still reference it.

Branch 2's `max(_ceil, highs[i]) if not np.isnan(_ceil) else highs[i]` is
belt-and-braces: `_ceil` should never be NaN when `was_side` is true, but `max()`
against NaN would poison the value permanently, so it's guarded.

Branch 3, the classification:

```python
if is_bull:
    _last_type = "accumulation"
    if not show_cont and _range_start_trend == 1:
        _last_type = ""          # 359-361
elif is_bear:
    _last_type = "distribution"
    if not show_cont and _range_start_trend == -1:
        _last_type = ""          # 363-364
```

Broke upward → accumulation (smart money was buying). Broke downward →
distribution (smart money was selling). The nested `if` is the
**reversal-only filter**: if the range began in an uptrend and also broke
upward, it was just a pause in a trend, not accumulation — so blank the label
unless `show_cont=True`.

Note there's no `else` on `elif is_bear`. If the range ends because `is_side`
went false but neither `is_bull` nor `is_bear` is true, `_last_type` keeps its
previous value. Given how `is_side` is defined this is a narrow case, but the
label is "last classified range", not "this range".

### Trace (`rsi_length=5`, `sensitivity=20` → band 30–70)

| i | rsi | prev | is_side | is_bull | is_bear | branch | in_range | ceil | floor | type |
|---|---|---|---|---|---|---|---|---|---|---|
| 0–4 | NaN | | | | | warm-up `continue` | False | NaN | NaN | "" |
| 5 | 61.54 | (61.54) | ✓ | | | **1 begins** | True | 105 | 101 | "" |
| 6 | 72.22 | 61.54 | ✓ (prev in band) | ✗ (prev ≤ 70) | | 2 expand | True | **109** | 101 | "" |
| 7 | 53.61 | 72.22 | ✓ | | | 2 | True | 109 | 101 | "" |
| 8 | 43.18 | 53.61 | ✓ | | | 2 | True | 109 | **100** | "" |
| 9 | 65.53 | 43.18 | ✓ | | | 2 | True | **110** | 100 | "" |
| 10 | 72.34 | 65.53 | ✓ (prev in band) | ✗ | | 2 | True | **114** | 100 | "" |
| 11 | 58.02 | 72.34 | ✓ | | | 2 | True | 114 | 100 | "" |
| 12–14 | 46.5 / 41.4 / 60.5 | | ✓ | | | 2 | True | 114 | 100 | "" |
| 15 | 69.36 | 60.46 | ✓ | ✗ | | 2 | True | **116** | 100 | "" |
| 16–18 | 54.1 / 44.4 / 36.2 | | ✓ | | | 2 | True | 116 | 100 | "" |
| 19 | 29.46 | 36.23 | ✓ (**prev** in band) | | ✗ (prev ≥ 30) | 2 | True | 116 | **97** | "" |
| **20** | 26.38 | 29.46 | ✗ (both < 30) | | **✓** | **3 ends** | **False** | 116 | 97 | **distribution** |
| 21 | 47.11 | 26.38 | ✓ | | | **1 begins again** | True | **103** | **99** | distribution ⚠ |
| 22 | 36.43 | 47.11 | ✓ | | | 2 | True | 103 | **96** | distribution ⚠ |
| 23 | 31.13 | 36.43 | ✓ | | | 2 | True | 103 | **93** | distribution ⚠ |

Things this trace makes concrete:

- **The range lasts 15 bars (5→19)** even though price rallied from 101 to 116
  inside it. RSI oscillated between 29 and 72, never *twice consecutively*
  outside the band, so `is_side` stayed true. A 15-point trend got labelled
  "sideways". If you want ranges that look like ranges, lower `sensitivity`.
- **`is_bull` never fires anywhere in this dataset.** RSI touches 72.2 and 72.3
  at bars 6 and 10, but never on two consecutive bars, so `rsi_state` is never
  `"bull"` and no range can ever be labelled *accumulation* here.
- **Bar 19 is the trap.** RSI is 29.46, below the lower band — but `prev_r` is
  36.23, inside it, so the `or` in `is_side` keeps the range alive for one more
  bar, and the floor expands to 97. The range only ends at bar 20.
- **⚠ `range_type` is sticky across ranges.** From bar 21 a brand-new range is
  in progress (`in_range=True`, fresh 103/99 box), but `range_type` still reads
  `"distribution"` from the range that ended at bar 20. Branch 1 seeds `_ceil`
  and `_floor` but never resets `_last_type`. Any consumer reading
  `in_range == True` alongside `range_type` gets a label describing a *different*
  range. If you rely on this column, either clear `_last_type` in branch 1 or
  only read `range_type` on bars where `in_range == False`.

---

## 6. `compute_order_blocks(df, bos_df, max_age)` — lines 386–465

### What it does

When a BOS fires, look back for the candle that marks the origin of the move —
for a bullish break, the candle with the **lowest low** before it — and publish
that candle's high/low as an order block zone. Track it until price invalidates
it.

```python
ob_bull_mitigated = np.ones(n, dtype=bool)   # 405
```
Note the default is `True` (`np.ones` for a bool array = all `True`). "No order
block" and "order block already mitigated" are represented the same way, which
makes the flag safe to test without a NaN check.

```python
active_bull_obs = []   # 412: [{"top":…, "bot":…, "bar":…}]
active_bear_obs = []   # 413
```
A list, not a single value — multiple order blocks can be live at once.

### Creating a block

```python
if bos_bull[i]:
    look_start = max(0, i - max_age)     # 419
    if look_start < i:                   # 420
        segment_lows = lows[look_start:i]
        min_idx = look_start + np.argmin(segment_lows)   # 422
        ob_top = highs[min_idx]
        ob_bot = lows[min_idx]
        active_bull_obs.append({"top": ob_top, "bot": ob_bot, "bar": i})
```

- `max(0, …)` clamps so early bars don't produce a negative slice start.
- `if look_start < i` is the empty-window guard; it's only false at `i == 0`.
- `np.argmin` returns the index **within the slice**, so line 422 adds
  `look_start` to convert it back to an absolute bar number. Getting this offset
  wrong is a classic bug — worth noting it's handled correctly here.
- The slice is `[look_start:i]`, excluding the break bar itself.

> **Gotcha — the docstring doesn't match the code.** The docstring says
> "candle with lowest low **between swing low and BOS break bar**". The code
> searches the entire `max_age` window (default **500 bars**) back from the
> break. With the default that's effectively "the lowest low of the last 500
> bars", which in a long uptrend will keep returning the same ancient candle. In
> our trace both the bar-6 and bar-10 breaks resolve to the same bar-4 candle,
> and the identical block gets appended twice. To match the docstring you'd
> clamp `look_start` to the bar index of the current `sl1` swing low.

Lines 427–434 mirror this with `np.argmax` over highs for bearish breaks.

### Mitigation

```python
active_bull_obs = [ob for ob in active_bull_obs if closes[i] >= ob["bot"]]
active_bear_obs = [ob for ob in active_bear_obs if closes[i] <= ob["top"]]
```
Lines 438–446. List comprehensions used as filters: rebuild the list keeping
only survivors. A bullish block dies when a **close** (not a wick) goes below its
bottom — demand failed. A bearish block dies when a close goes above its top.

Two consequences: mitigation is permanent (the dict is discarded, not flagged),
and because this runs *after* creation in the same iteration, a block created at
bar `i` is immediately tested against bar `i`'s close.

```python
if active_bull_obs:
    nearest = active_bull_obs[-1]
```
Lines 449–450. `if <list>` is falsy when empty. `[-1]` is the last appended =
most recent. The variable is called `nearest` but it is **most recent, not
nearest in price** — with several blocks live, a closer one may be ignored.

### Trace

| i | event | active_bull_obs | active_bear_obs | ob_bull top/bot | ob_bear top/bot | bull_mit | bear_mit |
|---|---|---|---|---|---|---|---|
| 0–5 | — | `[]` | `[]` | NaN | NaN | True | True |
| **6** | bull BOS | argmin of `lows[0:6]=[98,100,102,99,97,101]` → 97 at **bar 4** → block `{top:101, bot:97}`. Close 108 ≥ 97 → survives | `[]` | **101 / 97** | NaN | **False** | True |
| 7–9 | — | survives (closes 104, 101, 109 all ≥ 97) | `[]` | 101 / 97 | NaN | False | True |
| **10** | bull BOS | argmin of `lows[0:10]` → still 97 at bar 4 → **duplicate** block appended | `[]` | 101 / 97 | NaN | False | True |
| 11–14 | — | survive | `[]` | 101 / 97 | NaN | False | True |
| **15** | bull BOS | argmin of `lows[0:15]` → still bar 4 → third duplicate | `[]` | 101 / 97 | NaN | False | True |
| 16–18 | — | survive | `[]` | 101 / 97 | NaN | False | True |
| **19** | bear BOS | close 98 ≥ 97 → bull blocks survive | argmax of `highs[0:19]` → 116 at **bar 15** → `{top:116, bot:112}`. Close 98 ≤ 116 → survives | 101 / 97 | **116 / 112** | False | **False** |
| **20** | — | close **96 < 97** → all three bull blocks filtered out → `[]` | survives | **NaN** | 116 / 112 | **True** | False |
| 21–23 | — | `[]` | survives (closes 102, 97, 94 all ≤ 116) | NaN | 116 / 112 | True | False |

The bar-20 row shows mitigation working: one close below 97 invalidates the
demand zone, `ob_bull_top/bot` revert to NaN and `ob_bull_mitigated` flips back
to `True`.

The bear block from bar 19 never mitigates in this sample — price would have to
close above 116, and it's falling.

---

## 7. `compute_fvg(df, max_age)` — lines 472–545

### What it does

Detects three-candle imbalances: a gap between candle 1's range and candle 3's
range that candle 2 blew straight through.

```python
for i in range(2, n):     # 497
```
Starts at 2 because the test reads `i - 2`.

```python
if lows[i] > highs[i - 2] and closes[i - 1] > opens[i - 1]:
    fvg_top = lows[i]
    fvg_bot = highs[i - 2]
```
Lines 500–503. Two conditions: (a) bar `i`'s low is above bar `i-2`'s high — an
untraded price band exists between them; (b) the middle candle closed above its
open, confirming the gap was created by buying. The zone is bounded below by the
old high and above by the new low.

> **Note.** The docstring at line 475 says `candle[i-1].high < candle[i+1].low`,
> which is the same relationship written with the middle candle as the anchor.
> The code anchors on the third candle instead — same pattern, different index
> convention, no look-ahead. Worth knowing when cross-checking against Pine.

Lines 506–509 are the bearish mirror: bar `i`'s high below bar `i-2`'s low, with
a bearish middle candle. Note `fvg_top = lows[i-2]` and `fvg_bot = highs[i]` —
top and bottom are assigned so that `top > bot` always holds regardless of
direction.

### Mitigation

```python
active_bull_fvgs = [
    f for f in active_bull_fvgs
    if lows[i] <= f["top"] or i - f["bar"] < max_age
]
# Actually: mitigated when price fills the gap (low < fvg_bot)
active_bull_fvgs = [
    f for f in active_bull_fvgs
    if not (lows[i] < f["bot"]) and (i - f["bar"] < max_age)
]
```
Lines 512–521.

> **⚠ The first comprehension is dead code.** It's immediately overwritten by the
> second, and it can't even remove anything the second wouldn't: it drops an FVG
> only when `lows[i] > top` **and** the age limit is exceeded, and the second
> drops everything past the age limit anyway. The author's own comment on line
> 517 ("Actually: …") reads like a mid-edit correction that was never cleaned up.
> Deleting lines 512–516 changes no behaviour. Do that — leaving it in invites
> someone to "fix" the wrong filter later.

The real rule (lines 518–521): a bullish FVG survives while price has **not**
traded below its bottom, and while it's younger than `max_age`. Note the age is
measured against the creation bar stored in `f["bar"]` — that's what the `"bar"`
key is for; it's never used for anything else.

Line 523–526 mirror it: a bearish FVG dies when a high pushes above its top.

Mitigation here uses **wicks** (`lows[i]`, `highs[i]`), unlike order blocks which
use closes. That's a deliberate difference — a gap is filled the moment price
trades through it.

```python
fvg_bull_mid[i] = (nearest["top"] + nearest["bot"]) / 2
```
Line 533. The 50% level, used as a partial take-profit target.

### Trace

| i | bullish test | bearish test | after mitigation | published |
|---|---|---|---|---|
| 2 | `low 102 > high[0] 102`? no | `high 106 < low[0] 98`? no | — | — |
| 3 | no | no | — | — |
| **4** | no | `high 101 < low[2] 102` ✓ and `close[3] 100 < open[3] 103` ✓ | bear `{top:102, bot:101}` created; `high[4] 101 > 102`? no → survives | bear 102/101, mid **101.5** |
| 5 | no | no | `high[5] 105 > 102` → bear **killed** | — |
| **6** | `low 105 > high[4] 101` ✓ and `close[5] 104 > open[5] 101` ✓ | no | bull `{top:105, bot:101}`; `low[6] 105 < 101`? no → survives | bull 105/101, mid **103** |
| 7 | no | no | `low[7] 103 < 101`? no → survives | bull 105/101, mid 103 |
| **8** | no | `high 104 < low[6] 105` ✓ and `close[7] 104 < open[7] 107` ✓ | bull: `low[8] 100 < 101` → **killed**. bear `{top:105, bot:104}` created | bear 105/104, mid **104.5** |
| 9 | no | no | `high[9] 110 > 105` → bear **killed** | — |
| **10** | `low 110 > high[8] 104` ✓ and `close[9] 109 > open[9] 106` ✓ | no | bull `{top:110, bot:104}` | bull 110/104, mid **107** |
| 11 | no | no | `low[11] 108 < 104`? no | bull 110/104, mid 107 |
| **12** | no | `high 108 < low[10] 110` ✓ and `close[11] 109 < open[11] 112` ✓ | bull survives (`low 104 < 104`? **no**, strict). bear `{top:110, bot:108}` | **both**: bull 110/104 mid 107, bear 110/108 mid **109** |
| **13** | no | `high 106 < low[11] 108` ✓ and `close[12] 105 < open[12] 108` ✓ | bull: `low[13] 102 < 104` → **killed**. bear from 12 survives; new bear `{top:108, bot:106}` appended | bear **108/106** (the `[-1]`, i.e. newest), mid 107 |
| 14 | no | no | `high[14] 111 > 108` and `> 110` → both bears **killed** | — |
| **15** | `low 112 > high[13] 106` ✓ and `close[14] 110 > open[14] 107` ✓ | no | bull `{top:112, bot:106}` | bull 112/106, mid **109** |
| 16 | no | no | survives | bull 112/106, mid 109 |
| **17** | no | `high 109 < low[15] 112` ✓ and `close[16] 110 < open[16] 113` ✓ | bull: `low[17] 105 < 106` → **killed**. bear `{top:112, bot:109}` | bear 112/109, mid **110.5** |
| **18** | no | `high 105 < low[16] 109` ✓ and `close[17] 106 < open[17] 109` ✓ | new bear `{top:109, bot:105}` | bear 109/105, mid **107** |
| **19** | no | `high 101 < low[17] 105` ✓ ✓ | new bear `{top:105, bot:101}` | bear 105/101, mid **103** |
| **20** | no | `high 99 < low[18] 101` ✓ ✓ | new bear `{top:101, bot:99}` | bear 101/99, mid **100** |
| 21 | no | no | `high[21] 103 > 101` and `> 99`… the 105/101 bear survives (103 ≤ 105) | bear 105/101, mid 103 |
| 22 | no | no | survives | bear 105/101, mid 103 |
| **23** | no | `high 97 < low[21] 99` ✓ and `close[22] 97 < open[22] 100` ✓ | new bear `{top:99, bot:97}` | bear 99/97, mid **98** |

Bar 12 is the interesting one: a bullish and a bearish FVG are simultaneously
live, which is normal — they're at different price levels (104–110 vs 108–110)
and both are legitimate untested imbalances.

Bar 12's bull survival is also a nice edge case: `lows[12]` is exactly 104 and
the test is `lows[i] < f["bot"]`, strict — touching the bottom of the gap doesn't
fill it. One tick lower and it would have died.

---

## 8. `compute_equal_hl(df, lookback, range_pct)` — lines 552–614

### What it does

Finds clusters of swing highs (or lows) at nearly the same price — the liquidity
pools that price tends to run before reversing.

Our 24-bar sample produces **no** equal highs (pivot highs are 106, 109, 114,
116, 103 — no two within 1%), so this section uses a **second, smaller dataset**
built specifically to trigger it:

| i | high | low | close | pivot_high |
|---|---|---|---|---|
| 0 | 105 | 101 | 104 | |
| 1 | 108 | 104 | 107 | |
| 2 | **110** | 106 | 109 | |
| 3 | 107 | 103 | 104 | |
| 4 | 104 | 100 | 101 | **110** (from bar 2) |
| 5 | 107 | 103 | 106 | |
| 6 | **110.5** | 106 | 109 | |
| 7 | 106 | 102 | 103 | |
| 8 | 103 | 99 | 100 | **110.5** (from bar 6) |
| 9 | 105 | 101 | 104 | |
| 10 | 108 | 104 | 107 | |
| 11 | **112** | 108 | **111** | |
| 12 | 110 | 106 | 107 | |
| 13 | 107 | 103 | 104 | **112** (from bar 11) |

### Line by line

```python
eqh_swept = np.ones(n, dtype=bool)    # 566: default True, same idea as OB
swing_highs = []                      # 569: [(bar_idx, price)]
active_eqh  = []                      # 572: [{"level": float}]
```

```python
if not np.isnan(phs[i]):
    swing_highs.append((i, phs[i]))
    recent = [p for (_, p) in swing_highs[-10:]]
```
Lines 576–579. On each new pivot high, append it, then take the prices of the
last 10 swings. The `(_, p)` unpacking discards the bar index — it's stored but
never actually used.

```python
    if len(recent) >= 2:
        for j in range(len(recent) - 1):
            for k in range(j + 1, len(recent)):
                avg = (recent[j] + recent[k]) / 2
                if avg > 0 and abs(recent[j] - recent[k]) / avg < range_pct:
                    active_eqh.append({"level": avg})
                    break
```
Lines 580–587. A nested double loop over all unordered pairs. `k` starts at
`j + 1` so each pair is visited once. For each pair: take the midpoint, and
compare their absolute difference as a fraction of that midpoint against
`range_pct`. The `avg > 0` guard prevents division by zero on degenerate data.

The equal-high **level** published is the midpoint of the pair, not either high.

> **Gotchas in this block:**
>
> 1. **The `break` only exits the inner `k` loop.** The outer `j` loop keeps
>    going, so one pivot arrival can append several levels. With 10 swings
>    clustered in a tight range you can add many near-duplicate entries.
> 2. **Nothing deduplicates.** The same price level can be appended repeatedly on
>    successive pivots — see bar 13 in the trace below, where a level that was
>    already swept comes back.
> 3. **`recent` is recomputed from scratch** on every pivot and re-scanned in
>    full, so old pairs are re-detected again and again.

Lines 589–598 are the identical construction for lows.

```python
active_eqh = [e for e in active_eqh if closes[i] <= e["level"]]
active_eql = [e for e in active_eql if closes[i] >= e["level"]]
```
Lines 601–602. Sweep detection, same filter-by-comprehension pattern. An equal-
high level is "swept" once a close gets above it, and is then discarded.

```python
if active_eqh:
    eqh_level[i] = active_eqh[-1]["level"]
    eqh_swept[i] = False
```
Lines 604–606. Again `[-1]` = most recently added, and again `eqh_swept` really
means "no unswept level is currently tracked" rather than "a sweep just happened".

### Trace (second dataset, `lookback=2`, `range_pct=0.01`)

| i | pivot | pair check | active_eqh | eqh_level | eqh_swept |
|---|---|---|---|---|---|
| 0–3 | — | — | `[]` | NaN | True |
| **4** | ph 110 | `recent=[110]`, `len < 2` → inner loops skipped | `[]` | NaN | True |
| 5–7 | — | — | `[]` | NaN | True |
| **8** | ph 110.5 | `recent=[110, 110.5]`. Pair (110, 110.5): avg 110.25, diff 0.5, 0.5/110.25 = **0.45% < 1%** ✓ | `[{level: 110.25}]` | **110.25** | **False** |
| 9 | — | close 104 ≤ 110.25 → survives | same | 110.25 | False |
| 10 | — | close 107 ≤ 110.25 → survives | same | 110.25 | False |
| **11** | — | **close 111 > 110.25 → swept, filtered out** | `[]` | NaN | **True** |
| 12 | — | — | `[]` | NaN | True |
| **13** | ph 112 | `recent=[110, 110.5, 112]`. j=0,k=1: 0.45% ✓ → **append 110.25 again**, `break` inner. j=1,k=2: (110.5,112) → 1.5/111.25 = 1.35% ✗ | `[{level: 110.25}]` ⚠ | **110.25** ⚠ | **False** ⚠ |

Bar 13 is gotcha #2 in action: the 110.25 level was swept at bar 11 and should be
gone, but the pair `(110, 110.5)` is still sitting in `swing_highs` and gets
re-detected, resurrecting a dead level. Since price is now trading *below* it
again, the sweep filter doesn't remove it, and it stays published indefinitely.

A fix would be to record swept levels in a set and skip them on re-detection, or
to only test pairs involving the pivot that just arrived (`recent[-1]`) rather
than re-scanning all pairs.

---

## 9. `align_to_base(series_or_df, base_index)` — lines 621–623

```python
return series_or_df.reindex(base_index, method="ffill")
```

One line, but conceptually important. Higher-timeframe data (say H4 bias) has
one row every 4 hours; the base timeframe (M1) has one row every minute.
`reindex` maps the HTF frame onto the M1 timestamps, and `method="ffill"`
carries each HTF value forward until the next one appears.

The result is "what was the H4 bias as of this minute?" — and because forward-
fill only ever looks backwards, no future information leaks into the backtest.
It works on both a `Series` and a `DataFrame` because `reindex` is defined on
both, which is why the parameter is untyped.

One caveat: the HTF bar stamped `12:00` becomes visible at M1 `12:00`, i.e. at
the *open* of that HTF bar, before it has finished forming. If the HTF values
are computed from completed-bar logic you'll want to shift them by one HTF bar
before aligning, or you're using a bar's own outcome to trade its interior.

---

## Cross-cutting patterns

Once you've read two or three of these functions the rest are variations on the
same four ideas:

1. **Extract to numpy, loop, write back.** `df["x"].values` at the top, a
   `for i in range(n)` scan, `pd.DataFrame({...}, index=df.index)` at the bottom.
   The loops are stateful — each bar depends on what happened before — which is
   exactly the case where you can't vectorise.

2. **NaN as "nothing here".** Pre-fill outputs with `np.full(n, np.nan)` and test
   with `np.isnan`. For booleans, the equivalent is `np.ones(n, dtype=bool)` —
   default `True` meaning "mitigated / swept / absent".

3. **Rolling state variables** (`sh1`, `_ceil`, `_dir`, `active_bull_obs`)
   declared before the loop, mutated inside it, snapshotted into the output array
   at the end of every iteration. That final snapshot is what turns
   event-at-a-moment into a value-per-bar column.

4. **Crossover, not level.** Every break test is `now > level and prev <= level`,
   never just `now > level`. This is what makes events fire once instead of
   continuously.

5. **List comprehension as a filter.** `active = [x for x in active if <keep>]`
   appears in three functions. It's how zones get retired. Note that survivors
   are kept in insertion order, which is why `[-1]` reliably means "newest".

## Summary of issues found while tracing

Listed roughly by how much they'd affect live results:

| # | Location | Issue |
|---|---|---|
| 1 | `compute_bias` lines 81–86 | The HH/HL block re-runs from unchanged swing values every bar and silently overwrites a BOS-driven bias on the very next bar (bar 20 in the trace flips −1 → 1). |
| 2 | `compute_order_blocks` lines 418–425 | Searches the whole `max_age` (default 500-bar) window instead of "since the swing low" as documented; in a trend it re-appends the same ancient candle on every BOS. |
| 3 | `compute_wyckoff_ranges` branch 1 (lines 342–347) | `_last_type` is not reset when a new range starts, so `range_type` describes the *previous* range while `in_range` is `True`. |
| 4 | `compute_equal_hl` lines 582–587 | `break` exits only the inner loop; no dedup; swept levels get re-detected and resurrected (bar 13 of the second trace). |
| 5 | `compute_bos` line 109 | `use_close` is in the signature but never used — the function always uses closes, unlike `compute_bias`. |
| 6 | `compute_fvg` lines 512–516 | Dead filter, immediately overwritten by the one below it. Safe to delete. |
| 7 | `detect_pivots` line 31 | Strict uniqueness (`np.sum(...) == 1`) rejects every tie, which suppresses pivots on flat/repeated highs common in M1 FX data. |
| 8 | `compute_order_blocks` line 450, `compute_fvg` 530, `compute_equal_hl` 605 | The variable named `nearest` is the most *recent* zone, not the nearest in price. |
| 9 | `compute_wyckoff_ranges` line 295 | `piv_lb = 5` is hardcoded and ignores the lookback used elsewhere in the bot. |
| 10 | `detect_pivots` line 33 | `if confirm_idx < n` can never be false — dead guard. |
| 11 | `detect_pivots` lines 42–44 | Drops every column except OHLCV from the returned frame. |

None of these stop the code running; items 1–4 are the ones that change trading
decisions.
