#!/usr/bin/env python3
"""
INTRADAY BACKTEST – US Market | $50 Capital
============================================
Strategy : VWAP + 9 EMA Breakout with Volume Surge Filter
Timeframe: 5-minute bars (yfinance supports ~60 days history)
Universe : Same low-price, high-liquidity tickers as intraday_scanner.py

Entry Rules:
  1. Price crosses ABOVE VWAP from below
  2. Price is above 9 EMA
  3. Volume on signal bar >= 1.5x 20-bar rolling average
  4. RSI between 45 and 75
  5. No overnight holds – all positions closed at market end

Exit Rules:
  A. Target hit  : +2× ATR (2:1 R:R)  → full exit
  B. Stop hit    : -1.5× ATR           → full exit
  C. EOD exit    : last bar of session  → exit at close

Position Sizing ($50 capital):
  - Risk per trade = 3% of capital = $1.50
  - Shares = risk_$ / stop_distance  (whole shares, min 1)
  - Max cost capped at full capital

Usage:
  python intraday_backtest.py
  python intraday_backtest.py --days 30 --capital 50 --risk 3.0
  python intraday_backtest.py --ticker PLTR --days 60
"""

import sys
import io
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import argparse
import warnings

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

warnings.filterwarnings('ignore')

# ── Windows UTF-8 Fix ────────────────────────────────────────
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ── Universe ────────────────────────────────────────────────
UNIVERSE = {
    "SOFI": "Fintech",   "PLTR": "AI/Defense", "RIVN": "EV",
    "NIO":  "EV China",  "PLUG": "Hydrogen",   "F":    "Auto",
    "SNAP": "Social",    "HOOD": "Fintech",     "MARA": "Crypto",
    "RIOT": "Crypto",    "SOUN": "AI Voice",    "HIMS": "Telehealth",
    "TQQQ": "3x QQQ",    "SQQQ": "3x Short",   "UVXY": "VIX ETF",
}

# ── Strategy Parameters ─────────────────────────────────────
EMA_FAST      = 9
RSI_PERIOD    = 14
ATR_PERIOD    = 14
VOL_MA_BARS   = 20
ATR_STOP_MULT = 1.5      # Stop = entry - 1.5 × ATR
ATR_TGT_MULT  = 3.0      # Target = entry + 3.0 × ATR  (2:1 R:R approx)
VOL_SURGE     = 1.2      # Volume surge threshold (relaxed for more signals)
RSI_MIN       = 40
RSI_MAX       = 78
MAX_TRADES_DAY = 3       # Max entries per ticker per day
COMMISSION     = 0.005   # $0.005 per share (Webull/Robinhood style)


# ── Indicator Helpers ───────────────────────────────────────
def calc_rsi(s, period=14):
    d = s.diff()
    gain = d.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calc_vwap(h, l, c, v):
    tp = (h + l + c) / 3
    cumtp_v = (tp * v).cumsum()
    cumv    = v.cumsum()
    return cumtp_v / cumv.replace(0, np.nan)


def calc_atr(h, l, c, period=14):
    hl  = h - l
    hpc = (h - c.shift(1)).abs()
    lpc = (l - c.shift(1)).abs()
    tr  = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


