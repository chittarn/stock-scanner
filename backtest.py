#!/usr/bin/env python3
"""
Backtest script for the Adaptive Momentum Scanner.
It runs the strategy over a rolling historical window (default 2 years) and
produces basic performance metrics:
- CAGR
- Total return
- Max drawdown
- Win rate (fraction of weeks where the action plan improves equity)
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scanner_engine import ScannerEngine


def compute_metrics(equity_series: pd.Series):
    """Calculate simple back‑test metrics from an equity time series.
    equity_series must be indexed by date (daily) and be strictly increasing in time.
    Returns a dict with total_return, cagr, max_dd, win_rate.
    """
    equity = equity_series.dropna()
    # Ensure the index is datetime and sorted (important for correct time calculations)
    equity.index = pd.to_datetime(equity.index)
    equity = equity.sort_index()
    if equity.empty:
        return {}
    total_return = equity.iloc[-1] / equity.iloc[0] - 1.0
    # Use precise day count and guard against very small year spans
    days = (equity.index[-1] - equity.index[0]).days
    years = days / 365.25 if days > 0 else 0.0
    if years > 0:
        cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years) - 1
    else:
        cagr = 0.0
    # Max drawdown
    roll_max = equity.cummax()
    drawdown = (equity - roll_max) / roll_max
    max_dd = drawdown.min()
    # Win rate – count weeks where equity increased compared to previous week
    # Ensure resampling operates on a DatetimeIndex
    weekly = equity.resample('W').last()
    weekly_returns = weekly.pct_change().fillna(0)
    win_rate = (weekly_returns > 0).mean()
    return {
        "total_return": total_return,
        "cagr": cagr,
        "max_drawdown": max_dd,
        "win_rate": win_rate,
    }


def backtest(start_date: str = None, end_date: str = None, starting_capital: float = 10000.0, freq: str = 'W'):
    """Run the adaptive momentum strategy over a rolling window.
    For each period we:
    1. Pull price data up to the *end* of the window.
    2. Run the scanner engine to get the action plan.
    3. Apply the suggested BUY/SELL orders to a virtual portfolio.
    4. Record portfolio total value.
    """
    engine = ScannerEngine()
    # Pull a full year of data once – the engine will internally request the last year.
    # We'll reuse the same data for each step by trimming the end date.
    # Extend the engine to accept a custom end date (optional), but for simplicity we
    # re‑instantiate the engine each iteration which fetches fresh data up to today.

    # Build a date range for the back‑test
    # Determine date range
    if end_date is None:
        end_dt = datetime.now(engine.ist).date()
    else:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    if start_date is None:
        # Default to 2 years back if not provided
        start_dt = end_dt - timedelta(days=2 * 365)
    else:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    # We'll step forward week by week
    dates = pd.date_range(start=start_dt, end=end_dt, freq=freq)

    cash = starting_capital  # Use provided starting capital
    holdings = {}
    equity_curve = []

    # Prepare logging of weekly trades
    weekly_logs = []
    for current_end in dates:
        # Temporarily set the engine's internal "now" to the back‑test date so that
        # any time‑sensitive logic (e.g., moving‑average windows) uses the correct horizon.
        engine.now = datetime.combine(current_end, datetime.min.time()).replace(tzinfo=engine.ist)
        # Run the analysis for the current point in time, providing the back‑test date as the market horizon
        data = engine.get_analysis(end_date=current_end.date())
        # Apply SELL / EXIT / STOP orders first (cash out)
        for s in data.get('to_sell', []):
            ticker = s['ticker']
            if ticker in holdings:
                cash += holdings[ticker]['qty'] * data['prices'][ticker].iloc[-1]
                del holdings[ticker]
        # Apply BUY orders (add or new)
        for b in data.get('buy_orders', []):
            ticker = b['ticker']
            price = b['price'] if b['price'] > 0 else data['prices'][ticker].iloc[-1]
            shares = b['shares']
            cost = shares * price
            if cash >= cost:
                cash -= cost
                holdings[ticker] = holdings.get(ticker, {'qty': 0.0, 'avg_cost': 0.0})
                # Update average cost – simple weighted average
                prev = holdings[ticker]
                total_qty = prev['qty'] + shares
                new_avg = (prev['qty'] * prev['avg_cost'] + shares * price) / total_qty if total_qty > 0 else price
                holdings[ticker] = {'qty': total_qty, 'avg_cost': new_avg}
        # Compute portfolio value at the end of the week
        total_value = cash
        for t, h in holdings.items():
            # Use the latest available price from the engine's price matrix
            if t in data['prices']:
                cur_price = data['prices'][t].iloc[-1]
            else:
                cur_price = h['avg_cost']
            total_value += h['qty'] * cur_price
        equity_curve.append((current_end, total_value))
        # Log weekly trade counts
        weekly_logs.append({
            "date": current_end.strftime("%Y-%m-%d"),
            "buys": len(data.get('buy_orders', [])),
            "sells": len(data.get('to_sell', []))
        })

    # Build a pandas Series for metrics
    equity_series = pd.Series({d: v for d, v in equity_curve})
    metrics = compute_metrics(equity_series)
    # Summarize trade activity
    total_buys = sum(log['buys'] for log in weekly_logs)
    total_sells = sum(log['sells'] for log in weekly_logs)
    print(f"Total BUY orders executed: {total_buys}")
    print(f"Total SELL orders executed: {total_sells}")
    print("Backtest Results (custom date range, weekly stepping):")
    print(f"  Total Return: {metrics['total_return']*100:.2f}%")
    print(f"  CAGR: {metrics['cagr']*100:.2f}%")
    print(f"  Max Drawdown: {metrics['max_drawdown']*100:.2f}%")
    print(f"  Weekly Win Rate: {metrics['win_rate']*100:.2f}%")
    # Optionally save to JSON for later analysis
    try:
        import json, os
        out_path = os.path.join(os.path.dirname(__file__), "backtest_results.json")
        with open(out_path, "w") as f:
            json.dump(metrics, f, indent=4)
        print(f"Metrics saved to {out_path}")
    except Exception:
        pass
    # Save weekly trade logs
    out_path_logs = os.path.join(os.path.dirname(__file__), "weekly_trade_logs.json")
    with open(out_path_logs, "w") as f:
        json.dump(weekly_logs, f, indent=4)
    print(f"Weekly trade logs saved to {out_path_logs}")

if __name__ == "__main__":
    backtest(start_date="2026-01-01", starting_capital=300.0)
