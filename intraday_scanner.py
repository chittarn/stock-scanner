#!/usr/bin/env python3
"""
INTRADAY MOMENTUM SCANNER – US Market | $50 Capital
=====================================================
Strategy: VWAP + 9EMA Breakout with Volume Surge Filter
- Universe: Low-priced high-liquidity US stocks (<$20 or fractional-friendly ETFs)
- Signals: VWAP cross, 9EMA trend, Volume surge, RSI momentum, Gap-up detection
- Position Sizing: Risk-based for exactly $50 starting capital
- Risk: 1R = $1.50 max loss per trade (3% of $50)
- Target: 2:1 or 3:1 Risk-Reward

Usage:
    python intraday_scanner.py
    python intraday_scanner.py --capital 50 --risk 3.0
    python intraday_scanner.py --watch          # Continuous mode, refreshes every 5 min
"""

import sys
import io
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import argparse
import time
import warnings
import os

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich import print as rprint
from rich.live import Live
from rich.layout import Layout

warnings.filterwarnings('ignore')

# -- Windows UTF-8 Fix --
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ─────────────────────────────────────────────
#  UNIVERSE – Stocks priced well for $50 capital
#  (fractional shares not assumed – keep price low)
# ─────────────────────────────────────────────
UNIVERSE = {
    # High-beta tech / meme / growth (volatile, good for intraday)
    "SOFI": "Fintech",
    "PLTR": "AI/Defense",
    "RIVN": "EV",
    "NIO":  "EV China",
    "PLUG": "Hydrogen",
    "F":    "Auto",
    "SNAP": "Social Media",
    "BBAI": "AI Small-cap",
    "IONQ": "Quantum",
    "SOUN": "AI Voice",
    "HIMS": "Telehealth",
    "TLRY": "Cannabis",
    "HOOD": "Fintech",
    "MARA": "Crypto Mining",
    "RIOT": "Crypto Mining",
    "OPEN": "PropTech",
    "CLOV": "Healthtech",
    "AMC":  "Entertainment",
    "BB":   "Legacy Tech",
    "GRAB": "SE Asia Tech",
    # Leveraged ETFs (high movement per dollar)
    "SOXS": "3x Short Semi",
    "TQQQ": "3x Long QQQ",
    "SQQQ": "3x Short QQQ",
    "UVXY": "VIX 1.5x",
    "SPXS": "3x Short SPX",
    "LABU": "3x Long BioTech",
}

# Strategy Parameters
RSI_PERIOD = 14
EMA_FAST = 9
EMA_SLOW = 21
VOL_MA_PERIOD = 20
ATR_PERIOD = 14
MIN_VOLUME = 500_000         # Min average daily volume
MIN_PRICE = 0.50             # Filter penny stocks
MAX_PRICE = 50.0             # Keep affordable for $50 capital
RSI_MIN = 45                 # Not oversold
RSI_MAX = 78                 # Not overbought
VOL_SURGE_MIN = 1.5          # Volume must be 1.5x average
MIN_RISK_REWARD = 1.8        # Minimum R:R ratio


def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calc_vwap(high, low, close, volume):
    """Calculate VWAP from OHLCV data."""
    typical = (high + low + close) / 3
    vwap = (typical * volume).cumsum() / volume.cumsum()
    return vwap