# ── Core Backtest Engine ────────────────────────────────────
class IntradayBacktest:
    def __init__(self, capital=50.0, risk_pct=3.0, days=30):
        self.capital   = capital
        self.risk_pct  = risk_pct
        self.days      = min(days, 59)   # yfinance 5m limit ~60 days
        self.console   = Console(force_terminal=True, highlight=False)
        self.trades    = []
        self.daily_pnl = {}

    # ── Fetch 5-minute data ──────────────────────────────────
    def fetch(self, ticker):
        try:
            df = yf.download(
                ticker,
                period=f"{self.days}d",
                interval="5m",
                auto_adjust=True,
                progress=False
            )
            if df is None or len(df) < 30:
                return None
            # Flatten MultiIndex if present
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df[['Open','High','Low','Close','Volume']].copy()
            df.dropna(inplace=True)
            return df
        except Exception:
            return None

    # ── Simulate one ticker ──────────────────────────────────
    def simulate_ticker(self, ticker, sector):
        df = self.fetch(ticker)
        if df is None:
            return []

        # Add indicators
        df['ema9']    = df['Close'].ewm(span=EMA_FAST, adjust=False).mean()
        df['rsi']     = calc_rsi(df['Close'], RSI_PERIOD)
        df['atr']     = calc_atr(df['High'], df['Low'], df['Close'], ATR_PERIOD)
        df['vol_ma']  = df['Volume'].rolling(VOL_MA_BARS).mean()
        df['vol_rat'] = df['Volume'] / df['vol_ma'].replace(0, np.nan)

        # VWAP resets daily – compute per day
        df['date']  = df.index.date
        df['vwap']  = np.nan
        for day, grp in df.groupby('date'):
            vwap_vals = calc_vwap(grp['High'], grp['Low'], grp['Close'], grp['Volume'])
            df.loc[grp.index, 'vwap'] = vwap_vals.values

        df['prev_close'] = df['Close'].shift(1)
        df['prev_vwap']  = df['vwap'].shift(1)

        trades = []
        # Group by date for session management
        for day, day_df in df.groupby('date'):
            day_df = day_df.copy().reset_index()
            n_trades = 0
            i = VOL_MA_BARS + 2
            while i < len(day_df) - 1 and n_trades < MAX_TRADES_DAY:
                row      = day_df.iloc[i]
                prev_row = day_df.iloc[i - 1]

                close     = float(row['Close'])
                prev_close= float(prev_row['Close'])
                vwap      = float(row['vwap'])
                prev_vwap = float(prev_row['vwap'])
                ema9      = float(row['ema9'])
                rsi       = float(row['rsi'])
                atr       = float(row['atr'])
                vol_rat   = float(row['vol_rat'])

                if any(pd.isna(x) for x in [vwap, ema9, rsi, atr, vol_rat]):
                    i += 1
                    continue

                # Skip if price too high for our capital
                if close > self.capital:
                    i += 1
                    continue

                # ── Entry Signal ──────────────────────────────────
                # Primary: fresh VWAP cross + above EMA + volume
                vwap_cross  = (prev_close < prev_vwap) and (close >= vwap)
                # Secondary: sustained above VWAP + EMA bullish (EMA rising)
                prev_ema9   = float(day_df['ema9'].iloc[i - 1])
                ema_rising  = ema9 > prev_ema9
                above_vwap  = close > vwap
                sustained   = above_vwap and ema_rising and (close > float(day_df['ema9'].iloc[max(0, i-3)]))

                above_ema  = close > ema9
                vol_surge  = vol_rat >= VOL_SURGE
                rsi_ok     = RSI_MIN <= rsi <= RSI_MAX

                signal = (vwap_cross or sustained) and above_ema and vol_surge and rsi_ok

                if signal:
                    entry_price  = close
                    stop_dist    = atr * ATR_STOP_MULT
                    tgt_dist     = atr * ATR_TGT_MULT
                    stop_price   = entry_price - stop_dist
                    target_price = entry_price + tgt_dist

                    if stop_dist <= 0:
                        i += 1
                        continue

                    # Position sizing
                    risk_dollars = self.capital * (self.risk_pct / 100)
                    shares = max(1, int(risk_dollars / stop_dist))
                    cost   = shares * entry_price
                    if cost > self.capital:
                        shares = max(1, int(self.capital / entry_price))
                        cost   = shares * entry_price
                    if shares < 1:
                        i += 1
                        continue

                    entry_time = row['Datetime'] if 'Datetime' in row else row.name
                    exit_price = None
                    exit_time  = None
                    exit_reason= None
                    pnl        = None

                    # ── Scan forward bars for exit ────────────────
                    for j in range(i + 1, len(day_df)):
                        fwd = day_df.iloc[j]
                        fwd_high  = float(fwd['High'])
                        fwd_low   = float(fwd['Low'])
                        fwd_close = float(fwd['Close'])
                        fwd_time  = fwd['Datetime'] if 'Datetime' in fwd else fwd.name

                        is_last_bar = (j == len(day_df) - 1)

                        # Target hit (use High of bar)
                        if fwd_high >= target_price:
                            exit_price  = target_price
                            exit_time   = fwd_time
                            exit_reason = "TARGET"
                            break
                        # Stop hit (use Low of bar)
                        elif fwd_low <= stop_price:
                            exit_price  = stop_price
                            exit_time   = fwd_time
                            exit_reason = "STOP"
                            break
                        # EOD forced exit
                        elif is_last_bar:
                            exit_price  = fwd_close
                            exit_time   = fwd_time
                            exit_reason = "EOD"
                            break

                    if exit_price is None:
                        i += 1
                        continue

                    gross_pnl = (exit_price - entry_price) * shares
                    commission = shares * COMMISSION * 2   # entry + exit
                    net_pnl   = gross_pnl - commission

                    trades.append({
                        'date':        str(day),
                        'ticker':      ticker,
                        'sector':      sector,
                        'entry_time':  str(entry_time),
                        'exit_time':   str(exit_time),
                        'entry':       round(entry_price, 4),
                        'exit':        round(exit_price, 4),
                        'stop':        round(stop_price, 4),
                        'target':      round(target_price, 4),
                        'shares':      shares,
                        'cost':        round(cost, 2),
                        'gross_pnl':   round(gross_pnl, 4),
                        'commission':  round(commission, 4),
                        'net_pnl':     round(net_pnl, 4),
                        'exit_reason': exit_reason,
                        'rsi_entry':   round(rsi, 1),
                        'vol_ratio':   round(vol_rat, 2),
                        'atr':         round(atr, 4),
                    })
                    n_trades += 1

                    # Advance past the trade
                    next_bar = day_df[day_df.index > j].index
                    i = next_bar[0] if len(next_bar) > 0 else len(day_df)
                else:
                    i += 1

        return trades

    # ── Run all tickers ──────────────────────────────────────
    def run(self, tickers=None):
        universe = tickers or UNIVERSE
        all_trades = []

        with self.console.status("[bold green]Downloading 5-min data & backtesting...") as status:
            for ticker, sector in (universe.items() if isinstance(universe, dict) else [(t, "N/A") for t in universe]):
                status.update(f"[bold green]Processing {ticker}...")
                t_trades = self.simulate_ticker(ticker, sector)
                all_trades.extend(t_trades)

        self.trades = all_trades
        self._build_daily_pnl()
        self.report()

    def _build_daily_pnl(self):
        for t in self.trades:
            d = t['date']
            self.daily_pnl[d] = self.daily_pnl.get(d, 0.0) + t['net_pnl']

    # ── Report ───────────────────────────────────────────────
    def report(self):
        c = self.console
        if not self.trades:
            c.print("[bold red]No trades generated. Check data availability or loosen filters.[/bold red]")
            return

        df = pd.DataFrame(self.trades)
        total_trades  = len(df)
        wins          = df[df['net_pnl'] > 0]
        losses        = df[df['net_pnl'] <= 0]
        win_rate      = len(wins) / total_trades * 100
        total_pnl     = df['net_pnl'].sum()
        avg_win       = wins['net_pnl'].mean() if len(wins) else 0
        avg_loss      = losses['net_pnl'].mean() if len(losses) else 0
        profit_factor = (wins['net_pnl'].sum() / abs(losses['net_pnl'].sum())
                         if len(losses) and losses['net_pnl'].sum() != 0 else float('inf'))

        # Equity curve & drawdown
        equity = [self.capital]
        for t in sorted(self.trades, key=lambda x: x['date']):
            equity.append(equity[-1] + t['net_pnl'])
        eq_series = pd.Series(equity)
        peak      = eq_series.cummax()
        drawdown  = (eq_series - peak) / peak * 100
        max_dd    = drawdown.min()
        final_eq  = equity[-1]
        total_ret = (final_eq / self.capital - 1) * 100

        # Exit reason breakdown
        reason_counts = df['exit_reason'].value_counts()

        # ── Summary Panel ───────────────────────────────────
        c.print(Panel.fit(
            f"[bold cyan]INTRADAY BACKTEST RESULTS[/bold cyan]\n"
            f"Capital: [white]${self.capital:.2f}[/white]   "
            f"Risk/Trade: [yellow]{self.risk_pct}%[/yellow]   "
            f"Period: [dim]Last {self.days} days (5-min bars)[/dim]",
            border_style="cyan"
        ))

        # ── Performance Table ───────────────────────────────
        perf = Table(title="Performance Summary", header_style="bold magenta")
        perf.add_column("Metric", style="cyan", width=22)
        perf.add_column("Value", justify="right", width=16)

        ret_color = "green" if total_ret >= 0 else "red"
        dd_color  = "red"

        perf.add_row("Starting Capital",    f"${self.capital:.2f}")
        perf.add_row("Final Equity",        f"[{ret_color}]${final_eq:.2f}[/{ret_color}]")
        perf.add_row("Total Return",        f"[{ret_color}]{total_ret:+.2f}%[/{ret_color}]")
        perf.add_row("Total Net P&L",       f"[{ret_color}]${total_pnl:+.2f}[/{ret_color}]")
        perf.add_row("-" * 22, "-" * 14)
        perf.add_row("Total Trades",        str(total_trades))
        perf.add_row("Wins",                f"[green]{len(wins)}[/green]")
        perf.add_row("Losses",              f"[red]{len(losses)}[/red]")
        perf.add_row("Win Rate",            f"{'[green]' if win_rate >= 50 else '[red]'}{win_rate:.1f}%{'[/green]' if win_rate >= 50 else '[/red]'}")
        perf.add_row("Avg Win",             f"[green]${avg_win:+.2f}[/green]")
        perf.add_row("Avg Loss",            f"[red]${avg_loss:+.2f}[/red]")
        perf.add_row("Profit Factor",       f"{'[green]' if profit_factor >= 1.5 else '[yellow]'}{profit_factor:.2f}{'[/green]' if profit_factor >= 1.5 else '[/yellow]'}")
        perf.add_row("Max Drawdown",        f"[{dd_color}]{max_dd:.2f}%[/{dd_color}]")
        perf.add_row("-" * 22, "-" * 14)
        perf.add_row("Target Exits",        str(reason_counts.get('TARGET', 0)))
        perf.add_row("Stop Exits",          str(reason_counts.get('STOP', 0)))
        perf.add_row("EOD Exits",           str(reason_counts.get('EOD', 0)))
        c.print(perf)

        # ── Ticker Breakdown ────────────────────────────────
        ticker_grp = df.groupby('ticker').agg(
            trades=('net_pnl', 'count'),
            total_pnl=('net_pnl', 'sum'),
            win_rate=('net_pnl', lambda x: (x > 0).mean() * 100),
            avg_pnl=('net_pnl', 'mean')
        ).sort_values('total_pnl', ascending=False)

        tkr = Table(title="Per-Ticker Breakdown", header_style="bold blue")
        tkr.add_column("Ticker",    style="bold white", width=8)
        tkr.add_column("Trades",   justify="right", width=7)
        tkr.add_column("Total P&L",justify="right", width=10)
        tkr.add_column("Win Rate", justify="right", width=9)
        tkr.add_column("Avg P&L",  justify="right", width=9)

        for ticker, row in ticker_grp.iterrows():
            pnl_c = "green" if row['total_pnl'] >= 0 else "red"
            tkr.add_row(
                ticker,
                str(int(row['trades'])),
                f"[{pnl_c}]${row['total_pnl']:+.2f}[/{pnl_c}]",
                f"{row['win_rate']:.0f}%",
                f"${row['avg_pnl']:+.2f}"
            )
        c.print(tkr)

        # ── Daily P&L Table ─────────────────────────────────
        daily_df = pd.Series(self.daily_pnl).sort_index()
        if len(daily_df) > 0:
            daily_tbl = Table(title="Daily P&L Log", header_style="bold cyan")
            daily_tbl.add_column("Date",  width=12)
            daily_tbl.add_column("P&L",   justify="right", width=10)
            daily_tbl.add_column("Bar",   width=30)

            for date, pnl in daily_df.tail(20).items():
                color = "green" if pnl >= 0 else "red"
                bar_len = int(abs(pnl) / max(daily_df.abs().max(), 0.01) * 20)
                bar = ("+" * bar_len) if pnl >= 0 else ("-" * bar_len)
                daily_tbl.add_row(
                    str(date),
                    f"[{color}]${pnl:+.2f}[/{color}]",
                    f"[{color}]{bar}[/{color}]"
                )
            c.print(daily_tbl)

        # ── Recent Trade Log ─────────────────────────────────
        recent = Table(title="Recent 20 Trades", header_style="bold white")
        recent.add_column("Date",   width=11)
        recent.add_column("Ticker", width=6, style="bold")
        recent.add_column("Entry",  justify="right", width=7)
        recent.add_column("Exit",   justify="right", width=7)
        recent.add_column("Shs",    justify="right", width=4)
        recent.add_column("Net P&L",justify="right", width=9)
        recent.add_column("Reason", width=8)
        recent.add_column("RSI",    justify="right", width=5)
        recent.add_column("VolX",   justify="right", width=5)

        sorted_trades = sorted(self.trades, key=lambda x: (x['date'], x['entry_time']))
        for t in sorted_trades[-20:]:
            color = "green" if t['net_pnl'] >= 0 else "red"
            r_color = {"TARGET": "green", "STOP": "red", "EOD": "yellow"}.get(t['exit_reason'], "white")
            recent.add_row(
                t['date'], t['ticker'],
                f"${t['entry']:.2f}", f"${t['exit']:.2f}",
                str(t['shares']),
                f"[{color}]${t['net_pnl']:+.2f}[/{color}]",
                f"[{r_color}]{t['exit_reason']}[/{r_color}]",
                str(t['rsi_entry']),
                f"{t['vol_ratio']:.1f}x"
            )
        c.print(recent)

        # ── Save CSV ─────────────────────────────────────────
        out_path = "intraday_backtest_results.csv"
        df.to_csv(out_path, index=False)
        c.print(f"\n[dim]Full trade log saved -> {out_path}[/dim]")


# ── CLI Entry Point ───────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Intraday Backtest – VWAP+EMA Strategy | $50 Capital"
    )
    parser.add_argument('--capital', type=float, default=50.0,
                        help='Starting capital in USD (default: 50)')
    parser.add_argument('--risk', type=float, default=3.0,
                        help='Risk per trade as %% of capital (default: 3.0)')
    parser.add_argument('--days', type=int, default=30,
                        help='Days of 5-min history to backtest (max 59, default: 30)')
    parser.add_argument('--ticker', type=str, default=None,
                        help='Backtest a single ticker only (e.g. --ticker PLTR)')
    args = parser.parse_args()

    bt = IntradayBacktest(capital=args.capital, risk_pct=args.risk, days=args.days)

    if args.ticker:
        ticker = args.ticker.upper()
        universe = {ticker: UNIVERSE.get(ticker, "Custom")}
        bt.run(tickers=universe)
    else:
        bt.run()


if __name__ == "__main__":
    main()
