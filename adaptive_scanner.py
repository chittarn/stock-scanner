#!/usr/bin/env python3
"""
ADAPTIVE MOMENTUM SCANNER (CLI Version)
- Powered by ScannerEngine
"""

from scanner_engine import ScannerEngine
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint
import pandas as pd

class CLIScanner:
    def __init__(self):
        self.engine = ScannerEngine()
        self.console = Console()

    def run(self):
        rprint(Panel.fit(
            f"[bold cyan]ADAPTIVE MOMENTUM SCANNER[/bold cyan]\n[dim]{self.engine.now.strftime('%Y-%m-%d %I:%M %p IST')}[/dim]",
            border_style="blue"
        ))

        with self.console.status("[bold green]Fetching & Analyzing data..."):
            data = self.engine.get_analysis()

        # 📊 Market Regime Table
        reg_color = "green" if data['regime'] == "BULL" else "yellow" if data['regime'] == "VOLATILE" else "red"
        reg_table = Table(title="Market Regime", box=None)
        reg_table.add_column("Metric", style="cyan")
        reg_table.add_column("Value", style="bold")
        reg_table.add_row("SPY Price", f"${data['spy_price']:.2f}")
        reg_table.add_row("SPY 200 SMA", f"${data['spy_ma']:.2f}")
        reg_table.add_row("Distance", f"{data['dist']:+.2f}%")
        reg_table.add_row("Regime", f"[{reg_color}]{data['regime']}[/{reg_color}]")
        self.console.print(reg_table)

        # 📈 Rankings Table
        n_target = 2 if data['regime'] == "BULL" else 1 if data['regime'] == "VOLATILE" else 0
        sorted_tickers = sorted(data['scores'].items(), key=lambda x: x[1]['score'], reverse=True)
        
        rank_table = Table(title=f"Momentum Rankings (Target Top {n_target})")
        rank_table.add_column("Rank", justify="center")
        rank_table.add_column("Ticker", style="bold")
        rank_table.add_column("Sector", style="dim")
        rank_table.add_column("Conviction", justify="right")
        rank_table.add_column("Price", justify="right")
        rank_table.add_column("Holdings", justify="center")

        top_4 = [t for t, _ in sorted_tickers[:4]]

        for i, (t, d) in enumerate(sorted_tickers, 1):
            is_held = self.engine.config['my_holdings'].get(t, {}).get('qty', 0) > 0
            hold_icon = "[H]" if is_held else ""
            row_style = "bold green" if i <= 2 else "yellow" if i <= 4 else ""
            
            rank_table.add_row(
                str(i), t, d['sector'], f"{d['conviction']:.1f}", 
                f"${d['price']:.2f}", hold_icon,
                style=row_style
            )
        self.console.print(rank_table)

        # 💼 Portfolio Analysis
        port_table = Table(title="Current Portfolio Status")
        port_table.add_column("Ticker")
        port_table.add_column("Value", justify="right")
        port_table.add_column("P&L %", justify="right")
        port_table.add_column("Stop Loss (ATR)", justify="right")
        port_table.add_column("Status", justify="center")

        total_value = 0.0
        total_cost = 0.0
        to_sell = []
        
        for t, h in self.engine.config['my_holdings'].items():
            if h['qty'] <= 0: continue
            
            curr_price = data['prices'][t].iloc[-1]
            val = h['qty'] * curr_price
            cost = h['qty'] * h['avg_cost']
            total_value += val
            total_cost += cost
            pnl_pct = (curr_price / h['avg_cost'] - 1) * 100
            
            # ATR Stop
            curr_atr = data['atr'][t].iloc[-1]
            atr_stop_dist = (self.engine.config['atr_mult'] * curr_atr) / curr_price * 100
            
            status = "[green]KEEP[/green]"
            reason = ""
            
            if data['regime'] == "BEAR":
                status = "[red]SELL[/red]"
                reason = "Bear Market"
            elif pnl_pct < -7: 
                status = "[bold red]STOP[/bold red]"
                reason = "Stop Loss"
            elif t not in top_4:
                status = "[yellow]EXIT[/yellow]"
                reason = "Dropped out of Top 4"
            elif not data['scores'][t]['above_ma200']:
                status = "[yellow]EXIT[/yellow]"
                reason = "Below 200 SMA"
            
            if "SELL" in status or "EXIT" in status or "STOP" in status:
                to_sell.append({'ticker': t, 'qty': h['qty'], 'reason': reason})

            port_table.add_row(
                t, f"${val:.2f}", f"{pnl_pct:+.1f}%", 
                f"-{atr_stop_dist:.1f}%", status
            )
        
        self.console.print(port_table)

        # 📊 Summary
        if total_cost > 0:
            summary_table = Table(title="Portfolio Summary", box=None)
            total_pnl_pct = (total_value / total_cost - 1) * 100
            pnl_color = "green" if total_pnl_pct >= 0 else "red"
            summary_table.add_row("Total Invested", f"${total_cost:.2f}")
            summary_table.add_row("Current Value", f"${total_value:.2f}")
            summary_table.add_row("Overall P&L %", f"[{pnl_color}]{total_pnl_pct:+.2f}%[/{pnl_color}]")
            self.console.print(summary_table)

        # 🎯 Action Plan
        action_panel = []
        if data['regime'] == "BEAR":
            action_panel.append("[bold red]ACTION: SELL EVERYTHING - MARKET IN BEAR REGIME[/bold red]")
        else:
            if to_sell:
                action_panel.append("[bold red]SELL ORDERS:[/bold red]")
                for s in to_sell:
                    action_panel.append(f" - {s['ticker']}: {s['qty']:.4f} shares ({s['reason']})")
            
            target_total = max(total_value, self.engine.config['initial_capital'])
            target_per_stock = target_total / n_target if n_target > 0 else 0
            
            action_panel.append(f"\n[bold green]TARGET ALLOCATION (${target_per_stock:.2f} each):[/bold green]")
            for t_rank in sorted_tickers[:n_target]:
                ticker = t_rank[0]
                is_held = self.engine.config['my_holdings'].get(ticker, {}).get('qty', 0) > 0
                curr_val = self.engine.config['my_holdings'].get(ticker, {}).get('qty', 0) * data['prices'][ticker].iloc[-1] if is_held else 0
                diff = target_per_stock - curr_val
                
                if diff > 5.0:
                    action_panel.append(f" - [bold green]BUY[/bold green] {ticker}: ${diff:.2f} (~{(diff/data['prices'][ticker].iloc[-1]):.4f} shares)")
                elif is_held:
                    action_panel.append(f" - [bold blue]HOLD[/bold blue] {ticker}: (Current value ${curr_val:.2f})")

        if not action_panel:
            action_panel.append("OK: Everything looks good. No trades needed this week.")

        self.console.print(Panel("\n".join(action_panel), title="Weekly Action Plan", border_style="green"))

if __name__ == "__main__":
    scanner = CLIScanner()
    scanner.run()