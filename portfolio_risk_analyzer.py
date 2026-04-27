#!/usr/bin/env python3
"""
PORTFOLIO RISK & ACTION ANALYZER v2.0
- Analyzes momentum, risk, and correlation.
- Provides crystal clear Buy/Sell action steps.
- Local high-information version.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import pytz
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns

# ==========================================================
# 🔧 CONFIGURATION (Synced with Scanner)
# ==========================================================
UNIVERSE = ["NVDA", "MSFT", "QQQ", "AMZN", "SMH", "CAT", "XLE", "WMT", "GLD"]
SECTORS = {
    "NVDA": "Semis", "MSFT": "Software", "QQQ": "Index (Tech)",
    "AMZN": "Consumer", "SMH": "Semis", "CAT": "Industrials",
    "XLE": "Energy", "WMT": "Retail", "GLD": "Gold"
}
INITIAL_CAPITAL = 300.0

# 👇 UPDATE YOUR HOLDINGS HERE 👇
MY_HOLDINGS = {
    "NVDA": {"qty": 0.7596353, "avg_cost": 162.35},
    "QQQ":  {"qty": 0.06518589, "avg_cost": 613.63},
    "SMH":  {"qty": 0.04550342, "avg_cost": 439.53},
    "CAT":  {"qty": 0.14455407, "avg_cost": 818.59},
}

class RiskActionAnalyzer:
    def __init__(self):
        self.console = Console()
        self.ist = pytz.timezone('Asia/Kolkata')
        self.now = datetime.now(self.ist)

    def fetch_data(self):
        with self.console.status("[bold green]Analyzing market data..."):
            data = yf.download(UNIVERSE + ['SPY'], period="1y", auto_adjust=True, progress=False)
            close = data['Close'].ffill()
            return close

    def run(self):
        self.console.print(Panel.fit(
            f"[bold cyan]PORTFOLIO RISK & ACTION ANALYZER[/bold cyan]\n[dim]{self.now.strftime('%Y-%m-%d %I:%M %p IST')}[/dim]",
            border_style="blue"
        ))

        prices = self.fetch_data()
        
        # 1. Market Regime
        spy_price = prices['SPY'].iloc[-1]
        spy_ma = prices['SPY'].rolling(window=200).mean().iloc[-1]
        dist = (spy_price / spy_ma - 1) * 100
        regime = "BULL" if dist >= 0 else "VOLATILE" if dist >= -5 else "BEAR"
        
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
        
        scores = {}
        for t in UNIVERSE:
            curr = prices[t].iloc[-1]
            p6m = prices[t].iloc[-min(126, len(prices)-1)]
            p3m = prices[t].iloc[-min(63, len(prices)-1)]
            score = ((curr/p6m - 1) * 0.6 + (curr/p3m - 1) * 0.4) * 100
            ma = prices[t].rolling(window=200).mean().iloc[-1]
            above_ma = curr > ma if not pd.isna(ma) else True
            scores[t] = {"score": score, "price": curr, "above_ma": above_ma}

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
            
            trend = "[green]UP[/]" if d['above_ma'] else "[red]DN[/]"
            rank_table.add_row(str(i), t, SECTORS.get(t, ""), f"{d['score']:.1f}%", trend, marker)
        
        self.console.print(rank_table)

        # 4. Risk Profile Table
        same_sector = SECTORS.get(t1) == SECTORS.get(t2)
        div_score = (1 - max(0, correlation)) * 100
        if same_sector: div_score *= 0.7
        
        risk_table = Table(title=f"Detailed Risk: {t1} vs {t2}")
        risk_table.add_column("Metric")
        risk_table.add_column("Value")
        risk_table.add_column("Impact")
        
        risk_table.add_row("Correlation", f"{correlation:.2f}", "[red]HIGH[/]" if correlation > 0.7 else "[green]LOW[/]")
        risk_table.add_row("Sector Overlap", f"{SECTORS.get(t1)} | {SECTORS.get(t2)}", "[red]MATCH[/]" if same_sector else "[green]NO[/]")
        risk_table.add_row("Diversification Score", f"{div_score:.0f}/100", "[yellow]MODERATE[/]")
        self.console.print(risk_table)

        # 5. CLEAR ACTION PLAN
        total_val = 0.0
        total_cost = 0.0
        to_sell = []
        top_4 = [r[0] for r in sorted_ranks[:4]]
        
        for t, h in MY_HOLDINGS.items():
            if h['qty'] <= 0: continue
            curr_p = prices[t].iloc[-1]
            total_val += h['qty'] * curr_p
            total_cost += h['qty'] * h['avg_cost']
            if regime == "BEAR" or t not in top_4 or not scores[t]['above_ma']:
                to_sell.append(t)

        target_total = max(total_val, INITIAL_CAPITAL)
        n_target = 2 if regime == "BULL" else 1 if regime == "VOLATILE" else 0
        target_per = target_total / n_target if n_target > 0 else 0

        action_text = []
        if regime == "BEAR":
            action_text.append("[bold red]ACTION: SELL EVERYTHING.[/bold red] Market in Bear Regime.")
        else:
            if to_sell:
                action_text.append("[bold red]SELL ORDERS:[/bold red]")
                for s in to_sell:
                    action_text.append(f" - [bold]{s}[/bold]: Exit completely. (Reason: Dropped from Top 4 or Trend DN)")
            
            action_text.append(f"\n[bold green]BUY / TOP-UP ORDERS (Target ${target_per:.2f} ea):[/bold green]")
            for t in [r[0] for r in sorted_ranks[:n_target]]:
                curr_shares = MY_HOLDINGS.get(t, {}).get('qty', 0)
                curr_v = curr_shares * prices[t].iloc[-1]
                diff = target_per - curr_v
                if diff > 5.0:
                    action_text.append(f" - [bold]BUY {t}[/bold]: Invest [green]${diff:.2f}[/] (~{(diff/prices[t].iloc[-1]):.4f} shares)")
                else:
                    action_text.append(f" - [bold]HOLD {t}[/bold]: Position already sized correctly.")

            if div_score < 40:
                action_text.append(f"\n[bold yellow]RISK TIP:[/bold yellow] {t1} and {t2} are moving together. If you want more safety, buy {t3} instead of {t2}.")

        self.console.print(Panel("\n".join(action_text), title="FINAL WEEKLY ACTION PLAN", border_style="green"))

if __name__ == "__main__":
    analyzer = RiskActionAnalyzer()
    analyzer.run()