def calc_atr(high, low, close, period=14):
    h_l = high - low
    h_pc = (high - close.shift(1)).abs()
    l_pc = (low - close.shift(1)).abs()
    tr = pd.concat([h_l, h_pc, l_pc], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def get_signal_strength(row):
    """Return 0-100 signal strength score."""
    score = 0
    # VWAP position (25 pts)
    if row['above_vwap']:
        score += 25
    # EMA9 trend (20 pts)
    if row['above_ema9']:
        score += 20
    # Volume surge (25 pts)
    surge = row['vol_ratio']
    if surge >= 3.0:
        score += 25
    elif surge >= 2.0:
        score += 18
    elif surge >= 1.5:
        score += 10
    # RSI zone (15 pts)
    rsi = row['rsi']
    if 55 <= rsi <= 70:
        score += 15
    elif 48 <= rsi < 55:
        score += 8
    elif rsi > 70:
        score += 5  # Overbought, less ideal
    # Gap up (15 pts)
    if row['gap_pct'] > 2.0:
        score += 15
    elif row['gap_pct'] > 0.5:
        score += 8
    return score


def fetch_intraday_data(tickers, interval='5m', period='1d'):
    """Fetch 5-minute intraday data for all tickers."""
    results = {}
    for ticker in tickers:
        try:
            data = yf.download(ticker, period=period, interval=interval,
                               auto_adjust=True, progress=False)
            if data is not None and len(data) >= 10:
                results[ticker] = data
        except Exception:
            pass
    return results


def fetch_daily_data(tickers, period='30d'):
    """Fetch daily data for baseline calculations."""
    try:
        data = yf.download(tickers, period=period, auto_adjust=True, progress=False)
        return data
    except Exception:
        return None


def analyze_ticker(ticker, intraday_df, daily_close, daily_volume, sector, capital=50.0, risk_pct=3.0):
    """
    Analyze a single ticker and return signal data or None.
    """
    if intraday_df is None or len(intraday_df) < 10:
        return None

    try:
        close = intraday_df['Close'].squeeze()
        high = intraday_df['High'].squeeze()
        low = intraday_df['Low'].squeeze()
        volume = intraday_df['Volume'].squeeze()

        curr_price = float(close.iloc[-1])
        curr_vol = float(volume.iloc[-1])

        # Price filter
        if curr_price < MIN_PRICE or curr_price > MAX_PRICE:
            return None

        # Daily volume check
        if daily_volume is not None and float(daily_volume) < MIN_VOLUME:
            return None

        # EMA calculations
        ema9 = close.ewm(span=EMA_FAST, adjust=False).mean()
        ema21 = close.ewm(span=EMA_SLOW, adjust=False).mean()

        # VWAP (resets each day by default on 5min data)
        vwap = calc_vwap(high, low, close, volume)

        # RSI
        rsi = calc_rsi(close, RSI_PERIOD)
        curr_rsi = float(rsi.iloc[-1])

        # ATR (intraday)
        atr = calc_atr(high, low, close, ATR_PERIOD)
        curr_atr = float(atr.iloc[-1])

        # Average volume (from daily data or intraday estimate)
        avg_vol_intraday = float(volume.rolling(20).mean().iloc[-1]) if len(volume) >= 20 else float(volume.mean())
        if avg_vol_intraday == 0:
            return None
        vol_ratio = curr_vol / avg_vol_intraday if avg_vol_intraday > 0 else 1.0

        # Gap from yesterday's close
        gap_pct = 0.0
        if daily_close is not None and len(daily_close) >= 2:
            prev_close = float(daily_close.iloc[-2])
            if prev_close > 0:
                today_open = float(intraday_df['Open'].iloc[0].squeeze())
                gap_pct = (today_open / prev_close - 1) * 100

        # Signal flags
        curr_vwap = float(vwap.iloc[-1])
        curr_ema9 = float(ema9.iloc[-1])
        curr_ema21 = float(ema21.iloc[-1])
        above_vwap = curr_price > curr_vwap
        above_ema9 = curr_price > curr_ema9
        ema_trending = curr_ema9 > curr_ema21

        # RSI filter
        if curr_rsi < RSI_MIN or curr_rsi > RSI_MAX:
            return None

        # Volume surge filter
        if vol_ratio < VOL_SURGE_MIN:
            return None

        # ── Position Sizing for $50 ──────────────────────────────
        max_risk_dollars = capital * (risk_pct / 100)  # e.g., $1.50 at 3%
        stop_distance = curr_atr * 1.5               # ATR-based stop
        if stop_distance <= 0:
            stop_distance = curr_price * 0.02        # Fallback: 2% stop

        stop_price = curr_price - stop_distance
        target_1r = curr_price + stop_distance         # 1:1 R:R
        target_2r = curr_price + (stop_distance * 2)   # 2:1 R:R
        target_3r = curr_price + (stop_distance * 3)   # 3:1 R:R

        # Max shares we can buy with full $50, but risk-limited
        shares_by_risk = max_risk_dollars / stop_distance
        shares_by_capital = capital / curr_price
        shares = min(shares_by_risk, shares_by_capital)
        shares = max(1, int(shares))  # At least 1 share (whole shares only for simplicity)

        actual_cost = shares * curr_price
        if actual_cost > capital:
            shares = max(1, int(capital / curr_price))
            actual_cost = shares * curr_price

        actual_risk = shares * stop_distance
        rr_ratio = stop_distance / stop_distance * 2  # 2:1 target

        row = {
            'ticker': ticker,
            'sector': sector,
            'price': curr_price,
            'vwap': curr_vwap,
            'ema9': curr_ema9,
            'ema21': curr_ema21,
            'rsi': curr_rsi,
            'atr': curr_atr,
            'vol_ratio': vol_ratio,
            'gap_pct': gap_pct,
            'above_vwap': above_vwap,
            'above_ema9': above_ema9,
            'ema_trending': ema_trending,
            'stop': stop_price,
            'target_2r': target_2r,
            'target_3r': target_3r,
            'shares': shares,
            'cost': actual_cost,
            'risk_dollars': actual_risk,
        }
        row['signal_score'] = get_signal_strength(row)
        return row

    except Exception as e:
        return None


def print_header(console, capital, risk_pct):
    now = datetime.now()
    header = Panel.fit(
        f"[bold cyan]** INTRADAY MOMENTUM SCANNER **[/bold cyan]  [dim]US Market[/dim]\n"
        f"[white]Capital: [bold green]${capital:.2f}[/bold green]   "
        f"Risk/Trade: [bold yellow]{risk_pct}%[/bold yellow] (${capital * risk_pct / 100:.2f})   "
        f"Time: [dim]{now.strftime('%Y-%m-%d %H:%M:%S')} IST[/dim]",
        border_style="cyan",
        title="[bold]INTRADAY SCANNER v1.0[/bold]"
    )
    console.print(header)


def print_market_overview(console, spy_data, qqq_data, vix_data):
    """Print a quick market overview."""
    table = Table(title="Market Overview", box=None, show_header=True, header_style="bold magenta")
    table.add_column("Index", style="cyan", width=8)
    table.add_column("Price", justify="right", width=10)
    table.add_column("Change", justify="right", width=10)
    table.add_column("Trend", justify="center", width=10)

    for name, data in [("SPY", spy_data), ("QQQ", qqq_data), ("VIX", vix_data)]:
        if data is None or len(data) < 2:
            table.add_row(name, "N/A", "N/A", "—")
            continue
        try:
            close = data['Close'].squeeze()
            curr = float(close.iloc[-1])
            prev = float(close.iloc[-2])
            chg = (curr / prev - 1) * 100
            color = "green" if chg >= 0 else "red"
            arrow = "▲" if chg >= 0 else "▼"
            trend = "BULLISH" if chg > 0.3 else "BEARISH" if chg < -0.3 else "NEUTRAL"
            table.add_row(name, f"${curr:.2f}", f"[{color}]{arrow}{abs(chg):.2f}%[/{color}]", trend)
        except Exception:
            table.add_row(name, "ERR", "ERR", "—")

    console.print(table)


def print_signals(console, signals, capital, risk_pct):
    if not signals:
        console.print("[bold red]No qualifying signals found at this time.[/bold red]")
        console.print("[dim]Criteria: RSI 45-78, Volume >=1.5x avg, Price $0.50-$50[/dim]")
        return

    signals.sort(key=lambda x: x['signal_score'], reverse=True)

    table = Table(
        title=f"Intraday Signals -- Top {len(signals)} Candidates",
        show_header=True,
        header_style="bold cyan",
        border_style="cyan"
    )
    table.add_column("#", justify="center", width=3)
    table.add_column("Ticker", style="bold white", width=6)
    table.add_column("Sector", style="dim", width=14)
    table.add_column("Price", justify="right", width=7)
    table.add_column("VWAP", justify="right", width=7)
    table.add_column("RSI", justify="right", width=5)
    table.add_column("Vol×", justify="right", width=5)
    table.add_column("Gap%", justify="right", width=6)
    table.add_column("Stop", justify="right", width=7)
    table.add_column("T2R", justify="right", width=7)
    table.add_column("T3R", justify="right", width=7)
    table.add_column("Shares", justify="right", width=6)
    table.add_column("Cost$", justify="right", width=7)
    table.add_column("Risk$", justify="right", width=6)
    table.add_column("Score", justify="right", width=6)
    table.add_column("Setup", justify="center", width=20)

    for i, s in enumerate(signals, 1):
        score = s['signal_score']
        score_color = "bold green" if score >= 70 else "yellow" if score >= 50 else "dim"

        gap_str = f"+{s['gap_pct']:.1f}%" if s['gap_pct'] > 0 else f"{s['gap_pct']:.1f}%"
        gap_color = "green" if s['gap_pct'] > 1 else "red" if s['gap_pct'] < -1 else "white"

        # Setup descriptor
        setup_parts = []
        if s['above_vwap']:
            setup_parts.append("[green]VWAP+[/green]")
        if s['above_ema9']:
            setup_parts.append("[cyan]EMA+[/cyan]")
        if s['ema_trending']:
            setup_parts.append("[blue]TREND[/blue]")
        if s['vol_ratio'] >= 2.5:
            setup_parts.append("[magenta]VOL![/magenta]")
        if s['gap_pct'] > 2:
            setup_parts.append("[yellow]GAP+[/yellow]")
        setup_str = " ".join(setup_parts) if setup_parts else "[dim]--[/dim]"

        row_style = "bold" if i <= 3 else ""

        table.add_row(
            str(i),
            s['ticker'],
            s['sector'],
            f"${s['price']:.2f}",
            f"${s['vwap']:.2f}",
            f"{s['rsi']:.0f}",
            f"{s['vol_ratio']:.1f}x",
            f"[{gap_color}]{gap_str}[/{gap_color}]",
            f"[red]${s['stop']:.2f}[/red]",
            f"[green]${s['target_2r']:.2f}[/green]",
            f"[bold green]${s['target_3r']:.2f}[/bold green]",
            str(s['shares']),
            f"${s['cost']:.2f}",
            f"[yellow]${s['risk_dollars']:.2f}[/yellow]",
            f"[{score_color}]{score}[/{score_color}]",
            setup_str,
            style=row_style
        )

    console.print(table)

    # Print top pick detail
    if signals:
        top = signals[0]
        detail = Panel(
            f"[bold cyan]TOP PICK: {top['ticker']}[/bold cyan]  [{top['sector']}]\n\n"
            f"  Entry:     [white]${top['price']:.2f}[/white]   (current market price)\n"
            f"  Stop Loss: [bold red]${top['stop']:.2f}[/bold red]   "
            f"(-${top['price'] - top['stop']:.2f} / ATR-based)\n"
            f"  Target 2R: [green]${top['target_2r']:.2f}[/green]   "
            f"(+${top['target_2r'] - top['price']:.2f})\n"
            f"  Target 3R: [bold green]${top['target_3r']:.2f}[/bold green]   "
            f"(+${top['target_3r'] - top['price']:.2f})\n\n"
            f"  Shares:  [white]{top['shares']}[/white]   "
            f"Cost: [white]${top['cost']:.2f}[/white]   "
            f"Max Loss: [red]${top['risk_dollars']:.2f}[/red]\n"
            f"  RSI: {top['rsi']:.0f}   Vol: {top['vol_ratio']:.1f}x   "
            f"Gap: {top['gap_pct']:+.2f}%   Score: {top['signal_score']}/100",
            title="[bold]Best Setup[/bold]",
            border_style="green"
        )
        console.print(detail)

    # Risk summary
    console.print(
        f"\n[dim]Capital: ${capital:.2f} | Risk per trade: ${capital * risk_pct / 100:.2f} "
        f"({risk_pct}%) | Signals found: {len(signals)}"
        f" | {datetime.now().strftime('%H:%M:%S')}[/dim]"
    )


def run_scanner(capital=50.0, risk_pct=3.0, watch=False, interval_minutes=5):
    console = Console(force_terminal=True, highlight=False)

    while True:
        console.clear()
        print_header(console, capital, risk_pct)

        tickers = list(UNIVERSE.keys())
        all_tickers = tickers + ['SPY', 'QQQ', '^VIX']

        with console.status("[bold green]📡 Fetching market data..."):
            # Fetch market overview data
            try:
                spy_d = yf.download('SPY', period='1d', interval='5m', progress=False, auto_adjust=True)
                qqq_d = yf.download('QQQ', period='1d', interval='5m', progress=False, auto_adjust=True)
                vix_d = yf.download('^VIX', period='1d', interval='5m', progress=False, auto_adjust=True)
            except Exception:
                spy_d = qqq_d = vix_d = None

            print_market_overview(console, spy_d, qqq_d, vix_d)
            console.print()

            # Fetch daily data for gap & volume calculations
            try:
                daily_data = yf.download(tickers, period='25d', auto_adjust=True, progress=False)
                daily_close = daily_data['Close'] if 'Close' in daily_data else None
                daily_volume = daily_data['Volume'].mean() if 'Volume' in daily_data else None
            except Exception:
                daily_close = None
                daily_volume = None

            # Fetch intraday data
            console.print(f"[dim]Scanning {len(tickers)} tickers for intraday signals...[/dim]")
            intraday_data = fetch_intraday_data(tickers, interval='5m', period='1d')

        # Analyze each ticker
        signals = []
        with console.status("[bold cyan]🔍 Analyzing signals..."):
            for ticker, sector in UNIVERSE.items():
                intra_df = intraday_data.get(ticker)
                d_close = daily_close[ticker] if daily_close is not None and ticker in daily_close.columns else None
                d_vol = daily_volume[ticker] if daily_volume is not None and ticker in daily_volume.index else None

                result = analyze_ticker(
                    ticker, intra_df, d_close, d_vol, sector,
                    capital=capital, risk_pct=risk_pct
                )
                if result:
                    signals.append(result)

        print_signals(console, signals, capital, risk_pct)

        if not watch:
            break

        console.print(f"\n[dim]⏱ Next scan in {interval_minutes} minutes... (Ctrl+C to stop)[/dim]")
        try:
            time.sleep(interval_minutes * 60)
        except KeyboardInterrupt:
            console.print("\n[bold yellow]Scanner stopped.[/bold yellow]")
            break


def main():
    parser = argparse.ArgumentParser(
        description="Intraday Momentum Scanner for US Market | $50 Capital"
    )
    parser.add_argument('--capital', type=float, default=50.0,
                        help='Trading capital in USD (default: 50)')
    parser.add_argument('--risk', type=float, default=3.0,
                        help='Risk per trade as %% of capital (default: 3.0)')
    parser.add_argument('--watch', action='store_true',
                        help='Continuous mode – refreshes every 5 minutes')
    parser.add_argument('--interval', type=int, default=5,
                        help='Refresh interval in minutes for watch mode (default: 5)')
    args = parser.parse_args()

    run_scanner(
        capital=args.capital,
        risk_pct=args.risk,
        watch=args.watch,
        interval_minutes=args.interval
    )


if __name__ == "__main__":
    main()
