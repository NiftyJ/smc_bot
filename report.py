"""
Interactive HTML report — equity curve + per-trade candlestick charts.

Generates a single self-contained HTML file with:
  1. Summary stats table
  2. Equity & drawdown curves
  3. Per-trade M1 candlestick chart (±100 bars context) with entry/exit/SL/TP
  4. Per-trade M5 candlestick chart (±60 bars context) for structure view
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# -----------------------------------------------------------------------
# Colors
# -----------------------------------------------------------------------
BG = "#0e1117"
CARD_BG = "#1a1f2e"
TEXT = "#e0e0e0"
GREEN = "#00c853"
RED = "#ff1744"
CYAN = "#00e5ff"
ORANGE = "#ff9100"
YELLOW = "#ffd600"
GRAY = "#555"
TP_COLOR = "#00e676"
SL_COLOR = "#ff5252"
ENTRY_COLOR = "#448aff"


def _candle_fig(df_slice: pd.DataFrame, title: str,
                entry_price: float, exit_price: float,
                sl: float, tp: float,
                entry_time: pd.Timestamp, exit_time: pd.Timestamp,
                direction: str) -> go.Figure:
    """Build a candlestick chart with trade markers."""
    fig = go.Figure()

    # Candlesticks
    fig.add_trace(go.Candlestick(
        x=df_slice.index,
        open=df_slice["open"],
        high=df_slice["high"],
        low=df_slice["low"],
        close=df_slice["close"],
        increasing_line_color=GREEN,
        decreasing_line_color=RED,
        increasing_fillcolor=GREEN,
        decreasing_fillcolor=RED,
        name="Price",
    ))

    x_min = df_slice.index[0]
    x_max = df_slice.index[-1]

    # Entry line
    fig.add_shape(type="line", x0=x_min, x1=x_max,
                  y0=entry_price, y1=entry_price,
                  line=dict(color=ENTRY_COLOR, width=1.5, dash="dash"))
    fig.add_annotation(x=entry_time, y=entry_price,
                       text=f"ENTRY {entry_price:.5f}",
                       showarrow=True, arrowhead=2,
                       font=dict(color=ENTRY_COLOR, size=10),
                       arrowcolor=ENTRY_COLOR, ax=0, ay=-30)

    # SL line
    fig.add_shape(type="line", x0=x_min, x1=x_max,
                  y0=sl, y1=sl,
                  line=dict(color=SL_COLOR, width=1.5, dash="dot"))
    fig.add_annotation(x=x_max, y=sl,
                       text=f"SL {sl:.5f}",
                       showarrow=False,
                       font=dict(color=SL_COLOR, size=9),
                       xanchor="right")

    # TP line
    fig.add_shape(type="line", x0=x_min, x1=x_max,
                  y0=tp, y1=tp,
                  line=dict(color=TP_COLOR, width=1.5, dash="dot"))
    fig.add_annotation(x=x_max, y=tp,
                       text=f"TP {tp:.5f}",
                       showarrow=False,
                       font=dict(color=TP_COLOR, size=9),
                       xanchor="right")

    # Exit marker
    is_win = (direction == "LONG" and exit_price > entry_price) or \
             (direction == "SHORT" and exit_price < entry_price)
    exit_color = GREEN if is_win else RED
    fig.add_trace(go.Scatter(
        x=[exit_time], y=[exit_price],
        mode="markers+text",
        marker=dict(size=12, color=exit_color, symbol="x"),
        text=[f"EXIT {exit_price:.5f}"],
        textposition="top center",
        textfont=dict(color=exit_color, size=10),
        name="Exit",
        showlegend=False,
    ))

    # SL/TP zone shading
    if direction == "LONG":
        # Green zone: entry to TP
        fig.add_shape(type="rect", x0=x_min, x1=x_max,
                      y0=entry_price, y1=tp,
                      fillcolor="rgba(0,200,83,0.06)", line_width=0)
        # Red zone: entry to SL
        fig.add_shape(type="rect", x0=x_min, x1=x_max,
                      y0=sl, y1=entry_price,
                      fillcolor="rgba(255,23,68,0.06)", line_width=0)
    else:
        fig.add_shape(type="rect", x0=x_min, x1=x_max,
                      y0=tp, y1=entry_price,
                      fillcolor="rgba(0,200,83,0.06)", line_width=0)
        fig.add_shape(type="rect", x0=x_min, x1=x_max,
                      y0=entry_price, y1=sl,
                      fillcolor="rgba(255,23,68,0.06)", line_width=0)

    fig.update_layout(
        title=dict(text=title, font=dict(color=TEXT, size=13)),
        template="plotly_dark",
        paper_bgcolor=CARD_BG,
        plot_bgcolor=BG,
        xaxis=dict(rangeslider_visible=False, gridcolor=GRAY),
        yaxis=dict(gridcolor=GRAY, tickformat=".5f"),
        height=350,
        margin=dict(l=60, r=30, t=40, b=30),
        showlegend=False,
    )
    return fig


def build_report(trades: pd.DataFrame, metrics: dict,
                 data: dict, cfg) -> str:
    """
    Build full HTML report.
    Returns the HTML string.
    """
    m1 = data[cfg.tf_m1]
    m5 = data[cfg.tf_m5]
    h4 = data[cfg.tf_h4]
    d1 = data[cfg.tf_d1]

    # ---- Equity & Drawdown ----
    equity = metrics["equity_curve"]
    dd = metrics["drawdown_curve"]

    eq_fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                           row_heights=[0.7, 0.3],
                           vertical_spacing=0.04)

    eq_fig.add_trace(go.Scatter(
        x=list(range(len(equity))), y=equity,
        fill="tozeroy", fillcolor="rgba(0,229,255,0.1)",
        line=dict(color=CYAN, width=2),
        name="Equity",
    ), row=1, col=1)

    eq_fig.add_trace(go.Scatter(
        x=list(range(len(dd))), y=dd,
        fill="tozeroy", fillcolor="rgba(255,23,68,0.2)",
        line=dict(color=RED, width=1.5),
        name="Drawdown %",
    ), row=2, col=1)

    # Mark wins/losses on equity curve
    pnl_arr = trades["pnl"].values
    for idx in range(len(pnl_arr)):
        color = GREEN if pnl_arr[idx] > 0 else RED
        eq_fig.add_trace(go.Scatter(
            x=[idx], y=[equity[idx]],
            mode="markers",
            marker=dict(size=8, color=color),
            showlegend=False,
            hovertext=f"Trade #{idx+1}: ${pnl_arr[idx]:+.2f}",
            hoverinfo="text",
        ), row=1, col=1)

    eq_fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=CARD_BG,
        plot_bgcolor=BG,
        height=400,
        margin=dict(l=60, r=30, t=20, b=30),
        showlegend=False,
        xaxis2=dict(title="Trade #", gridcolor=GRAY),
        yaxis=dict(title="Equity ($)", gridcolor=GRAY),
        yaxis2=dict(title="DD %", gridcolor=GRAY),
    )

    # ---- Per-trade charts ----
    trade_charts_html = ""
    for idx, row in trades.iterrows():
        entry_t = pd.Timestamp(row["entry_time"])
        exit_t = pd.Timestamp(row["exit_time"])
        direction = row["direction"]
        entry_p = row["entry_price"]
        exit_p = row["exit_price"]
        sl = row["sl"]
        tp = row["tp"]
        pnl = row["pnl"]
        trigger = row.get("trigger", "")
        mode = row.get("entry_mode", "")
        reason = row.get("exit_reason", "")
        rr = row.get("rr", 0)

        is_win = pnl > 0
        pnl_color = GREEN if is_win else RED
        result_text = "WIN" if is_win else "LOSS"

        # D1 slice: ±30 bars around entry (±30 days context)
        d1_loc = d1.index.searchsorted(entry_t)
        d1_start = max(0, d1_loc - 30)
        d1_end = min(len(d1), d1_loc + 30)
        d1_slice = d1.iloc[d1_start:d1_end]

        d1_title = f"D1 | Bias Context"
        d1_fig = _candle_fig(d1_slice, d1_title, entry_p, exit_p, sl, tp,
                             entry_t, exit_t, direction)

        # H4 slice: ±40 bars around entry (~1 week each side)
        h4_loc = h4.index.searchsorted(entry_t)
        h4_start = max(0, h4_loc - 40)
        h4_end = min(len(h4), h4_loc + 40)
        h4_slice = h4.iloc[h4_start:h4_end]

        h4_title = f"H4 | Structure Context"
        h4_fig = _candle_fig(h4_slice, h4_title, entry_p, exit_p, sl, tp,
                             entry_t, exit_t, direction)

        # M5 slice: ±60 bars around entry
        m5_loc = m5.index.searchsorted(entry_t)
        m5_start = max(0, m5_loc - 60)
        m5_end = min(len(m5), m5_loc + 60)
        m5_slice = m5.iloc[m5_start:m5_end]

        m5_title = f"M5 | Confirmation"
        m5_fig = _candle_fig(m5_slice, m5_title, entry_p, exit_p, sl, tp,
                             entry_t, exit_t, direction)

        # M1 slice: ±100 bars around entry
        m1_loc = m1.index.searchsorted(entry_t)
        m1_start = max(0, m1_loc - 100)
        m1_end = min(len(m1), m1_loc + 100)
        m1_slice = m1.iloc[m1_start:m1_end]

        m1_title = f"M1 | Entry Detail"
        m1_fig = _candle_fig(m1_slice, m1_title, entry_p, exit_p, sl, tp,
                             entry_t, exit_t, direction)

        trade_charts_html += f"""
        <div class="trade-card">
            <div class="trade-header">
                <span class="trade-num">Trade #{idx + 1}</span>
                <span class="badge {'win' if is_win else 'loss'}">{result_text}</span>
                <span class="badge dir">{direction}</span>
                <span class="badge mode">{mode}</span>
                <span class="badge trigger-badge">{trigger}</span>
                <span class="badge exit-badge">{reason}</span>
            </div>
            <div class="trade-stats">
                <div class="stat">
                    <span class="stat-label">Entry</span>
                    <span class="stat-value">{entry_p:.5f}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Exit</span>
                    <span class="stat-value">{exit_p:.5f}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">SL</span>
                    <span class="stat-value" style="color:{SL_COLOR}">{sl:.5f}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">TP</span>
                    <span class="stat-value" style="color:{TP_COLOR}">{tp:.5f}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">RR Target</span>
                    <span class="stat-value">{rr:.2f}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">PnL</span>
                    <span class="stat-value" style="color:{pnl_color}">${pnl:+,.2f}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Time</span>
                    <span class="stat-value">{entry_t.strftime('%Y-%m-%d %H:%M')} &rarr; {exit_t.strftime('%H:%M')}</span>
                </div>
            </div>
            <div class="chart-grid-4">
                <div class="chart-cell">{d1_fig.to_html(full_html=False, include_plotlyjs=False)}</div>
                <div class="chart-cell">{h4_fig.to_html(full_html=False, include_plotlyjs=False)}</div>
                <div class="chart-cell">{m5_fig.to_html(full_html=False, include_plotlyjs=False)}</div>
                <div class="chart-cell">{m1_fig.to_html(full_html=False, include_plotlyjs=False)}</div>
            </div>
        </div>
        """

    # ---- Summary stats ----
    stats_html = f"""
    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-title">Total Trades</div>
            <div class="stat-big">{metrics['total_trades']}</div>
        </div>
        <div class="stat-card">
            <div class="stat-title">Win Rate</div>
            <div class="stat-big">{metrics['win_rate']}%</div>
        </div>
        <div class="stat-card">
            <div class="stat-title">Profit Factor</div>
            <div class="stat-big">{metrics['profit_factor']}</div>
        </div>
        <div class="stat-card">
            <div class="stat-title">Net PnL</div>
            <div class="stat-big" style="color:{GREEN if metrics['net_pnl']>0 else RED}">${metrics['net_pnl']:+,.2f}</div>
        </div>
        <div class="stat-card">
            <div class="stat-title">Sharpe Ratio</div>
            <div class="stat-big">{metrics['sharpe']}</div>
        </div>
        <div class="stat-card">
            <div class="stat-title">Max Drawdown</div>
            <div class="stat-big" style="color:{RED}">{metrics['max_drawdown_pct']}%</div>
        </div>
        <div class="stat-card">
            <div class="stat-title">Avg Win</div>
            <div class="stat-big" style="color:{GREEN}">${metrics['avg_win']:,.2f}</div>
        </div>
        <div class="stat-card">
            <div class="stat-title">Avg Loss</div>
            <div class="stat-big" style="color:{RED}">${metrics['avg_loss']:,.2f}</div>
        </div>
        <div class="stat-card">
            <div class="stat-title">Avg RR</div>
            <div class="stat-big">{metrics['avg_rr_achieved']}</div>
        </div>
        <div class="stat-card">
            <div class="stat-title">Recovery Factor</div>
            <div class="stat-big">{metrics['recovery_factor']}</div>
        </div>
        <div class="stat-card">
            <div class="stat-title">Long / Short</div>
            <div class="stat-big">{metrics['long_trades']} / {metrics['short_trades']}</div>
        </div>
        <div class="stat-card">
            <div class="stat-title">Max Streak W/L</div>
            <div class="stat-big">{metrics['max_win_streak']} / {metrics['max_loss_streak']}</div>
        </div>
    </div>
    """

    # Entry mode & exit reason breakdown
    mode_rows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in metrics.get("entry_modes", {}).items())
    exit_rows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in metrics.get("exit_reasons", {}).items())

    breakdown_html = f"""
    <div class="breakdown-row">
        <div class="breakdown-table">
            <h3>Entry Modes</h3>
            <table><thead><tr><th>Mode</th><th>Count</th></tr></thead>
            <tbody>{mode_rows}</tbody></table>
        </div>
        <div class="breakdown-table">
            <h3>Exit Reasons</h3>
            <table><thead><tr><th>Reason</th><th>Count</th></tr></thead>
            <tbody>{exit_rows}</tbody></table>
        </div>
    </div>
    """

    # ---- Full HTML ----
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SMC MTF Strategy Report &mdash; {cfg.symbol}</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: {BG};
    color: {TEXT};
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    padding: 24px;
  }}
  h1 {{ font-size: 22px; margin-bottom: 4px; color: {CYAN}; }}
  h2 {{ font-size: 17px; margin: 28px 0 12px; color: {TEXT}; border-bottom: 1px solid {GRAY}; padding-bottom: 6px; }}
  h3 {{ font-size: 14px; margin-bottom: 8px; color: {CYAN}; }}
  .subtitle {{ font-size: 13px; color: #888; margin-bottom: 20px; }}
  .stats-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 10px;
    margin-bottom: 20px;
  }}
  .stat-card {{
    background: {CARD_BG};
    border-radius: 8px;
    padding: 14px;
    text-align: center;
  }}
  .stat-title {{ font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: 0.5px; }}
  .stat-big {{ font-size: 20px; font-weight: 700; margin-top: 4px; }}
  .breakdown-row {{
    display: flex;
    gap: 20px;
    margin-bottom: 20px;
  }}
  .breakdown-table {{
    background: {CARD_BG};
    border-radius: 8px;
    padding: 14px;
    flex: 1;
  }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ padding: 6px 10px; text-align: left; }}
  th {{ color: #888; border-bottom: 1px solid {GRAY}; }}
  td {{ border-bottom: 1px solid #222; }}
  .equity-section {{
    background: {CARD_BG};
    border-radius: 8px;
    padding: 12px;
    margin-bottom: 20px;
  }}
  .trade-card {{
    background: {CARD_BG};
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 16px;
  }}
  .trade-header {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 10px;
    flex-wrap: wrap;
  }}
  .trade-num {{ font-weight: 700; font-size: 15px; }}
  .badge {{
    font-size: 11px;
    padding: 3px 8px;
    border-radius: 4px;
    font-weight: 600;
    text-transform: uppercase;
  }}
  .badge.win {{ background: rgba(0,200,83,0.2); color: {GREEN}; }}
  .badge.loss {{ background: rgba(255,23,68,0.2); color: {RED}; }}
  .badge.dir {{ background: rgba(68,138,255,0.2); color: {ENTRY_COLOR}; }}
  .badge.mode {{ background: rgba(255,145,0,0.2); color: {ORANGE}; }}
  .badge.trigger-badge {{ background: rgba(255,214,0,0.15); color: {YELLOW}; }}
  .badge.exit-badge {{ background: rgba(120,120,120,0.2); color: #aaa; }}
  .trade-stats {{
    display: flex;
    gap: 18px;
    margin-bottom: 10px;
    flex-wrap: wrap;
  }}
  .stat {{ display: flex; flex-direction: column; }}
  .stat-label {{ font-size: 10px; color: #888; text-transform: uppercase; }}
  .stat-value {{ font-size: 13px; font-weight: 600; }}
  .chart-grid-4 {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }}
  .chart-cell {{ min-width: 0; }}
  @media (max-width: 900px) {{
    .chart-grid-4 {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
  <h1>SMC Multi-Timeframe Strategy Report</h1>
  <div class="subtitle">{cfg.symbol} | M1 bars: {len(m1):,} | {m1.index[0].strftime('%Y-%m-%d')} to {m1.index[-1].strftime('%Y-%m-%d')}</div>

  <h2>Performance Summary</h2>
  {stats_html}
  {breakdown_html}

  <h2>Equity Curve</h2>
  <div class="equity-section">
    {eq_fig.to_html(full_html=False, include_plotlyjs=False)}
  </div>

  <h2>Trade Details ({metrics['total_trades']} trades)</h2>
  {trade_charts_html}

</body>
</html>"""

    return html


def save_report(html: str, path: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Report saved to {path}")
