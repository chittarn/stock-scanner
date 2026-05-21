#!/usr/bin/env python3
"""
PORTFOLIO RISK & ACTION ANALYZER v2.0
- Analyzes momentum, risk, and correlation.
- Provides crystal clear Buy/Sell action steps.
- Dynamic version powered by ScannerEngine.
"""

from scanner_engine import ScannerEngine
import pandas as pd
import numpy as np
from datetime import datetime
import pytz
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns

class RiskActionAnalyzer:
    def __init__(self):
        self.engine = ScannerEngine()
        self.console = Console()
        self.ist = pytz.timezone('Asia/Kolkata')
        self.now = datetime.now(self.ist)

    def run(self):
        self.console.print(Panel.fit(
            f"[bold cyan]PORTFOLIO RISK & ACTION ANALYZER[/bold cyan]\n[dim]{self.now.strftime('%Y-%m-%d %I:%M %p IST')}[/dim]",
            border_style="blue"
        ))

        # Fetch dynamic scanner analysis
        data = self.engine.get_analysis()
        prices = data['prices']
        regime = data['regime']
        spy_price = data['spy_price']
        spy_ma = data['spy_ma']
        dist = data['dist']
        scores = data['scores']
        atr = data['atr']

        # 1. Market Regime
        reg_table = Table(title="Market Regime", box=None)
        reg_table.add_column("Metric", style="cyan")
        reg_table.add_column("Value")
        reg_table.add_row("SPY Price", f"${spy_price:.2f}")
        reg_table.add_row("Distance from 200 SMA", f"{dist:+.2f}%")
        reg_table.add_row("Regime", f"[bold {'green' if regime=='BULL' else 'red'}]{regime}[/]")
        self.console.print(reg_table)

        # 2. Momentum & Correlation
        returns = prices.pct_change().dropna()
        corr_matrix = returns.tail(60).corr() # 3-month correlation

        sorted_ranks = sorted(scores.items(), key=lambda x: x[1]['score'], reverse=True)
        t1, t2 = sorted_ranks[0][0], sorted_ranks[1][0]
        t3 = sorted_ranks[2][0]
        correlation = corr_matrix.loc[t1, t2]

        # 3. Rankings Table
        rank_table = Table(title="Momentum Rankings & Risk Context")
        rank_table.add_column("Rank", justify="center")
        rank_table.add_column("Ticker", style="bold")
        rank_table.add_column("Sector", style="dim")
        rank_table.add_column("Score", justify="right")
        rank_table.add_column("Trend", justify="center")
        rank_table.add_column("Risk Marker", justify="center")

        for i, (t, d) in enumerate(sorted_ranks[:5], 1):
            marker = ""
            if i == 2 and correlation > 0.7: marker = "[red]HIGH CORR[/red]"
            elif i == 2: marker = "[green]OK[/green]"
            
            trend = "[green]UP[/]" if d['above_ma200'] else "[red]DN[/]"
            rank_table.add_row(str(i), t, d['sector'], f"{d['score']:.1f}%", trend, marker)
        
        self.console.print(rank_table)

        # 4. Risk Profile Table
        same_sector = scores[t1]['sector'] == scores[t2]['sector']
        div_score = (1 - max(0, correlation)) * 100
        if same_sector: div_score *= 0.7
        
        risk_table = Table(title=f"Detailed Risk: {t1} vs {t2}")
        risk_table.add_column("Metric")
        risk_table.add_column("Value")
        risk_table.add_column("Impact")
        
        risk_table.add_row("Correlation", f"{correlation:.2f}", "[red]HIGH[/]" if correlation > 0.7 else "[green]LOW[/]")
        risk_table.add_row("Sector Overlap", f"{scores[t1]['sector']} | {scores[t2]['sector']}", "[red]MATCH[/]" if same_sector else "[green]NO[/]")
        risk_table.add_row("Diversification Score", f"{div_score:.0f}/100", "[yellow]MODERATE[/]")
        self.console.print(risk_table)

        # 5. CLEAR ACTION PLAN
        total_val = 0.0
        total_cost = 0.0
        to_sell = []
        
        n_target = 2 if regime == "BULL" else 1 if regime == "VOLATILE" else 0
        top_targets = [t for t, _ in sorted_ranks[:n_target]]
        
        for t, h in self.engine.config['my_holdings'].items():
            if h['qty'] <= 0: continue
            
            curr_price = scores.get(t, {}).get('price')
            if curr_price is None or pd.isna(curr_price):
                curr_price = prices[t].dropna().iloc[-1] if (t in prices.columns and len(prices[t].dropna()) > 0) else h['avg_cost']
                
            val = h['qty'] * curr_price
            cost = h['qty'] * h['avg_cost']
            total_val += val
            total_cost += cost
            pnl_pct = (curr_price / h['avg_cost'] - 1) * 100
            
            # ATR Stop
            curr_atr = atr[t].iloc[-1]
            atr_stop_dist = (self.engine.config['atr_mult'] * curr_atr) / curr_price * 100
            
            reason = ""
            if regime == "BEAR":
                reason = "Bear Market"
            elif pnl_pct < -atr_stop_dist:
                reason = f"Stop Loss (ATR: -{atr_stop_dist:.1f}%)"
            elif t not in top_targets:
                reason = f"Out of Top {n_target}"
            elif not scores[t]['above_ma200']:
                reason = "Below 200 SMA"
                
            if reason:
                to_sell.append((t, reason))

        target_total = max(total_val, self.engine.config['initial_capital'])
        target_per = target_total / n_target if n_target > 0 else 0

        action_text = []
        if regime == "BEAR":
            action_text.append("[bold red]ACTION: SELL EVERYTHING.[/bold red] Market in Bear Regime.")
        else:
            if to_sell:
                action_text.append("[bold red]SELL ORDERS:[/bold red]")
                for s, r in to_sell:
                    action_text.append(f" - [bold]{s}[/bold]: Exit completely. (Reason: {r})")
            
            action_text.append(f"\n[bold green]BUY / TOP-UP ORDERS (Target ${target_per:.2f} ea):[/bold green]")
            
            # Find the top targets, excluding anything that triggered a sell signal today
            to_sell_tickers = [s[0] for s in to_sell]
            buy_candidates = [t for t in sorted_ranks if t[0] not in to_sell_tickers][:n_target]
            
            for t_rank in buy_candidates:
                ticker = t_rank[0]
                is_held = self.engine.config['my_holdings'].get(ticker, {}).get('qty', 0) > 0
                curr_v = self.engine.config['my_holdings'].get(ticker, {}).get('qty', 0) * prices[ticker].iloc[-1] if is_held else 0
                diff = target_per - curr_v
                
                if not is_held:
                    action_text.append(f" - [bold]BUY {ticker}[/bold]: Invest [green]${target_per:.2f}[/] (~{(target_per/prices[ticker].iloc[-1]):.4f} shares)")
                elif diff > max(5.0, target_per * 0.10):
                    action_text.append(f" - [bold]BUY (Add) {ticker}[/bold]: Invest [green]${diff:.2f}[/] (~{(diff/prices[ticker].iloc[-1]):.4f} shares)")
                else:
                    action_text.append(f" - [bold]HOLD {ticker}[/bold]: Position already sized correctly.")

            if div_score < 40:
                action_text.append(f"\n[bold yellow]RISK TIP:[/bold yellow] {t1} and {t2} are moving together. If you want more safety, buy {t3} instead of {t2}.")

        self.console.print(Panel("\n".join(action_text), title="FINAL WEEKLY ACTION PLAN", border_style="green"))

if __name__ == "__main__":
    analyzer = RiskActionAnalyzer()
    analyzer.run()

