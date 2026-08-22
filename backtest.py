"""Backtest engine — equity curve, metrics, and reporting."""

import numpy as np
import pandas as pd


def compute_metrics(trades: pd.DataFrame, initial_capital: float,
                    cfg=None) -> dict:
    """
    Compute strategy performance metrics from the trade log.

    Costs come from the trade log itself: the strategy books the instrument's
    round-turn commission and assumed slippage per contract on every trade
    (futures commission is real — roughly $1.20 round turn on a micro and
    $4.20 on a full-size E-mini — it is just tiny next to the notional).
    Older logs without those columns fall back to `cfg`, then to zero.
    """
    if trades.empty:
        return {"total_trades": 0, "net_pnl": 0.0, "win_rate": 0.0}

    gross = trades["pnl"].values.astype(float)

    if "commission" in trades.columns:
        commissions = trades["commission"].values.astype(float)
    elif cfg is not None:
        commissions = cfg.commission_per_contract * trades["qty"].values.astype(float)
    else:
        commissions = np.zeros(len(gross))

    if "slippage" in trades.columns:
        slippage = trades["slippage"].values.astype(float)
    else:
        slippage = np.zeros(len(gross))

    pnl = gross - commissions - slippage

    wins = pnl[pnl > 0]
    losses = pnl[pnl <= 0]
    total = len(pnl)
    n_wins = len(wins)
    n_losses = len(losses)

    net_pnl = pnl.sum()
    win_rate = n_wins / total * 100 if total > 0 else 0.0
    gross_profit = wins.sum() if n_wins > 0 else 0.0
    gross_loss = abs(losses.sum()) if n_losses > 0 else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    avg_win = wins.mean() if n_wins > 0 else 0.0
    avg_loss = abs(losses.mean()) if n_losses > 0 else 0.0
    avg_rr = avg_win / avg_loss if avg_loss > 0 else float("inf")

    # Equity curve
    equity = initial_capital + np.cumsum(pnl)
    peak = np.maximum.accumulate(equity)
    drawdown = (peak - equity) / peak * 100
    max_dd = drawdown.max()

    # Sharpe (daily approximation: annualize from avg trade)
    if len(pnl) > 1 and pnl.std() > 0:
        sharpe = (pnl.mean() / pnl.std()) * np.sqrt(252)
    else:
        sharpe = 0.0

    # Consecutive stats
    streak_w = streak_l = max_streak_w = max_streak_l = 0
    for p in pnl:
        if p > 0:
            streak_w += 1
            streak_l = 0
            max_streak_w = max(max_streak_w, streak_w)
        else:
            streak_l += 1
            streak_w = 0
            max_streak_l = max(max_streak_l, streak_l)

    recovery_factor = net_pnl / (max_dd / 100 * initial_capital) if max_dd > 0 else float("inf")

    # Breakdown by exit reason
    exit_counts = trades["exit_reason"].value_counts().to_dict()

    # Breakdown by entry mode
    mode_counts = trades["entry_mode"].value_counts().to_dict() if "entry_mode" in trades.columns else {}

    # Breakdown by direction
    if "direction" in trades.columns:
        longs = trades[trades["direction"] == "LONG"]
        shorts = trades[trades["direction"] == "SHORT"]
    else:
        longs = shorts = pd.DataFrame()

    return {
        "total_trades": total,
        "wins": n_wins,
        "losses": n_losses,
        "win_rate": round(win_rate, 2),
        "net_pnl": round(net_pnl, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": round(profit_factor, 3),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "avg_rr_achieved": round(avg_rr, 2),
        "sharpe": round(sharpe, 3),
        "max_drawdown_pct": round(max_dd, 2),
        "recovery_factor": round(recovery_factor, 3),
        "max_win_streak": max_streak_w,
        "max_loss_streak": max_streak_l,
        "gross_pnl_before_costs": round(gross.sum(), 2),
        "total_commissions": round(commissions.sum(), 2),
        "total_slippage": round(slippage.sum(), 2),
        "total_contracts": round(float(trades["qty"].sum()), 2) if "qty" in trades.columns else 0.0,
        "avg_contracts": round(float(trades["qty"].mean()), 2) if "qty" in trades.columns else 0.0,
        "exit_reasons": exit_counts,
        "entry_modes": mode_counts,
        "long_trades": len(longs),
        "short_trades": len(shorts),
        "long_pnl": round(longs["pnl"].sum(), 2) if not longs.empty else 0.0,
        "short_pnl": round(shorts["pnl"].sum(), 2) if not shorts.empty else 0.0,
        "equity_curve": equity,
        "drawdown_curve": drawdown,
    }


def print_report(metrics: dict, trades: pd.DataFrame):
    """Print formatted backtest report."""
    print("\n" + "=" * 60)
    print("  SMC MULTI-TIMEFRAME STRATEGY — BACKTEST REPORT")
    print("=" * 60)

    print(f"\n  Total Trades:     {metrics['total_trades']}")
    print(f"  Wins / Losses:    {metrics['wins']} / {metrics['losses']}")
    print(f"  Win Rate:         {metrics['win_rate']}%")
    print(f"  Net PnL:          ${metrics['net_pnl']:,.2f}")
    print(f"  Gross Profit:     ${metrics['gross_profit']:,.2f}")
    print(f"  Gross Loss:       ${metrics['gross_loss']:,.2f}")
    print(f"  Profit Factor:    {metrics['profit_factor']}")
    print(f"  Avg Win:          ${metrics['avg_win']:,.2f}")
    print(f"  Avg Loss:         ${metrics['avg_loss']:,.2f}")
    print(f"  Avg RR Achieved:  {metrics['avg_rr_achieved']}")
    print(f"  Sharpe Ratio:     {metrics['sharpe']}")
    print(f"  Max Drawdown:     {metrics['max_drawdown_pct']}%")
    print(f"  Recovery Factor:  {metrics['recovery_factor']}")
    print(f"  Max Win Streak:   {metrics['max_win_streak']}")
    print(f"  Max Loss Streak:  {metrics['max_loss_streak']}")
    print(f"  Gross (pre-cost): ${metrics['gross_pnl_before_costs']:,.2f}")
    print(f"  Commissions:      ${metrics['total_commissions']:,.2f}")
    print(f"  Slippage:         ${metrics['total_slippage']:,.2f}")
    print(f"  Contracts traded: {metrics['total_contracts']:,.0f} (avg {metrics['avg_contracts']}/trade)")

    print(f"\n  --- Direction ---")
    print(f"  Long:  {metrics['long_trades']} trades, PnL ${metrics['long_pnl']:,.2f}")
    print(f"  Short: {metrics['short_trades']} trades, PnL ${metrics['short_pnl']:,.2f}")

    print(f"\n  --- Entry Mode ---")
    for mode, count in metrics.get("entry_modes", {}).items():
        print(f"  {mode}: {count} trades")

    print(f"\n  --- Exit Reasons ---")
    for reason, count in metrics.get("exit_reasons", {}).items():
        print(f"  {reason}: {count}")

    if not trades.empty:
        print(f"\n  --- Sample Trades (last 10) ---")
        cols = ["entry_time", "exit_time", "direction", "entry_price",
                "exit_price", "sl", "tp", "pnl", "exit_reason",
                "entry_mode", "trigger", "rr"]
        display_cols = [c for c in cols if c in trades.columns]
        print(trades[display_cols].tail(10).to_string(index=False))

    print("\n" + "=" * 60)
