#!/usr/bin/env python3
"""
ADAPTIVE MOMENTUM BACKTEST (Aligned with Live Scanner)
- Volatility-Adjusted Momentum: (6M*0.6 + 3M*0.4) / annualized_vol
- Regime Detection: SPY vs 200/50 SMA + ATR volatility check
- Hysteresis: Buy Top 2, Sell if > Rank 4
- Trend Filter: Stock must be above 200-day SMA to buy
- Universe: Loaded from config.json (matches live scanner)
- Fees: 0.3% per trade
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import argparse
import json
import os
import warnings
from rich.console import Console
from rich.table import Table

warnings.filterwarnings('ignore')

# Strategy Parameters
DEFAULT_UNIVERSE = ["NVDA", "MSFT", "QQQ", "AMZN", "SMH", "CAT", "XLE", "WMT", "GLD"]
MA_PERIOD = 200
ATR_PERIOD = 14
ATR_MULT = 2.5
FX_FEE = 0.003
MIN_TRADE = 5.0
W6 = 0.6
W3 = 0.4

class AdaptiveBacktest:
    def __init__(self, start_date, end_date=None, initial_capital=300.0, config_path="config.json"):
        self.console = Console()
        self.start = start_date
        # Buffer to calculate MA and Momentum
        buffer_start = datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=300)
        self.data_start = buffer_start.strftime('%Y-%m-%d')
        self.data_end = end_date or datetime.now().strftime('%Y-%m-%d')
        self.display_start = pd.to_datetime(start_date)
        
        # Load universe from config to match live scanner
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
            self.universe = config.get('universe', DEFAULT_UNIVERSE)
            self.console.print(f"[cyan]Loaded universe from {config_path}: {len(self.universe)} tickers[/cyan]")
        else:
            self.universe = DEFAULT_UNIVERSE
            self.console.print(f"[yellow]Config not found, using default universe[/yellow]")
        
        self.capital = initial_capital
        self.cash = initial_capital
        self.holdings = {} # {ticker: {shares, cost}}
        self.trades = []
        self.history = []
        
    def fetch_data(self):
        self.console.print(f"[cyan]Fetch: Data from {self.data_start} to {self.data_end}...[/cyan]")
        symbols = list(set(self.universe + ['SPY']))
        data = yf.download(symbols, start=self.data_start, end=self.data_end, auto_adjust=True, progress=False)
        self.prices = data['Close'].ffill()
        self.high = data['High'].ffill()
        self.low = data['Low'].ffill()
        
        # Precompute indicators (matching live scanner)
        self.spy_ma = self.prices['SPY'].rolling(window=MA_PERIOD).mean()
        self.spy_ma50 = self.prices['SPY'].rolling(window=50).mean()
        self.mas = self.prices.rolling(window=MA_PERIOD).mean()
        
        # ATR Calculation
        self.atrs = pd.DataFrame(index=self.prices.index)
        for t in self.universe:
            if t in self.prices.columns:
                h_l = self.high[t] - self.low[t]
                h_pc = abs(self.high[t] - self.prices[t].shift(1))
                l_pc = abs(self.low[t] - self.prices[t].shift(1))
                tr = pd.concat([h_l, h_pc, l_pc], axis=1).max(axis=1)
                self.atrs[t] = tr.rolling(window=ATR_PERIOD).mean()
        
        # SPY ATR for regime volatility check
        if 'SPY' in self.prices.columns:
            h_l = self.high['SPY'] - self.low['SPY']
            h_pc = abs(self.high['SPY'] - self.prices['SPY'].shift(1))
            l_pc = abs(self.low['SPY'] - self.prices['SPY'].shift(1))
            tr = pd.concat([h_l, h_pc, l_pc], axis=1).max(axis=1)
            self.spy_atr = tr.rolling(window=ATR_PERIOD).mean()
        
        self.console.print(f"[green]OK: Data loaded: {len(self.prices)} days[/green]")

    def get_regime(self, date):
        """Regime detection aligned with live scanner logic."""
        spy_price = self.prices['SPY'].loc[date]
        ma200 = self.spy_ma.loc[date]
        ma50 = self.spy_ma50.loc[date]
        if pd.isna(ma200): return 'BULL'
        
        # Match live scanner: price vs MA comparison (not distance-based)
        if spy_price < ma200:
            regime = 'BEAR'
        elif not pd.isna(ma50) and spy_price < ma50:
            regime = 'VOLATILE'
        else:
            regime = 'BULL'
        
        # ATR volatility check (matches live scanner)
        if hasattr(self, 'spy_atr'):
            idx = self.prices.index.get_loc(date)
            if idx >= 20:
                spy_atr_val = self.spy_atr.iloc[idx]
                if not pd.isna(spy_atr_val):
                    avg_atr = self.spy_atr.iloc[idx-20:idx].mean()
                    if spy_atr_val > avg_atr * 1.5 and regime != 'BEAR':
                        regime = 'VOLATILE'
        
        return regime

    def get_rankings(self, date):
        """Volatility-adjusted momentum scoring aligned with live scanner."""
        idx = self.prices.index.get_loc(date)
        p3m_idx = max(0, idx - 63)
        p6m_idx = max(0, idx - 126)
        
        scores = {}
        for t in self.universe:
            if t in self.prices.columns:
                curr = self.prices[t].loc[date]
                p3m = self.prices[t].iloc[p3m_idx]
                p6m = self.prices[t].iloc[p6m_idx]
                
                ret3m = (curr / p3m - 1) * 100 if p3m > 0 else 0
                ret6m = (curr / p6m - 1) * 100 if p6m > 0 else 0
                raw_score = (ret6m * W6) + (ret3m * W3)
                
                # Volatility-adjusted momentum (matches live scanner)
                start_idx = max(0, idx - 60)
                returns = self.prices[t].iloc[start_idx:idx+1].pct_change().dropna()
                vol = returns.std() * np.sqrt(252) if len(returns) > 1 else 0.01
                vol = max(vol, 0.01)
                score = raw_score / vol
                
                ma = self.mas[t].loc[date]
                above_ma = curr > ma if not pd.isna(ma) else True
                
                # Conviction equals score (matches live scanner)
                conviction = score
                scores[t] = {'score': score, 'above_ma': above_ma, 'conviction': conviction}
        
        sorted_ranks = sorted(scores.items(), key=lambda x: x[1]['conviction'], reverse=True)
        return sorted_ranks # List of (ticker, data)

    def portfolio_value(self, date):
        val = self.cash
        for t, h in self.holdings.items():
            val += h['shares'] * self.prices[t].loc[date]
        return val

    def sell(self, date, ticker, reason):
        if ticker not in self.holdings: return
        price = self.prices[ticker].loc[date]
        shares = self.holdings[ticker]['shares']
        gross = shares * price
        fee = gross * FX_FEE
        net = gross - fee
        cost = self.holdings[ticker]['cost']
        pnl = net - (shares * cost)
        
        self.cash += net
        del self.holdings[ticker]
        self.trades.append({
            'date': date, 'action': 'SELL', 'ticker': ticker,
            'price': price, 'shares': shares, 'pnl': pnl, 
            'pnl_pct': (net / (shares * cost) - 1) * 100 if cost > 0 else 0,
            'reason': reason, 'fee': fee
        })

    def buy(self, date, ticker, amount):
        if amount < MIN_TRADE: return
        price = self.prices[ticker].loc[date]
        fee = amount * FX_FEE
        net = amount - fee
        shares = net / price
        
        if ticker not in self.holdings:
            self.holdings[ticker] = {'shares': 0.0, 'cost': 0.0}
        
        h = self.holdings[ticker]
        total_shares = h['shares'] + shares
        h['cost'] = ((h['shares'] * h['cost']) + (shares * price)) / total_shares if total_shares > 0 else price
        h['shares'] = total_shares
        self.cash -= amount
        self.trades.append({
            'date': date, 'action': 'BUY', 'ticker': ticker,
            'price': price, 'shares': shares, 'fee': fee
        })

    def rebalance(self, date):
        regime = self.get_regime(date)
        if regime == 'BEAR':
            for t in list(self.holdings.keys()):
                self.sell(date, t, 'BEAR_MARKET')
            return

        n_target = 2 if regime == 'BULL' else 1
        rankings = self.get_rankings(date)
        top_2 = [r[0] for r in rankings[:2]]
        top_4 = [r[0] for r in rankings[:4]]
        
        # 1. Stop Loss Check (ATR-based approx or fixed)
        for t in list(self.holdings.keys()):
            price = self.prices[t].loc[date]
            cost = self.holdings[t]['cost']
            # Using 10% hard stop for backtest stability, but ATR-based logic could be added
            if (price / cost - 1) < -0.10: 
                self.sell(date, t, 'STOP_LOSS')

        # 2. Hysteresis Sell: Drop if not in Top 4 OR below 200 SMA
        for t in list(self.holdings.keys()):
            if t not in top_4:
                self.sell(date, t, 'RANK_EXIT')
            else:
                ma = self.mas[t].loc[date]
                if self.prices[t].loc[date] < ma:
                    self.sell(date, t, 'BELOW_SMA')

        # 3. New Buys: If Rank is Top 2 AND Above SMA
        total_val = self.portfolio_value(date)
        target_per_stock = total_val / n_target
        
        for i, (t, d) in enumerate(rankings[:n_target]):
            if d['above_ma']:
                curr_shares = self.holdings.get(t, {}).get('shares', 0)
                curr_val = curr_shares * self.prices[t].loc[date]
                diff = target_per_stock - curr_val
                if diff > MIN_TRADE:
                    self.buy(date, t, diff)

    def run(self):
        self.fetch_data()
        dates = self.prices.index
        # Scan on Fridays
        fridays = dates[dates.dayofweek == 4]
        bench_shares = self.capital / self.prices['SPY'].loc[self.display_start:].iloc[0]
        
        for date in dates:
            val = self.portfolio_value(date)
            bench = bench_shares * self.prices['SPY'].loc[date]
            
            if date >= self.display_start:
                self.history.append({
                    'date': date, 'portfolio': val, 'benchmark': bench,
                    'cash': self.cash, 'positions': len(self.holdings)
                })
            
            if date in fridays and date >= self.display_start:
                self.rebalance(date)
        
        self.report()

    def report(self):
        df = pd.DataFrame(self.history)
        if df.empty: return
        
        final_val = df['portfolio'].iloc[-1]
        final_bench = df['benchmark'].iloc[-1]
        total_ret = (final_val / self.capital - 1) * 100
        bench_ret = (final_bench / self.capital - 1) * 100
        
        table = Table(title="Backtest Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Strategy", justify="right")
        table.add_column("SPY", justify="right")
        table.add_row("Total Return", f"{total_ret:.1f}%", f"{bench_ret:.1f}%")
        table.add_row("Final Value", f"${final_val:.2f}", f"${final_bench:.2f}")
        table.add_row("Trades", str(len(self.trades)), "-")
        
        self.console.print(table)
        
        if len(self.trades) > 0:
            trade_df = pd.DataFrame(self.trades)
            sells = trade_df[trade_df['action'] == 'SELL']
            if not sells.empty:
                win_rate = (sells['pnl'] > 0).sum() / len(sells) * 100
                self.console.print(f"[bold]Win Rate:[/bold] {win_rate:.1f}%")
            
            self.console.print("\n[bold]Recent Trades:[/bold]")
            for _, t in trade_df.tail(10).iterrows():
                color = "green" if t['action'] == "BUY" else "red"
                pnl_str = f" P&L: {t['pnl']:+.2f}" if t['action'] == "SELL" else ""
                self.console.print(f"[{color}]{t['date'].date()} {t['action']} {t['ticker']}[/{color}] @ ${t['price']:.2f}{pnl_str}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', default='2020-01-01')
    parser.add_argument('--capital', type=float, default=300.0)
    parser.add_argument('--config', default='config.json', help='Path to config.json for universe')
    args = parser.parse_args()
    
    bt = AdaptiveBacktest(args.start, initial_capital=args.capital, config_path=args.config)
    bt.run()

if __name__ == "__main__":
    main()